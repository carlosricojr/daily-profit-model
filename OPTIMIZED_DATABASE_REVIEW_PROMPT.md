# Optimized Database Review Prompt

## Executive Summary
Generate specialized analysis agents to perform a comprehensive database review and provide actionable recommendations for our PostgreSQL trading database implementation.

## Agent Tasks

### Agent 1: Partition Implementation Review
**Mission**: Compare our partition migration implementation against Supabase best practices

**Resources to analyze**:
- https://supabase.com/blog/postgres-dynamic-table-partitioning
- https://github.com/supabase/supabase/tree/master/examples/enterprise-patterns/supachat
- src/utils/partition_migration_manager.py
- tests/test_partition_migration.py

**Deliverables**:
1. Gap analysis vs Supabase approach
2. Missing features identification
3. Risk assessment of current implementation
4. Prioritized enhancement recommendations

### Agent 2: Database Test Suite Analysis
**Mission**: Execute and analyze all database-related tests

**Test suites to run**:
```bash
pytest tests/test_database* -v
pytest tests/test_schema* -v
pytest tests/test_partition* -v
pytest tests/test_alembic* -v
pytest tests/test_data_structure* -v
```

**Deliverables**:
1. Test coverage report
2. Failure pattern analysis
3. Missing test identification
4. Architectural concerns from test results

### Agent 3: Partition Migration Dry Run
**Mission**: Execute and analyze partition migration dry run

**Command to execute**:
```bash
uv run --env-file .env python -c "
from utils.database import get_db_manager
from utils.partition_migration_manager import PartitionMigrationManager

pm = PartitionMigrationManager(get_db_manager())
for table in ['raw_metrics_hourly', 'raw_metrics_daily', 'raw_trades_closed']:
    analysis = pm.analyze_table_for_partitioning(table)
    if analysis['needs_partitioning']:
        result = pm.convert_to_partitioned_table(
            table, 
            analysis['partition_column'],
            analysis['recommended_strategy'],
            dry_run=True
        )
        print(f'{table}: {result}')
"
```

**Deliverables**:
1. Current partition state analysis
2. Migration plan validation
3. Performance impact assessment
4. Risk identification

### Agent 4: Schema Accuracy Validation
**Mission**: Ensure 100% accuracy between SQLAlchemy models and SQL schema

**Files to compare**:
- src/db_schema/models.py (SQLAlchemy)
- src/db_schema/schema.sql (PostgreSQL)
- ai-docs/api-docs/data-structures.md (API specs)

**Deliverables**:
1. Field-by-field comparison matrix
2. Data type mismatch report
3. Missing constraint identification
4. API compatibility assessment

### Agent 5: Implementation Simplification Analysis
**Mission**: Identify opportunities to reduce complexity without losing functionality

**Components to review**:
- src/utils/database.py
- src/utils/schema_manager.py
- src/utils/enhanced_alembic_schema_manager.py
- src/utils/partition_migration_manager.py
- src/db_schema/alembic/

**Deliverables**:
1. Redundancy elimination plan
2. Code consolidation opportunities
3. Simplified architecture proposal
4. Migration path to cleaner implementation

## Final Synthesis Requirements

After all agents complete their analysis, synthesize findings into:

1. **Current State Assessment**
   - Database health score (1-10)
   - Critical issues requiring immediate attention
   - Technical debt quantification

2. **Optimization Roadmap**
   - Quick wins (< 1 day effort)
   - Medium improvements (1-5 days)
   - Long-term enhancements (> 5 days)

3. **Risk Mitigation Plan**
   - Data integrity safeguards
   - Performance optimization priorities
   - Backup and recovery strategies

4. **Implementation Priorities**
   - P0: Critical fixes (data loss prevention)
   - P1: Performance improvements
   - P2: Developer experience enhancements
   - P3: Nice-to-have optimizations

## Success Criteria

The review is successful when we have:
- ✅ Complete understanding of current database state
- ✅ Clear migration path to partitioned tables
- ✅ Simplified schema management approach
- ✅ 100% model-schema alignment
- ✅ Actionable 30-60-90 day improvement plan

## Constraints

- Maintain zero downtime during any migrations
- Preserve all existing data
- Ensure backward compatibility
- Minimize operational complexity
- Optimize for developer productivity