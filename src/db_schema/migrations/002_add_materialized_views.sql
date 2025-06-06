-- Migration: 002_add_materialized_views.sql
-- Version: 2.0.0 (Balanced)
-- Description: Create materialized views for common aggregations
-- Author: Database Schema Architect
-- Date: 2025-01-06

BEGIN;

-- ========================================
-- Account Performance Summary
-- ========================================

CREATE MATERIALIZED VIEW IF NOT EXISTS prop_trading_model.mv_account_performance_summary AS
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
    COALESCE(m.total_trades, 0) as lifetime_trades,
    COALESCE(m.net_profit, 0) as lifetime_profit,
    COALESCE(m.gross_profit, 0) as lifetime_gross_profit,
    COALESCE(m.gross_loss, 0) as lifetime_gross_loss,
    COALESCE(m.win_rate, 0) as lifetime_win_rate,
    COALESCE(m.profit_factor, 0) as lifetime_profit_factor,
    COALESCE(m.sharpe_ratio, 0) as lifetime_sharpe_ratio,
    COALESCE(m.sortino_ratio, 0) as lifetime_sortino_ratio,
    COALESCE(m.max_drawdown_pct, 0) as lifetime_max_drawdown_pct,
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
    a.updated_at as last_updated,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM (
    SELECT DISTINCT ON (account_id) *
    FROM prop_trading_model.raw_accounts_data
    ORDER BY account_id, ingestion_timestamp DESC
) a
LEFT JOIN prop_trading_model.raw_plans_data p ON a.plan_id = p.plan_id
LEFT JOIN (
    SELECT DISTINCT ON (account_id) *
    FROM prop_trading_model.raw_metrics_alltime
    ORDER BY account_id, ingestion_timestamp DESC
) m ON a.account_id = m.account_id
LEFT JOIN LATERAL (
    SELECT 
        account_id,
        SUM(total_trades) as trades_last_30d,
        SUM(net_profit) as profit_last_30d,
        COUNT(DISTINCT date) as trading_days_last_30d,
        CASE 
            WHEN SUM(total_trades) > 0 
            THEN SUM(winning_trades)::DECIMAL / SUM(total_trades) * 100
            ELSE 0 
        END as win_rate_last_30d
    FROM prop_trading_model.raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY account_id
) daily ON true
LEFT JOIN LATERAL (
    SELECT 
        account_id,
        SUM(total_trades) as trades_last_7d,
        SUM(net_profit) as profit_last_7d,
        CASE 
            WHEN SUM(total_trades) > 0 
            THEN SUM(winning_trades)::DECIMAL / SUM(total_trades) * 100
            ELSE 0 
        END as win_rate_last_7d
    FROM prop_trading_model.raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY account_id
) weekly ON true
WITH DATA;

-- Create indexes (with existence checks)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_account_performance_account_id') THEN
        CREATE UNIQUE INDEX idx_mv_account_performance_account_id 
            ON prop_trading_model.mv_account_performance_summary(account_id);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_account_performance_status') THEN
        CREATE INDEX idx_mv_account_performance_status 
            ON prop_trading_model.mv_account_performance_summary(status) 
            WHERE status = 'Active';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_account_performance_phase') THEN
        CREATE INDEX idx_mv_account_performance_phase 
            ON prop_trading_model.mv_account_performance_summary(phase);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_account_performance_profit') THEN
        CREATE INDEX idx_mv_account_performance_profit 
            ON prop_trading_model.mv_account_performance_summary(lifetime_profit DESC);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_account_performance_recent_profit') THEN
        CREATE INDEX idx_mv_account_performance_recent_profit 
            ON prop_trading_model.mv_account_performance_summary(profit_last_30d DESC);
    END IF;
END $$;

-- ========================================
-- Daily Trading Statistics
-- ========================================

CREATE MATERIALIZED VIEW IF NOT EXISTS prop_trading_model.mv_daily_trading_stats AS
SELECT 
    date,
    COUNT(DISTINCT account_id) as active_accounts,
    COUNT(DISTINCT CASE WHEN net_profit > 0 THEN account_id END) as profitable_accounts,
    COUNT(DISTINCT CASE WHEN net_profit < 0 THEN account_id END) as losing_accounts,
    SUM(total_trades) as total_trades,
    SUM(winning_trades) as total_winning_trades,
    SUM(losing_trades) as total_losing_trades,
    SUM(net_profit) as total_profit,
    SUM(gross_profit) as total_gross_profit,
    SUM(gross_loss) as total_gross_loss,
    AVG(net_profit) as avg_profit,
    STDDEV(net_profit) as profit_stddev,
    SUM(volume_traded) as total_volume,
    SUM(lots_traded) as total_lots,
    AVG(win_rate) as avg_win_rate,
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
FROM prop_trading_model.raw_metrics_daily
WHERE date >= CURRENT_DATE - INTERVAL '365 days'
GROUP BY date
WITH DATA;

-- Create indexes (with existence checks)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_daily_stats_date') THEN
        CREATE UNIQUE INDEX idx_mv_daily_stats_date 
            ON prop_trading_model.mv_daily_trading_stats(date);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_daily_stats_year_month') THEN
        CREATE INDEX idx_mv_daily_stats_year_month 
            ON prop_trading_model.mv_daily_trading_stats(year, month);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_daily_stats_dow') THEN
        CREATE INDEX idx_mv_daily_stats_dow 
            ON prop_trading_model.mv_daily_trading_stats(day_of_week);
    END IF;
END $$;

-- ========================================
-- Symbol Performance Statistics
-- ========================================

CREATE MATERIALIZED VIEW IF NOT EXISTS prop_trading_model.mv_symbol_performance AS
WITH symbol_stats AS (
    SELECT 
        std_symbol,
        COUNT(DISTINCT account_id) as traders_count,
        COUNT(*) as total_trades,
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
    FROM prop_trading_model.raw_trades_closed
    WHERE trade_date >= CURRENT_DATE - INTERVAL '90 days'
        AND std_symbol IS NOT NULL
    GROUP BY std_symbol
    HAVING COUNT(*) > 100  -- Only symbols with significant activity
)
SELECT 
    std_symbol,
    traders_count,
    total_trades,
    total_profit,
    avg_profit,
    profit_stddev,
    winning_trades,
    losing_trades,
    gross_profit,
    gross_loss,
    CASE 
        WHEN total_trades > 0 
        THEN winning_trades::DECIMAL / total_trades * 100 
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

-- Create indexes (with existence checks)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_symbol_performance_symbol') THEN
        CREATE UNIQUE INDEX idx_mv_symbol_performance_symbol 
            ON prop_trading_model.mv_symbol_performance(std_symbol);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_symbol_performance_profit') THEN
        CREATE INDEX idx_mv_symbol_performance_profit 
            ON prop_trading_model.mv_symbol_performance(total_profit DESC);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_symbol_performance_trades') THEN
        CREATE INDEX idx_mv_symbol_performance_trades 
            ON prop_trading_model.mv_symbol_performance(total_trades DESC);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_symbol_performance_win_rate') THEN
        CREATE INDEX idx_mv_symbol_performance_win_rate 
            ON prop_trading_model.mv_symbol_performance(win_rate DESC);
    END IF;
END $$;

-- ========================================
-- Account Trading Patterns
-- ========================================

CREATE MATERIALIZED VIEW IF NOT EXISTS prop_trading_model.mv_account_trading_patterns AS
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
    FROM prop_trading_model.raw_trades_closed
    WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
)
SELECT 
    account_id,
    login,
    COUNT(*) as total_trades_30d,
    -- Symbol concentration
    COUNT(DISTINCT std_symbol) as unique_symbols,
    MODE() WITHIN GROUP (ORDER BY std_symbol) as favorite_symbol,
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

-- Create indexes (with existence checks)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_trading_patterns_account_id') THEN
        CREATE UNIQUE INDEX idx_mv_trading_patterns_account_id 
            ON prop_trading_model.mv_account_trading_patterns(account_id);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_trading_patterns_login') THEN
        CREATE INDEX idx_mv_trading_patterns_login 
            ON prop_trading_model.mv_account_trading_patterns(login);
    END IF;
END $$;

-- ========================================
-- Market Regime Performance
-- ========================================

CREATE MATERIALIZED VIEW IF NOT EXISTS prop_trading_model.mv_market_regime_performance AS
SELECT 
    r.date,
    r.summary->>'market_sentiment' as market_sentiment,
    r.summary->>'volatility_regime' as volatility_regime,
    r.summary->>'liquidity_state' as liquidity_state,
    COUNT(DISTINCT m.account_id) as active_accounts,
    SUM(m.total_trades) as total_trades,
    SUM(m.net_profit) as total_profit,
    AVG(m.net_profit) as avg_profit,
    STDDEV(m.net_profit) as profit_stddev,
    AVG(m.win_rate) as avg_win_rate,
    SUM(m.volume_traded) as total_volume,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.net_profit) as median_profit,
    COUNT(DISTINCT CASE WHEN m.net_profit > 0 THEN m.account_id END) as profitable_accounts,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM prop_trading_model.raw_regimes_daily r
INNER JOIN prop_trading_model.raw_metrics_daily m ON r.date = m.date
WHERE r.date >= CURRENT_DATE - INTERVAL '180 days'
    AND r.summary IS NOT NULL
GROUP BY r.date, r.summary
WITH DATA;

-- Create indexes (with existence checks)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_regime_performance_date') THEN
        CREATE INDEX idx_mv_regime_performance_date 
            ON prop_trading_model.mv_market_regime_performance(date DESC);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_mv_regime_performance_sentiment') THEN
        CREATE INDEX idx_mv_regime_performance_sentiment 
            ON prop_trading_model.mv_market_regime_performance(market_sentiment);
    END IF;
END $$;

-- ========================================
-- Create Refresh Functions
-- ========================================

CREATE OR REPLACE FUNCTION prop_trading_model.refresh_materialized_views() RETURNS void AS $$
BEGIN
    -- Refresh views in dependency order
    REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_daily_trading_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_symbol_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_account_performance_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_account_trading_patterns;
    REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_market_regime_performance;
    
    -- Log refresh
    INSERT INTO prop_trading_model.pipeline_execution_log (
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

-- ========================================
-- Update Migration Log
-- ========================================

INSERT INTO prop_trading_model.alembic_version (version_num) 
VALUES ('002_add_materialized_views');

COMMIT;

-- ========================================
-- Post-migration: Schedule refresh
-- ========================================

-- Add to scheduled jobs
INSERT INTO prop_trading_model.scheduled_jobs (job_name, schedule, command) 
VALUES ('refresh_materialized_views', '0 */2 * * *', 'SELECT prop_trading_model.refresh_materialized_views();')
ON CONFLICT (job_name) DO UPDATE SET schedule = EXCLUDED.schedule;

-- Initial refresh
SELECT prop_trading_model.refresh_materialized_views();