#!/usr/bin/env python3
"""Check record counts in the database tables."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from utils.database import get_db_manager

def main():
    """Execute queries to check record counts and data completeness."""
    db = get_db_manager()
    
    # Basic counts and ranges
    basic_queries = {
        "Daily metrics count": "SELECT COUNT(*) as count FROM prop_trading_model.raw_metrics_daily",
        "Alltime metrics count": "SELECT COUNT(*) as count FROM prop_trading_model.raw_metrics_alltime",
        "Hourly metrics count": "SELECT COUNT(*) as count FROM prop_trading_model.raw_metrics_hourly",
        "Closed trades count": "SELECT COUNT(*) as count FROM prop_trading_model.raw_trades_closed",
        "Open trades count": "SELECT COUNT(*) as count FROM prop_trading_model.raw_trades_open",
        "Daily metrics date range": "SELECT MIN(date) as min_date, MAX(date) as max_date FROM prop_trading_model.raw_metrics_daily",
        "Hourly metrics date range": "SELECT MIN(date) as min_date, MAX(date) as max_date FROM prop_trading_model.raw_metrics_hourly",
        "Closed trades date range": "SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date FROM prop_trading_model.raw_trades_closed"
    }
    
    # Data quality checks for intelligent pipeline
    quality_queries = {
        "Accounts with missing daily data": """
            SELECT COUNT(DISTINCT a.account_id) as missing_accounts
            FROM prop_trading_model.raw_metrics_alltime a
            LEFT JOIN prop_trading_model.raw_metrics_daily d ON a.account_id = d.account_id
            WHERE d.account_id IS NULL AND a.first_trade_date IS NOT NULL
        """,
        "Recent dates missing hourly data": """
            SELECT COUNT(DISTINCT d.date) as missing_hourly_dates
            FROM prop_trading_model.raw_metrics_daily d
            LEFT JOIN (
                SELECT date, COUNT(DISTINCT hour) as hour_count
                FROM prop_trading_model.raw_metrics_hourly
                GROUP BY date
                HAVING COUNT(DISTINCT hour) < 24
            ) h ON d.date = h.date
            WHERE d.date >= CURRENT_DATE - INTERVAL '7 days'
            AND h.date IS NULL
        """,
        "Trades without account_id": """
            SELECT COUNT(*) as trades_without_account_id
            FROM prop_trading_model.raw_trades_closed
            WHERE account_id IS NULL
        """
    }
    
    print("Database Record Counts and Data Quality Report")
    print("=" * 60)
    
    print("\n📊 BASIC RECORD COUNTS")
    print("-" * 30)
    for description, query in basic_queries.items():
        try:
            result = db.model_db.execute_query(query)
            print(f"\n{description}:")
            if result:
                for key, value in result[0].items():
                    if isinstance(value, int):
                        print(f"  {key}: {value:,}")
                    else:
                        print(f"  {key}: {value}")
            else:
                print("  No results returned")
        except Exception as e:
            print(f"  Error: {str(e)}")
    
    print(f"\n\n🔍 DATA QUALITY CHECKS")
    print("-" * 30)
    for description, query in quality_queries.items():
        try:
            result = db.model_db.execute_query(query)
            print(f"\n{description}:")
            if result:
                for key, value in result[0].items():
                    status = "✅ Good" if value == 0 else f"⚠️  {value:,} issues found"
                    print(f"  {status}")
            else:
                print("  No results returned")
        except Exception as e:
            print(f"  Error: {str(e)}")
    
    print("\n" + "=" * 60)
    print("💡 TIP: Run the intelligent pipeline to fill any missing data gaps!")
    print("   uv run --env-file .env -- python -m src.data_ingestion.ingest_metrics_intelligent")
    print("   uv run --env-file .env -- python -m src.data_ingestion.ingest_trades_intelligent closed")
    
    db.close()

if __name__ == "__main__":
    main()