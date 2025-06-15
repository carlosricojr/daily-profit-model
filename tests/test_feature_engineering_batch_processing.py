#!/usr/bin/env python3
"""
Comprehensive tests for feature engineering batch processing and saving.
Tests batch operations, error recovery, and database operations with ML best practices.
"""

import unittest
from unittest.mock import patch, Mock
from datetime import date, datetime
import pandas as pd
import numpy as np
import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.feature_engineering.feature_engineering import UnifiedFeatureEngineer


class TestBatchProcessing(unittest.TestCase):
    """Test batch processing with ML engineering best practices."""

    def setUp(self):
        """Setup test fixtures."""
        self.mock_db_patcher = patch('src.feature_engineering.feature_engineering.get_db_manager')
        self.mock_get_db = self.mock_db_patcher.start()
        self.mock_db = Mock()
        self.mock_get_db.return_value = self.mock_db
        
        # Mock query monitor
        self.mock_query_monitor_patcher = patch('src.feature_engineering.feature_engineering.QueryPerformanceMonitor')
        self.mock_query_monitor_class = self.mock_query_monitor_patcher.start()
        self.mock_query_monitor = Mock()
        self.mock_query_monitor_class.return_value = self.mock_query_monitor
        self.mock_query_monitor.track_query.return_value.__enter__ = Mock(return_value=None)
        self.mock_query_monitor.track_query.return_value.__exit__ = Mock(return_value=None)
        
        # Create engineer with small batch size for testing
        self.engineer = UnifiedFeatureEngineer(config={"batch_size": 3})
        
        # Setup logger to capture logs
        self.log_capture = []
        self.test_handler = logging.Handler()
        self.test_handler.emit = lambda record: self.log_capture.append(record)
        logger = logging.getLogger('src.feature_engineering.feature_engineering')
        logger.addHandler(self.test_handler)
        logger.setLevel(logging.INFO)

    def tearDown(self):
        """Cleanup test fixtures."""
        self.mock_db_patcher.stop()
        self.mock_query_monitor_patcher.stop()
        logger = logging.getLogger('src.feature_engineering.feature_engineering')
        logger.removeHandler(self.test_handler)

    def test_process_batches_normal_flow(self):
        """Test normal batch processing flow."""
        # Create work items
        work_items = [
            ("ACC001", "12345", date(2024, 1, 10)),
            ("ACC002", "12346", date(2024, 1, 10)),
            ("ACC003", "12347", date(2024, 1, 10)),
            ("ACC004", "12348", date(2024, 1, 11)),
            ("ACC005", "12349", date(2024, 1, 11)),
        ]
        
        # Mock bulk fetch to return data for all accounts
        def mock_bulk_fetch_all_data(account_ids, dates, start_date, end_date, include_enhanced):
            bulk_data = {
                "static_features": {},
                "dynamic_features": {},
                "open_positions": {},
                "performance_data": {},
                "trades_data": {},
                "market_data": {},
            }
            
            # Add data for each account/date combination
            for acc_id in account_ids:
                for dt in dates:
                    key = (acc_id, dt)
                    bulk_data["static_features"][key] = {"starting_balance": 50000}
                    bulk_data["dynamic_features"][key] = {"current_balance": 52000}
                    bulk_data["open_positions"][key] = {"open_pnl": 100}
                    bulk_data["market_data"][dt] = {"market_sentiment_score": 0.1}
            
            return bulk_data
        
        self.engineer._bulk_fetch_all_data = Mock(side_effect=mock_bulk_fetch_all_data)
        
        # Mock feature calculation
        def mock_calculate_features(account_id, login, feature_date, bulk_data, include_enhanced):
            return {
                "account_id": account_id,
                "login": login,
                "feature_date": feature_date,
                "feature_version": "5.0.0",
                "current_balance": 52000
            }
        
        self.engineer._calculate_features_from_bulk_data = Mock(side_effect=mock_calculate_features)
        
        # Mock validation to always pass
        self.engineer._validate_features = Mock(return_value=True)
        
        # Mock bulk save
        self.engineer._bulk_save_features = Mock(return_value=2)  # Return number saved
        
        # Process batches
        total_records = self.engineer._process_batches(
            work_items, 
            date(2024, 1, 10), 
            date(2024, 1, 11),
            validate_bias=True,
            include_enhanced_metrics=False
        )
        
        # Verify batching occurred correctly
        # With batch_size=3, should have 2 batches: [3 items, 2 items]
        self.assertEqual(self.engineer._bulk_fetch_all_data.call_count, 2)
        self.assertEqual(self.engineer._bulk_save_features.call_count, 2)
        
        # Verify total records processed
        self.assertEqual(total_records, 4)  # 2 saves * 2 records each
        
        # Check progress logging (100 items = log every batch, 5 items = log at 100%)
        progress_logs = [r for r in self.log_capture if "Progress:" in r.getMessage()]
        self.assertGreater(len(progress_logs), 0)

    def test_process_batches_with_failures(self):
        """Test batch processing with individual feature calculation failures."""
        work_items = [
            ("ACC001", "12345", date(2024, 1, 10)),
            ("ACC002", "12346", date(2024, 1, 10)),  # This will fail
            ("ACC003", "12347", date(2024, 1, 10)),
        ]
        
        # Mock bulk fetch
        self.engineer._bulk_fetch_all_data = Mock(return_value={
            "static_features": {},
            "dynamic_features": {},
            "open_positions": {},
            "performance_data": {},
            "trades_data": {},
            "market_data": {},
        })
        
        # Mock feature calculation to fail for ACC002
        def mock_calculate_features(account_id, login, feature_date, bulk_data, include_enhanced):
            if account_id == "ACC002":
                raise Exception("Feature calculation failed for ACC002")
            return {
                "account_id": account_id,
                "login": login,
                "feature_date": feature_date,
                "feature_version": "5.0.0"
            }
        
        self.engineer._calculate_features_from_bulk_data = Mock(side_effect=mock_calculate_features)
        self.engineer._validate_features = Mock(return_value=True)
        self.engineer._bulk_save_features = Mock(return_value=2)  # Save successful features
        
        # Process batch
        total_records = self.engineer._process_batches(
            work_items,
            date(2024, 1, 10),
            date(2024, 1, 10),
            validate_bias=False,
            include_enhanced_metrics=False
        )
        
        # Should process ACC001 and ACC003, skip ACC002
        self.assertEqual(total_records, 2)
        
        # Check error was logged
        error_logs = [r for r in self.log_capture if r.levelno == logging.ERROR]
        self.assertTrue(any("ACC002" in r.getMessage() for r in error_logs))
        
        # Verify error counter was incremented
        self.assertEqual(self.engineer.performance_metrics["errors_encountered"], 1)

    def test_process_batches_progress_logging(self):
        """Test progress logging at correct intervals."""
        # Create 100 work items
        work_items = [(f"ACC{i:03d}", f"123{i:02d}", date(2024, 1, 10)) 
                      for i in range(100)]
        
        # Mock methods
        self.engineer._bulk_fetch_all_data = Mock(return_value={})
        self.engineer._calculate_features_from_bulk_data = Mock(return_value={"account_id": "test"})
        self.engineer._validate_features = Mock(return_value=True)
        self.engineer._bulk_save_features = Mock(return_value=3)
        
        # Clear log capture
        self.log_capture.clear()
        
        # Process batches
        self.engineer._process_batches(
            work_items,
            date(2024, 1, 10),
            date(2024, 1, 10),
            validate_bias=False,
            include_enhanced_metrics=False
        )
        
        # For 100 items with batch_size=3, we have ~34 batches
        # Should log every 5% of total work items = every 5 items processed
        # So approximately every 2 batches (5/3 ≈ 2)
        progress_logs = [r for r in self.log_capture if "Progress:" in r.getMessage()]
        
        # Should have multiple progress logs
        self.assertGreater(len(progress_logs), 1)
        
        # Last log should show 100%
        self.assertIn("100", progress_logs[-1].getMessage())

    def test_bulk_fetch_all_data_orchestration(self):
        """Test orchestration of all bulk fetch operations."""
        # Mock all individual bulk fetch methods
        self.engineer._bulk_fetch_static_features = Mock(return_value={"static": "data"})
        self.engineer._bulk_fetch_dynamic_features = Mock(return_value={"dynamic": "data"})
        self.engineer._bulk_fetch_open_positions = Mock(return_value={"positions": "data"})
        self.engineer._bulk_fetch_performance_data = Mock(return_value={"performance": "data"})
        self.engineer._bulk_fetch_trades_data = Mock(return_value={"trades": "data"})
        self.engineer._bulk_fetch_market_data = Mock(return_value={"market": "data"})
        self.engineer._bulk_fetch_enhanced_metrics = Mock(return_value={"enhanced": "data"})
        self.engineer._bulk_fetch_alltime_metrics = Mock(return_value={"alltime": "data"})
        
        account_ids = ["ACC001", "ACC002"]
        dates = [date(2024, 1, 10), date(2024, 1, 11)]
        
        # Test without enhanced metrics
        self.engineer._bulk_fetch_all_data(
            account_ids, dates, date(2024, 1, 10), date(2024, 1, 11), 
            include_enhanced_metrics=False
        )
        
        # Verify all basic fetches were called
        self.engineer._bulk_fetch_static_features.assert_called_once_with(account_ids, dates)
        self.engineer._bulk_fetch_dynamic_features.assert_called_once_with(account_ids, dates)
        self.engineer._bulk_fetch_open_positions.assert_called_once_with(account_ids, dates)
        self.engineer._bulk_fetch_performance_data.assert_called_once()
        self.engineer._bulk_fetch_trades_data.assert_called_once()
        self.engineer._bulk_fetch_market_data.assert_called_once_with(dates)
        
        # Enhanced metrics should NOT be called
        self.engineer._bulk_fetch_enhanced_metrics.assert_not_called()
        self.engineer._bulk_fetch_alltime_metrics.assert_not_called()
        
        # Test with enhanced metrics
        self.engineer._bulk_fetch_enhanced_metrics.reset_mock()
        self.engineer._bulk_fetch_alltime_metrics.reset_mock()
        
        self.engineer._bulk_fetch_all_data(
            account_ids, dates, date(2024, 1, 10), date(2024, 1, 11),
            include_enhanced_metrics=True
        )
        
        # Enhanced metrics should be called
        self.engineer._bulk_fetch_enhanced_metrics.assert_called_once()
        self.engineer._bulk_fetch_alltime_metrics.assert_called_once_with(account_ids)

    def test_validate_features_comprehensive(self):
        """Test comprehensive feature validation."""
        features = {
            "account_id": "ACC001",
            "feature_date": date(2024, 1, 10),
            "daily_sharpe": 25.0,  # Unrealistic
            "daily_sortino": 1.8,  # Realistic
            "daily_gain_to_pain": -0.5,  # Invalid negative
            "profit_distribution_skew": 0.5,  # Valid
            "volatility_adaptability": 0.7,  # Valid
        }
        
        # Mock bulk data with performance data
        bulk_data = {
            "performance_data": {
                "ACC001": pd.DataFrame({
                    "date": pd.date_range(end=date(2024, 1, 10), periods=10).date,
                    "net_profit": np.random.normal(100, 50, 10)
                })
            }
        }
        
        # Mock bias validator
        self.engineer.bias_validator.validate_data_availability = Mock(return_value=True)
        self.engineer.bias_validator.validate_feature_target_alignment = Mock()
        self.engineer.bias_validator.validate_rolling_window = Mock(return_value=True)
        
        # Validate
        is_valid = self.engineer._validate_features(features, date(2024, 1, 10), bulk_data)
        
        # Should be valid overall
        self.assertTrue(is_valid)
        
        # Unrealistic values should be corrected
        self.assertEqual(features["daily_sharpe"], 0.0)  # Reset from 25.0
        self.assertEqual(features["daily_sortino"], 1.8)  # Kept as is
        self.assertEqual(features["daily_gain_to_pain"], 0.0)  # Reset from negative
        
        # Check bias validation was called
        self.engineer.bias_validator.validate_data_availability.assert_called()
        self.engineer.bias_validator.validate_feature_target_alignment.assert_called()

    def test_bulk_save_features_success(self):
        """Test successful bulk save of features."""
        features_batch = [
            {
                "account_id": "ACC001",
                "feature_date": date(2024, 1, 10),
                "feature_version": "5.0.0",
                "current_balance": 52000,
                "rolling_pnl_avg_5d": 150.0,
            },
            {
                "account_id": "ACC002", 
                "feature_date": date(2024, 1, 10),
                "feature_version": "5.0.0",
                "current_balance": 48000,
                "rolling_pnl_avg_5d": -50.0,
            }
        ]
        
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.rowcount = 2
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_db.model_db.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        self.mock_db.model_db.get_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Execute bulk save
        saved_count = self.engineer._bulk_save_features(features_batch)
        
        # Verify
        self.assertEqual(saved_count, 2)
        
        # Check SQL was executed
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        
        # Verify SQL structure
        self.assertIn("INSERT INTO feature_store_account_daily", sql_call)
        self.assertIn("ON CONFLICT (account_id, feature_date)", sql_call)
        self.assertIn("DO UPDATE SET", sql_call)

    def test_bulk_save_features_with_conflict(self):
        """Test bulk save with ON CONFLICT handling."""
        features_batch = [
            {
                "account_id": "ACC001",
                "feature_date": date(2024, 1, 10),
                "feature_version": "5.0.0",
                "current_balance": 52000,
                "created_at": datetime.now(),
            }
        ]
        
        # Mock successful update on conflict
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.rowcount = 1  # One row affected (updated)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_db.model_db.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        self.mock_db.model_db.get_connection.return_value.__exit__ = Mock(return_value=None)
        
        saved_count = self.engineer._bulk_save_features(features_batch)
        
        # Should handle conflict gracefully
        self.assertEqual(saved_count, 1)

    def test_bulk_save_features_fallback_to_single(self):
        """Test fallback to single saves when bulk save fails."""
        features_batch = [
            {"account_id": "ACC001", "feature_date": date(2024, 1, 10), "value": 1},
            {"account_id": "ACC002", "feature_date": date(2024, 1, 10), "value": 2},
            {"account_id": "ACC003", "feature_date": date(2024, 1, 10), "value": 3},
        ]
        
        # Mock bulk save to fail
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception("Bulk insert failed")
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_db.model_db.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        self.mock_db.model_db.get_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Mock single save to succeed for 2 out of 3
        single_save_count = 0
        def mock_single_save(features):
            nonlocal single_save_count
            if features["account_id"] != "ACC002":  # ACC002 fails
                single_save_count += 1
            else:
                raise Exception("Single save failed for ACC002")
        
        self.engineer._save_single_feature = Mock(side_effect=mock_single_save)
        
        # Execute
        saved_count = self.engineer._bulk_save_features(features_batch)
        
        # Should have tried single saves and saved 2 out of 3
        self.assertEqual(saved_count, 2)
        self.assertEqual(self.engineer._save_single_feature.call_count, 3)
        
        # Check error was logged
        error_logs = [r for r in self.log_capture if r.levelno == logging.ERROR]
        self.assertTrue(any("bulk saving features" in r.getMessage() for r in error_logs))
        self.assertTrue(any("ACC002" in r.getMessage() for r in error_logs))

    def test_save_single_feature(self):
        """Test single feature save functionality."""
        feature = {
            "account_id": "ACC001",
            "feature_date": date(2024, 1, 10),
            "feature_version": "5.0.0",
            "current_balance": 52000,
            "rolling_pnl_avg_5d": 150.0,
        }
        
        # Mock database
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_db.model_db.get_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        self.mock_db.model_db.get_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Execute
        self.engineer._save_single_feature(feature)
        
        # Verify SQL execution
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        
        # Check SQL structure
        self.assertIn("INSERT INTO feature_store_account_daily", sql_call)
        self.assertIn("ON CONFLICT (account_id, feature_date)", sql_call)
        
        # Check values were passed
        values = mock_cursor.execute.call_args[0][1]
        self.assertIn("ACC001", values)
        self.assertIn(date(2024, 1, 10), values)
        self.assertIn("5.0.0", values)

    def test_error_recovery_retry_logic(self):
        """Test error recovery with retry logic for failed accounts."""
        work_items = [("ACC001", "12345", date(2024, 1, 10))]
        
        # Mock bulk fetch
        self.engineer._bulk_fetch_all_data = Mock(return_value={})
        
        # Mock feature calculation to fail first 2 times, succeed on 3rd
        self.call_count = 0
        def mock_calculate_with_retry(account_id, login, feature_date, bulk_data, include_enhanced):
            self.call_count += 1
            if self.call_count < 3:
                raise Exception(f"Temporary failure #{self.call_count}")
            return {"account_id": account_id, "feature_date": feature_date}
        
        self.engineer._calculate_features_from_bulk_data = Mock(side_effect=mock_calculate_with_retry)
        self.engineer._validate_features = Mock(return_value=True)
        self.engineer._bulk_save_features = Mock(return_value=1)
        
        # ML Best Practice: Implement retry logic (3 attempts)
        # This would be in the actual implementation
        # For now, we test that failures are logged appropriately
        
        self.engineer._process_batches(
            work_items,
            date(2024, 1, 10),
            date(2024, 1, 10),
            validate_bias=False,
            include_enhanced_metrics=False
        )
        
        # In current implementation, it fails once
        # In ideal implementation with retry, it would succeed after 3 attempts
        # This test documents the expected behavior for retry logic
        
        # Check that error was logged
        error_logs = [r for r in self.log_capture if r.levelno == logging.ERROR]
        self.assertTrue(len(error_logs) > 0)


class TestMonitoringAndReporting(unittest.TestCase):
    """Test monitoring and reporting functionality."""

    def setUp(self):
        """Setup test fixtures."""
        self.mock_db_patcher = patch('src.feature_engineering.feature_engineering.get_db_manager')
        self.mock_get_db = self.mock_db_patcher.start()
        self.mock_db = Mock()
        self.mock_get_db.return_value = self.mock_db
        
        self.engineer = UnifiedFeatureEngineer()

    def tearDown(self):
        """Cleanup test fixtures."""
        self.mock_db_patcher.stop()

    def test_run_comprehensive_monitoring(self):
        """Test comprehensive quality monitoring."""
        # Mock sample data
        sample_df = pd.DataFrame({
            "account_id": ["ACC001", "ACC002"] * 50,
            "feature_date": pd.date_range(start="2024-01-10", periods=100).date,
            "current_balance": np.random.normal(50000, 5000, 100),
            "rolling_pnl_avg_5d": np.random.normal(100, 50, 100),
            "trades_count_5d": np.random.randint(0, 20, 100),
            "market_sentiment_score": np.random.uniform(-1, 1, 100),
            "day_of_week": np.random.randint(0, 7, 100),
        })
        
        self.mock_db.model_db.execute_query_df.return_value = sample_df
        
        # Mock quality monitor
        self.engineer.quality_monitor.monitor_feature_coverage = Mock(return_value={
            "current_balance": {"coverage_rate": 1.0, "is_adequate": True},
            "rolling_pnl_avg_5d": {"coverage_rate": 0.95, "is_adequate": True},
        })
        
        self.engineer.quality_monitor.get_quality_summary = Mock(return_value={
            "total_issues": 2,
            "quality_score": 0.95
        })
        
        # Run monitoring
        result = self.engineer._run_comprehensive_monitoring(
            date(2024, 1, 10), date(2024, 1, 20)
        )
        
        # Verify structure
        self.assertIn("sample_size", result)
        self.assertIn("coverage", result)
        self.assertIn("distributions", result)
        self.assertIn("summary", result)
        
        # Verify sample size
        self.assertEqual(result["sample_size"], 100)

    def test_analyze_feature_distributions(self):
        """Test feature distribution analysis."""
        # Create test data with known distributions
        test_df = pd.DataFrame({
            "account_id": ["ACC001"] * 100,
            "feature_date": pd.date_range(start="2024-01-01", periods=100).date,
            "feature_numeric_1": np.random.normal(100, 20, 100),
            "feature_numeric_2": np.random.uniform(0, 1, 100),
            "feature_numeric_3": np.concatenate([np.full(50, np.nan), np.random.normal(50, 10, 50)]),
        })
        
        distributions = self.engineer._analyze_feature_distributions(test_df)
        
        # Check numeric features are analyzed
        self.assertIn("feature_numeric_1", distributions)
        self.assertIn("feature_numeric_2", distributions)
        self.assertIn("feature_numeric_3", distributions)
        
        # Check statistics
        feat1_stats = distributions["feature_numeric_1"]
        self.assertIn("mean", feat1_stats)
        self.assertIn("std", feat1_stats)
        self.assertIn("min", feat1_stats)
        self.assertIn("max", feat1_stats)
        self.assertIn("nulls", feat1_stats)
        self.assertIn("null_pct", feat1_stats)
        
        # Verify null percentage calculation
        feat3_stats = distributions["feature_numeric_3"]
        self.assertEqual(feat3_stats["nulls"], 50)
        self.assertEqual(feat3_stats["null_pct"], 50.0)

    def test_create_comprehensive_summary(self):
        """Test comprehensive summary creation."""
        start_time = datetime.now()
        
        # Mock components
        self.engineer.bias_validator.get_violations_summary = Mock(return_value={
            "has_violations": False,
            "count": 0,
            "violation_rate": 0.0
        })
        
        self.engineer.query_monitor.get_summary = Mock(return_value={
            "total_queries": 100,
            "total_time": 45.5,
            "avg_query_time": 0.455,
            "slow_queries_count": 2,
            "queries_by_type": {"bulk_fetch": 20, "bulk_save": 5}
        })
        
        quality_results = {
            "sample_size": 1000,
            "coverage": {"feature1": {"coverage_rate": 0.98}},
            "summary": {"quality_score": 0.96}
        }
        
        # Create summary
        result = self.engineer._create_comprehensive_summary(
            start_time,
            total_records=500,
            validate_bias=True,
            enable_monitoring=True,
            quality_results=quality_results
        )
        
        # Verify structure
        self.assertEqual(result["total_records"], 500)
        self.assertIn("execution_time_seconds", result)
        self.assertEqual(result["feature_version"], "5.0.0")
        
        # Check configuration
        self.assertTrue(result["configuration"]["validation_enabled"])
        self.assertTrue(result["configuration"]["monitoring_enabled"])
        
        # Check performance metrics
        self.assertIn("records_per_second", result["performance_metrics"])
        
        # Check query optimization
        self.assertIn("query_reduction_factor", result["query_optimization"])
        
        # Check optional sections
        self.assertIn("lookahead_bias_check", result)
        self.assertIn("quality_monitoring", result)

    def test_log_completion_status(self):
        """Test completion status logging."""
        result = {
            "total_records": 1000,
            "execution_time_seconds": 120.5,
            "performance_metrics": {"records_per_second": 8.3},
            "query_optimization": {
                "bulk_queries": 50,
                "equivalent_individual_queries": 500,
                "query_reduction_factor": 10.0,
                "avg_query_time": 0.241
            },
            "lookahead_bias_check": {
                "has_violations": False,
                "count": 0,
                "violation_rate": 0.0
            },
            "quality_monitoring": {
                "summary": {
                    "quality_score": 0.98,
                    "total_issues": 3,
                    "issue_breakdown": {"low_coverage": 2, "out_of_range": 1}
                },
                "distributions": {
                    "daily_sharpe": {"mean": 1.5, "std": 0.3, "null_pct": 2.0},
                    "daily_sortino": {"mean": 1.8, "std": 0.4, "null_pct": 2.0},
                    "volatility_adaptability": {"mean": 0.7, "std": 0.15, "null_pct": 5.0}
                }
            }
        }
        
        # Capture logs
        log_capture = []
        test_handler = logging.Handler()
        test_handler.emit = lambda record: log_capture.append(record)
        logger = logging.getLogger('src.feature_engineering.feature_engineering')
        logger.addHandler(test_handler)
        
        # Log completion
        self.engineer._log_completion_status(result, include_enhanced_metrics=True)
        
        # Verify key information was logged
        log_messages = [r.getMessage() for r in log_capture]
        full_log = "\n".join(log_messages)
        
        # Check basic metrics
        self.assertIn("Total records processed: 1000", full_log)
        self.assertIn("Execution time: 120.50 seconds", full_log)
        self.assertIn("Processing rate: 8.3 records/second", full_log)
        
        # Check query optimization
        self.assertIn("Bulk queries executed: 50", full_log)
        self.assertIn("Reduction factor: 10.0x", full_log)
        
        # Check validation results
        self.assertIn("No lookahead bias violations detected", full_log)
        
        # Check quality monitoring
        self.assertIn("Quality score: 0.98", full_log)
        
        # Check enhanced metrics section
        self.assertIn("ENHANCED RISK METRICS", full_log)
        self.assertIn("Feature Version: 5.0.0", full_log)
        self.assertIn("Risk-adjusted performance metrics", full_log)
        
        # Cleanup
        logger.removeHandler(test_handler)


if __name__ == "__main__":
    unittest.main()