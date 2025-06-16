-- Migration: Add performance metrics columns to stg_accounts_daily_snapshots
-- This migration adds ~90 new columns for comprehensive performance tracking
-- The table is partitioned by month, so we need to handle the parent and all partitions

-- UP Migration
BEGIN;

-- Add columns to the parent table (will cascade to existing and future partitions)
ALTER TABLE prop_trading_model.stg_accounts_daily_snapshots
-- Risk-adjusted returns (using double precision for Sharpe/Sortino as they're ratios)
ADD COLUMN IF NOT EXISTS daily_sharpe double precision,
ADD COLUMN IF NOT EXISTS daily_sortino double precision,
ADD COLUMN IF NOT EXISTS risk_adj_profit numeric(20,8),
ADD COLUMN IF NOT EXISTS risk_adj_ret numeric(20,8),
ADD COLUMN IF NOT EXISTS downside_risk_adj_ret numeric(20,8),
ADD COLUMN IF NOT EXISTS gain_to_pain numeric(20,8),
ADD COLUMN IF NOT EXISTS profit_factor numeric(20,8),
ADD COLUMN IF NOT EXISTS success_rate numeric(5,4),

-- Profit distribution (monetary values need precision for financial calculations)
ADD COLUMN IF NOT EXISTS profit_perc_10 numeric(20,8),
ADD COLUMN IF NOT EXISTS profit_perc_25 numeric(20,8),
ADD COLUMN IF NOT EXISTS profit_perc_75 numeric(20,8),
ADD COLUMN IF NOT EXISTS profit_perc_90 numeric(20,8),
ADD COLUMN IF NOT EXISTS mean_profit numeric(20,8),
ADD COLUMN IF NOT EXISTS median_profit numeric(20,8),
ADD COLUMN IF NOT EXISTS std_profits numeric(20,8),
ADD COLUMN IF NOT EXISTS min_profit numeric(20,8),
ADD COLUMN IF NOT EXISTS max_profit numeric(20,8),
ADD COLUMN IF NOT EXISTS expectancy numeric(20,8),

-- Drawdown metrics
ADD COLUMN IF NOT EXISTS mean_drawdown numeric(20,8),
ADD COLUMN IF NOT EXISTS median_drawdown numeric(20,8),
ADD COLUMN IF NOT EXISTS max_drawdown_value numeric(20,8), -- renamed to avoid conflict with existing max_drawdown
ADD COLUMN IF NOT EXISTS mean_num_trades_in_dd numeric(10,2),
ADD COLUMN IF NOT EXISTS median_num_trades_in_dd numeric(10,2),
ADD COLUMN IF NOT EXISTS max_num_trades_in_dd integer,

-- Trading behavior
ADD COLUMN IF NOT EXISTS mean_duration numeric(20,8),
ADD COLUMN IF NOT EXISTS median_duration numeric(20,8),
ADD COLUMN IF NOT EXISTS std_durations numeric(20,8),
ADD COLUMN IF NOT EXISTS mean_tp numeric(20,8),
ADD COLUMN IF NOT EXISTS median_tp numeric(20,8),
ADD COLUMN IF NOT EXISTS cv_tp numeric(20,8),
ADD COLUMN IF NOT EXISTS mean_sl numeric(20,8),
ADD COLUMN IF NOT EXISTS median_sl numeric(20,8),
ADD COLUMN IF NOT EXISTS cv_sl numeric(20,8),
ADD COLUMN IF NOT EXISTS mean_tp_vs_sl numeric(20,8),
ADD COLUMN IF NOT EXISTS median_tp_vs_sl numeric(20,8),
ADD COLUMN IF NOT EXISTS cv_tp_vs_sl numeric(20,8),

-- Volume/position metrics
ADD COLUMN IF NOT EXISTS total_lots numeric(20,8),
ADD COLUMN IF NOT EXISTS total_volume numeric(20,8),
ADD COLUMN IF NOT EXISTS std_volumes numeric(20,8),
ADD COLUMN IF NOT EXISTS mean_num_open_pos numeric(10,2),
ADD COLUMN IF NOT EXISTS max_num_open_pos integer,
ADD COLUMN IF NOT EXISTS mean_val_open_pos numeric(20,8),
ADD COLUMN IF NOT EXISTS max_val_open_pos numeric(20,8),
ADD COLUMN IF NOT EXISTS max_val_to_eqty_open_pos numeric(10,6),

-- Streak analysis
ADD COLUMN IF NOT EXISTS mean_num_consec_wins numeric(10,2),
ADD COLUMN IF NOT EXISTS max_num_consec_wins integer,
ADD COLUMN IF NOT EXISTS mean_num_consec_losses numeric(10,2),
ADD COLUMN IF NOT EXISTS max_num_consec_losses integer,
ADD COLUMN IF NOT EXISTS max_val_consec_wins numeric(20,8),
ADD COLUMN IF NOT EXISTS max_val_consec_losses numeric(20,8),

-- Trade aggregations with defaults for easier queries
ADD COLUMN IF NOT EXISTS trades_last_1d integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS trades_last_7d integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS trades_last_30d integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS volume_usd_last_1d numeric(20,8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS volume_usd_last_7d numeric(20,8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS volume_usd_last_30d numeric(20,8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS profit_last_1d numeric(20,8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS profit_last_7d numeric(20,8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS profit_last_30d numeric(20,8) DEFAULT 0,
ADD COLUMN IF NOT EXISTS unique_symbols_last_7d integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS unique_symbols_last_30d integer DEFAULT 0,

-- Trade timing patterns (ratios between 0 and 1)
ADD COLUMN IF NOT EXISTS trades_morning_ratio numeric(5,4),
ADD COLUMN IF NOT EXISTS trades_afternoon_ratio numeric(5,4),
ADD COLUMN IF NOT EXISTS trades_evening_ratio numeric(5,4),
ADD COLUMN IF NOT EXISTS trades_weekend_ratio numeric(5,4),
ADD COLUMN IF NOT EXISTS avg_trade_hour_of_day numeric(4,2),

-- Symbol concentration (ratios between 0 and 1)
ADD COLUMN IF NOT EXISTS top_symbol_concentration numeric(5,4),
ADD COLUMN IF NOT EXISTS symbol_diversification_index numeric(5,4),
ADD COLUMN IF NOT EXISTS forex_pairs_ratio numeric(5,4),  -- EURUSD, GBPUSD, etc
ADD COLUMN IF NOT EXISTS metals_ratio numeric(5,4),       -- XAUUSD, XAGUSD
ADD COLUMN IF NOT EXISTS index_ratio numeric(5,4),        -- NDX100, US30, SPX500, etc
ADD COLUMN IF NOT EXISTS crypto_ratio numeric(5,4),       -- BTCUSD, ETHUSD, SOLUSD, etc
ADD COLUMN IF NOT EXISTS energy_ratio numeric(5,4),       -- USOUSD, UKOUSD, XNGUSD

-- Rolling features
ADD COLUMN IF NOT EXISTS sharpe_ratio_5d numeric(20,8),
ADD COLUMN IF NOT EXISTS sharpe_ratio_10d numeric(20,8),
ADD COLUMN IF NOT EXISTS sharpe_ratio_20d numeric(20,8),
ADD COLUMN IF NOT EXISTS profit_volatility_5d numeric(20,8),
ADD COLUMN IF NOT EXISTS profit_volatility_10d numeric(20,8),
ADD COLUMN IF NOT EXISTS profit_volatility_20d numeric(20,8),
ADD COLUMN IF NOT EXISTS win_rate_5d numeric(5,4),
ADD COLUMN IF NOT EXISTS win_rate_10d numeric(5,4),
ADD COLUMN IF NOT EXISTS win_rate_20d numeric(5,4),
ADD COLUMN IF NOT EXISTS balance_change_5d numeric(20,8),
ADD COLUMN IF NOT EXISTS balance_change_10d numeric(20,8),
ADD COLUMN IF NOT EXISTS balance_change_20d numeric(20,8),
ADD COLUMN IF NOT EXISTS equity_high_water_mark numeric(20,8),
ADD COLUMN IF NOT EXISTS days_since_equity_high integer,

-- Plan progress indicators
ADD COLUMN IF NOT EXISTS progress_to_profit_target numeric(5,4),
ADD COLUMN IF NOT EXISTS distance_from_max_drawdown_pct numeric(5,4),
ADD COLUMN IF NOT EXISTS days_until_evaluation integer,
ADD COLUMN IF NOT EXISTS payout_eligibility_score numeric(5,4),
ADD COLUMN IF NOT EXISTS consistency_score numeric(5,4),
ADD COLUMN IF NOT EXISTS daily_loss_limit_usage numeric(5,4),
ADD COLUMN IF NOT EXISTS total_loss_limit_usage numeric(5,4),
ADD COLUMN IF NOT EXISTS leverage_usage_ratio numeric(5,4),

-- Additional metrics from raw_metrics_daily
ADD COLUMN IF NOT EXISTS mean_account_margin numeric(20,8);

-- Create indexes on the parent table for frequently queried columns
-- These will be inherited by all partitions automatically
CREATE INDEX IF NOT EXISTS idx_snapshots_risk_metrics 
ON prop_trading_model.stg_accounts_daily_snapshots(daily_sharpe, daily_sortino, profit_factor)
WHERE daily_sharpe IS NOT NULL OR daily_sortino IS NOT NULL OR profit_factor IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_snapshots_trading_activity 
ON prop_trading_model.stg_accounts_daily_snapshots(trades_last_7d, volume_usd_last_7d)
WHERE trades_last_7d > 0 OR volume_usd_last_7d > 0;

CREATE INDEX IF NOT EXISTS idx_snapshots_drawdown_metrics
ON prop_trading_model.stg_accounts_daily_snapshots(max_drawdown_value, mean_drawdown)
WHERE max_drawdown_value IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_snapshots_rolling_performance
ON prop_trading_model.stg_accounts_daily_snapshots(sharpe_ratio_20d, win_rate_20d)
WHERE sharpe_ratio_20d IS NOT NULL;

-- Create covering index for common performance queries
CREATE INDEX IF NOT EXISTS idx_snapshots_performance_cover
ON prop_trading_model.stg_accounts_daily_snapshots(
    account_id, 
    snapshot_date DESC, 
    daily_sharpe, 
    profit_factor, 
    trades_last_7d
)
WHERE status = 1; -- Only for active accounts

-- Apply specific indexes to existing partitions for better query performance
-- This ensures optimal performance even if indexes weren't inherited properly
DO $$
DECLARE
    partition_record RECORD;
    index_sql TEXT;
BEGIN
    FOR partition_record IN 
        SELECT 
            schemaname,
            tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename LIKE 'stg_accounts_daily_snapshots_%'
        AND tablename ~ '_\d{4}_\d{2}$' -- Only match YYYY_MM pattern
    LOOP
        -- Create partition-specific index for risk metrics
        index_sql := format(
            'CREATE INDEX IF NOT EXISTS idx_%I_risk_metrics ON %I.%I(daily_sharpe, daily_sortino, profit_factor) WHERE daily_sharpe IS NOT NULL OR daily_sortino IS NOT NULL OR profit_factor IS NOT NULL',
            partition_record.tablename,
            partition_record.schemaname,
            partition_record.tablename
        );
        EXECUTE index_sql;
        
        -- Create partition-specific index for trading activity
        index_sql := format(
            'CREATE INDEX IF NOT EXISTS idx_%I_trading_activity ON %I.%I(trades_last_7d, volume_usd_last_7d) WHERE trades_last_7d > 0 OR volume_usd_last_7d > 0',
            partition_record.tablename,
            partition_record.schemaname,
            partition_record.tablename
        );
        EXECUTE index_sql;
    END LOOP;
END $$;

-- Add comment to document the migration
COMMENT ON TABLE prop_trading_model.stg_accounts_daily_snapshots IS 
'Daily account snapshots with comprehensive performance metrics. Enhanced with ~90 new columns for risk analysis, trading behavior, and performance tracking. Partitioned by month on snapshot_date.';

COMMIT;

-- DOWN Migration (Rollback)
-- To rollback this migration, save this as a separate file or run manually
/*
BEGIN;

-- Drop indexes first
DROP INDEX IF EXISTS prop_trading_model.idx_snapshots_risk_metrics;
DROP INDEX IF EXISTS prop_trading_model.idx_snapshots_trading_activity;
DROP INDEX IF EXISTS prop_trading_model.idx_snapshots_drawdown_metrics;
DROP INDEX IF EXISTS prop_trading_model.idx_snapshots_rolling_performance;
DROP INDEX IF EXISTS prop_trading_model.idx_snapshots_performance_cover;

-- Drop partition-specific indexes
DO $$
DECLARE
    partition_record RECORD;
BEGIN
    FOR partition_record IN 
        SELECT 
            schemaname,
            tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename LIKE 'stg_accounts_daily_snapshots_%'
        AND tablename ~ '_\d{4}_\d{2}$'
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS %I.idx_%I_risk_metrics', 
                       partition_record.schemaname, partition_record.tablename);
        EXECUTE format('DROP INDEX IF EXISTS %I.idx_%I_trading_activity', 
                       partition_record.schemaname, partition_record.tablename);
    END LOOP;
END $$;

-- Drop all the new columns
ALTER TABLE prop_trading_model.stg_accounts_daily_snapshots
DROP COLUMN IF EXISTS daily_sharpe,
DROP COLUMN IF EXISTS daily_sortino,
DROP COLUMN IF EXISTS risk_adj_profit,
DROP COLUMN IF EXISTS risk_adj_ret,
DROP COLUMN IF EXISTS downside_risk_adj_ret,
DROP COLUMN IF EXISTS gain_to_pain,
DROP COLUMN IF EXISTS profit_factor,
DROP COLUMN IF EXISTS success_rate,
DROP COLUMN IF EXISTS profit_perc_10,
DROP COLUMN IF EXISTS profit_perc_25,
DROP COLUMN IF EXISTS profit_perc_75,
DROP COLUMN IF EXISTS profit_perc_90,
DROP COLUMN IF EXISTS mean_profit,
DROP COLUMN IF EXISTS median_profit,
DROP COLUMN IF EXISTS std_profits,
DROP COLUMN IF EXISTS min_profit,
DROP COLUMN IF EXISTS max_profit,
DROP COLUMN IF EXISTS expectancy,
DROP COLUMN IF EXISTS mean_drawdown,
DROP COLUMN IF EXISTS median_drawdown,
DROP COLUMN IF EXISTS max_drawdown_value,
DROP COLUMN IF EXISTS mean_num_trades_in_dd,
DROP COLUMN IF EXISTS median_num_trades_in_dd,
DROP COLUMN IF EXISTS max_num_trades_in_dd,
DROP COLUMN IF EXISTS mean_duration,
DROP COLUMN IF EXISTS median_duration,
DROP COLUMN IF EXISTS std_durations,
DROP COLUMN IF EXISTS mean_tp,
DROP COLUMN IF EXISTS median_tp,
DROP COLUMN IF EXISTS cv_tp,
DROP COLUMN IF EXISTS mean_sl,
DROP COLUMN IF EXISTS median_sl,
DROP COLUMN IF EXISTS cv_sl,
DROP COLUMN IF EXISTS mean_tp_vs_sl,
DROP COLUMN IF EXISTS median_tp_vs_sl,
DROP COLUMN IF EXISTS cv_tp_vs_sl,
DROP COLUMN IF EXISTS total_lots,
DROP COLUMN IF EXISTS total_volume,
DROP COLUMN IF EXISTS std_volumes,
DROP COLUMN IF EXISTS mean_num_open_pos,
DROP COLUMN IF EXISTS max_num_open_pos,
DROP COLUMN IF EXISTS mean_val_open_pos,
DROP COLUMN IF EXISTS max_val_open_pos,
DROP COLUMN IF EXISTS max_val_to_eqty_open_pos,
DROP COLUMN IF EXISTS mean_num_consec_wins,
DROP COLUMN IF EXISTS max_num_consec_wins,
DROP COLUMN IF EXISTS mean_num_consec_losses,
DROP COLUMN IF EXISTS max_num_consec_losses,
DROP COLUMN IF EXISTS max_val_consec_wins,
DROP COLUMN IF EXISTS max_val_consec_losses,
DROP COLUMN IF EXISTS trades_last_1d,
DROP COLUMN IF EXISTS trades_last_7d,
DROP COLUMN IF EXISTS trades_last_30d,
DROP COLUMN IF EXISTS volume_usd_last_1d,
DROP COLUMN IF EXISTS volume_usd_last_7d,
DROP COLUMN IF EXISTS volume_usd_last_30d,
DROP COLUMN IF EXISTS profit_last_1d,
DROP COLUMN IF EXISTS profit_last_7d,
DROP COLUMN IF EXISTS profit_last_30d,
DROP COLUMN IF EXISTS unique_symbols_last_7d,
DROP COLUMN IF EXISTS unique_symbols_last_30d,
DROP COLUMN IF EXISTS trades_morning_ratio,
DROP COLUMN IF EXISTS trades_afternoon_ratio,
DROP COLUMN IF EXISTS trades_evening_ratio,
DROP COLUMN IF EXISTS trades_weekend_ratio,
DROP COLUMN IF EXISTS avg_trade_hour_of_day,
DROP COLUMN IF EXISTS top_symbol_concentration,
DROP COLUMN IF EXISTS symbol_diversification_index,
DROP COLUMN IF EXISTS forex_pairs_ratio,
DROP COLUMN IF EXISTS metals_ratio,
DROP COLUMN IF EXISTS index_ratio,
DROP COLUMN IF EXISTS crypto_ratio,
DROP COLUMN IF EXISTS energy_ratio,
DROP COLUMN IF EXISTS sharpe_ratio_5d,
DROP COLUMN IF EXISTS sharpe_ratio_10d,
DROP COLUMN IF EXISTS sharpe_ratio_20d,
DROP COLUMN IF EXISTS profit_volatility_5d,
DROP COLUMN IF EXISTS profit_volatility_10d,
DROP COLUMN IF EXISTS profit_volatility_20d,
DROP COLUMN IF EXISTS win_rate_5d,
DROP COLUMN IF EXISTS win_rate_10d,
DROP COLUMN IF EXISTS win_rate_20d,
DROP COLUMN IF EXISTS balance_change_5d,
DROP COLUMN IF EXISTS balance_change_10d,
DROP COLUMN IF EXISTS balance_change_20d,
DROP COLUMN IF EXISTS equity_high_water_mark,
DROP COLUMN IF EXISTS days_since_equity_high,
DROP COLUMN IF EXISTS progress_to_profit_target,
DROP COLUMN IF EXISTS distance_from_max_drawdown_pct,
DROP COLUMN IF EXISTS days_until_evaluation,
DROP COLUMN IF EXISTS payout_eligibility_score,
DROP COLUMN IF EXISTS consistency_score,
DROP COLUMN IF EXISTS daily_loss_limit_usage,
DROP COLUMN IF EXISTS total_loss_limit_usage,
DROP COLUMN IF EXISTS leverage_usage_ratio,
DROP COLUMN IF EXISTS mean_account_margin;

-- Remove comment
COMMENT ON TABLE prop_trading_model.stg_accounts_daily_snapshots IS NULL;

COMMIT;
*/