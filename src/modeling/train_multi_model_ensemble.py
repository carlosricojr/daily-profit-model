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
import woodwork as ww

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"

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
    "trades_placed": {
        "objective": "regression",
        "metric": "rmse", 
        "description": "Number of trades prediction"
    },
    "win_rate": {
        "objective": "regression",
        "metric": "mae",
        "description": "Daily win rate prediction"
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
    path = ARTEFACT_DIR / f"{split}_matrix.parquet"
    return pd.read_parquet(path)

def prepare_data_for_target(df: pd.DataFrame, target: str) -> tuple:
    """Prepare features and target for a specific model."""
    # 1. re-attach Woodwork typing (fast – uses pandas dtypes + stored metadata)
    df.ww.init()                      # if .ww is not already initialised

    # 2. pull every column whose logical type is Categorical or Boolean
    cat_cols = df.ww.select(include=["categorical", "boolean"]).columns.tolist()

    # 3. remove target columns
    feature_cols = [c for c in df.columns if not c.startswith("target_")]

    X = df[feature_cols]
    y = df[f"target_{target}"]
    
    # Remove rows with missing target values
    mask = ~y.isna()
    X = X[mask]
    y = y[mask]
    
    return X, y

def train_model(X_train, y_train, X_val, y_val, config: dict) -> lgb.LGBMModel:
    """Train a LightGBM model with given configuration."""
    
    # 4. tell LightGBM which columns are categorical
    train_data = lgb.Dataset(X_train, label=y_train, categorical_feature=X_train.ww.select(include=["categorical", "boolean"]).columns.tolist())
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
    
    score = np.zeros(len(predictions["net_profit"]))
    
    # Net profit contribution (40% weight)
    if "net_profit" in predictions:
        # Normalize to 0-1 range
        profit_score = (predictions["net_profit"] - predictions["net_profit"].min()) / \
                      (predictions["net_profit"].max() - predictions["net_profit"].min() + 1e-8)
        score += 0.4 * profit_score
    
    # Profitability probability (20% weight)
    if "is_profitable" in predictions:
        score += 0.2 * predictions["is_profitable"]
    
    # High profit probability (20% weight)  
    if "is_highly_profitable" in predictions:
        score += 0.2 * predictions["is_highly_profitable"]
    
    # Activity level (10% weight) - high activity might mean more exposure
    if "trades_placed" in predictions:
        activity_score = (predictions["trades_placed"] - predictions["trades_placed"].min()) / \
                        (predictions["trades_placed"].max() - predictions["trades_placed"].min() + 1e-8)
        score += 0.1 * activity_score
    
    # Win rate (10% weight)
    if "win_rate" in predictions:
        score += 0.1 * predictions["win_rate"]
    
    return score

def main():
    """Train ensemble of models for different targets."""
    
    print("Loading feature matrices...")
    train_df = load_feature_matrix("train")
    val_df = load_feature_matrix("val")
    test_df = load_feature_matrix("test")
    
    print(f"Train shape: {train_df.shape}")
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
            
            # Train model
            model = train_model(X_train, y_train, X_val, y_val, config)
            models[target] = model
            
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
                
        except Exception as e:
            print(f"Error training model for {target}: {e}")
            continue
    
    # Calculate ensemble scores
    if test_predictions:
        print(f"\n{'='*60}")
        print("Calculating ensemble hedging scores...")
        ensemble_scores = calculate_ensemble_score(test_predictions)
        
        print(f"Ensemble score distribution:")
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
                "net_profit": 0.4,
                "is_profitable": 0.2,
                "is_highly_profitable": 0.2,
                "trades_placed": 0.1,
                "win_rate": 0.1
            }
        }
        joblib.dump(ensemble_config, model_dir / "ensemble_config.joblib")
        print(f"Saved ensemble configuration")

if __name__ == "__main__":
    main()