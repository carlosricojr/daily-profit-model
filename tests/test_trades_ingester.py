"""
Tests for the enhanced trades ingester with checkpointing.
"""

import pytest
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
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
        test_data = {
            'last_processed_date': '2024-01-15',
            'total_records': 12345
        }
        
        # Save checkpoint
        self.checkpoint_manager.save_checkpoint('test_stage', test_data)
        
        # Load checkpoint
        loaded_data = self.checkpoint_manager.load_checkpoint('test_stage')
        
        assert loaded_data == test_data
    
    def test_load_nonexistent_checkpoint(self):
        """Test loading non-existent checkpoint returns None."""
        result = self.checkpoint_manager.load_checkpoint('nonexistent')
        assert result is None
    
    def test_clear_checkpoint(self):
        """Test clearing checkpoints."""
        # Save checkpoint
        self.checkpoint_manager.save_checkpoint('test_stage', {'data': 'test'})
        
        # Verify it exists
        assert self.checkpoint_manager.load_checkpoint('test_stage') is not None
        
        # Clear it
        self.checkpoint_manager.clear_checkpoint('test_stage')
        
        # Verify it's gone
        assert self.checkpoint_manager.load_checkpoint('test_stage') is None


class TestTradesIngester:
    """Test enhanced trades ingester functionality."""
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_ingester_initialization(self, mock_api_client, mock_db_manager):
        """Test trades ingester initialization."""
        ingester = TradesIngester()
        
        assert ingester.db_manager is not None
        assert ingester.api_client is not None
        assert ingester.checkpoint_manager is not None
        assert ingester.metrics['api_calls'] == 0
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_validate_trade_record(self, mock_api_client, mock_db_manager):
        """Test trade record validation."""
        ingester = TradesIngester()
        
        # Valid closed trade
        valid_closed = {
            'trade_id': '123',
            'account_id': '456',
            'login': 'user1',
            'symbol': 'EURUSD',
            'side': 'buy',
            'open_time': datetime.now(),
            'close_time': datetime.now(),
            'profit': 100.0,
            'lots': 0.1
        }
        assert ingester._validate_trade_record(valid_closed, 'closed')
        
        # Invalid - missing required field
        invalid = valid_closed.copy()
        del invalid['trade_id']
        assert not ingester._validate_trade_record(invalid, 'closed')
        
        # Invalid - negative lots
        invalid = valid_closed.copy()
        invalid['lots'] = -0.1
        assert not ingester._validate_trade_record(invalid, 'closed')
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_safe_float_conversion(self, mock_api_client, mock_db_manager):
        """Test safe float conversion."""
        ingester = TradesIngester()
        
        assert ingester._safe_float(123.45) == 123.45
        assert ingester._safe_float('123.45') == 123.45
        assert ingester._safe_float(None) is None
        assert ingester._safe_float('invalid') is None
        assert ingester._safe_float([1, 2, 3]) is None
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_parse_timestamp(self, mock_api_client, mock_db_manager):
        """Test timestamp parsing."""
        ingester = TradesIngester()
        
        # Test various formats
        assert ingester._parse_timestamp('2024-01-15T10:30:45.123Z') is not None
        assert ingester._parse_timestamp('2024-01-15T10:30:45Z') is not None
        assert ingester._parse_timestamp('2024-01-15 10:30:45') is not None
        assert ingester._parse_timestamp('20240115103045') is not None
        assert ingester._parse_timestamp(None) is None
        assert ingester._parse_timestamp('invalid') is None
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_checkpoint_resume(self, mock_api_client, mock_db_manager):
        """Test resuming from checkpoint."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create checkpoint
            checkpoint_manager = CheckpointManager(temp_dir)
            checkpoint_data = {
                'last_processed_date': '2024-01-10',
                'total_records': 5000
            }
            checkpoint_manager.save_checkpoint('trades_closed', checkpoint_data)
            
            # Mock API and DB
            mock_api_instance = Mock()
            mock_api_instance.get_trades.return_value = iter([])  # No trades
            mock_api_instance.format_date.return_value = '20240110'
            mock_api_client.return_value = mock_api_instance
            
            mock_db_instance = Mock()
            mock_db_instance.model_db.execute_command.return_value = 0
            mock_db_manager.return_value = mock_db_instance
            
            # Create ingester with custom checkpoint manager
            ingester = TradesIngester()
            ingester.checkpoint_manager = checkpoint_manager
            
            # Run ingestion with checkpoint resume
            result = ingester.ingest_trades(
                trade_type='closed',
                start_date=date(2024, 1, 1),  # Will be overridden by checkpoint
                end_date=date(2024, 1, 15),
                resume_from_checkpoint=True
            )
            
            # Should have loaded checkpoint
            assert result == 5000  # Initial records from checkpoint
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_metrics_tracking(self, mock_api_client, mock_db_manager):
        """Test metrics tracking during ingestion."""
        # Mock API with some data
        mock_api_instance = Mock()
        mock_api_instance.get_trades.return_value = iter([[
            {'tradeId': '1', 'accountId': 'A1', 'login': 'U1', 'symbol': 'EURUSD', 
             'side': 'buy', 'openTime': '2024-01-15T10:00:00Z', 'profit': 100},
            {'tradeId': '2', 'accountId': 'A2', 'login': 'U2', 'symbol': 'GBPUSD',
             'side': 'sell', 'openTime': '2024-01-15T11:00:00Z', 'profit': -50},
        ]])
        mock_api_instance.format_date.side_effect = lambda d: d.strftime('%Y%m%d')
        mock_api_client.return_value = mock_api_instance
        
        # Mock DB
        mock_db_instance = Mock()
        mock_db_instance.model_db.get_connection.return_value.__enter__ = Mock()
        mock_db_instance.model_db.get_connection.return_value.__exit__ = Mock()
        mock_db_manager.return_value = mock_db_instance
        
        ingester = TradesIngester()
        
        # Run ingestion
        ingester.ingest_trades(
            trade_type='open',
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15)
        )
        
        # Check metrics
        assert ingester.metrics['api_calls'] > 0
        assert ingester.metrics['validation_errors'] >= 0
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_api_error_handling(self, mock_api_client, mock_db_manager):
        """Test handling of API errors."""
        # Mock API that raises error
        mock_api_instance = Mock()
        mock_api_instance.get_trades.side_effect = APIError("API is down")
        mock_api_instance.format_date.return_value = '20240115'
        mock_api_client.return_value = mock_api_instance
        
        # Mock DB
        mock_db_manager.return_value = Mock()
        
        ingester = TradesIngester()
        
        # Should raise error for open trades (no retry)
        with pytest.raises(APIError):
            ingester.ingest_trades(
                trade_type='open',
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15)
            )
        
        assert ingester.metrics['api_errors'] > 0
    
    @patch('data_ingestion.ingest_trades.get_db_manager')
    @patch('data_ingestion.ingest_trades.RiskAnalyticsAPIClient')
    def test_duplicate_handling(self, mock_api_client, mock_db_manager):
        """Test handling of duplicate records."""
        # Mock API
        mock_api_instance = Mock()
        mock_api_client.return_value = mock_api_instance
        
        # Mock DB with duplicate tracking
        mock_cursor = Mock()
        mock_cursor.fetchone.side_effect = [(100,), (101,)]  # Before and after counts
        
        mock_conn = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        
        mock_db_instance = Mock()
        mock_db_instance.model_db.get_connection.return_value.__enter__.return_value = mock_conn
        mock_db_instance.model_db.get_connection.return_value.__exit__ = Mock(return_value=None)
        mock_db_manager.return_value = mock_db_instance
        
        ingester = TradesIngester()
        
        # Insert batch with 5 records but only 1 new
        batch_data = [
            {'trade_id': f'T{i}', 'other': 'data'} for i in range(5)
        ]
        
        success = ingester._insert_trades_batch(batch_data, 'test_table')
        
        assert success
        assert ingester.metrics['duplicate_records'] == 4  # 5 total - 1 new


if __name__ == '__main__':
    pytest.main([__file__, '-v'])