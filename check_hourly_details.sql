-- Check hourly metrics ingestion progress
SELECT 
    'Total hourly records' as metric,
    COUNT(*) as count
FROM prop_trading_model.raw_metrics_hourly
UNION ALL
SELECT 
    'Records added since start (197652)' as metric,
    COUNT(*) - 197652 as count
FROM prop_trading_model.raw_metrics_hourly
UNION ALL
-- Check recent ingestion activity
SELECT 
    'Records added in last 5 minutes' as metric,
    COUNT(*) as count
FROM prop_trading_model.raw_metrics_hourly
WHERE ingestion_timestamp > NOW() - INTERVAL '5 minutes'
UNION ALL
SELECT 
    'Records added in last 30 minutes' as metric,
    COUNT(*) as count
FROM prop_trading_model.raw_metrics_hourly
WHERE ingestion_timestamp > NOW() - INTERVAL '30 minutes';

-- Show sample of recent records
SELECT 
    account_id, 
    date, 
    hour,
    ingestion_timestamp
FROM prop_trading_model.raw_metrics_hourly
WHERE ingestion_timestamp > NOW() - INTERVAL '5 minutes'
ORDER BY ingestion_timestamp DESC
LIMIT 10;
