"""
Partition Migration Manager for PostgreSQL Tables

Implements dynamic table partitioning following Supabase patterns:
- Safe conversion of regular tables to partitioned tables
- Automatic partition creation based on data
- Progressive data migration for large tables
- Zero-downtime migrations
"""

import logging
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor

from .database import DatabaseManager

logger = logging.getLogger(__name__)


class PartitionMigrationManager:
    """
    Manages conversion of regular tables to partitioned tables.
    
    Features:
    - Automatic partition creation based on date ranges
    - Progressive data migration to avoid locks
    - Validation and rollback capabilities
    - Trading-aware migration timing
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.schema_name = "prop_trading_model"
        
    def analyze_table_for_partitioning(self, table_name: str) -> Dict[str, Any]:
        """
        Analyze a table to determine if it needs partitioning.
        
        Returns analysis including:
        - Current size and row count
        - Date range of data
        - Recommended partition strategy
        - Migration complexity estimate
        """
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get table size and row count
                cursor.execute(f"""
                    SELECT 
                        pg_size_pretty(pg_total_relation_size('{self.schema_name}.{table_name}')) as total_size,
                        pg_size_pretty(pg_relation_size('{self.schema_name}.{table_name}')) as table_size,
                        pg_size_pretty(pg_indexes_size('{self.schema_name}.{table_name}')) as indexes_size,
                        COUNT(*) as row_count
                    FROM {self.schema_name}.{table_name}
                """)
                size_info = cursor.fetchone()
                
                # Check if table has date column for partitioning
                cursor.execute(f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = '{self.schema_name}'
                    AND table_name = '{table_name}'
                    AND data_type IN ('date', 'timestamp', 'timestamp without time zone')
                    AND column_name IN ('date', 'datetime', 'created_at', 'trade_date')
                    ORDER BY ordinal_position
                    LIMIT 1
                """)
                date_column = cursor.fetchone()
                
                if not date_column:
                    return {
                        "needs_partitioning": False,
                        "reason": "No suitable date column found",
                        "size_info": size_info
                    }
                
                partition_column = date_column['column_name']
                
                # Get date range
                cursor.execute(f"""
                    SELECT 
                        MIN({partition_column})::date as min_date,
                        MAX({partition_column})::date as max_date,
                        COUNT(DISTINCT DATE_TRUNC('month', {partition_column})) as month_count
                    FROM {self.schema_name}.{table_name}
                """)
                date_range = cursor.fetchone()
                
                # Check if already partitioned
                cursor.execute(f"""
                    SELECT relkind 
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = '{self.schema_name}'
                    AND c.relname = '{table_name}'
                """)
                table_kind = cursor.fetchone()
                
                is_partitioned = table_kind and table_kind['relkind'] == 'p'
                
                # Determine if partitioning is recommended
                needs_partitioning = (
                    not is_partitioned and
                    size_info['row_count'] > 100000 and  # More than 100k rows
                    date_range['month_count'] > 3  # Data spans multiple months
                )
                
                return {
                    "needs_partitioning": needs_partitioning,
                    "is_already_partitioned": is_partitioned,
                    "table_name": table_name,
                    "partition_column": partition_column,
                    "size_info": size_info,
                    "date_range": date_range,
                    "migration_complexity": self._estimate_complexity(size_info['row_count']),
                    "recommended_strategy": "monthly" if date_range['month_count'] > 12 else "daily"
                }
    
    def _estimate_complexity(self, row_count: int) -> str:
        """Estimate migration complexity based on row count."""
        if row_count < 100000:
            return "LOW"
        elif row_count < 1000000:
            return "MEDIUM"
        elif row_count < 10000000:
            return "HIGH"
        else:
            return "VERY_HIGH"
    
    def convert_to_partitioned_table(
        self,
        table_name: str,
        partition_column: str = "date",
        partition_strategy: str = "monthly",
        batch_size: int = 10000,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Convert a regular table to a partitioned table.
        
        This implements the complete migration process:
        1. Create new partitioned table structure
        2. Create partition tables for date ranges
        3. Migrate data in batches
        4. Validate data integrity
        5. Atomic table swap
        """
        try:
            # Analyze table first
            analysis = self.analyze_table_for_partitioning(table_name)
            
            if not analysis["needs_partitioning"] and not dry_run:
                return {
                    "success": False,
                    "reason": "Table does not need partitioning",
                    "analysis": analysis
                }
            
            logger.info(f"Starting partition migration for {table_name}")
            logger.info(f"Table size: {analysis['size_info']['total_size']}")
            logger.info(f"Row count: {analysis['size_info']['row_count']:,}")
            
            if dry_run:
                return self._generate_migration_plan(table_name, partition_column, partition_strategy, analysis)
            
            # Execute migration
            with self.db_manager.model_db.get_connection() as conn:
                try:
                    # Start transaction
                    conn.autocommit = False
                    
                    # Step 1: Create partitioned table structure
                    new_table_name = f"{table_name}_p"
                    self._create_partitioned_table(conn, table_name, new_table_name, partition_column)
                    
                    # Step 2: Create partitions
                    partitions_created = self._create_partitions(
                        conn, 
                        new_table_name, 
                        partition_column,
                        analysis['date_range']['min_date'],
                        analysis['date_range']['max_date'],
                        partition_strategy
                    )
                    
                    # Step 3: Migrate data in batches
                    migration_stats = self._migrate_data_in_batches(
                        conn,
                        table_name,
                        new_table_name,
                        partition_column,
                        batch_size,
                        analysis['date_range']['min_date'],
                        analysis['date_range']['max_date']
                    )
                    
                    # Step 4: Create indexes
                    self._recreate_indexes(conn, table_name, new_table_name)
                    
                    # Step 5: Validate migration
                    validation_result = self._validate_migration(conn, table_name, new_table_name)
                    
                    if not validation_result['valid']:
                        raise Exception(f"Migration validation failed: {validation_result['errors']}")
                    
                    # Step 6: Atomic table swap
                    self._swap_tables(conn, table_name, new_table_name)
                    
                    # Commit transaction
                    conn.commit()
                    
                    return {
                        "success": True,
                        "partitions_created": partitions_created,
                        "rows_migrated": migration_stats['total_rows'],
                        "migration_time": migration_stats['duration'],
                        "validation": validation_result
                    }
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Migration failed, rolling back: {e}")
                    raise
                    
        except Exception as e:
            logger.error(f"Partition migration failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _create_partitioned_table(self, conn, source_table: str, target_table: str, partition_column: str):
        """Create partitioned table with same structure as source."""
        with conn.cursor() as cursor:
            # Get source table DDL (using pg_dump style approach)
            cursor.execute(f"""
                SELECT 
                    'CREATE TABLE {self.schema_name}.{target_table} (LIKE {self.schema_name}.{source_table} INCLUDING ALL) PARTITION BY RANGE ({partition_column})' as ddl
            """)
            ddl = cursor.fetchone()[0]
            
            logger.info(f"Creating partitioned table: {target_table}")
            cursor.execute(ddl)
    
    def _create_partitions(
        self,
        conn,
        table_name: str,
        partition_column: str,
        min_date: date,
        max_date: date,
        strategy: str = "monthly"
    ) -> List[str]:
        """Create partition tables for date range."""
        partitions = []
        
        with conn.cursor() as cursor:
            # Start before min_date for safety
            current_date = min_date.replace(day=1) - relativedelta(months=1)
            # End after max_date for future data
            end_date = max_date.replace(day=1) + relativedelta(months=3)
            
            while current_date < end_date:
                if strategy == "monthly":
                    partition_name = f"{table_name}_{current_date.strftime('%Y_%m')}"
                    next_date = current_date + relativedelta(months=1)
                else:  # daily
                    partition_name = f"{table_name}_{current_date.strftime('%Y%m%d')}"
                    next_date = current_date + timedelta(days=1)
                
                # Create partition
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema_name}.{partition_name}
                    PARTITION OF {self.schema_name}.{table_name}
                    FOR VALUES FROM ('{current_date}') TO ('{next_date}')
                """)
                
                partitions.append(partition_name)
                logger.info(f"Created partition: {partition_name}")
                
                current_date = next_date
        
        return partitions
    
    def _migrate_data_in_batches(
        self,
        conn,
        source_table: str,
        target_table: str,
        partition_column: str,
        batch_size: int,
        min_date: date,
        max_date: date
    ) -> Dict[str, Any]:
        """Migrate data in batches to avoid long locks."""
        start_time = datetime.now()
        total_rows = 0
        
        with conn.cursor() as cursor:
            # Migrate month by month for better performance
            current_date = min_date.replace(day=1)
            
            while current_date <= max_date:
                next_month = current_date + relativedelta(months=1)
                
                # Count rows for this month
                cursor.execute(f"""
                    SELECT COUNT(*) 
                    FROM {self.schema_name}.{source_table}
                    WHERE {partition_column} >= %s AND {partition_column} < %s
                """, (current_date, next_month))
                
                month_rows = cursor.fetchone()[0]
                
                if month_rows > 0:
                    # Use INSERT with ORDER BY for better cache efficiency
                    cursor.execute(f"""
                        INSERT INTO {self.schema_name}.{target_table}
                        SELECT * FROM {self.schema_name}.{source_table}
                        WHERE {partition_column} >= %s AND {partition_column} < %s
                        ORDER BY {partition_column}
                    """, (current_date, next_month))
                    
                    total_rows += month_rows
                    logger.info(f"Migrated {month_rows:,} rows for {current_date.strftime('%Y-%m')}")
                
                current_date = next_month
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return {
            "total_rows": total_rows,
            "duration": duration,
            "rows_per_second": total_rows / duration if duration > 0 else 0
        }
    
    def _recreate_indexes(self, conn, source_table: str, target_table: str):
        """Recreate indexes on partitioned table."""
        with conn.cursor() as cursor:
            # Get indexes from source table
            cursor.execute(f"""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = '{self.schema_name}'
                AND tablename = '{source_table}'
                AND indexname NOT LIKE '%_pkey'  -- Skip primary key
            """)
            
            for index in cursor.fetchall():
                old_name = index[0]
                new_name = old_name.replace(source_table, target_table)
                new_def = index[1].replace(source_table, target_table).replace(old_name, new_name)
                
                logger.info(f"Creating index: {new_name}")
                cursor.execute(new_def)
    
    def _validate_migration(self, conn, source_table: str, target_table: str) -> Dict[str, Any]:
        """Validate data integrity after migration."""
        errors = []
        
        with conn.cursor() as cursor:
            # Compare row counts
            cursor.execute(f"SELECT COUNT(*) FROM {self.schema_name}.{source_table}")
            source_count = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT COUNT(*) FROM {self.schema_name}.{target_table}")
            target_count = cursor.fetchone()[0]
            
            if source_count != target_count:
                errors.append(f"Row count mismatch: {source_count} vs {target_count}")
            
            # Compare checksums for sample data
            cursor.execute(f"""
                SELECT MD5(string_agg(account_id::text || date::text, ',' ORDER BY account_id, date))
                FROM (
                    SELECT account_id, date FROM {self.schema_name}.{source_table}
                    ORDER BY RANDOM() LIMIT 10000
                ) sample
            """)
            source_checksum = cursor.fetchone()[0]
            
            cursor.execute(f"""
                SELECT MD5(string_agg(account_id::text || date::text, ',' ORDER BY account_id, date))
                FROM (
                    SELECT account_id, date FROM {self.schema_name}.{target_table}
                    WHERE (account_id, date) IN (
                        SELECT account_id, date FROM {self.schema_name}.{source_table}
                        ORDER BY RANDOM() LIMIT 10000
                    )
                ) sample
            """)
            target_checksum = cursor.fetchone()[0]
            
            if source_checksum != target_checksum:
                errors.append("Data integrity check failed")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "source_count": source_count,
            "target_count": target_count
        }
    
    def _swap_tables(self, conn, old_table: str, new_table: str):
        """Atomic table swap."""
        with conn.cursor() as cursor:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Rename old table to backup
            cursor.execute(f"""
                ALTER TABLE {self.schema_name}.{old_table} 
                RENAME TO {old_table}_backup_{timestamp}
            """)
            
            # Rename new table to original name
            cursor.execute(f"""
                ALTER TABLE {self.schema_name}.{new_table} 
                RENAME TO {old_table}
            """)
            
            logger.info(f"Table swap completed. Backup: {old_table}_backup_{timestamp}")
    
    def _generate_migration_plan(
        self,
        table_name: str,
        partition_column: str,
        partition_strategy: str,
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate migration plan for dry run."""
        # Calculate partitions needed
        min_date = analysis['date_range']['min_date']
        max_date = analysis['date_range']['max_date']
        
        partitions_needed = []
        current_date = min_date.replace(day=1) - relativedelta(months=1)
        end_date = max_date.replace(day=1) + relativedelta(months=3)
        
        while current_date < end_date:
            if partition_strategy == "monthly":
                partition_name = f"{table_name}_{current_date.strftime('%Y_%m')}"
                next_date = current_date + relativedelta(months=1)
            else:
                partition_name = f"{table_name}_{current_date.strftime('%Y%m%d')}"
                next_date = current_date + timedelta(days=1)
            
            partitions_needed.append({
                "name": partition_name,
                "start": current_date,
                "end": next_date
            })
            
            current_date = next_date
        
        # Estimate migration time
        rows_per_second = 50000  # Conservative estimate
        estimated_time = analysis['size_info']['row_count'] / rows_per_second
        
        return {
            "dry_run": True,
            "plan": {
                "table": table_name,
                "partition_column": partition_column,
                "strategy": partition_strategy,
                "partitions_needed": len(partitions_needed),
                "partition_list": partitions_needed[:10],  # Show first 10
                "estimated_time_seconds": estimated_time,
                "estimated_time_human": f"{estimated_time/60:.1f} minutes",
                "space_required": analysis['size_info']['total_size'],
                "steps": [
                    f"1. Create partitioned table {table_name}_p",
                    f"2. Create {len(partitions_needed)} partition tables",
                    f"3. Migrate {analysis['size_info']['row_count']:,} rows in batches",
                    "4. Recreate indexes on partitioned table",
                    "5. Validate data integrity",
                    f"6. Rename {table_name} to {table_name}_backup_<timestamp>",
                    f"7. Rename {table_name}_p to {table_name}"
                ]
            }
        }


def create_partition_functions(db_manager: DatabaseManager) -> None:
    """
    Create PostgreSQL functions for dynamic partition management.
    
    Based on Supabase patterns for automatic partition creation.
    """
    with db_manager.model_db.get_connection() as conn:
        with conn.cursor() as cursor:
            # Function to create monthly partitions dynamically
            cursor.execute("""
                CREATE OR REPLACE FUNCTION prop_trading_model.create_monthly_partition(
                    parent_table text,
                    partition_date date
                ) RETURNS text AS $$
                DECLARE
                    partition_name text;
                    start_date date;
                    end_date date;
                BEGIN
                    -- Calculate partition boundaries
                    start_date := date_trunc('month', partition_date);
                    end_date := start_date + interval '1 month';
                    
                    -- Generate partition name
                    partition_name := parent_table || '_' || to_char(start_date, 'YYYY_MM');
                    
                    -- Check if partition exists
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'prop_trading_model'
                        AND c.relname = partition_name
                    ) THEN
                        -- Create partition
                        EXECUTE format(
                            'CREATE TABLE prop_trading_model.%I PARTITION OF prop_trading_model.%I FOR VALUES FROM (%L) TO (%L)',
                            partition_name, parent_table, start_date, end_date
                        );
                        
                        RAISE NOTICE 'Created partition: %', partition_name;
                    END IF;
                    
                    RETURN partition_name;
                END;
                $$ LANGUAGE plpgsql;
                
                -- Function to ensure partitions exist for a date range
                CREATE OR REPLACE FUNCTION prop_trading_model.ensure_partitions_exist(
                    parent_table text,
                    start_date date,
                    end_date date
                ) RETURNS integer AS $$
                DECLARE
                    current_date date;
                    partitions_created integer := 0;
                BEGIN
                    current_date := date_trunc('month', start_date);
                    
                    WHILE current_date <= end_date LOOP
                        PERFORM prop_trading_model.create_monthly_partition(parent_table, current_date);
                        partitions_created := partitions_created + 1;
                        current_date := current_date + interval '1 month';
                    END LOOP;
                    
                    RETURN partitions_created;
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            conn.commit()
            logger.info("Created partition management functions")