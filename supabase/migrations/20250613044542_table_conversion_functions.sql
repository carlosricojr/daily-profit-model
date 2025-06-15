-- Table Conversion Functions for Zero-Downtime Partitioning
-- Based on Supabase article best practices and partition_migration_manager.py

-- Simple dry run function to analyze conversion requirements
CREATE OR REPLACE FUNCTION prop_trading_model.analyze_table_conversion(
    table_name text
) RETURNS jsonb AS $$
DECLARE
    date_col text;
    min_date date;
    max_date date;
    row_count bigint;
    table_size text;
    is_partitioned boolean;
BEGIN
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    -- Check if already partitioned
    SELECT c.relkind = 'p' INTO is_partitioned
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'prop_trading_model' AND c.relname = table_name;
    
    IF is_partitioned THEN
        RETURN jsonb_build_object(
            'error', 'Table is already partitioned',
            'is_partitioned', true
        );
    END IF;
    
    -- Get table stats
    EXECUTE format('
        SELECT MIN(%I), MAX(%I), COUNT(*), pg_size_pretty(pg_total_relation_size(''prop_trading_model.%I''))
        FROM prop_trading_model.%I WHERE %I IS NOT NULL',
        date_col, date_col, table_name, table_name, date_col
    ) INTO min_date, max_date, row_count, table_size;
    
    RETURN jsonb_build_object(
        'table_name', table_name,
        'date_column', date_col,
        'row_count', row_count,
        'table_size', table_size,
        'date_range', jsonb_build_object('min', min_date, 'max', max_date),
        'months_spanned', EXTRACT(YEAR FROM max_date) * 12 + EXTRACT(MONTH FROM max_date) -
                         (EXTRACT(YEAR FROM min_date) * 12 + EXTRACT(MONTH FROM min_date)) + 1,
        'partitions_needed', EXTRACT(YEAR FROM max_date) * 12 + EXTRACT(MONTH FROM max_date) -
                            (EXTRACT(YEAR FROM min_date) * 12 + EXTRACT(MONTH FROM min_date)) + 4
    );
END;
$$ LANGUAGE plpgsql;

-- Main conversion function - simplified and robust
CREATE OR REPLACE FUNCTION prop_trading_model.convert_to_partitioned(
    table_name text,
    batch_months integer DEFAULT 1  -- Process 1 month at a time by default
) RETURNS text AS $$
DECLARE
    new_table_name text;
    date_col text;
    min_date date;
    max_date date;
    curr_month date;
    next_month date;
    rows_migrated bigint := 0;
    month_rows bigint;
    backup_table_name text;
    idx record;
BEGIN
    -- Validate table exists and isn't already partitioned
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prop_trading_model' AND c.relname = table_name
    ) THEN
        RAISE EXCEPTION 'Table % does not exist', table_name;
    END IF;
    
    -- Check if already partitioned
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prop_trading_model' AND c.relname = table_name AND c.relkind = 'p'
    ) THEN
        RAISE EXCEPTION 'Table % is already partitioned', table_name;
    END IF;
    
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    new_table_name := table_name || '_partitioned';
    
    -- Get date range
    EXECUTE format('SELECT MIN(%I), MAX(%I) FROM prop_trading_model.%I WHERE %I IS NOT NULL',
                   date_col, date_col, table_name, date_col) 
    INTO min_date, max_date;
    
    IF min_date IS NULL THEN
        RAISE EXCEPTION 'No data found in table %', table_name;
    END IF;
    
    RAISE NOTICE 'Converting % to partitioned table. Date range: % to %', table_name, min_date, max_date;
    
    -- Create partitioned table structure
    EXECUTE format('CREATE TABLE prop_trading_model.%I (LIKE prop_trading_model.%I INCLUDING ALL) PARTITION BY RANGE (%I)',
                   new_table_name, table_name, date_col);
    
    -- Create all needed partitions upfront (following Supabase article pattern)
    PERFORM prop_trading_model.ensure_partitions_exist_range(
        new_table_name,
        date_trunc('month', min_date) - interval '1 month',
        date_trunc('month', max_date) + interval '3 months'
    );
    
    -- Migrate data month by month to avoid long locks
    curr_month := date_trunc('month', min_date);
    WHILE curr_month <= date_trunc('month', max_date) LOOP
        next_month := curr_month + (batch_months || ' months')::interval;
        
        -- Copy one month of data
        EXECUTE format('
            INSERT INTO prop_trading_model.%I 
            SELECT * FROM prop_trading_model.%I 
            WHERE %I >= %L AND %I < %L',
            new_table_name, table_name, date_col, curr_month, date_col, next_month
        );
        
        GET DIAGNOSTICS month_rows = ROW_COUNT;
        rows_migrated := rows_migrated + month_rows;
        
        -- Progress update
        IF month_rows > 0 THEN
            RAISE NOTICE 'Migrated % rows for %', month_rows, to_char(curr_month, 'YYYY-MM');
        END IF;
        
        curr_month := next_month;
    END LOOP;
    
    -- Recreate indexes on partitioned table
    FOR idx IN (
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'prop_trading_model' 
        AND tablename = table_name
        AND indexname NOT LIKE '%_pkey'  -- Skip primary key
    ) LOOP
        EXECUTE replace(
            replace(idx.indexdef, table_name, new_table_name),
            idx.indexname, 
            replace(idx.indexname, table_name, new_table_name)
        );
        RAISE NOTICE 'Created index %', replace(idx.indexname, table_name, new_table_name);
    END LOOP;
    
    -- Validate migration
    DECLARE
        original_count bigint;
        new_count bigint;
    BEGIN
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', table_name) INTO original_count;
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', new_table_name) INTO new_count;
        
        IF original_count != new_count THEN
            RAISE EXCEPTION 'Row count mismatch: original=%, new=%', original_count, new_count;
        END IF;
        
        RAISE NOTICE 'Validation passed: % rows migrated', new_count;
    END;
    
    -- Atomic table swap
    backup_table_name := table_name || '_backup_' || to_char(now(), 'YYYYMMDD_HH24MISS');
    EXECUTE format('ALTER TABLE prop_trading_model.%I RENAME TO %I', table_name, backup_table_name);
    EXECUTE format('ALTER TABLE prop_trading_model.%I RENAME TO %I', new_table_name, table_name);
    
    RETURN format('Successfully converted %s to partitioned table. Backup table: %s. Rows migrated: %s',
                  table_name, backup_table_name, rows_migrated);
    
EXCEPTION WHEN OTHERS THEN
    -- Cleanup on error
    EXECUTE format('DROP TABLE IF EXISTS prop_trading_model.%I CASCADE', new_table_name);
    RAISE;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT EXECUTE ON FUNCTION prop_trading_model.analyze_table_conversion TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.convert_to_partitioned TO postgres;

-- Add documentation
COMMENT ON FUNCTION prop_trading_model.analyze_table_conversion IS 
'Analyzes a table to determine conversion requirements for partitioning. 
Returns JSON with table statistics and partition requirements.';

COMMENT ON FUNCTION prop_trading_model.convert_to_partitioned IS 
'Converts a regular table to a partitioned table with minimal downtime. 
Uses month-by-month migration to avoid long locks.
Parameters:
  - table_name: Name of table to convert
  - batch_months: Number of months to process at once (default 1)
Returns success message with backup table name and rows migrated.';