-- Migration: Fix Trade Account IDs
-- Created: 2025-06-15
-- Purpose: Replace MD5 hash account_ids with actual account_ids from raw_metrics_alltime
-- ------------------------------------------------------------

-- 1. Fix closed trades with MD5 hash account_ids
UPDATE prop_trading_model.raw_trades_closed t
SET account_id = m.account_id
FROM prop_trading_model.raw_metrics_alltime m
WHERE t.login = m.login
  AND t.platform = m.platform
  AND t.broker = m.broker
  AND LENGTH(t.account_id) = 32  -- MD5 hashes are 32 characters
  AND t.account_id ~ '^[0-9a-f]{32}$';  -- Matches MD5 pattern

-- 2. Fix open trades with MD5 hash account_ids
UPDATE prop_trading_model.raw_trades_open t
SET account_id = m.account_id
FROM prop_trading_model.raw_metrics_alltime m
WHERE t.login = m.login
  AND t.platform = m.platform
  AND t.broker = m.broker
  AND LENGTH(t.account_id) = 32  -- MD5 hashes are 32 characters
  AND t.account_id ~ '^[0-9a-f]{32}$';  -- Matches MD5 pattern

-- 3. Log summary of fixes
DO $$
DECLARE
    closed_fixed INTEGER;
    open_fixed INTEGER;
    closed_unmatched INTEGER;
    open_unmatched INTEGER;
BEGIN
    -- Count fixed records
    SELECT COUNT(*) INTO closed_fixed
    FROM prop_trading_model.raw_trades_closed
    WHERE account_id IS NOT NULL
    AND LENGTH(account_id) != 32;
    
    SELECT COUNT(*) INTO open_fixed
    FROM prop_trading_model.raw_trades_open
    WHERE account_id IS NOT NULL
    AND LENGTH(account_id) != 32;
    
    -- Count remaining MD5 hashes (unmatched)
    SELECT COUNT(*) INTO closed_unmatched
    FROM prop_trading_model.raw_trades_closed
    WHERE LENGTH(account_id) = 32
    AND account_id ~ '^[0-9a-f]{32}$';
    
    SELECT COUNT(*) INTO open_unmatched
    FROM prop_trading_model.raw_trades_open
    WHERE LENGTH(account_id) = 32
    AND account_id ~ '^[0-9a-f]{32}$';
    
    RAISE NOTICE 'Account ID Fix Summary:';
    RAISE NOTICE '  Closed trades fixed: %', closed_fixed;
    RAISE NOTICE '  Open trades fixed: %', open_fixed;
    RAISE NOTICE '  Closed trades unmatched: %', closed_unmatched;
    RAISE NOTICE '  Open trades unmatched: %', open_unmatched;
END $$;