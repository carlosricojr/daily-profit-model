"""
Test script to validate that the optimized feature engineering produces
the same results as the original implementation while being faster.
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
from engineer_features import FeatureEngineer
from engineer_features_optimized import OptimizedFeatureEngineer

logger = logging.getLogger(__name__)


class OptimizationValidator:
    """Validates that optimized implementation produces same results."""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        self.original_engineer = FeatureEngineer()
        self.optimized_engineer = OptimizedFeatureEngineer()
    
    def validate_optimization(self, 
                            test_accounts: List[str] = None,
                            test_days: int = 7) -> Dict[str, Any]:
        """
        Run both implementations and compare results.
        
        Args:
            test_accounts: List of account IDs to test (None = use sample)
            test_days: Number of days to test
        
        Returns:
            Validation results including performance metrics and differences
        """
        # Setup test parameters
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date - timedelta(days=test_days - 1)
        
        # Get test accounts if not provided
        if not test_accounts:
            test_accounts = self._get_sample_accounts(start_date, end_date, limit=5)
        
        logger.info(f"Testing optimization with {len(test_accounts)} accounts from {start_date} to {end_date}")
        
        # Clear any existing test data
        self._cleanup_test_data(test_accounts, start_date, end_date)
        
        results = {
            'test_params': {
                'accounts': test_accounts,
                'start_date': str(start_date),
                'end_date': str(end_date),
                'days': test_days
            },
            'original': {},
            'optimized': {},
            'comparison': {}
        }
        
        # Run original implementation
        logger.info("Running original implementation...")
        original_start = time.time()
        original_records = self._run_original_implementation(test_accounts, start_date, end_date)
        original_time = time.time() - original_start
        
        results['original'] = {
            'records_created': original_records,
            'execution_time': original_time,
            'queries_executed': self._estimate_original_queries(test_accounts, test_days)
        }
        
        # Get original results
        original_features = self._get_features_snapshot(test_accounts, start_date, end_date)
        
        # Clear data for optimized run
        self._cleanup_test_data(test_accounts, start_date, end_date)
        
        # Run optimized implementation
        logger.info("Running optimized implementation...")
        optimized_start = time.time()
        optimized_records = self._run_optimized_implementation(test_accounts, start_date, end_date)
        optimized_time = time.time() - optimized_start
        
        results['optimized'] = {
            'records_created': optimized_records,
            'execution_time': optimized_time,
            'query_stats': self.optimized_engineer.query_stats.copy()
        }
        
        # Get optimized results
        optimized_features = self._get_features_snapshot(test_accounts, start_date, end_date)
        
        # Compare results
        comparison = self._compare_features(original_features, optimized_features)
        results['comparison'] = comparison
        
        # Calculate performance improvement
        speedup = original_time / optimized_time if optimized_time > 0 else 0
        query_reduction = (
            (results['original']['queries_executed'] - results['optimized']['query_stats']['bulk_queries']) 
            / results['original']['queries_executed'] * 100
            if results['original']['queries_executed'] > 0 else 0
        )
        
        results['performance_improvement'] = {
            'speedup_factor': round(speedup, 2),
            'time_saved_seconds': round(original_time - optimized_time, 2),
            'query_reduction_pct': round(query_reduction, 2)
        }
        
        # Log summary
        self._log_validation_summary(results)
        
        return results
    
    def _get_sample_accounts(self, start_date: date, end_date: date, limit: int = 5) -> List[str]:
        """Get a sample of active accounts for testing."""
        query = """
        SELECT DISTINCT account_id
        FROM stg_accounts_daily_snapshots
        WHERE date >= %s AND date <= %s
        ORDER BY account_id
        LIMIT %s
        """
        results = self.db_manager.model_db.execute_query(query, (start_date, end_date, limit))
        return [r['account_id'] for r in results]
    
    def _cleanup_test_data(self, account_ids: List[str], start_date: date, end_date: date):
        """Remove existing features for test accounts."""
        query = """
        DELETE FROM feature_store_account_daily
        WHERE account_id = ANY(%s) 
          AND feature_date >= %s 
          AND feature_date <= %s
        """
        self.db_manager.model_db.execute_command(query, (account_ids, start_date, end_date))
    
    def _run_original_implementation(self, account_ids: List[str], start_date: date, end_date: date) -> int:
        """Run original feature engineering for specific accounts."""
        total_records = 0
        
        for account_id in account_ids:
            # Get login for account
            login_query = """
            SELECT DISTINCT login
            FROM stg_accounts_daily_snapshots
            WHERE account_id = %s
            LIMIT 1
            """
            result = self.db_manager.model_db.execute_query(login_query, (account_id,))
            if result:
                login = result[0]['login']
                records = self.original_engineer._engineer_features_for_account(
                    account_id, login, start_date, end_date, force_rebuild=True
                )
                total_records += records
        
        return total_records
    
    def _run_optimized_implementation(self, account_ids: List[str], start_date: date, end_date: date) -> int:
        """Run optimized feature engineering."""
        # Create a temporary implementation that only processes specific accounts
        work_items = []
        
        for account_id in account_ids:
            # Get login for account
            login_query = """
            SELECT DISTINCT login
            FROM stg_accounts_daily_snapshots
            WHERE account_id = %s
            LIMIT 1
            """
            result = self.db_manager.model_db.execute_query(login_query, (account_id,))
            if result:
                login = result[0]['login']
                # Add work items for each date
                current_date = start_date
                while current_date <= end_date:
                    work_items.append((account_id, login, current_date))
                    current_date += timedelta(days=1)
        
        # Process using optimized batch method
        return self.optimized_engineer._process_batch_optimized(work_items, start_date, end_date)
    
    def _estimate_original_queries(self, account_ids: List[str], days: int) -> int:
        """Estimate number of queries in original implementation."""
        # For each account-date combination:
        # - 1 query to check if features exist
        # - 6 feature category queries (static, dynamic, performance, behavioral, market, open positions)
        # - 1 save query
        # Plus for each account:
        # - Multiple queries for rolling windows (approx 5 per window)
        
        queries_per_account_date = 8
        rolling_queries_per_account = 25  # Approximate
        
        total_queries = (
            len(account_ids) * days * queries_per_account_date +
            len(account_ids) * rolling_queries_per_account
        )
        
        return total_queries
    
    def _get_features_snapshot(self, account_ids: List[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Get features for comparison."""
        query = """
        SELECT *
        FROM feature_store_account_daily
        WHERE account_id = ANY(%s)
          AND feature_date >= %s
          AND feature_date <= %s
        ORDER BY account_id, feature_date
        """
        
        return self.db_manager.model_db.execute_query_df(query, (account_ids, start_date, end_date))
    
    def _compare_features(self, original_df: pd.DataFrame, optimized_df: pd.DataFrame) -> Dict[str, Any]:
        """Compare feature DataFrames for differences."""
        comparison = {
            'records_match': len(original_df) == len(optimized_df),
            'original_records': len(original_df),
            'optimized_records': len(optimized_df),
            'differences': []
        }
        
        if original_df.empty or optimized_df.empty:
            comparison['error'] = 'One or both DataFrames are empty'
            return comparison
        
        # Sort both DataFrames for comparison
        original_df = original_df.sort_values(['account_id', 'feature_date']).reset_index(drop=True)
        optimized_df = optimized_df.sort_values(['account_id', 'feature_date']).reset_index(drop=True)
        
        # Compare column by column
        numeric_columns = original_df.select_dtypes(include=['float64', 'int64']).columns
        
        for col in original_df.columns:
            if col in optimized_df.columns:
                if col in numeric_columns:
                    # For numeric columns, check if values are close
                    if not pd.isna(original_df[col]).equals(pd.isna(optimized_df[col])):
                        comparison['differences'].append({
                            'column': col,
                            'type': 'null_mismatch',
                            'details': 'Different null patterns'
                        })
                    else:
                        # Compare non-null values
                        mask = ~pd.isna(original_df[col])
                        if mask.any():
                            orig_vals = original_df.loc[mask, col]
                            opt_vals = optimized_df.loc[mask, col]
                            
                            # Use relative tolerance for floating point comparison
                            if not pd.Series(orig_vals).equals(pd.Series(opt_vals)):
                                max_diff = abs(orig_vals - opt_vals).max()
                                if max_diff > 0.001:  # Tolerance for floating point
                                    comparison['differences'].append({
                                        'column': col,
                                        'type': 'value_mismatch',
                                        'max_difference': float(max_diff),
                                        'sample_original': float(orig_vals.iloc[0]) if len(orig_vals) > 0 else None,
                                        'sample_optimized': float(opt_vals.iloc[0]) if len(opt_vals) > 0 else None
                                    })
                else:
                    # For non-numeric columns, check exact match
                    if not original_df[col].equals(optimized_df[col]):
                        comparison['differences'].append({
                            'column': col,
                            'type': 'value_mismatch',
                            'details': 'Non-numeric column values differ'
                        })
            else:
                comparison['differences'].append({
                    'column': col,
                    'type': 'missing_column',
                    'details': 'Column missing in optimized version'
                })
        
        # Check for extra columns in optimized version
        for col in optimized_df.columns:
            if col not in original_df.columns:
                comparison['differences'].append({
                    'column': col,
                    'type': 'extra_column',
                    'details': 'Extra column in optimized version'
                })
        
        comparison['all_values_match'] = len(comparison['differences']) == 0
        
        return comparison
    
    def _log_validation_summary(self, results: Dict[str, Any]):
        """Log a summary of validation results."""
        logger.info("=" * 60)
        logger.info("OPTIMIZATION VALIDATION SUMMARY")
        logger.info("=" * 60)
        
        # Test parameters
        logger.info(f"Test accounts: {len(results['test_params']['accounts'])}")
        logger.info(f"Date range: {results['test_params']['start_date']} to {results['test_params']['end_date']}")
        
        # Performance comparison
        logger.info("\nPERFORMANCE COMPARISON:")
        logger.info(f"Original implementation:")
        logger.info(f"  - Execution time: {results['original']['execution_time']:.2f} seconds")
        logger.info(f"  - Estimated queries: {results['original']['queries_executed']}")
        
        logger.info(f"\nOptimized implementation:")
        logger.info(f"  - Execution time: {results['optimized']['execution_time']:.2f} seconds")
        logger.info(f"  - Bulk queries: {results['optimized']['query_stats']['bulk_queries']}")
        logger.info(f"  - Query reduction: {results['performance_improvement']['query_reduction_pct']:.1f}%")
        
        logger.info(f"\nIMPROVEMENT:")
        logger.info(f"  - Speedup: {results['performance_improvement']['speedup_factor']}x faster")
        logger.info(f"  - Time saved: {results['performance_improvement']['time_saved_seconds']:.2f} seconds")
        
        # Results comparison
        logger.info("\nRESULTS COMPARISON:")
        logger.info(f"Records created - Original: {results['original']['records_created']}, Optimized: {results['optimized']['records_created']}")
        
        if results['comparison']['all_values_match']:
            logger.info("✓ All feature values match between implementations!")
        else:
            logger.warning(f"✗ Found {len(results['comparison']['differences'])} differences:")
            for diff in results['comparison']['differences'][:5]:  # Show first 5
                logger.warning(f"  - {diff['column']}: {diff['type']} - {diff.get('details', '')}")
        
        logger.info("=" * 60)


def main():
    """Main function for testing optimization."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test feature engineering optimization')
    parser.add_argument('--accounts', nargs='+', help='Specific account IDs to test')
    parser.add_argument('--days', type=int, default=7, help='Number of days to test')
    parser.add_argument('--log-level', default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='test_optimization')
    
    # Run validation
    validator = OptimizationValidator()
    try:
        results = validator.validate_optimization(
            test_accounts=args.accounts,
            test_days=args.days
        )
        
        # Return success if all values match
        if results['comparison']['all_values_match']:
            logger.info("Optimization validation PASSED!")
            return 0
        else:
            logger.error("Optimization validation FAILED - results differ!")
            return 1
            
    except Exception as e:
        logger.error(f"Validation failed with error: {str(e)}")
        raise


if __name__ == '__main__':
    exit(main())