#!/usr/bin/env python3
"""
Simplified staging snapshots creator that works with actual database structure
"""
import argparse
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from utils.database import get_db_manager, close_db_connections
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class StagingSnapshotsCreator:
    """Creates daily snapshots of account states for feature engineering."""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        self.staging_table = "stg_accounts_daily_snapshots"
        self.raw_metrics_alltime_table = "raw_metrics_alltime"
        self.raw_metrics_daily_table = "raw_metrics_daily"
        self.raw_metrics_hourly_table = "raw_metrics_hourly"
        self.raw_plans_data_table = "raw_plans_data"
        self.raw_regimes_daily_table = "raw_regimes_daily"
        
    def create_snapshots(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        force_rebuild: bool = False,
    ) -> int:
        """Create staging snapshots for the specified date range."""
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
                # Default to January 1st 2024
                start_date = date(2024, 1, 1)

            logger.info(f"Creating snapshots from {start_date} to {end_date}")

            # Process each date
            current_date = start_date
            while current_date <= end_date:
                if force_rebuild or not self._snapshots_exist_for_date(current_date):
                    date_records = self._create_snapshots_for_date(current_date)
                    total_records += date_records
                    logger.info(f"Created {date_records} snapshots for {current_date}")
                else:
                    logger.info(f"Snapshots already exist for {current_date}, skipping")

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
        """Return True if each account_id has exactly *one* row in both
        `raw_metrics_daily` (for the given date) and `stg_accounts_daily_snapshots`
        (for the same date), and the set of account_ids matches between the two
        tables.  Otherwise return False.

        This guarantees a 1-to-1 correspondence between the source metrics and
        the already-materialised snapshots; if anything is missing or
        duplicated we must rebuild the snapshots for that day.
        """

        validation_query = f"""
        WITH
            -- Raw metrics counts per account for the date
            raw_counts AS (
                SELECT account_id, COUNT(*)        AS cnt
                FROM {self.raw_metrics_daily_table}
                WHERE date = %(check_date)s
                GROUP BY account_id
            ),
            -- Snapshot counts per account for the same date
            stg_counts AS (
                SELECT account_id, COUNT(*)        AS cnt
                FROM {self.staging_table}
                WHERE snapshot_date = %(check_date)s
                GROUP BY account_id
            ),
            -- Problem #1: duplicates (cnt <> 1) in either table
            dupes AS (
                SELECT account_id FROM raw_counts WHERE cnt <> 1
                UNION
                SELECT account_id FROM stg_counts WHERE cnt <> 1
            ),
            -- Problem #2: account_ids present in one table but not the other
            mismatched AS (
                SELECT rc.account_id
                FROM raw_counts rc
                FULL OUTER JOIN stg_counts sc USING (account_id)
                WHERE rc.account_id IS NULL OR sc.account_id IS NULL
            )
        SELECT (
            NOT EXISTS (SELECT 1 FROM dupes)       -- no duplicates
            AND NOT EXISTS (SELECT 1 FROM mismatched) -- same account set
            AND EXISTS (SELECT 1 FROM raw_counts)  -- at least one account present
        ) AS is_consistent
        """

        result = self.db_manager.model_db.execute_query(validation_query, {"check_date": check_date})
        return bool(result and result[0]["is_consistent"])

    def _create_snapshots_for_date(self, snapshot_date: date) -> int:
        """Create snapshots for a specific date."""
        # Delete existing snapshots for this date if any
        delete_query = f"DELETE FROM {self.staging_table} WHERE snapshot_date = %(snapshot_date)s"
        self.db_manager.model_db.execute_command(delete_query, {"snapshot_date": snapshot_date})

        # Simplified insert query using only raw_metrics_daily and raw_plans_data
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
        WITH account_metrics AS (
            -- Get accounts and their metrics for the snapshot date
            SELECT 
                account_id,
                login,
                trader_id,
                plan_id,
                phase,
                status,
                starting_balance,
                current_balance,
                current_equity,
                max_drawdown,
                -- Calculate active days up to this date
                (SELECT COUNT(DISTINCT date) 
                 FROM raw_metrics_daily rmd2 
                 WHERE rmd2.account_id = rmd.account_id 
                   AND rmd2.date <= rmd.date
                   AND rmd2.num_trades > 0) as days_active,
                -- Calculate days since last trade
                CASE 
                    WHEN EXISTS (
                        SELECT 1 FROM raw_metrics_daily rmd3 
                        WHERE rmd3.account_id = rmd.account_id 
                          AND rmd3.date <= rmd.date
                          AND rmd3.num_trades > 0
                    ) THEN 
                        rmd.date - (
                            SELECT MAX(date) 
                            FROM raw_metrics_daily rmd4 
                            WHERE rmd4.account_id = rmd.account_id 
                              AND rmd4.date <= rmd.date
                              AND rmd4.num_trades > 0
                        )
                    ELSE NULL
                END as days_since_last_trade
            FROM raw_metrics_daily rmd
            WHERE date = %(snapshot_date)s
                AND account_id IS NOT NULL
                AND phase = 4  -- Funded accounts only
        ),
        plan_info AS (
            -- Get latest plan information
            SELECT DISTINCT ON (plan_id)
                plan_id,
                profit_target,
                max_drawdown as plan_max_drawdown,
                max_daily_drawdown,
                liquidate_friday,
                inactivity_period,
                daily_drawdown_by_balance_equity,
                enable_consistency
            FROM raw_plans_data
            ORDER BY plan_id, ingestion_timestamp DESC
        )
        SELECT 
            am.account_id,
            am.login,
            %(snapshot_date)s::date as snapshot_date,
            am.trader_id,
            am.plan_id,
            am.phase,
            am.status,
            am.starting_balance,
            am.current_balance as balance,
            am.current_equity as equity,
            COALESCE(pi.profit_target, 0) as profit_target,
            CASE 
                WHEN am.starting_balance > 0 AND pi.profit_target IS NOT NULL 
                THEN ((pi.profit_target - am.starting_balance) / am.starting_balance * 100)
                ELSE 0 
            END as profit_target_pct,
            COALESCE(pi.max_daily_drawdown, 0) as max_daily_drawdown,
            0 as max_daily_drawdown_pct,  -- Would need to calculate from historical data
            COALESCE(am.max_drawdown, 0) as max_drawdown,
            CASE 
                WHEN am.starting_balance > 0 
                THEN (am.max_drawdown / am.starting_balance * 100)
                ELSE 0 
            END as max_drawdown_pct,
            0 as max_leverage,  -- Not available in raw_metrics_daily
            FALSE as is_drawdown_relative,  -- Default to absolute
            COALESCE(am.days_active, 0) as days_active,
            COALESCE(am.days_since_last_trade, 0) as days_since_last_trade,
            -- Distance to profit target
            CASE 
                WHEN pi.profit_target IS NOT NULL 
                THEN pi.profit_target - am.current_equity
                ELSE 0
            END as distance_to_profit_target,
            -- Distance to max drawdown (simplified)
            CASE
                WHEN pi.plan_max_drawdown IS NOT NULL
                THEN am.current_equity - (am.starting_balance - pi.plan_max_drawdown)
                ELSE am.current_equity - (am.starting_balance - am.max_drawdown)
            END as distance_to_max_drawdown,
            COALESCE(pi.liquidate_friday, FALSE) as liquidate_friday,
            COALESCE(pi.inactivity_period, 0) as inactivity_period,
            COALESCE(pi.daily_drawdown_by_balance_equity, FALSE) as daily_drawdown_by_balance_equity,
            COALESCE(pi.enable_consistency, FALSE) as enable_consistency
        FROM account_metrics am
        LEFT JOIN plan_info pi ON am.plan_id = pi.plan_id
        """
        
        params = {"snapshot_date": snapshot_date}
        rows_affected = self.db_manager.model_db.execute_command(insert_query, params)
        
        return rows_affected


def main():
    parser = argparse.ArgumentParser(description="Create staging snapshots for accounts")
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild even if snapshots exist",
    )
    parser.add_argument(
        "--clean-data",
        action="store_true", 
        help="Clean data after creating snapshots (compatibility argument)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level=args.log_level, log_file="create_staging_snapshots")
    
    try:
        creator = StagingSnapshotsCreator()
        records = creator.create_snapshots(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild,
        )
        logger.info(f"Total snapshots created: {records}")
    except Exception as e:
        logger.error(f"Snapshot creation failed: {e}")
        raise
    finally:
        close_db_connections()


if __name__ == "__main__":
    main()