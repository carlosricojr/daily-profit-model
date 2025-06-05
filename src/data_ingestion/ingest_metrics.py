"""
Ingest metrics data from the /metrics API endpoints (alltime, daily, hourly).
Stores data in the respective raw_metrics_* tables.
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


class MetricsIngester:
    """Handles ingestion of metrics data from the API."""
    
    def __init__(self):
        """Initialize the metrics ingester."""
        self.db_manager = get_db_manager()
        self.api_client = RiskAnalyticsAPIClient()
        
        # Table mapping for different metric types
        self.table_mapping = {
            'alltime': 'raw_metrics_alltime',
            'daily': 'raw_metrics_daily',
            'hourly': 'raw_metrics_hourly'
        }
    
    def ingest_metrics(self,
                      metric_type: str,
                      start_date: Optional[date] = None,
                      end_date: Optional[date] = None,
                      logins: Optional[List[str]] = None,
                      accountids: Optional[List[str]] = None,
                      force_full_refresh: bool = False) -> int:
        """
        Ingest metrics data from the API.
        
        Args:
            metric_type: Type of metrics ('alltime', 'daily', 'hourly')
            start_date: Start date for daily/hourly metrics
            end_date: End date for daily/hourly metrics
            logins: Optional list of specific login IDs
            accountids: Optional list of specific account IDs
            force_full_refresh: If True, truncate existing data and reload
            
        Returns:
            Number of records ingested
        """
        if metric_type not in self.table_mapping:
            raise ValueError(f"Invalid metric type: {metric_type}")
        
        table_name = self.table_mapping[metric_type]
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f'ingest_metrics_{metric_type}',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Handle full refresh
            if force_full_refresh:
                logger.warning(f"Force full refresh requested for {metric_type}. Truncating existing data.")
                self.db_manager.model_db.execute_command(f"TRUNCATE TABLE {table_name}")
            
            # Ingest based on metric type
            if metric_type == 'alltime':
                total_records = self._ingest_alltime_metrics(
                    table_name, logins, accountids
                )
            else:
                total_records = self._ingest_time_series_metrics(
                    metric_type, table_name, start_date, end_date, 
                    logins, accountids
                )
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f'ingest_metrics_{metric_type}',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'start_date': str(start_date) if start_date else None,
                    'end_date': str(end_date) if end_date else None,
                    'force_full_refresh': force_full_refresh
                }
            )
            
            logger.info(f"Successfully ingested {total_records} {metric_type} metric records")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f'ingest_metrics_{metric_type}',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to ingest {metric_type} metrics: {str(e)}")
            raise
    
    def _ingest_alltime_metrics(self,
                               table_name: str,
                               logins: Optional[List[str]],
                               accountids: Optional[List[str]]) -> int:
        """Ingest all-time metrics data."""
        batch_data = []
        batch_size = 1000
        total_records = 0
        
        logger.info("Starting all-time metrics ingestion...")
        
        for page_num, metrics_page in enumerate(self.api_client.get_metrics(
            metric_type='alltime',
            logins=logins,
            accountids=accountids
        )):
            logger.info(f"Processing page {page_num + 1} with {len(metrics_page)} metrics")
            
            for metric in metrics_page:
                record = self._transform_alltime_metric(metric)
                batch_data.append(record)
                
                if len(batch_data) >= batch_size:
                    self._insert_metrics_batch(batch_data, table_name)
                    total_records += len(batch_data)
                    batch_data = []
        
        # Insert remaining records
        if batch_data:
            self._insert_metrics_batch(batch_data, table_name)
            total_records += len(batch_data)
        
        return total_records
    
    def _ingest_time_series_metrics(self,
                                  metric_type: str,
                                  table_name: str,
                                  start_date: Optional[date],
                                  end_date: Optional[date],
                                  logins: Optional[List[str]],
                                  accountids: Optional[List[str]]) -> int:
        """Ingest daily or hourly metrics data."""
        # Determine date range
        if not end_date:
            end_date = datetime.now().date() - timedelta(days=1)  # Yesterday
        if not start_date:
            # Default to last 30 days for initial load
            start_date = end_date - timedelta(days=30)
        
        batch_data = []
        batch_size = 1000
        total_records = 0
        
        # Process date by date to manage volume (especially for hourly)
        current_date = start_date
        while current_date <= end_date:
            date_str = self.api_client.format_date(current_date)
            logger.info(f"Processing {metric_type} metrics for date: {date_str}")
            
            # For hourly metrics, we might want to specify hours
            hours = list(range(24)) if metric_type == 'hourly' else None
            
            for page_num, metrics_page in enumerate(self.api_client.get_metrics(
                metric_type=metric_type,
                logins=logins,
                accountids=accountids,
                dates=[date_str],
                hours=hours
            )):
                logger.debug(f"Date {date_str}, page {page_num + 1}: {len(metrics_page)} records")
                
                for metric in metrics_page:
                    if metric_type == 'daily':
                        record = self._transform_daily_metric(metric)
                    else:  # hourly
                        record = self._transform_hourly_metric(metric)
                    
                    batch_data.append(record)
                    
                    if len(batch_data) >= batch_size:
                        self._insert_metrics_batch(batch_data, table_name)
                        total_records += len(batch_data)
                        batch_data = []
            
            current_date += timedelta(days=1)
        
        # Insert remaining records
        if batch_data:
            self._insert_metrics_batch(batch_data, table_name)
            total_records += len(batch_data)
        
        return total_records
    
    def _transform_alltime_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform all-time metric record for database."""
        return {
            'account_id': metric.get('accountId'),
            'login': metric.get('login'),
            'net_profit': metric.get('netProfit'),
            'gross_profit': metric.get('grossProfit'),
            'gross_loss': metric.get('grossLoss'),
            'total_trades': metric.get('totalTrades'),
            'winning_trades': metric.get('winningTrades'),
            'losing_trades': metric.get('losingTrades'),
            'win_rate': metric.get('winRate'),
            'profit_factor': metric.get('profitFactor'),
            'average_win': metric.get('averageWin'),
            'average_loss': metric.get('averageLoss'),
            'average_rrr': metric.get('averageRRR'),
            'expectancy': metric.get('expectancy'),
            'sharpe_ratio': metric.get('sharpeRatio'),
            'sortino_ratio': metric.get('sortinoRatio'),
            'max_drawdown': metric.get('maxDrawdown'),
            'max_drawdown_pct': metric.get('maxDrawdownPct'),
            'ingestion_timestamp': datetime.now(),
            'source_api_endpoint': '/v2/metrics/alltime'
        }
    
    def _transform_daily_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform daily metric record for database."""
        # Parse date from YYYYMMDD format
        date_str = str(metric.get('date', ''))
        if date_str and len(date_str) == 8:
            metric_date = datetime.strptime(date_str, '%Y%m%d').date()
        else:
            metric_date = None
        
        return {
            'account_id': metric.get('accountId'),
            'login': metric.get('login'),
            'date': metric_date,
            'net_profit': metric.get('netProfit'),  # TARGET VARIABLE
            'gross_profit': metric.get('grossProfit'),
            'gross_loss': metric.get('grossLoss'),
            'total_trades': metric.get('totalTrades'),
            'winning_trades': metric.get('winningTrades'),
            'losing_trades': metric.get('losingTrades'),
            'win_rate': metric.get('winRate'),
            'profit_factor': metric.get('profitFactor'),
            'lots_traded': metric.get('lotsTraded'),
            'volume_traded': metric.get('volumeTraded'),
            'commission': metric.get('commission'),
            'swap': metric.get('swap'),
            'balance_start': metric.get('balanceStart'),
            'balance_end': metric.get('balanceEnd'),
            'equity_start': metric.get('equityStart'),
            'equity_end': metric.get('equityEnd'),
            'ingestion_timestamp': datetime.now(),
            'source_api_endpoint': '/v2/metrics/daily'
        }
    
    def _transform_hourly_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform hourly metric record for database."""
        # Parse date from YYYYMMDD format
        date_str = str(metric.get('date', ''))
        if date_str and len(date_str) == 8:
            metric_date = datetime.strptime(date_str, '%Y%m%d').date()
        else:
            metric_date = None
        
        return {
            'account_id': metric.get('accountId'),
            'login': metric.get('login'),
            'date': metric_date,
            'hour': metric.get('hour'),
            'net_profit': metric.get('netProfit'),
            'gross_profit': metric.get('grossProfit'),
            'gross_loss': metric.get('grossLoss'),
            'total_trades': metric.get('totalTrades'),
            'winning_trades': metric.get('winningTrades'),
            'losing_trades': metric.get('losingTrades'),
            'win_rate': metric.get('winRate'),
            'lots_traded': metric.get('lotsTraded'),
            'volume_traded': metric.get('volumeTraded'),
            'ingestion_timestamp': datetime.now(),
            'source_api_endpoint': '/v2/metrics/hourly'
        }
    
    def _insert_metrics_batch(self, batch_data: List[Dict[str, Any]], table_name: str):
        """Insert a batch of metric records into the database."""
        if not batch_data:
            return
        
        try:
            # Build the insert query with ON CONFLICT
            columns = list(batch_data[0].keys())
            placeholders = ', '.join(['%s'] * len(columns))
            columns_str = ', '.join(columns)
            
            # Determine conflict columns based on table
            if 'alltime' in table_name:
                conflict_cols = 'account_id, ingestion_timestamp'
            elif 'daily' in table_name:
                conflict_cols = 'account_id, date, ingestion_timestamp'
            else:  # hourly
                conflict_cols = 'account_id, date, hour, ingestion_timestamp'
            
            query = f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_cols}) DO NOTHING
            """
            
            # Convert to list of tuples
            values = [tuple(record[col] for col in columns) for record in batch_data]
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(query, values)
            
            logger.debug(f"Inserted batch of {len(batch_data)} records into {table_name}")
            
        except Exception as e:
            logger.error(f"Failed to insert batch into {table_name}: {str(e)}")
            raise
    
    def close(self):
        """Clean up resources."""
        self.api_client.close()


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Ingest metrics data from Risk Analytics API')
    parser.add_argument('metric_type', choices=['alltime', 'daily', 'hourly'],
                       help='Type of metrics to ingest')
    parser.add_argument('--start-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Start date for daily/hourly metrics (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='End date for daily/hourly metrics (YYYY-MM-DD)')
    parser.add_argument('--logins', nargs='+', help='Specific login IDs to fetch')
    parser.add_argument('--accountids', nargs='+', help='Specific account IDs to fetch')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Force full refresh (truncate and reload)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file=f'ingest_metrics_{args.metric_type}')
    
    # Run ingestion
    ingester = MetricsIngester()
    try:
        records = ingester.ingest_metrics(
            metric_type=args.metric_type,
            start_date=args.start_date,
            end_date=args.end_date,
            logins=args.logins,
            accountids=args.accountids,
            force_full_refresh=args.force_refresh
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    finally:
        ingester.close()


if __name__ == '__main__':
    main()