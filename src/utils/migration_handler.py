"""
Database migration handler for the daily profit model.
Manages schema creation and migrations in a controlled manner.
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class MigrationHandler:
    """Handles database schema creation and migrations."""
    
    def __init__(self, db_connection, schema_dir: Path):
        """
        Initialize the migration handler.
        
        Args:
            db_connection: DatabaseConnection instance
            schema_dir: Path to directory containing schema and migrations
        """
        self.db = db_connection
        self.schema_dir = schema_dir
        self.schema_file = schema_dir / "schema.sql"
        self.migrations_dir = schema_dir / "migrations"
        
    def ensure_schema_exists(self) -> bool:
        """
        Ensure the database schema exists and is up to date.
        
        Returns:
            True if schema was created or updated, False if already up to date
        """
        logger.info("Checking database schema status...")
        
        # First check if schema exists
        if not self._schema_exists():
            logger.info("Schema does not exist, creating...")
            self._create_schema()
            self._run_migrations()
            return True
            
        # Schema exists, check if migrations are needed
        pending_migrations = self._get_pending_migrations()
        if pending_migrations:
            logger.info(f"Found {len(pending_migrations)} pending migrations")
            self._run_migrations(pending_migrations)
            return True
            
        logger.info("Schema is up to date")
        return False
        
    def _schema_exists(self) -> bool:
        """Check if the prop_trading_model schema exists."""
        query = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.schemata 
            WHERE schema_name = 'prop_trading_model'
        )
        """
        result = self.db.execute_query(query)
        return result[0]["exists"] if result else False
        
    def _create_schema(self):
        """Create the initial database schema."""
        if not self.schema_file.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_file}")
            
        logger.info(f"Creating database schema from {self.schema_file}")
        
        # Read schema file
        with open(self.schema_file, "r") as f:
            schema_sql = f.read()
            
        # Execute schema creation
        with self.db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(schema_sql)
                
        logger.info("Database schema created successfully")
        
    def _get_pending_migrations(self) -> List[Dict[str, Any]]:
        """Get list of migrations that haven't been applied yet."""
        # First check if migration tracking table exists
        if not self._migration_table_exists():
            return self._get_all_migrations()
            
        # Get applied migrations
        query = """
        SELECT migration_name, checksum 
        FROM prop_trading_model.schema_migrations
        ORDER BY applied_at
        """
        applied = {row["migration_name"]: row["checksum"] 
                  for row in self.db.execute_query(query)}
        
        # Get all migration files
        all_migrations = self._get_all_migrations()
        
        # Find pending migrations
        pending = []
        for migration in all_migrations:
            name = migration["name"]
            checksum = migration["checksum"]
            
            if name not in applied:
                pending.append(migration)
            elif applied[name] != checksum:
                logger.warning(f"Migration {name} has been modified! "
                             f"Expected checksum: {applied[name]}, "
                             f"Current checksum: {checksum}")
                # In production, this should raise an error
                # For now, we'll skip modified migrations
                
        return pending
        
    def _get_all_migrations(self) -> List[Dict[str, Any]]:
        """Get all migration files sorted by name."""
        if not self.migrations_dir.exists():
            return []
            
        migrations = []
        for file_path in sorted(self.migrations_dir.glob("*.sql")):
            with open(file_path, "r") as f:
                content = f.read()
                
            migrations.append({
                "name": file_path.name,
                "path": file_path,
                "content": content,
                "checksum": hashlib.sha256(content.encode()).hexdigest()
            })
            
        return migrations
        
    def _migration_table_exists(self) -> bool:
        """Check if the migration tracking table exists."""
        query = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'prop_trading_model' 
            AND table_name = 'schema_migrations'
        )
        """
        result = self.db.execute_query(query)
        return result[0]["exists"] if result else False
        
    def _create_migration_table(self):
        """Create the migration tracking table."""
        query = """
        CREATE TABLE IF NOT EXISTS prop_trading_model.schema_migrations (
            migration_name VARCHAR(255) PRIMARY KEY,
            checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            applied_by VARCHAR(100) DEFAULT CURRENT_USER,
            execution_time_ms INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT
        );
        
        COMMENT ON TABLE prop_trading_model.schema_migrations IS 
        'Tracks applied database migrations';
        """
        self.db.execute_command(query)
        logger.info("Created migration tracking table")
        
    def _run_migrations(self, migrations: Optional[List[Dict[str, Any]]] = None):
        """Run pending migrations."""
        # Ensure migration tracking table exists
        if not self._migration_table_exists():
            self._create_migration_table()
            
        # Get migrations to run
        if migrations is None:
            migrations = self._get_all_migrations()
            
        for migration in migrations:
            self._apply_migration(migration)
            
    def _apply_migration(self, migration: Dict[str, Any]):
        """Apply a single migration."""
        name = migration["name"]
        content = migration["content"]
        checksum = migration["checksum"]
        
        logger.info(f"Applying migration: {name}")
        start_time = datetime.now()
        
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Execute migration
                    cursor.execute(content)
                    
                    # Record successful migration
                    execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    cursor.execute("""
                        INSERT INTO prop_trading_model.schema_migrations 
                        (migration_name, checksum, execution_time_ms, success)
                        VALUES (%s, %s, %s, TRUE)
                    """, (name, checksum, execution_time_ms))
                    
            logger.info(f"Successfully applied migration: {name} ({execution_time_ms}ms)")
            
        except Exception as e:
            logger.error(f"Failed to apply migration {name}: {str(e)}")
            
            # Record failed migration
            try:
                with self.db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO prop_trading_model.schema_migrations 
                            (migration_name, checksum, success, error_message)
                            VALUES (%s, %s, FALSE, %s)
                            ON CONFLICT (migration_name) DO UPDATE
                            SET success = FALSE, error_message = EXCLUDED.error_message
                        """, (name, checksum, str(e)))
            except Exception:
                pass  # Don't fail if we can't record the failure
                
            raise
            
    def get_migration_status(self) -> List[Dict[str, Any]]:
        """Get the status of all migrations."""
        if not self._migration_table_exists():
            return []
            
        query = """
        SELECT 
            migration_name,
            checksum,
            applied_at,
            applied_by,
            execution_time_ms,
            success,
            error_message
        FROM prop_trading_model.schema_migrations
        ORDER BY applied_at DESC
        """
        return self.db.execute_query(query)