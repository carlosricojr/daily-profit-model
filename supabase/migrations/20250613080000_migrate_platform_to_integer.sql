-- Migration: Convert platform, broker, and manager fields in raw_trades_open from VARCHAR to INTEGER
-- Date: 2025-06-13
-- Purpose: Align data types across all tables (should be INTEGER everywhere except ticket which can be string)

BEGIN;

-- Step 1: Add temporary integer columns
ALTER TABLE prop_trading_model.raw_trades_open 
ADD COLUMN platform_int INTEGER,
ADD COLUMN broker_int INTEGER,
ADD COLUMN manager_int INTEGER;

-- Step 2: Convert existing varchar values to integers
UPDATE prop_trading_model.raw_trades_open 
SET platform_int = platform::INTEGER
WHERE platform IS NOT NULL 
  AND platform ~ '^[0-9]+$';  -- Only convert valid numeric strings

UPDATE prop_trading_model.raw_trades_open 
SET broker_int = broker::INTEGER
WHERE broker IS NOT NULL 
  AND broker ~ '^[0-9]+$';

UPDATE prop_trading_model.raw_trades_open 
SET manager_int = manager::INTEGER
WHERE manager IS NOT NULL 
  AND manager ~ '^[0-9]+$';

-- Step 3: Check for any non-numeric values that couldn't be converted
DO $$
DECLARE
    invalid_count INTEGER;
    r RECORD;
BEGIN
    -- Check platform
    SELECT COUNT(*) INTO invalid_count
    FROM prop_trading_model.raw_trades_open
    WHERE platform IS NOT NULL 
      AND platform !~ '^[0-9]+$';
    
    IF invalid_count > 0 THEN
        RAISE NOTICE 'Found % rows with non-numeric platform values', invalid_count;
        FOR r IN 
            SELECT DISTINCT platform, COUNT(*) as count
            FROM prop_trading_model.raw_trades_open
            WHERE platform IS NOT NULL 
              AND platform !~ '^[0-9]+$'
            GROUP BY platform
        LOOP
            RAISE NOTICE 'Invalid platform value: % (count: %)', r.platform, r.count;
        END LOOP;
    END IF;

    -- Check broker
    SELECT COUNT(*) INTO invalid_count
    FROM prop_trading_model.raw_trades_open
    WHERE broker IS NOT NULL 
      AND broker !~ '^[0-9]+$';
    
    IF invalid_count > 0 THEN
        RAISE NOTICE 'Found % rows with non-numeric broker values', invalid_count;
    END IF;

    -- Check manager
    SELECT COUNT(*) INTO invalid_count
    FROM prop_trading_model.raw_trades_open
    WHERE manager IS NOT NULL 
      AND manager !~ '^[0-9]+$';
    
    IF invalid_count > 0 THEN
        RAISE NOTICE 'Found % rows with non-numeric manager values', invalid_count;
    END IF;
END $$;

-- Step 4: Drop the columns from the parent table first (this will cascade to partitions)
ALTER TABLE prop_trading_model.raw_trades_open 
DROP COLUMN platform CASCADE,
DROP COLUMN broker CASCADE,
DROP COLUMN manager CASCADE;

-- Step 5: Rename the temporary columns
ALTER TABLE prop_trading_model.raw_trades_open 
RENAME COLUMN platform_int TO platform;

ALTER TABLE prop_trading_model.raw_trades_open 
RENAME COLUMN broker_int TO broker;

ALTER TABLE prop_trading_model.raw_trades_open 
RENAME COLUMN manager_int TO manager;

-- Step 6: Re-add the NOT NULL constraint for platform
ALTER TABLE prop_trading_model.raw_trades_open 
ALTER COLUMN platform SET NOT NULL;

-- Step 7: Recreate the unique constraint (it was dropped when we dropped the columns)
ALTER TABLE prop_trading_model.raw_trades_open
ADD CONSTRAINT raw_trades_open_position_login_platform_broker_trade_date_key 
UNIQUE (position, login, platform, broker, trade_date);

-- Step 8: Verify the migration
DO $$
DECLARE
    col_type text;
    success_count integer := 0;
BEGIN
    -- Check platform
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'prop_trading_model'
      AND table_name = 'raw_trades_open'
      AND column_name = 'platform';
    
    IF col_type = 'integer' THEN
        RAISE NOTICE 'Platform migration successful: now INTEGER type';
        success_count := success_count + 1;
    ELSE
        RAISE WARNING 'Platform migration failed: still %', col_type;
    END IF;

    -- Check broker
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'prop_trading_model'
      AND table_name = 'raw_trades_open'
      AND column_name = 'broker';
    
    IF col_type = 'integer' THEN
        RAISE NOTICE 'Broker migration successful: now INTEGER type';
        success_count := success_count + 1;
    ELSE
        RAISE WARNING 'Broker migration failed: still %', col_type;
    END IF;

    -- Check manager
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'prop_trading_model'
      AND table_name = 'raw_trades_open'
      AND column_name = 'manager';
    
    IF col_type = 'integer' THEN
        RAISE NOTICE 'Manager migration successful: now INTEGER type';
        success_count := success_count + 1;
    ELSE
        RAISE WARNING 'Manager migration failed: still %', col_type;
    END IF;

    IF success_count = 3 THEN
        RAISE NOTICE 'All migrations successful!';
    ELSE
        RAISE EXCEPTION 'Some migrations failed!';
    END IF;
END $$;

COMMIT;

-- Post-migration: Display statistics
SELECT 
    'Migration Complete' as status,
    COUNT(*) as total_rows,
    COUNT(DISTINCT platform) as unique_platforms,
    COUNT(DISTINCT broker) as unique_brokers,
    COUNT(DISTINCT manager) as unique_managers,
    MIN(platform) as min_platform,
    MAX(platform) as max_platform
FROM prop_trading_model.raw_trades_open;