"""
Enhanced Feature Engineering Module V2
Incorporates comprehensive risk factors from the enhanced metrics API.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
import argparse
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging_config import setup_logging
from utils.query_performance import QueryPerformanceMonitor

# Import base classes from original engineer_features
from .engineer_features import (
    LookaheadBiasValidator, 
    FeatureQualityMonitor,
    OptimizedFeatureEngineer,
    PRODUCTION_CONFIG
)

# Updated feature version
FEATURE_VERSION = "4.0.0"  # Major version bump for comprehensive risk factors

logger = logging.getLogger(__name__)


class EnhancedFeatureEngineerV2(OptimizedFeatureEngineer):
    """
    Enhanced feature engineer that incorporates comprehensive risk factors
    from the metrics API based on project whitepaper requirements.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the enhanced feature engineer."""
        super().__init__()
        
        self.config = {**PRODUCTION_CONFIG, **(config or {})}
        
        # Add validation and monitoring
        self.bias_validator = LookaheadBiasValidator(strict_mode=True)
        self.quality_monitor = FeatureQualityMonitor(self.db_manager)
        
        # Enhanced performance monitoring
        self.query_monitor = QueryPerformanceMonitor(
            log_file=f"logs/feature_engineering_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        # Extended rolling windows for new risk metrics
        self.rolling_windows = [1, 3, 5, 7, 10, 20, 30]
        
        # Track overall performance
        self.performance_metrics = {
            "total_processing_time": 0,
            "total_records_processed": 0,
            "total_features_created": 0,
            "memory_peak_mb": 0,
            "errors_encountered": 0,
            "validation_violations": 0,
        }

    def _bulk_fetch_enhanced_metrics(
        self, account_ids: List[str], dates: List[date]
    ) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch enhanced metrics data including all risk factors."""
        self.query_stats["bulk_queries"] += 1
        self.query_stats["total_queries"] += len(account_ids) * len(dates)
        
        query = """
        SELECT 
            account_id,
            date,
            -- Core performance metrics
            net_profit,
            gross_profit,
            gross_loss,
            num_trades,
            winning_trades,
            losing_trades,
            win_rate,
            profit_factor,
            -- Enhanced risk metrics
            gain_to_pain,
            success_rate,
            mean_profit,
            median_profit,
            std_profits,
            risk_adj_profit,
            -- Distribution metrics
            min_profit,
            max_profit,
            profit_perc_10,
            profit_perc_25,
            profit_perc_75,
            profit_perc_90,
            -- Return metrics
            daily_sharpe,
            daily_sortino,
            mean_ret,
            std_rets,
            risk_adj_ret,
            downside_std_rets,
            downside_risk_adj_ret,
            -- Relative metrics
            rel_net_profit,
            rel_mean_profit,
            rel_median_profit,
            rel_std_profits,
            rel_risk_adj_profit,
            -- Drawdown metrics
            mean_drawdown,
            median_drawdown,
            max_drawdown,
            mean_num_trades_in_dd,
            median_num_trades_in_dd,
            max_num_trades_in_dd,
            -- Volume and lot metrics
            total_lots,
            total_volume,
            mean_winning_lot,
            mean_losing_lot,
            mean_winning_volume,
            mean_losing_volume,
            -- Duration metrics
            mean_duration,
            median_duration,
            std_durations,
            cv_durations,
            -- SL/TP metrics
            mean_tp,
            mean_sl,
            mean_tp_vs_sl,
            -- Consecutive patterns
            mean_num_consec_wins,
            max_num_consec_wins,
            mean_num_consec_losses,
            max_num_consec_losses,
            -- Position metrics
            mean_num_open_pos,
            max_num_open_pos,
            mean_val_open_pos,
            -- Activity metrics
            mean_trades_per_day,
            median_trades_per_day,
            max_trades_per_day,
            num_traded_symbols,
            -- Additional metadata
            plan_id,
            status,
            phase
        FROM raw_metrics_daily
        WHERE account_id = ANY(%s) AND date = ANY(%s)
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))
        
        # Convert to lookup dictionary
        metrics_lookup = {}
        for row in results:
            key = (row["account_id"], row["date"])
            metrics_lookup[key] = {k: v for k, v in row.items() if k not in ["account_id", "date"]}
        
        logger.debug(f"Bulk fetched {len(metrics_lookup)} enhanced metric records")
        return metrics_lookup

    def _bulk_fetch_alltime_metrics(
        self, account_ids: List[str]
    ) -> Dict[str, Dict]:
        """Bulk fetch all-time metrics for baseline risk profiling."""
        self.query_stats["bulk_queries"] += 1
        
        query = """
        WITH latest_metrics AS (
            SELECT DISTINCT ON (account_id)
                account_id,
                -- Lifetime performance
                net_profit as lifetime_net_profit,
                num_trades as lifetime_num_trades,
                win_rate as lifetime_win_rate,
                profit_factor as lifetime_profit_factor,
                sharpe_ratio as lifetime_sharpe,
                sortino_ratio as lifetime_sortino,
                -- Risk metrics
                gain_to_pain as lifetime_gain_to_pain,
                risk_adj_profit as lifetime_risk_adj_profit,
                daily_sharpe as lifetime_daily_sharpe,
                daily_sortino as lifetime_daily_sortino,
                -- Behavioral metrics
                mean_duration as lifetime_mean_duration,
                mean_tp_vs_sl as lifetime_mean_tp_vs_sl,
                -- Consistency metrics
                mean_trades_per_day as lifetime_mean_trades_per_day,
                num_traded_symbols as lifetime_num_traded_symbols,
                -- Experience metrics
                days_since_first_trade,
                num_trades,
                -- Status
                plan_id,
                trader_id,
                status,
                phase
            FROM raw_metrics_alltime
            WHERE account_id = ANY(%s)
            ORDER BY account_id, ingestion_timestamp DESC
        )
        SELECT * FROM latest_metrics
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_ids,))
        
        # Convert to lookup dictionary
        alltime_lookup = {}
        for row in results:
            account_id = row["account_id"]
            alltime_lookup[account_id] = {k: v for k, v in row.items() if k != "account_id"}
        
        logger.debug(f"Bulk fetched all-time metrics for {len(alltime_lookup)} accounts")
        return alltime_lookup

    def _calculate_risk_adjusted_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict],
        alltime_metrics: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Calculate advanced risk-adjusted features."""
        features = {}
        
        # Get daily metrics for feature date
        daily_key = (account_id, feature_date)
        if daily_key in enhanced_metrics:
            daily_data = enhanced_metrics[daily_key]
            
            # Core risk metrics
            features["daily_gain_to_pain"] = daily_data.get("gain_to_pain", 0.0)
            features["daily_risk_adj_profit"] = daily_data.get("risk_adj_profit", 0.0)
            features["daily_sharpe"] = daily_data.get("daily_sharpe", 0.0)
            features["daily_sortino"] = daily_data.get("daily_sortino", 0.0)
            
            # Distribution features
            features["profit_distribution_skew"] = self._calculate_skewness(daily_data)
            features["profit_distribution_kurtosis"] = self._calculate_kurtosis(daily_data)
            features["profit_tail_ratio"] = self._calculate_tail_ratio(daily_data)
            
            # Drawdown severity
            if daily_data.get("mean_drawdown") and daily_data.get("max_drawdown"):
                features["drawdown_severity_ratio"] = abs(
                    daily_data["mean_drawdown"] / daily_data["max_drawdown"]
                ) if daily_data["max_drawdown"] != 0 else 0
            
            # Trading efficiency
            if daily_data.get("total_volume", 0) > 0:
                features["profit_per_volume"] = (
                    daily_data.get("net_profit", 0) / daily_data["total_volume"]
                ) * 10000  # Normalize
            
            if daily_data.get("mean_duration", 0) > 0:
                features["profit_per_hour"] = (
                    daily_data.get("net_profit", 0) / daily_data["mean_duration"]
                )
        
        # Compare to lifetime metrics
        if account_id in alltime_metrics:
            lifetime = alltime_metrics[account_id]
            
            # Performance relative to lifetime
            if lifetime.get("lifetime_daily_sharpe"):
                features["sharpe_vs_lifetime"] = (
                    features.get("daily_sharpe", 0) - lifetime["lifetime_daily_sharpe"]
                )
            
            if lifetime.get("lifetime_win_rate"):
                current_win_rate = daily_data.get("win_rate", 0) if daily_key in enhanced_metrics else 0
                features["win_rate_vs_lifetime"] = current_win_rate - lifetime["lifetime_win_rate"]
            
            # Experience-weighted features
            days_trading = lifetime.get("days_since_first_trade", 1)
            features["experience_factor"] = min(days_trading / 90, 1.0)  # Cap at 90 days
            features["trades_per_day_experience_adj"] = (
                daily_data.get("mean_trades_per_day", 0) * features["experience_factor"]
                if daily_key in enhanced_metrics else 0
            )
        
        return features

    def _calculate_behavioral_consistency_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict],
        window: int = 7
    ) -> Dict[str, Any]:
        """Calculate behavioral consistency features over time."""
        features = {}
        
        # Collect metrics over window
        window_data = []
        for i in range(window):
            check_date = feature_date - timedelta(days=i)
            key = (account_id, check_date)
            if key in enhanced_metrics:
                window_data.append(enhanced_metrics[key])
        
        if len(window_data) >= 3:  # Need minimum data
            # Trading frequency consistency
            trades_per_day = [d.get("num_trades", 0) for d in window_data]
            features[f"trading_frequency_cv_{window}d"] = (
                np.std(trades_per_day) / np.mean(trades_per_day)
                if np.mean(trades_per_day) > 0 else 0
            )
            
            # Lot size consistency
            avg_lots = [d.get("total_lots", 0) / max(d.get("num_trades", 1), 1) for d in window_data]
            features[f"lot_size_consistency_{window}d"] = (
                1 - (np.std(avg_lots) / np.mean(avg_lots))
                if np.mean(avg_lots) > 0 else 0
            )
            
            # Win rate stability
            win_rates = [d.get("win_rate", 0) for d in window_data]
            features[f"win_rate_stability_{window}d"] = (
                1 - (np.std(win_rates) / 100)  # Normalized
            )
            
            # Risk management consistency
            sl_usage = []
            tp_usage = []
            for d in window_data:
                if d.get("mean_sl", 0) > 0:
                    sl_usage.append(1)
                else:
                    sl_usage.append(0)
                if d.get("mean_tp", 0) > 0:
                    tp_usage.append(1)
                else:
                    tp_usage.append(0)
            
            features[f"sl_usage_consistency_{window}d"] = np.mean(sl_usage)
            features[f"tp_usage_consistency_{window}d"] = np.mean(tp_usage)
            
            # Consecutive pattern features
            max_consec_wins = [d.get("max_num_consec_wins", 0) for d in window_data]
            max_consec_losses = [d.get("max_num_consec_losses", 0) for d in window_data]
            features[f"avg_max_consec_wins_{window}d"] = np.mean(max_consec_wins)
            features[f"avg_max_consec_losses_{window}d"] = np.mean(max_consec_losses)
        else:
            # Default values when insufficient data
            features[f"trading_frequency_cv_{window}d"] = 0.0
            features[f"lot_size_consistency_{window}d"] = 0.0
            features[f"win_rate_stability_{window}d"] = 0.0
            features[f"sl_usage_consistency_{window}d"] = 0.0
            features[f"tp_usage_consistency_{window}d"] = 0.0
            features[f"avg_max_consec_wins_{window}d"] = 0.0
            features[f"avg_max_consec_losses_{window}d"] = 0.0
        
        return features

    def _calculate_enhanced_rolling_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict]
    ) -> Dict[str, Any]:
        """Calculate enhanced rolling window features."""
        features = {}
        
        for window in self.rolling_windows:
            # Collect data for window
            window_data = []
            for i in range(window):
                check_date = feature_date - timedelta(days=i)
                key = (account_id, check_date)
                if key in enhanced_metrics:
                    window_data.append(enhanced_metrics[key])
            
            if len(window_data) >= min(3, window):  # Adaptive minimum
                # Risk-adjusted returns
                sharpe_values = [d.get("daily_sharpe", 0) for d in window_data]
                features[f"avg_sharpe_{window}d"] = np.mean(sharpe_values)
                features[f"sharpe_volatility_{window}d"] = np.std(sharpe_values)
                
                # Gain-to-pain ratio
                gtp_values = [d.get("gain_to_pain", 0) for d in window_data]
                features[f"avg_gain_to_pain_{window}d"] = np.mean(gtp_values)
                
                # Risk-adjusted profit
                risk_adj_values = [d.get("risk_adj_profit", 0) for d in window_data]
                features[f"sum_risk_adj_profit_{window}d"] = np.sum(risk_adj_values)
                
                # Drawdown analysis
                dd_values = [abs(d.get("mean_drawdown", 0)) for d in window_data]
                features[f"avg_drawdown_{window}d"] = np.mean(dd_values)
                features[f"max_drawdown_{window}d"] = np.max(dd_values) if dd_values else 0
                
                # Trading intensity
                trades = [d.get("num_trades", 0) for d in window_data]
                features[f"num_trades_{window}d"] = np.sum(trades)
                features[f"trading_days_{window}d"] = len([t for t in trades if t > 0])
                
                # Efficiency metrics
                if window >= 7:
                    volumes = [d.get("total_volume", 0) for d in window_data]
                    profits = [d.get("net_profit", 0) for d in window_data]
                    total_volume = np.sum(volumes)
                    total_profit = np.sum(profits)
                    
                    if total_volume > 0:
                        features[f"volume_weighted_return_{window}d"] = (
                            total_profit / total_volume
                        ) * 10000
                    
                    # Time-weighted returns
                    durations = [d.get("mean_duration", 1) for d in window_data]
                    time_weighted_profits = [
                        p / d if d > 0 else 0 
                        for p, d in zip(profits, durations)
                    ]
                    features[f"time_weighted_return_{window}d"] = np.mean(time_weighted_profits)
            else:
                # Default values
                features[f"avg_sharpe_{window}d"] = 0.0
                features[f"sharpe_volatility_{window}d"] = 0.0
                features[f"avg_gain_to_pain_{window}d"] = 0.0
                features[f"sum_risk_adj_profit_{window}d"] = 0.0
                features[f"avg_drawdown_{window}d"] = 0.0
                features[f"max_drawdown_{window}d"] = 0.0
                features[f"num_trades_{window}d"] = 0
                features[f"trading_days_{window}d"] = 0
                
                if window >= 7:
                    features[f"volume_weighted_return_{window}d"] = 0.0
                    features[f"time_weighted_return_{window}d"] = 0.0
        
        return features

    def _calculate_market_regime_interaction_features(
        self,
        account_id: str,
        feature_date: date,
        enhanced_metrics: Dict[Tuple[str, date], Dict],
        market_data: Dict[date, Dict]
    ) -> Dict[str, Any]:
        """Calculate features that capture trader performance under different market regimes."""
        features = {}
        
        # Get current market regime
        current_market = market_data.get(feature_date, {})
        volatility_regime = current_market.get("market_volatility_regime", "normal")
        
        # Performance in different volatility regimes
        high_vol_days = []
        normal_vol_days = []
        low_vol_days = []
        
        for i in range(30):  # Look back 30 days
            check_date = feature_date - timedelta(days=i)
            market = market_data.get(check_date, {})
            metrics_key = (account_id, check_date)
            
            if metrics_key in enhanced_metrics:
                daily_profit = enhanced_metrics[metrics_key].get("net_profit", 0)
                vol_regime = market.get("market_volatility_regime", "normal")
                
                if "high" in vol_regime.lower():
                    high_vol_days.append(daily_profit)
                elif "low" in vol_regime.lower():
                    low_vol_days.append(daily_profit)
                else:
                    normal_vol_days.append(daily_profit)
        
        # Calculate regime-specific performance
        if high_vol_days:
            features["avg_profit_high_vol"] = np.mean(high_vol_days)
            features["win_rate_high_vol"] = len([p for p in high_vol_days if p > 0]) / len(high_vol_days) * 100
        else:
            features["avg_profit_high_vol"] = 0.0
            features["win_rate_high_vol"] = 0.0
        
        if normal_vol_days:
            features["avg_profit_normal_vol"] = np.mean(normal_vol_days)
            features["win_rate_normal_vol"] = len([p for p in normal_vol_days if p > 0]) / len(normal_vol_days) * 100
        else:
            features["avg_profit_normal_vol"] = 0.0
            features["win_rate_normal_vol"] = 0.0
        
        if low_vol_days:
            features["avg_profit_low_vol"] = np.mean(low_vol_days)
            features["win_rate_low_vol"] = len([p for p in low_vol_days if p > 0]) / len(low_vol_days) * 100
        else:
            features["avg_profit_low_vol"] = 0.0
            features["win_rate_low_vol"] = 0.0
        
        # Volatility adaptability score
        vol_performances = []
        if high_vol_days:
            vol_performances.append(np.mean(high_vol_days))
        if normal_vol_days:
            vol_performances.append(np.mean(normal_vol_days))
        if low_vol_days:
            vol_performances.append(np.mean(low_vol_days))
        
        if len(vol_performances) > 1:
            features["volatility_adaptability"] = 1 - (np.std(vol_performances) / (abs(np.mean(vol_performances)) + 1))
        else:
            features["volatility_adaptability"] = 0.0
        
        # Current regime indicator
        features["is_high_vol_regime"] = 1 if "high" in volatility_regime.lower() else 0
        features["is_low_vol_regime"] = 1 if "low" in volatility_regime.lower() else 0
        
        return features

    def _calculate_features_from_bulk_data_enhanced(
        self,
        account_id: str,
        login: str,
        feature_date: date,
        bulk_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Calculate features using enhanced bulk-fetched data."""
        try:
            # Start with base features from parent class
            features = super()._calculate_features_from_bulk_data(
                account_id, login, feature_date, bulk_data
            )
            
            if not features:
                return None
            
            # Add enhanced risk-adjusted features
            risk_features = self._calculate_risk_adjusted_features(
                account_id,
                feature_date,
                bulk_data.get("enhanced_metrics", {}),
                bulk_data.get("alltime_metrics", {})
            )
            features.update(risk_features)
            
            # Add behavioral consistency features
            consistency_features = self._calculate_behavioral_consistency_features(
                account_id,
                feature_date,
                bulk_data.get("enhanced_metrics", {}),
                window=7
            )
            features.update(consistency_features)
            
            # Add enhanced rolling features
            rolling_features = self._calculate_enhanced_rolling_features(
                account_id,
                feature_date,
                bulk_data.get("enhanced_metrics", {})
            )
            features.update(rolling_features)
            
            # Add market regime interaction features
            if "market_data" in bulk_data:
                regime_features = self._calculate_market_regime_interaction_features(
                    account_id,
                    feature_date,
                    bulk_data.get("enhanced_metrics", {}),
                    bulk_data["market_data"]
                )
                features.update(regime_features)
            
            # Add feature version
            features["feature_version"] = FEATURE_VERSION
            
            return features
            
        except Exception as e:
            logger.error(
                f"Error calculating enhanced features for {account_id} on {feature_date}: {str(e)}"
            )
            return None

    def _bulk_fetch_all_data_enhanced(
        self,
        account_ids: List[str],
        dates: List[date],
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Fetch all data including enhanced metrics."""
        # Get base data from parent class
        bulk_data = super()._bulk_fetch_all_data_monitored(
            account_ids, dates, start_date, end_date
        )
        
        # Add enhanced metrics
        with self.query_monitor.track_query(
            "bulk_fetch_enhanced_metrics", "Fetching enhanced risk metrics"
        ):
            # Get more historical data for risk calculations
            historical_start = start_date - timedelta(days=90)
            historical_dates = []
            current = historical_start
            while current <= end_date:
                historical_dates.append(current)
                current += timedelta(days=1)
            
            bulk_data["enhanced_metrics"] = self._bulk_fetch_enhanced_metrics(
                account_ids, historical_dates
            )
        
        # Add all-time metrics for baseline comparison
        with self.query_monitor.track_query(
            "bulk_fetch_alltime", "Fetching all-time metrics"
        ):
            bulk_data["alltime_metrics"] = self._bulk_fetch_alltime_metrics(account_ids)
        
        return bulk_data

    def _calculate_skewness(self, daily_data: Dict) -> float:
        """Calculate skewness from profit distribution percentiles."""
        try:
            p10 = daily_data.get("profit_perc_10", 0)
            p25 = daily_data.get("profit_perc_25", 0)
            p50 = daily_data.get("median_profit", 0)
            p75 = daily_data.get("profit_perc_75", 0)
            p90 = daily_data.get("profit_perc_90", 0)
            
            # Simplified skewness calculation using percentiles
            # Positive skew = right tail is longer
            upper_tail = p90 - p50
            lower_tail = p50 - p10
            
            if upper_tail + lower_tail > 0:
                return (upper_tail - lower_tail) / (upper_tail + lower_tail)
            return 0.0
        except:
            return 0.0

    def _calculate_kurtosis(self, daily_data: Dict) -> float:
        """Calculate kurtosis from profit distribution percentiles."""
        try:
            p10 = daily_data.get("profit_perc_10", 0)
            p25 = daily_data.get("profit_perc_25", 0)
            p75 = daily_data.get("profit_perc_75", 0)
            p90 = daily_data.get("profit_perc_90", 0)
            
            # Simplified kurtosis using interquartile range
            iqr = p75 - p25
            full_range = p90 - p10
            
            if iqr > 0:
                return full_range / iqr - 2.91  # Normalize to normal distribution
            return 0.0
        except:
            return 0.0

    def _calculate_tail_ratio(self, daily_data: Dict) -> float:
        """Calculate tail ratio from profit distribution."""
        try:
            p90 = abs(daily_data.get("profit_perc_90", 0))
            p10 = abs(daily_data.get("profit_perc_10", 0))
            
            if p10 > 0:
                return p90 / p10
            return 0.0
        except:
            return 0.0

    def engineer_features_enhanced(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        force_rebuild: bool = False,
        validate_bias: bool = True,
        enable_monitoring: bool = True,
    ) -> Dict[str, Any]:
        """
        Engineer features with enhanced risk metrics.
        """
        # Override the parent's method to use enhanced calculations
        start_time = datetime.now()
        
        # Reset metrics for this run
        self.bias_validator.reset_violations()
        self.performance_metrics = {k: 0 for k in self.performance_metrics}
        
        logger.info(
            f"[ENHANCED V2] Starting feature engineering from {start_date} to {end_date}"
        )
        logger.info(
            f"Options: validation={validate_bias}, monitoring={enable_monitoring}, rebuild={force_rebuild}"
        )
        
        try:
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)
            if not start_date:
                start_date = end_date - timedelta(days=7)
            
            # Get work items
            work_items = self._get_work_items(start_date, end_date, force_rebuild)
            
            if not work_items:
                logger.info("No work items to process")
                return self._create_comprehensive_summary(
                    start_time, 0, validate_bias, enable_monitoring
                )
            
            logger.info(f"Processing {len(work_items)} account-date combinations")
            
            # Process batches
            total_records = self._process_batches_enhanced(
                work_items, start_date, end_date, validate_bias
            )
            
            # Run quality monitoring if enabled
            quality_results = {}
            if enable_monitoring and total_records > 0:
                quality_results = self._run_comprehensive_monitoring(
                    start_date, end_date
                )
            
            # Create result summary
            result = self._create_comprehensive_summary(
                start_time,
                total_records,
                validate_bias,
                enable_monitoring,
                quality_results,
            )
            
            # Log performance metrics
            self.query_monitor.log_summary()
            self.query_monitor.save_performance_log()
            
            # Log completion
            self._log_completion_status_enhanced(result)
            
            return result
            
        except Exception as e:
            self.performance_metrics["errors_encountered"] += 1
            logger.error(f"Enhanced feature engineering failed: {str(e)}")
            
            # Save any performance data collected
            self.query_monitor.save_performance_log()
            
            raise

    def _process_batches_enhanced(
        self,
        work_items: List[Tuple[str, str, date]],
        start_date: date,
        end_date: date,
        validate_bias: bool,
    ) -> int:
        """Process batches with enhanced features."""
        total_records = 0
        batch_size = self.config["batch_size"]
        
        for i in range(0, len(work_items), batch_size):
            batch = work_items[i : i + batch_size]
            
            # Extract unique accounts and dates
            account_ids = list(set(item[0] for item in batch))
            dates = list(set(item[2] for item in batch))
            
            # Bulk fetch all data including enhanced metrics
            bulk_data = self._bulk_fetch_all_data_enhanced(
                account_ids, dates, start_date, end_date
            )
            
            # Process each work item
            features_batch = []
            for account_id, login, feature_date in batch:
                try:
                    features = self._calculate_features_from_bulk_data_enhanced(
                        account_id, login, feature_date, bulk_data
                    )
                    if features and (not validate_bias or self._validate_features(features, feature_date)):
                        features_batch.append(features)
                except Exception as e:
                    logger.error(
                        f"Error processing {account_id} on {feature_date}: {str(e)}"
                    )
                    self.performance_metrics["errors_encountered"] += 1
            
            # Bulk save features
            if features_batch:
                saved = self._bulk_save_features(features_batch)
                total_records += saved
            
            # Progress logging
            progress = min(100, ((i + len(batch)) / len(work_items)) * 100)
            if (i + len(batch)) % 100 == 0 or progress >= 100:
                logger.info(
                    f"Progress: {progress:.1f}% ({i + len(batch)}/{len(work_items)})"
                )
        
        self.performance_metrics["total_records_processed"] = total_records
        return total_records

    def _validate_features(self, features: Dict[str, Any], feature_date: date) -> bool:
        """Validate features for lookahead bias and data quality."""
        # Basic validation from parent
        if not self.bias_validator.validate_data_availability(
            feature_date, feature_date, "enhanced_features"
        ):
            self.performance_metrics["validation_violations"] += 1
            return False
        
        # Additional validation for risk metrics
        risk_metrics = [
            "daily_sharpe", "daily_sortino", "daily_gain_to_pain",
            "profit_distribution_skew", "volatility_adaptability"
        ]
        
        for metric in risk_metrics:
            if metric in features:
                value = features[metric]
                # Check for unrealistic values
                if isinstance(value, (int, float)):
                    if abs(value) > 1000:  # Sanity check
                        logger.warning(
                            f"Unrealistic value for {metric}: {value} on {feature_date}"
                        )
                        features[metric] = 0.0  # Reset to default
        
        return True

    def _log_completion_status_enhanced(self, result: Dict[str, Any]):
        """Log enhanced completion status with risk metrics summary."""
        # Call parent's logging
        super()._log_completion_status(result)
        
        # Add enhanced metrics summary
        logger.info("\n" + "="*80)
        logger.info("ENHANCED RISK METRICS SUMMARY")
        logger.info("="*80)
        
        logger.info(f"Feature Version: {FEATURE_VERSION}")
        logger.info("\nNew Risk Features Added:")
        logger.info("  - Risk-adjusted performance metrics (Sharpe, Sortino, Gain-to-Pain)")
        logger.info("  - Profit distribution analysis (skewness, kurtosis, tail ratios)")
        logger.info("  - Behavioral consistency tracking")
        logger.info("  - Market regime adaptability scoring")
        logger.info("  - Time and volume weighted returns")
        logger.info("  - Extended rolling windows (up to 30 days)")
        
        if result.get("quality_monitoring", {}).get("distributions"):
            logger.info("\nKey Risk Metrics Distribution:")
            distributions = result["quality_monitoring"]["distributions"]
            
            for metric in ["daily_sharpe", "daily_sortino", "volatility_adaptability"]:
                if metric in distributions:
                    dist = distributions[metric]
                    logger.info(
                        f"  - {metric}: mean={dist['mean']:.3f}, "
                        f"std={dist['std']:.3f}, nulls={dist['null_pct']:.1f}%"
                    )
        
        logger.info("="*80)


def engineer_features_enhanced_v2(**kwargs):
    """
    Main entry point for enhanced feature engineering with comprehensive risk metrics.
    """
    engineer = EnhancedFeatureEngineerV2()
    return engineer.engineer_features_enhanced(**kwargs)


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(
        description="Enhanced feature engineering with comprehensive risk metrics"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for feature engineering (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for feature engineering (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild of existing features",
    )
    parser.add_argument(
        "--no-validation", action="store_true", help="Disable lookahead bias validation"
    )
    parser.add_argument(
        "--no-monitoring", action="store_true", help="Disable quality monitoring"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file="engineer_features_enhanced_v2")
    
    # Run feature engineering
    try:
        result = engineer_features_enhanced_v2(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild,
            validate_bias=not args.no_validation,
            enable_monitoring=not args.no_monitoring,
        )
        
        logger.info(
            f"Enhanced feature engineering complete: {result['total_records']} records processed"
        )
        
    except Exception as e:
        logger.error(f"Enhanced feature engineering failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()