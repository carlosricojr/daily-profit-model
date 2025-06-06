"""
Test suite for the enhanced accounts ingester.
Tests account data ingestion with validation and production features.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json
import tempfile
from pathlib import Path

from src.data_ingestion.ingest_accounts import AccountsIngester


class TestAccountsIngester(unittest.TestCase):
    """Test the enhanced accounts ingester."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
        # Mock database and API client
        self.mock_db_manager = Mock()
        self.mock_api_client = Mock()
        self.mock_model_db = Mock()
        self.mock_db_manager.model_db = self.mock_model_db
        
        # Patch the dependencies
        self.patches = [
            patch('src.data_ingestion.base_ingester.get_db_manager'),
            patch('src.data_ingestion.ingest_accounts.RiskAnalyticsAPIClient')
        ]
        
        self.mock_get_db = self.patches[0].start()
        self.mock_api_class = self.patches[1].start()
        
        self.mock_get_db.return_value = self.mock_db_manager
        self.mock_api_class.return_value = self.mock_api_client
        
        self.ingester = AccountsIngester(checkpoint_dir=self.temp_dir)
    
    def tearDown(self):
        for p in self.patches:
            p.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_validate_account_record(self):
        """Test account record validation."""
        # Valid account
        valid_account = {
            'accountId': 'ACC123',
            'login': 12345,
            'traderId': 'TRADER123',
            'planId': 'PLAN123',
            'startingBalance': 10000.0,
            'currentBalance': 10500.0,
            'breached': 0,
            'phase': 'evaluation',
            'status': 'active'
        }
        
        is_valid, errors = self.ingester._validate_record(valid_account)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Invalid account - missing required field
        invalid_account = {
            'login': 12345,
            'startingBalance': 10000.0
        }
        
        is_valid, errors = self.ingester._validate_record(invalid_account)
        self.assertFalse(is_valid)
        self.assertIn('missing_accountId', errors)
        
        # Invalid account - negative balance
        negative_balance = valid_account.copy()
        negative_balance['currentBalance'] = -100.0
        
        is_valid, errors = self.ingester._validate_record(negative_balance)
        self.assertFalse(is_valid)
        self.assertIn('negative_balance', errors)
        
        # Invalid account - balance less than starting
        invalid_balance = valid_account.copy()
        invalid_balance['currentBalance'] = 5000.0  # Less than starting 10000
        invalid_balance['breached'] = 0  # Not breached but balance went down
        
        is_valid, errors = self.ingester._validate_record(invalid_balance)
        self.assertFalse(is_valid)
        self.assertIn('balance_inconsistency', errors)
    
    def test_transform_account_record(self):
        """Test account record transformation."""
        raw_account = {
            'accountId': 'ACC123',
            'login': 12345,
            'traderId': 'TRADER123',
            'planId': 'PLAN123',
            'startingBalance': 10000.0,
            'currentBalance': 10500.0,
            'currentEquity': 10600.0,
            'profitTargetPct': 10.0,
            'maxDailyDrawdownPct': 5.0,
            'maxDrawdownPct': 10.0,
            'maxLeverage': 100,
            'isDrawdownRelative': True,
            'breached': 0,
            'isUpgraded': 1,
            'phase': 'evaluation',
            'status': 'active',
            'createdAt': '2024-01-01T00:00:00Z',
            'updatedAt': '2024-01-15T12:00:00Z'
        }
        
        transformed = self.ingester._transform_record(raw_account)
        
        self.assertEqual(transformed['account_id'], 'ACC123')
        self.assertEqual(transformed['login'], 12345)
        self.assertEqual(transformed['starting_balance'], 10000.0)
        self.assertEqual(transformed['breached'], 0)
        self.assertEqual(transformed['is_upgraded'], 1)
        self.assertIn('ingestion_timestamp', transformed)
        self.assertEqual(transformed['source_api_endpoint'], '/accounts')
    
    def test_checkpoint_resume(self):
        """Test resuming from checkpoint."""
        # Create a checkpoint file
        checkpoint_data = {
            'ingestion_type': 'accounts',
            'last_processed_page': 2,
            'total_records': 150,
            'timestamp': datetime.now().isoformat(),
            'metrics': {
                'total_records': 150,
                'new_records': 140,
                'duplicate_records': 5,
                'invalid_records': 5,
                'api_calls': 3,
                'api_errors': 0,
                'db_errors': 0,
                'validation_errors': {}
            }
        }
        
        checkpoint_file = Path(self.temp_dir) / "accounts_checkpoint.json"
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f)
        
        # Mock API response
        self.mock_api_client.get_accounts.return_value = iter([
            [{'accountId': 'ACC1', 'login': 1, 'startingBalance': 10000}]
        ])
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Run ingestion with resume
        result = self.ingester.ingest_accounts(resume_from_checkpoint=True)
        
        # Should have loaded checkpoint
        self.assertEqual(self.ingester.metrics.total_records, 150)
    
    def test_filtering_by_logins_and_traders(self):
        """Test filtering accounts by login IDs and trader IDs."""
        # Mock API response
        self.mock_api_client.get_accounts.return_value = iter([
            [
                {'accountId': 'ACC1', 'login': 12345, 'traderId': 'T1', 'startingBalance': 10000},
                {'accountId': 'ACC2', 'login': 67890, 'traderId': 'T2', 'startingBalance': 20000}
            ]
        ])
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Run ingestion with filters
        result = self.ingester.ingest_accounts(
            logins=['12345', '67890'],
            traders=['T1', 'T2']
        )
        
        # Verify API was called with filters
        self.mock_api_client.get_accounts.assert_called_with(
            logins=['12345', '67890'],
            traders=['T1', 'T2']
        )
        
        self.assertEqual(result, 2)
    
    def test_phase_and_status_validation(self):
        """Test validation of phase and status fields."""
        # Valid phases and statuses
        valid_phases = ['evaluation', 'challenge', 'funded', 'express']
        valid_statuses = ['active', 'inactive', 'suspended', 'terminated']
        
        for phase in valid_phases:
            account = {
                'accountId': 'ACC123',
                'login': 12345,
                'phase': phase,
                'status': 'active',
                'startingBalance': 10000
            }
            is_valid, errors = self.ingester._validate_record(account)
            self.assertTrue(is_valid, f"Phase '{phase}' should be valid")
        
        for status in valid_statuses:
            account = {
                'accountId': 'ACC123', 
                'login': 12345,
                'phase': 'evaluation',
                'status': status,
                'startingBalance': 10000
            }
            is_valid, errors = self.ingester._validate_record(account)
            self.assertTrue(is_valid, f"Status '{status}' should be valid")
        
        # Invalid phase
        account = {
            'accountId': 'ACC123',
            'login': 12345,
            'phase': 'invalid_phase',
            'status': 'active',
            'startingBalance': 10000
        }
        is_valid, errors = self.ingester._validate_record(account)
        self.assertFalse(is_valid)
        self.assertIn('invalid_phase', errors)
    
    def test_duplicate_account_handling(self):
        """Test handling of duplicate accounts."""
        # Mock API to return duplicates
        self.mock_api_client.get_accounts.return_value = iter([
            [
                {'accountId': 'ACC1', 'login': 12345, 'startingBalance': 10000},
                {'accountId': 'ACC1', 'login': 12345, 'startingBalance': 10000},  # Duplicate
                {'accountId': 'ACC2', 'login': 67890, 'startingBalance': 20000}
            ]
        ])
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Run ingestion with deduplication
        result = self.ingester.ingest_accounts(enable_deduplication=True)
        
        # Check metrics
        self.assertEqual(self.ingester.metrics.total_records, 3)
        self.assertEqual(self.ingester.metrics.new_records, 2)  # Only 2 unique
        self.assertEqual(self.ingester.metrics.duplicate_records, 1)
    
    def test_metrics_tracking(self):
        """Test comprehensive metrics tracking."""
        # Mock API responses - mix of valid and invalid accounts
        self.mock_api_client.get_accounts.return_value = iter([
            [
                {'accountId': 'ACC1', 'login': 12345, 'startingBalance': 10000},
                {'accountId': 'ACC2', 'login': 67890, 'startingBalance': -5000},  # Invalid
                {'accountId': 'ACC3', 'login': 11111, 'phase': 'invalid', 'startingBalance': 10000},  # Invalid
                {'accountId': 'ACC4', 'login': 22222, 'startingBalance': 10000}
            ]
        ])
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Run ingestion with validation
        result = self.ingester.ingest_accounts(enable_validation=True)
        
        # Check metrics
        self.assertEqual(self.ingester.metrics.total_records, 4)
        self.assertEqual(self.ingester.metrics.new_records, 2)  # 2 valid
        self.assertEqual(self.ingester.metrics.invalid_records, 2)  # 2 invalid
        self.assertGreater(self.ingester.metrics.api_calls, 0)
        self.assertIn('negative_starting_balance', self.ingester.metrics.validation_errors)
        self.assertIn('invalid_phase', self.ingester.metrics.validation_errors)
    
    def test_force_refresh(self):
        """Test force refresh clears existing data."""
        # Mock database operations
        mock_conn = MagicMock()
        self.mock_model_db.get_connection.return_value = mock_conn
        self.mock_model_db.execute_command = Mock()
        
        # Mock API response
        self.mock_api_client.get_accounts.return_value = iter([
            [{'accountId': 'ACC1', 'login': 12345, 'startingBalance': 10000}]
        ])
        
        # Run with force refresh
        self.ingester.ingest_accounts(force_full_refresh=True)
        
        # Verify TRUNCATE was called
        self.mock_model_db.execute_command.assert_called_with(
            "TRUNCATE TABLE raw_accounts_data"
        )


if __name__ == '__main__':
    unittest.main()