"""
Unit tests for data validation in preprocessing pipeline.
"""

import unittest
from datetime import date, datetime
from unittest.mock import Mock
import sys
import os
import warnings

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

# Suppress deprecation warnings for DataValidator in tests
# We still need to test the deprecated class
warnings.filterwarnings("ignore", message="DataValidator is deprecated", category=DeprecationWarning)

from preprocessing.data_validator import (
    DataValidator,
    ValidationResult,
    ValidationStatus,
)
from preprocessing.data_quality_rules import RuleType, get_rules_for_table


class TestDataValidator(unittest.TestCase):
    """Test cases for DataValidator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db_manager = Mock()
        self.mock_db_manager.model_db = Mock()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            self.validator = DataValidator(self.mock_db_manager)
        self.test_date = date(2024, 1, 15)

    def test_validate_staging_snapshot_no_data(self):
        """Test validation when no data exists for the date."""
        # Mock no data found
        self.mock_db_manager.model_db.execute_query.return_value = [{"count": 0}]

        results = self.validator.validate_staging_snapshot(self.test_date)

        # Should have at least one failed result for no data
        failed_results = [r for r in results if r.status == ValidationStatus.FAILED]
        self.assertGreater(len(failed_results), 0)
        self.assertEqual(failed_results[0].rule_name, "data_completeness_check")

    def test_validate_staging_snapshot_with_nulls(self):
        """Test validation with null values in critical fields."""
        # Mock data with nulls
        self.mock_db_manager.model_db.execute_query.side_effect = [
            [{"count": 100}],  # Has data
            [
                {  # Null check results
                    "total_records": 100,
                    "null_account_id": 5,
                    "null_login": 0,
                    "null_balance": 10,
                    "null_equity": 8,
                    "null_starting_balance": 0,
                }
            ],
            # Additional queries for other checks...
            [
                {
                    "total": 100,
                    "negative_balance": 0,
                    "negative_equity": 0,
                    "invalid_profit_target": 0,
                    "invalid_max_dd": 0,
                    "negative_days": 0,
                    "min_balance": 1000,
                    "max_balance": 50000,
                    "avg_balance": 25000,
                }
            ],
            [{"total": 100, "equity_exceeds_balance": 0, "equity_too_low": 0}],
            [{"invalid_days": 0}],
            [{"missing_plans": 0}],
            [
                {
                    "oldest_record": datetime.now(),
                    "newest_record": datetime.now(),
                    "total_records": 100,
                }
            ],
        ]

        results = self.validator.validate_staging_snapshot(self.test_date)

        # Should have failed validation for null account_id
        account_id_results = [
            r for r in results if r.rule_name == "null_check_account_id"
        ]
        self.assertEqual(len(account_id_results), 1)
        self.assertEqual(account_id_results[0].status, ValidationStatus.FAILED)
        self.assertEqual(account_id_results[0].affected_records, 5)

    def test_validate_data_types_negative_balance(self):
        """Test validation catches negative balances."""
        # Set up specific test for _check_data_types
        self.mock_db_manager.model_db.execute_query.side_effect = [
            [{"count": 100}],  # Has data
            [
                {  # Null check results - all good
                    "total_records": 100,
                    "null_account_id": 0,
                    "null_login": 0,
                    "null_balance": 0,
                    "null_equity": 0,
                    "null_starting_balance": 0,
                }
            ],
            [
                {  # Range check with negative balances
                    "total": 100,
                    "negative_balance": 3,
                    "negative_equity": 0,
                    "invalid_profit_target": 0,
                    "invalid_max_dd": 0,
                    "negative_days": 0,
                    "min_balance": -500,
                    "max_balance": 50000,
                    "avg_balance": 25000,
                }
            ],
            [{"total": 100, "equity_exceeds_balance": 0, "equity_too_low": 0}],
            [{"invalid_days": 0}],
            [{"missing_plans": 0}],
            [
                {
                    "oldest_record": datetime.now(),
                    "newest_record": datetime.now(),
                    "total_records": 100,
                }
            ],
        ]

        results = self.validator.validate_staging_snapshot(self.test_date)

        # Should have failed validation for negative balance
        negative_balance_results = [
            r for r in results if r.rule_name == "negative_balance_check"
        ]
        self.assertEqual(len(negative_balance_results), 1)
        self.assertEqual(negative_balance_results[0].status, ValidationStatus.FAILED)
        self.assertEqual(negative_balance_results[0].affected_records, 3)

    def test_validate_business_rules(self):
        """Test business rule validation."""
        # Set up for business rules test
        self.mock_db_manager.model_db.execute_query.side_effect = [
            [{"count": 100}],  # Has data
            [
                {  # Null check results - all good
                    "total_records": 100,
                    "null_account_id": 0,
                    "null_login": 0,
                    "null_balance": 0,
                    "null_equity": 0,
                    "null_starting_balance": 0,
                }
            ],
            [
                {  # Range check - all good
                    "total": 100,
                    "negative_balance": 0,
                    "negative_equity": 0,
                    "invalid_profit_target": 0,
                    "invalid_max_dd": 0,
                    "negative_days": 0,
                    "min_balance": 1000,
                    "max_balance": 50000,
                    "avg_balance": 25000,
                }
            ],
            [
                {  # Equity/balance consistency check
                    "total": 100,
                    "equity_exceeds_balance": 5,
                    "equity_too_low": 2,
                }
            ],
            [{"invalid_days": 3}],  # Trading days consistency
            [{"missing_plans": 0}],
            [
                {
                    "oldest_record": datetime.now(),
                    "newest_record": datetime.now(),
                    "total_records": 100,
                }
            ],
        ]

        results = self.validator.validate_staging_snapshot(self.test_date)

        # Check for business rule warnings/failures
        equity_warnings = [r for r in results if "equity_balance" in r.rule_name]
        self.assertGreater(len(equity_warnings), 0)

        trading_days_results = [
            r for r in results if r.rule_name == "trading_days_consistency"
        ]
        self.assertEqual(len(trading_days_results), 1)
        self.assertEqual(trading_days_results[0].status, ValidationStatus.FAILED)

    def test_profile_data(self):
        """Test data profiling functionality."""
        # Mock column information
        self.mock_db_manager.model_db.execute_query.side_effect = [
            [{"row_count": 1000}],  # Row count
            [  # Column information
                {
                    "column_name": "account_id",
                    "data_type": "character varying",
                    "is_nullable": "NO",
                },
                {
                    "column_name": "current_balance",
                    "data_type": "numeric",
                    "is_nullable": "YES",
                },
                {
                    "column_name": "phase",
                    "data_type": "character varying",
                    "is_nullable": "YES",
                },
                {"column_name": "date", "data_type": "date", "is_nullable": "NO"},
            ],
            [
                {  # Null counts
                    "null_account_id": 0,
                    "null_current_balance": 50,
                    "null_phase": 10,
                    "null_date": 0,
                }
            ],
            [
                {  # Numeric statistics
                    "min_current_balance": 1000,
                    "max_current_balance": 100000,
                    "avg_current_balance": 25000,
                    "std_current_balance": 15000,
                }
            ],
            [  # Categorical stats for account_id
                {"value": "ACC001", "count": 30},
                {"value": "ACC002", "count": 25},
                {"value": "ACC003", "count": 20},
            ],
            [  # Categorical stats for phase
                {"value": "Funded", "count": 800},
                {"value": "Challenge", "count": 150},
                {"value": "Verification", "count": 50},
            ],
            [
                {  # Date range
                    "min_date": date(2024, 1, 1),
                    "max_date": date(2024, 1, 31),
                }
            ],
        ]

        profile = self.validator.profile_data("test_table", date_column="date")

        self.assertEqual(profile.table_name, "test_table")
        self.assertEqual(profile.row_count, 1000)
        self.assertEqual(profile.column_count, 4)
        self.assertEqual(profile.null_counts["current_balance"], 50)
        self.assertIn("current_balance", profile.numeric_stats)
        self.assertEqual(profile.numeric_stats["current_balance"]["min"], 1000)
        self.assertIn("phase", profile.categorical_stats)
        self.assertEqual(profile.date_range[0], date(2024, 1, 1))

    def test_generate_validation_report(self):
        """Test enhanced validation report generation with production features."""
        # Add some test results with enhanced features
        self.validator.validation_results = [
            ValidationResult(
                rule_name="test_passed",
                status=ValidationStatus.PASSED,
                message="Test passed successfully",
            ),
            ValidationResult(
                rule_name="test_warning",
                status=ValidationStatus.WARNING,
                message="Test generated warning",
                affected_records=10,
                details={"threshold": 95.0, "actual": 92.5},
            ),
            ValidationResult(
                rule_name="test_failed",
                status=ValidationStatus.FAILED,
                message="Test failed",
                affected_records=5,
            ),
        ]

        # Test metrics tracking
        self.validator.validation_metrics = {
            "total_checks": 5,
            "execution_time": 2.5,
            "errors_encountered": 1,
        }

        report = self.validator.generate_validation_report()

        # Check report contains expected sections
        self.assertIn("DATA VALIDATION REPORT", report)
        self.assertIn("SUMMARY", report)
        self.assertIn("Total Validations: 3", report)
        self.assertIn("Passed: 1", report)
        self.assertIn("Warnings: 1", report)
        self.assertIn("Failed: 1", report)
        self.assertIn("FAILED VALIDATIONS", report)
        self.assertIn("WARNINGS", report)
        self.assertIn("test_failed", report)
        self.assertIn("test_warning", report)

        # Test enhanced validator features
        self.assertTrue(self.validator.enable_profiling)
        self.assertEqual(self.validator.timeout_seconds, 300)  # Default timeout


class TestEnhancedValidationFeatures(unittest.TestCase):
    """Test cases for enhanced production validation features."""

    def setUp(self):
        """Set up enhanced test fixtures."""
        self.mock_db_manager = Mock()
        self.mock_db_manager.model_db = Mock()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            self.validator = DataValidator(
                self.mock_db_manager, enable_profiling=True, timeout_seconds=60
            )

    def test_enhanced_validator_initialization(self):
        """Test enhanced validator initialization with production features."""
        # Test default settings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            validator_default = DataValidator(self.mock_db_manager)
        self.assertTrue(validator_default.enable_profiling)
        self.assertEqual(validator_default.timeout_seconds, 300)

        # Test custom settings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            validator_custom = DataValidator(
                self.mock_db_manager, enable_profiling=False, timeout_seconds=120
            )
        self.assertFalse(validator_custom.enable_profiling)
        self.assertEqual(validator_custom.timeout_seconds, 120)

    def test_validation_metrics_tracking(self):
        """Test validation metrics are properly tracked."""
        # Mock basic responses
        self.mock_db_manager.model_db.execute_query.side_effect = [
            [{"count": 100}],  # Has data
        ]

        # Run validation
        from datetime import date

        self.validator.validate_staging_snapshot(date(2024, 1, 15))

        # Check metrics are tracked
        self.assertGreater(self.validator.validation_metrics["total_checks"], 0)
        self.assertGreaterEqual(self.validator.validation_metrics["execution_time"], 0)
        self.assertGreaterEqual(
            self.validator.validation_metrics["errors_encountered"], 0
        )

        # Check that validation start time was set
        self.assertIsNotNone(self.validator.validation_start_time)

    def test_enhanced_error_handling(self):
        """Test enhanced error handling in validation."""
        # Mock database error
        self.mock_db_manager.model_db.execute_query.side_effect = Exception(
            "Database connection failed"
        )

        # Run validation - should handle error gracefully
        from datetime import date

        results = self.validator.validate_staging_snapshot(date(2024, 1, 15))

        # Should have error result
        error_results = [r for r in results if r.rule_name == "validation_system_error"]
        self.assertEqual(len(error_results), 1)
        self.assertEqual(error_results[0].status, ValidationStatus.FAILED)
        self.assertIn("critical error", error_results[0].message.lower())

    def test_enhanced_logging_structure(self):
        """Test that enhanced logging produces structured output."""
        # This test verifies that the enhanced logging structure is working
        # In production, this would help with log aggregation and monitoring
        self.mock_db_manager.model_db.execute_query.side_effect = [
            [{"count": 100}],  # Has data
            [
                {
                    "total_records": 100,
                    "null_account_id": 0,
                    "null_login": 0,
                    "null_balance": 0,
                    "null_equity": 0,
                    "null_starting_balance": 0,
                }
            ],
            [
                {
                    "total": 100,
                    "negative_balance": 0,
                    "negative_equity": 0,
                    "invalid_profit_target": 0,
                    "invalid_max_dd": 0,
                    "negative_days": 0,
                    "min_balance": 1000,
                    "max_balance": 50000,
                    "avg_balance": 25000,
                }
            ],
            [{"total": 100, "equity_exceeds_balance": 0, "equity_too_low": 0}],
            [{"invalid_days": 0}],
            [{"missing_plans": 0}],
            [
                {
                    "oldest_record": datetime.now(),
                    "newest_record": datetime.now(),
                    "total_records": 100,
                }
            ],
        ]

        from datetime import date

        self.validator.validate_staging_snapshot(date(2024, 1, 15))

        # Verify structured metrics are available
        self.assertIn("total_checks", self.validator.validation_metrics)
        self.assertIn("execution_time", self.validator.validation_metrics)
        self.assertIn("errors_encountered", self.validator.validation_metrics)


class TestDataQualityRules(unittest.TestCase):
    """Test cases for data quality rules."""

    def test_get_rules_for_table(self):
        """Test retrieving rules for specific tables."""
        staging_rules = get_rules_for_table("stg_accounts_daily_snapshots")
        self.assertGreater(len(staging_rules), 0)
        self.assertTrue(
            all(r.table_name == "stg_accounts_daily_snapshots" for r in staging_rules)
        )

        accounts_rules = get_rules_for_table("raw_accounts_data")
        self.assertGreater(len(accounts_rules), 0)

        metrics_rules = get_rules_for_table("raw_metrics_daily")
        self.assertGreater(len(metrics_rules), 0)

        # Test non-existent table
        empty_rules = get_rules_for_table("non_existent_table")
        self.assertEqual(len(empty_rules), 0)

    def test_rule_types(self):
        """Test that rules have appropriate types."""
        staging_rules = get_rules_for_table("stg_accounts_daily_snapshots")

        # Check we have different types of rules
        rule_types = set(r.rule_type for r in staging_rules)
        self.assertIn(RuleType.COMPLETENESS, rule_types)
        self.assertIn(RuleType.VALIDITY, rule_types)
        self.assertIn(RuleType.CONSISTENCY, rule_types)

    def test_critical_rules(self):
        """Test that critical rules are properly marked."""
        from preprocessing.data_quality_rules import get_critical_rules

        critical_rules = get_critical_rules()
        self.assertGreater(len(critical_rules), 0)
        self.assertTrue(all(r.severity == "error" for r in critical_rules))

    def test_enhanced_rule_features(self):
        """Test enhanced rule features for production environments."""
        staging_rules = get_rules_for_table("stg_accounts_daily_snapshots")

        # Test that enhanced attributes exist
        first_rule = staging_rules[0]
        self.assertTrue(hasattr(first_rule, "tags"))
        self.assertTrue(hasattr(first_rule, "business_impact"))
        self.assertTrue(hasattr(first_rule, "owner"))
        self.assertTrue(hasattr(first_rule, "execution_timeout_seconds"))
        self.assertTrue(hasattr(first_rule, "retry_count"))

        # Test enhanced rule with production metadata
        enhanced_rule = None
        for rule in staging_rules:
            if rule.rule_id == "STG_001":
                enhanced_rule = rule
                break

        self.assertIsNotNone(enhanced_rule)
        self.assertEqual(enhanced_rule.business_impact, "critical")
        self.assertIn("critical", enhanced_rule.tags)
        self.assertEqual(enhanced_rule.owner, "data_engineering_team")
        self.assertEqual(enhanced_rule.execution_timeout_seconds, 30)

    def test_rule_business_impact_levels(self):
        """Test that rules have appropriate business impact levels."""
        all_rules = get_rules_for_table("stg_accounts_daily_snapshots")

        # Check business impact values are valid
        valid_impacts = ["low", "medium", "high", "critical"]
        for rule in all_rules:
            self.assertIn(rule.business_impact, valid_impacts)

        # Critical rules should have high or critical business impact
        critical_rules = [r for r in all_rules if r.severity == "error"]
        for rule in critical_rules:
            if hasattr(rule, "business_impact"):
                self.assertIn(rule.business_impact, ["high", "critical"])

    def test_rule_metadata_completeness(self):
        """Test that production rules have complete metadata."""
        staging_rules = get_rules_for_table("stg_accounts_daily_snapshots")

        for rule in staging_rules:
            # All rules should have basic metadata
            self.assertIsNotNone(rule.rule_id)
            self.assertIsNotNone(rule.rule_name)
            self.assertIsNotNone(rule.description)
            self.assertIsNotNone(rule.table_name)
            self.assertIsInstance(rule.enabled, bool)

            # Production metadata should be present
            self.assertIsInstance(rule.tags, list)
            self.assertGreater(rule.execution_timeout_seconds, 0)
            self.assertGreaterEqual(rule.retry_count, 0)

            # Critical rules should have owners
            if rule.severity == "error":
                self.assertIsNotNone(rule.owner)


if __name__ == "__main__":
    unittest.main()
