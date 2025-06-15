-- Migration: Add missing primary key and index to raw_trades_open table
-- Date: 2025-06-13
-- Purpose: Restore primary key and index that were lost during column type migration

-- Add primary key constraint on (platform, position, trade_date)
ALTER TABLE prop_trading_model.raw_trades_open 
ADD CONSTRAINT raw_trades_open_pkey PRIMARY KEY (platform, position, trade_date);

-- Add missing index on login, platform, broker
CREATE INDEX idx_raw_trades_open_login_platform_broker 
ON prop_trading_model.raw_trades_open(login, platform, broker);

-- Verify the primary key was created
DO $$
DECLARE
    pk_exists boolean;
    idx_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 
        FROM information_schema.table_constraints 
        WHERE table_schema = 'prop_trading_model' 
        AND table_name = 'raw_trades_open' 
        AND constraint_type = 'PRIMARY KEY'
    ) INTO pk_exists;
    
    SELECT EXISTS (
        SELECT 1 
        FROM pg_indexes 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename = 'raw_trades_open' 
        AND indexname = 'idx_raw_trades_open_login_platform_broker'
    ) INTO idx_exists;
    
    IF pk_exists THEN
        RAISE NOTICE 'Primary key successfully added to raw_trades_open';
    ELSE
        RAISE EXCEPTION 'Failed to add primary key to raw_trades_open';
    END IF;
    
    IF idx_exists THEN
        RAISE NOTICE 'Index idx_raw_trades_open_login_platform_broker successfully added';
    ELSE
        RAISE WARNING 'Failed to add index idx_raw_trades_open_login_platform_broker';
    END IF;
END $$;