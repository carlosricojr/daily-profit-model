"""
Ingest plans data from CSV files.
Stores data in the raw_plans_data table.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import argparse
import pandas as pd
import glob

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class PlansIngester:
    """Handles ingestion of plans data from CSV files."""
    
    def __init__(self):
        """Initialize the plans ingester."""
        self.db_manager = get_db_manager()
        self.table_name = 'raw_plans_data'
        
        # Expected column mappings from CSV to database
        self.column_mapping = {
            'Plan ID': 'plan_id',
            'PlanID': 'plan_id',
            'plan_id': 'plan_id',
            'Plan Name': 'plan_name',
            'PlanName': 'plan_name',
            'plan_name': 'plan_name',
            'Type': 'plan_type',
            'type': 'plan_type',
            'Starting Balance': 'starting_balance',
            'starting_balance': 'starting_balance',
            'Profit Target': 'profit_target',
            'profit_target': 'profit_target',
            'Profit Target %': 'profit_target_pct',
            'profit_target_pct': 'profit_target_pct',
            'Max Drawdown': 'max_drawdown',
            'max_drawdown': 'max_drawdown',
            'Max Drawdown %': 'max_drawdown_pct',
            'max_drawdown_pct': 'max_drawdown_pct',
            'Max Daily Drawdown': 'max_daily_drawdown',
            'max_daily_drawdown': 'max_daily_drawdown',
            'Max Daily Drawdown %': 'max_daily_drawdown_pct',
            'max_daily_drawdown_pct': 'max_daily_drawdown_pct',
            'Max Leverage': 'max_leverage',
            'max_leverage': 'max_leverage',
            'Is Drawdown Relative': 'is_drawdown_relative',
            'is_drawdown_relative': 'is_drawdown_relative',
            'Min Trading Days': 'min_trading_days',
            'min_trading_days': 'min_trading_days',
            'Max Trading Days': 'max_trading_days',
            'max_trading_days': 'max_trading_days',
            'Profit Split %': 'profit_split_pct',
            'profit_split_pct': 'profit_split_pct'
        }
    
    def ingest_plans(self, 
                    csv_directory: str = None,
                    specific_files: Optional[List[str]] = None,
                    force_full_refresh: bool = False) -> int:
        """
        Ingest plans data from CSV files.
        
        Args:
            csv_directory: Directory containing CSV files (defaults to raw-data/plans)
            specific_files: List of specific CSV files to process
            force_full_refresh: If True, truncate existing data and reload all
            
        Returns:
            Number of records ingested
        """
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_plans',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Handle full refresh
            if force_full_refresh:
                logger.warning("Force full refresh requested for plans. Truncating existing data.")
                self.db_manager.model_db.execute_command(f"TRUNCATE TABLE {self.table_name}")
            
            # Determine CSV files to process
            if specific_files:
                csv_files = specific_files
            else:
                if not csv_directory:
                    # Default to raw-data/plans relative to project root
                    project_root = Path(__file__).parent.parent.parent
                    csv_directory = project_root / "raw-data" / "plans"
                else:
                    csv_directory = Path(csv_directory)
                
                # Find all CSV files in the directory
                csv_files = list(csv_directory.glob("*.csv"))
                logger.info(f"Found {len(csv_files)} CSV files in {csv_directory}")
            
            # Process each CSV file
            for csv_file in csv_files:
                file_records = self._process_csv_file(csv_file)
                total_records += file_records
                logger.info(f"Processed {file_records} records from {csv_file}")
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_plans',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'files_processed': len(csv_files),
                    'force_full_refresh': force_full_refresh
                }
            )
            
            logger.info(f"Successfully ingested {total_records} plan records from {len(csv_files)} files")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='ingest_plans',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to ingest plans data: {str(e)}")
            raise
    
    def _process_csv_file(self, csv_file: Path) -> int:
        """
        Process a single CSV file and insert records into the database.
        
        Args:
            csv_file: Path to the CSV file
            
        Returns:
            Number of records processed from this file
        """
        try:
            logger.info(f"Processing CSV file: {csv_file}")
            
            # Read CSV file
            df = pd.read_csv(csv_file)
            logger.info(f"Read {len(df)} rows from {csv_file}")
            
            # Rename columns based on mapping
            df_renamed = df.rename(columns=self.column_mapping)
            
            # Add ingestion timestamp
            df_renamed['ingestion_timestamp'] = datetime.now()
            
            # Convert DataFrame to list of dictionaries
            records = df_renamed.to_dict('records')
            
            # Clean and transform records
            cleaned_records = []
            for record in records:
                cleaned_record = self._transform_plan_record(record)
                if cleaned_record:
                    cleaned_records.append(cleaned_record)
            
            # Insert records in batches
            batch_size = 100
            total_inserted = 0
            
            for i in range(0, len(cleaned_records), batch_size):
                batch = cleaned_records[i:i + batch_size]
                self._insert_plans_batch(batch)
                total_inserted += len(batch)
            
            return total_inserted
            
        except Exception as e:
            logger.error(f"Failed to process CSV file {csv_file}: {str(e)}")
            raise
    
    def _transform_plan_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transform and clean a plan record from CSV.
        
        Args:
            record: Raw record from CSV
            
        Returns:
            Cleaned record ready for database insertion, or None if invalid
        """
        # Extract only the columns we need
        db_columns = [
            'plan_id', 'plan_name', 'plan_type', 'starting_balance',
            'profit_target', 'profit_target_pct', 'max_drawdown', 'max_drawdown_pct',
            'max_daily_drawdown', 'max_daily_drawdown_pct', 'max_leverage',
            'is_drawdown_relative', 'min_trading_days', 'max_trading_days',
            'profit_split_pct', 'ingestion_timestamp'
        ]
        
        cleaned_record = {}
        for col in db_columns:
            if col in record:
                value = record[col]
                
                # Handle NaN values
                if pd.isna(value):
                    value = None
                
                # Convert boolean strings to actual booleans
                if col == 'is_drawdown_relative' and value is not None:
                    if isinstance(value, str):
                        value = value.lower() in ['true', 'yes', '1', 't', 'y']
                    else:
                        value = bool(value)
                
                # Convert percentage strings to decimals
                if col.endswith('_pct') and value is not None:
                    if isinstance(value, str) and value.endswith('%'):
                        value = float(value.rstrip('%'))
                
                cleaned_record[col] = value
            else:
                # Set default values for missing columns
                if col == 'ingestion_timestamp':
                    cleaned_record[col] = datetime.now()
                else:
                    cleaned_record[col] = None
        
        # Validate required fields
        if not cleaned_record.get('plan_id'):
            logger.warning(f"Skipping record with missing plan_id: {record}")
            return None
        
        return cleaned_record
    
    def _insert_plans_batch(self, batch_data: List[Dict[str, Any]]):
        """Insert a batch of plan records into the database."""
        if not batch_data:
            return
        
        try:
            # Build the insert query with ON CONFLICT
            columns = list(batch_data[0].keys())
            placeholders = ', '.join(['%s'] * len(columns))
            columns_str = ', '.join(columns)
            
            query = f"""
            INSERT INTO {self.table_name} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT (plan_id, ingestion_timestamp) DO NOTHING
            """
            
            # Convert to list of tuples
            values = [tuple(record[col] for col in columns) for record in batch_data]
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.executemany(query, values)
            
            logger.debug(f"Inserted batch of {len(batch_data)} plan records")
            
        except Exception as e:
            logger.error(f"Failed to insert batch: {str(e)}")
            if batch_data:
                logger.error(f"Sample record: {batch_data[0]}")
            raise


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Ingest plans data from CSV files')
    parser.add_argument('--csv-dir', help='Directory containing CSV files')
    parser.add_argument('--files', nargs='+', help='Specific CSV files to process')
    parser.add_argument('--force-refresh', action='store_true',
                       help='Force full refresh (truncate and reload)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='ingest_plans')
    
    # Run ingestion
    ingester = PlansIngester()
    try:
        # Convert file paths to Path objects if provided
        specific_files = [Path(f) for f in args.files] if args.files else None
        
        records = ingester.ingest_plans(
            csv_directory=args.csv_dir,
            specific_files=specific_files,
            force_full_refresh=args.force_refresh
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    except Exception as e:
        logger.error(f"Ingestion failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()