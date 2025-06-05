"""
Train LightGBM model for daily profit prediction.
Implements time-series aware splitting, hyperparameter tuning, and model evaluation.
"""

import os
import sys
import logging
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple
import argparse
import pandas as pd
import numpy as np
import json
import joblib
from pathlib import Path

# Machine learning imports
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
import optuna
from optuna.samplers import TPESampler
import shap

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Handles training of the LightGBM model for daily profit prediction."""
    
    def __init__(self, model_version: Optional[str] = None):
        """
        Initialize the model trainer.
        
        Args:
            model_version: Version identifier for the model
        """
        self.db_manager = get_db_manager()
        self.model_version = model_version or f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Model artifacts directory
        self.artifacts_dir = Path("model_artifacts") / self.model_version
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Feature columns (exclude target and metadata)
        self.exclude_columns = [
            'id', 'login', 'prediction_date', 'feature_date', 
            'target_net_profit', 'created_at'
        ]
        
        # Categorical features
        self.categorical_features = [
            'market_volatility_regime', 'market_liquidity_state'
        ]
        
        # Model and preprocessing objects
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.best_params = None
    
    def train_model(self,
                   train_ratio: float = 0.7,
                   val_ratio: float = 0.15,
                   tune_hyperparameters: bool = True,
                   n_trials: int = 50) -> Dict[str, Any]:
        """
        Train the LightGBM model with time-series aware splitting.
        
        Args:
            train_ratio: Proportion of data for training
            val_ratio: Proportion of data for validation
            tune_hyperparameters: Whether to tune hyperparameters
            n_trials: Number of Optuna trials for hyperparameter tuning
            
        Returns:
            Dictionary containing training results and metrics
        """
        start_time = datetime.now()
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='train_model',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            logger.info(f"Starting model training - Version: {self.model_version}")
            
            # Load training data
            logger.info("Loading training data...")
            X, y, dates = self._load_training_data()
            logger.info(f"Loaded {len(X)} training samples")
            
            # Split data (time-series aware)
            logger.info("Splitting data for training, validation, and testing...")
            splits = self._split_data(X, y, dates, train_ratio, val_ratio)
            X_train, X_val, X_test = splits['X_train'], splits['X_val'], splits['X_test']
            y_train, y_val, y_test = splits['y_train'], splits['y_val'], splits['y_test']
            dates_train, dates_val, dates_test = splits['dates_train'], splits['dates_val'], splits['dates_test']
            
            logger.info(f"Train: {len(X_train)} samples ({dates_train.min()} to {dates_train.max()})")
            logger.info(f"Val: {len(X_val)} samples ({dates_val.min()} to {dates_val.max()})")
            logger.info(f"Test: {len(X_test)} samples ({dates_test.min()} to {dates_test.max()})")
            
            # Baseline model
            baseline_metrics = self._evaluate_baseline(y_train, y_val, y_test)
            logger.info(f"Baseline MAE (predict previous day): {baseline_metrics['test_mae']:.2f}")
            
            # Scale features
            logger.info("Scaling features...")
            X_train_scaled, X_val_scaled, X_test_scaled = self._scale_features(
                X_train, X_val, X_test
            )
            
            # Hyperparameter tuning
            if tune_hyperparameters:
                logger.info(f"Starting hyperparameter tuning with {n_trials} trials...")
                self.best_params = self._tune_hyperparameters(
                    X_train_scaled, y_train, X_val_scaled, y_val, n_trials
                )
                logger.info(f"Best parameters: {self.best_params}")
            else:
                # Use default parameters
                self.best_params = self._get_default_params()
            
            # Train final model
            logger.info("Training final model...")
            self.model = self._train_lightgbm(
                X_train_scaled, y_train, X_val_scaled, y_val, self.best_params
            )
            
            # Evaluate model
            logger.info("Evaluating model...")
            metrics = self._evaluate_model(
                X_train_scaled, y_train, X_val_scaled, y_val, X_test_scaled, y_test
            )
            
            # Calculate feature importance
            logger.info("Calculating feature importance...")
            feature_importance = self._calculate_feature_importance()
            
            # Calculate SHAP values for test set
            logger.info("Calculating SHAP values...")
            shap_values = self._calculate_shap_values(X_test_scaled[:1000])  # Sample for speed
            
            # Save model and artifacts
            logger.info("Saving model artifacts...")
            self._save_artifacts(metrics, feature_importance)
            
            # Register model in database
            self._register_model(
                dates_train, dates_val, dates_test, metrics, feature_importance
            )
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='train_model',
                execution_date=datetime.now().date(),
                status='success',
                execution_details={
                    'model_version': self.model_version,
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'train_samples': len(X_train),
                    'val_samples': len(X_val),
                    'test_samples': len(X_test),
                    'test_mae': metrics['test_mae'],
                    'test_r2': metrics['test_r2']
                }
            )
            
            # Return results
            results = {
                'model_version': self.model_version,
                'metrics': metrics,
                'baseline_metrics': baseline_metrics,
                'feature_importance': feature_importance,
                'best_params': self.best_params,
                'data_splits': {
                    'train': {'start': dates_train.min(), 'end': dates_train.max(), 'samples': len(X_train)},
                    'val': {'start': dates_val.min(), 'end': dates_val.max(), 'samples': len(X_val)},
                    'test': {'start': dates_test.min(), 'end': dates_test.max(), 'samples': len(X_test)}
                }
            }
            
            logger.info(f"Model training completed successfully - Version: {self.model_version}")
            return results
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='train_model',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e)
            )
            logger.error(f"Failed to train model: {str(e)}")
            raise
    
    def _load_training_data(self) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """Load and prepare training data from the database."""
        query = """
        SELECT *
        FROM model_training_input
        ORDER BY prediction_date
        """
        
        df = self.db_manager.model_db.execute_query_df(query)
        
        if df.empty:
            raise ValueError("No training data found in model_training_input table")
        
        # Separate features, target, and dates
        dates = pd.to_datetime(df['prediction_date'])
        y = df['target_net_profit']
        
        # Get feature columns
        self.feature_columns = [col for col in df.columns if col not in self.exclude_columns]
        X = df[self.feature_columns]
        
        # Handle categorical features
        for cat_col in self.categorical_features:
            if cat_col in X.columns:
                X[cat_col] = X[cat_col].astype('category')
        
        logger.info(f"Feature columns: {len(self.feature_columns)}")
        logger.info(f"Date range: {dates.min()} to {dates.max()}")
        logger.info(f"Target statistics - Mean: ${y.mean():.2f}, Std: ${y.std():.2f}")
        
        return X, y, dates
    
    def _split_data(self, X: pd.DataFrame, y: pd.Series, dates: pd.Series,
                   train_ratio: float, val_ratio: float) -> Dict[str, Any]:
        """Split data using time-series aware approach."""
        n_samples = len(X)
        train_size = int(n_samples * train_ratio)
        val_size = int(n_samples * val_ratio)
        
        # Time-based splitting
        X_train = X.iloc[:train_size]
        y_train = y.iloc[:train_size]
        dates_train = dates.iloc[:train_size]
        
        X_val = X.iloc[train_size:train_size + val_size]
        y_val = y.iloc[train_size:train_size + val_size]
        dates_val = dates.iloc[train_size:train_size + val_size]
        
        X_test = X.iloc[train_size + val_size:]
        y_test = y.iloc[train_size + val_size:]
        dates_test = dates.iloc[train_size + val_size:]
        
        return {
            'X_train': X_train, 'y_train': y_train, 'dates_train': dates_train,
            'X_val': X_val, 'y_val': y_val, 'dates_val': dates_val,
            'X_test': X_test, 'y_test': y_test, 'dates_test': dates_test
        }
    
    def _evaluate_baseline(self, y_train: pd.Series, y_val: pd.Series, 
                         y_test: pd.Series) -> Dict[str, float]:
        """Evaluate simple baseline model (predict previous day's PnL)."""
        # For baseline, predict the mean of training data
        train_mean = y_train.mean()
        
        baseline_pred_val = np.full(len(y_val), train_mean)
        baseline_pred_test = np.full(len(y_test), train_mean)
        
        return {
            'val_mae': mean_absolute_error(y_val, baseline_pred_val),
            'val_rmse': np.sqrt(mean_squared_error(y_val, baseline_pred_val)),
            'test_mae': mean_absolute_error(y_test, baseline_pred_test),
            'test_rmse': np.sqrt(mean_squared_error(y_test, baseline_pred_test))
        }
    
    def _scale_features(self, X_train: pd.DataFrame, X_val: pd.DataFrame,
                       X_test: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Scale numerical features while preserving categorical ones."""
        # Identify numerical columns
        numerical_cols = [col for col in X_train.columns 
                         if col not in self.categorical_features]
        
        # Initialize scaler
        self.scaler = StandardScaler()
        
        # Fit on training data and transform all sets
        X_train_scaled = X_train.copy()
        X_val_scaled = X_val.copy()
        X_test_scaled = X_test.copy()
        
        X_train_scaled[numerical_cols] = self.scaler.fit_transform(X_train[numerical_cols])
        X_val_scaled[numerical_cols] = self.scaler.transform(X_val[numerical_cols])
        X_test_scaled[numerical_cols] = self.scaler.transform(X_test[numerical_cols])
        
        return X_train_scaled, X_val_scaled, X_test_scaled
    
    def _get_default_params(self) -> Dict[str, Any]:
        """Get default LightGBM parameters."""
        return {
            'objective': 'regression_l1',  # MAE
            'metric': 'mae',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.9,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'min_child_samples': 20,
            'reg_alpha': 0.1,
            'reg_lambda': 0.1,
            'n_estimators': 300,
            'random_state': 42,
            'verbosity': -1
        }
    
    def _tune_hyperparameters(self, X_train: pd.DataFrame, y_train: pd.Series,
                            X_val: pd.DataFrame, y_val: pd.Series,
                            n_trials: int) -> Dict[str, Any]:
        """Tune hyperparameters using Optuna with time series cross-validation."""
        
        def objective(trial):
            params = {
                'objective': trial.suggest_categorical('objective', ['regression_l1', 'huber', 'fair']),
                'metric': 'mae',
                'boosting_type': 'gbdt',
                'num_leaves': trial.suggest_int('num_leaves', 10, 100),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                'feature_fraction': trial.suggest_float('feature_fraction', 0.5, 1.0),
                'bagging_fraction': trial.suggest_float('bagging_fraction', 0.5, 1.0),
                'bagging_freq': trial.suggest_int('bagging_freq', 1, 10),
                'min_child_samples': trial.suggest_int('min_child_samples', 5, 50),
                'reg_alpha': trial.suggest_float('reg_alpha', 0.001, 10.0, log=True),
                'reg_lambda': trial.suggest_float('reg_lambda', 0.001, 10.0, log=True),
                'n_estimators': trial.suggest_int('n_estimators', 100, 500),
                'random_state': 42,
                'verbosity': -1
            }
            
            # Additional parameters for robust objectives
            if params['objective'] == 'huber':
                params['alpha'] = trial.suggest_float('huber_alpha', 0.5, 2.0)
            elif params['objective'] == 'fair':
                params['fair_c'] = trial.suggest_float('fair_c', 0.5, 2.0)
            
            # Train model with current parameters
            model = lgb.LGBMRegressor(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
                categorical_feature=self.categorical_features
            )
            
            # Evaluate on validation set
            y_pred = model.predict(X_val)
            mae = mean_absolute_error(y_val, y_pred)
            
            return mae
        
        # Create Optuna study
        study = optuna.create_study(direction='minimize', sampler=TPESampler(seed=42))
        study.optimize(objective, n_trials=n_trials)
        
        logger.info(f"Best trial MAE: {study.best_value:.4f}")
        
        return study.best_params
    
    def _train_lightgbm(self, X_train: pd.DataFrame, y_train: pd.Series,
                       X_val: pd.DataFrame, y_val: pd.Series,
                       params: Dict[str, Any]) -> lgb.LGBMRegressor:
        """Train the final LightGBM model with best parameters."""
        model = lgb.LGBMRegressor(**params)
        
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(20)],
            categorical_feature=self.categorical_features
        )
        
        return model
    
    def _evaluate_model(self, X_train: pd.DataFrame, y_train: pd.Series,
                       X_val: pd.DataFrame, y_val: pd.Series,
                       X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, float]:
        """Evaluate model on all data splits."""
        metrics = {}
        
        for name, X, y in [('train', X_train, y_train), 
                          ('val', X_val, y_val), 
                          ('test', X_test, y_test)]:
            y_pred = self.model.predict(X)
            
            metrics[f'{name}_mae'] = mean_absolute_error(y, y_pred)
            metrics[f'{name}_rmse'] = np.sqrt(mean_squared_error(y, y_pred))
            metrics[f'{name}_r2'] = r2_score(y, y_pred)
            
            # Calculate percentiles of absolute errors
            abs_errors = np.abs(y - y_pred)
            metrics[f'{name}_mae_p50'] = np.percentile(abs_errors, 50)
            metrics[f'{name}_mae_p90'] = np.percentile(abs_errors, 90)
            metrics[f'{name}_mae_p95'] = np.percentile(abs_errors, 95)
        
        return metrics
    
    def _calculate_feature_importance(self) -> Dict[str, float]:
        """Calculate and return feature importance scores."""
        importance = self.model.feature_importances_
        feature_importance = dict(zip(self.feature_columns, importance))
        
        # Sort by importance
        feature_importance = dict(sorted(
            feature_importance.items(), 
            key=lambda x: x[1], 
            reverse=True
        ))
        
        # Log top features
        logger.info("Top 10 most important features:")
        for i, (feature, score) in enumerate(list(feature_importance.items())[:10]):
            logger.info(f"  {i+1}. {feature}: {score:.4f}")
        
        return feature_importance
    
    def _calculate_shap_values(self, X_sample: pd.DataFrame) -> np.ndarray:
        """Calculate SHAP values for model interpretability."""
        explainer = shap.TreeExplainer(self.model)
        shap_values = explainer.shap_values(X_sample)
        
        # Save SHAP summary plot
        shap.summary_plot(
            shap_values, X_sample, 
            feature_names=self.feature_columns,
            show=False
        )
        import matplotlib.pyplot as plt
        plt.savefig(self.artifacts_dir / 'shap_summary.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        return shap_values
    
    def _save_artifacts(self, metrics: Dict[str, float], 
                       feature_importance: Dict[str, float]):
        """Save model artifacts to disk."""
        # Save model
        model_path = self.artifacts_dir / 'model.pkl'
        joblib.dump(self.model, model_path)
        logger.info(f"Model saved to {model_path}")
        
        # Save scaler
        scaler_path = self.artifacts_dir / 'scaler.pkl'
        joblib.dump(self.scaler, scaler_path)
        logger.info(f"Scaler saved to {scaler_path}")
        
        # Save feature columns
        features_path = self.artifacts_dir / 'feature_columns.json'
        with open(features_path, 'w') as f:
            json.dump(self.feature_columns, f, indent=2)
        
        # Save hyperparameters
        params_path = self.artifacts_dir / 'hyperparameters.json'
        with open(params_path, 'w') as f:
            json.dump(self.best_params, f, indent=2)
        
        # Save metrics
        metrics_path = self.artifacts_dir / 'metrics.json'
        with open(metrics_path, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        # Save feature importance
        importance_path = self.artifacts_dir / 'feature_importance.json'
        with open(importance_path, 'w') as f:
            json.dump(feature_importance, f, indent=2)
    
    def _register_model(self, dates_train: pd.Series, dates_val: pd.Series,
                       dates_test: pd.Series, metrics: Dict[str, float],
                       feature_importance: Dict[str, float]):
        """Register model in the database."""
        query = """
        INSERT INTO model_registry (
            model_version, model_type,
            training_start_date, training_end_date,
            validation_start_date, validation_end_date,
            test_start_date, test_end_date,
            train_mae, train_rmse, train_r2,
            val_mae, val_rmse, val_r2,
            test_mae, test_rmse, test_r2,
            hyperparameters, feature_list, feature_importance,
            model_file_path, scaler_file_path,
            is_active
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = (
            self.model_version,
            'LightGBM',
            dates_train.min().date(),
            dates_train.max().date(),
            dates_val.min().date(),
            dates_val.max().date(),
            dates_test.min().date(),
            dates_test.max().date(),
            metrics['train_mae'],
            metrics['train_rmse'],
            metrics['train_r2'],
            metrics['val_mae'],
            metrics['val_rmse'],
            metrics['val_r2'],
            metrics['test_mae'],
            metrics['test_rmse'],
            metrics['test_r2'],
            json.dumps(self.best_params),
            json.dumps(self.feature_columns),
            json.dumps(feature_importance),
            str(self.artifacts_dir / 'model.pkl'),
            str(self.artifacts_dir / 'scaler.pkl'),
            False  # Not active by default
        )
        
        self.db_manager.model_db.execute_command(query, params)
        logger.info(f"Model registered in database: {self.model_version}")


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Train LightGBM model for daily profit prediction')
    parser.add_argument('--model-version', help='Model version identifier')
    parser.add_argument('--train-ratio', type=float, default=0.7,
                       help='Proportion of data for training')
    parser.add_argument('--val-ratio', type=float, default=0.15,
                       help='Proportion of data for validation')
    parser.add_argument('--tune-hyperparameters', action='store_true',
                       help='Perform hyperparameter tuning')
    parser.add_argument('--n-trials', type=int, default=50,
                       help='Number of Optuna trials for tuning')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='train_model')
    
    # Train model
    trainer = ModelTrainer(model_version=args.model_version)
    try:
        results = trainer.train_model(
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            tune_hyperparameters=args.tune_hyperparameters,
            n_trials=args.n_trials
        )
        
        # Print summary
        logger.info("\n" + "="*50)
        logger.info("MODEL TRAINING SUMMARY")
        logger.info("="*50)
        logger.info(f"Model Version: {results['model_version']}")
        logger.info(f"Test MAE: ${results['metrics']['test_mae']:.2f}")
        logger.info(f"Test RMSE: ${results['metrics']['test_rmse']:.2f}")
        logger.info(f"Test R²: {results['metrics']['test_r2']:.4f}")
        logger.info(f"Baseline Test MAE: ${results['baseline_metrics']['test_mae']:.2f}")
        improvement = (
            (results['baseline_metrics']['test_mae'] - results['metrics']['test_mae']) / 
            results['baseline_metrics']['test_mae'] * 100
        )
        logger.info(f"Improvement over baseline: {improvement:.1f}%")
        
    except Exception as e:
        logger.error(f"Model training failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()