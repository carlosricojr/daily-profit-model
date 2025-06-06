"""
Integrated Feature Engineering Module
This version integrates the N+1 query optimizations into the production feature engineer.
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
from collections import defaultdict
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging
from utils.query_performance import QueryPerformanceMonitor

# Import the optimized components
from engineer_features_optimized import OptimizedFeatureEngineer

# Import validation and monitoring components from original
from engineer_features import (
    LookaheadBiasValidator, 
    FeatureQualityMonitor,
    FEATURE_VERSION,
    PRODUCTION_CONFIG
)

logger = logging.getLogger(__name__)


class IntegratedProductionFeatureEngineer(OptimizedFeatureEngineer):
    """
    Production-ready feature engineer that combines:
    1. N+1 query optimizations from OptimizedFeatureEngineer
    2. Comprehensive validation from ProductionFeatureEngineer
    3. Quality monitoring and bias detection
    4. Performance tracking and logging
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the integrated feature engineer."""
        super().__init__()
        
        self.config = {**PRODUCTION_CONFIG, **(config or {})}
        
        # Add validation and monitoring
        self.bias_validator = LookaheadBiasValidator(strict_mode=True)
        self.quality_monitor = FeatureQualityMonitor(self.db_manager)
        
        # Enhanced performance monitoring
        self.query_monitor = QueryPerformanceMonitor(
            log_file=f'logs/feature_engineering_queries_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
        
        # Track overall performance
        self.performance_metrics = {
            'total_processing_time': 0,
            'total_records_processed': 0,
            'total_features_created': 0,
            'memory_peak_mb': 0,
            'errors_encountered': 0,
            'validation_violations': 0
        }
    
    def engineer_features_with_validation(self,
                                        start_date: Optional[date] = None,
                                        end_date: Optional[date] = None,
                                        force_rebuild: bool = False,
                                        validate_bias: bool = True,
                                        enable_monitoring: bool = True) -> Dict[str, Any]:
        """
        Engineer features with optimized queries, validation, and monitoring.
        
        Args:
            start_date: Start date for feature engineering
            end_date: End date for feature engineering  
            force_rebuild: If True, rebuild features even if they exist
            validate_bias: If True, perform lookahead bias validation
            enable_monitoring: If True, enable quality monitoring
            
        Returns:
            Dictionary with processing results, validation summary, and metrics
        """
        start_time = datetime.now()
        
        # Reset metrics for this run
        self.bias_validator.reset_violations()
        self.performance_metrics = {k: 0 for k in self.performance_metrics}
        
        logger.info(f"[INTEGRATED] Starting feature engineering from {start_date} to {end_date}")
        logger.info(f"Options: validation={validate_bias}, monitoring={enable_monitoring}, rebuild={force_rebuild}")
        
        try:
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)
            if not start_date:
                start_date = end_date - timedelta(days=7)
            
            # Validate input parameters
            if start_date > end_date:
                raise ValueError(f"Start date {start_date} cannot be after end date {end_date}")
            
            # Get work items using optimized method
            work_items = self._get_work_items(start_date, end_date, force_rebuild)
            
            if not work_items:
                logger.info("No work items to process")
                return self._create_comprehensive_summary(start_time, 0, validate_bias, enable_monitoring)
            
            logger.info(f"Processing {len(work_items)} account-date combinations")
            
            # Process with enhanced batch method that includes validation
            total_records = self._process_batches_with_validation(
                work_items, start_date, end_date, validate_bias
            )
            
            # Run quality monitoring if enabled
            quality_results = {}
            if enable_monitoring and total_records > 0:
                quality_results = self._run_comprehensive_monitoring(start_date, end_date)
            
            # Create comprehensive result summary
            result = self._create_comprehensive_summary(
                start_time, total_records, validate_bias, enable_monitoring, quality_results
            )
            
            # Log performance metrics
            self.query_monitor.log_summary()
            self.query_monitor.save_performance_log()
            
            # Log completion
            self._log_completion_status(result)
            
            return result
            
        except Exception as e:
            self.performance_metrics['errors_encountered'] += 1
            logger.error(f"Feature engineering failed: {str(e)}")
            
            # Save any performance data collected
            self.query_monitor.save_performance_log()
            
            raise
    
    def _process_batches_with_validation(self, work_items: List[Tuple[str, str, date]], 
                                       start_date: date, end_date: date,
                                       validate_bias: bool) -> int:
        """Process batches with integrated validation."""
        total_records = 0
        batch_size = self.config['batch_size']
        
        for i in range(0, len(work_items), batch_size):
            batch = work_items[i:i + batch_size]
            
            # Track batch processing
            with self.query_monitor.track_query('process_batch', f'Processing batch of {len(batch)} items'):
                batch_records = self._process_batch_enhanced(batch, start_date, end_date, validate_bias)
                total_records += batch_records
            
            # Progress logging
            progress = min(100, ((i + len(batch)) / len(work_items)) * 100)
            if (i + len(batch)) % 100 == 0 or progress >= 100:
                logger.info(f"Progress: {progress:.1f}% ({i + len(batch)}/{len(work_items)})")
                
                # Log intermediate metrics
                logger.debug(f"Queries executed: {self.query_stats['bulk_queries']} bulk, "
                           f"{self.query_stats['total_queries']} equivalent individual")
        
        self.performance_metrics['total_records_processed'] = total_records
        return total_records
    
    def _process_batch_enhanced(self, work_items: List[Tuple[str, str, date]], 
                              start_date: date, end_date: date,
                              validate_bias: bool) -> int:
        """Enhanced batch processing with validation."""
        if not work_items:
            return 0
        
        # Extract unique accounts and dates
        account_ids = list(set(item[0] for item in work_items))
        dates = list(set(item[2] for item in work_items))
        
        # Bulk fetch all data with performance tracking
        bulk_data = self._bulk_fetch_all_data_monitored(account_ids, dates, start_date, end_date)
        
        # Process each work item with validation
        features_batch = []
        for account_id, login, feature_date in work_items:
            try:
                features = self._calculate_and_validate_features(
                    account_id, login, feature_date, bulk_data, validate_bias
                )
                if features:
                    features_batch.append(features)
            except Exception as e:
                logger.error(f"Error processing {account_id} on {feature_date}: {str(e)}")
                self.performance_metrics['errors_encountered'] += 1
        
        # Bulk save features
        if features_batch:
            with self.query_monitor.track_query('bulk_save', f'Saving {len(features_batch)} features'):
                return self._bulk_save_features(features_batch)
        
        return 0
    
    def _bulk_fetch_all_data_monitored(self, account_ids: List[str], dates: List[date],
                                     start_date: date, end_date: date) -> Dict[str, Any]:
        """Fetch all data with performance monitoring."""
        bulk_data = {}
        
        # Static features
        with self.query_monitor.track_query('bulk_fetch_static', 'Fetching static features'):
            bulk_data['static_features'] = self._bulk_fetch_static_features(account_ids, dates)
        
        # Dynamic features
        with self.query_monitor.track_query('bulk_fetch_dynamic', 'Fetching dynamic features'):
            bulk_data['dynamic_features'] = self._bulk_fetch_dynamic_features(account_ids, dates)
        
        # Open positions
        with self.query_monitor.track_query('bulk_fetch_positions', 'Fetching open positions'):
            bulk_data['open_positions'] = self._bulk_fetch_open_positions(account_ids, dates)
        
        # Performance data
        with self.query_monitor.track_query('bulk_fetch_performance', 'Fetching performance data'):
            bulk_data['performance_data'] = self._bulk_fetch_performance_data(
                account_ids, start_date, end_date
            )
        
        # Trades data
        with self.query_monitor.track_query('bulk_fetch_trades', 'Fetching trades data'):
            bulk_data['trades_data'] = self._bulk_fetch_trades_data(
                account_ids, start_date, end_date
            )
        
        # Market data
        with self.query_monitor.track_query('bulk_fetch_market', 'Fetching market data'):
            bulk_data['market_data'] = self._bulk_fetch_market_data(dates)
        
        return bulk_data
    
    def _calculate_and_validate_features(self, account_id: str, login: str, 
                                       feature_date: date, bulk_data: Dict[str, Any],
                                       validate_bias: bool) -> Optional[Dict[str, Any]]:
        """Calculate features with integrated validation."""
        # Calculate base features using optimized method
        features = self._calculate_features_from_bulk_data(account_id, login, feature_date, bulk_data)
        
        if not features:
            return None
        
        # Perform bias validation if enabled
        if validate_bias:
            # Validate data availability
            if not self.bias_validator.validate_data_availability(
                feature_date, feature_date, 'base_features'
            ):
                self.performance_metrics['validation_violations'] += 1
                return None
            
            # Validate target alignment
            target_date = feature_date + timedelta(days=1)
            self.bias_validator.validate_feature_target_alignment(
                feature_date, target_date, 'target_alignment'
            )
            
            # Validate rolling windows
            if account_id in bulk_data['performance_data']:
                perf_df = bulk_data['performance_data'][account_id]
                filtered_df = perf_df[perf_df['date'] <= feature_date]
                
                for window in self.rolling_windows:
                    if len(filtered_df) >= window:
                        window_data = filtered_df.head(window)
                        window_start = window_data['date'].min()
                        window_end = window_data['date'].max()
                        
                        if not self.bias_validator.validate_rolling_window(
                            feature_date, window_start, window_end, f'rolling_{window}d'
                        ):
                            self.performance_metrics['validation_violations'] += 1
        
        return features
    
    def _run_comprehensive_monitoring(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Run comprehensive feature quality monitoring."""
        try:
            logger.info("Running feature quality monitoring...")
            
            # Sample features for analysis
            sample_query = f"""
            SELECT *
            FROM {self.feature_table}
            WHERE feature_date >= %s AND feature_date <= %s
            ORDER BY RANDOM()
            LIMIT 5000
            """
            
            with self.query_monitor.track_query('quality_monitoring', 'Feature quality sampling'):
                sample_df = self.db_manager.model_db.execute_query_df(
                    sample_query, (start_date, end_date)
                )
            
            if sample_df.empty:
                return {'status': 'no_data'}
            
            # Run various quality checks
            quality_results = {
                'sample_size': len(sample_df),
                'date_range': {'start': str(start_date), 'end': str(end_date)}
            }
            
            # Coverage analysis
            required_features = [
                'current_balance', 'rolling_pnl_avg_5d', 'trades_count_5d',
                'market_sentiment_score', 'day_of_week'
            ]
            quality_results['coverage'] = self.quality_monitor.monitor_feature_coverage(
                sample_df, required_features
            )
            
            # Distribution analysis
            quality_results['distributions'] = self._analyze_feature_distributions(sample_df)
            
            # Get quality summary
            quality_results['summary'] = self.quality_monitor.get_quality_summary()
            
            return quality_results
            
        except Exception as e:
            logger.error(f"Quality monitoring failed: {str(e)}")
            return {'status': 'error', 'error': str(e)}
    
    def _analyze_feature_distributions(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze feature distributions for quality assessment."""
        distributions = {}
        
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_columns[:10]:  # Analyze top 10 numeric features
            if col in ['account_id', 'feature_date']:
                continue
                
            col_data = df[col].dropna()
            if len(col_data) > 0:
                distributions[col] = {
                    'mean': float(col_data.mean()),
                    'std': float(col_data.std()),
                    'min': float(col_data.min()),
                    'max': float(col_data.max()),
                    'nulls': int(df[col].isna().sum()),
                    'null_pct': float(df[col].isna().sum() / len(df) * 100)
                }
        
        return distributions
    
    def _create_comprehensive_summary(self, start_time: datetime, total_records: int,
                                    validate_bias: bool, enable_monitoring: bool,
                                    quality_results: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create comprehensive summary of the feature engineering run."""
        execution_time = (datetime.now() - start_time).total_seconds()
        self.performance_metrics['total_processing_time'] = execution_time
        
        # Get validation summary
        violations_summary = self.bias_validator.get_violations_summary() if validate_bias else {}
        
        # Get query performance summary
        query_summary = self.query_monitor.get_summary()
        
        result = {
            'total_records': total_records,
            'execution_time_seconds': execution_time,
            'feature_version': FEATURE_VERSION,
            'configuration': {
                'validation_enabled': validate_bias,
                'monitoring_enabled': enable_monitoring,
                **self.config
            },
            'performance_metrics': {
                **self.performance_metrics,
                'records_per_second': total_records / execution_time if execution_time > 0 else 0
            },
            'query_optimization': {
                'bulk_queries': self.query_stats['bulk_queries'],
                'equivalent_individual_queries': self.query_stats['total_queries'],
                'query_reduction_factor': (
                    self.query_stats['total_queries'] / self.query_stats['bulk_queries']
                    if self.query_stats['bulk_queries'] > 0 else 0
                ),
                **query_summary
            }
        }
        
        if validate_bias:
            result['lookahead_bias_check'] = violations_summary
        
        if enable_monitoring and quality_results:
            result['quality_monitoring'] = quality_results
        
        return result
    
    def _log_completion_status(self, result: Dict[str, Any]):
        """Log detailed completion status."""
        logger.info("=" * 80)
        logger.info("FEATURE ENGINEERING COMPLETED")
        logger.info("=" * 80)
        
        # Basic metrics
        logger.info(f"Total records processed: {result['total_records']}")
        logger.info(f"Execution time: {result['execution_time_seconds']:.2f} seconds")
        logger.info(f"Processing rate: {result['performance_metrics']['records_per_second']:.1f} records/second")
        
        # Query optimization
        qo = result['query_optimization']
        logger.info(f"\nQuery Optimization:")
        logger.info(f"  - Bulk queries executed: {qo['bulk_queries']}")
        logger.info(f"  - Equivalent individual queries: {qo['equivalent_individual_queries']}")
        logger.info(f"  - Reduction factor: {qo['query_reduction_factor']:.1f}x")
        logger.info(f"  - Average query time: {qo['avg_query_time']:.3f}s")
        
        # Validation results
        if 'lookahead_bias_check' in result:
            bias_check = result['lookahead_bias_check']
            if bias_check.get('has_violations'):
                logger.warning(f"\nLookahead Bias Violations: {bias_check['count']}")
                logger.warning(f"Violation rate: {bias_check['violation_rate']:.2%}")
            else:
                logger.info("\n✓ No lookahead bias violations detected")
        
        # Quality monitoring
        if 'quality_monitoring' in result and result['quality_monitoring'].get('summary'):
            qm = result['quality_monitoring']['summary']
            logger.info(f"\nQuality Monitoring:")
            logger.info(f"  - Quality score: {qm['quality_score']:.2f}")
            logger.info(f"  - Total issues: {qm['total_issues']}")
            if qm['issue_breakdown']:
                logger.info(f"  - Issue types: {qm['issue_breakdown']}")
        
        logger.info("=" * 80)


def engineer_features_optimized(**kwargs):
    """
    Main entry point for optimized feature engineering.
    Maintains backward compatibility with original interface.
    """
    engineer = IntegratedProductionFeatureEngineer()
    
    # Map legacy parameters if needed
    if 'validate_bias' not in kwargs:
        kwargs['validate_bias'] = True
    if 'enable_monitoring' not in kwargs:
        kwargs['enable_monitoring'] = True
    
    return engineer.engineer_features_with_validation(**kwargs)


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(
        description='Optimized feature engineering with N+1 query fixes and comprehensive validation'
    )
    parser.add_argument('--start-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Start date for feature engineering (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='End date for feature engineering (YYYY-MM-DD)')
    parser.add_argument('--force-rebuild', action='store_true',
                       help='Force rebuild of existing features')
    parser.add_argument('--no-validation', action='store_true',
                       help='Disable lookahead bias validation')
    parser.add_argument('--no-monitoring', action='store_true',
                       help='Disable quality monitoring')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='engineer_features_integrated')
    
    # Run feature engineering
    try:
        result = engineer_features_optimized(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild,
            validate_bias=not args.no_validation,
            enable_monitoring=not args.no_monitoring
        )
        
        logger.info(f"Feature engineering complete: {result['total_records']} records processed")
        
    except Exception as e:
        logger.error(f"Feature engineering failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()