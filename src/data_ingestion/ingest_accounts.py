"""
Ingest accounts data from the /accounts API endpoint.
Stores data in the raw_accounts_data table.
"""

import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import argparse

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.api_client import RiskAnalyticsAPIClient
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class AccountsIngester:
    """Handles ingestion of accounts data from the API."""
    
    def __init__(self):
        """Initialize the accounts ingester."""
        self.db_manager = get_db_manager()
        self.api_client = RiskAnalyticsAPIClient()
        self.table_name = 'raw_accounts_data'
        self.source_endpoint = '/accounts'
        
    def ingest_accounts(self, 
                       logins: Optional[List[str]] = None,
                       traders: Optional[List[str]] = None,
                       force_full_refresh: bool = False) -> int:
        """
        Ingest accounts data from the API.
        
        Args:
            logins: Optional list of specific login IDs to fetch
            traders: Optional list of specific trader IDs to fetch
            force_full_refresh: If True, truncate existing data and reload all
            
        Returns:
            Number of records ingested
        """
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_accounts',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Check if we need to do a full refresh
            if force_full_refresh:
                logger.warning("Force full refresh requested. Truncating existing data.")
                self.db_manager.model_db.execute_command(f"TRUNCATE TABLE {self.table_name}")
            
            # Prepare batch for insertion
            batch_data = []
            batch_size = 1000
            
            # Fetch accounts data with pagination
            logger.info("Starting accounts data ingestion...")
            for page_num, accounts_page in enumerate(self.api_client.get_accounts(
                logins=logins, 
                traders=traders
            )):
                logger.info(f"Processing page {page_num + 1} with {len(accounts_page)} accounts")
                
                for account in accounts_page:
                    # Transform account data for database insertion
                    record = self._transform_account_record(account)
                    batch_data.append(record)
                    
                    # Insert batch when it reaches the size limit
                    if len(batch_data) >= batch_size:
                        self._insert_batch(batch_data)
                        total_records += len(batch_data)
                        batch_data = []
                
            # Insert any remaining records
            if batch_data:
                self._insert_batch(batch_data)
                total_records += len(batch_data)
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_accounts',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'force_full_refresh': force_full_refresh
                }
            )
            
            logger.info(f"Successfully ingested {total_records} account records")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_accounts',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to ingest accounts data: {str(e)}")
            raise
    
    def _transform_account_record(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform API account record to database format.
        
        Args:
            account: Raw account data from API
            
        Returns:
            Transformed record ready for database insertion
        """
        return {
            'account_id': account.get('accountId'),
            'login': account.get('login'),
            'trader_id': account.get('traderId'),
            'plan_id': account.get('planId'),
            'starting_balance': account.get('startingBalance'),
            'current_balance': account.get('currentBalance'),
            'current_equity': account.get('currentEquity'),
            'profit_target_pct': account.get('profitTargetPct'),
            'max_daily_drawdown_pct': account.get('maxDailyDrawdownPct'),
            'max_drawdown_pct': account.get('maxDrawdownPct'),
            'max_leverage': account.get('maxLeverage'),
            'is_drawdown_relative': account.get('isDrawdownRelative'),
            'breached': account.get('breached', 0),
            'is_upgraded': account.get('isUpgraded', 0),
            'phase': account.get('phase'),
            'status': account.get('status'),
            'created_at': account.get('createdAt'),
            'updated_at': account.get('updatedAt'),
            'ingestion_timestamp': datetime.now(),
            'source_api_endpoint': self.source_endpoint
        }
    
    def _insert_batch(self, batch_data: List[Dict[str, Any]]):
        """Insert a batch of records into the database."""
        try:
            # Use ON CONFLICT to handle duplicates
            query = f"""
            INSERT INTO {self.table_name} 
            ({', '.join(batch_data[0].keys())})
            VALUES ({', '.join(['%s'] * len(batch_data[0]))})
            ON CONFLICT (account_id, ingestion_timestamp) DO NOTHING
            """
            
            # Convert to list of tuples for bulk insert
            values = [tuple(record.values()) for record in batch_data]
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(query, values)
            
            logger.debug(f"Inserted batch of {len(batch_data)} records")
            
        except Exception as e:
            logger.error(f"Failed to insert batch: {str(e)}")
            raise
    
    def close(self):
        """Clean up resources."""
        self.api_client.close()


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Ingest accounts data from Risk Analytics API')
    parser.add_argument('--logins', nargs='+', help='Specific login IDs to fetch')
    parser.add_argument('--traders', nargs='+', help='Specific trader IDs to fetch')
    parser.add_argument('--force-refresh', action='store_true', 
                       help='Force full refresh (truncate and reload)')
    parser.add_argument('--log-level', default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='ingest_accounts')
    
    # Run ingestion
    ingester = AccountsIngester()
    try:
        records = ingester.ingest_accounts(
            logins=args.logins,
            traders=args.traders,
            force_full_refresh=args.force_refresh
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    finally:
        ingester.close()


if __name__ == '__main__':
    main()