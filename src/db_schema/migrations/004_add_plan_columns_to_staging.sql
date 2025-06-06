-- Migration: Add new plan columns to staging and feature tables
-- Date: 2025-01-06
-- Description: Adds liquidate_friday, inactivity_period, daily_drawdown_by_balance_equity, enable_consistency columns

-- Add columns to staging table
ALTER TABLE prop_trading_model.stg_accounts_daily_snapshots 
ADD COLUMN IF NOT EXISTS liquidate_friday BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS inactivity_period INTEGER,
ADD COLUMN IF NOT EXISTS daily_drawdown_by_balance_equity BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS enable_consistency BOOLEAN DEFAULT FALSE;

-- Add columns to feature store table
ALTER TABLE prop_trading_model.feature_store_account_daily 
ADD COLUMN IF NOT EXISTS liquidate_friday INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS inactivity_period INTEGER,
ADD COLUMN IF NOT EXISTS daily_drawdown_by_balance_equity INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS enable_consistency INTEGER DEFAULT 0;

-- Add comments for documentation
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.liquidate_friday IS 'Whether account must liquidate positions on Friday';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.inactivity_period IS 'Days allowed without trading before breach';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.daily_drawdown_by_balance_equity IS 'Daily drawdown calculation method';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.enable_consistency IS 'Whether consistency rules apply';

COMMENT ON COLUMN prop_trading_model.feature_store_account_daily.liquidate_friday IS 'Whether account must liquidate positions on Friday (0/1)';
COMMENT ON COLUMN prop_trading_model.feature_store_account_daily.inactivity_period IS 'Days allowed without trading before breach';
COMMENT ON COLUMN prop_trading_model.feature_store_account_daily.daily_drawdown_by_balance_equity IS 'Daily drawdown calculation method (0/1)';
COMMENT ON COLUMN prop_trading_model.feature_store_account_daily.enable_consistency IS 'Whether consistency rules apply (0/1)';