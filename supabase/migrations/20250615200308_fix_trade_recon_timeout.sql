-- Fix for trade reconciliation timeout issue
-- This creates an index to speed up the account_id resolution JOIN operation

-- Create index on raw_metrics_alltime for efficient lookups
CREATE INDEX IF NOT EXISTS idx_raw_metrics_alltime_lookup 
ON prop_trading_model.raw_metrics_alltime (login, platform, broker, account_id);

-- Also create index on trades tables for the resolution process
CREATE INDEX IF NOT EXISTS idx_raw_trades_closed_resolution 
ON prop_trading_model.raw_trades_closed (login, platform, broker) 
WHERE account_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_raw_trades_open_resolution 
ON prop_trading_model.raw_trades_open (login, platform, broker) 
WHERE account_id IS NULL;

-- Analyze tables to update statistics
ANALYZE prop_trading_model.raw_metrics_alltime;
ANALYZE prop_trading_model.raw_trades_closed;
ANALYZE prop_trading_model.raw_trades_open;