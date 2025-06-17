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

            # Collect all dates that need (re)building first
            dates_to_process = []
            current_date = start_date
            while current_date <= end_date:
                if force_rebuild or not self._snapshots_exist_for_date(current_date):
                    dates_to_process.append(current_date)
                current_date += timedelta(days=1)

            if not dates_to_process:
                logger.info("No snapshots required – everything up-to-date.")
            else:
                # Run snapshot builds concurrently – simple thread pool using the
                # existing connection pool (thread-safe via SQLAlchemy).
                from concurrent.futures import ThreadPoolExecutor, as_completed

                max_workers = min(4, len(dates_to_process))  # keep it lightweight
                logger.info(
                    f"Building snapshots for {len(dates_to_process)} day(s) "
                    f"using {max_workers} worker(s)…"
                )

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_map = {
                        executor.submit(self._create_snapshots_for_date, d): d
                        for d in dates_to_process
                    }

                    for future in as_completed(future_map):
                        date = future_map[future]
                        try:
                            date_records = future.result()
                            total_records += date_records
                            logger.info(
                                f"Created {date_records} snapshots for {date}"
                            )
                        except Exception as exc:
                            logger.error(f"Snapshot creation failed for {date}: {exc}")
                            raise

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
        # Upsert using INSERT … ON CONFLICT to avoid a delete-then-insert round trip
        insert_query = """
        INSERT INTO prop_trading_model.stg_accounts_daily_snapshots (
            account_id, 
            login, 
            snapshot_date, 
            trader_id, 
            plan_id, 
            phase, 
            status, 
            type,
            platform, 
            broker,
            price_stream,
            country,
            starting_balance,
            days_to_next_payout, 
            todays_payouts,
            approved_payouts,
            pending_payouts,
            prior_days_balance,
            prior_days_equity,
            current_balance, 
            current_equity,
            first_trade_date,
            days_since_initial_deposit,
            days_since_first_trade,
            num_trades,
            net_profit,
            gross_profit,
            gross_loss,
            profit_target, 
            profit_target_pct, 
            max_daily_drawdown, 
            max_daily_drawdown_pct,
            max_drawdown, 
            max_drawdown_pct,
            max_leverage, 
            is_drawdown_relative,
            days_active, 
            days_since_last_trade,
            distance_to_profit_target, 
            distance_to_max_drawdown,
            liquidate_friday, 
            inactivity_period, 
            daily_drawdown_by_balance_equity, 
            enable_consistency,
            top_symbol_concentration, 
            herfindahl_index, 
            symbol_diversification_index,
            forex_pairs_ratio, 
            metals_ratio, 
            index_ratio, 
            crypto_ratio, 
            energy_ratio,
            -- Trade aggregations
            trades_last_1d, trades_last_7d, trades_last_30d,
            volume_usd_last_1d, 
            volume_usd_last_7d, 
            volume_usd_last_30d,
            profit_last_1d, 
            profit_last_7d, 
            profit_last_30d,
            unique_symbols_last_7d, 
            unique_symbols_last_30d,
            -- Trade timing patterns
            trades_morning_ratio, 
            trades_afternoon_ratio,
            trades_evening_ratio, 
            trades_weekend_ratio, 
            avg_trade_hour_of_day,
            -- Rolling metrics
            sharpe_ratio_5d, 
            sharpe_ratio_10d, 
            sharpe_ratio_20d,
            profit_volatility_5d, 
            profit_volatility_10d, 
            profit_volatility_20d,
            win_rate_5d, 
            win_rate_10d, 
            win_rate_20d,
            balance_change_5d, 
            balance_change_10d, 
            balance_change_20d,
            equity_high_water_mark, 
            days_since_equity_high,
            -- Performance metrics from raw_metrics_daily
            daily_sharpe, 
            daily_sortino,
            profit_factor, 
            success_rate,
            mean_profit, 
            median_profit,
            mean_drawdown, 
            median_drawdown,
            mean_duration, 
            median_duration,
            total_lots, 
            total_volume,
            -- Additional performance metrics
            risk_adj_profit, 
            risk_adj_ret, 
            downside_risk_adj_ret,
            gain_to_pain, 
            max_profit, 
            min_profit,
            -- Percentile and statistical metrics
            profit_perc_10, 
            profit_perc_25, 
            profit_perc_75, 
            profit_perc_90,
            std_profits, 
            expectancy,
            -- Drawdown metrics
            mean_num_trades_in_dd, 
            median_num_trades_in_dd, 
            max_num_trades_in_dd,
            -- Trade setup metrics
            std_durations, 
            mean_tp, 
            median_tp, 
            cv_tp,
            mean_sl, 
            median_sl, 
            cv_sl,
            mean_tp_vs_sl, 
            median_tp_vs_sl, 
            cv_tp_vs_sl,
            -- Volume and position metrics
            std_volumes, 
            mean_num_open_pos, 
            max_num_open_pos,
            mean_val_open_pos, 
            max_val_open_pos, 
            max_val_to_eqty_open_pos,
            -- Consecutive wins/losses metrics
            mean_num_consec_wins, 
            max_num_consec_wins,
            mean_num_consec_losses, 
            max_num_consec_losses,
            max_val_consec_wins, 
            max_val_consec_losses
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
                type,
                starting_balance,
                current_balance,
                current_equity,
                max_drawdown,
                platform,
                broker,
                country,
                -- Performance metrics from raw_metrics_daily
                daily_sharpe,
                daily_sortino,
                profit_factor,
                success_rate,
                mean_profit,
                median_profit,
                mean_drawdown,
                median_drawdown,
                mean_duration,
                median_duration,
                total_lots,
                total_volume,
                -- Additional performance metrics
                risk_adj_profit,
                risk_adj_ret,
                downside_risk_adj_ret,
                gain_to_pain,
                max_profit,
                min_profit,
                -- Percentile and statistical metrics
                profit_perc_10,
                profit_perc_25,
                profit_perc_75,
                profit_perc_90,
                std_profits,
                expectancy,
                -- Drawdown metrics
                mean_num_trades_in_dd,
                median_num_trades_in_dd,
                max_num_trades_in_dd,
                -- Trade setup metrics
                std_durations,
                mean_tp,
                median_tp,
                cv_tp,
                mean_sl,
                median_sl,
                cv_sl,
                mean_tp_vs_sl,
                median_tp_vs_sl,
                cv_tp_vs_sl,
                -- Volume and position metrics
                std_volumes,
                mean_num_open_pos,
                max_num_open_pos,
                mean_val_open_pos,
                max_val_open_pos,
                max_val_to_eqty_open_pos,
                -- Consecutive wins/losses metrics
                mean_num_consec_wins,
                max_num_consec_wins,
                mean_num_consec_losses,
                max_num_consec_losses,
                max_val_consec_wins,
                max_val_consec_losses,
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
        ),
        trade_aggregations AS (
            SELECT 
                account_id,
                -- Recent activity
                COUNT(CASE WHEN DATE(close_time) = %(snapshot_date)s THEN 1 END) as trades_last_1d,
                COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '7 days' THEN 1 END) as trades_last_7d,
                COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN 1 END) as trades_last_30d,
                
                COALESCE(SUM(CASE WHEN DATE(close_time) = %(snapshot_date)s THEN volume_usd END), 0) as volume_usd_last_1d,
                COALESCE(SUM(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '7 days' THEN volume_usd END), 0) as volume_usd_last_7d,
                COALESCE(SUM(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN volume_usd END), 0) as volume_usd_last_30d,
                
                COALESCE(SUM(CASE WHEN DATE(close_time) = %(snapshot_date)s THEN profit END), 0) as profit_last_1d,
                COALESCE(SUM(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '7 days' THEN profit END), 0) as profit_last_7d,
                COALESCE(SUM(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN profit END), 0) as profit_last_30d,
                
                COUNT(DISTINCT CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '7 days' THEN std_symbol END) as unique_symbols_last_7d,
                COUNT(DISTINCT CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN std_symbol END) as unique_symbols_last_30d,
                
                -- Timing patterns (EST+7 = Asia/Singapore timezone)
                AVG(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' 
                         THEN EXTRACT(hour FROM open_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Singapore') END) as avg_trade_hour_of_day,
                
                COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' 
                           AND EXTRACT(hour FROM open_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Singapore') BETWEEN 6 AND 11 THEN 1 END)::numeric / 
                NULLIF(COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN 1 END), 0) as trades_morning_ratio,
                
                COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' 
                           AND EXTRACT(hour FROM open_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Singapore') BETWEEN 12 AND 17 THEN 1 END)::numeric / 
                NULLIF(COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN 1 END), 0) as trades_afternoon_ratio,
                
                COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' 
                           AND EXTRACT(hour FROM open_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Singapore') BETWEEN 18 AND 23 THEN 1 END)::numeric / 
                NULLIF(COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN 1 END), 0) as trades_evening_ratio,
                
                COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' 
                           AND EXTRACT(dow FROM open_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Singapore') IN (0, 6) THEN 1 END)::numeric / 
                NULLIF(COUNT(CASE WHEN DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days' THEN 1 END), 0) as trades_weekend_ratio
                
            FROM prop_trading_model.raw_trades_closed
            WHERE account_id IN (SELECT account_id FROM account_metrics)
                AND DATE(close_time) <= %(snapshot_date)s
                AND DATE(close_time) >= %(snapshot_date)s - INTERVAL '30 days'
            GROUP BY account_id
        ),
        rolling_metrics AS (
            -- Calculate rolling window metrics using window functions
            SELECT * FROM (
                SELECT 
                    account_id,
                    date,
                -- 5-day rolling Sharpe  
                AVG(daily_sharpe) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                ) as sharpe_ratio_5d,
                -- 10-day rolling Sharpe
                AVG(daily_sharpe) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                ) as sharpe_ratio_10d,
                -- 20-day rolling Sharpe
                AVG(daily_sharpe) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as sharpe_ratio_20d,
                
                -- Profit volatility using window functions
                STDDEV(net_profit) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                ) as profit_volatility_5d,
                STDDEV(net_profit) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                ) as profit_volatility_10d,
                STDDEV(net_profit) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as profit_volatility_20d,
                
                -- Win rates using window functions
                AVG(success_rate) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                ) as win_rate_5d,
                AVG(success_rate) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                ) as win_rate_10d,
                AVG(success_rate) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                ) as win_rate_20d,
                
                -- Balance changes using window functions
                (current_balance - LAG(current_balance, 5) OVER (
                    PARTITION BY account_id ORDER BY date
                )) / NULLIF(LAG(current_balance, 5) OVER (
                    PARTITION BY account_id ORDER BY date
                ), 0) as balance_change_5d,
                
                (current_balance - LAG(current_balance, 10) OVER (
                    PARTITION BY account_id ORDER BY date
                )) / NULLIF(LAG(current_balance, 10) OVER (
                    PARTITION BY account_id ORDER BY date
                ), 0) as balance_change_10d,
                
                (current_balance - LAG(current_balance, 20) OVER (
                    PARTITION BY account_id ORDER BY date
                )) / NULLIF(LAG(current_balance, 20) OVER (
                    PARTITION BY account_id ORDER BY date
                ), 0) as balance_change_20d,
                
                -- High water mark using window functions
                MAX(current_equity) OVER (
                    PARTITION BY account_id 
                    ORDER BY date 
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) as equity_high_water_mark,
                
                -- Keep current_equity to use in the calculation
                current_equity
                
            FROM prop_trading_model.raw_metrics_daily rmd
            WHERE account_id IN (SELECT account_id FROM account_metrics)
                AND date <= %(snapshot_date)s
                AND date > %(snapshot_date)s - INTERVAL '30 days'
            ) subq
            WHERE date = %(snapshot_date)s
        ),
        symbol_concentration AS (
            SELECT 
                account_id,
                -- Top symbol concentration (highest traded symbol's share)
                MAX(symbol_trade_count)::numeric / NULLIF(SUM(symbol_trade_count), 0) as top_symbol_concentration,
                
                -- Herfindahl index for diversification (sum of squared market shares)
                -- Lower values indicate more diversification (0 = perfect, 1 = single symbol)
                SUM(POWER(symbol_trade_count::numeric / total_trades, 2)) as herfindahl_index,
                
                -- Normalized entropy diversification index
                CASE 
                    WHEN COUNT(*) > 1 THEN
                        -SUM((symbol_trade_count::numeric / total_trades) * 
                             LN(symbol_trade_count::numeric / total_trades)) / LN(COUNT(*))
                    ELSE 0
                END as symbol_diversification_index,
                
                -- Asset class ratios with mutually exclusive classification
                -- Priority: Crypto > Forex > Metals > Energy > Index
                
                -- Crypto ratio
                LEAST(COALESCE(SUM(CASE WHEN symbol_class = 'crypto' THEN symbol_trade_count ELSE 0 END)::numeric / 
                NULLIF(total_trades, 0), 0), 1)::numeric(5,4) as crypto_ratio,
                
                -- Forex ratio
                LEAST(COALESCE(SUM(CASE WHEN symbol_class = 'forex' THEN symbol_trade_count ELSE 0 END)::numeric / 
                NULLIF(total_trades, 0), 0), 1)::numeric(5,4) as forex_pairs_ratio,
                
                -- Metals ratio
                LEAST(COALESCE(SUM(CASE WHEN symbol_class = 'metals' THEN symbol_trade_count ELSE 0 END)::numeric / 
                NULLIF(total_trades, 0), 0), 1)::numeric(5,4) as metals_ratio,
                
                -- Energy ratio
                LEAST(COALESCE(SUM(CASE WHEN symbol_class = 'energy' THEN symbol_trade_count ELSE 0 END)::numeric / 
                NULLIF(total_trades, 0), 0), 1)::numeric(5,4) as energy_ratio,
                
                -- Index ratio
                LEAST(COALESCE(SUM(CASE WHEN symbol_class = 'index' THEN symbol_trade_count ELSE 0 END)::numeric / 
                NULLIF(total_trades, 0), 0), 1)::numeric(5,4) as index_ratio
                
            FROM (
                SELECT 
                    account_id,
                    std_symbol,
                    symbol_trade_count,
                    total_trades,
                    -- Mutually exclusive symbol classification with priority order
                    CASE 
                        -- Priority 1: Crypto
                        WHEN UPPER(std_symbol) IN (
                            'BTCUSD', 'ETHUSD', 'SOLUSD', 'LTCUSD', 'BCHUSD', 'AVAXUSD', 
                            'TRXUSD', 'DOGEUSD', 'BNBUSD', 'COMPUSD', 'ADAUSD', 'DOTUSD', 
                            'XRPUSD', 'MATICUSD', 'LINKUSD', 'UNIUSD', 'AAVEUSD'
                        ) OR (
                            UPPER(std_symbol) LIKE 'BTC%%%%' OR 
                            UPPER(std_symbol) LIKE 'ETH%%%%' OR 
                            UPPER(std_symbol) LIKE 'SOL%%%%' OR
                            UPPER(std_symbol) LIKE 'LTC%%%%' OR
                            UPPER(std_symbol) LIKE 'BCH%%%%' OR
                            UPPER(std_symbol) LIKE 'BNB%%%%' OR
                            UPPER(std_symbol) LIKE 'ADA%%%%' OR
                            UPPER(std_symbol) LIKE 'DOT%%%%' OR
                            UPPER(std_symbol) LIKE 'XRP%%%%' OR
                            UPPER(std_symbol) LIKE 'DOGE%%%%' OR
                            UPPER(std_symbol) LIKE 'AVAX%%%%' OR
                            UPPER(std_symbol) LIKE 'MATIC%%%%'
                        ) THEN 'crypto'
                        
                        -- Priority 2: Forex (excluding crypto and metals)
                        WHEN UPPER(std_symbol) NOT LIKE 'XAU%%%%' 
                         AND UPPER(std_symbol) NOT LIKE 'XAG%%%%'
                         AND UPPER(std_symbol) NOT LIKE 'XPT%%%%'
                         AND UPPER(std_symbol) NOT LIKE 'XPD%%%%'
                         AND (
                            UPPER(std_symbol) IN (
                                -- Major pairs
                                'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD', 'NZDUSD',
                                -- Cross pairs
                                'EURJPY', 'GBPJPY', 'EURGBP', 'EURAUD', 'EURCAD', 'EURNZD', 'EURCHF',
                                'GBPAUD', 'GBPCAD', 'GBPNZD', 'GBPCHF', 'AUDJPY', 'CADJPY', 'CHFJPY', 
                                'NZDJPY', 'AUDCAD', 'AUDNZD', 'AUDCHF', 'NZDCAD', 'NZDCHF', 'CADCHF',
                                -- Exotic pairs
                                'USDMXN', 'USDZAR', 'USDSEK', 'USDNOK', 'USDSGD', 'USDCNH', 'USDPLN',
                                'USDHUF', 'USDTRY', 'USDDKK', 'EURSGD', 'EURNOK', 'EURPLN', 'EURHUF',
                                'EURTRY', 'EURZAR', 'SGDJPY', 'CNHJPY'
                            ) OR (
                                -- Pattern matching for forex pairs
                                LENGTH(std_symbol) = 6 AND 
                                std_symbol ~ '^[A-Z]{6}$' AND
                                (RIGHT(std_symbol, 3) IN ('USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD') OR
                                 LEFT(std_symbol, 3) IN ('USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD'))
                            )
                         ) THEN 'forex'
                        
                        -- Priority 3: Metals
                        WHEN UPPER(std_symbol) IN ('XAUUSD', 'XAGUSD', 'XPTUSD', 'XPDUSD', 'XAUEUR', 'XAUAUD', 'XAUGBP')
                         OR UPPER(std_symbol) LIKE 'XAU%%%%' 
                         OR UPPER(std_symbol) LIKE 'XAG%%%%'
                         OR UPPER(std_symbol) LIKE 'XPT%%%%'
                         OR UPPER(std_symbol) LIKE 'XPD%%%%'
                         THEN 'metals'
                        
                        -- Priority 4: Energy
                        WHEN UPPER(std_symbol) IN ('USOUSD', 'UKOUSD', 'XNGUSD', 'WTIOIL', 'BRENTOIL', 'NGAS')
                         OR UPPER(std_symbol) LIKE '%%%%OIL%%%%' 
                         OR UPPER(std_symbol) LIKE 'USO%%%%' 
                         OR UPPER(std_symbol) LIKE 'UKO%%%%'
                         OR UPPER(std_symbol) LIKE 'XNG%%%%'
                         OR UPPER(std_symbol) LIKE 'WTI%%%%'
                         OR UPPER(std_symbol) LIKE 'BRENT%%%%'
                         OR UPPER(std_symbol) LIKE 'NGAS%%%%'
                         THEN 'energy'
                        
                        -- Priority 5: Index (everything else that looks like an index)
                        WHEN UPPER(std_symbol) IN (
                            'NDX100', 'US30', 'SPX500', 'GER30', 'JPN225', 'UK100', 'FRA40', 
                            'ASX200', 'EUSTX50', 'USTEC', 'HK50', 'ESTX50', 'EUR50', 'F40',
                            'US500', 'NAS100', 'DJ30', 'DAX30', 'FTSE100', 'CAC40', 'NIKKEI225'
                        ) OR (
                            -- Pattern matching for indices
                            UPPER(std_symbol) LIKE '%%%%100' OR 
                            UPPER(std_symbol) LIKE '%%%%30' OR 
                            UPPER(std_symbol) LIKE '%%%%50' OR 
                            UPPER(std_symbol) LIKE '%%%%200' OR
                            UPPER(std_symbol) LIKE '%%%%225' OR
                            UPPER(std_symbol) LIKE '%%%%40' OR
                            UPPER(std_symbol) LIKE '%%%%500'
                        ) THEN 'index'
                        
                        -- Default: unclassified (counted as index for simplicity)
                        ELSE 'index'
                    END as symbol_class
                FROM (
                    SELECT 
                        account_id,
                        std_symbol,
                        COUNT(*) as symbol_trade_count,
                        SUM(COUNT(*)) OVER (PARTITION BY account_id) as total_trades
                    FROM prop_trading_model.raw_trades_closed
                    WHERE account_id IN (SELECT account_id FROM account_metrics)
                        AND close_time >= %(snapshot_date)s - INTERVAL '30 days'
                        AND close_time <= %(snapshot_date)s + INTERVAL '1 day'
                        AND std_symbol IS NOT NULL
                    GROUP BY account_id, std_symbol
                ) trade_counts
            ) symbol_stats
            GROUP BY account_id, total_trades
        ),
        equity_high_dates AS (
            -- Calculate days since equity high for each account
            -- This avoids nested window functions by using a lateral join approach
            SELECT DISTINCT ON (am.account_id)
                am.account_id,
                COALESCE(
                    %(snapshot_date)s::date - 
                    (SELECT MAX(h.date) 
                     FROM prop_trading_model.raw_metrics_daily h 
                     WHERE h.account_id = am.account_id 
                       AND h.date <= %(snapshot_date)s
                       AND h.current_equity >= (
                           SELECT MAX(current_equity) 
                           FROM prop_trading_model.raw_metrics_daily
                           WHERE account_id = am.account_id
                             AND date <= %(snapshot_date)s
                       )
                    ), 0
                )::integer as days_since_equity_high
            FROM account_metrics am
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
                enable_consistency,
                max_leverage,
                is_drawdown_relative
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
            am.type,
            am.platform,
            am.broker,
            am.country,
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
            COALESCE(pi.max_leverage, 100) as max_leverage,
            COALESCE(pi.is_drawdown_relative, FALSE) as is_drawdown_relative,
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
            COALESCE(pi.enable_consistency, FALSE) as enable_consistency,
            -- Symbol concentration metrics (ensure all ratios stay within 0-1)
            LEAST(GREATEST(COALESCE(sc.top_symbol_concentration, 0), 0), 1)::numeric(5,4) as top_symbol_concentration,
            LEAST(GREATEST(COALESCE(sc.herfindahl_index, 0), 0), 1) as herfindahl_index,
            LEAST(GREATEST(COALESCE(sc.symbol_diversification_index, 0), 0), 1)::numeric(5,4) as symbol_diversification_index,
            LEAST(GREATEST(COALESCE(sc.forex_pairs_ratio, 0), 0), 1)::numeric(5,4) as forex_pairs_ratio,
            LEAST(GREATEST(COALESCE(sc.metals_ratio, 0), 0), 1)::numeric(5,4) as metals_ratio,
            LEAST(GREATEST(COALESCE(sc.index_ratio, 0), 0), 1)::numeric(5,4) as index_ratio,
            LEAST(GREATEST(COALESCE(sc.crypto_ratio, 0), 0), 1)::numeric(5,4) as crypto_ratio,
            LEAST(GREATEST(COALESCE(sc.energy_ratio, 0), 0), 1)::numeric(5,4) as energy_ratio,
            -- Trade aggregations
            COALESCE(ta.trades_last_1d, 0) as trades_last_1d,
            COALESCE(ta.trades_last_7d, 0) as trades_last_7d,
            COALESCE(ta.trades_last_30d, 0) as trades_last_30d,
            LEAST(GREATEST(COALESCE(ta.volume_usd_last_1d, 0), -999999999999), 999999999999)::numeric(20,8) as volume_usd_last_1d,
            LEAST(GREATEST(COALESCE(ta.volume_usd_last_7d, 0), -999999999999), 999999999999)::numeric(20,8) as volume_usd_last_7d,
            LEAST(GREATEST(COALESCE(ta.volume_usd_last_30d, 0), -999999999999), 999999999999)::numeric(20,8) as volume_usd_last_30d,
            LEAST(GREATEST(COALESCE(ta.profit_last_1d, 0), -999999999999), 999999999999)::numeric(20,8) as profit_last_1d,
            LEAST(GREATEST(COALESCE(ta.profit_last_7d, 0), -999999999999), 999999999999)::numeric(20,8) as profit_last_7d,
            LEAST(GREATEST(COALESCE(ta.profit_last_30d, 0), -999999999999), 999999999999)::numeric(20,8) as profit_last_30d,
            COALESCE(ta.unique_symbols_last_7d, 0) as unique_symbols_last_7d,
            COALESCE(ta.unique_symbols_last_30d, 0) as unique_symbols_last_30d,
            -- Trade timing patterns (ensure ratios stay within 0-1)
            LEAST(GREATEST(COALESCE(ta.trades_morning_ratio, 0), 0), 1)::numeric(5,4) as trades_morning_ratio,
            LEAST(GREATEST(COALESCE(ta.trades_afternoon_ratio, 0), 0), 1)::numeric(5,4) as trades_afternoon_ratio,
            LEAST(GREATEST(COALESCE(ta.trades_evening_ratio, 0), 0), 1)::numeric(5,4) as trades_evening_ratio,
            LEAST(GREATEST(COALESCE(ta.trades_weekend_ratio, 0), 0), 1)::numeric(5,4) as trades_weekend_ratio,
            COALESCE(ta.avg_trade_hour_of_day, 0) as avg_trade_hour_of_day,
            -- Rolling metrics
            COALESCE(rm.sharpe_ratio_5d, 0) as sharpe_ratio_5d,
            COALESCE(rm.sharpe_ratio_10d, 0) as sharpe_ratio_10d,
            COALESCE(rm.sharpe_ratio_20d, 0) as sharpe_ratio_20d,
            COALESCE(rm.profit_volatility_5d, 0) as profit_volatility_5d,
            COALESCE(rm.profit_volatility_10d, 0) as profit_volatility_10d,
            COALESCE(rm.profit_volatility_20d, 0) as profit_volatility_20d,
            LEAST(GREATEST(COALESCE(rm.win_rate_5d, 0), 0), 1)::numeric(5,4) as win_rate_5d,
            LEAST(GREATEST(COALESCE(rm.win_rate_10d, 0), 0), 1)::numeric(5,4) as win_rate_10d,
            LEAST(GREATEST(COALESCE(rm.win_rate_20d, 0), 0), 1)::numeric(5,4) as win_rate_20d,
            COALESCE(rm.balance_change_5d, 0) as balance_change_5d,
            COALESCE(rm.balance_change_10d, 0) as balance_change_10d,
            COALESCE(rm.balance_change_20d, 0) as balance_change_20d,
            COALESCE(rm.equity_high_water_mark, 0) as equity_high_water_mark,
            COALESCE(ehd.days_since_equity_high, 0) as days_since_equity_high,
            -- Performance metrics from raw_metrics_daily
            COALESCE(am.daily_sharpe, 0) as daily_sharpe,
            COALESCE(am.daily_sortino, 0) as daily_sortino,
            LEAST(GREATEST(COALESCE(am.profit_factor, 0), -999999999999), 999999999999)::numeric(20,8) as profit_factor,
            LEAST(GREATEST(COALESCE(am.success_rate, 0), 0), 1)::numeric(5,4) as success_rate,
            LEAST(GREATEST(COALESCE(am.mean_profit, 0), -999999999999), 999999999999)::numeric(20,8) as mean_profit,
            LEAST(GREATEST(COALESCE(am.median_profit, 0), -999999999999), 999999999999)::numeric(20,8) as median_profit,
            LEAST(GREATEST(COALESCE(am.mean_drawdown, 0), -999999999999), 999999999999)::numeric(20,8) as mean_drawdown,
            LEAST(GREATEST(COALESCE(am.median_drawdown, 0), -999999999999), 999999999999)::numeric(20,8) as median_drawdown,
            LEAST(GREATEST(COALESCE(am.mean_duration, 0), -999999999999), 999999999999)::numeric(20,8) as mean_duration,
            LEAST(GREATEST(COALESCE(am.median_duration, 0), -999999999999), 999999999999)::numeric(20,8) as median_duration,
            LEAST(GREATEST(COALESCE(am.total_lots, 0), -999999999999), 999999999999)::numeric(20,8) as total_lots,
            LEAST(GREATEST(COALESCE(am.total_volume, 0), -999999999999), 999999999999)::numeric(20,8) as total_volume,
            -- Additional performance metrics
            -- Cast and constrain to fit numeric(20,8) - max value is 10^12
            LEAST(GREATEST(COALESCE(am.risk_adj_profit, 0), -999999999999), 999999999999)::numeric(20,8) as risk_adj_profit,
            LEAST(GREATEST(COALESCE(am.risk_adj_ret, 0), -999999999999), 999999999999)::numeric(20,8) as risk_adj_ret,
            LEAST(GREATEST(COALESCE(am.downside_risk_adj_ret, 0), -999999999999), 999999999999)::numeric(20,8) as downside_risk_adj_ret,
            LEAST(GREATEST(COALESCE(am.gain_to_pain, 0), -999999999999), 999999999999)::numeric(20,8) as gain_to_pain,
            LEAST(GREATEST(COALESCE(am.max_profit, 0), -999999999999), 999999999999)::numeric(20,8) as max_profit,
            LEAST(GREATEST(COALESCE(am.min_profit, 0), -999999999999), 999999999999)::numeric(20,8) as min_profit,
            -- Percentile and statistical metrics
            LEAST(GREATEST(COALESCE(am.profit_perc_10, 0), -999999999999), 999999999999)::numeric(20,8) as profit_perc_10,
            LEAST(GREATEST(COALESCE(am.profit_perc_25, 0), -999999999999), 999999999999)::numeric(20,8) as profit_perc_25,
            LEAST(GREATEST(COALESCE(am.profit_perc_75, 0), -999999999999), 999999999999)::numeric(20,8) as profit_perc_75,
            LEAST(GREATEST(COALESCE(am.profit_perc_90, 0), -999999999999), 999999999999)::numeric(20,8) as profit_perc_90,
            LEAST(GREATEST(COALESCE(am.std_profits, 0), -999999999999), 999999999999)::numeric(20,8) as std_profits,
            LEAST(GREATEST(COALESCE(am.expectancy, 0), -999999999999), 999999999999)::numeric(20,8) as expectancy,
            -- Drawdown metrics
            COALESCE(am.mean_num_trades_in_dd, 0) as mean_num_trades_in_dd,
            COALESCE(am.median_num_trades_in_dd, 0) as median_num_trades_in_dd,
            COALESCE(am.max_num_trades_in_dd, 0) as max_num_trades_in_dd,
            -- Trade setup metrics
            LEAST(GREATEST(COALESCE(am.std_durations, 0), -999999999999), 999999999999)::numeric(20,8) as std_durations,
            LEAST(GREATEST(COALESCE(am.mean_tp, 0), -999999999999), 999999999999)::numeric(20,8) as mean_tp,
            LEAST(GREATEST(COALESCE(am.median_tp, 0), -999999999999), 999999999999)::numeric(20,8) as median_tp,
            LEAST(GREATEST(COALESCE(am.cv_tp, 0), -999999999999), 999999999999)::numeric(20,8) as cv_tp,
            LEAST(GREATEST(COALESCE(am.mean_sl, 0), -999999999999), 999999999999)::numeric(20,8) as mean_sl,
            LEAST(GREATEST(COALESCE(am.median_sl, 0), -999999999999), 999999999999)::numeric(20,8) as median_sl,
            LEAST(GREATEST(COALESCE(am.cv_sl, 0), -999999999999), 999999999999)::numeric(20,8) as cv_sl,
            LEAST(GREATEST(COALESCE(am.mean_tp_vs_sl, 0), -999999999999), 999999999999)::numeric(20,8) as mean_tp_vs_sl,
            LEAST(GREATEST(COALESCE(am.median_tp_vs_sl, 0), -999999999999), 999999999999)::numeric(20,8) as median_tp_vs_sl,
            LEAST(GREATEST(COALESCE(am.cv_tp_vs_sl, 0), -999999999999), 999999999999)::numeric(20,8) as cv_tp_vs_sl,
            -- Volume and position metrics
            LEAST(GREATEST(COALESCE(am.std_volumes, 0), -999999999999), 999999999999)::numeric(20,8) as std_volumes,
            COALESCE(am.mean_num_open_pos, 0) as mean_num_open_pos,
            COALESCE(am.max_num_open_pos, 0) as max_num_open_pos,
            LEAST(GREATEST(COALESCE(am.mean_val_open_pos, 0), -999999999999), 999999999999)::numeric(20,8) as mean_val_open_pos,
            LEAST(GREATEST(COALESCE(am.max_val_open_pos, 0), -999999999999), 999999999999)::numeric(20,8) as max_val_open_pos,
            COALESCE(am.max_val_to_eqty_open_pos, 0) as max_val_to_eqty_open_pos,
            -- Consecutive wins/losses metrics
            COALESCE(am.mean_num_consec_wins, 0) as mean_num_consec_wins,
            COALESCE(am.max_num_consec_wins, 0) as max_num_consec_wins,
            COALESCE(am.mean_num_consec_losses, 0) as mean_num_consec_losses,
            COALESCE(am.max_num_consec_losses, 0) as max_num_consec_losses,
            LEAST(GREATEST(COALESCE(am.max_val_consec_wins, 0), -999999999999), 999999999999)::numeric(20,8) as max_val_consec_wins,
            LEAST(GREATEST(COALESCE(am.max_val_consec_losses, 0), -999999999999), 999999999999)::numeric(20,8) as max_val_consec_losses
        FROM account_metrics am
        LEFT JOIN plan_info pi ON am.plan_id = pi.plan_id
        LEFT JOIN symbol_concentration sc ON am.account_id = sc.account_id
        LEFT JOIN trade_aggregations ta ON am.account_id = ta.account_id
        LEFT JOIN rolling_metrics rm ON am.account_id = rm.account_id
        LEFT JOIN equity_high_dates ehd ON am.account_id = ehd.account_id

        ON CONFLICT (account_id, snapshot_date) DO UPDATE SET
            login                       = EXCLUDED.login,
            trader_id                   = EXCLUDED.trader_id,
            plan_id                     = EXCLUDED.plan_id,
            phase                       = EXCLUDED.phase,
            status                      = EXCLUDED.status,
            type                        = EXCLUDED.type,
            platform                    = EXCLUDED.platform,
            broker                      = EXCLUDED.broker,
            country                     = EXCLUDED.country,
            starting_balance            = EXCLUDED.starting_balance,
            balance                     = EXCLUDED.balance,
            equity                      = EXCLUDED.equity,
            profit_target               = EXCLUDED.profit_target,
            profit_target_pct           = EXCLUDED.profit_target_pct,
            max_daily_drawdown          = EXCLUDED.max_daily_drawdown,
            max_daily_drawdown_pct      = EXCLUDED.max_daily_drawdown_pct,
            max_drawdown                = EXCLUDED.max_drawdown,
            max_drawdown_pct            = EXCLUDED.max_drawdown_pct,
            max_leverage                = EXCLUDED.max_leverage,
            is_drawdown_relative        = EXCLUDED.is_drawdown_relative,
            days_active                 = EXCLUDED.days_active,
            days_since_last_trade       = EXCLUDED.days_since_last_trade,
            distance_to_profit_target   = EXCLUDED.distance_to_profit_target,
            distance_to_max_drawdown    = EXCLUDED.distance_to_max_drawdown,
            liquidate_friday            = EXCLUDED.liquidate_friday,
            inactivity_period           = EXCLUDED.inactivity_period,
            daily_drawdown_by_balance_equity = EXCLUDED.daily_drawdown_by_balance_equity,
            enable_consistency          = EXCLUDED.enable_consistency,
            top_symbol_concentration    = EXCLUDED.top_symbol_concentration,
            herfindahl_index           = EXCLUDED.herfindahl_index,
            symbol_diversification_index = EXCLUDED.symbol_diversification_index,
            forex_pairs_ratio          = EXCLUDED.forex_pairs_ratio,
            metals_ratio               = EXCLUDED.metals_ratio,
            index_ratio                = EXCLUDED.index_ratio,
            crypto_ratio               = EXCLUDED.crypto_ratio,
            energy_ratio               = EXCLUDED.energy_ratio,
            -- Trade aggregations
            trades_last_1d             = EXCLUDED.trades_last_1d,
            trades_last_7d             = EXCLUDED.trades_last_7d,
            trades_last_30d            = EXCLUDED.trades_last_30d,
            volume_usd_last_1d         = EXCLUDED.volume_usd_last_1d,
            volume_usd_last_7d         = EXCLUDED.volume_usd_last_7d,
            volume_usd_last_30d        = EXCLUDED.volume_usd_last_30d,
            profit_last_1d             = EXCLUDED.profit_last_1d,
            profit_last_7d             = EXCLUDED.profit_last_7d,
            profit_last_30d            = EXCLUDED.profit_last_30d,
            unique_symbols_last_7d     = EXCLUDED.unique_symbols_last_7d,
            unique_symbols_last_30d    = EXCLUDED.unique_symbols_last_30d,
            -- Trade timing patterns
            trades_morning_ratio       = EXCLUDED.trades_morning_ratio,
            trades_afternoon_ratio     = EXCLUDED.trades_afternoon_ratio,
            trades_evening_ratio       = EXCLUDED.trades_evening_ratio,
            trades_weekend_ratio       = EXCLUDED.trades_weekend_ratio,
            avg_trade_hour_of_day      = EXCLUDED.avg_trade_hour_of_day,
            -- Rolling metrics
            sharpe_ratio_5d            = EXCLUDED.sharpe_ratio_5d,
            sharpe_ratio_10d           = EXCLUDED.sharpe_ratio_10d,
            sharpe_ratio_20d           = EXCLUDED.sharpe_ratio_20d,
            profit_volatility_5d       = EXCLUDED.profit_volatility_5d,
            profit_volatility_10d      = EXCLUDED.profit_volatility_10d,
            profit_volatility_20d      = EXCLUDED.profit_volatility_20d,
            win_rate_5d                = EXCLUDED.win_rate_5d,
            win_rate_10d               = EXCLUDED.win_rate_10d,
            win_rate_20d               = EXCLUDED.win_rate_20d,
            balance_change_5d          = EXCLUDED.balance_change_5d,
            balance_change_10d         = EXCLUDED.balance_change_10d,
            balance_change_20d         = EXCLUDED.balance_change_20d,
            equity_high_water_mark     = EXCLUDED.equity_high_water_mark,
            days_since_equity_high     = EXCLUDED.days_since_equity_high,
            -- Performance metrics from raw_metrics_daily
            daily_sharpe               = EXCLUDED.daily_sharpe,
            daily_sortino              = EXCLUDED.daily_sortino,
            profit_factor              = EXCLUDED.profit_factor,
            success_rate               = EXCLUDED.success_rate,
            mean_profit                = EXCLUDED.mean_profit,
            median_profit              = EXCLUDED.median_profit,
            mean_drawdown              = EXCLUDED.mean_drawdown,
            median_drawdown            = EXCLUDED.median_drawdown,
            mean_duration              = EXCLUDED.mean_duration,
            median_duration            = EXCLUDED.median_duration,
            total_lots                 = EXCLUDED.total_lots,
            total_volume               = EXCLUDED.total_volume,
            -- Additional performance metrics
            risk_adj_profit            = EXCLUDED.risk_adj_profit,
            risk_adj_ret               = EXCLUDED.risk_adj_ret,
            downside_risk_adj_ret      = EXCLUDED.downside_risk_adj_ret,
            gain_to_pain               = EXCLUDED.gain_to_pain,
            max_profit                 = EXCLUDED.max_profit,
            min_profit                 = EXCLUDED.min_profit,
            -- Percentile and statistical metrics
            profit_perc_10             = EXCLUDED.profit_perc_10,
            profit_perc_25             = EXCLUDED.profit_perc_25,
            profit_perc_75             = EXCLUDED.profit_perc_75,
            profit_perc_90             = EXCLUDED.profit_perc_90,
            std_profits                = EXCLUDED.std_profits,
            expectancy                 = EXCLUDED.expectancy,
            -- Drawdown metrics
            mean_num_trades_in_dd      = EXCLUDED.mean_num_trades_in_dd,
            median_num_trades_in_dd    = EXCLUDED.median_num_trades_in_dd,
            max_num_trades_in_dd       = EXCLUDED.max_num_trades_in_dd,
            -- Trade setup metrics
            std_durations              = EXCLUDED.std_durations,
            mean_tp                    = EXCLUDED.mean_tp,
            median_tp                  = EXCLUDED.median_tp,
            cv_tp                      = EXCLUDED.cv_tp,
            mean_sl                    = EXCLUDED.mean_sl,
            median_sl                  = EXCLUDED.median_sl,
            cv_sl                      = EXCLUDED.cv_sl,
            mean_tp_vs_sl              = EXCLUDED.mean_tp_vs_sl,
            median_tp_vs_sl            = EXCLUDED.median_tp_vs_sl,
            cv_tp_vs_sl                = EXCLUDED.cv_tp_vs_sl,
            -- Volume and position metrics
            std_volumes                = EXCLUDED.std_volumes,
            mean_num_open_pos          = EXCLUDED.mean_num_open_pos,
            max_num_open_pos           = EXCLUDED.max_num_open_pos,
            mean_val_open_pos          = EXCLUDED.mean_val_open_pos,
            max_val_open_pos           = EXCLUDED.max_val_open_pos,
            max_val_to_eqty_open_pos   = EXCLUDED.max_val_to_eqty_open_pos,
            -- Consecutive wins/losses metrics
            mean_num_consec_wins       = EXCLUDED.mean_num_consec_wins,
            max_num_consec_wins        = EXCLUDED.max_num_consec_wins,
            mean_num_consec_losses     = EXCLUDED.mean_num_consec_losses,
            max_num_consec_losses      = EXCLUDED.max_num_consec_losses,
            max_val_consec_wins        = EXCLUDED.max_val_consec_wins,
            max_val_consec_losses      = EXCLUDED.max_val_consec_losses,
            updated_at                  = NOW()
        """
        
        params = {"snapshot_date": snapshot_date}
        # Debug: Log query length and param count
        logger.debug(f"Query length: {len(insert_query)} chars")
        logger.debug(f"Parameters: {params}")
        
        # Debug: Count parameter placeholders
        import re
        placeholders = re.findall(r'%\(snapshot_date\)s', insert_query)
        logger.debug(f"Found {len(placeholders)} %(snapshot_date)s placeholders")
        
        # Use 30 minute timeout for complex snapshot queries
        logger.info(f"Executing snapshot query for {snapshot_date} with {len(insert_query)} chars")
        start_time = datetime.now()
        rows_affected = self.db_manager.model_db.execute_command(insert_query, params, timeout_seconds=1800)
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Query completed in {elapsed:.2f} seconds")
        
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