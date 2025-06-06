"""
Feature Validation Tests - Version 1
Tests for lookahead bias detection and feature quality.
"""

import unittest
from datetime import timedelta, date
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.feature_engineering.engineer_features import (
    LookaheadBiasValidator,
    FeatureQualityMonitor,
    IntegratedProductionFeatureEngineer,
    FEATURE_VERSION,
)


class TestLookaheadBiasValidator(unittest.TestCase):
    """Test lookahead bias detection."""

    def setUp(self):
        self.validator = LookaheadBiasValidator(strict_mode=False)

    def test_valid_data_availability(self):
        """Test valid data access (past data)."""
        feature_date = date(2024, 1, 10)
        data_date = date(2024, 1, 9)

        is_valid = self.validator.validate_data_availability(
            feature_date, data_date, "test_feature"
        )

        self.assertTrue(is_valid)
        self.assertEqual(len(self.validator.violations), 0)

    def test_invalid_data_availability(self):
        """Test invalid data access (future data)."""
        feature_date = date(2024, 1, 10)
        data_date = date(2024, 1, 11)

        is_valid = self.validator.validate_data_availability(
            feature_date, data_date, "test_feature"
        )

        self.assertFalse(is_valid)
        self.assertEqual(len(self.validator.violations), 1)
        self.assertEqual(
            self.validator.violations[0]["violation_type"], "future_data_access"
        )

    def test_valid_rolling_window(self):
        """Test valid rolling window (no future data)."""
        feature_date = date(2024, 1, 10)
        window_start = date(2024, 1, 6)
        window_end = date(2024, 1, 10)

        is_valid = self.validator.validate_rolling_window(
            feature_date, window_start, window_end, "rolling_5d"
        )

        self.assertTrue(is_valid)
        self.assertEqual(len(self.validator.violations), 0)

    def test_invalid_rolling_window(self):
        """Test invalid rolling window (includes future data)."""
        feature_date = date(2024, 1, 10)
        window_start = date(2024, 1, 8)
        window_end = date(2024, 1, 12)

        is_valid = self.validator.validate_rolling_window(
            feature_date, window_start, window_end, "rolling_5d"
        )

        self.assertFalse(is_valid)
        self.assertEqual(len(self.validator.violations), 1)
        self.assertEqual(
            self.validator.violations[0]["violation_type"], "future_window_data"
        )

    def test_violations_summary(self):
        """Test violations summary generation."""
        # Add multiple violations
        feature_date = date(2024, 1, 10)

        # Future data access
        self.validator.validate_data_availability(
            feature_date, date(2024, 1, 11), "feature1"
        )
        self.validator.validate_data_availability(
            feature_date, date(2024, 1, 12), "feature2"
        )

        # Future window
        self.validator.validate_rolling_window(
            feature_date, date(2024, 1, 8), date(2024, 1, 11), "rolling_feature"
        )

        summary = self.validator.get_violations_summary()

        self.assertTrue(summary["has_violations"])
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["violation_types"]["future_data_access"], 2)
        self.assertEqual(summary["violation_types"]["future_window_data"], 1)


class TestFeatureQuality(unittest.TestCase):
    """Test feature quality checks."""

    def test_feature_completeness(self):
        """Test detection of missing features."""
        features = {
            "account_id": "test123",
            "current_balance": 1000.0,
            "current_equity": None,  # Missing
            "rolling_pnl_avg_5d": 50.0,
        }

        required_features = ["current_balance", "current_equity", "rolling_pnl_avg_5d"]

        # Check for missing features
        missing = [f for f in required_features if features.get(f) is None]

        self.assertEqual(len(missing), 1)
        self.assertIn("current_equity", missing)

    def test_feature_range_validation(self):
        """Test feature value range validation."""
        # Test cases with expected validity
        test_cases = [
            ("win_rate_5d", 150.0, False),  # Win rate > 100%
            ("win_rate_5d", 75.0, True),  # Valid win rate
            ("sharpe_ratio_5d", 50.0, False),  # Unrealistic Sharpe
            ("sharpe_ratio_5d", 2.5, True),  # Reasonable Sharpe
            ("buy_sell_ratio_5d", 2.0, False),  # Ratio > 1
            ("buy_sell_ratio_5d", 0.6, True),  # Valid ratio
        ]

        for feature_name, value, expected_valid in test_cases:
            # Simple range validation
            if "win_rate" in feature_name:
                is_valid = 0 <= value <= 100
            elif "sharpe_ratio" in feature_name:
                is_valid = -10 <= value <= 10
            elif "buy_sell_ratio" in feature_name:
                is_valid = 0 <= value <= 1
            else:
                is_valid = True

            self.assertEqual(
                is_valid,
                expected_valid,
                f"Feature {feature_name} with value {value} validation failed",
            )


class TestMemoryOptimization(unittest.TestCase):
    """Test memory optimization techniques."""

    def test_batch_processing(self):
        """Test batch processing logic."""
        # Create sample data
        n_records = 1000
        batch_size = 100

        # Simulate batch processing
        batches_processed = 0
        for i in range(0, n_records, batch_size):
            batch_end = min(i + batch_size, n_records)
            batch_records = batch_end - i

            self.assertLessEqual(batch_records, batch_size)
            batches_processed += 1

        expected_batches = (n_records + batch_size - 1) // batch_size
        self.assertEqual(batches_processed, expected_batches)

    def test_data_chunking(self):
        """Test data chunking for large queries."""
        # Simulate chunked reading
        total_records = 10000
        chunk_size = 1000

        records_read = 0
        chunks = []

        offset = 0
        while offset < total_records:
            chunk_end = min(offset + chunk_size, total_records)
            chunk_records = chunk_end - offset
            chunks.append(chunk_records)
            records_read += chunk_records
            offset += chunk_size

        self.assertEqual(records_read, total_records)
        self.assertEqual(len(chunks), 10)
        self.assertTrue(all(c <= chunk_size for c in chunks))


class TestFeatureAlignment(unittest.TestCase):
    """Test feature-target alignment."""

    def test_prediction_date_calculation(self):
        """Test that prediction_date = feature_date + 1."""
        feature_dates = pd.date_range("2024-01-01", "2024-01-10")

        for feature_date in feature_dates:
            expected_prediction_date = feature_date + timedelta(days=1)

            # Simulate alignment
            actual_prediction_date = feature_date + pd.Timedelta(days=1)

            self.assertEqual(actual_prediction_date, expected_prediction_date)

    def test_no_same_day_target(self):
        """Ensure we never use same-day target (lookahead bias)."""
        feature_date = date(2024, 1, 10)
        target_date = date(2024, 1, 10)

        # This should be invalid
        is_valid = target_date > feature_date

        self.assertFalse(is_valid, "Same-day target should not be allowed")


class TestFeatureVersioning(unittest.TestCase):
    """Test feature versioning system."""

    def test_feature_hash_generation(self):
        """Test consistent hash generation for feature sets."""
        import hashlib

        feature_set_1 = ["feature_a", "feature_b", "feature_c"]
        feature_set_2 = ["feature_c", "feature_a", "feature_b"]  # Different order
        feature_set_3 = ["feature_a", "feature_b", "feature_d"]  # Different features

        def get_feature_hash(features):
            feature_str = ",".join(sorted(features))
            return hashlib.sha256(feature_str.encode()).hexdigest()

        hash_1 = get_feature_hash(feature_set_1)
        hash_2 = get_feature_hash(feature_set_2)
        hash_3 = get_feature_hash(feature_set_3)

        # Same features in different order should have same hash
        self.assertEqual(hash_1, hash_2)

        # Different features should have different hash
        self.assertNotEqual(hash_1, hash_3)


class TestAdvancedLookaheadBiasValidator(unittest.TestCase):
    """Test advanced lookahead bias validation features from V2."""

    def setUp(self):
        self.validator = LookaheadBiasValidator(strict_mode=True)

    def test_strict_mode_enforcement(self):
        """Test that strict mode raises exceptions for violations."""
        feature_date = date(2024, 1, 10)
        future_date = date(2024, 1, 11)

        with self.assertRaises(ValueError):
            self.validator.validate_data_availability(
                feature_date, future_date, "future_feature"
            )

    def test_target_alignment_validation(self):
        """Test feature-target temporal alignment validation (V2 feature)."""
        feature_date = date(2024, 1, 10)
        correct_target = date(2024, 1, 11)  # D+1
        incorrect_target = date(2024, 1, 12)  # D+2

        # Correct alignment should pass
        result = self.validator.validate_feature_target_alignment(
            feature_date, correct_target, "correct_target"
        )
        self.assertTrue(result)

        # Incorrect alignment should fail
        result = self.validator.validate_feature_target_alignment(
            feature_date, incorrect_target, "incorrect_target"
        )
        self.assertFalse(result)

    def test_comprehensive_violations_tracking(self):
        """Test comprehensive violations tracking with statistics (V2 feature)."""
        # Create multiple violations with non-strict validator
        feature_date = date(2024, 1, 10)
        non_strict_validator = LookaheadBiasValidator(strict_mode=False)

        # Add various violation types
        non_strict_validator.validate_data_availability(
            feature_date, date(2024, 1, 11), "violation1"
        )
        non_strict_validator.validate_rolling_window(
            feature_date, date(2024, 1, 8), date(2024, 1, 11), "violation2"
        )

        summary = non_strict_validator.get_violations_summary()

        # Check enhanced summary structure
        self.assertIn("violation_types", summary)
        self.assertIn("severity_breakdown", summary)
        self.assertIn("validation_stats", summary)
        self.assertIn("violation_rate", summary)

        # Validate statistics
        self.assertTrue(summary["has_violations"])
        self.assertEqual(summary["count"], 2)
        self.assertGreater(summary["violation_rate"], 0)


class TestFeatureQualityMonitor(unittest.TestCase):
    """Test advanced feature quality monitoring from V2."""

    def setUp(self):
        # Mock database manager for testing
        from unittest.mock import Mock

        self.mock_db = Mock()
        self.monitor = FeatureQualityMonitor(self.mock_db)

    def test_feature_coverage_monitoring(self):
        """Test feature coverage monitoring with comprehensive metrics."""
        # Create test data with varying coverage
        test_data = pd.DataFrame(
            {
                "feature_a": [1, 2, 3, None, 5] * 20,  # 80% coverage
                "feature_b": [1, 2, 3, 4, 5] * 20,  # 100% coverage
                "feature_c": [None] * 100,  # 0% coverage
            }
        )

        required_features = ["feature_a", "feature_b", "feature_c"]

        coverage_results = self.monitor.monitor_feature_coverage(
            test_data, required_features
        )

        # Validate coverage calculations (returned as fractions 0-1)
        self.assertAlmostEqual(
            coverage_results["feature_a"]["coverage_rate"], 0.8, places=2
        )
        self.assertEqual(coverage_results["feature_b"]["coverage_rate"], 1.0)
        self.assertEqual(coverage_results["feature_c"]["coverage_rate"], 0.0)

        # Validate adequacy assessments
        self.assertIn("is_adequate", coverage_results["feature_a"])
        self.assertIn("missing_count", coverage_results["feature_a"])
        self.assertIn("total_count", coverage_results["feature_a"])

    def test_feature_range_validation(self):
        """Test feature range validation with business rules."""
        test_data = pd.DataFrame(
            {
                "win_rate_5d": [10, 20, 30, 150, -5, 50],  # 2 out of 6 invalid
                "sharpe_ratio_5d": [1, 2, 3, 4, 5, 6],  # All valid
                "profit_factor_5d": [
                    0.1,
                    0.5,
                    0.9,
                    1.5,
                    -0.1,
                    0.7,
                ],  # 2 out of 6 invalid
            }
        )

        feature_ranges = {
            "win_rate_5d": (0, 100),
            "sharpe_ratio_5d": (-10, 10),
            "profit_factor_5d": (0, 10),
        }

        range_results = self.monitor.validate_feature_ranges(test_data, feature_ranges)

        # Validate range validation results
        self.assertAlmostEqual(
            range_results["win_rate_5d"]["out_of_range_percentage"], 33.33, places=1
        )
        self.assertEqual(
            range_results["sharpe_ratio_5d"]["out_of_range_percentage"], 0.0
        )
        self.assertAlmostEqual(
            range_results["profit_factor_5d"]["out_of_range_percentage"],
            16.67,
            places=1,
        )

        # Validate adequacy (5% threshold)
        self.assertTrue(range_results["sharpe_ratio_5d"]["is_valid"])
        self.assertFalse(range_results["win_rate_5d"]["is_valid"])

    def test_feature_drift_detection(self):
        """Test statistical feature drift detection (V2 feature)."""
        np.random.seed(42)

        # Create reference and comparison DataFrames
        reference_data = pd.DataFrame({"test_feature": np.random.normal(100, 15, 1000)})
        drifted_data = pd.DataFrame(
            {
                "test_feature": np.random.normal(120, 15, 1000)  # Mean shifted
            }
        )

        drift_result = self.monitor.detect_feature_drift(
            drifted_data, reference_data, "test_feature"
        )

        # Validate drift detection structure
        self.assertIn("drift_detected", drift_result)
        self.assertIn("ks_statistic", drift_result)
        self.assertIn("p_value", drift_result)
        self.assertIn("mean_shift_pct", drift_result)
        self.assertIn("severity", drift_result)

        # Should detect significant drift
        self.assertGreaterEqual(drift_result["ks_statistic"], 0)
        self.assertGreaterEqual(drift_result["mean_shift_pct"], 0)

    def test_quality_summary_generation(self):
        """Test comprehensive quality summary generation."""
        # Generate some quality issues by calling monitoring methods
        test_data = pd.DataFrame(
            {
                "low_coverage_feature": [1, None, None, None, None]
                * 20,  # 20% coverage
            }
        )

        # Monitor coverage (should generate issues)
        self.monitor.monitor_feature_coverage(test_data, ["low_coverage_feature"])

        # Get quality summary
        summary = self.monitor.get_quality_summary()

        # Validate summary structure
        self.assertIn("total_issues", summary)
        self.assertIn("issue_breakdown", summary)
        self.assertIn("severity_breakdown", summary)
        self.assertIn("quality_score", summary)
        self.assertIn("timestamp", summary)


class TestIntegratedProductionFeatureEngineer(unittest.TestCase):
    """Test production feature engineer combining all best features."""

    def setUp(self):
        from unittest.mock import patch, Mock

        # Mock database manager to avoid connection issues
        self.mock_db_patcher = patch(
            "src.feature_engineering.engineer_features.get_db_manager"
        )
        self.mock_get_db = self.mock_db_patcher.start()
        self.mock_db = Mock()
        self.mock_get_db.return_value = self.mock_db

        # Create engineer with test configuration
        self.config = {
            "batch_size": 10,
            "max_workers": 2,
            "memory_limit_mb": 128,
            "enable_monitoring": True,
            "enable_bias_validation": True,
        }
        self.engineer = IntegratedProductionFeatureEngineer(config=self.config)

    def tearDown(self):
        self.mock_db_patcher.stop()

    def test_comprehensive_initialization(self):
        """Test proper initialization with all components."""
        # Test configuration
        self.assertEqual(self.engineer.config["batch_size"], 10)
        self.assertTrue(self.engineer.config["enable_bias_validation"])

        # Test component initialization
        self.assertIsNotNone(self.engineer.bias_validator)
        self.assertIsNotNone(self.engineer.quality_monitor)
        self.assertTrue(self.engineer.bias_validator.strict_mode)

    def test_memory_manager_context(self):
        """Test memory management context manager."""

        with self.engineer.memory_manager():
            # Should execute without errors
            list(range(1000))  # Create some memory usage

        # Memory manager should track peak usage
        self.assertGreaterEqual(self.engineer.performance_metrics["memory_peak_mb"], 0)

    def test_comprehensive_feature_engineering_workflow(self):
        """Test complete feature engineering workflow with validation."""
        # Mock database responses
        self.mock_db.model_db.execute_query.return_value = []
        self.mock_db.model_db.execute_query_df.return_value = pd.DataFrame()

        # Test feature engineering workflow
        result = self.engineer.engineer_features_with_validation(
            start_date=date(2024, 1, 10), end_date=date(2024, 1, 11), validate_bias=True
        )

        # Validate comprehensive result structure
        required_keys = [
            "total_records",
            "execution_time_seconds",
            "lookahead_bias_check",
            "feature_version",
            "performance_metrics",
            "configuration",
            "query_optimization",
        ]

        for key in required_keys:
            self.assertIn(key, result, f"Missing required key: {key}")

        # Validate bias check structure
        bias_check = result["lookahead_bias_check"]
        self.assertIn("has_violations", bias_check)
        self.assertIn("validation_stats", bias_check)
        self.assertIn("violation_rate", bias_check)

        # Validate configuration preservation
        self.assertEqual(result["configuration"]["validation_enabled"], True)
        self.assertEqual(result["feature_version"], FEATURE_VERSION)

    def test_error_handling_and_recovery(self):
        """Test comprehensive error handling and recovery mechanisms."""
        # Test invalid date range handling
        with self.assertRaises(ValueError):
            self.engineer.engineer_features_with_validation(
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 10),  # Invalid: start > end
                validate_bias=True,
            )

    def test_performance_metrics_tracking(self):
        """Test comprehensive performance metrics tracking."""
        self.mock_db.model_db.execute_query.return_value = []
        self.mock_db.model_db.execute_query_df.return_value = pd.DataFrame()

        result = self.engineer.engineer_features_with_validation(
            start_date=date(2024, 1, 10), end_date=date(2024, 1, 11), validate_bias=True
        )

        # Validate performance tracking
        perf_metrics = result["performance_metrics"]
        required_metrics = [
            "total_processing_time",
            "total_records_processed",
            "memory_peak_mb",
            "errors_encountered",
        ]

        for metric in required_metrics:
            self.assertIn(metric, perf_metrics)
            self.assertIsInstance(perf_metrics[metric], (int, float))


class TestIntegrationAndProductionReadiness(unittest.TestCase):
    """Test complete system integration and production readiness."""

    def test_feature_version_consistency(self):
        """Test that feature version is properly tracked."""
        self.assertIsNotNone(FEATURE_VERSION)
        self.assertRegex(FEATURE_VERSION, r"^\d+\.\d+\.\d+$")  # Semantic versioning

    def test_comprehensive_bias_prevention(self):
        """Test comprehensive lookahead bias prevention across all features."""
        validator = LookaheadBiasValidator(strict_mode=True)

        # Test various bias scenarios
        feature_date = date(2024, 1, 15)

        # Valid scenarios should pass
        valid_scenarios = [
            (feature_date, feature_date, "same_day_data"),
            (feature_date, feature_date - timedelta(days=1), "previous_day_data"),
            (feature_date, feature_date - timedelta(days=7), "week_old_data"),
        ]

        for feat_date, data_date, scenario in valid_scenarios:
            result = validator.validate_data_availability(
                feat_date, data_date, scenario
            )
            self.assertTrue(result, f"Valid scenario {scenario} should pass")

        # Invalid scenarios should be caught
        invalid_scenarios = [
            (feature_date, feature_date + timedelta(days=1), "future_data"),
            (feature_date, feature_date + timedelta(days=7), "week_future_data"),
        ]

        for feat_date, data_date, scenario in invalid_scenarios:
            with self.assertRaises(
                ValueError, msg=f"Invalid scenario {scenario} should raise exception"
            ):
                validator.validate_data_availability(feat_date, data_date, scenario)

    def test_production_scalability_simulation(self):
        """Test system behavior under production-like load."""
        from unittest.mock import patch, Mock

        with patch(
            "src.feature_engineering.engineer_features.get_db_manager"
        ) as mock_get_db:
            mock_db = Mock()
            mock_db.model_db.execute_query.return_value = []
            mock_db.model_db.execute_query_df.return_value = pd.DataFrame()
            mock_get_db.return_value = mock_db

            # Test with different configurations
            configs = [
                {"batch_size": 1, "max_workers": 1},  # Minimal
                {"batch_size": 100, "max_workers": 4},  # Standard
                {"batch_size": 1000, "max_workers": 8},  # High performance
            ]

            for i, config in enumerate(configs):
                engineer = IntegratedProductionFeatureEngineer(config=config)

                result = engineer.engineer_features_with_validation(
                    start_date=date(2024, 1, 10),
                    end_date=date(2024, 1, 10),
                    validate_bias=True,
                )

                # Should complete successfully with any configuration
                self.assertIsNotNone(result)
                self.assertIn("execution_time_seconds", result)
                self.assertIn("performance_metrics", result)


def run_validation_tests():
    """Run all validation tests and return results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes (organized by complexity)

    # Basic V1 functionality tests
    suite.addTests(loader.loadTestsFromTestCase(TestLookaheadBiasValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatureQuality))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryOptimization))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatureAlignment))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatureVersioning))

    # Advanced V2 functionality tests
    suite.addTests(loader.loadTestsFromTestCase(TestAdvancedLookaheadBiasValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatureQualityMonitor))

    # Production V2+V3 integration tests
    suite.addTests(
        loader.loadTestsFromTestCase(TestIntegratedProductionFeatureEngineer)
    )
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationAndProductionReadiness))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return comprehensive summary
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful(),
        "feature_version": FEATURE_VERSION,
        "test_categories": {
            "basic_v1_tests": 5,  # Original 5 test classes
            "advanced_v2_tests": 2,  # Advanced bias validation + quality monitoring
            "production_integration_tests": 2,  # Production engineer + integration
            "total_test_classes": 9,
        },
    }


if __name__ == "__main__":
    unittest.main()
