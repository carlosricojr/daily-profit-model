#!/usr/bin/env python3
"""
Test the trade count checking functionality.
Validates that API trade counts match expected values.
"""

import sys
from datetime import date
from pathlib import Path

# Add src directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from utils.api_client import RiskAnalyticsAPIClient
from utils.database import get_db_manager
from utils.logging_config import get_logger

logger = get_logger(__name__)


def test_trade_count_api():
    """Test that the trade count API method returns expected values."""
    api_client = RiskAnalyticsAPIClient()
    
    try:
        # Test data with expected counts
        test_cases = [
            {
                "date": date(2024, 1, 1),
                "expected_closed": 2139,
                "expected_open": 0,
            },
            {
                "date": date(2025, 6, 9),
                "expected_closed": 26956,
                "expected_open": 14422,
            },
            {
                "date": date(2025, 6, 10),
                "expected_closed": 30956,
                "expected_open": 14017,
            },
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            test_date = test_case["date"]
            date_str = api_client.format_date(test_date)
            
            # Test closed trades count
            closed_count = api_client.get_trade_count(
                trade_type="closed",
                trade_date=date_str
            )
            
            if closed_count == test_case["expected_closed"]:
                logger.info(f"✓ {test_date} closed trades: {closed_count} (expected: {test_case['expected_closed']})")
            else:
                logger.error(f"✗ {test_date} closed trades: {closed_count} (expected: {test_case['expected_closed']})")
                all_passed = False
            
            # Test open trades count
            open_count = api_client.get_trade_count(
                trade_type="open",
                trade_date=date_str
            )
            
            if open_count == test_case["expected_open"]:
                logger.info(f"✓ {test_date} open trades: {open_count} (expected: {test_case['expected_open']})")
            else:
                logger.error(f"✗ {test_date} open trades: {open_count} (expected: {test_case['expected_open']})")
                all_passed = False
        
        # Assert all tests passed
        assert all_passed, "Some trade count tests failed"
        
        logger.info("All trade count API tests passed!")
        
    except Exception as e:
        logger.error(f"Trade count API test failed: {str(e)}")
        raise
    finally:
        api_client.close()


def test_trade_count_db_comparison():
    """Test that we can compare API counts with database counts."""
    api_client = RiskAnalyticsAPIClient()
    db_manager = get_db_manager()
    
    try:
        # Test with a recent date to check DB comparison functionality
        test_date = date(2025, 6, 10)
        date_str = api_client.format_date(test_date)
        
        # Get API count
        api_closed_count = api_client.get_trade_count(
            trade_type="closed",
            trade_date=date_str
        )
        
        # Get DB count
        db_result = db_manager.model_db.execute_query(
            "SELECT COUNT(*) as count FROM prop_trading_model.raw_trades_closed WHERE trade_date = %s",
            [test_date]
        )
        db_closed_count = db_result[0]["count"] if db_result else 0
        
        # Log the comparison
        logger.info(f"API vs DB for {test_date} closed trades: API={api_closed_count}, DB={db_closed_count}")
        
        # Check if we need to fetch more data
        if api_closed_count > db_closed_count:
            logger.warning(f"Missing {api_closed_count - db_closed_count} closed trades for {test_date}")
        elif api_closed_count == db_closed_count:
            logger.info(f"Database is up to date for {test_date} closed trades")
        
        # Test open trades as well
        api_open_count = api_client.get_trade_count(
            trade_type="open",
            trade_date=date_str
        )
        
        db_result = db_manager.model_db.execute_query(
            "SELECT COUNT(*) as count FROM prop_trading_model.raw_trades_open WHERE trade_date = %s",
            [test_date]
        )
        db_open_count = db_result[0]["count"] if db_result else 0
        
        logger.info(f"API vs DB for {test_date} open trades: API={api_open_count}, DB={db_open_count}")
        
        if api_open_count > db_open_count:
            logger.warning(f"Missing {api_open_count - db_open_count} open trades for {test_date}")
        elif api_open_count == db_open_count:
            logger.info(f"Database is up to date for {test_date} open trades")
        
    except Exception as e:
        logger.error(f"Trade count DB comparison test failed: {str(e)}")
        raise
    finally:
        api_client.close()
        db_manager.close()


def run_trade_count_tests():
    """Run all trade count tests."""
    logger.info("="*60)
    logger.info("Running trade count tests...")
    logger.info("="*60)
    
    tests = [
        ("API Count Test", test_trade_count_api),
        ("DB Comparison Test", test_trade_count_db_comparison),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            logger.info(f"\nRunning {test_name}...")
            test_func()
            results.append((test_name, True, None))
            logger.info(f"{test_name} passed ✓")
        except Exception as e:
            results.append((test_name, False, str(e)))
            logger.error(f"{test_name} failed: {str(e)}")
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("TEST SUMMARY")
    logger.info("="*60)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        logger.info(f"{test_name}: {status}")
        if error:
            logger.info(f"  Error: {error}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = run_trade_count_tests()
    sys.exit(0 if success else 1)