-- Migration: Trade Reconciliation Core Objects
-- Created automatically by AI on 2025-06-13
-- ------------------------------------------------------------
-- NOTE: run via `npx supabase db push --linked` (user action)

-- 1. trade_recon table -----------------------------------------------------
CREATE TABLE IF NOT EXISTS prop_trading_model.trade_recon (
    account_id             VARCHAR(255) PRIMARY KEY,
    has_alltime            BOOLEAN      NOT NULL DEFAULT FALSE,
    num_trades_alltime     INTEGER,
    has_daily              BOOLEAN      NOT NULL DEFAULT FALSE,
    num_trades_daily       INTEGER,
    has_hourly             BOOLEAN      NOT NULL DEFAULT FALSE,
    num_trades_hourly      INTEGER,
    has_raw_closed         BOOLEAN      NOT NULL DEFAULT FALSE,
    num_trades_raw_closed  INTEGER,
    trades_recon_checksum  BOOLEAN      NOT NULL DEFAULT FALSE,
    issues                 JSONB        DEFAULT '[]'::jsonb,
    last_checked           TIMESTAMPTZ  DEFAULT NOW(),
    last_reconciled        TIMESTAMPTZ,
    failed_attempts        INTEGER      DEFAULT 0,
    last_failed_attempt    TIMESTAMPTZ,
    created_at             TIMESTAMPTZ  DEFAULT NOW()
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_trade_recon_checksum ON prop_trading_model.trade_recon (trades_recon_checksum);
CREATE INDEX IF NOT EXISTS idx_trade_recon_last_checked ON prop_trading_model.trade_recon (last_checked);

-- 2. Materialized view with ALL account_ids -------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS prop_trading_model.mv_all_account_ids AS
SELECT DISTINCT account_id FROM (
    SELECT account_id FROM prop_trading_model.raw_metrics_alltime WHERE account_id IS NOT NULL
    UNION
    SELECT account_id FROM prop_trading_model.raw_metrics_daily  WHERE account_id IS NOT NULL
    UNION
    SELECT account_id FROM prop_trading_model.raw_metrics_hourly WHERE account_id IS NOT NULL
    UNION
    SELECT account_id FROM prop_trading_model.raw_trades_closed  WHERE account_id IS NOT NULL
) t;

CREATE INDEX IF NOT EXISTS idx_mv_all_account_ids ON prop_trading_model.mv_all_account_ids (account_id);

-- 3. PL/pgSQL function to update stats ------------------------------------
CREATE OR REPLACE FUNCTION prop_trading_model.update_trade_recon_stats(p_account_id VARCHAR)
RETURNS VOID AS $$
BEGIN
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
        trades_recon_checksum
    )
    SELECT 
        p_account_id,
        COALESCE(a.has_alltime, FALSE),
        a.num_trades_alltime,
        COALESCE(d.has_daily, FALSE),
        d.num_trades_daily,
        COALESCE(h.has_hourly, FALSE),
        h.num_trades_hourly,
        COALESCE(c.has_closed, FALSE),
        c.num_trades_closed,
        CASE 
            WHEN a.num_trades_alltime IS NOT NULL 
                 AND a.num_trades_alltime = d.num_trades_daily 
                 AND a.num_trades_alltime = h.num_trades_hourly 
                 AND a.num_trades_alltime = c.num_trades_closed 
            THEN TRUE
            WHEN a.num_trades_alltime IS NULL 
                 AND d.num_trades_daily  IS NULL 
                 AND h.num_trades_hourly IS NULL 
                 AND c.num_trades_closed IS NULL
            THEN TRUE
            ELSE FALSE
        END
    FROM 
        (SELECT 
            COUNT(*) > 0 AS has_alltime,
            MAX(num_trades) AS num_trades_alltime
         FROM prop_trading_model.raw_metrics_alltime 
         WHERE account_id = p_account_id) a,
        (SELECT 
            COUNT(*) > 0 AS has_daily,
            SUM(num_trades) AS num_trades_daily
         FROM prop_trading_model.raw_metrics_daily 
         WHERE account_id = p_account_id) d,
        (SELECT 
            COUNT(*) > 0 AS has_hourly,
            SUM(num_trades) AS num_trades_hourly
         FROM prop_trading_model.raw_metrics_hourly 
         WHERE account_id = p_account_id) h,
        (SELECT 
            COUNT(*) > 0 AS has_closed,
            COUNT(*)   AS num_trades_closed
         FROM prop_trading_model.raw_trades_closed 
         WHERE account_id = p_account_id) c
    ON CONFLICT (account_id) DO UPDATE SET
        has_alltime           = EXCLUDED.has_alltime,
        num_trades_alltime    = EXCLUDED.num_trades_alltime,
        has_daily             = EXCLUDED.has_daily,
        num_trades_daily      = EXCLUDED.num_trades_daily,
        has_hourly            = EXCLUDED.has_hourly,
        num_trades_hourly     = EXCLUDED.num_trades_hourly,
        has_raw_closed        = EXCLUDED.has_raw_closed,
        num_trades_raw_closed = EXCLUDED.num_trades_raw_closed,
        trades_recon_checksum = EXCLUDED.trades_recon_checksum,
        last_checked          = NOW();
END;
$$ LANGUAGE plpgsql;

-- 4. Permissions (optional) -----------------------------------------------
-- GRANT SELECT, INSERT, UPDATE, DELETE ON prop_trading_model.trade_recon TO api_role; 