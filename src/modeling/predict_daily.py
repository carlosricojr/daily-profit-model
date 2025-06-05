"""
Version 2: Advanced Daily Prediction with Shadow Deployment and Drift Detection
Implements shadow deployment, real-time drift detection, and advanced monitoring.
"""

import os
import sys
import logging
import json
import joblib
import warnings
import asyncio
import threading
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple, Union
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.database import get_db_manager
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore', category=UserWarning)


class ShadowDeploymentManager:
    """Manages shadow deployment of models for safe testing."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        
    def create_shadow_deployment(self, shadow_model_version: str,
                                production_model_version: str,
                                deployment_config: Dict[str, Any]) -> str:
        """Create a new shadow deployment."""
        # Create shadow deployments table if needed
        create_table_query = """
        CREATE TABLE IF NOT EXISTS shadow_deployments (
            id SERIAL PRIMARY KEY,
            deployment_id VARCHAR(100) NOT NULL UNIQUE,
            shadow_model_version VARCHAR(50) NOT NULL,
            production_model_version VARCHAR(50) NOT NULL,
            traffic_percentage DECIMAL(5, 2) DEFAULT 100.0,
            start_date DATE NOT NULL,
            end_date DATE,
            status VARCHAR(20) DEFAULT 'active',
            deployment_config JSONB,
            performance_metrics JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        deployment_id = f"shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            self.db_manager.model_db.execute_command(create_table_query)
            
            # Insert deployment record
            insert_query = """
            INSERT INTO shadow_deployments (
                deployment_id, shadow_model_version, production_model_version,
                traffic_percentage, start_date, deployment_config
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            params = (
                deployment_id,
                shadow_model_version,
                production_model_version,
                deployment_config.get('traffic_percentage', 100.0),
                datetime.now().date(),
                json.dumps(deployment_config)
            )
            
            self.db_manager.model_db.execute_command(insert_query, params)
            
            logger.info(f"Created shadow deployment: {deployment_id}")
            logger.info(f"  Shadow model: {shadow_model_version}")
            logger.info(f"  Production model: {production_model_version}")
            logger.info(f"  Traffic percentage: {deployment_config.get('traffic_percentage', 100)}%")
            
            return deployment_id
            
        except Exception as e:
            logger.error(f"Failed to create shadow deployment: {e}")
            raise
    
    def get_active_shadow_deployments(self) -> List[Dict[str, Any]]:
        """Get all active shadow deployments."""
        query = """
        SELECT * FROM shadow_deployments
        WHERE status = 'active'
            AND (end_date IS NULL OR end_date >= CURRENT_DATE)
        ORDER BY created_at DESC
        """
        
        try:
            deployments = self.db_manager.model_db.execute_query(query)
            return deployments
        except Exception as e:
            logger.warning(f"Failed to get active shadow deployments: {e}")
            return []
    
    def update_shadow_performance(self, deployment_id: str,
                                 performance_metrics: Dict[str, Any]):
        """Update shadow deployment performance metrics."""
        update_query = """
        UPDATE shadow_deployments
        SET performance_metrics = %s, updated_at = CURRENT_TIMESTAMP
        WHERE deployment_id = %s
        """
        
        try:
            self.db_manager.model_db.execute_command(update_query, (
                json.dumps(performance_metrics),
                deployment_id
            ))
        except Exception as e:
            logger.warning(f"Failed to update shadow performance: {e}")
    
    def compare_shadow_vs_production(self, deployment_id: str,
                                   evaluation_period_days: int = 7) -> Dict[str, Any]:
        """Compare shadow deployment performance vs production."""
        # Get deployment details
        deployment_query = """
        SELECT * FROM shadow_deployments WHERE deployment_id = %s
        """
        
        deployment = self.db_manager.model_db.execute_query(deployment_query, (deployment_id,))
        if not deployment:
            return {"error": "Deployment not found"}
        
        deployment = deployment[0]
        shadow_model = deployment['shadow_model_version']
        production_model = deployment['production_model_version']
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=evaluation_period_days)
        
        # Get predictions for both models
        comparison_query = """
        SELECT 
            model_version,
            AVG(CASE WHEN actual_net_profit IS NOT NULL 
                THEN ABS(predicted_net_profit - actual_net_profit) END) as avg_mae,
            AVG(CASE WHEN actual_net_profit IS NOT NULL 
                THEN CASE WHEN (actual_net_profit > 0) = (predicted_net_profit > 0) 
                     THEN 1.0 ELSE 0.0 END END) as direction_accuracy,
            AVG(prediction_confidence) as avg_confidence,
            COUNT(*) as total_predictions,
            COUNT(CASE WHEN actual_net_profit IS NOT NULL THEN 1 END) as evaluated_predictions
        FROM model_predictions_enhanced
        WHERE model_version IN (%s, %s)
            AND prediction_date BETWEEN %s AND %s
        GROUP BY model_version
        """
        
        try:
            comparison_results = self.db_manager.model_db.execute_query(
                comparison_query, (shadow_model, production_model, start_date, end_date)
            )
            
            # Process results
            metrics_by_model = {result['model_version']: result for result in comparison_results}
            
            shadow_metrics = metrics_by_model.get(shadow_model, {})
            production_metrics = metrics_by_model.get(production_model, {})
            
            comparison = {
                "deployment_id": deployment_id,
                "evaluation_period": f"{start_date} to {end_date}",
                "shadow_model": shadow_model,
                "production_model": production_model,
                "shadow_metrics": shadow_metrics,
                "production_metrics": production_metrics
            }
            
            # Calculate relative performance
            if shadow_metrics and production_metrics:
                if production_metrics.get('avg_mae') and shadow_metrics.get('avg_mae'):
                    mae_improvement = (
                        (production_metrics['avg_mae'] - shadow_metrics['avg_mae']) / 
                        production_metrics['avg_mae'] * 100
                    )
                    comparison["mae_improvement_pct"] = mae_improvement
                
                if production_metrics.get('direction_accuracy') and shadow_metrics.get('direction_accuracy'):
                    accuracy_improvement = (
                        shadow_metrics['direction_accuracy'] - production_metrics['direction_accuracy']
                    ) * 100
                    comparison["accuracy_improvement_pct"] = accuracy_improvement
                
                # Determine recommendation
                mae_better = shadow_metrics.get('avg_mae', float('inf')) < production_metrics.get('avg_mae', float('inf'))
                accuracy_better = shadow_metrics.get('direction_accuracy', 0) > production_metrics.get('direction_accuracy', 0)
                
                if mae_better and accuracy_better:
                    comparison["recommendation"] = "promote_shadow"
                elif mae_better or accuracy_better:
                    comparison["recommendation"] = "continue_testing"
                else:
                    comparison["recommendation"] = "keep_production"
            
            return comparison
            
        except Exception as e:
            logger.error(f"Failed to compare shadow vs production: {e}")
            return {"error": str(e)}
    
    def end_shadow_deployment(self, deployment_id: str, reason: str = "manual"):
        """End a shadow deployment."""
        update_query = """
        UPDATE shadow_deployments
        SET status = 'ended', end_date = CURRENT_DATE, updated_at = CURRENT_TIMESTAMP
        WHERE deployment_id = %s
        """
        
        try:
            self.db_manager.model_db.execute_command(update_query, (deployment_id,))
            logger.info(f"Ended shadow deployment {deployment_id}: {reason}")
        except Exception as e:
            logger.error(f"Failed to end shadow deployment: {e}")


class RealTimeDriftDetector:
    """Real-time drift detection for incoming prediction data."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.reference_distributions = {}
        self.drift_thresholds = {
            'feature_drift': 0.1,
            'prediction_drift': 0.15,
            'performance_drift': 0.2
        }
        
    def load_reference_distributions(self, model_version: str):
        """Load reference distributions for drift detection."""
        # Get reference data from model artifacts
        query = "SELECT model_file_path FROM model_registry_v2 WHERE model_version = %s"
        result = self.db_manager.model_db.execute_query(query, (model_version,))
        
        if not result:
            logger.warning(f"No reference data found for model {model_version}")
            return
        
        model_path = Path(result[0]['model_file_path'])
        reference_data_path = model_path.parent / 'reference_data.pkl'
        
        if reference_data_path.exists():
            try:
                self.reference_distributions[model_version] = joblib.load(reference_data_path)
                logger.info(f"Loaded reference distributions for {model_version}")
            except Exception as e:
                logger.warning(f"Failed to load reference distributions: {e}")
    
    def detect_real_time_drift(self, current_features: pd.DataFrame,
                              current_predictions: np.ndarray,
                              model_version: str) -> Dict[str, Any]:
        """Detect drift in real-time prediction data."""
        drift_results = {
            "model_version": model_version,
            "detection_timestamp": datetime.now().isoformat(),
            "feature_drift": {},
            "prediction_drift": {},
            "overall_drift_detected": False
        }
        
        # Feature drift detection
        if model_version in self.reference_distributions:
            reference_data = self.reference_distributions[model_version]
            
            # Calculate feature drift scores
            feature_drift_scores = {}
            for feature in current_features.columns:
                if feature in reference_data.columns:
                    drift_score = self._calculate_feature_drift(
                        reference_data[feature], current_features[feature]
                    )
                    feature_drift_scores[feature] = drift_score
            
            drift_results["feature_drift"] = {
                "scores": feature_drift_scores,
                "max_drift": max(feature_drift_scores.values()) if feature_drift_scores else 0,
                "drifted_features": [
                    f for f, score in feature_drift_scores.items() 
                    if score > self.drift_thresholds['feature_drift']
                ]
            }
        
        # Prediction drift detection
        prediction_drift = self._detect_prediction_drift(current_predictions, model_version)
        drift_results["prediction_drift"] = prediction_drift
        
        # Overall drift assessment
        feature_drift_detected = len(drift_results["feature_drift"].get("drifted_features", [])) > 0
        prediction_drift_detected = prediction_drift.get("drift_detected", False)
        
        drift_results["overall_drift_detected"] = feature_drift_detected or prediction_drift_detected
        
        # Log drift detection if significant
        if drift_results["overall_drift_detected"]:
            self._log_real_time_drift(drift_results)
        
        return drift_results
    
    def _calculate_feature_drift(self, reference_series: pd.Series, 
                               current_series: pd.Series) -> float:
        """Calculate drift score for a single feature."""
        try:
            from scipy.spatial.distance import jensenshannon
            
            # Remove NaN values
            ref_clean = reference_series.dropna()
            cur_clean = current_series.dropna()
            
            if len(ref_clean) == 0 or len(cur_clean) == 0:
                return 0.0
            
            # Handle categorical vs numerical
            if ref_clean.dtype == 'object' or cur_clean.dtype == 'object':
                # Categorical drift
                ref_counts = ref_clean.value_counts(normalize=True)
                cur_counts = cur_clean.value_counts(normalize=True)
                
                all_categories = set(ref_counts.index) | set(cur_counts.index)
                ref_probs = np.array([ref_counts.get(cat, 0) for cat in all_categories])
                cur_probs = np.array([cur_counts.get(cat, 0) for cat in all_categories])
            else:
                # Numerical drift
                min_val = min(ref_clean.min(), cur_clean.min())
                max_val = max(ref_clean.max(), cur_clean.max())
                
                if min_val == max_val:
                    return 0.0
                
                bins = np.linspace(min_val, max_val, 50)
                ref_hist, _ = np.histogram(ref_clean, bins=bins, density=True)
                cur_hist, _ = np.histogram(cur_clean, bins=bins, density=True)
                
                ref_probs = ref_hist / (ref_hist.sum() + 1e-8)
                cur_probs = cur_hist / (cur_hist.sum() + 1e-8)
            
            # Add epsilon and normalize
            eps = 1e-8
            ref_probs = ref_probs + eps
            cur_probs = cur_probs + eps
            ref_probs = ref_probs / ref_probs.sum()
            cur_probs = cur_probs / cur_probs.sum()
            
            # Calculate Jensen-Shannon divergence
            js_divergence = jensenshannon(ref_probs, cur_probs)
            return float(js_divergence)
            
        except Exception as e:
            logger.warning(f"Failed to calculate feature drift: {e}")
            return 0.0
    
    def _detect_prediction_drift(self, current_predictions: np.ndarray,
                               model_version: str) -> Dict[str, Any]:
        """Detect drift in prediction distribution."""
        # Get historical predictions for comparison
        query = """
        SELECT predicted_net_profit
        FROM model_predictions_enhanced
        WHERE model_version = %s
            AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            AND created_at < CURRENT_DATE - INTERVAL '1 day'
        LIMIT 10000
        """
        
        try:
            historical_df = self.db_manager.model_db.execute_query_df(query, (model_version,))
            
            if len(historical_df) < 100:
                return {"drift_detected": False, "message": "Insufficient historical data"}
            
            historical_predictions = historical_df['predicted_net_profit'].values
            
            # Compare distributions
            hist_mean = np.mean(historical_predictions)
            hist_std = np.std(historical_predictions)
            curr_mean = np.mean(current_predictions)
            curr_std = np.std(current_predictions)
            
            # Calculate drift metrics
            mean_shift = abs(curr_mean - hist_mean) / (hist_std + 1e-8)
            std_ratio = curr_std / (hist_std + 1e-8)
            
            # Detect significant drift
            drift_detected = (
                mean_shift > self.drift_thresholds['prediction_drift'] or
                std_ratio > 2.0 or std_ratio < 0.5
            )
            
            return {
                "drift_detected": drift_detected,
                "mean_shift": mean_shift,
                "std_ratio": std_ratio,
                "historical_mean": hist_mean,
                "current_mean": curr_mean,
                "historical_std": hist_std,
                "current_std": curr_std
            }
            
        except Exception as e:
            logger.warning(f"Failed to detect prediction drift: {e}")
            return {"drift_detected": False, "error": str(e)}
    
    def _log_real_time_drift(self, drift_results: Dict[str, Any]):
        """Log real-time drift detection results."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS real_time_drift_detections (
            id SERIAL PRIMARY KEY,
            model_version VARCHAR(50) NOT NULL,
            detection_timestamp TIMESTAMP NOT NULL,
            feature_drift_count INTEGER,
            max_feature_drift DECIMAL(10, 6),
            prediction_drift_detected BOOLEAN,
            prediction_mean_shift DECIMAL(10, 6),
            drift_details JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        insert_query = """
        INSERT INTO real_time_drift_detections (
            model_version, detection_timestamp, feature_drift_count,
            max_feature_drift, prediction_drift_detected, prediction_mean_shift, drift_details
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            self.db_manager.model_db.execute_command(create_table_query)
            
            params = (
                drift_results['model_version'],
                datetime.now(),
                len(drift_results['feature_drift'].get('drifted_features', [])),
                drift_results['feature_drift'].get('max_drift', 0),
                drift_results['prediction_drift'].get('drift_detected', False),
                drift_results['prediction_drift'].get('mean_shift', 0),
                json.dumps(drift_results)
            )
            
            self.db_manager.model_db.execute_command(insert_query, params)
            
        except Exception as e:
            logger.warning(f"Failed to log real-time drift: {e}")


class AdvancedDailyPredictor:
    """Advanced Daily Predictor with shadow deployment and real-time monitoring."""
    
    def __init__(self, model_version: Optional[str] = None):
        """Initialize advanced predictor."""
        self.db_manager = get_db_manager()
        self.model_version = model_version
        
        # Initialize components
        self.shadow_manager = ShadowDeploymentManager(self.db_manager)
        self.drift_detector = RealTimeDriftDetector(self.db_manager)
        
        # Model components
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.model_metadata = None
        
        # Shadow deployment models
        self.shadow_models = {}
        
        # Performance tracking
        self.performance_metrics = {
            'prediction_times': [],
            'drift_checks': [],
            'shadow_comparisons': []
        }
        
        self._load_model()
        self._load_shadow_models()
        
    def _load_model(self):
        """Load primary model with enhanced monitoring."""
        # Get model metadata (try v2 registry first)
        if self.model_version:
            query = """
            SELECT * FROM model_registry_v2 
            WHERE model_version = %s
            """
            params = (self.model_version,)
        else:
            query = """
            SELECT * FROM model_registry_v2 
            WHERE is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """
            params = None
        
        try:
            result = self.db_manager.model_db.execute_query(query, params)
        except:
            # Fallback to original registries
            if self.model_version:
                query = """
                SELECT * FROM model_registry_enhanced 
                WHERE model_version = %s
                UNION ALL
                SELECT * FROM model_registry 
                WHERE model_version = %s
                """
                params = (self.model_version, self.model_version)
            else:
                query = """
                SELECT * FROM model_registry_enhanced 
                WHERE is_active = true
                UNION ALL
                SELECT * FROM model_registry 
                WHERE is_active = true
                ORDER BY created_at DESC
                LIMIT 1
                """
                params = None
            
            result = self.db_manager.model_db.execute_query(query, params)
        
        if not result:
            raise ValueError(f"No model found with version: {self.model_version}")
        
        self.model_metadata = result[0]
        self.model_version = self.model_metadata['model_version']
        
        logger.info(f"Loading advanced model version: {self.model_version}")
        
        # Load model artifacts
        model_path = Path(self.model_metadata['model_file_path'])
        scaler_path = Path(self.model_metadata['scaler_file_path'])
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if not scaler_path.exists():
            raise FileNotFoundError(f"Scaler file not found: {scaler_path}")
        
        # Load components
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        
        # Load feature columns
        features_path = model_path.parent / 'feature_columns.json'
        with open(features_path, 'r') as f:
            self.feature_columns = json.load(f)
        
        # Load reference distributions for drift detection
        self.drift_detector.load_reference_distributions(self.model_version)
        
        logger.info(f"Advanced model loaded successfully: {self.model_version}")
    
    def _load_shadow_models(self):
        """Load any active shadow deployment models."""
        active_deployments = self.shadow_manager.get_active_shadow_deployments()
        
        for deployment in active_deployments:
            shadow_version = deployment['shadow_model_version']
            
            if shadow_version != self.model_version:
                try:
                    # Load shadow model
                    shadow_model_data = self._load_shadow_model(shadow_version)
                    self.shadow_models[shadow_version] = {
                        'model': shadow_model_data['model'],
                        'scaler': shadow_model_data['scaler'],
                        'feature_columns': shadow_model_data['feature_columns'],
                        'deployment_id': deployment['deployment_id'],
                        'traffic_percentage': deployment['traffic_percentage']
                    }
                    
                    logger.info(f"Loaded shadow model: {shadow_version}")
                    
                except Exception as e:
                    logger.warning(f"Failed to load shadow model {shadow_version}: {e}")
    
    def _load_shadow_model(self, model_version: str) -> Dict[str, Any]:
        """Load a specific shadow model."""
        # Get model metadata
        query = """
        SELECT * FROM model_registry_v2 WHERE model_version = %s
        UNION ALL
        SELECT * FROM model_registry_enhanced WHERE model_version = %s
        UNION ALL
        SELECT * FROM model_registry WHERE model_version = %s
        LIMIT 1
        """
        
        result = self.db_manager.model_db.execute_query(query, (model_version, model_version, model_version))
        
        if not result:
            raise ValueError(f"Shadow model not found: {model_version}")
        
        metadata = result[0]
        
        # Load artifacts
        model_path = Path(metadata['model_file_path'])
        scaler_path = Path(metadata['scaler_file_path'])
        
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        
        features_path = model_path.parent / 'feature_columns.json'
        with open(features_path, 'r') as f:
            feature_columns = json.load(f)
        
        return {
            'model': model,
            'scaler': scaler,
            'feature_columns': feature_columns,
            'metadata': metadata
        }
    
    def predict_daily(self, 
                     prediction_date: Optional[date] = None,
                     save_predictions: bool = True,
                     enable_shadow_deployment: bool = True,
                     enable_drift_detection: bool = True,
                     batch_size: int = 1000) -> pd.DataFrame:
        """Generate advanced predictions with shadow deployment and drift detection."""
        start_time = datetime.now()
        batch_id = f"batch_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='predict_daily_v2',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Determine dates
            if prediction_date is None:
                prediction_date = datetime.now().date()
            
            feature_date = prediction_date - timedelta(days=1)
            
            logger.info(f"Generating advanced predictions for {prediction_date}")
            logger.info(f"Shadow deployment enabled: {enable_shadow_deployment}")
            logger.info(f"Drift detection enabled: {enable_drift_detection}")
            
            # Get features
            features_df = self._get_features_for_prediction(feature_date)
            
            if features_df.empty:
                logger.warning(f"No features found for date {feature_date}")
                return pd.DataFrame()
            
            logger.info(f"Processing {len(features_df)} accounts")
            
            # Process in batches for better performance and monitoring
            all_predictions = []
            
            for i in range(0, len(features_df), batch_size):
                batch_features = features_df.iloc[i:i + batch_size]
                batch_predictions = self._process_prediction_batch(
                    batch_features,
                    prediction_date,
                    feature_date,
                    enable_shadow_deployment,
                    enable_drift_detection,
                    batch_id,
                    i // batch_size + 1
                )
                all_predictions.append(batch_predictions)
            
            # Combine all batch results
            if all_predictions:
                predictions_df = pd.concat(all_predictions, ignore_index=True)
            else:
                predictions_df = pd.DataFrame()
            
            # Save predictions if requested
            if save_predictions and not predictions_df.empty:
                saved_count = self._save_advanced_predictions(predictions_df)
                logger.info(f"Saved {saved_count} advanced predictions to database")
            
            # Log batch summary
            total_time = (datetime.now() - start_time).total_seconds() * 1000
            self._log_advanced_batch_summary(predictions_df, batch_id, total_time)
            
            # Update shadow deployment performance
            if enable_shadow_deployment:
                self._update_shadow_deployment_metrics(predictions_df)
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='predict_daily_v2',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=len(predictions_df),
                execution_details={
                    'batch_id': batch_id,
                    'duration_ms': total_time,
                    'shadow_models_used': len(self.shadow_models),
                    'drift_detection_enabled': enable_drift_detection
                }
            )
            
            return predictions_df
            
        except Exception as e:
            self.db_manager.log_pipeline_execution(
                pipeline_stage='predict_daily_v2',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e)
            )
            logger.error(f"Advanced prediction generation failed: {str(e)}")
            raise
    
    def _process_prediction_batch(self, batch_features: pd.DataFrame,
                                prediction_date: date,
                                feature_date: date,
                                enable_shadow_deployment: bool,
                                enable_drift_detection: bool,
                                batch_id: str,
                                batch_number: int) -> pd.DataFrame:
        """Process a single batch of predictions."""
        batch_start_time = datetime.now()
        
        logger.info(f"Processing batch {batch_number} ({len(batch_features)} accounts)")
        
        # Prepare features
        X = self._prepare_features(batch_features)
        
        # Generate primary predictions
        primary_predictions = self.model.predict(X)
        
        # Initialize results DataFrame
        results_df = pd.DataFrame({
            'login': batch_features['login'],
            'prediction_date': prediction_date,
            'feature_date': feature_date,
            'predicted_net_profit': primary_predictions,
            'model_version': self.model_version,
            'batch_id': batch_id,
            'batch_number': batch_number
        })
        
        # Drift detection
        drift_results = {}
        if enable_drift_detection:
            try:
                drift_results = self.drift_detector.detect_real_time_drift(
                    X, primary_predictions, self.model_version
                )
                
                # Add drift flags to results
                results_df['drift_detected'] = drift_results.get('overall_drift_detected', False)
                results_df['feature_drift_count'] = len(drift_results.get('feature_drift', {}).get('drifted_features', []))
                results_df['prediction_drift_detected'] = drift_results.get('prediction_drift', {}).get('drift_detected', False)
                
            except Exception as e:
                logger.warning(f"Drift detection failed for batch {batch_number}: {e}")
                drift_results = {}
        
        # Shadow deployment predictions
        shadow_predictions = {}
        if enable_shadow_deployment and self.shadow_models:
            shadow_predictions = self._generate_shadow_predictions(X, batch_features)
            
            # Add shadow predictions to results
            for shadow_version, shadow_data in shadow_predictions.items():
                results_df[f'shadow_{shadow_version}_prediction'] = shadow_data['predictions']
                results_df[f'shadow_{shadow_version}_confidence'] = shadow_data.get('confidence', 0.5)
        
        # Calculate enhanced confidence and risk scores
        results_df = self._enhance_predictions(results_df, batch_features, drift_results)
        
        # Performance tracking
        batch_duration = (datetime.now() - batch_start_time).total_seconds() * 1000
        results_df['batch_processing_time_ms'] = batch_duration / len(batch_features)
        
        logger.info(f"Batch {batch_number} completed in {batch_duration:.1f}ms")
        
        return results_df
    
    def _generate_shadow_predictions(self, X: pd.DataFrame, 
                                   batch_features: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """Generate predictions from shadow deployment models."""
        shadow_predictions = {}
        
        for shadow_version, shadow_data in self.shadow_models.items():
            try:
                # Check if this batch should use shadow model (traffic percentage)
                traffic_pct = shadow_data.get('traffic_percentage', 100)
                if traffic_pct < 100:
                    # Sample based on traffic percentage
                    sample_mask = np.random.random(len(X)) < (traffic_pct / 100)
                    if not sample_mask.any():
                        continue
                    X_shadow = X[sample_mask]
                else:
                    X_shadow = X
                    sample_mask = np.ones(len(X), dtype=bool)
                
                # Ensure feature compatibility
                shadow_features = shadow_data['feature_columns']
                common_features = [f for f in shadow_features if f in X.columns]
                
                if len(common_features) < len(shadow_features) * 0.8:  # Need at least 80% features
                    logger.warning(f"Shadow model {shadow_version} has incompatible features")
                    continue
                
                # Prepare features for shadow model
                X_shadow_prepared = X_shadow[common_features].copy()
                
                # Scale features using shadow model's scaler
                numerical_cols = [col for col in common_features 
                                if col not in ['market_volatility_regime', 'market_liquidity_state']]
                X_shadow_scaled = X_shadow_prepared.copy()
                X_shadow_scaled[numerical_cols] = shadow_data['scaler'].transform(X_shadow_prepared[numerical_cols])
                
                # Generate predictions
                shadow_preds = shadow_data['model'].predict(X_shadow_scaled)
                
                # Fill predictions for full batch (use NaN for non-sampled)
                full_predictions = np.full(len(X), np.nan)
                full_predictions[sample_mask] = shadow_preds
                
                # Calculate simple confidence (could be enhanced)
                confidence = np.full(len(X), 0.5)
                
                shadow_predictions[shadow_version] = {
                    'predictions': full_predictions,
                    'confidence': confidence,
                    'traffic_percentage': traffic_pct,
                    'features_used': len(common_features),
                    'sample_size': len(X_shadow)
                }
                
                logger.debug(f"Generated {len(X_shadow)} shadow predictions for {shadow_version}")
                
            except Exception as e:
                logger.warning(f"Failed to generate shadow predictions for {shadow_version}: {e}")
        
        return shadow_predictions
    
    def _get_features_for_prediction(self, feature_date: date) -> pd.DataFrame:
        """Get features with enhanced filtering and validation."""
        query = """
        SELECT f.*, s.phase, s.status
        FROM feature_store_account_daily f
        JOIN stg_accounts_daily_snapshots s
            ON f.account_id = s.account_id AND f.feature_date = s.date
        WHERE f.feature_date = %s
            AND s.phase = 'Funded'
            AND s.status IN ('Active', 'Trading')
        ORDER BY f.login
        """
        
        features_df = self.db_manager.model_db.execute_query_df(query, (feature_date,))
        
        if not features_df.empty:
            # Enhanced data quality checks
            # Check for accounts with sufficient trading history
            min_trading_days = 7
            if 'active_trading_days_count' in features_df.columns:
                sufficient_history = features_df['active_trading_days_count'] >= min_trading_days
                if not sufficient_history.all():
                    logger.info(f"Filtered out {(~sufficient_history).sum()} accounts with < {min_trading_days} trading days")
                    features_df = features_df[sufficient_history]
            
            # Check for extreme values that might indicate data quality issues
            numerical_cols = features_df.select_dtypes(include=[np.number]).columns
            for col in numerical_cols:
                if col in features_df.columns:
                    q99 = features_df[col].quantile(0.99)
                    q1 = features_df[col].quantile(0.01)
                    extreme_mask = (features_df[col] > q99 * 10) | (features_df[col] < q1 * 10)
                    if extreme_mask.any():
                        logger.warning(f"Found {extreme_mask.sum()} extreme values in {col}")
        
        return features_df
    
    def _prepare_features(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for prediction with validation."""
        # Select feature columns
        X = features_df[self.feature_columns].copy()
        
        # Handle categorical features
        categorical_features = ['market_volatility_regime', 'market_liquidity_state']
        for cat_col in categorical_features:
            if cat_col in X.columns:
                X[cat_col] = X[cat_col].astype('category')
        
        # Identify numerical columns for scaling
        numerical_cols = [col for col in X.columns if col not in categorical_features]
        
        # Apply scaling to numerical features
        X_scaled = X.copy()
        X_scaled[numerical_cols] = self.scaler.transform(X[numerical_cols])
        
        return X_scaled
    
    def _enhance_predictions(self, results_df: pd.DataFrame,
                           batch_features: pd.DataFrame,
                           drift_results: Dict[str, Any]) -> pd.DataFrame:
        """Enhance predictions with confidence, risk scores, and metadata."""
        # Calculate prediction confidence
        base_confidence = 70
        
        # Adjust confidence based on drift detection
        if drift_results.get('overall_drift_detected', False):
            confidence_penalty = min(20, len(drift_results.get('feature_drift', {}).get('drifted_features', [])) * 3)
            results_df['prediction_confidence'] = base_confidence - confidence_penalty
        else:
            results_df['prediction_confidence'] = base_confidence
        
        # Calculate risk scores
        risk_threshold = results_df['predicted_net_profit'].quantile(0.1)
        results_df['is_high_risk'] = results_df['predicted_net_profit'] < risk_threshold
        
        # Calculate risk score (0-100, higher = more risky)
        risk_scores = np.zeros(len(results_df))
        
        # Risk from prediction magnitude
        pred_losses = np.minimum(0, results_df['predicted_net_profit'])
        if pred_losses.std() > 0:
            loss_risk = (pred_losses - pred_losses.mean()) / pred_losses.std()
            risk_scores += np.maximum(0, loss_risk) * 40
        
        # Risk from drift detection
        if 'drift_detected' in results_df.columns:
            drift_mask = results_df['drift_detected']
            risk_scores[drift_mask] += 30
        
        results_df['risk_score'] = np.clip(risk_scores, 0, 100)
        
        # Add predicted direction
        results_df['predicted_direction'] = np.where(
            results_df['predicted_net_profit'] > 0, 'PROFIT', 'LOSS'
        )
        
        # Data quality score (based on feature completeness)
        if not batch_features.empty:
            completeness = (1 - batch_features[self.feature_columns].isnull().sum(axis=1) / len(self.feature_columns)) * 100
            results_df['data_quality_score'] = completeness.values
        else:
            results_df['data_quality_score'] = 0
        
        return results_df
    
    def _save_advanced_predictions(self, predictions_df: pd.DataFrame) -> int:
        """Save advanced predictions with shadow deployment data."""
        # Create advanced predictions table if needed
        create_table_query = """
        CREATE TABLE IF NOT EXISTS model_predictions_v2 (
            id SERIAL PRIMARY KEY,
            login VARCHAR(255) NOT NULL,
            prediction_date DATE NOT NULL,
            feature_date DATE NOT NULL,
            predicted_net_profit DECIMAL(18, 2),
            prediction_confidence DECIMAL(5, 2),
            model_version VARCHAR(50),
            
            -- Shadow deployment data
            shadow_predictions JSONB,
            
            -- Drift detection results
            drift_detected BOOLEAN DEFAULT FALSE,
            feature_drift_count INTEGER DEFAULT 0,
            prediction_drift_detected BOOLEAN DEFAULT FALSE,
            
            -- Risk and quality scores
            is_high_risk BOOLEAN,
            risk_score DECIMAL(5, 2),
            predicted_direction VARCHAR(10),
            data_quality_score DECIMAL(5, 2),
            
            -- Performance metadata
            batch_id VARCHAR(100),
            batch_number INTEGER,
            batch_processing_time_ms DECIMAL(10, 2),
            
            -- Actual outcomes (filled later)
            actual_net_profit DECIMAL(18, 2),
            prediction_error DECIMAL(18, 2),
            direction_correct BOOLEAN,
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(login, prediction_date, model_version)
        )
        """
        
        try:
            self.db_manager.model_db.execute_command(create_table_query)
            
            # Prepare records for insertion
            records = []
            for _, row in predictions_df.iterrows():
                # Collect shadow predictions
                shadow_preds = {}
                for col in row.index:
                    if col.startswith('shadow_') and col.endswith('_prediction'):
                        shadow_version = col.replace('shadow_', '').replace('_prediction', '')
                        if not pd.isna(row[col]):
                            shadow_preds[shadow_version] = {
                                'prediction': float(row[col]),
                                'confidence': float(row.get(f'shadow_{shadow_version}_confidence', 0.5))
                            }
                
                record = {
                    'login': row['login'],
                    'prediction_date': row['prediction_date'],
                    'feature_date': row['feature_date'],
                    'predicted_net_profit': float(row['predicted_net_profit']),
                    'prediction_confidence': float(row['prediction_confidence']),
                    'model_version': row['model_version'],
                    'shadow_predictions': json.dumps(shadow_preds) if shadow_preds else None,
                    'drift_detected': row.get('drift_detected', False),
                    'feature_drift_count': int(row.get('feature_drift_count', 0)),
                    'prediction_drift_detected': row.get('prediction_drift_detected', False),
                    'is_high_risk': row.get('is_high_risk', False),
                    'risk_score': float(row.get('risk_score', 0)),
                    'predicted_direction': row['predicted_direction'],
                    'data_quality_score': float(row.get('data_quality_score', 0)),
                    'batch_id': row.get('batch_id'),
                    'batch_number': int(row.get('batch_number', 0)),
                    'batch_processing_time_ms': float(row.get('batch_processing_time_ms', 0))
                }
                records.append(record)
            
            # Batch insert
            saved_count = 0
            if records:
                columns = list(records[0].keys())
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join(columns)
                
                query = f"""
                INSERT INTO model_predictions_v2 ({columns_str})
                VALUES ({placeholders})
                ON CONFLICT (login, prediction_date, model_version) 
                DO UPDATE SET
                    predicted_net_profit = EXCLUDED.predicted_net_profit,
                    prediction_confidence = EXCLUDED.prediction_confidence,
                    shadow_predictions = EXCLUDED.shadow_predictions,
                    drift_detected = EXCLUDED.drift_detected
                """
                
                with self.db_manager.model_db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        for record in records:
                            values = [record[col] for col in columns]
                            cursor.execute(query, values)
                            saved_count += 1
            
            return saved_count
            
        except Exception as e:
            logger.error(f"Failed to save advanced predictions: {e}")
            return 0
    
    def _log_advanced_batch_summary(self, predictions_df: pd.DataFrame,
                                  batch_id: str, total_time_ms: float):
        """Log comprehensive batch summary."""
        if predictions_df.empty:
            return
        
        logger.info(f"Advanced prediction batch summary ({batch_id}):")
        logger.info(f"  Total accounts: {len(predictions_df)}")
        logger.info(f"  Processing time: {total_time_ms:.1f}ms")
        logger.info(f"  Avg time per prediction: {total_time_ms/len(predictions_df):.2f}ms")
        logger.info(f"  Mean predicted PnL: ${predictions_df['predicted_net_profit'].mean():.2f}")
        logger.info(f"  Predicted profits: {(predictions_df['predicted_net_profit'] > 0).sum()}")
        logger.info(f"  Predicted losses: {(predictions_df['predicted_net_profit'] < 0).sum()}")
        logger.info(f"  Average confidence: {predictions_df['prediction_confidence'].mean():.1f}%")
        
        if 'drift_detected' in predictions_df.columns:
            drift_count = predictions_df['drift_detected'].sum()
            logger.info(f"  Drift detected: {drift_count} accounts ({drift_count/len(predictions_df)*100:.1f}%)")
        
        if 'is_high_risk' in predictions_df.columns:
            high_risk_count = predictions_df['is_high_risk'].sum()
            logger.info(f"  High risk accounts: {high_risk_count} ({high_risk_count/len(predictions_df)*100:.1f}%)")
        
        # Shadow deployment summary
        shadow_cols = [col for col in predictions_df.columns if col.startswith('shadow_') and col.endswith('_prediction')]
        if shadow_cols:
            logger.info(f"  Shadow models used: {len(shadow_cols)}")
            for col in shadow_cols:
                model_name = col.replace('shadow_', '').replace('_prediction', '')
                non_null_count = predictions_df[col].notna().sum()
                logger.info(f"    {model_name}: {non_null_count} predictions")
    
    def _update_shadow_deployment_metrics(self, predictions_df: pd.DataFrame):
        """Update shadow deployment performance metrics."""
        for deployment_id in predictions_df['batch_id'].unique():
            try:
                # Calculate metrics for this batch
                batch_metrics = {
                    'batch_id': deployment_id,
                    'timestamp': datetime.now().isoformat(),
                    'predictions_count': len(predictions_df),
                    'avg_confidence': float(predictions_df['prediction_confidence'].mean()),
                    'high_risk_rate': float((predictions_df.get('is_high_risk', False)).mean()),
                    'drift_detection_rate': float((predictions_df.get('drift_detected', False)).mean())
                }
                
                # Update deployment metrics (simplified - in production would be more sophisticated)
                for shadow_version in self.shadow_models.keys():
                    shadow_col = f'shadow_{shadow_version}_prediction'
                    if shadow_col in predictions_df.columns:
                        shadow_predictions = predictions_df[shadow_col].dropna()
                        if len(shadow_predictions) > 0:
                            batch_metrics[f'{shadow_version}_predictions'] = len(shadow_predictions)
                            batch_metrics[f'{shadow_version}_avg_prediction'] = float(shadow_predictions.mean())
                
                # This would typically update a more sophisticated metrics tracking system
                logger.debug(f"Updated shadow deployment metrics: {batch_metrics}")
                
            except Exception as e:
                logger.warning(f"Failed to update shadow deployment metrics: {e}")
    
    def create_shadow_deployment(self, shadow_model_version: str,
                               traffic_percentage: float = 100.0,
                               duration_days: int = 7) -> str:
        """Create a new shadow deployment."""
        deployment_config = {
            'traffic_percentage': traffic_percentage,
            'duration_days': duration_days,
            'auto_promote': False,
            'comparison_metrics': ['mae', 'direction_accuracy', 'confidence'],
            'created_by': 'predict_daily_v2'
        }
        
        deployment_id = self.shadow_manager.create_shadow_deployment(
            shadow_model_version,
            self.model_version,
            deployment_config
        )
        
        # Reload shadow models to include new deployment
        self._load_shadow_models()
        
        return deployment_id
    
    def evaluate_shadow_deployments(self, evaluation_period_days: int = 7) -> Dict[str, Any]:
        """Evaluate all active shadow deployments."""
        active_deployments = self.shadow_manager.get_active_shadow_deployments()
        
        evaluation_results = {}
        
        for deployment in active_deployments:
            deployment_id = deployment['deployment_id']
            try:
                comparison = self.shadow_manager.compare_shadow_vs_production(
                    deployment_id, evaluation_period_days
                )
                evaluation_results[deployment_id] = comparison
                
                logger.info(f"Shadow deployment {deployment_id} evaluation:")
                if 'mae_improvement_pct' in comparison:
                    logger.info(f"  MAE improvement: {comparison['mae_improvement_pct']:.1f}%")
                if 'accuracy_improvement_pct' in comparison:
                    logger.info(f"  Accuracy improvement: {comparison['accuracy_improvement_pct']:.1f}%")
                if 'recommendation' in comparison:
                    logger.info(f"  Recommendation: {comparison['recommendation']}")
                
            except Exception as e:
                logger.error(f"Failed to evaluate shadow deployment {deployment_id}: {e}")
                evaluation_results[deployment_id] = {"error": str(e)}
        
        return evaluation_results


def main():
    """Main function for advanced prediction generation."""
    parser = argparse.ArgumentParser(description='Advanced Daily Predictions v2')
    parser.add_argument('--prediction-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Date to predict for (YYYY-MM-DD)')
    parser.add_argument('--model-version', help='Model version to use')
    parser.add_argument('--no-save', action='store_true',
                       help='Do not save predictions')
    parser.add_argument('--disable-shadow', action='store_true',
                       help='Disable shadow deployment')
    parser.add_argument('--disable-drift-detection', action='store_true',
                       help='Disable drift detection')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='Batch size for processing')
    parser.add_argument('--create-shadow', help='Create shadow deployment with specified model version')
    parser.add_argument('--shadow-traffic', type=float, default=100.0,
                       help='Traffic percentage for shadow deployment')
    parser.add_argument('--evaluate-shadows', action='store_true',
                       help='Evaluate active shadow deployments')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level=args.log_level, log_file='predict_daily_v2')
    
    # Create advanced predictor
    predictor = AdvancedDailyPredictor(model_version=args.model_version)
    
    try:
        if args.create_shadow:
            # Create shadow deployment
            deployment_id = predictor.create_shadow_deployment(
                args.create_shadow,
                args.shadow_traffic
            )
            logger.info(f"Created shadow deployment: {deployment_id}")
            
        elif args.evaluate_shadows:
            # Evaluate shadow deployments
            results = predictor.evaluate_shadow_deployments()
            
            logger.info("\nShadow Deployment Evaluation Results:")
            logger.info("=" * 60)
            
            for deployment_id, result in results.items():
                logger.info(f"\nDeployment: {deployment_id}")
                if 'error' in result:
                    logger.info(f"  Error: {result['error']}")
                else:
                    logger.info(f"  Shadow Model: {result.get('shadow_model', 'Unknown')}")
                    logger.info(f"  Production Model: {result.get('production_model', 'Unknown')}")
                    if 'mae_improvement_pct' in result:
                        logger.info(f"  MAE Improvement: {result['mae_improvement_pct']:.1f}%")
                    if 'accuracy_improvement_pct' in result:
                        logger.info(f"  Accuracy Improvement: {result['accuracy_improvement_pct']:.1f}%")
                    if 'recommendation' in result:
                        logger.info(f"  Recommendation: {result['recommendation'].upper()}")
            
        else:
            # Generate predictions
            predictions = predictor.predict_daily(
                prediction_date=args.prediction_date,
                save_predictions=not args.no_save,
                enable_shadow_deployment=not args.disable_shadow,
                enable_drift_detection=not args.disable_drift_detection,
                batch_size=args.batch_size
            )
            
            if not predictions.empty:
                # Display advanced summary
                logger.info("\nAdvanced Prediction Summary:")
                logger.info("=" * 50)
                
                logger.info(f"Total Predictions: {len(predictions)}")
                logger.info(f"Mean Predicted PnL: ${predictions['predicted_net_profit'].mean():.2f}")
                logger.info(f"Average Confidence: {predictions['prediction_confidence'].mean():.1f}%")
                
                if 'drift_detected' in predictions.columns:
                    drift_count = predictions['drift_detected'].sum()
                    logger.info(f"Drift Detected: {drift_count} accounts ({drift_count/len(predictions)*100:.1f}%)")
                
                if 'is_high_risk' in predictions.columns:
                    high_risk_count = predictions['is_high_risk'].sum()
                    logger.info(f"High Risk: {high_risk_count} accounts ({high_risk_count/len(predictions)*100:.1f}%)")
                
                # Shadow deployment summary
                shadow_cols = [col for col in predictions.columns if col.startswith('shadow_') and col.endswith('_prediction')]
                if shadow_cols:
                    logger.info(f"\nShadow Models Active: {len(shadow_cols)}")
                    for col in shadow_cols:
                        model_name = col.replace('shadow_', '').replace('_prediction', '')
                        non_null_count = predictions[col].notna().sum()
                        logger.info(f"  {model_name}: {non_null_count} predictions")
                
                logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"Advanced prediction failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()