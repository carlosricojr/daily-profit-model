#!/usr/bin/env python3
"""
Demonstration of enhanced data validation system usage.
Shows practical examples of how to use the validation in production.
"""

import os
import sys
from datetime import date, datetime
from unittest.mock import Mock

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from preprocessing.data_validator import DataValidator, ValidationStatus
from preprocessing.data_quality_rules import get_rules_for_table, get_critical_rules


def demo_rule_management():
    """Demonstrate rule management capabilities."""
    print("\n" + "=" * 80)
    print("DATA QUALITY RULES MANAGEMENT DEMO")
    print("=" * 80)

    # Get rules for different tables
    staging_rules = get_rules_for_table("stg_accounts_daily_snapshots")
    accounts_rules = get_rules_for_table("raw_accounts_data")
    metrics_rules = get_rules_for_table("raw_metrics_daily")

    print("📊 Rule Summary:")
    print(f"  Staging Rules: {len(staging_rules)}")
    print(f"  Accounts Rules: {len(accounts_rules)}")
    print(f"  Metrics Rules: {len(metrics_rules)}")

    # Show critical rules
    critical_rules = get_critical_rules()
    print(f"  Critical Rules: {len(critical_rules)}")

    # Show rule types distribution
    rule_types = {}
    for rule in staging_rules:
        rule_type = rule.rule_type.value
        rule_types[rule_type] = rule_types.get(rule_type, 0) + 1

    print("\n📋 Rule Types for Staging:")
    for rule_type, count in rule_types.items():
        print(f"  {rule_type.title()}: {count}")

    # Show enhanced rule features
    print("\n🔧 Enhanced Features Example (First Rule):")
    first_rule = staging_rules[0]
    print(f"  Rule ID: {first_rule.rule_id}")
    print(f"  Business Impact: {first_rule.business_impact}")
    print(f"  Tags: {', '.join(first_rule.tags)}")
    print(f"  Owner: {first_rule.owner}")
    print(f"  Execution Timeout: {first_rule.execution_timeout_seconds}s")
    print(f"  Retry Count: {first_rule.retry_count}")


def demo_data_validation():
    """Demonstrate data validation with mocked database."""
    print("\n" + "=" * 80)
    print("DATA VALIDATION DEMO")
    print("=" * 80)

    # Mock database manager
    mock_db_manager = Mock()

    # Create enhanced validator
    validator = DataValidator(
        db_manager=mock_db_manager, enable_profiling=True, timeout_seconds=300
    )

    print("🚀 Validator Configuration:")
    print(f"  Profiling Enabled: {validator.enable_profiling}")
    print(f"  Timeout: {validator.timeout_seconds}s")

    # Mock database responses for a realistic validation scenario
    mock_db_manager.model_db.execute_query.side_effect = [
        # Data completeness check
        [{"count": 1000}],  # Has data
        # Null check results
        [
            {
                "total_records": 1000,
                "null_account_id": 0,
                "null_login": 0,
                "null_balance": 25,  # 2.5% null rate - warning level
                "null_equity": 15,
                "null_starting_balance": 0,
            }
        ],
        # Range checks
        [
            {
                "total": 1000,
                "negative_balance": 0,
                "negative_equity": 0,
                "invalid_profit_target": 2,  # 2 invalid records
                "invalid_max_dd": 0,
                "negative_days": 0,
                "min_balance": 1000,
                "max_balance": 250000,
                "avg_balance": 45000,
            }
        ],
        # Business rules check
        [
            {
                "total": 1000,
                "equity_exceeds_balance": 5,  # 5 accounts with equity > balance
                "equity_too_low": 10,
            }
        ],
        # Trading days consistency
        [{"invalid_days": 0}],
        # Referential integrity
        [{"missing_plans": 3}],  # 3 accounts with missing plan data
        # Data freshness
        [
            {
                "oldest_record": datetime(2024, 1, 15, 8, 0, 0),
                "newest_record": datetime(2024, 1, 15, 10, 30, 0),
                "total_records": 1000,
            }
        ],
    ]

    # Run validation
    test_date = date(2024, 1, 15)
    print(f"\n🔍 Running validation for {test_date}...")

    results = validator.validate_staging_snapshot(test_date)

    # Analyze results
    passed = sum(1 for r in results if r.status == ValidationStatus.PASSED)
    warnings = sum(1 for r in results if r.status == ValidationStatus.WARNING)
    failed = sum(1 for r in results if r.status == ValidationStatus.FAILED)

    print("\n📈 Validation Results:")
    print(f"  ✅ Passed: {passed}")
    print(f"  ⚠️  Warnings: {warnings}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📊 Total Checks: {validator.validation_metrics['total_checks']}")
    print(f"  ⏱️  Execution Time: {validator.validation_metrics['execution_time']:.2f}s")

    # Show detailed results
    print("\n📋 Detailed Results:")
    for result in results:
        status_symbol = {"PASSED": "✅", "WARNING": "⚠️", "FAILED": "❌"}[
            result.status.name
        ]
        print(f"  {status_symbol} {result.rule_name}: {result.message}")
        if result.affected_records:
            print(f"      Affected Records: {result.affected_records}")


def demo_data_profiling():
    """Demonstrate data profiling capabilities."""
    print("\n" + "=" * 80)
    print("DATA PROFILING DEMO")
    print("=" * 80)

    # Mock database for profiling
    mock_db_manager = Mock()
    validator = DataValidator(mock_db_manager)

    # Mock responses for data profiling
    mock_db_manager.model_db.execute_query.side_effect = [
        # Row count
        [{"row_count": 5000}],
        # Column information
        [
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
                "column_name": "current_equity",
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
        # Null counts
        [
            {
                "null_account_id": 0,
                "null_current_balance": 125,  # 2.5%
                "null_current_equity": 85,  # 1.7%
                "null_phase": 50,  # 1.0%
                "null_date": 0,
            }
        ],
        # Numeric statistics
        [
            {
                "min_current_balance": 5000,
                "max_current_balance": 500000,
                "avg_current_balance": 75000,
                "std_current_balance": 45000,
                "min_current_equity": 4800,
                "max_current_equity": 485000,
                "avg_current_equity": 72000,
                "std_current_equity": 43000,
            }
        ],
        # Categorical stats for account_id (top values)
        [
            {"value": "ACC_12345", "count": 15},
            {"value": "ACC_67890", "count": 12},
            {"value": "ACC_11111", "count": 10},
        ],
        # Categorical stats for phase
        [
            {"value": "Funded", "count": 4200},
            {"value": "Challenge", "count": 650},
            {"value": "Verification", "count": 150},
        ],
        # Date range
        [{"min_date": date(2024, 1, 1), "max_date": date(2024, 1, 31)}],
    ]

    print("🔍 Generating data profile for 'stg_accounts_daily_snapshots'...")

    profile = validator.profile_data("stg_accounts_daily_snapshots", date_column="date")

    print("\n📊 Data Profile Results:")
    print(f"  Table: {profile.table_name}")
    print(f"  Rows: {profile.row_count:,}")
    print(f"  Columns: {profile.column_count}")

    print("\n🔢 Null Counts:")
    for column, null_count in profile.null_counts.items():
        null_pct = (
            (null_count / profile.row_count * 100) if profile.row_count > 0 else 0
        )
        print(f"  {column}: {null_count:,} ({null_pct:.1f}%)")

    print("\n📈 Numeric Statistics:")
    for column, stats in profile.numeric_stats.items():
        print(f"  {column}:")
        print(f"    Min: ${stats['min']:,.2f}")
        print(f"    Max: ${stats['max']:,.2f}")
        print(f"    Mean: ${stats['mean']:,.2f}")
        print(f"    Std: ${stats['std']:,.2f}")

    print("\n📋 Categorical Statistics:")
    for column, stats in profile.categorical_stats.items():
        print(f"  {column}: {stats['unique_values']} unique values")
        print(f"    Top values: {stats['top_values'][:3]}")

    if profile.date_range:
        print(f"\n📅 Date Range: {profile.date_range[0]} to {profile.date_range[1]}")


def demo_validation_report():
    """Demonstrate validation report generation."""
    print("\n" + "=" * 80)
    print("VALIDATION REPORT DEMO")
    print("=" * 80)

    # Create validator with some mock results
    mock_db_manager = Mock()
    validator = DataValidator(mock_db_manager)

    # Add some sample validation results
    from preprocessing.data_validator import ValidationResult

    validator.validation_results = [
        ValidationResult(
            rule_name="account_id_completeness",
            status=ValidationStatus.PASSED,
            message="All account IDs are present",
            affected_records=0,
        ),
        ValidationResult(
            rule_name="balance_range_check",
            status=ValidationStatus.WARNING,
            message="Found 15 accounts with unusually high balances",
            affected_records=15,
            details={"threshold": 100000, "max_found": 250000},
        ),
        ValidationResult(
            rule_name="negative_equity_check",
            status=ValidationStatus.FAILED,
            message="Found 3 accounts with negative equity",
            affected_records=3,
            details={"min_equity": -1500},
        ),
    ]

    print("📝 Generating validation report...")

    report = validator.generate_validation_report()

    print("\n" + "=" * 80)
    print("GENERATED VALIDATION REPORT")
    print("=" * 80)
    print(report)


def main():
    """Run all demonstrations."""
    print("🚀 Enhanced Data Validation System Demonstration")
    print("This demo shows the practical usage of the integrated validation system")

    demo_rule_management()
    demo_data_validation()
    demo_data_profiling()
    demo_validation_report()

    print("\n" + "=" * 80)
    print("✅ DEMONSTRATION COMPLETE")
    print("=" * 80)
    print("The enhanced data validation system is ready for production use!")
    print("\nKey Features Demonstrated:")
    print("• Enhanced rule management with business metadata")
    print("• Comprehensive validation with timing and metrics")
    print("• Detailed data profiling capabilities")
    print("• Professional validation reports")
    print("• Production-ready error handling and logging")


if __name__ == "__main__":
    main()
