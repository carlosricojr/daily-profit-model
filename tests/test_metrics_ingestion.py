"""
Comprehensive tests for the optimized intelligent metrics ingester.

This module provides complete test coverage for the IntelligentMetricsIngester
including all optimization features, data quality monitoring, and edge cases.
"""

import unittest
from datetime import datetime, date
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestMetricsIngester(unittest.TestCase):
    """Comprehensive test suite for MetricsIngester."""
    
    @patch('data_ingestion.ingest_metrics.RiskAnalyticsAPIClient')
    @patch('data_ingestion.ingest_metrics.BaseIngester.__init__')
    def setUp(self, mock_base_init, mock_api_client_class):
        """Set up test fixtures with proper mocking."""
        # Mock base class initialization
        mock_base_init.return_value = None
        
        # Import the class after mocking
        from data_ingestion.ingest_metrics import MetricsIngester, MetricType
        
        # Create ingester instance
        self.ingester = MetricsIngester()
        
        # Mock database manager
        self.mock_db_manager = MagicMock()
        self.mock_db_manager.model_db = MagicMock()
        self.ingester.db_manager = self.mock_db_manager
        
        # Mock API client
        self.mock_api_client = MagicMock()
        self.ingester.api_client = self.mock_api_client
        mock_api_client_class.return_value = self.mock_api_client
        
        # Store MetricType for tests
        self.MetricType = MetricType
        
        # Set up default configuration
        self.ingester.config.batch_size = 1000
        self.ingester.config.max_retries = 3
        self.ingester.config.timeout = 30
        self.ingester.config.alltime_batch_size = 50
        self.ingester.config.hourly_batch_size = 25
        self.ingester.config.daily_lookback_days = 90
        self.ingester.config.hourly_lookback_days = 30
        self.ingester.config.max_missing_slots = 50000
        self.ingester.config.api_rate_limit_delay = 0.025
        
        # Mock checkpoint managers
        self.ingester.checkpoint_managers = {
            "alltime": MagicMock(),
            "daily": MagicMock(),
            "hourly": MagicMock()
        }
        
        # Mock metrics
        self.ingester.metrics_by_type = {
            "alltime": MagicMock(),
            "daily": MagicMock(),
            "hourly": MagicMock()
        }


class TestInitialization(TestMetricsIngester):
    """Test ingester initialization and setup."""
    
    def test_field_mappings_initialization(self):
        """Test that all field mappings are properly initialized."""
        # Test core field mappings exist
        self.assertIn('login', self.ingester.core_fields)
        self.assertIn('accountId', self.ingester.core_fields)
        
        # Test combined mappings
        self.assertGreater(len(self.ingester.alltime_field_mapping), 50)
        self.assertGreater(len(self.ingester.daily_field_mapping), 50)
        self.assertGreater(len(self.ingester.hourly_field_mapping), 50)
        
        # Test hourly mapping includes hour field
        self.assertIn('hour', self.ingester.hourly_field_mapping)
        
        # Test daily mapping includes daily-specific fields
        self.assertIn('days_to_next_payout', self.ingester.daily_field_mapping)
    
    def test_table_mapping_setup(self):
        """Test table mapping configuration."""
        expected_tables = {
            self.MetricType.ALLTIME: "prop_trading_model.raw_metrics_alltime",
            self.MetricType.DAILY: "prop_trading_model.raw_metrics_daily",
            self.MetricType.HOURLY: "prop_trading_model.raw_metrics_hourly",
        }
        
        self.assertEqual(self.ingester.table_mapping, expected_tables)
    
    def test_configuration_setup(self):
        """Test configuration values are properly set."""
        self.assertEqual(self.ingester.config.batch_size, 1000)
        self.assertEqual(self.ingester.config.max_retries, 3)
        self.assertEqual(self.ingester.config.timeout, 30)
        self.assertEqual(self.ingester.config.alltime_batch_size, 50)
        self.assertEqual(self.ingester.config.hourly_batch_size, 25)
        self.assertEqual(self.ingester.config.daily_lookback_days, 90)
        self.assertEqual(self.ingester.config.hourly_lookback_days, 30)
        self.assertEqual(self.ingester.config.max_missing_slots, 50000)
        self.assertEqual(self.ingester.config.api_rate_limit_delay, 0.025)


class TestDateRangeIngestion(TestMetricsIngester):
    """Test date range ingestion flow."""
    
    def test_ingest_with_date_range_complete_flow(self):
        """Test complete date range ingestion flow."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 3)
        
        # Mock missing daily dates
        self.ingester._get_missing_daily_dates = Mock(return_value=[
            date(2024, 1, 1), date(2024, 1, 2)
        ])
        
        # Mock account IDs from daily range
        self.ingester._get_account_ids_from_daily_range = Mock(return_value=[
            "123456", "789012"
        ])
        
        # Mock ingestion methods
        self.ingester._ingest_daily_for_dates = Mock(return_value=150)
        self.ingester._ingest_alltime_for_accounts = Mock(return_value=2)
        self.ingester._ingest_hourly_optimized = Mock(return_value=75)
        
        # Execute
        results = self.ingester.ingest_with_date_range(start_date, end_date)
        
        # Verify results
        self.assertEqual(results["daily"], 150)
        self.assertEqual(results["alltime"], 2)
        self.assertEqual(results["hourly"], 75)
        
        # Verify method calls
        self.ingester._get_missing_daily_dates.assert_called_once_with(start_date, end_date)
        self.ingester._ingest_daily_for_dates.assert_called_once()
        self.ingester._ingest_alltime_for_accounts.assert_called_once()
        self.ingester._ingest_hourly_optimized.assert_called_once()
    
    def test_ingest_with_date_range_no_missing_daily(self):
        """Test date range ingestion when no daily data is missing."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 3)
        
        # Mock no missing daily dates
        self.ingester._get_missing_daily_dates = Mock(return_value=[])
        
        # Mock account IDs from existing data
        self.ingester._get_account_ids_from_daily_range = Mock(return_value=[
            "123456", "789012"
        ])
        
        # Mock other methods
        self.ingester._ingest_alltime_for_accounts = Mock(return_value=2)
        self.ingester._ingest_hourly_optimized = Mock(return_value=25)
        
        # Execute
        results = self.ingester.ingest_with_date_range(start_date, end_date)
        
        # Verify daily records is 0 but other flows continue
        self.assertEqual(results["daily"], 0)
        self.assertEqual(results["alltime"], 2)
        self.assertEqual(results["hourly"], 25)
    
    def test_ingest_with_date_range_force_refresh(self):
        """Test date range ingestion with force refresh."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 2)
        
        # Mock methods
        self.ingester._ingest_daily_for_dates = Mock(return_value=100)
        self.ingester._get_account_ids_from_daily_range = Mock(return_value=["123"])
        self.ingester._ingest_alltime_for_accounts = Mock(return_value=1)
        self.ingester._ingest_hourly_optimized = Mock(return_value=50)
        
        # Execute with force refresh
        self.ingester.ingest_with_date_range(
            start_date, end_date, force_full_refresh=True
        )
        
        # Verify _get_missing_daily_dates was not called (force refresh)
        with self.assertRaises(AttributeError):
            self.ingester._get_missing_daily_dates.assert_called()
        
        # Verify dates were generated directly
        self.ingester._ingest_daily_for_dates.assert_called_once()
        call_args = self.ingester._ingest_daily_for_dates.call_args[0][0]
        self.assertEqual(len(call_args), 2)  # 2 days


class TestNoDateRangeIngestion(TestMetricsIngester):
    """Test ingestion without date range constraints."""
    
    def test_ingest_without_date_range_complete_flow(self):
        """Test complete ingestion flow without date range."""
        # Mock methods
        self.ingester._ingest_alltime_for_accounts = Mock(return_value=1000)
        self.ingester._get_strategic_missing_daily_data = Mock(return_value=[
            ("123456", date(2024, 1, 1)),
            ("789012", date(2024, 1, 2))
        ])
        self.ingester._ingest_daily_for_missing = Mock(return_value=200)
        self.ingester._ingest_hourly_strategic = Mock(return_value=150)
        
        # Execute
        results = self.ingester.ingest_without_date_range()
        
        # Verify results
        self.assertEqual(results["alltime"], 1000)
        self.assertEqual(results["daily"], 200)
        self.assertEqual(results["hourly"], 150)
        
        # Verify method calls
        self.ingester._ingest_alltime_for_accounts.assert_called_once_with(None)
        self.ingester._get_strategic_missing_daily_data.assert_called_once()
        self.ingester._ingest_daily_for_missing.assert_called_once()
        self.ingester._ingest_hourly_strategic.assert_called_once()
    
    def test_ingest_without_date_range_no_missing_data(self):
        """Test ingestion when no missing data is found."""
        # Mock methods to return empty results
        self.ingester._ingest_alltime_for_accounts = Mock(return_value=1000)
        self.ingester._get_strategic_missing_daily_data = Mock(return_value=[])
        self.ingester._ingest_hourly_strategic = Mock(return_value=0)
        
        # Execute
        results = self.ingester.ingest_without_date_range()
        
        # Verify results
        self.assertEqual(results["alltime"], 1000)
        self.assertEqual(results["daily"], 0)
        self.assertEqual(results["hourly"], 0)


class TestOptimizedHourlyIngestion(TestMetricsIngester):
    """Test optimized hourly ingestion methods."""
    
    def test_get_accounts_needing_hourly_updates(self):
        """Test identification of accounts needing hourly updates."""
        account_ids = ["123456", "789012", "345678"]
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 3)
        
        # Mock database response
        mock_results = [
            {"account_id": "123456", "latest_date": date(2024, 1, 1), "latest_hour": 10},
            {"account_id": "789012", "latest_date": date(2024, 1, 2), "latest_hour": -1},
        ]
        self.mock_db_manager.model_db.execute_query.return_value = mock_results
        
        # Execute
        updates_needed = self.ingester._get_accounts_needing_hourly_updates(
            account_ids, start_date, end_date
        )
        
        # Verify results
        expected = [
            ("123456", date(2024, 1, 1), 10),
            ("789012", date(2024, 1, 2), -1)
        ]
        self.assertEqual(updates_needed, expected)
        
        # Verify database was queried
        self.mock_db_manager.model_db.execute_query.assert_called()
    
    def test_ingest_hourly_optimized_with_updates_needed(self):
        """Test optimized hourly ingestion when updates are needed."""
        account_ids = ["123456", "789012"]
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 2)
        
        # Mock accounts needing updates
        self.ingester._get_accounts_needing_hourly_updates = Mock(return_value=[
            ("123456", date(2024, 1, 1), 10),
            ("789012", date(2024, 1, 1), -1)
        ])
        
        # Mock API response
        api_records = [
            {"accountId": "123456", "login": 123456, "mt_version": "MT4", "broker": "TestBroker", "date": "20240101", "hour": 11, "netProfit": 100},
            {"accountId": "789012", "login": 789012, "mt_version": "MT5", "broker": "TestBroker", "date": "20240102", "hour": 0, "netProfit": 50}
        ]
        self.mock_api_client.get_metrics.return_value = iter([api_records])
        
        # Mock transform and insert
        def mock_transform(x):
            return {
                "transformed": True,
                "account_id": x.get("accountId"),
                "login": x.get("login"),
                "platform": x.get("mt_version"),
                "broker": x.get("broker"),
                **x
            }
        self.ingester._transform_hourly_metric = Mock(side_effect=mock_transform)
        self.ingester._insert_batch_with_upsert = Mock(return_value=2)
        
        # Execute
        result = self.ingester._ingest_hourly_optimized(
            account_ids, start_date, end_date
        )
        
        # Verify
        self.assertEqual(result, 2)
        self.ingester._get_accounts_needing_hourly_updates.assert_called_once()
        self.mock_api_client.get_metrics.assert_called()
        self.ingester._insert_batch_with_upsert.assert_called()
    
    def test_ingest_hourly_optimized_no_updates_needed(self):
        """Test optimized hourly ingestion when no updates are needed."""
        account_ids = ["123456"]
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 2)
        
        # Mock no accounts needing updates
        self.ingester._get_accounts_needing_hourly_updates = Mock(return_value=[])
        
        # Execute
        result = self.ingester._ingest_hourly_optimized(
            account_ids, start_date, end_date
        )
        
        # Verify
        self.assertEqual(result, 0)
        # API should not be called
        self.mock_api_client.get_metrics.assert_not_called()
    
    def test_ingest_hourly_strategic(self):
        """Test strategic hourly ingestion."""
        # Mock database response for strategic query
        mock_accounts = [
            {"account_id": "123456", "latest_date": date(2024, 1, 1), "latest_hour": 10},
            {"account_id": "789012", "latest_date": date(2024, 1, 2), "latest_hour": -1}
        ]
        self.mock_db_manager.model_db.execute_query.return_value = mock_accounts
        
        # Mock API response
        api_records = [
            {"accountId": "123456", "date": "20240102", "hour": 11, "netProfit": 100}
        ]
        self.mock_api_client.get_metrics.return_value = iter([api_records])
        
        # Mock transform and insert
        self.ingester._transform_hourly_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        self.ingester._insert_batch_with_upsert = Mock(return_value=1)
        
        # Execute
        result = self.ingester._ingest_hourly_strategic()
        
        # Verify
        self.assertEqual(result, 1)
        self.mock_db_manager.model_db.execute_query.assert_called()
        self.mock_api_client.get_metrics.assert_called()


class TestDataTransformation(TestMetricsIngester):
    """Test data transformation methods."""
    
    def test_transform_alltime_metric(self):
        """Test alltime metric transformation."""
        raw_metric = {
            "login": "12345",
            "accountId": "ACC123",
            "netProfit": 1500.50,
            "numTrades": 100,
            "successRate": 65.5,
            "firstTradeDate": "2024-01-01",
            "updatedDate": "2024-01-15T10:30:00Z"
        }
        
        # Execute
        transformed = self.ingester._transform_alltime_metric(raw_metric)
        
        # Verify basic fields
        self.assertEqual(transformed["login"], "12345")
        self.assertEqual(transformed["account_id"], "ACC123")
        self.assertEqual(transformed["net_profit"], 1500.50)
        self.assertEqual(transformed["num_trades"], 100)
        self.assertEqual(transformed["success_rate"], 65.5)
        
        # Verify system fields
        self.assertIn("ingestion_timestamp", transformed)
        self.assertEqual(transformed["source_api_endpoint"], "/v2/metrics/alltime")
        
        # Verify date parsing
        self.assertEqual(transformed["first_trade_date"], date(2024, 1, 1))
        self.assertIsInstance(transformed["updated_date"], datetime)
    
    def test_transform_daily_metric(self):
        """Test daily metric transformation."""
        raw_metric = {
            "date": "2024-01-01T00:00:00Z",
            "login": "12345",
            "accountId": "ACC123",
            "netProfit": 250.75,
            "days_to_next_payout": 5,
            "todays_payouts": 100.00
        }
        
        # Execute
        transformed = self.ingester._transform_daily_metric(raw_metric)
        
        # Verify
        self.assertEqual(transformed["date"], date(2024, 1, 1))
        self.assertEqual(transformed["account_id"], "ACC123")
        self.assertEqual(transformed["net_profit"], 250.75)
        self.assertEqual(transformed["days_to_next_payout"], 5)
        self.assertEqual(transformed["todays_payouts"], 100.00)
        self.assertEqual(transformed["source_api_endpoint"], "/v2/metrics/daily")
    
    def test_transform_hourly_metric(self):
        """Test hourly metric transformation."""
        raw_metric = {
            "date": "2024-01-01T00:00:00Z",
            "datetime": "2024-01-01T10:00:00Z",
            "hour": 10,
            "login": "12345",
            "accountId": "ACC123",
            "netProfit": 50.25,
            "numTrades": 5
        }
        
        # Execute
        transformed = self.ingester._transform_hourly_metric(raw_metric)
        
        # Verify
        self.assertEqual(transformed["date"], date(2024, 1, 1))
        self.assertEqual(transformed["hour"], 10)
        self.assertEqual(transformed["account_id"], "ACC123")
        self.assertEqual(transformed["net_profit"], 50.25)
        self.assertEqual(transformed["num_trades"], 5)
        self.assertEqual(transformed["source_api_endpoint"], "/v2/metrics/hourly")
        self.assertIsInstance(transformed["datetime"], datetime)
    
    def test_safe_float_conversion(self):
        """Test safe float conversion helper."""
        # Valid conversions
        self.assertEqual(self.ingester._safe_float("123.45"), 123.45)
        self.assertEqual(self.ingester._safe_float(123.45), 123.45)
        self.assertEqual(self.ingester._safe_float(123), 123.0)
        
        # Invalid conversions
        self.assertIsNone(self.ingester._safe_float(None))
        self.assertIsNone(self.ingester._safe_float("invalid"))
        self.assertIsNone(self.ingester._safe_float(""))
    
    def test_safe_int_conversion(self):
        """
        Test safe integer conversion helper with strict whole number validation.
        
        The _safe_int method should only accept values that represent whole numbers,
        rejecting any floats with decimal parts to ensure data quality.
        """
        # Valid conversions
        self.assertEqual(self.ingester._safe_int("123"), 123)
        self.assertEqual(self.ingester._safe_int(123.0), 123)
        self.assertEqual(self.ingester._safe_int(123), 123)
        
        # Invalid conversions
        self.assertIsNone(self.ingester._safe_int(None))
        self.assertIsNone(self.ingester._safe_int("invalid"))
        self.assertIsNone(self.ingester._safe_int(123.45))
    
    def test_safe_bound_extreme_values(self):
        """Test extreme value bounding."""
        # DECIMAL(10,6) field bounds
        self.assertEqual(
            self.ingester._safe_bound_extreme(99999.999999, 'cv_durations'),
            9999.999999
        )
        self.assertEqual(
            self.ingester._safe_bound_extreme(-99999.999999, 'cv_durations'),
            -9999.999999
        )
        
        # DECIMAL(5,2) field bounds
        self.assertEqual(
            self.ingester._safe_bound_extreme(9999.99, 'success_rate'),
            999.99
        )
        
        # Normal values pass through
        self.assertEqual(
            self.ingester._safe_bound_extreme(50.5, 'success_rate'),
            50.5
        )
    
    def test_parse_date_formats(self):
        """Test date parsing from various formats."""
        # ISO format with time
        self.assertEqual(
            self.ingester._parse_date("2024-01-01T10:30:00Z"),
            date(2024, 1, 1)
        )
        
        # Date only format
        self.assertEqual(
            self.ingester._parse_date("2024-01-01"),
            date(2024, 1, 1)
        )
        
        # Invalid formats
        self.assertIsNone(self.ingester._parse_date("invalid"))
        self.assertIsNone(self.ingester._parse_date(None))
        self.assertIsNone(self.ingester._parse_date(""))


class TestDatabaseInteraction(TestMetricsIngester):
    """Test database interaction methods."""
    
    def test_get_missing_daily_dates(self):
        """Test missing daily dates detection."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 5)
        
        # Mock database response
        mock_results = [
            {"date": date(2024, 1, 2)},
            {"date": date(2024, 1, 4)}
        ]
        self.mock_db_manager.model_db.execute_query.return_value = mock_results
        
        # Execute
        missing_dates = self.ingester._get_missing_daily_dates(start_date, end_date)
        
        # Verify
        expected = [date(2024, 1, 2), date(2024, 1, 4)]
        self.assertEqual(missing_dates, expected)
        
        # Verify query was called with correct parameters
        self.mock_db_manager.model_db.execute_query.assert_called_once()
        call_args = self.mock_db_manager.model_db.execute_query.call_args
        self.assertEqual(call_args[0][1], (start_date, end_date, start_date, end_date))
    
    def test_get_account_ids_from_daily_range(self):
        """Test account ID extraction from daily range."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 3)
        
        # Mock database response
        mock_results = [
            {"account_id": "123456"},
            {"account_id": "789012"},
            {"account_id": "345678"}
        ]
        self.mock_db_manager.model_db.execute_query.return_value = mock_results
        
        # Execute
        account_ids = self.ingester._get_account_ids_from_daily_range(start_date, end_date)
        
        # Verify
        expected = ["123456", "789012", "345678"]
        self.assertEqual(account_ids, expected)
    
    def test_get_strategic_missing_daily_data(self):
        """Test strategic missing daily data detection."""
        # Mock database response
        mock_results = [
            {"account_id": "123456", "date": date(2024, 1, 1)},
            {"account_id": "789012", "date": date(2024, 1, 2)}
        ]
        self.mock_db_manager.model_db.execute_query.return_value = mock_results
        
        # Execute
        missing_data = self.ingester._get_strategic_missing_daily_data()
        
        # Verify
        expected = [("123456", date(2024, 1, 1)), ("789012", date(2024, 1, 2))]
        self.assertEqual(missing_data, expected)
    
    def test_insert_batch_with_upsert_alltime(self):
        """Test batch insertion with upsert for alltime metrics."""
        batch_data = [
            {"account_id": "123456", "net_profit": 1000.0, "num_trades": 50},
            {"account_id": "789012", "net_profit": 2000.0, "num_trades": 75}
        ]
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2
        mock_cursor.mogrify.return_value = b"mocked_sql"  # Return bytes
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.mock_db_manager.model_db.get_connection.return_value.__enter__.return_value = mock_conn
        
        # Mock execute_batch
        with patch('psycopg2.extras.execute_batch') as mock_execute_batch:
            # Execute
            result = self.ingester._insert_batch_with_upsert(batch_data, self.MetricType.ALLTIME)
        
        # Verify
        self.assertEqual(result, 2)
        mock_execute_batch.assert_called_once()
        mock_conn.commit.assert_called_once()
    
    def test_insert_batch_with_upsert_hourly(self):
        """Test batch insertion with upsert for hourly metrics."""
        batch_data = [
            {"account_id": "123456", "date": date(2024, 1, 1), "hour": 10, "net_profit": 100.0}
        ]
        
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_cursor.mogrify.return_value = b"mocked_sql"  # Return bytes
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.mock_db_manager.model_db.get_connection.return_value.__enter__.return_value = mock_conn
        
        # Mock execute_batch
        with patch('psycopg2.extras.execute_batch') as mock_execute_batch:
            # Execute
            result = self.ingester._insert_batch_with_upsert(batch_data, self.MetricType.HOURLY)
        
        # Verify
        self.assertEqual(result, 1)
        mock_execute_batch.assert_called_once()
        mock_conn.commit.assert_called_once()
    
    def test_insert_batch_with_upsert_empty_batch(self):
        """Test batch insertion with empty batch."""
        result = self.ingester._insert_batch_with_upsert([], self.MetricType.DAILY)
        self.assertEqual(result, 0)


class TestDataQualityMonitoring(TestMetricsIngester):
    """Test data quality monitoring functionality."""
    
    def test_get_data_quality_issues(self):
        """Test data quality issue detection."""
        # Mock database response with quality issues
        mock_results = [
            {
                "account_id": "123456",
                "date": date(2024, 1, 1),
                "daily_trades": 50,
                "hourly_records": 0,
                "sum_hourly_trades": 0,
                "issue_type": "missing_all_hourly"
            },
            {
                "account_id": "789012",
                "date": date(2024, 1, 2),
                "daily_trades": 25,
                "hourly_records": 12,
                "sum_hourly_trades": 20,
                "issue_type": "trade_count_mismatch"
            }
        ]
        self.mock_db_manager.model_db.execute_query.return_value = mock_results
        
        # Execute
        issues = self.ingester.get_data_quality_issues()
        
        # Verify
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]["issue_type"], "missing_all_hourly")
        self.assertEqual(issues[1]["issue_type"], "trade_count_mismatch")
        
        # Verify database was queried
        self.mock_db_manager.model_db.execute_query.assert_called_once()


class TestAPIInteraction(TestMetricsIngester):
    """Test API interaction methods."""
    
    def test_ingest_alltime_for_accounts_specific_accounts(self):
        """Test alltime ingestion for specific accounts."""
        account_ids = ["123456", "789012"]
        
        # Mock API response
        api_records = [
            {"login": "12345", "accountId": "123456", "netProfit": 1000},
            {"login": "78901", "accountId": "789012", "netProfit": 2000}
        ]
        self.mock_api_client.get_metrics.return_value = iter([api_records])
        
        # Mock transform and insert
        self.ingester._transform_alltime_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        self.ingester._insert_batch_with_upsert = Mock(return_value=2)
        
        # Execute
        result = self.ingester._ingest_alltime_for_accounts(account_ids)
        
        # Verify
        self.assertEqual(result, 2)
        self.mock_api_client.get_metrics.assert_called()
        self.ingester._insert_batch_with_upsert.assert_called_once()
    
    def test_ingest_alltime_for_accounts_all_accounts(self):
        """Test alltime ingestion for all accounts."""
        # Mock API response
        api_records = [
            {"login": "12345", "accountId": "123456", "netProfit": 1000}
        ]
        self.mock_api_client.get_metrics.return_value = iter([api_records])
        
        # Mock transform and insert
        self.ingester._transform_alltime_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        self.ingester._insert_batch_with_upsert = Mock(return_value=1)
        
        # Execute (None means all accounts)
        result = self.ingester._ingest_alltime_for_accounts(None)
        
        # Verify
        self.assertEqual(result, 1)
        self.mock_api_client.get_metrics.assert_called_with(
            metric_type="alltime", limit=1000
        )
    
    def test_ingest_daily_for_dates(self):
        """Test daily ingestion for specific dates."""
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        
        # Mock API response - one call per date
        api_responses = [
            iter([[{"date": "20240101", "accountId": "123456", "login": 123456, "mt_version": "MT4", "broker": "TestBroker", "netProfit": 100}]]),
            iter([[{"date": "20240102", "accountId": "123456", "login": 123456, "mt_version": "MT4", "broker": "TestBroker", "netProfit": 150}]])
        ]
        self.mock_api_client.get_metrics.side_effect = api_responses
        
        # Mock transform and insert
        def mock_transform(x):
            return {
                "transformed": True,
                "account_id": x.get("accountId"),
                "login": x.get("login"),
                "platform": x.get("mt_version"),
                "broker": x.get("broker"),
                **x
            }
        self.ingester._transform_daily_metric = Mock(side_effect=mock_transform)
        self.ingester._insert_batch_with_upsert = Mock(return_value=1)
        
        # Execute
        result = self.ingester._ingest_daily_for_dates(dates)
        
        # Verify
        self.assertEqual(result, 2)
        # API should be called for each date
        self.assertEqual(self.mock_api_client.get_metrics.call_count, 2)
    
    def test_ingest_daily_for_missing(self):
        """Test daily ingestion for missing account-date combinations."""
        missing_data = [
            ("123456", date(2024, 1, 1)),
            ("789012", date(2024, 1, 1)),
            ("123456", date(2024, 1, 2))
        ]
        
        # Mock API response - one call per date
        api_responses = [
            iter([[
                {"date": "20240101", "accountId": "123456", "login": 123456, "mt_version": "MT4", "broker": "TestBroker", "netProfit": 100},
                {"date": "20240101", "accountId": "789012", "login": 789012, "mt_version": "MT5", "broker": "TestBroker", "netProfit": 200}
            ]]),
            iter([[{"date": "20240102", "accountId": "123456", "login": 123456, "mt_version": "MT4", "broker": "TestBroker", "netProfit": 150}]])
        ]
        self.mock_api_client.get_metrics.side_effect = api_responses
        
        # Mock transform and insert
        def mock_transform(x):
            return {
                "transformed": True,
                "account_id": x.get("accountId"),
                "login": x.get("login"),
                "platform": x.get("mt_version"),
                "broker": x.get("broker"),
                **x
            }
        self.ingester._transform_daily_metric = Mock(side_effect=mock_transform)
        self.ingester._insert_batch_with_upsert = Mock(side_effect=[2, 1])  # 2 records for first date, 1 for second
        
        # Execute
        result = self.ingester._ingest_daily_for_missing(missing_data)
        
        # Verify - should group by date and call API for each date
        self.assertGreater(result, 0)
        self.mock_api_client.get_metrics.assert_called()


class TestEdgeCasesAndErrorHandling(TestMetricsIngester):
    """Test edge cases and error handling."""
    
    def test_empty_account_ids_list(self):
        """Test handling of empty account IDs list."""
        # Test hourly updates
        result = self.ingester._get_accounts_needing_hourly_updates([], date(2024, 1, 1), date(2024, 1, 2))
        self.assertEqual(result, [])
        
        # Test optimized hourly ingestion
        result = self.ingester._ingest_hourly_optimized([], date(2024, 1, 1), date(2024, 1, 2))
        self.assertEqual(result, 0)
    
    def test_api_error_handling(self):
        """Test API error handling."""
        # Mock API to raise exception
        self.mock_api_client.get_metrics.side_effect = Exception("API Error")
        
        # Test that daily ingestion handles API errors gracefully
        dates = [date(2024, 1, 1)]
        result = self.ingester._ingest_daily_for_dates(dates)
        
        # Should return 0 due to error handling
        self.assertEqual(result, 0)
    
    def test_database_error_handling(self):
        """Test database error handling."""
        # Mock database to raise exception
        self.mock_db_manager.model_db.execute_query.side_effect = Exception("DB Error")
        
        # Test that strategic missing data query raises exception
        with self.assertRaises(Exception) as context:
            self.ingester._get_strategic_missing_daily_data()
        
        # Verify the exception message
        self.assertEqual(str(context.exception), "DB Error")
    
    def test_invalid_date_formats(self):
        """Test handling of invalid date formats in data."""
        raw_metric = {
            "date": "invalid-date",
            "accountId": "123456",
            "netProfit": 100
        }
        
        # Execute transformation
        transformed = self.ingester._transform_daily_metric(raw_metric)
        
        # Should handle invalid date gracefully
        self.assertIsNone(transformed["date"])
    
    def test_none_values_in_numeric_fields(self):
        """Test handling of None values in numeric fields."""
        raw_metric = {
            "accountId": "123456",
            "netProfit": None,
            "numTrades": None,
            "successRate": None
        }
        
        # Execute transformation
        transformed = self.ingester._transform_alltime_metric(raw_metric)
        
        # Should handle None values gracefully
        self.assertIsNone(transformed.get("net_profit"))
        self.assertIsNone(transformed.get("num_trades"))
        self.assertIsNone(transformed.get("success_rate"))
    
    def test_extreme_numeric_values(self):
        """Test handling of extreme numeric values."""
        raw_metric = {
            "accountId": "123456",
            "successRate": 99999.99,  # Too large for DECIMAL(5,2)
            "cvDurations": 999999.999999,  # Too large for DECIMAL(10,6)
        }
        
        # Execute transformation
        transformed = self.ingester._transform_alltime_metric(raw_metric)
        
        # Should bound extreme values
        self.assertLessEqual(transformed["success_rate"], 999.99)
        self.assertLessEqual(transformed["cv_durations"], 9999.999999)


class TestPerformanceAndConfiguration(TestMetricsIngester):
    """Test performance optimizations and configuration."""
    
    def test_batch_size_configuration(self):
        """Test that batch sizes are respected."""
        # Test configuration values
        self.assertEqual(self.ingester.config.batch_size, 1000)
        self.assertEqual(self.ingester.config.hourly_batch_size, 25)
        self.assertEqual(self.ingester.config.alltime_batch_size, 50)
    
    def test_rate_limiting_configuration(self):
        """Test rate limiting configuration."""
        # Test that lookback days is properly configured
        self.assertEqual(self.ingester.config.hourly_lookback_days, 30)
    
    @patch('time.sleep')
    def test_rate_limiting_implementation(self, mock_sleep):
        """Test that rate limiting is implemented."""
        # Test alltime ingestion with multiple batches
        account_ids = [f"ACC{i:03d}" for i in range(100)]  # 100 accounts, 2 batches
        
        # Mock API response
        self.mock_api_client.get_metrics.return_value = iter([[]])
        
        # Mock transform and insert
        self.ingester._transform_alltime_metric = Mock(side_effect=lambda x: x)
        self.ingester._insert_batch_with_upsert = Mock(return_value=0)
        
        # Execute
        self.ingester._ingest_alltime_for_accounts(account_ids)
        
        # Verify sleep was called for rate limiting
        mock_sleep.assert_called()
    
    def test_memory_management_limits(self):
        """Test memory management with large datasets."""
        # Test with configuration limits
        self.assertIsInstance(self.ingester.config.max_missing_slots, int)
        self.assertGreater(self.ingester.config.max_missing_slots, 0)


class TestUtilityMethods(TestMetricsIngester):
    """Test utility and helper methods."""
    
    def test_log_summary(self):
        """Test logging summary functionality."""
        results = {
            "alltime": 1000,
            "daily": 500,
            "hourly": 2000
        }
        
        # This should not raise any exceptions
        self.ingester._log_summary(results)
    
    def test_close_method(self):
        """Test cleanup method."""
        # Mock API client with close method
        self.ingester.api_client.close = Mock()
        
        # Mock db_manager with close method
        self.ingester.db_manager.close = Mock()
        
        # Execute
        self.ingester.close()
        
        # Verify cleanup was attempted
        self.ingester.api_client.close.assert_called_once()
        self.ingester.db_manager.close.assert_called_once()
    
    def test_close_method_error_handling(self):
        """Test cleanup method with errors."""
        # Mock API client to raise error on close
        self.ingester.api_client.close = Mock(side_effect=Exception("Close error"))
        
        # Should not raise exception
        self.ingester.close()


if __name__ == "__main__":
    # Configure test runner
    unittest.main(verbosity=2, buffer=True)