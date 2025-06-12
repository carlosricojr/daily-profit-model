-- Check hourly metrics ingestion progress
SELECT 
    'Current hourly records' as metric,
    COUNT(*) as count,
    MIN(date) as earliest_date,
    MAX(date) as latest_date,
    COUNT(DISTINCT account_id) as unique_accounts
FROM prop_trading_model.raw_metrics_hourly

UNION ALL

-- Check recent hourly records (last hour)
SELECT 
    'Hourly records added in last hour' as metric,
    COUNT(*) as count,
    MIN(date) as earliest_date,
    MAX(date) as latest_date,
    COUNT(DISTINCT account_id) as unique_accounts
FROM prop_trading_model.raw_metrics_hourly
WHERE ingestion_timestamp > NOW() - INTERVAL '1 hour'

UNION ALL

-- Check most recent ingestion timestamp
SELECT 
    'Most recent ingestion' as metric,
    NULL as count,
    NULL as earliest_date,
    MAX(ingestion_timestamp)::date as latest_date,
    NULL as unique_accounts
FROM prop_trading_model.raw_metrics_hourly
WHERE ingestion_timestamp > NOW() - INTERVAL '1 day';
