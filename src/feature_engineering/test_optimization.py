"""
Test script to validate performance characteristics of the unified feature engineering module.
Tests query optimization, batch processing efficiency, and feature correctness.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
import pandas as pd
import time
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging
from feature_engineering.feature_engineering import UnifiedFeatureEngineer

logger = logging.getLogger(__name__)


class FeatureEngineeringPerformanceValidator:
    """Validates performance characteristics of the unified feature engineering implementation."""

    def __init__(self):
        self.db_manager = get_db_manager()
        self.engineer = UnifiedFeatureEngineer()

    def validate_performance(
        self, test_accounts: List[str] = None, test_days: int = 7
    ) -> Dict[str, Any]:
        """
        Run feature engineering and validate performance characteristics.

        Args:
            test_accounts: List of account IDs to test (None = use sample)
            test_days: Number of days to test

        Returns:
            Validation results including performance metrics
        """
        # Setup test parameters
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date - timedelta(days=test_days - 1)

        # Get test accounts if not provided
        if not test_accounts:
            test_accounts = self._get_sample_accounts(start_date, end_date, limit=5)

        logger.info(
            f"Testing feature engineering performance with {len(test_accounts)} accounts from {start_date} to {end_date}"
        )

        # Clear any existing test data
        self._cleanup_test_data(test_accounts, start_date, end_date)

        results = {
            "test_params": {
                "accounts": test_accounts,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "days": test_days,
                "total_expected_records": len(test_accounts) * test_days,
            },
            "performance": {},
            "quality": {},
            "optimization": {},
        }

        # Run feature engineering with performance tracking
        logger.info("Running unified feature engineering...")
        run_start = time.time()
        
        # Run the feature engineering
        eng_results = self.engineer.engineer_features(
            start_date=start_date,
            end_date=end_date,
            force_rebuild=True,
            validate_bias=True,
            enable_monitoring=True,
            include_enhanced_metrics=True
        )
        
        run_time = time.time() - run_start

        # Extract performance metrics
        results["performance"] = {
            "total_records": eng_results.get("total_records", 0),
            "execution_time": run_time,
            "records_per_second": eng_results["performance_metrics"].get("records_per_second", 0),
            "memory_peak_mb": eng_results["performance_metrics"].get("memory_peak_mb", 0),
            "errors_encountered": eng_results["performance_metrics"].get("errors_encountered", 0),
        }

        # Extract optimization metrics
        results["optimization"] = eng_results.get("query_optimization", {})

        # Validate the created features
        features_df = self._get_features_snapshot(test_accounts, start_date, end_date)
        validation_results = self._validate_features(features_df, test_accounts, test_days)
        results["quality"] = validation_results

        # Check for lookahead bias violations
        if "lookahead_bias_check" in eng_results:
            results["bias_validation"] = eng_results["lookahead_bias_check"]

        # Log summary
        self._log_validation_summary(results)

        return results

    def benchmark_query_optimization(self, sample_size: int = 10) -> Dict[str, Any]:
        """
        Benchmark the query optimization by comparing theoretical vs actual queries.
        """
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date - timedelta(days=6)  # 7 days
        
        accounts = self._get_sample_accounts(start_date, end_date, limit=sample_size)
        
        # Calculate theoretical queries without optimization
        days = 7
        theoretical_queries = self._calculate_theoretical_queries(len(accounts), days)
        
        # Clear any existing data
        self._cleanup_test_data(accounts, start_date, end_date)
        
        # Run actual feature engineering
        eng_results = self.engineer.engineer_features(
            start_date=start_date,
            end_date=end_date,
            force_rebuild=True,
            validate_bias=False,  # Skip validation for performance test
            enable_monitoring=False
        )
        
        actual_queries = eng_results["query_optimization"]["bulk_queries"]
        query_reduction = eng_results["query_optimization"]["query_reduction_factor"]
        
        return {
            "sample_size": sample_size,
            "days": days,
            "theoretical_queries": theoretical_queries,
            "actual_bulk_queries": actual_queries,
            "query_reduction_factor": query_reduction,
            "queries_saved": theoretical_queries - actual_queries,
            "optimization_efficiency": (theoretical_queries - actual_queries) / theoretical_queries * 100
        }

    def _get_sample_accounts(
        self, start_date: date, end_date: date, limit: int = 5
    ) -> List[str]:
        """Get a sample of active accounts for testing."""
        query = """
        SELECT DISTINCT account_id
        FROM stg_accounts_daily_snapshots
        WHERE snapshot_date >= %s AND snapshot_date <= %s
        ORDER BY account_id
        LIMIT %s
        """
        results = self.db_manager.model_db.execute_query(
            query, (start_date, end_date, limit)
        )
        return [r["account_id"] for r in results]

    def _cleanup_test_data(
        self, account_ids: List[str], start_date: date, end_date: date
    ):
        """Remove existing features for test accounts."""
        query = """
        DELETE FROM feature_store_account_daily
        WHERE account_id = ANY(%s) 
          AND feature_date >= %s 
          AND feature_date <= %s
        """
        self.db_manager.model_db.execute_command(
            query, (account_ids, start_date, end_date)
        )

    def _calculate_theoretical_queries(self, num_accounts: int, days: int) -> int:
        """
        Calculate theoretical number of queries without bulk optimization.
        
        For each account-date combination:
        - 1 query to check if features exist
        - 6 feature category queries (static, dynamic, performance, behavioral, market, open positions)
        - 1 save query
        Plus for each account:
        - Multiple queries for rolling windows (approx 5 per window, 7 windows)
        - Enhanced metrics queries
        """
        queries_per_account_date = 8
        rolling_queries_per_account = 35  # 7 windows * 5 queries
        enhanced_metrics_queries = 10  # Additional queries for risk metrics
        
        total_queries = (
            num_accounts * days * queries_per_account_date
            + num_accounts * rolling_queries_per_account
            + num_accounts * enhanced_metrics_queries
        )
        
        return total_queries

    def _get_features_snapshot(
        self, account_ids: List[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Get features for validation."""
        query = """
        SELECT *
        FROM feature_store_account_daily
        WHERE account_id = ANY(%s)
          AND feature_date >= %s
          AND feature_date <= %s
        ORDER BY account_id, feature_date
        """

        return self.db_manager.model_db.execute_query_df(
            query, (account_ids, start_date, end_date)
        )

    def _validate_features(
        self, features_df: pd.DataFrame, expected_accounts: List[str], expected_days: int
    ) -> Dict[str, Any]:
        """Validate feature completeness and quality."""
        validation = {
            "records_created": len(features_df),
            "expected_records": len(expected_accounts) * expected_days,
            "completeness": len(features_df) / (len(expected_accounts) * expected_days) * 100,
            "missing_records": [],
            "feature_coverage": {},
            "null_rates": {},
        }
        
        if features_df.empty:
            validation["error"] = "No features were created"
            return validation
        
        # Check for missing records
        created_keys = set(
            zip(features_df["account_id"], features_df["feature_date"])
        )
        
        for account_id in expected_accounts:
            for day_offset in range(expected_days):
                expected_date = features_df["feature_date"].min() + timedelta(days=day_offset)
                if (account_id, expected_date) not in created_keys:
                    validation["missing_records"].append({
                        "account_id": account_id,
                        "feature_date": str(expected_date)
                    })
        
        # Check feature coverage
        core_features = [
            "current_balance", "rolling_pnl_avg_5d", "trades_count_5d",
            "market_sentiment_score", "daily_sharpe", "volatility_adaptability"
        ]
        
        for feature in core_features:
            if feature in features_df.columns:
                non_null_count = features_df[feature].notna().sum()
                validation["feature_coverage"][feature] = {
                    "present": True,
                    "coverage_pct": non_null_count / len(features_df) * 100
                }
            else:
                validation["feature_coverage"][feature] = {
                    "present": False,
                    "coverage_pct": 0
                }
        
        # Calculate null rates for numeric features
        numeric_cols = features_df.select_dtypes(include=["float64", "int64"]).columns
        for col in numeric_cols[:10]:  # Top 10 features
            null_rate = features_df[col].isna().sum() / len(features_df) * 100
            validation["null_rates"][col] = round(null_rate, 2)
        
        return validation

    def _log_validation_summary(self, results: Dict[str, Any]):
        """Log a summary of validation results."""
        logger.info("=" * 60)
        logger.info("FEATURE ENGINEERING PERFORMANCE VALIDATION")
        logger.info("=" * 60)

        # Test parameters
        logger.info(f"Test accounts: {len(results['test_params']['accounts'])}")
        logger.info(
            f"Date range: {results['test_params']['start_date']} to {results['test_params']['end_date']}"
        )
        logger.info(f"Expected records: {results['test_params']['total_expected_records']}")

        # Performance metrics
        logger.info("\nPERFORMANCE METRICS:")
        perf = results["performance"]
        logger.info(f"  - Total records created: {perf['total_records']}")
        logger.info(f"  - Execution time: {perf['execution_time']:.2f} seconds")
        logger.info(f"  - Processing rate: {perf['records_per_second']:.1f} records/second")
        logger.info(f"  - Peak memory usage: {perf['memory_peak_mb']:.1f} MB")
        logger.info(f"  - Errors encountered: {perf['errors_encountered']}")

        # Query optimization
        logger.info("\nQUERY OPTIMIZATION:")
        opt = results["optimization"]
        if opt:
            logger.info(f"  - Bulk queries executed: {opt.get('bulk_queries', 'N/A')}")
            logger.info(f"  - Query reduction factor: {opt.get('query_reduction_factor', 'N/A'):.1f}x")
            logger.info(f"  - Average query time: {opt.get('avg_query_time', 'N/A'):.3f}s")

        # Quality validation
        logger.info("\nQUALITY VALIDATION:")
        quality = results["quality"]
        logger.info(f"  - Records created: {quality['records_created']}/{quality['expected_records']}")
        logger.info(f"  - Completeness: {quality['completeness']:.1f}%")
        
        if quality["missing_records"]:
            logger.warning(f"  - Missing records: {len(quality['missing_records'])}")
        
        logger.info("\n  Feature coverage:")
        for feature, coverage in quality["feature_coverage"].items():
            if coverage["present"]:
                logger.info(f"    - {feature}: {coverage['coverage_pct']:.1f}%")
            else:
                logger.warning(f"    - {feature}: MISSING")

        # Bias validation
        if "bias_validation" in results:
            bias = results["bias_validation"]
            if bias.get("has_violations"):
                logger.warning(f"\n  ⚠️  Lookahead bias violations: {bias['count']}")
            else:
                logger.info("\n  ✓ No lookahead bias violations detected")

        logger.info("=" * 60)


def main():
    """Main function for testing feature engineering performance."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test feature engineering performance and optimization"
    )
    parser.add_argument("--accounts", nargs="+", help="Specific account IDs to test")
    parser.add_argument("--days", type=int, default=7, help="Number of days to test")
    parser.add_argument(
        "--benchmark", action="store_true", help="Run query optimization benchmark"
    )
    parser.add_argument(
        "--sample-size", type=int, default=10, help="Sample size for benchmark"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file="test_optimization")

    # Run validation
    validator = FeatureEngineeringPerformanceValidator()
    
    try:
        if args.benchmark:
            # Run query optimization benchmark
            logger.info("Running query optimization benchmark...")
            benchmark_results = validator.benchmark_query_optimization(
                sample_size=args.sample_size
            )
            
            logger.info("\nBENCHMARK RESULTS:")
            logger.info(f"Sample size: {benchmark_results['sample_size']} accounts")
            logger.info(f"Theoretical queries: {benchmark_results['theoretical_queries']}")
            logger.info(f"Actual bulk queries: {benchmark_results['actual_bulk_queries']}")
            logger.info(f"Query reduction: {benchmark_results['query_reduction_factor']:.1f}x")
            logger.info(f"Optimization efficiency: {benchmark_results['optimization_efficiency']:.1f}%")
            
        else:
            # Run standard performance validation
            results = validator.validate_performance(
                test_accounts=args.accounts, test_days=args.days
            )

            # Check if validation passed
            quality = results["quality"]
            if quality["completeness"] >= 95 and results["performance"]["errors_encountered"] == 0:
                logger.info("\n✓ Performance validation PASSED!")
                return 0
            else:
                logger.error("\n✗ Performance validation FAILED!")
                return 1

    except Exception as e:
        logger.error(f"Validation failed with error: {str(e)}")
        raise


if __name__ == "__main__":
    exit(main())