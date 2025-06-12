#!/usr/bin/env python3
"""
Tests for the intelligent metrics ingestion with precise hourly detection.

This module tests the new precise hourly detection and batching logic
that identifies specific missing (account_id, date, hour) tuples.
"""

import unittest
from datetime import datetime, date, timedelta
from collections import defaultdict
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestIntelligentMetricsIngestion(unittest.TestCase):
    """Test suite for intelligent metrics ingestion functionality."""
    
    @patch('utils.database.DatabaseManager')
    @patch('utils.api_client.RiskAnalyticsAPIClient')
    def setUp(self, mock_api_client_class, mock_db_manager_class):
        """Set up test fixtures."""
        # Import here to ensure proper mocking
        from data_ingestion.ingest_metrics_intelligent import IntelligentMetricsIngester
        
        # Mock the database manager
        self.mock_db_manager = MagicMock()
        self.mock_db_manager.model_db = MagicMock()
        mock_db_manager_class.return_value = self.mock_db_manager
        
        # Mock API client
        self.mock_api_client = MagicMock()
        mock_api_client_class.return_value = self.mock_api_client
        
        # Create ingester with mocked dependencies
        self.ingester = IntelligentMetricsIngester()
        self.ingester.api_client = self.mock_api_client
        self.ingester.db_manager = self.mock_db_manager  # Ensure ingester uses our mock
        
        # Mock the transform methods to avoid complex transformation logic in tests
        self.ingester._transform_hourly_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        self.ingester._transform_daily_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        self.ingester._transform_alltime_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
    
    def test_get_missing_hourly_records(self):
        """Test the precise missing hourly record detection."""
        # Test data - 2 accounts, 2 dates = 96 possible hourly slots
        account_date_pairs = [
            ("123456", date(2024, 1, 1)),
            ("123456", date(2024, 1, 2)),
            ("789012", date(2024, 1, 1)),
            ("789012", date(2024, 1, 2))
        ]
        
        # Since the ingester catches exceptions and falls back to assuming all hours are missing,
        # we need to properly mock the execute_query to return an iterable result.
        # The query will return existing hourly records that should be excluded from missing.
        
        # Mock database response - simulate some existing hourly records
        # Missing hours: account 123456 on 2024-01-01 hours 10-23
        #               account 789012 on 2024-01-02 all hours
        existing_records = [
            {"account_id": "123456", "date": date(2024, 1, 1), "hour": h} 
            for h in range(0, 10)  # Hours 0-9 exist
        ] + [
            {"account_id": "123456", "date": date(2024, 1, 2), "hour": h} 
            for h in range(0, 24)  # All hours exist
        ] + [
            {"account_id": "789012", "date": date(2024, 1, 1), "hour": h} 
            for h in range(0, 24)  # All hours exist
        ]
        # Account 789012 on 2024-01-02 has no records (all 24 hours missing)
        
        # The query only returns existing records from hourly table
        # So we simulate the records that exist (not missing)
        self.mock_db_manager.model_db.execute_query.return_value = existing_records
        
        # Call the method
        missing_slots = self.ingester._get_missing_hourly_records(account_date_pairs)
        
        # Verify results
        # Should find: 14 hours for account 123456 on 2024-01-01 (hours 10-23)
        #            + 24 hours for account 789012 on 2024-01-02
        # Total: 38 missing slots
        self.assertEqual(len(missing_slots), 38)
        
        # Check specific missing slots
        missing_set = set(missing_slots)
        
        # Verify account 123456, 2024-01-01, hours 10-23 are missing
        for hour in range(10, 24):
            self.assertIn(("123456", date(2024, 1, 1), hour), missing_set)
        
        # Verify account 789012, 2024-01-02, all hours are missing
        for hour in range(24):
            self.assertIn(("789012", date(2024, 1, 2), hour), missing_set)
    
    def test_create_hourly_api_batches(self):
        """Test the creation of optimized API batches."""
        # Create test missing slots across different dates
        missing_slots = []
        
        # Date 1: 30 accounts with various missing hours
        date1 = date(2024, 1, 1)
        for i in range(30):
            account_id = f"ACC{i:03d}"
            for hour in [0, 6, 12, 18]:  # Each account missing 4 specific hours
                missing_slots.append((account_id, date1, hour))
        
        # Date 2: 10 accounts with all hours missing
        date2 = date(2024, 1, 2)
        for i in range(10):
            account_id = f"ACC{100+i:03d}"
            for hour in range(24):
                missing_slots.append((account_id, date2, hour))
        
        # Call the method
        api_batches = self.ingester._create_hourly_api_batches(missing_slots)
        
        # Verify batch structure
        # Date 1: 30 accounts should be split into 2 batches (25 + 5)
        # Date 2: 10 accounts in 1 batch
        # Total: 3 batches
        self.assertEqual(len(api_batches), 3)
        
        # Check batch format
        for batch in api_batches:
            self.assertIn("dates", batch)
            self.assertIn("accountIds", batch)
            self.assertIn("hours", batch)
            
            # Verify date format (YYYYMMDD)
            self.assertEqual(len(batch["dates"]), 8)
            self.assertTrue(batch["dates"].isdigit())
            
            # Verify account IDs are comma-separated
            account_list = batch["accountIds"].split(",")
            self.assertLessEqual(len(account_list), 25)  # Max 25 accounts per batch
            
            # Verify hours are all 24 hours
            self.assertEqual(batch["hours"], ",".join(str(h) for h in range(24)))
        
        # Verify date grouping
        dates_in_batches = [batch["dates"] for batch in api_batches]
        self.assertEqual(dates_in_batches.count("20240101"), 2)  # 2 batches for date1
        self.assertEqual(dates_in_batches.count("20240102"), 1)  # 1 batch for date2
    
    def test_ingest_hourly_precise_no_verification(self):
        """Test that precise ingestion processes all records without verification."""
        # Create test missing slots
        missing_slots = [
            ("123456", date(2024, 1, 1), 10),
            ("123456", date(2024, 1, 1), 11),
            ("789012", date(2024, 1, 1), 12),
        ]
        
        # Mock API response
        api_response = [
            {"accountId": "123456", "date": "20240101", "hour": 10, "netProfit": 100},
            {"accountId": "123456", "date": "20240101", "hour": 11, "netProfit": 150},
            {"accountId": "789012", "date": "20240101", "hour": 12, "netProfit": -50},
            {"accountId": "999999", "date": "20240101", "hour": 13, "netProfit": 200},  # Extra record
        ]
        
        # Mock the API client
        self.ingester.api_client.get_metrics = Mock()
        self.ingester.api_client.get_metrics.return_value = iter([api_response])
        
        # Mock the insert method to capture what's being inserted
        inserted_batches = []
        def capture_insert(batch_data, metric_type):
            inserted_batches.append(batch_data.copy())
            return len(batch_data)
        
        self.ingester._insert_batch_with_upsert = Mock(side_effect=capture_insert)
        
        # Set batch size to 3 for testing
        self.ingester.config.batch_size = 3
        
        # Call the method
        result = self.ingester._ingest_hourly_precise(missing_slots)
        
        # Verify all 4 records were processed (including the extra one)
        # This confirms no verification is happening
        self.assertEqual(result, 4)
        
        # Verify insertion was called
        self.assertEqual(len(inserted_batches), 2)  # 3 records + 1 record
        self.assertEqual(len(inserted_batches[0]), 3)  # First batch
        self.assertEqual(len(inserted_batches[1]), 1)  # Remaining record
    
    def test_performance_comparison(self):
        """Test to demonstrate the performance difference between old and new methods."""
        # Simulate a large dataset
        num_accounts = 1000
        num_dates = 30
        
        # Create account-date pairs
        account_date_pairs = []
        for i in range(num_accounts):
            account_id = f"ACC{i:04d}"
            for j in range(num_dates):
                date_val = date(2024, 1, 1) + timedelta(days=j)
                account_date_pairs.append((account_id, date_val))
        
        # Total possible hourly slots: 1000 * 30 * 24 = 720,000
        
        # Mock database to return some existing records
        # Simulate 50% of records exist (random hours missing)
        existing_records = []
        for account_id, date_val in account_date_pairs:
            for hour in range(0, 24, 2):  # Every other hour exists
                existing_records.append({
                    "account_id": account_id,
                    "date": date_val,
                    "hour": hour
                })
        
        self.mock_db_manager.model_db.execute_query.return_value = existing_records
        
        # Time the missing record detection (this would be slow with 17M records)
        import time
        start_time = time.time()
        missing_slots = self.ingester._get_missing_hourly_records(account_date_pairs[:100])  # Test with subset
        detection_time = time.time() - start_time
        
        # Create API batches
        start_time = time.time()
        api_batches = self.ingester._create_hourly_api_batches(missing_slots)
        batch_creation_time = time.time() - start_time
        
        # Verify efficiency
        self.assertLess(detection_time, 5.0)  # Should complete in under 5 seconds
        self.assertLess(batch_creation_time, 1.0)  # Batch creation should be very fast
        
        # Verify batch optimization
        # With 100 accounts * 30 dates * 12 missing hours = 36,000 missing slots
        # Should create batches grouped by date with max 25 accounts each
        # 100 accounts / 25 = 4 batches per date
        # 30 dates * 4 batches = 120 batches
        self.assertLessEqual(len(api_batches), 120)


class TestIntelligentPipelineIntegration(unittest.TestCase):
    """Test the integration of intelligent ingestion with the pipeline."""
    
    @patch('utils.database.DatabaseManager')
    @patch('utils.api_client.RiskAnalyticsAPIClient')
    def test_ingest_with_date_range_flow(self, mock_api_client_class, mock_db_manager_class):
        """Test the complete flow when a date range is provided."""
        from data_ingestion.ingest_metrics_intelligent import IntelligentMetricsIngester
        
        # Set up mocks
        mock_db = MagicMock()
        mock_db_manager = MagicMock()
        mock_db_manager.model_db = mock_db
        mock_db_manager_class.return_value = mock_db_manager
        
        mock_api_client = MagicMock()
        mock_api_client_class.return_value = mock_api_client
        
        ingester = IntelligentMetricsIngester()
        ingester.api_client = mock_api_client
        ingester.db_manager = mock_db_manager  # Ensure the ingester uses our mock
        
        # Mock the database queries in order
        # Each query result must be an iterable (list)
        mock_db.execute_query.side_effect = [
            # _get_missing_daily_dates query result
            [{"date": date(2024, 1, 1)}, {"date": date(2024, 1, 2)}],
            # _ingest_daily_for_dates will make API calls (no DB queries)
            # _get_account_ids_from_daily_range query result
            [{"account_id": "123456"}, {"account_id": "789012"}],
            # _get_account_date_pairs_from_daily query result
            [
                {"account_id": "123456", "date": date(2024, 1, 1)},
                {"account_id": "123456", "date": date(2024, 1, 2)},
                {"account_id": "789012", "date": date(2024, 1, 1)},
                {"account_id": "789012", "date": date(2024, 1, 2)}
            ],
            # _get_missing_hourly_records query result (existing records)
            []  # No existing records, so all will be missing
        ]
        
        # Mock API responses - return empty iterators
        ingester.api_client.get_metrics = Mock(return_value=iter([[]]))
        
        # Mock the insert method to prevent actual DB writes
        ingester._insert_batch_with_upsert = Mock(return_value=0)
        
        # Mock the transform methods
        ingester._transform_hourly_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        ingester._transform_daily_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        ingester._transform_alltime_metric = Mock(side_effect=lambda x: {"transformed": True, **x})
        
        # Run the flow
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 2)
        
        results = ingester.ingest_with_date_range(start_date, end_date)
        
        # Verify the flow
        self.assertIn("daily", results)
        self.assertIn("hourly", results)
        self.assertIn("alltime", results)
        
        # Verify database queries were made in correct order
        self.assertEqual(mock_db.execute_query.call_count, 4)


if __name__ == "__main__":
    unittest.main()