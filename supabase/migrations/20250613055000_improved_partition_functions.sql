-- Improved partition migration functions based on lessons learned
-- This migration updates the existing functions to handle large tables better

-- Drop the old problematic function
DROP FUNCTION IF EXISTS prop_trading_model.copy_data_to_partitioned(text, integer);

-- Create improved copy function that processes data in smaller batches
-- and provides better progress tracking
CREATE OR REPLACE FUNCTION prop_trading_model.copy_data_to_partitioned(
    table_name text,
    batch_days integer DEFAULT 1,
    max_days_per_transaction integer DEFAULT 30
) RETURNS text AS $$
DECLARE
    date_col text;
    min_date date;
    max_date date;
    resume_date date;
    curr_date date;
    end_batch_date date;
    total_rows bigint := 0;
    batch_rows bigint;
    old_table text;
    rows_before bigint;
    rows_after bigint;
    days_processed integer := 0;
BEGIN
    old_table := table_name || '_old';
    
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    -- Get current row count before starting
    EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name) INTO rows_before;
    
    -- Get date range from old table
    EXECUTE format('SELECT MIN(%I::date), MAX(%I::date) FROM prop_trading_model.%I WHERE %I IS NOT NULL',
                   date_col, date_col, old_table, date_col) 
    INTO min_date, max_date;
    
    -- Find where to resume from (day after the last date in new table)
    EXECUTE format('SELECT COALESCE(MAX(%I::date), %L::date - interval ''1 day'')::date FROM prop_trading_model.%I',
                   date_col, min_date, table_name) 
    INTO resume_date;
    
    -- Start from the next day after what we've already copied
    curr_date := resume_date + interval '1 day';
    
    -- Calculate end date for this batch (limit days per transaction)
    end_batch_date := LEAST(curr_date + (max_days_per_transaction || ' days')::interval - interval '1 day', max_date);
    
    -- Log where we're starting from
    RAISE NOTICE 'Processing from % to % (max % days)', curr_date, end_batch_date, max_days_per_transaction;
    
    -- Copy data in daily batches
    WHILE curr_date <= end_batch_date AND curr_date <= max_date LOOP
        -- Copy batch
        EXECUTE format('
            INSERT INTO prop_trading_model.%I 
            SELECT * FROM prop_trading_model.%I 
            WHERE %I::date = %L',
            table_name, old_table, date_col, curr_date
        );
        
        GET DIAGNOSTICS batch_rows = ROW_COUNT;
        
        IF batch_rows > 0 THEN
            total_rows := total_rows + batch_rows;
            RAISE NOTICE 'Copied % rows for %', batch_rows, curr_date;
        END IF;
        
        days_processed := days_processed + 1;
        curr_date := curr_date + interval '1 day';
    END LOOP;
    
    -- Get final row count
    EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name) INTO rows_after;
    
    -- Check if migration is complete
    DECLARE
        original_count bigint;
    BEGIN
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', old_table) INTO original_count;
        
        IF rows_after = original_count THEN
            -- Success - safe to drop the old table
            RETURN format('Migration complete! Copied all %s rows. Old table (%s) can be dropped.', 
                         rows_after, old_table);
        ELSE
            -- Return progress info
            RETURN format('Processed %s days, copied %s rows in this batch. Total: %s/%s rows (%.1f%%). Run again to continue.',
                         days_processed, total_rows, rows_after, original_count, 
                         (rows_after::numeric / original_count * 100));
        END IF;
    END;
END;
$$ LANGUAGE plpgsql;

-- Create a helper function for autonomous batch processing
-- This function processes smaller chunks and is designed to work within timeout constraints
CREATE OR REPLACE FUNCTION prop_trading_model.migrate_table_in_batches(
    table_name text,
    days_per_run integer DEFAULT 30
) RETURNS TABLE (
    status text,
    rows_copied bigint,
    total_rows bigint,
    original_rows bigint,
    percent_complete numeric,
    message text
) AS $$
DECLARE
    result text;
    old_table text;
    new_count bigint;
    old_count bigint;
BEGIN
    old_table := table_name || '_old';
    
    -- Check if old table exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename = old_table
    ) THEN
        RETURN QUERY SELECT 
            'ERROR'::text,
            0::bigint,
            0::bigint,
            0::bigint,
            0::numeric,
            format('Table %s not found. Run convert_to_partitioned_optimized first.', old_table)::text;
        RETURN;
    END IF;
    
    -- Run the copy function
    result := prop_trading_model.copy_data_to_partitioned(table_name, 1, days_per_run);
    
    -- Get current counts
    EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name) INTO new_count;
    EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', old_table) INTO old_count;
    
    -- Return status
    RETURN QUERY SELECT 
        CASE 
            WHEN new_count = old_count THEN 'COMPLETE'
            ELSE 'IN_PROGRESS'
        END::text as status,
        new_count - COALESCE(LAG(new_count) OVER (), 0) as rows_copied,
        new_count as total_rows,
        old_count as original_rows,
        ROUND((new_count::numeric / NULLIF(old_count, 0) * 100), 2) as percent_complete,
        result as message;
END;
$$ LANGUAGE plpgsql;

-- Create an improved check function that shows better progress info
CREATE OR REPLACE FUNCTION prop_trading_model.check_partition_migration_status(
    table_name text
) RETURNS jsonb AS $$
DECLARE
    old_exists boolean;
    new_exists boolean;
    new_is_partitioned boolean;
    old_count bigint := 0;
    new_count bigint := 0;
    date_col text;
    min_migrated date;
    max_migrated date;
    next_to_migrate date;
    days_remaining integer;
    estimated_time_remaining interval;
    avg_rows_per_day numeric;
BEGIN
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    -- Check if old table exists
    SELECT EXISTS(
        SELECT 1 FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename = table_name || '_old'
    ) INTO old_exists;
    
    -- Check new table
    SELECT EXISTS(
        SELECT 1 FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename = table_name
    ) INTO new_exists;
    
    IF new_exists THEN
        SELECT c.relkind = 'p' INTO new_is_partitioned
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prop_trading_model' AND c.relname = table_name;
    END IF;
    
    -- Get counts if tables exist
    IF old_exists THEN
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name || '_old') INTO old_count;
    END IF;
    
    IF new_exists THEN
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name) INTO new_count;
        EXECUTE format('SELECT MIN(%I::date), MAX(%I::date) FROM prop_trading_model.%I WHERE %I IS NOT NULL',
                       date_col, date_col, table_name, date_col) 
        INTO min_migrated, max_migrated;
    END IF;
    
    -- Calculate remaining work
    IF old_exists AND new_exists AND max_migrated IS NOT NULL THEN
        EXECUTE format('
            SELECT 
                MIN(%I::date),
                COUNT(DISTINCT %I::date),
                AVG(day_rows)
            FROM (
                SELECT %I::date, COUNT(*) as day_rows
                FROM prop_trading_model.%I
                WHERE %I::date > %L
                GROUP BY %I::date
            ) t',
            date_col, date_col, date_col, table_name || '_old', date_col, max_migrated, date_col
        ) INTO next_to_migrate, days_remaining, avg_rows_per_day;
        
        -- Estimate time remaining (assuming 10K rows per second)
        IF avg_rows_per_day IS NOT NULL AND days_remaining IS NOT NULL THEN
            estimated_time_remaining := make_interval(secs => (avg_rows_per_day * days_remaining / 10000)::integer);
        END IF;
    END IF;
    
    RETURN jsonb_build_object(
        'old_table_exists', old_exists,
        'new_table_exists', new_exists,
        'new_table_is_partitioned', new_is_partitioned,
        'old_table_rows', old_count,
        'new_table_rows', new_count,
        'migration_progress', CASE 
            WHEN old_count > 0 THEN round((new_count::numeric / old_count) * 100, 2) 
            ELSE 0 
        END,
        'migrated_date_range', jsonb_build_object('min', min_migrated, 'max', max_migrated),
        'next_date_to_migrate', next_to_migrate,
        'days_remaining', days_remaining,
        'estimated_time_remaining', estimated_time_remaining::text,
        'status', CASE
            WHEN NOT old_exists AND new_is_partitioned THEN 'READY'
            WHEN old_exists AND NOT new_exists THEN 'NOT_STARTED'
            WHEN old_count = new_count AND old_count > 0 THEN 'COMPLETE'
            WHEN new_count > 0 AND new_count < old_count THEN 'IN_PROGRESS'
            ELSE 'UNKNOWN'
        END
    );
END;
$$ LANGUAGE plpgsql;

-- Update permissions
GRANT EXECUTE ON FUNCTION prop_trading_model.copy_data_to_partitioned TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.migrate_table_in_batches TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.check_partition_migration_status TO postgres;

-- Add helpful comments
COMMENT ON FUNCTION prop_trading_model.copy_data_to_partitioned IS 
'Improved version that copies data in daily batches with configurable transaction size. 
Automatically resumes from where it left off. Limits to 30 days per run by default to avoid timeouts.';

COMMENT ON FUNCTION prop_trading_model.migrate_table_in_batches IS 
'Helper function to run migration in batches. Returns status information. 
Run repeatedly until status = COMPLETE.';

COMMENT ON FUNCTION prop_trading_model.check_partition_migration_status IS 
'Enhanced status check that provides detailed migration progress including time estimates.';