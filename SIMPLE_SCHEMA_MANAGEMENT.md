# Simple Schema Management Approach

## Goal: One Simple, Reliable System

Replace 2,600+ lines of complex schema management with <300 lines of simple, reliable code.

## Recommended Approach: Pure Alembic

### Why Alembic?
- Industry standard (used by Reddit, Yelp, OpenStack)
- Battle-tested with PostgreSQL
- Handles all edge cases
- Great documentation
- Simple CLI

### Implementation in 5 Steps

## Step 1: Clean Setup (30 minutes)

```bash
# Clean out old complexity
rm -rf src/utils/schema_manager.py
rm -rf src/utils/alembic_schema_manager.py  
rm -rf src/utils/enhanced_alembic_schema_manager.py
rm -rf src/utils/migration_handler.py

# Initialize clean Alembic
cd /home/carlos/trading/daily-profit-model
alembic init src/db_schema/alembic_clean

# Configure for your database
sed -i 's|sqlalchemy.url = .*|sqlalchemy.url = postgresql://user:pass@localhost/dbname|' src/db_schema/alembic_clean/alembic.ini
```

## Step 2: Simple Configuration (src/db_schema/alembic_clean/env.py)

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import your models
from db_schema.models import Base

config = context.config

# Override with environment variable
db_url = os.getenv('DATABASE_URL')
if db_url:
    config.set_main_option('sqlalchemy.url', db_url)

target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema='prop_trading_model',
        include_schemas=True
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
            version_table_schema='prop_trading_model',
            include_schemas=True
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

## Step 3: Simple Wrapper (src/utils/db.py)

```python
"""
Simple database utilities.
This is ALL you need for schema management.
"""
import os
import logging
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

class Database:
    """Simple database management."""
    
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/postgres')
        self.alembic_ini = Path(__file__).parent.parent / "db_schema/alembic_clean/alembic.ini"
        
    def ensure_current(self):
        """Ensure database is up to date with latest migrations."""
        cfg = Config(str(self.alembic_ini))
        cfg.set_main_option("sqlalchemy.url", self.db_url)
        
        try:
            # This is all you need!
            command.upgrade(cfg, "head")
            logger.info("Database schema is current")
        except Exception as e:
            logger.error(f"Failed to upgrade database: {e}")
            raise
    
    def create_migration(self, message: str):
        """Create a new migration."""
        cfg = Config(str(self.alembic_ini))
        cfg.set_main_option("sqlalchemy.url", self.db_url)
        
        try:
            revision = command.revision(cfg, autogenerate=True, message=message)
            logger.info(f"Created migration: {revision}")
            return revision
        except Exception as e:
            logger.error(f"Failed to create migration: {e}")
            raise
            
    def get_current_revision(self):
        """Get current database revision."""
        cfg = Config(str(self.alembic_ini))
        cfg.set_main_option("sqlalchemy.url", self.db_url)
        
        # Simple and works
        engine = create_engine(self.db_url)
        with engine.connect() as conn:
            result = conn.execute(
                "SELECT version_num FROM prop_trading_model.alembic_version"
            )
            row = result.first()
            return row[0] if row else None

# That's it! No more complexity needed.
```

## Step 4: Update Pipeline (src/pipeline_orchestration/run_pipeline.py)

```python
def _create_schema(self, force_recreate=False, preserve_data=True, dry_run=False):
    """Simplified schema management."""
    if force_recreate:
        logger.warning("Force recreate not supported with Alembic. Use migrations instead.")
        return
        
    # This is all you need!
    from utils.db import Database
    db = Database()
    
    if dry_run:
        logger.info("Dry run: Would check and apply migrations")
    else:
        db.ensure_current()
```

## Step 5: Developer Workflow

```bash
# Make model changes in models.py
vim src/db_schema/models.py

# Generate migration
alembic revision --autogenerate -m "Add new trading metrics"

# Review the generated migration
vim src/db_schema/alembic_clean/versions/xxx_add_new_trading_metrics.py

# Apply migration
alembic upgrade head

# That's it!
```

## Production Deployment

```bash
# Check pending migrations
alembic current
alembic history

# Generate SQL for review (safe!)
alembic upgrade head --sql > pending_changes.sql

# Apply after review
alembic upgrade head
```

## Handling Partitions Simply

Instead of complex partition migration manager:

```python
# In your Alembic migration file
def upgrade():
    # Create partitioned table
    op.execute("""
        CREATE TABLE raw_metrics_daily (
            account_id TEXT,
            date DATE,
            balance DECIMAL(15,2),
            -- ... other columns
        ) PARTITION BY RANGE (date);
    """)
    
    # Create partitions for next 12 months
    for month in range(12):
        date = datetime.now() + relativedelta(months=month)
        partition_name = f"raw_metrics_daily_{date.strftime('%Y_%m')}"
        start_date = date.replace(day=1)
        end_date = start_date + relativedelta(months=1)
        
        op.execute(f"""
            CREATE TABLE {partition_name} 
            PARTITION OF raw_metrics_daily
            FOR VALUES FROM ('{start_date}') TO ('{end_date}');
        """)
```

## Partition Maintenance (Cron Job)

```python
#!/usr/bin/env python3
# create_future_partitions.py - Run monthly via cron

import psycopg2
from datetime import datetime
from dateutil.relativedelta import relativedelta

def create_future_partitions():
    """Create partitions for next 3 months."""
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()
    
    tables = ['raw_metrics_daily', 'raw_metrics_hourly', 'raw_trades_closed']
    
    for table in tables:
        for month_offset in range(1, 4):  # Next 3 months
            date = datetime.now() + relativedelta(months=month_offset)
            partition_name = f"{table}_{date.strftime('%Y_%m')}"
            start_date = date.replace(day=1)
            end_date = start_date + relativedelta(months=1)
            
            # Create if not exists
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS prop_trading_model.{partition_name}
                PARTITION OF prop_trading_model.{table}
                FOR VALUES FROM ('{start_date}') TO ('{end_date}');
            """)
    
    conn.commit()
    conn.close()
    print("Partitions created successfully")

if __name__ == "__main__":
    create_future_partitions()
```

## Benefits of This Approach

### 1. **Simplicity**
- 300 lines vs 2,600 lines
- Standard Alembic commands
- No custom parsing or comparison

### 2. **Reliability**
- Alembic handles all edge cases
- Atomic migrations
- Proven in production

### 3. **Developer Experience**
```bash
# Everyone knows these commands
alembic revision --autogenerate -m "message"
alembic upgrade head
alembic downgrade -1
```

### 4. **Safety**
- SQL preview before applying
- Easy rollbacks
- Version control friendly

### 5. **Performance**
- No schema parsing on every run
- Fast migration checks
- Minimal overhead

## Migration from Current System

1. **Create Initial Migration**
   ```bash
   # Capture current state
   alembic revision --autogenerate -m "Initial schema from existing database"
   # Mark as applied without running
   alembic stamp head
   ```

2. **Remove Old Systems**
   ```bash
   # Clean up
   rm -rf src/db_schema/auto_migrations
   rm -rf src/utils/*schema_manager*.py
   ```

3. **Update Documentation**
   - Document the simple workflow
   - Remove complex procedures
   - Add to README

## Common Tasks Made Simple

### Add a Column
```bash
alembic revision --autogenerate -m "Add risk_score to accounts"
alembic upgrade head
```

### Create an Index
```bash
alembic revision --autogenerate -m "Add index on trade_date"
alembic upgrade head
```

### Add a Table
```python
# Just add to models.py, then:
alembic revision --autogenerate -m "Add model_predictions table"
alembic upgrade head
```

## That's It!

No more:
- Custom schema parsing
- Complex comparison logic
- Migration loops
- Multiple tracking tables
- Over-engineered safety checks

Just simple, reliable schema management that works.