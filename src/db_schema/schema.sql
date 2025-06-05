-- Prop Trading Model Database Schema - Version 2 (Balanced)
-- This version implements table partitioning, materialized views, and migration versioning
-- Includes all optimizations from Version 1 plus advanced features

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
-- Partitioned Tables Setup
-- ========================================

-- Raw trades closed - PARTITIONED BY RANGE (trade_date)
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

-- Create monthly partitions for the last 2 years and next 3 months
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

-- Raw metrics daily - PARTITIONED BY RANGE (date)
CREATE TABLE IF NOT EXISTS raw_metrics_daily (
    id SERIAL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    date DATE NOT NULL,  -- Partition key
    net_profit DECIMAL(18, 2),
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
    FOR year IN 2022..2025 LOOP
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

-- ========================================
-- Non-Partitioned Tables (from V1 with enhancements)
-- ========================================

-- Raw accounts data with cascading foreign keys
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

-- All indexes from V1 plus additional ones
CREATE INDEX idx_raw_accounts_account_id ON raw_accounts_data(account_id);
CREATE INDEX idx_raw_accounts_login ON raw_accounts_data(login);
CREATE INDEX idx_raw_accounts_trader_id ON raw_accounts_data(trader_id) WHERE trader_id IS NOT NULL;
CREATE INDEX idx_raw_accounts_plan_id ON raw_accounts_data(plan_id) WHERE plan_id IS NOT NULL;
CREATE INDEX idx_raw_accounts_ingestion ON raw_accounts_data(ingestion_timestamp DESC);
CREATE INDEX idx_raw_accounts_status ON raw_accounts_data(status) WHERE status = 'Active';
CREATE INDEX idx_raw_accounts_phase ON raw_accounts_data(phase);
CREATE INDEX idx_raw_accounts_updated ON raw_accounts_data(updated_at DESC) WHERE updated_at IS NOT NULL;

-- Raw plans data (reference table)
CREATE TABLE IF NOT EXISTS raw_plans_data (
    id SERIAL PRIMARY KEY,
    plan_id VARCHAR(255) NOT NULL UNIQUE,  -- Made UNIQUE for FK reference
    plan_name VARCHAR(255),
    plan_type VARCHAR(100),
    starting_balance DECIMAL(18, 2) CHECK (starting_balance > 0),
    profit_target DECIMAL(18, 2) CHECK (profit_target > 0),
    profit_target_pct DECIMAL(5, 2) CHECK (profit_target_pct > 0 AND profit_target_pct <= 100),
    max_drawdown DECIMAL(18, 2),
    max_drawdown_pct DECIMAL(5, 2) CHECK (max_drawdown_pct > 0 AND max_drawdown_pct <= 100),
    max_daily_drawdown DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2) CHECK (max_daily_drawdown_pct > 0 AND max_daily_drawdown_pct <= 100),
    max_leverage DECIMAL(10, 2) CHECK (max_leverage > 0),
    is_drawdown_relative BOOLEAN DEFAULT FALSE,
    min_trading_days INTEGER CHECK (min_trading_days >= 0),
    max_trading_days INTEGER CHECK (max_trading_days >= min_trading_days),
    profit_split_pct DECIMAL(5, 2) CHECK (profit_split_pct >= 0 AND profit_split_pct <= 100),
    ingestion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
CREATE UNIQUE INDEX idx_mv_account_performance_account_id ON mv_account_performance_summary(account_id);
CREATE INDEX idx_mv_account_performance_status ON mv_account_performance_summary(status);
CREATE INDEX idx_mv_account_performance_profit ON mv_account_performance_summary(lifetime_profit DESC);

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

CREATE UNIQUE INDEX idx_mv_daily_stats_date ON mv_daily_trading_stats(date);

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

CREATE UNIQUE INDEX idx_mv_symbol_performance_symbol ON mv_symbol_performance(std_symbol);
CREATE INDEX idx_mv_symbol_performance_profit ON mv_symbol_performance(total_profit DESC);

-- ========================================
-- Foreign Key Constraints with Cascading
-- ========================================

-- Add foreign keys with appropriate cascading rules
ALTER TABLE raw_accounts_data 
    ADD CONSTRAINT fk_accounts_plan_id 
    FOREIGN KEY (plan_id) 
    REFERENCES raw_plans_data(plan_id) 
    ON DELETE SET NULL 
    ON UPDATE CASCADE;

ALTER TABLE stg_accounts_daily_snapshots 
    ADD CONSTRAINT fk_stg_accounts_plan_id 
    FOREIGN KEY (plan_id) 
    REFERENCES raw_plans_data(plan_id) 
    ON DELETE SET NULL 
    ON UPDATE CASCADE;

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

-- ========================================
-- Scheduled Jobs Setup (using pg_cron or similar)
-- ========================================

-- Create job scheduling table
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

CREATE INDEX idx_query_performance_fingerprint ON query_performance_log(query_fingerprint);
CREATE INDEX idx_query_performance_logged_at ON query_performance_log(logged_at DESC);

-- ========================================
-- Remaining tables from Version 1
-- ========================================

-- Include all other tables from Version 1 with same structure
-- (raw_metrics_alltime, raw_metrics_hourly, raw_trades_open, raw_regimes_daily,
--  stg_accounts_daily_snapshots, feature_store_account_daily, model_training_input,
--  model_predictions, model_registry, pipeline_execution_log)

-- [Previous tables omitted for brevity but would include all from V1]

-- ========================================
-- Grant permissions
-- ========================================

-- GRANT USAGE ON SCHEMA prop_trading_model TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA prop_trading_model TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA prop_trading_model TO your_app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA prop_trading_model TO your_app_user;