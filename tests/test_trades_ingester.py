"""
Tests for the enhanced trades ingester with checkpointing.
"""

import pytest
from datetime import date
from unittest.mock import Mock, patch
import tempfile
import shutil

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_ingestion.ingest_trades import TradesIngester, CheckpointManager
from utils.api_client import APIError


class TestCheckpointManager:
    """Test checkpoint manager functionality."""

    def setup_method(self):
        """Create temporary checkpoint directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.checkpoint_manager = CheckpointManager(self.temp_dir)

    def teardown_method(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_save_and_load_checkpoint(self):
        """Test saving and loading checkpoints."""
        test_data = {"last_processed_date": "2024-01-15", "total_records": 12345}

        # Save checkpoint
        self.checkpoint_manager.save_checkpoint("test_stage", test_data)

        # Load checkpoint
        loaded_data = self.checkpoint_manager.load_checkpoint("test_stage")

        assert loaded_data == test_data

    def test_load_nonexistent_checkpoint(self):
        """Test loading non-existent checkpoint returns None."""
        result = self.checkpoint_manager.load_checkpoint("nonexistent")
        assert result is None

    def test_clear_checkpoint(self):
        """Test clearing checkpoints."""
        # Save checkpoint
        self.checkpoint_manager.save_checkpoint("test_stage", {"data": "test"})

        # Verify it exists
        assert self.checkpoint_manager.load_checkpoint("test_stage") is not None

        # Clear it
        self.checkpoint_manager.clear_checkpoint("test_stage")

        # Verify it's gone
        assert self.checkpoint_manager.load_checkpoint("test_stage") is None


class TestTradesIngester:
    """Test enhanced trades ingester functionality."""

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_ingester_initialization(self, mock_api_client, mock_db_manager):
        """Test trades ingester initialization."""
        ingester = TradesIngester()

        assert ingester.db_manager is not None
        assert ingester.api_client is not None
        assert ingester.checkpoint_manager is not None
        assert ingester.metrics.api_calls == 0

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_validate_trade_record(self, mock_api_client, mock_db_manager):
        """Test trade record validation."""
        ingester = TradesIngester()

        # Valid closed trade (using actual API field names)
        valid_closed = {
            "tradeDate": "2025-06-01T00:00:00.000Z",
            "broker": 4,
            "mngr": 201,
            "platform": 8,
            "ticket": "W8994887965912253",
            "position": "W8994887965912253",
            "login": "25011525",
            "trdSymbol": "BTCUSD",
            "stdSymbol": "BTCUSD",
            "side": "Sell",
            "lots": 0.9,
            "contractSize": 1,
            "qtyInBaseCrncy": 0.9,
            "volumeUSD": 94496.1,
            "stopLoss": None,
            "takeProfit": None,
            "openTime": "2025-05-31T04:55:46.978Z",
            "openPrice": 103387.2,
            "closeTime": "2025-06-01T00:06:00.721Z",
            "closePrice": 104995.67,
            "duration": 19.170484166666668,
            "profit": -1447.62,
            "commission": 0,
            "fee": 0,
            "swap": 0,
            "comment": None,
            "client_margin": 4724.805,
            "firm_margin": 188.99220000000003
        }
        is_valid, errors = ingester._validate_trade_record(valid_closed, "closed")
        print(f"Valid closed trade validation: {is_valid}, errors: {errors}")
        assert is_valid is True
        assert len(errors) == 0

        # Invalid - missing required field
        invalid = valid_closed.copy()
        del invalid["position"]
        is_valid, errors = ingester._validate_trade_record(invalid, "closed")
        print(f"Invalid closed trade validation: {is_valid}, errors: {errors}")
        assert is_valid is False
        assert any("Missing required field: position" in error for error in errors)

        # Invalid - negative lots
        invalid = valid_closed.copy()
        invalid["lots"] = -0.1
        is_valid, errors = ingester._validate_trade_record(invalid, "closed")
        print(f"Invalid closed trade validation: {is_valid}, errors: {errors}")
        assert is_valid is False
        assert any("Lots must be positive" in error for error in errors)

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_safe_float_conversion(self, mock_api_client, mock_db_manager):
        """Test safe float conversion."""
        ingester = TradesIngester()

        assert ingester._safe_float(123.45) == 123.45
        assert ingester._safe_float("123.45") == 123.45
        assert ingester._safe_float(None) is None
        assert ingester._safe_float("invalid") is None
        assert ingester._safe_float([1, 2, 3]) is None

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_parse_timestamp(self, mock_api_client, mock_db_manager):
        """Test timestamp parsing."""
        ingester = TradesIngester()

        # Test various formats
        assert ingester._parse_timestamp("2024-01-15T10:30:45.123Z") is not None
        assert ingester._parse_timestamp("2024-01-15T10:30:45Z") is not None
        assert ingester._parse_timestamp("2024-01-15 10:30:45") is not None
        assert ingester._parse_timestamp("20240115103045") is not None
        assert ingester._parse_timestamp(None) is None
        assert ingester._parse_timestamp("invalid") is None

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_checkpoint_resume(self, mock_api_client, mock_db_manager):
        """Test resuming from checkpoint."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create checkpoint
            checkpoint_manager = CheckpointManager(temp_dir)
            checkpoint_data = {
                "last_processed_date": "2024-01-10",
                "total_records": 5000,
            }
            checkpoint_manager.save_checkpoint("trades_closed", checkpoint_data)

            # Mock API and DB
            mock_api_instance = Mock()
            mock_api_instance.get_trades.return_value = iter([])  # No trades
            mock_api_instance.format_date.return_value = "20240110"
            mock_api_client.return_value = mock_api_instance

            mock_db_instance = Mock()
            mock_db_instance.log_pipeline_execution = Mock()
            mock_db_instance.model_db = Mock()
            mock_db_instance.model_db.execute_command = Mock(return_value=0)
            
            # Setup context manager for database connection
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = (0,)  # No trades need resolution
            mock_cursor.fetchall.return_value = []  # No missing mappings
            mock_cursor.__enter__ = Mock(return_value=mock_cursor)
            mock_cursor.__exit__ = Mock(return_value=None)
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=None)
            mock_db_instance.model_db.get_connection.return_value = mock_conn
            
            mock_db_manager.return_value = mock_db_instance

            # Create ingester with custom checkpoint manager
            ingester = TradesIngester()
            ingester.checkpoint_manager = checkpoint_manager

            # Run ingestion with checkpoint resume
            result = ingester.ingest_trades(
                trade_type="closed",
                start_date=date(2024, 1, 1),  # Will be overridden by checkpoint
                end_date=date(2024, 1, 15),
                resume_from_checkpoint=True,
            )

            # Should have loaded checkpoint
            # Should have preserved checkpoint metrics
            assert ingester.metrics.total_records == 5000  # From checkpoint
            # No new records in this run (API returned empty)
            assert ingester.metrics.new_records == 0  # No new records added in this run
            assert result == 0  # Returns new_records from this run

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_metrics_tracking(self, mock_api_client, mock_db_manager):
        """Test metrics tracking during ingestion."""
        # Mock API with some data
        mock_api_instance = Mock()
        mock_api_instance.get_trades.return_value = iter(
            [
                [
                    {
                        "tradeDate": "2024-01-15T00:00:00.000Z",
                        "broker": 5,
                        "mngr": 1,
                        "platform": 5,
                        "ticket": "T1",
                        "position": "P1",
                        "login": "U1",
                        "trdSymbol": "EURUSD",
                        "stdSymbol": "EURUSD",
                        "side": "Buy",
                        "lots": 1.0,
                        "contractSize": 100000,
                        "qtyInBaseCrncy": 100000,
                        "volumeUSD": 100000,
                        "stopLoss": 1.0900,
                        "takeProfit": 1.1100,
                        "openTime": "2024-01-15T10:00:00Z",
                        "openPrice": 1.1000,
                        "closeTime": "2024-01-15T11:00:00Z",
                        "closePrice": 1.1010,
                        "duration": 1.0,
                        "profit": 100,
                        "commission": 0,
                        "fee": 0,
                        "swap": 0,
                        "comment": "",
                        "client_margin": 500,
                        "firm_margin": 20,
                    },
                    {
                        "tradeDate": "2024-01-15T00:00:00.000Z",
                        "broker": 5,
                        "mngr": 1,
                        "platform": 5,
                        "ticket": "T2",
                        "position": "P2",
                        "login": "U2",
                        "trdSymbol": "GBPUSD",
                        "stdSymbol": "GBPUSD",
                        "side": "Sell",
                        "lots": 0.5,
                        "contractSize": 100000,
                        "qtyInBaseCrncy": 50000,
                        "volumeUSD": 62500,
                        "stopLoss": 1.2700,
                        "takeProfit": 1.2500,
                        "openTime": "2024-01-15T11:00:00Z",
                        "openPrice": 1.2600,
                        "closeTime": "2024-01-15T12:00:00Z",
                        "closePrice": 1.2650,
                        "duration": 1.0,
                        "profit": -50,
                        "commission": 0,
                        "fee": 0,
                        "swap": 0,
                        "comment": "",
                        "client_margin": 315,
                        "firm_margin": 12.6,
                    },
                ]
            ]
        )
        mock_api_instance.format_date.side_effect = lambda d: d.strftime("%Y%m%d")
        mock_api_client.return_value = mock_api_instance

        # Mock DB
        mock_db_instance = Mock()
        mock_db_instance.log_pipeline_execution = Mock()
        mock_db_instance.model_db = Mock()
        
        # Setup context manager for database connection
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (0,)  # No trades need resolution
        mock_cursor.fetchall.return_value = []  # No missing mappings
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_db_instance.model_db.get_connection.return_value = mock_conn
        
        mock_db_manager.return_value = mock_db_instance

        ingester = TradesIngester()

        # Run ingestion
        ingester.ingest_trades(
            trade_type="open", start_date=date(2024, 1, 15), end_date=date(2024, 1, 15)
        )

        # Check metrics
        assert ingester.metrics.api_calls > 0
        assert len(ingester.metrics.validation_errors) >= 0

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_api_error_handling(self, mock_api_client, mock_db_manager):
        """Test handling of API errors."""
        # Mock API that raises error
        mock_api_instance = Mock()
        mock_api_instance.get_trades.side_effect = APIError("API is down")
        mock_api_instance.format_date.return_value = "20240115"
        mock_api_client.return_value = mock_api_instance

        # Mock DB
        mock_db_instance = Mock()
        mock_db_instance.log_pipeline_execution = Mock()
        mock_db_manager.return_value = mock_db_instance

        ingester = TradesIngester()

        # Should raise error for open trades (no retry)
        with pytest.raises(APIError):
            ingester.ingest_trades(
                trade_type="open",
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15),
            )

        # API error should be counted
        assert ingester.metrics.api_errors == 1  # API error is now tracked

    @patch("data_ingestion.ingest_trades.get_db_manager")
    @patch("data_ingestion.ingest_trades.RiskAnalyticsAPIClient")
    def test_duplicate_handling(self, mock_api_client, mock_db_manager):
        """Test handling of duplicate records."""
        # Mock API
        mock_api_instance = Mock()
        mock_api_client.return_value = mock_api_instance

        # Mock DB with duplicate tracking
        mock_cursor = Mock()
        mock_cursor.fetchone.side_effect = [(100,), (101,)]  # Before and after counts

        mock_conn = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)

        mock_db_instance = Mock()
        mock_db_instance.model_db = Mock()
        mock_db_instance.model_db.get_connection.return_value = mock_conn
        mock_db_manager.return_value = mock_db_instance

        ingester = TradesIngester()

        # Insert batch with 5 records but only 1 new - using real trade record fields
        # Primary key is (platform, position, trade_date) for trades tables
        from datetime import date
        batch_data = [
            {
                "platform": "5",
                "position": f"P{i}",
                "trade_date": date(2024, 1, 15),
                "broker": "5",
                "login": "12345",
                "profit": 100.0,
                "lots": 1.0,
                "ingestion_timestamp": "2024-01-15 10:00:00",
                "source_api_endpoint": "/v2/trades/closed"
            } for i in range(5)
        ]

        success = ingester._insert_trades_batch(batch_data, "test_table")

        assert success
        assert ingester.metrics.duplicate_records == 4  # 5 total - 1 new

    @patch("data_ingestion.ingest_trades.get_db_manager")
    def test_batch_account_resolution(self, mock_db_manager):
        """Test batch account ID resolution functionality."""
        # Mock DB with proper context managers
        mock_db_instance = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Setup mock responses for the optimized query flow
        mock_cursor.fetchone.return_value = (1,)  # Has trades needing resolution
        mock_cursor.rowcount = 1000  # 1000 trades updated
        mock_cursor.fetchall.side_effect = [
            # First call: check for missing mappings after update
            [("login1", 5, 4), ("login2", 5, 4)],
            # Second call: check for duplicate account_ids
            []  # No duplicates
        ]
        
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_db_instance.model_db.get_connection.return_value = mock_conn
        mock_db_manager.return_value = mock_db_instance
        
        ingester = TradesIngester()
        
        # Test account resolution
        updated_count = ingester._batch_resolve_account_ids("raw_trades_closed")
        
        # Verify results
        assert updated_count == 1000  # Trades were updated
        assert mock_cursor.execute.call_count >= 4  # COUNT, UPDATE, SELECT missing, SELECT duplicates
        assert mock_conn.commit.called  # Changes were committed
        
    @patch("data_ingestion.ingest_trades.get_db_manager")
    def test_batch_account_resolution_duplicate_error(self, mock_db_manager):
        """Test that duplicate account_ids for same (login, platform, broker) raise an error."""
        # Mock DB with proper context managers
        mock_db_instance = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Setup mock returns
        mock_cursor.fetchone.return_value = (1,)  # Has trades needing resolution
        mock_cursor.rowcount = 0  # No rows updated by UPDATE JOIN
        
        # First fetchall returns missing mappings, second returns duplicate account_ids
        mock_cursor.fetchall.side_effect = [
            [("login1", 5, 4)],  # Missing mapping
            [("login1", 5, 4, 2)]  # Duplicate account_ids (count > 1)
        ]
        
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_db_instance.model_db.get_connection.return_value = mock_conn
        mock_db_manager.return_value = mock_db_instance
        
        ingester = TradesIngester()
        
        # Should raise AssertionError due to duplicate account_ids
        with pytest.raises(AssertionError) as exc_info:
            ingester._batch_resolve_account_ids("raw_trades_closed")
        
        assert "Multiple account_ids found" in str(exc_info.value)
        assert "login=login1" in str(exc_info.value)
        assert "platform=5" in str(exc_info.value)
        assert "broker=4" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
