-- Optimized partition conversion that works within statement timeout limits
-- This version creates partitions first, then copies data in smaller chunks

-- Function to convert table with progress tracking
CREATE OR REPLACE FUNCTION prop_trading_model.convert_to_partitioned_optimized(
    table_name text
) RETURNS text AS $$
DECLARE
    date_col text;
    min_date date;
    max_date date;
    rows_converted bigint;
BEGIN
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    -- Get date range
    EXECUTE format('SELECT MIN(%I), MAX(%I) FROM prop_trading_model.%I WHERE %I IS NOT NULL',
                   date_col, date_col, table_name, date_col) 
    INTO min_date, max_date;
    
    -- Check if already partitioned
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prop_trading_model' AND c.relname = table_name AND c.relkind = 'p'
    ) THEN
        RETURN 'Table is already partitioned';
    END IF;
    
    -- Step 1: Rename original table
    EXECUTE format('ALTER TABLE prop_trading_model.%I RENAME TO %I', table_name, table_name || '_old');
    
    -- Step 2: Create new partitioned table with same structure
    EXECUTE format('CREATE TABLE prop_trading_model.%I (LIKE prop_trading_model.%I INCLUDING ALL) PARTITION BY RANGE (%I)',
                   table_name, table_name || '_old', date_col);
    
    -- Step 3: Create all needed partitions
    PERFORM prop_trading_model.ensure_partitions_exist_range(
        table_name,
        (date_trunc('month', min_date) - interval '1 month')::date,
        (date_trunc('month', max_date) + interval '3 months')::date
    );
    
    -- Step 4: Get total row count for progress tracking
    EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name || '_old') INTO rows_converted;
    
    RETURN format('Partitioned table created. Original table renamed to %s. Total rows to migrate: %s. Run copy_data_to_partitioned() to complete migration.',
                  table_name || '_old', rows_converted);
END;
$$ LANGUAGE plpgsql;

-- Separate function to copy data in manageable chunks
CREATE OR REPLACE FUNCTION prop_trading_model.copy_data_to_partitioned(
    table_name text,
    batch_days integer DEFAULT 7  -- Copy 1 week at a time
) RETURNS text AS $$
DECLARE
    date_col text;
    min_date date;
    max_date date;
    curr_date date;
    next_date date;
    total_rows bigint := 0;
    batch_rows bigint;
    old_table text;
BEGIN
    old_table := table_name || '_old';
    
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    -- Get date range from old table
    EXECUTE format('SELECT MIN(%I), MAX(%I) FROM prop_trading_model.%I WHERE %I IS NOT NULL',
                   date_col, date_col, old_table, date_col) 
    INTO min_date, max_date;
    
    -- Copy data in weekly batches
    curr_date := min_date;
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
    
    -- Validate row counts
    DECLARE
        original_count bigint;
        new_count bigint;
    BEGIN
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', old_table) INTO original_count;
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name) INTO new_count;
        
        IF original_count = new_count THEN
            -- Success - drop the old table
            EXECUTE format('DROP TABLE prop_trading_model.%I', old_table);
            RETURN format('Successfully migrated %s rows. Old table dropped.', new_count);
        ELSE
            RETURN format('WARNING: Row count mismatch! Original: %s, New: %s. Old table preserved.', original_count, new_count);
        END IF;
    END;
END;
$$ LANGUAGE plpgsql;

-- Function to check migration status
CREATE OR REPLACE FUNCTION prop_trading_model.check_partition_migration_status(
    table_name text
) RETURNS jsonb AS $$
DECLARE
    old_exists boolean;
    new_exists boolean;
    new_is_partitioned boolean;
    old_count bigint;
    new_count bigint;
    date_col text;
    min_migrated date;
    max_migrated date;
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
        EXECUTE format('SELECT MIN(%I), MAX(%I) FROM prop_trading_model.%I WHERE %I IS NOT NULL',
                       date_col, date_col, table_name, date_col) 
        INTO min_migrated, max_migrated;
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
        'migrated_date_range', jsonb_build_object('min', min_migrated, 'max', max_migrated)
    );
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT EXECUTE ON FUNCTION prop_trading_model.convert_to_partitioned_optimized TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.copy_data_to_partitioned TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.check_partition_migration_status TO postgres;

-- Add documentation
COMMENT ON FUNCTION prop_trading_model.convert_to_partitioned_optimized IS 
'Step 1 of optimized partition conversion. Creates partitioned table structure and renames original table.';

COMMENT ON FUNCTION prop_trading_model.copy_data_to_partitioned IS 
'Step 2 of optimized partition conversion. Copies data in small batches to avoid timeouts.';

COMMENT ON FUNCTION prop_trading_model.check_partition_migration_status IS 
'Check the status of an ongoing partition migration.';