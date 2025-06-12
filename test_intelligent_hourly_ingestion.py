#!/usr/bin/env python3
"""
Test script for the new intelligent hourly metrics ingestion.

This script validates that the new precise hourly detection and batching
logic works correctly and is more efficient than the previous implementation.
"""

import os
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from data_ingestion.ingest_metrics_intelligent import IntelligentMetricsIngester
from utils.database import DatabaseManager
from utils.logging_config import setup_logging, get_logger

# Set up logging
setup_logging(log_level="DEBUG", log_file="test_intelligent_hourly")
logger = get_logger(__name__)


def test_missing_hourly_detection():
    """Test the precise missing hourly record detection."""
    logger.info("=" * 60)
    logger.info("Testing Precise Missing Hourly Detection")
    logger.info("=" * 60)
    
    # Initialize ingester
    ingester = IntelligentMetricsIngester()
    db_manager = DatabaseManager()
    
    try:
        # Get a sample of account-date pairs from recent data
        query = """
            SELECT DISTINCT account_id, date
            FROM prop_trading_model.raw_metrics_daily
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            AND date < CURRENT_DATE
            ORDER BY date DESC, account_id
            LIMIT 10
        """
        
        results = db_manager.model_db.execute_query(query)
        account_date_pairs = [(row["account_id"], row["date"]) for row in results]
        
        if not account_date_pairs:
            logger.warning("No recent daily metrics found for testing")
            return
        
        logger.info(f"Testing with {len(account_date_pairs)} account-date pairs")
        
        # Test the new precise detection method
        missing_slots = ingester._get_missing_hourly_records(account_date_pairs)
        
        logger.info(f"Found {len(missing_slots)} specific missing hourly records")
        
        # Group by account-date to see the pattern
        missing_by_account_date = defaultdict(list)
        for account_id, date_val, hour in missing_slots:
            missing_by_account_date[(account_id, date_val)].append(hour)
        
        # Display sample results
        logger.info("\nSample of missing hourly records:")
        for i, ((account_id, date_val), hours) in enumerate(missing_by_account_date.items()):
            if i >= 5:  # Show only first 5
                break
            logger.info(f"  Account {account_id}, Date {date_val}: Missing hours {sorted(hours)}")
        
        # Test batch creation
        if missing_slots:
            api_batches = ingester._create_hourly_api_batches(missing_slots)
            logger.info(f"\nCreated {len(api_batches)} API batches from {len(missing_slots)} missing slots")
            
            # Show batch statistics
            total_accounts = sum(len(batch['accountIds'].split(',')) for batch in api_batches)
            logger.info(f"Total account-date combinations in batches: {total_accounts}")
            logger.info(f"Average accounts per batch: {total_accounts / len(api_batches):.1f}")
            
            # Show sample batch
            if api_batches:
                logger.info("\nSample API batch:")
                sample = api_batches[0]
                logger.info(f"  Date: {sample['dates']}")
                logger.info(f"  Accounts: {len(sample['accountIds'].split(','))} accounts")
                logger.info(f"  Hours: {sample['hours']}")
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)
    finally:
        if hasattr(ingester, 'close'):
            ingester.close()
        if hasattr(db_manager, 'close'):
            db_manager.close()


def compare_methods():
    """Compare old vs new detection methods."""
    logger.info("\n" + "=" * 60)
    logger.info("Comparing Old vs New Detection Methods")
    logger.info("=" * 60)
    
    ingester = IntelligentMetricsIngester()
    
    try:
        # Get test data
        start_date = date.today() - timedelta(days=7)
        end_date = date.today() - timedelta(days=1)
        
        # Get account IDs from daily range
        account_ids = ingester._get_account_ids_from_daily_range(start_date, end_date)
        
        if not account_ids:
            logger.warning("No accounts found in date range")
            return
        
        # Limit to first 100 accounts for testing
        test_accounts = account_ids[:100]
        logger.info(f"Testing with {len(test_accounts)} accounts from {start_date} to {end_date}")
        
        # Old method: Get account-date pairs with missing hours
        import time
        start_time = time.time()
        old_missing = ingester._get_account_date_pairs_with_missing_hours(
            test_accounts, start_date, end_date
        )
        old_time = time.time() - start_time
        
        logger.info(f"\nOld method:")
        logger.info(f"  - Found {len(old_missing)} account-date pairs with missing hours")
        logger.info(f"  - Time taken: {old_time:.2f} seconds")
        logger.info(f"  - Would fetch: {len(old_missing) * 24} hourly records")
        
        # New method: Get precise missing slots
        account_date_pairs = ingester._get_account_date_pairs_from_daily(
            test_accounts, start_date, end_date
        )
        
        start_time = time.time()
        new_missing = ingester._get_missing_hourly_records(account_date_pairs)
        new_time = time.time() - start_time
        
        logger.info(f"\nNew method:")
        logger.info(f"  - Found {len(new_missing)} specific missing hourly records")
        logger.info(f"  - Time taken: {new_time:.2f} seconds")
        logger.info(f"  - Will fetch only: {len(new_missing)} hourly records")
        
        # Calculate efficiency gain
        if old_missing:
            old_fetch_count = len(old_missing) * 24
            new_fetch_count = len(new_missing)
            efficiency_gain = ((old_fetch_count - new_fetch_count) / old_fetch_count) * 100
            logger.info(f"\nEfficiency gain: {efficiency_gain:.1f}% fewer records to fetch")
            
            # Create API batches for comparison
            if new_missing:
                api_batches = ingester._create_hourly_api_batches(new_missing)
                logger.info(f"API calls needed: {len(api_batches)} batches")
        
    except Exception as e:
        logger.error(f"Comparison failed: {str(e)}", exc_info=True)
    finally:
        if hasattr(ingester, 'close'):
            ingester.close()


def test_small_ingestion():
    """Test actual ingestion with a small dataset."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Small-Scale Intelligent Hourly Ingestion")
    logger.info("=" * 60)
    
    ingester = IntelligentMetricsIngester()
    
    try:
        # Use yesterday's data for testing
        test_date = date.today() - timedelta(days=1)
        
        logger.info(f"Testing ingestion for date: {test_date}")
        
        # Run intelligent ingestion for one day
        results = ingester.ingest_with_date_range(
            start_date=test_date,
            end_date=test_date,
            force_full_refresh=False
        )
        
        logger.info("\nIngestion Results:")
        for metric_type, count in results.items():
            logger.info(f"  - {metric_type}: {count} records")
        
    except Exception as e:
        logger.error(f"Ingestion test failed: {str(e)}", exc_info=True)
    finally:
        if hasattr(ingester, 'close'):
            ingester.close()


if __name__ == "__main__":
    logger.info("Starting intelligent hourly ingestion tests...")
    
    # Run tests
    test_missing_hourly_detection()
    compare_methods()
    
    # Optional: Run actual ingestion test
    response = input("\nRun actual ingestion test? (y/n): ")
    if response.lower() == 'y':
        test_small_ingestion()
    
    logger.info("\nTests completed!")