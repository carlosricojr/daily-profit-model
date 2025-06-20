#!/usr/bin/env python
"""Memory-optimized training for LightGBM models.

This script addresses OOM issues by:
1. Loading only required columns for each model
2. Optimizing data types on load
3. Processing models sequentially
4. Aggressive garbage collection
"""

import pandas as pd
import lightgbm as lgb
import pyarrow.parquet as pq
from pathlib import Path
import joblib
import numpy as np
import gc
import psutil
from typing import Dict, List, Tuple, Optional
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"

# Model configuration
MODEL_CONFIGS = {
    "net_profit": {
        "objective": "regression",
        "metric": "mae",
        "description": "Daily net profit prediction"
    },
    "gross_profit": {
        "objective": "regression", 
        "metric": "mae",
        "description": "Daily gross profit prediction"
    },
    "num_trades": {
        "objective": "regression",
        "metric": "rmse", 
        "description": "Number of trades prediction"
    },
    "is_profitable": {
        "objective": "binary",
        "metric": "auc",
        "description": "Profitable day classification"
    }
}


def get_memory_usage_gb():
    """Get current memory usage in GB."""
    return psutil.Process().memory_info().rss / (1024 ** 3)


def optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Optimize DataFrame dtypes to reduce memory usage."""
    logger.info(f"Optimizing dtypes for {len(df.columns)} columns...")
    initial_memory = df.memory_usage(deep=True).sum() / 1024**3
    
    # Convert nullable Int64 to float64 (more memory efficient)
    for col in df.columns:
        if str(df[col].dtype).startswith('Int'):
            df[col] = df[col].astype('float64')
    
    # Convert low-cardinality object columns to category
    for col in df.select_dtypes(include=['object']).columns:
        num_unique = df[col].nunique()
        if num_unique / len(df) < 0.5:  # Less than 50% unique values
            df[col] = df[col].astype('category')
    
    # Downcast numeric types where possible
    for col in df.select_dtypes(include=['float64']).columns:
        # Check if values fit in float32
        col_min = df[col].min()
        col_max = df[col].max()
        if pd.notna(col_min) and pd.notna(col_max):
            if col_min > np.finfo(np.float32).min and col_max < np.finfo(np.float32).max:
                df[col] = df[col].astype('float32')
    
    final_memory = df.memory_usage(deep=True).sum() / 1024**3
    logger.info(f"Memory reduced from {initial_memory:.2f} GB to {final_memory:.2f} GB "
                f"({(1 - final_memory/initial_memory)*100:.1f}% reduction)")
    
    return df


def get_feature_columns(parquet_path: Path, target: str) -> List[str]:
    """Get non-null feature columns for a specific target."""
    logger.info(f"Analyzing columns for {target}...")
    
    # Read schema
    pf = pq.ParquetFile(parquet_path)
    all_columns = pf.schema_arrow.names
    
    # We need the target column and feature columns
    target_col = f"target_{target}"
    
    # Read a sample to check for all-null columns
    sample_df = pf.read_row_group(0).to_pandas()
    
    # Find non-null columns
    non_null_columns = []
    for col in all_columns:
        if col.startswith('target_'):
            # Keep all target columns for now
            if col == target_col:
                non_null_columns.append(col)
        elif sample_df[col].notna().any():
            # Only keep feature columns with at least one non-null value
            non_null_columns.append(col)
    
    logger.info(f"Selected {len(non_null_columns)} non-null columns out of {len(all_columns)}")
    return non_null_columns


def load_data_for_target(split: str, target: str, columns: List[str]) -> Tuple[pd.DataFrame, pd.Series]:
    """Load data efficiently for a specific target."""
    logger.info(f"Loading {split} data for {target}...")
    logger.info(f"Memory usage before load: {get_memory_usage_gb():.2f} GB")
    
    # Prefer clean version if available
    clean_path = ARTEFACT_DIR / "clean" / f"{split}_matrix.parquet"
    original_path = ARTEFACT_DIR / f"{split}_matrix.parquet"
    
    path = clean_path if clean_path.exists() else original_path
    
    # Load only required columns
    df = pd.read_parquet(path, columns=columns, engine='pyarrow')
    
    # Optimize dtypes immediately
    df = optimize_dtypes(df)
    
    # Filter rows with non-null target
    target_col = f"target_{target}"
    mask = df[target_col].notna()
    df = df[mask].copy()
    
    logger.info(f"Loaded {len(df):,} rows with {len(df.columns)} columns")
    logger.info(f"Memory usage after load: {get_memory_usage_gb():.2f} GB")
    
    # Separate features and target
    feature_cols = [c for c in df.columns if not c.startswith('target_')]
    X = df[feature_cols]
    y = df[target_col]
    
    # Clean up
    del df
    gc.collect()
    
    return X, y


def train_single_model(target: str, config: Dict, columns: List[str]) -> lgb.Booster:
    """Train a single model with memory optimization."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Training model for: {target}")
    logger.info(f"Description: {config['description']}")
    logger.info(f"{'='*60}")
    
    try:
        # Load data
        X_train, y_train = load_data_for_target("train", target, columns)
        X_val, y_val = load_data_for_target("val", target, columns)
        
        logger.info(f"Training samples: {len(X_train):,}")
        logger.info(f"Validation samples: {len(X_val):,}")
        
        # Create LightGBM datasets
        # Initialize Woodwork for categorical detection
        X_train.ww.init()
        cat_features = X_train.ww.select(include=["categorical", "boolean"]).columns.tolist()
        
        train_data = lgb.Dataset(X_train, label=y_train, categorical_feature=cat_features)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
        
        # Parameters (simplified for memory efficiency)
        params = {
            "objective": config["objective"],
            "metric": config["metric"],
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
            "random_state": 42,
            "num_threads": 4  # Limit threads to reduce memory
        }
        
        # Train model
        logger.info("Training model...")
        model = lgb.train(
            params,
            train_data,
            valid_sets=[val_data],
            num_boost_round=1000,
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)]
        )
        
        # Evaluate
        val_pred = model.predict(X_val, num_iteration=model.best_iteration)
        if config["objective"] == "regression":
            if config["metric"] == "mae":
                score = np.mean(np.abs(val_pred - y_val))
            else:  # rmse
                score = np.sqrt(np.mean((val_pred - y_val) ** 2))
        else:  # binary
            from sklearn.metrics import roc_auc_score
            score = roc_auc_score(y_val, val_pred)
        
        logger.info(f"Validation {config['metric']}: {score:.4f}")
        
        # Save model
        model_dir = ARTEFACT_DIR / "models"
        model_dir.mkdir(exist_ok=True)
        model_path = model_dir / f"lgb_{target}_memory_opt.txt"
        model.save_model(str(model_path))
        logger.info(f"Model saved to: {model_path}")
        
        # Aggressive cleanup
        del X_train, y_train, X_val, y_val, train_data, val_data
        gc.collect()
        
        logger.info(f"Memory after cleanup: {get_memory_usage_gb():.2f} GB")
        
        return model
        
    except Exception as e:
        logger.error(f"Error training {target}: {e}")
        return None


def main():
    """Train models with memory optimization."""
    logger.info("Starting memory-optimized training")
    logger.info(f"Initial memory: {get_memory_usage_gb():.2f} GB")
    
    # Determine which parquet file to analyze
    clean_train = ARTEFACT_DIR / "clean" / "train_matrix.parquet"
    original_train = ARTEFACT_DIR / "train_matrix.parquet"
    train_path = clean_train if clean_train.exists() else original_train
    
    logger.info(f"Using training data: {train_path}")
    
    # Train each model sequentially
    models = {}
    for target, config in MODEL_CONFIGS.items():
        # Get columns for this target
        columns = get_feature_columns(train_path, target)
        
        # Train model
        model = train_single_model(target, config, columns)
        if model:
            models[target] = model
        
        # Force garbage collection between models
        gc.collect()
    
    logger.info(f"\nTraining complete. Successfully trained {len(models)} models.")
    logger.info(f"Final memory usage: {get_memory_usage_gb():.2f} GB")
    
    # Save model list
    model_list = list(models.keys())
    joblib.dump(model_list, ARTEFACT_DIR / "models" / "memory_opt_models.joblib")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Memory-optimized model training")
    parser.add_argument("--targets", nargs="+", help="Specific targets to train")
    parser.add_argument("--sample-frac", type=float, default=1.0, 
                       help="Fraction of data to use (for testing)")
    
    args = parser.parse_args()
    
    if args.targets:
        # Filter MODEL_CONFIGS to only requested targets
        MODEL_CONFIGS = {k: v for k, v in MODEL_CONFIGS.items() if k in args.targets}
    
    main()