"""
Unified Feature Engineering Module
Combines optimized query performance with comprehensive risk metrics and validation.
Version: 5.0.0 - Unified architecture
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
import multiprocessing as mp
import psutil
from collections import defaultdict
from contextlib import contextmanager

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging
from utils.query_performance import QueryPerformanceMonitor

# Feature engineering constants and configuration
FEATURE_VERSION = "5.0.0"  # Unified version
logger = logging.getLogger(__name__)


def get_optimal_config():
    """Get optimal configuration based on system resources."""
    cpu_count = mp.cpu_count()
    total_ram_mb = psutil.virtual_memory().total // (1024**2)

    return {
        "batch_size": min(3000, total_ram_mb // 40),  # Dynamic based on RAM
        "chunk_size": min(8000, total_ram_mb // 15),
        "max_workers": max(1, cpu_count - 4),  # Leave 4 cores for OS
        "memory_limit_mb": int(total_ram_mb * 0.85),  # 85% of total RAM
        "enable_monitoring": True,
        "enable_bias_validation": True,
        "quality_threshold": 0.95,
    }


PRODUCTION_CONFIG = get_optimal_config()


# ============================================================================
# VALIDATION AND MONITORING CLASSES
# ============================================================================

class LookaheadBiasValidator:
    """Enhanced validator for lookahead bias prevention."""

    def __init__(self, strict_mode: bool = True):
        self.violations = []
        self.strict_mode = strict_mode
        self.validation_stats = {
            "total_validations": 0,
            "violations_count": 0,
            "last_validation": None,
        }

    def validate_data_availability(
        self, feature_date: date, data_date: date, feature_name: str
    ) -> bool:
        """Enhanced validation with detailed tracking."""
        self.validation_stats["total_validations"] += 1
        self.validation_stats["last_validation"] = datetime.now()

        if data_date > feature_date:
            violation = {
                "feature_date": feature_date,
                "data_date": data_date,
                "feature_name": feature_name,
                "violation_type": "future_data_access",
                "severity": "high",
                "detected_at": datetime.now(),
                "days_ahead": (data_date - feature_date).days,
            }
            self.violations.append(violation)
            self.validation_stats["violations_count"] += 1

            if self.strict_mode:
                logger.error(
                    f"CRITICAL: Lookahead bias detected: {feature_name} uses data from {data_date} on {feature_date}"
                )
                raise ValueError(f"Lookahead bias violation: {feature_name}")
            else:
                logger.warning(
                    f"Lookahead bias detected: {feature_name} uses data from {data_date} on {feature_date}"
                )
            return False
        return True

    def validate_rolling_window(
        self,
        feature_date: date,
        window_start: date,
        window_end: date,
        feature_name: str,
    ) -> bool:
        """Enhanced rolling window validation with detailed metrics."""
        self.validation_stats["total_validations"] += 1

        if window_end > feature_date:
            violation = {
                "feature_date": feature_date,
                "window_start": window_start,
                "window_end": window_end,
                "feature_name": feature_name,
                "violation_type": "future_window_data",
                "severity": "high",
                "detected_at": datetime.now(),
                "days_ahead": (window_end - feature_date).days,
            }
            self.violations.append(violation)
            self.validation_stats["violations_count"] += 1

            if self.strict_mode:
                logger.error(
                    f"CRITICAL: Rolling window lookahead bias: {feature_name} window ends on {window_end} > feature_date {feature_date}"
                )
                raise ValueError(f"Rolling window lookahead bias: {feature_name}")
            else:
                logger.warning(
                    f"Rolling window lookahead bias: {feature_name} window ends on {window_end} > feature_date {feature_date}"
                )
            return False
        return True

    def validate_feature_target_alignment(
        self, feature_date: date, target_date: date, feature_name: str
    ) -> bool:
        """Ensure proper feature-target temporal alignment."""
        self.validation_stats["total_validations"] += 1

        # Target should be exactly 1 day after feature date
        expected_target_date = feature_date + timedelta(days=1)

        if target_date != expected_target_date:
            violation = {
                "feature_date": feature_date,
                "target_date": target_date,
                "expected_target_date": expected_target_date,
                "feature_name": feature_name,
                "violation_type": "incorrect_target_alignment",
                "severity": "medium",
                "detected_at": datetime.now(),
            }
            self.violations.append(violation)
            logger.warning(
                f"Target alignment issue: {feature_name} target_date {target_date} != expected {expected_target_date}"
            )
            return False
        return True

    def get_violations_summary(self) -> Dict[str, Any]:
        """Enhanced violations summary with statistics."""
        if not self.violations:
            return {
                "has_violations": False,
                "count": 0,
                "validation_stats": self.validation_stats,
                "violation_rate": 0.0,
            }

        violation_types = defaultdict(int)
        severity_counts = defaultdict(int)

        for violation in self.violations:
            violation_types[violation["violation_type"]] += 1
            severity_counts[violation["severity"]] += 1

        return {
            "has_violations": True,
            "count": len(self.violations),
            "violations": self.violations[:10],  # First 10 violations
            "violation_types": dict(violation_types),
            "severity_breakdown": dict(severity_counts),
            "validation_stats": self.validation_stats,
            "violation_rate": self.validation_stats["violations_count"]
            / max(1, self.validation_stats["total_validations"]),
        }

    def reset_violations(self):
        """Reset violations for new validation run."""
        self.violations = []
        self.validation_stats["violations_count"] = 0


class FeatureQualityMonitor:
    """Advanced feature quality monitoring."""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager or get_db_manager()
        self.quality_metrics = {}
        self.feature_stats = defaultdict(dict)
        self.quality_issues = []

    def monitor_feature_coverage(
        self, features_df: pd.DataFrame, required_features: List[str]
    ) -> Dict[str, Any]:
        """Monitor feature coverage and completeness."""
        coverage_metrics = {}

        for feature in required_features:
            if feature in features_df.columns:
                non_null_count = features_df[feature].notna().sum()
                total_count = len(features_df)
                coverage_rate = non_null_count / total_count if total_count > 0 else 0

                coverage_metrics[feature] = {
                    "coverage_rate": coverage_rate,
                    "missing_count": total_count - non_null_count,
                    "total_count": total_count,
                    "is_adequate": coverage_rate
                    >= PRODUCTION_CONFIG["quality_threshold"],
                }

                if coverage_rate < PRODUCTION_CONFIG["quality_threshold"]:
                    self.quality_issues.append(
                        {
                            "issue_type": "low_coverage",
                            "feature_name": feature,
                            "coverage_rate": coverage_rate,
                            "severity": "high" if coverage_rate < 0.8 else "medium",
                            "detected_at": datetime.now(),
                        }
                    )
            else:
                coverage_metrics[feature] = {
                    "coverage_rate": 0.0,
                    "missing_count": len(features_df),
                    "total_count": len(features_df),
                    "is_adequate": False,
                }
                self.quality_issues.append(
                    {
                        "issue_type": "missing_feature",
                        "feature_name": feature,
                        "severity": "critical",
                        "detected_at": datetime.now(),
                    }
                )

        return coverage_metrics

    def validate_feature_ranges(
        self, features_df: pd.DataFrame, feature_ranges: Dict[str, Tuple[float, float]]
    ) -> Dict[str, Any]:
        """Validate feature values are within expected ranges."""
        range_results = {}

        for feature_name, (min_val, max_val) in feature_ranges.items():
            if feature_name in features_df.columns:
                feature_data = features_df[feature_name].dropna()
                if len(feature_data) > 0:
                    out_of_range = (
                        (feature_data < min_val) | (feature_data > max_val)
                    ).sum()
                    total_count = len(feature_data)
                    out_of_range_pct = (out_of_range / total_count) * 100

                    range_results[feature_name] = {
                        "out_of_range_count": out_of_range,
                        "out_of_range_percentage": out_of_range_pct,
                        "total_count": total_count,
                        "is_valid": out_of_range_pct <= 5.0,  # 5% threshold
                    }

                    if out_of_range_pct > 5.0:
                        self.quality_issues.append(
                            {
                                "issue_type": "out_of_range_values",
                                "feature_name": feature_name,
                                "out_of_range_percentage": out_of_range_pct,
                                "severity": "high"
                                if out_of_range_pct > 20.0
                                else "medium",
                                "detected_at": datetime.now(),
                            }
                        )
                else:
                    range_results[feature_name] = {
                        "out_of_range_count": 0,
                        "out_of_range_percentage": 0.0,
                        "total_count": 0,
                        "is_valid": False,
                    }
            else:
                range_results[feature_name] = {
                    "out_of_range_count": 0,
                    "out_of_range_percentage": 0.0,
                    "total_count": 0,
                    "is_valid": False,
                }

        return range_results

    def detect_feature_drift(
        self, current_df: pd.DataFrame, reference_df: pd.DataFrame, feature_name: str
    ) -> Dict[str, Any]:
        """Detect feature drift using statistical tests."""
        from scipy import stats

        if (
            feature_name not in current_df.columns
            or feature_name not in reference_df.columns
        ):
            return {
                "drift_detected": False,
                "ks_statistic": 0.0,
                "p_value": 1.0,
                "mean_shift_pct": 0.0,
                "severity": "none",
                "error": f"Feature {feature_name} not found in one or both DataFrames",
            }

        current_data = current_df[feature_name].dropna()
        reference_data = reference_df[feature_name].dropna()

        if len(current_data) == 0 or len(reference_data) == 0:
            return {
                "drift_detected": False,
                "ks_statistic": 0.0,
                "p_value": 1.0,
                "mean_shift_pct": 0.0,
                "severity": "none",
                "error": "Insufficient data for drift detection",
            }

        # Kolmogorov-Smirnov test
        ks_statistic, p_value = stats.ks_2samp(current_data, reference_data)

        # Calculate mean shift
        current_mean = current_data.mean()
        reference_mean = reference_data.mean()
        mean_shift_pct = (
            abs((current_mean - reference_mean) / reference_mean * 100)
            if reference_mean != 0
            else 0
        )

        # Determine drift
        drift_detected = p_value < 0.05  # 5% significance level

        # Determine severity
        if not drift_detected:
            severity = "none"
        elif mean_shift_pct > 20:
            severity = "high"
        elif mean_shift_pct > 10:
            severity = "medium"
        else:
            severity = "low"

        if drift_detected:
            self.quality_issues.append(
                {
                    "issue_type": "feature_drift",
                    "feature_name": feature_name,
                    "ks_statistic": ks_statistic,
                    "p_value": p_value,
                    "mean_shift_pct": mean_shift_pct,
                    "severity": severity,
                    "detected_at": datetime.now(),
                }
            )

        return {
            "drift_detected": drift_detected,
            "ks_statistic": ks_statistic,
            "p_value": p_value,
            "mean_shift_pct": mean_shift_pct,
            "severity": severity,
        }

    def get_quality_summary(self) -> Dict[str, Any]:
        """Get comprehensive quality summary."""
        issue_counts = defaultdict(int)
        severity_counts = defaultdict(int)

        for issue in self.quality_issues:
            issue_counts[issue["issue_type"]] += 1
            severity_counts[issue["severity"]] += 1

        return {
            "total_issues": len(self.quality_issues),
            "issue_breakdown": dict(issue_counts),
            "severity_breakdown": dict(severity_counts),
            "quality_score": max(
                0, 1.0 - (len(self.quality_issues) * 0.1)
            ),  # Simple scoring
            "issues": self.quality_issues[-10:],  # Latest 10 issues
            "timestamp": datetime.now(),
        }


# ============================================================================
# MAIN FEATURE ENGINEERING CLASS
# ============================================================================

class UnifiedFeatureEngineer:
    """
    Unified feature engineer that combines:
    1. Optimized bulk query processing
    2. Comprehensive risk metrics
    3. Lookahead bias validation
    4. Quality monitoring
    5. Performance tracking
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the unified feature engineer."""
        self.db_manager = get_db_manager()
        self.feature_table = "feature_store_account_daily"
        self.config = {**PRODUCTION_CONFIG, **(config or {})}
        
        # Extended rolling windows for risk metrics
        self.rolling_windows = [1, 3, 5, 7, 10, 20, 30]
        
        # Performance tracking
        self.query_stats = {
            "total_queries": 0,
            "bulk_queries": 0,
            "time_saved": 0,
            "query_times": [],
        }
        
        # Validation and monitoring
        self.bias_validator = LookaheadBiasValidator(strict_mode=True)
        self.quality_monitor = FeatureQualityMonitor(self.db_manager)
        
        # Enhanced performance monitoring
        self.query_monitor = QueryPerformanceMonitor(
            log_file=f"logs/feature_engineering_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        # Track overall performance
        self.performance_metrics = {
            "total_processing_time": 0,
            "total_records_processed": 0,
            "total_features_created": 0,
            "memory_peak_mb": 0,
            "errors_encountered": 0,
            "validation_violations": 0,
        }

    @contextmanager
    def memory_manager(self):
        """Context manager for memory tracking."""
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024  # MB

        try:
            yield
        finally:
            import gc
            gc.collect()  # Force garbage collection
            end_memory = process.memory_info().rss / 1024 / 1024  # MB
            peak_memory = max(start_memory, end_memory)

            if peak_memory > self.performance_metrics["memory_peak_mb"]:
                self.performance_metrics["memory_peak_mb"] = peak_memory

    def engineer_features(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        force_rebuild: bool = False,
        validate_bias: bool = True,
        enable_monitoring: bool = True,
        include_enhanced_metrics: bool = True,
    ) -> Dict[str, Any]:
        """
        Main entry point for feature engineering.
        
        Args:
            start_date: Start date for feature engineering
            end_date: End date for feature engineering
            force_rebuild: If True, rebuild features even if they exist
            validate_bias: If True, perform lookahead bias validation
            enable_monitoring: If True, enable quality monitoring
            include_enhanced_metrics: If True, include enhanced risk metrics
            
        Returns:
            Dictionary with processing results, validation summary, and metrics
        """
        start_time = datetime.now()
        
        # Reset metrics for this run
        self.bias_validator.reset_violations()
        self.performance_metrics = {k: 0 for k in self.performance_metrics}
        
        logger.info(
            f"[UNIFIED] Starting feature engineering from {start_date} to {end_date}"
        )
        logger.info(
            f"Options: validation={validate_bias}, monitoring={enable_monitoring}, "
            f"enhanced_metrics={include_enhanced_metrics}, rebuild={force_rebuild}"
        )
        
        try:
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)
            if not start_date:
                start_date = end_date - timedelta(days=7)
            
            # Validate input parameters
            if start_date > end_date:
                raise ValueError(
                    f"Start date {start_date} cannot be after end date {end_date}"
                )
            
            # Get work items
            work_items = self._get_work_items(start_date, end_date, force_rebuild)
            
            if not work_items:
                logger.info("No work items to process")
                return self._create_comprehensive_summary(
                    start_time, 0, validate_bias, enable_monitoring
                )
            
            logger.info(f"Processing {len(work_items)} account-date combinations")
            
            # Process batches
            total_records = self._process_batches(
                work_items, start_date, end_date, validate_bias, include_enhanced_metrics
            )
            
            # Run quality monitoring if enabled
            quality_results = {}
            if enable_monitoring and total_records > 0:
                quality_results = self._run_comprehensive_monitoring(
                    start_date, end_date
                )
            
            # Create result summary
            result = self._create_comprehensive_summary(
                start_time,
                total_records,
                validate_bias,
                enable_monitoring,
                quality_results,
            )
            
            # Log performance metrics
            self.query_monitor.log_summary()
            self.query_monitor.save_performance_log()
            
            # Log completion
            self._log_completion_status(result, include_enhanced_metrics)
            
            return result
            
        except Exception as e:
            self.performance_metrics["errors_encountered"] += 1
            logger.error(f"Feature engineering failed: {str(e)}")
            
            # Save any performance data collected
            self.query_monitor.save_performance_log()
            
            raise

    # ========================================================================
    # DATA FETCHING METHODS
    # ========================================================================
    
    def _get_work_items(
        self, start_date: date, end_date: date, force_rebuild: bool
    ) -> List[Tuple[str, str, date]]:
        """Get list of account-date combinations to process."""
        if force_rebuild:
            query = """
            SELECT DISTINCT account_id, login, snapshot_date as feature_date
            FROM stg_accounts_daily_snapshots
            WHERE snapshot_date >= %s AND snapshot_date <= %s
            ORDER BY snapshot_date, account_id
            """
            params = (start_date, end_date)
        else:
            # Only get missing features
            query = """
            SELECT DISTINCT s.account_id, s.login, s.snapshot_date as feature_date
            FROM stg_accounts_daily_snapshots s
            LEFT JOIN feature_store_account_daily f
                ON s.account_id = f.account_id AND s.snapshot_date = f.feature_date
            WHERE s.snapshot_date >= %s AND s.snapshot_date <= %s
                AND f.account_id IS NULL
            ORDER BY s.snapshot_date, s.account_id
            """
            params = (start_date, end_date)

        results = self.db_manager.model_db.execute_query(query, params)
        return [(r["account_id"], r["login"], r["feature_date"]) for r in results]

    def _bulk_fetch_static_features(
        self, account_ids: List[str], dates: List[date]
    ) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch static account features."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(account_ids) * len(dates)

        query = """
        SELECT 
            account_id,
            date,
            starting_balance,
            max_daily_drawdown_pct,
            max_drawdown_pct,
            profit_target_pct,
            max_leverage,
            CASE WHEN is_drawdown_relative THEN 1 ELSE 0 END as is_drawdown_relative,
            CASE WHEN liquidate_friday THEN 1 ELSE 0 END as liquidate_friday,
            inactivity_period,
            CASE WHEN daily_drawdown_by_balance_equity THEN 1 ELSE 0 END as daily_drawdown_by_balance_equity,
            CASE WHEN enable_consistency THEN 1 ELSE 0 END as enable_consistency
        FROM stg_accounts_daily_snapshots
        WHERE account_id = ANY(%s) AND date = ANY(%s)
        """

        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))

        # Convert to lookup dictionary
        features_lookup = {}
        for row in results:
            key = (row["account_id"], row["date"])
            features_lookup[key] = {
                "starting_balance": row["starting_balance"],
                "max_daily_drawdown_pct": row["max_daily_drawdown_pct"],
                "max_drawdown_pct": row["max_drawdown_pct"],
                "profit_target_pct": row["profit_target_pct"],
                "max_leverage": row["max_leverage"],
                "is_drawdown_relative": row["is_drawdown_relative"],
                "liquidate_friday": row["liquidate_friday"],
                "inactivity_period": row["inactivity_period"],
                "daily_drawdown_by_balance_equity": row["daily_drawdown_by_balance_equity"],
                "enable_consistency": row["enable_consistency"],
            }

        logger.debug(f"Bulk fetched {len(features_lookup)} static feature records")
        return features_lookup

    def _bulk_fetch_dynamic_features(
        self, account_ids: List[str], dates: List[date]
    ) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch dynamic account features."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(account_ids) * len(dates)

        query = """
        SELECT 
            account_id,
            date,
            current_balance,
            current_equity,
            days_since_first_trade,
            active_trading_days_count,
            distance_to_profit_target,
            distance_to_max_drawdown
        FROM stg_accounts_daily_snapshots
        WHERE account_id = ANY(%s) AND date = ANY(%s)
        """

        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))

        # Convert to lookup dictionary
        features_lookup = {}
        for row in results:
            key = (row["account_id"], row["date"])
            features_lookup[key] = {
                "current_balance": row["current_balance"],
                "current_equity": row["current_equity"],
                "days_since_first_trade": row["days_since_first_trade"] or 0,
                "active_trading_days_count": row["active_trading_days_count"] or 0,
                "distance_to_profit_target": row["distance_to_profit_target"],
                "distance_to_max_drawdown": row["distance_to_max_drawdown"],
            }

        return features_lookup

    def _bulk_fetch_open_positions(
        self, account_ids: List[str], dates: List[date]
    ) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch open positions data."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(account_ids) * len(dates)

        query = """
        SELECT 
            account_id,
            trade_date,
            SUM(unrealized_pnl) as open_pnl,
            SUM(volume_usd) as open_positions_volume
        FROM raw_trades_open
        WHERE account_id = ANY(%s) AND trade_date = ANY(%s)
        GROUP BY account_id, trade_date
        """

        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))

        # Convert to lookup dictionary
        positions_lookup = {}
        for row in results:
            key = (row["account_id"], row["trade_date"])
            positions_lookup[key] = {
                "open_pnl": row["open_pnl"] or 0.0,
                "open_positions_volume": row["open_positions_volume"] or 0.0,
            }

        return positions_lookup

    def _bulk_fetch_performance_data(
        self, account_ids: List[str], start_date: date, end_date: date
    ) -> Dict[str, pd.DataFrame]:
        """Bulk fetch historical performance data for all accounts."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(account_ids) * 60

        # Get more historical data for rolling windows
        historical_start = start_date - timedelta(days=90)

        query = """
        SELECT 
            account_id,
            date,
            net_profit
        FROM raw_metrics_daily
        WHERE account_id = ANY(%s) 
            AND date >= %s 
            AND date <= %s
        ORDER BY account_id, date DESC
        """

        df = self.db_manager.model_db.execute_query_df(
            query, (account_ids, historical_start, end_date)
        )

        # Group by account_id for easy lookup
        performance_lookup = {}
        if not df.empty:
            for account_id, group in df.groupby("account_id"):
                performance_lookup[account_id] = group.sort_values(
                    "date", ascending=False
                )

        logger.debug(
            f"Bulk fetched performance data for {len(performance_lookup)} accounts"
        )
        return performance_lookup

    def _bulk_fetch_trades_data(
        self, account_ids: List[str], start_date: date, end_date: date
    ) -> Dict[str, pd.DataFrame]:
        """Bulk fetch trades data for behavioral features."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(account_ids) * 5

        # Get trades for behavioral features (5-day window)
        behavioral_start = start_date - timedelta(days=5)

        query = """
        SELECT 
            trade_date,
            broker,
            manager,
            platform,
            login,
            account_id,
            std_symbol,
            side,
            lots,
            contract_size,
            qty_in_base_ccy,
            volume_usd,
            stop_loss,
            take_profit,
            open_time,
            open_price,
            close_time,
            close_price,
            duration,
            profit,
            commission,
            fee,
            swap,
            comment
            
        FROM raw_trades_closed
        WHERE account_id = ANY(%s) 
            AND trade_date >= %s 
            AND trade_date <= %s
        ORDER BY account_id, trade_date
        """

        df = self.db_manager.model_db.execute_query_df(
            query, (account_ids, behavioral_start, end_date)
        )

        # Group by account_id for easy lookup
        trades_lookup = {}
        if not df.empty:
            for account_id, group in df.groupby("account_id"):
                trades_lookup[account_id] = group

        logger.debug(f"Bulk fetched trades data for {len(trades_lookup)} accounts")
        return trades_lookup

    def _bulk_fetch_market_data(self, dates: List[date]) -> Dict[date, Dict]:
        """Bulk fetch market regime data."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(dates)

        query = """
        WITH ranked_regimes AS (
            SELECT 
                date,
                market_news,
                instruments,
                country_economic_indicators,
                news_analysis,
                summary,
                ingestion_timestamp,
                ROW_NUMBER() OVER (PARTITION BY date ORDER BY ingestion_timestamp DESC) as rn
            FROM raw_regimes_daily
            WHERE date = ANY(%s)
        )
        SELECT * FROM ranked_regimes WHERE rn = 1
        """

        results = self.db_manager.model_db.execute_query(query, (dates,))

        # Convert to lookup dictionary
        market_lookup = {}
        for row in results:
            market_lookup[row["date"]] = self._parse_market_features(row)

        logger.debug(f"Bulk fetched market data for {len(market_lookup)} dates")
        return market_lookup

    def _bulk_fetch_enhanced_metrics(
        self, account_ids: List[str], dates: List[date]
    ) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch enhanced metrics data including all risk factors."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(account_ids) * len(dates)
        
        query = """
        SELECT 
            account_id,
            date,
            -- Core performance metrics
            net_profit,
            gross_profit,
            gross_loss,
            num_trades,
            winning_trades,
            losing_trades,
            win_rate,
            profit_factor,
            -- Enhanced risk metrics
            gain_to_pain,
            success_rate,
            mean_profit,
            median_profit,
            std_profits,
            risk_adj_profit,
            -- Distribution metrics
            min_profit,
            max_profit,
            profit_perc_10,
            profit_perc_25,
            profit_perc_75,
            profit_perc_90,
            -- Return metrics
            daily_sharpe,
            daily_sortino,
            mean_ret,
            std_rets,
            risk_adj_ret,
            downside_std_rets,
            downside_risk_adj_ret,
            -- Relative metrics
            rel_net_profit,
            rel_mean_profit,
            rel_median_profit,
            rel_std_profits,
            rel_risk_adj_profit,
            -- Drawdown metrics
            mean_drawdown,
            median_drawdown,
            max_drawdown,
            mean_num_trades_in_dd,
            median_num_trades_in_dd,
            max_num_trades_in_dd,
            -- Volume and lot metrics
            total_lots,
            total_volume,
            mean_winning_lot,
            mean_losing_lot,
            mean_winning_volume,
            mean_losing_volume,
            -- Duration metrics
            mean_duration,
            median_duration,
            std_durations,
            cv_durations,
            -- SL/TP metrics
            mean_tp,
            mean_sl,
            mean_tp_vs_sl,
            -- Consecutive patterns
            mean_num_consec_wins,
            max_num_consec_wins,
            mean_num_consec_losses,
            max_num_consec_losses,
            -- Position metrics
            mean_num_open_pos,
            max_num_open_pos,
            mean_val_open_pos,
            -- Activity metrics
            mean_trades_per_day,
            median_trades_per_day,
            max_trades_per_day,
            num_traded_symbols,
            -- Additional metadata
            plan_id,
            status,
            phase
        FROM raw_metrics_daily
        WHERE account_id = ANY(%s) AND date = ANY(%s)
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))
        
        # Convert to lookup dictionary
        metrics_lookup = {}
        for row in results:
            key = (row["account_id"], row["date"])
            metrics_lookup[key] = {k: v for k, v in row.items() if k not in ["account_id", "date"]}
        
        logger.debug(f"Bulk fetched {len(metrics_lookup)} enhanced metric records")
        return metrics_lookup

    def _bulk_fetch_alltime_metrics(
        self, account_ids: List[str]
    ) -> Dict[str, Dict]:
        """Bulk fetch all-time metrics for baseline risk profiling."""
        self.query_stats["bulk_queries"] += 1
        
        query = """
        WITH latest_metrics AS (
            SELECT DISTINCT ON (account_id)
                account_id,
                -- Lifetime performance
                net_profit as lifetime_net_profit,
                num_trades as lifetime_num_trades,
                win_rate as lifetime_win_rate,
                profit_factor as lifetime_profit_factor,
                sharpe_ratio as lifetime_sharpe,
                sortino_ratio as lifetime_sortino,
                -- Risk metrics
                gain_to_pain as lifetime_gain_to_pain,
                risk_adj_profit as lifetime_risk_adj_profit,
                daily_sharpe as lifetime_daily_sharpe,
                daily_sortino as lifetime_daily_sortino,
                -- Behavioral metrics
                mean_duration as lifetime_mean_duration,
                mean_tp_vs_sl as lifetime_mean_tp_vs_sl,
                -- Consistency metrics
                mean_trades_per_day as lifetime_mean_trades_per_day,
                num_traded_symbols as lifetime_num_traded_symbols,
                -- Experience metrics
                days_since_first_trade,
                num_trades,
                -- Status
                plan_id,
                trader_id,
                status,
                phase
            FROM raw_metrics_alltime
            WHERE account_id = ANY(%s)
            ORDER BY account_id, ingestion_timestamp DESC
        )
        SELECT * FROM latest_metrics
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_ids,))
        
        # Convert to lookup dictionary
        alltime_lookup = {}
        for row in results:
            account_id = row["account_id"]
            alltime_lookup[account_id] = {k: v for k, v in row.items() if k != "account_id"}
        
        logger.debug(f"Bulk fetched all-time metrics for {len(alltime_lookup)} accounts")
        return alltime_lookup

    # ========================================================================
    # FEATURE CALCULATION METHODS
    # ========================================================================

    def _parse_market_features(self, regime_data: Dict) -> Dict[str, Any]:
        """Parse market features from regime data."""
        features = {}

        # Parse sentiment score
        try:
            news_analysis = (
                json.loads(regime_data["news_analysis"])
                if isinstance(regime_data["news_analysis"], str)
                else regime_data["news_analysis"]
            )

            sentiment_score = news_analysis.get("sentiment_summary", {}).get(
                "average_score", 0.0
            )
            features["market_sentiment_score"] = sentiment_score
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            features["market_sentiment_score"] = 0.0

        # Parse volatility regime and liquidity state
        try:
            summary = (
                json.loads(regime_data["summary"])
                if isinstance(regime_data["summary"], str)
                else regime_data["summary"]
            )

            key_metrics = summary.get("key_metrics", {})
            features["market_volatility_regime"] = key_metrics.get(
                "volatility_regime", "normal"
            )
            features["market_liquidity_state"] = key_metrics.get(
                "liquidity_state", "normal"
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            features["market_volatility_regime"] = "normal"
            features["market_liquidity_state"] = "normal"

        # Parse instrument data
        try:
            instruments = (
                json.loads(regime_data["instruments"])
                if isinstance(regime_data["instruments"], str)
                else regime_data["instruments"]
            )

            # Get specific asset metrics
            vix_data = instruments.get("data", {}).get("VIX", {})
            features["vix_level"] = vix_data.get("last_price", 15.0)

            dxy_data = instruments.get("data", {}).get("DXY", {})
            features["dxy_level"] = dxy_data.get("last_price", 100.0)

            sp500_data = instruments.get("data", {}).get("SP500", {})
            features["sp500_daily_return"] = sp500_data.get("daily_return", 0.0)

            btc_data = instruments.get("data", {}).get("BTCUSD", {})
            features["btc_volatility_90d"] = btc_data.get("volatility_90d", 0.5)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            features.update(
                {
                    "vix_level": 15.0,
                    "dxy_level": 100.0,
                    "sp500_daily_return": 0.0,
                    "btc_volatility_90d": 0.5,
                }
            )

        # Parse economic indicators
        try:
            indicators = (
                json.loads(regime_data["country_economic_indicators"])
                if isinstance(regime_data["country_economic_indicators"], str)
                else regime_data["country_economic_indicators"]
            )

            features["fed_funds_rate"] = indicators.get("fed_funds_rate_effective", 5.0)
        except (json.JSONDecodeError, KeyError, TypeError):
            features["fed_funds_rate"] = 5.0

        return features

    def _calculate_features_from_bulk_data(
        self,
        account_id: str,
        login: str,
        feature_date: date,
        bulk_data: Dict[str, Any],
        include_enhanced: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Calculate features using bulk-fetched data."""
        try:
            features = {
                "account_id": account_id,
                "login": login,
                "feature_date": feature_date,
                "feature_version": FEATURE_VERSION,
            }

            # 1. Static features from bulk data
            static_key = (account_id, feature_date)
            if static_key in bulk_data["static_features"]:
                features.update(bulk_data["static_features"][static_key])
            else:
                # Use default values
                features.update(
                    {
                        "starting_balance": None,
                        "max_daily_drawdown_pct": None,
                        "max_drawdown_pct": None,
                        "profit_target_pct": None,
                        "max_leverage": None,
                        "is_drawdown_relative": 0,
                        "liquidate_friday": 0,
                        "inactivity_period": None,
                        "daily_drawdown_by_balance_equity": 0,
                        "enable_consistency": 0,
                    }
                )

            # 2. Dynamic features from bulk data
            dynamic_key = (account_id, feature_date)
            if dynamic_key in bulk_data["dynamic_features"]:
                features.update(bulk_data["dynamic_features"][dynamic_key])
            else:
                features.update(
                    {
                        "current_balance": None,
                        "current_equity": None,
                        "days_since_first_trade": 0,
                        "active_trading_days_count": 0,
                        "distance_to_profit_target": None,
                        "distance_to_max_drawdown": None,
                    }
                )

            # 3. Open positions from bulk data
            positions_key = (account_id, feature_date)
            if positions_key in bulk_data["open_positions"]:
                features.update(bulk_data["open_positions"][positions_key])
            else:
                features["open_pnl"] = 0.0
                features["open_positions_volume"] = 0.0

            # 4. Performance features from bulk data
            performance_features = self._calculate_performance_features_from_bulk(
                account_id, feature_date, bulk_data["performance_data"]
            )
            features.update(performance_features)

            # 5. Behavioral features from bulk data
            behavioral_features = self._calculate_behavioral_features_from_bulk(
                account_id, feature_date, bulk_data["trades_data"]
            )
            features.update(behavioral_features)

            # 6. Market features from bulk data
            if feature_date in bulk_data["market_data"]:
                features.update(bulk_data["market_data"][feature_date])
            else:
                # Default market features
                features.update(
                    {
                        "market_sentiment_score": 0.0,
                        "market_volatility_regime": "normal",
                        "market_liquidity_state": "normal",
                        "vix_level": 15.0,
                        "dxy_level": 100.0,
                        "sp500_daily_return": 0.0,
                        "btc_volatility_90d": 0.5,
                        "fed_funds_rate": 5.0,
                    }
                )

            # 7. Time features (calculated, no query needed)
            time_features = self._get_time_features(feature_date)
            features.update(time_features)
            
            # 8. Enhanced risk features (if enabled)
            if include_enhanced and "enhanced_metrics" in bulk_data:
                # Add risk-adjusted features
                risk_features = self._calculate_risk_adjusted_features(
                    account_id,
                    feature_date,
                    bulk_data.get("enhanced_metrics", {}),
                    bulk_data.get("alltime_metrics", {})
                )
                features.update(risk_features)
                
                # Add behavioral consistency features
                consistency_features = self._calculate_behavioral_consistency_features(
                    account_id,
                    feature_date,
                    bulk_data.get("enhanced_metrics", {}),
                    window=7
                )
                features.update(consistency_features)
                
                # Add enhanced rolling features
                rolling_features = self._calculate_enhanced_rolling_features(
                    account_id,
                    feature_date,
                    bulk_data.get("enhanced_metrics", {})
                )
                features.update(rolling_features)
                
                # Add market regime interaction features
                if "market_data" in bulk_data:
                    regime_features = self._calculate_market_regime_interaction_features(
                        account_id,
                        feature_date,
                        bulk_data.get("enhanced_metrics", {}),
                        bulk_data["market_data"]
                    )
                    features.update(regime_features)

            return features

        except Exception as e:
            logger.error(
                f"Error calculating features for {account_id} on {feature_date}: {str(e)}"
            )
            return None

    def _calculate_performance_features_from_bulk(
        self,
        account_id: str,
        feature_date: date,
        performance_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """Calculate rolling performance features from bulk data."""
        features = {}

        if account_id not in performance_data:
            # Return default values for all rolling features
            for window in self.rolling_windows:
                features.update(self._get_default_rolling_features(window))
            return features

        # Get the account's performance data
        pnl_df = performance_data[account_id]

        # Filter to only data up to feature_date
        pnl_df = pnl_df[pnl_df["date"] <= feature_date]

        if pnl_df.empty:
            for window in self.rolling_windows:
                features.update(self._get_default_rolling_features(window))
            return features

        # Calculate features for each rolling window
        for window in self.rolling_windows:
            if len(pnl_df) >= window:
                window_data = pnl_df.head(window)

                # Basic statistics
                features[f"rolling_pnl_sum_{window}d"] = window_data["net_profit"].sum()
                features[f"rolling_pnl_avg_{window}d"] = window_data[
                    "net_profit"
                ].mean()
                features[f"rolling_pnl_std_{window}d"] = window_data["net_profit"].std()

                if window >= 3:
                    features[f"rolling_pnl_min_{window}d"] = window_data[
                        "net_profit"
                    ].min()
                    features[f"rolling_pnl_max_{window}d"] = window_data[
                        "net_profit"
                    ].max()

                    # Win rate
                    wins = (window_data["net_profit"] > 0).sum()
                    features[f"win_rate_{window}d"] = (wins / window) * 100

                if window >= 5:
                    # Profit factor
                    gains = window_data[window_data["net_profit"] > 0][
                        "net_profit"
                    ].sum()
                    losses = abs(
                        window_data[window_data["net_profit"] < 0]["net_profit"].sum()
                    )
                    if losses > 0:
                        features[f"profit_factor_{window}d"] = gains / losses
                    else:
                        features[f"profit_factor_{window}d"] = gains if gains > 0 else 0

                    # Sharpe ratio (simplified)
                    if features[f"rolling_pnl_std_{window}d"] > 0:
                        features[f"sharpe_ratio_{window}d"] = (
                            features[f"rolling_pnl_avg_{window}d"]
                            / features[f"rolling_pnl_std_{window}d"]
                        ) * np.sqrt(252)  # Annualized
                    else:
                        features[f"sharpe_ratio_{window}d"] = 0
            else:
                features.update(self._get_default_rolling_features(window))

        return features

    def _calculate_behavioral_features_from_bulk(
        self, account_id: str, feature_date: date, trades_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, Any]:
        """Calculate behavioral features from bulk trades data."""
        features = {}

        if account_id not in trades_data:
            # Return default values
            return {
                "trades_count_5d": 0,
                "avg_trade_duration_5d": 0.0,
                "avg_lots_per_trade_5d": 0.0,
                "avg_volume_per_trade_5d": 0.0,
                "stop_loss_usage_rate_5d": 0.0,
                "take_profit_usage_rate_5d": 0.0,
                "buy_sell_ratio_5d": 0.5,
                "top_symbol_concentration_5d": 0.0,
            }

        # Get the account's trades data
        trades_df = trades_data[account_id]

        # Filter to 5-day window
        window_start = feature_date - timedelta(days=4)
        trades_df = trades_df[
            (trades_df["trade_date"] >= window_start)
            & (trades_df["trade_date"] <= feature_date)
        ]

        if trades_df.empty:
            return {
                "trades_count_5d": 0,
                "avg_trade_duration_5d": 0.0,
                "avg_lots_per_trade_5d": 0.0,
                "avg_volume_per_trade_5d": 0.0,
                "stop_loss_usage_rate_5d": 0.0,
                "take_profit_usage_rate_5d": 0.0,
                "buy_sell_ratio_5d": 0.5,
                "top_symbol_concentration_5d": 0.0,
            }

        # Trade count
        features["trades_count_5d"] = len(trades_df)

        # Average trade duration (in hours)
        if "open_time" in trades_df.columns and "close_time" in trades_df.columns:
            trades_df["duration"] = (
                pd.to_datetime(trades_df["close_time"])
                - pd.to_datetime(trades_df["open_time"])
            ).dt.total_seconds() / 3600
            features["avg_trade_duration_5d"] = trades_df["duration"].mean()
        else:
            features["avg_trade_duration_5d"] = 0.0

        # Average lots and volume
        features["avg_lots_per_trade_5d"] = trades_df["lots"].mean()
        features["avg_volume_per_trade_5d"] = trades_df["volume_usd"].mean()

        # Stop loss and take profit usage
        sl_count = (
            trades_df["stop_loss"].notna() & (trades_df["stop_loss"] != 0)
        ).sum()
        tp_count = (
            trades_df["take_profit"].notna() & (trades_df["take_profit"] != 0)
        ).sum()
        features["stop_loss_usage_rate_5d"] = (sl_count / len(trades_df)) * 100
        features["take_profit_usage_rate_5d"] = (tp_count / len(trades_df)) * 100

        # Buy/sell ratio
        buy_count = (trades_df["side"] == "buy").sum()
        sell_count = (trades_df["side"] == "sell").sum()
        total_sides = buy_count + sell_count
        if total_sides > 0:
            features["buy_sell_ratio_5d"] = buy_count / total_sides
        else:
            features["buy_sell_ratio_5d"] = 0.5

        # Symbol concentration
        if "std_symbol" in trades_df.columns:
            symbol_counts = trades_df["std_symbol"].value_counts()
            if len(symbol_counts) > 0:
                features["top_symbol_concentration_5d"] = (
                    symbol_counts.iloc[0] / len(trades_df)
                ) * 100
            else:
                features["top_symbol_concentration_5d"] = 0.0
        else:
            features["top_symbol_concentration_5d"] = 0.0

        return features

    def _get_default_rolling_features(self, window: int) -> Dict[str, float]:
        """Get default values for rolling features when not enough data."""
        features = {
            f"rolling_pnl_sum_{window}d": 0.0,
            f"rolling_pnl_avg_{window}d": 0.0,
            f"rolling_pnl_std_{window}d": 0.0,
        }

        if window >= 3:
            features[f"rolling_pnl_min_{window}d"] = 0.0
            features[f"rolling_pnl_max_{window}d"] = 0.0
            features[f"win_rate_{window}d"] = 0.0

        if window >= 5:
            features[f"profit_factor_{window}d"] = 0.0
            features[f"sharpe_ratio_{window}d"] = 0.0

        return features

    def _get_time_features(self, feature_date: date) -> Dict[str, Any]:
        """Calculate date and time features."""
        return {
            "day_of_week": feature_date.weekday(),  # 0 = Monday, 6 = Sunday
            "week_of_month": (feature_date.day - 1) // 7 + 1,
            "month": feature_date.month,
            "quarter": (feature_date.month - 1) // 3 + 1,
            "day_of_year": feature_date.timetuple().tm_yday,
            "is_month_start": feature_date.day <= 3,
            "is_month_end": feature_date.day >= 28,
            "is_quarter_start": feature_date.month in [1, 4, 7, 10]
            and feature_date.day <= 3,
            "is_quarter_end": feature_date.month in [3, 6, 9, 12]
            and feature_date.day >= 28,
        }

    # ========================================================================
    # ENHANCED RISK FEATURES
    # ========================================================================

    def _calculate_risk_adjusted_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict],
        alltime_metrics: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Calculate advanced risk-adjusted features."""
        features = {}
        
        # Get daily metrics for feature date
        daily_key = (account_id, feature_date)
        if daily_key in enhanced_metrics:
            daily_data = enhanced_metrics[daily_key]
            
            # Core risk metrics
            features["daily_gain_to_pain"] = daily_data.get("gain_to_pain", 0.0)
            features["daily_risk_adj_profit"] = daily_data.get("risk_adj_profit", 0.0)
            features["daily_sharpe"] = daily_data.get("daily_sharpe", 0.0)
            features["daily_sortino"] = daily_data.get("daily_sortino", 0.0)
            
            # Distribution features
            features["profit_distribution_skew"] = self._calculate_skewness(daily_data)
            features["profit_distribution_kurtosis"] = self._calculate_kurtosis(daily_data)
            features["profit_tail_ratio"] = self._calculate_tail_ratio(daily_data)
            
            # Drawdown severity
            if daily_data.get("mean_drawdown") and daily_data.get("max_drawdown"):
                features["drawdown_severity_ratio"] = abs(
                    daily_data["mean_drawdown"] / daily_data["max_drawdown"]
                ) if daily_data["max_drawdown"] != 0 else 0
            
            # Trading efficiency
            if daily_data.get("total_volume", 0) > 0:
                features["profit_per_volume"] = (
                    daily_data.get("net_profit", 0) / daily_data["total_volume"]
                ) * 10000  # Normalize
            
            if daily_data.get("mean_duration", 0) > 0:
                features["profit_per_hour"] = (
                    daily_data.get("net_profit", 0) / daily_data["mean_duration"]
                )
        
        # Compare to lifetime metrics
        if account_id in alltime_metrics:
            lifetime = alltime_metrics[account_id]
            
            # Performance relative to lifetime
            if lifetime.get("lifetime_daily_sharpe"):
                features["sharpe_vs_lifetime"] = (
                    features.get("daily_sharpe", 0) - lifetime["lifetime_daily_sharpe"]
                )
            
            if lifetime.get("lifetime_win_rate"):
                current_win_rate = daily_data.get("win_rate", 0) if daily_key in enhanced_metrics else 0
                features["win_rate_vs_lifetime"] = current_win_rate - lifetime["lifetime_win_rate"]
            
            # Experience-weighted features
            days_trading = lifetime.get("days_since_first_trade", 1)
            features["experience_factor"] = min(days_trading / 90, 1.0)  # Cap at 90 days
            features["trades_per_day_experience_adj"] = (
                daily_data.get("mean_trades_per_day", 0) * features["experience_factor"]
                if daily_key in enhanced_metrics else 0
            )
        
        return features

    def _calculate_behavioral_consistency_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict],
        window: int = 7
    ) -> Dict[str, Any]:
        """Calculate behavioral consistency features over time."""
        features = {}
        
        # Collect metrics over window
        window_data = []
        for i in range(window):
            check_date = feature_date - timedelta(days=i)
            key = (account_id, check_date)
            if key in enhanced_metrics:
                window_data.append(enhanced_metrics[key])
        
        if len(window_data) >= 3:  # Need minimum data
            # Trading frequency consistency
            trades_per_day = [d.get("num_trades", 0) for d in window_data]
            features[f"trading_frequency_cv_{window}d"] = (
                np.std(trades_per_day) / np.mean(trades_per_day)
                if np.mean(trades_per_day) > 0 else 0
            )
            
            # Lot size consistency
            avg_lots = [d.get("total_lots", 0) / max(d.get("num_trades", 1), 1) for d in window_data]
            features[f"lot_size_consistency_{window}d"] = (
                1 - (np.std(avg_lots) / np.mean(avg_lots))
                if np.mean(avg_lots) > 0 else 0
            )
            
            # Win rate stability
            win_rates = [d.get("win_rate", 0) for d in window_data]
            features[f"win_rate_stability_{window}d"] = (
                1 - (np.std(win_rates) / 100)  # Normalized
            )
            
            # Risk management consistency
            sl_usage = []
            tp_usage = []
            for d in window_data:
                if d.get("mean_sl", 0) > 0:
                    sl_usage.append(1)
                else:
                    sl_usage.append(0)
                if d.get("mean_tp", 0) > 0:
                    tp_usage.append(1)
                else:
                    tp_usage.append(0)
            
            features[f"sl_usage_consistency_{window}d"] = np.mean(sl_usage)
            features[f"tp_usage_consistency_{window}d"] = np.mean(tp_usage)
            
            # Consecutive pattern features
            max_consec_wins = [d.get("max_num_consec_wins", 0) for d in window_data]
            max_consec_losses = [d.get("max_num_consec_losses", 0) for d in window_data]
            features[f"avg_max_consec_wins_{window}d"] = np.mean(max_consec_wins)
            features[f"avg_max_consec_losses_{window}d"] = np.mean(max_consec_losses)
        else:
            # Default values when insufficient data
            features[f"trading_frequency_cv_{window}d"] = 0.0
            features[f"lot_size_consistency_{window}d"] = 0.0
            features[f"win_rate_stability_{window}d"] = 0.0
            features[f"sl_usage_consistency_{window}d"] = 0.0
            features[f"tp_usage_consistency_{window}d"] = 0.0
            features[f"avg_max_consec_wins_{window}d"] = 0.0
            features[f"avg_max_consec_losses_{window}d"] = 0.0
        
        return features

    def _calculate_enhanced_rolling_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict]
    ) -> Dict[str, Any]:
        """Calculate enhanced rolling window features."""
        features = {}
        
        for window in self.rolling_windows:
            # Collect data for window
            window_data = []
            for i in range(window):
                check_date = feature_date - timedelta(days=i)
                key = (account_id, check_date)
                if key in enhanced_metrics:
                    window_data.append(enhanced_metrics[key])
            
            if len(window_data) >= min(3, window):  # Adaptive minimum
                # Risk-adjusted returns
                sharpe_values = [d.get("daily_sharpe", 0) for d in window_data]
                features[f"avg_sharpe_{window}d"] = np.mean(sharpe_values)
                features[f"sharpe_volatility_{window}d"] = np.std(sharpe_values)
                
                # Gain-to-pain ratio
                gtp_values = [d.get("gain_to_pain", 0) for d in window_data]
                features[f"avg_gain_to_pain_{window}d"] = np.mean(gtp_values)
                
                # Risk-adjusted profit
                risk_adj_values = [d.get("risk_adj_profit", 0) for d in window_data]
                features[f"sum_risk_adj_profit_{window}d"] = np.sum(risk_adj_values)
                
                # Drawdown analysis
                dd_values = [abs(d.get("mean_drawdown", 0)) for d in window_data]
                features[f"avg_drawdown_{window}d"] = np.mean(dd_values)
                features[f"max_drawdown_{window}d"] = np.max(dd_values) if dd_values else 0
                
                # Trading intensity
                trades = [d.get("num_trades", 0) for d in window_data]
                features[f"num_trades_{window}d"] = np.sum(trades)
                features[f"trading_days_{window}d"] = len([t for t in trades if t > 0])
                
                # Efficiency metrics
                if window >= 7:
                    volumes = [d.get("total_volume", 0) for d in window_data]
                    profits = [d.get("net_profit", 0) for d in window_data]
                    total_volume = np.sum(volumes)
                    total_profit = np.sum(profits)
                    
                    if total_volume > 0:
                        features[f"volume_weighted_return_{window}d"] = (
                            total_profit / total_volume
                        ) * 10000
                    
                    # Time-weighted returns
                    durations = [d.get("mean_duration", 1) for d in window_data]
                    time_weighted_profits = [
                        p / d if d > 0 else 0 
                        for p, d in zip(profits, durations)
                    ]
                    features[f"time_weighted_return_{window}d"] = np.mean(time_weighted_profits)
            else:
                # Default values
                features[f"avg_sharpe_{window}d"] = 0.0
                features[f"sharpe_volatility_{window}d"] = 0.0
                features[f"avg_gain_to_pain_{window}d"] = 0.0
                features[f"sum_risk_adj_profit_{window}d"] = 0.0
                features[f"avg_drawdown_{window}d"] = 0.0
                features[f"max_drawdown_{window}d"] = 0.0
                features[f"num_trades_{window}d"] = 0
                features[f"trading_days_{window}d"] = 0
                
                if window >= 7:
                    features[f"volume_weighted_return_{window}d"] = 0.0
                    features[f"time_weighted_return_{window}d"] = 0.0
        
        return features

    def _calculate_market_regime_interaction_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict],
        market_data: Dict[date, Dict]
    ) -> Dict[str, Any]:
        """Calculate features that capture trader performance under different market regimes."""
        features = {}
        
        # Get current market regime
        current_market = market_data.get(feature_date, {})
        volatility_regime = current_market.get("market_volatility_regime", "normal")
        
        # Performance in different volatility regimes
        high_vol_days = []
        normal_vol_days = []
        low_vol_days = []
        
        for i in range(30):  # Look back 30 days
            check_date = feature_date - timedelta(days=i)
            market = market_data.get(check_date, {})
            metrics_key = (account_id, check_date)
            
            if metrics_key in enhanced_metrics:
                daily_profit = enhanced_metrics[metrics_key].get("net_profit", 0)
                vol_regime = market.get("market_volatility_regime", "normal")
                
                if "high" in vol_regime.lower():
                    high_vol_days.append(daily_profit)
                elif "low" in vol_regime.lower():
                    low_vol_days.append(daily_profit)
                else:
                    normal_vol_days.append(daily_profit)
        
        # Calculate regime-specific performance
        if high_vol_days:
            features["avg_profit_high_vol"] = np.mean(high_vol_days)
            features["win_rate_high_vol"] = len([p for p in high_vol_days if p > 0]) / len(high_vol_days) * 100
        else:
            features["avg_profit_high_vol"] = 0.0
            features["win_rate_high_vol"] = 0.0
        
        if normal_vol_days:
            features["avg_profit_normal_vol"] = np.mean(normal_vol_days)
            features["win_rate_normal_vol"] = len([p for p in normal_vol_days if p > 0]) / len(normal_vol_days) * 100
        else:
            features["avg_profit_normal_vol"] = 0.0
            features["win_rate_normal_vol"] = 0.0
        
        if low_vol_days:
            features["avg_profit_low_vol"] = np.mean(low_vol_days)
            features["win_rate_low_vol"] = len([p for p in low_vol_days if p > 0]) / len(low_vol_days) * 100
        else:
            features["avg_profit_low_vol"] = 0.0
            features["win_rate_low_vol"] = 0.0
        
        # Volatility adaptability score
        vol_performances = []
        if high_vol_days:
            vol_performances.append(np.mean(high_vol_days))
        if normal_vol_days:
            vol_performances.append(np.mean(normal_vol_days))
        if low_vol_days:
            vol_performances.append(np.mean(low_vol_days))
        
        if len(vol_performances) > 1:
            features["volatility_adaptability"] = 1 - (np.std(vol_performances) / (abs(np.mean(vol_performances)) + 1))
        else:
            features["volatility_adaptability"] = 0.0
        
        # Current regime indicator
        features["is_high_vol_regime"] = 1 if "high" in volatility_regime.lower() else 0
        features["is_low_vol_regime"] = 1 if "low" in volatility_regime.lower() else 0
        
        return features

    def _calculate_skewness(self, daily_data: Dict) -> float:
        """Calculate skewness from profit distribution percentiles."""
        try:
            p10 = daily_data.get("profit_perc_10", 0)
            p50 = daily_data.get("median_profit", 0)
            p90 = daily_data.get("profit_perc_90", 0)
            
            # Simplified skewness calculation using percentiles
            # Positive skew = right tail is longer
            upper_tail = p90 - p50
            lower_tail = p50 - p10
            
            if upper_tail + lower_tail > 0:
                return (upper_tail - lower_tail) / (upper_tail + lower_tail)
            return 0.0
        except Exception:
            return 0.0

    def _calculate_kurtosis(self, daily_data: Dict) -> float:
        """Calculate kurtosis from profit distribution percentiles."""
        try:
            p10 = daily_data.get("profit_perc_10", 0)
            p25 = daily_data.get("profit_perc_25", 0)
            p75 = daily_data.get("profit_perc_75", 0)
            p90 = daily_data.get("profit_perc_90", 0)
            
            # Simplified kurtosis using interquartile range
            iqr = p75 - p25
            full_range = p90 - p10
            
            if iqr > 0:
                return full_range / iqr - 2.91  # Normalize to normal distribution
            return 0.0
        except Exception:
            return 0.0

    def _calculate_tail_ratio(self, daily_data: Dict) -> float:
        """Calculate tail ratio from profit distribution."""
        try:
            p90 = abs(daily_data.get("profit_perc_90", 0))
            p10 = abs(daily_data.get("profit_perc_10", 0))
            
            if p10 > 0:
                return p90 / p10
            return 0.0
        except Exception:
            return 0.0

    # ========================================================================
    # BATCH PROCESSING AND SAVING
    # ========================================================================

    def _process_batches(
        self,
        work_items: List[Tuple[str, str, date]],
        start_date: date,
        end_date: date,
        validate_bias: bool,
        include_enhanced_metrics: bool
    ) -> int:
        """Process batches with enhanced features."""
        total_records = 0
        batch_size = self.config["batch_size"]
        
        for i in range(0, len(work_items), batch_size):
            batch = work_items[i : i + batch_size]
            
            # Extract unique accounts and dates
            account_ids = list(set(item[0] for item in batch))
            dates = list(set(item[2] for item in batch))
            
            # Bulk fetch all data
            bulk_data = self._bulk_fetch_all_data(
                account_ids, dates, start_date, end_date, include_enhanced_metrics
            )
            
            # Process each work item
            features_batch = []
            for account_id, login, feature_date in batch:
                try:
                    features = self._calculate_features_from_bulk_data(
                        account_id, login, feature_date, bulk_data, include_enhanced_metrics
                    )
                    if features and (not validate_bias or self._validate_features(features, feature_date, bulk_data)):
                        features_batch.append(features)
                except Exception as e:
                    logger.error(
                        f"Error processing {account_id} on {feature_date}: {str(e)}"
                    )
                    self.performance_metrics["errors_encountered"] += 1
            
            # Bulk save features
            if features_batch:
                with self.query_monitor.track_query(
                    "bulk_save", f"Saving {len(features_batch)} features"
                ):
                    saved = self._bulk_save_features(features_batch)
                    total_records += saved
            
            # Progress logging
            progress = min(100, ((i + len(batch)) / len(work_items)) * 100)
            if (i + len(batch)) % 100 == 0 or progress >= 100:
                logger.info(
                    f"Progress: {progress:.1f}% ({i + len(batch)}/{len(work_items)})"
                )
                logger.debug(
                    f"Queries executed: {self.query_stats['bulk_queries']} bulk, "
                    f"{self.query_stats['total_queries']} equivalent individual"
                )
        
        self.performance_metrics["total_records_processed"] = total_records
        return total_records

    def _bulk_fetch_all_data(
        self,
        account_ids: List[str],
        dates: List[date],
        start_date: date,
        end_date: date,
        include_enhanced_metrics: bool
    ) -> Dict[str, Any]:
        """Fetch all data with performance monitoring."""
        bulk_data = {}

        # Static features
        with self.query_monitor.track_query(
            "bulk_fetch_static", "Fetching static features"
        ):
            bulk_data["static_features"] = self._bulk_fetch_static_features(
                account_ids, dates
            )

        # Dynamic features
        with self.query_monitor.track_query(
            "bulk_fetch_dynamic", "Fetching dynamic features"
        ):
            bulk_data["dynamic_features"] = self._bulk_fetch_dynamic_features(
                account_ids, dates
            )

        # Open positions
        with self.query_monitor.track_query(
            "bulk_fetch_positions", "Fetching open positions"
        ):
            bulk_data["open_positions"] = self._bulk_fetch_open_positions(
                account_ids, dates
            )

        # Performance data
        with self.query_monitor.track_query(
            "bulk_fetch_performance", "Fetching performance data"
        ):
            bulk_data["performance_data"] = self._bulk_fetch_performance_data(
                account_ids, start_date, end_date
            )

        # Trades data
        with self.query_monitor.track_query(
            "bulk_fetch_trades", "Fetching trades data"
        ):
            bulk_data["trades_data"] = self._bulk_fetch_trades_data(
                account_ids, start_date, end_date
            )

        # Market data
        with self.query_monitor.track_query(
            "bulk_fetch_market", "Fetching market data"
        ):
            bulk_data["market_data"] = self._bulk_fetch_market_data(dates)
            
        # Enhanced metrics (if enabled)
        if include_enhanced_metrics:
            with self.query_monitor.track_query(
                "bulk_fetch_enhanced_metrics", "Fetching enhanced risk metrics"
            ):
                # Get more historical data for risk calculations
                historical_start = start_date - timedelta(days=90)
                historical_dates = []
                current = historical_start
                while current <= end_date:
                    historical_dates.append(current)
                    current += timedelta(days=1)
                
                bulk_data["enhanced_metrics"] = self._bulk_fetch_enhanced_metrics(
                    account_ids, historical_dates
                )
            
            # All-time metrics for baseline comparison
            with self.query_monitor.track_query(
                "bulk_fetch_alltime", "Fetching all-time metrics"
            ):
                bulk_data["alltime_metrics"] = self._bulk_fetch_alltime_metrics(account_ids)

        return bulk_data

    def _validate_features(self, features: Dict[str, Any], feature_date: date, bulk_data: Dict[str, Any]) -> bool:
        """Validate features for lookahead bias and data quality."""
        # Basic validation
        if not self.bias_validator.validate_data_availability(
            feature_date, feature_date, "base_features"
        ):
            self.performance_metrics["validation_violations"] += 1
            return False
        
        # Validate target alignment
        target_date = feature_date + timedelta(days=1)
        self.bias_validator.validate_feature_target_alignment(
            feature_date, target_date, "target_alignment"
        )
        
        # Validate rolling windows
        account_id = features["account_id"]
        if account_id in bulk_data.get("performance_data", {}):
            perf_df = bulk_data["performance_data"][account_id]
            filtered_df = perf_df[perf_df["date"] <= feature_date]
            
            for window in self.rolling_windows:
                if len(filtered_df) >= window:
                    window_data = filtered_df.head(window)
                    window_start = window_data["date"].min()
                    window_end = window_data["date"].max()
                    
                    if not self.bias_validator.validate_rolling_window(
                        feature_date, window_start, window_end, f"rolling_{window}d"
                    ):
                        self.performance_metrics["validation_violations"] += 1
        
        # Additional validation for risk metrics
        risk_metrics = [
            "daily_sharpe", "daily_sortino", "daily_gain_to_pain",
            "profit_distribution_skew", "volatility_adaptability"
        ]
        
        for metric in risk_metrics:
            if metric in features:
                value = features[metric]
                # Check for unrealistic values
                if isinstance(value, (int, float)):
                    if abs(value) > 1000:  # Sanity check
                        logger.warning(
                            f"Unrealistic value for {metric}: {value} on {feature_date}"
                        )
                        features[metric] = 0.0  # Reset to default
        
        return True

    def _bulk_save_features(self, features_batch: List[Dict[str, Any]]) -> int:
        """Save a batch of features efficiently using bulk insert."""
        if not features_batch:
            return 0

        # Prepare data for bulk insert
        columns = list(features_batch[0].keys())

        # Build bulk insert query
        placeholders = ", ".join(["%s"] * len(columns))
        columns_str = ", ".join(columns)

        # Create values list
        values_list = []
        for features in features_batch:
            values_list.append([features.get(col) for col in columns])

        # Build the bulk insert query with ON CONFLICT
        query = f"""
        INSERT INTO {self.feature_table} ({columns_str})
        VALUES {", ".join([f"({placeholders})" for _ in range(len(features_batch))])}
        ON CONFLICT (account_id, feature_date) 
        DO UPDATE SET
            {", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col not in ["account_id", "feature_date"]])}
        """

        # Flatten values for query execution
        flat_values = [val for row in values_list for val in row]

        try:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, flat_values)
                    return cursor.rowcount
        except Exception as e:
            logger.error(f"Error bulk saving features: {str(e)}")
            # Fall back to individual saves
            saved_count = 0
            for features in features_batch:
                try:
                    self._save_single_feature(features)
                    saved_count += 1
                except Exception as e2:
                    logger.error(
                        f"Error saving feature for {features.get('account_id')}: {str(e2)}"
                    )
            return saved_count

    def _save_single_feature(self, features: Dict[str, Any]):
        """Save a single feature record (fallback method)."""
        columns = list(features.keys())
        values = [features[col] for col in columns]

        placeholders = ", ".join(["%s"] * len(columns))
        columns_str = ", ".join(columns)

        query = f"""
        INSERT INTO {self.feature_table} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (account_id, feature_date) 
        DO UPDATE SET
            {", ".join([f"{col} = EXCLUDED.{col}" for col in columns if col not in ["account_id", "feature_date"]])}
        """

        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, values)

    # ========================================================================
    # MONITORING AND REPORTING
    # ========================================================================

    def _run_comprehensive_monitoring(
        self, start_date: date, end_date: date
    ) -> Dict[str, Any]:
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

            with self.query_monitor.track_query(
                "quality_monitoring", "Feature quality sampling"
            ):
                sample_df = self.db_manager.model_db.execute_query_df(
                    sample_query, (start_date, end_date)
                )

            if sample_df.empty:
                return {"status": "no_data"}

            # Run various quality checks
            quality_results = {
                "sample_size": len(sample_df),
                "date_range": {"start": str(start_date), "end": str(end_date)},
            }

            # Coverage analysis
            required_features = [
                "current_balance",
                "rolling_pnl_avg_5d",
                "trades_count_5d",
                "market_sentiment_score",
                "day_of_week",
            ]
            quality_results["coverage"] = self.quality_monitor.monitor_feature_coverage(
                sample_df, required_features
            )

            # Distribution analysis
            quality_results["distributions"] = self._analyze_feature_distributions(
                sample_df
            )

            # Get quality summary
            quality_results["summary"] = self.quality_monitor.get_quality_summary()

            return quality_results

        except Exception as e:
            logger.error(f"Quality monitoring failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    def _analyze_feature_distributions(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze feature distributions for quality assessment."""
        distributions = {}

        numeric_columns = df.select_dtypes(include=[np.number]).columns

        for col in numeric_columns[:20]:  # Analyze top 20 numeric features
            if col in ["account_id", "feature_date"]:
                continue

            col_data = df[col].dropna()
            if len(col_data) > 0:
                distributions[col] = {
                    "mean": float(col_data.mean()),
                    "std": float(col_data.std()),
                    "min": float(col_data.min()),
                    "max": float(col_data.max()),
                    "nulls": int(df[col].isna().sum()),
                    "null_pct": float(df[col].isna().sum() / len(df) * 100),
                }

        return distributions

    def _create_comprehensive_summary(
        self,
        start_time: datetime,
        total_records: int,
        validate_bias: bool,
        enable_monitoring: bool,
        quality_results: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Create comprehensive summary of the feature engineering run."""
        execution_time = (datetime.now() - start_time).total_seconds()
        self.performance_metrics["total_processing_time"] = execution_time

        # Get validation summary
        violations_summary = (
            self.bias_validator.get_violations_summary() if validate_bias else {}
        )

        # Get query performance summary
        query_summary = self.query_monitor.get_summary()

        result = {
            "total_records": total_records,
            "execution_time_seconds": execution_time,
            "feature_version": FEATURE_VERSION,
            "configuration": {
                "validation_enabled": validate_bias,
                "monitoring_enabled": enable_monitoring,
                **self.config,
            },
            "performance_metrics": {
                **self.performance_metrics,
                "records_per_second": total_records / execution_time
                if execution_time > 0
                else 0,
            },
            "query_optimization": {
                "bulk_queries": self.query_stats["bulk_queries"],
                "equivalent_individual_queries": self.query_stats["total_queries"],
                "query_reduction_factor": (
                    self.query_stats["total_queries"] / self.query_stats["bulk_queries"]
                    if self.query_stats["bulk_queries"] > 0
                    else 0
                ),
                **query_summary,
            },
        }

        if validate_bias:
            result["lookahead_bias_check"] = violations_summary

        if enable_monitoring and quality_results:
            result["quality_monitoring"] = quality_results

        return result

    def _log_completion_status(self, result: Dict[str, Any], include_enhanced_metrics: bool):
        """Log detailed completion status."""
        logger.info("=" * 80)
        logger.info("FEATURE ENGINEERING COMPLETED")
        logger.info("=" * 80)

        # Basic metrics
        logger.info(f"Total records processed: {result['total_records']}")
        logger.info(f"Execution time: {result['execution_time_seconds']:.2f} seconds")
        logger.info(
            f"Processing rate: {result['performance_metrics']['records_per_second']:.1f} records/second"
        )

        # Query optimization
        qo = result["query_optimization"]
        logger.info("\nQuery Optimization:")
        logger.info(f"  - Bulk queries executed: {qo['bulk_queries']}")
        logger.info(
            f"  - Equivalent individual queries: {qo['equivalent_individual_queries']}"
        )
        logger.info(f"  - Reduction factor: {qo['query_reduction_factor']:.1f}x")
        logger.info(f"  - Average query time: {qo['avg_query_time']:.3f}s")

        # Validation results
        if "lookahead_bias_check" in result:
            bias_check = result["lookahead_bias_check"]
            if bias_check.get("has_violations"):
                logger.warning(f"\nLookahead Bias Violations: {bias_check['count']}")
                logger.warning(f"Violation rate: {bias_check['violation_rate']:.2%}")
            else:
                logger.info("\n✓ No lookahead bias violations detected")

        # Quality monitoring
        if "quality_monitoring" in result and result["quality_monitoring"].get(
            "summary"
        ):
            qm = result["quality_monitoring"]["summary"]
            logger.info("\nQuality Monitoring:")
            logger.info(f"  - Quality score: {qm['quality_score']:.2f}")
            logger.info(f"  - Total issues: {qm['total_issues']}")
            if qm["issue_breakdown"]:
                logger.info(f"  - Issue types: {qm['issue_breakdown']}")
                
        # Enhanced metrics summary (if enabled)
        if include_enhanced_metrics:
            logger.info("\n" + "="*80)
            logger.info("ENHANCED RISK METRICS")
            logger.info("="*80)
            logger.info(f"Feature Version: {FEATURE_VERSION}")
            logger.info("\nEnhanced Features Included:")
            logger.info("  - Risk-adjusted performance metrics (Sharpe, Sortino, Gain-to-Pain)")
            logger.info("  - Profit distribution analysis (skewness, kurtosis, tail ratios)")
            logger.info("  - Behavioral consistency tracking")
            logger.info("  - Market regime adaptability scoring")
            logger.info("  - Time and volume weighted returns")
            logger.info("  - Extended rolling windows (up to 30 days)")
            
            if result.get("quality_monitoring", {}).get("distributions"):
                logger.info("\nKey Risk Metrics Distribution:")
                distributions = result["quality_monitoring"]["distributions"]
                
                for metric in ["daily_sharpe", "daily_sortino", "volatility_adaptability"]:
                    if metric in distributions:
                        dist = distributions[metric]
                        logger.info(
                            f"  - {metric}: mean={dist['mean']:.3f}, "
                            f"std={dist['std']:.3f}, nulls={dist['null_pct']:.1f}%"
                        )

        logger.info("=" * 80)


# ============================================================================
# BACKWARD COMPATIBILITY CLASSES
# ============================================================================

class OptimizedFeatureEngineer(UnifiedFeatureEngineer):
    """Backward compatibility wrapper for OptimizedFeatureEngineer."""
    pass


class IntegratedProductionFeatureEngineer(UnifiedFeatureEngineer):
    """Backward compatibility wrapper for IntegratedProductionFeatureEngineer."""
    
    def engineer_features_with_validation(self, **kwargs):
        """Wrapper method for backward compatibility."""
        return self.engineer_features(**kwargs)


class EnhancedFeatureEngineerV2(UnifiedFeatureEngineer):
    """Backward compatibility wrapper for EnhancedFeatureEngineerV2."""
    
    def engineer_features_enhanced(self, **kwargs):
        """Wrapper method for backward compatibility."""
        # Ensure enhanced metrics are included
        kwargs["include_enhanced_metrics"] = True
        return self.engineer_features(**kwargs)


# ============================================================================
# MAIN ENTRY POINTS
# ============================================================================

def engineer_features_unified(**kwargs):
    """
    Main entry point for unified feature engineering.
    """
    engineer = UnifiedFeatureEngineer()
    return engineer.engineer_features(**kwargs)


def engineer_features_optimized(**kwargs):
    """
    Backward compatibility entry point.
    """
    return engineer_features_unified(**kwargs)


def engineer_features_enhanced_v2(**kwargs):
    """
    Entry point with enhanced metrics enabled by default.
    """
    kwargs["include_enhanced_metrics"] = True
    return engineer_features_unified(**kwargs)


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(
        description="Unified feature engineering with comprehensive risk metrics and optimization"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for feature engineering (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for feature engineering (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild of existing features",
    )
    parser.add_argument(
        "--no-validation", action="store_true", help="Disable lookahead bias validation"
    )
    parser.add_argument(
        "--no-monitoring", action="store_true", help="Disable quality monitoring"
    )
    parser.add_argument(
        "--no-enhanced-metrics", action="store_true", help="Disable enhanced risk metrics"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file="feature_engineering_unified")

    # Run feature engineering
    try:
        result = engineer_features_unified(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild,
            validate_bias=not args.no_validation,
            enable_monitoring=not args.no_monitoring,
            include_enhanced_metrics=not args.no_enhanced_metrics,
        )

        logger.info(
            f"Feature engineering complete: {result['total_records']} records processed"
        )

    except Exception as e:
        logger.error(f"Feature engineering failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()