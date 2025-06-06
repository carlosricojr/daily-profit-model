-- Migration: Add new columns to raw_plans_data table
-- Date: 2025-01-06
-- Description: Adds liquidate_friday, inactivity_period, daily_drawdown_by_balance_equity, enable_consistency columns

-- Add new columns to raw_plans_data if they don't exist
ALTER TABLE prop_trading_model.raw_plans_data 
ADD COLUMN IF NOT EXISTS liquidate_friday BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS inactivity_period INTEGER CHECK (inactivity_period >= 0),
ADD COLUMN IF NOT EXISTS daily_drawdown_by_balance_equity BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS enable_consistency BOOLEAN DEFAULT FALSE;

-- Add comments for documentation
COMMENT ON COLUMN prop_trading_model.raw_plans_data.liquidate_friday IS 'Whether account can hold positions over the weekend (TRUE = must liquidate, FALSE = can hold)';
COMMENT ON COLUMN prop_trading_model.raw_plans_data.inactivity_period IS 'Number of days an account can go without placing a trade before breach';
COMMENT ON COLUMN prop_trading_model.raw_plans_data.daily_drawdown_by_balance_equity IS 'How daily drawdown is calculated (TRUE = from previous day balance or equity whichever is higher, FALSE = from previous day balance only)';
COMMENT ON COLUMN prop_trading_model.raw_plans_data.enable_consistency IS 'Whether consistency rules are applied to the account';