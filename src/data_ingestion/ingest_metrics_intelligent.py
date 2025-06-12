"""
Enhanced metrics ingester with intelligent data fetching.
Only fetches data that doesn't already exist in the database.
"""

import os
import sys
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum
import time
from collections import defaultdict

# Ensure we can import from parent directories
try:
    from .base_ingester import BaseIngester, IngestionMetrics, CheckpointManager
    from ..utils.api_client import RiskAnalyticsAPIClient
    from ..utils.logging_config import get_logger
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_ingestion.base_ingester import BaseIngester, IngestionMetrics, CheckpointManager
    from utils.api_client import RiskAnalyticsAPIClient
    from utils.logging_config import get_logger

logger = get_logger(__name__)


class MetricType(Enum):
    """Enum for metric types."""
    ALLTIME = "alltime"
    DAILY = "daily"
    HOURLY = "hourly"


class IntelligentMetricsIngester(BaseIngester):
    """
    Enhanced metrics ingester that intelligently fetches only missing data.
    
    Key features:
    - Checks existing data before making API calls
    - Only fetches missing daily/hourly records
    - Always updates alltime records (as they can change)
    - Optimized for both date-range and full ingestion scenarios
    """

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        enable_validation: bool = True,
        enable_deduplication: bool = True,
    ):
        """Initialize the intelligent metrics ingester."""
        # Initialize base class with a dummy table name
        super().__init__(
            ingestion_type="metrics",
            table_name="raw_metrics_alltime",
            checkpoint_dir=checkpoint_dir,
            enable_validation=enable_validation,
            enable_deduplication=enable_deduplication,
        )

        self.checkpoint_dir = checkpoint_dir
        self.enable_validation = enable_validation
        self.enable_deduplication = enable_deduplication

        # Configuration
        self.config = type('Config', (), {
            'batch_size': 1000,
            'max_retries': 3,
            'timeout': 30,
            'account_batch_size': 50,  # For alltime metrics
            'hourly_batch_size': 25,   # For hourly metrics (more data per account)
        })()

        # Initialize API client
        self.api_client = RiskAnalyticsAPIClient()

        # Table mapping
        self.table_mapping = {
            MetricType.ALLTIME: "prop_trading_model.raw_metrics_alltime",
            MetricType.DAILY: "prop_trading_model.raw_metrics_daily",
            MetricType.HOURLY: "prop_trading_model.raw_metrics_hourly",
        }

        # Initialize checkpoint managers and metrics
        self.checkpoint_managers = {}
        self.metrics_by_type = {}

        for metric_type in MetricType:
            checkpoint_file = os.path.join(
                checkpoint_dir or os.path.join(os.path.dirname(__file__), "checkpoints"),
                f"metrics_{metric_type.value}_checkpoint.json",
            )
            self.checkpoint_managers[metric_type.value] = CheckpointManager(
                checkpoint_file, f"metrics_{metric_type.value}"
            )
            self.metrics_by_type[metric_type.value] = IngestionMetrics()
        
        # Initialize field mappings
        self._init_field_mappings()

    def _init_field_mappings(self):
        """Initialize comprehensive field mappings directly (no dependencies)."""
        # Core identification and metadata fields
        self.core_fields = {
            'login': 'login',
            'accountId': 'account_id',
            'planId': 'plan_id',
            'trader': 'trader_id',
            'status': 'status',
            'type': 'type',
            'phase': 'phase',
            'broker': 'broker',
            'mt_version': 'platform',
            'price_stream': 'price_stream',
            'country': 'country'
        }
        
        # Payout and balance fields
        self.payout_balance_fields = {
            'approved_payouts': 'approved_payouts',
            'pending_payouts': 'pending_payouts',
            'startingBalance': 'starting_balance',
            'priorDaysBalance': 'prior_days_balance',
            'priorDaysEquity': 'prior_days_equity',
            'currentBalance': 'current_balance',
            'currentEquity': 'current_equity'
        }
        
        # Trading timeline fields
        self.timeline_fields = {
            'firstTradeDate': 'first_trade_date',
            'daysSinceInitialDeposit': 'days_since_initial_deposit',
            'daysSinceFirstTrade': 'days_since_first_trade',
            'numTrades': 'num_trades',
            'firstTradeOpen': 'first_trade_open',
            'lastTradeOpen': 'last_trade_open',
            'lastTradeClose': 'last_trade_close',
            'lifeTimeInDays': 'lifetime_in_days'
        }
        
        # Core performance metrics
        self.performance_fields = {
            'netProfit': 'net_profit',
            'grossProfit': 'gross_profit',
            'grossLoss': 'gross_loss',
            'gainToPain': 'gain_to_pain',
            'profitFactor': 'profit_factor',
            'successRate': 'success_rate',
            'meanProfit': 'mean_profit',
            'medianProfit': 'median_profit',
            'stdProfits': 'std_profits',
            'riskAdjProfit': 'risk_adj_profit',
            'expectancy': 'expectancy'
        }
        
        # Distribution metrics
        self.distribution_fields = {
            'minProfit': 'min_profit',
            'maxProfit': 'max_profit',
            'profitPerc10': 'profit_perc_10',
            'profitPerc25': 'profit_perc_25',
            'profitPerc75': 'profit_perc_75',
            'profitPerc90': 'profit_perc_90'
        }
        
        # Outlier analysis
        self.outlier_fields = {
            'profitTop10PrcntTrades': 'profit_top_10_prcnt_trades',
            'profitBottom10PrcntTrades': 'profit_bottom_10_prcnt_trades',
            'top10PrcntProfitContrib': 'top_10_prcnt_profit_contrib',
            'bottom10PrcntLossContrib': 'bottom_10_prcnt_loss_contrib',
            'oneStdOutlierProfit': 'one_std_outlier_profit',
            'oneStdOutlierProfitContrib': 'one_std_outlier_profit_contrib',
            'twoStdOutlierProfit': 'two_std_outlier_profit',
            'twoStdOutlierProfitContrib': 'two_std_outlier_profit_contrib'
        }
        
        # Per-unit profitability
        self.unit_profit_fields = {
            'netProfitPerUSDVolume': 'net_profit_per_usd_volume',
            'grossProfitPerUSDVolume': 'gross_profit_per_usd_volume',
            'grossLossPerUSDVolume': 'gross_loss_per_usd_volume',
            'distanceGrossProfitLossPerUSDVolume': 'distance_gross_profit_loss_per_usd_volume',
            'multipleGrossProfitLossPerUSDVolume': 'multiple_gross_profit_loss_per_usd_volume',
            'grossProfitPerLot': 'gross_profit_per_lot',
            'grossLossPerLot': 'gross_loss_per_lot',
            'distanceGrossProfitLossPerLot': 'distance_gross_profit_loss_per_lot',
            'multipleGrossProfitLossPerLot': 'multiple_gross_profit_loss_per_lot',
            'netProfitPerDuration': 'net_profit_per_duration',
            'grossProfitPerDuration': 'gross_profit_per_duration',
            'grossLossPerDuration': 'gross_loss_per_duration'
        }
        
        # Return metrics
        self.return_fields = {
            'meanRet': 'mean_ret',
            'stdRets': 'std_rets',
            'riskAdjRet': 'risk_adj_ret',
            'downsideStdRets': 'downside_std_rets',
            'downsideRiskAdjRet': 'downside_risk_adj_ret',
            'totalRet': 'total_ret',
            'dailyMeanRet': 'daily_mean_ret',
            'dailyStdRet': 'daily_std_ret',
            'dailySharpe': 'daily_sharpe',
            'dailyDownsideStdRet': 'daily_downside_std_ret',
            'dailySortino': 'daily_sortino',
        }
        
        # Relative (normalized) metrics
        self.relative_fields = {
            'relNetProfit': 'rel_net_profit',
            'relGrossProfit': 'rel_gross_profit',
            'relGrossLoss': 'rel_gross_loss',
            'relMeanProfit': 'rel_mean_profit',
            'relMedianProfit': 'rel_median_profit',
            'relStdProfits': 'rel_std_profits',
            'relRiskAdjProfit': 'rel_risk_adj_profit',
            'relMinProfit': 'rel_min_profit',
            'relMaxProfit': 'rel_max_profit',
            'relProfitPerc10': 'rel_profit_perc_10',
            'relProfitPerc25': 'rel_profit_perc_25',
            'relProfitPerc75': 'rel_profit_perc_75',
            'relProfitPerc90': 'rel_profit_perc_90',
            'relProfitTop10PrcntTrades': 'rel_profit_top_10_prcnt_trades',
            'relProfitBottom10PrcntTrades': 'rel_profit_bottom_10_prcnt_trades',
            'relOneStdOutlierProfit': 'rel_one_std_outlier_profit',
            'relTwoStdOutlierProfit': 'rel_two_std_outlier_profit'
        }
        
        # Drawdown analysis
        self.drawdown_fields = {
            'meanDrawDown': 'mean_drawdown',
            'medianDrawDown': 'median_drawdown',
            'maxDrawDown': 'max_drawdown',
            'meanNumTradesInDD': 'mean_num_trades_in_dd',
            'medianNumTradesInDD': 'median_num_trades_in_dd',
            'maxNumTradesInDD': 'max_num_trades_in_dd',
            'relMeanDrawDown': 'rel_mean_drawdown',
            'relMedianDrawDown': 'rel_median_drawdown',
            'relMaxDrawDown': 'rel_max_drawdown',
        }
        
        # Volume and lot metrics
        self.volume_lot_fields = {
            'totalLots': 'total_lots',
            'totalVolume': 'total_volume',
            'stdVolumes': 'std_volumes',
            'meanWinningLot': 'mean_winning_lot',
            'meanLosingLot': 'mean_losing_lot',
            'distanceWinLossLots': 'distance_win_loss_lots',
            'multipleWinLossLots': 'multiple_win_loss_lots',
            'meanWinningVolume': 'mean_winning_volume',
            'meanLosingVolume': 'mean_losing_volume',
            'distanceWinLossVolume': 'distance_win_loss_volume',
            'multipleWinLossVolume': 'multiple_win_loss_volume'
        }
        
        # Duration metrics
        self.duration_fields = {
            'meanDuration': 'mean_duration',
            'medianDuration': 'median_duration',
            'stdDurations': 'std_durations',
            'minDuration': 'min_duration',
            'maxDuration': 'max_duration',
            'cvDurations': 'cv_durations'
        }
        
        # Stop loss and take profit metrics
        self.sl_tp_fields = {
            'meanTP': 'mean_tp',
            'medianTP': 'median_tp',
            'stdTP': 'std_tp',
            'minTP': 'min_tp',
            'maxTP': 'max_tp',
            'cvTP': 'cv_tp',
            'meanSL': 'mean_sl',
            'medianSL': 'median_sl',
            'stdSL': 'std_sl',
            'minSL': 'min_sl',
            'maxSL': 'max_sl',
            'cvSL': 'cv_sl',
            'meanTPvsSL': 'mean_tp_vs_sl',
            'medianTPvsSL': 'median_tp_vs_sl',
            'minTPvsSL': 'min_tp_vs_sl',
            'maxTPvsSL': 'max_tp_vs_sl',
            'cvTPvsSL': 'cv_tp_vs_sl'
        }
        
        # Consecutive wins/losses
        self.streak_fields = {
            'meanNumConsecWins': 'mean_num_consec_wins',
            'medianNumConsecWins': 'median_num_consec_wins',
            'maxNumConsecWins': 'max_num_consec_wins',
            'meanNumConsecLosses': 'mean_num_consec_losses',
            'medianNumConsecLosses': 'median_num_consec_losses',
            'maxNumConsecLosses': 'max_num_consec_losses',
            'meanValConsecWins': 'mean_val_consec_wins',
            'medianValConsecWins': 'median_val_consec_wins',
            'maxValConsecWins': 'max_val_consec_wins',
            'meanValConsecLosses': 'mean_val_consec_losses',
            'medianValConsecLosses': 'median_val_consec_losses',
            'maxValConsecLosses': 'max_val_consec_losses'
        }
        
        # Open position metrics
        self.position_fields = {
            'meanNumOpenPos': 'mean_num_open_pos',
            'medianNumOpenPos': 'median_num_open_pos',
            'maxNumOpenPos': 'max_num_open_pos',
            'meanValOpenPos': 'mean_val_open_pos',
            'medianValOpenPos': 'median_val_open_pos',
            'maxValOpenPos': 'max_val_open_pos',
            'meanValtoEqtyOpenPos': 'mean_val_to_eqty_open_pos',
            'medianValtoEqtyOpenPos': 'median_val_to_eqty_open_pos',
            'maxValtoEqtyOpenPos': 'max_val_to_eqty_open_pos'
        }
        
        # Margin and activity metrics
        self.margin_activity_fields = {
            'meanAccountMargin': 'mean_account_margin',
            'meanFirmMargin': 'mean_firm_margin',
            'meanTradesPerDay': 'mean_trades_per_day',
            'medianTradesPerDay': 'median_trades_per_day',
            'minTradesPerDay': 'min_trades_per_day',
            'maxTradesPerDay': 'max_trades_per_day',
            'cvTradesPerDay': 'cv_trades_per_day',
            'meanIdleDays': 'mean_idle_days',
            'medianIdleDays': 'median_idle_days',
            'maxIdleDays': 'max_idle_days',
            'minIdleDays': 'min_idle_days',
            'numTradedSymbols': 'num_traded_symbols',
            'mostTradedSymbol': 'most_traded_symbol',
            'mostTradedSmbTrades': 'most_traded_smb_trades'
        }
        
        # Daily-specific fields
        self.daily_hourly_specific_fields = {
            'days_to_next_payout': 'days_to_next_payout',
            'todays_payouts': 'todays_payouts'
        }

        # Hourly-specific fields
        self.hourly_specific_fields = {
            'hour': 'hour'
        }
        
        # Other fields
        self.alltime_specific_fields = {
            'updatedDate': 'updated_date',
        }
        
        # Combine all field mappings for alltime metrics
        self.alltime_field_mapping = {
            **self.core_fields,
            **self.payout_balance_fields,
            **self.timeline_fields,
            **self.performance_fields,
            **self.distribution_fields,
            **self.outlier_fields,
            **self.unit_profit_fields,
            **self.return_fields,
            **self.relative_fields,
            **self.drawdown_fields,
            **self.volume_lot_fields,
            **self.duration_fields,
            **self.sl_tp_fields,
            **self.streak_fields,
            **self.position_fields,
            **self.margin_activity_fields,
            **self.alltime_specific_fields
        }
        
        # Daily metrics include most alltime fields plus daily-specific
        self.daily_field_mapping = {
            **self.core_fields,
            **self.payout_balance_fields,
            **self.timeline_fields,
            **self.performance_fields,
            **self.distribution_fields,
            **self.outlier_fields,
            **self.unit_profit_fields,
            **self.return_fields,
            **self.relative_fields,
            **self.drawdown_fields,
            **self.volume_lot_fields,
            **self.duration_fields,
            **self.sl_tp_fields,
            **self.streak_fields,
            **self.position_fields,
            **self.margin_activity_fields,
            **self.daily_hourly_specific_fields
        }
        
        # Hourly metrics use similar fields as daily
        self.hourly_field_mapping = {
            **self.core_fields,
            **self.payout_balance_fields,
            **self.timeline_fields,
            **self.performance_fields,
            **self.distribution_fields,
            **self.outlier_fields,
            **self.unit_profit_fields,
            **self.return_fields,
            **self.relative_fields,
            **self.drawdown_fields,
            **self.volume_lot_fields,
            **self.duration_fields,
            **self.sl_tp_fields,
            **self.streak_fields,
            **self.position_fields,
            **self.margin_activity_fields,
            **self.daily_hourly_specific_fields,
            **self.hourly_specific_fields
        }

    def ingest_with_date_range(
        self,
        start_date: date,
        end_date: Optional[date] = None,
        force_full_refresh: bool = False,
    ) -> Dict[str, int]:
        """
        Intelligent ingestion for a specific date range (Flow 1).
        
        1. Get missing daily records in date range
        2. Extract account IDs from those records
        3. Update alltime metrics for those accounts
        4. Fill in missing hourly metrics for those accounts/dates
        
        Args:
            start_date: Start date for ingestion
            end_date: End date for ingestion (defaults to yesterday)
            force_full_refresh: If True, ignore existing data
            
        Returns:
            Dictionary with counts for each metric type
        """
        if not end_date:
            end_date = datetime.now().date() - timedelta(days=1)
            
        logger.info(f"Starting intelligent ingestion for date range {start_date} to {end_date}")
        results = {}
        
        try:
            # Step 1: Get missing daily dates in range
            if force_full_refresh:
                missing_daily_dates = [start_date + timedelta(days=x) 
                                     for x in range((end_date - start_date).days + 1)]
            else:
                missing_daily_dates = self._get_missing_daily_dates(start_date, end_date)
            
            if not missing_daily_dates:
                logger.info("All daily metrics already exist for date range")
                results["daily"] = 0
                # Still get account IDs from existing data
                account_ids = self._get_account_ids_from_daily_range(start_date, end_date)
            else:
                # Ingest missing daily metrics
                logger.info(f"Found {len(missing_daily_dates)} missing daily dates")
                daily_records = self._ingest_daily_for_dates(missing_daily_dates)
                results["daily"] = daily_records
                
                # Get account IDs from full date range (including newly ingested)
                account_ids = self._get_account_ids_from_daily_range(start_date, end_date)
            
            logger.info(f"Found {len(account_ids)} accounts in date range")
            
            if account_ids:
                # Step 3: Update alltime metrics for these accounts
                logger.info("Updating alltime metrics for discovered accounts...")
                alltime_records = self._ingest_alltime_for_accounts(account_ids)
                results["alltime"] = alltime_records
                
                # Step 4: Fill in missing hourly metrics with precise detection
                logger.info("Checking for missing hourly metrics with precise detection...")
                
                # First get account-date pairs from daily metrics
                account_date_pairs = self._get_account_date_pairs_from_daily(
                    account_ids, start_date, end_date
                )
                
                if not account_date_pairs:
                    logger.info("No account-date pairs found in daily metrics")
                    results["hourly"] = 0
                else:
                    logger.info(f"Checking {len(account_date_pairs)} account-date pairs for missing hourly data")
                    
                    if force_full_refresh:
                        # Force refresh: assume all hours are missing
                        missing_hourly_slots = [
                            (acc_id, date_val, hour)
                            for acc_id, date_val in account_date_pairs
                            for hour in range(24)
                        ]
                    else:
                        # Use precise detection to find specific missing hours
                        missing_hourly_slots = self._get_missing_hourly_records(account_date_pairs)
                    
                    if missing_hourly_slots:
                        logger.info(f"Found {len(missing_hourly_slots)} specific missing hourly records")
                        hourly_records = self._ingest_hourly_for_missing(missing_hourly_slots)
                        results["hourly"] = hourly_records
                    else:
                        logger.info("All hourly metrics already exist for accounts in date range")
                        results["hourly"] = 0
            else:
                results["alltime"] = 0
                results["hourly"] = 0
            
            # Log summary
            self._log_summary(results)
            return results
            
        except Exception as e:
            logger.error(f"Intelligent ingestion failed: {str(e)}", exc_info=True)
            raise

    def ingest_without_date_range(self, force_full_refresh: bool = False) -> Dict[str, int]:
        """
        Intelligent ingestion without date range (Flow 2).
        
        1. Get all alltime records (always refresh as they can change)
        2. Get all missing daily records
        3. Get all missing hourly records
        
        Args:
            force_full_refresh: If True, ignore existing data
            
        Returns:
            Dictionary with counts for each metric type
        """
        logger.info("Starting intelligent ingestion without date range")
        results = {}
        
        try:
            # Step 1: Get all alltime metrics (always refresh as they can change)
            logger.info("Fetching all alltime metrics...")
            alltime_records = self._ingest_alltime_for_accounts(None)  # None means all accounts
            results["alltime"] = alltime_records
            
            # Step 2: Get all missing daily records
            logger.info("Checking for missing daily records...")
            if force_full_refresh:
                # For full refresh, we'd need to truncate and reload
                # This is handled by the force_full_refresh flag in main ingestion
                logger.warning("Force full refresh requires truncating tables - use with caution")
                missing_daily = []
            else:
                missing_daily = self._get_all_missing_daily_data()
            
            if missing_daily:
                logger.info(f"Found {len(missing_daily)} missing daily account-date combinations")
                daily_records = self._ingest_daily_for_missing(missing_daily)
                results["daily"] = daily_records
            else:
                logger.info("All daily metrics are up to date")
                results["daily"] = 0
            
            # Step 3: Get all missing hourly records
            logger.info("Checking for missing hourly records...")
            if force_full_refresh:
                missing_hourly = []
            else:
                missing_hourly = self._get_all_missing_hourly_data()
            
            if missing_hourly:
                logger.info(f"Found {len(missing_hourly)} missing hourly account-date-hour combinations")
                hourly_records = self._ingest_hourly_for_missing(missing_hourly)
                results["hourly"] = hourly_records
            else:
                logger.info("All hourly metrics are up to date")
                results["hourly"] = 0
            
            # Log summary
            self._log_summary(results)
            return results
            
        except Exception as e:
            logger.error(f"Intelligent ingestion failed: {str(e)}", exc_info=True)
            raise

    def _get_missing_daily_dates(self, start_date: date, end_date: date) -> List[date]:
        """Get dates in range that don't have complete daily metrics."""
        query = """
            WITH date_series AS (
                SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS date
            ),
            existing_dates AS (
                SELECT DISTINCT date 
                FROM prop_trading_model.raw_metrics_daily 
                WHERE date BETWEEN %s AND %s
            )
            SELECT ds.date
            FROM date_series ds
            LEFT JOIN existing_dates ed ON ds.date = ed.date
            WHERE ed.date IS NULL
            ORDER BY ds.date
        """
        
        results = self.db_manager.model_db.execute_query(
            query, (start_date, end_date, start_date, end_date)
        )
        
        return [row["date"] for row in results]

    def _get_account_ids_from_daily_range(self, start_date: date, end_date: date) -> List[str]:
        """Get unique account IDs from daily metrics in date range."""
        query = """
            SELECT DISTINCT account_id 
            FROM prop_trading_model.raw_metrics_daily 
            WHERE date >= %s AND date <= %s 
            AND account_id IS NOT NULL
            ORDER BY account_id
        """
        
        results = self.db_manager.model_db.execute_query(
            query, (start_date, end_date)
        )
        
        return [row["account_id"] for row in results]
    
    def _get_account_date_pairs_from_daily(
        self, account_ids: List[str], start_date: date, end_date: date
    ) -> List[Tuple[str, date]]:
        """Get all account-date pairs from daily metrics for given accounts and date range."""
        if not account_ids:
            return []
            
        # Process in batches to avoid query size limits
        account_date_pairs = []
        batch_size = 1000
        
        for i in range(0, len(account_ids), batch_size):
            batch = account_ids[i:i + batch_size]
            
            query = """
                SELECT DISTINCT account_id, date
                FROM prop_trading_model.raw_metrics_daily
                WHERE account_id = ANY(%s)
                AND date BETWEEN %s AND %s
                AND account_id IS NOT NULL
                ORDER BY account_id, date
            """
            
            results = self.db_manager.model_db.execute_query(
                query, (batch, start_date, end_date)
            )
            
            account_date_pairs.extend([(row["account_id"], row["date"]) for row in results])
        
        return account_date_pairs

    def _get_missing_hourly_data(
        self, account_ids: List[str], start_date: date, end_date: date
    ) -> List[Tuple[str, date]]:
        """DEPRECATED: Use _get_missing_hourly_records for precise hour-level detection."""
        # This method is kept for backward compatibility but should not be used
        # Use _get_missing_hourly_records instead for more efficient processing
        return self._get_account_date_pairs_with_missing_hours(account_ids, start_date, end_date)
    
    def _get_account_date_pairs_with_missing_hours(
        self, account_ids: List[str], start_date: date, end_date: date
    ) -> List[Tuple[str, date]]:
        """Get account-date combinations that have ANY missing hourly data."""
        if not account_ids:
            return []
            
        # Process in batches to avoid query size limits
        missing_data = []
        batch_size = 1000
        
        for i in range(0, len(account_ids), batch_size):
            batch = account_ids[i:i + batch_size]
            
            query = """
                WITH expected_data AS (
                    -- Get all account-date combinations from daily metrics
                    SELECT DISTINCT 
                        d.account_id,
                        d.date
                    FROM prop_trading_model.raw_metrics_daily d
                    WHERE d.account_id = ANY(%s)
                    AND d.date BETWEEN %s AND %s
                ),
                existing_hourly AS (
                    -- Check which ones have ANY hourly data (we need all 24 hours)
                    SELECT 
                        account_id,
                        date,
                        COUNT(DISTINCT hour) as hours_count
                    FROM prop_trading_model.raw_metrics_hourly
                    WHERE account_id = ANY(%s)
                    AND date BETWEEN %s AND %s
                    GROUP BY account_id, date
                    HAVING COUNT(DISTINCT hour) = 24  -- Only complete days
                )
                SELECT 
                    e.account_id,
                    e.date
                FROM expected_data e
                LEFT JOIN existing_hourly h 
                    ON e.account_id = h.account_id 
                    AND e.date = h.date
                WHERE h.account_id IS NULL
                ORDER BY e.account_id, e.date
            """
            
            results = self.db_manager.model_db.execute_query(
                query, (batch, start_date, end_date, batch, start_date, end_date)
            )
            
            missing_data.extend([(row["account_id"], row["date"]) for row in results])
        
        return missing_data
    
    def _get_missing_hourly_records(
        self, account_date_pairs: List[Tuple[str, date]]
    ) -> List[Tuple[str, date, int]]:
        """
        Get precise list of missing hourly records (account_id, date, hour).
        
        This method identifies specific missing hours rather than entire days,
        enabling more efficient API calls.
        
        Args:
            account_date_pairs: List of (account_id, date) tuples to check
            
        Returns:
            List of (account_id, date, hour) tuples that are missing
        """
        if not account_date_pairs:
            return []
            
        logger.info(f"Checking for missing hourly records across {len(account_date_pairs)} account-date pairs")
        
        # Process in batches to avoid memory issues
        all_missing_slots = []
        batch_size = 500  # Smaller batches for more granular processing
        
        for i in range(0, len(account_date_pairs), batch_size):
            batch = account_date_pairs[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(account_date_pairs) + batch_size - 1) // batch_size
            
            logger.debug(f"Processing batch {batch_num}/{total_batches} for missing hour detection")
            
            # Step 1: Generate all possible hourly slots for this batch
            all_possible_slots = set()
            for account_id, date_val in batch:
                for hour in range(24):
                    all_possible_slots.add((account_id, date_val, hour))
            
            # Step 2: Query existing hourly records
            # Build efficient query using VALUES clause
            values_list = []
            for account_id, date_val in batch:
                values_list.append(f"('{account_id}', '{date_val}'::date)")
            
            values_clause = ",".join(values_list)
            
            query = f"""
                WITH target_pairs AS (
                    SELECT * FROM (VALUES {values_clause}) AS t(account_id, date)
                ),
                existing_hours AS (
                    SELECT DISTINCT
                        h.account_id,
                        h.date,
                        h.hour
                    FROM prop_trading_model.raw_metrics_hourly h
                    INNER JOIN target_pairs t 
                        ON h.account_id = t.account_id 
                        AND h.date = t.date
                )
                SELECT account_id, date, hour FROM existing_hours
            """
            
            try:
                results = self.db_manager.model_db.execute_query(query)
                
                # Convert results to set for efficient lookup
                existing_slots = set()
                for row in results:
                    existing_slots.add((row["account_id"], row["date"], row["hour"]))
                
                # Step 3: Compute missing slots
                missing_slots = all_possible_slots - existing_slots
                all_missing_slots.extend(list(missing_slots))
                
                logger.debug(f"Batch {batch_num}: {len(all_possible_slots)} possible slots, "
                           f"{len(existing_slots)} exist, {len(missing_slots)} missing")
                
            except Exception as e:
                logger.error(f"Error checking missing hourly records for batch {batch_num}: {str(e)}")
                # Fall back to assuming all hours are missing for this batch
                all_missing_slots.extend(list(all_possible_slots))
        
        logger.info(f"Found {len(all_missing_slots)} specific missing hourly records")
        return sorted(all_missing_slots)  # Sort for consistent processing
    
    def _create_hourly_api_batches(
        self, missing_slots: List[Tuple[str, date, int]]
    ) -> List[Dict[str, str]]:
        """
        Create optimized API batches from missing hourly slots.
        
        Groups missing slots by date and creates batches with:
        - Single date per batch
        - Up to 25 account IDs per batch
        - All 24 hours (API is most efficient this way)
        
        Args:
            missing_slots: List of (account_id, date, hour) tuples
            
        Returns:
            List of batch dictionaries ready for API calls
        """
        if not missing_slots:
            return []
            
        # Group by date and collect unique accounts
        date_accounts = defaultdict(set)
        for account_id, date_val, hour in missing_slots:
            date_accounts[date_val].add(account_id)
        
        # Create batches
        api_batches = []
        max_accounts_per_batch = self.config.hourly_batch_size
        
        for date_val, account_ids in sorted(date_accounts.items()):
            account_list = sorted(list(account_ids))  # Sort for consistency
            
            # Split accounts into batches of 25
            for i in range(0, len(account_list), max_accounts_per_batch):
                batch_accounts = account_list[i:i + max_accounts_per_batch]
                
                batch = {
                    "dates": date_val.strftime("%Y%m%d"),
                    "accountIds": ",".join(batch_accounts),
                    "hours": ",".join(str(h) for h in range(24))  # Always fetch all hours
                }
                api_batches.append(batch)
        
        logger.info(f"Created {len(api_batches)} API batches from {len(missing_slots)} missing slots")
        return api_batches

    def _get_all_missing_daily_data(self) -> List[Tuple[str, date]]:
        """Get all missing daily account-date combinations based on gaps."""
        query = """
            -- Find gaps in daily data by comparing with alltime metrics
            WITH alltime_accounts AS (
                SELECT DISTINCT account_id
                FROM prop_trading_model.raw_metrics_alltime
            ),
            account_date_ranges AS (
                -- Get first and last trade dates from alltime metrics
                SELECT 
                    account_id,
                    first_trade_date,
                    CURRENT_DATE - INTERVAL '1 day' as end_date
                FROM prop_trading_model.raw_metrics_alltime
                WHERE first_trade_date IS NOT NULL
            ),
            expected_dates AS (
                -- Generate all dates between first trade and yesterday
                SELECT 
                    adr.account_id,
                    generate_series(
                        adr.first_trade_date, 
                        adr.end_date, 
                        '1 day'::interval
                    )::date as date
                FROM account_date_ranges adr
            ),
            existing_data AS (
                SELECT account_id, date
                FROM prop_trading_model.raw_metrics_daily
            )
            SELECT 
                ed.account_id,
                ed.date
            FROM expected_dates ed
            LEFT JOIN existing_data ex 
                ON ed.account_id = ex.account_id 
                AND ed.date = ex.date
            WHERE ex.account_id IS NULL
            ORDER BY ed.account_id, ed.date
            LIMIT 10000  -- Limit to prevent overwhelming the system
        """
        
        results = self.db_manager.model_db.execute_query(query)
        return [(row["account_id"], row["date"]) for row in results]

    def _get_all_missing_hourly_data(self) -> List[Tuple[str, date, int]]:
        """Get all missing hourly account-date-hour combinations."""
        query = """
            -- Find missing hourly data based on daily metrics
            WITH daily_data AS (
                SELECT DISTINCT account_id, date
                FROM prop_trading_model.raw_metrics_daily
                WHERE date >= CURRENT_DATE - INTERVAL '90 days'  -- Limit to recent data
            ),
            expected_hourly AS (
                -- Each day should have 24 hours
                SELECT 
                    d.account_id,
                    d.date,
                    h.hour
                FROM daily_data d
                CROSS JOIN generate_series(0, 23) as h(hour)
            ),
            existing_hourly AS (
                SELECT account_id, date, hour
                FROM prop_trading_model.raw_metrics_hourly
            )
            SELECT 
                e.account_id,
                e.date,
                e.hour
            FROM expected_hourly e
            LEFT JOIN existing_hourly h 
                ON e.account_id = h.account_id 
                AND e.date = h.date 
                AND e.hour = h.hour
            WHERE h.account_id IS NULL
            ORDER BY e.account_id, e.date, e.hour
            LIMIT 50000  -- Limit to prevent overwhelming the system
        """
        
        results = self.db_manager.model_db.execute_query(query)
        return [(row["account_id"], row["date"], row["hour"]) for row in results]

    def _ingest_daily_for_dates(self, dates: List[date]) -> int:
        """Ingest daily metrics for specific dates."""
        if not dates:
            return 0
            
        # Import transform and validation methods from original
        
        total_records = 0
        
        for target_date in dates:
            try:
                logger.info(f"Fetching daily metrics for {target_date}")
                
                batch_data = []
                date_str = target_date.strftime("%Y%m%d")
                
                for page_num, records in enumerate(
                    self.api_client.get_metrics(
                        metric_type="daily",
                        dates=[date_str],
                        limit=1000
                    )
                ):
                    logger.info(f"Processing page {page_num} with {len(records)} records")
                    
                    for record in records:
                        # Use transform method from original ingester
                        transformed = self._transform_daily_metric(record)
                        batch_data.append(transformed)
                        
                        if len(batch_data) >= self.config.batch_size:
                            self._insert_batch_with_upsert(batch_data, MetricType.DAILY)
                            total_records += len(batch_data)
                            batch_data = []
                
                # Insert remaining records
                if batch_data:
                    self._insert_batch_with_upsert(batch_data, MetricType.DAILY)
                    total_records += len(batch_data)
                    
            except Exception as e:
                logger.error(f"Error fetching daily metrics for {target_date}: {str(e)}")
                continue
        
        return total_records

    def _ingest_alltime_for_accounts(self, account_ids: Optional[List[str]]) -> int:
        """Ingest alltime metrics for specific accounts (or all if None)."""
        total_records = 0
        
        if account_ids is None:
            # Fetch all alltime metrics
            logger.info("Fetching all alltime metrics...")
            
            for page_num, records in enumerate(
                self.api_client.get_metrics(
                    metric_type="alltime",
                    limit=1000
                )
            ):
                batch_data = []
                logger.info(f"Processing page {page_num} with {len(records)} records")
                
                for record in records:
                    transformed = self._transform_alltime_metric(record)
                    batch_data.append(transformed)
                
                if batch_data:
                    self._insert_batch_with_upsert(batch_data, MetricType.ALLTIME)
                    total_records += len(batch_data)
        else:
            # Fetch in batches for specific accounts
            batch_size = self.config.account_batch_size
            
            for i in range(0, len(account_ids), batch_size):
                batch = account_ids[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(account_ids) + batch_size - 1) // batch_size
                
                logger.info(f"Processing alltime batch {batch_num}/{total_batches}")
                
                try:
                    batch_data = []
                    
                    for page_num, records in enumerate(
                        self.api_client.get_metrics(
                            metric_type="alltime",
                            account_ids=batch,
                            limit=50
                        )
                    ):
                        for record in records:
                            transformed = self._transform_alltime_metric(record)
                            batch_data.append(transformed)
                    
                    if batch_data:
                        self._insert_batch_with_upsert(batch_data, MetricType.ALLTIME)
                        total_records += len(batch_data)
                        
                    # Small delay between batches
                    if i + batch_size < len(account_ids):
                        time.sleep(0.1)
                        
                except Exception as e:
                    logger.error(f"Error processing alltime batch {batch_num}: {str(e)}")
                    continue
        
        return total_records

    def _ingest_hourly_for_missing(
        self, missing_data: List[Union[Tuple[str, date], Tuple[str, date, int]]]
    ) -> int:
        """Ingest hourly metrics for missing account-date(-hour) combinations."""
        if not missing_data:
            return 0
        
        # Check if we have precise hour-level data or just account-date pairs
        if missing_data and len(missing_data[0]) == 3:
            # New precise method: we have (account_id, date, hour) tuples
            return self._ingest_hourly_precise(missing_data)
        else:
            # Legacy method: we have (account_id, date) tuples
            return self._ingest_hourly_legacy(missing_data)
    
    def _ingest_hourly_precise(
        self, missing_slots: List[Tuple[str, date, int]]
    ) -> int:
        """
        Ingest hourly metrics using precise missing slot detection.
        
        This method uses optimized batching to minimize API calls while
        fetching only truly missing data.
        
        Args:
            missing_slots: List of (account_id, date, hour) tuples
            
        Returns:
            Number of records ingested
        """
        logger.info(f"Starting precise hourly ingestion for {len(missing_slots)} missing slots")
        
        # Create optimized API batches
        api_batches = self._create_hourly_api_batches(missing_slots)
        
        if not api_batches:
            logger.info("No API batches created - nothing to ingest")
            return 0
        
        total_records = 0
        total_inserted = 0
        
        for batch_idx, api_batch in enumerate(api_batches, 1):
            try:
                logger.info(f"Processing API batch {batch_idx}/{len(api_batches)} - "
                          f"Date: {api_batch['dates']}, "
                          f"Accounts: {len(api_batch['accountIds'].split(','))}")
                
                batch_data = []
                api_call_count = 0
                
                # Make API call with precise parameters
                for page_num, records in enumerate(
                    self.api_client.get_metrics(
                        metric_type="hourly",
                        account_ids=api_batch['accountIds'].split(','),
                        dates=[api_batch['dates']],
                        hours=[int(h) for h in api_batch['hours'].split(',')],
                        limit=1000
                    )
                ):
                    api_call_count += 1
                    logger.debug(f"API call {api_call_count} returned {len(records)} records")
                    
                    for record in records:
                        # Process all records since API call was made for missing data only
                        transformed = self._transform_hourly_metric(record)
                        batch_data.append(transformed)
                        
                        if len(batch_data) >= self.config.batch_size:
                            rows_inserted = self._insert_batch_with_upsert(batch_data, MetricType.HOURLY)
                            total_records += len(batch_data)
                            total_inserted += rows_inserted
                            logger.debug(f"Inserted batch of {len(batch_data)} records, {rows_inserted} new")
                            batch_data = []
                
                # Insert remaining records
                if batch_data:
                    rows_inserted = self._insert_batch_with_upsert(batch_data, MetricType.HOURLY)
                    total_records += len(batch_data)
                    total_inserted += rows_inserted
                    logger.debug(f"Inserted final batch of {len(batch_data)} records, {rows_inserted} new")
                
                # Small delay between API batches to avoid rate limiting
                if batch_idx < len(api_batches):
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Error processing API batch {batch_idx}: {str(e)}", exc_info=True)
                continue
        
        logger.info(f"Precise hourly ingestion complete: {total_records} records processed, "
                   f"{total_inserted} new records inserted")
        return total_records
    
    def _ingest_hourly_legacy(
        self, missing_data: List[Tuple[str, date]]
    ) -> int:
        """Legacy hourly ingestion method for backward compatibility."""
        if not missing_data:
            return 0
            
        # Group by account for efficient API calls
        account_dates = defaultdict(set)
        
        for account_id, date_val in missing_data:
            account_dates[account_id].add(date_val)
        
        total_records = 0
        batch_size = self.config.hourly_batch_size
        account_list = list(account_dates.keys())
        
        for i in range(0, len(account_list), batch_size):
            batch_accounts = account_list[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(account_list) + batch_size - 1) // batch_size
            
            logger.info(f"Processing hourly batch {batch_num}/{total_batches} (legacy method)")
            
            # Get all dates for this batch of accounts
            all_dates = set()
            for account in batch_accounts:
                all_dates.update(account_dates[account])
            
            # Convert dates to string format
            date_strings = [d.strftime("%Y%m%d") for d in sorted(all_dates)]
            
            try:
                batch_data = []
                
                for page_num, records in enumerate(
                    self.api_client.get_metrics(
                        metric_type="hourly",
                        account_ids=batch_accounts,
                        dates=date_strings,
                        hours=list(range(24)),  # Get all hours
                        limit=1000
                    )
                ):
                    for record in records:
                        transformed = self._transform_hourly_metric(record)
                        batch_data.append(transformed)
                        
                        if len(batch_data) >= self.config.batch_size:
                            self._insert_batch_with_upsert(batch_data, MetricType.HOURLY)
                            total_records += len(batch_data)
                            batch_data = []
                
                # Insert remaining records
                if batch_data:
                    self._insert_batch_with_upsert(batch_data, MetricType.HOURLY)
                    total_records += len(batch_data)
                
                # Delay between batches
                if i + batch_size < len(account_list):
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"Error processing hourly batch {batch_num}: {str(e)}")
                continue
        
        return total_records
    
    def _parse_date_from_record(self, record: Dict[str, Any]) -> Optional[date]:
        """Parse date from various record formats."""
        date_str = record.get("date", "")
        if date_str:
            if "T" in str(date_str):  # ISO format
                return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            elif len(str(date_str)) == 8:  # YYYYMMDD format
                return datetime.strptime(str(date_str), "%Y%m%d").date()
        return None

    def _ingest_daily_for_missing(self, missing_data: List[Tuple[str, date]]) -> int:
        """Ingest daily metrics for missing account-date combinations."""
        if not missing_data:
            return 0
            
        # Group by date for efficient API calls
        date_accounts = defaultdict(list)
        
        for account_id, date_val in missing_data:
            date_accounts[date_val].append(account_id)
        
        total_records = 0
        
        for date_val, account_ids in date_accounts.items():
            try:
                logger.info(f"Fetching daily metrics for {date_val} ({len(account_ids)} accounts)")
                
                batch_data = []
                date_str = date_val.strftime("%Y%m%d")
                
                # Process accounts in chunks
                for i in range(0, len(account_ids), 100):
                    chunk = account_ids[i:i + 100]
                    
                    for page_num, records in enumerate(
                        self.api_client.get_metrics(
                            metric_type="daily",
                            account_ids=chunk,
                            dates=[date_str],
                            limit=1000
                        )
                    ):
                        for record in records:
                            transformed = self._transform_daily_metric(record)
                            batch_data.append(transformed)
                            
                            if len(batch_data) >= self.config.batch_size:
                                self._insert_batch_with_upsert(batch_data, MetricType.DAILY)
                                total_records += len(batch_data)
                                batch_data = []
                
                # Insert remaining records
                if batch_data:
                    self._insert_batch_with_upsert(batch_data, MetricType.DAILY)
                    total_records += len(batch_data)
                    
            except Exception as e:
                logger.error(f"Error fetching daily metrics for {date_val}: {str(e)}")
                continue
        
        return total_records

    def _insert_batch_with_upsert(self, batch_data: List[Dict[str, Any]], metric_type: MetricType) -> int:
        """Insert batch with proper ON CONFLICT handling."""
        if not batch_data:
            return 0
            
        table_name = self.table_mapping[metric_type]
        
        try:
            columns = list(batch_data[0].keys())
            placeholders = ", ".join(["%s"] * len(columns))
            columns_str = ", ".join(columns)
            
            # Get conflict clause based on table type
            if metric_type == MetricType.ALLTIME:
                conflict_clause = "ON CONFLICT (account_id) DO UPDATE SET"
                conflict_keys = ["account_id"]
            elif metric_type == MetricType.HOURLY:
                conflict_clause = "ON CONFLICT (account_id, date, hour) DO UPDATE SET"
                conflict_keys = ["account_id", "date", "hour"]
            else:  # DAILY
                conflict_clause = "ON CONFLICT (account_id, date) DO UPDATE SET"
                conflict_keys = ["account_id", "date"]
            
            # Build update SET clause
            update_columns = [col for col in columns if col not in conflict_keys]
            update_set = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
            
            query = f"""
                INSERT INTO {table_name} ({columns_str})
                VALUES ({placeholders})
                {conflict_clause} {update_set}
            """
            
            values = [
                tuple(record[col] for col in columns) for record in batch_data
            ]
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    from psycopg2.extras import execute_batch
                    execute_batch(cursor, query, values, page_size=1000)
                    rows_affected = cursor.rowcount
                    conn.commit()
                    
            logger.debug(f"Inserted/updated {rows_affected} records into {table_name}")
            # Return actual rows affected to distinguish between inserts and updates
            return rows_affected
            
        except Exception as e:
            logger.error(f"Failed to insert batch: {str(e)}")
            raise

    def _log_summary(self, results: Dict[str, int]):
        """Log ingestion summary."""
        total_records = sum(results.values())
        logger.info(f"\n{'=' * 60}")
        logger.info("INTELLIGENT INGESTION SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"Total records processed: {total_records}")
        for metric_type, count in results.items():
            logger.info(f"  - {metric_type.capitalize()} metrics: {count} records")

    # Transform methods copied directly from original implementation
    def _transform_alltime_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform all-time metric record with comprehensive field mapping."""
        record = {
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/alltime"
        }
        
        # Process ONLY fields that are in our field mapping to avoid unmapped fields
        for api_field, db_field in self.alltime_field_mapping.items():
            if api_field in metric:
                value = metric.get(api_field)
                
                # Handle specific data types
                if db_field in ['login', 'account_id', 'trader_id', 'country', 'most_traded_symbol']:
                    record[db_field] = str(value) if value is not None else None
                elif db_field in ['plan_id', 'status', 'type', 'phase', 'broker', 'platform', 'price_stream',
                                'days_since_initial_deposit', 'days_since_first_trade', 'num_trades',
                                'max_num_trades_in_dd',  # Only max is integer
                                'median_num_consec_wins', 'max_num_consec_wins',
                                'median_num_consec_losses', 'max_num_consec_losses',
                                'median_num_open_pos', 'max_num_open_pos',
                                'median_trades_per_day', 'min_trades_per_day', 'max_trades_per_day',
                                'median_idle_days', 'max_idle_days', 'min_idle_days',
                                'num_traded_symbols', 'most_traded_smb_trades']:
                    record[db_field] = self._safe_int(value)
                elif db_field == 'first_trade_date':
                    record[db_field] = self._parse_date(value)
                elif db_field in ['first_trade_open', 'last_trade_open', 'last_trade_close', 'updated_date']:
                    record[db_field] = self._parse_timestamp(value)
                elif db_field in ['gain_to_pain', 'risk_adj_profit', 'daily_sharpe', 'daily_sortino', 
                                'mean_ret', 'std_rets', 'risk_adj_ret',
                                'downside_std_rets', 'downside_risk_adj_ret', 'total_ret', 'daily_mean_ret',
                                'daily_std_ret', 'daily_downside_std_ret', 'rel_risk_adj_profit',
                                'net_profit_per_usd_volume', 'gross_profit_per_usd_volume', 
                                'gross_loss_per_usd_volume', 'distance_gross_profit_loss_per_usd_volume',
                                'multiple_gross_profit_loss_per_usd_volume', 'multiple_gross_profit_loss_per_lot',
                                # Add DECIMAL(10,6) fields that need bounds checking
                                'lifetime_in_days', 'one_std_outlier_profit_contrib', 'two_std_outlier_profit_contrib',
                                'multiple_win_loss_lots', 'multiple_win_loss_volume', 'cv_durations', 'cv_tp', 'cv_sl',
                                'mean_tp_vs_sl', 'median_tp_vs_sl', 'min_tp_vs_sl', 'max_tp_vs_sl', 'cv_tp_vs_sl',
                                'mean_val_to_eqty_open_pos', 'median_val_to_eqty_open_pos', 'max_val_to_eqty_open_pos',
                                'cv_trades_per_day',
                                # Add DECIMAL(5,2) fields that need bounds checking  
                                'success_rate', 'top_10_prcnt_profit_contrib', 'bottom_10_prcnt_loss_contrib']:
                    # Use bounds checking for fields prone to extreme values
                    record[db_field] = self._safe_bound_extreme(value, db_field)
                elif db_field in ['mean_num_trades_in_dd', 'median_num_trades_in_dd',  # FIXED: These are decimals
                                'mean_num_consec_wins', 'mean_num_consec_losses', 'mean_num_open_pos',
                                'mean_trades_per_day', 'mean_idle_days']:
                    # Decimal fields that represent averages/means
                    record[db_field] = self._safe_float(value)
                else:
                    # Default to float for numeric fields
                    record[db_field] = self._safe_float(value)

        return record

    def _transform_daily_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform daily metric record with comprehensive field mapping."""
        # Parse date from ISO format
        date_str = metric.get("date", "")
        metric_date = None
        if date_str:
            if "T" in str(date_str):  # ISO format
                metric_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            elif len(str(date_str)) == 8:  # YYYYMMDD format
                metric_date = datetime.strptime(str(date_str), "%Y%m%d").date()
        
        record = {
            "date": metric_date,
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/daily"
        }
        
        # Process ONLY fields that are in our field mapping to avoid unmapped fields
        for api_field, db_field in self.daily_field_mapping.items():
            if api_field in metric and db_field not in record:
                value = metric.get(api_field)
                
                # Handle specific data types
                if db_field in ['login', 'account_id', 'trader_id', 'country', 'most_traded_symbol']:
                    record[db_field] = str(value) if value is not None else None
                elif db_field in ['plan_id', 'status', 'type', 'phase', 'broker', 'platform', 'price_stream',
                                'days_since_initial_deposit', 'days_since_first_trade', 'num_trades',
                                'days_to_next_payout',  # ADDED: New daily-specific field
                                'max_num_trades_in_dd',  # Only max is integer
                                'median_num_consec_wins', 'max_num_consec_wins',
                                'median_num_consec_losses', 'max_num_consec_losses',
                                'median_num_open_pos', 'max_num_open_pos',
                                'median_trades_per_day', 'min_trades_per_day', 'max_trades_per_day',
                                'median_idle_days', 'max_idle_days', 'min_idle_days',
                                'num_traded_symbols', 'most_traded_smb_trades']:
                    record[db_field] = self._safe_int(value)
                elif db_field == 'first_trade_date':
                    record[db_field] = self._parse_date(value)
                elif db_field in ['first_trade_open', 'last_trade_open', 'last_trade_close', 'updated_date']:
                    record[db_field] = self._parse_timestamp(value)
                elif db_field in ['gain_to_pain', 'risk_adj_profit', 'daily_sharpe', 'daily_sortino', 
                                'mean_ret', 'std_rets', 'risk_adj_ret',
                                'downside_std_rets', 'downside_risk_adj_ret', 'total_ret', 'daily_mean_ret',
                                'daily_std_ret', 'daily_downside_std_ret', 'rel_risk_adj_profit',
                                'net_profit_per_usd_volume', 'gross_profit_per_usd_volume', 
                                'gross_loss_per_usd_volume', 'distance_gross_profit_loss_per_usd_volume',
                                'multiple_gross_profit_loss_per_usd_volume', 'multiple_gross_profit_loss_per_lot',
                                # Add DECIMAL(10,6) fields that need bounds checking
                                'lifetime_in_days', 'one_std_outlier_profit_contrib', 'two_std_outlier_profit_contrib',
                                'multiple_win_loss_lots', 'multiple_win_loss_volume', 'cv_durations', 'cv_tp', 'cv_sl',
                                'mean_tp_vs_sl', 'median_tp_vs_sl', 'min_tp_vs_sl', 'max_tp_vs_sl', 'cv_tp_vs_sl',
                                'mean_val_to_eqty_open_pos', 'median_val_to_eqty_open_pos', 'max_val_to_eqty_open_pos',
                                'cv_trades_per_day',
                                # Add DECIMAL(5,2) fields that need bounds checking  
                                'success_rate', 'top_10_prcnt_profit_contrib', 'bottom_10_prcnt_loss_contrib']:
                    # Use bounds checking for fields prone to extreme values
                    record[db_field] = self._safe_bound_extreme(value, db_field)
                elif db_field in ['mean_num_trades_in_dd', 'median_num_trades_in_dd',  # FIXED: These are decimals
                                'mean_num_consec_wins', 'mean_num_consec_losses', 'mean_num_open_pos',  # FIXED: These can be decimals
                                'mean_trades_per_day', 'mean_idle_days',
                                'todays_payouts']:  # ADDED: New daily-specific field
                    # Decimal fields that represent averages/means or can be decimal values
                    record[db_field] = self._safe_float(value)
                else:
                    # Default to float for numeric fields
                    record[db_field] = self._safe_float(value)
        
        return record

    def _transform_hourly_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform hourly metric record with comprehensive field mapping."""
        # Parse date from ISO format
        date_str = metric.get("date", "")
        metric_date = None
        if date_str:
            if "T" in str(date_str):  # ISO format
                metric_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            elif len(str(date_str)) == 8:  # YYYYMMDD format
                metric_date = datetime.strptime(str(date_str), "%Y%m%d").date()
        
        # Parse datetime for hourly-specific timestamp
        datetime_str = metric.get("datetime", "")
        metric_datetime = None
        if datetime_str:
            if "T" in str(datetime_str):  # ISO format
                metric_datetime = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        
        record = {
            "date": metric_date,
            "datetime": metric_datetime,  # ADDED: Hourly-specific datetime field
            "hour": self._safe_int(metric.get("hour")),  # ADDED: Hour field
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/hourly"
        }
        
        # Process ONLY fields that are in our field mapping to avoid unmapped fields
        for api_field, db_field in self.hourly_field_mapping.items():
            if api_field in metric and db_field not in record:
                value = metric.get(api_field)
                
                # Handle specific data types
                if db_field in ['login', 'account_id', 'trader_id', 'country', 'most_traded_symbol']:
                    record[db_field] = str(value) if value is not None else None
                elif db_field in ['plan_id', 'status', 'type', 'phase', 'broker', 'platform', 'price_stream',
                                'days_since_initial_deposit', 'days_since_first_trade', 'num_trades',
                                'days_to_next_payout',  # Hourly-specific field
                                'max_num_trades_in_dd',  # Only max is integer
                                'median_num_consec_wins', 'max_num_consec_wins',
                                'median_num_consec_losses', 'max_num_consec_losses',
                                'median_num_open_pos', 'max_num_open_pos',
                                'median_trades_per_day', 'min_trades_per_day', 'max_trades_per_day',
                                'median_idle_days', 'max_idle_days', 'min_idle_days',
                                'num_traded_symbols', 'most_traded_smb_trades']:
                    record[db_field] = self._safe_int(value)
                elif db_field == 'first_trade_date':
                    record[db_field] = self._parse_date(value)
                elif db_field in ['first_trade_open', 'last_trade_open', 'last_trade_close', 'updated_date']:
                    record[db_field] = self._parse_timestamp(value)
                elif db_field in ['gain_to_pain', 'risk_adj_profit', 'daily_sharpe', 'daily_sortino', 
                                'mean_ret', 'std_rets', 'risk_adj_ret',
                                'downside_std_rets', 'downside_risk_adj_ret', 'total_ret', 'daily_mean_ret',
                                'daily_std_ret', 'daily_downside_std_ret', 'rel_risk_adj_profit',
                                'net_profit_per_usd_volume', 'gross_profit_per_usd_volume', 
                                'gross_loss_per_usd_volume', 'distance_gross_profit_loss_per_usd_volume',
                                'multiple_gross_profit_loss_per_usd_volume', 'multiple_gross_profit_loss_per_lot',
                                # Add DECIMAL(10,6) fields that need bounds checking
                                'lifetime_in_days', 'one_std_outlier_profit_contrib', 'two_std_outlier_profit_contrib',
                                'multiple_win_loss_lots', 'multiple_win_loss_volume', 'cv_durations', 'cv_tp', 'cv_sl',
                                'mean_tp_vs_sl', 'median_tp_vs_sl', 'min_tp_vs_sl', 'max_tp_vs_sl', 'cv_tp_vs_sl',
                                'mean_val_to_eqty_open_pos', 'median_val_to_eqty_open_pos', 'max_val_to_eqty_open_pos',
                                'cv_trades_per_day',
                                # Add DECIMAL(5,2) fields that need bounds checking  
                                'success_rate', 'top_10_prcnt_profit_contrib', 'bottom_10_prcnt_loss_contrib']:
                    # Use bounds checking for fields prone to extreme values
                    record[db_field] = self._safe_bound_extreme(value, db_field)
                elif db_field in ['mean_num_trades_in_dd', 'median_num_trades_in_dd',  # FIXED: These can be decimals
                                'mean_num_consec_wins', 'mean_num_consec_losses', 'mean_num_open_pos',  # FIXED: These can be decimals
                                'mean_trades_per_day', 'mean_idle_days',
                                'todays_payouts']:  # Hourly-specific field
                    # Decimal fields that represent averages/means or can be decimal values
                    record[db_field] = self._safe_float(value)
                else:
                    # Default to float for numeric fields, with proper null handling
                    record[db_field] = self._safe_float(value)
        
        return record

    # Helper methods for transform functions
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value) -> Optional[int]:
        """Safely convert to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string to date object."""
        if not date_str:
            return None
        try:
            # Handle ISO format with time component
            if 'T' in date_str:
                return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            else:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            logger.warning(f"Could not parse date: {date_str}")
            return None

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse various timestamp formats."""
        if not timestamp_str:
            return None
        
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
        
        logger.warning(f"Could not parse timestamp: {timestamp_str}")
        return None

    def _safe_bound_extreme(self, value: Any, field_name: str) -> Optional[float]:
        """Safely handle extreme values that might cause numeric overflow."""
        val = self._safe_float(value)
        if val is None:
            return None
        
        # Fields with DECIMAL(10,6) precision can only hold values < 10^4 = 10,000
        decimal_10_6_fields = [
            'lifetime_in_days', 'one_std_outlier_profit_contrib', 'two_std_outlier_profit_contrib',
            'multiple_win_loss_lots', 'multiple_win_loss_volume', 'cv_durations', 'cv_tp', 'cv_sl',
            'mean_tp_vs_sl', 'median_tp_vs_sl', 'min_tp_vs_sl', 'max_tp_vs_sl', 'cv_tp_vs_sl',
            'mean_val_to_eqty_open_pos', 'median_val_to_eqty_open_pos', 'max_val_to_eqty_open_pos',
            'cv_trades_per_day'
        ]
        
        # Fields with DECIMAL(5,2) precision can only hold values < 10^3 = 1,000  
        decimal_5_2_fields = [
            'success_rate', 'top_10_prcnt_profit_contrib', 'bottom_10_prcnt_loss_contrib'
        ]
        
        if field_name in decimal_10_6_fields:
            # DECIMAL(10,6) fields can only hold values with absolute value < 10^4
            if abs(val) >= 9999.999999:  # Leave small margin for safety
                return 9999.999999 if val > 0 else -9999.999999
        elif field_name in decimal_5_2_fields:
            # DECIMAL(5,2) fields can only hold values with absolute value < 10^3
            if abs(val) >= 999.99:  # Leave small margin for safety
                return 999.99 if val > 0 else -999.99
        
        # Define reasonable bounds for different metric types
        if 'ratio' in field_name or 'sharpe' in field_name or 'sortino' in field_name:
            # Ratios and Sharpe/Sortino can be extreme but cap at ±1000
            if abs(val) > 1000:
                return 1000.0 if val > 0 else -1000.0
        elif 'per_usd_volume' in field_name or 'per_lot' in field_name:
            # Per-unit metrics can be very large in edge cases
            if abs(val) > 1000000:
                return 1000000.0 if val > 0 else -1000000.0
        elif 'multiple' in field_name:
            # Multiples should be reasonable - but this was already handled above for DECIMAL(10,6)
            if abs(val) > 10000:
                return 10000.0 if val > 0 else -10000.0
        
        # For DOUBLE PRECISION fields, PostgreSQL can handle ±1.7976931348623157E+308
        # but we'll use a reasonable cap to avoid issues
        if abs(val) > 1e15:  # 1 quadrillion
            return 1e15 if val > 0 else -1e15
        
        return val

    def close(self):
        """Close the ingester and clean up resources."""
        try:
            if hasattr(self.api_client, 'close'):
                self.api_client.close()
        except Exception as e:
            logger.error(f"Error closing API client: {str(e)}")

        # Clean up database connections if available
        try:
            if hasattr(self, 'db_manager') and hasattr(self.db_manager, 'close'):
                self.db_manager.close()
        except Exception as e:
            logger.error(f"Error closing database manager: {str(e)}")


def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Intelligent metrics ingestion - only fetches missing data"
    )
    
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for ingestion (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for ingestion (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force full refresh (ignore existing data)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    from utils.logging_config import setup_logging
    setup_logging(log_level=args.log_level, log_file="intelligent_metrics_ingestion")

    # Run ingestion
    ingester = IntelligentMetricsIngester()

    try:
        if args.start_date:
            # Flow 1: Date range provided
            ingester.ingest_with_date_range(
                start_date=args.start_date,
                end_date=args.end_date,
                force_full_refresh=args.force_refresh,
            )
        else:
            # Flow 2: No date range
            ingester.ingest_without_date_range(
                force_full_refresh=args.force_refresh,
            )
            
        logger.info("Intelligent ingestion complete")
        
    except Exception as e:
        logger.error(f"Ingestion failed: {str(e)}", exc_info=True)
        raise
    finally:
        ingester.close()


if __name__ == "__main__":
    main()