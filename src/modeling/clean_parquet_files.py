#!/usr/bin/env python
"""Clean parquet files by removing empty object columns and optimizing dtypes."""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
import gc
import psutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"
CLEAN_DIR = ARTEFACT_DIR / "clean"

def get_memory_gb():
    """Get current memory usage in GB."""
    return psutil.Process().memory_info().rss / (1024 ** 3)

def clean_parquet_file(input_path: Path, output_path: Path):
    """Clean a parquet file by removing empty columns and optimizing dtypes."""
    logger.info(f"\nCleaning {input_path.name}...")
    logger.info(f"Original file size: {input_path.stat().st_size / (1024**2):.1f} MB")
    
    # Load in chunks to handle memory better
    chunk_size = 50000
    chunks = []
    
    # Read file info first
    total_rows = pd.read_parquet(input_path, columns=['daily_id']).shape[0]
    logger.info(f"Total rows: {total_rows:,}")
    
    # Get column names and identify which to keep
    sample_df = pd.read_parquet(input_path).head(1000)
    
    # Identify columns to drop (empty object columns)
    columns_to_drop = []
    columns_to_convert = {}
    
    for col in sample_df.columns:
        if sample_df[col].dtype == 'object':
            if sample_df[col].notna().sum() == 0:
                columns_to_drop.append(col)
                logger.info(f"  Dropping empty column: {col}")
        elif sample_df[col].dtype == 'float64':
            # Check if we can safely convert to float32
            if col.startswith('target_'):
                continue  # Keep targets as float64 for precision
            columns_to_convert[col] = 'float32'
    
    logger.info(f"\nDropping {len(columns_to_drop)} empty object columns")
    logger.info(f"Converting {len(columns_to_convert)} float64 columns to float32")
    
    # Process in chunks
    logger.info("\nProcessing file in chunks...")
    for i in range(0, total_rows, chunk_size):
        if i % (chunk_size * 5) == 0:
            logger.info(f"  Processing rows {i:,} to {min(i + chunk_size, total_rows):,} - Memory: {get_memory_gb():.1f} GB")
        
        # Read chunk
        chunk_df = pd.read_parquet(
            input_path,
            columns=lambda x: x not in columns_to_drop
        ).iloc[i:i+chunk_size]
        
        # Convert dtypes
        for col, new_dtype in columns_to_convert.items():
            if col in chunk_df.columns:
                chunk_df[col] = chunk_df[col].astype(new_dtype)
        
        chunks.append(chunk_df)
        
        # Periodically consolidate to avoid too many chunks in memory
        if len(chunks) >= 10:
            logger.info(f"  Consolidating chunks... Memory: {get_memory_gb():.1f} GB")
            consolidated = pd.concat(chunks, ignore_index=False)
            chunks = [consolidated]
            gc.collect()
    
    # Final consolidation
    logger.info("Consolidating all chunks...")
    clean_df = pd.concat(chunks, ignore_index=False)
    
    # Save cleaned file
    logger.info(f"Saving cleaned file to {output_path}...")
    clean_df.to_parquet(output_path, engine='pyarrow', compression='snappy')
    
    # Report results
    logger.info(f"\n✓ Cleaning complete!")
    logger.info(f"  Original columns: {len(sample_df.columns)}")
    logger.info(f"  Cleaned columns: {len(clean_df.columns)}")
    logger.info(f"  Original file size: {input_path.stat().st_size / (1024**2):.1f} MB")
    logger.info(f"  Cleaned file size: {output_path.stat().st_size / (1024**2):.1f} MB")
    logger.info(f"  Memory usage of cleaned data: {clean_df.memory_usage(deep=True).sum() / (1024**3):.2f} GB")
    
    # Clean up
    del clean_df, chunks
    gc.collect()

def main():
    """Clean all feature matrices."""
    
    CLEAN_DIR.mkdir(exist_ok=True)
    
    # Clean each matrix
    for split in ['train', 'val', 'test']:
        input_path = ARTEFACT_DIR / f"{split}_matrix.parquet"
        output_path = CLEAN_DIR / f"{split}_matrix.parquet"
        
        if not input_path.exists():
            logger.warning(f"{input_path} not found, skipping...")
            continue
            
        if output_path.exists():
            logger.info(f"{output_path} already exists, skipping...")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Cleaning {split} matrix")
        logger.info(f"{'='*60}")
        
        clean_parquet_file(input_path, output_path)
        logger.info(f"Memory after {split}: {get_memory_gb():.1f} GB")
    
    logger.info("\n✓ All files cleaned!")
    logger.info(f"\nCleaned files saved to: {CLEAN_DIR}")
    logger.info("\nTo use cleaned files in training, update the path to:")
    logger.info(f"  ARTEFACT_DIR / 'clean' / f'{{split}}_matrix.parquet'")

if __name__ == "__main__":
    main()