-- Enable pg_cron extension for scheduled jobs
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Grant usage on cron schema to postgres role
GRANT USAGE ON SCHEMA cron TO postgres;

-- Schedule daily partition creation at 11:00 PM
-- This ensures partitions are created 3 months ahead for all partitioned tables
SELECT cron.schedule(
    'create-future-partitions',
    '0 23 * * *',  -- Every day at 11 PM
    $$
    SELECT prop_trading_model.ensure_partitions_exist('raw_metrics_daily', 3);
    SELECT prop_trading_model.ensure_partitions_exist('raw_metrics_hourly', 3);
    SELECT prop_trading_model.ensure_partitions_exist('raw_trades_closed', 3);
    SELECT prop_trading_model.ensure_partitions_exist('raw_trades_open', 3);
    $$
);

-- Create a function for partition cleanup that pg_cron can call
CREATE OR REPLACE FUNCTION prop_trading_model.cleanup_old_partitions()
RETURNS void AS $$
DECLARE
    partition_rec record;
    parent_table text;
    oldest_data_date date;
    newest_data_date date;
    partition_date date;
    row_count bigint;
BEGIN
    -- Process each partitioned table
    FOR parent_table IN
        SELECT DISTINCT split_part(tablename, '_20', 1) as base_table
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
    LOOP
        -- Find the actual data range for this table
        EXECUTE format('
            SELECT MIN(date), MAX(date) 
            FROM prop_trading_model.%I 
            WHERE date IS NOT NULL
        ', parent_table) INTO oldest_data_date, newest_data_date;
        
        -- Skip if no data found
        CONTINUE WHEN oldest_data_date IS NULL;
        
        -- Check each partition for this table
        FOR partition_rec IN
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'prop_trading_model' 
            AND tablename LIKE parent_table || '_20%'
            AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
        LOOP
            -- Extract date from partition name (format: table_YYYY_MM)
            partition_date := to_date(right(partition_rec.tablename, 7), 'YYYY_MM');
            
            -- Only consider partitions outside the data range
            IF partition_date < date_trunc('month', oldest_data_date) OR 
               partition_date > date_trunc('month', newest_data_date + interval '1 month') THEN
               
                -- Check if partition is actually empty
                EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', partition_rec.tablename) 
                INTO row_count;
                
                -- Drop only if truly empty and outside data range
                IF row_count = 0 THEN
                    EXECUTE format('DROP TABLE prop_trading_model.%I', partition_rec.tablename);
                    RAISE NOTICE 'Dropped empty partition outside data range: %', partition_rec.tablename;
                ELSE
                    RAISE NOTICE 'Keeping non-empty partition: % (% rows)', partition_rec.tablename, row_count;
                END IF;
            END IF;
        END LOOP;
        
        RAISE NOTICE 'Cleanup completed for %: data range % to %', parent_table, oldest_data_date, newest_data_date;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Schedule monthly cleanup using the function
SELECT cron.schedule(
    'cleanup-unused-partitions',
    '0 2 1 * *',  -- First day of month at 2 AM
    'SELECT prop_trading_model.cleanup_old_partitions();'
);

-- Create a view to monitor scheduled jobs
CREATE OR REPLACE VIEW prop_trading_model.partition_cron_jobs AS
SELECT 
    jobid,
    jobname,
    schedule,
    command,
    nodename,
    nodeport,
    database,
    username,
    active
FROM cron.job
WHERE jobname IN ('create-future-partitions', 'cleanup-unused-partitions');

-- Create a function to manually trigger partition creation
CREATE OR REPLACE FUNCTION prop_trading_model.manually_create_partitions(
    months_ahead integer DEFAULT 3
) RETURNS TABLE (
    table_name text,
    partitions_created integer
) AS $$
BEGIN
    -- Create partitions for all partitioned tables
    table_name := 'raw_metrics_daily';
    partitions_created := prop_trading_model.ensure_partitions_exist(table_name, months_ahead);
    RETURN NEXT;
    
    table_name := 'raw_metrics_hourly';
    partitions_created := prop_trading_model.ensure_partitions_exist(table_name, months_ahead);
    RETURN NEXT;
    
    table_name := 'raw_trades_closed';
    partitions_created := prop_trading_model.ensure_partitions_exist(table_name, months_ahead);
    RETURN NEXT;
    
    table_name := 'raw_trades_open';
    partitions_created := prop_trading_model.ensure_partitions_exist(table_name, months_ahead);
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- Drop existing view if it exists and recreate
DROP VIEW IF EXISTS prop_trading_model.partition_status;
CREATE VIEW prop_trading_model.partition_status AS
WITH partition_info AS (
    SELECT 
        split_part(tablename, '_20', 1) as parent_table,
        tablename as partition_name,
        to_date(right(tablename, 7), 'YYYY_MM') as partition_month,
        pg_size_pretty(pg_total_relation_size('prop_trading_model.' || tablename)) as size
    FROM pg_tables 
    WHERE schemaname = 'prop_trading_model' 
    AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
)
SELECT 
    parent_table,
    COUNT(*) as total_partitions,
    MIN(partition_month) as oldest_partition,
    MAX(partition_month) as newest_partition,
    SUM(pg_total_relation_size('prop_trading_model.' || partition_name))::bigint as total_size_bytes,
    pg_size_pretty(SUM(pg_total_relation_size('prop_trading_model.' || partition_name))::bigint) as total_size
FROM partition_info
GROUP BY parent_table
ORDER BY parent_table;

-- Add comment explaining the automation
COMMENT ON VIEW prop_trading_model.partition_cron_jobs IS 
'Shows the scheduled pg_cron jobs for automatic partition management. 
- create-future-partitions: Runs daily at 11 PM to ensure partitions exist 3 months ahead
- cleanup-unused-partitions: Runs monthly on the 1st at 2 AM to remove empty partitions outside data range';

COMMENT ON FUNCTION prop_trading_model.manually_create_partitions IS 
'Manually trigger partition creation for all partitioned tables. 
Default creates 3 months ahead, but can specify custom months_ahead parameter.';

COMMENT ON VIEW prop_trading_model.partition_status IS 
'Overview of all partitioned tables showing partition count, date range, and total size.';