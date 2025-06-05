"""
Generate daily predictions for all eligible accounts.
Loads the latest data, runs feature engineering, and generates predictions for T+1.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
import argparse
import pandas as pd
import numpy as np
import json
import joblib
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class DailyPredictor:
    """Handles daily prediction generation for all eligible accounts."""
    
    def __init__(self, model_version: Optional[str] = None):
        """
        Initialize the daily predictor.
        
        Args:
            model_version: Version of model to use (defaults to active model)
        """
        self.db_manager = get_db_manager()
        self.model_version = model_version
        
        # Load model artifacts
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.model_metadata = None
        
        self._load_model()
    
    def _load_model(self):
        """Load the model and associated artifacts."""
        # Get model metadata from registry
        if self.model_version:
            query = """
            SELECT * FROM model_registry 
            WHERE model_version = %s
            """
            params = (self.model_version,)
        else:
            # Get the active model
            query = """
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
        
        logger.info(f"Loading model version: {self.model_version}")
        
        # Load model artifacts
        model_path = Path(self.model_metadata['model_file_path'])
        scaler_path = Path(self.model_metadata['scaler_file_path'])
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if not scaler_path.exists():
            raise FileNotFoundError(f"Scaler file not found: {scaler_path}")
        
        # Load model and scaler
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        
        # Load feature columns
        features_path = model_path.parent / 'feature_columns.json'
        with open(features_path, 'r') as f:
            self.feature_columns = json.load(f)
        
        logger.info(f"Model loaded successfully: {self.model_version}")
    
    def predict_daily(self, 
                     prediction_date: Optional[date] = None,
                     save_predictions: bool = True) -> pd.DataFrame:
        """
        Generate predictions for all eligible accounts for a specific date.
        
        Args:
            prediction_date: Date to predict for (T+1). If None, predicts for tomorrow.
            save_predictions: Whether to save predictions to database
            
        Returns:
            DataFrame containing predictions
        """
        start_time = datetime.now()
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='predict_daily',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Determine prediction date (T+1)
            if prediction_date is None:
                prediction_date = datetime.now().date()  # Predict for today based on yesterday's features
            
            feature_date = prediction_date - timedelta(days=1)  # T
            
            logger.info(f"Generating predictions for {prediction_date} using features from {feature_date}")
            
            # Get features for all eligible accounts
            features_df = self._get_features_for_prediction(feature_date)
            
            if features_df.empty:
                logger.warning(f"No features found for date {feature_date}")
                return pd.DataFrame()
            
            logger.info(f"Found features for {len(features_df)} accounts")
            
            # Prepare features for prediction
            X = self._prepare_features(features_df)
            
            # Generate predictions
            predictions_raw = self.model.predict(X)
            
            # Create predictions DataFrame
            predictions_df = pd.DataFrame({
                'login': features_df['login'],
                'prediction_date': prediction_date,
                'feature_date': feature_date,
                'predicted_net_profit': predictions_raw,
                'model_version': self.model_version
            })
            
            # Calculate prediction confidence (based on historical accuracy)
            predictions_df['prediction_confidence'] = self._calculate_confidence(
                features_df, predictions_raw
            )
            
            # Save predictions if requested
            if save_predictions:
                saved_count = self._save_predictions(predictions_df)
                logger.info(f"Saved {saved_count} predictions to database")
            
            # Log summary statistics
            logger.info(f"Prediction summary for {prediction_date}:")
            logger.info(f"  - Total accounts: {len(predictions_df)}")
            logger.info(f"  - Mean predicted PnL: ${predictions_df['predicted_net_profit'].mean():.2f}")
            logger.info(f"  - Std predicted PnL: ${predictions_df['predicted_net_profit'].std():.2f}")
            logger.info(f"  - Predicted winners: {(predictions_df['predicted_net_profit'] > 0).sum()}")
            logger.info(f"  - Predicted losers: {(predictions_df['predicted_net_profit'] < 0).sum()}")
            
            # Identify high-risk accounts (large predicted losses)
            high_risk_threshold = predictions_df['predicted_net_profit'].quantile(0.05)
            high_risk_accounts = predictions_df[
                predictions_df['predicted_net_profit'] < high_risk_threshold
            ]
            logger.info(f"  - High risk accounts (bottom 5%): {len(high_risk_accounts)}")
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='predict_daily',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=len(predictions_df),
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'prediction_date': str(prediction_date),
                    'feature_date': str(feature_date),
                    'model_version': self.model_version,
                    'accounts_predicted': len(predictions_df),
                    'mean_prediction': float(predictions_df['predicted_net_profit'].mean())
                }
            )
            
            return predictions_df
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='predict_daily',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e)
            )
            logger.error(f"Failed to generate predictions: {str(e)}")
            raise
    
    def _get_features_for_prediction(self, feature_date: date) -> pd.DataFrame:
        """Get features for all eligible accounts for the feature date."""
        query = """
        SELECT f.*, s.phase, s.status
        FROM feature_store_account_daily f
        JOIN stg_accounts_daily_snapshots s
            ON f.account_id = s.account_id AND f.feature_date = s.date
        WHERE f.feature_date = %s
            AND s.phase = 'Funded'
            AND s.status IN ('Active', 'Trading')  -- Adjust based on your status values
        """
        
        features_df = self.db_manager.model_db.execute_query_df(query, (feature_date,))
        
        return features_df
    
    def _prepare_features(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for prediction (scaling, column selection, etc.)."""
        # Select only the feature columns used in training
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
    
    def _calculate_confidence(self, features_df: pd.DataFrame, 
                            predictions: np.ndarray) -> np.ndarray:
        """
        Calculate prediction confidence based on feature quality and historical accuracy.
        
        This is a simplified confidence calculation. In production, you might:
        - Use prediction intervals from the model
        - Calculate based on similar historical predictions
        - Use ensemble disagreement as uncertainty measure
        """
        confidence_scores = np.ones(len(predictions)) * 0.7  # Base confidence
        
        # Adjust confidence based on data quality
        # Lower confidence for accounts with fewer historical data points
        if 'active_trading_days_count' in features_df.columns:
            # More trading days = higher confidence
            trading_days = features_df['active_trading_days_count'].values
            confidence_adjustment = np.clip(trading_days / 100, 0.5, 1.0)
            confidence_scores *= confidence_adjustment
        
        # Lower confidence for extreme predictions
        pred_std = np.std(predictions)
        pred_mean = np.mean(predictions)
        z_scores = np.abs((predictions - pred_mean) / (pred_std + 1e-6))
        extreme_adjustment = 1.0 - np.clip(z_scores / 3, 0, 0.3)
        confidence_scores *= extreme_adjustment
        
        # Convert to percentage
        confidence_scores = np.clip(confidence_scores * 100, 10, 95)
        
        return confidence_scores
    
    def _save_predictions(self, predictions_df: pd.DataFrame) -> int:
        """Save predictions to the database."""
        # Prepare data for insertion
        records = []
        for _, row in predictions_df.iterrows():
            records.append({
                'login': row['login'],
                'prediction_date': row['prediction_date'],
                'feature_date': row['feature_date'],
                'predicted_net_profit': float(row['predicted_net_profit']),
                'prediction_confidence': float(row['prediction_confidence']),
                'model_version': row['model_version'],
                'shap_values': None,  # Would be calculated if needed
                'top_positive_features': None,
                'top_negative_features': None,
                'actual_net_profit': None,  # Filled later when actual is known
                'prediction_error': None
            })
        
        # Insert into database
        saved_count = 0
        if records:
            # Use batch insert
            columns = list(records[0].keys())
            placeholders = ', '.join(['%s'] * len(columns))
            columns_str = ', '.join(columns)
            
            query = f"""
            INSERT INTO model_predictions ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT (login, prediction_date, model_version) 
            DO UPDATE SET
                predicted_net_profit = EXCLUDED.predicted_net_profit,
                prediction_confidence = EXCLUDED.prediction_confidence
            """
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    for record in records:
                        values = [record[col] for col in columns]
                        cursor.execute(query, values)
                        saved_count += 1
        
        return saved_count
    
    def evaluate_predictions(self, evaluation_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Evaluate predictions against actual outcomes.
        
        Args:
            evaluation_date: Date to evaluate predictions for
            
        Returns:
            Dictionary containing evaluation metrics
        """
        if evaluation_date is None:
            evaluation_date = datetime.now().date() - timedelta(days=1)
        
        logger.info(f"Evaluating predictions for {evaluation_date}")
        
        # Get predictions and actuals
        query = """
        SELECT 
            p.login,
            p.predicted_net_profit,
            p.prediction_confidence,
            m.net_profit as actual_net_profit
        FROM model_predictions p
        JOIN raw_metrics_daily m
            ON p.login = m.login AND p.prediction_date = m.date
        WHERE p.prediction_date = %s
            AND p.model_version = %s
        """
        
        results_df = self.db_manager.model_db.execute_query_df(
            query, (evaluation_date, self.model_version)
        )
        
        if results_df.empty:
            logger.warning(f"No predictions found for evaluation on {evaluation_date}")
            return {}
        
        # Calculate metrics
        y_true = results_df['actual_net_profit']
        y_pred = results_df['predicted_net_profit']
        
        mae = np.mean(np.abs(y_true - y_pred))
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
        
        # Directional accuracy
        direction_correct = ((y_true > 0) == (y_pred > 0)).mean() * 100
        
        # Update predictions with actual values and errors
        update_query = """
        UPDATE model_predictions
        SET actual_net_profit = %s,
            prediction_error = %s
        WHERE login = %s 
            AND prediction_date = %s 
            AND model_version = %s
        """
        
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                for _, row in results_df.iterrows():
                    error = row['predicted_net_profit'] - row['actual_net_profit']
                    cursor.execute(update_query, (
                        row['actual_net_profit'],
                        error,
                        row['login'],
                        evaluation_date,
                        self.model_version
                    ))
        
        evaluation_metrics = {
            'evaluation_date': evaluation_date,
            'model_version': self.model_version,
            'accounts_evaluated': len(results_df),
            'mae': mae,
            'rmse': rmse,
            'direction_accuracy': direction_correct,
            'actual_mean': y_true.mean(),
            'predicted_mean': y_pred.mean(),
            'actual_std': y_true.std(),
            'predicted_std': y_pred.std()
        }
        
        logger.info(f"Evaluation complete: MAE=${mae:.2f}, Direction accuracy={direction_correct:.1f}%")
        
        return evaluation_metrics


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Generate daily predictions')
    parser.add_argument('--prediction-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Date to predict for (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--model-version', help='Model version to use (defaults to active model)')
    parser.add_argument('--no-save', action='store_true',
                       help='Do not save predictions to database')
    parser.add_argument('--evaluate', action='store_true',
                       help='Evaluate yesterday\'s predictions against actuals')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='predict_daily')
    
    # Create predictor
    predictor = DailyPredictor(model_version=args.model_version)
    
    try:
        if args.evaluate:
            # Evaluate previous predictions
            metrics = predictor.evaluate_predictions()
            if metrics:
                logger.info("\nEvaluation Results:")
                logger.info(f"  Date: {metrics['evaluation_date']}")
                logger.info(f"  Accounts: {metrics['accounts_evaluated']}")
                logger.info(f"  MAE: ${metrics['mae']:.2f}")
                logger.info(f"  RMSE: ${metrics['rmse']:.2f}")
                logger.info(f"  Direction Accuracy: {metrics['direction_accuracy']:.1f}%")
        else:
            # Generate predictions
            predictions = predictor.predict_daily(
                prediction_date=args.prediction_date,
                save_predictions=not args.no_save
            )
            
            if not predictions.empty:
                # Display top predictions
                logger.info("\nTop 10 Predicted Profits:")
                top_profits = predictions.nlargest(10, 'predicted_net_profit')
                for _, row in top_profits.iterrows():
                    logger.info(f"  {row['login']}: ${row['predicted_net_profit']:.2f} "
                              f"(confidence: {row['prediction_confidence']:.1f}%)")
                
                logger.info("\nTop 10 Predicted Losses:")
                top_losses = predictions.nsmallest(10, 'predicted_net_profit')
                for _, row in top_losses.iterrows():
                    logger.info(f"  {row['login']}: ${row['predicted_net_profit']:.2f} "
                              f"(confidence: {row['prediction_confidence']:.1f}%)")
    
    except Exception as e:
        logger.error(f"Prediction failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()