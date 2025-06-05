"""
Ingest trades data from the /trades API endpoints (closed and open).
Handles the large volume of closed trades (81M records) efficiently.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import argparse

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.api_client import RiskAnalyticsAPIClient
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class TradesIngester:
    """Handles ingestion of trades data from the API."""
    
    def __init__(self):
        """Initialize the trades ingester."""
        self.db_manager = get_db_manager()
        self.api_client = RiskAnalyticsAPIClient()
        
        # Table mapping for trade types
        self.table_mapping = {
            'closed': 'raw_trades_closed',
            'open': 'raw_trades_open'
        }
    
    def ingest_trades(self,
                     trade_type: str,
                     start_date: Optional[date] = None,
                     end_date: Optional[date] = None,
                     logins: Optional[List[str]] = None,
                     symbols: Optional[List[str]] = None,
                     batch_days: int = 7,
                     force_full_refresh: bool = False) -> int:
        """
        Ingest trades data from the API.
        
        Args:
            trade_type: Type of trades ('closed' or 'open')
            start_date: Start date for trade ingestion
            end_date: End date for trade ingestion
            logins: Optional list of specific login IDs
            symbols: Optional list of specific symbols
            batch_days: Number of days to process at once (for closed trades)
            force_full_refresh: If True, truncate existing data and reload
            
        Returns:
            Number of records ingested
        """
        if trade_type not in self.table_mapping:
            raise ValueError(f"Invalid trade type: {trade_type}")
        
        table_name = self.table_mapping[trade_type]
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f'ingest_trades_{trade_type}',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Handle full refresh
            if force_full_refresh:
                logger.warning(f"Force full refresh requested for {trade_type} trades. Truncating existing data.")
                self.db_manager.model_db.execute_command(f"TRUNCATE TABLE {table_name}")
            
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)  # Yesterday
            if not start_date:
                if trade_type == 'open':
                    # For open trades, we only need recent data
                    start_date = end_date
                else:
                    # For closed trades, default to last 30 days for initial load
                    start_date = end_date - timedelta(days=30)
            
            # Ingest trades
            if trade_type == 'closed':
                total_records = self._ingest_closed_trades(
                    table_name, start_date, end_date, logins, symbols, batch_days
                )
            else:
                total_records = self._ingest_open_trades(
                    table_name, start_date, end_date, logins, symbols
                )
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f'ingest_trades_{trade_type}',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'batch_days': batch_days if trade_type == 'closed' else None,
                    'force_full_refresh': force_full_refresh
                }
            )
            
            logger.info(f"Successfully ingested {total_records} {trade_type} trade records")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f'ingest_trades_{trade_type}',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to ingest {trade_type} trades: {str(e)}")
            raise
    
    def _ingest_closed_trades(self,
                            table_name: str,
                            start_date: date,
                            end_date: date,
                            logins: Optional[List[str]],
                            symbols: Optional[List[str]],
                            batch_days: int) -> int:
        """
        Ingest closed trades data in date batches to handle large volume.
        
        Critical: 81M records require careful handling
        """
        batch_data = []
        batch_size = 5000  # Larger batch for closed trades
        total_records = 0
        
        # Process in date chunks to manage volume
        current_start = start_date
        while current_start <= end_date:
            current_end = min(current_start + timedelta(days=batch_days - 1), end_date)
            
            logger.info(f"Processing closed trades from {current_start} to {current_end}")
            
            # Format dates for API
            start_str = self.api_client.format_date(current_start)
            end_str = self.api_client.format_date(current_end)
            
            # Fetch trades for this date range
            for page_num, trades_page in enumerate(self.api_client.get_trades(
                trade_type='closed',
                logins=logins,
                symbols=symbols,
                trade_date_from=start_str,
                trade_date_to=end_str
            )):
                if page_num % 10 == 0:  # Log progress every 10 pages
                    logger.info(f"Processing page {page_num + 1} for dates {start_str}-{end_str}")
                
                for trade in trades_page:
                    record = self._transform_closed_trade(trade)
                    batch_data.append(record)
                    
                    if len(batch_data) >= batch_size:
                        self._insert_trades_batch(batch_data, table_name)
                        total_records += len(batch_data)
                        batch_data = []
                        
                        # Log progress for large datasets
                        if total_records % 50000 == 0:
                            logger.info(f"Progress: {total_records:,} records processed")
            
            # Move to next date batch
            current_start = current_end + timedelta(days=1)
        
        # Insert remaining records
        if batch_data:
            self._insert_trades_batch(batch_data, table_name)
            total_records += len(batch_data)
        
        return total_records
    
    def _ingest_open_trades(self,
                          table_name: str,
                          start_date: date,
                          end_date: date,
                          logins: Optional[List[str]],
                          symbols: Optional[List[str]]) -> int:
        """Ingest open trades data (typically much smaller volume)."""
        batch_data = []
        batch_size = 1000
        total_records = 0
        
        # For open trades, we typically only need the latest snapshot
        logger.info(f"Processing open trades for {end_date}")
        
        # Format date for API
        date_str = self.api_client.format_date(end_date)
        
        for page_num, trades_page in enumerate(self.api_client.get_trades(
            trade_type='open',
            logins=logins,
            symbols=symbols,
            trade_date_from=date_str,
            trade_date_to=date_str
        )):
            logger.info(f"Processing page {page_num + 1} with {len(trades_page)} open trades")
            
            for trade in trades_page:
                record = self._transform_open_trade(trade)
                batch_data.append(record)
                
                if len(batch_data) >= batch_size:
                    self._insert_trades_batch(batch_data, table_name)
                    total_records += len(batch_data)
                    batch_data = []
        
        # Insert remaining records
        if batch_data:
            self._insert_trades_batch(batch_data, table_name)
            total_records += len(batch_data)
        
        return total_records
    
    def _transform_closed_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Transform closed trade record for database."""
        # Parse timestamps
        open_time = self._parse_timestamp(trade.get('openTime'))
        close_time = self._parse_timestamp(trade.get('closeTime'))
        
        # Parse trade date from YYYYMMDD format
        trade_date_str = str(trade.get('tradeDate', ''))
        if trade_date_str and len(trade_date_str) == 8:
            trade_date = datetime.strptime(trade_date_str, '%Y%m%d').date()
        else:
            trade_date = None
        
        return {
            'trade_id': trade.get('tradeId'),
            'account_id': trade.get('accountId'),
            'login': trade.get('login'),
            'symbol': trade.get('symbol'),
            'std_symbol': trade.get('stdSymbol'),
            'side': trade.get('side'),
            'open_time': open_time,
            'close_time': close_time,
            'trade_date': trade_date,
            'open_price': trade.get('openPrice'),
            'close_price': trade.get('closePrice'),
            'stop_loss': trade.get('stopLoss'),
            'take_profit': trade.get('takeProfit'),
            'lots': trade.get('lots'),
            'volume_usd': trade.get('volumeUSD'),
            'profit': trade.get('profit'),
            'commission': trade.get('commission'),
            'swap': trade.get('swap'),
            'ingestion_timestamp': datetime.now(),
            'source_api_endpoint': '/v2/trades/closed'
        }
    
    def _transform_open_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Transform open trade record for database."""
        # Parse timestamps
        open_time = self._parse_timestamp(trade.get('openTime'))
        
        # Parse trade date
        trade_date_str = str(trade.get('tradeDate', ''))
        if trade_date_str and len(trade_date_str) == 8:
            trade_date = datetime.strptime(trade_date_str, '%Y%m%d').date()
        else:
            trade_date = None
        
        return {
            'trade_id': trade.get('tradeId'),
            'account_id': trade.get('accountId'),
            'login': trade.get('login'),
            'symbol': trade.get('symbol'),
            'std_symbol': trade.get('stdSymbol'),
            'side': trade.get('side'),
            'open_time': open_time,
            'trade_date': trade_date,
            'open_price': trade.get('openPrice'),
            'current_price': trade.get('currentPrice'),
            'stop_loss': trade.get('stopLoss'),
            'take_profit': trade.get('takeProfit'),
            'lots': trade.get('lots'),
            'volume_usd': trade.get('volumeUSD'),
            'unrealized_pnl': trade.get('unrealizedPnL'),
            'commission': trade.get('commission'),
            'swap': trade.get('swap'),
            'ingestion_timestamp': datetime.now(),
            'source_api_endpoint': '/v2/trades/open'
        }
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse various timestamp formats from the API."""
        if not timestamp_str:
            return None
        
        # Try different formats
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y%m%d%H%M%S'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
        
        logger.warning(f"Could not parse timestamp: {timestamp_str}")
        return None
    
    def _insert_trades_batch(self, batch_data: List[Dict[str, Any]], table_name: str):
        """Insert a batch of trade records into the database."""
        if not batch_data:
            return
        
        try:
            # Build the insert query
            columns = list(batch_data[0].keys())
            placeholders = ', '.join(['%s'] * len(columns))
            columns_str = ', '.join(columns)
            
            query = f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            """
            
            # Note: For trades, we don't use ON CONFLICT as trade_id should be unique
            # If duplicates occur, it's better to know about them
            
            # Convert to list of tuples
            values = [tuple(record[col] for col in columns) for record in batch_data]
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(query, values)
            
            logger.debug(f"Inserted batch of {len(batch_data)} records into {table_name}")
            
        except Exception as e:
            logger.error(f"Failed to insert batch into {table_name}: {str(e)}")
            # Log sample of problematic data for debugging
            if batch_data:
                logger.error(f"Sample record: {batch_data[0]}")
            raise
    
    def close(self):
        """Clean up resources."""
        self.api_client.close()


def ingest_trades_closed(**kwargs):
    """Convenience function for backward compatibility."""
    ingester = TradesIngester()
    try:
        return ingester.ingest_trades(trade_type='closed', **kwargs)
    finally:
        ingester.close()


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Ingest trades data from Risk Analytics API')
    parser.add_argument('trade_type', choices=['closed', 'open'],
                       help='Type of trades to ingest')
    parser.add_argument('--start-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Start date for trades (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='End date for trades (YYYY-MM-DD)')
    parser.add_argument('--logins', nargs='+', help='Specific login IDs to fetch')
    parser.add_argument('--symbols', nargs='+', help='Specific symbols to fetch')
    parser.add_argument('--batch-days', type=int, default=7,
                       help='Number of days to process at once for closed trades')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Force full refresh (truncate and reload)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file=f'ingest_trades_{args.trade_type}')
    
    # Run ingestion
    ingester = TradesIngester()
    try:
        records = ingester.ingest_trades(
            trade_type=args.trade_type,
            start_date=args.start_date,
            end_date=args.end_date,
            logins=args.logins,
            symbols=args.symbols,
            batch_days=args.batch_days,
            force_full_refresh=args.force_refresh
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    finally:
        ingester.close()


if __name__ == '__main__':
    main()