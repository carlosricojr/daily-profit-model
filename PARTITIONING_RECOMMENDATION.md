# Database Partitioning Recommendation for raw_metrics_hourly

## Executive Summary

**YES, the `raw_metrics_hourly` table should be partitioned.** Based on current data volumes and growth projections, partitioning will provide significant benefits for query performance, maintenance operations, and long-term scalability.

## Current State Analysis

### Data Volume
- **Current records**: 724,866 (covering ~7 months)
- **Current size**: 689 MB
- **Daily growth**: ~240,000 records/day (~343 MB/day) when fully active
- **Projected 3-year size**: 262.8M records (~367 GB)

### Table Structure
- **Primary Key**: `(account_id, date, hour)`
- **Current indexes**: 5 indexes including the PK
- **Not currently partitioned** (unlike `raw_metrics_daily` which IS partitioned)

## Recommendation: Implement Monthly Range Partitioning

### Benefits of Partitioning

1. **Query Performance**
   - Partition pruning for date-based queries
   - Faster aggregations when querying specific time periods
   - Improved index performance on smaller partitions

2. **Maintenance Operations**
   - Faster VACUUM and ANALYZE on individual partitions
   - Ability to drop old data by dropping partitions (instant vs DELETE)
   - Parallel maintenance operations on different partitions

3. **Data Management**
   - Easy archival of old data
   - Partition-wise backups
   - Better cache utilization

4. **Scalability**
   - Linear growth handling
   - Prevents single large table performance degradation
   - Easier to implement data retention policies

### Proposed Implementation

```sql
-- 1. Create new partitioned table
CREATE TABLE raw_metrics_hourly_new (
    -- Same schema as current table
    LIKE raw_metrics_hourly INCLUDING ALL
) PARTITION BY RANGE (date);

-- 2. Create partitions (example for recent months)
CREATE TABLE raw_metrics_hourly_y2024m11 PARTITION OF raw_metrics_hourly_new
    FOR VALUES FROM ('2024-11-01') TO ('2024-12-01');
    
CREATE TABLE raw_metrics_hourly_y2024m12 PARTITION OF raw_metrics_hourly_new
    FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');
-- ... continue for all needed months

-- 3. Migrate data
INSERT INTO raw_metrics_hourly_new 
SELECT * FROM raw_metrics_hourly;

-- 4. Swap tables
ALTER TABLE raw_metrics_hourly RENAME TO raw_metrics_hourly_old;
ALTER TABLE raw_metrics_hourly_new RENAME TO raw_metrics_hourly;

-- 5. Recreate indexes on partitioned table
-- (Most will be automatically created on partitions)
```

### Partition Strategy

1. **Partition by month** (same as `raw_metrics_daily`)
   - Aligns with business reporting cycles
   - Manageable partition sizes (~10-15 GB per partition at scale)
   - Good balance between partition count and size

2. **Automatic partition creation**
   - Use the existing `create_monthly_partitions()` function
   - Schedule monthly job to create future partitions

3. **Retention policy**
   - Keep 3 years of detailed hourly data
   - Archive or aggregate older data

## Implementation Considerations

### Pros
- Matches existing pattern (daily table is already partitioned)
- Minimal application code changes required
- PostgreSQL handles partition routing automatically
- Significant performance improvements for time-based queries

### Cons
- Migration requires brief downtime or careful orchestration
- Slightly more complex backup/restore procedures
- Cross-partition queries have small overhead

### Migration Path

1. **Test in development** first
2. **Create partitioned table** alongside existing
3. **Dual-write period** (write to both tables)
4. **Migrate historical data** in batches
5. **Switch reads** to new table
6. **Drop old table** after validation

## Query Pattern Optimization

Common query patterns will benefit from partitioning:

```sql
-- ✅ Single partition scan
SELECT * FROM raw_metrics_hourly 
WHERE date >= '2025-06-01' AND date < '2025-07-01'
AND account_id = '12345';

-- ✅ Multiple partition parallel scan
SELECT date, AVG(net_profit) 
FROM raw_metrics_hourly
WHERE date >= '2025-01-01'
GROUP BY date;

-- ⚠️ Full table scan (use sparingly)
SELECT * FROM raw_metrics_hourly
WHERE net_profit > 1000;
```

## Monitoring and Maintenance

Post-partitioning tasks:
1. Monitor partition sizes monthly
2. Ensure partition creation job is running
3. Update table statistics regularly
4. Consider partition-wise indexes for heavy queries

## Conclusion

Partitioning `raw_metrics_hourly` is strongly recommended given:
- Current size (689 MB) growing rapidly
- Expected scale (367 GB over 3 years)
- Existing successful pattern with `raw_metrics_daily`
- Clear date-based access patterns

The benefits far outweigh the implementation complexity, and the sooner it's implemented, the easier the migration will be.