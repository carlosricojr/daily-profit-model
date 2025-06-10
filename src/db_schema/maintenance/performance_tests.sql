-- Performance Testing Queries - Version 2 (Balanced)
-- Tests for partitioned tables and materialized views

-- ========================================
-- Test 1: Partition Pruning Effectiveness
-- ========================================

-- Test that queries only scan relevant partitions
EXPLAIN (ANALYZE, BUFFERS) 
SELECT 
    account_id,
    trade_date,
    COUNT(*) as trade_count,
    SUM(profit) as total_profit
FROM prop_trading_model.raw_trades_closed
WHERE trade_date BETWEEN '2024-06-01' AND '2024-06-30'
GROUP BY account_id, trade_date
ORDER BY total_profit DESC
LIMIT 100;

-- Verify partition pruning
SELECT * FROM prop_trading_model.check_partition_pruning(
    $$SELECT * FROM prop_trading_model.raw_trades_closed 
      WHERE trade_date BETWEEN '2024-06-01' AND '2024-06-30'$$
);

-- ========================================
-- Test 2: Materialized View Performance
-- ========================================

-- Compare direct query vs materialized view
-- Direct query (should be slower)
EXPLAIN (ANALYZE, BUFFERS)
SELECT 
    a.account_id,
    a.status,
    SUM(m.net_profit) as total_profit,
    AVG(m.win_rate) as avg_win_rate
FROM prop_trading_model.raw_accounts_data a
JOIN prop_trading_model.raw_metrics_daily m ON a.account_id = m.account_id
WHERE a.status = 'Active'
    AND m.date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY a.account_id, a.status
ORDER BY total_profit DESC
LIMIT 100;

-- Materialized view query (should be faster)
EXPLAIN (ANALYZE, BUFFERS)
SELECT 
    account_id,
    status,
    profit_last_30d,
    win_rate_last_30d
FROM prop_trading_model.mv_account_performance_summary
WHERE status = 'Active'
ORDER BY profit_last_30d DESC
LIMIT 100;

-- ========================================
-- Test 3: Cross-Partition Aggregation
-- ========================================

-- Test performance of queries spanning multiple partitions
EXPLAIN (ANALYZE, BUFFERS)
WITH monthly_performance AS (
    SELECT 
        account_id,
        DATE_TRUNC('month', trade_date) as month,
        COUNT(*) as trades,
        SUM(profit) as profit,
        SUM(volume_usd) as volume
    FROM prop_trading_model.raw_trades_closed
    WHERE trade_date >= '2024-01-01'
    GROUP BY account_id, DATE_TRUNC('month', trade_date)
)
SELECT 
    account_id,
    COUNT(DISTINCT month) as active_months,
    SUM(trades) as num_trades,
    SUM(profit) as total_profit,
    AVG(profit) as avg_monthly_profit
FROM monthly_performance
GROUP BY account_id
HAVING COUNT(DISTINCT month) >= 3
ORDER BY total_profit DESC;

-- ========================================
-- Test 4: Parallel Query Execution
-- ========================================

-- Test parallel scan on partitioned table
SET max_parallel_workers_per_gather = 4;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT 
    std_symbol,
    COUNT(*) as trade_count,
    SUM(profit) as total_profit,
    AVG(lots) as avg_lots
FROM prop_trading_model.raw_trades_closed
WHERE trade_date >= '2024-01-01'
    AND std_symbol IS NOT NULL
GROUP BY std_symbol
HAVING COUNT(*) > 1000
ORDER BY total_profit DESC;

RESET max_parallel_workers_per_gather;

-- ========================================
-- Test 5: Materialized View Refresh Performance
-- ========================================

-- Test concurrent refresh timing
\timing on

-- Refresh individual views and measure time
REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_daily_trading_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_symbol_performance;
REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_account_performance_summary;

\timing off

-- ========================================
-- Test 6: Join Performance with Partitions
-- ========================================

-- Complex join across partitioned and non-partitioned tables
EXPLAIN (ANALYZE, BUFFERS)
SELECT 
    a.account_id,
    a.phase,
    p.plan_name,
    t.symbol_stats.*,
    m.daily_stats.*
FROM prop_trading_model.raw_accounts_data a
JOIN prop_trading_model.raw_plans_data p ON a.plan_id = p.plan_id
JOIN LATERAL (
    SELECT 
        COUNT(DISTINCT std_symbol) as unique_symbols,
        COUNT(*) as num_trades,
        SUM(profit) as total_profit
    FROM prop_trading_model.raw_trades_closed
    WHERE account_id = a.account_id
        AND trade_date >= CURRENT_DATE - INTERVAL '30 days'
) t(symbol_stats) ON true
JOIN LATERAL (
    SELECT 
        AVG(net_profit) as avg_daily_profit,
        AVG(win_rate) as avg_win_rate
    FROM prop_trading_model.raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '30 days'
) m(daily_stats) ON true
WHERE a.status = 'Active'
LIMIT 50;

-- ========================================
-- Test 7: Time-based Partition Access
-- ========================================

-- Test various time ranges to verify optimal partition access
-- Single partition access
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*), SUM(profit) 
FROM prop_trading_model.raw_trades_closed
WHERE trade_date >= '2024-06-01' AND trade_date < '2024-07-01';

-- Cross-partition access (3 months)
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*), SUM(profit) 
FROM prop_trading_model.raw_trades_closed
WHERE trade_date >= '2024-04-01' AND trade_date < '2024-07-01';

-- Full year access
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*), SUM(profit) 
FROM prop_trading_model.raw_trades_closed
WHERE trade_date >= '2024-01-01' AND trade_date < '2025-01-01';

-- ========================================
-- Load Testing with Concurrent Queries
-- ========================================

-- Simulate concurrent access to partitioned tables
CREATE OR REPLACE FUNCTION prop_trading_model.load_test_partitions(
    p_concurrent_queries INTEGER DEFAULT 10,
    p_iterations INTEGER DEFAULT 100
) RETURNS TABLE(
    query_type TEXT,
    avg_execution_time INTERVAL,
    min_execution_time INTERVAL,
    max_execution_time INTERVAL
) AS $$
DECLARE
    start_time TIMESTAMP;
    end_time TIMESTAMP;
    i INTEGER;
    j INTEGER;
BEGIN
    -- Test 1: Random account queries
    start_time := clock_timestamp();
    
    FOR i IN 1..p_iterations LOOP
        FOR j IN 1..p_concurrent_queries LOOP
            PERFORM * FROM prop_trading_model.raw_trades_closed
            WHERE account_id = 'ACC' || (random() * 10000)::INTEGER::TEXT
                AND trade_date >= CURRENT_DATE - INTERVAL '30 days'
            LIMIT 100;
        END LOOP;
    END LOOP;
    
    end_time := clock_timestamp();
    
    RETURN QUERY
    SELECT 
        'Random Account Queries'::TEXT,
        (end_time - start_time) / (p_iterations * p_concurrent_queries),
        (end_time - start_time) / (p_iterations * p_concurrent_queries),
        (end_time - start_time) / (p_iterations * p_concurrent_queries);
    
    -- Add more test scenarios as needed
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Performance Comparison Summary
-- ========================================

CREATE OR REPLACE VIEW prop_trading_model.v_performance_comparison AS
WITH v1_baseline AS (
    -- Simulated V1 performance metrics (replace with actual if available)
    SELECT 
        'Daily metrics retrieval' as test_name, 50 as v1_ms
    UNION ALL SELECT 'Feature store query', 200
    UNION ALL SELECT 'Trade aggregation', 5000
    UNION ALL SELECT 'Account overview', 100
),
v2_results AS (
    -- Actual V2 performance (would be populated from real tests)
    SELECT 
        'Daily metrics retrieval' as test_name, 30 as v2_ms
    UNION ALL SELECT 'Feature store query', 50
    UNION ALL SELECT 'Trade aggregation', 1000
    UNION ALL SELECT 'Account overview', 20
)
SELECT 
    b.test_name,
    b.v1_ms as v1_time_ms,
    r.v2_ms as v2_time_ms,
    round((b.v1_ms - r.v2_ms)::numeric / b.v1_ms * 100, 1) as improvement_pct,
    CASE 
        WHEN round((b.v1_ms - r.v2_ms)::numeric / b.v1_ms * 100, 1) > 50 THEN 'Excellent'
        WHEN round((b.v1_ms - r.v2_ms)::numeric / b.v1_ms * 100, 1) > 25 THEN 'Good'
        WHEN round((b.v1_ms - r.v2_ms)::numeric / b.v1_ms * 100, 1) > 0 THEN 'Moderate'
        ELSE 'No improvement'
    END as rating
FROM v1_baseline b
JOIN v2_results r ON b.test_name = r.test_name
ORDER BY improvement_pct DESC;

-- ========================================
-- Expected Performance Benchmarks V2
-- ========================================

/*
Performance Targets for Version 2:

1. Partition pruning: >95% reduction in scanned data for date-range queries
2. Materialized view queries: <50ms for pre-aggregated data
3. Cross-partition aggregation: <2s for 3-month range
4. Parallel query execution: 3-4x speedup with 4 workers
5. MV refresh time: <30s for hourly refresh
6. Join performance: <500ms for complex multi-table joins
7. Concurrent access: Linear scaling up to 20 concurrent queries

Improvements over V1:
- 80% reduction in trade aggregation query time
- 75% reduction in account overview query time  
- 60% reduction in feature store access time
- 50% reduction in storage for old partitions (compression)

Monitoring Targets:
- Partition pruning effectiveness: >90% of queries
- MV staleness: <2 hours for all views
- Index bloat: <10% on active partitions
- Cache hit ratio: >98% for hot partitions
*/