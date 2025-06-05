-- Partition Index Management - Version 2 (Balanced)
-- Scripts for managing indexes on partitioned tables

-- ========================================
-- Partition Index Analysis
-- ========================================

-- View to monitor partition sizes and index usage
CREATE OR REPLACE VIEW prop_trading_model.v_partition_stats AS
SELECT 
    parent.relname as parent_table,
    child.relname as partition_name,
    pg_size_pretty(pg_relation_size(child.oid)) as partition_size,
    pg_size_pretty(pg_indexes_size(child.oid)) as indexes_size,
    pg_size_pretty(pg_total_relation_size(child.oid)) as total_size,
    child.reltuples::bigint as estimated_rows,
    CASE 
        WHEN parent.relname = 'raw_trades_closed' THEN
            substring(child.relname from '\d{4}_\d{2}$')
        WHEN parent.relname = 'raw_metrics_daily' THEN
            substring(child.relname from '\d{4}$')
        ELSE NULL
    END as partition_key,
    (pg_stat_get_live_tuples(child.oid) + pg_stat_get_dead_tuples(child.oid))::float / 
        NULLIF(pg_stat_get_live_tuples(child.oid), 0) * 100 as bloat_pct
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
JOIN pg_namespace n ON parent.relnamespace = n.oid
WHERE n.nspname = 'prop_trading_model'
ORDER BY parent.relname, child.relname;

-- ========================================
-- Automated Index Creation for New Partitions
-- ========================================

CREATE OR REPLACE FUNCTION prop_trading_model.create_partition_indexes(
    p_parent_table TEXT,
    p_partition_name TEXT
) RETURNS void AS $$
BEGIN
    IF p_parent_table = 'raw_trades_closed' THEN
        -- Create indexes for trades partition
        EXECUTE format('
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (trade_date);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id, trade_date);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (login);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (std_symbol) WHERE std_symbol IS NOT NULL;
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (profit) WHERE profit != 0;
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (trade_id);',
            'idx_' || p_partition_name || '_account_id', p_partition_name,
            'idx_' || p_partition_name || '_trade_date', p_partition_name,
            'idx_' || p_partition_name || '_account_date', p_partition_name,
            'idx_' || p_partition_name || '_login', p_partition_name,
            'idx_' || p_partition_name || '_symbol', p_partition_name,
            'idx_' || p_partition_name || '_profit', p_partition_name,
            'idx_' || p_partition_name || '_trade_id', p_partition_name
        );
        
    ELSIF p_parent_table = 'raw_metrics_daily' THEN
        -- Create indexes for metrics partition
        EXECUTE format('
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (date DESC);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (account_id, date DESC);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (login);
            CREATE INDEX CONCURRENTLY IF NOT EXISTS %I ON prop_trading_model.%I (login, date DESC);',
            'idx_' || p_partition_name || '_account_id', p_partition_name,
            'idx_' || p_partition_name || '_date', p_partition_name,
            'idx_' || p_partition_name || '_account_date', p_partition_name,
            'idx_' || p_partition_name || '_login', p_partition_name,
            'idx_' || p_partition_name || '_login_date', p_partition_name
        );
    END IF;
    
    -- Analyze the new partition
    EXECUTE format('ANALYZE prop_trading_model.%I', p_partition_name);
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Partition Index Usage Monitoring
-- ========================================

CREATE OR REPLACE VIEW prop_trading_model.v_partition_index_usage AS
WITH partition_indexes AS (
    SELECT 
        schemaname,
        tablename,
        indexname,
        idx_scan,
        idx_tup_read,
        idx_tup_fetch,
        pg_relation_size(indexrelid) as index_size
    FROM pg_stat_user_indexes
    WHERE schemaname = 'prop_trading_model'
        AND (tablename LIKE 'raw_trades_closed_%' OR tablename LIKE 'raw_metrics_daily_%')
)
SELECT 
    CASE 
        WHEN tablename LIKE 'raw_trades_closed_%' THEN 'raw_trades_closed'
        WHEN tablename LIKE 'raw_metrics_daily_%' THEN 'raw_metrics_daily'
    END as parent_table,
    tablename as partition_name,
    indexname,
    idx_scan,
    idx_tup_read,
    pg_size_pretty(index_size) as index_size,
    CASE 
        WHEN idx_scan = 0 THEN 'UNUSED'
        WHEN idx_scan < 100 THEN 'RARELY USED'
        WHEN idx_scan < 1000 THEN 'OCCASIONALLY USED'
        ELSE 'FREQUENTLY USED'
    END as usage_category
FROM partition_indexes
ORDER BY parent_table, partition_name, idx_scan DESC;

-- ========================================
-- Partition Maintenance Procedures
-- ========================================

-- Function to drop unused partition indexes
CREATE OR REPLACE FUNCTION prop_trading_model.drop_unused_partition_indexes(
    p_min_age_days INTEGER DEFAULT 30,
    p_dry_run BOOLEAN DEFAULT TRUE
) RETURNS TABLE(
    partition_name TEXT,
    index_name TEXT,
    index_size TEXT,
    last_used TIMESTAMP,
    drop_command TEXT
) AS $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN 
        SELECT 
            i.schemaname,
            i.tablename,
            i.indexname,
            pg_size_pretty(pg_relation_size(i.indexrelid)) as size_pretty,
            s.last_idx_scan
        FROM pg_stat_user_indexes i
        JOIN pg_stat_user_tables s ON i.tablename = s.relname AND i.schemaname = s.schemaname
        WHERE i.schemaname = 'prop_trading_model'
            AND (i.tablename LIKE 'raw_trades_closed_%' OR i.tablename LIKE 'raw_metrics_daily_%')
            AND i.idx_scan = 0
            AND (CURRENT_TIMESTAMP - s.last_idx_scan > p_min_age_days * INTERVAL '1 day' 
                 OR s.last_idx_scan IS NULL)
    LOOP
        partition_name := rec.tablename;
        index_name := rec.indexname;
        index_size := rec.size_pretty;
        last_used := rec.last_idx_scan;
        drop_command := format('DROP INDEX IF EXISTS %I.%I;', rec.schemaname, rec.indexname);
        
        IF NOT p_dry_run THEN
            EXECUTE drop_command;
        END IF;
        
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Partition Constraint Exclusion Check
-- ========================================

-- Function to verify constraint exclusion is working
CREATE OR REPLACE FUNCTION prop_trading_model.check_partition_pruning(
    p_query TEXT
) RETURNS TABLE(
    partition_name TEXT,
    is_scanned BOOLEAN
) AS $$
DECLARE
    plan_json JSONB;
    partition_rec RECORD;
BEGIN
    -- Get query plan as JSON
    EXECUTE format('EXPLAIN (FORMAT JSON) %s', p_query) INTO plan_json;
    
    -- Extract scanned relations
    FOR partition_rec IN 
        SELECT child.relname as partition_name
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        JOIN pg_namespace n ON parent.relnamespace = n.oid
        WHERE n.nspname = 'prop_trading_model'
            AND parent.relname IN ('raw_trades_closed', 'raw_metrics_daily')
    LOOP
        partition_name := partition_rec.partition_name;
        is_scanned := plan_json::text LIKE '%' || partition_rec.partition_name || '%';
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Global Partition Index Creation
-- ========================================

-- Create global indexes that PostgreSQL will maintain across partitions
-- Note: This requires PostgreSQL 11+

-- Global index on raw_trades_closed
CREATE INDEX IF NOT EXISTS idx_global_trades_account_id 
    ON prop_trading_model.raw_trades_closed (account_id);
CREATE INDEX IF NOT EXISTS idx_global_trades_trade_date 
    ON prop_trading_model.raw_trades_closed (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_global_trades_account_date 
    ON prop_trading_model.raw_trades_closed (account_id, trade_date DESC);

-- Global index on raw_metrics_daily
CREATE INDEX IF NOT EXISTS idx_global_metrics_account_id 
    ON prop_trading_model.raw_metrics_daily (account_id);
CREATE INDEX IF NOT EXISTS idx_global_metrics_date 
    ON prop_trading_model.raw_metrics_daily (date DESC);
CREATE INDEX IF NOT EXISTS idx_global_metrics_account_date 
    ON prop_trading_model.raw_metrics_daily (account_id, date DESC);

-- ========================================
-- Index Maintenance Schedule
-- ========================================

CREATE OR REPLACE FUNCTION prop_trading_model.maintain_partition_indexes() RETURNS void AS $$
DECLARE
    partition_rec RECORD;
    old_partitions TIMESTAMP;
BEGIN
    -- Define old partition threshold (e.g., 6 months)
    old_partitions := CURRENT_DATE - INTERVAL '6 months';
    
    -- Reindex old partitions that might be bloated
    FOR partition_rec IN 
        SELECT 
            child.relname as partition_name,
            CASE 
                WHEN child.relname LIKE 'raw_trades_closed_%' THEN 
                    to_date(substring(child.relname from '\d{4}_\d{2}$'), 'YYYY_MM')
                WHEN child.relname LIKE 'raw_metrics_daily_%' THEN 
                    to_date(substring(child.relname from '\d{4}$') || '-01-01', 'YYYY-MM-DD')
            END as partition_date
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        JOIN pg_namespace n ON parent.relnamespace = n.oid
        WHERE n.nspname = 'prop_trading_model'
            AND parent.relname IN ('raw_trades_closed', 'raw_metrics_daily')
    LOOP
        IF partition_rec.partition_date < old_partitions THEN
            -- For old partitions, consider more aggressive maintenance
            EXECUTE format('REINDEX TABLE CONCURRENTLY prop_trading_model.%I', 
                          partition_rec.partition_name);
        ELSE
            -- For recent partitions, just update statistics
            EXECUTE format('ANALYZE prop_trading_model.%I', 
                          partition_rec.partition_name);
        END IF;
    END LOOP;
    
    -- Drop unused indexes on old partitions
    PERFORM prop_trading_model.drop_unused_partition_indexes(
        p_min_age_days := 90,
        p_dry_run := FALSE
    );
    
    -- Log maintenance
    INSERT INTO prop_trading_model.pipeline_execution_log (
        pipeline_stage,
        execution_date,
        start_time,
        end_time,
        status,
        execution_details
    ) VALUES (
        'partition_index_maintenance',
        CURRENT_DATE,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        'success',
        jsonb_build_object('action', 'completed')
    );
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- Index Advisory Queries
-- ========================================

-- Query to suggest missing partition indexes
CREATE OR REPLACE VIEW prop_trading_model.v_partition_index_advisor AS
WITH frequent_queries AS (
    SELECT 
        query,
        calls,
        mean_time,
        query LIKE '%raw_trades_closed%' as uses_trades,
        query LIKE '%raw_metrics_daily%' as uses_metrics
    FROM pg_stat_statements
    WHERE query LIKE '%prop_trading_model%'
        AND mean_time > 100  -- Queries taking more than 100ms
        AND calls > 10
)
SELECT 
    'Consider adding index' as recommendation,
    CASE 
        WHEN uses_trades THEN 'raw_trades_closed'
        WHEN uses_metrics THEN 'raw_metrics_daily'
    END as table_name,
    query,
    calls,
    mean_time
FROM frequent_queries
WHERE uses_trades OR uses_metrics
ORDER BY mean_time DESC
LIMIT 20;