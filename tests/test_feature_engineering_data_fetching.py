#!/usr/bin/env python3
"""
Comprehensive tests for feature engineering data fetching methods.
Tests bulk fetch operations with ML engineering best practices.
"""

import unittest
from unittest.mock import patch, Mock
from datetime import date
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.feature_engineering.feature_engineering import UnifiedFeatureEngineer


class TestDataFetchingMethods(unittest.TestCase):
    """Test data fetching methods with ML engineering best practices."""

    def setUp(self):
        """Setup test fixtures."""
        self.mock_db_patcher = patch('src.feature_engineering.feature_engineering.get_db_manager')
        self.mock_get_db = self.mock_db_patcher.start()
        self.mock_db = Mock()
        self.mock_get_db.return_value = self.mock_db
        
        self.engineer = UnifiedFeatureEngineer()
        self.test_accounts = ["ACC001", "ACC002", "ACC003"]
        self.test_dates = [date(2024, 1, 10), date(2024, 1, 11), date(2024, 1, 12)]

    def tearDown(self):
        """Cleanup test fixtures."""
        self.mock_db_patcher.stop()

    def test_get_work_items_force_rebuild(self):
        """Test work items retrieval with force rebuild."""
        # Mock database response
        mock_results = [
            {"account_id": "ACC001", "login": "12345", "feature_date": date(2024, 1, 10)},
            {"account_id": "ACC002", "login": "12346", "feature_date": date(2024, 1, 10)},
            {"account_id": "ACC001", "login": "12345", "feature_date": date(2024, 1, 11)},
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        # Test force rebuild
        work_items = self.engineer._get_work_items(
            date(2024, 1, 10), date(2024, 1, 11), force_rebuild=True
        )
        
        # Verify results
        self.assertEqual(len(work_items), 3)
        self.assertEqual(work_items[0], ("ACC001", "12345", date(2024, 1, 10)))
        
        # Verify correct query was used (should not have LEFT JOIN)
        query_call = self.mock_db.model_db.execute_query.call_args
        self.assertNotIn("LEFT JOIN", query_call[0][0])

    def test_get_work_items_incremental(self):
        """Test work items retrieval for incremental updates."""
        # Mock database response - only missing features
        mock_results = [
            {"account_id": "ACC003", "login": "12347", "feature_date": date(2024, 1, 11)},
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        # Test incremental (not force rebuild)
        work_items = self.engineer._get_work_items(
            date(2024, 1, 10), date(2024, 1, 11), force_rebuild=False
        )
        
        # Verify results
        self.assertEqual(len(work_items), 1)
        self.assertEqual(work_items[0], ("ACC003", "12347", date(2024, 1, 11)))
        
        # Verify correct query was used (should have LEFT JOIN)
        query_call = self.mock_db.model_db.execute_query.call_args
        self.assertIn("LEFT JOIN", query_call[0][0])

    def test_get_work_items_empty_result(self):
        """Test work items when no data found."""
        self.mock_db.model_db.execute_query.return_value = []
        
        work_items = self.engineer._get_work_items(
            date(2024, 1, 10), date(2024, 1, 11), force_rebuild=False
        )
        
        self.assertEqual(len(work_items), 0)

    def test_bulk_fetch_static_features_normal_case(self):
        """Test bulk fetch static features with normal data."""
        # Mock database response
        mock_results = [
            {
                "account_id": "ACC001",
                "date": date(2024, 1, 10),
                "starting_balance": 50000.0,
                "max_daily_drawdown_pct": 5.0,
                "max_drawdown_pct": 12.0,
                "profit_target_pct": 10.0,
                "max_leverage": 100,
                "is_drawdown_relative": 1,
                "liquidate_friday": 0,
                "inactivity_period": 30,
                "daily_drawdown_by_balance_equity": 1,
                "enable_consistency": 1,
            },
            {
                "account_id": "ACC002",
                "date": date(2024, 1, 10),
                "starting_balance": 100000.0,
                "max_daily_drawdown_pct": 3.0,
                "max_drawdown_pct": 8.0,
                "profit_target_pct": 8.0,
                "max_leverage": 50,
                "is_drawdown_relative": 0,
                "liquidate_friday": 1,
                "inactivity_period": 14,
                "daily_drawdown_by_balance_equity": 0,
                "enable_consistency": 0,
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        # Test bulk fetch
        result = self.engineer._bulk_fetch_static_features(
            ["ACC001", "ACC002"], [date(2024, 1, 10)]
        )
        
        # Verify results structure
        self.assertIn(("ACC001", date(2024, 1, 10)), result)
        self.assertIn(("ACC002", date(2024, 1, 10)), result)
        
        # Verify data integrity
        acc1_data = result[("ACC001", date(2024, 1, 10))]
        self.assertEqual(acc1_data["starting_balance"], 50000.0)
        self.assertEqual(acc1_data["max_leverage"], 100)
        self.assertEqual(acc1_data["is_drawdown_relative"], 1)

    def test_bulk_fetch_static_features_with_nulls(self):
        """Test bulk fetch static features with NULL values."""
        # Mock database response with NULLs
        mock_results = [
            {
                "account_id": "ACC001",
                "date": date(2024, 1, 10),
                "starting_balance": None,  # NULL
                "max_daily_drawdown_pct": 5.0,
                "max_drawdown_pct": None,  # NULL
                "profit_target_pct": 10.0,
                "max_leverage": None,  # NULL
                "is_drawdown_relative": 1,
                "liquidate_friday": 0,
                "inactivity_period": None,  # NULL
                "daily_drawdown_by_balance_equity": 1,
                "enable_consistency": 1,
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        # Test bulk fetch
        result = self.engineer._bulk_fetch_static_features(
            ["ACC001"], [date(2024, 1, 10)]
        )
        
        # Verify NULL handling - NULLs should be preserved
        acc1_data = result[("ACC001", date(2024, 1, 10))]
        self.assertIsNone(acc1_data["starting_balance"])
        self.assertIsNone(acc1_data["max_drawdown_pct"])
        self.assertIsNone(acc1_data["max_leverage"])
        self.assertIsNone(acc1_data["inactivity_period"])

    def test_bulk_fetch_static_features_empty_result(self):
        """Test bulk fetch static features with no data found."""
        self.mock_db.model_db.execute_query.return_value = []
        
        result = self.engineer._bulk_fetch_static_features(
            ["ACC001"], [date(2024, 1, 10)]
        )
        
        # Should return empty dict
        self.assertEqual(len(result), 0)
        self.assertIsInstance(result, dict)

    def test_bulk_fetch_dynamic_features_normal_case(self):
        """Test bulk fetch dynamic features with normal data."""
        mock_results = [
            {
                "account_id": "ACC001",
                "date": date(2024, 1, 10),
                "current_balance": 52000.0,
                "current_equity": 52500.0,
                "days_since_first_trade": 45,
                "active_trading_days_count": 40,
                "distance_to_profit_target": 0.04,  # 4% away
                "distance_to_max_drawdown": 0.08,   # 8% cushion
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        result = self.engineer._bulk_fetch_dynamic_features(
            ["ACC001"], [date(2024, 1, 10)]
        )
        
        acc1_data = result[("ACC001", date(2024, 1, 10))]
        self.assertEqual(acc1_data["current_balance"], 52000.0)
        self.assertEqual(acc1_data["days_since_first_trade"], 45)
        # Test that None/NULL is converted to 0 for certain fields
        self.assertIsInstance(acc1_data["days_since_first_trade"], int)

    def test_bulk_fetch_open_positions(self):
        """Test bulk fetch open positions data."""
        mock_results = [
            {
                "account_id": "ACC001",
                "trade_date": date(2024, 1, 10),
                "open_pnl": -150.0,
                "open_positions_volume": 10000.0,
            },
            {
                "account_id": "ACC002",
                "trade_date": date(2024, 1, 10),
                "open_pnl": 250.0,
                "open_positions_volume": 25000.0,
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        result = self.engineer._bulk_fetch_open_positions(
            ["ACC001", "ACC002", "ACC003"], [date(2024, 1, 10)]
        )
        
        # Check data is correctly mapped
        self.assertEqual(result[("ACC001", date(2024, 1, 10))]["open_pnl"], -150.0)
        self.assertEqual(result[("ACC002", date(2024, 1, 10))]["open_pnl"], 250.0)
        
        # ACC003 not in results - should not be in dictionary
        self.assertNotIn(("ACC003", date(2024, 1, 10)), result)

    def test_bulk_fetch_performance_data(self):
        """Test bulk fetch historical performance data."""
        # Create mock DataFrame response
        mock_df = pd.DataFrame({
            "account_id": ["ACC001", "ACC001", "ACC001", "ACC002", "ACC002"],
            "date": [
                date(2024, 1, 10),
                date(2024, 1, 9),
                date(2024, 1, 8),
                date(2024, 1, 10),
                date(2024, 1, 9),
            ],
            "net_profit": [100.0, -50.0, 200.0, 300.0, 150.0]
        })
        self.mock_db.model_db.execute_query_df.return_value = mock_df
        
        result = self.engineer._bulk_fetch_performance_data(
            ["ACC001", "ACC002"], date(2024, 1, 8), date(2024, 1, 10)
        )
        
        # Verify structure
        self.assertIn("ACC001", result)
        self.assertIn("ACC002", result)
        
        # Verify data is sorted by date descending
        acc1_df = result["ACC001"]
        self.assertEqual(len(acc1_df), 3)
        self.assertEqual(acc1_df.iloc[0]["date"], date(2024, 1, 10))
        self.assertEqual(acc1_df.iloc[0]["net_profit"], 100.0)

    def test_bulk_fetch_performance_data_empty(self):
        """Test bulk fetch performance data with no results."""
        # Empty DataFrame
        mock_df = pd.DataFrame()
        self.mock_db.model_db.execute_query_df.return_value = mock_df
        
        result = self.engineer._bulk_fetch_performance_data(
            ["ACC001"], date(2024, 1, 8), date(2024, 1, 10)
        )
        
        # Should return empty dict
        self.assertEqual(len(result), 0)

    def test_bulk_fetch_trades_data(self):
        """Test bulk fetch trades data for behavioral features."""
        mock_df = pd.DataFrame({
            "account_id": ["ACC001", "ACC001", "ACC002"],
            "trade_date": [date(2024, 1, 10), date(2024, 1, 9), date(2024, 1, 10)],
            "side": ["buy", "sell", "buy"],
            "lots": [0.1, 0.2, 0.5],
            "volume_usd": [10000.0, 20000.0, 50000.0],
            "profit": [50.0, -30.0, 120.0],
            "duration": [3600, 7200, 1800],  # seconds
            "stop_loss": [1.1000, 0, 1.2000],
            "take_profit": [1.1200, 1.1500, 0],
            "std_symbol": ["EURUSD", "EURUSD", "GBPUSD"],
        })
        self.mock_db.model_db.execute_query_df.return_value = mock_df
        
        result = self.engineer._bulk_fetch_trades_data(
            ["ACC001", "ACC002"], date(2024, 1, 5), date(2024, 1, 10)
        )
        
        # Verify grouping
        self.assertIn("ACC001", result)
        self.assertIn("ACC002", result)
        self.assertEqual(len(result["ACC001"]), 2)
        self.assertEqual(len(result["ACC002"]), 1)

    def test_bulk_fetch_market_data(self):
        """Test bulk fetch market regime data."""
        mock_results = [
            {
                "date": date(2024, 1, 10),
                "market_news": '{"events": []}',
                "instruments": '{"data": {"VIX": {"last_price": 15.5}}}',
                "country_economic_indicators": '{"fed_funds_rate_effective": 5.25}',
                "news_analysis": '{"sentiment_summary": {"average_score": 0.15}}',
                "summary": '{"key_metrics": {"volatility_regime": "COMPRESSED", "liquidity_state": "normal"}}',
                "ingestion_timestamp": "2024-01-10T12:00:00Z"
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        result = self.engineer._bulk_fetch_market_data([date(2024, 1, 10)])
        
        # Verify parsing
        self.assertIn(date(2024, 1, 10), result)
        market_features = result[date(2024, 1, 10)]
        
        # Check parsed features
        self.assertEqual(market_features["market_sentiment_score"], 0.15)
        self.assertEqual(market_features["vix_level"], 15.5)
        self.assertEqual(market_features["fed_funds_rate"], 5.25)
        self.assertEqual(market_features["market_volatility_regime"], "COMPRESSED")

    def test_bulk_fetch_market_data_parse_errors(self):
        """Test market data parsing with malformed JSON."""
        mock_results = [
            {
                "date": date(2024, 1, 10),
                "market_news": "INVALID JSON",  # Invalid
                "instruments": None,  # NULL
                "country_economic_indicators": '{}',  # Empty
                "news_analysis": '{"wrong_key": "value"}',  # Missing expected keys
                "summary": '{"key_metrics": {}}',  # Missing values
                "ingestion_timestamp": "2024-01-10T12:00:00Z"
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        result = self.engineer._bulk_fetch_market_data([date(2024, 1, 10)])
        
        # Should handle gracefully with defaults
        self.assertIn(date(2024, 1, 10), result)
        market_features = result[date(2024, 1, 10)]
        
        # Check default values are used
        self.assertEqual(market_features["market_sentiment_score"], 0.0)
        self.assertEqual(market_features["vix_level"], 15.0)  # Default
        self.assertEqual(market_features["fed_funds_rate"], 5.0)  # Default
        self.assertEqual(market_features["market_volatility_regime"], "BALANCED")  # Default

    def test_bulk_fetch_enhanced_metrics(self):
        """Test bulk fetch enhanced metrics with all risk factors."""
        mock_results = [
            {
                "account_id": "ACC001",
                "date": date(2024, 1, 10),
                "net_profit": 150.0,
                "gross_profit": 300.0,
                "gross_loss": -150.0,
                "num_trades": 10,
                "winning_trades": 6,
                "losing_trades": 4,
                "win_rate": 60.0,
                "profit_factor": 2.0,
                "gain_to_pain": 1.8,
                "daily_sharpe": 1.5,
                "daily_sortino": 1.8,
                "profit_perc_10": -50.0,
                "profit_perc_25": -10.0,
                "median_profit": 15.0,
                "profit_perc_75": 40.0,
                "profit_perc_90": 100.0,
                "mean_drawdown": -5.0,
                "max_drawdown": -12.0,
                "total_volume": 100000.0,
                "mean_duration": 3.5,
                "plan_id": 100,
                "status": 1,
                "phase": 2,
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        result = self.engineer._bulk_fetch_enhanced_metrics(
            ["ACC001"], [date(2024, 1, 10)]
        )
        
        # Verify all metrics are captured
        key = ("ACC001", date(2024, 1, 10))
        self.assertIn(key, result)
        metrics = result[key]
        
        # Check key risk metrics
        self.assertEqual(metrics["gain_to_pain"], 1.8)
        self.assertEqual(metrics["daily_sharpe"], 1.5)
        self.assertEqual(metrics["daily_sortino"], 1.8)
        self.assertEqual(metrics["profit_perc_10"], -50.0)
        self.assertEqual(metrics["profit_perc_90"], 100.0)

    def test_bulk_fetch_alltime_metrics(self):
        """Test bulk fetch all-time metrics for baseline comparison."""
        mock_results = [
            {
                "account_id": "ACC001",
                "lifetime_net_profit": 5000.0,
                "lifetime_num_trades": 500,
                "lifetime_win_rate": 58.0,
                "lifetime_profit_factor": 1.6,
                "lifetime_sharpe": 1.2,
                "lifetime_sortino": 1.4,
                "lifetime_gain_to_pain": 1.5,
                "lifetime_daily_sharpe": 1.1,
                "lifetime_daily_sortino": 1.3,
                "lifetime_mean_duration": 4.2,
                "lifetime_mean_tp_vs_sl": 1.8,
                "lifetime_mean_trades_per_day": 2.5,
                "lifetime_num_traded_symbols": 15,
                "days_since_first_trade": 180,
                "num_trades": 500,
                "plan_id": 100,
                "trader_id": "TRADER001",
                "status": 1,
                "phase": 2,
            }
        ]
        self.mock_db.model_db.execute_query.return_value = mock_results
        
        result = self.engineer._bulk_fetch_alltime_metrics(["ACC001"])
        
        # Verify structure
        self.assertIn("ACC001", result)
        metrics = result["ACC001"]
        
        # Check key lifetime metrics
        self.assertEqual(metrics["lifetime_net_profit"], 5000.0)
        self.assertEqual(metrics["lifetime_win_rate"], 58.0)
        self.assertEqual(metrics["days_since_first_trade"], 180)

    def test_query_stats_tracking(self):
        """Test that query statistics are properly tracked."""
        # Mock some responses
        self.mock_db.model_db.execute_query.return_value = []
        
        # Reset query stats
        self.engineer.query_stats = {
            "total_queries": 0,
            "bulk_queries": 0,
            "time_saved": 0,
            "query_times": [],
        }
        
        # Execute several bulk fetches
        self.engineer._bulk_fetch_static_features(["ACC001", "ACC002"], [date(2024, 1, 10)])
        self.engineer._bulk_fetch_dynamic_features(["ACC001"], [date(2024, 1, 10)])
        
        # Verify stats are updated
        self.assertEqual(self.engineer.query_stats["bulk_queries"], 2)
        # Each bulk query represents multiple individual queries
        self.assertGreater(self.engineer.query_stats["total_queries"], 2)

    def test_error_handling_and_logging(self):
        """Test error handling in bulk fetch methods."""
        # Simulate database error
        self.mock_db.model_db.execute_query.side_effect = Exception("Database connection failed")
        
        # Should raise and be handled by caller
        with self.assertRaises(Exception) as context:
            self.engineer._bulk_fetch_static_features(["ACC001"], [date(2024, 1, 10)])
        
        self.assertIn("Database connection failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()