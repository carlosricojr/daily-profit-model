# Migration Guide: Custom Schema Management → Alembic

This document outlines the migration from our custom schema management system to Alembic-based schema management.

## Overview

We're transitioning from a custom-built schema management system to Alembic (SQLAlchemy's migration tool) to leverage:

- **Industry-standard migrations**: Proven, battle-tested migration system
- **Automatic dependency resolution**: No more manual dependency ordering
- **Better rollback capabilities**: More reliable rollback mechanisms
- **Reduced maintenance**: Less custom code to maintain
- **Enhanced safety**: Built-in safeguards and best practices

## What's Changing

### Before (Custom System)
- Custom SQL parsing with regex
- Manual dependency management
- Custom version tracking table (`schema_version`)
- Custom migration script generation
- Manual rollback script creation

### After (Alembic Integration)
- Alembic's proven migration system
- Automatic dependency resolution
- Standard `alembic_version` table
- Alembic's autogenerate feature
- Built-in rollback capabilities

## What's Being Preserved

### Kept Features
1. **Schema validation tests** - All existing validation continues to work
2. **Field mapping validation** - API-to-schema alignment checks remain
3. **Dry-run capabilities** - Preview migrations before applying
4. **Data preservation** - Safe migrations without data loss
5. **Backward compatibility** - Fallback to custom system if needed
6. **Integration points** - Same interface for pipeline orchestration

### Kept Files
- `schema.sql` - Master schema definition (unchanged)
- `setup_schema_functions.sql` - Helper functions (unchanged)
- `test_schema_validation.py` - Schema validation tests (unchanged)
- `test_schema_field_mapping_alignment.py` - Field mapping tests (unchanged)

## New Components

### New Files
- `src/utils/alembic_schema_manager.py` - Alembic integration
- `src/db_schema/alembic/` - Alembic configuration directory
  - `alembic.ini` - Alembic configuration
  - `env.py` - Migration environment
  - `script.py.mako` - Migration template
  - `versions/` - Migration files directory
- `tests/test_alembic_schema_manager.py` - Alembic integration tests

### Updated Files
- `src/pipeline_orchestration/run_pipeline.py` - Uses Alembic with fallback
- `airflow/dags/airflow_dag.py` - Uses Alembic with fallback

## Migration Process

### Phase 1: Preparation (Current)
- [x] Install Alembic and SQLAlchemy dependencies
- [x] Create `AlembicSchemaManager` class
- [x] Implement fallback mechanism
- [x] Update pipeline orchestration
- [x] Create comprehensive tests

### Phase 2: Transition
1. **Initialize Alembic** (first run):
   ```bash
   # The system will automatically:
   # - Create alembic configuration
   # - Initialize version control
   # - Stamp current state as baseline
   python -m src.pipeline_orchestration.run_pipeline --stages schema --dry-run
   ```

2. **Verify transition**:
   ```bash
   # Check that Alembic is working
   python -m src.pipeline_orchestration.run_pipeline --stages schema
   ```

### Phase 3: Cleanup (Future)
- Remove custom schema management code (optional)
- Archive old migration files
- Update documentation

## Usage Examples

### Basic Schema Management
```python
from src.utils.alembic_schema_manager import create_alembic_schema_manager
from src.utils.database import get_db_manager

# Create manager
db_manager = get_db_manager()
schema_manager = create_alembic_schema_manager(db_manager)

# Ensure schema compliance
result = schema_manager.ensure_schema_compliance(
    schema_path=Path("src/db_schema/schema.sql"),
    preserve_data=True,
    dry_run=False
)
```

### Pipeline Integration
```bash
# Run with Alembic (automatic)
python -m src.pipeline_orchestration.run_pipeline --stages schema

# Force dry run to see what would happen
python -m src.pipeline_orchestration.run_pipeline --stages schema --dry-run

# Force fallback to custom system (if needed)
DISABLE_ALEMBIC=1 python -m src.pipeline_orchestration.run_pipeline --stages schema
```

### Manual Migration Operations
```python
# Apply pending migrations
result = schema_manager.apply_migrations(dry_run=False)

# Rollback to previous version
result = schema_manager.rollback_migration("-1")

# Get migration history
history = schema_manager.get_migration_history()

# Generate migration from schema file
revision_id = schema_manager.generate_migration_from_schema_file(
    schema_path=Path("src/db_schema/schema.sql"),
    message="Update schema from file"
)
```

## Troubleshooting

### Common Issues

#### 1. Alembic Import Error
**Symptom**: `ImportError: No module named 'alembic'`
**Solution**: System automatically falls back to custom schema manager

#### 2. Migration Conflicts
**Symptom**: Multiple migration heads
**Solution**: 
```bash
# Check migration status
alembic -c src/db_schema/alembic/alembic.ini current

# Merge heads if needed
alembic -c src/db_schema/alembic/alembic.ini merge heads -m "merge conflicts"
```

#### 3. Schema Drift
**Symptom**: Database doesn't match schema.sql
**Solution**: System will generate migration to bring database in line with schema.sql

### Debugging

#### Enable SQL Logging
```python
# In alembic_schema_manager.py, change:
engine = create_engine(
    connection_string,
    echo=True  # Enable SQL logging
)
```

#### Check Migration Status
```python
history = schema_manager.get_migration_history()
for migration in history:
    print(f"Revision: {migration['revision']}")
    print(f"Message: {migration['message']}")
    print(f"Current: {migration['is_current']}")
```

## Safety Features

### Data Preservation
- Alembic migrations preserve data by default
- No DROP TABLE operations without explicit confirmation
- Rollback capabilities for safe recovery

### Validation
- All existing schema validation tests continue to run
- Field mapping validation ensures API compatibility
- Dry-run mode for safe testing

### Fallback Mechanism
- Automatic fallback to custom system if Alembic unavailable
- Graceful error handling
- No breaking changes to existing workflows

## Performance Considerations

### Improvements
- **Faster migrations**: Alembic's optimized migration engine
- **Better dependency resolution**: No manual ordering required
- **Reduced parsing overhead**: Less regex-based SQL parsing

### Monitoring
- Migration execution time tracking
- Detailed logging of all operations
- Performance metrics collection

## Testing Strategy

### Automated Tests
- Unit tests for Alembic integration
- Integration tests with existing validation
- Backward compatibility tests
- Fallback mechanism tests

### Manual Testing
1. **Fresh installation**: Test on clean database
2. **Migration scenarios**: Test various schema changes
3. **Rollback testing**: Verify rollback capabilities
4. **Performance testing**: Compare migration speeds

## Rollback Plan

If issues arise, the system can be rolled back:

1. **Immediate**: Set `DISABLE_ALEMBIC=1` environment variable
2. **Temporary**: Use `--force-recreate-schema` flag for emergency reset
3. **Permanent**: Remove Alembic integration (keep custom system)

## Benefits Realized

### For Developers
- **Reduced complexity**: Less custom code to maintain
- **Better tooling**: Standard Alembic commands available
- **Improved reliability**: Battle-tested migration system

### For Operations
- **Safer migrations**: Built-in safeguards and best practices
- **Better monitoring**: Standard migration tracking
- **Easier troubleshooting**: Well-documented Alembic ecosystem

### For the Project
- **Industry standards**: Following established patterns
- **Reduced maintenance**: Less custom code to maintain
- **Better scalability**: Proven system for large schemas

## Next Steps

1. **Monitor**: Watch for any issues during transition
2. **Optimize**: Fine-tune Alembic configuration as needed
3. **Document**: Update operational procedures
4. **Train**: Ensure team familiarity with Alembic commands

## Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Migration Best Practices](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Our Schema Validation Tests](../tests/test_schema_validation.py) 