"""
Create staging accounts daily snapshots by combining accounts and metrics data.
Creates the stg_accounts_daily_snapshots table for feature engineering.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Optional
import argparse

# Ensure we can import from parent directories
try:
    from ..utils.database import get_db_manager
    from ..utils.logging_config import setup_logging
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.database import get_db_manager
    from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class StagingSnapshotCreator:
    """Creates daily account snapshots in the staging layer."""

    def __init__(self):
        """Initialize the staging snapshot creator."""
        self.db_manager = get_db_manager()
        self.staging_table = "stg_accounts_daily_snapshots"

    def create_snapshots(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        force_rebuild: bool = False,
    ) -> int:
        """
        Create daily account snapshots combining accounts and metrics data.

        Args:
            start_date: Start date for snapshot creation
            end_date: End date for snapshot creation
            force_rebuild: If True, rebuild snapshots even if they exist

        Returns:
            Number of snapshot records created
        """
        start_time = datetime.now()
        total_records = 0

        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage="create_staging_snapshots",
                execution_date=datetime.now().date(),
                status="running",
                execution_time_seconds=0,
                records_processed=0,
                error_message=None,
                records_failed=0,
            )

            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)
            if not start_date:
                # Default to last 30 days
                start_date = end_date - timedelta(days=30)

            logger.info(f"Creating snapshots from {start_date} to {end_date}")

            # Process date by date
            current_date = start_date
            while current_date <= end_date:
                # Check if snapshots already exist for this date
                if not force_rebuild and self._snapshots_exist_for_date(current_date):
                    logger.info(
                        f"Snapshots already exist for {current_date}, skipping..."
                    )
                    current_date += timedelta(days=1)
                    continue

                # Create snapshots for this date
                date_records = self._create_snapshots_for_date(current_date)
                total_records += date_records
                logger.info(f"Created {date_records} snapshots for {current_date}")

                current_date += timedelta(days=1)

            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage="create_staging_snapshots",
                execution_date=datetime.now().date(),
                status="success",
                execution_time_seconds=(datetime.now() - start_time).total_seconds(),
                records_processed=total_records,
                error_message=None,
                records_failed=0,
            )

            logger.info(f"Successfully created {total_records} snapshot records")
            return total_records

        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage="create_staging_snapshots",
                execution_date=datetime.now().date(),
                status="failed",
                execution_time_seconds=(datetime.now() - start_time).total_seconds(),
                records_processed=0,
                error_message=str(e),
                records_failed=total_records,
            )
            logger.error(f"Failed to create snapshots: {str(e)}")
            raise

    def _snapshots_exist_for_date(self, check_date: date) -> bool:
        """Check if snapshots already exist for a given date."""
        query = f"""
        SELECT COUNT(*) as count 
        FROM {self.staging_table}
        WHERE snapshot_date = %s
        """
        result = self.db_manager.model_db.execute_query(query, (check_date,))
        return result[0]["count"] > 0

    def _create_snapshots_for_date(self, snapshot_date: date) -> int:
        """
        Create snapshots for all eligible accounts on a specific date.

        Combines:
        - Latest account state from raw_accounts_data
        - Daily metrics from raw_metrics_daily
        - Plan information from raw_plans_data
        """
        # Delete existing snapshots for this date if any
        delete_query = f"DELETE FROM {self.staging_table} WHERE snapshot_date = %s"
        self.db_manager.model_db.execute_command(delete_query, (snapshot_date,))

        # Query to create snapshots
        # This query gets the latest account state and joins with metrics and plans
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
        WITH latest_accounts AS (
            -- Get accounts from raw_metrics_daily for the snapshot date
            SELECT DISTINCT ON (account_id) 
                account_id, 
                login, 
                trader_id, 
                plan_id, 
                phase, 
                status,
                starting_balance, 
                current_balance, 
                current_equity,
                0.0 as profit_target_pct, -- Will get from plans 
                daily_drawdown_pct as max_daily_drawdown_pct, 
                max_drawdown_pct,
                0.0 as max_leverage, -- Not available in raw_metrics_daily
                FALSE as is_drawdown_relative, -- Default to absolute
                0 as breached, -- Assume active accounts are not breached
                0 as is_upgraded -- Assume not upgraded
            FROM raw_metrics_daily
            WHERE date = %s
                AND account_id IS NOT NULL
                AND phase = 4 -- Only funded accounts (phase 4)
            ORDER BY account_id
        ),
        account_metrics AS (
            -- Get metrics for the snapshot date
            SELECT 
                account_id,
                balance_end as day_end_balance,
                equity_end as day_end_equity
            FROM raw_metrics_daily
            WHERE date = %s
        ),
        account_history AS (
            -- Calculate days since first trade and active trading days
            SELECT 
                account_id,
                MIN(date) as first_trade_date,
                MAX(date) as last_trade_date,
                COUNT(DISTINCT date) as active_days,
                COUNT(DISTINCT CASE WHEN date <= %s THEN date END) as active_days_to_date
            FROM raw_metrics_daily
            WHERE num_trades > 0
            GROUP BY account_id
        ),
        plan_info AS (
            -- Get latest plan information
            SELECT DISTINCT ON (plan_id)
                plan_id,
                profit_target,
                max_drawdown,
                max_daily_drawdown,
                liquidate_friday,
                inactivity_period,
                daily_drawdown_by_balance_equity,
                enable_consistency
            FROM raw_plans_data
            ORDER BY plan_id, ingestion_timestamp DESC
        )
        SELECT 
            la.account_id,
            la.login,
            %s::date as snapshot_date,
            la.trader_id,
            la.plan_id,
            la.phase,
            la.status,
            la.starting_balance,
            COALESCE(am.day_end_balance, la.current_balance) as balance,
            COALESCE(am.day_end_equity, la.current_equity) as equity,
            pi.profit_target,
            la.profit_target_pct,
            pi.max_daily_drawdown,
            la.max_daily_drawdown_pct,
            pi.max_drawdown,
            la.max_drawdown_pct,
            la.max_leverage,
            la.is_drawdown_relative,
            COALESCE(ah.active_days_to_date, 0) as days_active,
            CASE 
                WHEN ah.last_trade_date IS NULL THEN NULL
                ELSE %s::date - ah.last_trade_date
            END as days_since_last_trade,
            -- Distance to profit target
            CASE 
                WHEN pi.profit_target IS NOT NULL THEN 
                    pi.profit_target - COALESCE(am.day_end_equity, la.current_equity)
                ELSE 
                    la.starting_balance * (la.profit_target_pct / 100.0) - 
                    COALESCE(am.day_end_equity, la.current_equity)
            END as distance_to_profit_target,
            -- Distance to max drawdown (simplified - would need more complex calculation in production)
            CASE
                WHEN la.is_drawdown_relative THEN
                    COALESCE(am.day_end_equity, la.current_equity) - 
                    (la.starting_balance * (1 - la.max_drawdown_pct / 100.0))
                ELSE
                    COALESCE(am.day_end_equity, la.current_equity) - 
                    (la.starting_balance - la.starting_balance * (la.max_drawdown_pct / 100.0))
            END as distance_to_max_drawdown,
            -- New plan columns
            COALESCE(pi.liquidate_friday, FALSE) as liquidate_friday,
            pi.inactivity_period,
            COALESCE(pi.daily_drawdown_by_balance_equity, FALSE) as daily_drawdown_by_balance_equity,
            COALESCE(pi.enable_consistency, FALSE) as enable_consistency
        FROM latest_accounts la
        LEFT JOIN account_metrics am ON la.account_id = am.account_id
        LEFT JOIN account_history ah ON la.account_id = ah.account_id
        LEFT JOIN plan_info pi ON la.plan_id = pi.plan_id
        -- No additional WHERE clause needed since we already filtered in latest_accounts CTE
        """

        # Execute the insert
        params = (
            snapshot_date,  # For latest_accounts CTE
            snapshot_date,  # For account_metrics CTE  
            snapshot_date,  # For account_history CTE
            snapshot_date,  # For snapshot_date field in SELECT
            snapshot_date,  # For days_since_last_trade calculation
        )
        rows_affected = self.db_manager.model_db.execute_command(insert_query, params)

        return rows_affected

    def clean_data(
        self, handle_missing: bool = True, detect_outliers: bool = True
    ) -> None:
        """
        Clean the staging data by handling missing values and outliers.

        Args:
            handle_missing: Whether to handle missing values
            detect_outliers: Whether to detect and log outliers
        """
        logger.info("Starting data cleaning process...")

        if handle_missing:
            self._handle_missing_values()

        if detect_outliers:
            self._detect_outliers()

        logger.info("Data cleaning completed")

    def _handle_missing_values(self):
        """Handle missing values in the staging table."""
        # Get data profile
        query = f"""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(current_balance) as non_null_balance,
            COUNT(current_equity) as non_null_equity,
            COUNT(days_since_first_trade) as non_null_days,
            COUNT(distance_to_profit_target) as non_null_dist_profit,
            COUNT(distance_to_max_drawdown) as non_null_dist_dd
        FROM {self.staging_table}
        """

        result = self.db_manager.model_db.execute_query(query)
        if result:
            profile = result[0]
            total = profile["total_rows"]

            logger.info(f"Missing value profile for {total} rows:")
            logger.info(
                f"  - current_balance: {total - profile['non_null_balance']} missing"
            )
            logger.info(
                f"  - current_equity: {total - profile['non_null_equity']} missing"
            )
            logger.info(
                f"  - days_since_first_trade: {total - profile['non_null_days']} missing"
            )

        # Update missing numerical values with appropriate defaults
        updates = [
            (
                "UPDATE {} SET days_since_first_trade = 0 WHERE days_since_first_trade IS NULL",
                "days_since_first_trade",
            ),
            (
                "UPDATE {} SET active_trading_days_count = 0 WHERE active_trading_days_count IS NULL",
                "active_trading_days_count",
            ),
        ]

        for update_query, field in updates:
            rows = self.db_manager.model_db.execute_command(
                update_query.format(self.staging_table)
            )
            if rows > 0:
                logger.info(f"Updated {rows} NULL values for {field}")

    def _detect_outliers(self):
        """Detect and log outliers in key fields."""
        # Query to get statistics for outlier detection
        query = f"""
        SELECT 
            PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY current_balance) as balance_p1,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY current_balance) as balance_q1,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY current_balance) as balance_median,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY current_balance) as balance_q3,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY current_balance) as balance_p99,
            AVG(current_balance) as balance_mean,
            STDDEV(current_balance) as balance_std
        FROM {self.staging_table}
        WHERE current_balance IS NOT NULL
        """

        result = self.db_manager.model_db.execute_query(query)
        if result and result[0]["balance_q1"] is not None and result[0]["balance_q3"] is not None:
            stats = result[0]

            # Calculate IQR for outlier detection
            iqr = stats["balance_q3"] - stats["balance_q1"]
            lower_bound = stats["balance_q1"] - 1.5 * iqr
            upper_bound = stats["balance_q3"] + 1.5 * iqr

            logger.info("Balance statistics:")
            logger.info(f"  - Mean: ${stats['balance_mean']:,.2f}")
            logger.info(f"  - Median: ${stats['balance_median']:,.2f}")
            logger.info(f"  - Std Dev: ${stats['balance_std']:,.2f}")
            logger.info(f"  - IQR bounds: ${lower_bound:,.2f} to ${upper_bound:,.2f}")

            # Count outliers
            outlier_query = f"""
            SELECT COUNT(*) as outlier_count
            FROM {self.staging_table}
            WHERE current_balance < %s OR current_balance > %s
            """
            outlier_result = self.db_manager.model_db.execute_query(
                outlier_query, (lower_bound, upper_bound)
            )
            if outlier_result:
                logger.info(
                    f"  - Outliers detected: {outlier_result[0]['outlier_count']}"
                )
        else:
            logger.info("No data available for outlier detection - staging table may be empty")


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(
        description="Create staging account daily snapshots"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for snapshot creation (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for snapshot creation (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild of existing snapshots",
    )
    parser.add_argument(
        "--clean-data",
        action="store_true",
        help="Run data cleaning after creating snapshots",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file="create_staging_snapshots")

    # Run snapshot creation
    creator = StagingSnapshotCreator()
    try:
        records = creator.create_snapshots(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild,
        )
        logger.info(f"Snapshot creation complete. Total records: {records}")

        # Run data cleaning if requested
        if args.clean_data:
            creator.clean_data()

    except Exception as e:
        logger.error(f"Snapshot creation failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
