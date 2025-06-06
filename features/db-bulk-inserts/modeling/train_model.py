"""
Version 1: Enhanced Model Training with Basic Monitoring and Versioning
Implements comprehensive logging, prediction confidence intervals, and model monitoring.
"""

import os
import sys
import logging
import json
import joblib
import warnings
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import argparse

import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
import optuna
from optuna.samplers import TPESampler
import shap

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.database import get_db_manager
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

warnings.filterwarnings('ignore', category=UserWarning)


class ModelMonitor:
    """Handles model performance monitoring and alerting."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        
    def log_training_metrics(self, model_version: str, metrics: Dict[str, Any]):
        """Log training metrics with enhanced monitoring."""
        query = """
        INSERT INTO model_training_metrics (
            model_version, train_mae, train_rmse, train_r2,
            val_mae, val_rmse, val_r2, test_mae, test_rmse, test_r2,
            training_duration_seconds, baseline_mae, improvement_over_baseline,
            created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = (
            model_version,
            metrics.get('train_mae', 0),
            metrics.get('train_rmse', 0),
            metrics.get('train_r2', 0),
            metrics.get('val_mae', 0),
            metrics.get('val_rmse', 0),
            metrics.get('val_r2', 0),
            metrics.get('test_mae', 0),
            metrics.get('test_rmse', 0),
            metrics.get('test_r2', 0),
            metrics.get('training_duration', 0),
            metrics.get('baseline_mae', 0),
            metrics.get('improvement_over_baseline', 0),
            datetime.now()
        )
        
        # Create table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS model_training_metrics (
            id SERIAL PRIMARY KEY,
            model_version VARCHAR(50) NOT NULL,
            train_mae DECIMAL(18, 4),
            train_rmse DECIMAL(18, 4),
            train_r2 DECIMAL(5, 4),
            val_mae DECIMAL(18, 4),
            val_rmse DECIMAL(18, 4),
            val_r2 DECIMAL(5, 4),
            test_mae DECIMAL(18, 4),
            test_rmse DECIMAL(18, 4),
            test_r2 DECIMAL(5, 4),
            training_duration_seconds INTEGER,
            baseline_mae DECIMAL(18, 4),
            improvement_over_baseline DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        try:
            self.db_manager.model_db.execute_command(create_table_query)
            self.db_manager.model_db.execute_command(query, params)
            logger.info(f"Training metrics logged for model {model_version}")
        except Exception as e:
            logger.warning(f"Failed to log training metrics: {e}")
    
    def check_model_degradation(self, model_version: str, current_metrics: Dict[str, float]) -> Dict[str, Any]:
        """Check for model performance degradation."""
        # Get historical metrics for comparison
        query = """
        SELECT test_mae, test_r2, created_at
        FROM model_training_metrics
        WHERE model_version != %s
        ORDER BY created_at DESC
        LIMIT 5
        """
        
        try:
            historical_results = self.db_manager.model_db.execute_query(query, (model_version,))
            
            if not historical_results:
                return {"status": "no_comparison", "message": "No historical models for comparison"}
            
            # Calculate average historical performance
            historical_mae = np.mean([r['test_mae'] for r in historical_results])
            historical_r2 = np.mean([r['test_r2'] for r in historical_results])
            
            current_mae = current_metrics.get('test_mae', float('inf'))
            current_r2 = current_metrics.get('test_r2', 0)
            
            # Check for degradation (>10% worse MAE or >5% worse R2)
            mae_degradation = (current_mae - historical_mae) / historical_mae if historical_mae > 0 else 0
            r2_degradation = (historical_r2 - current_r2) / abs(historical_r2) if historical_r2 != 0 else 0
            
            alerts = []
            if mae_degradation > 0.1:
                alerts.append(f"MAE degraded by {mae_degradation:.1%}")
            if r2_degradation > 0.05:
                alerts.append(f"R2 degraded by {r2_degradation:.1%}")
            
            status = "degraded" if alerts else "acceptable"
            
            return {
                "status": status,
                "current_mae": current_mae,
                "historical_mae": historical_mae,
                "current_r2": current_r2,
                "historical_r2": historical_r2,
                "alerts": alerts
            }
            
        except Exception as e:
            logger.warning(f"Failed to check model degradation: {e}")
            return {"status": "error", "message": str(e)}


class PredictionIntervals:
    """Calculate prediction confidence intervals using quantile regression."""
    
    def __init__(self):
        self.lower_model = None
        self.upper_model = None
        
    def fit(self, X_train: pd.DataFrame, y_train: pd.Series,
           X_val: pd.DataFrame, y_val: pd.Series,
           params: Dict[str, Any], alpha: float = 0.1):
        """
        Fit quantile regression models for prediction intervals.
        
        Args:
            alpha: Significance level (0.1 for 90% confidence intervals)
        """
        # Lower quantile (alpha/2)
        lower_params = params.copy()
        lower_params['objective'] = 'quantile'
        lower_params['alpha'] = alpha / 2
        
        self.lower_model = lgb.LGBMRegressor(**lower_params)
        self.lower_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)]
        )
        
        # Upper quantile (1 - alpha/2)
        upper_params = params.copy()
        upper_params['objective'] = 'quantile'
        upper_params['alpha'] = 1 - alpha / 2
        
        self.upper_model = lgb.LGBMRegressor(**upper_params)
        self.upper_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)]
        )
        
    def predict_intervals(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Predict confidence intervals."""
        if self.lower_model is None or self.upper_model is None:
            raise ValueError("Models not fitted. Call fit() first.")
            
        lower_pred = self.lower_model.predict(X)
        upper_pred = self.upper_model.predict(X)
        
        return lower_pred, upper_pred


class EnhancedModelTrainer:
    """Enhanced Model Trainer with monitoring, versioning, and confidence intervals."""
    
    def __init__(self, model_version: Optional[str] = None):
        """Initialize the enhanced model trainer."""
        self.db_manager = get_db_manager()
        self.model_version = model_version or f"v1_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Model artifacts directory
        self.artifacts_dir = Path("model_artifacts") / self.model_version
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.monitor = ModelMonitor(self.db_manager)
        self.prediction_intervals = PredictionIntervals()
        
        # Feature configuration
        self.exclude_columns = [
            'id', 'login', 'prediction_date', 'feature_date', 
            'target_net_profit', 'created_at'
        ]
        self.categorical_features = [
            'market_volatility_regime', 'market_liquidity_state'
        ]
        
        # Model components
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.best_params = None
        
    def train_model(self,
                   train_ratio: float = 0.7,
                   val_ratio: float = 0.15,
                   tune_hyperparameters: bool = True,
                   n_trials: int = 50,
                   enable_prediction_intervals: bool = True) -> Dict[str, Any]:
        """Train model with enhanced monitoring and confidence intervals."""
        start_time = datetime.now()
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='train_model_v1',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            logger.info(f"Starting enhanced model training - Version: {self.model_version}")
            
            # Load and prepare data
            X, y, dates = self._load_training_data()
            splits = self._split_data(X, y, dates, train_ratio, val_ratio)
            
            # Evaluate baseline
            baseline_metrics = self._evaluate_baseline(
                splits['y_train'], splits['y_val'], splits['y_test']
            )
            
            # Scale features
            X_train_scaled, X_val_scaled, X_test_scaled = self._scale_features(
                splits['X_train'], splits['X_val'], splits['X_test']
            )
            
            # Hyperparameter tuning
            if tune_hyperparameters:
                logger.info("Starting hyperparameter optimization...")
                self.best_params = self._tune_hyperparameters(
                    X_train_scaled, splits['y_train'], X_val_scaled, splits['y_val'], n_trials
                )
            else:
                self.best_params = self._get_default_params()
            
            # Train main model
            logger.info("Training primary model...")
            self.model = self._train_lightgbm(
                X_train_scaled, splits['y_train'], X_val_scaled, splits['y_val'], self.best_params
            )
            
            # Train prediction intervals
            if enable_prediction_intervals:
                logger.info("Training prediction interval models...")
                self.prediction_intervals.fit(
                    X_train_scaled, splits['y_train'], X_val_scaled, splits['y_val'], self.best_params
                )
            
            # Evaluate model
            metrics = self._evaluate_model(
                X_train_scaled, splits['y_train'],
                X_val_scaled, splits['y_val'],
                X_test_scaled, splits['y_test']
            )
            
            # Enhanced evaluation with intervals
            if enable_prediction_intervals:
                interval_metrics = self._evaluate_prediction_intervals(
                    X_test_scaled, splits['y_test']
                )
                metrics.update(interval_metrics)
            
            # Calculate feature importance and SHAP
            feature_importance = self._calculate_feature_importance()
            shap_values = self._calculate_shap_values(X_test_scaled[:500])
            
            # Training duration
            training_duration = (datetime.now() - start_time).total_seconds()
            metrics['training_duration'] = training_duration
            metrics['baseline_mae'] = baseline_metrics['test_mae']
            metrics['improvement_over_baseline'] = (
                (baseline_metrics['test_mae'] - metrics['test_mae']) / baseline_metrics['test_mae'] * 100
            )
            
            # Save artifacts
            self._save_enhanced_artifacts(metrics, feature_importance, shap_values)
            
            # Register model
            self._register_enhanced_model(splits['dates_train'], splits['dates_val'], 
                                        splits['dates_test'], metrics, feature_importance)
            
            # Log metrics to monitoring
            self.monitor.log_training_metrics(self.model_version, metrics)
            
            # Check for performance degradation
            degradation_check = self.monitor.check_model_degradation(self.model_version, metrics)
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='train_model_v1',
                execution_date=datetime.now().date(),
                status='success',
                execution_details={
                    'model_version': self.model_version,
                    'duration_seconds': training_duration,
                    'test_mae': metrics['test_mae'],
                    'improvement_over_baseline': metrics['improvement_over_baseline'],
                    'degradation_status': degradation_check['status']
                }
            )
            
            # Prepare results
            results = {
                'model_version': self.model_version,
                'metrics': metrics,
                'baseline_metrics': baseline_metrics,
                'feature_importance': feature_importance,
                'best_params': self.best_params,
                'degradation_check': degradation_check,
                'training_duration': training_duration,
                'data_splits': {
                    'train': {'start': splits['dates_train'].min(), 'end': splits['dates_train'].max(), 'samples': len(splits['X_train'])},
                    'val': {'start': splits['dates_val'].min(), 'end': splits['dates_val'].max(), 'samples': len(splits['X_val'])},
                    'test': {'start': splits['dates_test'].min(), 'end': splits['dates_test'].max(), 'samples': len(splits['X_test'])}
                }
            }
            
            logger.info(f"Enhanced model training completed - Version: {self.model_version}")
            return results
            
        except Exception as e:
            self.db_manager.log_pipeline_execution(
                pipeline_stage='train_model_v1',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e)
            )
            logger.error(f"Enhanced model training failed: {str(e)}")
            raise
    
    def _load_training_data(self) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """Load training data with enhanced validation."""
        query = """
        SELECT *
        FROM model_training_input
        WHERE target_net_profit IS NOT NULL
        ORDER BY prediction_date
        """
        
        df = self.db_manager.model_db.execute_query_df(query)
        
        if df.empty:
            raise ValueError("No training data found")
        
        # Data quality checks
        logger.info(f"Loaded {len(df)} training samples")
        logger.info(f"Missing target values: {df['target_net_profit'].isna().sum()}")
        logger.info(f"Date range: {df['prediction_date'].min()} to {df['prediction_date'].max()}")
        
        # Remove rows with missing targets
        df = df.dropna(subset=['target_net_profit'])
        
        dates = pd.to_datetime(df['prediction_date'])
        y = df['target_net_profit']
        
        self.feature_columns = [col for col in df.columns if col not in self.exclude_columns]
        X = df[self.feature_columns].copy()
        
        # Handle categorical features
        for cat_col in self.categorical_features:
            if cat_col in X.columns:
                X[cat_col] = X[cat_col].astype('category')
        
        # Feature validation
        missing_features = X.isnull().sum()
        if missing_features.any():
            logger.warning(f"Features with missing values: {missing_features[missing_features > 0].to_dict()}")
        
        return X, y, dates
    
    def _split_data(self, X: pd.DataFrame, y: pd.Series, dates: pd.Series,
                   train_ratio: float, val_ratio: float) -> Dict[str, Any]:
        """Split data with time-series awareness."""
        n_samples = len(X)
        train_size = int(n_samples * train_ratio)
        val_size = int(n_samples * val_ratio)
        
        return {
            'X_train': X.iloc[:train_size],
            'y_train': y.iloc[:train_size],
            'dates_train': dates.iloc[:train_size],
            'X_val': X.iloc[train_size:train_size + val_size],
            'y_val': y.iloc[train_size:train_size + val_size],
            'dates_val': dates.iloc[train_size:train_size + val_size],
            'X_test': X.iloc[train_size + val_size:],
            'y_test': y.iloc[train_size + val_size:],
            'dates_test': dates.iloc[train_size + val_size:]
        }
    
    def _evaluate_baseline(self, y_train: pd.Series, y_val: pd.Series, 
                         y_test: pd.Series) -> Dict[str, float]:
        """Evaluate baseline model."""
        train_mean = y_train.mean()
        
        return {
            'val_mae': mean_absolute_error(y_val, np.full(len(y_val), train_mean)),
            'test_mae': mean_absolute_error(y_test, np.full(len(y_test), train_mean))
        }
    
    def _scale_features(self, X_train: pd.DataFrame, X_val: pd.DataFrame,
                       X_test: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Scale numerical features."""
        numerical_cols = [col for col in X_train.columns 
                         if col not in self.categorical_features]
        
        self.scaler = StandardScaler()
        
        X_train_scaled = X_train.copy()
        X_val_scaled = X_val.copy()
        X_test_scaled = X_test.copy()
        
        X_train_scaled[numerical_cols] = self.scaler.fit_transform(X_train[numerical_cols])
        X_val_scaled[numerical_cols] = self.scaler.transform(X_val[numerical_cols])
        X_test_scaled[numerical_cols] = self.scaler.transform(X_test[numerical_cols])
        
        return X_train_scaled, X_val_scaled, X_test_scaled
    
    def _get_default_params(self) -> Dict[str, Any]:
        """Get optimized default parameters."""
        return {
            'objective': 'regression_l1',
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
        """Enhanced hyperparameter tuning with monitoring."""
        
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
            
            # Train model
            model = lgb.LGBMRegressor(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
                categorical_feature=self.categorical_features
            )
            
            # Evaluate
            y_pred = model.predict(X_val)
            mae = mean_absolute_error(y_val, y_pred)
            
            return mae
        
        # Create study with enhanced sampling
        study = optuna.create_study(
            direction='minimize', 
            sampler=TPESampler(seed=42, n_startup_trials=10)
        )
        study.optimize(objective, n_trials=n_trials)
        
        logger.info(f"Hyperparameter optimization completed: Best MAE = {study.best_value:.4f}")
        
        return study.best_params
    
    def _train_lightgbm(self, X_train: pd.DataFrame, y_train: pd.Series,
                       X_val: pd.DataFrame, y_val: pd.Series,
                       params: Dict[str, Any]) -> lgb.LGBMRegressor:
        """Train LightGBM model with enhanced monitoring."""
        model = lgb.LGBMRegressor(**params)
        
        # Enhanced callbacks
        callbacks = [
            lgb.early_stopping(50),
            lgb.log_evaluation(50)
        ]
        
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=callbacks,
            categorical_feature=self.categorical_features
        )
        
        return model
    
    def _evaluate_model(self, X_train: pd.DataFrame, y_train: pd.Series,
                       X_val: pd.DataFrame, y_val: pd.Series,
                       X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, float]:
        """Enhanced model evaluation with additional metrics."""
        metrics = {}
        
        for name, X, y in [('train', X_train, y_train), 
                          ('val', X_val, y_val), 
                          ('test', X_test, y_test)]:
            y_pred = self.model.predict(X)
            
            # Standard metrics
            metrics[f'{name}_mae'] = mean_absolute_error(y, y_pred)
            metrics[f'{name}_rmse'] = np.sqrt(mean_squared_error(y, y_pred))
            metrics[f'{name}_r2'] = r2_score(y, y_pred)
            
            # Additional metrics
            abs_errors = np.abs(y - y_pred)
            metrics[f'{name}_mae_p50'] = np.percentile(abs_errors, 50)
            metrics[f'{name}_mae_p90'] = np.percentile(abs_errors, 90)
            metrics[f'{name}_mae_p95'] = np.percentile(abs_errors, 95)
            
            # Directional accuracy
            direction_correct = ((y > 0) == (y_pred > 0)).mean()
            metrics[f'{name}_direction_accuracy'] = direction_correct
            
            # Mean absolute percentage error
            with np.errstate(divide='ignore', invalid='ignore'):
                mape = np.mean(np.abs((y - y_pred) / y)) * 100
                mape = np.nan_to_num(mape, nan=0, posinf=0, neginf=0)
            metrics[f'{name}_mape'] = mape
        
        return metrics
    
    def _evaluate_prediction_intervals(self, X_test: pd.DataFrame, 
                                     y_test: pd.Series) -> Dict[str, float]:
        """Evaluate prediction interval quality."""
        try:
            lower_pred, upper_pred = self.prediction_intervals.predict_intervals(X_test)
            
            # Coverage (what percentage of actual values fall within intervals)
            coverage = ((y_test >= lower_pred) & (y_test <= upper_pred)).mean()
            
            # Average interval width
            avg_width = np.mean(upper_pred - lower_pred)
            
            # Interval score (lower is better)
            alpha = 0.1  # 90% confidence intervals
            interval_score = np.mean(
                (upper_pred - lower_pred) + 
                (2 / alpha) * (lower_pred - y_test) * (y_test < lower_pred) +
                (2 / alpha) * (y_test - upper_pred) * (y_test > upper_pred)
            )
            
            return {
                'interval_coverage': coverage,
                'interval_avg_width': avg_width,
                'interval_score': interval_score
            }
        except Exception as e:
            logger.warning(f"Failed to evaluate prediction intervals: {e}")
            return {}
    
    def _calculate_feature_importance(self) -> Dict[str, float]:
        """Calculate enhanced feature importance."""
        importance = self.model.feature_importances_
        feature_importance = dict(zip(self.feature_columns, importance))
        
        # Normalize to percentages
        total_importance = sum(feature_importance.values())
        if total_importance > 0:
            feature_importance = {
                k: (v / total_importance * 100) 
                for k, v in feature_importance.items()
            }
        
        # Sort by importance
        feature_importance = dict(sorted(
            feature_importance.items(), 
            key=lambda x: x[1], 
            reverse=True
        ))
        
        # Log top features
        logger.info("Top 15 most important features:")
        for i, (feature, score) in enumerate(list(feature_importance.items())[:15]):
            logger.info(f"  {i+1:2d}. {feature}: {score:.2f}%")
        
        return feature_importance
    
    def _calculate_shap_values(self, X_sample: pd.DataFrame) -> np.ndarray:
        """Calculate SHAP values for interpretability."""
        try:
            explainer = shap.TreeExplainer(self.model)
            shap_values = explainer.shap_values(X_sample)
            
            # Create and save summary plot
            import matplotlib.pyplot as plt
            plt.figure(figsize=(10, 8))
            shap.summary_plot(
                shap_values, X_sample, 
                feature_names=self.feature_columns,
                show=False
            )
            plt.savefig(self.artifacts_dir / 'shap_summary.png', dpi=150, bbox_inches='tight')
            plt.close()
            
            return shap_values
        except Exception as e:
            logger.warning(f"Failed to calculate SHAP values: {e}")
            return np.array([])
    
    def _save_enhanced_artifacts(self, metrics: Dict[str, float], 
                               feature_importance: Dict[str, float],
                               shap_values: np.ndarray):
        """Save enhanced model artifacts."""
        # Save model and scaler
        joblib.dump(self.model, self.artifacts_dir / 'model.pkl')
        joblib.dump(self.scaler, self.artifacts_dir / 'scaler.pkl')
        
        # Save prediction intervals
        if self.prediction_intervals.lower_model is not None:
            joblib.dump(self.prediction_intervals, self.artifacts_dir / 'prediction_intervals.pkl')
        
        # Save enhanced metadata
        with open(self.artifacts_dir / 'feature_columns.json', 'w') as f:
            json.dump(self.feature_columns, f, indent=2)
        
        with open(self.artifacts_dir / 'hyperparameters.json', 'w') as f:
            json.dump(self.best_params, f, indent=2)
        
        with open(self.artifacts_dir / 'metrics.json', 'w') as f:
            # Convert numpy types to native Python types for JSON serialization
            serializable_metrics = {}
            for k, v in metrics.items():
                if isinstance(v, (np.int64, np.int32)):
                    serializable_metrics[k] = int(v)
                elif isinstance(v, (np.float64, np.float32)):
                    serializable_metrics[k] = float(v)
                else:
                    serializable_metrics[k] = v
            json.dump(serializable_metrics, f, indent=2)
        
        with open(self.artifacts_dir / 'feature_importance.json', 'w') as f:
            json.dump(feature_importance, f, indent=2)
        
        # Save model summary
        model_summary = {
            'model_version': self.model_version,
            'created_at': datetime.now().isoformat(),
            'model_type': 'LightGBM',
            'feature_count': len(self.feature_columns),
            'training_samples': metrics.get('train_samples', 0),
            'key_metrics': {
                'test_mae': metrics.get('test_mae'),
                'test_r2': metrics.get('test_r2'),
                'direction_accuracy': metrics.get('test_direction_accuracy'),
                'improvement_over_baseline': metrics.get('improvement_over_baseline')
            }
        }
        
        with open(self.artifacts_dir / 'model_summary.json', 'w') as f:
            json.dump(model_summary, f, indent=2)
        
        logger.info(f"Enhanced artifacts saved to {self.artifacts_dir}")
    
    def _register_enhanced_model(self, dates_train: pd.Series, dates_val: pd.Series,
                               dates_test: pd.Series, metrics: Dict[str, float],
                               feature_importance: Dict[str, float]):
        """Register model with enhanced metadata."""
        # Create enhanced registry table if needed
        create_table_query = """
        CREATE TABLE IF NOT EXISTS model_registry_enhanced (
            id SERIAL PRIMARY KEY,
            model_version VARCHAR(50) NOT NULL UNIQUE,
            model_type VARCHAR(50) DEFAULT 'LightGBM',
            training_start_date DATE,
            training_end_date DATE,
            validation_start_date DATE,
            validation_end_date DATE,
            test_start_date DATE,
            test_end_date DATE,
            
            -- Enhanced metrics
            train_mae DECIMAL(18, 4),
            train_rmse DECIMAL(18, 4),
            train_r2 DECIMAL(5, 4),
            train_direction_accuracy DECIMAL(5, 4),
            val_mae DECIMAL(18, 4),
            val_rmse DECIMAL(18, 4),
            val_r2 DECIMAL(5, 4),
            val_direction_accuracy DECIMAL(5, 4),
            test_mae DECIMAL(18, 4),
            test_rmse DECIMAL(18, 4),
            test_r2 DECIMAL(5, 4),
            test_direction_accuracy DECIMAL(5, 4),
            
            -- Prediction intervals
            interval_coverage DECIMAL(5, 4),
            interval_avg_width DECIMAL(18, 4),
            
            -- Model metadata
            hyperparameters JSONB,
            feature_list JSONB,
            feature_importance JSONB,
            
            -- File paths
            model_file_path VARCHAR(500),
            scaler_file_path VARCHAR(500),
            intervals_file_path VARCHAR(500),
            
            -- Status
            is_active BOOLEAN DEFAULT FALSE,
            training_duration_seconds INTEGER,
            improvement_over_baseline DECIMAL(10, 4),
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        try:
            self.db_manager.model_db.execute_command(create_table_query)
            
            # Insert model record
            query = """
            INSERT INTO model_registry_enhanced (
                model_version, model_type,
                training_start_date, training_end_date,
                validation_start_date, validation_end_date,
                test_start_date, test_end_date,
                train_mae, train_rmse, train_r2, train_direction_accuracy,
                val_mae, val_rmse, val_r2, val_direction_accuracy,
                test_mae, test_rmse, test_r2, test_direction_accuracy,
                interval_coverage, interval_avg_width,
                hyperparameters, feature_list, feature_importance,
                model_file_path, scaler_file_path, intervals_file_path,
                training_duration_seconds, improvement_over_baseline,
                is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                metrics.get('train_mae'),
                metrics.get('train_rmse'),
                metrics.get('train_r2'),
                metrics.get('train_direction_accuracy'),
                metrics.get('val_mae'),
                metrics.get('val_rmse'),
                metrics.get('val_r2'),
                metrics.get('val_direction_accuracy'),
                metrics.get('test_mae'),
                metrics.get('test_rmse'),
                metrics.get('test_r2'),
                metrics.get('test_direction_accuracy'),
                metrics.get('interval_coverage'),
                metrics.get('interval_avg_width'),
                json.dumps(self.best_params),
                json.dumps(self.feature_columns),
                json.dumps(feature_importance),
                str(self.artifacts_dir / 'model.pkl'),
                str(self.artifacts_dir / 'scaler.pkl'),
                str(self.artifacts_dir / 'prediction_intervals.pkl'),
                int(metrics.get('training_duration', 0)),
                metrics.get('improvement_over_baseline'),
                False  # Not active by default
            )
            
            self.db_manager.model_db.execute_command(query, params)
            logger.info(f"Enhanced model registered: {self.model_version}")
            
        except Exception as e:
            logger.warning(f"Failed to register enhanced model: {e}")


def main():
    """Main function for Version 1 enhanced training."""
    parser = argparse.ArgumentParser(description='Enhanced Model Training v1')
    parser.add_argument('--model-version', help='Model version identifier')
    parser.add_argument('--train-ratio', type=float, default=0.7)
    parser.add_argument('--val-ratio', type=float, default=0.15)
    parser.add_argument('--tune-hyperparameters', action='store_true')
    parser.add_argument('--n-trials', type=int, default=50)
    parser.add_argument('--disable-intervals', action='store_true',
                       help='Disable prediction intervals training')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level=args.log_level, log_file='train_model_v1')
    
    # Train model
    trainer = EnhancedModelTrainer(model_version=args.model_version)
    
    try:
        results = trainer.train_model(
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            tune_hyperparameters=args.tune_hyperparameters,
            n_trials=args.n_trials,
            enable_prediction_intervals=not args.disable_intervals
        )
        
        # Print comprehensive summary
        logger.info("\n" + "="*60)
        logger.info("ENHANCED MODEL TRAINING SUMMARY (Version 1)")
        logger.info("="*60)
        logger.info(f"Model Version: {results['model_version']}")
        logger.info(f"Training Duration: {results['training_duration']:.1f} seconds")
        logger.info("")
        logger.info("Performance Metrics:")
        logger.info(f"  Test MAE: ${results['metrics']['test_mae']:.2f}")
        logger.info(f"  Test RMSE: ${results['metrics']['test_rmse']:.2f}")
        logger.info(f"  Test R²: {results['metrics']['test_r2']:.4f}")
        logger.info(f"  Direction Accuracy: {results['metrics'].get('test_direction_accuracy', 0):.1%}")
        logger.info(f"  Baseline MAE: ${results['baseline_metrics']['test_mae']:.2f}")
        logger.info(f"  Improvement: {results['metrics']['improvement_over_baseline']:.1f}%")
        
        if 'interval_coverage' in results['metrics']:
            logger.info("")
            logger.info("Prediction Intervals:")
            logger.info(f"  Coverage: {results['metrics']['interval_coverage']:.1%}")
            logger.info(f"  Avg Width: ${results['metrics']['interval_avg_width']:.2f}")
        
        logger.info("")
        logger.info("Model Status:")
        logger.info(f"  Degradation Check: {results['degradation_check']['status']}")
        if results['degradation_check']['status'] == 'degraded':
            logger.warning(f"  Alerts: {', '.join(results['degradation_check']['alerts'])}")
        
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Enhanced model training failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()