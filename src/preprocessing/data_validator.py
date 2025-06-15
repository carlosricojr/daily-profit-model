"""
Data validation module for preprocessing pipeline.
Implements basic data quality checks and validation rules.

⚠️  DEPRECATION NOTICE ⚠️
This module is deprecated in favor of Great Expectations integration.
Please use preprocessing.great_expectations_config.GreatExpectationsValidator instead.

The Great Expectations implementation provides:
- More comprehensive validation rules
- Better error reporting and data profiling
- Industry-standard data quality framework
- ML-specific validation patterns
- Automated data documentation

For backward compatibility, this module will remain available but is no longer actively maintained.
"""

import logging
import warnings
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
from dataclasses import dataclass
from enum import Enum
import time
from contextlib import contextmanager

# Issue deprecation warning
warnings.warn(
    "DataValidator is deprecated. Please use preprocessing.great_expectations_config.GreatExpectationsValidator instead. "
    "The Great Expectations implementation provides more comprehensive validation and better ML pipeline integration.",
    DeprecationWarning,
    stacklevel=2
)

try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    # Fallback for test imports
    import logging

    logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation status enumeration."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class ValidationResult:
    """Container for validation results."""

    rule_name: str
    status: ValidationStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    affected_records: Optional[int] = None


@dataclass
class DataProfile:
    """Container for data profiling statistics."""

    table_name: str
    row_count: int
    column_count: int
    null_counts: Dict[str, int]
    data_types: Dict[str, str]
    numeric_stats: Dict[str, Dict[str, float]]
    categorical_stats: Dict[str, Dict[str, Any]]
    date_range: Optional[Tuple[date, date]] = None


class DataValidator:
    """
    Enhanced data validation for preprocessing pipeline with production features.
    
    ⚠️  DEPRECATED: Use preprocessing.great_expectations_config.GreatExpectationsValidator instead.
    """

    def __init__(
        self, db_manager, enable_profiling: bool = True, timeout_seconds: int = 300
    ):
        """Initialize data validator with enhanced features."""
        # Issue deprecation warning on instantiation
        warnings.warn(
            "DataValidator is deprecated. Please use preprocessing.great_expectations_config.GreatExpectationsValidator instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        self.db_manager = db_manager
        self.validation_results = []
        self.enable_profiling = enable_profiling
        self.timeout_seconds = timeout_seconds
        self.validation_start_time = None
        self.validation_metrics = {
            "total_checks": 0,
            "execution_time": 0,
            "errors_encountered": 0,
        }

    @contextmanager
    def _timed_validation(self, check_name: str):
        """Context manager for timing validation checks."""
        start_time = time.time()
        try:
            logger.debug(f"Starting validation check: {check_name}")
            yield
            execution_time = time.time() - start_time
            logger.debug(
                f"Completed validation check: {check_name} in {execution_time:.2f}s"
            )
        except Exception as e:
            execution_time = time.time() - start_time
            self.validation_metrics["errors_encountered"] += 1
            logger.error(
                f"Error in validation check {check_name} after {execution_time:.2f}s: {str(e)}"
            )
            raise
        finally:
            self.validation_metrics["total_checks"] += 1

    def validate_staging_snapshot(self, snapshot_date: date) -> List[ValidationResult]:
        """
        Enhanced validation of staging snapshot data for a given date.

        Args:
            snapshot_date: Date to validate

        Returns:
            List of validation results
        """
        logger.warning(
            "DataValidator.validate_staging_snapshot is deprecated. "
            "Use GreatExpectationsValidator.validate_ml_pipeline_data_quality instead."
        )
        
        self.validation_start_time = time.time()
        self.validation_results = []
        self.validation_metrics = {
            "total_checks": 0,
            "execution_time": 0,
            "errors_encountered": 0,
        }

        logger.info(f"Starting comprehensive validation for {snapshot_date}")

        try:
            # Run validation checks with timing
            with self._timed_validation("data_completeness"):
                self._check_data_completeness(snapshot_date)

            with self._timed_validation("data_types"):
                self._check_data_types(snapshot_date)

            with self._timed_validation("business_rules"):
                self._check_business_rules(snapshot_date)

            with self._timed_validation("referential_integrity"):
                self._check_referential_integrity(snapshot_date)

            with self._timed_validation("data_freshness"):
                self._check_data_freshness(snapshot_date)

            # Calculate execution time
            self.validation_metrics["execution_time"] = (
                time.time() - self.validation_start_time
            )

            # Log comprehensive summary
            failed = sum(
                1
                for r in self.validation_results
                if r.status == ValidationStatus.FAILED
            )
            warnings = sum(
                1
                for r in self.validation_results
                if r.status == ValidationStatus.WARNING
            )
            passed = sum(
                1
                for r in self.validation_results
                if r.status == ValidationStatus.PASSED
            )

            logger.info(
                f"Validation complete for {snapshot_date}: "
                f"{passed} passed, {warnings} warnings, {failed} failed. "
                f"Total checks: {self.validation_metrics['total_checks']}, "
                f"Execution time: {self.validation_metrics['execution_time']:.2f}s, "
                f"Errors: {self.validation_metrics['errors_encountered']}"
            )

            # Log structured metrics for monitoring
            logger.info(
                "Validation metrics",
                extra={
                    "extra_fields": {
                        "snapshot_date": str(snapshot_date),
                        "validation_summary": {
                            "passed": passed,
                            "warnings": warnings,
                            "failed": failed,
                            "total_checks": self.validation_metrics["total_checks"],
                            "execution_time_seconds": self.validation_metrics[
                                "execution_time"
                            ],
                            "errors_encountered": self.validation_metrics[
                                "errors_encountered"
                            ],
                        },
                    }
                },
            )

        except Exception as e:
            logger.error(
                f"Critical error during validation of {snapshot_date}: {str(e)}"
            )
            self.validation_results.append(
                ValidationResult(
                    rule_name="validation_system_error",
                    status=ValidationStatus.FAILED,
                    message=f"Validation system encountered critical error: {str(e)}",
                )
            )

        return self.validation_results

    def _check_data_completeness(self, snapshot_date: date):
        """Check for missing required data."""
        # Check if we have snapshots for the date
        query = """
        SELECT COUNT(*) as count 
        FROM stg_accounts_daily_snapshots
        WHERE date = %s
        """
        result = self.db_manager.model_db.execute_query(query, (snapshot_date,))
        count = result[0]["count"] if result else 0

        if count == 0:
            self.validation_results.append(
                ValidationResult(
                    rule_name="data_completeness_check",
                    status=ValidationStatus.FAILED,
                    message=f"No snapshot data found for {snapshot_date}",
                    affected_records=0,
                )
            )
        else:
            # Check for required fields
            null_check_query = """
            SELECT 
                COUNT(*) as total_records,
                COUNT(CASE WHEN account_id IS NULL THEN 1 END) as null_account_id,
                COUNT(CASE WHEN login IS NULL THEN 1 END) as null_login,
                COUNT(CASE WHEN current_balance IS NULL THEN 1 END) as null_balance,
                COUNT(CASE WHEN current_equity IS NULL THEN 1 END) as null_equity,
                COUNT(CASE WHEN starting_balance IS NULL THEN 1 END) as null_starting_balance
            FROM stg_accounts_daily_snapshots
            WHERE date = %s
            """
            null_results = self.db_manager.model_db.execute_query(
                null_check_query, (snapshot_date,)
            )

            if null_results:
                nulls = null_results[0]
                total = nulls["total_records"]

                # Check critical fields
                critical_nulls = {
                    "account_id": nulls["null_account_id"],
                    "login": nulls["null_login"],
                    "starting_balance": nulls["null_starting_balance"],
                }

                for field, null_count in critical_nulls.items():
                    if null_count > 0:
                        self.validation_results.append(
                            ValidationResult(
                                rule_name=f"null_check_{field}",
                                status=ValidationStatus.FAILED,
                                message=f"Found {null_count} NULL values in critical field '{field}'",
                                affected_records=null_count,
                                details={
                                    "null_percentage": (null_count / total * 100)
                                    if total > 0
                                    else 0
                                },
                            )
                        )
                    else:
                        self.validation_results.append(
                            ValidationResult(
                                rule_name=f"null_check_{field}",
                                status=ValidationStatus.PASSED,
                                message=f"No NULL values in critical field '{field}'",
                                affected_records=0,
                            )
                        )

                # Check non-critical fields with warnings
                if nulls["null_balance"] > total * 0.05:  # More than 5% nulls
                    self.validation_results.append(
                        ValidationResult(
                            rule_name="null_check_current_balance",
                            status=ValidationStatus.WARNING,
                            message=f"High NULL rate in current_balance: {nulls['null_balance']} records",
                            affected_records=nulls["null_balance"],
                            details={
                                "null_percentage": (nulls["null_balance"] / total * 100)
                                if total > 0
                                else 0
                            },
                        )
                    )

    def _check_data_types(self, snapshot_date: date):
        """Validate data types and value ranges."""
        # Check numeric ranges
        range_query = """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN current_balance < 0 THEN 1 END) as negative_balance,
            COUNT(CASE WHEN current_equity < 0 THEN 1 END) as negative_equity,
            COUNT(CASE WHEN profit_target_pct < 0 OR profit_target_pct > 100 THEN 1 END) as invalid_profit_target,
            COUNT(CASE WHEN max_drawdown_pct < 0 OR max_drawdown_pct > 100 THEN 1 END) as invalid_max_dd,
            COUNT(CASE WHEN days_since_first_trade < 0 THEN 1 END) as negative_days,
            MIN(current_balance) as min_balance,
            MAX(current_balance) as max_balance,
            AVG(current_balance) as avg_balance
        FROM stg_accounts_daily_snapshots
        WHERE date = %s
        """

        results = self.db_manager.model_db.execute_query(range_query, (snapshot_date,))

        if results:
            stats = results[0]

            # Check for negative balances (should not exist in funded accounts)
            if stats["negative_balance"] > 0:
                self.validation_results.append(
                    ValidationResult(
                        rule_name="negative_balance_check",
                        status=ValidationStatus.FAILED,
                        message=f"Found {stats['negative_balance']} accounts with negative balance",
                        affected_records=stats["negative_balance"],
                    )
                )
            else:
                self.validation_results.append(
                    ValidationResult(
                        rule_name="negative_balance_check",
                        status=ValidationStatus.PASSED,
                        message="No negative balances found",
                    )
                )

            # Check percentage fields
            if stats["invalid_profit_target"] > 0:
                self.validation_results.append(
                    ValidationResult(
                        rule_name="profit_target_range_check",
                        status=ValidationStatus.FAILED,
                        message=f"Found {stats['invalid_profit_target']} records with profit_target_pct outside 0-100 range",
                        affected_records=stats["invalid_profit_target"],
                    )
                )

            # Check for extremely high balances (potential data errors)
            if (
                stats["max_balance"] and stats["max_balance"] > 10000000
            ):  # $10M threshold
                self.validation_results.append(
                    ValidationResult(
                        rule_name="extreme_balance_check",
                        status=ValidationStatus.WARNING,
                        message=f"Found extremely high balance: ${stats['max_balance']:,.2f}",
                        details={
                            "min_balance": stats["min_balance"],
                            "max_balance": stats["max_balance"],
                            "avg_balance": stats["avg_balance"],
                        },
                    )
                )

    def _check_business_rules(self, snapshot_date: date):
        """Validate business logic rules."""
        # Rule: Current equity should not exceed current balance by more than 10%
        equity_check_query = """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN current_equity > current_balance * 1.1 THEN 1 END) as equity_exceeds_balance,
            COUNT(CASE WHEN current_equity < current_balance * 0.5 THEN 1 END) as equity_too_low
        FROM stg_accounts_daily_snapshots
        WHERE date = %s
        AND current_balance IS NOT NULL 
        AND current_equity IS NOT NULL
        """

        results = self.db_manager.model_db.execute_query(
            equity_check_query, (snapshot_date,)
        )

        if results:
            stats = results[0]

            if stats["equity_exceeds_balance"] > 0:
                self.validation_results.append(
                    ValidationResult(
                        rule_name="equity_balance_consistency",
                        status=ValidationStatus.WARNING,
                        message=f"Found {stats['equity_exceeds_balance']} accounts where equity > balance * 1.1",
                        affected_records=stats["equity_exceeds_balance"],
                    )
                )

            if stats["equity_too_low"] > 0:
                self.validation_results.append(
                    ValidationResult(
                        rule_name="equity_balance_minimum",
                        status=ValidationStatus.WARNING,
                        message=f"Found {stats['equity_too_low']} accounts where equity < balance * 0.5",
                        affected_records=stats["equity_too_low"],
                    )
                )

        # Rule: Active trading days should not exceed days since first trade
        days_check_query = """
        SELECT 
            COUNT(*) as invalid_days
        FROM stg_accounts_daily_snapshots
        WHERE date = %s
        AND active_trading_days_count > days_since_first_trade
        AND days_since_first_trade IS NOT NULL
        """

        results = self.db_manager.model_db.execute_query(
            days_check_query, (snapshot_date,)
        )

        if results and results[0]["invalid_days"] > 0:
            self.validation_results.append(
                ValidationResult(
                    rule_name="trading_days_consistency",
                    status=ValidationStatus.FAILED,
                    message=f"Found {results[0]['invalid_days']} accounts where active_trading_days > days_since_first_trade",
                    affected_records=results[0]["invalid_days"],
                )
            )

    def _check_referential_integrity(self, snapshot_date: date):
        """Check foreign key relationships."""
        # Check if all plan_ids exist in raw_plans_data
        plan_check_query = """
        SELECT COUNT(DISTINCT s.plan_id) as missing_plans
        FROM stg_accounts_daily_snapshots s
        LEFT JOIN raw_plans_data p ON s.plan_id = p.plan_id
        WHERE s.date = %s
        AND s.plan_id IS NOT NULL
        AND p.plan_id IS NULL
        """

        results = self.db_manager.model_db.execute_query(
            plan_check_query, (snapshot_date,)
        )

        if results and results[0]["missing_plans"] > 0:
            self.validation_results.append(
                ValidationResult(
                    rule_name="plan_referential_integrity",
                    status=ValidationStatus.WARNING,
                    message=f"Found {results[0]['missing_plans']} plan_ids without matching plan data",
                    affected_records=results[0]["missing_plans"],
                )
            )
        else:
            self.validation_results.append(
                ValidationResult(
                    rule_name="plan_referential_integrity",
                    status=ValidationStatus.PASSED,
                    message="All plan_ids have matching plan data",
                )
            )

    def _check_data_freshness(self, snapshot_date: date):
        """Check if data is recent enough."""
        # Check ingestion timestamp
        freshness_query = """
        SELECT 
            MIN(created_at) as oldest_record,
            MAX(created_at) as newest_record,
            COUNT(*) as total_records
        FROM stg_accounts_daily_snapshots
        WHERE date = %s
        """

        results = self.db_manager.model_db.execute_query(
            freshness_query, (snapshot_date,)
        )

        if results and results[0]["newest_record"]:
            newest = results[0]["newest_record"]
            age_hours = (datetime.now() - newest).total_seconds() / 3600

            if age_hours > 48:  # Data older than 48 hours
                self.validation_results.append(
                    ValidationResult(
                        rule_name="data_freshness_check",
                        status=ValidationStatus.WARNING,
                        message=f"Snapshot data is {age_hours:.1f} hours old",
                        details={
                            "oldest_record": str(results[0]["oldest_record"]),
                            "newest_record": str(results[0]["newest_record"]),
                        },
                    )
                )
            else:
                self.validation_results.append(
                    ValidationResult(
                        rule_name="data_freshness_check",
                        status=ValidationStatus.PASSED,
                        message=f"Data is fresh ({age_hours:.1f} hours old)",
                    )
                )

    def profile_data(
        self, table_name: str, date_column: Optional[str] = None
    ) -> DataProfile:
        """
        Generate data profiling statistics for a table.

        Args:
            table_name: Name of the table to profile
            date_column: Optional date column for range analysis

        Returns:
            DataProfile object with statistics
        """
        # Get basic counts
        count_query = f"SELECT COUNT(*) as row_count FROM {table_name}"
        count_result = self.db_manager.model_db.execute_query(count_query)
        row_count = count_result[0]["row_count"] if count_result else 0

        # Get column information
        columns_query = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'prop_trading_model'
        AND table_name = %s
        ORDER BY ordinal_position
        """
        columns = self.db_manager.model_db.execute_query(columns_query, (table_name,))

        column_count = len(columns)
        data_types = {col["column_name"]: col["data_type"] for col in columns}

        # Get null counts
        null_counts = {}
        if row_count > 0:
            null_query_parts = [
                f"COUNT(CASE WHEN {col['column_name']} IS NULL THEN 1 END) as null_{col['column_name']}"
                for col in columns
            ]
            null_query = f"SELECT {', '.join(null_query_parts)} FROM {table_name}"
            null_results = self.db_manager.model_db.execute_query(null_query)

            if null_results:
                null_counts = {
                    col["column_name"]: null_results[0][f"null_{col['column_name']}"]
                    for col in columns
                }

        # Get numeric statistics
        numeric_stats = {}
        numeric_columns = [
            col["column_name"]
            for col in columns
            if "numeric" in col["data_type"]
            or "decimal" in col["data_type"]
            or "integer" in col["data_type"]
        ]

        if numeric_columns and row_count > 0:
            stats_parts = []
            for col in numeric_columns:
                stats_parts.extend(
                    [
                        f"MIN({col}) as min_{col}",
                        f"MAX({col}) as max_{col}",
                        f"AVG({col}) as avg_{col}",
                        f"STDDEV({col}) as std_{col}",
                    ]
                )

            stats_query = f"SELECT {', '.join(stats_parts)} FROM {table_name}"
            stats_results = self.db_manager.model_db.execute_query(stats_query)

            if stats_results:
                for col in numeric_columns:
                    numeric_stats[col] = {
                        "min": stats_results[0][f"min_{col}"],
                        "max": stats_results[0][f"max_{col}"],
                        "mean": stats_results[0][f"avg_{col}"],
                        "std": stats_results[0][f"std_{col}"],
                    }

        # Get categorical statistics (for varchar columns)
        categorical_stats = {}
        varchar_columns = [
            col["column_name"] for col in columns if "character" in col["data_type"]
        ]

        for col in varchar_columns[:5]:  # Limit to first 5 to avoid long queries
            if row_count > 0:
                cat_query = f"""
                SELECT {col} as value, COUNT(*) as count
                FROM {table_name}
                WHERE {col} IS NOT NULL
                GROUP BY {col}
                ORDER BY count DESC
                LIMIT 10
                """
                cat_results = self.db_manager.model_db.execute_query(cat_query)

                if cat_results:
                    categorical_stats[col] = {
                        "unique_values": len(cat_results),
                        "top_values": [(r["value"], r["count"]) for r in cat_results],
                    }

        # Get date range if date column specified
        date_range = None
        if date_column and row_count > 0:
            date_query = f"SELECT MIN({date_column}) as min_date, MAX({date_column}) as max_date FROM {table_name}"
            date_results = self.db_manager.model_db.execute_query(date_query)

            if date_results and date_results[0]["min_date"]:
                date_range = (date_results[0]["min_date"], date_results[0]["max_date"])

        return DataProfile(
            table_name=table_name,
            row_count=row_count,
            column_count=column_count,
            null_counts=null_counts,
            data_types=data_types,
            numeric_stats=numeric_stats,
            categorical_stats=categorical_stats,
            date_range=date_range,
        )

    def generate_validation_report(self, output_file: Optional[str] = None) -> str:
        """
        Generate a validation report from the results.

        Args:
            output_file: Optional file path to save the report

        Returns:
            Report as string
        """
        report_lines = [
            "=" * 80,
            "DATA VALIDATION REPORT",
            f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            "",
        ]

        # Summary statistics
        total = len(self.validation_results)
        passed = sum(
            1 for r in self.validation_results if r.status == ValidationStatus.PASSED
        )
        warnings = sum(
            1 for r in self.validation_results if r.status == ValidationStatus.WARNING
        )
        failed = sum(
            1 for r in self.validation_results if r.status == ValidationStatus.FAILED
        )

        report_lines.extend(
            [
                "SUMMARY",
                "-" * 40,
                f"Total Validations: {total}",
                f"Passed: {passed} ({passed / total * 100:.1f}%)"
                if total > 0
                else "Passed: 0",
                f"Warnings: {warnings} ({warnings / total * 100:.1f}%)"
                if total > 0
                else "Warnings: 0",
                f"Failed: {failed} ({failed / total * 100:.1f}%)"
                if total > 0
                else "Failed: 0",
                "",
            ]
        )

        # Failed validations
        if failed > 0:
            report_lines.extend(["FAILED VALIDATIONS", "-" * 40])
            for result in self.validation_results:
                if result.status == ValidationStatus.FAILED:
                    report_lines.append(
                        f"[FAILED] {result.rule_name}: {result.message}"
                    )
                    if result.affected_records:
                        report_lines.append(
                            f"         Affected Records: {result.affected_records}"
                        )
                    if result.details:
                        report_lines.append(f"         Details: {result.details}")
            report_lines.append("")

        # Warnings
        if warnings > 0:
            report_lines.extend(["WARNINGS", "-" * 40])
            for result in self.validation_results:
                if result.status == ValidationStatus.WARNING:
                    report_lines.append(
                        f"[WARNING] {result.rule_name}: {result.message}"
                    )
                    if result.affected_records:
                        report_lines.append(
                            f"          Affected Records: {result.affected_records}"
                        )
                    if result.details:
                        report_lines.append(f"          Details: {result.details}")
            report_lines.append("")

        # Passed validations (summary only)
        if passed > 0:
            report_lines.extend(["PASSED VALIDATIONS", "-" * 40])
            for result in self.validation_results:
                if result.status == ValidationStatus.PASSED:
                    report_lines.append(f"[PASSED] {result.rule_name}")
            report_lines.append("")

        report = "\n".join(report_lines)

        # Save to file if requested
        if output_file:
            with open(output_file, "w") as f:
                f.write(report)
            logger.info(f"Validation report saved to {output_file}")

        return report
