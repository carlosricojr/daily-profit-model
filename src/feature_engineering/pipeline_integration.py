"""
Integration module for feature engineering in the main pipeline.

This module provides a simple interface for the pipeline orchestrator to run
the feature engineering stage.
"""

import logging
import subprocess
import pathlib
from typing import Dict, Any

logger = logging.getLogger(__name__)


def run_feature_engineering(config: Dict[str, Any]) -> bool:
    """
    Run the feature engineering pipeline stage.
    
    This function is designed to be called from src.pipeline_orchestration.run_pipeline
    
    Args:
        config: Configuration dictionary from the main pipeline
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Starting feature engineering stage...")
    
    # Determine environment file
    env_file = config.get('env_file', '.env.local')
    
    # Build command
    cmd = [
        "uv", "run", "--env-file", env_file, "--",
        "python", "-m", "src.feature_engineering.orchestrate_feature_engineering"
    ]
    
    # Add flags based on config
    if config.get('rebuild_feature_definitions', False):
        cmd.append("--rebuild-definitions")
    
    if config.get('skip_cleanup', False):
        cmd.append("--skip-cleanup")
    
    try:
        # Run the orchestration script
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=pathlib.Path.cwd()  # Ensure we're in the right directory
        )
        
        logger.info("Feature engineering completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Feature engineering failed with return code: {e.returncode}")
        if e.stdout:
            logger.error(f"Stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"Stderr: {e.stderr}")
        return False


def check_feature_engineering_outputs() -> Dict[str, bool]:
    """
    Check if feature engineering outputs exist.
    
    Returns:
        dict: Status of each expected output file
    """
    # Resolve repository root (two levels up from current file: src/feature_engineering/)
    artefact_dir = pathlib.Path(__file__).resolve().parents[2] / "artefacts"
    
    outputs = {
        'feature_definitions': artefact_dir / "daily_feature_defs_v1.joblib",
        'train_matrix': artefact_dir / "train_matrix.parquet",
        'val_matrix': artefact_dir / "val_matrix.parquet",
        'test_matrix': artefact_dir / "test_matrix.parquet"
    }
    
    status = {}
    for name, path in outputs.items():
        status[name] = path.exists()
        
    return status
