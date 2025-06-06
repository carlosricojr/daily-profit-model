"""
Test suite for the metrics ingester with comprehensive validation.
Tests alltime, daily, and hourly metrics ingestion with production-ready features.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import date
import os
import tempfile
from pathlib import Path

from src.data_ingestion.ingest_metrics import MetricsIngester, MetricType
from src.data_ingestion.base_ingester import CheckpointManager


class TestCheckpointManager(unittest.TestCase):
    """Test checkpoint management for metrics ingestion."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.checkpoint_file = Path(self.temp_dir) / "metrics_checkpoint.json"
        self.checkpoint_manager = CheckpointManager(
            str(self.checkpoint_file), "metrics_daily"
        )

    def tearDown(self):
        # Clean up
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
        os.rmdir(self.temp_dir)

    def test_save_and_load_checkpoint(self):
        """Test saving and loading checkpoint data."""
        checkpoint_data = {
            "metric_type": "daily",
            "last_processed_date": "2024-01-15",
            "last_processed_page": 5,
            "total_records": 1000,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        }

        # Save checkpoint
        self.checkpoint_manager.save_checkpoint(checkpoint_data)
        self.assertTrue(self.checkpoint_file.exists())

        # Load checkpoint
        loaded_data = self.checkpoint_manager.load_checkpoint()
        self.assertEqual(loaded_data, checkpoint_data)

    def test_load_nonexistent_checkpoint(self):
        """Test loading when no checkpoint exists."""
        checkpoint = self.checkpoint_manager.load_checkpoint()
        self.assertIsNone(checkpoint)

    def test_clear_checkpoint(self):
        """Test clearing checkpoint."""
        # Save a checkpoint first
        self.checkpoint_manager.save_checkpoint({"test": "data"})
        self.assertTrue(self.checkpoint_file.exists())

        # Clear it
        self.checkpoint_manager.clear_checkpoint()
        self.assertFalse(self.checkpoint_file.exists())


class TestMetricsIngester(unittest.TestCase):
    """Test the enhanced metrics ingester."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Mock database and API client
        self.mock_db_manager = Mock()
        self.mock_api_client = Mock()
        self.mock_model_db = Mock()
        self.mock_db_manager.model_db = self.mock_model_db

        # Patch the dependencies
        self.patches = [
            patch("src.data_ingestion.base_ingester.get_db_manager"),
            patch("src.data_ingestion.ingest_metrics.RiskAnalyticsAPIClient"),
        ]

        self.mock_get_db = self.patches[0].start()
        self.mock_api_class = self.patches[1].start()

        self.mock_get_db.return_value = self.mock_db_manager
        self.mock_api_class.return_value = self.mock_api_client

        self.ingester = MetricsIngester(checkpoint_dir=self.temp_dir)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ingester_initialization(self):
        """Test ingester initialization."""
        self.assertIsNotNone(self.ingester.db_manager)
        self.assertIsNotNone(self.ingester.api_client)
        self.assertIsNotNone(self.ingester.checkpoint_managers)
        self.assertIn("alltime", self.ingester.checkpoint_managers)
        self.assertIn("daily", self.ingester.checkpoint_managers)
        self.assertIn("hourly", self.ingester.checkpoint_managers)
        self.assertEqual(len(self.ingester.metrics_by_type), 3)

    def test_validate_record(self):
        """Test metric record validation."""
        # Valid alltime metric
        valid_alltime = {
            "accountId": "ACC123",
            "login": 12345,
            "netProfit": 1000.50,
            "grossProfit": 1500.0,
            "grossLoss": -500.0,
            "totalTrades": 100,
            "winningTrades": 60,
            "losingTrades": 40,
        }

        is_valid, errors = self.ingester._validate_record(
            valid_alltime, MetricType.ALLTIME
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # Invalid metric - missing required field
        invalid_metric = {"login": 12345, "netProfit": 1000.50}

        is_valid, errors = self.ingester._validate_record(
            invalid_metric, MetricType.ALLTIME
        )
        self.assertFalse(is_valid)
        self.assertIn("missing_account_id", errors)

        # Invalid metric - negative trade count
        invalid_trades = valid_alltime.copy()
        invalid_trades["totalTrades"] = -5

        is_valid, errors = self.ingester._validate_record(
            invalid_trades, MetricType.ALLTIME
        )
        self.assertFalse(is_valid)
        self.assertIn("negative_trade_count", errors)

    def test_validate_daily_metric(self):
        """Test daily metric validation."""
        # Valid daily metric
        valid_daily = {
            "accountId": "ACC123",
            "login": 12345,
            "date": "20240115",
            "netProfit": 100.0,
            "balanceStart": 10000.0,
            "balanceEnd": 10100.0,
        }

        is_valid, errors = self.ingester._validate_record(valid_daily, MetricType.DAILY)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # Invalid date format
        invalid_date = valid_daily.copy()
        invalid_date["date"] = "2024-01-15"  # Wrong format

        is_valid, errors = self.ingester._validate_record(
            invalid_date, MetricType.DAILY
        )
        self.assertFalse(is_valid)
        self.assertIn("invalid_date_format", errors)

    def test_validate_hourly_metric(self):
        """Test hourly metric validation."""
        # Valid hourly metric
        valid_hourly = {
            "accountId": "ACC123",
            "login": 12345,
            "date": "20240115",
            "hour": 14,
            "netProfit": 50.0,
        }

        is_valid, errors = self.ingester._validate_record(
            valid_hourly, MetricType.HOURLY
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # Invalid hour
        invalid_hour = valid_hourly.copy()
        invalid_hour["hour"] = 25  # Invalid hour

        is_valid, errors = self.ingester._validate_record(
            invalid_hour, MetricType.HOURLY
        )
        self.assertFalse(is_valid)
        self.assertIn("invalid_hour", errors)

    def test_safe_float_conversion(self):
        """Test safe float conversion."""
        # Valid conversions
        self.assertEqual(self.ingester._safe_float("123.45"), 123.45)
        self.assertEqual(self.ingester._safe_float(123.45), 123.45)
        self.assertEqual(self.ingester._safe_float(123), 123.0)

        # Invalid conversions
        self.assertIsNone(self.ingester._safe_float("invalid"))
        self.assertIsNone(self.ingester._safe_float(None))
        self.assertIsNone(self.ingester._safe_float(""))

    def test_checkpoint_resume_daily_metrics(self):
        """Test resuming from checkpoint for daily metrics."""
        # Set up checkpoint data
        checkpoint_data = {
            "metric_type": "daily",
            "last_processed_date": "2024-01-15",
            "last_processed_page": -1,  # -1 means date is complete
            "total_records": 500,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "timestamp": "2024-01-15T10:00:00",
            "ingestion_type": "metrics_daily",
        }
        # Create checkpoint file
        import json

        checkpoint_file = os.path.join(self.temp_dir, "metrics_daily_checkpoint.json")
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f)

        # Mock API response
        self.mock_api_client.get_metrics.return_value = iter(
            [[{"accountId": "ACC1", "login": 1, "date": "20240116", "netProfit": 100}]]
        )
        self.mock_api_client.format_date.side_effect = lambda d: d.strftime("%Y%m%d")

        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn

        # Run ingestion with resume
        result = self.ingester.ingest_metrics(
            metric_type="daily",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            resume_from_checkpoint=True,
        )

        # Verify checkpoint was loaded by checking we only processed new records
        # Should return 1 new record (metrics from checkpoint are restored but not counted in return)
        self.assertEqual(result, 1)

    def test_metrics_tracking(self):
        """Test that metrics are properly tracked during ingestion."""
        # Mock API responses
        self.mock_api_client.get_metrics.return_value = iter(
            [
                [
                    {"accountId": "ACC1", "login": 1, "netProfit": 100},
                    {
                        "accountId": "ACC2",
                        "login": 2,
                        "netProfit": "invalid",
                    },  # Invalid
                    {"accountId": "ACC3", "login": 3, "netProfit": 200},
                ]
            ]
        )

        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn

        # Run ingestion
        self.ingester.ingest_metrics(metric_type="alltime", enable_validation=True)

        # Check metrics
        metrics = self.ingester.metrics_by_type["alltime"]
        self.assertEqual(metrics.total_records, 3)
        self.assertEqual(metrics.new_records, 2)  # 2 valid
        self.assertEqual(metrics.invalid_records, 1)  # 1 invalid
        self.assertGreater(metrics.api_calls, 0)
        self.assertEqual(metrics.api_errors, 0)

    def test_date_range_processing(self):
        """Test date range processing for time series metrics."""
        # Mock API to return data for specific dates
        api_responses = []
        for day in range(5):
            api_responses.append(
                [
                    {
                        "accountId": f"ACC{i}",
                        "login": i,
                        "date": f"2024011{day}",
                        "netProfit": i * 10,
                    }
                    for i in range(1, 4)
                ]
            )

        self.mock_api_client.get_metrics.side_effect = [
            iter([resp]) for resp in api_responses
        ]
        self.mock_api_client.format_date.side_effect = lambda d: d.strftime("%Y%m%d")

        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn

        # Run ingestion for date range
        result = self.ingester.ingest_metrics(
            metric_type="daily",
            start_date=date(2024, 1, 10),
            end_date=date(2024, 1, 14),
        )

        # Should process 5 days * 3 records = 15 records
        self.assertEqual(result, 15)

        # Verify API was called for each date
        self.assertEqual(self.mock_api_client.get_metrics.call_count, 5)

    def test_hourly_metrics_processing(self):
        """Test hourly metrics processing with hour specification."""
        # Mock API response for hourly data
        hourly_data = []
        for hour in range(24):
            hourly_data.append(
                {
                    "accountId": "ACC1",
                    "login": 12345,
                    "date": "20240115",
                    "hour": hour,
                    "netProfit": hour * 10.0,
                }
            )

        self.mock_api_client.get_metrics.return_value = iter([hourly_data])
        self.mock_api_client.format_date.return_value = "20240115"

        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn

        # Run hourly ingestion
        result = self.ingester.ingest_metrics(
            metric_type="hourly",
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
        )

        # Should process all 24 hours
        self.assertEqual(result, 24)

        # Verify hours were specified in API call
        api_call_args = self.mock_api_client.get_metrics.call_args
        self.assertEqual(api_call_args[1]["hours"], list(range(24)))

    def test_duplicate_handling(self):
        """Test duplicate record handling."""
        # Mock API to return duplicates
        self.mock_api_client.get_metrics.return_value = iter(
            [
                [
                    {"accountId": "ACC1", "login": 1, "netProfit": 100},
                    {"accountId": "ACC1", "login": 1, "netProfit": 100},  # Duplicate
                    {"accountId": "ACC2", "login": 2, "netProfit": 200},
                ]
            ]
        )

        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn

        # Run ingestion with deduplication
        self.ingester.ingest_metrics(metric_type="alltime", enable_deduplication=True)

        # Check metrics
        metrics = self.ingester.metrics_by_type["alltime"]
        self.assertEqual(metrics.total_records, 3)
        self.assertEqual(metrics.new_records, 2)  # Only 2 unique
        self.assertEqual(metrics.duplicate_records, 1)

    def test_api_error_handling(self):
        """Test handling of API errors."""
        # Mock API to raise an error
        from src.utils.api_client import APIError

        self.mock_api_client.get_metrics.side_effect = APIError(
            "API rate limit exceeded"
        )

        # Run ingestion and expect it to handle the error
        with self.assertRaises(APIError):
            self.ingester.ingest_metrics(metric_type="alltime")

        # Check that error was tracked
        metrics = self.ingester.metrics_by_type["alltime"]
        self.assertEqual(metrics.api_errors, 1)

        # Verify pipeline execution was logged as failed
        self.mock_db_manager.log_pipeline_execution.assert_called()
        last_call = self.mock_db_manager.log_pipeline_execution.call_args_list[-1]
        self.assertEqual(last_call[1]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
