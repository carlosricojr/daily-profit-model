-- Migration to fix feature_store_account_daily schema alignment
-- This replaces the simple feature store with one that matches the feature engineering output

-- First, drop the existing table with the wrong schema
DROP TABLE IF EXISTS prop_trading_model.feature_store_account_daily CASCADE;

-- Create the new feature_store_account_daily table with the correct schema
CREATE TABLE prop_trading_model.feature_store_account_daily (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    feature_date DATE NOT NULL,
    feature_version VARCHAR(50),
    
    -- Static features (from stg_accounts_daily_snapshots)
    starting_balance DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(10, 4),
    max_drawdown_pct DECIMAL(10, 4),
    profit_target_pct DECIMAL(10, 4),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative INTEGER DEFAULT 0,
    liquidate_friday INTEGER DEFAULT 0,
    inactivity_period INTEGER,
    daily_drawdown_by_balance_equity INTEGER DEFAULT 0,
    enable_consistency INTEGER DEFAULT 0,
    
    -- Dynamic features (from stg_accounts_daily_snapshots)
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    days_since_first_trade INTEGER DEFAULT 0,
    active_trading_days_count INTEGER DEFAULT 0,
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_max_drawdown DECIMAL(18, 2),
    
    -- Open positions features (from raw_trades_open)
    open_pnl DECIMAL(18, 2) DEFAULT 0,
    open_positions_volume DECIMAL(18, 2) DEFAULT 0,
    
    -- Rolling performance features (1d, 3d, 5d, 10d, 20d windows)
    rolling_pnl_sum_1d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_avg_1d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_std_1d DECIMAL(18, 2) DEFAULT 0,
    
    rolling_pnl_sum_3d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_avg_3d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_std_3d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_min_3d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_max_3d DECIMAL(18, 2) DEFAULT 0,
    win_rate_3d DECIMAL(5, 2) DEFAULT 0,
    
    rolling_pnl_sum_5d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_avg_5d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_std_5d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_min_5d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_max_5d DECIMAL(18, 2) DEFAULT 0,
    win_rate_5d DECIMAL(5, 2) DEFAULT 0,
    profit_factor_5d DECIMAL(10, 4) DEFAULT 0,
    sharpe_ratio_5d DECIMAL(10, 4) DEFAULT 0,
    
    rolling_pnl_sum_10d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_avg_10d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_std_10d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_min_10d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_max_10d DECIMAL(18, 2) DEFAULT 0,
    win_rate_10d DECIMAL(5, 2) DEFAULT 0,
    profit_factor_10d DECIMAL(10, 4) DEFAULT 0,
    sharpe_ratio_10d DECIMAL(10, 4) DEFAULT 0,
    
    rolling_pnl_sum_20d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_avg_20d DECIMAL(18, 2) DEFAULT 0,
    rolling_pnl_std_20d DECIMAL(18, 2) DEFAULT 0,
    win_rate_20d DECIMAL(5, 2) DEFAULT 0,
    profit_factor_20d DECIMAL(10, 4) DEFAULT 0,
    sharpe_ratio_20d DECIMAL(10, 4) DEFAULT 0,
    
    -- Behavioral features (5d window)
    trades_count_5d INTEGER DEFAULT 0,
    avg_trade_duration_5d DECIMAL(10, 2) DEFAULT 0,
    avg_lots_per_trade_5d DECIMAL(10, 4) DEFAULT 0,
    avg_volume_per_trade_5d DECIMAL(18, 2) DEFAULT 0,
    stop_loss_usage_rate_5d DECIMAL(5, 2) DEFAULT 0,
    take_profit_usage_rate_5d DECIMAL(5, 2) DEFAULT 0,
    buy_sell_ratio_5d DECIMAL(10, 4) DEFAULT 0.5,
    top_symbol_concentration_5d DECIMAL(5, 2) DEFAULT 0,
    
    -- Market features
    market_sentiment_score DECIMAL(10, 4) DEFAULT 0,
    market_volatility_regime VARCHAR(50) DEFAULT 'BALANCED',
    market_liquidity_state VARCHAR(50) DEFAULT 'normal',
    vix_level DECIMAL(10, 2) DEFAULT 15.0,
    dxy_level DECIMAL(10, 2) DEFAULT 100.0,
    sp500_daily_return DECIMAL(10, 4) DEFAULT 0,
    btc_volatility_90d DECIMAL(10, 4) DEFAULT 0.5,
    fed_funds_rate DECIMAL(5, 2) DEFAULT 5.0,
    
    -- Time features
    day_of_week INTEGER,
    week_of_month INTEGER,
    month INTEGER,
    quarter INTEGER,
    day_of_year INTEGER,
    is_month_start BOOLEAN DEFAULT FALSE,
    is_month_end BOOLEAN DEFAULT FALSE,
    is_quarter_start BOOLEAN DEFAULT FALSE,
    is_quarter_end BOOLEAN DEFAULT FALSE,
    
    -- System fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(account_id, feature_date)
);

-- Create indexes for performance
CREATE INDEX idx_feature_store_account_date ON prop_trading_model.feature_store_account_daily(account_id, feature_date DESC);
CREATE INDEX idx_feature_store_date ON prop_trading_model.feature_store_account_daily(feature_date DESC);
CREATE INDEX idx_feature_store_login ON prop_trading_model.feature_store_account_daily(login);
CREATE INDEX idx_feature_store_created ON prop_trading_model.feature_store_account_daily(created_at DESC);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION prop_trading_model.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_feature_store_updated_at BEFORE UPDATE
    ON prop_trading_model.feature_store_account_daily
    FOR EACH ROW EXECUTE FUNCTION prop_trading_model.update_updated_at_column();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON prop_trading_model.feature_store_account_daily TO authenticated;
GRANT USAGE ON SEQUENCE prop_trading_model.feature_store_account_daily_id_seq TO authenticated;

COMMENT ON TABLE prop_trading_model.feature_store_account_daily IS 'Stores engineered features for each account on each date, used as input for model training';
COMMENT ON COLUMN prop_trading_model.feature_store_account_daily.feature_version IS 'Version of the feature engineering logic used';
COMMENT ON COLUMN prop_trading_model.feature_store_account_daily.is_drawdown_relative IS '0/1 integer instead of boolean for ML compatibility';