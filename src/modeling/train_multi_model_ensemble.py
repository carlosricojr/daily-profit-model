#!/usr/bin/env python
"""Example script showing how to train multiple models for ensemble predictions.

This demonstrates the multi-model approach where we train separate models
for different target variables and combine them for hedging decisions.
"""

import pandas as pd
import lightgbm as lgb
from pathlib import Path
import joblib
import numpy as np
from typing import Dict
import psutil
import gc

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"

def get_memory_usage():
    """Get current memory usage in GB."""
    process = psutil.Process()
    return process.memory_info().rss / (1024 ** 3)

def print_memory_usage(stage: str):
    """Print current memory usage with a stage label."""
    mem_gb = get_memory_usage()
    available_gb = psutil.virtual_memory().available / (1024 ** 3)
    total_gb = psutil.virtual_memory().total / (1024 ** 3)
    percent = psutil.virtual_memory().percent
    print(f"\n[Memory] {stage}: {mem_gb:.2f} GB used | {available_gb:.2f} GB available | {percent:.1f}% of {total_gb:.1f} GB total")

# Model configuration for different targets
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
    "gross_loss": {
        "objective": "regression",
        "metric": "mae",
        "description": "Daily gross loss prediction"
    },
    "num_trades": {
        "objective": "regression",
        "metric": "rmse", 
        "description": "Number of trades prediction"
    },
    "success_rate": {
        "objective": "regression",
        "metric": "mae",
        "description": "Daily success rate prediction"
    },
    "risk_adj_ret": {
        "objective": "regression",
        "metric": "mae",
        "description": "Risk adjusted return prediction"
    },
    "max_drawdown": {
        "objective": "regression",
        "metric": "mae",
        "description": "Maximum drawdown prediction"
    },
    "is_profitable": {
        "objective": "binary",
        "metric": "auc",
        "description": "Profitable day classification"
    },
    "is_highly_profitable": {
        "objective": "binary",
        "metric": "auc", 
        "description": "High profit day classification"
    }
}

def load_feature_matrix(split: str) -> pd.DataFrame:
    """Load feature matrix for a given split."""
    # Try cleaned version first
    clean_path = ARTEFACT_DIR / "clean" / f"{split}_matrix.parquet"
    if clean_path.exists():
        path = clean_path
        print(f"  Loading cleaned {split} matrix...")
    else:
        path = ARTEFACT_DIR / f"{split}_matrix.parquet"
        print(f"  Loading original {split} matrix...")
    return pd.read_parquet(path)

def prepare_data_for_target(df: pd.DataFrame, target: str) -> tuple:
    """Prepare features and target for a specific model."""
    # Get target column
    target_col = f"target_{target}"
    if target_col not in df.columns:
        raise ValueError(f"Target column {target_col} not found in dataframe")
    
    # Remove rows with missing target values FOR THIS SPECIFIC TARGET
    # This allows us to use all available data for each target
    mask = ~df[target_col].isna()
    df_filtered = df[mask].copy()
    
    print(f"  Filtered {(~mask).sum():,} rows with missing {target} values ({len(df_filtered):,} remaining)")
    
    # 1. re-attach Woodwork typing (fast – uses pandas dtypes + stored metadata)
    df_filtered.ww.init()                      # if .ww is not already initialised

    # 2. pull every column whose logical type is Categorical or Boolean
    cat_cols = df_filtered.ww.select(include=["categorical", "boolean"]).columns.tolist()

    # 3. remove target columns
    feature_cols = [c for c in df_filtered.columns if not c.startswith("target_")]

    X = df_filtered[feature_cols]
    y = df_filtered[target_col]
    
    return X, y

def train_model(X_train, y_train, X_val, y_val, config: dict) -> lgb.LGBMModel:
    """Train a LightGBM model with given configuration."""
    
    # 4. tell LightGBM which columns are categorical
    train_data = lgb.Dataset(X_train, label=y_train, categorical_feature=X_train.ww.select(include=["categorical", "boolean", "country_code"]).columns.tolist())
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
    
    # Base parameters
    params = {
        "objective": config["objective"],
        "metric": config["metric"],
        "boosting_type": "gbdt",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "random_state": 42
    }
    
    # Train model
    model = lgb.train(
        params,
        train_data,
        valid_sets=[val_data],
        num_boost_round=1000,
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)]
    )
    
    return model

def calculate_ensemble_score(predictions: Dict[str, np.ndarray]) -> np.ndarray:
    """Calculate ensemble hedging score from multiple model predictions."""
    
    # Example weighted ensemble logic
    # You can customize this based on business requirements
    
    # Get length from any prediction array
    n_samples = len(next(iter(predictions.values())))
    score = np.zeros(n_samples)
    
    # Net profit contribution (30% weight)
    if "net_profit" in predictions:
        # Normalize to 0-1 range
        profit_score = (predictions["net_profit"] - predictions["net_profit"].min()) / \
                      (predictions["net_profit"].max() - predictions["net_profit"].min() + 1e-8)
        score += 0.30 * profit_score
    
    # Profitability probability (20% weight)
    if "is_profitable" in predictions:
        score += 0.20 * predictions["is_profitable"]
    
    # High profit probability (15% weight)  
    if "is_highly_profitable" in predictions:
        score += 0.15 * predictions["is_highly_profitable"]
    
    # Success rate (10% weight) - prefer higher win rates
    if "success_rate" in predictions:
        score += 0.10 * predictions["success_rate"]
    
    # Activity level (5% weight) - moderate activity is good
    if "num_trades" in predictions:
        # Normalize and cap extreme values
        trades_norm = (predictions["num_trades"] - predictions["num_trades"].min()) / \
                     (predictions["num_trades"].max() - predictions["num_trades"].min() + 1e-8)
        # Prefer moderate activity (inverse U-shape)
        activity_score = trades_norm * (1 - 0.5 * trades_norm)
        score += 0.05 * activity_score
    
    # Risk-adjusted return (10% weight) - prefer higher risk-adjusted returns
    if "risk_adj_ret" in predictions:
        risk_score = (predictions["risk_adj_ret"] - predictions["risk_adj_ret"].min()) / \
                    (predictions["risk_adj_ret"].max() - predictions["risk_adj_ret"].min() + 1e-8)
        score += 0.10 * risk_score
    
    # Drawdown penalty (10% weight) - penalize high drawdowns
    if "max_drawdown" in predictions:
        # Invert drawdown so lower drawdown = higher score
        drawdown_score = 1 - (predictions["max_drawdown"] - predictions["max_drawdown"].min()) / \
                        (predictions["max_drawdown"].max() - predictions["max_drawdown"].min() + 1e-8)
        score += 0.10 * drawdown_score
    
    return score

def main():
    """Train ensemble of models for different targets."""
    
    print_memory_usage("Start")
    
    print("\nLoading feature matrices...")
    train_df = load_feature_matrix("train")
    print_memory_usage("After loading train")
    
    val_df = load_feature_matrix("val")
    print_memory_usage("After loading val")
    
    test_df = load_feature_matrix("test")
    print_memory_usage("After loading test")
    
    print(f"\nTrain shape: {train_df.shape}")
    print(f"Val shape: {val_df.shape}")
    print(f"Test shape: {test_df.shape}")
    
    # Train models for each target
    models = {}
    test_predictions = {}
    
    for target, config in MODEL_CONFIGS.items():
        print(f"\n{'='*60}")
        print(f"Training model for: {target}")
        print(f"Description: {config['description']}")
        print(f"{'='*60}")
        
        try:
            # Prepare data
            X_train, y_train = prepare_data_for_target(train_df, target)
            X_val, y_val = prepare_data_for_target(val_df, target)
            X_test, y_test = prepare_data_for_target(test_df, target)
            
            print(f"Training samples: {len(X_train)}")
            print(f"Target distribution: mean={y_train.mean():.3f}, std={y_train.std():.3f}")
            
            print_memory_usage(f"Before training {target}")
            
            # Train model
            model = train_model(X_train, y_train, X_val, y_val, config)
            models[target] = model
            
            print_memory_usage(f"After training {target}")
            
            # Make test predictions
            test_pred = model.predict(X_test, num_iteration=model.best_iteration)
            test_predictions[target] = test_pred
            
            # Evaluate on test set
            if config["objective"] == "regression":
                mae = np.mean(np.abs(test_pred - y_test))
                print(f"Test MAE: {mae:.3f}")
            else:
                from sklearn.metrics import roc_auc_score
                auc = roc_auc_score(y_test, test_pred)
                print(f"Test AUC: {auc:.3f}")
            
            # Clean up temporary data to free memory
            del X_train, y_train, X_val, y_val, X_test, y_test
            gc.collect()
            print_memory_usage(f"After cleanup for {target}")
                
        except Exception as e:
            print(f"Error training model for {target}: {e}")
            continue
    
    # Calculate ensemble scores
    if test_predictions:
        print(f"\n{'='*60}")
        print("Calculating ensemble hedging scores...")
        ensemble_scores = calculate_ensemble_score(test_predictions)
        
        print("Ensemble score distribution:")
        print(f"  Mean: {ensemble_scores.mean():.3f}")
        print(f"  Std: {ensemble_scores.std():.3f}")
        print(f"  Min: {ensemble_scores.min():.3f}")
        print(f"  Max: {ensemble_scores.max():.3f}")
        
        # Save models and ensemble logic
        model_dir = ARTEFACT_DIR / "models"
        model_dir.mkdir(exist_ok=True)
        
        for target, model in models.items():
            model_path = model_dir / f"lgb_{target}_v1.txt"
            model.save_model(str(model_path))
            print(f"Saved model: {model_path}")
        
        # Save ensemble configuration
        ensemble_config = {
            "models": list(models.keys()),
            "weights": {
                "net_profit": 0.30,
                "is_profitable": 0.20,
                "is_highly_profitable": 0.15,
                "success_rate": 0.10,
                "num_trades": 0.05,
                "risk_adj_ret": 0.10,
                "max_drawdown": 0.10
            }
        }
        joblib.dump(ensemble_config, model_dir / "ensemble_config.joblib")
        print("Saved ensemble configuration")
    
    # Final cleanup
    del train_df, val_df, test_df
    gc.collect()
    print_memory_usage("Final")

if __name__ == "__main__":
    main()
