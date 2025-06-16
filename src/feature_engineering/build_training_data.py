"""
Build the model training input table by combining features with target variables.
Features from day D are aligned with target PnL from day D+1.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List, Tuple
import argparse
import pandas as pd
import numpy as np
import gc
import warnings
warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class TrainingDataBuilder:
    """Builds the model training input table with enhanced feature engineering."""

    def __init__(self, chunk_size: int = 10000):
        """Initialize the training data builder.
        
        Args:
            chunk_size: Number of records to process at once for memory efficiency
        """
        self.db_manager = get_db_manager()
        self.training_table = "model_training_input"
        self.chunk_size = chunk_size
        
        # Define feature groups for easier management
        self.account_feature_groups = {
            'static': ['starting_balance', 'profit_target_pct', 'max_daily_drawdown_pct', 
                      'max_drawdown_pct', 'max_leverage', 'is_drawdown_relative'],
            'dynamic': ['balance', 'equity', 'days_active', 'distance_to_profit_target',
                       'distance_to_max_drawdown'],
            'performance': ['daily_sharpe', 'daily_sortino', 'profit_factor', 'success_rate',
                          'consistency_score', 'leverage_usage_ratio'],
            'rolling': ['sharpe_ratio_5d', 'sharpe_ratio_10d', 'sharpe_ratio_20d',
                       'profit_volatility_5d', 'profit_volatility_10d', 'profit_volatility_20d',
                       'win_rate_5d', 'win_rate_10d', 'win_rate_20d'],
            'behavioral': ['trades_last_7d', 'volume_usd_last_7d', 'top_symbol_concentration',
                          'symbol_diversification_index', 'trades_morning_ratio']
        }
        
        self.regime_feature_groups = {
            'sentiment': ['sentiment_avg', 'sentiment_bullish_count', 'sentiment_bearish_count',
                         'sentiment_very_bullish'],
            'macro': ['fed_funds_rate', 'cpi_us', 'treasury_2y', 'treasury_10y', 
                     'yield_curve_spread', 'dollar_index', 'vix_close'],
            'market': ['sp500_daily_return', 'nasdaq_daily_return', 'btc_daily_return'],
            'risk': ['prob_risk_on', 'prob_risk_off', 'prob_vol_spike', 'max_risk_probability']
        }

    def build_training_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        force_rebuild: bool = False,
        target_days_ahead: int = 1,
    ) -> int:
        """
        Build training data by aligning features with target variables.

        Args:
            start_date: Start date for training data
            end_date: End date for training data
            force_rebuild: If True, rebuild even if data exists
            target_days_ahead: Number of days ahead to predict (default 1)

        Returns:
            Number of training records created
        """
        start_time = datetime.now()
        total_records = 0

        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage="build_training_data",
                execution_date=datetime.now().date(),
                status="running",
                execution_time_seconds=0,
                records_processed=0,
                error_message=None,
                records_failed=0,
            )

            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(
                    days=2
                )  # Need D+1 for target
            if not start_date:
                start_date = end_date - timedelta(days=90)  # Default to 90 days

            logger.info(f"Building training data from {start_date} to {end_date}")

            # Clear existing data if force rebuild
            if force_rebuild:
                logger.warning(
                    "Force rebuild requested. Truncating existing training data."
                )
                self.db_manager.model_db.execute_command(
                    f"TRUNCATE TABLE {self.training_table}"
                )

            # Build training data with enhanced features
            total_records = self._build_training_records_enhanced(
                start_date, end_date, target_days_ahead
            )

            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage="build_training_data",
                execution_date=datetime.now().date(),
                status="success",
                execution_time_seconds=(datetime.now() - start_time).total_seconds(),
                records_processed=total_records,
                error_message=None,
                records_failed=0,
            )

            logger.info(f"Successfully created {total_records} training records")
            return total_records

        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage="build_training_data",
                execution_date=datetime.now().date(),
                status="failed",
                execution_time_seconds=(datetime.now() - start_time).total_seconds(),
                records_processed=0,
                error_message=str(e),
                records_failed=total_records,
            )
            logger.error(f"Failed to build training data: {str(e)}")
            raise

    def _build_training_records_enhanced(
        self, 
        start_date: date, 
        end_date: date,
        target_days_ahead: int = 1
    ) -> int:
        """
        Build training records with enhanced feature engineering.
        Processes data in chunks for memory efficiency.
        """
        total_records = 0
        current_date = start_date
        
        # Process data in daily chunks for memory efficiency
        while current_date <= end_date:
            chunk_end = min(current_date + timedelta(days=7), end_date)
            
            logger.info(f"Processing chunk: {current_date} to {chunk_end}")
            
            # Load features for date range
            df = self._load_features_for_date_range(
                current_date, chunk_end, target_days_ahead
            )
            
            if df is not None and len(df) > 0:
                # Engineer interaction features
                df = self._engineer_interaction_features(df)
                
                # Clean feature names for LightGBM
                df = self._clean_feature_names_for_lightgbm(df)
                
                # Save to database in batches
                records_saved = self._save_training_data_batch(df)
                total_records += records_saved
                
                logger.info(f"Saved {records_saved} records for chunk")
            
            # Clean up memory
            del df
            gc.collect()
            
            current_date = chunk_end + timedelta(days=1)
        
        return total_records
    
    def _load_features_for_date_range(
        self,
        start_date: date,
        end_date: date,
        target_days_ahead: int
    ) -> Optional[pd.DataFrame]:
        """
        Load and join account features with regime features.
        
        TEMPORAL ASSUMPTIONS:
        - Features use data only up to and including snapshot_date
        - Target uses data from snapshot_date + target_days_ahead
        - No future data leakage in feature calculations
        - All joins respect temporal boundaries
        """
        query = """
        -- TEMPORAL VALIDATION: Features from snapshot_date, target from snapshot_date + N days
        -- All feature data must be <= snapshot_date to prevent forward-looking bias
        WITH feature_data AS (
            SELECT 
                -- Account identifiers
                s.account_id,
                s.login,
                s.snapshot_date,
                s.snapshot_date + INTERVAL '%s days' as prediction_date,
                
                -- Account static features
                s.starting_balance,
                s.profit_target_pct,
                s.max_daily_drawdown_pct,
                s.max_drawdown_pct,
                s.max_leverage,
                s.is_drawdown_relative,
                
                -- Account dynamic features
                s.balance,
                s.equity,
                s.days_active,
                s.distance_to_profit_target,
                s.distance_to_max_drawdown,
                s.days_since_last_trade,
                
                -- Account performance metrics
                COALESCE(s.daily_sharpe, 0) as daily_sharpe,
                COALESCE(s.daily_sortino, 0) as daily_sortino,
                COALESCE(s.profit_factor, 0) as profit_factor,
                COALESCE(s.success_rate, 0) as success_rate,
                COALESCE(s.consistency_score, 0) as consistency_score,
                COALESCE(s.leverage_usage_ratio, 0) as leverage_usage_ratio,
                COALESCE(s.daily_loss_limit_usage, 0) as daily_loss_limit_usage,
                COALESCE(s.total_loss_limit_usage, 0) as total_loss_limit_usage,
                
                -- Account rolling metrics
                COALESCE(s.sharpe_ratio_5d, 0) as sharpe_ratio_5d,
                COALESCE(s.sharpe_ratio_10d, 0) as sharpe_ratio_10d,
                COALESCE(s.sharpe_ratio_20d, 0) as sharpe_ratio_20d,
                COALESCE(s.profit_volatility_5d, 0) as profit_volatility_5d,
                COALESCE(s.profit_volatility_10d, 0) as profit_volatility_10d,
                COALESCE(s.profit_volatility_20d, 0) as profit_volatility_20d,
                COALESCE(s.win_rate_5d, 0) as win_rate_5d,
                COALESCE(s.win_rate_10d, 0) as win_rate_10d,
                COALESCE(s.win_rate_20d, 0) as win_rate_20d,
                
                -- Account behavioral features
                COALESCE(s.trades_last_7d, 0) as trades_last_7d,
                COALESCE(s.volume_usd_last_7d, 0) as volume_usd_last_7d,
                COALESCE(s.profit_last_7d, 0) as profit_last_7d,
                COALESCE(s.unique_symbols_last_7d, 0) as unique_symbols_last_7d,
                COALESCE(s.top_symbol_concentration, 0) as top_symbol_concentration,
                COALESCE(s.symbol_diversification_index, 0) as symbol_diversification_index,
                COALESCE(s.trades_morning_ratio, 0) as trades_morning_ratio,
                COALESCE(s.trades_afternoon_ratio, 0) as trades_afternoon_ratio,
                COALESCE(s.trades_evening_ratio, 0) as trades_evening_ratio,
                
                -- Regime features (market-wide)
                COALESCE(r.sentiment_avg, 0) as sentiment_avg,
                COALESCE(r.sentiment_bullish_count, 0) as sentiment_bullish_count,
                COALESCE(r.sentiment_bearish_count, 0) as sentiment_bearish_count,
                COALESCE(r.sentiment_very_bullish, 0) as sentiment_very_bullish,
                COALESCE(r.fed_funds_rate, 0) as fed_funds_rate,
                COALESCE(r.cpi_us, 0) as cpi_us,
                COALESCE(r.treasury_2y, 0) as treasury_2y,
                COALESCE(r.treasury_10y, 0) as treasury_10y,
                COALESCE(r.yield_curve_spread, 0) as yield_curve_spread,
                COALESCE(r.dollar_index, 0) as dollar_index,
                COALESCE(r.vix_close, 20) as vix_close,  -- Default VIX to 20 if missing
                COALESCE(r.unemployment_rate, 0) as unemployment_rate,
                COALESCE(r.gdp_growth_rate, 0) as gdp_growth_rate,
                COALESCE(r.consumer_confidence, 0) as consumer_confidence,
                COALESCE(r.sp500_close, 0) as sp500_close,
                COALESCE(r.sp500_daily_return, 0) as sp500_daily_return,
                COALESCE(r.sp500_vol_20d, 0) as sp500_vol_20d,
                COALESCE(r.nasdaq_close, 0) as nasdaq_close,
                COALESCE(r.nasdaq_daily_return, 0) as nasdaq_daily_return,
                COALESCE(r.dow_close, 0) as dow_close,
                COALESCE(r.dow_daily_return, 0) as dow_daily_return,
                COALESCE(r.russell_daily_return, 0) as russell_daily_return,
                COALESCE(r.eurusd_close, 0) as eurusd_close,
                COALESCE(r.eurusd_change, 0) as eurusd_change,
                COALESCE(r.gbpusd_close, 0) as gbpusd_close,
                COALESCE(r.gbpusd_change, 0) as gbpusd_change,
                COALESCE(r.usdjpy_close, 0) as usdjpy_close,
                COALESCE(r.usdjpy_change, 0) as usdjpy_change,
                COALESCE(r.btc_close, 0) as btc_close,
                COALESCE(r.btc_daily_return, 0) as btc_daily_return,
                COALESCE(r.eth_close, 0) as eth_close,
                COALESCE(r.eth_daily_return, 0) as eth_daily_return,
                COALESCE(r.gold_close, 0) as gold_close,
                COALESCE(r.gold_change, 0) as gold_change,
                COALESCE(r.oil_close, 0) as oil_close,
                COALESCE(r.oil_change, 0) as oil_change,
                r.volatility_regime,
                r.liquidity_state,
                r.sentiment_level,
                r.yield_curve_shape,
                COALESCE(r.has_anomalies, 0) as has_anomalies,
                r.regime_fingerprint,
                COALESCE(r.prob_risk_on, 0.5) as prob_risk_on,
                COALESCE(r.prob_risk_off, 0.5) as prob_risk_off,
                COALESCE(r.prob_vol_spike, 0) as prob_vol_spike,
                COALESCE(r.max_risk_probability, 0.5) as max_risk_probability,
                
                -- Target data from future snapshot
                future.balance as future_balance,
                future.equity as future_equity,
                future.status as future_status
                
            FROM prop_trading_model.stg_accounts_daily_snapshots s
            LEFT JOIN prop_trading_model.mv_regime_daily_features r 
                ON s.snapshot_date = r.date
            LEFT JOIN prop_trading_model.stg_accounts_daily_snapshots future
                ON s.account_id = future.account_id
                AND future.snapshot_date = s.snapshot_date + INTERVAL '%s days'
            WHERE 
                s.snapshot_date >= %s
                AND s.snapshot_date <= %s
                AND s.status = 1  -- Active accounts only
                AND s.balance > 0  -- Valid balance
                AND future.account_id IS NOT NULL  -- Has future data
        )
        SELECT 
            *,
            -- Calculate binary target (0.1% threshold)
            CASE 
                WHEN future_balance > balance * 1.001 THEN 1 
                ELSE 0 
            END as will_profit
        FROM feature_data
        """
        
        try:
            # Execute query with parameters
            df = pd.read_sql(
                query,
                self.db_manager.model_db.connection,
                params=(target_days_ahead, target_days_ahead, start_date, end_date)
            )
            
            # Convert date columns
            df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
            df['prediction_date'] = pd.to_datetime(df['prediction_date'])
            
            # Add time-based features
            df = self._add_time_features(df)
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading features: {str(e)}")
            return None
    
    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add time-based features from snapshot date.
        """
        df['day_of_week'] = df['snapshot_date'].dt.dayofweek
        df['week_of_month'] = df['snapshot_date'].dt.day // 7 + 1
        df['month'] = df['snapshot_date'].dt.month
        df['quarter'] = df['snapshot_date'].dt.quarter
        df['day_of_year'] = df['snapshot_date'].dt.dayofyear
        df['is_month_start'] = df['snapshot_date'].dt.is_month_start.astype(int)
        df['is_month_end'] = df['snapshot_date'].dt.is_month_end.astype(int)
        df['is_quarter_start'] = df['snapshot_date'].dt.is_quarter_start.astype(int)
        df['is_quarter_end'] = df['snapshot_date'].dt.is_quarter_end.astype(int)
        
        return df
    
    def _engineer_interaction_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create interaction features between account and market conditions.
        """
        # Risk-adjusted performance
        df['risk_adjusted_sharpe'] = df['daily_sharpe'] * (1 - df['max_risk_probability'])
        
        # Volatility alignment (account volatility vs market VIX)
        df['volatility_alignment'] = np.where(
            df['vix_close'] > 0,
            df['profit_volatility_10d'] / (df['vix_close'] / 100),
            0
        )
        
        # Sentiment trading alignment
        df['sentiment_trading_alignment'] = df['success_rate'] * df['sentiment_avg']
        
        # Market stress indicator (composite)
        df['market_stress'] = (
            (df['vix_close'] > 20).astype(int) + 
            (df['yield_curve_spread'] < 0).astype(int) +
            (df['prob_vol_spike'] > 0.5).astype(int)
        ) / 3.0
        
        # Account resilience score
        df['resilience_score'] = (
            df['consistency_score'] * 0.4 +
            (100 - df['total_loss_limit_usage']) * 0.3 +
            df['symbol_diversification_index'] * 100 * 0.3
        )
        
        # Additional interaction features
        # Performance under market stress
        df['stress_performance'] = df['daily_sharpe'] * (1 - df['market_stress'])
        
        # Leverage efficiency (how well leverage is used given market conditions)
        df['leverage_efficiency'] = np.where(
            df['max_leverage'] > 0,
            df['leverage_usage_ratio'] * df['prob_risk_on'],
            0
        )
        
        # Trading activity alignment with market volatility
        df['activity_volatility_ratio'] = np.where(
            df['sp500_vol_20d'] > 0,
            df['trades_last_7d'] / df['sp500_vol_20d'],
            0
        )
        
        # Profit momentum in trending markets
        df['trend_profit_momentum'] = np.where(
            abs(df['sp500_daily_return']) > 0.01,  # Trending day
            df['profit_last_7d'] * np.sign(df['sp500_daily_return']),
            0
        )
        
        # Risk appetite score
        df['risk_appetite_score'] = (
            df['trades_last_7d'] * df['prob_risk_on'] * 
            (1 - df['daily_loss_limit_usage'] / 100)
        )
        
        return df
    
    def _clean_feature_names_for_lightgbm(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean feature names to be LightGBM compatible.
        LightGBM doesn't like special characters in feature names.
        """
        # Characters to replace
        chars_to_replace = ['[', ']', '{', '}', '(', ')', ',', ':', ';', '"', "'", ' ']
        
        # Create mapping of old to new column names
        new_columns = {}
        for col in df.columns:
            new_col = col
            for char in chars_to_replace:
                new_col = new_col.replace(char, '_')
            # Remove multiple underscores
            while '__' in new_col:
                new_col = new_col.replace('__', '_')
            # Remove trailing underscores
            new_col = new_col.strip('_')
            new_columns[col] = new_col
        
        # Rename columns
        df = df.rename(columns=new_columns)
        
        return df
    
    def _save_training_data_batch(self, df: pd.DataFrame) -> int:
        """
        Save training data batch to database.
        """
        # Select columns to save
        columns_to_save = [
            'account_id', 'login', 'snapshot_date', 'prediction_date',
            # Target
            'will_profit',
            # All feature columns (excluding temporary columns)
            *[col for col in df.columns if col not in [
                'future_balance', 'future_equity', 'future_status'
            ]]
        ]
        
        # Remove duplicates from column list
        columns_to_save = list(dict.fromkeys(columns_to_save))
        
        # Filter dataframe
        save_df = df[columns_to_save]
        
        # Save to database
        try:
            save_df.to_sql(
                self.training_table,
                self.db_manager.model_db.connection,
                schema='prop_trading_model',
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            return len(save_df)
        except Exception as e:
            logger.error(f"Error saving training data: {str(e)}")
            return 0
    
    def _build_training_records(self, start_date: date, end_date: date) -> int:
        """
        Build training records by joining features with target variables.

        The key alignment:
        - Features are from feature_date (day D)
        - Target is from prediction_date (day D+1)
        """
        # This query joins features from day D with target PnL from day D+1
        insert_query = f"""
        INSERT INTO {self.training_table} (
            account_id, login, prediction_date, feature_date,
            -- Static features
            starting_balance, max_daily_drawdown_pct, max_drawdown_pct,
            profit_target_pct, max_leverage, is_drawdown_relative,
            -- Dynamic features
            current_balance, current_equity, days_since_first_trade,
            active_trading_days_count, distance_to_profit_target,
            distance_to_max_drawdown, open_pnl, open_positions_volume,
            -- Rolling performance features
            rolling_pnl_sum_1d, rolling_pnl_avg_1d, rolling_pnl_std_1d,
            rolling_pnl_sum_3d, rolling_pnl_avg_3d, rolling_pnl_std_3d,
            rolling_pnl_min_3d, rolling_pnl_max_3d, win_rate_3d,
            rolling_pnl_sum_5d, rolling_pnl_avg_5d, rolling_pnl_std_5d,
            rolling_pnl_min_5d, rolling_pnl_max_5d, win_rate_5d,
            profit_factor_5d, sharpe_ratio_5d,
            rolling_pnl_sum_10d, rolling_pnl_avg_10d, rolling_pnl_std_10d,
            rolling_pnl_min_10d, rolling_pnl_max_10d, win_rate_10d,
            profit_factor_10d, sharpe_ratio_10d,
            rolling_pnl_sum_20d, rolling_pnl_avg_20d, rolling_pnl_std_20d,
            win_rate_20d, profit_factor_20d, sharpe_ratio_20d,
            -- Behavioral features
            trades_count_5d, avg_trade_duration_5d, avg_lots_per_trade_5d,
            avg_volume_per_trade_5d, stop_loss_usage_rate_5d,
            take_profit_usage_rate_5d, buy_sell_ratio_5d,
            top_symbol_concentration_5d,
            -- Market features
            market_sentiment_score, market_volatility_regime,
            market_liquidity_state, vix_level, dxy_level,
            sp500_daily_return, btc_volatility_90d, fed_funds_rate,
            -- Time features
            day_of_week, week_of_month, month, quarter, day_of_year,
            is_month_start, is_month_end, is_quarter_start, is_quarter_end,
            -- Target variable
            target_net_profit
        )
        SELECT 
            f.account_id,
            f.login,
            f.feature_date + INTERVAL '1 day' as prediction_date,  -- D+1
            f.feature_date,  -- D
            -- All feature columns
            f.starting_balance, f.max_daily_drawdown_pct, f.max_drawdown_pct,
            f.profit_target_pct, f.max_leverage, f.is_drawdown_relative,
            f.current_balance, f.current_equity, f.days_since_first_trade,
            f.active_trading_days_count, f.distance_to_profit_target,
            f.distance_to_max_drawdown, f.open_pnl, f.open_positions_volume,
            f.rolling_pnl_sum_1d, f.rolling_pnl_avg_1d, f.rolling_pnl_std_1d,
            f.rolling_pnl_sum_3d, f.rolling_pnl_avg_3d, f.rolling_pnl_std_3d,
            f.rolling_pnl_min_3d, f.rolling_pnl_max_3d, f.win_rate_3d,
            f.rolling_pnl_sum_5d, f.rolling_pnl_avg_5d, f.rolling_pnl_std_5d,
            f.rolling_pnl_min_5d, f.rolling_pnl_max_5d, f.win_rate_5d,
            f.profit_factor_5d, f.sharpe_ratio_5d,
            f.rolling_pnl_sum_10d, f.rolling_pnl_avg_10d, f.rolling_pnl_std_10d,
            f.rolling_pnl_min_10d, f.rolling_pnl_max_10d, f.win_rate_10d,
            f.profit_factor_10d, f.sharpe_ratio_10d,
            f.rolling_pnl_sum_20d, f.rolling_pnl_avg_20d, f.rolling_pnl_std_20d,
            f.win_rate_20d, f.profit_factor_20d, f.sharpe_ratio_20d,
            f.trades_count_5d, f.avg_trade_duration_5d, f.avg_lots_per_trade_5d,
            f.avg_volume_per_trade_5d, f.stop_loss_usage_rate_5d,
            f.take_profit_usage_rate_5d, f.buy_sell_ratio_5d,
            f.top_symbol_concentration_5d,
            f.market_sentiment_score, f.market_volatility_regime,
            f.market_liquidity_state, f.vix_level, f.dxy_level,
            f.sp500_daily_return, f.btc_volatility_90d, f.fed_funds_rate,
            f.day_of_week, f.week_of_month, f.month, f.quarter, f.day_of_year,
            f.is_month_start, f.is_month_end, f.is_quarter_start, f.is_quarter_end,
            -- Target from D+1
            COALESCE(t.net_profit, 0) as target_net_profit
        FROM feature_store_account_daily f
        LEFT JOIN raw_metrics_daily t
            ON f.account_id = t.account_id 
            AND t.date = f.feature_date + INTERVAL '1 day'
        WHERE f.feature_date >= %s 
            AND f.feature_date <= %s
            AND f.account_id IN (
                -- Only include accounts that are active on D+1
                SELECT DISTINCT account_id 
                FROM stg_accounts_daily_snapshots
                WHERE snapshot_date = f.feature_date + INTERVAL '1 day'
            )
        ON CONFLICT (account_id, prediction_date) DO NOTHING
        """

        # Execute the insert
        rows_affected = self.db_manager.model_db.execute_command(
            insert_query, (start_date, end_date)
        )

        return rows_affected

    def validate_training_data(self) -> Dict[str, Any]:
        """Validate the training data for completeness and quality."""
        validation_results = {}

        # Check record count
        count_query = f"SELECT COUNT(*) as total FROM {self.training_table}"
        result = self.db_manager.model_db.execute_query(count_query)
        validation_results["total_records"] = result[0]["total"] if result else 0

        # Check for NULL targets
        null_target_query = f"""
        SELECT COUNT(*) as null_targets 
        FROM {self.training_table}
        WHERE target_net_profit IS NULL
        """
        result = self.db_manager.model_db.execute_query(null_target_query)
        validation_results["null_targets"] = result[0]["null_targets"] if result else 0

        # Check date alignment
        alignment_query = f"""
        SELECT 
            MIN(prediction_date - feature_date) as min_diff,
            MAX(prediction_date - feature_date) as max_diff,
            AVG(prediction_date - feature_date) as avg_diff
        FROM {self.training_table}
        """
        result = self.db_manager.model_db.execute_query(alignment_query)
        if result:
            validation_results["date_alignment"] = {
                "min_diff_days": result[0]["min_diff"].days
                if result[0]["min_diff"]
                else None,
                "max_diff_days": result[0]["max_diff"].days
                if result[0]["max_diff"]
                else None,
                "avg_diff_days": float(result[0]["avg_diff"].days)
                if result[0]["avg_diff"]
                else None,
            }

        # Check feature completeness
        feature_query = f"""
        SELECT 
            COUNT(*) as total,
            COUNT(current_balance) as has_balance,
            COUNT(rolling_pnl_avg_5d) as has_rolling_features,
            COUNT(market_sentiment_score) as has_market_features
        FROM {self.training_table}
        """
        result = self.db_manager.model_db.execute_query(feature_query)
        if result:
            total = result[0]["total"]
            validation_results["feature_completeness"] = {
                "balance_coverage": (result[0]["has_balance"] / total * 100)
                if total > 0
                else 0,
                "rolling_coverage": (result[0]["has_rolling_features"] / total * 100)
                if total > 0
                else 0,
                "market_coverage": (result[0]["has_market_features"] / total * 100)
                if total > 0
                else 0,
            }

        # Target variable statistics
        target_stats_query = f"""
        SELECT 
            AVG(target_net_profit) as mean_pnl,
            STDDEV(target_net_profit) as std_pnl,
            MIN(target_net_profit) as min_pnl,
            MAX(target_net_profit) as max_pnl,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY target_net_profit) as median_pnl,
            CASE 
                WHEN COUNT(*) > 0 THEN COUNT(CASE WHEN target_net_profit > 0 THEN 1 END)::FLOAT / COUNT(*) * 100 
                ELSE 0 
            END as win_rate
        FROM {self.training_table}
        WHERE target_net_profit IS NOT NULL
        """
        result = self.db_manager.model_db.execute_query(target_stats_query)
        if result:
            validation_results["target_statistics"] = result[0]

        return validation_results


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description="Build model training data")
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for training data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for training data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Force rebuild of existing training data",
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate training data after building"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file="build_training_data")

    # Run training data builder
    builder = TrainingDataBuilder(chunk_size=args.chunk_size)
    try:
        records = builder.build_training_data(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild,
            target_days_ahead=args.target_days,
        )
        logger.info(f"Training data build complete. Total records: {records}")

        # Validate if requested
        if args.validate:
            logger.info("Validating training data...")
            validation = builder.validate_training_data()

            logger.info(f"Total records: {validation['total_records']}")
            logger.info(f"NULL targets: {validation['null_targets']}")

            if "date_alignment" in validation:
                logger.info(f"Date alignment: {validation['date_alignment']}")

            if "feature_completeness" in validation:
                logger.info(
                    f"Feature completeness: {validation['feature_completeness']}"
                )

            if "target_statistics" in validation:
                stats = validation["target_statistics"]
                logger.info("Target statistics:")
                logger.info(f"  - Positive rate: {stats['positive_rate']:.2%}")
                logger.info(f"  - Positive count: {stats['positive_count']:,}")
                logger.info(f"  - Negative count: {stats['negative_count']:,}")
                logger.info(f"  - Total count: {stats['total_count']:,}")
                if stats.get('class_balance_ratio') is not None:
                    logger.info(f"  - Class balance ratio: {stats['class_balance_ratio']:.3f}")
            
            if "interaction_features" in validation:
                interact = validation["interaction_features"]
                logger.info("Interaction feature statistics:")
                for key, value in interact.items():
                    if value is not None:
                        logger.info(f"  - {key}: {float(value):.3f}")
            
            # Log feature list
            features = builder.get_feature_list()
            logger.info(f"Total features available: {len(features)}")
            logger.info(f"Feature groups:")
            logger.info(f"  - Account features: ~40")
            logger.info(f"  - Regime features: ~45")
            logger.info(f"  - Time features: 9")
            logger.info(f"  - Interaction features: 10")

    except Exception as e:
        logger.error(f"Training data build failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
