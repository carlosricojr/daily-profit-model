"""
Engineer features for the daily profit prediction model.
Creates features from multiple data sources and stores them in feature_store_account_daily.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
import argparse
import pandas as pd
import numpy as np
import json
from scipy import stats

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Handles feature engineering for the daily profit model."""
    
    def __init__(self):
        """Initialize the feature engineer."""
        self.db_manager = get_db_manager()
        self.feature_table = 'feature_store_account_daily'
        
        # Rolling window configurations
        self.rolling_windows = [1, 3, 5, 10, 20]
        
    def engineer_features(self,
                         start_date: Optional[date] = None,
                         end_date: Optional[date] = None,
                         force_rebuild: bool = False) -> int:
        """
        Engineer features for all accounts and dates in the specified range.
        
        Args:
            start_date: Start date for feature engineering
            end_date: End date for feature engineering
            force_rebuild: If True, rebuild features even if they exist
            
        Returns:
            Number of feature records created
        """
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)
            if not start_date:
                start_date = end_date - timedelta(days=30)
            
            logger.info(f"Engineering features from {start_date} to {end_date}")
            
            # Get all unique accounts
            accounts = self._get_active_accounts(start_date, end_date)
            logger.info(f"Found {len(accounts)} active accounts to process")
            
            # Process each account
            for account_id, login in accounts:
                account_records = self._engineer_features_for_account(
                    account_id, login, start_date, end_date, force_rebuild
                )
                total_records += account_records
                
                if total_records % 1000 == 0:
                    logger.info(f"Progress: {total_records} feature records created")
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'accounts_processed': len(accounts),
                    'force_rebuild': force_rebuild
                }
            )
            
            logger.info(f"Successfully created {total_records} feature records")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to engineer features: {str(e)}")
            raise
    
    def _get_active_accounts(self, start_date: date, end_date: date) -> List[Tuple[str, str]]:
        """Get list of active accounts in the date range."""
        query = """
        SELECT DISTINCT account_id, login
        FROM stg_accounts_daily_snapshots
        WHERE date >= %s AND date <= %s
        ORDER BY account_id
        """
        results = self.db_manager.model_db.execute_query(query, (start_date, end_date))
        return [(r['account_id'], r['login']) for r in results]
    
    def _engineer_features_for_account(self,
                                     account_id: str,
                                     login: str,
                                     start_date: date,
                                     end_date: date,
                                     force_rebuild: bool) -> int:
        """Engineer features for a single account over the date range."""
        records_created = 0
        
        # Process each date
        current_date = start_date
        while current_date <= end_date:
            # Check if features already exist
            if not force_rebuild and self._features_exist(account_id, current_date):
                current_date += timedelta(days=1)
                continue
            
            # Engineer features for this date
            features = self._calculate_features_for_date(account_id, login, current_date)
            
            if features:
                self._save_features(features)
                records_created += 1
            
            current_date += timedelta(days=1)
        
        return records_created
    
    def _features_exist(self, account_id: str, feature_date: date) -> bool:
        """Check if features already exist for an account and date."""
        query = f"""
        SELECT EXISTS(
            SELECT 1 FROM {self.feature_table}
            WHERE account_id = %s AND feature_date = %s
        )
        """
        result = self.db_manager.model_db.execute_query(query, (account_id, feature_date))
        return result[0]['exists'] if result else False
    
    def _calculate_features_for_date(self,
                                   account_id: str,
                                   login: str,
                                   feature_date: date) -> Optional[Dict[str, Any]]:
        """
        Calculate all features for an account on a specific date.
        Features from day D are used to predict PnL for day D+1.
        """
        try:
            # Initialize feature dictionary
            features = {
                'account_id': account_id,
                'login': login,
                'feature_date': feature_date
            }
            
            # 1. Static Account & Plan Features
            static_features = self._get_static_features(account_id, feature_date)
            features.update(static_features)
            
            # 2. Dynamic Account State Features
            dynamic_features = self._get_dynamic_features(account_id, feature_date)
            features.update(dynamic_features)
            
            # 3. Historical Performance Features
            performance_features = self._get_performance_features(account_id, feature_date)
            features.update(performance_features)
            
            # 4. Behavioral Features
            behavioral_features = self._get_behavioral_features(account_id, feature_date)
            features.update(behavioral_features)
            
            # 5. Market Regime Features
            market_features = self._get_market_features(feature_date)
            features.update(market_features)
            
            # 6. Date and Time Features
            time_features = self._get_time_features(feature_date)
            features.update(time_features)
            
            return features
            
        except Exception as e:
            logger.error(f"Error calculating features for {account_id} on {feature_date}: {str(e)}")
            return None
    
    def _get_static_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Get static account and plan features."""
        query = """
        SELECT 
            starting_balance,
            max_daily_drawdown_pct,
            max_drawdown_pct,
            profit_target_pct,
            max_leverage,
            CASE WHEN is_drawdown_relative THEN 1 ELSE 0 END as is_drawdown_relative
        FROM stg_accounts_daily_snapshots
        WHERE account_id = %s AND date = %s
        """
        
        result = self.db_manager.model_db.execute_query(query, (account_id, feature_date))
        
        if result:
            return result[0]
        else:
            # Return defaults if not found
            return {
                'starting_balance': None,
                'max_daily_drawdown_pct': None,
                'max_drawdown_pct': None,
                'profit_target_pct': None,
                'max_leverage': None,
                'is_drawdown_relative': 0
            }
    
    def _get_dynamic_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Get dynamic account state features as of EOD feature_date."""
        # Get snapshot data
        snapshot_query = """
        SELECT 
            current_balance,
            current_equity,
            days_since_first_trade,
            active_trading_days_count,
            distance_to_profit_target,
            distance_to_max_drawdown
        FROM stg_accounts_daily_snapshots
        WHERE account_id = %s AND date = %s
        """
        
        snapshot_result = self.db_manager.model_db.execute_query(
            snapshot_query, (account_id, feature_date)
        )
        
        features = {}
        if snapshot_result:
            features.update(snapshot_result[0])
        else:
            features.update({
                'current_balance': None,
                'current_equity': None,
                'days_since_first_trade': 0,
                'active_trading_days_count': 0,
                'distance_to_profit_target': None,
                'distance_to_max_drawdown': None
            })
        
        # Get open positions data
        open_positions_query = """
        SELECT 
            SUM(unrealized_pnl) as open_pnl,
            SUM(volume_usd) as open_positions_volume
        FROM raw_trades_open
        WHERE account_id = %s AND trade_date = %s
        """
        
        open_result = self.db_manager.model_db.execute_query(
            open_positions_query, (account_id, feature_date)
        )
        
        if open_result and open_result[0]['open_pnl'] is not None:
            features['open_pnl'] = open_result[0]['open_pnl']
            features['open_positions_volume'] = open_result[0]['open_positions_volume']
        else:
            features['open_pnl'] = 0.0
            features['open_positions_volume'] = 0.0
        
        return features
    
    def _get_performance_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Calculate rolling window performance features."""
        features = {}
        
        # Get historical daily PnL data
        pnl_query = """
        SELECT date, net_profit
        FROM raw_metrics_daily
        WHERE account_id = %s AND date <= %s
        ORDER BY date DESC
        LIMIT 60  -- Maximum window we need
        """
        
        pnl_df = self.db_manager.model_db.execute_query_df(pnl_query, (account_id, feature_date))
        
        if pnl_df.empty:
            # Return default values for all rolling features
            for window in self.rolling_windows:
                features.update(self._get_default_rolling_features(window))
            return features
        
        # Calculate features for each rolling window
        for window in self.rolling_windows:
            if len(pnl_df) >= window:
                window_data = pnl_df.head(window)
                
                # Basic statistics
                features[f'rolling_pnl_sum_{window}d'] = window_data['net_profit'].sum()
                features[f'rolling_pnl_avg_{window}d'] = window_data['net_profit'].mean()
                features[f'rolling_pnl_std_{window}d'] = window_data['net_profit'].std()
                
                if window >= 3:
                    features[f'rolling_pnl_min_{window}d'] = window_data['net_profit'].min()
                    features[f'rolling_pnl_max_{window}d'] = window_data['net_profit'].max()
                    
                    # Win rate
                    wins = (window_data['net_profit'] > 0).sum()
                    features[f'win_rate_{window}d'] = (wins / window) * 100
                
                if window >= 5:
                    # Profit factor
                    gains = window_data[window_data['net_profit'] > 0]['net_profit'].sum()
                    losses = abs(window_data[window_data['net_profit'] < 0]['net_profit'].sum())
                    if losses > 0:
                        features[f'profit_factor_{window}d'] = gains / losses
                    else:
                        features[f'profit_factor_{window}d'] = gains if gains > 0 else 0
                    
                    # Sharpe ratio (simplified)
                    if features[f'rolling_pnl_std_{window}d'] > 0:
                        features[f'sharpe_ratio_{window}d'] = (
                            features[f'rolling_pnl_avg_{window}d'] / 
                            features[f'rolling_pnl_std_{window}d']
                        ) * np.sqrt(252)  # Annualized
                    else:
                        features[f'sharpe_ratio_{window}d'] = 0
            else:
                features.update(self._get_default_rolling_features(window))
        
        return features
    
    def _get_default_rolling_features(self, window: int) -> Dict[str, float]:
        """Get default values for rolling features when not enough data."""
        features = {
            f'rolling_pnl_sum_{window}d': 0.0,
            f'rolling_pnl_avg_{window}d': 0.0,
            f'rolling_pnl_std_{window}d': 0.0
        }
        
        if window >= 3:
            features[f'rolling_pnl_min_{window}d'] = 0.0
            features[f'rolling_pnl_max_{window}d'] = 0.0
            features[f'win_rate_{window}d'] = 0.0
        
        if window >= 5:
            features[f'profit_factor_{window}d'] = 0.0
            features[f'sharpe_ratio_{window}d'] = 0.0
        
        return features
    
    def _get_behavioral_features(self, account_id: str, feature_date: date) -> Dict[str, Any]:
        """Calculate behavioral trading features."""
        # Use 5-day window for behavioral features
        window_start = feature_date - timedelta(days=4)
        
        trades_query = """
        SELECT 
            trade_id,
            symbol,
            std_symbol,
            side,
            open_time,
            close_time,
            stop_loss,
            take_profit,
            lots,
            volume_usd
        FROM raw_trades_closed
        WHERE account_id = %s 
            AND trade_date >= %s 
            AND trade_date <= %s
        """
        
        trades_df = self.db_manager.model_db.execute_query_df(
            trades_query, (account_id, window_start, feature_date)
        )
        
        features = {}
        
        if trades_df.empty:
            # Return default values
            features.update({
                'trades_count_5d': 0,
                'avg_trade_duration_5d': 0.0,
                'avg_lots_per_trade_5d': 0.0,
                'avg_volume_per_trade_5d': 0.0,
                'stop_loss_usage_rate_5d': 0.0,
                'take_profit_usage_rate_5d': 0.0,
                'buy_sell_ratio_5d': 0.5,
                'top_symbol_concentration_5d': 0.0
            })
        else:
            # Trade count
            features['trades_count_5d'] = len(trades_df)
            
            # Average trade duration (in hours)
            if 'open_time' in trades_df.columns and 'close_time' in trades_df.columns:
                trades_df['duration'] = (
                    pd.to_datetime(trades_df['close_time']) - 
                    pd.to_datetime(trades_df['open_time'])
                ).dt.total_seconds() / 3600
                features['avg_trade_duration_5d'] = trades_df['duration'].mean()
            else:
                features['avg_trade_duration_5d'] = 0.0
            
            # Average lots and volume
            features['avg_lots_per_trade_5d'] = trades_df['lots'].mean()
            features['avg_volume_per_trade_5d'] = trades_df['volume_usd'].mean()
            
            # Stop loss and take profit usage
            sl_count = (trades_df['stop_loss'].notna() & (trades_df['stop_loss'] != 0)).sum()
            tp_count = (trades_df['take_profit'].notna() & (trades_df['take_profit'] != 0)).sum()
            features['stop_loss_usage_rate_5d'] = (sl_count / len(trades_df)) * 100
            features['take_profit_usage_rate_5d'] = (tp_count / len(trades_df)) * 100
            
            # Buy/sell ratio
            buy_count = (trades_df['side'] == 'buy').sum()
            sell_count = (trades_df['side'] == 'sell').sum()
            total_sides = buy_count + sell_count
            if total_sides > 0:
                features['buy_sell_ratio_5d'] = buy_count / total_sides
            else:
                features['buy_sell_ratio_5d'] = 0.5
            
            # Symbol concentration
            if 'std_symbol' in trades_df.columns:
                symbol_counts = trades_df['std_symbol'].value_counts()
                if len(symbol_counts) > 0:
                    features['top_symbol_concentration_5d'] = (
                        symbol_counts.iloc[0] / len(trades_df)
                    ) * 100
                else:
                    features['top_symbol_concentration_5d'] = 0.0
            else:
                features['top_symbol_concentration_5d'] = 0.0
        
        return features
    
    def _get_market_features(self, feature_date: date) -> Dict[str, Any]:
        """Extract market regime features for the date."""
        query = """
        SELECT 
            market_news,
            instruments,
            country_economic_indicators,
            news_analysis,
            summary
        FROM raw_regimes_daily
        WHERE date = %s
        ORDER BY ingestion_timestamp DESC
        LIMIT 1
        """
        
        result = self.db_manager.model_db.execute_query(query, (feature_date,))
        
        features = {}
        
        if result:
            regime_data = result[0]
            
            # Parse sentiment score
            try:
                news_analysis = json.loads(regime_data['news_analysis']) if isinstance(
                    regime_data['news_analysis'], str
                ) else regime_data['news_analysis']
                
                sentiment_score = news_analysis.get('sentiment_summary', {}).get(
                    'average_score', 0.0
                )
                features['market_sentiment_score'] = sentiment_score
            except:
                features['market_sentiment_score'] = 0.0
            
            # Parse volatility regime and liquidity state
            try:
                summary = json.loads(regime_data['summary']) if isinstance(
                    regime_data['summary'], str
                ) else regime_data['summary']
                
                key_metrics = summary.get('key_metrics', {})
                features['market_volatility_regime'] = key_metrics.get('volatility_regime', 'normal')
                features['market_liquidity_state'] = key_metrics.get('liquidity_state', 'normal')
            except:
                features['market_volatility_regime'] = 'normal'
                features['market_liquidity_state'] = 'normal'
            
            # Parse instrument data
            try:
                instruments = json.loads(regime_data['instruments']) if isinstance(
                    regime_data['instruments'], str
                ) else regime_data['instruments']
                
                # Get specific asset metrics
                vix_data = instruments.get('data', {}).get('VIX', {})
                features['vix_level'] = vix_data.get('last_price', 15.0)
                
                dxy_data = instruments.get('data', {}).get('DXY', {})
                features['dxy_level'] = dxy_data.get('last_price', 100.0)
                
                sp500_data = instruments.get('data', {}).get('SP500', {})
                features['sp500_daily_return'] = sp500_data.get('daily_return', 0.0)
                
                btc_data = instruments.get('data', {}).get('BTCUSD', {})
                features['btc_volatility_90d'] = btc_data.get('volatility_90d', 0.5)
            except:
                features.update({
                    'vix_level': 15.0,
                    'dxy_level': 100.0,
                    'sp500_daily_return': 0.0,
                    'btc_volatility_90d': 0.5
                })
            
            # Parse economic indicators
            try:
                indicators = json.loads(regime_data['country_economic_indicators']) if isinstance(
                    regime_data['country_economic_indicators'], str
                ) else regime_data['country_economic_indicators']
                
                features['fed_funds_rate'] = indicators.get('fed_funds_rate_effective', 5.0)
            except:
                features['fed_funds_rate'] = 5.0
        
        else:
            # Default values if no regime data found
            features.update({
                'market_sentiment_score': 0.0,
                'market_volatility_regime': 'normal',
                'market_liquidity_state': 'normal',
                'vix_level': 15.0,
                'dxy_level': 100.0,
                'sp500_daily_return': 0.0,
                'btc_volatility_90d': 0.5,
                'fed_funds_rate': 5.0
            })
        
        return features
    
    def _get_time_features(self, feature_date: date) -> Dict[str, Any]:
        """Calculate date and time features."""
        features = {
            'day_of_week': feature_date.weekday(),  # 0 = Monday, 6 = Sunday
            'week_of_month': (feature_date.day - 1) // 7 + 1,
            'month': feature_date.month,
            'quarter': (feature_date.month - 1) // 3 + 1,
            'day_of_year': feature_date.timetuple().tm_yday,
            'is_month_start': feature_date.day <= 3,
            'is_month_end': feature_date.day >= 28,
            'is_quarter_start': feature_date.month in [1, 4, 7, 10] and feature_date.day <= 3,
            'is_quarter_end': feature_date.month in [3, 6, 9, 12] and feature_date.day >= 28
        }
        
        return features
    
    def _save_features(self, features: Dict[str, Any]):
        """Save calculated features to the database."""
        # Convert feature dict to match database columns
        columns = list(features.keys())
        values = [features[col] for col in columns]
        
        # Build insert query with ON CONFLICT
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)
        
        query = f"""
        INSERT INTO {self.feature_table} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (account_id, feature_date) 
        DO UPDATE SET
            {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in ['account_id', 'feature_date']])}
        """
        
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, values)


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Engineer features for daily profit model')
    parser.add_argument('--start-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Start date for feature engineering (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='End date for feature engineering (YYYY-MM-DD)')
    parser.add_argument('--force-rebuild', action='store_true',
                       help='Force rebuild of existing features')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='engineer_features')
    
    # Run feature engineering
    engineer = FeatureEngineer()
    try:
        records = engineer.engineer_features(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild
        )
        logger.info(f"Feature engineering complete. Total records: {records}")
    except Exception as e:
        logger.error(f"Feature engineering failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()