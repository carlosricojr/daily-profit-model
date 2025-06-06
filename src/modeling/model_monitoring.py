"""
Model monitoring utilities for tracking performance, drift, and health metrics.
Provides different levels of monitoring capabilities for production ML systems.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime, date
from dataclasses import dataclass
import json
from scipy import stats
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


@dataclass
class ModelMetrics:
    """Container for model performance metrics."""
    mae: float
    rmse: float
    r2: float
    direction_accuracy: float
    percentile_errors: Dict[int, float]
    prediction_count: int
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'mae': self.mae,
            'rmse': self.rmse,
            'r2': self.r2,
            'direction_accuracy': self.direction_accuracy,
            'percentile_errors': self.percentile_errors,
            'prediction_count': self.prediction_count,
            'timestamp': self.timestamp.isoformat()
        }


class BaseMonitor:
    """Base class for model monitoring."""
    
    def __init__(self, db_manager, model_version: str):
        self.db_manager = db_manager
        self.model_version = model_version
        self.metrics_history = []
        
    def calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> ModelMetrics:
        """Calculate comprehensive model metrics."""
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2 = r2_score(y_true, y_pred)
        
        # Direction accuracy
        direction_correct = ((y_true > 0) == (y_pred > 0)).mean()
        
        # Percentile errors
        abs_errors = np.abs(y_true - y_pred)
        percentiles = {
            50: np.percentile(abs_errors, 50),
            75: np.percentile(abs_errors, 75),
            90: np.percentile(abs_errors, 90),
            95: np.percentile(abs_errors, 95),
            99: np.percentile(abs_errors, 99)
        }
        
        return ModelMetrics(
            mae=mae,
            rmse=rmse,
            r2=r2,
            direction_accuracy=direction_correct,
            percentile_errors=percentiles,
            prediction_count=len(y_true),
            timestamp=datetime.now()
        )
    
    def log_metrics(self, metrics: ModelMetrics, prediction_date: date):
        """Log metrics to database."""
        query = """
        INSERT INTO model_performance_metrics 
        (model_version, prediction_date, mae, rmse, r2, direction_accuracy,
         percentile_errors, prediction_count, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        self.db_manager.model_db.execute_command(
            query,
            (
                self.model_version,
                prediction_date,
                metrics.mae,
                metrics.rmse,
                metrics.r2,
                metrics.direction_accuracy,
                json.dumps(metrics.percentile_errors),
                metrics.prediction_count,
                metrics.timestamp
            )
        )


class ConservativeMonitor(BaseMonitor):
    """Version 1: Basic monitoring with performance tracking."""
    
    def __init__(self, db_manager, model_version: str):
        super().__init__(db_manager, model_version)
        self.performance_threshold = 1.2  # Alert if performance degrades by 20%
        
    def monitor_predictions(self, predictions_df: pd.DataFrame, actuals_df: Optional[pd.DataFrame] = None):
        """Monitor prediction quality and log basic metrics."""
        # Log prediction distribution
        logger.info(f"Prediction statistics for {self.model_version}:")
        logger.info(f"  Mean: ${predictions_df['predicted_net_profit'].mean():.2f}")
        logger.info(f"  Std: ${predictions_df['predicted_net_profit'].std():.2f}")
        logger.info(f"  Min: ${predictions_df['predicted_net_profit'].min():.2f}")
        logger.info(f"  Max: ${predictions_df['predicted_net_profit'].max():.2f}")
        
        # Check for anomalies in predictions
        self._check_prediction_anomalies(predictions_df)
        
        # If actuals are available, calculate performance
        if actuals_df is not None:
            metrics = self.calculate_metrics(
                actuals_df['actual_net_profit'].values,
                predictions_df['predicted_net_profit'].values
            )
            self.metrics_history.append(metrics)
            
            # Check performance degradation
            if self._check_performance_degradation(metrics):
                logger.warning(f"Performance degradation detected for model {self.model_version}")
                self._send_alert("performance_degradation", metrics)
    
    def _check_prediction_anomalies(self, predictions_df: pd.DataFrame):
        """Check for anomalous predictions."""
        predictions = predictions_df['predicted_net_profit'].values
        
        # Check for extreme values (beyond 3 std)
        mean_pred = np.mean(predictions)
        std_pred = np.std(predictions)
        extreme_predictions = np.abs(predictions - mean_pred) > 3 * std_pred
        
        if extreme_predictions.any():
            logger.warning(f"Found {extreme_predictions.sum()} extreme predictions")
            
        # Check for NaN or infinite values
        if np.isnan(predictions).any() or np.isinf(predictions).any():
            logger.error("Found NaN or infinite predictions!")
            self._send_alert("invalid_predictions", {"count": np.isnan(predictions).sum()})
    
    def _check_performance_degradation(self, current_metrics: ModelMetrics) -> bool:
        """Check if model performance has degraded."""
        if len(self.metrics_history) < 5:
            return False
            
        # Compare with historical average
        historical_mae = np.mean([m.mae for m in self.metrics_history[-10:-1]])
        
        return current_metrics.mae > historical_mae * self.performance_threshold
    
    def _send_alert(self, alert_type: str, details: Any):
        """Send alert (placeholder for actual alerting system)."""
        logger.warning(f"ALERT [{alert_type}]: {details}")
        # In production, this would send to monitoring system (e.g., PagerDuty, Slack)


class BalancedMonitor(ConservativeMonitor):
    """Version 2: Comprehensive monitoring with drift detection."""
    
    def __init__(self, db_manager, model_version: str):
        super().__init__(db_manager, model_version)
        self.feature_statistics = {}
        self.drift_threshold = 0.1  # KS statistic threshold
        
    def monitor_feature_drift(self, current_features: pd.DataFrame, reference_features: pd.DataFrame) -> Dict[str, float]:
        """Monitor feature drift using Kolmogorov-Smirnov test."""
        drift_scores = {}
        
        for column in current_features.columns:
            if column in reference_features.columns:
                # Skip categorical features
                if current_features[column].dtype in ['object', 'category']:
                    continue
                
                # Calculate KS statistic
                ks_stat, p_value = stats.ks_2samp(
                    reference_features[column].dropna(),
                    current_features[column].dropna()
                )
                
                drift_scores[column] = {
                    'ks_statistic': ks_stat,
                    'p_value': p_value,
                    'is_drifted': ks_stat > self.drift_threshold
                }
                
                if ks_stat > self.drift_threshold:
                    logger.warning(f"Feature drift detected in {column}: KS={ks_stat:.3f}")
        
        return drift_scores
    
    def monitor_prediction_drift(self, current_predictions: np.ndarray, reference_predictions: np.ndarray) -> Dict[str, float]:
        """Monitor prediction distribution drift."""
        # KS test for prediction distribution
        ks_stat, p_value = stats.ks_2samp(reference_predictions, current_predictions)
        
        # Wasserstein distance
        wasserstein_dist = stats.wasserstein_distance(reference_predictions, current_predictions)
        
        # Population Stability Index (PSI)
        psi = self._calculate_psi(reference_predictions, current_predictions)
        
        drift_metrics = {
            'ks_statistic': ks_stat,
            'p_value': p_value,
            'wasserstein_distance': wasserstein_dist,
            'psi': psi,
            'is_drifted': ks_stat > self.drift_threshold or psi > 0.1
        }
        
        if drift_metrics['is_drifted']:
            logger.warning(f"Prediction drift detected: KS={ks_stat:.3f}, PSI={psi:.3f}")
            self._send_alert("prediction_drift", drift_metrics)
        
        return drift_metrics
    
    def _calculate_psi(self, expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
        """Calculate Population Stability Index."""
        def _psi_bucket(e_perc: float, a_perc: float) -> float:
            if a_perc == 0:
                a_perc = 0.0001
            if e_perc == 0:
                e_perc = 0.0001
            return (e_perc - a_perc) * np.log(e_perc / a_perc)
        
        # Create bins based on expected distribution
        breakpoints = np.linspace(expected.min(), expected.max(), buckets + 1)
        
        # Calculate frequencies
        expected_counts = np.histogram(expected, breakpoints)[0]
        actual_counts = np.histogram(actual, breakpoints)[0]
        
        # Convert to percentages
        expected_percents = expected_counts / len(expected)
        actual_percents = actual_counts / len(actual)
        
        # Calculate PSI
        psi = sum(_psi_bucket(e, a) for e, a in zip(expected_percents, actual_percents))
        
        return psi
    
    def create_monitoring_dashboard_data(self) -> Dict[str, Any]:
        """Create data for monitoring dashboard."""
        # Get recent metrics
        query = """
        SELECT * FROM model_performance_metrics
        WHERE model_version = %s
        ORDER BY created_at DESC
        LIMIT 30
        """
        
        recent_metrics = self.db_manager.model_db.execute_query_df(query, (self.model_version,))
        
        if recent_metrics.empty:
            return {}
        
        dashboard_data = {
            'model_version': self.model_version,
            'last_update': datetime.now().isoformat(),
            'performance_trends': {
                'mae': recent_metrics['mae'].tolist(),
                'rmse': recent_metrics['rmse'].tolist(),
                'direction_accuracy': recent_metrics['direction_accuracy'].tolist(),
                'dates': recent_metrics['prediction_date'].astype(str).tolist()
            },
            'current_metrics': {
                'mae': recent_metrics.iloc[0]['mae'],
                'rmse': recent_metrics.iloc[0]['rmse'],
                'r2': recent_metrics.iloc[0]['r2'],
                'direction_accuracy': recent_metrics.iloc[0]['direction_accuracy']
            },
            'alerts': self._get_recent_alerts()
        }
        
        return dashboard_data
    
    def _get_recent_alerts(self) -> List[Dict[str, Any]]:
        """Get recent alerts from monitoring system."""
        # Placeholder - in production this would query alert system
        return []


class AggressiveMonitor(BalancedMonitor):
    """Version 3: Full MLOps monitoring with advanced analytics."""
    
    def __init__(self, db_manager, model_version: str):
        super().__init__(db_manager, model_version)
        self.experiment_tracker = ExperimentTracker(db_manager)
        self.performance_analyzer = PerformanceAnalyzer()
        
    def monitor_model_health(self, comprehensive: bool = True) -> Dict[str, Any]:
        """Comprehensive model health monitoring."""
        health_report = {
            'model_version': self.model_version,
            'timestamp': datetime.now().isoformat(),
            'health_score': 100.0,
            'components': {}
        }
        
        # Performance health
        perf_health = self._check_performance_health()
        health_report['components']['performance'] = perf_health
        health_report['health_score'] *= perf_health['score']
        
        # Data quality health
        data_health = self._check_data_quality_health()
        health_report['components']['data_quality'] = data_health
        health_report['health_score'] *= data_health['score']
        
        # Prediction distribution health
        pred_health = self._check_prediction_health()
        health_report['components']['predictions'] = pred_health
        health_report['health_score'] *= pred_health['score']
        
        # System health (latency, throughput)
        if comprehensive:
            system_health = self._check_system_health()
            health_report['components']['system'] = system_health
            health_report['health_score'] *= system_health['score']
        
        # Overall status
        if health_report['health_score'] < 70:
            health_report['status'] = 'critical'
        elif health_report['health_score'] < 85:
            health_report['status'] = 'warning'
        else:
            health_report['status'] = 'healthy'
        
        return health_report
    
    def _check_performance_health(self) -> Dict[str, Any]:
        """Check model performance health."""
        # Get recent performance metrics
        query = """
        SELECT mae, rmse, direction_accuracy, created_at
        FROM model_performance_metrics
        WHERE model_version = %s
        ORDER BY created_at DESC
        LIMIT 30
        """
        
        metrics_df = self.db_manager.model_db.execute_query_df(query, (self.model_version,))
        
        if metrics_df.empty:
            return {'score': 1.0, 'status': 'no_data'}
        
        # Check for performance degradation trend
        mae_trend = np.polyfit(range(len(metrics_df)), metrics_df['mae'].values, 1)[0]
        
        health_score = 1.0
        issues = []
        
        if mae_trend > 0:  # MAE increasing
            health_score *= 0.8
            issues.append('performance_degradation_trend')
        
        # Check variance
        mae_cv = metrics_df['mae'].std() / metrics_df['mae'].mean()
        if mae_cv > 0.2:  # High variance
            health_score *= 0.9
            issues.append('high_performance_variance')
        
        return {
            'score': health_score,
            'mae_trend': mae_trend,
            'mae_cv': mae_cv,
            'issues': issues
        }
    
    def _check_data_quality_health(self) -> Dict[str, Any]:
        """Check data quality health."""
        # This would check for missing data, outliers, etc.
        # Placeholder implementation
        return {'score': 0.95, 'issues': []}
    
    def _check_prediction_health(self) -> Dict[str, Any]:
        """Check prediction distribution health."""
        # Get recent predictions
        query = """
        SELECT predicted_net_profit
        FROM model_predictions
        WHERE model_version = %s
        AND prediction_date >= CURRENT_DATE - INTERVAL '7 days'
        """
        
        predictions_df = self.db_manager.model_db.execute_query_df(query, (self.model_version,))
        
        if predictions_df.empty:
            return {'score': 1.0, 'status': 'no_data'}
        
        predictions = predictions_df['predicted_net_profit'].values
        health_score = 1.0
        issues = []
        
        # Check for extreme predictions
        extreme_ratio = (np.abs(predictions) > np.percentile(np.abs(predictions), 99)).mean()
        if extreme_ratio > 0.02:  # More than 2% extreme
            health_score *= 0.9
            issues.append('excessive_extreme_predictions')
        
        # Check for prediction collapse (all similar values)
        pred_std = np.std(predictions)
        if pred_std < 10:  # Too low variance
            health_score *= 0.7
            issues.append('prediction_collapse')
        
        return {
            'score': health_score,
            'prediction_std': pred_std,
            'extreme_ratio': extreme_ratio,
            'issues': issues
        }
    
    def _check_system_health(self) -> Dict[str, Any]:
        """Check system performance health."""
        # This would check latency, throughput, resource usage
        # Placeholder implementation
        return {'score': 0.98, 'latency_p95': 250, 'throughput': 1000}
    
    def trigger_automated_retraining(self, reason: str) -> bool:
        """Trigger automated model retraining."""
        logger.info(f"Triggering automated retraining. Reason: {reason}")
        
        # Check if retraining is needed
        if not self._should_retrain():
            logger.info("Retraining criteria not met")
            return False
        
        # Log retraining trigger
        query = """
        INSERT INTO model_retraining_triggers
        (model_version, trigger_reason, trigger_time, status)
        VALUES (%s, %s, %s, %s)
        """
        
        self.db_manager.model_db.execute_command(
            query,
            (self.model_version, reason, datetime.now(), 'triggered')
        )
        
        # In production, this would trigger a retraining job
        # For now, just return True
        return True
    
    def _should_retrain(self) -> bool:
        """Determine if model should be retrained."""
        # Check various criteria
        health_report = self.monitor_model_health()
        
        # Retrain if health score is low
        if health_report['health_score'] < 75:
            return True
        
        # Check time since last training
        query = """
        SELECT created_at FROM model_registry
        WHERE model_version = %s
        """
        
        result = self.db_manager.model_db.execute_query(query, (self.model_version,))
        if result:
            days_since_training = (datetime.now() - result[0]['created_at']).days
            if days_since_training > 30:  # Retrain monthly
                return True
        
        return False


class ExperimentTracker:
    """Track A/B testing experiments for models."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def create_experiment(self, name: str, control_model: str, treatment_model: str,
                         traffic_split: float = 0.5) -> str:
        """Create a new A/B test experiment."""
        experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        query = """
        INSERT INTO model_experiments
        (experiment_id, experiment_name, control_model, treatment_model,
         traffic_split, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        self.db_manager.model_db.execute_command(
            query,
            (experiment_id, name, control_model, treatment_model,
             traffic_split, 'active', datetime.now())
        )
        
        logger.info(f"Created experiment {experiment_id}: {control_model} vs {treatment_model}")
        return experiment_id
    
    def assign_to_variant(self, account_id: str, experiment_id: str) -> str:
        """Assign account to control or treatment group."""
        # Get experiment details
        query = """
        SELECT traffic_split FROM model_experiments
        WHERE experiment_id = %s AND status = 'active'
        """
        
        result = self.db_manager.model_db.execute_query(query, (experiment_id,))
        if not result:
            return 'control'  # Default to control if experiment not found
        
        traffic_split = result[0]['traffic_split']
        
        # Deterministic assignment based on account_id hash
        import hashlib
        hash_value = int(hashlib.md5(f"{account_id}_{experiment_id}".encode()).hexdigest()[:8], 16)
        assignment = 'treatment' if (hash_value % 100) < (traffic_split * 100) else 'control'
        
        # Log assignment
        query = """
        INSERT INTO experiment_assignments
        (experiment_id, account_id, variant, assigned_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (experiment_id, account_id) DO NOTHING
        """
        
        self.db_manager.model_db.execute_command(
            query,
            (experiment_id, account_id, assignment, datetime.now())
        )
        
        return assignment
    
    def analyze_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """Analyze A/B test results."""
        # Get experiment data
        query = """
        SELECT 
            ea.variant,
            COUNT(DISTINCT mp.login) as accounts,
            AVG(ABS(mp.prediction_error)) as mae,
            STDDEV(ABS(mp.prediction_error)) as mae_std,
            AVG(CASE WHEN (mp.predicted_net_profit > 0) = (mp.actual_net_profit > 0) 
                THEN 1.0 ELSE 0.0 END) as direction_accuracy
        FROM experiment_assignments ea
        JOIN model_predictions mp ON ea.account_id = mp.login
        WHERE ea.experiment_id = %s
        AND mp.actual_net_profit IS NOT NULL
        GROUP BY ea.variant
        """
        
        results = self.db_manager.model_db.execute_query(query, (experiment_id,))
        
        if len(results) < 2:
            return {'status': 'insufficient_data'}
        
        # Statistical significance test
        control = next(r for r in results if r['variant'] == 'control')
        treatment = next(r for r in results if r['variant'] == 'treatment')
        
        # T-test for MAE difference
        t_stat = (control['mae'] - treatment['mae']) / np.sqrt(
            control['mae_std']**2 / control['accounts'] + 
            treatment['mae_std']**2 / treatment['accounts']
        )
        
        p_value = 2 * (1 - stats.norm.cdf(abs(t_stat)))
        
        return {
            'control': control,
            'treatment': treatment,
            'mae_improvement': (control['mae'] - treatment['mae']) / control['mae'],
            'direction_accuracy_improvement': treatment['direction_accuracy'] - control['direction_accuracy'],
            't_statistic': t_stat,
            'p_value': p_value,
            'is_significant': p_value < 0.05
        }


class PerformanceAnalyzer:
    """Analyze model performance patterns."""
    
    def analyze_performance_by_segment(self, predictions_df: pd.DataFrame, 
                                     actuals_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze performance across different segments."""
        merged_df = predictions_df.merge(actuals_df, on=['login', 'prediction_date'])
        merged_df['error'] = merged_df['predicted_net_profit'] - merged_df['actual_net_profit']
        merged_df['abs_error'] = np.abs(merged_df['error'])
        
        segments = {}
        
        # By prediction magnitude
        merged_df['pred_magnitude'] = pd.cut(
            merged_df['predicted_net_profit'],
            bins=[-np.inf, -100, 0, 100, np.inf],
            labels=['large_loss', 'small_loss', 'small_profit', 'large_profit']
        )
        
        for segment in merged_df['pred_magnitude'].unique():
            segment_data = merged_df[merged_df['pred_magnitude'] == segment]
            segments[f'magnitude_{segment}'] = {
                'count': len(segment_data),
                'mae': segment_data['abs_error'].mean(),
                'bias': segment_data['error'].mean(),
                'direction_accuracy': ((segment_data['predicted_net_profit'] > 0) == 
                                     (segment_data['actual_net_profit'] > 0)).mean()
            }
        
        # By day of week
        merged_df['day_of_week'] = pd.to_datetime(merged_df['prediction_date']).dt.dayofweek
        for day in range(7):
            day_data = merged_df[merged_df['day_of_week'] == day]
            if len(day_data) > 0:
                segments[f'day_{day}'] = {
                    'count': len(day_data),
                    'mae': day_data['abs_error'].mean(),
                    'bias': day_data['error'].mean()
                }
        
        return segments
    
    def identify_failure_patterns(self, predictions_df: pd.DataFrame, 
                                actuals_df: pd.DataFrame,
                                threshold_multiplier: float = 2.0) -> List[Dict[str, Any]]:
        """Identify patterns in prediction failures."""
        merged_df = predictions_df.merge(actuals_df, on=['login', 'prediction_date'])
        merged_df['abs_error'] = np.abs(merged_df['predicted_net_profit'] - merged_df['actual_net_profit'])
        
        # Define failure as error > threshold * MAE
        mae = merged_df['abs_error'].mean()
        merged_df['is_failure'] = merged_df['abs_error'] > threshold_multiplier * mae
        
        failures = []
        
        # Check for account-specific failures
        account_failures = merged_df.groupby('login')['is_failure'].agg(['sum', 'count'])
        account_failures['failure_rate'] = account_failures['sum'] / account_failures['count']
        
        high_failure_accounts = account_failures[account_failures['failure_rate'] > 0.3]
        if len(high_failure_accounts) > 0:
            failures.append({
                'pattern': 'high_failure_accounts',
                'count': len(high_failure_accounts),
                'accounts': high_failure_accounts.index.tolist()[:10]  # Top 10
            })
        
        # Check for temporal patterns
        merged_df['date'] = pd.to_datetime(merged_df['prediction_date'])
        daily_failures = merged_df.groupby('date')['is_failure'].mean()
        
        # Detect failure spikes
        failure_threshold = daily_failures.mean() + 2 * daily_failures.std()
        failure_spikes = daily_failures[daily_failures > failure_threshold]
        
        if len(failure_spikes) > 0:
            failures.append({
                'pattern': 'temporal_failure_spikes',
                'dates': failure_spikes.index.strftime('%Y-%m-%d').tolist(),
                'failure_rates': failure_spikes.values.tolist()
            })
        
        return failures


# Create database tables for monitoring (add to schema.sql)
MONITORING_TABLES_SQL = """
-- Model performance metrics table
CREATE TABLE IF NOT EXISTS model_performance_metrics (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(50) NOT NULL,
    prediction_date DATE NOT NULL,
    mae DECIMAL(18, 4),
    rmse DECIMAL(18, 4),
    r2 DECIMAL(5, 4),
    direction_accuracy DECIMAL(5, 4),
    percentile_errors JSONB,
    prediction_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(model_version, prediction_date)
);

-- Model experiments table
CREATE TABLE IF NOT EXISTS model_experiments (
    experiment_id VARCHAR(50) PRIMARY KEY,
    experiment_name VARCHAR(255),
    control_model VARCHAR(50),
    treatment_model VARCHAR(50),
    traffic_split DECIMAL(3, 2),
    status VARCHAR(20),
    created_at TIMESTAMP,
    ended_at TIMESTAMP
);

-- Experiment assignments table
CREATE TABLE IF NOT EXISTS experiment_assignments (
    experiment_id VARCHAR(50),
    account_id VARCHAR(255),
    variant VARCHAR(20),
    assigned_at TIMESTAMP,
    PRIMARY KEY (experiment_id, account_id)
);

-- Model retraining triggers table
CREATE TABLE IF NOT EXISTS model_retraining_triggers (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(50),
    trigger_reason TEXT,
    trigger_time TIMESTAMP,
    status VARCHAR(20),
    completed_at TIMESTAMP
);

CREATE INDEX idx_performance_metrics_model ON model_performance_metrics(model_version);
CREATE INDEX idx_performance_metrics_date ON model_performance_metrics(prediction_date);
CREATE INDEX idx_experiments_status ON model_experiments(status);
CREATE INDEX idx_assignments_experiment ON experiment_assignments(experiment_id);
"""