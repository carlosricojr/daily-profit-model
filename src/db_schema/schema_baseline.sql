-- Prop Trading Model Database Schema
-- This schema defines all tables for the daily profit prediction model
-- as specified in baseline-implementation-roadmap.md

-- Create the dedicated schema for the model
CREATE SCHEMA IF NOT EXISTS prop_trading_model;

-- Set the search path to our schema
SET search_path TO prop_trading_model;

-- ========================================
-- Raw Data Tables (Data Ingestion Layer)
-- ========================================

-- Raw accounts data from /accounts API
CREATE TABLE IF NOT EXISTS raw_accounts_data (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    trader_id VARCHAR(255),
    plan_id VARCHAR(255),
    starting_balance DECIMAL(18, 2),
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    profit_target_pct DECIMAL(5, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_drawdown_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative BOOLEAN,
    breached INTEGER DEFAULT 0,
    is_upgraded INTEGER DEFAULT 0,
    phase VARCHAR(50),
    status VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(account_id, ingestion_timestamp)
);

-- Indexes for raw_accounts_data
CREATE INDEX idx_raw_accounts_account_id ON raw_accounts_data(account_id);
CREATE INDEX idx_raw_accounts_login ON raw_accounts_data(login);
CREATE INDEX idx_raw_accounts_ingestion ON raw_accounts_data(ingestion_timestamp);

-- Raw metrics alltime data from /metrics/alltime API
CREATE TABLE IF NOT EXISTS raw_metrics_alltime (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    net_profit DECIMAL(18, 2),
    gross_profit DECIMAL(18, 2),
    gross_loss DECIMAL(18, 2),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DECIMAL(5, 2),
    profit_factor DECIMAL(10, 2),
    average_win DECIMAL(18, 2),
    average_loss DECIMAL(18, 2),
    average_rrr DECIMAL(10, 2),
    expectancy DECIMAL(18, 2),
    sharpe_ratio DECIMAL(10, 2),
    sortino_ratio DECIMAL(10, 2),
    max_drawdown DECIMAL(18, 2),
    max_drawdown_pct DECIMAL(5, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(account_id, ingestion_timestamp)
);

-- Indexes for raw_metrics_alltime
CREATE INDEX idx_raw_metrics_alltime_account_id ON raw_metrics_alltime(account_id);
CREATE INDEX idx_raw_metrics_alltime_login ON raw_metrics_alltime(login);

-- Raw metrics daily data from /metrics/daily API (SOURCE FOR TARGET VARIABLE)
CREATE TABLE IF NOT EXISTS raw_metrics_daily (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    net_profit DECIMAL(18, 2), -- This is our target variable
    gross_profit DECIMAL(18, 2),
    gross_loss DECIMAL(18, 2),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DECIMAL(5, 2),
    profit_factor DECIMAL(10, 2),
    lots_traded DECIMAL(18, 4),
    volume_traded DECIMAL(18, 2),
    commission DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    balance_start DECIMAL(18, 2),
    balance_end DECIMAL(18, 2),
    equity_start DECIMAL(18, 2),
    equity_end DECIMAL(18, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(account_id, date, ingestion_timestamp)
);

-- Indexes for raw_metrics_daily
CREATE INDEX idx_raw_metrics_daily_account_id ON raw_metrics_daily(account_id);
CREATE INDEX idx_raw_metrics_daily_date ON raw_metrics_daily(date);
CREATE INDEX idx_raw_metrics_daily_account_date ON raw_metrics_daily(account_id, date);

-- Raw metrics hourly data from /metrics/hourly API
CREATE TABLE IF NOT EXISTS raw_metrics_hourly (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    net_profit DECIMAL(18, 2),
    gross_profit DECIMAL(18, 2),
    gross_loss DECIMAL(18, 2),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DECIMAL(5, 2),
    lots_traded DECIMAL(18, 4),
    volume_traded DECIMAL(18, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(account_id, date, hour, ingestion_timestamp)
);

-- Indexes for raw_metrics_hourly
CREATE INDEX idx_raw_metrics_hourly_account_id ON raw_metrics_hourly(account_id);
CREATE INDEX idx_raw_metrics_hourly_date_hour ON raw_metrics_hourly(date, hour);

-- Raw trades closed data from /trades/closed API (81M records - needs careful handling)
CREATE TABLE IF NOT EXISTS raw_trades_closed (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    symbol VARCHAR(50),
    std_symbol VARCHAR(50),
    side VARCHAR(10),
    open_time TIMESTAMP,
    close_time TIMESTAMP,
    trade_date DATE,
    open_price DECIMAL(18, 6),
    close_price DECIMAL(18, 6),
    stop_loss DECIMAL(18, 6),
    take_profit DECIMAL(18, 6),
    lots DECIMAL(18, 4),
    volume_usd DECIMAL(18, 2),
    profit DECIMAL(18, 2),
    commission DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500)
);

-- Indexes for raw_trades_closed (critical for 81M records)
CREATE INDEX idx_raw_trades_closed_account_id ON raw_trades_closed(account_id);
CREATE INDEX idx_raw_trades_closed_trade_date ON raw_trades_closed(trade_date);
CREATE INDEX idx_raw_trades_closed_close_time ON raw_trades_closed(close_time);
CREATE INDEX idx_raw_trades_closed_account_date ON raw_trades_closed(account_id, trade_date);

-- Raw trades open data from /trades/open API
CREATE TABLE IF NOT EXISTS raw_trades_open (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    symbol VARCHAR(50),
    std_symbol VARCHAR(50),
    side VARCHAR(10),
    open_time TIMESTAMP,
    trade_date DATE,
    open_price DECIMAL(18, 6),
    current_price DECIMAL(18, 6),
    stop_loss DECIMAL(18, 6),
    take_profit DECIMAL(18, 6),
    lots DECIMAL(18, 4),
    volume_usd DECIMAL(18, 2),
    unrealized_pnl DECIMAL(18, 2),
    commission DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500)
);

-- Indexes for raw_trades_open
CREATE INDEX idx_raw_trades_open_account_id ON raw_trades_open(account_id);
CREATE INDEX idx_raw_trades_open_trade_date ON raw_trades_open(trade_date);

-- Raw plans data from Plans CSV files
CREATE TABLE IF NOT EXISTS raw_plans_data (
    id SERIAL PRIMARY KEY,
    plan_id VARCHAR(255) NOT NULL,
    plan_name VARCHAR(255),
    plan_type VARCHAR(100),
    starting_balance DECIMAL(18, 2),
    profit_target DECIMAL(18, 2),
    profit_target_pct DECIMAL(5, 2),
    max_drawdown DECIMAL(18, 2),
    max_drawdown_pct DECIMAL(5, 2),
    max_daily_drawdown DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative BOOLEAN,
    min_trading_days INTEGER,
    max_trading_days INTEGER,
    profit_split_pct DECIMAL(5, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plan_id, ingestion_timestamp)
);

-- Raw regimes daily data from Supabase public.regimes_daily
CREATE TABLE IF NOT EXISTS raw_regimes_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    market_news JSONB,
    instruments JSONB,
    country_economic_indicators JSONB,
    news_analysis JSONB,
    summary JSONB,
    vector_daily_regime FLOAT[], -- Array of floats for the regime vector
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, ingestion_timestamp)
);

-- Indexes for raw_regimes_daily
CREATE INDEX idx_raw_regimes_daily_date ON raw_regimes_daily(date);
CREATE INDEX idx_raw_regimes_daily_ingestion ON raw_regimes_daily(ingestion_timestamp);

-- ========================================
-- Staging Tables (Preprocessing Layer)
-- ========================================

-- Staging table for daily account snapshots
CREATE TABLE IF NOT EXISTS stg_accounts_daily_snapshots (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    trader_id VARCHAR(255),
    plan_id VARCHAR(255),
    phase VARCHAR(50),
    status VARCHAR(50),
    starting_balance DECIMAL(18, 2),
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    profit_target_pct DECIMAL(5, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_drawdown_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative BOOLEAN,
    days_since_first_trade INTEGER,
    active_trading_days_count INTEGER,
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_max_drawdown DECIMAL(18, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, date)
);

-- Indexes for stg_accounts_daily_snapshots
CREATE INDEX idx_stg_accounts_daily_account_id ON stg_accounts_daily_snapshots(account_id);
CREATE INDEX idx_stg_accounts_daily_date ON stg_accounts_daily_snapshots(date);
CREATE INDEX idx_stg_accounts_daily_account_date ON stg_accounts_daily_snapshots(account_id, date);

-- ========================================
-- Feature Store Table
-- ========================================

-- Feature store for account daily features (features for day D to predict D+1)
CREATE TABLE IF NOT EXISTS feature_store_account_daily (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    feature_date DATE NOT NULL, -- Date D (features are for this date)
    
    -- Static Account & Plan Features
    starting_balance DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_drawdown_pct DECIMAL(5, 2),
    profit_target_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative INTEGER,
    
    -- Dynamic Account State Features (as of EOD D)
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    days_since_first_trade INTEGER,
    active_trading_days_count INTEGER,
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_max_drawdown DECIMAL(18, 2),
    open_pnl DECIMAL(18, 2),
    open_positions_volume DECIMAL(18, 2),
    
    -- Historical Performance Features (Rolling Windows)
    -- 1-day window
    rolling_pnl_sum_1d DECIMAL(18, 2),
    rolling_pnl_avg_1d DECIMAL(18, 2),
    rolling_pnl_std_1d DECIMAL(18, 2),
    
    -- 3-day window
    rolling_pnl_sum_3d DECIMAL(18, 2),
    rolling_pnl_avg_3d DECIMAL(18, 2),
    rolling_pnl_std_3d DECIMAL(18, 2),
    rolling_pnl_min_3d DECIMAL(18, 2),
    rolling_pnl_max_3d DECIMAL(18, 2),
    win_rate_3d DECIMAL(5, 2),
    
    -- 5-day window
    rolling_pnl_sum_5d DECIMAL(18, 2),
    rolling_pnl_avg_5d DECIMAL(18, 2),
    rolling_pnl_std_5d DECIMAL(18, 2),
    rolling_pnl_min_5d DECIMAL(18, 2),
    rolling_pnl_max_5d DECIMAL(18, 2),
    win_rate_5d DECIMAL(5, 2),
    profit_factor_5d DECIMAL(10, 2),
    sharpe_ratio_5d DECIMAL(10, 2),
    
    -- 10-day window
    rolling_pnl_sum_10d DECIMAL(18, 2),
    rolling_pnl_avg_10d DECIMAL(18, 2),
    rolling_pnl_std_10d DECIMAL(18, 2),
    rolling_pnl_min_10d DECIMAL(18, 2),
    rolling_pnl_max_10d DECIMAL(18, 2),
    win_rate_10d DECIMAL(5, 2),
    profit_factor_10d DECIMAL(10, 2),
    sharpe_ratio_10d DECIMAL(10, 2),
    
    -- 20-day window
    rolling_pnl_sum_20d DECIMAL(18, 2),
    rolling_pnl_avg_20d DECIMAL(18, 2),
    rolling_pnl_std_20d DECIMAL(18, 2),
    win_rate_20d DECIMAL(5, 2),
    profit_factor_20d DECIMAL(10, 2),
    sharpe_ratio_20d DECIMAL(10, 2),
    
    -- Behavioral Features
    trades_count_5d INTEGER,
    avg_trade_duration_5d DECIMAL(10, 2),
    avg_lots_per_trade_5d DECIMAL(18, 4),
    avg_volume_per_trade_5d DECIMAL(18, 2),
    stop_loss_usage_rate_5d DECIMAL(5, 2),
    take_profit_usage_rate_5d DECIMAL(5, 2),
    buy_sell_ratio_5d DECIMAL(5, 2),
    top_symbol_concentration_5d DECIMAL(5, 2),
    
    -- Market Regime Features (from regimes_daily for day D)
    market_sentiment_score DECIMAL(10, 4),
    market_volatility_regime VARCHAR(50),
    market_liquidity_state VARCHAR(50),
    vix_level DECIMAL(10, 2),
    dxy_level DECIMAL(10, 2),
    sp500_daily_return DECIMAL(10, 4),
    btc_volatility_90d DECIMAL(10, 4),
    fed_funds_rate DECIMAL(10, 4),
    
    -- Date and Time Features
    day_of_week INTEGER,
    week_of_month INTEGER,
    month INTEGER,
    quarter INTEGER,
    day_of_year INTEGER,
    is_month_start BOOLEAN,
    is_month_end BOOLEAN,
    is_quarter_start BOOLEAN,
    is_quarter_end BOOLEAN,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, feature_date)
);

-- Indexes for feature_store_account_daily
CREATE INDEX idx_feature_store_account_id ON feature_store_account_daily(account_id);
CREATE INDEX idx_feature_store_date ON feature_store_account_daily(feature_date);
CREATE INDEX idx_feature_store_account_date ON feature_store_account_daily(account_id, feature_date);

-- ========================================
-- Model Training and Prediction Tables
-- ========================================

-- Model training input table (features from day D, target from day D+1)
CREATE TABLE IF NOT EXISTS model_training_input (
    id SERIAL PRIMARY KEY,
    login VARCHAR(255) NOT NULL,
    prediction_date DATE NOT NULL, -- Date D+1 (date we're predicting for)
    feature_date DATE NOT NULL, -- Date D (date features are from)
    
    -- All features from feature_store_account_daily
    -- (These are duplicated here for training convenience)
    starting_balance DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_drawdown_pct DECIMAL(5, 2),
    profit_target_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative INTEGER,
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    days_since_first_trade INTEGER,
    active_trading_days_count INTEGER,
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_max_drawdown DECIMAL(18, 2),
    open_pnl DECIMAL(18, 2),
    open_positions_volume DECIMAL(18, 2),
    rolling_pnl_sum_1d DECIMAL(18, 2),
    rolling_pnl_avg_1d DECIMAL(18, 2),
    rolling_pnl_std_1d DECIMAL(18, 2),
    rolling_pnl_sum_3d DECIMAL(18, 2),
    rolling_pnl_avg_3d DECIMAL(18, 2),
    rolling_pnl_std_3d DECIMAL(18, 2),
    rolling_pnl_min_3d DECIMAL(18, 2),
    rolling_pnl_max_3d DECIMAL(18, 2),
    win_rate_3d DECIMAL(5, 2),
    rolling_pnl_sum_5d DECIMAL(18, 2),
    rolling_pnl_avg_5d DECIMAL(18, 2),
    rolling_pnl_std_5d DECIMAL(18, 2),
    rolling_pnl_min_5d DECIMAL(18, 2),
    rolling_pnl_max_5d DECIMAL(18, 2),
    win_rate_5d DECIMAL(5, 2),
    profit_factor_5d DECIMAL(10, 2),
    sharpe_ratio_5d DECIMAL(10, 2),
    rolling_pnl_sum_10d DECIMAL(18, 2),
    rolling_pnl_avg_10d DECIMAL(18, 2),
    rolling_pnl_std_10d DECIMAL(18, 2),
    rolling_pnl_min_10d DECIMAL(18, 2),
    rolling_pnl_max_10d DECIMAL(18, 2),
    win_rate_10d DECIMAL(5, 2),
    profit_factor_10d DECIMAL(10, 2),
    sharpe_ratio_10d DECIMAL(10, 2),
    rolling_pnl_sum_20d DECIMAL(18, 2),
    rolling_pnl_avg_20d DECIMAL(18, 2),
    rolling_pnl_std_20d DECIMAL(18, 2),
    win_rate_20d DECIMAL(5, 2),
    profit_factor_20d DECIMAL(10, 2),
    sharpe_ratio_20d DECIMAL(10, 2),
    trades_count_5d INTEGER,
    avg_trade_duration_5d DECIMAL(10, 2),
    avg_lots_per_trade_5d DECIMAL(18, 4),
    avg_volume_per_trade_5d DECIMAL(18, 2),
    stop_loss_usage_rate_5d DECIMAL(5, 2),
    take_profit_usage_rate_5d DECIMAL(5, 2),
    buy_sell_ratio_5d DECIMAL(5, 2),
    top_symbol_concentration_5d DECIMAL(5, 2),
    market_sentiment_score DECIMAL(10, 4),
    market_volatility_regime VARCHAR(50),
    market_liquidity_state VARCHAR(50),
    vix_level DECIMAL(10, 2),
    dxy_level DECIMAL(10, 2),
    sp500_daily_return DECIMAL(10, 4),
    btc_volatility_90d DECIMAL(10, 4),
    fed_funds_rate DECIMAL(10, 4),
    day_of_week INTEGER,
    week_of_month INTEGER,
    month INTEGER,
    quarter INTEGER,
    day_of_year INTEGER,
    is_month_start BOOLEAN,
    is_month_end BOOLEAN,
    is_quarter_start BOOLEAN,
    is_quarter_end BOOLEAN,
    
    -- Target variable (from raw_metrics_daily for prediction_date)
    target_net_profit DECIMAL(18, 2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(login, prediction_date)
);

-- Indexes for model_training_input
CREATE INDEX idx_model_training_login ON model_training_input(login);
CREATE INDEX idx_model_training_prediction_date ON model_training_input(prediction_date);
CREATE INDEX idx_model_training_feature_date ON model_training_input(feature_date);

-- Model predictions table
CREATE TABLE IF NOT EXISTS model_predictions (
    id SERIAL PRIMARY KEY,
    login VARCHAR(255) NOT NULL,
    prediction_date DATE NOT NULL, -- Date D+1 (date we're predicting for)
    feature_date DATE NOT NULL, -- Date D (date features are from)
    predicted_net_profit DECIMAL(18, 2),
    prediction_confidence DECIMAL(5, 2),
    model_version VARCHAR(50),
    
    -- SHAP values for top features (store as JSONB for flexibility)
    shap_values JSONB,
    top_positive_features JSONB,
    top_negative_features JSONB,
    
    -- Actual outcome (filled in later for evaluation)
    actual_net_profit DECIMAL(18, 2),
    prediction_error DECIMAL(18, 2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(login, prediction_date, model_version)
);

-- Indexes for model_predictions
CREATE INDEX idx_model_predictions_login ON model_predictions(login);
CREATE INDEX idx_model_predictions_date ON model_predictions(prediction_date);
CREATE INDEX idx_model_predictions_login_date ON model_predictions(login, prediction_date);

-- ========================================
-- Model Metadata and Versioning
-- ========================================

-- Model registry table
CREATE TABLE IF NOT EXISTS model_registry (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(50) NOT NULL UNIQUE,
    model_type VARCHAR(50) DEFAULT 'LightGBM',
    training_start_date DATE,
    training_end_date DATE,
    validation_start_date DATE,
    validation_end_date DATE,
    test_start_date DATE,
    test_end_date DATE,
    
    -- Model performance metrics
    train_mae DECIMAL(18, 4),
    train_rmse DECIMAL(18, 4),
    train_r2 DECIMAL(5, 4),
    val_mae DECIMAL(18, 4),
    val_rmse DECIMAL(18, 4),
    val_r2 DECIMAL(5, 4),
    test_mae DECIMAL(18, 4),
    test_rmse DECIMAL(18, 4),
    test_r2 DECIMAL(5, 4),
    
    -- Model parameters (stored as JSONB)
    hyperparameters JSONB,
    feature_list JSONB,
    feature_importance JSONB,
    
    -- Model artifacts location
    model_file_path VARCHAR(500),
    scaler_file_path VARCHAR(500),
    
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create update trigger for model_registry
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_model_registry_updated_at BEFORE UPDATE
    ON model_registry FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========================================
-- Audit and Logging Tables
-- ========================================

-- Pipeline execution log
CREATE TABLE IF NOT EXISTS pipeline_execution_log (
    id SERIAL PRIMARY KEY,
    pipeline_stage VARCHAR(100) NOT NULL,
    execution_date DATE NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(50) NOT NULL, -- 'running', 'success', 'failed'
    records_processed INTEGER,
    error_message TEXT,
    execution_details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for pipeline_execution_log
CREATE INDEX idx_pipeline_log_stage ON pipeline_execution_log(pipeline_stage);
CREATE INDEX idx_pipeline_log_date ON pipeline_execution_log(execution_date);
CREATE INDEX idx_pipeline_log_status ON pipeline_execution_log(status);

-- ========================================
-- Grant permissions (adjust as needed)
-- ========================================

-- Example: Grant usage on schema to application user
-- GRANT USAGE ON SCHEMA prop_trading_model TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA prop_trading_model TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA prop_trading_model TO your_app_user;