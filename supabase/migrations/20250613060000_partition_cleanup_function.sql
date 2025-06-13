-- Add cleanup function for partition migrations
-- This function verifies migration success and safely cleans up

CREATE OR REPLACE FUNCTION prop_trading_model.finalize_partition_migration(
    table_name text,
    safety_checks boolean DEFAULT true
) RETURNS jsonb AS $$
DECLARE
    old_table text;
    old_count bigint;
    new_count bigint;
    old_min_date timestamp;
    old_max_date timestamp;
    new_min_date timestamp;
    new_max_date timestamp;
    old_distinct_days integer;
    new_distinct_days integer;
    old_accounts integer;
    new_accounts integer;
    date_col text;
    sample_match boolean;
    result jsonb;
BEGIN
    old_table := table_name || '_old';
    
    -- Determine date column
    date_col := CASE 
        WHEN table_name IN ('raw_trades_closed', 'raw_trades_open') THEN 'trade_date'
        ELSE 'date'
    END;
    
    -- Check if old table exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename = old_table
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Old table does not exist',
            'message', format('Table %s not found', old_table)
        );
    END IF;
    
    -- Get comprehensive statistics from both tables
    EXECUTE format('
        SELECT COUNT(*), MIN(%I), MAX(%I), COUNT(DISTINCT %I::date), COUNT(DISTINCT account_id)
        FROM prop_trading_model.%I',
        date_col, date_col, date_col, old_table
    ) INTO old_count, old_min_date, old_max_date, old_distinct_days, old_accounts;
    
    EXECUTE format('
        SELECT COUNT(*), MIN(%I), MAX(%I), COUNT(DISTINCT %I::date), COUNT(DISTINCT account_id)
        FROM prop_trading_model.%I',
        date_col, date_col, date_col, table_name
    ) INTO new_count, new_min_date, new_max_date, new_distinct_days, new_accounts;
    
    -- Perform safety checks if enabled
    IF safety_checks THEN
        -- Check 1: Row counts must match
        IF old_count != new_count THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Row count mismatch',
                'old_count', old_count,
                'new_count', new_count,
                'difference', old_count - new_count
            );
        END IF;
        
        -- Check 2: Date ranges must match
        IF old_min_date != new_min_date OR old_max_date != new_max_date THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Date range mismatch',
                'old_date_range', jsonb_build_object('min', old_min_date, 'max', old_max_date),
                'new_date_range', jsonb_build_object('min', new_min_date, 'max', new_max_date)
            );
        END IF;
        
        -- Check 3: Distinct days must match
        IF old_distinct_days != new_distinct_days THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Distinct days mismatch',
                'old_distinct_days', old_distinct_days,
                'new_distinct_days', new_distinct_days
            );
        END IF;
        
        -- Check 4: Account counts must match
        IF old_accounts != new_accounts THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Account count mismatch',
                'old_accounts', old_accounts,
                'new_accounts', new_accounts
            );
        END IF;
        
        -- Check 5: Sample data verification (pick a random date)
        EXECUTE format('
            WITH sample_date AS (
                SELECT %I::date as check_date
                FROM prop_trading_model.%I
                WHERE %I IS NOT NULL
                ORDER BY RANDOM()
                LIMIT 1
            )
            SELECT 
                (SELECT COUNT(*) FROM prop_trading_model.%I WHERE %I::date = (SELECT check_date FROM sample_date)) =
                (SELECT COUNT(*) FROM prop_trading_model.%I WHERE %I::date = (SELECT check_date FROM sample_date))
            ',
            date_col, old_table, date_col, old_table, date_col, table_name, date_col
        ) INTO sample_match;
        
        IF NOT sample_match THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Sample data verification failed',
                'message', 'Random sample check showed different row counts'
            );
        END IF;
    END IF;
    
    -- All checks passed - proceed with cleanup
    BEGIN
        -- Drop the old table
        EXECUTE format('DROP TABLE prop_trading_model.%I CASCADE', old_table);
        
        -- Build success result
        result := jsonb_build_object(
            'success', true,
            'action', 'Migration finalized',
            'old_table_dropped', old_table,
            'rows_migrated', new_count,
            'date_range', jsonb_build_object('min', new_min_date, 'max', new_max_date),
            'distinct_days', new_distinct_days,
            'distinct_accounts', new_accounts,
            'message', format('Successfully migrated %s rows to partitioned table %s', new_count, table_name)
        );
        
        -- Note: VACUUM should be run separately as it cannot be run in a transaction
        result := result || jsonb_build_object(
            'next_step', format('Run VACUUM ANALYZE prop_trading_model.%s; to optimize the table', table_name)
        );
        
        RETURN result;
        
    EXCEPTION WHEN OTHERS THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Failed to drop old table',
            'detail', SQLERRM
        );
    END;
END;
$$ LANGUAGE plpgsql;

-- Create a function to run vacuum on partitioned tables (must be called separately)
CREATE OR REPLACE FUNCTION prop_trading_model.vacuum_partitioned_table(
    table_name text,
    full_vacuum boolean DEFAULT false
) RETURNS TABLE (
    partition_name text,
    status text
) AS $$
DECLARE
    partition record;
    vacuum_cmd text;
BEGIN
    -- Vacuum parent table
    vacuum_cmd := CASE 
        WHEN full_vacuum THEN 'VACUUM FULL ANALYZE prop_trading_model.%I'
        ELSE 'VACUUM ANALYZE prop_trading_model.%I'
    END;
    
    BEGIN
        EXECUTE format(vacuum_cmd, table_name);
        RETURN QUERY SELECT table_name, 'Vacuumed parent table'::text;
    EXCEPTION WHEN OTHERS THEN
        RETURN QUERY SELECT table_name, format('Error: %s', SQLERRM)::text;
    END;
    
    -- Vacuum each partition
    FOR partition IN 
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename LIKE table_name || '_%'
        AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
        ORDER BY tablename
    LOOP
        BEGIN
            EXECUTE format(vacuum_cmd, partition.tablename);
            RETURN QUERY SELECT partition.tablename, 'Vacuumed'::text;
        EXCEPTION WHEN OTHERS THEN
            RETURN QUERY SELECT partition.tablename, format('Error: %s', SQLERRM)::text;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Create a procedure to orchestrate the entire migration process
-- Procedures can COMMIT, unlike functions
CREATE OR REPLACE PROCEDURE prop_trading_model.migrate_table_to_partitioned(
    p_table_name text,
    p_days_per_batch integer DEFAULT 30
) 
LANGUAGE plpgsql
AS $$
DECLARE
    migration_status jsonb;
    batch_result text;
    total_batches integer := 0;
    max_batches integer := 100; -- Safety limit
BEGIN
    -- First check if table needs conversion
    migration_status := prop_trading_model.check_partition_migration_status(p_table_name);
    
    IF migration_status->>'status' = 'READY' THEN
        RAISE NOTICE 'Table % is already partitioned', p_table_name;
        RETURN;
    END IF;
    
    -- If not started, run the conversion
    IF migration_status->>'status' = 'NOT_STARTED' THEN
        RAISE NOTICE 'Converting % to partitioned table...', p_table_name;
        PERFORM prop_trading_model.convert_to_partitioned_optimized(p_table_name);
        COMMIT; -- Commit the table structure changes
    END IF;
    
    -- Copy data in batches
    WHILE total_batches < max_batches LOOP
        batch_result := prop_trading_model.copy_data_to_partitioned(p_table_name, 1, p_days_per_batch);
        COMMIT; -- Commit after each batch
        
        total_batches := total_batches + 1;
        RAISE NOTICE 'Batch %: %', total_batches, batch_result;
        
        -- Check if migration is complete
        IF batch_result LIKE '%Migration complete!%' THEN
            RAISE NOTICE 'Migration completed successfully!';
            EXIT;
        END IF;
        
        -- Safety check
        migration_status := prop_trading_model.check_partition_migration_status(p_table_name);
        IF migration_status->>'status' = 'COMPLETE' THEN
            EXIT;
        END IF;
    END LOOP;
    
    -- Final status
    migration_status := prop_trading_model.check_partition_migration_status(p_table_name);
    RAISE NOTICE 'Final status: %', migration_status;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION prop_trading_model.finalize_partition_migration TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.vacuum_partitioned_table TO postgres;
GRANT EXECUTE ON PROCEDURE prop_trading_model.migrate_table_to_partitioned TO postgres;

-- Add documentation
COMMENT ON FUNCTION prop_trading_model.finalize_partition_migration IS 
'Verifies migration was successful and drops the old table. 
Performs comprehensive safety checks unless disabled.
Returns JSON with success status and details.';

COMMENT ON FUNCTION prop_trading_model.vacuum_partitioned_table IS 
'Runs VACUUM ANALYZE on a partitioned table and all its partitions.
Set full_vacuum=true for VACUUM FULL (requires more time and locks).';

COMMENT ON PROCEDURE prop_trading_model.migrate_table_to_partitioned IS 
'Complete migration procedure that handles conversion and data copy with automatic commits.
Can handle large tables by committing after each batch. 
Note: Can only be called via CALL statement, not SELECT.';