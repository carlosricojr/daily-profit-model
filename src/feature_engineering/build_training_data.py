"""
Build the model training input table by combining features with target variables.
Features from day D are aligned with target PnL from day D+1.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Optional
import argparse
import pandas as pd

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class TrainingDataBuilder:
    """Builds the model training input table."""
    
    def __init__(self):
        """Initialize the training data builder."""
        self.db_manager = get_db_manager()
        self.training_table = 'model_training_input'
        
    def build_training_data(self,
                          start_date: Optional[date] = None,
                          end_date: Optional[date] = None,
                          force_rebuild: bool = False) -> int:
        """
        Build training data by aligning features with target variables.
        
        Args:
            start_date: Start date for training data
            end_date: End date for training data
            force_rebuild: If True, rebuild even if data exists
            
        Returns:
            Number of training records created
        """
        start_time = datetime.now()
        total_records = 0
        
        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage='build_training_data',
                execution_date=datetime.now().date(),
                status='running'
            )
            
            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=2)  # Need D+1 for target
            if not start_date:
                start_date = end_date - timedelta(days=90)  # Default to 90 days
            
            logger.info(f"Building training data from {start_date} to {end_date}")
            
            # Clear existing data if force rebuild
            if force_rebuild:
                logger.warning("Force rebuild requested. Truncating existing training data.")
                self.db_manager.model_db.execute_command(f"TRUNCATE TABLE {self.training_table}")
            
            # Build training data using SQL
            total_records = self._build_training_records(start_date, end_date)
            
            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage='build_training_data',
                execution_date=datetime.now().date(),
                status='success',
                records_processed=total_records,
                execution_details={
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'start_date': str(start_date),
                    'end_date': str(end_date),
                    'force_rebuild': force_rebuild
                }
            )
            
            logger.info(f"Successfully created {total_records} training records")
            return total_records
            
        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage='build_training_data',
                execution_date=datetime.now().date(),
                status='failed',
                error_message=str(e),
                records_processed=total_records
            )
            logger.error(f"Failed to build training data: {str(e)}")
            raise
    
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
            login, prediction_date, feature_date,
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
                WHERE date = f.feature_date + INTERVAL '1 day'
            )
        ON CONFLICT (login, prediction_date) DO NOTHING
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
        validation_results['total_records'] = result[0]['total'] if result else 0
        
        # Check for NULL targets
        null_target_query = f"""
        SELECT COUNT(*) as null_targets 
        FROM {self.training_table}
        WHERE target_net_profit IS NULL
        """
        result = self.db_manager.model_db.execute_query(null_target_query)
        validation_results['null_targets'] = result[0]['null_targets'] if result else 0
        
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
            validation_results['date_alignment'] = {
                'min_diff_days': result[0]['min_diff'].days if result[0]['min_diff'] else None,
                'max_diff_days': result[0]['max_diff'].days if result[0]['max_diff'] else None,
                'avg_diff_days': float(result[0]['avg_diff'].days) if result[0]['avg_diff'] else None
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
            total = result[0]['total']
            validation_results['feature_completeness'] = {
                'balance_coverage': (result[0]['has_balance'] / total * 100) if total > 0 else 0,
                'rolling_coverage': (result[0]['has_rolling_features'] / total * 100) if total > 0 else 0,
                'market_coverage': (result[0]['has_market_features'] / total * 100) if total > 0 else 0
            }
        
        # Target variable statistics
        target_stats_query = f"""
        SELECT 
            AVG(target_net_profit) as mean_pnl,
            STDDEV(target_net_profit) as std_pnl,
            MIN(target_net_profit) as min_pnl,
            MAX(target_net_profit) as max_pnl,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY target_net_profit) as median_pnl,
            COUNT(CASE WHEN target_net_profit > 0 THEN 1 END)::FLOAT / COUNT(*) * 100 as win_rate
        FROM {self.training_table}
        WHERE target_net_profit IS NOT NULL
        """
        result = self.db_manager.model_db.execute_query(target_stats_query)
        if result:
            validation_results['target_statistics'] = result[0]
        
        return validation_results


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(description='Build model training data')
    parser.add_argument('--start-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='Start date for training data (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                       help='End date for training data (YYYY-MM-DD)')
    parser.add_argument('--force-rebuild', action='store_true',
                       help='Force rebuild of existing training data')
    parser.add_argument('--validate', action='store_true',
                       help='Validate training data after building')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(log_level=args.log_level, log_file='build_training_data')
    
    # Run training data builder
    builder = TrainingDataBuilder()
    try:
        records = builder.build_training_data(
            start_date=args.start_date,
            end_date=args.end_date,
            force_rebuild=args.force_rebuild
        )
        logger.info(f"Training data build complete. Total records: {records}")
        
        # Validate if requested
        if args.validate:
            logger.info("Validating training data...")
            validation = builder.validate_training_data()
            
            logger.info(f"Total records: {validation['total_records']}")
            logger.info(f"NULL targets: {validation['null_targets']}")
            
            if 'date_alignment' in validation:
                logger.info(f"Date alignment: {validation['date_alignment']}")
            
            if 'feature_completeness' in validation:
                logger.info(f"Feature completeness: {validation['feature_completeness']}")
            
            if 'target_statistics' in validation:
                stats = validation['target_statistics']
                logger.info(f"Target PnL statistics:")
                logger.info(f"  - Mean: ${stats['mean_pnl']:.2f}")
                logger.info(f"  - Std Dev: ${stats['std_pnl']:.2f}")
                logger.info(f"  - Min: ${stats['min_pnl']:.2f}")
                logger.info(f"  - Max: ${stats['max_pnl']:.2f}")
                logger.info(f"  - Median: ${stats['median_pnl']:.2f}")
                logger.info(f"  - Win Rate: {stats['win_rate']:.2f}%")
        
    except Exception as e:
        logger.error(f"Training data build failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()