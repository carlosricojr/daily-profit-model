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
    "num_trades",
    "success_rate", 
    "lots", 
    "risk_adj_ret", 
    "max_drawdown",
    "most_traded_symbol", 
    "mean_firm_margin"
]


def get_available_target_columns() -> List[str]:
    """Get list of target columns that actually exist in the cleaned data."""
    try:
        # Load a sample of the cleaned daily metrics to check available columns
        CLEANED_DATA_DIR = PROJECT_ROOT / "artefacts" / "cleaned_data"
        daily_metrics_path = CLEANED_DATA_DIR / "daily_metrics_df.parquet"
        
        if not daily_metrics_path.exists():
            logger.error(f"Cleaned data file not found: {daily_metrics_path}")
            return []
        
        # Read just the schema to get column names (efficient)
        sample = pd.read_parquet(daily_metrics_path, columns=['account_id'])
        all_columns = pd.read_parquet(daily_metrics_path).columns.tolist()
        
        # Return target columns that exist in the cleaned data
        available = [col for col in TARGET_COLUMNS if col in all_columns]
        logger.info(f"Found {len(available)} target columns in cleaned data")
        return available
        
    except Exception as e:
        logger.warning(f"Could not load cleaned data: {e}")
        # Fallback: try database if cleaned data not available
        try:
            query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'raw_metrics_daily' 
            AND column_name IN ('net_profit', 'gross_profit', 'gross_loss', 'num_trades',
                                'success_rate', 'lots', 'risk_adj_ret', 'max_drawdown',
                                'most_traded_symbol', 'mean_firm_margin')
            """
            
            result = execute_query_df(query)
            return result['column_name'].tolist()
        except:
            return []


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
        
        # Check which targets already exist and which are missing
        existing_targets = [col for col in matrix.columns if col.startswith("target_")]
        if existing_targets:
            logger.info(f"  Found {len(existing_targets)} existing target columns")
            # Check if we're missing any expected targets
            expected_targets = [f"target_{col}" for col in available_targets]
            missing_targets = [t for t in expected_targets if t not in existing_targets]
            if not missing_targets:
                logger.info("  All expected targets already exist, skipping...")
                return True
            else:
                logger.info(f"  Missing targets: {missing_targets}")
                logger.info("  Will add missing targets to existing matrix...")
        
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
            
            # Load targets from cleaned parquet file
            CLEANED_DATA_DIR = PROJECT_ROOT / "artefacts" / "cleaned_data"
            daily_metrics_path = CLEANED_DATA_DIR / "daily_metrics_df.parquet"
            
            logger.info(f"  Loading targets from {daily_metrics_path}")
            
            # Load only required columns and date range for efficiency
            cols_to_load = available_targets + ['account_id', 'date']
            
            # Read the cleaned data
            targets_df = pd.read_parquet(daily_metrics_path, columns=cols_to_load)
            
            # Filter to date range
            targets_df = targets_df[
                (targets_df['date'] >= pd.Timestamp(min_date)) & 
                (targets_df['date'] <= pd.Timestamp(max_date))
            ].copy()
            
            targets_df['daily_id'] = make_daily_id(targets_df['account_id'], targets_df['date'])
            
            # Filter to only the daily_ids we need
            targets_df = targets_df[targets_df['daily_id'].isin(daily_ids_int)]
            
        else:
            # For single index, same approach
            logger.warning("  Single index matrix detected, this is unexpected for feature matrices")
            
            # Load from cleaned data
            CLEANED_DATA_DIR = PROJECT_ROOT / "artefacts" / "cleaned_data"
            daily_metrics_path = CLEANED_DATA_DIR / "daily_metrics_df.parquet"
            
            # Load only required columns
            cols_to_load = available_targets + ['account_id', 'date']
            targets_df = pd.read_parquet(daily_metrics_path, columns=cols_to_load)
            
            # Create daily_id
            targets_df['daily_id'] = make_daily_id(targets_df['account_id'], targets_df['date'])
            
            # Filter to only the daily_ids we need
            targets_df = targets_df[targets_df['daily_id'].isin(daily_ids_int)]
        
        logger.info(f"  Found {len(targets_df)} target rows")
        
        # Set index to match matrix
        targets_df = targets_df.set_index('daily_id')
        
        # Add target columns with proper MultiIndex handling
        logger.info("  Adding target columns...")
        
        # Determine which targets to add (only missing ones if some already exist)
        if existing_targets:
            targets_to_add = [col for col in available_targets if f'target_{col}' not in matrix.columns]
            logger.info(f"  Adding only missing targets: {targets_to_add}")
        else:
            targets_to_add = available_targets
            logger.info("  Adding all target columns...")
        
        if isinstance(matrix.index, pd.MultiIndex):
            # For MultiIndex, we need to align by the first level (daily_id)
            # Create a mapping from daily_id to target values
            for col in targets_to_add:
                if col in targets_df.columns:
                    # Map targets based on the daily_id level
                    daily_id_level = matrix.index.get_level_values(0)
                    matrix[f'target_{col}'] = daily_id_level.map(targets_df[col])
        else:
            # For single index, direct assignment works
            for col in targets_to_add:
                if col in targets_df.columns:
                    matrix[f'target_{col}'] = targets_df[col]
        
        # Add binary classification targets if net_profit exists
        if 'target_net_profit' in matrix.columns:
            logger.info("  Adding binary classification targets...")
            matrix['target_is_profitable'] = (matrix['target_net_profit'] > 0).astype(int)
            
            # Calculate 90th percentile for highly profitable
            profit_90th = matrix['target_net_profit'].quantile(0.9)
            matrix['target_is_highly_profitable'] = (matrix['target_net_profit'] > profit_90th).astype(int)
        
        # Drop rows where *all* targets are NaN to avoid training-time filtering later
        target_cols_full = [col for col in matrix.columns if col.startswith("target_") and col not in ("target_is_profitable", "target_is_highly_profitable")]
        before_rows = len(matrix)
        matrix = matrix.dropna(subset=target_cols_full, how="all")
        dropped = before_rows - len(matrix)
        if dropped:
            logger.info(f"  Dropped {dropped:,} rows with no target values")
        
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
            if not add_targets_to_matrix(matrix_path, available_targets=available_targets):
                logger.error(f"Failed to add targets to {split} matrix")
                return 1
    
    # Process training data - either chunks or complete matrix
    chunk_files = sorted(ARTEFACT_DIR.glob("train_chunk_*_features.parquet"))
    train_matrix_path = ARTEFACT_DIR / "train_matrix.parquet"
    
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
    elif train_matrix_path.exists():
        # Process existing train_matrix.parquet to add missing targets
        logger.info("\nFound existing train_matrix.parquet")
        if not add_targets_to_matrix(train_matrix_path, available_targets=available_targets):
            logger.error("Failed to add targets to train matrix")
            return 1
    else:
        logger.warning("No training feature chunks or train_matrix.parquet found to process!")
    
    logger.info("\nTarget addition process complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())