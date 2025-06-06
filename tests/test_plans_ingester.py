"""
Test suite for the enhanced plans ingester.
Tests plan data ingestion from CSV files with production features.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import tempfile
from pathlib import Path
import pandas as pd

from src.data_ingestion.ingest_plans_enhanced import PlansIngester


class TestPlansIngester(unittest.TestCase):
    """Test the enhanced plans ingester."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.csv_dir = Path(self.temp_dir) / "plans"
        self.csv_dir.mkdir()
        
        # Mock database manager
        self.mock_db_manager = Mock()
        self.mock_model_db = Mock()
        self.mock_db_manager.model_db = self.mock_model_db
        
        # Patch the dependencies
        self.patches = [
            patch('src.data_ingestion.base_ingester.get_db_manager')
        ]
        
        self.mock_get_db = self.patches[0].start()
        self.mock_get_db.return_value = self.mock_db_manager
        
        # Mock log_pipeline_execution
        self.mock_db_manager.log_pipeline_execution = Mock()
        
        # Make sure insert_batch doesn't exist so we use executemany
        if hasattr(self.mock_model_db, 'insert_batch'):
            delattr(self.mock_model_db, 'insert_batch')
        
        self.ingester = PlansIngester(checkpoint_dir=self.temp_dir)
    
    def tearDown(self):
        for p in self.patches:
            p.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_csv(self, filename: str, data: list):
        """Helper to create a test CSV file."""
        csv_path = self.csv_dir / filename
        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False)
        return csv_path
    
    def test_validate_plan_record(self):
        """Test plan record validation."""
        # Valid plan
        valid_plan = {
            'plan_id': 'PLAN123',
            'plan_name': 'Standard Challenge',
            'plan_type': 'challenge',
            'starting_balance': 10000.0,
            'profit_target': 1000.0,
            'profit_target_pct': 10.0,
            'max_drawdown': 1000.0,
            'max_drawdown_pct': 10.0,
            'max_daily_drawdown': 500.0,
            'max_daily_drawdown_pct': 5.0,
            'max_leverage': 100,
            'is_drawdown_relative': True,
            'min_trading_days': 5,
            'max_trading_days': 30,
            'profit_split_pct': 80.0
        }
        
        is_valid, errors = self.ingester._validate_record(valid_plan)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Invalid plan - missing plan_id
        invalid_plan = valid_plan.copy()
        invalid_plan['plan_id'] = None
        
        is_valid, errors = self.ingester._validate_record(invalid_plan)
        self.assertFalse(is_valid)
        self.assertIn('missing_plan_id', errors)
        
        # Invalid plan - negative balance
        negative_balance = valid_plan.copy()
        negative_balance['starting_balance'] = -1000.0
        
        is_valid, errors = self.ingester._validate_record(negative_balance)
        self.assertFalse(is_valid)
        self.assertIn('negative_starting_balance', errors)
        
        # Invalid plan - percentage out of range
        invalid_pct = valid_plan.copy()
        invalid_pct['profit_target_pct'] = 150.0  # > 100%
        
        is_valid, errors = self.ingester._validate_record(invalid_pct)
        self.assertFalse(is_valid)
        self.assertIn('profit_target_pct_out_of_range', errors)
    
    def test_column_mapping(self):
        """Test CSV column name mapping."""
        # Create CSV with various column name formats
        data = [{
            'Plan ID': 'PLAN123',
            'Plan Name': 'Test Plan',
            'Type': 'challenge',
            'Starting Balance': 10000,
            'Profit Target %': 10.0,
            'Max Drawdown %': 10.0,
            'Max Daily Drawdown %': 5.0,
            'Max Leverage': 100,
            'Is Drawdown Relative': 'true',
            'Min Trading Days': 5,
            'Profit Split %': 80.0
        }]
        
        csv_path = self.create_test_csv('test_plans.csv', data)
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Process CSV
        result = self.ingester.ingest_plans(csv_directory=str(self.csv_dir))
        
        self.assertEqual(result, 1)
        
        # Verify mapped correctly
        insert_call = mock_cursor.executemany.call_args
        inserted_data = insert_call[0][1][0]  # First record
        
        # Check mapping worked (column order depends on implementation)
        self.assertIn('PLAN123', inserted_data)  # plan_id
        self.assertIn('Test Plan', inserted_data)  # plan_name
        self.assertIn(10000, inserted_data)  # starting_balance
    
    def test_boolean_conversion(self):
        """Test boolean field conversion."""
        test_cases = [
            ('true', True),
            ('True', True),
            ('TRUE', True),
            ('yes', True),
            ('Yes', True),
            ('1', True),
            ('t', True),
            ('y', True),
            ('false', False),
            ('False', False),
            ('no', False),
            ('0', False),
            ('f', False),
            ('n', False),
            ('', False),
            (None, None)
        ]
        
        for input_val, expected in test_cases:
            data = [{
                'plan_id': 'PLAN123',
                'is_drawdown_relative': input_val
            }]
            
            df = pd.DataFrame(data)
            records = df.to_dict('records')
            transformed = self.ingester._transform_record(records[0])
            
            self.assertEqual(
                transformed['is_drawdown_relative'], 
                expected,
                f"Failed for input '{input_val}'"
            )
    
    def test_percentage_conversion(self):
        """Test percentage string to decimal conversion."""
        data = [{
            'plan_id': 'PLAN123',
            'profit_target_pct': '10%',  # String with %
            'max_drawdown_pct': 10.0,     # Already numeric
            'max_daily_drawdown_pct': '5',  # String without %
            'profit_split_pct': '80.5%'   # Decimal percentage
        }]
        
        df = pd.DataFrame(data)
        records = df.to_dict('records')
        transformed = self.ingester._transform_record(records[0])
        
        self.assertEqual(transformed['profit_target_pct'], 10.0)
        self.assertEqual(transformed['max_drawdown_pct'], 10.0)
        self.assertEqual(transformed['max_daily_drawdown_pct'], 5.0)
        self.assertEqual(transformed['profit_split_pct'], 80.5)
    
    def test_multiple_csv_files(self):
        """Test processing multiple CSV files."""
        # Create multiple CSV files
        plans1 = [
            {'plan_id': 'PLAN1', 'plan_name': 'Plan 1', 'starting_balance': 10000},
            {'plan_id': 'PLAN2', 'plan_name': 'Plan 2', 'starting_balance': 20000}
        ]
        plans2 = [
            {'plan_id': 'PLAN3', 'plan_name': 'Plan 3', 'starting_balance': 30000},
            {'plan_id': 'PLAN4', 'plan_name': 'Plan 4', 'starting_balance': 40000}
        ]
        
        self.create_test_csv('plans_2024.csv', plans1)
        self.create_test_csv('plans_2025.csv', plans2)
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Process all CSV files
        result = self.ingester.ingest_plans(csv_directory=str(self.csv_dir))
        
        self.assertEqual(result, 4)  # Total from both files
        self.assertEqual(self.ingester.metrics.files_processed, 2)
    
    def test_invalid_csv_handling(self):
        """Test handling of invalid CSV data."""
        # Create CSV with invalid data
        data = [
            {'plan_id': 'PLAN1', 'starting_balance': 10000},  # Valid
            {'plan_id': '', 'starting_balance': 20000},       # Missing plan_id
            {'plan_id': 'PLAN3', 'starting_balance': 'invalid'},  # Invalid balance
            {'plan_id': 'PLAN4', 'starting_balance': -5000},   # Negative balance
            {'plan_id': 'PLAN5', 'starting_balance': 50000}   # Valid
        ]
        
        self.create_test_csv('mixed_plans.csv', data)
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Process with validation enabled
        result = self.ingester.ingest_plans(
            csv_directory=str(self.csv_dir),
            enable_validation=True
        )
        
        # Debug the metrics
        print("\nDebug metrics:")
        print(f"  Total records: {self.ingester.metrics.total_records}")
        print(f"  New records: {self.ingester.metrics.new_records}")
        print(f"  Invalid records: {self.ingester.metrics.invalid_records}")
        print(f"  Validation errors: {dict(self.ingester.metrics.validation_errors)}")
        
        # Should only process valid records
        # The improved validation should now catch empty plan_id
        self.assertEqual(result, 2)  # Only PLAN1 and PLAN5
        self.assertEqual(self.ingester.metrics.total_records, 5)
        self.assertEqual(self.ingester.metrics.invalid_records, 3)  # PLAN2, PLAN3, PLAN4
    
    def test_duplicate_plan_handling(self):
        """Test handling of duplicate plans."""
        # Create CSV with duplicates
        data = [
            {'plan_id': 'PLAN1', 'plan_name': 'Plan 1', 'starting_balance': 10000},
            {'plan_id': 'PLAN1', 'plan_name': 'Plan 1 Dup', 'starting_balance': 10000},  # Duplicate
            {'plan_id': 'PLAN2', 'plan_name': 'Plan 2', 'starting_balance': 20000}
        ]
        
        self.create_test_csv('duplicate_plans.csv', data)
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Process with deduplication
        result = self.ingester.ingest_plans(
            csv_directory=str(self.csv_dir),
            enable_deduplication=True
        )
        
        self.assertEqual(result, 2)  # Only unique plans
        self.assertEqual(self.ingester.metrics.duplicate_records, 1)
    
    def test_specific_files_processing(self):
        """Test processing specific CSV files only."""
        # Create multiple CSV files
        self.create_test_csv('plans_old.csv', [{'plan_id': 'OLD1', 'starting_balance': 1000}])
        target_file = self.create_test_csv('plans_new.csv', [{'plan_id': 'NEW1', 'starting_balance': 2000}])
        self.create_test_csv('plans_temp.csv', [{'plan_id': 'TEMP1', 'starting_balance': 3000}])
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Process only specific file
        result = self.ingester.ingest_plans(specific_files=[target_file])
        
        self.assertEqual(result, 1)  # Only from target file
        self.assertEqual(self.ingester.metrics.files_processed, 1)
    
    def test_checkpoint_resume(self):
        """Test resuming from checkpoint for CSV processing."""
        # Create checkpoint indicating file was partially processed
        checkpoint_data = {
            'ingestion_type': 'plans',
            'last_processed_file': 'plans_2024.csv',
            'last_processed_row': 50,
            'total_records': 50,
            'timestamp': datetime.now().isoformat()
        }
        
        checkpoint_file = Path(self.temp_dir) / "plans_checkpoint.json"
        import json
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f)
        
        # Create CSV with 100 rows
        data = [{'plan_id': f'PLAN{i}', 'starting_balance': i * 1000} for i in range(100)]
        self.create_test_csv('plans_2024.csv', data)
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        self.mock_model_db.get_connection.return_value = mock_conn
        
        # Process with resume
        result = self.ingester.ingest_plans(
            csv_directory=str(self.csv_dir),
            resume_from_checkpoint=True
        )
        
        # Should process remaining 49 rows (rows 51-99, 0-indexed)
        self.assertEqual(result, 49)


if __name__ == '__main__':
    unittest.main()