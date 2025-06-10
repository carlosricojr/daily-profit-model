# Database Schema

This directory contains the database schema and maintenance scripts for the Daily Profit Model.

## Structure

- `schema.sql` - Main consolidated schema file containing all tables, indexes, functions, and materialized views
- `indexes/` - Index management and analysis scripts
- `maintenance/` - Performance testing and maintenance scripts
- `docs/` - Database documentation and analysis reports
- `archive/` - Old schema versions and migration files (not used in current development)
  - `migrations/` - Archived migration files that have been integrated into schema.sql

## Usage

### Intelligent Schema Management (Recommended)

The system now includes intelligent schema management that:
- Compares current database state with desired schema
- Generates migrations only for differences
- Preserves existing data by default
- Provides dry-run mode to preview changes
- Tracks schema versions for rollback capability

```bash
# Check schema compliance and apply changes (preserves data)
python src/pipeline_orchestration/run_pipeline.py --stages schema

# Preview what changes would be made without applying them
python src/pipeline_orchestration/run_pipeline.py --stages schema --dry-run

# Force faster migration without preserving data in dropped tables
python src/pipeline_orchestration/run_pipeline.py --stages schema --no-preserve-data
```

### Force Recreate Schema (Development Only)

**WARNING**: This will DROP the entire `prop_trading_model` schema and recreate it from scratch!

```bash
# Force drop and recreate (DESTROYS ALL DATA!)
python src/pipeline_orchestration/run_pipeline.py --stages schema --force-recreate-schema

# Or directly with psql (also destructive)
psql -U your_user -d your_database -f src/db_schema/schema.sql
```

### Setup Schema Helper Functions

For full schema comparison functionality, run this once:

```bash
psql -U your_user -d your_database -f src/db_schema/setup_schema_functions.sql
```

### Key Features

1. **Partitioned Tables**:
   - `raw_metrics_daily` - Partitioned by month
   - `raw_trades_closed` - Partitioned by month
   
2. **Materialized Views**:
   - `mv_account_performance_summary` - Account-level performance metrics
   - `mv_daily_trading_stats` - Daily aggregate statistics
   - `mv_symbol_performance` - Symbol-level performance analysis
   - `mv_account_trading_patterns` - Trading behavior patterns
   - `mv_market_regime_performance` - Performance by market conditions

3. **Functions**:
   - `refresh_materialized_views()` - Refresh all materialized views
   - `create_monthly_partitions()` - Create new monthly partitions
   - `drop_old_partitions()` - Clean up old partitions

## Schema Versioning

The system automatically tracks schema versions in the `schema_version` table:

```sql
-- View migration history
SELECT version_id, version_hash, applied_at, description, status
FROM prop_trading_model.schema_version
ORDER BY applied_at DESC;

-- View current schema version
SELECT version_hash, applied_at
FROM prop_trading_model.schema_version
WHERE status = 'applied'
ORDER BY applied_at DESC
LIMIT 1;
```

Auto-generated migrations are saved in `src/db_schema/auto_migrations/` with timestamp-based naming.

## Recent Schema Changes

- **Trades Tables**: The `account_id` column in both `raw_trades_closed` and `raw_trades_open` tables is now nullable. This allows ingestion of trades where only the login is available initially, with account_id being resolved later when platform/mt_version mapping is implemented. Login indexes have been added for efficient account resolution.

## Development Notes

The system supports two modes:

1. **Intelligent Migration Mode** (Default):
   - Compares current schema with desired state
   - Generates minimal migrations
   - Preserves data
   - Tracks versions
   - Supports rollback

2. **Force Recreate Mode** (Development):
   - Drops entire schema
   - Recreates from scratch
   - Fast but destructive
   - Good for initial setup or testing

## Partition Management

The schema automatically creates partitions for the last 3 years plus 3 months into the future. To add more partitions:

```sql
SELECT prop_trading_model.create_monthly_partitions('raw_metrics_daily', '2025-01-01'::date, '2025-12-31'::date);
SELECT prop_trading_model.create_monthly_partitions('raw_trades_closed', '2025-01-01'::date, '2025-12-31'::date);
```

## Performance Monitoring

Use the scripts in `maintenance/` to monitor performance:

```sql
-- Check partition sizes and usage
SELECT * FROM prop_trading_model.v_partition_stats;

-- Run performance tests
\i maintenance/performance_tests.sql
```