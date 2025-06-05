"""
Ingest regimes_daily data from the Supabase public.regimes_daily table.
Stores data in the raw_regimes_daily table.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
import argparse
import json
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class RegimesIngester:
    """Handles ingestion of regimes_daily data from Supabase."""
    
    def __init__(self):
        """Initialize the regimes ingester."""
        self.db_manager = get_db_manager()
        self.table_name = 'raw_regimes_daily'
        
    def ingest_regimes(self,
                      start_date: Optional[date] = None,
                      end_date: Optional[date] = None,
                      force_full_refresh: bool = False) -> int:
        """
        Ingest regimes_daily data from the source Supabase table.
        
        Args:
            start_date: Start date for regime data
            end_date: End date for regime data
            force_full_refresh: If True, truncate existing data and reload all
            
        Returns:
            Number of records ingested
        """
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_regimes',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Handle full refresh
            if force_full_refresh:
                logger.warning("Force full refresh requested for regimes. Truncating existing data.")
                self.db_manager.model_db.execute_command(f"TRUNCATE TABLE {self.table_name}")
            
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)  # Yesterday
            if not start_date:
                if force_full_refresh:
                    # For full refresh, go back further
                    start_date = end_date - timedelta(days=365)  # Last year
                else:
                    # For incremental, default to last 30 days
                    start_date = end_date - timedelta(days=30)
            
            # Query source data
            logger.info(f"Querying regimes_daily from {start_date} to {end_date}")
            
            query = """
            SELECT 
                date,
                market_news,
                instruments,
                country_economic_indicators,
                news_analysis,
                summary,
                vector_daily_regime,
                created_at,
                updated_at
            FROM public.regimes_daily
            WHERE date >= %s AND date <= %s
            ORDER BY date
            """
            
            # Fetch data from source database
            with self.db_manager.source_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (start_date, end_date))
                    
                    # Process in batches to handle large datasets
                    batch_size = 100
                    batch_data = []
                    
                    while True:
                        rows = cursor.fetchmany(batch_size)
                        if not rows:
                            break
                        
                        # Transform rows
                        for row in rows:
                            record = self._transform_regime_record(row)
                            batch_data.append(record)
                        
                        # Insert batch when full
                        if len(batch_data) >= batch_size:
                            self._insert_regimes_batch(batch_data)
                            total_records += len(batch_data)
                            batch_data = []
                            
                            # Log progress
                            if total_records % 1000 == 0:
                                logger.info(f"Progress: {total_records} records processed")
                    
                    # Insert remaining records
                    if batch_data:
                        self._insert_regimes_batch(batch_data)
                        total_records += len(batch_data)
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_regimes',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'force_full_refresh': force_full_refresh
                }
            )
            
            logger.info(f"Successfully ingested {total_records} regime records")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_regimes',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to ingest regimes data: {str(e)}")
            raise
    
    def _transform_regime_record(self, row: tuple) -> Dict[str, Any]:
        """
        Transform a regime record from the source database.
        
        Args:
            row: Row from cursor fetchmany
            
        Returns:
            Transformed record ready for insertion
        """
        # Unpack the row based on our SELECT statement order
        (date_val, market_news, instruments, country_economic_indicators,
         news_analysis, summary, vector_daily_regime, created_at, updated_at) = row
        
        # Handle the vector_daily_regime conversion
        # It might come as a list, numpy array, or string representation
        if vector_daily_regime is not None:
            if isinstance(vector_daily_regime, str):
                # Parse string representation of array
                try:
                    vector_daily_regime = json.loads(vector_daily_regime)
                except:
                    # Try numpy-style parsing
                    vector_daily_regime = np.fromstring(
                        vector_daily_regime.strip('[]'), sep=','
                    ).tolist()
            elif isinstance(vector_daily_regime, np.ndarray):
                vector_daily_regime = vector_daily_regime.tolist()
            # Ensure it's a list of floats
            if isinstance(vector_daily_regime, list):
                vector_daily_regime = [float(x) for x in vector_daily_regime]
        
        return {
            'date': date_val,
            'market_news': json.dumps(market_news) if isinstance(market_news, dict) else market_news,
            'instruments': json.dumps(instruments) if isinstance(instruments, dict) else instruments,
            'country_economic_indicators': json.dumps(country_economic_indicators) if isinstance(country_economic_indicators, dict) else country_economic_indicators,
            'news_analysis': json.dumps(news_analysis) if isinstance(news_analysis, dict) else news_analysis,
            'summary': json.dumps(summary) if isinstance(summary, dict) else summary,
            'vector_daily_regime': vector_daily_regime,
            'created_at': created_at,
            'updated_at': updated_at,
            'ingestion_timestamp': datetime.now()
        }
    
    def _insert_regimes_batch(self, batch_data: List[Dict[str, Any]]):
        """Insert a batch of regime records into the database."""
        if not batch_data:
            return
        
        try:
            # Build the insert query with ON CONFLICT
            query = """
            INSERT INTO {} (
                date, market_news, instruments, country_economic_indicators,
                news_analysis, summary, vector_daily_regime, created_at,
                updated_at, ingestion_timestamp
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, ingestion_timestamp) DO NOTHING
            """.format(self.table_name)
            
            # Convert to list of tuples
            values = [
                (
                    record['date'],
                    record['market_news'],
                    record['instruments'],
                    record['country_economic_indicators'],
                    record['news_analysis'],
                    record['summary'],
                    record['vector_daily_regime'],
                    record['created_at'],
                    record['updated_at'],
                    record['ingestion_timestamp']
                )
                for record in batch_data
            ]
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(query, values)
            
            logger.debug(f"Inserted batch of {len(batch_data)} regime records")
            
        except Exception as e:
            logger.error(f"Failed to insert batch: {str(e)}")
            if batch_data:
                logger.error(f"Sample record date: {batch_data[0].get('date')}")
            raise
    
    def get_latest_ingested_date(self) -> Optional[date]:
        """Get the latest date already ingested to support incremental loads."""
        query = f"SELECT MAX(date) as max_date FROM {self.table_name}"
        
        try:
            result = self.db_manager.model_db.execute_query(query)
            if result and result[0]['max_date']:
                return result[0]['max_date']
        except Exception as e:
            logger.warning(f"Could not get latest date: {str(e)}")
        
        return None


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Ingest regimes_daily data from Supabase')
    parser.add_argument('--start-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Start date for regimes data (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='End date for regimes data (YYYY-MM-DD)')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Force full refresh (truncate and reload)')
    parser.add_argument('--incremental', action='store_true',
                       help='Perform incremental load from last ingested date')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='ingest_regimes')
    
    # Run ingestion
    ingester = RegimesIngester()
    try:
        # Handle incremental load
        start_date = args.start_date
        if args.incremental and not args.force_refresh:
            latest_date = ingester.get_latest_ingested_date()
            if latest_date:
                start_date = latest_date + timedelta(days=1)
                logger.info(f"Incremental load from {start_date}")
        
        records = ingester.ingest_regimes(
            start_date=start_date,
            end_date=args.end_date,
            force_full_refresh=args.force_refresh
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    except Exception as e:
        logger.error(f"Ingestion failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()