-- Setup functions needed for schema management
-- Run this once to enable full schema comparison functionality

-- Function to get complete table definition
CREATE OR REPLACE FUNCTION prop_trading_model.pg_get_tabledef(table_name text)
RETURNS text AS $$
DECLARE
    table_def text;
    schema_name text;
    table_name_only text;
    col_defs text;
    constraint_defs text;
BEGIN
    -- Parse schema and table name
    IF position('.' IN table_name) > 0 THEN
        schema_name := split_part(table_name, '.', 1);
        table_name_only := split_part(table_name, '.', 2);
    ELSE
        schema_name := 'prop_trading_model';
        table_name_only := table_name;
    END IF;
    
    -- Get column definitions
    SELECT string_agg(
        column_def,
        E',\n    ' ORDER BY ordinal_position
    ) INTO col_defs
    FROM (
        SELECT 
            ordinal_position,
            column_name || ' ' || 
            CASE 
                WHEN data_type = 'character varying' THEN 'VARCHAR(' || character_maximum_length || ')'
                WHEN data_type = 'numeric' THEN 'DECIMAL(' || numeric_precision || ',' || numeric_scale || ')'
                WHEN data_type = 'timestamp without time zone' THEN 'TIMESTAMP'
                ELSE UPPER(data_type)
            END ||
            CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END ||
            CASE WHEN column_default IS NOT NULL THEN ' DEFAULT ' || column_default ELSE '' END
            as column_def
        FROM information_schema.columns
        WHERE table_schema = schema_name
          AND table_name = table_name_only
    ) cols;
    
    -- Get constraint definitions (excluding foreign keys for simplicity)
    SELECT string_agg(
        constraint_def,
        E',\n    '
    ) INTO constraint_defs
    FROM (
        SELECT 
            CASE constraint_type
                WHEN 'PRIMARY KEY' THEN 'PRIMARY KEY (' || column_list || ')'
                WHEN 'UNIQUE' THEN 'UNIQUE(' || column_list || ')'
                WHEN 'CHECK' THEN 'CHECK ' || check_clause
            END as constraint_def
        FROM (
            SELECT 
                tc.constraint_type,
                tc.constraint_name,
                string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) as column_list,
                cc.check_clause
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_schema = kcu.constraint_schema 
                AND tc.constraint_name = kcu.constraint_name
            LEFT JOIN information_schema.check_constraints cc
                ON tc.constraint_schema = cc.constraint_schema
                AND tc.constraint_name = cc.constraint_name
            WHERE tc.table_schema = schema_name
              AND tc.table_name = table_name_only
              AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'CHECK')
            GROUP BY tc.constraint_type, tc.constraint_name, cc.check_clause
        ) constraints
        WHERE constraint_def IS NOT NULL
    ) const_defs;
    
    -- Build complete table definition
    table_def := 'CREATE TABLE ' || schema_name || '.' || table_name_only || ' (' || E'\n    ' || col_defs;
    
    IF constraint_defs IS NOT NULL THEN
        table_def := table_def || E',\n    ' || constraint_defs;
    END IF;
    
    table_def := table_def || E'\n)';
    
    -- Add partitioning if applicable
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = schema_name
          AND c.relname = table_name_only
          AND c.relkind = 'p'  -- partitioned table
    ) THEN
        SELECT ' PARTITION BY ' || pg_get_partkeydef(c.oid)
        INTO constraint_defs
        FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = schema_name
          AND c.relname = table_name_only;
        
        table_def := table_def || constraint_defs;
    END IF;
    
    table_def := table_def || ';';
    
    RETURN table_def;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION prop_trading_model.pg_get_tabledef(text) TO PUBLIC;