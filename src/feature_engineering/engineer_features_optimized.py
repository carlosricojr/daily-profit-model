"""
Optimized Feature Engineering Module - Fixes N+1 Query Issues
This module replaces individual queries with bulk fetches and efficient data structures.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple, Set
import argparse
import pandas as pd
import numpy as np
import json
from collections import defaultdict
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Feature version for tracking changes
FEATURE_VERSION = "3.0.0"  # Optimized version with N+1 fixes


class OptimizedFeatureEngineer:
    """Optimized feature engineer that eliminates N+1 queries."""
    
    def __init__(self):
        """Initialize the optimized feature engineer."""
        self.db_manager = get_db_manager()
        self.feature_table = 'feature_store_account_daily'
        self.rolling_windows = [1, 3, 5, 10, 20]
        
        # Performance tracking
        self.query_stats = {
            'total_queries': 0,
            'bulk_queries': 0,
            'time_saved': 0,
            'query_times': []
        }
    
    def engineer_features(self,
                         start_date: Optional[date] = None,
                         end_date: Optional[date] = None,
                         force_rebuild: bool = False) -> int:
        """
        Engineer features for all accounts and dates using bulk queries.
        
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
                pipeline_stage='engineer_features_optimized',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)
            if not start_date:
                start_date = end_date - timedelta(days=30)
            
            logger.info(f"[OPTIMIZED] Engineering features from {start_date} to {end_date}")
            
            # Get work items (account-date combinations to process)
            work_items = self._get_work_items(start_date, end_date, force_rebuild)
            
            if not work_items:
                logger.info("No work items to process")
                return 0
            
            logger.info(f"Processing {len(work_items)} account-date combinations with bulk queries")
            
            # Process in efficient batches
            batch_size = 1000  # Process 1000 account-date combinations at a time
            for i in range(0, len(work_items), batch_size):
                batch = work_items[i:i + batch_size]
                batch_records = self._process_batch_optimized(batch, start_date, end_date)
                total_records += batch_records
                
                # Progress logging
                progress = min(100, ((i + batch_size) / len(work_items)) * 100)
                logger.info(f"Progress: {progress:.1f}% ({i + len(batch)}/{len(work_items)})")
            
            # Log successful completion with performance stats
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features_optimized',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'force_rebuild': force_rebuild,
                    'query_stats': self.query_stats,
                    'avg_query_time': np.mean(self.query_stats['query_times']) if self.query_stats['query_times'] else 0
                }
            )
            
            logger.info(f"Successfully created {total_records} feature records")
            logger.info(f"Query optimization stats: {self.query_stats['bulk_queries']} bulk queries vs {self.query_stats['total_queries']} that would have been individual queries")
            logger.info(f"Estimated time saved: {self.query_stats['time_saved']:.2f} seconds")
            
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='engineer_features_optimized',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to engineer features: {str(e)}")
            raise
    
    def _get_work_items(self, start_date: date, end_date: date, force_rebuild: bool) -> List[Tuple[str, str, date]]:
        """Get list of account-date combinations to process."""
        if force_rebuild:
            query = """
            SELECT DISTINCT account_id, login, date as feature_date
            FROM stg_accounts_daily_snapshots
            WHERE date >= %s AND date <= %s
            ORDER BY date, account_id
            """
            params = (start_date, end_date)
        else:
            # Only get missing features
            query = """
            SELECT DISTINCT s.account_id, s.login, s.date as feature_date
            FROM stg_accounts_daily_snapshots s
            LEFT JOIN feature_store_account_daily f
                ON s.account_id = f.account_id AND s.date = f.feature_date
            WHERE s.date >= %s AND s.date <= %s
                AND f.account_id IS NULL
            ORDER BY s.date, s.account_id
            """
            params = (start_date, end_date)
        
        results = self.db_manager.model_db.execute_query(query, params)
        return [(r['account_id'], r['login'], r['feature_date']) for r in results]
    
    def _process_batch_optimized(self, work_items: List[Tuple[str, str, date]], 
                                start_date: date, end_date: date) -> int:
        """Process a batch of work items using bulk queries."""
        if not work_items:
            return 0
        
        # Extract unique accounts and dates
        account_ids = list(set(item[0] for item in work_items))
        dates = list(set(item[2] for item in work_items))
        
        logger.debug(f"Processing batch: {len(account_ids)} accounts, {len(dates)} dates")
        
        # Create lookup for work items
        work_items_set = set((item[0], item[2]) for item in work_items)
        account_login_map = {item[0]: item[1] for item in work_items}
        
        # Bulk fetch all data needed
        bulk_data = self._bulk_fetch_all_data(account_ids, dates, start_date, end_date)
        
        # Process each work item using the bulk-fetched data
        features_batch = []
        for account_id, login, feature_date in work_items:
            features = self._calculate_features_from_bulk_data(
                account_id, login, feature_date, bulk_data
            )
            if features:
                features_batch.append(features)
        
        # Bulk save features
        if features_batch:
            return self._bulk_save_features(features_batch)
        
        return 0
    
    def _bulk_fetch_all_data(self, account_ids: List[str], dates: List[date],
                            start_date: date, end_date: date) -> Dict[str, Any]:
        """Fetch all required data in bulk queries."""
        bulk_data = {}
        
        # 1. Bulk fetch static features (account snapshots)
        query_start = time.time()
        bulk_data['static_features'] = self._bulk_fetch_static_features(account_ids, dates)
        self._track_query_time(time.time() - query_start)
        
        # 2. Bulk fetch dynamic features
        query_start = time.time()
        bulk_data['dynamic_features'] = self._bulk_fetch_dynamic_features(account_ids, dates)
        self._track_query_time(time.time() - query_start)
        
        # 3. Bulk fetch open positions
        query_start = time.time()
        bulk_data['open_positions'] = self._bulk_fetch_open_positions(account_ids, dates)
        self._track_query_time(time.time() - query_start)
        
        # 4. Bulk fetch historical performance data (for rolling windows)
        query_start = time.time()
        bulk_data['performance_data'] = self._bulk_fetch_performance_data(
            account_ids, start_date, end_date
        )
        self._track_query_time(time.time() - query_start)
        
        # 5. Bulk fetch trades data for behavioral features
        query_start = time.time()
        bulk_data['trades_data'] = self._bulk_fetch_trades_data(
            account_ids, start_date, end_date
        )
        self._track_query_time(time.time() - query_start)
        
        # 6. Bulk fetch market regime data
        query_start = time.time()
        bulk_data['market_data'] = self._bulk_fetch_market_data(dates)
        self._track_query_time(time.time() - query_start)
        
        return bulk_data
    
    def _bulk_fetch_static_features(self, account_ids: List[str], dates: List[date]) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch static account features."""
        self.query_stats['bulk_queries'] += 1
        self.query_stats['total_queries'] += len(account_ids) * len(dates)  # What it would have been
        
        query = """
        SELECT 
            account_id,
            date,
            starting_balance,
            max_daily_drawdown_pct,
            max_drawdown_pct,
            profit_target_pct,
            max_leverage,
            CASE WHEN is_drawdown_relative THEN 1 ELSE 0 END as is_drawdown_relative
        FROM stg_accounts_daily_snapshots
        WHERE account_id = ANY(%s) AND date = ANY(%s)
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))
        
        # Convert to lookup dictionary
        features_lookup = {}
        for row in results:
            key = (row['account_id'], row['date'])
            features_lookup[key] = {
                'starting_balance': row['starting_balance'],
                'max_daily_drawdown_pct': row['max_daily_drawdown_pct'],
                'max_drawdown_pct': row['max_drawdown_pct'],
                'profit_target_pct': row['profit_target_pct'],
                'max_leverage': row['max_leverage'],
                'is_drawdown_relative': row['is_drawdown_relative']
            }
        
        logger.debug(f"Bulk fetched {len(features_lookup)} static feature records")
        return features_lookup
    
    def _bulk_fetch_dynamic_features(self, account_ids: List[str], dates: List[date]) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch dynamic account features."""
        self.query_stats['bulk_queries'] += 1
        self.query_stats['total_queries'] += len(account_ids) * len(dates)
        
        query = """
        SELECT 
            account_id,
            date,
            current_balance,
            current_equity,
            days_since_first_trade,
            active_trading_days_count,
            distance_to_profit_target,
            distance_to_max_drawdown
        FROM stg_accounts_daily_snapshots
        WHERE account_id = ANY(%s) AND date = ANY(%s)
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))
        
        # Convert to lookup dictionary
        features_lookup = {}
        for row in results:
            key = (row['account_id'], row['date'])
            features_lookup[key] = {
                'current_balance': row['current_balance'],
                'current_equity': row['current_equity'],
                'days_since_first_trade': row['days_since_first_trade'] or 0,
                'active_trading_days_count': row['active_trading_days_count'] or 0,
                'distance_to_profit_target': row['distance_to_profit_target'],
                'distance_to_max_drawdown': row['distance_to_max_drawdown']
            }
        
        return features_lookup
    
    def _bulk_fetch_open_positions(self, account_ids: List[str], dates: List[date]) -> Dict[Tuple[str, date], Dict]:
        """Bulk fetch open positions data."""
        self.query_stats['bulk_queries'] += 1
        self.query_stats['total_queries'] += len(account_ids) * len(dates)
        
        query = """
        SELECT 
            account_id,
            trade_date,
            SUM(unrealized_pnl) as open_pnl,
            SUM(volume_usd) as open_positions_volume
        FROM raw_trades_open
        WHERE account_id = ANY(%s) AND trade_date = ANY(%s)
        GROUP BY account_id, trade_date
        """
        
        results = self.db_manager.model_db.execute_query(query, (account_ids, dates))
        
        # Convert to lookup dictionary
        positions_lookup = {}
        for row in results:
            key = (row['account_id'], row['trade_date'])
            positions_lookup[key] = {
                'open_pnl': row['open_pnl'] or 0.0,
                'open_positions_volume': row['open_positions_volume'] or 0.0
            }
        
        return positions_lookup
    
    def _bulk_fetch_performance_data(self, account_ids: List[str], 
                                   start_date: date, end_date: date) -> Dict[str, pd.DataFrame]:
        """Bulk fetch historical performance data for all accounts."""
        self.query_stats['bulk_queries'] += 1
        self.query_stats['total_queries'] += len(account_ids) * 60  # Assuming ~60 queries for rolling windows
        
        # Get more historical data for rolling windows
        historical_start = start_date - timedelta(days=60)
        
        query = """
        SELECT 
            account_id,
            date,
            net_profit
        FROM raw_metrics_daily
        WHERE account_id = ANY(%s) 
            AND date >= %s 
            AND date <= %s
        ORDER BY account_id, date DESC
        """
        
        df = self.db_manager.model_db.execute_query_df(
            query, (account_ids, historical_start, end_date)
        )
        
        # Group by account_id for easy lookup
        performance_lookup = {}
        if not df.empty:
            for account_id, group in df.groupby('account_id'):
                performance_lookup[account_id] = group.sort_values('date', ascending=False)
        
        logger.debug(f"Bulk fetched performance data for {len(performance_lookup)} accounts")
        return performance_lookup
    
    def _bulk_fetch_trades_data(self, account_ids: List[str], 
                               start_date: date, end_date: date) -> Dict[str, pd.DataFrame]:
        """Bulk fetch trades data for behavioral features."""
        self.query_stats['bulk_queries'] += 1
        self.query_stats['total_queries'] += len(account_ids) * 5  # Assuming ~5 days window per account
        
        # Get trades for behavioral features (5-day window)
        behavioral_start = start_date - timedelta(days=5)
        
        query = """
        SELECT 
            account_id,
            trade_date,
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
        WHERE account_id = ANY(%s) 
            AND trade_date >= %s 
            AND trade_date <= %s
        ORDER BY account_id, trade_date
        """
        
        df = self.db_manager.model_db.execute_query_df(
            query, (account_ids, behavioral_start, end_date)
        )
        
        # Group by account_id for easy lookup
        trades_lookup = {}
        if not df.empty:
            for account_id, group in df.groupby('account_id'):
                trades_lookup[account_id] = group
        
        logger.debug(f"Bulk fetched trades data for {len(trades_lookup)} accounts")
        return trades_lookup
    
    def _bulk_fetch_market_data(self, dates: List[date]) -> Dict[date, Dict]:
        """Bulk fetch market regime data."""
        self.query_stats['bulk_queries'] += 1
        self.query_stats['total_queries'] += len(dates)
        
        query = """
        WITH ranked_regimes AS (
            SELECT 
                date,
                market_news,
                instruments,
                country_economic_indicators,
                news_analysis,
                summary,
                ingestion_timestamp,
                ROW_NUMBER() OVER (PARTITION BY date ORDER BY ingestion_timestamp DESC) as rn
            FROM raw_regimes_daily
            WHERE date = ANY(%s)
        )
        SELECT * FROM ranked_regimes WHERE rn = 1
        """
        
        results = self.db_manager.model_db.execute_query(query, (dates,))
        
        # Convert to lookup dictionary
        market_lookup = {}
        for row in results:
            market_lookup[row['date']] = self._parse_market_features(row)
        
        logger.debug(f"Bulk fetched market data for {len(market_lookup)} dates")
        return market_lookup
    
    def _parse_market_features(self, regime_data: Dict) -> Dict[str, Any]:
        """Parse market features from regime data."""
        features = {}
        
        # Parse sentiment score
        try:
            news_analysis = json.loads(regime_data['news_analysis']) if isinstance(
                regime_data['news_analysis'], str
            ) else regime_data['news_analysis']
            
            sentiment_score = news_analysis.get('sentiment_summary', {}).get(
                'average_score', 0.0
            )
            features['market_sentiment_score'] = sentiment_score
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            features['market_sentiment_score'] = 0.0
        
        # Parse volatility regime and liquidity state
        try:
            summary = json.loads(regime_data['summary']) if isinstance(
                regime_data['summary'], str
            ) else regime_data['summary']
            
            key_metrics = summary.get('key_metrics', {})
            features['market_volatility_regime'] = key_metrics.get('volatility_regime', 'normal')
            features['market_liquidity_state'] = key_metrics.get('liquidity_state', 'normal')
        except (json.JSONDecodeError, KeyError, TypeError):
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
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
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
        except (json.JSONDecodeError, KeyError, TypeError):
            features['fed_funds_rate'] = 5.0
        
        return features
    
    def _calculate_features_from_bulk_data(self, account_id: str, login: str, 
                                         feature_date: date, bulk_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Calculate features using bulk-fetched data."""
        try:
            features = {
                'account_id': account_id,
                'login': login,
                'feature_date': feature_date
            }
            
            # 1. Static features from bulk data
            static_key = (account_id, feature_date)
            if static_key in bulk_data['static_features']:
                features.update(bulk_data['static_features'][static_key])
            else:
                # Use default values
                features.update({
                    'starting_balance': None,
                    'max_daily_drawdown_pct': None,
                    'max_drawdown_pct': None,
                    'profit_target_pct': None,
                    'max_leverage': None,
                    'is_drawdown_relative': 0
                })
            
            # 2. Dynamic features from bulk data
            dynamic_key = (account_id, feature_date)
            if dynamic_key in bulk_data['dynamic_features']:
                features.update(bulk_data['dynamic_features'][dynamic_key])
            else:
                features.update({
                    'current_balance': None,
                    'current_equity': None,
                    'days_since_first_trade': 0,
                    'active_trading_days_count': 0,
                    'distance_to_profit_target': None,
                    'distance_to_max_drawdown': None
                })
            
            # 3. Open positions from bulk data
            positions_key = (account_id, feature_date)
            if positions_key in bulk_data['open_positions']:
                features.update(bulk_data['open_positions'][positions_key])
            else:
                features['open_pnl'] = 0.0
                features['open_positions_volume'] = 0.0
            
            # 4. Performance features from bulk data
            performance_features = self._calculate_performance_features_from_bulk(
                account_id, feature_date, bulk_data['performance_data']
            )
            features.update(performance_features)
            
            # 5. Behavioral features from bulk data
            behavioral_features = self._calculate_behavioral_features_from_bulk(
                account_id, feature_date, bulk_data['trades_data']
            )
            features.update(behavioral_features)
            
            # 6. Market features from bulk data
            if feature_date in bulk_data['market_data']:
                features.update(bulk_data['market_data'][feature_date])
            else:
                # Default market features
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
            
            # 7. Time features (calculated, no query needed)
            time_features = self._get_time_features(feature_date)
            features.update(time_features)
            
            return features
            
        except Exception as e:
            logger.error(f"Error calculating features for {account_id} on {feature_date}: {str(e)}")
            return None
    
    def _calculate_performance_features_from_bulk(self, account_id: str, feature_date: date,
                                                performance_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate rolling performance features from bulk data."""
        features = {}
        
        if account_id not in performance_data:
            # Return default values for all rolling features
            for window in self.rolling_windows:
                features.update(self._get_default_rolling_features(window))
            return features
        
        # Get the account's performance data
        pnl_df = performance_data[account_id]
        
        # Filter to only data up to feature_date
        pnl_df = pnl_df[pnl_df['date'] <= feature_date]
        
        if pnl_df.empty:
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
    
    def _calculate_behavioral_features_from_bulk(self, account_id: str, feature_date: date,
                                               trades_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate behavioral features from bulk trades data."""
        features = {}
        
        if account_id not in trades_data:
            # Return default values
            return {
                'trades_count_5d': 0,
                'avg_trade_duration_5d': 0.0,
                'avg_lots_per_trade_5d': 0.0,
                'avg_volume_per_trade_5d': 0.0,
                'stop_loss_usage_rate_5d': 0.0,
                'take_profit_usage_rate_5d': 0.0,
                'buy_sell_ratio_5d': 0.5,
                'top_symbol_concentration_5d': 0.0
            }
        
        # Get the account's trades data
        trades_df = trades_data[account_id]
        
        # Filter to 5-day window
        window_start = feature_date - timedelta(days=4)
        trades_df = trades_df[
            (trades_df['trade_date'] >= window_start) & 
            (trades_df['trade_date'] <= feature_date)
        ]
        
        if trades_df.empty:
            return {
                'trades_count_5d': 0,
                'avg_trade_duration_5d': 0.0,
                'avg_lots_per_trade_5d': 0.0,
                'avg_volume_per_trade_5d': 0.0,
                'stop_loss_usage_rate_5d': 0.0,
                'take_profit_usage_rate_5d': 0.0,
                'buy_sell_ratio_5d': 0.5,
                'top_symbol_concentration_5d': 0.0
            }
        
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
    
    def _get_time_features(self, feature_date: date) -> Dict[str, Any]:
        """Calculate date and time features."""
        return {
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
    
    def _bulk_save_features(self, features_batch: List[Dict[str, Any]]) -> int:
        """Save a batch of features efficiently using bulk insert."""
        if not features_batch:
            return 0
        
        # Prepare data for bulk insert
        columns = list(features_batch[0].keys())
        
        # Build bulk insert query
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)
        
        # Create values list
        values_list = []
        for features in features_batch:
            values_list.append([features.get(col) for col in columns])
        
        # Build the bulk insert query with ON CONFLICT
        query = f"""
        INSERT INTO {self.feature_table} ({columns_str})
        VALUES {', '.join([f'({placeholders})' for _ in range(len(features_batch))])}
        ON CONFLICT (account_id, feature_date) 
        DO UPDATE SET
            {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in ['account_id', 'feature_date']])}
        """
        
        # Flatten values for query execution
        flat_values = [val for row in values_list for val in row]
        
        try:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, flat_values)
                    return cursor.rowcount
        except Exception as e:
            logger.error(f"Error bulk saving features: {str(e)}")
            # Fall back to individual saves
            saved_count = 0
            for features in features_batch:
                try:
                    self._save_single_feature(features)
                    saved_count += 1
                except Exception as e2:
                    logger.error(f"Error saving feature for {features.get('account_id')}: {str(e2)}")
            return saved_count
    
    def _save_single_feature(self, features: Dict[str, Any]):
        """Save a single feature record (fallback method)."""
        columns = list(features.keys())
        values = [features[col] for col in columns]
        
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
    
    def _track_query_time(self, query_time: float):
        """Track query execution time for performance monitoring."""
        self.query_stats['query_times'].append(query_time)
        # Estimate time saved (assuming individual queries would take 10ms each)
        estimated_individual_time = self.query_stats['total_queries'] * 0.01
        self.query_stats['time_saved'] = estimated_individual_time - sum(self.query_stats['query_times'])


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Optimized feature engineering with N+1 query fixes')
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
    setup_logging(log_level=args.log_level, log_file='engineer_features_optimized')
    
    # Run optimized feature engineering
    engineer = OptimizedFeatureEngineer()
    try:
        records = engineer.engineer_features(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild
        )
        logger.info(f"Optimized feature engineering complete. Total records: {records}")
    except Exception as e:
        logger.error(f"Feature engineering failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()