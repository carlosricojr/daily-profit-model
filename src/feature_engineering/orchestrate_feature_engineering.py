#!/usr/bin/env python
"""
Orchestrate the complete feature engineering pipeline.

This script coordinates:
1. Preparing and cleaning raw daily and hourly data.
2. Building feature definitions (if needed).
3. Building feature matrices (features only for training).
4. Adding targets to all matrices.
5. Final validation of outputs.

Usage:
    uv run --env-file .env.local -- python -m src.feature_engineering.orchestrate_feature_engineering [--rebuild-definitions]
"""

import argparse
import logging
import pathlib
import sys
import subprocess
from datetime import datetime
import pandas as pd

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Resolve repository root (two levels up from current file: src/feature_engineering/)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"
CLEANED_DATA_DIR = ARTEFACT_DIR / "cleaned_data"
FEATURE_DEF_PATH = ARTEFACT_DIR / "daily_feature_defs_v1.joblib"

def run_subprocess(cmd: list, description: str, timeout_minutes: int = 60) -> bool:
    """Run a subprocess and return True if successful."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Starting: {description}")
    logger.info(f"Command: {' '.join(cmd)}")
    logger.info(f"Timeout: {timeout_minutes} minutes")
    logger.info(f"{'='*60}\n")
    
    start_time = datetime.now()
    
    try:
        # Use Popen for real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )
        
        # Stream output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())  # Print to console
                logger.debug(output.strip())  # Also log it
        
        # Wait for process to complete
        return_code = process.poll()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if return_code == 0:
            logger.info(f"\n✓ {description} completed successfully in {elapsed:.1f} seconds")
            return True
        else:
            logger.error(f"\n✗ {description} failed after {elapsed:.1f} seconds")
            logger.error(f"Return code: {return_code}")
            return False
        
    except subprocess.TimeoutExpired:
        logger.error(f"\n✗ {description} timed out after {timeout_minutes} minutes")
        process.kill()
        return False
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"\n✗ {description} failed with error after {elapsed:.1f} seconds: {e}")
        return False

def check_feature_definitions() -> bool:
    """Check if feature definitions exist."""
    if FEATURE_DEF_PATH.exists():
        logger.info(f"Feature definitions found at {FEATURE_DEF_PATH}")
        try:
            # Try to get file info
            size_mb = FEATURE_DEF_PATH.stat().st_size / (1024 * 1024)
            logger.info(f"  Size: {size_mb:.2f} MB")
            logger.info(f"  Modified: {datetime.fromtimestamp(FEATURE_DEF_PATH.stat().st_mtime)}")
            return True
        except Exception as e:
            logger.warning(f"Could not read feature definitions: {e}")
            return False
    else:
        logger.info("Feature definitions not found")
        return False

def validate_outputs() -> dict:
    """Validate that all expected outputs exist and have correct structure."""
    logger.info("\nValidating outputs...")
    
    results = {
        'cleaned_daily_data': False,
        'cleaned_hourly_data': False,
        'feature_definitions': False,
        'test_matrix': False,
        'val_matrix': False,
        'train_matrix': False,
        'all_have_targets': True,
        'total_rows': 0
    }

    CLEANED_DATA_DIR.mkdir(exist_ok=True)
    daily_cleaned_path = CLEANED_DATA_DIR / "daily_metrics_df.parquet"
    hourly_cleaned_path = CLEANED_DATA_DIR / "hourly_metrics_df.parquet"
    
    if daily_cleaned_path.exists():
        logger.info(f"  daily_metrics_df.parquet: FOUND")
        results['cleaned_daily_data'] = True
    else:
        logger.info(f"  daily_metrics_df.parquet: NOT FOUND")

    if hourly_cleaned_path.exists():
        logger.info(f"  hourly_metrics_df.parquet: FOUND")
        results['cleaned_hourly_data'] = True
    else:
        logger.info(f"  hourly_metrics_df.parquet: NOT FOUND")
    
    # Check feature definitions
    results['feature_definitions'] = FEATURE_DEF_PATH.exists()
    
    # Check matrices
    for split in ['test', 'val', 'train']:
        matrix_path = ARTEFACT_DIR / f"{split}_matrix.parquet"
        
        if matrix_path.exists():
            try:
                # Get schema using pyarrow to avoid loading data
                import pyarrow.parquet as pq
                parquet_file = pq.ParquetFile(matrix_path)
                schema = parquet_file.schema
                n_rows = parquet_file.metadata.num_rows
                
                # Count features and targets from schema
                all_columns = [field.name for field in schema]
                has_features = sum(1 for col in all_columns if not col.startswith('target_'))
                has_targets = sum(1 for col in all_columns if col.startswith('target_'))
                
                logger.info(f"  {split}_matrix.parquet: {n_rows:,} rows, {has_features} features, {has_targets} targets")
                
                results[f'{split}_matrix'] = True
                results['total_rows'] += n_rows
                
                if has_targets == 0:
                    results['all_have_targets'] = False
                    logger.warning("    WARNING: No target columns found!")
                
            except Exception as e:
                logger.error(f"  {split}_matrix.parquet: ERROR - {e}")
                results[f'{split}_matrix'] = False
        else:
            logger.info(f"  {split}_matrix.parquet: NOT FOUND")
            results[f'{split}_matrix'] = False
    
    # Summary
    logger.info(f"\nTotal rows across all matrices: {results['total_rows']:,}")
    
    return results

def main():
    """Main orchestration function."""
    parser = argparse.ArgumentParser(description="Orchestrate feature engineering pipeline")
    parser.add_argument(
        "--rebuild-definitions",
        action="store_true",
        help="Force rebuild of feature definitions even if they exist"
    )

    parser.add_argument(
        "--data-prep-type",
        choices=['all', 'daily', 'hourly'],
        default='all',
        help="Specify which raw metrics to prepare (daily, hourly, or all)."
    )

    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip cleanup of intermediate files"
    )
    args = parser.parse_args()
    
    logger.info("Starting feature engineering orchestration...")
    logger.info(f"Working directory: {pathlib.Path.cwd()}")
    logger.info(f"Artefacts directory: {ARTEFACT_DIR.absolute()}")
    
    # Ensure artefacts directory exists
    ARTEFACT_DIR.mkdir(exist_ok=True)

    # Step 1: Prepare and clean raw data
    data_prep_cmd = [
        "uv", "run", "--env-file", ".env.local", "--", "python", "-m",
        "src.feature_engineering.prepare_data_streaming"
    ]
    # Add the flag if a specific type is requested
    if args.data_prep_type != 'all':
        data_prep_cmd.extend(["--metrics-type", args.data_prep_type])

    success = run_subprocess(
        data_prep_cmd,
        "Step 1: Preparing and cleaning raw data",
        timeout_minutes=120  # Give this step a generous timeout
    )
    if not success:
        logger.error("Failed to prepare data. Halting pipeline.")
        sys.exit(1)
    
    # Step 2: Build feature definitions if needed
    if args.rebuild_definitions or not check_feature_definitions():
        success = run_subprocess(
            ["uv", "run", "--env-file", ".env.local", "--", "python", "-m", 
             "src.feature_engineering.ft_feature_engineering"],
            "Step 2: Building feature definitions"
        )
        
        if not success:
            logger.error("Failed to build feature definitions")
            sys.exit(1)
    else:
        logger.info("Using existing feature definitions for Step 2.")
    
    # Step 3: Build feature matrices
    success = run_subprocess(
        ["uv", "run", "--env-file", ".env.local", "--", "python", "-m",
         "src.feature_engineering.ft_build_feature_matrix"],
        "Step 3: Building feature matrices"
    )
    
    if not success:
        logger.error("Failed to build feature matrices")
        sys.exit(1)
    
    # Step 4: Add targets to feature matrices
    success = run_subprocess(
        ["uv", "run", "--env-file", ".env.local", "--", "python", "-m",
         "src.feature_engineering.add_targets_to_features"],
        "Step 4: Adding targets to feature matrices"
    )
    
    if not success:
        logger.error("Failed to add targets to feature matrices")
        sys.exit(1)
    
    # Step 5: Concatenate training chunks into final train_matrix.parquet
    # Check if we have chunks to concatenate
    chunk_files = list(ARTEFACT_DIR.glob("train_chunk_*.parquet"))
    chunk_files = [f for f in chunk_files if not f.name.endswith('_features.parquet')]
    
    if chunk_files:
        logger.info(f"Found {len(chunk_files)} training chunks to concatenate")
        
        success = run_subprocess(
            ["uv", "run", "--env-file", ".env.local", "--", "python", "-m",
             "src.feature_engineering.concatenate_training_chunks", "--force"],
            "Step 5: Concatenating training chunks",
            timeout_minutes=30
        )
        
        if not success:
            logger.error("Failed to concatenate training chunks")
            sys.exit(1)
    else:
        logger.info("No training chunks found - skipping Step 5: Concatenation")
    
    # Step 6: Validate outputs
    validation_results = validate_outputs()
    
    # Step 7: Cleanup (optional) - now handled by concatenate_training_chunks
    # We'll just remove any error files or other temporary files
    if not args.skip_cleanup:
        logger.info("\nCleaning up any error files...")
        error_files = list(ARTEFACT_DIR.glob("*_error.parquet"))
        removed_count = 0
        for error_file in error_files:
            try:
                error_file.unlink()
                removed_count += 1
                logger.debug(f"  Removed: {error_file.name}")
            except Exception as e:
                logger.warning(f"  Could not remove {error_file.name}: {e}")
        if removed_count > 0:
            logger.info(f"  Removed {removed_count} error files")
    
    # Final summary
    logger.info("\n" + "="*60)
    logger.info("FEATURE ENGINEERING PIPELINE COMPLETE")
    logger.info("="*60)
    
    all_good = all([
        validation_results['cleaned_daily_data'],
        validation_results['cleaned_hourly_data'],
        validation_results['feature_definitions'],
        validation_results['test_matrix'],
        validation_results['val_matrix'],
        validation_results['train_matrix'],
        validation_results['all_have_targets']
    ])
    
    if all_good:
        logger.info("✓ All outputs successfully created")
        logger.info(f"✓ Total rows: {validation_results['total_rows']:,}")
        logger.info("\nNext steps:")
        logger.info("  1. Run model training with the generated matrices")
        logger.info("  2. Matrices are in: artefacts/")
        return 0
    else:
        logger.error("✗ Some outputs are missing or incomplete")
        for key, value in validation_results.items():
            if key != 'total_rows' and not value:
                logger.error(f"  - {key}: FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())