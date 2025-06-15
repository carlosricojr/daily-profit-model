-- Consolidated Partition Management System
-- This migration includes all finalized partition functions after testing

-- Drop old/duplicate functions first
DROP FUNCTION IF EXISTS prop_trading_model.copy_data_to_partitioned_optimized(text);
DROP FUNCTION IF EXISTS prop_trading_model.check_migration_dates(text);

-- Keep only the working, tested versions of functions
-- All other partition functions from previous migrations remain as they are working correctly

-- Create indexes on partitioned tables for better performance
DO $$
DECLARE
    partition_rec record;
BEGIN
    -- Create indexes on all partitions of raw_metrics_hourly
    FOR partition_rec IN
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename LIKE 'raw_metrics_hourly_%'
        AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
    LOOP
        -- Create index on date column if not exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE schemaname = 'prop_trading_model' 
            AND tablename = partition_rec.tablename 
            AND indexname = partition_rec.tablename || '_date_idx'
        ) THEN
            EXECUTE format('CREATE INDEX %I ON prop_trading_model.%I (date)', 
                          partition_rec.tablename || '_date_idx', partition_rec.tablename);
            RAISE NOTICE 'Created index on %.date', partition_rec.tablename;
        END IF;
        
        -- Create index on account_id if not exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE schemaname = 'prop_trading_model' 
            AND tablename = partition_rec.tablename 
            AND indexname = partition_rec.tablename || '_account_id_idx'
        ) THEN
            EXECUTE format('CREATE INDEX %I ON prop_trading_model.%I (account_id)', 
                          partition_rec.tablename || '_account_id_idx', partition_rec.tablename);
            RAISE NOTICE 'Created index on %.account_id', partition_rec.tablename;
        END IF;
    END LOOP;
END $$;

-- Add helpful views for partition monitoring
CREATE OR REPLACE VIEW prop_trading_model.partition_status AS
WITH partition_info AS (
    SELECT 
        schemaname,
        tablename,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
        CASE 
            WHEN tablename ~ '_20[0-9][0-9]_[0-9][0-9]$' 
            THEN to_date(right(tablename, 7), 'YYYY_MM')
            ELSE NULL
        END as partition_month
    FROM pg_tables 
    WHERE schemaname = 'prop_trading_model' 
    AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
),
row_counts AS (
    SELECT 
        relname as tablename,
        n_live_tup as approx_rows
    FROM pg_stat_user_tables
    WHERE schemaname = 'prop_trading_model'
)
SELECT 
    pi.tablename as partition_name,
    pi.partition_month,
    pi.size,
    COALESCE(rc.approx_rows, 0) as approx_rows,
    CASE 
        WHEN pi.partition_month < date_trunc('month', CURRENT_DATE - interval '24 months') THEN 'VERY_OLD'
        WHEN pi.partition_month < date_trunc('month', CURRENT_DATE - interval '12 months') THEN 'OLD'
        WHEN pi.partition_month > date_trunc('month', CURRENT_DATE) THEN 'FUTURE'
        ELSE 'CURRENT'
    END as status
FROM partition_info pi
LEFT JOIN row_counts rc ON pi.tablename = rc.tablename
ORDER BY pi.tablename;

-- Grant permissions on the view
GRANT SELECT ON prop_trading_model.partition_status TO postgres;

COMMENT ON VIEW prop_trading_model.partition_status IS 
'Monitoring view for all partitions showing size, row count, and age status';