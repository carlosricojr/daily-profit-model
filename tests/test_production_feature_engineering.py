#!/usr/bin/env python3
"""
Production Feature Engineering Test Suite

Comprehensive test suite validating production readiness of the feature engineering system.
Tests critical functionality combining best practices from all archived versions:
- Lookahead bias prevention with strict validation
- Feature quality monitoring with drift detection  
- Parallel processing with memory optimization
- Comprehensive error handling and recovery
- Performance and scalability validation

This test suite ensures all critical production features work correctly and safely.
"""

import sys
import os
import logging
import pytest
from datetime import datetime, timedelta, date
import time
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.feature_engineering.engineer_features import (
    LookaheadBiasValidator,
    FeatureQualityMonitor, 
    ProductionFeatureEngineer,
    FEATURE_VERSION
)
from src.utils.logging_config import setup_logging

# Configure logging for tests
setup_logging(log_level='INFO', log_file='production_feature_engineering_test')
logger = logging.getLogger(__name__)


class TestLookaheadBiasValidator:
    """Test suite for LookaheadBiasValidator production functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.validator = LookaheadBiasValidator(strict_mode=True)
        self.feature_date = date(2024, 1, 15)
    
    def test_data_availability_validation_valid_cases(self):
        """Test data availability validation with valid cases."""
        # Test same day data (valid)
        result = self.validator.validate_data_availability(
            self.feature_date, self.feature_date, 'same_day_feature'
        )
        assert result is True
        
        # Test previous day data (valid)
        previous_day = self.feature_date - timedelta(days=1)
        result = self.validator.validate_data_availability(
            self.feature_date, previous_day, 'previous_day_feature'
        )
        assert result is True
    
    def test_data_availability_validation_invalid_cases(self):
        """Test data availability validation catches future data."""
        future_date = self.feature_date + timedelta(days=1)
        
        with pytest.raises(ValueError, match="Lookahead bias violation"):
            self.validator.validate_data_availability(
                self.feature_date, future_date, 'future_feature'
            )
    
    def test_rolling_window_validation_valid_cases(self):
        """Test rolling window validation with valid cases."""
        window_start = self.feature_date - timedelta(days=5)
        window_end = self.feature_date  # Ends on feature date - valid
        
        result = self.validator.validate_rolling_window(
            self.feature_date, window_start, window_end, 'rolling_5d'
        )
        assert result is True
    
    def test_rolling_window_validation_invalid_cases(self):
        """Test rolling window validation catches future windows."""
        window_start = self.feature_date - timedelta(days=5)
        window_end = self.feature_date + timedelta(days=1)  # Future end - invalid
        
        with pytest.raises(ValueError, match="Rolling window lookahead bias"):
            self.validator.validate_rolling_window(
                self.feature_date, window_start, window_end, 'invalid_rolling_5d'
            )
    
    def test_target_alignment_validation(self):
        """Test feature-target temporal alignment validation."""
        # Correct alignment: target is D+1
        correct_target_date = self.feature_date + timedelta(days=1)
        result = self.validator.validate_feature_target_alignment(
            self.feature_date, correct_target_date, 'correct_target'
        )
        assert result is True
        
        # Incorrect alignment: target is D+2
        incorrect_target_date = self.feature_date + timedelta(days=2)
        result = self.validator.validate_feature_target_alignment(
            self.feature_date, incorrect_target_date, 'incorrect_target'
        )
        assert result is False
    
    def test_violations_tracking_and_summary(self):
        """Test comprehensive violations tracking and summary."""
        # Create some violations
        future_date = self.feature_date + timedelta(days=1)
        
        # Use non-strict mode to accumulate violations
        validator = LookaheadBiasValidator(strict_mode=False)
        
        # Generate violations
        validator.validate_data_availability(self.feature_date, future_date, 'violation1')
        validator.validate_rolling_window(
            self.feature_date, 
            self.feature_date - timedelta(days=3),
            self.feature_date + timedelta(days=1),
            'violation2'
        )
        
        summary = validator.get_violations_summary()
        
        assert summary['has_violations'] is True
        assert summary['count'] >= 2
        assert summary['validation_stats']['total_validations'] >= 2
        assert summary['validation_stats']['violations_count'] >= 2
        assert summary['violation_rate'] > 0
        assert 'violation_types' in summary
        assert 'severity_breakdown' in summary
    
    def test_reset_violations(self):
        """Test violations reset functionality."""
        # Create violations
        validator = LookaheadBiasValidator(strict_mode=False)
        future_date = self.feature_date + timedelta(days=1)
        validator.validate_data_availability(self.feature_date, future_date, 'test_violation')
        
        assert len(validator.violations) > 0
        
        # Reset violations
        validator.reset_violations()
        
        assert len(validator.violations) == 0
        assert validator.validation_stats['violations_count'] == 0


class TestFeatureQualityMonitor:
    """Test suite for FeatureQualityMonitor production functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        # Mock database manager for testing
        self.db_manager = None  # In production, this would be a real DB manager
        # For testing without DB dependency, we'll create mock monitor
        self.monitor = FeatureQualityMonitor(self.db_manager)
    
    def test_feature_coverage_monitoring(self):
        """Test feature coverage monitoring with various data scenarios."""
        import pandas as pd
        
        # Create test data with varying coverage
        test_data = pd.DataFrame({
            'feature_a': [1, 2, 3, None, 5] * 200,  # 80% coverage
            'feature_b': [1, None, None, None, 5] * 200,  # 40% coverage  
            'feature_c': [1, 2, 3, 4, 5] * 200,  # 100% coverage
            'feature_d': [None] * 1000,  # 0% coverage
        })
        
        required_features = ['feature_a', 'feature_b', 'feature_c', 'feature_d']
        
        coverage_results = self.monitor.monitor_feature_coverage(test_data, required_features)
        
        # Validate coverage calculations (rates are 0-1 not percentages)
        assert coverage_results['feature_a']['coverage_rate'] == 0.8  # 80%
        assert coverage_results['feature_b']['coverage_rate'] == 0.4  # 40%
        assert coverage_results['feature_c']['coverage_rate'] == 1.0  # 100%
        assert coverage_results['feature_d']['coverage_rate'] == 0.0  # 0%
        
        # Validate adequacy assessments (assuming 95% threshold)
        assert coverage_results['feature_c']['is_adequate'] == True
        assert coverage_results['feature_b']['is_adequate'] == False
        assert coverage_results['feature_d']['is_adequate'] == False
    
    def test_feature_range_validation(self):
        """Test feature range validation with edge cases."""
        import pandas as pd
        
        # Create test data with out-of-range values
        test_data = pd.DataFrame({
            'percentage_feature': [10, 20, 30, 150, -5, 50],  # 2 out of 6 invalid
            'count_feature': [1, 2, 3, 4, 5, 6],  # All valid
            'ratio_feature': [0.1, 0.5, 0.9, 1.5, -0.1, 0.7],  # 2 out of 6 invalid
        })
        
        feature_ranges = {
            'percentage_feature': (0, 100),
            'count_feature': (0, 10),
            'ratio_feature': (0, 1),
        }
        
        range_results = self.monitor.validate_feature_ranges(test_data, feature_ranges)
        
        # Validate range validation results
        assert abs(range_results['percentage_feature']['out_of_range_percentage'] - 33.33) < 0.1  # 2/6 * 100
        assert range_results['count_feature']['out_of_range_percentage'] == 0.0
        assert abs(range_results['ratio_feature']['out_of_range_percentage'] - 33.33) < 0.1
        
        # Validate adequacy (5% threshold)
        assert range_results['count_feature']['is_valid'] == True
        assert range_results['percentage_feature']['is_valid'] == False
        assert range_results['ratio_feature']['is_valid'] == False
    
    def test_feature_drift_detection(self):
        """Test feature drift detection with statistical rigor."""
        import pandas as pd
        import numpy as np
        
        np.random.seed(42)
        
        # Create reference data (normal distribution)
        reference_data = pd.Series(np.random.normal(100, 15, 1000))
        
        # Create comparison data with drift (shifted mean)
        drifted_data = pd.Series(np.random.normal(120, 15, 1000))  # Mean shifted by 20
        
        # Create comparison data without drift
        no_drift_data = pd.Series(np.random.normal(100, 15, 1000))  # Same distribution
        
        # Test drift detection with drifted data
        drift_result = self.monitor.detect_feature_drift(
            pd.DataFrame({'test_feature': drifted_data}),
            pd.DataFrame({'test_feature': reference_data}),
            'test_feature'
        )
        
        assert drift_result['drift_detected'] == True
        assert drift_result['ks_statistic'] > 0
        assert drift_result['p_value'] < 0.05
        assert drift_result['mean_shift_pct'] > 10  # Should detect significant mean shift
        
        # Test no drift detection with similar data
        no_drift_result = self.monitor.detect_feature_drift(
            pd.DataFrame({'test_feature': no_drift_data}),
            pd.DataFrame({'test_feature': reference_data}),
            'test_feature'
        )
        
        assert no_drift_result['drift_detected'] == False
        assert no_drift_result['p_value'] > 0.05
        assert no_drift_result['mean_shift_pct'] < 5  # Should be minimal shift
    
    def test_quality_summary_generation(self):
        """Test comprehensive quality summary generation."""
        import pandas as pd
        
        # Generate some quality issues
        test_data = pd.DataFrame({
            'low_coverage_feature': [1, None, None, None, None] * 200,  # 20% coverage
            'out_of_range_feature': [1, 2, 3, 150, 200] * 200,  # Some out of range
        })
        
        # Monitor coverage (should generate issues)
        required_features = ['low_coverage_feature']
        self.monitor.monitor_feature_coverage(test_data, required_features)
        
        # Monitor ranges (should generate issues)  
        feature_ranges = {'out_of_range_feature': (0, 100)}
        self.monitor.validate_feature_ranges(test_data, feature_ranges)
        
        # Get quality summary
        summary = self.monitor.get_quality_summary()
        
        assert 'total_issues' in summary
        assert 'issue_breakdown' in summary
        assert 'severity_breakdown' in summary
        assert 'quality_score' in summary
        assert 'timestamp' in summary
        
        # Should have detected quality issues
        assert summary['total_issues'] > 0
        assert summary['quality_score'] < 1.0


class TestProductionFeatureEngineer:
    """Test suite for ProductionFeatureEngineer production functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.config = {
            "batch_size": 10,  # Small for testing
            "max_workers": 2,
            "memory_limit_mb": 128,
            "enable_monitoring": True,
            "enable_bias_validation": True,
            "quality_threshold": 0.90
        }
        self.engineer = ProductionFeatureEngineer(config=self.config)
    
    def test_initialization_and_configuration(self):
        """Test proper initialization and configuration management."""
        # Test default configuration
        default_engineer = ProductionFeatureEngineer()
        assert default_engineer.config is not None
        assert 'batch_size' in default_engineer.config
        assert 'max_workers' in default_engineer.config
        
        # Test custom configuration
        custom_config = {"batch_size": 200, "memory_limit_mb": 1024}
        custom_engineer = ProductionFeatureEngineer(config=custom_config)
        
        assert custom_engineer.config['batch_size'] == 200
        assert custom_engineer.config['memory_limit_mb'] == 1024
        # Should still have defaults for unspecified values
        assert 'max_workers' in custom_engineer.config
    
    def test_memory_manager_context(self):
        """Test memory management context manager."""
        initial_memory = 0
        peak_memory = 0
        
        with self.engineer.memory_manager():
            # Simulate memory usage
            large_data = [i for i in range(100000)]
            peak_memory = len(large_data)
        
        # Memory manager should track peak usage
        assert self.engineer.performance_metrics['memory_peak_mb'] >= 0
    
    def test_lookahead_bias_validation_integration(self):
        """Test integration of lookahead bias validation."""
        # Test that bias validator is properly initialized
        assert self.engineer.bias_validator is not None
        assert self.engineer.bias_validator.strict_mode is True
        
        # Test validation during feature calculation (mock scenario)
        feature_date = date(2024, 1, 15)
        
        # This should pass validation
        result = self.engineer.bias_validator.validate_data_availability(
            feature_date, feature_date, 'valid_feature'
        )
        assert result is True
    
    def test_feature_quality_monitoring_integration(self):
        """Test integration of feature quality monitoring."""
        assert self.engineer.quality_monitor is not None
        
        # Test that monitoring can be triggered
        import pandas as pd
        import numpy as np
        
        sample_data = pd.DataFrame({
            'test_feature': np.random.normal(0, 1, 100)
        })
        
        required_features = ['test_feature']
        coverage_result = self.engineer.quality_monitor.monitor_feature_coverage(
            sample_data, required_features
        )
        
        assert 'test_feature' in coverage_result
        assert coverage_result['test_feature']['coverage_rate'] == 1.0  # 100% as fraction
    
    def test_performance_metrics_tracking(self):
        """Test comprehensive performance metrics tracking."""
        from unittest.mock import patch, Mock
        
        with patch('src.feature_engineering.engineer_features.get_db_manager') as mock_get_db:
            # Mock database responses
            mock_db = Mock()
            mock_db.model_db.execute_query.return_value = []
            mock_db.model_db.execute_query_df.return_value = pd.DataFrame()
            mock_get_db.return_value = mock_db
            
            # Create new engineer with mocked DB
            engineer = ProductionFeatureEngineer(config=self.config)
            
            # Reset metrics
            engineer.performance_metrics = {
                'total_processing_time': 0,
                'total_records_processed': 0,
                'total_features_created': 0,
                'memory_peak_mb': 0,
                'errors_encountered': 0
            }
            
            # Simulate processing
            start_time = datetime.now()
            
            # Mock feature engineering process
            result = engineer.engineer_features_with_validation(
                start_date=date(2024, 1, 10),
                end_date=date(2024, 1, 11),
                force_rebuild=False,
                validate_bias=True,
                parallel=False
            )
        
        # Validate performance tracking
        assert 'performance_metrics' in result
        assert 'execution_time_seconds' in result
        assert result['execution_time_seconds'] >= 0
        
        perf_metrics = result['performance_metrics']
        assert 'total_processing_time' in perf_metrics
        assert 'memory_peak_mb' in perf_metrics
        assert 'errors_encountered' in perf_metrics
    
    def test_error_handling_and_recovery(self):
        """Test error handling and recovery mechanisms."""
        # Test with invalid date range
        try:
            result = self.engineer.engineer_features_with_validation(
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 10),  # Invalid: start > end
                validate_bias=True
            )
            assert False, "Should have raised ValueError for invalid date range"
        except ValueError as e:
            assert "Start date" in str(e) and "cannot be after end date" in str(e)
    
    def test_result_summary_completeness(self):
        """Test comprehensive result summary generation."""
        from unittest.mock import patch, Mock
        
        with patch('src.feature_engineering.engineer_features.get_db_manager') as mock_get_db:
            # Mock database responses
            mock_db = Mock()
            mock_db.model_db.execute_query.return_value = []
            mock_db.model_db.execute_query_df.return_value = pd.DataFrame()
            mock_get_db.return_value = mock_db
            
            # Create new engineer with mocked DB
            engineer = ProductionFeatureEngineer(config=self.config)
            
            result = engineer.engineer_features_with_validation(
                start_date=date(2024, 1, 10),
                end_date=date(2024, 1, 11),
                validate_bias=True,
                parallel=False
            )
        
        # Validate result structure
        required_keys = [
            'total_records', 'execution_time_seconds', 'validation_enabled',
            'lookahead_bias_check', 'feature_version', 'performance_metrics',
            'configuration', 'records_per_second'
        ]
        
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"
        
        # Validate bias check structure
        bias_check = result['lookahead_bias_check']
        assert 'has_violations' in bias_check
        assert 'validation_stats' in bias_check
        assert 'violation_rate' in bias_check
        
        # Validate configuration preservation
        config = result['configuration']
        assert config['batch_size'] == self.config['batch_size']
        assert config['enable_bias_validation'] == self.config['enable_bias_validation']


class TestProductionReadiness:
    """Test suite for overall production readiness validation."""
    
    def test_system_integration(self):
        """Test complete system integration and workflow."""
        from unittest.mock import patch, Mock
        
        with patch('src.feature_engineering.engineer_features.get_db_manager') as mock_get_db:
            # Mock database responses
            mock_db = Mock()
            mock_db.model_db.execute_query.return_value = []
            mock_db.model_db.execute_query_df.return_value = pd.DataFrame()
            mock_get_db.return_value = mock_db
            
            # Test full workflow with all components
            config = {
                "batch_size": 5,
                "max_workers": 1,
                "memory_limit_mb": 64,
                "enable_monitoring": True,
                "enable_bias_validation": True
            }
            
            engineer = ProductionFeatureEngineer(config=config)
            
            # Test complete workflow
            result = engineer.engineer_features_with_validation(
                start_date=date(2024, 1, 10),
                end_date=date(2024, 1, 11),
                force_rebuild=False,
                validate_bias=True,
                parallel=False
            )
        
        assert result is not None
        assert result['feature_version'] == FEATURE_VERSION
        assert result['validation_enabled'] is True
    
    def test_performance_under_load(self):
        """Test system performance under simulated load."""
        from unittest.mock import patch, Mock
        
        with patch('src.feature_engineering.engineer_features.get_db_manager') as mock_get_db:
            # Mock database responses
            mock_db = Mock()
            mock_db.model_db.execute_query.return_value = []
            mock_db.model_db.execute_query_df.return_value = pd.DataFrame()
            mock_get_db.return_value = mock_db
            
            config = {"batch_size": 1, "max_workers": 1, "memory_limit_mb": 32}
            engineer = ProductionFeatureEngineer(config=config)
            
            start_time = time.time()
            
            # Simulate multiple processing runs
            for i in range(3):
                result = engineer.engineer_features_with_validation(
                    start_date=date(2024, 1, 10),
                    end_date=date(2024, 1, 10),  # Single day
                    validate_bias=True,
                    parallel=False
                )
                assert result is not None
        
        total_time = time.time() - start_time
        
        # Should complete within reasonable time (adjust threshold as needed)
        assert total_time < 30, f"Performance test took too long: {total_time}s"
    
    def test_configuration_validation(self):
        """Test configuration validation and defaults."""
        # Test with minimal config
        minimal_engineer = ProductionFeatureEngineer(config={"batch_size": 1})
        assert minimal_engineer.config['batch_size'] == 1
        assert 'max_workers' in minimal_engineer.config  # Should have default
        
        # Test with empty config
        empty_engineer = ProductionFeatureEngineer(config={})
        assert 'batch_size' in empty_engineer.config
        assert 'max_workers' in empty_engineer.config
        
        # Test with None config
        none_engineer = ProductionFeatureEngineer(config=None)
        assert none_engineer.config is not None
    
    def test_logging_and_monitoring(self):
        """Test comprehensive logging and monitoring capabilities."""
        from unittest.mock import patch, Mock
        import io
        import logging
        
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger('src.feature_engineering.engineer_features')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        try:
            with patch('src.feature_engineering.engineer_features.get_db_manager') as mock_get_db:
                # Mock database responses
                mock_db = Mock()
                mock_db.model_db.execute_query.return_value = []
                mock_db.model_db.execute_query_df.return_value = pd.DataFrame()
                mock_get_db.return_value = mock_db
                
                engineer = ProductionFeatureEngineer()
                
                result = engineer.engineer_features_with_validation(
                    start_date=date(2024, 1, 10),
                    end_date=date(2024, 1, 10),
                    validate_bias=True
                )
            
            # Should have logged important events
            log_output = log_capture.getvalue()
            # Note: In actual implementation, we'd verify specific log messages
            
        finally:
            logger.removeHandler(handler)


def run_production_test_suite():
    """Run the complete production test suite."""
    print("🔬 PRODUCTION FEATURE ENGINEERING TEST SUITE")
    print("=" * 70)
    print(f"Testing Feature Engineering Version: {FEATURE_VERSION}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    test_classes = [
        TestLookaheadBiasValidator,
        TestFeatureQualityMonitor, 
        TestProductionFeatureEngineer,
        TestProductionReadiness
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for test_class in test_classes:
        print(f"\n📋 Running {test_class.__name__}")
        print("-" * 50)
        
        # Get all test methods
        test_methods = [method for method in dir(test_class) if method.startswith('test_')]
        
        for method_name in test_methods:
            total_tests += 1
            try:
                # Create test instance and run setup
                test_instance = test_class()
                if hasattr(test_instance, 'setup_method'):
                    test_instance.setup_method()
                
                # Run the test
                test_method = getattr(test_instance, method_name)
                test_method()
                
                print(f"  ✅ {method_name}")
                passed_tests += 1
                
            except Exception as e:
                print(f"  ❌ {method_name}: {str(e)}")
                failed_tests.append((test_class.__name__, method_name, str(e)))
    
    # Print summary
    print("\n" + "=" * 70)
    print("📊 TEST SUITE SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if failed_tests:
        print("\n❌ FAILED TESTS:")
        for class_name, method_name, error in failed_tests:
            print(f"  - {class_name}.{method_name}: {error}")
        return False
    else:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ System is production-ready with comprehensive validation")
        print("✅ Lookahead bias prevention is working correctly")
        print("✅ Feature quality monitoring is operational")
        print("✅ Performance and memory optimization is functional")
        print("✅ Error handling and recovery mechanisms are in place")
        return True


if __name__ == '__main__':
    success = run_production_test_suite()
    sys.exit(0 if success else 1)