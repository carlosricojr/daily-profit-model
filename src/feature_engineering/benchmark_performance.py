"""
Performance Benchmarking for Feature Engineering v1
Measures computation time, memory usage, and feature quality.
"""

import time
import psutil
import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
import pandas as pd
import numpy as np
import argparse
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class FeatureEngineeringBenchmark:
    """Benchmark feature engineering performance."""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        self.results = {
            'computation_time': {},
            'memory_usage': {},
            'feature_quality': {},
            'data_quality': {}
        }
    
    def run_full_benchmark(self, n_accounts: int = 100, n_days: int = 30) -> Dict[str, Any]:
        """Run complete benchmark suite."""
        logger.info(f"Starting benchmark with {n_accounts} accounts over {n_days} days")
        
        # 1. Benchmark computation time
        self._benchmark_computation_time(n_accounts, n_days)
        
        # 2. Benchmark memory usage
        self._benchmark_memory_usage(n_accounts, n_days)
        
        # 3. Benchmark feature quality
        self._benchmark_feature_quality()
        
        # 4. Benchmark data quality
        self._benchmark_data_quality()
        
        # 5. Calculate summary metrics
        self._calculate_summary_metrics(n_accounts, n_days)
        
        return self.results
    
    def _benchmark_computation_time(self, n_accounts: int, n_days: int):
        """Measure feature computation time."""
        logger.info("Benchmarking computation time...")
        
        # Get sample accounts
        accounts_query = """
        SELECT DISTINCT account_id, login
        FROM stg_accounts_daily_snapshots
        WHERE date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY RANDOM()
        LIMIT %s
        """
        accounts = self.db_manager.model_db.execute_query(accounts_query, (n_accounts,))
        
        if not accounts:
            logger.warning("No accounts found for benchmarking")
            return
        
        # Measure time for different operations
        operations = {
            'single_account_single_day': self._time_single_account_single_day,
            'single_account_all_days': self._time_single_account_all_days,
            'all_accounts_single_day': self._time_all_accounts_single_day,
            'batch_processing': self._time_batch_processing
        }
        
        for op_name, op_func in operations.items():
            start_time = time.time()
            record_count = op_func(accounts, n_days)
            elapsed_time = time.time() - start_time
            
            self.results['computation_time'][op_name] = {
                'elapsed_seconds': elapsed_time,
                'records_processed': record_count,
                'records_per_second': record_count / elapsed_time if elapsed_time > 0 else 0
            }
            
            logger.info(f"{op_name}: {elapsed_time:.2f}s for {record_count} records")
    
    def _time_single_account_single_day(self, accounts: List[Dict], n_days: int) -> int:
        """Time feature calculation for single account, single day."""
        if not accounts:
            return 0
        
        account = accounts[0]
        feature_date = date.today() - timedelta(days=1)
        
        # Simulate feature calculation
        query = """
        SELECT COUNT(*) as count
        FROM raw_metrics_daily
        WHERE account_id = %s AND date <= %s
        LIMIT 60
        """
        
        self.db_manager.model_db.execute_query(
            query, (account['account_id'], feature_date)
        )
        
        return 1
    
    def _time_single_account_all_days(self, accounts: List[Dict], n_days: int) -> int:
        """Time feature calculation for single account, multiple days."""
        if not accounts:
            return 0
        
        account = accounts[0]
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=n_days-1)
        
        # Simulate feature calculation for date range
        query = """
        SELECT COUNT(*) as count
        FROM raw_metrics_daily
        WHERE account_id = %s AND date >= %s AND date <= %s
        """
        
        self.db_manager.model_db.execute_query(
            query, (account['account_id'], start_date, end_date)
        )
        
        return n_days
    
    def _time_all_accounts_single_day(self, accounts: List[Dict], n_days: int) -> int:
        """Time feature calculation for all accounts, single day."""
        if not accounts:
            return 0
        
        account_ids = [a['account_id'] for a in accounts]
        feature_date = date.today() - timedelta(days=1)
        
        # Simulate batch feature calculation
        query = """
        SELECT COUNT(*) as count
        FROM raw_metrics_daily
        WHERE account_id = ANY(%s) AND date = %s
        """
        
        self.db_manager.model_db.execute_query(
            query, (account_ids, feature_date)
        )
        
        return len(accounts)
    
    def _time_batch_processing(self, accounts: List[Dict], n_days: int) -> int:
        """Time batch processing approach."""
        if not accounts:
            return 0
        
        account_ids = [a['account_id'] for a in accounts[:10]]  # Limit for benchmark
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=n_days-1)
        
        # Simulate batch processing
        query = """
        SELECT account_id, date, net_profit
        FROM raw_metrics_daily
        WHERE account_id = ANY(%s) 
            AND date >= %s 
            AND date <= %s
        ORDER BY date, account_id
        """
        
        df = self.db_manager.model_db.execute_query_df(
            query, (account_ids, start_date, end_date)
        )
        
        return len(df)
    
    def _benchmark_memory_usage(self, n_accounts: int, n_days: int):
        """Measure memory usage patterns."""
        logger.info("Benchmarking memory usage...")
        
        process = psutil.Process(os.getpid())
        
        # Get baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Test different scenarios
        scenarios = {
            'small_batch': (10, 7),
            'medium_batch': (50, 30),
            'large_batch': (min(n_accounts, 100), min(n_days, 60))
        }
        
        for scenario_name, (test_accounts, test_days) in scenarios.items():
            # Force garbage collection
            import gc
            gc.collect()
            
            start_memory = process.memory_info().rss / 1024 / 1024
            
            # Simulate loading data
            self._simulate_data_loading(test_accounts, test_days)
            
            peak_memory = process.memory_info().rss / 1024 / 1024
            
            # Clean up
            gc.collect()
            
            end_memory = process.memory_info().rss / 1024 / 1024
            
            self.results['memory_usage'][scenario_name] = {
                'baseline_mb': baseline_memory,
                'start_mb': start_memory,
                'peak_mb': peak_memory,
                'end_mb': end_memory,
                'peak_increase_mb': peak_memory - start_memory,
                'accounts': test_accounts,
                'days': test_days
            }
    
    def _simulate_data_loading(self, n_accounts: int, n_days: int):
        """Simulate data loading for memory testing."""
        # Get sample data
        query = """
        SELECT *
        FROM raw_metrics_daily
        WHERE date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY RANDOM()
        LIMIT %s
        """
        
        limit = n_accounts * n_days
        df = self.db_manager.model_db.execute_query_df(
            query, (n_days + 30, limit)
        )
        
        # Simulate feature calculation
        if not df.empty:
            # Rolling calculations
            for window in [3, 5, 10]:
                df[f'rolling_avg_{window}'] = df.groupby('account_id')['net_profit'].transform(
                    lambda x: x.rolling(window, min_periods=1).mean()
                )
        
        return df
    
    def _benchmark_feature_quality(self):
        """Assess feature quality metrics."""
        logger.info("Benchmarking feature quality...")
        
        # Sample recent features
        sample_query = """
        SELECT *
        FROM feature_store_account_daily
        WHERE feature_date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY RANDOM()
        LIMIT 1000
        """
        
        df = self.db_manager.model_db.execute_query_df(sample_query)
        
        if df.empty:
            logger.warning("No features found for quality assessment")
            return
        
        # Calculate quality metrics
        feature_cols = [col for col in df.columns 
                       if col not in ['account_id', 'login', 'feature_date']]
        
        quality_metrics = {}
        
        for col in feature_cols:
            if col in df.columns:
                # Coverage (non-null percentage)
                coverage = (df[col].notna().sum() / len(df)) * 100
                
                # For numeric columns, calculate additional stats
                if pd.api.types.is_numeric_dtype(df[col]):
                    col_data = df[col].dropna()
                    if len(col_data) > 0:
                        quality_metrics[col] = {
                            'coverage_pct': coverage,
                            'mean': float(col_data.mean()),
                            'std': float(col_data.std()),
                            'min': float(col_data.min()),
                            'max': float(col_data.max()),
                            'zeros_pct': (col_data == 0).sum() / len(col_data) * 100
                        }
                else:
                    quality_metrics[col] = {
                        'coverage_pct': coverage,
                        'unique_values': df[col].nunique()
                    }
        
        self.results['feature_quality'] = {
            'total_features': len(feature_cols),
            'sample_size': len(df),
            'feature_metrics': quality_metrics,
            'overall_coverage': np.mean([m.get('coverage_pct', 0) 
                                        for m in quality_metrics.values()])
        }
    
    def _benchmark_data_quality(self):
        """Assess data quality and integrity."""
        logger.info("Benchmarking data quality...")
        
        quality_checks = {}
        
        # 1. Check for duplicate features
        duplicate_query = """
        SELECT COUNT(*) as duplicates
        FROM (
            SELECT account_id, feature_date, COUNT(*) as cnt
            FROM feature_store_account_daily
            WHERE feature_date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY account_id, feature_date
            HAVING COUNT(*) > 1
        ) dups
        """
        result = self.db_manager.model_db.execute_query(duplicate_query)
        quality_checks['duplicate_features'] = result[0]['duplicates'] if result else 0
        
        # 2. Check feature-target alignment
        alignment_query = """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN prediction_date = feature_date + INTERVAL '1 day' THEN 1 END) as aligned
        FROM model_training_input
        WHERE prediction_date >= CURRENT_DATE - INTERVAL '30 days'
        LIMIT 10000
        """
        result = self.db_manager.model_db.execute_query(alignment_query)
        if result and result[0]['total'] > 0:
            quality_checks['alignment_accuracy_pct'] = (
                result[0]['aligned'] / result[0]['total'] * 100
            )
        else:
            quality_checks['alignment_accuracy_pct'] = 0
        
        # 3. Check for data gaps
        gap_query = """
        WITH date_series AS (
            SELECT generate_series(
                CURRENT_DATE - INTERVAL '30 days',
                CURRENT_DATE - INTERVAL '1 day',
                '1 day'::interval
            )::date as date
        ),
        account_dates AS (
            SELECT DISTINCT account_id, feature_date
            FROM feature_store_account_daily
            WHERE feature_date >= CURRENT_DATE - INTERVAL '30 days'
        ),
        expected AS (
            SELECT a.account_id, d.date
            FROM (SELECT DISTINCT account_id FROM account_dates) a
            CROSS JOIN date_series d
        ),
        actual AS (
            SELECT account_id, feature_date as date
            FROM account_dates
        )
        SELECT COUNT(*) as missing_records
        FROM expected e
        LEFT JOIN actual a 
            ON e.account_id = a.account_id AND e.date = a.date
        WHERE a.account_id IS NULL
        LIMIT 10000
        """
        result = self.db_manager.model_db.execute_query(gap_query)
        quality_checks['data_gaps'] = result[0]['missing_records'] if result else 0
        
        # 4. Check for extreme values
        extreme_query = """
        SELECT 
            COUNT(CASE WHEN ABS(rolling_pnl_avg_5d) > 10000 THEN 1 END) as extreme_pnl,
            COUNT(CASE WHEN win_rate_5d > 100 OR win_rate_5d < 0 THEN 1 END) as invalid_win_rate,
            COUNT(CASE WHEN sharpe_ratio_5d > 10 OR sharpe_ratio_5d < -10 THEN 1 END) as extreme_sharpe,
            COUNT(*) as total
        FROM feature_store_account_daily
        WHERE feature_date >= CURRENT_DATE - INTERVAL '30 days'
        """
        result = self.db_manager.model_db.execute_query(extreme_query)
        if result:
            quality_checks['extreme_values'] = {
                'extreme_pnl_count': result[0]['extreme_pnl'],
                'invalid_win_rate_count': result[0]['invalid_win_rate'],
                'extreme_sharpe_count': result[0]['extreme_sharpe'],
                'total_checked': result[0]['total']
            }
        
        self.results['data_quality'] = quality_checks
    
    def _calculate_summary_metrics(self, n_accounts: int, n_days: int):
        """Calculate summary performance metrics."""
        summary = {
            'benchmark_config': {
                'n_accounts': n_accounts,
                'n_days': n_days,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # Computation efficiency
        if 'batch_processing' in self.results['computation_time']:
            batch_metrics = self.results['computation_time']['batch_processing']
            summary['computation_efficiency'] = {
                'records_per_second': batch_metrics.get('records_per_second', 0),
                'estimated_daily_capacity': batch_metrics.get('records_per_second', 0) * 3600 * 8  # 8 hour window
            }
        
        # Memory efficiency
        if 'large_batch' in self.results['memory_usage']:
            mem_metrics = self.results['memory_usage']['large_batch']
            if mem_metrics['accounts'] > 0:
                summary['memory_efficiency'] = {
                    'mb_per_account': mem_metrics['peak_increase_mb'] / mem_metrics['accounts'],
                    'estimated_1k_accounts_mb': (mem_metrics['peak_increase_mb'] / mem_metrics['accounts']) * 1000
                }
        
        # Feature quality
        if 'feature_quality' in self.results:
            summary['feature_quality_summary'] = {
                'total_features': self.results['feature_quality'].get('total_features', 0),
                'overall_coverage_pct': self.results['feature_quality'].get('overall_coverage', 0)
            }
        
        # Data quality
        if 'data_quality' in self.results:
            summary['data_quality_summary'] = {
                'has_duplicates': self.results['data_quality'].get('duplicate_features', 0) > 0,
                'alignment_ok': self.results['data_quality'].get('alignment_accuracy_pct', 0) >= 99,
                'has_data_gaps': self.results['data_quality'].get('data_gaps', 0) > 0
            }
        
        self.results['summary'] = summary
    
    def save_results(self, output_path: str):
        """Save benchmark results to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        logger.info(f"Benchmark results saved to {output_path}")
    
    def print_summary(self):
        """Print benchmark summary to console."""
        print("\n" + "="*60)
        print("FEATURE ENGINEERING v1 PERFORMANCE BENCHMARK")
        print("="*60)
        
        if 'summary' in self.results:
            summary = self.results['summary']
            
            print("\nBenchmark Configuration:")
            print(f"  Accounts: {summary['benchmark_config']['n_accounts']}")
            print(f"  Days: {summary['benchmark_config']['n_days']}")
            
            if 'computation_efficiency' in summary:
                print("\nComputation Performance:")
                print(f"  Records/second: {summary['computation_efficiency']['records_per_second']:.2f}")
                print(f"  Est. daily capacity: {summary['computation_efficiency']['estimated_daily_capacity']:,.0f} records")
            
            if 'memory_efficiency' in summary:
                print("\nMemory Usage:")
                print(f"  MB per account: {summary['memory_efficiency']['mb_per_account']:.2f}")
                print(f"  Est. 1K accounts: {summary['memory_efficiency']['estimated_1k_accounts_mb']:.0f} MB")
            
            if 'feature_quality_summary' in summary:
                print("\nFeature Quality:")
                print(f"  Total features: {summary['feature_quality_summary']['total_features']}")
                print(f"  Overall coverage: {summary['feature_quality_summary']['overall_coverage_pct']:.1f}%")
            
            if 'data_quality_summary' in summary:
                print("\nData Quality:")
                quality = summary['data_quality_summary']
                print(f"  Duplicates: {'Yes' if quality['has_duplicates'] else 'No'}")
                print(f"  Alignment OK: {'Yes' if quality['alignment_ok'] else 'No'}")
                print(f"  Data gaps: {'Yes' if quality['has_data_gaps'] else 'No'}")
        
        print("\n" + "="*60)


def main():
    """Run performance benchmark."""
    parser = argparse.ArgumentParser(description='Benchmark feature engineering performance')
    parser.add_argument('--accounts', type=int, default=100,
                       help='Number of accounts to benchmark')
    parser.add_argument('--days', type=int, default=30,
                       help='Number of days to process')
    parser.add_argument('--output', type=str, default='benchmark_results_v1.json',
                       help='Output file for results')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='benchmark_v1')
    
    # Run benchmark
    benchmark = FeatureEngineeringBenchmark()
    
    try:
        benchmark.run_full_benchmark(
            n_accounts=args.accounts,
            n_days=args.days
        )
        
        # Save results
        benchmark.save_results(args.output)
        
        # Print summary
        benchmark.print_summary()
        
    except Exception as e:
        logger.error(f"Benchmark failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()