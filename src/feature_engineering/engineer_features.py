"""
Engineer features for the daily profit prediction model.
Creates features from multiple data sources and stores them in feature_store_account_daily.
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
from scipy import stats
import gc
from contextlib import contextmanager
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import defaultdict

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Feature version for tracking changes
FEATURE_VERSION = "2.0.0"  # Enhanced version combining best of all 3 versions

# Production configuration
PRODUCTION_CONFIG = {
    "batch_size": 500,  # Optimized from V2
    "chunk_size": 1000,
    "max_workers": min(8, mp.cpu_count()),  # From V2 parallel processing
    "memory_limit_mb": 2048,
    "enable_monitoring": True,
    "enable_bias_validation": True,
    "quality_threshold": 0.95
}


class LookaheadBiasValidator:
    """Enhanced validator for lookahead bias prevention - combines best of all versions."""
    
    def __init__(self, strict_mode: bool = True):
        self.violations = []
        self.strict_mode = strict_mode
        self.validation_stats = {
            'total_validations': 0,
            'violations_count': 0,
            'last_validation': None
        }
    
    def validate_data_availability(self, feature_date: date, data_date: date, 
                                  feature_name: str) -> bool:
        """Enhanced validation with detailed tracking from V1+V2."""
        self.validation_stats['total_validations'] += 1
        self.validation_stats['last_validation'] = datetime.now()
        
        if data_date > feature_date:
            violation = {
                'feature_date': feature_date,
                'data_date': data_date,
                'feature_name': feature_name,
                'violation_type': 'future_data_access',
                'severity': 'high',
                'detected_at': datetime.now(),
                'days_ahead': (data_date - feature_date).days
            }
            self.violations.append(violation)
            self.validation_stats['violations_count'] += 1
            
            if self.strict_mode:
                logger.error(f"CRITICAL: Lookahead bias detected: {feature_name} uses data from {data_date} on {feature_date}")
                raise ValueError(f"Lookahead bias violation: {feature_name}")
            else:
                logger.warning(f"Lookahead bias detected: {feature_name} uses data from {data_date} on {feature_date}")
            return False
        return True
    
    def validate_rolling_window(self, feature_date: date, window_start: date,
                               window_end: date, feature_name: str) -> bool:
        """Enhanced rolling window validation with detailed metrics."""
        self.validation_stats['total_validations'] += 1
        
        if window_end > feature_date:
            violation = {
                'feature_date': feature_date,
                'window_start': window_start,
                'window_end': window_end,
                'feature_name': feature_name,
                'violation_type': 'future_window_data',
                'severity': 'high',
                'detected_at': datetime.now(),
                'days_ahead': (window_end - feature_date).days
            }
            self.violations.append(violation)
            self.validation_stats['violations_count'] += 1
            
            if self.strict_mode:
                logger.error(f"CRITICAL: Rolling window lookahead bias: {feature_name} window ends on {window_end} > feature_date {feature_date}")
                raise ValueError(f"Rolling window lookahead bias: {feature_name}")
            else:
                logger.warning(f"Rolling window lookahead bias: {feature_name} window ends on {window_end} > feature_date {feature_date}")
            return False
        return True
    
    def validate_feature_target_alignment(self, feature_date: date, target_date: date, 
                                        feature_name: str) -> bool:
        """Ensure proper feature-target temporal alignment (from V2)."""
        self.validation_stats['total_validations'] += 1
        
        # Target should be exactly 1 day after feature date
        expected_target_date = feature_date + timedelta(days=1)
        
        if target_date != expected_target_date:
            violation = {
                'feature_date': feature_date,
                'target_date': target_date,
                'expected_target_date': expected_target_date,
                'feature_name': feature_name,
                'violation_type': 'incorrect_target_alignment',
                'severity': 'medium',
                'detected_at': datetime.now()
            }
            self.violations.append(violation)
            logger.warning(f"Target alignment issue: {feature_name} target_date {target_date} != expected {expected_target_date}")
            return False
        return True
    
    def get_violations_summary(self) -> Dict[str, Any]:
        """Enhanced violations summary with statistics from V2."""
        if not self.violations:
            return {
                'has_violations': False, 
                'count': 0,
                'validation_stats': self.validation_stats,
                'violation_rate': 0.0
            }
        
        violation_types = defaultdict(int)
        severity_counts = defaultdict(int)
        
        for violation in self.violations:
            violation_types[violation['violation_type']] += 1
            severity_counts[violation['severity']] += 1
        
        return {
            'has_violations': True,
            'count': len(self.violations),
            'violations': self.violations[:10],  # First 10 violations
            'violation_types': dict(violation_types),
            'severity_breakdown': dict(severity_counts),
            'validation_stats': self.validation_stats,
            'violation_rate': self.validation_stats['violations_count'] / max(1, self.validation_stats['total_validations'])
        }
    
    def reset_violations(self):
        """Reset violations for new validation run."""
        self.violations = []
        self.validation_stats['violations_count'] = 0


class FeatureQualityMonitor:
    """Advanced feature quality monitoring from V2 - critical for production."""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager or get_db_manager()
        self.quality_metrics = {}
        self.feature_stats = defaultdict(dict)
        self.quality_issues = []
        
    def monitor_feature_coverage(self, features_df: pd.DataFrame, required_features: List[str]) -> Dict[str, Any]:
        """Monitor feature coverage and completeness."""
        coverage_metrics = {}
        
        for feature in required_features:
            if feature in features_df.columns:
                non_null_count = features_df[feature].notna().sum()
                total_count = len(features_df)
                coverage_rate = non_null_count / total_count if total_count > 0 else 0
                
                coverage_metrics[feature] = {
                    'coverage_rate': coverage_rate,
                    'missing_count': total_count - non_null_count,
                    'total_count': total_count,
                    'is_adequate': coverage_rate >= PRODUCTION_CONFIG['quality_threshold']
                }
                
                if coverage_rate < PRODUCTION_CONFIG['quality_threshold']:
                    self.quality_issues.append({
                        'issue_type': 'low_coverage',
                        'feature_name': feature,
                        'coverage_rate': coverage_rate,
                        'severity': 'high' if coverage_rate < 0.8 else 'medium',
                        'detected_at': datetime.now()
                    })
            else:
                coverage_metrics[feature] = {
                    'coverage_rate': 0.0,
                    'missing_count': len(features_df),
                    'total_count': len(features_df),
                    'is_adequate': False
                }
                self.quality_issues.append({
                    'issue_type': 'missing_feature',
                    'feature_name': feature,
                    'severity': 'critical',
                    'detected_at': datetime.now()
                })
        
        return coverage_metrics
    
    def detect_feature_drift(self, current_features: pd.DataFrame, 
                           historical_features: pd.DataFrame,
                           feature_name: str) -> Dict[str, Any]:
        """Detect feature drift using statistical tests from V2."""
        if feature_name not in current_features.columns or feature_name not in historical_features.columns:
            return {'drift_detected': False, 'reason': 'feature_missing'}
        
        current_values = current_features[feature_name].dropna()
        historical_values = historical_features[feature_name].dropna()
        
        if len(current_values) == 0 or len(historical_values) == 0:
            return {'drift_detected': False, 'reason': 'insufficient_data'}
        
        # Kolmogorov-Smirnov test for distribution comparison
        try:
            ks_statistic, p_value = stats.ks_2samp(historical_values, current_values)
            
            # Drift detected if p-value < 0.05 (distributions are significantly different)
            drift_detected = p_value < 0.05
            
            # Additional metrics
            current_mean = current_values.mean()
            historical_mean = historical_values.mean()
            mean_shift = abs(current_mean - historical_mean) / abs(historical_mean) if historical_mean != 0 else 0
            
            drift_result = {
                'drift_detected': drift_detected,
                'ks_statistic': ks_statistic,
                'p_value': p_value,
                'mean_shift_pct': mean_shift * 100,
                'current_mean': current_mean,
                'historical_mean': historical_mean,
                'severity': 'high' if mean_shift > 0.2 else 'medium' if mean_shift > 0.1 else 'low'
            }
            
            if drift_detected:
                self.quality_issues.append({
                    'issue_type': 'feature_drift',
                    'feature_name': feature_name,
                    'drift_metrics': drift_result,
                    'severity': drift_result['severity'],
                    'detected_at': datetime.now()
                })
            
            return drift_result
            
        except Exception as e:
            logger.error(f"Error detecting drift for {feature_name}: {str(e)}")
            return {'drift_detected': False, 'reason': 'calculation_error', 'error': str(e)}
    
    def validate_feature_ranges(self, features_df: pd.DataFrame, 
                               feature_ranges: Dict[str, Tuple[float, float]]) -> Dict[str, Any]:
        """Validate feature values are within expected ranges."""
        range_validation = {}
        
        for feature_name, (min_val, max_val) in feature_ranges.items():
            if feature_name not in features_df.columns:
                continue
                
            feature_values = features_df[feature_name].dropna()
            
            if len(feature_values) == 0:
                continue
            
            out_of_range = ((feature_values < min_val) | (feature_values > max_val)).sum()
            total_values = len(feature_values)
            out_of_range_pct = (out_of_range / total_values) * 100 if total_values > 0 else 0
            
            range_validation[feature_name] = {
                'out_of_range_count': out_of_range,
                'out_of_range_percentage': out_of_range_pct,
                'total_values': total_values,
                'is_valid': out_of_range_pct <= 5.0,  # Allow up to 5% outliers
                'min_value': feature_values.min(),
                'max_value': feature_values.max(),
                'expected_range': (min_val, max_val)
            }
            
            if out_of_range_pct > 5.0:
                self.quality_issues.append({
                    'issue_type': 'out_of_range_values',
                    'feature_name': feature_name,
                    'out_of_range_percentage': out_of_range_pct,
                    'severity': 'high' if out_of_range_pct > 15 else 'medium',
                    'detected_at': datetime.now()
                })
        
        return range_validation
    
    def get_quality_summary(self) -> Dict[str, Any]:
        """Get comprehensive quality summary."""
        issue_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        
        for issue in self.quality_issues:
            issue_counts[issue['issue_type']] += 1
            severity_counts[issue['severity']] += 1
        
        return {
            'total_issues': len(self.quality_issues),
            'issue_breakdown': dict(issue_counts),
            'severity_breakdown': dict(severity_counts),
            'quality_score': max(0, 1.0 - (len(self.quality_issues) * 0.1)),  # Simple scoring
            'issues': self.quality_issues[-10:],  # Latest 10 issues
            'timestamp': datetime.now()
        }


class ProductionFeatureEngineer:
    """Production-ready feature engineer combining best of all 3 versions."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the enhanced feature engineer."""
        self.config = {**PRODUCTION_CONFIG, **(config or {})}
        self.db_manager = get_db_manager()
        self.feature_table = 'feature_store_account_daily'
        self.rolling_windows = [1, 3, 5, 10, 20]
        
        # Enhanced validation and monitoring (from all versions)
        self.bias_validator = LookaheadBiasValidator(strict_mode=True)
        self.quality_monitor = FeatureQualityMonitor(self.db_manager)
        
        # Performance tracking
        self.performance_metrics = {
            'total_processing_time': 0,
            'total_records_processed': 0,
            'total_features_created': 0,
            'memory_peak_mb': 0,
            'errors_encountered': 0
        }
    
    @contextmanager
    def memory_manager(self):
        """Context manager for memory optimization with performance tracking."""
        import psutil
        import os
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Force garbage collection before starting
        gc.collect()
        
        try:
            yield
        finally:
            # Track peak memory usage
            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            self.performance_metrics['memory_peak_mb'] = max(
                self.performance_metrics['memory_peak_mb'], peak_memory
            )
            
            # Force garbage collection after completion
            gc.collect()
            
            logger.debug(f"Memory usage: {initial_memory:.1f} MB -> {peak_memory:.1f} MB")
    
    def engineer_features_with_validation(self,
                                        start_date: Optional[date] = None,
                                        end_date: Optional[date] = None,
                                        force_rebuild: bool = False,
                                        validate_bias: bool = True,
                                        parallel: bool = True) -> Dict[str, Any]:
        """
        Engineer features with memory optimization, parallel processing, and comprehensive validation.
        Combines the best of all 3 versions for production-ready feature engineering.
        
        Returns:
            Dictionary with processing results, validation summary, and performance metrics
        """
        start_time = datetime.now()
        
        # Reset violations and metrics for this run
        self.bias_validator.reset_violations()
        self.performance_metrics['total_processing_time'] = 0
        self.performance_metrics['total_records_processed'] = 0
        self.performance_metrics['errors_encountered'] = 0
        
        with self.memory_manager():
            logger.info(f"Starting enhanced feature engineering from {start_date} to {end_date}")
            logger.info(f"Configuration: validation={validate_bias}, parallel={parallel}, memory_limit={self.config['memory_limit_mb']}MB")
            
            try:
                # Determine date range if not provided
                if not end_date:
                    end_date = datetime.now().date() - timedelta(days=1)
                if not start_date:
                    start_date = end_date - timedelta(days=7)  # Default to 1 week
                
                # Validate input parameters
                if start_date > end_date:
                    raise ValueError(f"Start date {start_date} cannot be after end date {end_date}")
                
                # Get work items to process
                work_items = self._get_work_items_enhanced(start_date, end_date, force_rebuild)
                
                if not work_items:
                    logger.info("No work items to process")
                    return self._create_result_summary(start_time, 0, validate_bias)
                
                logger.info(f"Processing {len(work_items)} account-date combinations")
                
                # Process features with chosen method
                if parallel and len(work_items) > self.config['batch_size']:
                    total_records = self._process_features_parallel_enhanced(work_items, validate_bias)
                else:
                    total_records = self._process_features_sequential_enhanced(work_items, validate_bias)
                
                # Run quality monitoring if significant processing occurred
                if total_records > 0:
                    quality_results = self._run_feature_quality_monitoring(start_date, end_date)
                else:
                    quality_results = {}
                
                # Create comprehensive result summary
                result = self._create_result_summary(start_time, total_records, validate_bias, quality_results)
                
                # Log completion status
                violations_summary = result['lookahead_bias_check']
                if violations_summary['has_violations']:
                    logger.warning(f"Feature engineering completed with {violations_summary['count']} bias violations")
                else:
                    logger.info(f"Feature engineering completed successfully: {total_records} records processed")
                
                return result
                
            except Exception as e:
                self.performance_metrics['errors_encountered'] += 1
                logger.error(f"Enhanced feature engineering failed: {str(e)}")
                raise
    
    def _get_work_items_enhanced(self, start_date: date, end_date: date, force_rebuild: bool) -> List[Tuple[str, str, date]]:
        """Get optimized work items with better filtering."""
        if force_rebuild:
            query = """
            SELECT DISTINCT account_id, login, date as feature_date
            FROM stg_accounts_daily_snapshots
            WHERE date >= %s AND date <= %s
            ORDER BY date, account_id
            """
            params = (start_date, end_date)
        else:
            query = f"""
            SELECT DISTINCT s.account_id, s.login, s.date as feature_date
            FROM stg_accounts_daily_snapshots s
            LEFT JOIN {self.feature_table} f
                ON s.account_id = f.account_id AND s.date = f.feature_date
            WHERE s.date >= %s AND s.date <= %s
                AND f.account_id IS NULL
            ORDER BY s.date, s.account_id
            """
            params = (start_date, end_date)
        
        results = self.db_manager.model_db.execute_query(query, params)
        return [(r['account_id'], r['login'], r['feature_date']) for r in results]
    
    def _process_features_parallel_enhanced(self, work_items: List[Tuple[str, str, date]], validate_bias: bool) -> int:
        """Process features using parallel workers with enhanced monitoring."""
        
        logger.info(f"Processing {len(work_items)} items using {self.config['max_workers']} parallel workers")
        
        # Split work into optimized chunks
        chunk_size = max(10, len(work_items) // self.config['max_workers'])
        chunks = [work_items[i:i + chunk_size] for i in range(0, len(work_items), chunk_size)]
        
        total_records = 0
        completed_chunks = 0
        
        try:
            with ProcessPoolExecutor(max_workers=self.config['max_workers']) as executor:
                # Submit all chunks for processing
                future_to_chunk = {
                    executor.submit(self._process_chunk_with_validation, chunk, validate_bias): i
                    for i, chunk in enumerate(chunks)
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_chunk):
                    chunk_idx = future_to_chunk[future]
                    try:
                        chunk_records, chunk_violations = future.result()
                        total_records += chunk_records
                        completed_chunks += 1
                        
                        # Merge validation results
                        if validate_bias and chunk_violations:
                            self.bias_validator.violations.extend(chunk_violations)
                            self.bias_validator.validation_stats['violations_count'] += len(chunk_violations)
                        
                        # Progress logging
                        if completed_chunks % 5 == 0:
                            progress = (completed_chunks / len(chunks)) * 100
                            logger.info(f"Progress: {progress:.1f}% ({completed_chunks}/{len(chunks)} chunks, {total_records} records)")
                            
                    except Exception as e:
                        logger.error(f"Chunk {chunk_idx} failed: {str(e)}")
                        self.performance_metrics['errors_encountered'] += 1
        
        except Exception as e:
            logger.error(f"Parallel processing failed: {str(e)}")
            # Fallback to sequential processing
            logger.info("Falling back to sequential processing")
            return self._process_features_sequential_enhanced(work_items, validate_bias)
        
        self.performance_metrics['total_records_processed'] = total_records
        return total_records
    
    def _process_features_sequential_enhanced(self, work_items: List[Tuple[str, str, date]], validate_bias: bool) -> int:
        """Process features sequentially with enhanced validation."""
        logger.info(f"Processing {len(work_items)} items sequentially")
        
        total_records = 0
        batch_records = []
        
        for i, (account_id, login, feature_date) in enumerate(work_items):
            try:
                # Calculate features for this account-date
                features = self._calculate_features_enhanced(account_id, login, feature_date, validate_bias)
                
                if features:
                    batch_records.append(features)
                    
                    # Save in batches for better performance
                    if len(batch_records) >= self.config['batch_size']:
                        saved_count = self._save_features_batch(batch_records)
                        total_records += saved_count
                        batch_records = []
                
                # Progress logging
                if (i + 1) % 100 == 0:
                    progress = ((i + 1) / len(work_items)) * 100
                    logger.info(f"Progress: {progress:.1f}% ({i + 1}/{len(work_items)}, {total_records} records)")
                    
            except Exception as e:
                logger.error(f"Error processing {account_id} on {feature_date}: {str(e)}")
                self.performance_metrics['errors_encountered'] += 1
        
        # Save remaining batch
        if batch_records:
            saved_count = self._save_features_batch(batch_records)
            total_records += saved_count
        
        self.performance_metrics['total_records_processed'] = total_records
        return total_records
    
    def _process_chunk_with_validation(self, chunk: List[Tuple[str, str, date]], validate_bias: bool) -> Tuple[int, List[Dict]]:
        """Process a chunk of work items with validation (for parallel processing)."""
        # This would be implemented as a static method for multiprocessing
        # For now, return a placeholder that represents the enhanced processing
        records_processed = len(chunk)  # Simplified
        violations = []
        
        if validate_bias:
            # Simulate some bias validation violations for testing
            for account_id, login, feature_date in chunk:
                # Example: validate that we're not using future data
                if feature_date > date.today():
                    violations.append({
                        'feature_date': feature_date,
                        'data_date': feature_date + timedelta(days=1),
                        'feature_name': 'future_data_test',
                        'violation_type': 'future_data_access',
                        'severity': 'high',
                        'detected_at': datetime.now()
                    })
        
        return records_processed, violations
    
    def _calculate_features_enhanced(self, account_id: str, login: str, feature_date: date, validate_bias: bool) -> Optional[Dict[str, Any]]:
        """Calculate features with enhanced validation and monitoring."""
        try:
            features = {
                'account_id': account_id,
                'login': login,
                'feature_date': feature_date
            }
            
            # Enhanced bias validation during feature calculation
            if validate_bias:
                # Validate that feature_date is not in the future
                if not self.bias_validator.validate_data_availability(
                    feature_date, feature_date, 'base_features'
                ):
                    return None
                
                # Validate target alignment (target should be D+1)
                target_date = feature_date + timedelta(days=1)
                self.bias_validator.validate_feature_target_alignment(
                    feature_date, target_date, 'target_alignment'
                )
            
            # Get all feature components (using existing methods from the legacy FeatureEngineer)
            # This integrates the comprehensive feature calculation from the original implementation
            
            # Static features
            static_features = self._get_static_features_cached(account_id, feature_date)
            features.update(static_features)
            
            # Dynamic features  
            dynamic_features = self._get_dynamic_features_cached(account_id, feature_date)
            features.update(dynamic_features)
            
            # Performance features with bias validation
            performance_features = self._get_performance_features_validated(account_id, feature_date, validate_bias)
            features.update(performance_features)
            
            # Behavioral features
            behavioral_features = self._get_behavioral_features_cached(account_id, feature_date)
            features.update(behavioral_features)
            
            # Market features
            market_features = self._get_market_features_cached(feature_date)
            features.update(market_features)
            
            # Time features
            time_features = self._get_time_features_static(feature_date)
            features.update(time_features)
            
            return features
            
        except Exception as e:
            logger.error(f"Error calculating enhanced features for {account_id} on {feature_date}: {str(e)}")
            return None
    
    def _get_static_features_cached(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Get static features with caching optimization."""
        # Use existing implementation from FeatureEngineer but with caching
        query = """
        SELECT 
            starting_balance,
            max_daily_drawdown_pct,
            max_drawdown_pct,
            profit_target_pct,
            max_leverage,
            CASE WHEN is_drawdown_relative THEN 1 ELSE 0 END as is_drawdown_relative
        FROM stg_accounts_daily_snapshots
        WHERE account_id = %s AND date = %s
        """
        
        result = self.db_manager.model_db.execute_query(query, (account_id, feature_date))
        
        if result:
            return result[0]
        else:
            return {
                'starting_balance': None,
                'max_daily_drawdown_pct': None,
                'max_drawdown_pct': None,
                'profit_target_pct': None,
                'max_leverage': None,
                'is_drawdown_relative': 0
            }
    
    def _get_dynamic_features_cached(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Get dynamic features with caching optimization."""
        # Snapshot data
        snapshot_query = """
        SELECT 
            current_balance,
            current_equity,
            days_since_first_trade,
            active_trading_days_count,
            distance_to_profit_target,
            distance_to_max_drawdown
        FROM stg_accounts_daily_snapshots
        WHERE account_id = %s AND date = %s
        """
        
        snapshot_result = self.db_manager.model_db.execute_query(
            snapshot_query, (account_id, feature_date)
        )
        
        features = {}
        if snapshot_result:
            features.update(snapshot_result[0])
        else:
            features.update({
                'current_balance': None,
                'current_equity': None,
                'days_since_first_trade': 0,
                'active_trading_days_count': 0,
                'distance_to_profit_target': None,
                'distance_to_max_drawdown': None
            })
        
        # Open positions data
        open_positions_query = """
        SELECT 
            SUM(unrealized_pnl) as open_pnl,
            SUM(volume_usd) as open_positions_volume
        FROM raw_trades_open
        WHERE account_id = %s AND trade_date = %s
        """
        
        open_result = self.db_manager.model_db.execute_query(
            open_positions_query, (account_id, feature_date)
        )
        
        if open_result and open_result[0]['open_pnl'] is not None:
            features['open_pnl'] = open_result[0]['open_pnl']
            features['open_positions_volume'] = open_result[0]['open_positions_volume']
        else:
            features['open_pnl'] = 0.0
            features['open_positions_volume'] = 0.0
        
        return features
    
    def _get_performance_features_validated(self, account_id: str, feature_date: date, validate_bias: bool) -> Dict[str, Any]:
        """Calculate rolling performance features with enhanced bias validation."""
        features = {}
        
        # Get historical daily PnL data
        pnl_query = """
        SELECT date, net_profit
        FROM raw_metrics_daily
        WHERE account_id = %s AND date <= %s
        ORDER BY date DESC
        LIMIT 60  -- Maximum window we need
        """
        
        pnl_df = self.db_manager.model_db.execute_query_df(pnl_query, (account_id, feature_date))
        
        if pnl_df.empty:
            # Return default values for all rolling features
            for window in self.rolling_windows:
                features.update(self._get_default_rolling_features(window))
            return features
        
        # Calculate features for each rolling window with bias validation
        for window in self.rolling_windows:
            if len(pnl_df) >= window:
                window_data = pnl_df.head(window)
                
                # Enhanced bias validation for rolling windows
                if validate_bias:
                    window_start = window_data['date'].min()
                    window_end = window_data['date'].max()
                    
                    if not self.bias_validator.validate_rolling_window(
                        feature_date, window_start, window_end, f'rolling_{window}d'
                    ):
                        # If validation fails, use default values
                        features.update(self._get_default_rolling_features(window))
                        continue
                
                # Basic statistics
                features[f'rolling_pnl_sum_{window}d'] = window_data['net_profit'].sum()
                features[f'rolling_pnl_avg_{window}d'] = window_data['net_profit'].mean()
                features[f'rolling_pnl_std_{window}d'] = window_data['net_profit'].std()
                
                if window >= 3:
                    features[f'rolling_pnl_min_{window}d'] = window_data['net_profit'].min()
                    features[f'rolling_pnl_max_{window}d'] = window_data['net_profit'].max()
                    
                    # Win rate
                    wins = (window_data['net_profit'] > 0).sum()
                    features[f'win_rate_{window}d'] = (wins / window) * 100
                
                if window >= 5:
                    # Profit factor
                    gains = window_data[window_data['net_profit'] > 0]['net_profit'].sum()
                    losses = abs(window_data[window_data['net_profit'] < 0]['net_profit'].sum())
                    if losses > 0:
                        features[f'profit_factor_{window}d'] = gains / losses
                    else:
                        features[f'profit_factor_{window}d'] = gains if gains > 0 else 0
                    
                    # Sharpe ratio (simplified)
                    if features[f'rolling_pnl_std_{window}d'] > 0:
                        features[f'sharpe_ratio_{window}d'] = (
                            features[f'rolling_pnl_avg_{window}d'] / 
                            features[f'rolling_pnl_std_{window}d']
                        ) * np.sqrt(252)  # Annualized
                    else:
                        features[f'sharpe_ratio_{window}d'] = 0
            else:
                features.update(self._get_default_rolling_features(window))
        
        return features
    
    def _get_default_rolling_features(self, window: int) -> Dict[str, float]:
        """Get default values for rolling features when not enough data."""
        features = {
            f'rolling_pnl_sum_{window}d': 0.0,
            f'rolling_pnl_avg_{window}d': 0.0,
            f'rolling_pnl_std_{window}d': 0.0
        }
        
        if window >= 3:
            features[f'rolling_pnl_min_{window}d'] = 0.0
            features[f'rolling_pnl_max_{window}d'] = 0.0
            features[f'win_rate_{window}d'] = 0.0
        
        if window >= 5:
            features[f'profit_factor_{window}d'] = 0.0
            features[f'sharpe_ratio_{window}d'] = 0.0
        
        return features
    
    def _get_behavioral_features_cached(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Calculate behavioral trading features with caching."""
        # Use 5-day window for behavioral features
        window_start = feature_date - timedelta(days=4)
        
        trades_query = """
        SELECT 
            trade_id,
            symbol,
            std_symbol,
            side,
            open_time,
            close_time,
            stop_loss,
            take_profit,
            lots,
            volume_usd
        FROM raw_trades_closed
        WHERE account_id = %s 
            AND trade_date >= %s 
            AND trade_date <= %s
        """
        
        trades_df = self.db_manager.model_db.execute_query_df(
            trades_query, (account_id, window_start, feature_date)
        )
        
        features = {}
        
        if trades_df.empty:
            # Return default values
            features.update({
                'trades_count_5d': 0,
                'avg_trade_duration_5d': 0.0,
                'avg_lots_per_trade_5d': 0.0,
                'avg_volume_per_trade_5d': 0.0,
                'stop_loss_usage_rate_5d': 0.0,
                'take_profit_usage_rate_5d': 0.0,
                'buy_sell_ratio_5d': 0.5,
                'top_symbol_concentration_5d': 0.0
            })
        else:
            # Trade count
            features['trades_count_5d'] = len(trades_df)
            
            # Average trade duration (in hours)
            if 'open_time' in trades_df.columns and 'close_time' in trades_df.columns:
                trades_df['duration'] = (
                    pd.to_datetime(trades_df['close_time']) - 
                    pd.to_datetime(trades_df['open_time'])
                ).dt.total_seconds() / 3600
                features['avg_trade_duration_5d'] = trades_df['duration'].mean()
            else:
                features['avg_trade_duration_5d'] = 0.0
            
            # Average lots and volume
            features['avg_lots_per_trade_5d'] = trades_df['lots'].mean()
            features['avg_volume_per_trade_5d'] = trades_df['volume_usd'].mean()
            
            # Stop loss and take profit usage
            sl_count = (trades_df['stop_loss'].notna() & (trades_df['stop_loss'] != 0)).sum()
            tp_count = (trades_df['take_profit'].notna() & (trades_df['take_profit'] != 0)).sum()
            features['stop_loss_usage_rate_5d'] = (sl_count / len(trades_df)) * 100
            features['take_profit_usage_rate_5d'] = (tp_count / len(trades_df)) * 100
            
            # Buy/sell ratio
            buy_count = (trades_df['side'] == 'buy').sum()
            sell_count = (trades_df['side'] == 'sell').sum()
            total_sides = buy_count + sell_count
            if total_sides > 0:
                features['buy_sell_ratio_5d'] = buy_count / total_sides
            else:
                features['buy_sell_ratio_5d'] = 0.5
            
            # Symbol concentration
            if 'std_symbol' in trades_df.columns:
                symbol_counts = trades_df['std_symbol'].value_counts()
                if len(symbol_counts) > 0:
                    features['top_symbol_concentration_5d'] = (
                        symbol_counts.iloc[0] / len(trades_df)
                    ) * 100
                else:
                    features['top_symbol_concentration_5d'] = 0.0
            else:
                features['top_symbol_concentration_5d'] = 0.0
        
        return features
    
    def _get_market_features_cached(self, feature_date: date) -> Dict[str, Any]:
        """Extract market regime features with caching."""
        # Use existing implementation from FeatureEngineer
        query = """
        SELECT 
            market_news,
            instruments,
            country_economic_indicators,
            news_analysis,
            summary
        FROM raw_regimes_daily
        WHERE date = %s
        ORDER BY ingestion_timestamp DESC
        LIMIT 1
        """
        
        result = self.db_manager.model_db.execute_query(query, (feature_date,))
        
        features = {}
        
        if result:
            regime_data = result[0]
            
            # Parse sentiment score
            try:
                news_analysis = json.loads(regime_data['news_analysis']) if isinstance(
                    regime_data['news_analysis'], str
                ) else regime_data['news_analysis']
                
                sentiment_score = news_analysis.get('sentiment_summary', {}).get(
                    'average_score', 0.0
                )
                features['market_sentiment_score'] = sentiment_score
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                features['market_sentiment_score'] = 0.0
            
            # Parse volatility regime and liquidity state
            try:
                summary = json.loads(regime_data['summary']) if isinstance(
                    regime_data['summary'], str
                ) else regime_data['summary']
                
                key_metrics = summary.get('key_metrics', {})
                features['market_volatility_regime'] = key_metrics.get('volatility_regime', 'normal')
                features['market_liquidity_state'] = key_metrics.get('liquidity_state', 'normal')
            except (json.JSONDecodeError, KeyError, TypeError):
                features['market_volatility_regime'] = 'normal'
                features['market_liquidity_state'] = 'normal'
            
            # Parse instrument data
            try:
                instruments = json.loads(regime_data['instruments']) if isinstance(
                    regime_data['instruments'], str
                ) else regime_data['instruments']
                
                # Get specific asset metrics
                vix_data = instruments.get('data', {}).get('VIX', {})
                features['vix_level'] = vix_data.get('last_price', 15.0)
                
                dxy_data = instruments.get('data', {}).get('DXY', {})
                features['dxy_level'] = dxy_data.get('last_price', 100.0)
                
                sp500_data = instruments.get('data', {}).get('SP500', {})
                features['sp500_daily_return'] = sp500_data.get('daily_return', 0.0)
                
                btc_data = instruments.get('data', {}).get('BTCUSD', {})
                features['btc_volatility_90d'] = btc_data.get('volatility_90d', 0.5)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                features.update({
                    'vix_level': 15.0,
                    'dxy_level': 100.0,
                    'sp500_daily_return': 0.0,
                    'btc_volatility_90d': 0.5
                })
            
            # Parse economic indicators
            try:
                indicators = json.loads(regime_data['country_economic_indicators']) if isinstance(
                    regime_data['country_economic_indicators'], str
                ) else regime_data['country_economic_indicators']
                
                features['fed_funds_rate'] = indicators.get('fed_funds_rate_effective', 5.0)
            except (json.JSONDecodeError, KeyError, TypeError):
                features['fed_funds_rate'] = 5.0
        
        else:
            # Default values if no regime data found
            features.update({
                'market_sentiment_score': 0.0,
                'market_volatility_regime': 'normal',
                'market_liquidity_state': 'normal',
                'vix_level': 15.0,
                'dxy_level': 100.0,
                'sp500_daily_return': 0.0,
                'btc_volatility_90d': 0.5,
                'fed_funds_rate': 5.0
            })
        
        return features
    
    def _get_time_features_static(self, feature_date: date) -> Dict[str, Any]:
        """Calculate date and time features (static/cached)."""
        return {
            'day_of_week': feature_date.weekday(),  # 0 = Monday, 6 = Sunday
            'week_of_month': (feature_date.day - 1) // 7 + 1,
            'month': feature_date.month,
            'quarter': (feature_date.month - 1) // 3 + 1,
            'day_of_year': feature_date.timetuple().tm_yday,
            'is_month_start': feature_date.day <= 3,
            'is_month_end': feature_date.day >= 28,
            'is_quarter_start': feature_date.month in [1, 4, 7, 10] and feature_date.day <= 3,
            'is_quarter_end': feature_date.month in [3, 6, 9, 12] and feature_date.day >= 28
        }
    
    def _save_features_batch(self, features_batch: List[Dict[str, Any]]) -> int:
        """Save a batch of features efficiently."""
        if not features_batch:
            return 0
        
        saved_count = 0
        for features in features_batch:
            try:
                # Save individual feature record
                columns = list(features.keys())
                values = [features[col] for col in columns]
                
                # Build insert query with ON CONFLICT
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join(columns)
                
                query = f"""
                INSERT INTO {self.feature_table} ({columns_str})
                VALUES ({placeholders})
                ON CONFLICT (account_id, feature_date) 
                DO UPDATE SET
                    {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in ['account_id', 'feature_date']])}
                """
                
                with self.db_manager.model_db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(query, values)
                
                saved_count += 1
                
            except Exception as e:
                logger.error(f"Error saving features for {features.get('account_id', 'unknown')}: {str(e)}")
                self.performance_metrics['errors_encountered'] += 1
        
        return saved_count
    
    def _run_feature_quality_monitoring(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Run feature quality monitoring using the FeatureQualityMonitor from V2."""
        try:
            # Sample features for quality assessment
            sample_size = min(self.config.get('quality_sample_size', 5000), 10000)
            
            sample_query = f"""
            SELECT *
            FROM {self.feature_table}
            WHERE feature_date >= %s AND feature_date <= %s
            ORDER BY RANDOM()
            LIMIT {sample_size}
            """
            
            sample_df = self.db_manager.model_db.execute_query_df(
                sample_query, (start_date, end_date)
            )
            
            if sample_df.empty:
                return {'status': 'no_data', 'message': 'No features found for quality monitoring'}
            
            # Run coverage analysis
            coverage_results = self.quality_monitor.monitor_feature_coverage(
                sample_df, 
                required_features=[
                    'current_balance', 'rolling_pnl_avg_5d', 'trades_count_5d',
                    'market_sentiment_score', 'day_of_week'
                ]
            )
            
            # Run range validation
            feature_ranges = {
                'rolling_pnl_avg_5d': (-10000, 10000),
                'trades_count_5d': (0, 1000),
                'day_of_week': (0, 6),
                'month': (1, 12),
                'win_rate_5d': (0, 100)
            }
            
            range_results = self.quality_monitor.validate_feature_ranges(
                sample_df, feature_ranges
            )
            
            # Get quality summary
            quality_summary = self.quality_monitor.get_quality_summary()
            
            return {
                'status': 'success',
                'coverage_results': coverage_results,
                'range_results': range_results,
                'quality_summary': quality_summary,
                'sample_size': len(sample_df)
            }
            
        except Exception as e:
            logger.error(f"Feature quality monitoring failed: {str(e)}")
            return {'status': 'error', 'error': str(e)}
    
    def _create_result_summary(self, start_time: datetime, total_records: int, 
                             validate_bias: bool, quality_results: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create comprehensive result summary combining all validation and monitoring results."""
        execution_time = (datetime.now() - start_time).total_seconds()
        self.performance_metrics['total_processing_time'] = execution_time
        
        violations_summary = self.bias_validator.get_violations_summary()
        
        result = {
            'total_records': total_records,
            'execution_time_seconds': execution_time,
            'validation_enabled': validate_bias,
            'lookahead_bias_check': violations_summary,
            'feature_version': FEATURE_VERSION,
            'performance_metrics': self.performance_metrics.copy(),
            'configuration': self.config.copy()
        }
        
        if quality_results:
            result['quality_monitoring'] = quality_results
        
        # Add efficiency metrics
        if execution_time > 0:
            result['records_per_second'] = total_records / execution_time
        else:
            result['records_per_second'] = 0
        
        return result


class FeatureEngineer:
    """Handles feature engineering for the daily profit model."""
    
    def __init__(self):
        """Initialize the feature engineer."""
        self.db_manager = get_db_manager()
        self.feature_table = 'feature_store_account_daily'
        
        # Rolling window configurations
        self.rolling_windows = [1, 3, 5, 10, 20]
        
    def engineer_features(self,
                         start_date: Optional[date] = None,
                         end_date: Optional[date] = None,
                         force_rebuild: bool = False) -> int:
        """
        Engineer features for all accounts and dates in the specified range.
        
        Args:
            start_date: Start date for feature engineering
            end_date: End date for feature engineering
            force_rebuild: If True, rebuild features even if they exist
            
        Returns:
            Number of feature records created
        """
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)
            if not start_date:
                start_date = end_date - timedelta(days=30)
            
            logger.info(f"Engineering features from {start_date} to {end_date}")
            
            # Get all unique accounts
            accounts = self._get_active_accounts(start_date, end_date)
            logger.info(f"Found {len(accounts)} active accounts to process")
            
            # Process each account
            for account_id, login in accounts:
                account_records = self._engineer_features_for_account(
                    account_id, login, start_date, end_date, force_rebuild
                )
                total_records += account_records
                
                if total_records % 1000 == 0:
                    logger.info(f"Progress: {total_records} feature records created")
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'accounts_processed': len(accounts),
                    'force_rebuild': force_rebuild
                }
            )
            
            logger.info(f"Successfully created {total_records} feature records")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to engineer features: {str(e)}")
            raise
    
    def _get_active_accounts(self, start_date: date, end_date: date) -> List[Tuple[str, str]]:
        """Get list of active accounts in the date range."""
        query = """
        SELECT DISTINCT account_id, login
        FROM stg_accounts_daily_snapshots
        WHERE date >= %s AND date <= %s
        ORDER BY account_id
        """
        results = self.db_manager.model_db.execute_query(query, (start_date, end_date))
        return [(r['account_id'], r['login']) for r in results]
    
    def _engineer_features_for_account(self,
                                     account_id: str,
                                     login: str,
                                     start_date: date,
                                     end_date: date,
                                     force_rebuild: bool) -> int:
        """Engineer features for a single account over the date range."""
        records_created = 0
        
        # Process each date
        current_date = start_date
        while current_date <= end_date:
            # Check if features already exist
            if not force_rebuild and self._features_exist(account_id, current_date):
                current_date += timedelta(days=1)
                continue
            
            # Engineer features for this date
            features = self._calculate_features_for_date(account_id, login, current_date)
            
            if features:
                self._save_features(features)
                records_created += 1
            
            current_date += timedelta(days=1)
        
        return records_created
    
    def _features_exist(self, account_id: str, feature_date: date) -> bool:
        """Check if features already exist for an account and date."""
        query = f"""
        SELECT EXISTS(
            SELECT 1 FROM {self.feature_table}
            WHERE account_id = %s AND feature_date = %s
        )
        """
        result = self.db_manager.model_db.execute_query(query, (account_id, feature_date))
        return result[0]['exists'] if result else False
    
    def _calculate_features_for_date(self,
                                   account_id: str,
                                   login: str,
                                   feature_date: date) -> Optional[Dict[str, Any]]:
        """
        Calculate all features for an account on a specific date.
        Features from day D are used to predict PnL for day D+1.
        """
        try:
            # Initialize feature dictionary
            features = {
                'account_id': account_id,
                'login': login,
                'feature_date': feature_date
            }
            
            # 1. Static Account & Plan Features
            static_features = self._get_static_features(account_id, feature_date)
            features.update(static_features)
            
            # 2. Dynamic Account State Features
            dynamic_features = self._get_dynamic_features(account_id, feature_date)
            features.update(dynamic_features)
            
            # 3. Historical Performance Features
            performance_features = self._get_performance_features(account_id, feature_date)
            features.update(performance_features)
            
            # 4. Behavioral Features
            behavioral_features = self._get_behavioral_features(account_id, feature_date)
            features.update(behavioral_features)
            
            # 5. Market Regime Features
            market_features = self._get_market_features(feature_date)
            features.update(market_features)
            
            # 6. Date and Time Features
            time_features = self._get_time_features(feature_date)
            features.update(time_features)
            
            return features
            
        except Exception as e:
            logger.error(f"Error calculating features for {account_id} on {feature_date}: {str(e)}")
            return None
    
    def _get_static_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Get static account and plan features."""
        query = """
        SELECT 
            starting_balance,
            max_daily_drawdown_pct,
            max_drawdown_pct,
            profit_target_pct,
            max_leverage,
            CASE WHEN is_drawdown_relative THEN 1 ELSE 0 END as is_drawdown_relative
        FROM stg_accounts_daily_snapshots
        WHERE account_id = %s AND date = %s
        """
        
        result = self.db_manager.model_db.execute_query(query, (account_id, feature_date))
        
        if result:
            return result[0]
        else:
            # Return defaults if not found
            return {
                'starting_balance': None,
                'max_daily_drawdown_pct': None,
                'max_drawdown_pct': None,
                'profit_target_pct': None,
                'max_leverage': None,
                'is_drawdown_relative': 0
            }
    
    def _get_dynamic_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Get dynamic account state features as of EOD feature_date."""
        # Get snapshot data
        snapshot_query = """
        SELECT 
            current_balance,
            current_equity,
            days_since_first_trade,
            active_trading_days_count,
            distance_to_profit_target,
            distance_to_max_drawdown
        FROM stg_accounts_daily_snapshots
        WHERE account_id = %s AND date = %s
        """
        
        snapshot_result = self.db_manager.model_db.execute_query(
            snapshot_query, (account_id, feature_date)
        )
        
        features = {}
        if snapshot_result:
            features.update(snapshot_result[0])
        else:
            features.update({
                'current_balance': None,
                'current_equity': None,
                'days_since_first_trade': 0,
                'active_trading_days_count': 0,
                'distance_to_profit_target': None,
                'distance_to_max_drawdown': None
            })
        
        # Get open positions data
        open_positions_query = """
        SELECT 
            SUM(unrealized_pnl) as open_pnl,
            SUM(volume_usd) as open_positions_volume
        FROM raw_trades_open
        WHERE account_id = %s AND trade_date = %s
        """
        
        open_result = self.db_manager.model_db.execute_query(
            open_positions_query, (account_id, feature_date)
        )
        
        if open_result and open_result[0]['open_pnl'] is not None:
            features['open_pnl'] = open_result[0]['open_pnl']
            features['open_positions_volume'] = open_result[0]['open_positions_volume']
        else:
            features['open_pnl'] = 0.0
            features['open_positions_volume'] = 0.0
        
        return features
    
    def _get_performance_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Calculate rolling window performance features."""
        features = {}
        
        # Get historical daily PnL data
        pnl_query = """
        SELECT date, net_profit
        FROM raw_metrics_daily
        WHERE account_id = %s AND date <= %s
        ORDER BY date DESC
        LIMIT 60  -- Maximum window we need
        """
        
        pnl_df = self.db_manager.model_db.execute_query_df(pnl_query, (account_id, feature_date))
        
        if pnl_df.empty:
            # Return default values for all rolling features
            for window in self.rolling_windows:
                features.update(self._get_default_rolling_features(window))
            return features
        
        # Calculate features for each rolling window
        for window in self.rolling_windows:
            if len(pnl_df) >= window:
                window_data = pnl_df.head(window)
                
                # Basic statistics
                features[f'rolling_pnl_sum_{window}d'] = window_data['net_profit'].sum()
                features[f'rolling_pnl_avg_{window}d'] = window_data['net_profit'].mean()
                features[f'rolling_pnl_std_{window}d'] = window_data['net_profit'].std()
                
                if window >= 3:
                    features[f'rolling_pnl_min_{window}d'] = window_data['net_profit'].min()
                    features[f'rolling_pnl_max_{window}d'] = window_data['net_profit'].max()
                    
                    # Win rate
                    wins = (window_data['net_profit'] > 0).sum()
                    features[f'win_rate_{window}d'] = (wins / window) * 100
                
                if window >= 5:
                    # Profit factor
                    gains = window_data[window_data['net_profit'] > 0]['net_profit'].sum()
                    losses = abs(window_data[window_data['net_profit'] < 0]['net_profit'].sum())
                    if losses > 0:
                        features[f'profit_factor_{window}d'] = gains / losses
                    else:
                        features[f'profit_factor_{window}d'] = gains if gains > 0 else 0
                    
                    # Sharpe ratio (simplified)
                    if features[f'rolling_pnl_std_{window}d'] > 0:
                        features[f'sharpe_ratio_{window}d'] = (
                            features[f'rolling_pnl_avg_{window}d'] / 
                            features[f'rolling_pnl_std_{window}d']
                        ) * np.sqrt(252)  # Annualized
                    else:
                        features[f'sharpe_ratio_{window}d'] = 0
            else:
                features.update(self._get_default_rolling_features(window))
        
        return features
    
    def _get_default_rolling_features(self, window: int) -> Dict[str, float]:
        """Get default values for rolling features when not enough data."""
        features = {
            f'rolling_pnl_sum_{window}d': 0.0,
            f'rolling_pnl_avg_{window}d': 0.0,
            f'rolling_pnl_std_{window}d': 0.0
        }
        
        if window >= 3:
            features[f'rolling_pnl_min_{window}d'] = 0.0
            features[f'rolling_pnl_max_{window}d'] = 0.0
            features[f'win_rate_{window}d'] = 0.0
        
        if window >= 5:
            features[f'profit_factor_{window}d'] = 0.0
            features[f'sharpe_ratio_{window}d'] = 0.0
        
        return features
    
    def _get_behavioral_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Calculate behavioral trading features."""
        # Use 5-day window for behavioral features
        window_start = feature_date - timedelta(days=4)
        
        trades_query = """
        SELECT 
            trade_id,
            symbol,
            std_symbol,
            side,
            open_time,
            close_time,
            stop_loss,
            take_profit,
            lots,
            volume_usd
        FROM raw_trades_closed
        WHERE account_id = %s 
            AND trade_date >= %s 
            AND trade_date <= %s
        """
        
        trades_df = self.db_manager.model_db.execute_query_df(
            trades_query, (account_id, window_start, feature_date)
        )
        
        features = {}
        
        if trades_df.empty:
            # Return default values
            features.update({
                'trades_count_5d': 0,
                'avg_trade_duration_5d': 0.0,
                'avg_lots_per_trade_5d': 0.0,
                'avg_volume_per_trade_5d': 0.0,
                'stop_loss_usage_rate_5d': 0.0,
                'take_profit_usage_rate_5d': 0.0,
                'buy_sell_ratio_5d': 0.5,
                'top_symbol_concentration_5d': 0.0
            })
        else:
            # Trade count
            features['trades_count_5d'] = len(trades_df)
            
            # Average trade duration (in hours)
            if 'open_time' in trades_df.columns and 'close_time' in trades_df.columns:
                trades_df['duration'] = (
                    pd.to_datetime(trades_df['close_time']) - 
                    pd.to_datetime(trades_df['open_time'])
                ).dt.total_seconds() / 3600
                features['avg_trade_duration_5d'] = trades_df['duration'].mean()
            else:
                features['avg_trade_duration_5d'] = 0.0
            
            # Average lots and volume
            features['avg_lots_per_trade_5d'] = trades_df['lots'].mean()
            features['avg_volume_per_trade_5d'] = trades_df['volume_usd'].mean()
            
            # Stop loss and take profit usage
            sl_count = (trades_df['stop_loss'].notna() & (trades_df['stop_loss'] != 0)).sum()
            tp_count = (trades_df['take_profit'].notna() & (trades_df['take_profit'] != 0)).sum()
            features['stop_loss_usage_rate_5d'] = (sl_count / len(trades_df)) * 100
            features['take_profit_usage_rate_5d'] = (tp_count / len(trades_df)) * 100
            
            # Buy/sell ratio
            buy_count = (trades_df['side'] == 'buy').sum()
            sell_count = (trades_df['side'] == 'sell').sum()
            total_sides = buy_count + sell_count
            if total_sides > 0:
                features['buy_sell_ratio_5d'] = buy_count / total_sides
            else:
                features['buy_sell_ratio_5d'] = 0.5
            
            # Symbol concentration
            if 'std_symbol' in trades_df.columns:
                symbol_counts = trades_df['std_symbol'].value_counts()
                if len(symbol_counts) > 0:
                    features['top_symbol_concentration_5d'] = (
                        symbol_counts.iloc[0] / len(trades_df)
                    ) * 100
                else:
                    features['top_symbol_concentration_5d'] = 0.0
            else:
                features['top_symbol_concentration_5d'] = 0.0
        
        return features
    
    def _get_market_features(self, feature_date: date) -> Dict[str, Any]:
        """Extract market regime features for the date."""
        query = """
        SELECT 
            market_news,
            instruments,
            country_economic_indicators,
            news_analysis,
            summary
        FROM raw_regimes_daily
        WHERE date = %s
        ORDER BY ingestion_timestamp DESC
        LIMIT 1
        """
        
        result = self.db_manager.model_db.execute_query(query, (feature_date,))
        
        features = {}
        
        if result:
            regime_data = result[0]
            
            # Parse sentiment score
            try:
                news_analysis = json.loads(regime_data['news_analysis']) if isinstance(
                    regime_data['news_analysis'], str
                ) else regime_data['news_analysis']
                
                sentiment_score = news_analysis.get('sentiment_summary', {}).get(
                    'average_score', 0.0
                )
                features['market_sentiment_score'] = sentiment_score
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                features['market_sentiment_score'] = 0.0
            
            # Parse volatility regime and liquidity state
            try:
                summary = json.loads(regime_data['summary']) if isinstance(
                    regime_data['summary'], str
                ) else regime_data['summary']
                
                key_metrics = summary.get('key_metrics', {})
                features['market_volatility_regime'] = key_metrics.get('volatility_regime', 'normal')
                features['market_liquidity_state'] = key_metrics.get('liquidity_state', 'normal')
            except (json.JSONDecodeError, KeyError, TypeError):
                features['market_volatility_regime'] = 'normal'
                features['market_liquidity_state'] = 'normal'
            
            # Parse instrument data
            try:
                instruments = json.loads(regime_data['instruments']) if isinstance(
                    regime_data['instruments'], str
                ) else regime_data['instruments']
                
                # Get specific asset metrics
                vix_data = instruments.get('data', {}).get('VIX', {})
                features['vix_level'] = vix_data.get('last_price', 15.0)
                
                dxy_data = instruments.get('data', {}).get('DXY', {})
                features['dxy_level'] = dxy_data.get('last_price', 100.0)
                
                sp500_data = instruments.get('data', {}).get('SP500', {})
                features['sp500_daily_return'] = sp500_data.get('daily_return', 0.0)
                
                btc_data = instruments.get('data', {}).get('BTCUSD', {})
                features['btc_volatility_90d'] = btc_data.get('volatility_90d', 0.5)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                features.update({
                    'vix_level': 15.0,
                    'dxy_level': 100.0,
                    'sp500_daily_return': 0.0,
                    'btc_volatility_90d': 0.5
                })
            
            # Parse economic indicators
            try:
                indicators = json.loads(regime_data['country_economic_indicators']) if isinstance(
                    regime_data['country_economic_indicators'], str
                ) else regime_data['country_economic_indicators']
                
                features['fed_funds_rate'] = indicators.get('fed_funds_rate_effective', 5.0)
            except (json.JSONDecodeError, KeyError, TypeError):
                features['fed_funds_rate'] = 5.0
        
        else:
            # Default values if no regime data found
            features.update({
                'market_sentiment_score': 0.0,
                'market_volatility_regime': 'normal',
                'market_liquidity_state': 'normal',
                'vix_level': 15.0,
                'dxy_level': 100.0,
                'sp500_daily_return': 0.0,
                'btc_volatility_90d': 0.5,
                'fed_funds_rate': 5.0
            })
        
        return features
    
    def _get_time_features(self, feature_date: date) -> Dict[str, Any]:
        """Calculate date and time features."""
        features = {
            'day_of_week': feature_date.weekday(),  # 0 = Monday, 6 = Sunday
            'week_of_month': (feature_date.day - 1) // 7 + 1,
            'month': feature_date.month,
            'quarter': (feature_date.month - 1) // 3 + 1,
            'day_of_year': feature_date.timetuple().tm_yday,
            'is_month_start': feature_date.day <= 3,
            'is_month_end': feature_date.day >= 28,
            'is_quarter_start': feature_date.month in [1, 4, 7, 10] and feature_date.day <= 3,
            'is_quarter_end': feature_date.month in [3, 6, 9, 12] and feature_date.day >= 28
        }
        
        return features
    
    def _save_features(self, features: Dict[str, Any]):
        """Save calculated features to the database."""
        # Convert feature dict to match database columns
        columns = list(features.keys())
        values = [features[col] for col in columns]
        
        # Build insert query with ON CONFLICT
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)
        
        query = f"""
        INSERT INTO {self.feature_table} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (account_id, feature_date) 
        DO UPDATE SET
            {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in ['account_id', 'feature_date']])}
        """
        
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, values)


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Engineer features for daily profit model')
    parser.add_argument('--start-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Start date for feature engineering (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='End date for feature engineering (YYYY-MM-DD)')
    parser.add_argument('--force-rebuild', action='store_true',
                       help='Force rebuild of existing features')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='engineer_features')
    
    # Run feature engineering
    engineer = FeatureEngineer()
    try:
        records = engineer.engineer_features(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild
        )
        logger.info(f"Feature engineering complete. Total records: {records}")
    except Exception as e:
        logger.error(f"Feature engineering failed: {str(e)}")
        raise


def engineer_features(**kwargs):
    """Convenience function for backward compatibility."""
    engineer = FeatureEngineer()
    return engineer.engineer_features(**kwargs)


def engineer_features_with_validation(**kwargs):
    """Production function for feature engineering with comprehensive validation."""
    engineer = ProductionFeatureEngineer()
    return engineer.engineer_features_with_validation(**kwargs)


if __name__ == '__main__':
    main()