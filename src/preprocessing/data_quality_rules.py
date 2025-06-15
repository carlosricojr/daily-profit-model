"""
Data quality rules configuration for preprocessing pipeline.
Defines validation rules and thresholds for data quality checks.
"""

from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class RuleType(Enum):
    """Types of data quality rules."""

    COMPLETENESS = "completeness"
    VALIDITY = "validity"
    CONSISTENCY = "consistency"
    ACCURACY = "accuracy"
    UNIQUENESS = "uniqueness"
    TIMELINESS = "timeliness"


@dataclass
class DataQualityRule:
    """Enhanced definition of a data quality rule with production features."""

    rule_id: str
    rule_name: str
    rule_type: RuleType
    description: str
    table_name: str
    column_name: Optional[str] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    severity: str = "error"  # error, warning, info
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    created_date: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)
    execution_timeout_seconds: int = 60
    retry_count: int = 3
    business_impact: str = "medium"  # low, medium, high, critical
    owner: Optional[str] = None
    documentation_url: Optional[str] = None


# Define data quality rules for staging snapshots
STAGING_SNAPSHOT_RULES = [
    # Completeness Rules
    DataQualityRule(
        rule_id="STG_001",
        rule_name="account_id_not_null",
        rule_type=RuleType.COMPLETENESS,
        description="Account ID must not be null",
        table_name="stg_accounts_daily_snapshots",
        column_name="account_id",
        condition="account_id IS NOT NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "primary_key", "completeness"],
        business_impact="critical",
        owner="data_engineering_team",
        execution_timeout_seconds=30,
    ),
    DataQualityRule(
        rule_id="STG_002",
        rule_name="login_not_null",
        rule_type=RuleType.COMPLETENESS,
        description="Login must not be null",
        table_name="stg_accounts_daily_snapshots",
        column_name="login",
        condition="login IS NOT NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "authentication", "completeness"],
        business_impact="critical",
        owner="data_engineering_team",
        execution_timeout_seconds=30,
    ),
    DataQualityRule(
        rule_id="STG_003",
        rule_name="starting_balance_not_null",
        rule_type=RuleType.COMPLETENESS,
        description="Starting balance must not be null",
        table_name="stg_accounts_daily_snapshots",
        column_name="starting_balance",
        condition="starting_balance IS NOT NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "financial", "completeness"],
        business_impact="high",
        owner="business_analytics_team",
        execution_timeout_seconds=30,
    ),
    DataQualityRule(
        rule_id="STG_004",
        rule_name="current_balance_completeness",
        rule_type=RuleType.COMPLETENESS,
        description="Current balance should be mostly complete",
        table_name="stg_accounts_daily_snapshots",
        column_name="current_balance",
        condition="current_balance IS NOT NULL",
        threshold=95.0,
        severity="warning",
    ),
    # Validity Rules
    DataQualityRule(
        rule_id="STG_005",
        rule_name="balance_positive",
        rule_type=RuleType.VALIDITY,
        description="Current balance must be positive",
        table_name="stg_accounts_daily_snapshots",
        column_name="current_balance",
        condition="current_balance >= 0 OR current_balance IS NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "financial", "validity"],
        business_impact="high",
        owner="business_analytics_team",
        execution_timeout_seconds=45,
    ),
    DataQualityRule(
        rule_id="STG_006",
        rule_name="profit_target_pct_range",
        rule_type=RuleType.VALIDITY,
        description="Profit target percentage must be between 0 and 100",
        table_name="stg_accounts_daily_snapshots",
        column_name="profit_target_pct",
        condition="profit_target_pct BETWEEN 0 AND 100 OR profit_target_pct IS NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "business_rules", "validity"],
        business_impact="high",
        owner="business_analytics_team",
        execution_timeout_seconds=30,
    ),
    DataQualityRule(
        rule_id="STG_007",
        rule_name="max_drawdown_pct_range",
        rule_type=RuleType.VALIDITY,
        description="Max drawdown percentage must be between 0 and 100",
        table_name="stg_accounts_daily_snapshots",
        column_name="max_drawdown_pct",
        condition="max_drawdown_pct BETWEEN 0 AND 100 OR max_drawdown_pct IS NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "risk_management", "validity"],
        business_impact="high",
        owner="risk_management_team",
        execution_timeout_seconds=30,
    ),
    DataQualityRule(
        rule_id="STG_008",
        rule_name="days_since_first_trade_valid",
        rule_type=RuleType.VALIDITY,
        description="Days since first trade must be non-negative",
        table_name="stg_accounts_daily_snapshots",
        column_name="days_since_first_trade",
        condition="days_since_first_trade >= 0 OR days_since_first_trade IS NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "temporal", "validity"],
        business_impact="high",
        owner="data_engineering_team",
        execution_timeout_seconds=30,
    ),
    DataQualityRule(
        rule_id="STG_009",
        rule_name="phase_valid_values",
        rule_type=RuleType.VALIDITY,
        description="Phase must be a valid value",
        table_name="stg_accounts_daily_snapshots",
        column_name="phase",
        condition="phase IN ('Funded', 'Challenge', 'Verification') OR phase IS NULL",
        threshold=100.0,
        severity="warning",
    ),
    # Consistency Rules
    DataQualityRule(
        rule_id="STG_010",
        rule_name="equity_balance_consistency",
        rule_type=RuleType.CONSISTENCY,
        description="Current equity should not exceed current balance by more than 10%",
        table_name="stg_accounts_daily_snapshots",
        condition="current_equity <= current_balance * 1.1 OR current_equity IS NULL OR current_balance IS NULL",
        threshold=95.0,
        severity="warning",
    ),
    DataQualityRule(
        rule_id="STG_011",
        rule_name="trading_days_consistency",
        rule_type=RuleType.CONSISTENCY,
        description="Active trading days should not exceed days since first trade",
        table_name="stg_accounts_daily_snapshots",
        condition="active_trading_days_count <= days_since_first_trade OR days_since_first_trade IS NULL",
        threshold=100.0,
        severity="error",
        tags=["critical", "temporal", "consistency"],
        business_impact="high",
        owner="business_analytics_team",
        execution_timeout_seconds=45,
    ),
    DataQualityRule(
        rule_id="STG_012",
        rule_name="balance_reasonable_range",
        rule_type=RuleType.VALIDITY,
        description="Current balance should be within reasonable range",
        table_name="stg_accounts_daily_snapshots",
        column_name="current_balance",
        condition="current_balance BETWEEN 100 AND 10000000 OR current_balance IS NULL",
        threshold=99.0,
        severity="warning",
    ),
    # Uniqueness Rules
    DataQualityRule(
        rule_id="STG_013",
        rule_name="account_date_uniqueness",
        rule_type=RuleType.UNIQUENESS,
        description="Each account should have only one record per date",
        table_name="stg_accounts_daily_snapshots",
        condition="COUNT(*) = COUNT(DISTINCT CONCAT(account_id, '|', date))",
        threshold=100.0,
        severity="error",
        tags=["critical", "primary_key", "uniqueness"],
        business_impact="critical",
        owner="data_engineering_team",
        execution_timeout_seconds=60,
    ),
    # Timeliness Rules
    DataQualityRule(
        rule_id="STG_014",
        rule_name="data_freshness",
        rule_type=RuleType.TIMELINESS,
        description="Data should not be older than 48 hours",
        table_name="stg_accounts_daily_snapshots",
        condition="created_at >= NOW() - INTERVAL '48 hours'",
        threshold=90.0,
        severity="warning",
    ),
]


# Define rules for raw data tables
RAW_ACCOUNTS_RULES = [
    DataQualityRule(
        rule_id="RAW_ACC_001",
        rule_name="account_id_not_null",
        rule_type=RuleType.COMPLETENESS,
        description="Account ID must not be null in raw accounts",
        table_name="raw_accounts_data",
        column_name="account_id",
        condition="account_id IS NOT NULL",
        threshold=100.0,
        severity="error",
    ),
    DataQualityRule(
        rule_id="RAW_ACC_002",
        rule_name="breached_valid_values",
        rule_type=RuleType.VALIDITY,
        description="Breached must be 0 or 1",
        table_name="raw_accounts_data",
        column_name="breached",
        condition="breached IN (0, 1)",
        threshold=100.0,
        severity="error",
    ),
]


RAW_METRICS_DAILY_RULES = [
    DataQualityRule(
        rule_id="RAW_METRIC_001",
        rule_name="date_not_null",
        rule_type=RuleType.COMPLETENESS,
        description="Date must not be null in daily metrics",
        table_name="raw_metrics_daily",
        column_name="date",
        condition="date IS NOT NULL",
        threshold=100.0,
        severity="error",
    ),
    DataQualityRule(
        rule_id="RAW_METRIC_002",
        rule_name="win_rate_valid_range",
        rule_type=RuleType.VALIDITY,
        description="Win rate must be between 0 and 100",
        table_name="raw_metrics_daily",
        column_name="win_rate",
        condition="win_rate BETWEEN 0 AND 100 OR win_rate IS NULL",
        threshold=100.0,
        severity="error",
    ),
    DataQualityRule(
        rule_id="RAW_METRIC_003",
        rule_name="trades_consistency",
        rule_type=RuleType.CONSISTENCY,
        description="Total trades should equal winning + losing trades",
        table_name="raw_metrics_daily",
        condition="num_trades = winning_trades + losing_trades OR num_trades IS NULL",
        threshold=99.0,
        severity="warning",
    ),
]


def get_rules_for_table(table_name: str) -> List[DataQualityRule]:
    """Get all enabled rules for a specific table."""
    all_rules = []

    if table_name == "stg_accounts_daily_snapshots":
        all_rules = STAGING_SNAPSHOT_RULES
    elif table_name == "raw_accounts_data":
        all_rules = RAW_ACCOUNTS_RULES
    elif table_name == "raw_metrics_daily":
        all_rules = RAW_METRICS_DAILY_RULES

    return [rule for rule in all_rules if rule.enabled]


def get_rule_by_id(rule_id: str) -> Optional[DataQualityRule]:
    """Get a specific rule by its ID."""
    all_rules = STAGING_SNAPSHOT_RULES + RAW_ACCOUNTS_RULES + RAW_METRICS_DAILY_RULES
    for rule in all_rules:
        if rule.rule_id == rule_id:
            return rule
    return None


def get_critical_rules() -> List[DataQualityRule]:
    """Get all critical (error severity) rules."""
    all_rules = STAGING_SNAPSHOT_RULES + RAW_ACCOUNTS_RULES + RAW_METRICS_DAILY_RULES
    return [rule for rule in all_rules if rule.severity == "error" and rule.enabled]


# Data quality thresholds
QUALITY_THRESHOLDS = {
    "overall_quality_score": 95.0,  # Minimum acceptable quality score
    "critical_rule_pass_rate": 100.0,  # All critical rules must pass
    "warning_tolerance": 10,  # Maximum number of warnings allowed
    "null_rate_threshold": 5.0,  # Maximum acceptable null rate for non-critical fields
    "outlier_rate_threshold": 1.0,  # Maximum acceptable outlier rate
    "freshness_hours": 48,  # Maximum age of data in hours
}


# Remediation actions for common issues
REMEDIATION_ACTIONS = {
    "null_values": {
        "action": "fill_default",
        "description": "Fill NULL values with appropriate defaults",
        "fields": {
            "days_since_first_trade": 0,
            "active_trading_days_count": 0,
            "distance_to_profit_target": "calculate_from_balance",
            "distance_to_max_drawdown": "calculate_from_balance",
        },
    },
    "outliers": {
        "action": "flag_and_investigate",
        "description": "Flag outliers for manual investigation",
        "threshold_method": "iqr",  # interquartile range
        "multiplier": 1.5,
    },
    "duplicate_records": {
        "action": "keep_latest",
        "description": "Keep only the most recent record for duplicates",
        "order_by": "ingestion_timestamp DESC",
    },
    "invalid_values": {
        "action": "quarantine",
        "description": "Move invalid records to quarantine table for review",
    },
}
