"""
Enhanced metrics ingester with comprehensive risk factors support.
Includes all fields from /v2/metrics API based on project whitepaper requirements.
"""

import os
import sys
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from enum import Enum

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


class MetricsIngester(BaseIngester):
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

        # Add configuration
        self.config = type('Config', (), {
            'batch_size': 1000,
            'max_retries': 3,
            'timeout': 30
        })()

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
                                'multiple_gross_profit_loss_per_usd_volume', 'multiple_gross_profit_loss_per_lot']:
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
        
        # Process all fields using field mappings
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
                                'multiple_gross_profit_loss_per_usd_volume', 'multiple_gross_profit_loss_per_lot']:
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
        
        # Process all fields using field mappings (same comprehensive approach as daily/alltime)
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
                                'multiple_gross_profit_loss_per_usd_volume', 'multiple_gross_profit_loss_per_lot']:
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
        
        # Handle fields that may have different names in hourly vs daily/alltime
        if 'priorDaysBalance' in metric:
            record['balance_start'] = self._safe_float(metric['priorDaysBalance'])
        if 'currentBalance' in metric:
            record['balance_end'] = self._safe_float(metric['currentBalance'])
        if 'priorDaysEquity' in metric:
            record['equity_start'] = self._safe_float(metric['priorDaysEquity'])
        if 'currentEquity' in metric:
            record['equity_end'] = self._safe_float(metric['currentEquity'])
        
        # Handle specific hourly mappings (if needed for backward compatibility)
        if 'numTrades' in metric and 'num_trades' not in record:
            record['num_trades'] = self._safe_int(metric['numTrades'])
        if 'successRate' in metric and 'win_rate' not in record:
            record['win_rate'] = self._safe_float(metric['successRate'])
        if 'totalLots' in metric and 'lots_traded' not in record:
            record['lots_traded'] = self._safe_float(metric['totalLots'])
        if 'totalVolume' in metric and 'volume_traded' not in record:
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
    
    def _safe_bound_extreme(self, value: Any, field_name: str) -> Optional[float]:
        """Safely handle extreme values that might cause numeric overflow."""
        val = self._safe_float(value)
        if val is None:
            return None
        
        # Define reasonable bounds for different metric types
        if 'ratio' in field_name or 'sharpe' in field_name or 'sortino' in field_name:
            # Ratios and Sharpe/Sortino can be extreme but cap at ±1000
            if abs(val) > 1000:
                logger.debug(f"Capping extreme {field_name} value: {val} -> {1000 if val > 0 else -1000}")
                return 1000.0 if val > 0 else -1000.0
        elif 'per_usd_volume' in field_name or 'per_lot' in field_name:
            # Per-unit metrics can be very large in edge cases
            if abs(val) > 1000000:
                logger.debug(f"Capping extreme {field_name} value: {val} -> {1000000 if val > 0 else -1000000}")
                return 1000000.0 if val > 0 else -1000000.0
        elif 'multiple' in field_name:
            # Multiples should be reasonable
            if abs(val) > 10000:
                logger.debug(f"Capping extreme {field_name} value: {val} -> {10000 if val > 0 else -10000}")
                return 10000.0 if val > 0 else -10000.0
        
        # For DOUBLE PRECISION fields, PostgreSQL can handle ±1.7976931348623157E+308
        # but we'll use a reasonable cap to avoid issues
        if abs(val) > 1e15:  # 1 quadrillion
            logger.warning(f"Extremely large value for {field_name}: {val}, capping at ±1e15")
            return 1e15 if val > 0 else -1e15
        
        return val

    def _validate_record(
        self, record: Dict[str, Any], metric_type: MetricType
    ) -> Optional[str]:
        """Validate a transformed record."""
        if not self.enable_validation:
            return None

        # Required fields validation
        required_fields = ["account_id", "login"]
        if metric_type != MetricType.ALLTIME:
            required_fields.append("date")

        for field in required_fields:
            if field not in record or record[field] is None:
                return f"Missing required field: {field}"

        # Account ID should be a string
        if not isinstance(record.get("account_id"), str):
            return "account_id must be a string"

        # Validate date format for time-series metrics
        if metric_type != MetricType.ALLTIME and "date" in record:
            if not isinstance(record["date"], date):
                return "date must be a date object"

        return None

    def _get_record_key(self, record: Dict[str, Any], metric_type: MetricType) -> str:
        """Generate unique key for record deduplication."""
        if metric_type == MetricType.ALLTIME:
            return f"{record['account_id']}"
        elif metric_type == MetricType.HOURLY:
            return f"{record['account_id']}_{record['date']}_{record.get('hour', 0)}"
        else:  # DAILY
            return f"{record['account_id']}_{record['date']}"

    def _get_conflict_clause(self, table_name: str) -> str:
        """Get the ON CONFLICT clause for the table."""
        if "alltime" in table_name:
            return "ON CONFLICT (account_id) DO UPDATE SET"
        elif "hourly" in table_name:
            return "ON CONFLICT (account_id, date, hour) DO UPDATE SET"
        else:  # daily
            return "ON CONFLICT (account_id, date) DO UPDATE SET"

    def ingest_metrics(
        self,
        metric_type: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        logins: Optional[List[str]] = None,
        accountids: Optional[List[str]] = None,
        force_full_refresh: bool = False,
        resume_from_checkpoint: bool = True,
    ) -> int:
        """Ingest metrics data for the specified type."""
        try:
            # Parse metric type
            metric_enum = MetricType(metric_type.lower())
        except ValueError:
            raise ValueError(f"Invalid metric type: {metric_type}")

        # Set table name for this ingestion
        self.table_name = self.table_mapping[metric_enum]
        
        # Get the appropriate checkpoint manager and metrics
        checkpoint_manager = self.checkpoint_managers[metric_enum.value]
        metrics = self.metrics_by_type[metric_enum.value]
        
        # Override base class attributes for this run
        self.checkpoint_manager = checkpoint_manager
        self.metrics = metrics

        logger.info(
            f"Starting {metric_type} metrics ingestion to table {self.table_name}"
        )

        # Initialize checkpoint
        checkpoint = None
        if resume_from_checkpoint and not force_full_refresh:
            checkpoint = checkpoint_manager.load_checkpoint()
            if checkpoint:
                logger.info(f"Resuming from checkpoint: {checkpoint}")

        if force_full_refresh:
            logger.info(f"Force refresh: truncating {self.table_name}")
            self._truncate_table()
            checkpoint_manager.clear_checkpoint()

        try:
            if metric_enum == MetricType.ALLTIME:
                total_records = self._ingest_alltime_metrics(
                    logins, accountids, checkpoint
                )
            else:
                total_records = self._ingest_time_series_metrics(
                    metric_enum, start_date, end_date, logins, accountids, checkpoint
                )

            # Save final checkpoint
            checkpoint_manager.save_checkpoint(
                {
                    "metric_type": metric_type,
                    "completion_time": datetime.now().isoformat(),
                    "total_records": total_records,
                    "metrics": metrics.to_dict(),
                }
            )

            # Log final metrics
            logger.info(f"Ingestion complete: {total_records} records processed")
            metrics.log_final_summary()

            return total_records

        except Exception as e:
            logger.error(f"Ingestion failed: {str(e)}")
            raise

    def _ingest_alltime_metrics(
        self,
        logins: Optional[List[str]] = None,
        accountids: Optional[List[str]] = None,
        checkpoint: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Ingest all-time metrics data with enhanced risk factors."""
        try:
            # Resume from checkpoint
            start_page = 1
            if checkpoint:
                start_page = checkpoint.get("last_processed_page", 1) + 1
                if start_page > 1:
                    logger.info(f"Resuming from page {start_page}")

            batch_data = []
            pages_received = 0

            for page_num, records in enumerate(
                self.api_client.get_metrics(
                    metric_type="alltime", logins=logins, accountids=accountids
                )
            ):
                pages_received += 1
                # Skip pages already processed
                if page_num < start_page:
                    logger.info(f"Skipping already processed page {page_num}")
                    continue

                logger.info(f"Processing page {page_num} with {len(records)} records")

                for record in records:
                    try:
                        # Transform using enhanced field mappings
                        transformed = self._transform_alltime_metric(record)

                        # Validate record
                        validation_error = self._validate_record(
                            transformed, MetricType.ALLTIME
                        )
                        if validation_error:
                            logger.warning(f"Validation failed: {validation_error}")
                            self.metrics.validation_errors += 1
                            continue

                        # Check for duplicates
                        if self.enable_deduplication:
                            record_key = self._get_record_key(
                                transformed, MetricType.ALLTIME
                            )
                            if record_key in self.seen_records:
                                self.metrics.duplicate_records += 1
                                continue
                            self.seen_records.add(record_key)

                        batch_data.append(transformed)
                        self.metrics.new_records += 1

                        # Insert in batches
                        if len(batch_data) >= self.config.batch_size:
                            self._insert_batch(batch_data)
                            batch_data = []

                        # Save checkpoint periodically
                        if self.metrics.new_records % 10000 == 0:
                            self.checkpoint_manager.save_checkpoint(
                                {
                                    "metric_type": "alltime",
                                    "last_processed_page": page_num,
                                    "total_records": self.metrics.total_records,
                                    "metrics": self.metrics.to_dict(),
                                }
                            )

                    except Exception as e:
                        logger.error(f"Error processing record: {str(e)}")
                        self.metrics.invalid_records += 1

            # Insert remaining records
            if batch_data:
                self._insert_batch(batch_data)

            if pages_received == 0:
                logger.warning(f"No data pages received from API for {self.ingestion_type}")

            return self.metrics.new_records

        except Exception as e:
            if "API" in str(e) or "rate limit" in str(e):
                self.metrics.api_errors += 1
            logger.error(f"Error during alltime metrics ingestion: {str(e)}", exc_info=True)
            raise

    def _ingest_time_series_metrics(
        self,
        metric_type: MetricType,
        start_date: Optional[date],
        end_date: Optional[date],
        logins: Optional[List[str]],
        accountids: Optional[List[str]],
        checkpoint: Optional[Dict[str, Any]],
    ) -> int:
        """Ingest daily or hourly metrics data with enhanced risk factors."""
        # Determine date range
        if not end_date:
            end_date = datetime.now().date() - timedelta(days=1)
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Resume from checkpoint if available
        if checkpoint:
            checkpoint_date = checkpoint.get("last_processed_date")
            if checkpoint_date:
                start_date = datetime.strptime(checkpoint_date, "%Y-%m-%d").date()

        logger.info(f"Processing {metric_type.value} metrics from {start_date} to {end_date}")

        current_date = start_date
        total_records = 0

        while current_date <= end_date:
            try:
                logger.info(f"Processing {metric_type.value} metrics for {current_date}")

                batch_data = []
                pages_received = 0

                # Format date and prepare parameters
                date_str = current_date.strftime("%Y%m%d")
                hours = list(range(24)) if metric_type == MetricType.HOURLY else None

                for page_num, records in enumerate(
                    self.api_client.get_metrics(
                        metric_type=metric_type.value,
                        logins=logins,
                        accountids=accountids,
                        dates=[date_str],
                        hours=hours,
                    )
                ):
                    pages_received += 1

                    for record in records:
                        try:
                            # Transform using enhanced field mappings
                            if metric_type == MetricType.DAILY:
                                transformed = self._transform_daily_metric(record)
                            else:
                                transformed = self._transform_hourly_metric(record)

                            # Validate record
                            validation_error = self._validate_record(transformed, metric_type)
                            if validation_error:
                                logger.warning(f"Validation failed: {validation_error}")
                                self.metrics.validation_errors += 1
                                continue

                            # Check for duplicates
                            if self.enable_deduplication:
                                record_key = self._get_record_key(transformed, metric_type)
                                if record_key in self.seen_records:
                                    self.metrics.duplicate_records += 1
                                    continue
                                self.seen_records.add(record_key)

                            batch_data.append(transformed)
                            self.metrics.new_records += 1

                            # Insert in batches
                            if len(batch_data) >= self.config.batch_size:
                                self._insert_batch(batch_data)
                                batch_data = []

                        except Exception as e:
                            logger.error(f"Error processing record: {str(e)}")
                            self.metrics.invalid_records += 1

                # Insert remaining records for this date
                if batch_data:
                    self._insert_batch(batch_data)

                total_records += len(batch_data)

                # Save checkpoint after each date
                self.checkpoint_manager.save_checkpoint(
                    {
                        "metric_type": metric_type.value,
                        "last_processed_date": current_date.strftime("%Y-%m-%d"),
                        "total_records": total_records,
                        "metrics": self.metrics.to_dict(),
                    }
                )

                if pages_received == 0:
                    logger.info(f"No data for {current_date}")

            except Exception as e:
                logger.error(f"Error processing {current_date}: {str(e)}")
                self.metrics.api_errors += 1

            current_date += timedelta(days=1)

        return total_records

    def _truncate_table(self):
        """Truncate the current table."""
        try:
            query = f"TRUNCATE TABLE {self.table_name} CASCADE"
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    conn.commit()
            logger.info(f"Truncated table {self.table_name}")
        except Exception as e:
            logger.warning(f"Could not truncate table {self.table_name}: {str(e)}")
    
    def _insert_batch(self, records: List[Dict[str, Any]]) -> int:
        """Insert a batch of records with overflow protection."""
        if not records:
            return 0
        
        # Pre-process records to handle potential overflow
        processed_records = []
        for record in records:
            processed_record = record.copy()
            
            # Apply bounds checking to fields known to cause overflow
            overflow_fields = [
                'gain_to_pain', 'risk_adj_profit', 'daily_sharpe', 'daily_sortino',
                'sharpe_ratio', 'sortino_ratio', 'mean_ret', 'std_rets', 'risk_adj_ret',
                'downside_std_rets', 'downside_risk_adj_ret', 'total_ret', 'daily_mean_ret',
                'daily_std_ret', 'daily_downside_std_ret', 'rel_risk_adj_profit',
                'net_profit_per_usd_volume', 'gross_profit_per_usd_volume',
                'gross_loss_per_usd_volume', 'distance_gross_profit_loss_per_usd_volume',
                'multiple_gross_profit_loss_per_usd_volume', 'multiple_gross_profit_loss_per_lot'
            ]
            
            for field in overflow_fields:
                if field in processed_record and processed_record[field] is not None:
                    # For DECIMAL(18,10) fields, max value is 99,999,999.9999999999
                    value = processed_record[field]
                    if isinstance(value, (int, float)):
                        if abs(value) > 99999999:
                            logger.warning(
                                f"Capping overflow value for {field}: {value} -> "
                                f"{99999999 if value > 0 else -99999999}"
                            )
                            processed_record[field] = 99999999.0 if value > 0 else -99999999.0
            
            processed_records.append(processed_record)
        
        # Call parent's insert method with processed records
        return super()._insert_batch(processed_records)

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
        log_level=args.log_level, log_file=f"ingest_metrics_{args.metric_type}"
    )

    # Run ingestion
    ingester = MetricsIngester(
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