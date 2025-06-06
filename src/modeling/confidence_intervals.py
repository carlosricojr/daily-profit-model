"""
Confidence interval estimation for model predictions.
Implements multiple approaches from conservative to aggressive.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
import logging
from sklearn.neighbors import NearestNeighbors
import lightgbm as lgb

logger = logging.getLogger(__name__)


class BaseConfidenceEstimator:
    """Base class for confidence interval estimation."""
    
    def __init__(self, coverage: float = 0.90):
        """
        Initialize confidence estimator.
        
        Args:
            coverage: Target coverage probability (e.g., 0.90 for 90% CI)
        """
        self.coverage = coverage
        self.alpha = 1 - coverage
        
    def estimate_intervals(self, X: pd.DataFrame, predictions: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Estimate confidence intervals for predictions.
        
        Returns:
            Tuple of (lower_bounds, upper_bounds)
        """
        raise NotImplementedError


class ConservativeConfidenceEstimator(BaseConfidenceEstimator):
    """Version 1: Simple confidence intervals based on historical errors."""
    
    def __init__(self, coverage: float = 0.90):
        super().__init__(coverage)
        self.error_stats = None
        
    def fit(self, y_true: np.ndarray, y_pred: np.ndarray, X: Optional[pd.DataFrame] = None):
        """Fit the confidence estimator on historical data."""
        errors = y_true - y_pred
        
        # Calculate error statistics
        self.error_stats = {
            'mean': np.mean(errors),
            'std': np.std(errors),
            'percentiles': {
                'lower': np.percentile(errors, (self.alpha / 2) * 100),
                'upper': np.percentile(errors, (1 - self.alpha / 2) * 100)
            }
        }
        
        # Store absolute errors for heteroscedastic adjustment
        self.abs_errors = np.abs(errors)
        self.y_pred_train = y_pred
        
        logger.info(f"Fitted conservative CI estimator: mean_error={self.error_stats['mean']:.2f}, "
                   f"std_error={self.error_stats['std']:.2f}")
    
    def estimate_intervals(self, X: pd.DataFrame, predictions: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate confidence intervals using historical error distribution."""
        if self.error_stats is None:
            raise ValueError("Estimator must be fitted before use")
        
        # Basic approach: symmetric intervals based on error percentiles
        lower_bounds = predictions + self.error_stats['percentiles']['lower']
        upper_bounds = predictions + self.error_stats['percentiles']['upper']
        
        # Adjust for heteroscedasticity (larger intervals for extreme predictions)
        if hasattr(self, 'y_pred_train'):
            # Find similar historical predictions
            pred_std = np.std(self.y_pred_train)
            pred_mean = np.mean(self.y_pred_train)
            
            # Scale intervals based on prediction magnitude
            scale_factors = 1 + 0.1 * np.abs((predictions - pred_mean) / (pred_std + 1e-6))
            interval_width = upper_bounds - lower_bounds
            
            lower_bounds = predictions - (interval_width / 2) * scale_factors
            upper_bounds = predictions + (interval_width / 2) * scale_factors
        
        return lower_bounds, upper_bounds
    
    def get_prediction_uncertainty(self, X: pd.DataFrame, predictions: np.ndarray) -> np.ndarray:
        """Get uncertainty scores for predictions."""
        if self.error_stats is None:
            raise ValueError("Estimator must be fitted before use")
        
        # Simple uncertainty based on prediction magnitude
        pred_mean = np.mean(self.y_pred_train) if hasattr(self, 'y_pred_train') else 0
        pred_std = np.std(self.y_pred_train) if hasattr(self, 'y_pred_train') else 1
        
        # Higher uncertainty for predictions far from training distribution
        z_scores = np.abs((predictions - pred_mean) / (pred_std + 1e-6))
        uncertainty = self.error_stats['std'] * (1 + 0.1 * z_scores)
        
        return uncertainty


class BalancedConfidenceEstimator(BaseConfidenceEstimator):
    """Version 2: Quantile regression and nearest neighbors approach."""
    
    def __init__(self, coverage: float = 0.90, n_neighbors: int = 50):
        super().__init__(coverage)
        self.n_neighbors = n_neighbors
        self.lower_model = None
        self.upper_model = None
        self.nn_model = None
        self.X_train = None
        self.residuals_train = None
        
    def fit(self, y_true: np.ndarray, y_pred: np.ndarray, X: pd.DataFrame):
        """Fit quantile regression models and nearest neighbors."""
        self.X_train = X.copy()
        self.residuals_train = y_true - y_pred
        
        # Fit quantile regression forests for upper and lower bounds
        logger.info("Fitting quantile regression models...")
        
        # Lower quantile
        self.lower_model = lgb.LGBMRegressor(
            objective='quantile',
            alpha=self.alpha / 2,
            n_estimators=100,
            random_state=42,
            verbosity=-1
        )
        self.lower_model.fit(X, y_true)
        
        # Upper quantile
        self.upper_model = lgb.LGBMRegressor(
            objective='quantile',
            alpha=1 - self.alpha / 2,
            n_estimators=100,
            random_state=42,
            verbosity=-1
        )
        self.upper_model.fit(X, y_true)
        
        # Fit nearest neighbors for local uncertainty estimation
        self.nn_model = NearestNeighbors(n_neighbors=self.n_neighbors)
        self.nn_model.fit(X)
        
        logger.info(f"Fitted balanced CI estimator with {self.n_neighbors} neighbors")
    
    def estimate_intervals(self, X: pd.DataFrame, predictions: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate intervals using quantile regression and local information."""
        if self.lower_model is None:
            raise ValueError("Estimator must be fitted before use")
        
        # Get quantile predictions
        lower_quantile = self.lower_model.predict(X)
        upper_quantile = self.upper_model.predict(X)
        
        # Adjust using local uncertainty from nearest neighbors
        local_uncertainty = self._get_local_uncertainty(X)
        
        # Combine approaches
        lower_bounds = 0.7 * lower_quantile + 0.3 * (predictions - local_uncertainty)
        upper_bounds = 0.7 * upper_quantile + 0.3 * (predictions + local_uncertainty)
        
        # Ensure prediction is within bounds
        lower_bounds = np.minimum(lower_bounds, predictions)
        upper_bounds = np.maximum(upper_bounds, predictions)
        
        return lower_bounds, upper_bounds
    
    def _get_local_uncertainty(self, X: pd.DataFrame) -> np.ndarray:
        """Estimate local uncertainty using nearest neighbors."""
        distances, indices = self.nn_model.kneighbors(X)
        
        uncertainties = []
        for idx_list in indices:
            # Get residuals of nearest neighbors
            local_residuals = self.residuals_train[idx_list]
            
            # Calculate local uncertainty (e.g., 90th percentile of absolute residuals)
            local_uncertainty = np.percentile(np.abs(local_residuals), 90)
            uncertainties.append(local_uncertainty)
        
        return np.array(uncertainties)
    
    def get_calibrated_intervals(self, X: pd.DataFrame, predictions: np.ndarray,
                               calibration_data: Optional[Dict[str, np.ndarray]] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Get calibrated confidence intervals using historical coverage."""
        lower, upper = self.estimate_intervals(X, predictions)
        
        if calibration_data is not None:
            # Adjust intervals based on historical coverage
            y_true_cal = calibration_data['y_true']
            y_pred_cal = calibration_data['y_pred']
            X_cal = calibration_data['X']
            
            lower_cal, upper_cal = self.estimate_intervals(X_cal, y_pred_cal)
            
            # Calculate actual coverage
            coverage = np.mean((y_true_cal >= lower_cal) & (y_true_cal <= upper_cal))
            
            # Adjust interval width if coverage is off
            if coverage < self.coverage:
                # Widen intervals
                adjustment = (self.coverage / coverage) ** 0.5
                width = upper - lower
                center = (upper + lower) / 2
                lower = center - width * adjustment / 2
                upper = center + width * adjustment / 2
            
            logger.info(f"Calibrated intervals: actual coverage={coverage:.3f}, target={self.coverage:.3f}")
        
        return lower, upper


class AggressiveConfidenceEstimator(BaseConfidenceEstimator):
    """Version 3: Ensemble approach with multiple uncertainty estimation methods."""
    
    def __init__(self, coverage: float = 0.90, n_bootstrap: int = 100):
        super().__init__(coverage)
        self.n_bootstrap = n_bootstrap
        self.bootstrap_models = []
        self.dropout_model = None
        self.quantile_estimator = None
        self.conformal_predictor = None
        
    def fit(self, y_true: np.ndarray, y_pred: np.ndarray, X: pd.DataFrame, base_model=None):
        """Fit ensemble of uncertainty estimators."""
        logger.info("Fitting aggressive ensemble CI estimator...")
        
        # 1. Bootstrap ensemble
        self._fit_bootstrap_ensemble(X, y_true, base_model)
        
        # 2. Quantile estimator
        self.quantile_estimator = BalancedConfidenceEstimator(coverage=self.coverage)
        self.quantile_estimator.fit(y_true, y_pred, X)
        
        # 3. Conformal prediction
        self._fit_conformal_predictor(X, y_true, y_pred)
        
        # 4. MC Dropout approximation (if base model supports it)
        if base_model is not None and hasattr(base_model, 'predict'):
            self.dropout_model = self._create_dropout_wrapper(base_model)
        
        logger.info(f"Fitted ensemble with {len(self.bootstrap_models)} bootstrap models")
    
    def _fit_bootstrap_ensemble(self, X: pd.DataFrame, y: np.ndarray, base_model=None):
        """Fit bootstrap ensemble for uncertainty estimation."""
        n_samples = len(X)
        
        for i in range(self.n_bootstrap):
            # Bootstrap sample
            indices = np.random.choice(n_samples, n_samples, replace=True)
            X_boot = X.iloc[indices]
            y_boot = y[indices]
            
            # Fit model
            if base_model is not None:
                model = lgb.LGBMRegressor(**base_model.get_params())
            else:
                model = lgb.LGBMRegressor(n_estimators=50, random_state=42 + i, verbosity=-1)
            
            model.fit(X_boot, y_boot)
            self.bootstrap_models.append(model)
    
    def _fit_conformal_predictor(self, X: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray):
        """Fit conformal prediction for distribution-free intervals."""
        # Calculate conformity scores
        residuals = np.abs(y_true - y_pred)
        
        # Store conformity scores for calibration
        self.conformity_scores = residuals
        self.conformal_quantile = np.percentile(residuals, self.coverage * 100)
        
        logger.info(f"Conformal prediction quantile: {self.conformal_quantile:.2f}")
    
    def _create_dropout_wrapper(self, base_model):
        """Create MC Dropout wrapper for uncertainty estimation."""
        # This is a placeholder - actual implementation would depend on model type
        return base_model
    
    def estimate_intervals(self, X: pd.DataFrame, predictions: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate intervals using ensemble of methods."""
        intervals = []
        
        # 1. Bootstrap intervals
        if self.bootstrap_models:
            boot_intervals = self._get_bootstrap_intervals(X)
            intervals.append(boot_intervals)
        
        # 2. Quantile regression intervals
        if self.quantile_estimator is not None:
            quant_intervals = self.quantile_estimator.estimate_intervals(X, predictions)
            intervals.append(quant_intervals)
        
        # 3. Conformal intervals
        if hasattr(self, 'conformal_quantile'):
            conf_intervals = self._get_conformal_intervals(predictions)
            intervals.append(conf_intervals)
        
        # Aggregate intervals (weighted average)
        weights = [0.4, 0.4, 0.2]  # Bootstrap, quantile, conformal
        
        lower_bounds = np.zeros_like(predictions)
        upper_bounds = np.zeros_like(predictions)
        
        for i, (lower, upper) in enumerate(intervals):
            if i < len(weights):
                lower_bounds += weights[i] * lower
                upper_bounds += weights[i] * upper
        
        # Normalize weights
        total_weight = sum(weights[:len(intervals)])
        lower_bounds /= total_weight
        upper_bounds /= total_weight
        
        return lower_bounds, upper_bounds
    
    def _get_bootstrap_intervals(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Get prediction intervals from bootstrap ensemble."""
        # Get predictions from all bootstrap models
        bootstrap_preds = np.array([model.predict(X) for model in self.bootstrap_models])
        
        # Calculate percentiles
        lower = np.percentile(bootstrap_preds, (self.alpha / 2) * 100, axis=0)
        upper = np.percentile(bootstrap_preds, (1 - self.alpha / 2) * 100, axis=0)
        
        return lower, upper
    
    def _get_conformal_intervals(self, predictions: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Get conformal prediction intervals."""
        # Simple symmetric intervals
        lower = predictions - self.conformal_quantile
        upper = predictions + self.conformal_quantile
        
        return lower, upper
    
    def get_uncertainty_decomposition(self, X: pd.DataFrame, predictions: np.ndarray) -> Dict[str, np.ndarray]:
        """Decompose uncertainty into aleatoric and epistemic components."""
        uncertainties = {}
        
        if self.bootstrap_models:
            # Epistemic uncertainty (model uncertainty)
            bootstrap_preds = np.array([model.predict(X) for model in self.bootstrap_models])
            epistemic = np.std(bootstrap_preds, axis=0)
            uncertainties['epistemic'] = epistemic
            
            # Aleatoric uncertainty (data uncertainty)
            # Estimated from average prediction variance
            aleatoric = np.mean([np.abs(pred - predictions) for pred in bootstrap_preds], axis=0)
            uncertainties['aleatoric'] = aleatoric
            
            # Total uncertainty
            uncertainties['total'] = np.sqrt(epistemic**2 + aleatoric**2)
        
        return uncertainties
    
    def plot_coverage_analysis(self, y_true: np.ndarray, y_pred: np.ndarray, 
                             X: pd.DataFrame, save_path: Optional[str] = None):
        """Plot coverage analysis for confidence intervals."""
        import matplotlib.pyplot as plt
        
        lower, upper = self.estimate_intervals(X, y_pred)
        
        # Calculate coverage
        in_interval = (y_true >= lower) & (y_true <= upper)
        coverage = np.mean(in_interval)
        
        # Create subplots
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # 1. Prediction intervals
        ax = axes[0, 0]
        sorted_idx = np.argsort(y_pred)
        ax.scatter(range(len(y_pred)), y_pred[sorted_idx], alpha=0.6, label='Predictions')
        ax.fill_between(range(len(y_pred)), lower[sorted_idx], upper[sorted_idx], 
                       alpha=0.3, label=f'{self.coverage*100:.0f}% CI')
        ax.scatter(range(len(y_true)), y_true[sorted_idx], alpha=0.4, color='red', 
                  s=10, label='Actual')
        ax.set_title(f'Prediction Intervals (Coverage: {coverage:.3f})')
        ax.set_xlabel('Sample (sorted by prediction)')
        ax.set_ylabel('Value')
        ax.legend()
        
        # 2. Interval width vs prediction
        ax = axes[0, 1]
        interval_width = upper - lower
        ax.scatter(y_pred, interval_width, alpha=0.5)
        ax.set_xlabel('Prediction')
        ax.set_ylabel('Interval Width')
        ax.set_title('Interval Width vs Prediction')
        
        # 3. Coverage by prediction magnitude
        ax = axes[1, 0]
        bins = np.percentile(y_pred, [0, 25, 50, 75, 100])
        bin_coverage = []
        bin_centers = []
        
        for i in range(len(bins) - 1):
            mask = (y_pred >= bins[i]) & (y_pred < bins[i + 1])
            if mask.sum() > 0:
                bin_coverage.append(np.mean(in_interval[mask]))
                bin_centers.append((bins[i] + bins[i + 1]) / 2)
        
        ax.bar(range(len(bin_coverage)), bin_coverage)
        ax.axhline(y=self.coverage, color='r', linestyle='--', label='Target Coverage')
        ax.set_xticks(range(len(bin_coverage)))
        ax.set_xticklabels([f'Q{i+1}' for i in range(len(bin_coverage))])
        ax.set_ylabel('Coverage')
        ax.set_title('Coverage by Prediction Quartile')
        ax.legend()
        
        # 4. Calibration plot
        ax = axes[1, 1]
        expected_coverage = np.linspace(0.1, 0.99, 20)
        actual_coverage = []
        
        for ec in expected_coverage:
            alpha = 1 - ec
            lower_q = np.percentile(self.conformity_scores, alpha / 2 * 100)
            upper_q = np.percentile(self.conformity_scores, (1 - alpha / 2) * 100)
            
            lower_c = y_pred - upper_q
            upper_c = y_pred + upper_q
            
            actual_coverage.append(np.mean((y_true >= lower_c) & (y_true <= upper_c)))
        
        ax.plot(expected_coverage, actual_coverage, 'b-', label='Actual')
        ax.plot([0, 1], [0, 1], 'r--', label='Perfect Calibration')
        ax.set_xlabel('Expected Coverage')
        ax.set_ylabel('Actual Coverage')
        ax.set_title('Calibration Plot')
        ax.legend()
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"Coverage analysis plot saved to {save_path}")
        
        plt.close()
        
        return {
            'coverage': coverage,
            'mean_interval_width': np.mean(interval_width),
            'std_interval_width': np.std(interval_width)
        }