-- Check all metrics tables for recent activity
SELECT 
    'Daily metrics - total' as table_name,
    COUNT(*) as total_count,
    COUNT(CASE WHEN ingestion_timestamp > NOW() - INTERVAL '30 minutes' THEN 1 END) as recent_count
FROM prop_trading_model.raw_metrics_daily
UNION ALL
SELECT 
    'Hourly metrics - total' as table_name,
    COUNT(*) as total_count,
    COUNT(CASE WHEN ingestion_timestamp > NOW() - INTERVAL '30 minutes' THEN 1 END) as recent_count
FROM prop_trading_model.raw_metrics_hourly
UNION ALL
SELECT 
    'Alltime metrics - total' as table_name,
    COUNT(*) as total_count,
    COUNT(CASE WHEN ingestion_timestamp > NOW() - INTERVAL '30 minutes' THEN 1 END) as recent_count
FROM prop_trading_model.raw_metrics_alltime;

-- Check date range of daily metrics
SELECT 
    'Daily metrics date range' as info,
    MIN(date) as min_date,
    MAX(date) as max_date,
    COUNT(DISTINCT date) as unique_dates
FROM prop_trading_model.raw_metrics_daily
WHERE date >= '2024-04-15'::date;
