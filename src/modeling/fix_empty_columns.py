#!/usr/bin/env python
"""Remove empty object columns from parquet files that are causing memory issues."""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import logging
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"
CLEAN_DIR = ARTEFACT_DIR / "clean"

def fix_parquet_file(input_path: Path, output_path: Path):
    """Remove empty object columns from a parquet file."""
    logger.info(f"\nFixing {input_path.name}...")
    logger.info(f"Original size: {input_path.stat().st_size / (1024**2):.1f} MB")
    
    # Read schema first to identify object columns
    pf = pq.ParquetFile(input_path)
    schema = pf.schema
    
    # Get list of all columns
    all_columns = [field.name for field in schema]
    
    # Identify columns to check (those that shouldn't be in feature matrix)
    metadata_columns = [
        'login', 'account_id', 'plan_id', 'trader_id', 'status', 'type', 'phase',
        'broker', 'platform', 'price_stream', 'country', 'most_traded_symbol'
    ]
    
    # Find which metadata columns exist in this file
    columns_to_check = [col for col in all_columns if any(
        col == meta_col or col.startswith(f'{meta_col}.') or col.endswith(f'.{meta_col}')
        for meta_col in metadata_columns
    )]
    
    logger.info(f"Found {len(columns_to_check)} metadata columns to check")
    
    # Read small sample to check which columns are empty
    sample_df = pf.read(columns=columns_to_check).to_pandas()
    
    # Find empty columns
    empty_columns = []
    for col in columns_to_check:
        if sample_df[col].isna().all():
            empty_columns.append(col)
    
    logger.info(f"Found {len(empty_columns)} empty columns to remove")
    
    if not empty_columns:
        logger.info("No empty columns found, copying file as-is")
        shutil.copy2(input_path, output_path)
        return
    
    # Read all columns except empty ones
    columns_to_keep = [col for col in all_columns if col not in empty_columns]
    logger.info(f"Keeping {len(columns_to_keep)} columns (removed {len(empty_columns)})")
    
    # Read and write in chunks for memory efficiency
    logger.info("Processing file...")
    
    # Use PyArrow for efficient processing
    table = pf.read(columns=columns_to_keep)
    
    # Write to new file
    pq.write_table(table, output_path, compression='snappy')
    
    logger.info(f"Output size: {output_path.stat().st_size / (1024**2):.1f} MB")
    logger.info(f"Size reduction: {(1 - output_path.stat().st_size / input_path.stat().st_size) * 100:.1f}%")

def main():
    """Fix all feature matrices."""
    
    CLEAN_DIR.mkdir(exist_ok=True)
    
    for split in ['train', 'val', 'test']:
        input_path = ARTEFACT_DIR / f"{split}_matrix.parquet"
        output_path = CLEAN_DIR / f"{split}_matrix.parquet"
        
        if not input_path.exists():
            logger.warning(f"{input_path} not found")
            continue
            
        fix_parquet_file(input_path, output_path)
    
    logger.info("\n✓ All files processed!")
    logger.info(f"\nCleaned files saved to: {CLEAN_DIR}")
    logger.info("\nTo use cleaned files, update your training script to load from:")
    logger.info(f"  ARTEFACT_DIR / 'clean' / f'{{split}}_matrix.parquet'")

if __name__ == "__main__":
    main()