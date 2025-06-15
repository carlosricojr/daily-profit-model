-- Migration: Final Trade Reconciliation Setup
-- Created: 2025-06-15
-- Purpose: Ensure all database objects are properly configured for the enhanced reconciliation
-- ------------------------------------------------------------

-- 1. Ensure trade_recon table has all required columns (idempotent)
ALTER TABLE prop_trading_model.trade_recon 
ADD COLUMN IF NOT EXISTS reconciliation_status VARCHAR(50) DEFAULT 'pending';

-- 2. Update the update_trade_recon_stats function to handle partitioned tables efficiently
CREATE OR REPLACE FUNCTION prop_trading_model.update_trade_recon_stats(p_account_id VARCHAR)
RETURNS VOID AS $$
DECLARE
    v_alltime_count INTEGER;
    v_alltime_trades INTEGER;
    v_daily_count INTEGER;
    v_daily_trades BIGINT;
    v_hourly_count INTEGER;
    v_hourly_trades BIGINT;
    v_closed_count BIGINT;
BEGIN
    -- Set local timeout
    SET LOCAL statement_timeout = '60s';
    
    -- Get alltime metrics (not partitioned)
    SELECT COUNT(*), MAX(num_trades)
    INTO v_alltime_count, v_alltime_trades
    FROM prop_trading_model.raw_metrics_alltime
    WHERE account_id = p_account_id;
    
    -- Get daily metrics (partitioned)
    SELECT COUNT(*), SUM(num_trades)
    INTO v_daily_count, v_daily_trades
    FROM prop_trading_model.raw_metrics_daily
    WHERE account_id = p_account_id;
    
    -- Get hourly metrics (partitioned)
    SELECT COUNT(*), SUM(num_trades)
    INTO v_hourly_count, v_hourly_trades
    FROM prop_trading_model.raw_metrics_hourly
    WHERE account_id = p_account_id;
    
    -- Get closed trades count (partitioned)
    SELECT COUNT(*)
    INTO v_closed_count
    FROM prop_trading_model.raw_trades_closed
    WHERE account_id = p_account_id;
    
    -- Upsert into trade_recon
    INSERT INTO prop_trading_model.trade_recon (
        account_id,
        has_alltime,
        num_trades_alltime,
        has_daily,
        num_trades_daily,
        has_hourly,
        num_trades_hourly,
        has_raw_closed,
        num_trades_raw_closed,
        trades_recon_checksum,
        last_checked
    )
    VALUES (
        p_account_id,
        v_alltime_count > 0,
        v_alltime_trades,
        v_daily_count > 0,
        v_daily_trades,
        v_hourly_count > 0,
        v_hourly_trades,
        v_closed_count > 0,
        v_closed_count,
        -- Checksum passes if all counts match or all are null/zero
        CASE 
            WHEN v_alltime_trades IS NOT NULL AND v_alltime_trades > 0
                AND v_alltime_trades = v_daily_trades 
                AND v_alltime_trades = v_hourly_trades 
                AND v_alltime_trades = v_closed_count 
            THEN TRUE
            WHEN COALESCE(v_alltime_trades, 0) = 0 
                AND COALESCE(v_daily_trades, 0) = 0 
                AND COALESCE(v_hourly_trades, 0) = 0 
                AND COALESCE(v_closed_count, 0) = 0
            THEN TRUE
            ELSE FALSE
        END,
        NOW()
    )
    ON CONFLICT (account_id) DO UPDATE SET
        has_alltime = EXCLUDED.has_alltime,
        num_trades_alltime = EXCLUDED.num_trades_alltime,
        has_daily = EXCLUDED.has_daily,
        num_trades_daily = EXCLUDED.num_trades_daily,
        has_hourly = EXCLUDED.has_hourly,
        num_trades_hourly = EXCLUDED.num_trades_hourly,
        has_raw_closed = EXCLUDED.has_raw_closed,
        num_trades_raw_closed = EXCLUDED.num_trades_raw_closed,
        trades_recon_checksum = EXCLUDED.trades_recon_checksum,
        last_checked = NOW();
END;
$$ LANGUAGE plpgsql;

-- 3. Create helper function to get issue statistics
CREATE OR REPLACE FUNCTION prop_trading_model.get_issue_statistics()
RETURNS TABLE(
    issue_type TEXT,
    severity INTEGER,
    account_count BIGINT,
    sample_accounts TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        issue_obj->>'type' AS issue_type,
        (issue_obj->>'severity')::INTEGER AS severity,
        COUNT(DISTINCT tr.account_id) AS account_count,
        (ARRAY_AGG(DISTINCT tr.account_id ORDER BY tr.account_id))[1:5] AS sample_accounts
    FROM prop_trading_model.trade_recon tr,
         LATERAL jsonb_array_elements(tr.issues) AS issue_obj
    WHERE jsonb_array_length(tr.issues) > 0
    GROUP BY issue_obj->>'type', issue_obj->>'severity'
    ORDER BY severity, account_count DESC;
END;
$$ LANGUAGE plpgsql;

-- 4. Create indexes for better query performance
-- Index for finding accounts that need reconciliation
CREATE INDEX IF NOT EXISTS idx_trade_recon_needs_reconciliation 
ON prop_trading_model.trade_recon(trades_recon_checksum, failed_attempts, last_checked)
WHERE trades_recon_checksum = FALSE;

-- Index for finding accounts with specific issue types
CREATE INDEX IF NOT EXISTS idx_trade_recon_issues 
ON prop_trading_model.trade_recon USING gin(issues);

-- 5. Create a view for monitoring reconciliation progress
CREATE OR REPLACE VIEW prop_trading_model.v_reconciliation_progress AS
SELECT 
    COUNT(*) AS total_accounts,
    COUNT(*) FILTER (WHERE trades_recon_checksum = TRUE) AS reconciled,
    COUNT(*) FILTER (WHERE trades_recon_checksum = FALSE) AS needs_reconciliation,
    COUNT(*) FILTER (WHERE failed_attempts > 0) AS has_failures,
    COUNT(*) FILTER (WHERE jsonb_array_length(issues) > 0) AS has_issues,
    ROUND(100.0 * COUNT(*) FILTER (WHERE trades_recon_checksum = TRUE) / NULLIF(COUNT(*), 0), 2) AS reconciliation_percentage,
    MAX(last_checked) AS last_activity,
    MIN(last_checked) FILTER (WHERE trades_recon_checksum = FALSE) AS oldest_unreconciled
FROM prop_trading_model.trade_recon;

-- 6. Ensure proper permissions
GRANT SELECT ON prop_trading_model.v_reconciliation_progress TO service_role;
GRANT SELECT, INSERT, UPDATE ON prop_trading_model.trade_recon TO service_role;
GRANT EXECUTE ON FUNCTION prop_trading_model.update_trade_recon_stats TO service_role;
GRANT EXECUTE ON FUNCTION prop_trading_model.get_issue_statistics TO service_role;

-- 7. Initialize statistics
ANALYZE prop_trading_model.trade_recon;
ANALYZE prop_trading_model.raw_trades_closed;
ANALYZE prop_trading_model.raw_trades_open;
ANALYZE prop_trading_model.raw_metrics_alltime;
ANALYZE prop_trading_model.raw_metrics_daily;
ANALYZE prop_trading_model.raw_metrics_hourly;