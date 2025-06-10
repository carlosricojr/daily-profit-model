"""
Enhanced metrics ingester v2 with comprehensive risk factors support.
Includes all fields from /v2/metrics API based on project whitepaper requirements.
"""

import os
import sys
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import hashlib

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


class MetricsIngesterV2(BaseIngester):
    """Enhanced metrics ingester with comprehensive risk factors support."""

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        enable_validation: bool = True,
        enable_deduplication: bool = True,
    ):
        """Initialize the enhanced metrics ingester."""
        # Initialize base class with a dummy table name (we'll use multiple tables)
        super().__init__(
            ingestion_type="metrics",
            table_name="raw_metrics_alltime",  # Default table
            checkpoint_dir=checkpoint_dir,
            enable_validation=enable_validation,
            enable_deduplication=enable_deduplication,
        )

        # We'll initialize the base class for each metric type as needed
        self.checkpoint_dir = checkpoint_dir
        self.enable_validation = enable_validation
        self.enable_deduplication = enable_deduplication

        # Initialize API client
        self.api_client = RiskAnalyticsAPIClient()

        # Table mapping for different metric types
        self.table_mapping = {
            MetricType.ALLTIME: "raw_metrics_alltime",
            MetricType.DAILY: "raw_metrics_daily",
            MetricType.HOURLY: "raw_metrics_hourly",
        }

        # Initialize separate checkpoint managers and metrics for each type
        self.checkpoint_managers = {}
        self.metrics_by_type = {}

        for metric_type in MetricType:
            # Initialize base ingester components for each metric type
            checkpoint_file = os.path.join(
                checkpoint_dir
                or os.path.join(os.path.dirname(__file__), "checkpoints"),
                f"metrics_{metric_type.value}_checkpoint.json",
            )
            self.checkpoint_managers[metric_type.value] = CheckpointManager(
                checkpoint_file, f"metrics_{metric_type.value}"
            )
            self.metrics_by_type[metric_type.value] = IngestionMetrics()
        
        # Initialize comprehensive field mappings
        self._init_field_mappings()

    def _init_field_mappings(self):
        """Initialize comprehensive field mappings for all metric fields."""
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
            'mt_version': 'mt_version',
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
            'sharpeRatio': 'sharpe_ratio',
            'sortinoRatio': 'sortino_ratio'
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
            'maxDrawdownPct': 'max_drawdown_pct'
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
        self.daily_specific_fields = {
            'days_to_next_payout': 'days_to_next_payout',
            'todays_payouts': 'todays_payouts'
        }
        
        # Other fields
        self.other_fields = {
            'updatedDate': 'updated_date',
            'averageWin': 'average_win',
            'averageLoss': 'average_loss',
            'averageRRR': 'average_rrr',
            'totalTrades': 'total_trades',
            'winningTrades': 'winning_trades',
            'losingTrades': 'losing_trades',
            'winRate': 'win_rate',
            'commission': 'commission',
            'swap': 'swap'
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
            **self.other_fields
        }
        
        # Daily metrics include most alltime fields plus daily-specific
        self.daily_field_mapping = {
            **self.alltime_field_mapping,
            **self.daily_specific_fields
        }
        
        # Hourly metrics use similar fields as daily
        self.hourly_field_mapping = self.daily_field_mapping.copy()

    def _transform_alltime_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform all-time metric record with comprehensive field mapping."""
        record = {
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/alltime"
        }
        
        # Process all fields using field mappings
        for api_field, db_field in self.alltime_field_mapping.items():
            if api_field in metric:
                value = metric.get(api_field)
                
                # Handle specific data types
                if db_field in ['login', 'account_id', 'plan_id', 'trader_id', 'country', 'most_traded_symbol']:
                    record[db_field] = str(value) if value is not None else None
                elif db_field in ['status', 'type', 'phase', 'broker', 'mt_version', 'price_stream',
                                 'days_since_initial_deposit', 'days_since_first_trade', 'num_trades',
                                 'total_trades', 'winning_trades', 'losing_trades',
                                 'mean_num_trades_in_dd', 'median_num_trades_in_dd', 'max_num_trades_in_dd',
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
        
        # Process all fields using field mappings
        for api_field, db_field in self.daily_field_mapping.items():
            if api_field in metric and db_field not in record:
                value = metric.get(api_field)
                
                # Handle specific data types (same as alltime)
                if db_field in ['login', 'account_id', 'plan_id', 'trader_id', 'country', 'most_traded_symbol']:
                    record[db_field] = str(value) if value is not None else None
                elif db_field in ['status', 'type', 'phase', 'broker', 'mt_version', 'price_stream',
                                 'days_since_initial_deposit', 'days_since_first_trade', 'num_trades',
                                 'days_to_next_payout', 'total_trades', 'winning_trades', 'losing_trades',
                                 'mean_num_trades_in_dd', 'median_num_trades_in_dd', 'max_num_trades_in_dd',
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
                else:
                    # Default to float for numeric fields
                    record[db_field] = self._safe_float(value)
        
        # Handle fields that may have different names in daily vs alltime
        if 'priorDaysBalance' in metric:
            record['balance_start'] = self._safe_float(metric['priorDaysBalance'])
        if 'currentBalance' in metric:
            record['balance_end'] = self._safe_float(metric['currentBalance'])
        if 'priorDaysEquity' in metric:
            record['equity_start'] = self._safe_float(metric['priorDaysEquity'])
        if 'currentEquity' in metric:
            record['equity_end'] = self._safe_float(metric['currentEquity'])
        
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
        
        record = {
            "date": metric_date,
            "hour": metric.get("hour"),
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/hourly"
        }
        
        # Process core fields that are relevant for hourly metrics
        # Hourly metrics typically have fewer fields than daily/alltime
        hourly_relevant_fields = [
            'login', 'account_id', 'net_profit', 'gross_profit', 'gross_loss',
            'total_trades', 'winning_trades', 'losing_trades', 'win_rate',
            'lots_traded', 'volume_traded'
        ]
        
        for api_field, db_field in self.hourly_field_mapping.items():
            if api_field in metric and db_field in hourly_relevant_fields:
                value = metric.get(api_field)
                
                if db_field in ['login', 'account_id']:
                    record[db_field] = str(value) if value is not None else None
                elif db_field in ['total_trades', 'winning_trades', 'losing_trades']:
                    record[db_field] = self._safe_int(value)
                else:
                    record[db_field] = self._safe_float(value)
        
        # Handle specific mappings
        if 'numTrades' in metric:
            record['total_trades'] = self._safe_int(metric['numTrades'])
        if 'successRate' in metric:
            record['win_rate'] = self._safe_float(metric['successRate'])
        if 'totalLots' in metric:
            record['lots_traded'] = self._safe_float(metric['totalLots'])
        if 'totalVolume' in metric:
            record['volume_traded'] = self._safe_float(metric['totalVolume'])
        
        return record
    
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
    
    def _bound_decimal_10_2(self, value: Any) -> Optional[float]:
        """Bound value to fit in DECIMAL(10,2) - max 99999999.99."""
        val = self._safe_float(value)
        if val is None:
            return None
        # DECIMAL(10,2) can hold max 8 digits before decimal
        if abs(val) >= 100000000:  # 10^8
            return None  # Too large to fit
        return val

    # The rest of the methods remain the same as in the original MetricsIngester
    # Including: _validate_record, _get_record_key, _get_conflict_clause, 
    # ingest_metrics, _ingest_alltime_metrics, _ingest_time_series_metrics, close, main
    
    # ... (copy remaining methods from original file)


def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest metrics data with comprehensive risk factors support"
    )
    parser.add_argument(
        "metric_type",
        choices=["alltime", "daily", "hourly"],
        help="Type of metrics to ingest",
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for daily/hourly metrics (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for daily/hourly metrics (YYYY-MM-DD)",
    )
    parser.add_argument("--logins", nargs="+", help="Specific login IDs to fetch")
    parser.add_argument("--accountids", nargs="+", help="Specific account IDs to fetch")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force full refresh (truncate and reload)",
    )
    parser.add_argument(
        "--no-resume", action="store_true", help="Do not resume from checkpoint"
    )
    parser.add_argument(
        "--no-validation", action="store_true", help="Disable data validation"
    )
    parser.add_argument(
        "--no-deduplication", action="store_true", help="Disable deduplication"
    )
    parser.add_argument("--checkpoint-dir", help="Directory for checkpoint files")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    from utils.logging_config import setup_logging

    setup_logging(
        log_level=args.log_level, log_file=f"ingest_metrics_v2_{args.metric_type}"
    )

    # Run ingestion
    ingester = MetricsIngesterV2(
        checkpoint_dir=args.checkpoint_dir,
        enable_validation=not args.no_validation,
        enable_deduplication=not args.no_deduplication,
    )

    try:
        records = ingester.ingest_metrics(
            metric_type=args.metric_type,
            start_date=args.start_date,
            end_date=args.end_date,
            logins=args.logins,
            accountids=args.accountids,
            force_full_refresh=args.force_refresh,
            resume_from_checkpoint=not args.no_resume,
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    finally:
        ingester.close()


if __name__ == "__main__":
    main()