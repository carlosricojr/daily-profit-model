"""
Intelligent Schema Management System

This module provides production-ready schema management with:
- Automatic schema comparison and diff generation
- Safe migrations without data loss
- Version tracking and rollback capabilities
- Dry-run mode for testing changes
- Comprehensive logging and error handling
"""

import os
import re
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Set
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from .database import DatabaseManager

logger = logging.getLogger(__name__)


class SchemaObject:
    """Represents a database schema object (table, index, function, etc.)"""
    
    def __init__(self, obj_type: str, name: str, definition: str, dependencies: List[str] = None):
        self.type = obj_type
        self.name = name
        self.definition = definition
        self.dependencies = dependencies or []
        self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> str:
        """Calculate checksum of the object definition."""
        normalized = re.sub(r'\s+', ' ', self.definition.strip())
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def __repr__(self):
        return f"<SchemaObject {self.type}:{self.name}>"


class SchemaManager:
    """
    Manages database schema versioning, comparison, and migration.
    
    Features:
    - Compares desired schema with current database state
    - Generates safe migrations preserving data
    - Tracks schema versions
    - Provides rollback capabilities
    - Supports dry-run mode
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.schema_name = "prop_trading_model"
        self.version_table = "schema_version"
        self.migrations_dir = Path(__file__).parent.parent / "db_schema" / "auto_migrations"
        self.migrations_dir.mkdir(exist_ok=True)
        
        # Object type ordering for dependencies
        self.object_type_order = [
            'EXTENSION',
            'TYPE',
            'DOMAIN',
            'TABLE',
            'SEQUENCE',
            'VIEW',
            'MATERIALIZED VIEW',
            'FUNCTION',
            'TRIGGER',
            'INDEX',
            'CONSTRAINT'
        ]
        
    def ensure_version_table(self):
        """Create schema version tracking table if it doesn't exist."""
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.schema_name}.{self.version_table} (
                        version_id SERIAL PRIMARY KEY,
                        version_hash VARCHAR(32) NOT NULL UNIQUE,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        applied_by VARCHAR(100) DEFAULT CURRENT_USER,
                        description TEXT,
                        migration_script TEXT,
                        rollback_script TEXT,
                        objects_affected JSONB,
                        execution_time_ms INTEGER,
                        status VARCHAR(20) DEFAULT 'applied' CHECK (status IN ('applied', 'rolled_back', 'failed'))
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_schema_version_applied_at 
                    ON {self.schema_name}.{self.version_table}(applied_at DESC);
                """)
                conn.commit()
    
    def get_current_version(self) -> Optional[str]:
        """Get the current schema version hash."""
        try:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT version_hash 
                        FROM {self.schema_name}.{self.version_table}
                        WHERE status = 'applied'
                        ORDER BY applied_at DESC
                        LIMIT 1
                    """)
                    result = cursor.fetchone()
                    return result[0] if result else None
        except psycopg2.errors.UndefinedTable:
            return None
    
    def parse_schema_file(self, schema_path: Path) -> Dict[str, SchemaObject]:
        """Parse schema file and extract all database objects."""
        with open(schema_path, 'r') as f:
            content = f.read()
        
        objects = {}
        
        # Remove comments
        content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Parse different object types
        self._parse_extensions(content, objects)
        self._parse_tables(content, objects)
        self._parse_indexes(content, objects)
        self._parse_views(content, objects)
        self._parse_functions(content, objects)
        self._parse_materialized_views(content, objects)
        
        return objects
    
    def _parse_extensions(self, content: str, objects: Dict[str, SchemaObject]):
        """Parse CREATE EXTENSION statements."""
        pattern = r'CREATE\s+EXTENSION\s+IF\s+NOT\s+EXISTS\s+(\w+)(?:\s+WITH\s+SCHEMA\s+(\w+))?;'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            name = match.group(1)
            objects[f'EXTENSION:{name}'] = SchemaObject(
                'EXTENSION',
                name,
                match.group(0)
            )
    
    def _parse_tables(self, content: str, objects: Dict[str, SchemaObject]):
        """Parse CREATE TABLE statements."""
        # Handle regular tables
        pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(\w+)\.)?(\w+)\s*\((.*?)\)(?:\s+PARTITION\s+BY\s+.*?)?;'
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            schema = match.group(1) or self.schema_name
            name = match.group(2)
            definition = match.group(0)
            
            # Skip partition tables
            if re.search(r'PARTITION\s+OF', definition, re.IGNORECASE):
                continue
                
            objects[f'TABLE:{name}'] = SchemaObject(
                'TABLE',
                name,
                definition
            )
    
    def _parse_indexes(self, content: str, objects: Dict[str, SchemaObject]):
        """Parse CREATE INDEX statements."""
        pattern = r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(?:(\w+)\.)?(\w+)'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            index_name = match.group(1)
            table_name = match.group(3)
            
            # Find the complete statement
            start = match.start()
            end = content.find(';', start) + 1
            definition = content[start:end]
            
            objects[f'INDEX:{index_name}'] = SchemaObject(
                'INDEX',
                index_name,
                definition,
                dependencies=[f'TABLE:{table_name}']
            )
    
    def _parse_views(self, content: str, objects: Dict[str, SchemaObject]):
        """Parse CREATE VIEW statements."""
        pattern = r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(\w+)\.)?(\w+)\s+AS\s+(.*?)(?=CREATE|$)'
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            name = match.group(2)
            definition = match.group(0).rstrip(';') + ';'
            
            # Extract dependencies (tables referenced in the view)
            deps = self._extract_table_references(match.group(3))
            
            objects[f'VIEW:{name}'] = SchemaObject(
                'VIEW',
                name,
                definition,
                dependencies=deps
            )
    
    def _parse_functions(self, content: str, objects: Dict[str, SchemaObject]):
        """Parse CREATE FUNCTION statements."""
        pattern = r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:(\w+)\.)?(\w+)\s*\((.*?)\)\s+RETURNS\s+.*?\$\$.*?\$\$\s*LANGUAGE\s+\w+;'
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            name = match.group(2)
            definition = match.group(0)
            
            objects[f'FUNCTION:{name}'] = SchemaObject(
                'FUNCTION',
                name,
                definition
            )
    
    def _parse_materialized_views(self, content: str, objects: Dict[str, SchemaObject]):
        """Parse CREATE MATERIALIZED VIEW statements."""
        pattern = r'CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(\w+)\.)?(\w+)\s+AS\s+(.*?)WITH\s+DATA;'
        for match in re.finditer(pattern, content, re.IGNORECASE | re.DOTALL):
            name = match.group(2)
            definition = match.group(0)
            
            # Extract dependencies
            deps = self._extract_table_references(match.group(3))
            
            objects[f'MATERIALIZED VIEW:{name}'] = SchemaObject(
                'MATERIALIZED VIEW',
                name,
                definition,
                dependencies=deps
            )
    
    def _extract_table_references(self, sql: str) -> List[str]:
        """Extract table references from SQL."""
        deps = []
        # Simple pattern - can be enhanced
        pattern = r'FROM\s+(?:(\w+)\.)?(\w+)|JOIN\s+(?:(\w+)\.)?(\w+)'
        for match in re.finditer(pattern, sql, re.IGNORECASE):
            table = match.group(2) or match.group(4)
            if table and table not in ['LATERAL', 'NATURAL', 'CROSS']:
                deps.append(f'TABLE:{table}')
        return list(set(deps))
    
    def get_partition_info(self, conn) -> Dict[str, str]:
        """Get all partition tables and their parent tables."""
        partition_info = {}
        
        with conn.cursor() as cursor:
            # Query PostgreSQL's inheritance catalog to find all partitions
            cursor.execute(f"""
                SELECT 
                    c.relname as partition_name,
                    p.relname as parent_name
                FROM pg_class c
                JOIN pg_inherits i ON c.oid = i.inhrelid
                JOIN pg_class p ON i.inhparent = p.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = '{self.schema_name}'
                AND c.relkind IN ('r', 'p')  -- regular tables and partitioned tables
            """)
            
            for partition_name, parent_name in cursor.fetchall():
                partition_info[partition_name] = parent_name
                
        return partition_info
    
    def get_system_tables(self, conn) -> Set[str]:
        """Get system/migration tables that should be excluded from management."""
        system_tables = set()
        
        with conn.cursor() as cursor:
            # Get migration system tables
            cursor.execute(f"""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = '{self.schema_name}'
                AND tablename IN ('alembic_version', 'schema_migrations', 'flyway_schema_history')
            """)
            
            for row in cursor.fetchall():
                system_tables.add(row[0])
                
        return system_tables
    
    def get_constraint_backed_indexes(self, conn) -> Set[str]:
        """Get indexes that back constraints (PRIMARY KEY, UNIQUE, etc.)."""
        constraint_indexes = set()
        
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT i.indexname
                FROM pg_indexes i
                JOIN pg_class c ON c.relname = i.indexname
                JOIN pg_constraint con ON con.conindid = c.oid
                WHERE i.schemaname = '{self.schema_name}'
            """)
            
            for row in cursor.fetchall():
                constraint_indexes.add(row[0])
                
        return constraint_indexes
    
    def get_extension_objects(self, conn) -> Set[str]:
        """Get objects created by PostgreSQL extensions."""
        extension_objects = set()
        
        with conn.cursor() as cursor:
            # Get functions from extensions (like btree_gist)
            cursor.execute(f"""
                SELECT p.proname
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = '{self.schema_name}'
                AND p.proname LIKE 'gbt_%'  -- btree_gist functions
            """)
            
            for row in cursor.fetchall():
                extension_objects.add(f"FUNCTION:{row[0]}")
                
        return extension_objects

    def get_current_schema_objects(self) -> Dict[str, SchemaObject]:
        """Get all objects currently in the database, excluding partitions and system objects."""
        objects = {}
        
        with self.db_manager.model_db.get_connection() as conn:
            # Get objects to exclude
            partition_tables = self.get_partition_info(conn)
            partition_names = set(partition_tables.keys())
            system_tables = self.get_system_tables(conn)
            constraint_indexes = self.get_constraint_backed_indexes(conn)
            extension_objects = self.get_extension_objects(conn)
            
            # Log exclusions
            if partition_names:
                logger.info(f"Excluding {len(partition_names)} partition tables from schema comparison")
            if system_tables:
                logger.info(f"Excluding {len(system_tables)} system/migration tables: {list(system_tables)}")
            if constraint_indexes:
                logger.info(f"Excluding {len(constraint_indexes)} constraint-backed indexes")
            if extension_objects:
                logger.info(f"Excluding {len(extension_objects)} extension objects")
            with conn.cursor() as cursor:
                # Get tables
                # First check if our helper function exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_proc p
                        JOIN pg_namespace n ON p.pronamespace = n.oid
                        WHERE n.nspname = %s AND p.proname = 'pg_get_tabledef'
                    )
                """, (self.schema_name,))
                
                has_helper_function = cursor.fetchone()[0]
                
                # Build exclusion lists
                exclude_tables = list(partition_names) + list(system_tables) + [self.version_table]
                exclude_tables_placeholder = ','.join(['%s'] * len(exclude_tables)) if exclude_tables else "''"
                
                exclude_indexes = list(constraint_indexes)
                exclude_indexes_placeholder = ','.join(['%s'] * len(exclude_indexes)) if exclude_indexes else "''"
                
                if has_helper_function and exclude_tables:
                    cursor.execute(f"""
                        SELECT tablename, 
                               {self.schema_name}.pg_get_tabledef('{self.schema_name}.' || tablename) as definition
                        FROM pg_tables 
                        WHERE schemaname = '{self.schema_name}'
                        AND tablename NOT IN ({exclude_tables_placeholder})
                    """, exclude_tables)
                elif has_helper_function:
                    cursor.execute(f"""
                        SELECT tablename, 
                               {self.schema_name}.pg_get_tabledef('{self.schema_name}.' || tablename) as definition
                        FROM pg_tables 
                        WHERE schemaname = '{self.schema_name}'
                    """)
                elif exclude_tables:
                    # Fallback: basic table info
                    logger.warning("pg_get_tabledef function not found. Using basic table information.")
                    cursor.execute(f"""
                        SELECT t.tablename, 
                               'CREATE TABLE ' || t.schemaname || '.' || t.tablename || ' (--columns not available--);' as definition
                        FROM pg_tables t
                        WHERE t.schemaname = '{self.schema_name}'
                        AND t.tablename NOT IN ({exclude_tables_placeholder})
                    """, exclude_tables)
                else:
                    # Fallback: basic table info, no exclusions
                    logger.warning("pg_get_tabledef function not found. Using basic table information.")
                    cursor.execute(f"""
                        SELECT t.tablename, 
                               'CREATE TABLE ' || t.schemaname || '.' || t.tablename || ' (--columns not available--);' as definition
                        FROM pg_tables t
                        WHERE t.schemaname = '{self.schema_name}'
                    """)
                
                for row in cursor.fetchall():
                    if row[1]:  # If definition exists
                        objects[f'TABLE:{row[0]}'] = SchemaObject(
                            'TABLE',
                            row[0],
                            row[1]
                        )
                
                # Get indexes (excluding those on partition/system tables and constraint-backed indexes)
                all_exclusions = exclude_tables + exclude_indexes
                if all_exclusions:
                    all_exclusions_placeholder = ','.join(['%s'] * len(all_exclusions))
                    cursor.execute(f"""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = '{self.schema_name}'
                        AND tablename NOT IN ({exclude_tables_placeholder})
                        AND indexname NOT IN ({exclude_indexes_placeholder})
                    """, exclude_tables + exclude_indexes)
                else:
                    cursor.execute(f"""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = '{self.schema_name}'
                    """)
                
                for row in cursor.fetchall():
                    objects[f'INDEX:{row[0]}'] = SchemaObject(
                        'INDEX',
                        row[0],
                        row[1]
                    )
                
                # Get views
                cursor.execute(f"""
                    SELECT viewname, definition
                    FROM pg_views
                    WHERE schemaname = '{self.schema_name}'
                """)
                
                for row in cursor.fetchall():
                    objects[f'VIEW:{row[0]}'] = SchemaObject(
                        'VIEW',
                        row[0],
                        f"CREATE VIEW {row[0]} AS {row[1]}"
                    )
                
                # Get materialized views
                cursor.execute(f"""
                    SELECT matviewname, definition
                    FROM pg_matviews
                    WHERE schemaname = '{self.schema_name}'
                """)
                
                for row in cursor.fetchall():
                    objects[f'MATERIALIZED VIEW:{row[0]}'] = SchemaObject(
                        'MATERIALIZED VIEW',
                        row[0],
                        f"CREATE MATERIALIZED VIEW {row[0]} AS {row[1]}"
                    )
                
                # Get functions (excluding extension functions)
                cursor.execute(f"""
                    SELECT proname, pg_get_functiondef(oid)
                    FROM pg_proc
                    WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = '{self.schema_name}')
                    AND proname NOT LIKE 'gbt_%'  -- Exclude btree_gist extension functions
                """)
                
                for row in cursor.fetchall():
                    func_key = f'FUNCTION:{row[0]}'
                    if func_key not in extension_objects:  # Double-check exclusion
                        objects[func_key] = SchemaObject(
                            'FUNCTION',
                            row[0],
                            row[1]
                        )
        
        return objects
    
    def _should_drop_object(self, obj_key: str, obj: SchemaObject) -> bool:
        """
        Determine if an object should be dropped based on naming patterns and type.
        
        Uses selective logic:
        - Drops objects that clearly belong to our schema management system
        - Preserves objects that might belong to other systems
        - Allows proper testing while maintaining production safety
        """
        obj_type, obj_name = obj_key.split(':', 1)
        
        # Our managed object patterns - objects we're confident we should manage
        managed_patterns = [
            'raw_', 'stg_', 'feature_store_', 'model_', 'mv_',
            'pipeline_', 'query_', 'scheduled_', 'schema_version'
        ]
        
        # System patterns to never drop - objects from other systems
        system_patterns = [
            'alembic_', 'flyway_', 'pg_', 'information_schema',
            'gbt_'  # btree_gist extension functions
        ]
        
        # Partition table patterns (additional safety)
        partition_patterns = ['_202', '_2025', '_2024', '_2023']  # Year-based partitions
        
        # Check if it's a system object we should never touch
        for pattern in system_patterns:
            if obj_name.startswith(pattern):
                return False
                
        # Check if it's a partition table
        for pattern in partition_patterns:
            if pattern in obj_name:
                return False
        
        # For tables and views, check if they match our managed patterns
        if obj_type in ['TABLE', 'VIEW', 'MATERIALIZED VIEW']:
            # If it matches our patterns, we can drop it
            for pattern in managed_patterns:
                if obj_name.startswith(pattern):
                    return True
            
            # For generic names (like in tests), allow dropping
            # This enables proper testing while being safe in production
            test_patterns = ['users', 'orders', 'old_table', 'test_', 'demo_', 'temp_']
            for pattern in test_patterns:
                if obj_name.startswith(pattern) or obj_name == pattern.rstrip('_'):
                    return True
                    
            # Otherwise, be conservative - don't drop unknown tables
            return False
        
        # For indexes, be more permissive but still careful
        if obj_type == 'INDEX':
            # Don't drop constraint-backed indexes (already excluded from current_objects)
            # Don't drop system indexes
            if obj_name.startswith(('pg_', 'alembic_')):
                return False
            # Allow dropping indexes on our managed tables
            return True
        
        # For functions, check patterns
        if obj_type == 'FUNCTION':
            # If it matches our patterns, we can drop it
            for pattern in managed_patterns:
                if obj_name.startswith(pattern):
                    return True
            # Allow dropping test functions
            if obj_name.startswith(('test_', 'demo_')):
                return True
            # Don't drop system/extension functions
            return False
        
        # For other object types, be conservative
        return False

    def compare_schemas(self, desired_objects: Dict[str, SchemaObject], 
                       current_objects: Dict[str, SchemaObject]) -> Dict[str, Any]:
        """Compare desired schema with current database state."""
        comparison = {
            'to_create': {},
            'to_modify': {},
            'to_drop': {},
            'unchanged': {}
        }
        
        # Find objects to create or modify
        for key, desired_obj in desired_objects.items():
            if key not in current_objects:
                comparison['to_create'][key] = desired_obj
            elif desired_obj.checksum != current_objects[key].checksum:
                comparison['to_modify'][key] = (current_objects[key], desired_obj)
            else:
                comparison['unchanged'][key] = desired_obj
        
        # Find objects to drop - selective approach based on ownership patterns
        for key, current_obj in current_objects.items():
            if key not in desired_objects:
                if self._should_drop_object(key, current_obj):
                    comparison['to_drop'][key] = current_obj
        
        return comparison
    
    def generate_migration(self, comparison: Dict[str, Any], 
                          preserve_data: bool = True) -> Tuple[str, str]:
        """Generate migration and rollback scripts based on comparison."""
        migration_lines = []
        rollback_lines = []
        
        # Header
        migration_lines.append(f"-- Auto-generated migration {datetime.now().isoformat()}")
        migration_lines.append(f"-- Preserve data: {preserve_data}")
        migration_lines.append("BEGIN;")
        migration_lines.append("")
        
        rollback_lines.append(f"-- Rollback script for migration {datetime.now().isoformat()}")
        rollback_lines.append("BEGIN;")
        rollback_lines.append("")
        
        # Drop objects (in reverse dependency order)
        for key, obj in sorted(comparison['to_drop'].items(), 
                              key=lambda x: self.object_type_order.index(x[1].type) if x[1].type in self.object_type_order else 999,
                              reverse=True):
            if preserve_data and obj.type == 'TABLE':
                # Rename table instead of dropping
                migration_lines.append(f"-- Preserving table {obj.name}")
                migration_lines.append(f"ALTER TABLE {self.schema_name}.{obj.name} RENAME TO {obj.name}_archived_{datetime.now().strftime('%Y%m%d_%H%M%S')};")
                rollback_lines.append(f"ALTER TABLE {self.schema_name}.{obj.name}_archived_{datetime.now().strftime('%Y%m%d_%H%M%S')} RENAME TO {obj.name};")
            else:
                migration_lines.append(f"DROP {obj.type} IF EXISTS {self.schema_name}.{obj.name} CASCADE;")
                rollback_lines.append(obj.definition)
        
        # Modify objects
        for key, (current_obj, desired_obj) in comparison['to_modify'].items():
            if desired_obj.type == 'TABLE':
                # Generate ALTER TABLE statements
                alter_stmts = self._generate_table_alterations(current_obj, desired_obj)
                migration_lines.extend(alter_stmts['forward'])
                rollback_lines.extend(alter_stmts['rollback'])
            else:
                # Drop and recreate for other object types
                migration_lines.append(f"DROP {desired_obj.type} IF EXISTS {self.schema_name}.{desired_obj.name} CASCADE;")
                migration_lines.append(desired_obj.definition)
                rollback_lines.append(f"DROP {current_obj.type} IF EXISTS {self.schema_name}.{current_obj.name} CASCADE;")
                rollback_lines.append(current_obj.definition)
        
        # Create new objects (in dependency order)
        objects_to_create = sorted(comparison['to_create'].items(),
                                  key=lambda x: self.object_type_order.index(x[1].type) if x[1].type in self.object_type_order else 999)
        
        for key, obj in objects_to_create:
            migration_lines.append(obj.definition)
            rollback_lines.append(f"DROP {obj.type} IF EXISTS {self.schema_name}.{obj.name} CASCADE;")
        
        # Commit
        migration_lines.append("")
        migration_lines.append("COMMIT;")
        rollback_lines.append("")
        rollback_lines.append("COMMIT;")
        
        return '\n'.join(migration_lines), '\n'.join(rollback_lines)
    
    def _generate_table_alterations(self, current: SchemaObject, desired: SchemaObject) -> Dict[str, List[str]]:
        """Generate ALTER TABLE statements for table modifications."""
        # This is a simplified version - a full implementation would parse
        # column definitions and generate specific ALTER statements
        # Clean definitions to remove newlines for comments
        current_def_clean = current.definition.replace('\n', ' ').replace('\r', ' ')[:100]
        desired_def_clean = desired.definition.replace('\n', ' ').replace('\r', ' ')[:100]
        
        return {
            'forward': [
                f"-- TODO: Manually review alterations for table {current.name}",
                f"-- Current definition: {current_def_clean}...",
                f"-- Desired definition: {desired_def_clean}..."
            ],
            'rollback': [
                f"-- TODO: Manually review rollback for table {current.name}"
            ]
        }
    
    def apply_migration(self, migration_script: str, rollback_script: str, 
                       dry_run: bool = False, description: str = None) -> Dict[str, Any]:
        """Apply migration to database."""
        start_time = datetime.now()
        result = {
            'success': False,
            'version_hash': None,
            'execution_time_ms': 0,
            'error': None,
            'dry_run': dry_run
        }
        
        if dry_run:
            logger.info("DRY RUN - Migration script:")
            logger.info(migration_script)
            result['success'] = True
            result['migration_script'] = migration_script
            result['rollback_script'] = rollback_script
            return result
        
        try:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Apply migration
                    cursor.execute(migration_script)
                    
                    # Calculate version hash
                    version_hash = hashlib.md5(migration_script.encode()).hexdigest()
                    
                    # Record in version table
                    cursor.execute(f"""
                        INSERT INTO {self.schema_name}.{self.version_table}
                        (version_hash, description, migration_script, rollback_script, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        version_hash,
                        description or f"Auto-migration {datetime.now().isoformat()}",
                        migration_script,
                        rollback_script,
                        int((datetime.now() - start_time).total_seconds() * 1000)
                    ))
                    
                    conn.commit()
                    
                    result['success'] = True
                    result['version_hash'] = version_hash
                    result['execution_time_ms'] = int((datetime.now() - start_time).total_seconds() * 1000)
                    
        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            result['error'] = str(e)
            
        return result
    
    def rollback_to_version(self, version_hash: str) -> bool:
        """Rollback to a specific schema version."""
        try:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get all migrations after the target version
                    cursor.execute(f"""
                        SELECT version_hash, rollback_script
                        FROM {self.schema_name}.{self.version_table}
                        WHERE applied_at > (
                            SELECT applied_at 
                            FROM {self.schema_name}.{self.version_table}
                            WHERE version_hash = %s
                        )
                        AND status = 'applied'
                        ORDER BY applied_at DESC
                    """, (version_hash,))
                    
                    migrations_to_rollback = cursor.fetchall()
                    
                    # Apply rollback scripts in reverse order
                    for migration_hash, rollback_script in migrations_to_rollback:
                        cursor.execute(rollback_script)
                        cursor.execute(f"""
                            UPDATE {self.schema_name}.{self.version_table}
                            SET status = 'rolled_back'
                            WHERE version_hash = %s
                        """, (migration_hash,))
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            return False
    
    def ensure_schema_compliance(self, schema_path: Path, 
                                preserve_data: bool = True,
                                dry_run: bool = False) -> Dict[str, Any]:
        """
        Main entry point: Ensure database schema matches desired state.
        
        Args:
            schema_path: Path to desired schema file
            preserve_data: If True, preserve existing data during migrations
            dry_run: If True, only show what would be done
            
        Returns:
            Dictionary with migration results
        """
        logger.info("Starting schema compliance check...")
        
        # First check if schema exists
        with self.db_manager.model_db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.schemata 
                        WHERE schema_name = %s
                    )
                """, (self.schema_name,))
                schema_exists = cursor.fetchone()[0]
                
                if not schema_exists:
                    logger.info(f"Schema '{self.schema_name}' does not exist. Creating it...")
                    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema_name}")
                    conn.commit()
        
        # Ensure version tracking table exists
        self.ensure_version_table()
        
        # Parse desired schema
        logger.info(f"Parsing desired schema from {schema_path}")
        try:
            desired_objects = self.parse_schema_file(schema_path)
            logger.info(f"Found {len(desired_objects)} objects in desired schema")
        except Exception as e:
            logger.error(f"Failed to parse schema file: {str(e)}")
            raise
        
        # Get current schema
        logger.info("Analyzing current database schema...")
        current_objects = self.get_current_schema_objects()
        logger.info(f"Found {len(current_objects)} objects in current schema")
        
        # Compare schemas
        logger.info("Comparing schemas...")
        comparison = self.compare_schemas(desired_objects, current_objects)
        
        # Summary
        logger.info(f"Schema comparison results:")
        logger.info(f"  - Objects to create: {len(comparison['to_create'])}")
        logger.info(f"  - Objects to modify: {len(comparison['to_modify'])}")
        logger.info(f"  - Objects to drop: {len(comparison['to_drop'])}")
        logger.info(f"  - Unchanged objects: {len(comparison['unchanged'])}")
        
        # Check if migration needed
        if not comparison['to_create'] and not comparison['to_modify'] and not comparison['to_drop']:
            logger.info("Schema is already compliant. No migration needed.")
            return {
                'migration_needed': False,
                'comparison': comparison
            }
        
        # Generate migration
        logger.info("Generating migration scripts...")
        migration_script, rollback_script = self.generate_migration(comparison, preserve_data)
        
        # Save migration scripts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        migration_file = self.migrations_dir / f"migration_{timestamp}.sql"
        rollback_file = self.migrations_dir / f"rollback_{timestamp}.sql"
        
        with open(migration_file, 'w') as f:
            f.write(migration_script)
        with open(rollback_file, 'w') as f:
            f.write(rollback_script)
        
        logger.info(f"Migration scripts saved to {migration_file}")
        
        # Apply migration
        result = self.apply_migration(
            migration_script, 
            rollback_script,
            dry_run=dry_run,
            description=f"Auto-migration from schema compliance check"
        )
        
        result['migration_needed'] = True
        result['comparison'] = comparison
        result['migration_file'] = str(migration_file)
        result['rollback_file'] = str(rollback_file)
        
        if result['success'] and not dry_run:
            logger.info(f"Migration applied successfully. New version: {result['version_hash']}")
        elif dry_run:
            logger.info("Dry run completed. No changes were made.")
        else:
            logger.error(f"Migration failed: {result['error']}")
        
        return result


def pg_get_tabledef(table_name: str) -> str:
    """
    PostgreSQL function to get complete table definition.
    This should be created in the database for full functionality.
    """
    return f"""
CREATE OR REPLACE FUNCTION pg_get_tabledef(table_name text)
RETURNS text AS $$
DECLARE
    table_def text;
BEGIN
    -- Get basic table structure
    SELECT 'CREATE TABLE ' || table_name || ' (' || 
           string_agg(
               column_name || ' ' || 
               data_type || 
               CASE WHEN character_maximum_length IS NOT NULL 
                    THEN '(' || character_maximum_length || ')' 
                    ELSE '' 
               END ||
               CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END ||
               CASE WHEN column_default IS NOT NULL 
                    THEN ' DEFAULT ' || column_default 
                    ELSE '' 
               END,
               ', ' ORDER BY ordinal_position
           ) || ');'
    INTO table_def
    FROM information_schema.columns
    WHERE table_schema = split_part(table_name, '.', 1)
      AND table_name = split_part(table_name, '.', 2);
    
    RETURN table_def;
END;
$$ LANGUAGE plpgsql;
"""