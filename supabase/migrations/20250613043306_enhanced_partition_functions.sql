-- Enhanced Partition Management Functions for Trading Database
-- Based on Supabase dynamic partitioning patterns and existing partition_migration_manager.py

-- Function to create monthly partitions dynamically with enhanced features
CREATE OR REPLACE FUNCTION prop_trading_model.create_monthly_partition(
    parent_table text,
    partition_date date
) RETURNS text AS $$
DECLARE
    partition_name text;
    start_date date;
    end_date date;
    date_column text;
BEGIN
    -- Calculate partition boundaries
    start_date := date_trunc('month', partition_date);
    end_date := start_date + interval '1 month';
    
    -- Generate partition name
    partition_name := parent_table || '_' || to_char(start_date, 'YYYY_MM');
    
    -- Determine date column based on table
    CASE parent_table
        WHEN 'raw_metrics_daily', 'raw_metrics_hourly' THEN 
            date_column := 'date';
        WHEN 'raw_trades_closed', 'raw_trades_open' THEN 
            date_column := 'trade_date';
        ELSE 
            date_column := 'date'; -- default
    END CASE;
    
    -- Check if partition exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'prop_trading_model'
        AND c.relname = partition_name
    ) THEN
        -- Create partition with proper constraints
        EXECUTE format(
            'CREATE TABLE prop_trading_model.%I PARTITION OF prop_trading_model.%I 
             FOR VALUES FROM (%L) TO (%L)',
            partition_name, parent_table, start_date, end_date
        );
        
        -- Add check constraint for faster attachment (skip if constraint name would be too long)
        IF length(partition_name || '_date_check') <= 63 THEN
            EXECUTE format(
                'ALTER TABLE prop_trading_model.%I 
                 ADD CONSTRAINT %I_date_check 
                 CHECK (%I >= %L AND %I < %L)',
                partition_name, partition_name, date_column, start_date, date_column, end_date
            );
        END IF;
        
        RAISE NOTICE 'Created partition: %', partition_name;
    END IF;
    
    RETURN partition_name;
END;
$$ LANGUAGE plpgsql;

-- Function to ensure partitions exist for a date range
CREATE OR REPLACE FUNCTION prop_trading_model.ensure_partitions_exist(
    parent_table text,
    months_ahead integer DEFAULT 3
) RETURNS integer AS $$
DECLARE
    curr_date date;
    partitions_created integer := 0;
    end_date date;
BEGIN
    curr_date := date_trunc('month', CURRENT_DATE);
    end_date := curr_date + (months_ahead || ' months')::interval;
    
    WHILE curr_date <= end_date LOOP
        PERFORM prop_trading_model.create_monthly_partition(parent_table, curr_date);
        partitions_created := partitions_created + 1;
        curr_date := curr_date + interval '1 month';
    END LOOP;
    
    RETURN partitions_created;
END;
$$ LANGUAGE plpgsql;

-- Function for intelligent partition cleanup (manual execution)
CREATE OR REPLACE FUNCTION prop_trading_model.cleanup_unused_partitions(
    parent_table text
) RETURNS TABLE (
    action text,
    partition_name text,
    row_count bigint,
    reason text
) AS $$
DECLARE
    partition_rec record;
    oldest_data_date date;
    newest_data_date date;
    partition_date date;
    current_row_count bigint;
    date_column text;
BEGIN
    -- Determine date column
    CASE parent_table
        WHEN 'raw_metrics_daily', 'raw_metrics_hourly' THEN 
            date_column := 'date';
        WHEN 'raw_trades_closed', 'raw_trades_open' THEN 
            date_column := 'trade_date';
        ELSE 
            date_column := 'date';
    END CASE;
    
    -- Find the actual data range for this table
    EXECUTE format('
        SELECT MIN(%I), MAX(%I) 
        FROM prop_trading_model.%I 
        WHERE %I IS NOT NULL',
        date_column, date_column, parent_table, date_column
    ) INTO oldest_data_date, newest_data_date;
    
    -- Return info if no data found
    IF oldest_data_date IS NULL THEN
        action := 'SKIP';
        partition_name := parent_table;
        row_count := 0;
        reason := 'No data found in parent table';
        RETURN NEXT;
        RETURN;
    END IF;
    
    -- Check each partition for this table
    FOR partition_rec IN
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename LIKE parent_table || '_20%'
        AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
        ORDER BY tablename
    LOOP
        -- Extract date from partition name (format: table_YYYY_MM)
        partition_date := to_date(right(partition_rec.tablename, 7), 'YYYY_MM');
        
        -- Get row count for this partition
        EXECUTE format('SELECT COUNT(*) FROM prop_trading_model.%I', partition_rec.tablename) 
        INTO current_row_count;
        
        -- Determine action based on data range and content
        IF partition_date < date_trunc('month', oldest_data_date) THEN
            -- Partition is before our data range
            IF current_row_count = 0 THEN
                action := 'DROP';
                reason := 'Empty partition before data range';
            ELSE
                action := 'KEEP';
                reason := 'Non-empty partition (contains historical data)';
            END IF;
        ELSIF partition_date > date_trunc('month', newest_data_date + interval '1 month') THEN
            -- Partition is after our data range
            IF current_row_count = 0 THEN
                action := 'DROP';
                reason := 'Empty partition after data range';
            ELSE
                action := 'KEEP';
                reason := 'Non-empty partition (contains future data)';
            END IF;
        ELSE
            -- Partition is within our data range - always keep
            action := 'KEEP';
            IF current_row_count = 0 THEN
                reason := 'Empty partition within data range (gap preservation)';
            ELSE
                reason := 'Active partition with data';
            END IF;
        END IF;
        
        -- Return the analysis
        partition_name := partition_rec.tablename;
        row_count := current_row_count;
        RETURN NEXT;
    END LOOP;
    
END;
$$ LANGUAGE plpgsql;

-- Function to analyze table for partitioning needs
CREATE OR REPLACE FUNCTION prop_trading_model.analyze_table_for_partitioning(
    table_name text
) RETURNS TABLE (
    needs_partitioning boolean,
    is_already_partitioned boolean,
    row_count bigint,
    table_size text,
    min_date date,
    max_date date,
    month_count bigint,
    recommendation text
) AS $$
DECLARE
    date_column text;
    relkind char;
BEGIN
    -- Determine date column
    CASE table_name
        WHEN 'raw_metrics_daily', 'raw_metrics_hourly' THEN 
            date_column := 'date';
        WHEN 'raw_trades_closed', 'raw_trades_open' THEN 
            date_column := 'trade_date';
        ELSE 
            date_column := 'date';
    END CASE;
    
    -- Check if table is already partitioned
    SELECT c.relkind INTO relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'prop_trading_model'
    AND c.relname = table_name;
    
    is_already_partitioned := (relkind = 'p');
    
    -- Get table statistics
    EXECUTE format('
        SELECT 
            COUNT(*),
            pg_size_pretty(pg_total_relation_size(''prop_trading_model.%I'')),
            MIN(%I)::date,
            MAX(%I)::date,
            COUNT(DISTINCT DATE_TRUNC(''month'', %I))
        FROM prop_trading_model.%I',
        table_name, date_column, date_column, date_column, table_name
    ) INTO row_count, table_size, min_date, max_date, month_count;
    
    -- Determine if partitioning is needed
    needs_partitioning := NOT is_already_partitioned AND row_count > 100000 AND month_count > 3;
    
    -- Provide recommendation
    IF is_already_partitioned THEN
        recommendation := 'Already partitioned';
    ELSIF needs_partitioning THEN
        recommendation := format('Recommend partitioning: %s rows across %s months', 
                                row_count, month_count);
    ELSE
        recommendation := 'Partitioning not needed yet';
    END IF;
    
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- Helper function to create partitions for a specific date range
CREATE OR REPLACE FUNCTION prop_trading_model.ensure_partitions_exist_range(
    parent_table text,
    start_date date,
    end_date date
) RETURNS integer AS $$
DECLARE
    curr_date date;
    partitions_created integer := 0;
BEGIN
    curr_date := date_trunc('month', start_date);
    
    WHILE curr_date <= end_date LOOP
        PERFORM prop_trading_model.create_monthly_partition(parent_table, curr_date);
        partitions_created := partitions_created + 1;
        curr_date := curr_date + interval '1 month';
    END LOOP;
    
    RETURN partitions_created;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION prop_trading_model.create_monthly_partition TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.ensure_partitions_exist TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.cleanup_unused_partitions TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.analyze_table_for_partitioning TO postgres;
GRANT EXECUTE ON FUNCTION prop_trading_model.ensure_partitions_exist_range TO postgres;

-- Add comments for documentation
COMMENT ON FUNCTION prop_trading_model.create_monthly_partition IS 'Creates a monthly partition for the specified table and date';
COMMENT ON FUNCTION prop_trading_model.ensure_partitions_exist IS 'Ensures partitions exist for the next N months';
COMMENT ON FUNCTION prop_trading_model.cleanup_unused_partitions IS 'Analyzes partitions and identifies which can be safely dropped';
COMMENT ON FUNCTION prop_trading_model.analyze_table_for_partitioning IS 'Analyzes if a table needs partitioning based on size and date range';