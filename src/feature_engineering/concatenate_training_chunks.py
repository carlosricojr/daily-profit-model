#!/usr/bin/env python
"""
Utility script to concatenate training chunks into a single file.

This is a standalone script for when you need to combine the training chunks
after the main pipeline has completed.

Usage:
    uv run --env-file .env.local -- python -m src.feature_engineering.concatenate_training_chunks [--method METHOD]
    
    where METHOD is:
    - pyarrow: Memory-efficient streaming concatenation (default)
    - pandas: In-memory concatenation (requires ~200GB RAM)
"""

import argparse
import pathlib
import logging
import gc
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"


def concatenate_with_pyarrow(chunk_files: list) -> bool:
    """Memory-efficient concatenation using PyArrow."""
    try:
        import pyarrow.parquet as pq
        
        # Get total size estimate
        total_size_gb = sum(f.stat().st_size for f in chunk_files) / (1024**3)
        logger.info(f"Total size of chunks: {total_size_gb:.2f} GB")
        
        # Read first chunk to get schema
        logger.info("Reading schema from first chunk...")
        first_table = pq.read_table(chunk_files[0])
        schema = first_table.schema
        
        # Create output file
        output_path = ARTEFACT_DIR / "train_matrix.parquet"
        logger.info(f"Writing to {output_path}...")
        
        with pq.ParquetWriter(output_path, schema, compression='snappy') as writer:
            # Write first table
            writer.write_table(first_table)
            logger.info(f"  Written chunk 1/{len(chunk_files)}")
            del first_table
            
            # Stream remaining chunks
            for i, chunk_path in enumerate(chunk_files[1:], 2):
                table = pq.read_table(chunk_path)
                writer.write_table(table)
                logger.info(f"  Written chunk {i}/{len(chunk_files)}")
                
                # Free memory immediately
                del table
                gc.collect()
        
        # Verify output
        metadata = pq.read_metadata(output_path)
        logger.info(f"\nSuccessfully created {output_path}")
        logger.info(f"  Total rows: {metadata.num_rows:,}")
        logger.info(f"  Total columns: {metadata.num_columns}")
        logger.info(f"  File size: {output_path.stat().st_size / (1024**3):.2f} GB")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during PyArrow concatenation: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def validate_concatenation(output_path: pathlib.Path, chunk_files: list) -> bool:
    """Validate the concatenated file before cleanup."""
    try:
        import pyarrow.parquet as pq
        import pandas as pd
        
        logger.info("\nValidating concatenated file...")
        
        # Get metadata without loading the data
        metadata = pq.read_metadata(output_path)
        output_rows = metadata.num_rows
        output_cols = metadata.num_columns
        
        # Calculate expected rows
        expected_rows = 0
        for chunk_path in chunk_files:
            chunk_meta = pq.read_metadata(chunk_path)
            expected_rows += chunk_meta.num_rows
        
        logger.info(f"  Expected rows: {expected_rows:,}")
        logger.info(f"  Actual rows: {output_rows:,}")
        logger.info(f"  Columns: {output_cols}")
        
        # Check row count matches
        if output_rows != expected_rows:
            logger.error(f"Row count mismatch! Expected {expected_rows}, got {output_rows}")
            return False
        
        # Check for target columns
        schema = metadata.schema.to_arrow_schema()
        target_cols = [field.name for field in schema if field.name.startswith('target_')]
        logger.info(f"  Target columns: {len(target_cols)}")
        
        if not target_cols:
            logger.error("No target columns found in concatenated file!")
            return False
        
        # Quick sample check
        logger.info("  Checking sample data...")
        # PyArrow doesn't support nrows in read_parquet, so we'll read a small subset differently
        sample_table = pq.read_table(output_path, columns=target_cols[:3])
        sample_df = sample_table.slice(0, min(1000, sample_table.num_rows)).to_pandas()
        
        # Check for nulls in targets
        null_counts = sample_df[target_cols[:3]].isnull().sum()
        if null_counts.any():
            logger.warning(f"  Found nulls in sample: {null_counts.to_dict()}")
        
        logger.info("✓ Validation passed!")
        return True
        
    except Exception as e:
        logger.error(f"Validation failed: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Concatenate training chunks")
    parser.add_argument(
        "--no-validate",
        action='store_true',
        help="Skip validation after concatenation"
    )
    parser.add_argument(
        "--no-cleanup",
        action='store_true',
        help="Keep chunk files after successful concatenation"
    )
    parser.add_argument(
        "--force",
        action='store_true',
        help="Overwrite existing output file without prompting"
    )
    args = parser.parse_args()
    
    # Check if output already exists
    output_path = ARTEFACT_DIR / "train_matrix.parquet"
    if output_path.exists():
        if args.force:
            logger.warning(f"{output_path} already exists! Overwriting due to --force flag")
        else:
            logger.warning(f"{output_path} already exists!")
            response = input("Overwrite? (y/N): ")
            if response.lower() != 'y':
                logger.info("Cancelled")
                return 0
    
    # Find chunk files (with targets)
    chunk_files = sorted(ARTEFACT_DIR.glob("train_chunk_*.parquet"))
    # Exclude the raw feature chunks
    chunk_files = [f for f in chunk_files if not f.name.endswith('_features.parquet')]
    
    if not chunk_files:
        logger.error("No training chunks with targets found!")
        logger.info("Make sure to run add_targets_to_features.py first")
        return 1
    
    logger.info(f"Found {len(chunk_files)} training chunks with targets")
    
    # Always use PyArrow for concatenation
    success = concatenate_with_pyarrow(chunk_files)
    
    if not success:
        logger.error("Concatenation failed!")
        return 1
    
    # Validate unless skipped
    if not args.no_validate:
        if not validate_concatenation(output_path, chunk_files):
            logger.error("Validation failed! Chunks will be preserved.")
            return 1
    
    # Cleanup chunks after successful concatenation and validation
    if not args.no_cleanup:
        logger.info("\nCleaning up chunk files...")
        
        # Delete both the chunks with targets and the original feature chunks
        patterns = [
            "train_chunk_*.parquet",  # Chunks with targets
            "train_chunk_*_features.parquet"  # Original feature chunks
        ]
        
        removed_count = 0
        for pattern in patterns:
            for chunk_path in ARTEFACT_DIR.glob(pattern):
                try:
                    chunk_path.unlink()
                    removed_count += 1
                    logger.debug(f"  Deleted {chunk_path.name}")
                except Exception as e:
                    logger.warning(f"  Could not delete {chunk_path}: {e}")
        
        logger.info(f"  Removed {removed_count} chunk files")
    else:
        logger.info("\nChunk files preserved (--no-cleanup flag)")
    
    logger.info("\n✓ Successfully created train_matrix.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())