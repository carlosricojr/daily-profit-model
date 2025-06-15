#!/usr/bin/env python3
"""
Simplified staging snapshots creator for testing
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from src.utils.database import get_db_manager, close_db_connections
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class SimpleStaginSnapshots:
    def __init__(self):
        self.db_manager = get_db_manager()
        self.staging_table = "stg_accounts_daily_snapshots"
        
    def create_snapshots_for_date(self, snapshot_date: date) -> int:
        """Create simplified snapshots for testing"""
        
        # First, delete any existing snapshots for this date
        delete_query = f"DELETE FROM {self.staging_table} WHERE snapshot_date = %s"
        self.db_manager.model_db.execute_command(delete_query, (snapshot_date,))
        
        # Simplified insert query using only raw_metrics_daily
        insert_query = f"""
        INSERT INTO {self.staging_table} (
            account_id, login, snapshot_date, trader_id, plan_id, phase, status,
            starting_balance, balance, equity,
            profit_target, profit_target_pct, 
            max_daily_drawdown, max_daily_drawdown_pct,
            max_drawdown, max_drawdown_pct,
            max_leverage, is_drawdown_relative,
            days_active, days_since_last_trade,
            distance_to_profit_target, distance_to_max_drawdown,
            liquidate_friday, inactivity_period, 
            daily_drawdown_by_balance_equity, enable_consistency
        )
        SELECT 
            account_id,
            login,
            %(snapshot_date)s::date as snapshot_date,
            trader_id,
            plan_id,
            phase,
            status,
            starting_balance,
            current_balance as balance,
            current_equity as equity,
            0 as profit_target,  -- Default values for now
            0 as profit_target_pct,
            0 as max_daily_drawdown,  -- Not available in this table
            0 as max_daily_drawdown_pct,  -- Not available in this table
            max_drawdown,
            0 as max_drawdown_pct,  -- Not a direct column
            0 as max_leverage,
            FALSE as is_drawdown_relative,
            0 as days_active,
            0 as days_since_last_trade,
            0 as distance_to_profit_target,
            0 as distance_to_max_drawdown,
            FALSE as liquidate_friday,
            0 as inactivity_period,
            FALSE as daily_drawdown_by_balance_equity,
            FALSE as enable_consistency
        FROM raw_metrics_daily
        WHERE date = %(snapshot_date)s
            AND phase = 4  -- Funded accounts
            AND account_id IS NOT NULL
        """
        
        params = {"snapshot_date": snapshot_date}
        rows_affected = self.db_manager.model_db.execute_command(insert_query, params)
        logger.info(f"Created {rows_affected} snapshots for {snapshot_date}")
        return rows_affected
        

def main():
    setup_logging(log_file="create_staging_snapshots_simple")
    creator = SimpleStaginSnapshots()
    
    # Test with a single date that has data
    test_date = date(2024, 11, 20)
    rows = creator.create_snapshots_for_date(test_date)
    print(f"Created {rows} snapshots for {test_date}")
    
    close_db_connections()


if __name__ == "__main__":
    main()