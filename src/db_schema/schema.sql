-- Prop Trading Model Database Schema - Unified Version
-- Combines best features from all schema versions:
-- - Complete table definitions from baseline
-- - Partitioning and performance features from advanced version
-- - Comprehensive feature columns for ML pipeline

-- Create the dedicated schema for the model
CREATE SCHEMA IF NOT EXISTS prop_trading_model;

-- Set the search path to our schema
SET search_path TO prop_trading_model;

-- ========================================
-- Enable Required Extensions
-- ========================================

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- For exclusion constraints

-- ========================================
-- Migration Versioning Table (Alembic-style)
-- ========================================

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

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
    starting_balance DECIMAL(18, 2) CHECK (starting_balance >= 0),
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    profit_target_pct DECIMAL(5, 2) CHECK (profit_target_pct >= 0 AND profit_target_pct <= 100),
    max_daily_drawdown_pct DECIMAL(5, 2) CHECK (max_daily_drawdown_pct >= 0 AND max_daily_drawdown_pct <= 100),
    max_drawdown_pct DECIMAL(5, 2) CHECK (max_drawdown_pct >= 0 AND max_drawdown_pct <= 100),
    max_leverage DECIMAL(10, 2) CHECK (max_leverage > 0),
    is_drawdown_relative BOOLEAN DEFAULT FALSE,
    breached INTEGER DEFAULT 0 CHECK (breached IN (0, 1)),
    is_upgraded INTEGER DEFAULT 0 CHECK (is_upgraded IN (0, 1)),
    phase VARCHAR(50) CHECK (phase IN ('Phase 1', 'Phase 2', 'Funded', 'Demo')),
    status VARCHAR(50) CHECK (status IN ('Active', 'Inactive', 'Breached', 'Passed')),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(account_id, ingestion_timestamp)
);

-- Indexes for raw_accounts_data
CREATE INDEX IF NOT EXISTS idx_raw_accounts_account_id ON raw_accounts_data(account_id);
CREATE INDEX IF NOT EXISTS idx_raw_accounts_login ON raw_accounts_data(login);
CREATE INDEX IF NOT EXISTS idx_raw_accounts_trader_id ON raw_accounts_data(trader_id) WHERE trader_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_accounts_plan_id ON raw_accounts_data(plan_id) WHERE plan_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_accounts_ingestion ON raw_accounts_data(ingestion_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_raw_accounts_status ON raw_accounts_data(status) WHERE status = 'Active';
CREATE INDEX IF NOT EXISTS idx_raw_accounts_phase ON raw_accounts_data(phase);
CREATE INDEX IF NOT EXISTS idx_raw_accounts_updated ON raw_accounts_data(updated_at DESC) WHERE updated_at IS NOT NULL;

-- Raw metrics alltime data from /metrics/alltime API
CREATE TABLE IF NOT EXISTS raw_metrics_alltime (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    net_profit DECIMAL(18, 2),
    gross_profit DECIMAL(18, 2) CHECK (gross_profit >= 0),
    gross_loss DECIMAL(18, 2) CHECK (gross_loss <= 0),
    total_trades INTEGER CHECK (total_trades >= 0),
    winning_trades INTEGER CHECK (winning_trades >= 0),
    losing_trades INTEGER CHECK (losing_trades >= 0),
    win_rate DECIMAL(5, 2) CHECK (win_rate >= 0 AND win_rate <= 100),
    profit_factor DECIMAL(10, 2) CHECK (profit_factor >= 0),
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
CREATE INDEX IF NOT EXISTS idx_raw_metrics_alltime_account_id ON raw_metrics_alltime(account_id);
CREATE INDEX IF NOT EXISTS idx_raw_metrics_alltime_login ON raw_metrics_alltime(login);

-- Raw metrics daily - PARTITIONED BY RANGE (date) for performance
CREATE TABLE IF NOT EXISTS raw_metrics_daily (
    id SERIAL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    date DATE NOT NULL,  -- Partition key
    net_profit DECIMAL(18, 2), -- This is our target variable
    gross_profit DECIMAL(18, 2) CHECK (gross_profit >= 0),
    gross_loss DECIMAL(18, 2) CHECK (gross_loss <= 0),
    total_trades INTEGER CHECK (total_trades >= 0),
    winning_trades INTEGER CHECK (winning_trades >= 0),
    losing_trades INTEGER CHECK (losing_trades >= 0),
    win_rate DECIMAL(5, 2) CHECK (win_rate >= 0 AND win_rate <= 100),
    profit_factor DECIMAL(10, 2) CHECK (profit_factor >= 0),
    lots_traded DECIMAL(18, 4) CHECK (lots_traded >= 0),
    volume_traded DECIMAL(18, 2) CHECK (volume_traded >= 0),
    commission DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    balance_start DECIMAL(18, 2),
    balance_end DECIMAL(18, 2),
    equity_start DECIMAL(18, 2),
    equity_end DECIMAL(18, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    CONSTRAINT chk_daily_trades_consistency CHECK (total_trades = winning_trades + losing_trades),
    PRIMARY KEY (id, date),
    UNIQUE(account_id, date, ingestion_timestamp)
) PARTITION BY RANGE (date);

-- Create yearly partitions for metrics
DO $$
DECLARE
    year INTEGER;
BEGIN
    FOR year IN 2022..2026 LOOP
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS raw_metrics_daily_%s PARTITION OF raw_metrics_daily
            FOR VALUES FROM (%L) TO (%L)',
            year,
            year || '-01-01',
            (year + 1) || '-01-01'
        );
        
        -- Create indexes on each partition
        EXECUTE format('
            CREATE INDEX IF NOT EXISTS idx_raw_metrics_daily_%s_account_id ON raw_metrics_daily_%s (account_id);
            CREATE INDEX IF NOT EXISTS idx_raw_metrics_daily_%s_date ON raw_metrics_daily_%s (date DESC);
            CREATE INDEX IF NOT EXISTS idx_raw_metrics_daily_%s_account_date ON raw_metrics_daily_%s (account_id, date DESC);',
            year, year,
            year, year,
            year, year
        );
    END LOOP;
END $$;

-- Raw metrics hourly data from /metrics/hourly API
CREATE TABLE IF NOT EXISTS raw_metrics_hourly (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
    net_profit DECIMAL(18, 2),
    gross_profit DECIMAL(18, 2) CHECK (gross_profit >= 0),
    gross_loss DECIMAL(18, 2) CHECK (gross_loss <= 0),
    total_trades INTEGER CHECK (total_trades >= 0),
    winning_trades INTEGER CHECK (winning_trades >= 0),
    losing_trades INTEGER CHECK (losing_trades >= 0),
    win_rate DECIMAL(5, 2) CHECK (win_rate >= 0 AND win_rate <= 100),
    lots_traded DECIMAL(18, 4) CHECK (lots_traded >= 0),
    volume_traded DECIMAL(18, 2) CHECK (volume_traded >= 0),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(account_id, date, hour, ingestion_timestamp)
);

-- Indexes for raw_metrics_hourly
CREATE INDEX IF NOT EXISTS idx_raw_metrics_hourly_account_id ON raw_metrics_hourly(account_id);
CREATE INDEX IF NOT EXISTS idx_raw_metrics_hourly_date_hour ON raw_metrics_hourly(date, hour);

-- Raw trades closed - PARTITIONED BY RANGE (trade_date) for 81M records
CREATE TABLE IF NOT EXISTS raw_trades_closed (
    id BIGSERIAL,
    trade_id VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    symbol VARCHAR(50),
    std_symbol VARCHAR(50),
    side VARCHAR(10) CHECK (side IN ('buy', 'sell', 'BUY', 'SELL')),
    open_time TIMESTAMP,
    close_time TIMESTAMP,
    trade_date DATE NOT NULL,  -- Partition key
    open_price DECIMAL(18, 6) CHECK (open_price > 0),
    close_price DECIMAL(18, 6) CHECK (close_price > 0),
    stop_loss DECIMAL(18, 6),
    take_profit DECIMAL(18, 6),
    lots DECIMAL(18, 4) CHECK (lots > 0),
    volume_usd DECIMAL(18, 2) CHECK (volume_usd >= 0),
    profit DECIMAL(18, 2),
    commission DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    CONSTRAINT chk_close_after_open CHECK (close_time >= open_time),
    PRIMARY KEY (id, trade_date)  -- Include partition key in PK
) PARTITION BY RANGE (trade_date);

-- Create monthly partitions for trades
DO $$
DECLARE
    start_date DATE := '2023-01-01';
    end_date DATE := CURRENT_DATE + INTERVAL '3 months';
    partition_date DATE;
    partition_name TEXT;
BEGIN
    partition_date := start_date;
    
    WHILE partition_date < end_date LOOP
        partition_name := 'raw_trades_closed_' || to_char(partition_date, 'YYYY_MM');
        
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I PARTITION OF raw_trades_closed
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + INTERVAL '1 month'
        );
        
        -- Create indexes on each partition
        EXECUTE format('
            CREATE INDEX IF NOT EXISTS %I ON %I (account_id);
            CREATE INDEX IF NOT EXISTS %I ON %I (trade_date);
            CREATE INDEX IF NOT EXISTS %I ON %I (account_id, trade_date);
            CREATE INDEX IF NOT EXISTS %I ON %I (std_symbol) WHERE std_symbol IS NOT NULL;
            CREATE INDEX IF NOT EXISTS %I ON %I (profit) WHERE profit != 0;',
            'idx_' || partition_name || '_account_id', partition_name,
            'idx_' || partition_name || '_trade_date', partition_name,
            'idx_' || partition_name || '_account_date', partition_name,
            'idx_' || partition_name || '_symbol', partition_name,
            'idx_' || partition_name || '_profit', partition_name
        );
        
        partition_date := partition_date + INTERVAL '1 month';
    END LOOP;
END $$;

-- Raw trades open data from /trades/open API
CREATE TABLE IF NOT EXISTS raw_trades_open (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    symbol VARCHAR(50),
    std_symbol VARCHAR(50),
    side VARCHAR(10) CHECK (side IN ('buy', 'sell', 'BUY', 'SELL')),
    open_time TIMESTAMP,
    trade_date DATE,
    open_price DECIMAL(18, 6) CHECK (open_price > 0),
    current_price DECIMAL(18, 6) CHECK (current_price > 0),
    stop_loss DECIMAL(18, 6),
    take_profit DECIMAL(18, 6),
    lots DECIMAL(18, 4) CHECK (lots > 0),
    volume_usd DECIMAL(18, 2) CHECK (volume_usd >= 0),
    unrealized_pnl DECIMAL(18, 2),
    commission DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500)
);

-- Indexes for raw_trades_open
CREATE INDEX IF NOT EXISTS idx_raw_trades_open_account_id ON raw_trades_open(account_id);
CREATE INDEX IF NOT EXISTS idx_raw_trades_open_trade_date ON raw_trades_open(trade_date);

-- Raw plans data from Plans CSV files
CREATE TABLE IF NOT EXISTS raw_plans_data (
    id SERIAL PRIMARY KEY,
    plan_id VARCHAR(255) NOT NULL UNIQUE,  -- UNIQUE for FK reference
    plan_name VARCHAR(255),
    plan_type VARCHAR(100),
    starting_balance DECIMAL(18, 2) CHECK (starting_balance > 0),
    profit_target DECIMAL(18, 2) CHECK (profit_target >= 0),
    profit_target_pct DECIMAL(5, 2) CHECK (profit_target_pct >= 0),
    max_drawdown DECIMAL(18, 2),
    max_drawdown_pct DECIMAL(5, 2) CHECK (max_drawdown_pct >= 0),
    max_daily_drawdown DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2) CHECK (max_daily_drawdown_pct >= 0),
    max_leverage DECIMAL(10, 2) CHECK (max_leverage > 0),
    is_drawdown_relative BOOLEAN DEFAULT FALSE,
    min_trading_days INTEGER CHECK (min_trading_days >= 0),
    max_trading_days INTEGER,
    profit_split_pct DECIMAL(5, 2) CHECK (profit_split_pct >= 0 AND profit_split_pct <= 100),
    liquidate_friday BOOLEAN DEFAULT FALSE,  -- Whether account can hold over weekend
    inactivity_period INTEGER CHECK (inactivity_period >= 0),  -- Days before breach for inactivity
    daily_drawdown_by_balance_equity BOOLEAN DEFAULT FALSE,  -- How daily drawdown is calculated
    enable_consistency BOOLEAN DEFAULT FALSE,  -- Whether consistency rules apply
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_file VARCHAR(500)
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
CREATE INDEX IF NOT EXISTS idx_raw_regimes_daily_date ON raw_regimes_daily(date);
CREATE INDEX IF NOT EXISTS idx_raw_regimes_daily_ingestion ON raw_regimes_daily(ingestion_timestamp);

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
CREATE INDEX IF NOT EXISTS idx_stg_accounts_daily_account_id ON stg_accounts_daily_snapshots(account_id);
CREATE INDEX IF NOT EXISTS idx_stg_accounts_daily_date ON stg_accounts_daily_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_stg_accounts_daily_account_date ON stg_accounts_daily_snapshots(account_id, date);

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
CREATE INDEX IF NOT EXISTS idx_feature_store_account_id ON feature_store_account_daily(account_id);
CREATE INDEX IF NOT EXISTS idx_feature_store_date ON feature_store_account_daily(feature_date);
CREATE INDEX IF NOT EXISTS idx_feature_store_account_date ON feature_store_account_daily(account_id, feature_date);

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
CREATE INDEX IF NOT EXISTS idx_model_training_login ON model_training_input(login);
CREATE INDEX IF NOT EXISTS idx_model_training_prediction_date ON model_training_input(prediction_date);
CREATE INDEX IF NOT EXISTS idx_model_training_feature_date ON model_training_input(feature_date);

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
CREATE INDEX IF NOT EXISTS idx_model_predictions_login ON model_predictions(login);
CREATE INDEX IF NOT EXISTS idx_model_predictions_date ON model_predictions(prediction_date);
CREATE INDEX IF NOT EXISTS idx_model_predictions_login_date ON model_predictions(login, prediction_date);

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

DROP TRIGGER IF EXISTS update_model_registry_updated_at ON model_registry;
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
CREATE INDEX IF NOT EXISTS idx_pipeline_log_stage ON pipeline_execution_log(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_pipeline_log_date ON pipeline_execution_log(execution_date);
CREATE INDEX IF NOT EXISTS idx_pipeline_log_status ON pipeline_execution_log(status);

-- ========================================
-- Performance Monitoring Tables
-- ========================================

CREATE TABLE IF NOT EXISTS query_performance_log (
    id SERIAL PRIMARY KEY,
    query_fingerprint TEXT,
    query_text TEXT,
    mean_time_ms DECIMAL(10, 2),
    calls BIGINT,
    total_time_ms DECIMAL(10, 2),
    min_time_ms DECIMAL(10, 2),
    max_time_ms DECIMAL(10, 2),
    stddev_time_ms DECIMAL(10, 2),
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_query_performance_fingerprint ON query_performance_log(query_fingerprint);
CREATE INDEX IF NOT EXISTS idx_query_performance_logged_at ON query_performance_log(logged_at DESC);

-- ========================================
-- Scheduled Jobs Setup (using pg_cron or similar)
-- ========================================

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    job_id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL UNIQUE,
    schedule VARCHAR(100) NOT NULL,  -- cron expression
    command TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert maintenance job definitions
INSERT INTO scheduled_jobs (job_name, schedule, command) VALUES
    ('create_partitions', '0 0 25 * *', 'SELECT prop_trading_model.create_monthly_partitions();'),
    ('refresh_mv_hourly', '0 * * * *', 'SELECT prop_trading_model.refresh_materialized_views();'),
    ('update_statistics', '0 2 * * *', 'SELECT prop_trading_model.update_table_statistics();'),
    ('vacuum_analyze', '0 3 * * 0', 'SELECT prop_trading_model.vacuum_tables();')
ON CONFLICT (job_name) DO NOTHING;

-- ========================================
-- Materialized Views for Common Aggregations
-- ========================================

-- Account performance summary (refreshed daily)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_account_performance_summary AS
SELECT 
    a.account_id,
    a.login,
    a.trader_id,
    a.plan_id,
    a.phase,
    a.status,
    a.starting_balance,
    a.current_balance,
    a.current_equity,
    p.plan_name,
    p.profit_target_pct,
    p.max_drawdown_pct,
    COALESCE(m.total_trades, 0) as lifetime_trades,
    COALESCE(m.net_profit, 0) as lifetime_profit,
    COALESCE(m.win_rate, 0) as lifetime_win_rate,
    COALESCE(m.profit_factor, 0) as lifetime_profit_factor,
    COALESCE(m.sharpe_ratio, 0) as lifetime_sharpe_ratio,
    COALESCE(daily.trades_last_30d, 0) as trades_last_30d,
    COALESCE(daily.profit_last_30d, 0) as profit_last_30d,
    COALESCE(daily.win_rate_last_30d, 0) as win_rate_last_30d,
    a.updated_at as last_updated
FROM (
    SELECT DISTINCT ON (account_id) *
    FROM raw_accounts_data
    ORDER BY account_id, ingestion_timestamp DESC
) a
LEFT JOIN raw_plans_data p ON a.plan_id = p.plan_id
LEFT JOIN (
    SELECT DISTINCT ON (account_id) *
    FROM raw_metrics_alltime
    ORDER BY account_id, ingestion_timestamp DESC
) m ON a.account_id = m.account_id
LEFT JOIN LATERAL (
    SELECT 
        account_id,
        SUM(total_trades) as trades_last_30d,
        SUM(net_profit) as profit_last_30d,
        CASE 
            WHEN SUM(total_trades) > 0 
            THEN SUM(winning_trades)::DECIMAL / SUM(total_trades) * 100
            ELSE 0 
        END as win_rate_last_30d
    FROM raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY account_id
) daily ON true
WITH DATA;

-- Create indexes on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_account_performance_account_id ON mv_account_performance_summary(account_id);
CREATE INDEX IF NOT EXISTS idx_mv_account_performance_status ON mv_account_performance_summary(status);
CREATE INDEX IF NOT EXISTS idx_mv_account_performance_profit ON mv_account_performance_summary(lifetime_profit DESC);

-- Daily trading statistics (refreshed hourly)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_trading_stats AS
SELECT 
    date,
    COUNT(DISTINCT account_id) as active_accounts,
    SUM(total_trades) as total_trades,
    SUM(net_profit) as total_profit,
    AVG(net_profit) as avg_profit,
    STDDEV(net_profit) as profit_stddev,
    SUM(volume_traded) as total_volume,
    AVG(win_rate) as avg_win_rate,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY net_profit) as median_profit,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY net_profit) as profit_q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY net_profit) as profit_q3
FROM raw_metrics_daily
WHERE date >= CURRENT_DATE - INTERVAL '365 days'
GROUP BY date
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_stats_date ON mv_daily_trading_stats(date);

-- Symbol performance aggregation (refreshed daily)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_symbol_performance AS
SELECT 
    std_symbol,
    COUNT(DISTINCT account_id) as traders_count,
    COUNT(*) as total_trades,
    SUM(profit) as total_profit,
    AVG(profit) as avg_profit,
    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) * 100 as win_rate,
    SUM(volume_usd) as total_volume,
    STDDEV(profit) as profit_stddev,
    MAX(profit) as max_profit,
    MIN(profit) as min_profit
FROM raw_trades_closed
WHERE trade_date >= CURRENT_DATE - INTERVAL '90 days'
    AND std_symbol IS NOT NULL
GROUP BY std_symbol
HAVING COUNT(*) > 100  -- Only symbols with significant activity
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_symbol_performance_symbol ON mv_symbol_performance(std_symbol);
CREATE INDEX IF NOT EXISTS idx_mv_symbol_performance_profit ON mv_symbol_performance(total_profit DESC);

-- ========================================
-- Foreign Key Constraints with Cascading
-- ========================================

-- Add foreign keys with appropriate cascading rules
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_accounts_plan_id' 
        AND table_schema = 'prop_trading_model'
        AND table_name = 'raw_accounts_data'
    ) THEN
        ALTER TABLE raw_accounts_data 
            ADD CONSTRAINT fk_accounts_plan_id 
            FOREIGN KEY (plan_id) 
            REFERENCES raw_plans_data(plan_id) 
            ON DELETE SET NULL 
            ON UPDATE CASCADE;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_stg_accounts_plan_id' 
        AND table_schema = 'prop_trading_model'
        AND table_name = 'stg_accounts_daily_snapshots'
    ) THEN
        ALTER TABLE stg_accounts_daily_snapshots 
            ADD CONSTRAINT fk_stg_accounts_plan_id 
            FOREIGN KEY (plan_id) 
            REFERENCES raw_plans_data(plan_id) 
            ON DELETE SET NULL 
            ON UPDATE CASCADE;
    END IF;
END $$;

-- ========================================
-- Automated Maintenance Functions
-- ========================================

-- Function to automatically create new partitions
CREATE OR REPLACE FUNCTION create_monthly_partitions() RETURNS void AS $$
DECLARE
    next_month DATE;
    partition_name TEXT;
BEGIN
    -- Create partition for next month if it doesn't exist
    next_month := DATE_TRUNC('month', CURRENT_DATE + INTERVAL '1 month');
    partition_name := 'raw_trades_closed_' || to_char(next_month, 'YYYY_MM');
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_class 
        WHERE relname = partition_name 
        AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'prop_trading_model')
    ) THEN
        EXECUTE format('
            CREATE TABLE %I PARTITION OF raw_trades_closed
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            next_month,
            next_month + INTERVAL '1 month'
        );
        
        -- Create indexes on new partition
        EXECUTE format('
            CREATE INDEX %I ON %I (account_id);
            CREATE INDEX %I ON %I (trade_date);
            CREATE INDEX %I ON %I (account_id, trade_date);',
            'idx_' || partition_name || '_account_id', partition_name,
            'idx_' || partition_name || '_trade_date', partition_name,
            'idx_' || partition_name || '_account_date', partition_name
        );
        
        RAISE NOTICE 'Created partition: %', partition_name;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to refresh materialized views
CREATE OR REPLACE FUNCTION refresh_materialized_views() RETURNS void AS $$
BEGIN
    -- Refresh views in dependency order
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_trading_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_symbol_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_performance_summary;
    
    -- Log refresh
    INSERT INTO pipeline_execution_log (
        pipeline_stage, 
        execution_date, 
        start_time, 
        end_time, 
        status, 
        execution_details
    ) VALUES (
        'materialized_view_refresh',
        CURRENT_DATE,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        'success',
        jsonb_build_object(
            'views_refreshed', ARRAY['mv_daily_trading_stats', 'mv_symbol_performance', 'mv_account_performance_summary']
        )
    );
END;
$$ LANGUAGE plpgsql;

-- Function to analyze partition statistics
CREATE OR REPLACE FUNCTION analyze_partitions() RETURNS TABLE(
    table_name TEXT,
    partition_name TEXT,
    size_pretty TEXT,
    row_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        parent.relname::TEXT as table_name,
        child.relname::TEXT as partition_name,
        pg_size_pretty(pg_relation_size(child.oid)) as size_pretty,
        child.reltuples::BIGINT as row_count
    FROM pg_inherits
    JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
    JOIN pg_class child ON pg_inherits.inhrelid = child.oid
    WHERE parent.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'prop_trading_model')
    ORDER BY parent.relname, child.relname;
END;
$$ LANGUAGE plpgsql;

-- Function to update table statistics for all tables in the schema
CREATE OR REPLACE FUNCTION update_table_statistics() RETURNS void AS $$
DECLARE
    table_rec RECORD;
    start_time TIMESTAMP;
    total_tables INTEGER := 0;
    successful_tables INTEGER := 0;
BEGIN
    start_time := CURRENT_TIMESTAMP;
    
    -- Analyze all tables in the prop_trading_model schema
    FOR table_rec IN 
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model'
        ORDER BY tablename
    LOOP
        total_tables := total_tables + 1;
        
        BEGIN
            EXECUTE format('ANALYZE prop_trading_model.%I;', table_rec.tablename);
            successful_tables := successful_tables + 1;
            RAISE NOTICE 'Analyzed table: %', table_rec.tablename;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE WARNING 'Failed to analyze table %: %', table_rec.tablename, SQLERRM;
        END;
    END LOOP;
    
    -- Log the operation
    INSERT INTO pipeline_execution_log (
        pipeline_stage, 
        execution_date, 
        start_time, 
        end_time, 
        status, 
        records_processed,
        execution_details
    ) VALUES (
        'update_table_statistics',
        CURRENT_DATE,
        start_time,
        CURRENT_TIMESTAMP,
        CASE WHEN successful_tables = total_tables THEN 'success' ELSE 'partial_success' END,
        successful_tables,
        jsonb_build_object(
            'total_tables', total_tables,
            'successful_tables', successful_tables,
            'duration_seconds', EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time))
        )
    );
    
    RAISE NOTICE 'Statistics update complete: %/% tables analyzed', successful_tables, total_tables;
END;
$$ LANGUAGE plpgsql;

-- Function to vacuum all tables in the schema with intelligent scheduling
CREATE OR REPLACE FUNCTION vacuum_tables() RETURNS void AS $$
DECLARE
    table_rec RECORD;
    partition_rec RECORD;
    start_time TIMESTAMP;
    total_operations INTEGER := 0;
    successful_operations INTEGER := 0;
    operation_type TEXT;
BEGIN
    start_time := CURRENT_TIMESTAMP;
    
    -- Vacuum all regular tables in the prop_trading_model schema
    FOR table_rec IN 
        SELECT 
            tablename,
            CASE 
                WHEN tablename LIKE 'raw_%' THEN 'VACUUM ANALYZE'
                WHEN tablename LIKE 'mv_%' THEN 'VACUUM'  -- Materialized views
                ELSE 'VACUUM ANALYZE'
            END as vacuum_command
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model'
        ORDER BY 
            CASE 
                WHEN tablename IN ('raw_trades_closed', 'raw_metrics_daily') THEN 1  -- Partitioned tables first
                WHEN tablename LIKE 'raw_%' THEN 2  -- Raw tables
                WHEN tablename LIKE 'stg_%' THEN 3  -- Staging tables
                WHEN tablename LIKE 'feature_%' THEN 4  -- Feature tables
                WHEN tablename LIKE 'model_%' THEN 5  -- Model tables
                ELSE 6  -- Everything else
            END,
            tablename
    LOOP
        total_operations := total_operations + 1;
        
        BEGIN
            -- Skip partitioned parent tables (they don't store data directly)
            IF table_rec.tablename IN ('raw_trades_closed', 'raw_metrics_daily') THEN
                RAISE NOTICE 'Skipping partitioned parent table: %', table_rec.tablename;
                successful_operations := successful_operations + 1;
                CONTINUE;
            END IF;
            
            EXECUTE format('%s prop_trading_model.%I;', table_rec.vacuum_command, table_rec.tablename);
            successful_operations := successful_operations + 1;
            RAISE NOTICE 'Vacuumed table: % (% command)', table_rec.tablename, table_rec.vacuum_command;
            
        EXCEPTION
            WHEN OTHERS THEN
                RAISE WARNING 'Failed to vacuum table %: %', table_rec.tablename, SQLERRM;
        END;
    END LOOP;
    
    -- Vacuum partitions of partitioned tables
    FOR partition_rec IN 
        SELECT 
            child.relname as partition_name,
            parent.relname as parent_table
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        JOIN pg_namespace n ON parent.relnamespace = n.oid
        WHERE n.nspname = 'prop_trading_model'
        ORDER BY parent.relname, child.relname
    LOOP
        total_operations := total_operations + 1;
        
        BEGIN
            EXECUTE format('VACUUM ANALYZE prop_trading_model.%I;', partition_rec.partition_name);
            successful_operations := successful_operations + 1;
            RAISE NOTICE 'Vacuumed partition: % (parent: %)', partition_rec.partition_name, partition_rec.parent_table;
            
        EXCEPTION
            WHEN OTHERS THEN
                RAISE WARNING 'Failed to vacuum partition %: %', partition_rec.partition_name, SQLERRM;
        END;
    END LOOP;
    
    -- Log the operation
    INSERT INTO pipeline_execution_log (
        pipeline_stage, 
        execution_date, 
        start_time, 
        end_time, 
        status, 
        records_processed,
        execution_details
    ) VALUES (
        'vacuum_tables',
        CURRENT_DATE,
        start_time,
        CURRENT_TIMESTAMP,
        CASE WHEN successful_operations = total_operations THEN 'success' ELSE 'partial_success' END,
        successful_operations,
        jsonb_build_object(
            'total_operations', total_operations,
            'successful_operations', successful_operations,
            'duration_seconds', EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time))
        )
    );
    
    RAISE NOTICE 'Vacuum complete: %/% operations successful', successful_operations, total_operations;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Grant permissions (adjust as needed)
-- ========================================

-- Example: Grant usage on schema to application user
-- GRANT USAGE ON SCHEMA prop_trading_model TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA prop_trading_model TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA prop_trading_model TO your_app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA prop_trading_model TO your_app_user;