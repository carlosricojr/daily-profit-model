#!/usr/bin/env python3
"""
Quick test to verify trades ingester validation is working correctly.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data_ingestion.ingest_trades import TradesIngester, IngestionMetrics


def test_validation():
    """Test that validation is working."""
    ingester = TradesIngester(enable_validation=True)

    # Test valid trade (using actual API field names)
    valid_trade = {
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

    is_valid, errors = ingester._validate_trade_record(valid_trade, "closed")
    print(f"Valid trade validation: {is_valid}, errors: {errors}")
    assert is_valid
    assert len(errors) == 0

    # Test invalid trade - missing required field
    invalid_trade1 = valid_trade.copy()
    del invalid_trade1["position"]

    is_valid, errors = ingester._validate_trade_record(invalid_trade1, "closed")
    print(f"Invalid trade (missing position) validation: {is_valid}, errors: {errors}")
    assert not is_valid
    assert "Missing required field: position" in errors

    # Test invalid trade - negative lots
    invalid_trade2 = valid_trade.copy()
    invalid_trade2["lots"] = -0.1

    is_valid, errors = ingester._validate_trade_record(invalid_trade2, "closed")
    print(f"Invalid trade (negative lots) validation: {is_valid}, errors: {errors}")
    assert not is_valid
    assert "Lots must be positive" in errors

    # Test invalid trade - bad side
    invalid_trade3 = valid_trade.copy()
    invalid_trade3["side"] = "invalid_side"

    is_valid, errors = ingester._validate_trade_record(invalid_trade3, "closed")
    print(f"Invalid trade (bad side) validation: {is_valid}, errors: {errors}")
    assert not is_valid
    assert any("Invalid side" in error for error in errors)

    # Test metrics tracking
    metrics = IngestionMetrics()
    print(f"\nInitial metrics: {metrics}")

    # Simulate validation errors
    metrics.invalid_records += 1
    metrics.validation_errors["Missing required field: position"] += 1
    metrics.validation_errors["Lots must be positive"] += 1

    print(f"Updated metrics - invalid records: {metrics.invalid_records}")
    print(f"Validation errors: {dict(metrics.validation_errors)}")

    print("\n✅ All validation tests passed!")


if __name__ == "__main__":
    test_validation()
