#!/usr/bin/env python
"""
Add target columns to feature matrices after they have been generated.
This script processes feature matrices one at a time to avoid memory issues.

Usage:
    uv run --env-file .env.local -- python -m src.feature_engineering.add_targets_to_features
"""

import pathlib
import pandas as pd
import gc
import logging
import sys
from utils.database import execute_query_df
from typing import List, Optional
from .dtype_utils import get_memory_usage, fmt_memory_usage
from .utils import make_daily_id

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"

# Target columns to extract from raw_metrics_daily
TARGET_COLUMNS = [
    "net_profit", 
    "gross_profit", 
    "gross_loss", 
    "trades_placed",
    "win_rate", 
    "lots", 
    "risk_adj_ret", 
    "max_drawdown",
    "most_traded_symbol", 
    "mean_firm_margin"
]


def get_available_target_columns() -> List[str]:
    """Get list of target columns that actually exist in the database."""
    try:
        # Use parameterized query for safety
        placeholders = ','.join(['%s'] * len(TARGET_COLUMNS))
        query = f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s 
        AND column_name IN ({placeholders})
        """
        
        # Create params list with table name and column names
        params = ['raw_metrics_daily'] + list(TARGET_COLUMNS)
        
        # The database module has limitations with array parameters
        # Use a simpler, safe approach
        query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'raw_metrics_daily' 
        AND column_name IN ('net_profit', 'gross_profit', 'gross_loss', 'trades_placed',
                            'win_rate', 'lots', 'risk_adj_ret', 'max_drawdown',
                            'most_traded_symbol', 'mean_firm_margin')
        """
        
        result = execute_query_df(query)
        return result['column_name'].tolist()
    except Exception as e:
        logger.warning(f"Could not query column names: {e}")
        # Fallback: try to get columns from a sample query
        sample = execute_query_df("SELECT * FROM raw_metrics_daily LIMIT 1")
        return [col for col in TARGET_COLUMNS if col in sample.columns]


def add_targets_to_matrix(
    matrix_path: pathlib.Path,
    output_path: Optional[pathlib.Path] = None,
    available_targets: Optional[List[str]] = None
) -> bool:
    """
    Add target columns to a feature matrix.
    
    Returns True if successful, False otherwise.
    """
    if output_path is None:
        # Replace '_features.parquet' with '.parquet' for final output
        if matrix_path.name.endswith('_features.parquet'):
            output_path = matrix_path.parent / matrix_path.name.replace('_features.parquet', '.parquet')
        else:
            output_path = matrix_path
    
    logger.info(f"Processing {matrix_path.name}...")
    
    try:
        # Load the feature matrix
        logger.info("  Loading feature matrix...")
        matrix = pd.read_parquet(matrix_path)
        logger.info(f"  Matrix shape: {matrix.shape}")
        
        # Check if targets already exist
        if any(col.startswith("target_") for col in matrix.columns):
            logger.info("  Targets already exist, skipping...")
            return True
        
        # Get the daily_ids from the matrix index
        if isinstance(matrix.index, pd.MultiIndex):
            # For MultiIndex (daily_id, time), get unique daily_ids
            daily_ids = matrix.index.get_level_values(0).unique().tolist()
        else:
            daily_ids = matrix.index.unique().tolist()
        
        logger.info(f"  Found {len(daily_ids)} unique daily_ids")
        
        # Get available target columns if not provided
        if available_targets is None:
            available_targets = get_available_target_columns()
            logger.info(f"  Available target columns: {available_targets}")
        
        # Query targets in chunks to avoid memory issues
        chunk_size = 50000
        targets_list = []
        
        # Validate daily_ids are integers
        try:
            daily_ids_int = [int(id) for id in daily_ids]
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid daily_ids found: {e}")
            return False
        
        # Since daily_id is computed in the feature engineering script, we need to
        # extract the account_id and date components to query the raw table
        logger.info("  Extracting account_id and date from daily_ids...")
        
        # For MultiIndex, extract from the appropriate level
        if isinstance(matrix.index, pd.MultiIndex):
            # Get unique combinations of account_id and date from the matrix
            # The daily_id is a hash of account_id_date
            unique_index = matrix.index.to_frame().reset_index(drop=True)
            # We need to query based on the actual data in the matrix
            # Since we can't reverse the hash, we'll need to get all data and filter
            logger.info("  Using full table scan approach due to hashed IDs...")
            
            # The index level 1 holds the cutoff_time (D-1). Our targets are
            # the next day (D).  Shift the window forward by exactly one day
            # to avoid label leakage and ensure perfect alignment.

            cutoff_dates = matrix.index.get_level_values(1).unique()
            min_date = (cutoff_dates.min() + pd.Timedelta(days=1)).date()
            max_date = (cutoff_dates.max() + pd.Timedelta(days=1)).date()
            
            # Query targets for the date range
            cols_str = ', '.join(available_targets + ['account_id', 'date'])
            query = f"""
            SELECT {cols_str}
            FROM raw_metrics_daily
            WHERE date >= %(min_date)s AND date <= %(max_date)s
            """
            
            targets_df = execute_query_df(query, {
                'min_date': min_date.strftime('%Y-%m-%d'),
                'max_date': max_date.strftime('%Y-%m-%d')
            })
            
            targets_df['daily_id'] = make_daily_id(targets_df['account_id'], targets_df['date'])
            
            # Filter to only the daily_ids we need
            targets_df = targets_df[targets_df['daily_id'].isin(daily_ids_int)]
            
        else:
            # For single index, same approach
            logger.warning("  Single index matrix detected, this is unexpected for feature matrices")
            # Fall back to loading all data - this shouldn't happen in practice
            cols_str = ', '.join(available_targets)
            query = f"SELECT daily_id, {cols_str} FROM raw_metrics_daily"
            targets_df = execute_query_df(query)
            targets_df = targets_df[targets_df['daily_id'].isin(daily_ids_int)]
        
        logger.info(f"  Found {len(targets_df)} target rows")
        
        # Set index to match matrix
        targets_df = targets_df.set_index('daily_id')
        
        # Add target columns with proper MultiIndex handling
        logger.info("  Adding target columns...")
        
        if isinstance(matrix.index, pd.MultiIndex):
            # For MultiIndex, we need to align by the first level (daily_id)
            # Create a mapping from daily_id to target values
            for col in available_targets:
                if col in targets_df.columns:
                    # Map targets based on the daily_id level
                    daily_id_level = matrix.index.get_level_values(0)
                    matrix[f'target_{col}'] = daily_id_level.map(targets_df[col])
        else:
            # For single index, direct assignment works
            for col in available_targets:
                if col in targets_df.columns:
                    matrix[f'target_{col}'] = targets_df[col]
        
        # Add binary classification targets if net_profit exists
        if 'target_net_profit' in matrix.columns:
            logger.info("  Adding binary classification targets...")
            matrix['target_is_profitable'] = (matrix['target_net_profit'] > 0).astype(int)
            
            # Calculate 90th percentile for highly profitable
            profit_90th = matrix['target_net_profit'].quantile(0.9)
            matrix['target_is_highly_profitable'] = (matrix['target_net_profit'] > profit_90th).astype(int)
        
        # Save the matrix with targets
        logger.info(f"  Saving matrix with targets to {output_path}...")
        matrix.to_parquet(output_path, engine='pyarrow')
        
        # Report memory usage
        logger.info(f"  Saved: {matrix.shape} → {output_path} | {fmt_memory_usage(get_memory_usage(matrix))}")
        
        # Clean up
        del matrix
        del targets_df
        gc.collect()
        
        return True
        
    except Exception as e:
        logger.error(f"  ERROR processing {matrix_path}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function to add targets to all feature matrices."""
    logger.info("Starting target addition process...")
    
    # Get available target columns once
    available_targets = get_available_target_columns()
    logger.info(f"Available target columns in database: {available_targets}")
    
    if not available_targets:
        logger.error("No target columns found in database!")
        return 1
    
    # Process test and validation matrices first
    for split in ['test', 'val']:
        matrix_path = ARTEFACT_DIR / f"{split}_matrix.parquet"
        if matrix_path.exists():
            # Check if it already has targets
            df = pd.read_parquet(matrix_path, columns=[])
            if not any(col.startswith('target_') for col in df.columns):
                if not add_targets_to_matrix(matrix_path, available_targets=available_targets):
                    logger.error(f"Failed to add targets to {split} matrix")
                    return 1
            else:
                logger.info(f"{split}_matrix.parquet already has targets")
    
    # Process training chunks
    chunk_files = sorted(ARTEFACT_DIR.glob("train_chunk_*_features.parquet"))
    
    if chunk_files:
        logger.info(f"\nFound {len(chunk_files)} training feature chunks to process")
        
        success_count = 0
        for chunk_path in chunk_files:
            if add_targets_to_matrix(chunk_path, available_targets=available_targets):
                success_count += 1
        
        logger.info(f"\nSuccessfully processed {success_count}/{len(chunk_files)} chunks")
        
        if success_count != len(chunk_files):
            logger.error("Not all chunks were processed successfully!")
            return 1
            
        logger.info("\nAll training chunks now have targets.")
        logger.info("Use concatenate_training_chunks.py to combine them into train_matrix.parquet")
    else:
        logger.warning("No training feature chunks found to process!")
    
    logger.info("\nTarget addition process complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())