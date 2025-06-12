-- =====================================================
-- Partition Monitoring Queries
-- =====================================================
-- Use these queries to monitor the health and performance
-- of partitioned tables in the prop_trading_model schema

-- 1. View all partitions and their sizes
WITH partition_info AS (
    SELECT 
        nmsp_parent.nspname AS parent_schema,
        parent.relname AS parent_table,
        nmsp_child.nspname AS child_schema,
        child.relname AS partition_name,
        pg_size_pretty(pg_relation_size(child.oid)) AS partition_size,
        pg_relation_size(child.oid) AS size_bytes
    FROM pg_inherits
    JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
    JOIN pg_class child ON pg_inherits.inhrelid = child.oid
    JOIN pg_namespace nmsp_parent ON parent.relnamespace = nmsp_parent.oid
    JOIN pg_namespace nmsp_child ON child.relnamespace = nmsp_child.oid
    WHERE nmsp_parent.nspname = 'prop_trading_model'
)
SELECT 
    parent_table,
    partition_name,
    partition_size,
    ROUND(100.0 * size_bytes / SUM(size_bytes) OVER (PARTITION BY parent_table), 2) AS percent_of_table
FROM partition_info
ORDER BY parent_table, partition_name;

-- 2. Check partition row counts and date ranges
WITH partition_stats AS (
    SELECT 
        schemaname,
        tablename,
        CASE 
            WHEN tablename LIKE 'raw_metrics_daily_%' THEN 'raw_metrics_daily'
            WHEN tablename LIKE 'raw_metrics_hourly_%' THEN 'raw_metrics_hourly'
            WHEN tablename LIKE 'raw_trades_%' THEN 'raw_trades'
            ELSE 'other'
        END AS base_table,
        n_live_tup AS row_count,
        n_dead_tup AS dead_rows,
        last_vacuum,
        last_autovacuum
    FROM pg_stat_user_tables
    WHERE schemaname = 'prop_trading_model'
    AND tablename ~ '_y[0-9]{4}m[0-9]{2}$'
)
SELECT 
    base_table,
    tablename AS partition_name,
    TO_CHAR(row_count, '999,999,999') AS row_count,
    TO_CHAR(dead_rows, '999,999,999') AS dead_rows,
    CASE 
        WHEN dead_rows > 0 AND row_count > 0 
        THEN ROUND(100.0 * dead_rows / (row_count + dead_rows), 2) || '%'
        ELSE '0%'
    END AS bloat_percent,
    COALESCE(last_vacuum::text, last_autovacuum::text, 'Never') AS last_maintenance
FROM partition_stats
ORDER BY base_table, partition_name;

-- 3. Identify missing partitions for the next 3 months
WITH RECURSIVE future_months AS (
    SELECT 
        date_trunc('month', CURRENT_DATE) AS month_date
    UNION ALL
    SELECT 
        month_date + INTERVAL '1 month'
    FROM future_months
    WHERE month_date < date_trunc('month', CURRENT_DATE + INTERVAL '3 months')
),
required_partitions AS (
    SELECT 
        table_name,
        month_date,
        table_name || '_y' || to_char(month_date, 'YYYY') || 'm' || to_char(month_date, 'MM') AS partition_name
    FROM (
        SELECT 'raw_metrics_daily' AS table_name
        UNION ALL
        SELECT 'raw_metrics_hourly'
        UNION ALL
        SELECT 'raw_trades_closed'
    ) tables
    CROSS JOIN future_months
),
existing_partitions AS (
    SELECT 
        parent.relname AS parent_table,
        child.relname AS partition_name
    FROM pg_inherits
    JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
    JOIN pg_class child ON pg_inherits.inhrelid = child.oid
    JOIN pg_namespace nmsp ON parent.relnamespace = nmsp.oid
    WHERE nmsp.nspname = 'prop_trading_model'
)
SELECT 
    rp.table_name,
    to_char(rp.month_date, 'YYYY-MM') AS month,
    rp.partition_name,
    CASE 
        WHEN ep.partition_name IS NULL THEN 'MISSING'
        ELSE 'EXISTS'
    END AS status
FROM required_partitions rp
LEFT JOIN existing_partitions ep 
    ON rp.table_name = ep.parent_table 
    AND rp.partition_name = ep.partition_name
WHERE ep.partition_name IS NULL
ORDER BY rp.table_name, rp.month_date;

-- 4. Performance comparison: partitioned vs non-partitioned queries
-- (Run these with EXPLAIN ANALYZE to see partition pruning in action)

-- Example 1: Query that benefits from partition pruning
/*
EXPLAIN (ANALYZE, BUFFERS)
SELECT 
    date,
    COUNT(*) as record_count,
    AVG(net_profit) as avg_profit
FROM prop_trading_model.raw_metrics_hourly
WHERE date >= '2025-06-01' AND date < '2025-07-01'
GROUP BY date
ORDER BY date;
*/

-- Example 2: Query across multiple partitions
/*
EXPLAIN (ANALYZE, BUFFERS)
SELECT 
    account_id,
    COUNT(*) as total_hours,
    SUM(net_profit) as total_profit
FROM prop_trading_model.raw_metrics_hourly
WHERE date >= '2025-01-01'
GROUP BY account_id
HAVING COUNT(*) > 1000
ORDER BY total_profit DESC
LIMIT 100;
*/

-- 5. Check constraint exclusion is enabled (required for partition pruning)
SHOW constraint_exclusion;  -- Should be 'partition' or 'on'

-- 6. Monitor partition creation job (if using pg_cron)
/*
SELECT 
    jobid,
    schedule,
    command,
    nodename,
    nodeport,
    database,
    username,
    active,
    jobname
FROM cron.job
WHERE command LIKE '%create_monthly_partitions%';
*/

-- 7. Quick health check summary
WITH partition_summary AS (
    SELECT 
        parent.relname AS table_name,
        COUNT(*) AS partition_count,
        pg_size_pretty(SUM(pg_relation_size(child.oid))) AS total_size,
        MIN(child.relname) AS oldest_partition,
        MAX(child.relname) AS newest_partition
    FROM pg_inherits
    JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
    JOIN pg_class child ON pg_inherits.inhrelid = child.oid
    JOIN pg_namespace nmsp ON parent.relnamespace = nmsp.oid
    WHERE nmsp.nspname = 'prop_trading_model'
    GROUP BY parent.relname
)
SELECT 
    table_name,
    partition_count,
    total_size,
    oldest_partition,
    newest_partition,
    CASE 
        WHEN table_name = 'raw_metrics_hourly' AND partition_count = 0 
        THEN 'NOT PARTITIONED YET'
        WHEN partition_count > 0 
        THEN 'OK'
        ELSE 'CHECK REQUIRED'
    END AS status
FROM partition_summary
ORDER BY table_name;