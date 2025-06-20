#!/usr/bin/env python
"""Diagnose memory issues with parquet files."""

import pyarrow.parquet as pq
import pandas as pd
import psutil
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"

def get_memory_gb():
    """Get current memory usage in GB."""
    return psutil.Process().memory_info().rss / (1024 ** 3)

def diagnose_parquet_file(filepath):
    """Diagnose potential memory issues with a parquet file."""
    logger.info(f"\nDiagnosing: {filepath}")
    logger.info(f"File size: {filepath.stat().st_size / (1024**3):.2f} GB")
    
    # Read metadata without loading data
    parquet_file = pq.ParquetFile(filepath)
    metadata = parquet_file.metadata
    schema = parquet_file.schema
    
    logger.info(f"Number of rows: {metadata.num_rows:,}")
    logger.info(f"Number of columns: {metadata.num_columns}")
    
    # Check compression and encoding
    logger.info("\nColumn encodings and types:")
    problematic_columns = []
    
    for i in range(metadata.num_row_groups):
        row_group = metadata.row_group(i)
        for j in range(row_group.num_columns):
            column = row_group.column(j)
            col_meta = column.metadata
            
            # Check for dictionary encoding
            if col_meta and hasattr(col_meta, 'encodings') and 'PLAIN_DICTIONARY' in str(col_meta.encodings):
                field = schema.field(j)
                if str(field.type) in ['string', 'large_string', 'binary', 'large_binary']:
                    problematic_columns.append((field.name, field.type))
    
    if problematic_columns:
        logger.warning(f"\nFound {len(problematic_columns)} dictionary-encoded string/binary columns:")
        for col_name, col_type in problematic_columns[:10]:  # Show first 10
            logger.warning(f"  - {col_name} ({col_type})")
    
    # Test loading strategies
    logger.info("\nTesting different loading strategies...")
    
    # Strategy 1: Load with PyArrow
    logger.info("\n1. Testing PyArrow loading (first 1000 rows):")
    mem_before = get_memory_gb()
    table = parquet_file.read(columns=None, use_threads=False, use_pandas_metadata=True)
    df_sample = table.slice(0, 1000).to_pandas()
    mem_after = get_memory_gb()
    logger.info(f"   Memory used: {mem_after - mem_before:.2f} GB for 1000 rows")
    logger.info(f"   Extrapolated for full dataset: {(mem_after - mem_before) * metadata.num_rows / 1000:.2f} GB")
    del table, df_sample
    
    # Strategy 2: Check data types
    logger.info("\n2. Checking column data types:")
    table_sample = parquet_file.read(columns=None, use_threads=False).slice(0, 1000)
    df_sample = table_sample.to_pandas()
    
    # Count data types
    dtype_counts = df_sample.dtypes.value_counts()
    logger.info("   Data type distribution:")
    for dtype, count in dtype_counts.items():
        logger.info(f"   - {dtype}: {count} columns")
    
    # Check for high-cardinality object columns
    object_cols = df_sample.select_dtypes(include=['object']).columns
    if len(object_cols) > 0:
        logger.warning(f"\n   Found {len(object_cols)} object columns (potential memory issue)")
        
    # Memory usage by column type
    memory_by_type = df_sample.memory_usage(deep=True).sum() / 1024**2  # MB
    logger.info(f"\n   Sample memory usage: {memory_by_type:.2f} MB for 1000 rows")
    
    del table_sample, df_sample

def main():
    """Diagnose memory issues with the training data."""
    
    # Check train matrix
    train_path = ARTEFACT_DIR / "train_matrix.parquet"
    if train_path.exists():
        diagnose_parquet_file(train_path)
    
    # Also check a smaller matrix for comparison
    val_path = ARTEFACT_DIR / "val_matrix.parquet"
    if val_path.exists():
        diagnose_parquet_file(val_path)

if __name__ == "__main__":
    main()