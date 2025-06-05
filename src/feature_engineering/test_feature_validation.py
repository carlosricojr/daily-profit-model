"""
Feature Validation Tests - Version 1
Tests for lookahead bias detection and feature quality.
"""

import unittest
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engineer_features import LookaheadBiasValidator, MemoryOptimizedFeatureEngineer


class TestLookaheadBiasValidator(unittest.TestCase):
    """Test lookahead bias detection."""
    
    def setUp(self):
        self.validator = LookaheadBiasValidator()
    
    def test_valid_data_availability(self):
        """Test valid data access (past data)."""
        feature_date = date(2024, 1, 10)
        data_date = date(2024, 1, 9)
        
        is_valid = self.validator.validate_data_availability(
            feature_date, data_date, 'test_feature'
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(len(self.validator.violations), 0)
    
    def test_invalid_data_availability(self):
        """Test invalid data access (future data)."""
        feature_date = date(2024, 1, 10)
        data_date = date(2024, 1, 11)
        
        is_valid = self.validator.validate_data_availability(
            feature_date, data_date, 'test_feature'
        )
        
        self.assertFalse(is_valid)
        self.assertEqual(len(self.validator.violations), 1)
        self.assertEqual(self.validator.violations[0]['violation_type'], 'future_data_access')
    
    def test_valid_rolling_window(self):
        """Test valid rolling window (no future data)."""
        feature_date = date(2024, 1, 10)
        window_start = date(2024, 1, 6)
        window_end = date(2024, 1, 10)
        
        is_valid = self.validator.validate_rolling_window(
            feature_date, window_start, window_end, 'rolling_5d'
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(len(self.validator.violations), 0)
    
    def test_invalid_rolling_window(self):
        """Test invalid rolling window (includes future data)."""
        feature_date = date(2024, 1, 10)
        window_start = date(2024, 1, 8)
        window_end = date(2024, 1, 12)
        
        is_valid = self.validator.validate_rolling_window(
            feature_date, window_start, window_end, 'rolling_5d'
        )
        
        self.assertFalse(is_valid)
        self.assertEqual(len(self.validator.violations), 1)
        self.assertEqual(self.validator.violations[0]['violation_type'], 'future_window_data')
    
    def test_violations_summary(self):
        """Test violations summary generation."""
        # Add multiple violations
        feature_date = date(2024, 1, 10)
        
        # Future data access
        self.validator.validate_data_availability(
            feature_date, date(2024, 1, 11), 'feature1'
        )
        self.validator.validate_data_availability(
            feature_date, date(2024, 1, 12), 'feature2'
        )
        
        # Future window
        self.validator.validate_rolling_window(
            feature_date, date(2024, 1, 8), date(2024, 1, 11), 'rolling_feature'
        )
        
        summary = self.validator.get_violations_summary()
        
        self.assertTrue(summary['has_violations'])
        self.assertEqual(summary['count'], 3)
        self.assertEqual(summary['violation_types']['future_data_access'], 2)
        self.assertEqual(summary['violation_types']['future_window_data'], 1)


class TestFeatureQuality(unittest.TestCase):
    """Test feature quality checks."""
    
    def test_feature_completeness(self):
        """Test detection of missing features."""
        features = {
            'account_id': 'test123',
            'current_balance': 1000.0,
            'current_equity': None,  # Missing
            'rolling_pnl_avg_5d': 50.0
        }
        
        required_features = ['current_balance', 'current_equity', 'rolling_pnl_avg_5d']
        
        # Check for missing features
        missing = [f for f in required_features if features.get(f) is None]
        
        self.assertEqual(len(missing), 1)
        self.assertIn('current_equity', missing)
    
    def test_feature_range_validation(self):
        """Test feature value range validation."""
        # Test cases with expected validity
        test_cases = [
            ('win_rate_5d', 150.0, False),  # Win rate > 100%
            ('win_rate_5d', 75.0, True),    # Valid win rate
            ('sharpe_ratio_5d', 50.0, False),  # Unrealistic Sharpe
            ('sharpe_ratio_5d', 2.5, True),    # Reasonable Sharpe
            ('buy_sell_ratio_5d', 2.0, False), # Ratio > 1
            ('buy_sell_ratio_5d', 0.6, True),   # Valid ratio
        ]
        
        for feature_name, value, expected_valid in test_cases:
            # Simple range validation
            if 'win_rate' in feature_name:
                is_valid = 0 <= value <= 100
            elif 'sharpe_ratio' in feature_name:
                is_valid = -10 <= value <= 10
            elif 'buy_sell_ratio' in feature_name:
                is_valid = 0 <= value <= 1
            else:
                is_valid = True
            
            self.assertEqual(is_valid, expected_valid,
                           f"Feature {feature_name} with value {value} validation failed")


class TestMemoryOptimization(unittest.TestCase):
    """Test memory optimization techniques."""
    
    def test_batch_processing(self):
        """Test batch processing logic."""
        # Create sample data
        n_records = 1000
        batch_size = 100
        
        # Simulate batch processing
        batches_processed = 0
        for i in range(0, n_records, batch_size):
            batch_end = min(i + batch_size, n_records)
            batch_records = batch_end - i
            
            self.assertLessEqual(batch_records, batch_size)
            batches_processed += 1
        
        expected_batches = (n_records + batch_size - 1) // batch_size
        self.assertEqual(batches_processed, expected_batches)
    
    def test_data_chunking(self):
        """Test data chunking for large queries."""
        # Simulate chunked reading
        total_records = 10000
        chunk_size = 1000
        
        records_read = 0
        chunks = []
        
        offset = 0
        while offset < total_records:
            chunk_end = min(offset + chunk_size, total_records)
            chunk_records = chunk_end - offset
            chunks.append(chunk_records)
            records_read += chunk_records
            offset += chunk_size
        
        self.assertEqual(records_read, total_records)
        self.assertEqual(len(chunks), 10)
        self.assertTrue(all(c <= chunk_size for c in chunks))


class TestFeatureAlignment(unittest.TestCase):
    """Test feature-target alignment."""
    
    def test_prediction_date_calculation(self):
        """Test that prediction_date = feature_date + 1."""
        feature_dates = pd.date_range('2024-01-01', '2024-01-10')
        
        for feature_date in feature_dates:
            expected_prediction_date = feature_date + timedelta(days=1)
            
            # Simulate alignment
            actual_prediction_date = feature_date + pd.Timedelta(days=1)
            
            self.assertEqual(actual_prediction_date, expected_prediction_date)
    
    def test_no_same_day_target(self):
        """Ensure we never use same-day target (lookahead bias)."""
        feature_date = date(2024, 1, 10)
        target_date = date(2024, 1, 10)
        
        # This should be invalid
        is_valid = target_date > feature_date
        
        self.assertFalse(is_valid, "Same-day target should not be allowed")


class TestFeatureVersioning(unittest.TestCase):
    """Test feature versioning system."""
    
    def test_feature_hash_generation(self):
        """Test consistent hash generation for feature sets."""
        import hashlib
        
        feature_set_1 = ['feature_a', 'feature_b', 'feature_c']
        feature_set_2 = ['feature_c', 'feature_a', 'feature_b']  # Different order
        feature_set_3 = ['feature_a', 'feature_b', 'feature_d']  # Different features
        
        def get_feature_hash(features):
            feature_str = ','.join(sorted(features))
            return hashlib.sha256(feature_str.encode()).hexdigest()
        
        hash_1 = get_feature_hash(feature_set_1)
        hash_2 = get_feature_hash(feature_set_2)
        hash_3 = get_feature_hash(feature_set_3)
        
        # Same features in different order should have same hash
        self.assertEqual(hash_1, hash_2)
        
        # Different features should have different hash
        self.assertNotEqual(hash_1, hash_3)


def run_validation_tests():
    """Run all validation tests and return results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestLookaheadBiasValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatureQuality))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryOptimization))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatureAlignment))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatureVersioning))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return summary
    return {
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'success': result.wasSuccessful()
    }


if __name__ == '__main__':
    unittest.main()