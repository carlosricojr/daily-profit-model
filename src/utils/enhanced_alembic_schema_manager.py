"""
Enhanced Alembic Schema Manager for Production Trading Systems

This module implements sophisticated schema management following ML/trading best practices:
- Hybrid migration strategy (SQL + autogenerate)
- SQLAlchemy models for type safety and ML integration
- Production-grade safety validation
- Existing database synchronization
- Trading-specific safeguards
"""

import os
import re
import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
import tempfile
import subprocess
import sys
from dataclasses import dataclass

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, MetaData, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable, CreateIndex

from .database import DatabaseManager
from .partition_migration_manager import PartitionMigrationManager

logger = logging.getLogger(__name__)


@dataclass
class MigrationRisk:
    """Represents a migration risk assessment."""
    level: str  # CRITICAL, WARNING, INFO
    category: str  # DATA_LOSS, PERFORMANCE, TRADING_CONTINUITY
    message: str
    blocking: bool = False


class TradingSystemValidator:
    """Validates migrations for production trading system safety."""
    
    # Trading hours (UTC) - adjust for your market
    MARKET_OPEN = time(13, 30)  # 9:30 AM EST
    MARKET_CLOSE = time(20, 0)   # 4:00 PM EST
    
    # Critical trading tables that require special handling
    TRADING_TABLES = {
        'raw_trades_closed', 'raw_trades_open', 'raw_metrics_alltime',
        'raw_metrics_daily', 'raw_metrics_hourly', 'features_engineered'
    }
    
    # Operations that can cause data loss
    DATA_LOSS_PATTERNS = [
        r'\bDROP\s+TABLE\b',
        r'\bDROP\s+COLUMN\b',
        r'\bTRUNCATE\b',
        r'\bDELETE\s+FROM\b',
        r'\bALTER\s+COLUMN\s+.*\s+DROP\s+NOT\s+NULL\b'
    ]
    
    # Operations that can block for extended periods
    BLOCKING_PATTERNS = [
        r'\bALTER\s+TABLE\s+.*\s+ADD\s+COLUMN\s+.*\s+NOT\s+NULL\b',
        r'\bCREATE\s+INDEX\s+(?!CONCURRENTLY)\b',
        r'\bALTER\s+TABLE\s+.*\s+ALTER\s+COLUMN\s+.*\s+TYPE\b'
    ]
    
    def __init__(self):
        self.risks: List[MigrationRisk] = []
    
    def validate_migration(self, migration_script: str, affected_tables: Set[str]) -> Dict[str, Any]:
        """Comprehensive migration validation for trading systems."""
        self.risks = []
        
        # Check for data loss operations
        self._check_data_loss_operations(migration_script)
        
        # Check for blocking operations
        self._check_blocking_operations(migration_script, affected_tables)
        
        # Check trading continuity
        self._check_trading_continuity(affected_tables)
        
        # Check performance impact
        self._check_performance_impact(migration_script, affected_tables)
        
        # Determine if migration is safe
        critical_risks = [r for r in self.risks if r.level == "CRITICAL"]
        blocking_risks = [r for r in self.risks if r.blocking]
        
        return {
            "safe": len(critical_risks) == 0 and len(blocking_risks) == 0,
            "risks": [{"level": r.level, "category": r.category, "message": r.message} for r in self.risks],
            "critical_count": len(critical_risks),
            "blocking_count": len(blocking_risks),
            "recommendation": self._get_recommendation()
        }
    
    def _check_data_loss_operations(self, script: str):
        """Check for operations that could cause data loss."""
        for pattern in self.DATA_LOSS_PATTERNS:
            if re.search(pattern, script, re.IGNORECASE):
                self.risks.append(MigrationRisk(
                    level="CRITICAL",
                    category="DATA_LOSS",
                    message=f"Potential data loss operation detected: {pattern}",
                    blocking=True
                ))
    
    def _check_blocking_operations(self, script: str, affected_tables: Set[str]):
        """Check for operations that could block trading operations."""
        for pattern in self.BLOCKING_PATTERNS:
            if re.search(pattern, script, re.IGNORECASE):
                # Check if it affects trading tables
                affects_trading = bool(affected_tables.intersection(self.TRADING_TABLES))
                level = "CRITICAL" if affects_trading else "WARNING"
                
                self.risks.append(MigrationRisk(
                    level=level,
                    category="PERFORMANCE",
                    message=f"Blocking operation detected: {pattern}",
                    blocking=affects_trading
                ))
    
    def _check_trading_continuity(self, affected_tables: Set[str]):
        """Check if migration affects trading during market hours."""
        if self._is_market_hours():
            trading_tables_affected = affected_tables.intersection(self.TRADING_TABLES)
            if trading_tables_affected:
                self.risks.append(MigrationRisk(
                    level="CRITICAL",
                    category="TRADING_CONTINUITY",
                    message=f"Trading tables affected during market hours: {trading_tables_affected}",
                    blocking=True
                ))
    
    def _check_performance_impact(self, script: str, affected_tables: Set[str]):
        """Assess performance impact of migration."""
        large_tables = {'raw_trades_closed', 'raw_metrics_daily', 'features_engineered'}
        affected_large_tables = affected_tables.intersection(large_tables)
        
        if affected_large_tables and re.search(r'\bALTER\s+TABLE\b', script, re.IGNORECASE):
            self.risks.append(MigrationRisk(
                level="WARNING",
                category="PERFORMANCE",
                message=f"Large table modification may take significant time: {affected_large_tables}"
            ))
    
    def _is_market_hours(self) -> bool:
        """Check if current time is during market hours."""
        now = datetime.utcnow().time()
        return self.MARKET_OPEN <= now <= self.MARKET_CLOSE
    
    def _get_recommendation(self) -> str:
        """Get recommendation based on risk assessment."""
        critical_risks = [r for r in self.risks if r.level == "CRITICAL"]
        
        if critical_risks:
            return "REJECT: Critical risks detected. Manual review required."
        elif self._is_market_hours():
            return "DEFER: Consider running during off-market hours."
        elif any(r.level == "WARNING" for r in self.risks):
            return "CAUTION: Proceed with monitoring and rollback plan."
        else:
            return "APPROVE: Migration appears safe to execute."


class EnhancedAlembicSchemaManager:
    """
    Enhanced Alembic schema manager for production trading systems.
    
    Features:
    - Hybrid migration strategy (SQL + autogenerate)
    - SQLAlchemy models integration
    - Production-grade safety validation
    - Existing database synchronization
    - Trading-specific safeguards
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.schema_name = "prop_trading_model"  # Hardcoded as per requirements
        
        # Create SQLAlchemy engine
        self.engine = self._create_sqlalchemy_engine()
        
        # Setup Alembic configuration
        self._alembic_dir = Path(__file__).parent.parent / "db_schema" / "alembic"
        self._alembic_dir.mkdir(exist_ok=True)
        
        # Initialize validator
        self.validator = TradingSystemValidator()
        
        # Initialize partition migration manager
        self.partition_manager = PartitionMigrationManager(db_manager)
        
        # Setup Alembic with models
        self.alembic_cfg = self._setup_alembic_config()
        
        # Track if this is initial setup
        self._is_initial_setup = False
    
    @property
    def alembic_dir(self) -> Path:
        """Get the Alembic directory path."""
        return self._alembic_dir
    
    def _create_sqlalchemy_engine(self) -> Engine:
        """Create SQLAlchemy engine with production settings."""
        db_config = self.db_manager.model_db
        connection_string = (
            f"postgresql://{db_config.user}:{db_config.password}"
            f"@{db_config.host}:{db_config.port}/{db_config.database}"
        )
        
        engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
            echo=False,  # Set to True for debugging
            # Production settings
            connect_args={
                "application_name": "trading_schema_manager",
                "options": f"-csearch_path={self.schema_name},public"
            }
        )
        
        return engine
    
    def _setup_alembic_config(self) -> Config:
        """Setup enhanced Alembic configuration with models."""
        # Create alembic.ini
        alembic_ini = self.alembic_dir / "alembic.ini"
        if not alembic_ini.exists():
            self._create_alembic_ini(alembic_ini)
        
        # Create versions directory
        versions_dir = self.alembic_dir / "versions"
        versions_dir.mkdir(exist_ok=True)
        
        # Create enhanced env.py with models
        env_py = self.alembic_dir / "env.py"
        if not env_py.exists():
            self._create_enhanced_env_py(env_py)
        
        # Create script template
        script_mako = self.alembic_dir / "script.py.mako"
        if not script_mako.exists():
            self._create_enhanced_script_mako(script_mako)
        
        # Configure Alembic
        alembic_cfg = Config(str(alembic_ini))
        alembic_cfg.set_main_option("script_location", str(self.alembic_dir))
        alembic_cfg.set_main_option("sqlalchemy.url", str(self.engine.url))
        
        return alembic_cfg
    
    def create_baseline_migration(self) -> Dict[str, Any]:
        """
        Create baseline migration for existing database.
        
        This is critical for syncing Alembic with existing production data.
        """
        try:
            logger.info("Creating baseline migration for existing database...")
            
            # Check if database has existing schema
            with self.engine.connect() as conn:
                inspector = inspect(conn)
                existing_tables = inspector.get_table_names(schema=self.schema_name)
                
                if not existing_tables:
                    logger.info("No existing tables found, proceeding with normal migration")
                    return {"baseline_created": False, "reason": "no_existing_tables"}
            
            # Create baseline migration that represents current state
            revision_id = command.revision(
                self.alembic_cfg,
                message="Baseline migration for existing database",
                autogenerate=True
            )
            
            # Stamp the database at this revision without applying changes
            command.stamp(self.alembic_cfg, revision_id)
            
            logger.info(f"Created baseline migration: {revision_id}")
            self._is_initial_setup = True
            
            return {
                "baseline_created": True,
                "revision_id": revision_id,
                "existing_tables": len(existing_tables),
                "message": "Baseline migration created and database stamped"
            }
            
        except Exception as e:
            logger.error(f"Failed to create baseline migration: {e}")
            raise
    
    def ensure_schema_compliance(
        self, 
        schema_path: Path, 
        preserve_data: bool = True,
        dry_run: bool = False,
        force_baseline: bool = False
    ) -> Dict[str, Any]:
        """
        Enhanced schema compliance with existing database support.
        """
        try:
            # Ensure schema exists
            self.ensure_schema_exists()
            
            # Check if this is first-time setup with existing data
            needs_baseline = self._needs_baseline_migration()
            
            if needs_baseline or force_baseline:
                baseline_result = self.create_baseline_migration()
                if baseline_result["baseline_created"]:
                    return {
                        "success": True,
                        "migration_needed": False,
                        "baseline_created": True,
                        "message": "Baseline migration created for existing database"
                    }
            
            # Check for partition table conversions needed
            partition_check = self._check_partition_migrations_needed()
            
            if partition_check["partitioning_needed"]:
                logger.info(f"Tables need partitioning: {partition_check['tables_to_partition']}")
                
                # Handle partition migrations separately
                if not dry_run:
                    partition_results = self._handle_partition_migrations(
                        partition_check["tables_to_partition"],
                        dry_run=dry_run
                    )
                    
                    if not partition_results["success"]:
                        return partition_results
                else:
                    return {
                        "success": True,
                        "dry_run": True,
                        "partition_migrations_needed": True,
                        "tables_to_partition": partition_check["tables_to_partition"],
                        "message": "Partition migrations would be applied"
                    }
            
            # Standard migration flow
            return self._standard_migration_flow(schema_path, dry_run)
            
        except Exception as e:
            logger.error(f"Schema compliance check failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Schema compliance check failed"
            }
    
    def _needs_baseline_migration(self) -> bool:
        """Check if baseline migration is needed."""
        try:
            with self.engine.connect() as conn:
                # Check if alembic_version table exists
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = %s AND table_name = 'alembic_version'
                    )
                """), (self.schema_name,))
                
                alembic_exists = result.scalar()
                
                if not alembic_exists:
                    # Check if trading tables exist
                    inspector = inspect(conn)
                    existing_tables = inspector.get_table_names(schema=self.schema_name)
                    trading_tables = [t for t in existing_tables if t.startswith(('raw_', 'features_'))]
                    
                    return len(trading_tables) > 0
                
                return False
                
        except Exception as e:
            logger.warning(f"Could not determine baseline need: {e}")
            return False
    
    def _standard_migration_flow(self, schema_path: Path, dry_run: bool) -> Dict[str, Any]:
        """Standard migration flow after baseline is established."""
        try:
            # Check for pending migrations
            with self.engine.connect() as conn:
                script_dir = ScriptDirectory.from_config(self.alembic_cfg)
                context = MigrationContext.configure(conn)
                current_rev = context.get_current_revision()
                head_rev = script_dir.get_current_head()
                
                if current_rev == head_rev:
                    logger.info("Database schema is up to date")
                    return {
                        "success": True,
                        "migration_needed": False,
                        "message": "Schema is already compliant"
                    }
            
            # Apply pending migrations with validation
            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "message": "Dry run completed - migrations would be applied"
                }
            
            # Apply migrations
            command.upgrade(self.alembic_cfg, "head")
            
            return {
                "success": True,
                "migration_needed": True,
                "message": "Migrations applied successfully"
            }
            
        except Exception as e:
            logger.error(f"Standard migration flow failed: {e}")
            raise
    
    def _check_partition_migrations_needed(self) -> Dict[str, Any]:
        """
        Check if any tables need to be converted to partitioned tables.
        
        Compares current database state with schema.sql to detect:
        - Tables that should be partitioned but aren't
        - Tables with significant data that would benefit from partitioning
        """
        tables_to_partition = []
        
        try:
            with self.engine.connect() as conn:
                # Check raw_metrics_hourly specifically (your test case)
                hourly_analysis = self.partition_manager.analyze_table_for_partitioning("raw_metrics_hourly")
                
                if hourly_analysis["needs_partitioning"]:
                    tables_to_partition.append({
                        "table_name": "raw_metrics_hourly",
                        "analysis": hourly_analysis,
                        "partition_column": "date",
                        "strategy": "monthly"
                    })
                
                # Check other potentially large tables
                for table_name in ["raw_trades_closed", "raw_trades_open"]:
                    try:
                        analysis = self.partition_manager.analyze_table_for_partitioning(table_name)
                        if analysis["needs_partitioning"]:
                            tables_to_partition.append({
                                "table_name": table_name,
                                "analysis": analysis,
                                "partition_column": "trade_date" if "trades" in table_name else "date",
                                "strategy": "monthly"
                            })
                    except Exception as e:
                        logger.warning(f"Could not analyze {table_name} for partitioning: {e}")
                
                return {
                    "partitioning_needed": len(tables_to_partition) > 0,
                    "tables_to_partition": tables_to_partition
                }
                
        except Exception as e:
            logger.error(f"Failed to check partition migrations: {e}")
            return {
                "partitioning_needed": False,
                "tables_to_partition": [],
                "error": str(e)
            }
    
    def _handle_partition_migrations(
        self,
        tables_to_partition: List[Dict[str, Any]],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Handle conversion of regular tables to partitioned tables.
        
        This is done separately from standard Alembic migrations because:
        - Requires complex data migration logic
        - Needs special handling for large tables
        - Must validate data integrity
        """
        results = {
            "success": True,
            "migrations": []
        }
        
        for table_info in tables_to_partition:
            table_name = table_info["table_name"]
            
            logger.info(f"Processing partition migration for {table_name}")
            
            try:
                # Use partition manager to convert table
                migration_result = self.partition_manager.convert_to_partitioned_table(
                    table_name=table_name,
                    partition_column=table_info["partition_column"],
                    partition_strategy=table_info["strategy"],
                    batch_size=50000,  # Larger batches for better performance
                    dry_run=dry_run
                )
                
                results["migrations"].append({
                    "table": table_name,
                    "result": migration_result
                })
                
                if not migration_result.get("success", False) and not dry_run:
                    results["success"] = False
                    results["error"] = f"Failed to partition {table_name}: {migration_result.get('error')}"
                    break
                    
            except Exception as e:
                logger.error(f"Partition migration failed for {table_name}: {e}")
                results["success"] = False
                results["error"] = str(e)
                break
        
        return results
    
    def ensure_schema_exists(self):
        """Ensure the target schema exists."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"
                ), {"schema": self.schema_name})
                
                if not result.scalar():
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {self.schema_name}"))
                    conn.commit()
                    logger.info(f"Created schema: {self.schema_name}")
                else:
                    logger.info(f"Schema already exists: {self.schema_name}")
                    
        except Exception as e:
            logger.error(f"Failed to ensure schema exists: {e}")
            raise
    
    def _create_alembic_ini(self, ini_path: Path):
        """Create enhanced alembic.ini for trading systems."""
        ini_content = f"""# Enhanced Alembic configuration for trading systems

[alembic]
script_location = {self.alembic_dir}
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
prepend_sys_path = .
timezone = UTC
truncate_slug_length = 40
revision_environment = true
sourceless = false
version_path_separator = os
recursive_version_locations = false
output_encoding = utf-8

[trading]
schema_name = {self.schema_name}
validate_safety = true
market_hours_protection = true

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = INFO
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = INFO
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
        with open(ini_path, 'w') as f:
            f.write(ini_content)
    
    def _create_enhanced_env_py(self, env_path: Path):
        """Create enhanced env.py with SQLAlchemy models integration."""
        env_content = '''"""Enhanced Alembic environment for trading systems."""

import logging
import sys
from pathlib import Path
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Add src to path for model imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.append(str(src_path))

# Import trading system models (will be created)
try:
    from db_schema.models import Base
    target_metadata = Base.metadata
except ImportError:
    # Fallback if models not available yet
    target_metadata = None
    logging.warning("Trading models not found, using reflection")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger('alembic.env')

def include_object(object, name, type_, reflected, compare_to):
    """Control what objects are included in autogenerate."""
    if type_ == "table" and name.startswith(("temp_", "pg_")):
        return False
    return True

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        version_table_schema="prop_trading_model"
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
            version_table_schema="prop_trading_model"
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''
        with open(env_path, 'w') as f:
            f.write(env_content)
    
    def _create_enhanced_script_mako(self, script_path: Path):
        """Create enhanced script template with safety checks."""
        script_content = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Trading System Migration - Validated for Production Safety
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    """Apply migration changes."""
    ${upgrades if upgrades else "pass"}


def downgrade():
    """Rollback migration changes."""
    ${downgrades if downgrades else "pass"}
'''
        with open(script_path, 'w') as f:
            f.write(script_content)


def create_enhanced_alembic_schema_manager(db_manager: DatabaseManager) -> EnhancedAlembicSchemaManager:
    """Factory function for enhanced Alembic schema manager."""
    try:
        return EnhancedAlembicSchemaManager(db_manager)
    except Exception as e:
        logger.error(f"Failed to create enhanced Alembic schema manager: {e}")
        raise 