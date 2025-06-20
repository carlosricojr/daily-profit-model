#!/usr/bin/env python
"""Optimize parquet files to reduce memory usage.

This script:
1. Drops all-null columns
2. Converts object columns to categorical where appropriate
3. Converts nullable integers to float64
4. Saves optimized versions
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import numpy as np
import gc
import psutil
import logging
from typing import List, Dict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"


def get_memory_usage_gb():
    """Get current memory usage in GB."""
    return psutil.Process().memory_info().rss / (1024 ** 3)


def analyze_columns(parquet_path: Path, sample_size: int = 10000) -> Dict[str, List[str]]:
    """Analyze columns to identify optimization opportunities."""
    logger.info(f"Analyzing {parquet_path.name}...")
    
    pf = pq.ParquetFile(parquet_path)
    total_rows = pf.metadata.num_rows
    
    # Read a sample
    if pf.num_row_groups > 0:
        # Read multiple row groups to get a better sample
        row_groups_to_read = min(5, pf.num_row_groups)
        dfs = []
        for i in range(row_groups_to_read):
            df_chunk = pf.read_row_group(i).to_pandas()
            dfs.append(df_chunk.head(sample_size // row_groups_to_read))
        sample_df = pd.concat(dfs, ignore_index=True)
    else:
        sample_df = pd.read_parquet(parquet_path).head(sample_size)
    
    results = {
        "all_null_columns": [],
        "low_cardinality_strings": [],
        "nullable_int_columns": [],
        "high_null_columns": [],
        "columns_to_keep": []
    }
    
    for col in sample_df.columns:
        # Check if column is all null
        if sample_df[col].isna().all():
            results["all_null_columns"].append(col)
        else:
            results["columns_to_keep"].append(col)
            
            # Check for high null percentage (>95%)
            null_pct = sample_df[col].isna().sum() / len(sample_df)
            if null_pct > 0.95:
                results["high_null_columns"].append(col)
            
            # Check for nullable integers
            if str(sample_df[col].dtype).startswith('Int'):
                results["nullable_int_columns"].append(col)
            
            # Check for low cardinality strings
            if sample_df[col].dtype == 'object':
                unique_ratio = sample_df[col].nunique() / len(sample_df)
                if unique_ratio < 0.5:  # Less than 50% unique
                    results["low_cardinality_strings"].append(col)
    
    logger.info(f"Found {len(results['all_null_columns'])} all-null columns to drop")
    logger.info(f"Found {len(results['nullable_int_columns'])} nullable int columns to convert")
    logger.info(f"Found {len(results['low_cardinality_strings'])} string columns to categorize")
    
    return results


def optimize_batch(df: pd.DataFrame, column_info: Dict[str, List[str]]) -> pd.DataFrame:
    """Optimize a batch of data."""
    initial_memory = df.memory_usage(deep=True).sum() / 1024**3
    
    # Drop all-null columns
    cols_to_drop = [col for col in column_info["all_null_columns"] if col in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
    
    # Convert nullable integers to float64
    for col in column_info["nullable_int_columns"]:
        if col in df.columns:
            df[col] = df[col].astype('float64')
    
    # Convert low cardinality strings to category
    for col in column_info["low_cardinality_strings"]:
        if col in df.columns:
            df[col] = df[col].astype('category')
    
    # Downcast floats where possible
    float_cols = df.select_dtypes(include=['float64']).columns
    for col in float_cols:
        col_min = df[col].min()
        col_max = df[col].max()
        if pd.notna(col_min) and pd.notna(col_max):
            if col_min > np.finfo(np.float32).min and col_max < np.finfo(np.float32).max:
                df[col] = df[col].astype('float32')
    
    final_memory = df.memory_usage(deep=True).sum() / 1024**3
    reduction_pct = (1 - final_memory/initial_memory) * 100
    logger.info(f"Batch memory reduced by {reduction_pct:.1f}%")
    
    return df


def optimize_parquet_file(input_path: Path, output_path: Path, batch_size: int = 50000):
    """Optimize a parquet file by processing in batches."""
    logger.info(f"Optimizing {input_path.name}...")
    logger.info(f"Initial file size: {input_path.stat().st_size / 1024**2:.1f} MB")
    
    # First, analyze the columns
    column_info = analyze_columns(input_path)
    
    # Process in batches to avoid OOM
    pf = pq.ParquetFile(input_path)
    total_rows = pf.metadata.num_rows
    
    # Prepare output
    output_path.parent.mkdir(exist_ok=True, parents=True)
    writer = None
    rows_processed = 0
    
    # Process by row groups
    for i in range(pf.num_row_groups):
        logger.info(f"Processing row group {i+1}/{pf.num_row_groups}")
        
        # Read row group
        df_batch = pf.read_row_group(i).to_pandas()
        
        # Optimize
        df_batch = optimize_batch(df_batch, column_info)
        
        # Write to parquet
        table = pa.Table.from_pandas(df_batch)
        
        if writer is None:
            writer = pq.ParquetWriter(output_path, table.schema, compression='snappy')
        
        writer.write_table(table)
        rows_processed += len(df_batch)
        
        # Cleanup
        del df_batch, table
        gc.collect()
        
        logger.info(f"Processed {rows_processed:,}/{total_rows:,} rows. "
                   f"Memory: {get_memory_usage_gb():.1f} GB")
    
    if writer:
        writer.close()
    
    # Report results
    output_size_mb = output_path.stat().st_size / 1024**2
    logger.info(f"Output file size: {output_size_mb:.1f} MB")
    logger.info(f"Size reduction: {(1 - output_size_mb/(input_path.stat().st_size/1024**2))*100:.1f}%")
    
    # Verify output
    pf_out = pq.ParquetFile(output_path)
    logger.info(f"Output has {pf_out.metadata.num_rows:,} rows and "
               f"{pf_out.metadata.num_columns:,} columns")


def main():
    """Optimize all matrix parquet files."""
    files_to_optimize = [
        ("train_matrix.parquet", "optimized/train_matrix.parquet"),
        ("val_matrix.parquet", "optimized/val_matrix.parquet"),
        ("test_matrix.parquet", "optimized/test_matrix.parquet"),
    ]
    
    for input_file, output_file in files_to_optimize:
        input_path = ARTEFACT_DIR / input_file
        output_path = ARTEFACT_DIR / output_file
        
        if input_path.exists():
            logger.info(f"\n{'='*60}")
            logger.info(f"Optimizing {input_file}")
            logger.info(f"{'='*60}")
            
            try:
                optimize_parquet_file(input_path, output_path)
                logger.info(f"✓ Successfully optimized {input_file}")
            except Exception as e:
                logger.error(f"✗ Failed to optimize {input_file}: {e}")
        else:
            logger.warning(f"File not found: {input_path}")
    
    logger.info("\nOptimization complete!")
    logger.info("Optimized files are in: artefacts/optimized/")
    logger.info("\nTo use optimized files, update your training scripts to use the 'optimized' directory.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Optimize parquet files")
    parser.add_argument("--input", type=str, help="Specific file to optimize")
    parser.add_argument("--output", type=str, help="Output path")
    parser.add_argument("--batch-size", type=int, default=50000, 
                       help="Batch size for processing")
    
    args = parser.parse_args()
    
    if args.input:
        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else input_path.parent / "optimized" / input_path.name
        optimize_parquet_file(input_path, output_path, args.batch_size)
    else:
        main()