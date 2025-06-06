-- Migration: 001_add_partitioning.sql
-- Version: 2.0.0 (Balanced)
-- Description: Convert raw_trades_closed and raw_metrics_daily to partitioned tables
-- Author: Database Schema Architect
-- Date: 2025-01-06

-- This is a complex migration that requires careful execution

BEGIN;

-- ========================================
-- Step 1: Rename existing tables
-- ========================================

ALTER TABLE prop_trading_model.raw_trades_closed RENAME TO raw_trades_closed_old;
ALTER TABLE prop_trading_model.raw_metrics_daily RENAME TO raw_metrics_daily_old;

-- ========================================
-- Step 2: Create new partitioned tables
-- ========================================

-- Create partitioned raw_trades_closed
CREATE TABLE prop_trading_model.raw_trades_closed (
    id BIGSERIAL,
    trade_id VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    symbol VARCHAR(50),
    std_symbol VARCHAR(50),
    side VARCHAR(10) CHECK (side IN ('buy', 'sell', 'BUY', 'SELL')),
    open_time TIMESTAMP,
    close_time TIMESTAMP,
    trade_date DATE NOT NULL,
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
    PRIMARY KEY (id, trade_date)
) PARTITION BY RANGE (trade_date);

-- Create partitioned raw_metrics_daily
CREATE TABLE prop_trading_model.raw_metrics_daily (
    id SERIAL,
    account_id VARCHAR(255) NOT NULL,
    login VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
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

-- ========================================
-- Step 3: Create partitions based on existing data
-- ========================================

DO $$
DECLARE
    min_date DATE;
    max_date DATE;
    curr_date DATE;
    partition_name TEXT;
BEGIN
    -- For raw_trades_closed - create monthly partitions
    SELECT MIN(trade_date), MAX(trade_date) 
    INTO min_date, max_date
    FROM prop_trading_model.raw_trades_closed_old;
    
    -- Start from beginning of month
    curr_date := DATE_TRUNC('month', min_date);
    
    WHILE curr_date <= DATE_TRUNC('month', max_date) + INTERVAL '1 month' LOOP
        partition_name := 'raw_trades_closed_' || to_char(curr_date, 'YYYY_MM');
        
        EXECUTE format('
            CREATE TABLE prop_trading_model.%I PARTITION OF prop_trading_model.raw_trades_closed
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            curr_date,
            curr_date + INTERVAL '1 month'
        );
        
        curr_date := curr_date + INTERVAL '1 month';
    END LOOP;
    
    -- For raw_metrics_daily - create yearly partitions
    SELECT MIN(date), MAX(date) 
    INTO min_date, max_date
    FROM prop_trading_model.raw_metrics_daily_old;
    
    -- Start from beginning of year
    curr_date := DATE_TRUNC('year', min_date);
    
    WHILE curr_date <= DATE_TRUNC('year', max_date) + INTERVAL '1 year' LOOP
        partition_name := 'raw_metrics_daily_' || EXTRACT(YEAR FROM curr_date);
        
        EXECUTE format('
            CREATE TABLE prop_trading_model.%I PARTITION OF prop_trading_model.raw_metrics_daily
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            curr_date,
            curr_date + INTERVAL '1 year'
        );
        
        curr_date := curr_date + INTERVAL '1 year';
    END LOOP;
    
    -- Create future partitions
    PERFORM prop_trading_model.create_monthly_partitions();
END $$;

-- ========================================
-- Step 4: Copy data to partitioned tables
-- ========================================

-- Copy trades data in batches to avoid memory issues
DO $$
DECLARE
    batch_size INTEGER := 1000000;
    offset_val INTEGER := 0;
    rows_copied INTEGER;
BEGIN
    LOOP
        INSERT INTO prop_trading_model.raw_trades_closed
        SELECT * FROM prop_trading_model.raw_trades_closed_old
        ORDER BY id
        LIMIT batch_size
        OFFSET offset_val;
        
        GET DIAGNOSTICS rows_copied = ROW_COUNT;
        
        IF rows_copied = 0 THEN
            EXIT;
        END IF;
        
        offset_val := offset_val + batch_size;
        
        -- Log progress
        RAISE NOTICE 'Copied % rows to raw_trades_closed', offset_val;
        
        -- Allow other transactions
        COMMIT;
        BEGIN;
    END LOOP;
END $$;

-- Copy metrics data (smaller table, can do in one go)
INSERT INTO prop_trading_model.raw_metrics_daily
SELECT * FROM prop_trading_model.raw_metrics_daily_old;

-- ========================================
-- Step 5: Create indexes on all partitions
-- ========================================

DO $$
DECLARE
    partition_record RECORD;
BEGIN
    -- Create indexes on trades partitions
    FOR partition_record IN 
        SELECT child.relname as partition_name
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        WHERE parent.relname = 'raw_trades_closed'
        AND parent.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'prop_trading_model')
    LOOP
        EXECUTE format('
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (trade_date);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id, trade_date);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (std_symbol) WHERE std_symbol IS NOT NULL;
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (profit) WHERE profit != 0;',
            'idx_' || partition_record.partition_name || '_account_id', partition_record.partition_name,
            'idx_' || partition_record.partition_name || '_trade_date', partition_record.partition_name,
            'idx_' || partition_record.partition_name || '_account_date', partition_record.partition_name,
            'idx_' || partition_record.partition_name || '_symbol', partition_record.partition_name,
            'idx_' || partition_record.partition_name || '_profit', partition_record.partition_name
        );
    END LOOP;
    
    -- Create indexes on metrics partitions
    FOR partition_record IN 
        SELECT child.relname as partition_name
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        WHERE parent.relname = 'raw_metrics_daily'
        AND parent.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'prop_trading_model')
    LOOP
        EXECUTE format('
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (date DESC);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id, date DESC);',
            'idx_' || partition_record.partition_name || '_account_id', partition_record.partition_name,
            'idx_' || partition_record.partition_name || '_date', partition_record.partition_name,
            'idx_' || partition_record.partition_name || '_account_date', partition_record.partition_name
        );
    END LOOP;
END $$;

-- ========================================
-- Step 6: Verify data integrity
-- ========================================

DO $$
DECLARE
    old_count BIGINT;
    new_count BIGINT;
BEGIN
    -- Check trades
    SELECT COUNT(*) INTO old_count FROM prop_trading_model.raw_trades_closed_old;
    SELECT COUNT(*) INTO new_count FROM prop_trading_model.raw_trades_closed;
    
    IF old_count != new_count THEN
        RAISE EXCEPTION 'Data mismatch in raw_trades_closed: old=%, new=%', old_count, new_count;
    END IF;
    
    -- Check metrics
    SELECT COUNT(*) INTO old_count FROM prop_trading_model.raw_metrics_daily_old;
    SELECT COUNT(*) INTO new_count FROM prop_trading_model.raw_metrics_daily;
    
    IF old_count != new_count THEN
        RAISE EXCEPTION 'Data mismatch in raw_metrics_daily: old=%, new=%', old_count, new_count;
    END IF;
    
    RAISE NOTICE 'Data integrity verified successfully';
END $$;

-- ========================================
-- Step 7: Update foreign key references
-- ========================================

-- Update any views or functions that reference the old tables
-- (This would need to be customized based on your specific dependencies)

-- ========================================
-- Step 8: Create partition maintenance function
-- ========================================

CREATE OR REPLACE FUNCTION prop_trading_model.create_monthly_partitions() RETURNS void AS $$
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
            CREATE TABLE prop_trading_model.%I PARTITION OF prop_trading_model.raw_trades_closed
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            next_month,
            next_month + INTERVAL '1 month'
        );
        
        RAISE NOTICE 'Created partition: %', partition_name;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Step 9: Drop old tables (do this only after verification)
-- ========================================

-- DO NOT RUN IMMEDIATELY - Keep old tables for rollback capability
-- DROP TABLE prop_trading_model.raw_trades_closed_old;
-- DROP TABLE prop_trading_model.raw_metrics_daily_old;

-- ========================================
-- Step 10: Update migration log
-- ========================================

INSERT INTO prop_trading_model.alembic_version (version_num) 
VALUES ('001_add_partitioning');

COMMIT;

-- ========================================
-- Post-migration tasks
-- ========================================

-- Analyze all partitions
ANALYZE prop_trading_model.raw_trades_closed;
ANALYZE prop_trading_model.raw_metrics_daily;

-- Note: Schedule the old table drops for after successful verification
-- Create a reminder in pipeline_execution_log
INSERT INTO prop_trading_model.pipeline_execution_log (
    pipeline_stage,
    execution_date,
    start_time,
    end_time,
    status,
    execution_details
) VALUES (
    'partitioning_migration',
    CURRENT_DATE,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    'success',
    jsonb_build_object(
        'action', 'completed',
        'old_tables_retained', true,
        'reminder', 'Drop _old tables after 7 days if no issues'
    )
);