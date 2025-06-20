#!/usr/bin/env python
"""Train LightGBM models with Optuna hyperparameter optimization.

This module implements best practices for using Optuna with LightGBM including:
- Comprehensive hyperparameter search spaces
- Pruning for early stopping of unpromising trials
- Cross-validation integration
- Parallel trial execution
- Visualization and reporting
"""

import pandas as pd
import lightgbm as lgb
import optuna
try:
    from optuna.integration import LightGBMPruningCallback
except (ImportError, ModuleNotFoundError):
    # Fallback if optuna-integration is not installed
    import optuna
    
    class LightGBMPruningCallback:
        """Fallback pruning callback if optuna-integration not available."""
        def __init__(self, trial, metric, valid_name="valid_0"):
            self.trial = trial
            self.metric = metric
            self.valid_name = valid_name
            
        def __call__(self, env):
            # Get the evaluation result
            for eval_result in env.evaluation_result_list:
                if eval_result[0] == self.valid_name and eval_result[1] == self.metric:
                    value = eval_result[2]
                    self.trial.report(value, env.iteration)
                    if self.trial.should_prune():
                        raise optuna.TrialPruned()
from optuna.visualization import plot_optimization_history, plot_param_importances
from pathlib import Path
import joblib
import numpy as np
from typing import Dict, Tuple, Optional, Any
import psutil
import gc
import json
from datetime import datetime
import logging
from functools import partial

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"
OPTUNA_DIR = ARTEFACT_DIR / "optuna_studies"
OPTUNA_DIR.mkdir(exist_ok=True, parents=True)

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


def get_lgb_params_search_space(trial: optuna.Trial, objective: str) -> Dict[str, Any]:
    """Define comprehensive hyperparameter search space for LightGBM.
    
    Based on best practices from Optuna documentation and LightGBM tuning guides.
    """
    params = {
        "objective": objective,
        "boosting_type": trial.suggest_categorical("boosting_type", ["gbdt", "dart", "goss"]),
        "num_leaves": trial.suggest_int("num_leaves", 10, 200),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "bagging_freq": trial.suggest_int("bagging_freq", 1, 10),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "lambda_l1": trial.suggest_float("lambda_l1", 1e-8, 10.0, log=True),
        "lambda_l2": trial.suggest_float("lambda_l2", 1e-8, 10.0, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 12),
        "min_gain_to_split": trial.suggest_float("min_gain_to_split", 0.0, 1.0),
        "max_bin": trial.suggest_int("max_bin", 32, 512),
        "verbose": -1,
        "random_state": 42
    }
    
    # Add boosting type specific parameters
    if params["boosting_type"] == "dart":
        params["drop_rate"] = trial.suggest_float("drop_rate", 0.0, 0.2)
        params["max_drop"] = trial.suggest_int("max_drop", 3, 50)
        params["skip_drop"] = trial.suggest_float("skip_drop", 0.0, 1.0)
    
    # Note: GOSS doesn't support bagging
    if params["boosting_type"] == "goss":
        params["bagging_fraction"] = 1.0
        params["bagging_freq"] = 0
    
    return params


def load_and_prepare_data(target: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load feature matrices and prepare data for a specific target."""
    # Load data
    train_df = pd.read_parquet(ARTEFACT_DIR / "train_matrix.parquet")
    val_df = pd.read_parquet(ARTEFACT_DIR / "val_matrix.parquet")
    
    # Prepare data for target
    def prepare_for_target(df: pd.DataFrame, target: str) -> Tuple[pd.DataFrame, pd.Series]:
        target_col = f"target_{target}"
        mask = ~df[target_col].isna()
        df_filtered = df[mask].copy()
        
        # Initialize Woodwork
        df_filtered.ww.init()
        
        # Get feature columns
        feature_cols = [c for c in df_filtered.columns if not c.startswith("target_")]
        
        X = df_filtered[feature_cols]
        y = df_filtered[target_col]
        
        return X, y
    
    X_train, y_train = prepare_for_target(train_df, target)
    X_val, y_val = prepare_for_target(val_df, target)
    
    # Clean up
    del train_df, val_df
    gc.collect()
    
    return X_train, y_train, X_val, y_val


def create_objective(target: str, config: Dict[str, str], X_train: pd.DataFrame, 
                    y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series,
                    use_cv: bool = False, n_folds: int = 5) -> callable:
    """Create objective function for Optuna optimization.
    
    Args:
        target: Target variable name
        config: Model configuration
        X_train, y_train: Training data
        X_val, y_val: Validation data
        use_cv: Whether to use cross-validation
        n_folds: Number of CV folds
    """
    def objective(trial: optuna.Trial) -> float:
        # Get hyperparameters
        params = get_lgb_params_search_space(trial, config["objective"])
        params["metric"] = config["metric"]
        
        # Get categorical features
        cat_features = X_train.ww.select(include=["categorical", "boolean"]).columns.tolist()
        
        if use_cv:
            # Cross-validation approach
            lgb_train = lgb.Dataset(X_train, label=y_train, categorical_feature=cat_features)
            
            # Add pruning callback for CV
            pruning_callback = optuna.integration.LightGBMPruningCallback(trial, config["metric"])
            
            cv_results = lgb.cv(
                params,
                lgb_train,
                num_boost_round=1000,
                nfold=n_folds,
                stratified=True if config["objective"] == "binary" else False,
                shuffle=True,
                seed=42,
                callbacks=[lgb.early_stopping(50), pruning_callback],
                return_cvstd=True
            )
            
            # Get the best score (last value before early stopping)
            best_score = cv_results[f"{config['metric']}-mean"][-1]
            
        else:
            # Train-validation split approach
            lgb_train = lgb.Dataset(X_train, label=y_train, categorical_feature=cat_features)
            lgb_val = lgb.Dataset(X_val, label=y_val, reference=lgb_train, categorical_feature=cat_features)
            
            # Add pruning callback
            pruning_callback = LightGBMPruningCallback(trial, config["metric"], valid_name="valid_0")
            
            model = lgb.train(
                params,
                lgb_train,
                valid_sets=[lgb_val],
                valid_names=["valid_0"],
                num_boost_round=1000,
                callbacks=[lgb.early_stopping(50), pruning_callback]
            )
            
            best_score = model.best_score["valid_0"][config["metric"]]
        
        # For metrics where lower is better (mae, rmse), return as is
        # For metrics where higher is better (auc), return negative
        if config["metric"] in ["mae", "rmse", "mse"]:
            return best_score
        else:  # auc, etc.
            return -best_score
    
    return objective


def optimize_hyperparameters(target: str, config: Dict[str, str], 
                           n_trials: int = 100, 
                           timeout: Optional[int] = None,
                           n_jobs: int = 1,
                           use_cv: bool = False) -> Tuple[optuna.Study, Dict[str, Any]]:
    """Optimize hyperparameters using Optuna.
    
    Args:
        target: Target variable name
        config: Model configuration
        n_trials: Number of optimization trials
        timeout: Timeout in seconds
        n_jobs: Number of parallel jobs
        use_cv: Whether to use cross-validation
    
    Returns:
        study: Optuna study object
        best_params: Best hyperparameters found
    """
    logger.info(f"Starting hyperparameter optimization for {target}")
    
    # Load data
    X_train, y_train, X_val, y_val = load_and_prepare_data(target)
    logger.info(f"Loaded data - Train: {X_train.shape}, Val: {X_val.shape}")
    
    # Create study
    study_name = f"{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    storage = f"sqlite:///{OPTUNA_DIR}/optuna_{target}.db"
    
    # Determine optimization direction
    direction = "minimize" if config["metric"] in ["mae", "rmse", "mse"] else "maximize"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction=direction,
        load_if_exists=False,
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=50)
    )
    
    # Create objective function
    objective = create_objective(target, config, X_train, y_train, X_val, y_val, use_cv)
    
    # Optimize
    logger.info(f"Running {n_trials} trials with {n_jobs} parallel jobs")
    study.optimize(
        objective, 
        n_trials=n_trials,
        timeout=timeout,
        n_jobs=n_jobs,
        show_progress_bar=True
    )
    
    # Log results
    logger.info(f"Best trial: {study.best_trial.number}")
    logger.info(f"Best value: {study.best_value}")
    logger.info(f"Best params: {study.best_params}")
    
    # Save study results
    results = {
        "target": target,
        "best_params": study.best_params,
        "best_value": study.best_value,
        "best_trial": study.best_trial.number,
        "n_trials": len(study.trials),
        "study_name": study_name,
        "timestamp": datetime.now().isoformat()
    }
    
    results_path = OPTUNA_DIR / f"optimization_results_{target}.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    
    # Generate visualizations
    try:
        # Optimization history
        fig = plot_optimization_history(study)
        fig.write_html(OPTUNA_DIR / f"optimization_history_{target}.html")
        
        # Parameter importances
        fig = plot_param_importances(study)
        fig.write_html(OPTUNA_DIR / f"param_importances_{target}.html")
    except Exception as e:
        logger.warning(f"Failed to generate visualizations: {e}")
    
    # Clean up
    del X_train, y_train, X_val, y_val
    gc.collect()
    
    return study, study.best_params


def train_final_model(target: str, config: Dict[str, str], 
                     best_params: Dict[str, Any]) -> lgb.Booster:
    """Train final model with best hyperparameters.
    
    Args:
        target: Target variable name
        config: Model configuration
        best_params: Best hyperparameters from Optuna
        
    Returns:
        Trained LightGBM model
    """
    logger.info(f"Training final model for {target} with optimized parameters")
    
    # Load all data (train + val for final model)
    train_df = pd.read_parquet(ARTEFACT_DIR / "train_matrix.parquet")
    val_df = pd.read_parquet(ARTEFACT_DIR / "val_matrix.parquet")
    test_df = pd.read_parquet(ARTEFACT_DIR / "test_matrix.parquet")
    
    # Combine train and val for final training
    combined_df = pd.concat([train_df, val_df], axis=0, ignore_index=True)
    
    # Prepare data
    def prepare_for_target(df: pd.DataFrame, target: str) -> Tuple[pd.DataFrame, pd.Series]:
        target_col = f"target_{target}"
        mask = ~df[target_col].isna()
        df_filtered = df[mask].copy()
        df_filtered.ww.init()
        feature_cols = [c for c in df_filtered.columns if not c.startswith("target_")]
        X = df_filtered[feature_cols]
        y = df_filtered[target_col]
        return X, y
    
    X_train_final, y_train_final = prepare_for_target(combined_df, target)
    X_test, y_test = prepare_for_target(test_df, target)
    
    # Get categorical features
    cat_features = X_train_final.ww.select(include=["categorical", "boolean"]).columns.tolist()
    
    # Create datasets
    lgb_train = lgb.Dataset(X_train_final, label=y_train_final, categorical_feature=cat_features)
    lgb_test = lgb.Dataset(X_test, label=y_test, reference=lgb_train, categorical_feature=cat_features)
    
    # Set up parameters
    params = best_params.copy()
    params["objective"] = config["objective"]
    params["metric"] = config["metric"]
    params["verbose"] = -1
    params["random_state"] = 42
    
    # Train final model
    model = lgb.train(
        params,
        lgb_train,
        valid_sets=[lgb_test],
        num_boost_round=2000,
        callbacks=[lgb.early_stopping(100), lgb.log_evaluation(200)]
    )
    
    # Evaluate on test set
    test_pred = model.predict(X_test, num_iteration=model.best_iteration)
    
    if config["objective"] == "regression":
        if config["metric"] == "mae":
            test_score = np.mean(np.abs(test_pred - y_test))
        elif config["metric"] == "rmse":
            test_score = np.sqrt(np.mean((test_pred - y_test) ** 2))
    else:
        from sklearn.metrics import roc_auc_score
        test_score = roc_auc_score(y_test, test_pred)
    
    logger.info(f"Test {config['metric']}: {test_score:.4f}")
    
    # Save model
    model_dir = ARTEFACT_DIR / "models"
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / f"lgb_{target}_optuna_v1.txt"
    model.save_model(str(model_path))
    logger.info(f"Saved model to {model_path}")
    
    # Save training metadata
    metadata = {
        "target": target,
        "test_score": float(test_score),
        "metric": config["metric"],
        "best_iteration": model.best_iteration,
        "feature_names": model.feature_name(),
        "categorical_features": cat_features,
        "hyperparameters": best_params,
        "training_samples": len(X_train_final),
        "test_samples": len(X_test),
        "timestamp": datetime.now().isoformat()
    }
    
    metadata_path = model_dir / f"lgb_{target}_optuna_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    # Clean up
    del train_df, val_df, test_df, combined_df
    del X_train_final, y_train_final, X_test, y_test
    gc.collect()
    
    return model


def run_ensemble_optimization(targets: Optional[list] = None,
                            n_trials: int = 100,
                            timeout_per_target: Optional[int] = 3600,
                            n_jobs: int = 1,
                            use_cv: bool = False):
    """Run hyperparameter optimization for ensemble models.
    
    Args:
        targets: List of targets to optimize (None for all)
        n_trials: Number of trials per target
        timeout_per_target: Timeout in seconds per target
        n_jobs: Number of parallel jobs for optimization
        use_cv: Whether to use cross-validation
    """
    if targets is None:
        targets = list(MODEL_CONFIGS.keys())
    
    logger.info(f"Starting ensemble optimization for {len(targets)} targets")
    logger.info(f"Settings: n_trials={n_trials}, timeout={timeout_per_target}s, n_jobs={n_jobs}, use_cv={use_cv}")
    
    results = {}
    
    for target in targets:
        if target not in MODEL_CONFIGS:
            logger.warning(f"Skipping unknown target: {target}")
            continue
            
        logger.info(f"\n{'='*60}")
        logger.info(f"Optimizing: {target}")
        logger.info(f"Description: {MODEL_CONFIGS[target]['description']}")
        logger.info(f"{'='*60}")
        
        try:
            # Run optimization
            study, best_params = optimize_hyperparameters(
                target=target,
                config=MODEL_CONFIGS[target],
                n_trials=n_trials,
                timeout=timeout_per_target,
                n_jobs=n_jobs,
                use_cv=use_cv
            )
            
            # Train final model with best params
            model = train_final_model(target, MODEL_CONFIGS[target], best_params)
            
            results[target] = {
                "status": "success",
                "best_params": best_params,
                "best_value": study.best_value,
                "n_trials": len(study.trials)
            }
            
        except Exception as e:
            logger.error(f"Failed to optimize {target}: {e}")
            results[target] = {
                "status": "failed",
                "error": str(e)
            }
    
    # Save overall results
    overall_results = {
        "targets": results,
        "settings": {
            "n_trials": n_trials,
            "timeout_per_target": timeout_per_target,
            "n_jobs": n_jobs,
            "use_cv": use_cv
        },
        "timestamp": datetime.now().isoformat()
    }
    
    results_path = OPTUNA_DIR / "ensemble_optimization_results.json"
    with open(results_path, "w") as f:
        json.dump(overall_results, f, indent=2)
    
    logger.info(f"\nOptimization complete. Results saved to {results_path}")
    
    # Print summary
    logger.info("\nOptimization Summary:")
    for target, result in results.items():
        if result["status"] == "success":
            logger.info(f"  {target}: ✓ (best value: {result['best_value']:.4f}, trials: {result['n_trials']})")
        else:
            logger.info(f"  {target}: ✗ ({result['error']})")


def main():
    """Main entry point for Optuna optimization."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Optimize LightGBM models with Optuna")
    parser.add_argument("--targets", nargs="+", help="Specific targets to optimize")
    parser.add_argument("--n-trials", type=int, default=100, help="Number of trials per target")
    parser.add_argument("--timeout", type=int, help="Timeout in seconds per target")
    parser.add_argument("--n-jobs", type=int, default=1, help="Number of parallel jobs")
    parser.add_argument("--use-cv", action="store_true", help="Use cross-validation")
    
    args = parser.parse_args()
    
    run_ensemble_optimization(
        targets=args.targets,
        n_trials=args.n_trials,
        timeout_per_target=args.timeout,
        n_jobs=args.n_jobs,
        use_cv=args.use_cv
    )


if __name__ == "__main__":
    main()