-- Fix copy_data_to_partitioned to resume from where it left off
CREATE OR REPLACE FUNCTION prop_trading_model.copy_data_to_partitioned(
    table_name text,
    batch_days integer DEFAULT 7
) RETURNS text AS $$
DECLARE
    date_col text;
    min_date date;
    max_date date;
    resume_date date;
    curr_date date;
    next_date date;
    total_rows bigint := 0;
    batch_rows bigint;
    old_table text;
    rows_before bigint;
    rows_after bigint;
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
    EXECUTE format('SELECT MIN(%I), MAX(%I) FROM prop_trading_model.%I WHERE %I IS NOT NULL',
                   date_col, date_col, old_table, date_col) 
    INTO min_date, max_date;
    
    -- Find where to resume from (day after the last date in new table)
    EXECUTE format('SELECT COALESCE(MAX(%I), %L::date - interval ''1 day'')::date FROM prop_trading_model.%I',
                   date_col, min_date, table_name) 
    INTO resume_date;
    
    -- Start from the next day after what we've already copied
    curr_date := resume_date + interval '1 day';
    
    -- Log where we're starting from
    RAISE NOTICE 'Resuming from %, copying to %', curr_date, max_date;
    
    -- Copy data in batches
    WHILE curr_date <= max_date LOOP
        next_date := LEAST(curr_date + (batch_days || ' days')::interval, max_date + interval '1 day')::date;
        
        -- Copy batch
        EXECUTE format('
            INSERT INTO prop_trading_model.%I 
            SELECT * FROM prop_trading_model.%I 
            WHERE %I >= %L AND %I < %L',
            table_name, old_table, date_col, curr_date, date_col, next_date
        );
        
        GET DIAGNOSTICS batch_rows = ROW_COUNT;
        total_rows := total_rows + batch_rows;
        
        RAISE NOTICE 'Copied % rows for period % to %', batch_rows, curr_date, next_date - interval '1 day';
        
        curr_date := next_date;
    END LOOP;
    
    -- Get final row count
    EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name) INTO rows_after;
    
    -- Validate final counts
    DECLARE
        original_count bigint;
    BEGIN
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', old_table) INTO original_count;
        
        IF rows_after = original_count THEN
            -- Success - drop the old table
            EXECUTE format('DROP TABLE prop_trading_model.%I', old_table);
            RETURN format('Successfully migrated %s rows. Old table dropped.', rows_after);
        ELSE
            -- Return progress info
            RETURN format('Copied %s rows in this batch. Total: %s/%s rows (%.1f%%). Run again to continue.',
                         total_rows, rows_after, original_count, 
                         (rows_after::numeric / original_count * 100));
        END IF;
    END;
END;
$$ LANGUAGE plpgsql;

-- Also create a helper function to check what dates need to be migrated
CREATE OR REPLACE FUNCTION prop_trading_model.check_migration_dates(
    table_name text
) RETURNS TABLE (
    last_migrated_date date,
    next_date_to_migrate date,
    final_date_to_migrate date,
    days_remaining integer
) AS $$
DECLARE
    date_col text;
    old_table text;
BEGIN
    old_table := table_name || '_old';
    
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    RETURN QUERY
    SELECT 
        (SELECT MAX(d)::date FROM (SELECT unnest(ARRAY[date_col])::date as d FROM prop_trading_model.raw_metrics_hourly) t) as last_migrated,
        (SELECT MAX(d)::date + interval '1 day' FROM (SELECT unnest(ARRAY[date_col])::date as d FROM prop_trading_model.raw_metrics_hourly) t)::date as next_to_migrate,
        (SELECT MAX(d)::date FROM (SELECT unnest(ARRAY[date_col])::date as d FROM prop_trading_model.raw_metrics_hourly_old) t) as final_date,
        (SELECT EXTRACT(DAY FROM 
            (SELECT MAX(d)::date FROM (SELECT unnest(ARRAY[date_col])::date as d FROM prop_trading_model.raw_metrics_hourly_old) t) -
            COALESCE((SELECT MAX(d)::date FROM (SELECT unnest(ARRAY[date_col])::date as d FROM prop_trading_model.raw_metrics_hourly) t), 
                    (SELECT MIN(d)::date FROM (SELECT unnest(ARRAY[date_col])::date as d FROM prop_trading_model.raw_metrics_hourly_old) t) - interval '1 day')
        ))::integer as days_left;
EXCEPTION WHEN OTHERS THEN
    -- Simplified version if the dynamic query fails
    RETURN QUERY
    EXECUTE format('
        SELECT 
            (SELECT MAX(%I::date) FROM prop_trading_model.%I) as last_migrated,
            (SELECT COALESCE(MAX(%I::date), (SELECT MIN(%I::date) - interval ''1 day'' FROM prop_trading_model.%I)) + interval ''1 day'')::date as next_to_migrate,
            (SELECT MAX(%I::date) FROM prop_trading_model.%I) as final_date,
            0 as days_left
        ', date_col, table_name, date_col, date_col, old_table, date_col, old_table);
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT EXECUTE ON FUNCTION prop_trading_model.check_migration_dates TO postgres;

-- Add documentation
COMMENT ON FUNCTION prop_trading_model.copy_data_to_partitioned IS 
'Fixed version that resumes from where it left off instead of starting from the beginning each time.';

COMMENT ON FUNCTION prop_trading_model.check_migration_dates IS 
'Helper function to see what dates still need to be migrated.';