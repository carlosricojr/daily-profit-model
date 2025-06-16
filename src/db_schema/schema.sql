-- Daily Profit Model Database Schema - Consolidated Version
-- This is a single, unified schema file for early development stage
-- Includes all tables, indexes, functions, and materialized views
-- No separate migrations needed - drop and recreate for testing

-- ========================================
-- Schema Setup
-- ========================================

-- Drop schema if exists (for clean testing)
DROP SCHEMA IF EXISTS prop_trading_model CASCADE;

-- Create the dedicated schema for the model
CREATE SCHEMA prop_trading_model;

-- Set the search path to our schema
SET search_path TO prop_trading_model;

-- ========================================
-- Enable Required Extensions
-- ========================================

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- For exclusion constraints

-- ========================================
-- Raw Data Tables (Data Ingestion Layer)
-- ========================================

-- Raw metrics alltime data from /metrics/alltime API
CREATE TABLE raw_metrics_alltime (
    login VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL PRIMARY KEY,
    
    -- Account metadata
    plan_id VARCHAR(255),
    trader_id VARCHAR(255),
    status INTEGER CHECK (status IN (1, 2, 3)),
    type INTEGER,
    phase INTEGER CHECK (phase IN (1, 2, 3, 4)),
    broker INTEGER,
    platform INTEGER,
    price_stream INTEGER,
    country VARCHAR(2),
    
    -- Payout tracking
    approved_payouts DECIMAL(18, 2),
    pending_payouts DECIMAL(18, 2),
    
    -- Balance and equity
    starting_balance DECIMAL(18, 2),
    prior_days_balance DECIMAL(18, 2),
    prior_days_equity DECIMAL(18, 2),
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    
    -- Trading timeline
    first_trade_date DATE,
    days_since_initial_deposit INTEGER,
    days_since_first_trade INTEGER,
    num_trades INTEGER CHECK (num_trades >= 0),
    first_trade_open TIMESTAMP,
    last_trade_open TIMESTAMP,
    last_trade_close TIMESTAMP,
    lifetime_in_days DECIMAL(10, 6),
    
    -- Core performance metrics
    net_profit DECIMAL(18, 2),
    gross_profit DECIMAL(18, 2) CHECK (gross_profit >= 0),
    gross_loss DECIMAL(18, 2) CHECK (gross_loss <= 0),
    gain_to_pain DECIMAL(10, 2),
    profit_factor DECIMAL(10, 2) CHECK (profit_factor >= 0),
    success_rate DECIMAL(5, 2) CHECK (success_rate >= 0 AND success_rate <= 100),
    expectancy DECIMAL(18, 2),
    
    -- Enhanced risk metrics (DOUBLE PRECISION for extreme values)
    mean_profit DECIMAL(18, 2),
    median_profit DECIMAL(18, 2),
    std_profits DECIMAL(18, 2),
    risk_adj_profit DOUBLE PRECISION,
    
    -- Profit distribution
    min_profit DECIMAL(18, 2),
    max_profit DECIMAL(18, 2),
    profit_perc_10 DECIMAL(18, 2),
    profit_perc_25 DECIMAL(18, 2),
    profit_perc_75 DECIMAL(18, 2),
    profit_perc_90 DECIMAL(18, 2),
    
    -- Outlier analysis
    profit_top_10_prcnt_trades DECIMAL(18, 2),
    profit_bottom_10_prcnt_trades DECIMAL(18, 2),
    top_10_prcnt_profit_contrib DECIMAL(5, 2),
    bottom_10_prcnt_loss_contrib DECIMAL(5, 2),
    one_std_outlier_profit DECIMAL(18, 2),
    one_std_outlier_profit_contrib DECIMAL(10, 6),
    two_std_outlier_profit DECIMAL(18, 2),
    two_std_outlier_profit_contrib DECIMAL(10, 6),
    
    -- Per-unit profitability (DOUBLE PRECISION for extreme ratios)
    net_profit_per_usd_volume DOUBLE PRECISION,
    gross_profit_per_usd_volume DOUBLE PRECISION,
    gross_loss_per_usd_volume DOUBLE PRECISION,
    distance_gross_profit_loss_per_usd_volume DOUBLE PRECISION,
    multiple_gross_profit_loss_per_usd_volume DOUBLE PRECISION,
    gross_profit_per_lot DECIMAL(18, 6),
    gross_loss_per_lot DECIMAL(18, 6),
    distance_gross_profit_loss_per_lot DECIMAL(18, 6),
    multiple_gross_profit_loss_per_lot DOUBLE PRECISION,
    
    -- Duration-based profitability
    net_profit_per_duration DECIMAL(18, 6),
    gross_profit_per_duration DECIMAL(18, 6),
    gross_loss_per_duration DECIMAL(18, 6),
    
    -- Return metrics (DOUBLE PRECISION for extreme values)
    mean_ret DOUBLE PRECISION,
    std_rets DOUBLE PRECISION,
    risk_adj_ret DOUBLE PRECISION,
    downside_std_rets DOUBLE PRECISION,
    downside_risk_adj_ret DOUBLE PRECISION,
    total_ret DOUBLE PRECISION,
    daily_mean_ret DOUBLE PRECISION,
    daily_std_ret DOUBLE PRECISION,
    daily_sharpe DOUBLE PRECISION,
    daily_downside_std_ret DOUBLE PRECISION,
    daily_sortino DOUBLE PRECISION,
    
    -- Relative metrics
    rel_net_profit DECIMAL(18, 6),
    rel_gross_profit DECIMAL(18, 6),
    rel_gross_loss DECIMAL(18, 6),
    rel_mean_profit DECIMAL(18, 6),
    rel_median_profit DECIMAL(18, 6),
    rel_std_profits DECIMAL(18, 6),
    rel_risk_adj_profit DOUBLE PRECISION,
    rel_min_profit DECIMAL(18, 6),
    rel_max_profit DECIMAL(18, 6),
    rel_profit_perc_10 DECIMAL(18, 6),
    rel_profit_perc_25 DECIMAL(18, 6),
    rel_profit_perc_75 DECIMAL(18, 6),
    rel_profit_perc_90 DECIMAL(18, 6),
    rel_profit_top_10_prcnt_trades DECIMAL(18, 6),
    rel_profit_bottom_10_prcnt_trades DECIMAL(18, 6),
    rel_one_std_outlier_profit DECIMAL(18, 6),
    rel_two_std_outlier_profit DECIMAL(18, 6),
    
    -- Drawdown analysis
    mean_drawdown DECIMAL(18, 2),
    median_drawdown DECIMAL(18, 2),
    max_drawdown DECIMAL(18, 2),
    mean_num_trades_in_dd DECIMAL(18, 2),
    median_num_trades_in_dd DECIMAL(18, 2),
    max_num_trades_in_dd INTEGER,
    rel_mean_drawdown DECIMAL(18, 6),
    rel_median_drawdown DECIMAL(18, 6),
    rel_max_drawdown DECIMAL(18, 6),
    
    -- Volume and lot metrics
    total_lots DECIMAL(18, 6),
    total_volume DECIMAL(18, 2),
    std_volumes DECIMAL(18, 2),
    mean_winning_lot DECIMAL(18, 6),
    mean_losing_lot DECIMAL(18, 6),
    distance_win_loss_lots DECIMAL(18, 6),
    multiple_win_loss_lots DECIMAL(10, 6),
    mean_winning_volume DECIMAL(18, 2),
    mean_losing_volume DECIMAL(18, 2),
    distance_win_loss_volume DECIMAL(18, 2),
    multiple_win_loss_volume DECIMAL(10, 6),
    
    -- Duration metrics
    mean_duration DECIMAL(18, 6),
    median_duration DECIMAL(18, 6),
    std_durations DECIMAL(18, 6),
    min_duration DECIMAL(18, 6),
    max_duration DECIMAL(18, 6),
    cv_durations DECIMAL(10, 6),
    
    -- Stop loss and take profit metrics
    mean_tp DECIMAL(18, 6),
    median_tp DECIMAL(18, 6),
    std_tp DECIMAL(18, 6),
    min_tp DECIMAL(18, 6),
    max_tp DECIMAL(18, 6),
    cv_tp DECIMAL(10, 6),
    mean_sl DECIMAL(18, 6),
    median_sl DECIMAL(18, 6),
    std_sl DECIMAL(18, 6),
    min_sl DECIMAL(18, 6),
    max_sl DECIMAL(18, 6),
    cv_sl DECIMAL(10, 6),
    mean_tp_vs_sl DECIMAL(10, 6),
    median_tp_vs_sl DECIMAL(10, 6),
    min_tp_vs_sl DECIMAL(10, 6),
    max_tp_vs_sl DECIMAL(10, 6),
    cv_tp_vs_sl DECIMAL(10, 6),
    
    -- Consecutive wins/losses
    mean_num_consec_wins DECIMAL(10, 2),
    median_num_consec_wins INTEGER,
    max_num_consec_wins INTEGER,
    mean_num_consec_losses DECIMAL(10, 2),
    median_num_consec_losses INTEGER,
    max_num_consec_losses INTEGER,
    mean_val_consec_wins DECIMAL(18, 2),
    median_val_consec_wins DECIMAL(18, 2),
    max_val_consec_wins DECIMAL(18, 2),
    mean_val_consec_losses DECIMAL(18, 2),
    median_val_consec_losses DECIMAL(18, 2),
    max_val_consec_losses DECIMAL(18, 2),
    
    -- Open position metrics
    mean_num_open_pos DECIMAL(10, 2),
    median_num_open_pos INTEGER,
    max_num_open_pos INTEGER,
    mean_val_open_pos DECIMAL(18, 2),
    median_val_open_pos DECIMAL(18, 2),
    max_val_open_pos DECIMAL(18, 2),
    mean_val_to_eqty_open_pos DECIMAL(10, 6),
    median_val_to_eqty_open_pos DECIMAL(10, 6),
    max_val_to_eqty_open_pos DECIMAL(10, 6),
    
    -- Margin and activity metrics
    mean_account_margin DECIMAL(18, 2),
    mean_firm_margin DECIMAL(18, 2),
    mean_trades_per_day DECIMAL(10, 2),
    median_trades_per_day INTEGER,
    min_trades_per_day INTEGER,
    max_trades_per_day INTEGER,
    cv_trades_per_day DECIMAL(10, 6),
    mean_idle_days DECIMAL(10, 2),
    median_idle_days INTEGER,
    max_idle_days INTEGER,
    min_idle_days INTEGER,
    num_traded_symbols INTEGER,
    most_traded_symbol VARCHAR(50),
    most_traded_smb_trades INTEGER,
    
    -- Other fields
    updated_date TIMESTAMP,
    
    -- System fields
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    
    UNIQUE(account_id)
);

-- Create indexes for performance
CREATE INDEX idx_raw_metrics_alltime_account_id ON raw_metrics_alltime(account_id);
CREATE INDEX idx_raw_metrics_alltime_login ON raw_metrics_alltime(login);
CREATE INDEX idx_raw_metrics_alltime_plan_id ON raw_metrics_alltime(plan_id);
CREATE INDEX idx_raw_metrics_alltime_trader_id ON raw_metrics_alltime(trader_id);
CREATE INDEX idx_raw_metrics_alltime_login_platform_broker ON raw_metrics_alltime(login, platform, broker);

-- Raw metrics daily - PARTITIONED BY RANGE (date) for performance
CREATE TABLE raw_metrics_daily (
    date DATE NOT NULL,
    login VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    
    -- Account metadata
    plan_id VARCHAR(255),
    trader_id VARCHAR(255),
    status INTEGER CHECK (status IN (1, 2, 3)),
    type INTEGER,
    phase INTEGER,
    broker INTEGER,
    platform INTEGER,
    price_stream INTEGER,
    country VARCHAR(2),
    
    -- Payout tracking
    days_to_next_payout INTEGER,
    todays_payouts DECIMAL(18, 2),
    approved_payouts DECIMAL(18, 2),
    pending_payouts DECIMAL(18, 2),
    
    -- Balance and equity
    starting_balance DECIMAL(18, 2),
    prior_days_balance DECIMAL(18, 2),
    prior_days_equity DECIMAL(18, 2),
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    
    -- Trading timeline
    first_trade_date DATE,
    days_since_initial_deposit INTEGER,
    days_since_first_trade INTEGER,
    num_trades INTEGER CHECK (num_trades >= 0),
    
    -- Core performance metrics
    net_profit DECIMAL(18, 2),
    gross_profit DECIMAL(18, 2) CHECK (gross_profit >= 0),
    gross_loss DECIMAL(18, 2) CHECK (gross_loss <= 0),
    gain_to_pain DECIMAL(10, 2),
    profit_factor DECIMAL(10, 2) CHECK (profit_factor >= 0),
    success_rate DECIMAL(5, 2) CHECK (success_rate >= 0 AND success_rate <= 100),
    expectancy DECIMAL(18, 2),
    
    -- Enhanced risk metrics (DOUBLE PRECISION for extreme values)
    mean_profit DECIMAL(18, 2),
    median_profit DECIMAL(18, 2),
    std_profits DECIMAL(18, 2),
    risk_adj_profit DOUBLE PRECISION,
    
    -- Profit distribution
    min_profit DECIMAL(18, 2),
    max_profit DECIMAL(18, 2),
    profit_perc_10 DECIMAL(18, 2),
    profit_perc_25 DECIMAL(18, 2),
    profit_perc_75 DECIMAL(18, 2),
    profit_perc_90 DECIMAL(18, 2),
    
    -- Outlier analysis
    profit_top_10_prcnt_trades DECIMAL(18, 2),
    profit_bottom_10_prcnt_trades DECIMAL(18, 2),
    top_10_prcnt_profit_contrib DECIMAL(5, 2),
    bottom_10_prcnt_loss_contrib DECIMAL(5, 2),
    one_std_outlier_profit DECIMAL(18, 2),
    one_std_outlier_profit_contrib DECIMAL(10, 6),
    two_std_outlier_profit DECIMAL(18, 2),
    two_std_outlier_profit_contrib DECIMAL(10, 6),
    
    -- Per-unit profitability (DOUBLE PRECISION for extreme ratios)
    net_profit_per_usd_volume DOUBLE PRECISION,
    gross_profit_per_usd_volume DOUBLE PRECISION,
    gross_loss_per_usd_volume DOUBLE PRECISION,
    distance_gross_profit_loss_per_usd_volume DOUBLE PRECISION,
    multiple_gross_profit_loss_per_usd_volume DOUBLE PRECISION,
    gross_profit_per_lot DECIMAL(18, 6),
    gross_loss_per_lot DECIMAL(18, 6),
    distance_gross_profit_loss_per_lot DECIMAL(18, 6),
    multiple_gross_profit_loss_per_lot DOUBLE PRECISION,
    
    -- Duration-based profitability
    net_profit_per_duration DECIMAL(18, 6),
    gross_profit_per_duration DECIMAL(18, 6),
    gross_loss_per_duration DECIMAL(18, 6),
    
    -- Return metrics (DOUBLE PRECISION for extreme values)
    mean_ret DOUBLE PRECISION,
    std_rets DOUBLE PRECISION,
    risk_adj_ret DOUBLE PRECISION,
    downside_std_rets DOUBLE PRECISION,
    downside_risk_adj_ret DOUBLE PRECISION,
    total_ret DOUBLE PRECISION,
    daily_mean_ret DOUBLE PRECISION,
    daily_std_ret DOUBLE PRECISION,
    daily_sharpe DOUBLE PRECISION,
    daily_downside_std_ret DOUBLE PRECISION,
    daily_sortino DOUBLE PRECISION,
    
    -- Relative metrics
    rel_net_profit DECIMAL(18, 6),
    rel_gross_profit DECIMAL(18, 6),
    rel_gross_loss DECIMAL(18, 6),
    rel_mean_profit DECIMAL(18, 6),
    rel_median_profit DECIMAL(18, 6),
    rel_std_profits DECIMAL(18, 6),
    rel_risk_adj_profit DOUBLE PRECISION,
    rel_min_profit DECIMAL(18, 6),
    rel_max_profit DECIMAL(18, 6),
    rel_profit_perc_10 DECIMAL(18, 6),
    rel_profit_perc_25 DECIMAL(18, 6),
    rel_profit_perc_75 DECIMAL(18, 6),
    rel_profit_perc_90 DECIMAL(18, 6),
    rel_profit_top_10_prcnt_trades DECIMAL(18, 6),
    rel_profit_bottom_10_prcnt_trades DECIMAL(18, 6),
    rel_one_std_outlier_profit DECIMAL(18, 6),
    rel_two_std_outlier_profit DECIMAL(18, 6),
    
    -- Drawdown analysis
    mean_drawdown DECIMAL(18, 2),
    median_drawdown DECIMAL(18, 2),
    max_drawdown DECIMAL(18, 2),
    mean_num_trades_in_dd DECIMAL(18, 2),
    median_num_trades_in_dd DECIMAL(18, 2),
    max_num_trades_in_dd INTEGER,
    rel_mean_drawdown DECIMAL(18, 6),
    rel_median_drawdown DECIMAL(18, 6),
    rel_max_drawdown DECIMAL(18, 6),
    
    -- Volume and lot metrics
    total_lots DECIMAL(18, 6),
    total_volume DECIMAL(18, 2),
    std_volumes DECIMAL(18, 2),
    mean_winning_lot DECIMAL(18, 6),
    mean_losing_lot DECIMAL(18, 6),
    distance_win_loss_lots DECIMAL(18, 6),
    multiple_win_loss_lots DECIMAL(10, 6),
    mean_winning_volume DECIMAL(18, 2),
    mean_losing_volume DECIMAL(18, 2),
    distance_win_loss_volume DECIMAL(18, 2),
    multiple_win_loss_volume DECIMAL(10, 6),
    
    -- Duration metrics
    mean_duration DECIMAL(18, 6),
    median_duration DECIMAL(18, 6),
    std_durations DECIMAL(18, 6),
    min_duration DECIMAL(18, 6),
    max_duration DECIMAL(18, 6),
    cv_durations DECIMAL(10, 6),
    
    -- Stop loss and take profit metrics
    mean_tp DECIMAL(18, 6),
    median_tp DECIMAL(18, 6),
    std_tp DECIMAL(18, 6),
    min_tp DECIMAL(18, 6),
    max_tp DECIMAL(18, 6),
    cv_tp DECIMAL(10, 6),
    mean_sl DECIMAL(18, 6),
    median_sl DECIMAL(18, 6),
    std_sl DECIMAL(18, 6),
    min_sl DECIMAL(18, 6),
    max_sl DECIMAL(18, 6),
    cv_sl DECIMAL(10, 6),
    mean_tp_vs_sl DECIMAL(10, 6),
    median_tp_vs_sl DECIMAL(10, 6),
    min_tp_vs_sl DECIMAL(10, 6),
    max_tp_vs_sl DECIMAL(10, 6),
    cv_tp_vs_sl DECIMAL(10, 6),
    
    -- Consecutive wins/losses
    mean_num_consec_wins DECIMAL(10, 2),
    median_num_consec_wins INTEGER,
    max_num_consec_wins INTEGER,
    mean_num_consec_losses DECIMAL(10, 2),
    median_num_consec_losses INTEGER,
    max_num_consec_losses INTEGER,
    mean_val_consec_wins DECIMAL(18, 2),
    median_val_consec_wins DECIMAL(18, 2),
    max_val_consec_wins DECIMAL(18, 2),
    mean_val_consec_losses DECIMAL(18, 2),
    median_val_consec_losses DECIMAL(18, 2),
    max_val_consec_losses DECIMAL(18, 2),
    
    -- Open position metrics
    mean_num_open_pos DECIMAL(10, 2),
    median_num_open_pos INTEGER,
    max_num_open_pos INTEGER,
    mean_val_open_pos DECIMAL(18, 2),
    median_val_open_pos DECIMAL(18, 2),
    max_val_open_pos DECIMAL(18, 2),
    mean_val_to_eqty_open_pos DECIMAL(10, 6),
    median_val_to_eqty_open_pos DECIMAL(10, 6),
    max_val_to_eqty_open_pos DECIMAL(10, 6),
    
    -- Margin and activity metrics
    mean_account_margin DECIMAL(18, 2),
    mean_firm_margin DECIMAL(18, 2),
    num_traded_symbols INTEGER,
    most_traded_symbol VARCHAR(50),
    most_traded_smb_trades INTEGER,
    
    -- System fields
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    
    PRIMARY KEY (account_id, date)
) PARTITION BY RANGE (date);

-- Create partitions for raw_metrics_daily (last 3 years + future)
DO $$
DECLARE
    start_date date := '2022-01-01';
    partition_date date;
    partition_name text;
BEGIN
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            CURRENT_DATE + interval '3 months',
            interval '1 month'
        )::date
    LOOP
        partition_name := 'raw_metrics_daily_' || to_char(partition_date, 'YYYY_MM');
        
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I PARTITION OF raw_metrics_daily
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + interval '1 month'
        );
    END LOOP;
END $$;

-- Indexes for raw_metrics_daily
CREATE INDEX idx_raw_metrics_daily_account_date ON raw_metrics_daily(account_id, date DESC);
CREATE INDEX idx_raw_metrics_daily_date ON raw_metrics_daily(date DESC);
CREATE INDEX idx_raw_metrics_daily_login ON raw_metrics_daily(login);
CREATE INDEX idx_raw_metrics_daily_profit ON raw_metrics_daily(date DESC, net_profit DESC) WHERE net_profit IS NOT NULL;

-- Raw metrics hourly - PARTITIONED BY RANGE (date) for performance
CREATE TABLE raw_metrics_hourly (
    date DATE NOT NULL,
    datetime TIMESTAMP NOT NULL,
    hour INTEGER NOT NULL,
    login VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    
    -- Account metadata
    plan_id VARCHAR(255),
    trader_id VARCHAR(255),
    status INTEGER CHECK (status IN (1, 2, 3)),
    type INTEGER,
    phase INTEGER,
    broker INTEGER,
    platform INTEGER,
    price_stream INTEGER,
    country VARCHAR(2),
    
    -- Payout tracking
    days_to_next_payout INTEGER,
    todays_payouts DECIMAL(18, 2),
    approved_payouts DECIMAL(18, 2),
    pending_payouts DECIMAL(18, 2),
    
    -- Balance and equity
    starting_balance DECIMAL(18, 2),
    prior_days_balance DECIMAL(18, 2),
    prior_days_equity DECIMAL(18, 2),
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    
    -- Trading timeline
    first_trade_date DATE,
    days_since_initial_deposit INTEGER,
    days_since_first_trade INTEGER,
    num_trades INTEGER CHECK (num_trades >= 0),
    
    -- Core performance metrics
    net_profit DECIMAL(18, 2),
    gross_profit DECIMAL(18, 2) CHECK (gross_profit >= 0),
    gross_loss DECIMAL(18, 2) CHECK (gross_loss <= 0),
    gain_to_pain DECIMAL(10, 2),
    profit_factor DECIMAL(10, 2) CHECK (profit_factor >= 0),
    success_rate DECIMAL(5, 2) CHECK (success_rate >= 0 AND success_rate <= 100),
    expectancy DECIMAL(18, 2),
    
    -- Enhanced risk metrics (DOUBLE PRECISION for extreme values)
    mean_profit DECIMAL(18, 2),
    median_profit DECIMAL(18, 2),
    std_profits DECIMAL(18, 2),
    risk_adj_profit DOUBLE PRECISION,
    
    -- Profit distribution
    min_profit DECIMAL(18, 2),
    max_profit DECIMAL(18, 2),
    profit_perc_10 DECIMAL(18, 2),
    profit_perc_25 DECIMAL(18, 2),
    profit_perc_75 DECIMAL(18, 2),
    profit_perc_90 DECIMAL(18, 2),
    
    -- Outlier analysis
    profit_top_10_prcnt_trades DECIMAL(18, 2),
    profit_bottom_10_prcnt_trades DECIMAL(18, 2),
    top_10_prcnt_profit_contrib DECIMAL(5, 2),
    bottom_10_prcnt_loss_contrib DECIMAL(5, 2),
    one_std_outlier_profit DECIMAL(18, 2),
    one_std_outlier_profit_contrib DECIMAL(10, 6),
    two_std_outlier_profit DECIMAL(18, 2),
    two_std_outlier_profit_contrib DECIMAL(10, 6),
    
    -- Per-unit profitability (DOUBLE PRECISION for extreme ratios)
    net_profit_per_usd_volume DOUBLE PRECISION,
    gross_profit_per_usd_volume DOUBLE PRECISION,
    gross_loss_per_usd_volume DOUBLE PRECISION,
    distance_gross_profit_loss_per_usd_volume DOUBLE PRECISION,
    multiple_gross_profit_loss_per_usd_volume DOUBLE PRECISION,
    gross_profit_per_lot DECIMAL(18, 6),
    gross_loss_per_lot DECIMAL(18, 6),
    distance_gross_profit_loss_per_lot DECIMAL(18, 6),
    multiple_gross_profit_loss_per_lot DOUBLE PRECISION,
    
    -- Duration-based profitability
    net_profit_per_duration DECIMAL(18, 6),
    gross_profit_per_duration DECIMAL(18, 6),
    gross_loss_per_duration DECIMAL(18, 6),
    
    -- Return metrics (DOUBLE PRECISION for extreme values)
    mean_ret DOUBLE PRECISION,
    std_rets DOUBLE PRECISION,
    risk_adj_ret DOUBLE PRECISION,
    downside_std_rets DOUBLE PRECISION,
    downside_risk_adj_ret DOUBLE PRECISION,
    
    -- Relative metrics
    rel_net_profit DECIMAL(18, 6),
    rel_gross_profit DECIMAL(18, 6),
    rel_gross_loss DECIMAL(18, 6),
    rel_mean_profit DECIMAL(18, 6),
    rel_median_profit DECIMAL(18, 6),
    rel_std_profits DECIMAL(18, 6),
    rel_risk_adj_profit DOUBLE PRECISION,
    rel_min_profit DECIMAL(18, 6),
    rel_max_profit DECIMAL(18, 6),
    rel_profit_perc_10 DECIMAL(18, 6),
    rel_profit_perc_25 DECIMAL(18, 6),
    rel_profit_perc_75 DECIMAL(18, 6),
    rel_profit_perc_90 DECIMAL(18, 6),
    rel_profit_top_10_prcnt_trades DECIMAL(18, 6),
    rel_profit_bottom_10_prcnt_trades DECIMAL(18, 6),
    rel_one_std_outlier_profit DECIMAL(18, 6),
    rel_two_std_outlier_profit DECIMAL(18, 6),
    
    -- Drawdown analysis
    mean_drawdown DECIMAL(18, 2),
    median_drawdown DECIMAL(18, 2),
    max_drawdown DECIMAL(18, 2),
    mean_num_trades_in_dd DECIMAL(18, 2),
    median_num_trades_in_dd DECIMAL(18, 2),
    max_num_trades_in_dd INTEGER,
    rel_mean_drawdown DECIMAL(18, 6),
    rel_median_drawdown DECIMAL(18, 6),
    rel_max_drawdown DECIMAL(18, 6),
    
    -- Volume and lot metrics
    total_lots DECIMAL(18, 6),
    total_volume DECIMAL(18, 2),
    std_volumes DECIMAL(18, 2),
    mean_winning_lot DECIMAL(18, 6),
    mean_losing_lot DECIMAL(18, 6),
    distance_win_loss_lots DECIMAL(18, 6),
    multiple_win_loss_lots DECIMAL(10, 6),
    mean_winning_volume DECIMAL(18, 2),
    mean_losing_volume DECIMAL(18, 2),
    distance_win_loss_volume DECIMAL(18, 2),
    multiple_win_loss_volume DECIMAL(10, 6),
    
    -- Duration metrics
    mean_duration DECIMAL(18, 6),
    median_duration DECIMAL(18, 6),
    std_durations DECIMAL(18, 6),
    min_duration DECIMAL(18, 6),
    max_duration DECIMAL(18, 6),
    cv_durations DECIMAL(10, 6),
    
    -- Stop loss and take profit metrics
    mean_tp DECIMAL(18, 6),
    median_tp DECIMAL(18, 6),
    std_tp DECIMAL(18, 6),
    min_tp DECIMAL(18, 6),
    max_tp DECIMAL(18, 6),
    cv_tp DECIMAL(10, 6),
    mean_sl DECIMAL(18, 6),
    median_sl DECIMAL(18, 6),
    std_sl DECIMAL(18, 6),
    min_sl DECIMAL(18, 6),
    max_sl DECIMAL(18, 6),
    cv_sl DECIMAL(10, 6),
    mean_tp_vs_sl DECIMAL(10, 6),
    median_tp_vs_sl DECIMAL(10, 6),
    min_tp_vs_sl DECIMAL(10, 6),
    max_tp_vs_sl DECIMAL(10, 6),
    cv_tp_vs_sl DECIMAL(10, 6),
    
    -- Consecutive wins/losses
    mean_num_consec_wins DECIMAL(10, 2),
    median_num_consec_wins INTEGER,
    max_num_consec_wins INTEGER,
    mean_num_consec_losses DECIMAL(10, 2),
    median_num_consec_losses INTEGER,
    max_num_consec_losses INTEGER,
    mean_val_consec_wins DECIMAL(18, 2),
    median_val_consec_wins DECIMAL(18, 2),
    max_val_consec_wins DECIMAL(18, 2),
    mean_val_consec_losses DECIMAL(18, 2),
    median_val_consec_losses DECIMAL(18, 2),
    max_val_consec_losses DECIMAL(18, 2),
    
    -- Open position metrics
    mean_num_open_pos DECIMAL(10, 2),
    median_num_open_pos INTEGER,
    max_num_open_pos INTEGER,
    mean_val_open_pos DECIMAL(18, 2),
    median_val_open_pos DECIMAL(18, 2),
    max_val_open_pos DECIMAL(18, 2),
    mean_val_to_eqty_open_pos DECIMAL(10, 6),
    median_val_to_eqty_open_pos DECIMAL(10, 6),
    max_val_to_eqty_open_pos DECIMAL(10, 6),
    
    -- Margin and activity metrics
    mean_account_margin DECIMAL(18, 2),
    mean_firm_margin DECIMAL(18, 2),
    num_traded_symbols INTEGER,
    most_traded_symbol VARCHAR(50),
    most_traded_smb_trades INTEGER,
    
    -- System fields
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    PRIMARY KEY (account_id, date, hour)
) PARTITION BY RANGE (date);

-- Create partitions for raw_metrics_hourly (last 3 years + future)
DO $$
DECLARE
    start_date date := '2022-01-01';
    partition_date date;
    partition_name text;
BEGIN
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            CURRENT_DATE + interval '3 months',
            interval '1 month'
        )::date
    LOOP
        partition_name := 'raw_metrics_hourly_' || to_char(partition_date, 'YYYY_MM');
        
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I PARTITION OF raw_metrics_hourly
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + interval '1 month'
        );
    END LOOP;
END $$;

-- Indexes for raw_metrics_hourly
CREATE INDEX idx_raw_metrics_hourly_account_date ON raw_metrics_hourly(account_id, date DESC, hour);
CREATE INDEX idx_raw_metrics_hourly_date_hour ON raw_metrics_hourly(date DESC, hour);
CREATE INDEX idx_raw_metrics_hourly_plan_id ON raw_metrics_hourly(plan_id);
CREATE INDEX idx_raw_metrics_hourly_status_date ON raw_metrics_hourly(status, date DESC, hour);
CREATE INDEX idx_raw_metrics_hourly_profit ON raw_metrics_hourly(date DESC, hour, net_profit DESC) WHERE net_profit IS NOT NULL;

-- Raw trades closed - PARTITIONED BY RANGE (trade_date)
CREATE TABLE raw_trades_closed (
    trade_date DATE NOT NULL,
    broker INTEGER,
    manager INTEGER,
    platform INTEGER,
    ticket VARCHAR(255),
    position VARCHAR(255),
    login VARCHAR(255) NOT NULL,
    account_id VARCHAR(255), -- Nullable to handle cases where we only have login initially
    std_symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) CHECK (side IN ('buy', 'sell', 'BUY', 'SELL', 'Buy', 'Sell')),
    lots DECIMAL(18, 4),
    contract_size DECIMAL(18, 4),
    qty_in_base_ccy DECIMAL(18, 4),
    volume_usd DECIMAL(18, 4),
    stop_loss DECIMAL(18, 6),
    take_profit DECIMAL(18, 6),
    open_time TIMESTAMP,
    open_price DECIMAL(18, 6),
    close_time TIMESTAMP,
    close_price DECIMAL(18, 6),
    duration DECIMAL(18, 2),
    profit DECIMAL(18, 2),
    commission DECIMAL(18, 2),
    fee DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    comment VARCHAR(255),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(position, login, platform, broker, trade_date),
    PRIMARY KEY (platform, position, trade_date)
) PARTITION BY RANGE (trade_date);

-- Add comment explaining the nullable account_id
COMMENT ON COLUMN raw_trades_closed.account_id IS 'Account ID - may be temporarily set to login value until proper resolution with platform/mt_version is implemented';

-- Create partitions for raw_trades_closed
DO $$
DECLARE
    start_date date := '2022-01-01';
    partition_date date;
    partition_name text;
BEGIN
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            CURRENT_DATE + interval '3 months',
            interval '1 month'
        )::date
    LOOP
        partition_name := 'raw_trades_closed_' || to_char(partition_date, 'YYYY_MM');
        
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I PARTITION OF raw_trades_closed
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + interval '1 month'
        );
    END LOOP;
END $$;

-- Indexes for raw_trades_closed
CREATE INDEX idx_raw_trades_closed_account_id ON raw_trades_closed(account_id, trade_date DESC);
CREATE INDEX idx_raw_trades_closed_symbol ON raw_trades_closed(std_symbol, trade_date DESC) WHERE std_symbol IS NOT NULL;
CREATE INDEX idx_raw_trades_closed_profit ON raw_trades_closed(profit DESC, trade_date DESC);
CREATE INDEX idx_raw_trades_closed_login_platform_broker ON raw_trades_closed(login, platform, broker);

-- Raw trades open
CREATE TABLE raw_trades_open (
    trade_date DATE NOT NULL,
    broker INTEGER,
    manager INTEGER,
    platform INTEGER,
    ticket VARCHAR(255),  -- Keep as VARCHAR since API can send string or integer
    position VARCHAR(255),
    login VARCHAR(255) NOT NULL,
    account_id VARCHAR(255), -- Nullable to handle cases where we only have login initially
    std_symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) CHECK (side IN ('buy', 'sell', 'BUY', 'SELL', 'Buy', 'Sell')),
    lots DECIMAL(18, 4),
    contract_size DECIMAL(18, 4),
    qty_in_base_ccy DECIMAL(18, 4),
    volume_usd DECIMAL(18, 4),
    stop_loss DECIMAL(18, 6),
    take_profit DECIMAL(18, 6),
    open_time TIMESTAMP,
    open_price DECIMAL(18, 6),
    duration DECIMAL(18, 2),
    unrealized_profit DECIMAL(18, 2),
    commission DECIMAL(18, 2),
    fee DECIMAL(18, 2),
    swap DECIMAL(18, 2),
    comment VARCHAR(255),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(position, login, platform, broker, trade_date),
    PRIMARY KEY (platform, position, trade_date)
) PARTITION BY RANGE (trade_date);

-- Add comment explaining the nullable account_id
COMMENT ON COLUMN raw_trades_open.account_id IS 'Account ID - may be temporarily set to login value until proper resolution with platform/mt_version is implemented';

-- Create partitions for raw_trades_closed
DO $$
DECLARE
    start_date date := '2022-01-01';
    partition_date date;
    partition_name text;
BEGIN
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            CURRENT_DATE + interval '3 months',
            interval '1 month'
        )::date
    LOOP
        partition_name := 'raw_trades_open_' || to_char(partition_date, 'YYYY_MM');
        
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS %I PARTITION OF raw_trades_open
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + interval '1 month'
        );
    END LOOP;
END $$;

-- Indexes for raw_trades_open
CREATE INDEX idx_raw_trades_open_account_id ON raw_trades_open(account_id, trade_date DESC);
CREATE INDEX idx_raw_trades_open_symbol ON raw_trades_open(std_symbol, trade_date DESC) WHERE std_symbol IS NOT NULL;
CREATE INDEX idx_raw_trades_open_profit ON raw_trades_open(unrealized_profit DESC, trade_date DESC);
CREATE INDEX idx_raw_trades_open_login_platform_broker ON raw_trades_open(login, platform, broker);

-- Raw plans data
CREATE TABLE raw_plans_data (
    plan_id VARCHAR(255) NOT NULL PRIMARY KEY,
    plan_name VARCHAR(255) NOT NULL,
    plan_type VARCHAR(100),
    starting_balance DECIMAL(18, 2) CHECK (starting_balance > 0),
    profit_target DECIMAL(18, 2),
    profit_target_pct DECIMAL(5, 2) CHECK (profit_target_pct >= 0 AND profit_target_pct <= 100),
    max_drawdown DECIMAL(18, 2),
    max_drawdown_pct DECIMAL(5, 2) CHECK (max_drawdown_pct >= 0 AND max_drawdown_pct <= 100),
    max_daily_drawdown DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2) CHECK (max_daily_drawdown_pct >= 0 AND max_daily_drawdown_pct <= 100),
    profit_share_pct DECIMAL(5, 2) CHECK (profit_share_pct >= 0 AND profit_share_pct <= 100),
    max_leverage DECIMAL(10, 2) CHECK (max_leverage > 0),
    min_trading_days INTEGER CHECK (min_trading_days >= 0),
    max_trading_days INTEGER CHECK (max_trading_days >= 0),
    is_drawdown_relative BOOLEAN DEFAULT FALSE,
    liquidate_friday BOOLEAN DEFAULT FALSE,
    inactivity_period INTEGER CHECK (inactivity_period >= 0),
    daily_drawdown_by_balance_equity BOOLEAN DEFAULT FALSE,
    enable_consistency BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500)
);

-- Indexes for raw_plans_data
CREATE INDEX idx_raw_plans_plan_id ON raw_plans_data(plan_id);
CREATE INDEX idx_raw_plans_name ON raw_plans_data(plan_name);

-- Comments for plan columns
COMMENT ON COLUMN raw_plans_data.liquidate_friday IS 'Whether account can hold positions over the weekend (TRUE = must liquidate, FALSE = can hold)';
COMMENT ON COLUMN raw_plans_data.inactivity_period IS 'Number of days an account can go without placing a trade before breach';
COMMENT ON COLUMN raw_plans_data.daily_drawdown_by_balance_equity IS 'How daily drawdown is calculated (TRUE = from previous day balance or equity whichever is higher, FALSE = from previous day balance only)';
COMMENT ON COLUMN raw_plans_data.enable_consistency IS 'Whether consistency rules are applied to the account';

-- Raw market regimes daily data
CREATE TABLE raw_regimes_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    regime_name VARCHAR(100),
    summary JSONB,
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_api_endpoint VARCHAR(500),
    UNIQUE(date)
);

-- Indexes for raw_regimes_daily
CREATE INDEX idx_raw_regimes_date ON raw_regimes_daily(date DESC);
CREATE INDEX idx_raw_regimes_summary ON raw_regimes_daily USING gin(summary);

-- ========================================
-- Staging Tables (Data Processing Layer)
-- ========================================

-- Daily account snapshots for time-series analysis
CREATE TABLE stg_accounts_daily_snapshots (
    account_id VARCHAR(255) NOT NULL,
    snapshot_date DATE NOT NULL,
    
    -- Account metadata
    login VARCHAR(255) NOT NULL,
    plan_id VARCHAR(255),
    trader_id VARCHAR(255),
    status INTEGER CHECK (status IN (1, 2, 3)),
    type INTEGER,
    phase INTEGER CHECK (phase IN (1, 2, 3, 4)),
    broker INTEGER,
    platform INTEGER,
    country VARCHAR(2),
    starting_balance DECIMAL(18, 2),
    balance DECIMAL(18, 2),
    equity DECIMAL(18, 2),
    profit_target DECIMAL(18, 2),
    profit_target_pct DECIMAL(5, 2),
    max_daily_drawdown DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_drawdown DECIMAL(18, 2),
    max_drawdown_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative BOOLEAN,
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_max_drawdown DECIMAL(18, 2),
    liquidate_friday BOOLEAN DEFAULT FALSE,
    inactivity_period INTEGER,
    daily_drawdown_by_balance_equity BOOLEAN DEFAULT FALSE,
    enable_consistency BOOLEAN DEFAULT FALSE,
    days_active INTEGER,
    days_since_last_trade INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, snapshot_date)
) PARTITION BY RANGE (snapshot_date);

-- Indexes for staging table (parent)
CREATE INDEX idx_stg_accounts_daily_account_date ON stg_accounts_daily_snapshots(account_id, snapshot_date DESC);
CREATE INDEX idx_stg_accounts_daily_date ON stg_accounts_daily_snapshots(snapshot_date DESC);
CREATE INDEX idx_stg_accounts_daily_status ON stg_accounts_daily_snapshots(status) WHERE status = 1;

-- Create partitions for stg_accounts_daily_snapshots (last 3 years + future)
DO $$
DECLARE
    start_date date := '2022-01-01';
    partition_date date;
    partition_name text;
BEGIN
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            CURRENT_DATE + interval '3 months',
            interval '1 month'
        )::date
    LOOP
        partition_name := 'stg_accounts_daily_snapshots_' || to_char(partition_date, 'YYYY_MM');
        EXECUTE format('
            CREATE TABLE IF NOT EXISTS prop_trading_model.%I PARTITION OF prop_trading_model.stg_accounts_daily_snapshots
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + interval '1 month'
        );
    END LOOP;
END $$;

-- ========================================
-- Feature Store (ML Layer)
-- ========================================

-- Feature store for account daily features
CREATE TABLE feature_store_account_daily (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    feature_date DATE NOT NULL,
    
    -- Basic account features
    days_active INTEGER,
    current_phase VARCHAR(50),
    account_age_days INTEGER,
    
    -- Trading activity features
    trades_today INTEGER DEFAULT 0,
    trades_last_7d INTEGER DEFAULT 0,
    trades_last_30d INTEGER DEFAULT 0,
    trading_days_last_7d INTEGER DEFAULT 0,
    trading_days_last_30d INTEGER DEFAULT 0,
    avg_trades_per_day_7d DECIMAL(10, 4),
    avg_trades_per_day_30d DECIMAL(10, 4),
    
    -- Performance features
    profit_today DECIMAL(18, 2),
    profit_last_7d DECIMAL(18, 2),
    profit_last_30d DECIMAL(18, 2),
    roi_today DECIMAL(10, 4),
    roi_last_7d DECIMAL(10, 4),
    roi_last_30d DECIMAL(10, 4),
    
    -- Risk features
    win_rate_today DECIMAL(5, 2),
    win_rate_7d DECIMAL(5, 2),
    win_rate_30d DECIMAL(5, 2),
    profit_factor_7d DECIMAL(10, 2),
    profit_factor_30d DECIMAL(10, 2),
    max_drawdown_7d DECIMAL(18, 2),
    max_drawdown_30d DECIMAL(18, 2),
    current_drawdown DECIMAL(18, 2),
    current_drawdown_pct DECIMAL(5, 2),
    
    -- Trading behavior features
    avg_trade_size_7d DECIMAL(18, 4),
    avg_trade_size_30d DECIMAL(18, 4),
    avg_holding_time_hours_7d DECIMAL(10, 2),
    avg_holding_time_hours_30d DECIMAL(10, 2),
    
    -- Symbol diversification
    unique_symbols_7d INTEGER,
    unique_symbols_30d INTEGER,
    symbol_concentration_7d DECIMAL(5, 2),
    symbol_concentration_30d DECIMAL(5, 2),
    
    -- Time pattern features
    pct_trades_market_hours_7d DECIMAL(5, 2),
    pct_trades_market_hours_30d DECIMAL(5, 2),
    favorite_trading_hour_7d INTEGER,
    favorite_trading_hour_30d INTEGER,
    
    -- Consistency features
    daily_profit_volatility_7d DECIMAL(18, 2),
    daily_profit_volatility_30d DECIMAL(18, 2),
    profitable_days_pct_7d DECIMAL(5, 2),
    profitable_days_pct_30d DECIMAL(5, 2),
    
    -- Plan compliance features
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_profit_target_pct DECIMAL(5, 2),
    distance_to_drawdown_limit DECIMAL(18, 2),
    distance_to_drawdown_limit_pct DECIMAL(5, 2),
    days_until_deadline INTEGER,
    
    -- Market regime features
    market_volatility_regime VARCHAR(50),
    market_trend_regime VARCHAR(50),
    
    -- Target variable
    -- will_profit_next_day BOOLEAN, -- Target column not implemented yet
    next_day_profit DECIMAL(18, 2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, feature_date)
);

-- Indexes for feature store
CREATE INDEX idx_feature_store_account_date ON feature_store_account_daily(account_id, feature_date DESC);
CREATE INDEX idx_feature_store_date ON feature_store_account_daily(feature_date DESC);
-- CREATE INDEX idx_feature_store_profit_target ON feature_store_account_daily(will_profit_next_day, feature_date DESC); -- Column will_profit_next_day does not exist yet

-- ========================================
-- Model Management Tables
-- ========================================

-- Model training input tracking
CREATE TABLE model_training_input (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    prediction_date DATE NOT NULL,
    feature_date DATE NOT NULL,
    
    -- Static features
    starting_balance DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_drawdown_pct DECIMAL(5, 2),
    profit_target_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative BOOLEAN,
    
    -- Dynamic features
    current_balance DECIMAL(18, 2),
    current_equity DECIMAL(18, 2),
    days_since_first_trade INTEGER,
    active_trading_days_count INTEGER,
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_max_drawdown DECIMAL(18, 2),
    open_pnl DECIMAL(18, 2),
    open_positions_volume DECIMAL(18, 2),
    
    -- Rolling performance features
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
    profit_factor_5d DECIMAL(10, 4),
    sharpe_ratio_5d DECIMAL(10, 4),
    rolling_pnl_sum_10d DECIMAL(18, 2),
    rolling_pnl_avg_10d DECIMAL(18, 2),
    rolling_pnl_std_10d DECIMAL(18, 2),
    rolling_pnl_min_10d DECIMAL(18, 2),
    rolling_pnl_max_10d DECIMAL(18, 2),
    win_rate_10d DECIMAL(5, 2),
    profit_factor_10d DECIMAL(10, 4),
    sharpe_ratio_10d DECIMAL(10, 4),
    rolling_pnl_sum_20d DECIMAL(18, 2),
    rolling_pnl_avg_20d DECIMAL(18, 2),
    rolling_pnl_std_20d DECIMAL(18, 2),
    win_rate_20d DECIMAL(5, 2),
    profit_factor_20d DECIMAL(10, 4),
    sharpe_ratio_20d DECIMAL(10, 4),
    
    -- Behavioral features
    trades_count_5d INTEGER,
    avg_trade_duration_5d DECIMAL(10, 2),
    avg_lots_per_trade_5d DECIMAL(10, 4),
    avg_volume_per_trade_5d DECIMAL(18, 2),
    stop_loss_usage_rate_5d DECIMAL(5, 2),
    take_profit_usage_rate_5d DECIMAL(5, 2),
    buy_sell_ratio_5d DECIMAL(10, 4),
    top_symbol_concentration_5d DECIMAL(5, 2),
    
    -- Market features
    market_sentiment_score DECIMAL(10, 4),
    market_volatility_regime VARCHAR(50),
    market_liquidity_state VARCHAR(50),
    vix_level DECIMAL(10, 2),
    dxy_level DECIMAL(10, 2),
    sp500_daily_return DECIMAL(10, 4),
    btc_volatility_90d DECIMAL(10, 4),
    fed_funds_rate DECIMAL(5, 2),
    
    -- Time features
    day_of_week INTEGER,
    week_of_month INTEGER,
    month INTEGER,
    quarter INTEGER,
    day_of_year INTEGER,
    is_month_start BOOLEAN,
    is_month_end BOOLEAN,
    is_quarter_start BOOLEAN,
    is_quarter_end BOOLEAN,
    
    -- Target variable
    target_net_profit DECIMAL(18, 2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, prediction_date)
);

-- Model predictions tracking
CREATE TABLE model_predictions (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(100) NOT NULL,
    prediction_date DATE NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    predicted_profit_probability DECIMAL(5, 4),
    predicted_profit_amount DECIMAL(18, 2),
    feature_importance JSONB,
    prediction_confidence DECIMAL(5, 4),
    actual_profit DECIMAL(18, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(model_version, prediction_date, account_id)
);

-- Indexes for model predictions
CREATE INDEX idx_model_predictions_date ON model_predictions(prediction_date DESC);
CREATE INDEX idx_model_predictions_account ON model_predictions(account_id, prediction_date DESC);

-- Model registry
CREATE TABLE model_registry (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(100) NOT NULL UNIQUE,
    model_type VARCHAR(50) NOT NULL,
    training_completed_at TIMESTAMP NOT NULL,
    model_path VARCHAR(500),
    git_commit_hash VARCHAR(100),
    performance_metrics JSONB,
    feature_importance JSONB,
    is_active BOOLEAN DEFAULT FALSE,
    deployed_at TIMESTAMP,
    deprecated_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ========================================
-- Operational Tables
-- ========================================

-- Pipeline execution logging
CREATE TABLE pipeline_execution_log (
    id SERIAL PRIMARY KEY,
    pipeline_stage VARCHAR(100) NOT NULL,
    execution_date DATE NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(50) CHECK (status IN ('running', 'success', 'failed', 'warning')),
    records_processed INTEGER,
    records_failed INTEGER,
    error_message TEXT,
    execution_details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for pipeline execution log
CREATE INDEX idx_pipeline_execution_stage_date ON pipeline_execution_log(pipeline_stage, execution_date DESC);
CREATE INDEX idx_pipeline_execution_status ON pipeline_execution_log(status, created_at DESC);

-- Query performance monitoring
CREATE TABLE query_performance_log (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64),
    query_template TEXT,
    execution_time_ms DECIMAL(10, 2),
    rows_returned INTEGER,
    table_names TEXT[],
    index_used BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scheduled jobs tracking
CREATE TABLE scheduled_jobs (
    job_name VARCHAR(100) PRIMARY KEY,
    schedule VARCHAR(100) NOT NULL,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    status VARCHAR(50),
    error_count INTEGER DEFAULT 0,
    command TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ========================================
-- Materialized Views
-- ========================================

-- Account Performance Summary
CREATE MATERIALIZED VIEW mv_account_performance_summary AS
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
    p.max_daily_drawdown_pct,
    p.max_leverage,
    p.min_trading_days,
    p.max_trading_days,
    -- Lifetime metrics
    COALESCE(m.num_trades, 0) as lifetime_trades,
    COALESCE(m.net_profit, 0) as lifetime_profit,
    COALESCE(m.gross_profit, 0) as lifetime_gross_profit,
    COALESCE(m.gross_loss, 0) as lifetime_gross_loss,
    COALESCE(m.success_rate, 0) as lifetime_win_rate,
    COALESCE(m.profit_factor, 0) as lifetime_profit_factor,
    COALESCE(m.daily_sharpe, 0) as lifetime_sharpe_ratio,
    COALESCE(m.daily_sortino, 0) as lifetime_sortino_ratio,
    COALESCE(m.rel_max_drawdown, 0) as lifetime_max_drawdown_pct,
    -- Recent performance (30 days)
    COALESCE(daily.trades_last_30d, 0) as trades_last_30d,
    COALESCE(daily.profit_last_30d, 0) as profit_last_30d,
    COALESCE(daily.win_rate_last_30d, 0) as win_rate_last_30d,
    COALESCE(daily.trading_days_last_30d, 0) as trading_days_last_30d,
    -- Recent performance (7 days)
    COALESCE(weekly.trades_last_7d, 0) as trades_last_7d,
    COALESCE(weekly.profit_last_7d, 0) as profit_last_7d,
    COALESCE(weekly.win_rate_last_7d, 0) as win_rate_last_7d,
    -- Account health metrics
    CASE 
        WHEN a.starting_balance > 0 
        THEN ((a.current_balance - a.starting_balance) / a.starting_balance * 100)
        ELSE 0 
    END as total_return_pct,
    CASE 
        WHEN p.profit_target > 0 
        THEN ((p.profit_target - (a.current_balance - a.starting_balance)) / p.profit_target * 100)
        ELSE 0 
    END as distance_to_target_pct,
    a.updated_date as last_updated,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM (
    SELECT DISTINCT ON (account_id) *
    FROM raw_metrics_alltime
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
        SUM(num_trades) as trades_last_30d,
        SUM(net_profit) as profit_last_30d,
        COUNT(DISTINCT date) as trading_days_last_30d,
        CASE 
            WHEN SUM(num_trades) > 0 
            THEN SUM(num_trades * success_rate / 100)::DECIMAL / SUM(num_trades) * 100
            ELSE 0 
        END as win_rate_last_30d
    FROM raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY account_id
) daily ON true
LEFT JOIN LATERAL (
    SELECT 
        account_id,
        SUM(num_trades) as trades_last_7d,
        SUM(net_profit) as profit_last_7d,
        CASE 
            WHEN SUM(num_trades) > 0 
            THEN SUM(num_trades * success_rate / 100)::DECIMAL / SUM(num_trades) * 100
            ELSE 0 
        END as win_rate_last_7d
    FROM raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY account_id
) weekly ON true
WITH DATA;

-- Create indexes for mv_account_performance_summary
CREATE UNIQUE INDEX idx_mv_account_performance_account_id ON mv_account_performance_summary(account_id);
CREATE INDEX idx_mv_account_performance_status ON mv_account_performance_summary(status) WHERE status = 1;
CREATE INDEX idx_mv_account_performance_phase ON mv_account_performance_summary(phase);
CREATE INDEX idx_mv_account_performance_profit ON mv_account_performance_summary(lifetime_profit DESC);
CREATE INDEX idx_mv_account_performance_recent_profit ON mv_account_performance_summary(profit_last_30d DESC);

-- Daily Trading Statistics
CREATE MATERIALIZED VIEW mv_daily_trading_stats AS
SELECT 
    date,
    COUNT(DISTINCT account_id) as active_accounts,
    COUNT(DISTINCT CASE WHEN net_profit > 0 THEN account_id END) as profitable_accounts,
    COUNT(DISTINCT CASE WHEN net_profit < 0 THEN account_id END) as losing_accounts,
    SUM(num_trades) as num_trades,
    SUM(num_trades * success_rate / 100) as total_winning_trades,
    SUM(num_trades * (100 - success_rate) / 100) as total_losing_trades,
    SUM(net_profit) as total_profit,
    SUM(gross_profit) as total_gross_profit,
    SUM(gross_loss) as total_gross_loss,
    AVG(net_profit) as avg_profit,
    STDDEV(net_profit) as profit_stddev,
    SUM(total_volume) as total_volume,
    SUM(total_lots) as total_lots,
    AVG(success_rate) as avg_win_rate,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY net_profit) as median_profit,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY net_profit) as profit_q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY net_profit) as profit_q3,
    MAX(net_profit) as max_profit,
    MIN(net_profit) as min_profit,
    -- Day of week analysis
    EXTRACT(DOW FROM date)::INTEGER as day_of_week,
    EXTRACT(WEEK FROM date)::INTEGER as week_number,
    EXTRACT(MONTH FROM date)::INTEGER as month,
    EXTRACT(YEAR FROM date)::INTEGER as year,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM raw_metrics_daily
WHERE date >= CURRENT_DATE - INTERVAL '365 days'
GROUP BY date
WITH DATA;

-- Create indexes on mv_daily_trading_stats
CREATE UNIQUE INDEX idx_mv_daily_stats_date ON mv_daily_trading_stats(date);
CREATE INDEX idx_mv_daily_stats_year_month ON mv_daily_trading_stats(year, month);
CREATE INDEX idx_mv_daily_stats_dow ON mv_daily_trading_stats(day_of_week);

-- Symbol Performance Statistics
CREATE MATERIALIZED VIEW mv_symbol_performance AS
WITH symbol_stats AS (
    SELECT 
        std_symbol,
        COUNT(DISTINCT account_id) as traders_count,
        COUNT(*) as num_trades,
        SUM(profit) as total_profit,
        AVG(profit) as avg_profit,
        STDDEV(profit) as profit_stddev,
        SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning_trades,
        SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losing_trades,
        SUM(CASE WHEN profit > 0 THEN profit ELSE 0 END) as gross_profit,
        SUM(CASE WHEN profit < 0 THEN profit ELSE 0 END) as gross_loss,
        SUM(volume_usd) as total_volume,
        SUM(lots) as total_lots,
        MAX(profit) as max_profit,
        MIN(profit) as min_profit,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY profit) as median_profit,
        AVG(EXTRACT(EPOCH FROM (close_time - open_time))/3600) as avg_trade_duration_hours
    FROM raw_trades_closed
    WHERE trade_date >= CURRENT_DATE - INTERVAL '90 days'
        AND std_symbol IS NOT NULL
    GROUP BY std_symbol
    HAVING COUNT(*) > 100  -- Only symbols with significant activity
)
SELECT 
    std_symbol,
    traders_count,
    num_trades,
    total_profit,
    avg_profit,
    profit_stddev,
    winning_trades,
    losing_trades,
    gross_profit,
    gross_loss,
    CASE 
        WHEN num_trades > 0 
        THEN winning_trades::DECIMAL / num_trades * 100 
        ELSE 0 
    END as win_rate,
    CASE 
        WHEN gross_loss < 0 
        THEN ABS(gross_profit / gross_loss)
        ELSE 0 
    END as profit_factor,
    total_volume,
    total_lots,
    max_profit,
    min_profit,
    median_profit,
    avg_trade_duration_hours,
    CASE 
        WHEN profit_stddev > 0 
        THEN avg_profit / profit_stddev 
        ELSE 0 
    END as sharpe_approximation,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM symbol_stats
WITH DATA;

-- Create indexes for mv_symbol_performance
CREATE UNIQUE INDEX idx_mv_symbol_performance_symbol ON mv_symbol_performance(std_symbol);
CREATE INDEX idx_mv_symbol_performance_profit ON mv_symbol_performance(total_profit DESC);
CREATE INDEX idx_mv_symbol_performance_trades ON mv_symbol_performance(num_trades DESC);
CREATE INDEX idx_mv_symbol_performance_win_rate ON mv_symbol_performance(win_rate DESC);

-- Account Trading Patterns
CREATE MATERIALIZED VIEW mv_account_trading_patterns AS
WITH recent_trades AS (
    SELECT 
        account_id,
        login,
        std_symbol,
        side,
        EXTRACT(HOUR FROM open_time) as trade_hour,
        EXTRACT(DOW FROM trade_date) as trade_dow,
        profit,
        lots,
        volume_usd,
        CASE WHEN stop_loss IS NOT NULL THEN 1 ELSE 0 END as has_sl,
        CASE WHEN take_profit IS NOT NULL THEN 1 ELSE 0 END as has_tp
    FROM raw_trades_closed
    WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
)
SELECT 
    account_id,
    login,
    COUNT(*) as num_trades_30d,
    -- Symbol concentration
    COUNT(DISTINCT recent_trades.std_symbol) as unique_symbols,
    MODE() WITHIN GROUP (ORDER BY recent_trades.std_symbol) as favorite_symbol,
    MAX(symbol_trades.symbol_count)::DECIMAL / COUNT(*) * 100 as top_symbol_concentration_pct,
    -- Time patterns
    MODE() WITHIN GROUP (ORDER BY trade_hour) as favorite_hour,
    MODE() WITHIN GROUP (ORDER BY trade_dow) as favorite_day_of_week,
    -- Trading style
    AVG(lots) as avg_lot_size,
    STDDEV(lots) as lot_size_stddev,
    AVG(volume_usd) as avg_trade_volume,
    SUM(CASE WHEN side IN ('buy', 'BUY') THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) * 100 as buy_ratio,
    -- Risk management
    AVG(has_sl) * 100 as sl_usage_rate,
    AVG(has_tp) * 100 as tp_usage_rate,
    -- Performance by time
    AVG(CASE WHEN trade_hour BETWEEN 8 AND 16 THEN profit END) as avg_profit_market_hours,
    AVG(CASE WHEN trade_hour NOT BETWEEN 8 AND 16 THEN profit END) as avg_profit_off_hours,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM recent_trades
LEFT JOIN LATERAL (
    SELECT std_symbol, COUNT(*) as symbol_count
    FROM recent_trades rt2
    WHERE rt2.account_id = recent_trades.account_id
    GROUP BY std_symbol
    ORDER BY COUNT(*) DESC
    LIMIT 1
) symbol_trades ON true
GROUP BY account_id, login
WITH DATA;

-- Create indexes for mv_account_trading_patterns
CREATE UNIQUE INDEX idx_mv_trading_patterns_account_id ON mv_account_trading_patterns(account_id);
CREATE INDEX idx_mv_trading_patterns_login ON mv_account_trading_patterns(login);

-- Market Regime Performance
CREATE MATERIALIZED VIEW mv_market_regime_performance AS
SELECT 
    r.date,
    r.summary->>'market_sentiment' as market_sentiment,
    r.summary->>'volatility_regime' as volatility_regime,
    r.summary->>'liquidity_state' as liquidity_state,
    COUNT(DISTINCT m.account_id) as active_accounts,
    SUM(m.num_trades) as num_trades,
    SUM(m.net_profit) as total_profit,
    AVG(m.net_profit) as avg_profit,
    STDDEV(m.net_profit) as profit_stddev,
    AVG(m.success_rate) as avg_win_rate,
    SUM(m.total_volume) as total_volume,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.net_profit) as median_profit,
    COUNT(DISTINCT CASE WHEN m.net_profit > 0 THEN m.account_id END) as profitable_accounts,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM raw_regimes_daily r
INNER JOIN raw_metrics_daily m ON r.date = m.date
WHERE r.date >= CURRENT_DATE - INTERVAL '180 days'
    AND r.summary IS NOT NULL
GROUP BY r.date, r.summary
WITH DATA;

-- Create indexes for mv_market_regime_performance
CREATE INDEX idx_mv_regime_performance_date ON mv_market_regime_performance(date DESC);
CREATE INDEX idx_mv_regime_performance_sentiment ON mv_market_regime_performance(market_sentiment);

-- ========================================
-- Functions and Procedures
-- ========================================

-- Function to refresh all materialized views
CREATE OR REPLACE FUNCTION refresh_materialized_views() RETURNS void AS $$
BEGIN
    -- Refresh views in dependency order
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_trading_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_symbol_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_performance_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_trading_patterns;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_market_regime_performance;
    
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
            'views_refreshed', ARRAY[
                'mv_daily_trading_stats', 
                'mv_symbol_performance', 
                'mv_account_performance_summary',
                'mv_account_trading_patterns',
                'mv_market_regime_performance'
            ]
        )
    );
END;
$$ LANGUAGE plpgsql;

-- Function to create monthly partitions for partitioned tables
CREATE OR REPLACE FUNCTION create_monthly_partitions(
    table_name text,
    start_date date,
    end_date date
) RETURNS void AS $$
DECLARE
    partition_date date;
    partition_name text;
    date_column text;
BEGIN
    -- Determine date column based on table
    IF table_name = 'raw_metrics_daily' THEN
        date_column := 'date';
    ELSIF table_name = 'raw_metrics_hourly' THEN
        date_column := 'date';
    ELSIF table_name = 'raw_trades_closed' THEN
        date_column := 'trade_date';
    ELSIF table_name = 'raw_trades_open' THEN
        date_column := 'trade_date';
    ELSE
        RAISE EXCEPTION 'Unknown table for partitioning: %', table_name;
    END IF;
    
    -- Create partitions for each month
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            end_date,
            interval '1 month'
        )::date
    LOOP
        partition_name := table_name || '_' || to_char(partition_date, 'YYYY_MM');
        
        -- Check if partition exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_tables 
            WHERE schemaname = 'prop_trading_model' 
            AND tablename = partition_name
        ) THEN
            EXECUTE format('
                CREATE TABLE %I PARTITION OF %I
                FOR VALUES FROM (%L) TO (%L)',
                partition_name,
                table_name,
                partition_date,
                partition_date + interval '1 month'
            );
            
            RAISE NOTICE 'Created partition: %', partition_name;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Function to clean old partitions
CREATE OR REPLACE FUNCTION drop_old_partitions(
    table_name text,
    retention_months integer DEFAULT 36
) RETURNS void AS $$
DECLARE
    partition_record record;
    cutoff_date date;
BEGIN
    cutoff_date := CURRENT_DATE - (retention_months || ' months')::interval;
    
    FOR partition_record IN 
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename LIKE table_name || '_%'
        AND tablename ~ '\d{4}_\d{2}$'
    LOOP
        -- Extract date from partition name
        IF to_date(right(partition_record.tablename, 7), 'YYYY_MM') < cutoff_date THEN
            EXECUTE format('DROP TABLE IF EXISTS %I.%I', 'prop_trading_model', partition_record.tablename);
            RAISE NOTICE 'Dropped old partition: %', partition_record.tablename;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Permissions (adjust based on your users)
-- ========================================

-- Grant usage on schema
GRANT USAGE ON SCHEMA prop_trading_model TO PUBLIC;

-- Grant appropriate permissions on tables
GRANT SELECT ON ALL TABLES IN SCHEMA prop_trading_model TO PUBLIC;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA prop_trading_model TO PUBLIC;

-- Grant permissions on sequences
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA prop_trading_model TO PUBLIC;
