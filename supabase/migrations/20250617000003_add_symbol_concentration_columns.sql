-- Add symbol concentration columns to stg_accounts_daily_snapshots table
-- These columns track trading symbol diversification and asset class exposure

ALTER TABLE prop_trading_model.stg_accounts_daily_snapshots
ADD COLUMN IF NOT EXISTS top_symbol_concentration DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS herfindahl_index DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS symbol_diversification_index DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS forex_pairs_ratio DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS metals_ratio DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS index_ratio DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS crypto_ratio DECIMAL(10,6),
ADD COLUMN IF NOT EXISTS energy_ratio DECIMAL(10,6);

-- Add comments for documentation
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.top_symbol_concentration IS 'Percentage of trades in the most traded symbol (0-1)';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.herfindahl_index IS 'Herfindahl-Hirschman Index for symbol concentration (0=perfect diversification, 1=single symbol)';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.symbol_diversification_index IS 'Normalized entropy-based diversification index (0=single symbol, 1=perfect diversification)';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.forex_pairs_ratio IS 'Percentage of trades in forex currency pairs (0-1)';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.metals_ratio IS 'Percentage of trades in precious metals (0-1)';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.index_ratio IS 'Percentage of trades in stock indices (0-1)';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.crypto_ratio IS 'Percentage of trades in cryptocurrencies (0-1)';
COMMENT ON COLUMN prop_trading_model.stg_accounts_daily_snapshots.energy_ratio IS 'Percentage of trades in energy commodities (0-1)';

-- Create an index on the symbol concentration columns for efficient querying
CREATE INDEX IF NOT EXISTS idx_stg_accounts_daily_snapshots_symbol_metrics 
ON prop_trading_model.stg_accounts_daily_snapshots (
    snapshot_date,
    top_symbol_concentration,
    herfindahl_index,
    symbol_diversification_index
);