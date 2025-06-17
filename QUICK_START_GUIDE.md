# Daily Profit Model - Quick Start Guide

This guide helps you test the entire ML pipeline with one week of data to ensure everything works before processing larger datasets. The  pipeline only fetches missing data, making it much faster than traditional approaches.

## Prerequisites

- Python 3.13+ with `uv` package manager
- PostgreSQL database (local or cloud)
- API credentials for risk analytics data
- Configured `.env` file (see below)

## 1. Environment Setup

Create a `.env` file in the project root:

```bash
# API Configuration
RISK_API_KEY=your_api_key_here
RISK_API_BASE_URL=https://easton.apis.arizet.io/risk-analytics/tft/external/

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=daily_profit_model
DB_USER=your_db_user
DB_PASSWORD=your_db_password

# Note: Schema name 'prop_trading_model' is hardcoded in schema.sql

# Logging
LOG_LEVEL=INFO
LOG_DIR=logs
```

## 2. Database Setup

### Option A: Fresh Database
```bash
# Create database
createdb daily_profit_model

# Apply schema
psql -d daily_profit_model -f src/db_schema/schema.sql

# Verify tables (should show ~17 tables including partitions)
psql -d daily_profit_model -c "\dt prop_trading_model.*"
```

### Option B: Using  Pipeline Orchestrator
```bash
# Let the  pipeline create schema
uv run --env-file .env -- python -m src.pipeline_orchestration.run_pipeline_ --stages schema
```

### Expected Tables
- `raw_metrics_daily` - Daily performance metrics (partitioned)
- `raw_trades_closed` - Historical trades (partitioned)
- `raw_plans_data` - Trading plan definitions
- `raw_regimes_daily` - Market regime indicators
- `feature_store_account_daily` - ML features
- `model_training_input` - Training dataset
- `model_predictions` - Predictions output
- `model_registry` - Model metadata
- `pipeline_execution_log` - Execution tracking

## 3. Date Setup for Testing

```bash
# Calculate dates (last 7 days)
# Linux
START_DATE=$(date -d "7 days ago" +%Y-%m-%d)
END_DATE=$(date -d "yesterday" +%Y-%m-%d)

# macOS  
START_DATE=$(date -v-7d +%Y-%m-%d)
END_DATE=$(date -v-1d +%Y-%m-%d)

echo "Testing from $START_DATE to $END_DATE"
```

## 4. Quick Test ( Pipeline)

Run this for the fastest validation with  data fetching:

```bash
# 1.  metrics ingestion (only fetches missing data)
# This automatically discovers missing daily dates, extracts account IDs, 
# updates alltime for those accounts, and fills missing hourly data with
# precise hour-level detection (only fetches specific missing hours)
uv run --env-file .env -- python -m src.data_ingestion.ingest_metrics \
    --start-date $START_DATE --end-date $END_DATE

# 2.  trades ingestion (only fetches missing data)
uv run --env-file .env -- python -m src.data_ingestion.ingest_trades_ closed \
    --start-date $START_DATE --end-date $END_DATE

# 3. Create staging snapshots
uv run --env-file .env -- python -m src.preprocessing.create_staging_snapshots \
    --start-date $START_DATE --end-date $END_DATE

# 4. Engineer features (use optimized for speed)
uv run --env-file .env -- python -m src.feature_engineering.engineer_features \
    --start-date $START_DATE --end-date $END_DATE --use-optimized

# 5. Build training data
uv run --env-file .env -- python -m src.feature_engineering.build_training_data

# 6. Train model
uv run --env-file .env -- python -m src.modeling.train_model

# 7. Generate predictions
uv run --env-file .env -- python -m src.modeling.predict_daily
```

### Alternative: Legacy Individual Component Approach (Less Efficient)
```bash
# Note: The  pipeline combines these steps automatically
# Only use if you need granular control over individual components

# Legacy account discovery
ACTIVE_LOGINS=$(uv run --env-file .env -- python -m src.data_ingestion.discover_active_logins \
    --start-date $START_DATE --end-date $END_DATE --output-format comma)
```

## 5. Full Pipeline Test

For comprehensive testing including all data sources:

```bash
# Run complete  pipeline
uv run --env-file .env -- python -m src.pipeline_orchestration.run_pipeline_ \
    --start-date $START_DATE \
    --end-date $END_DATE \
    --log-level INFO
```

Or run specific stages:

```bash
# Just  ingestion and preprocessing
uv run --env-file .env -- python -m src.pipeline_orchestration.run_pipeline_ \
    --stages ingestion preprocessing \
    --start-date $START_DATE \
    --end-date $END_DATE
```

## 6. Validation Queries

### Check Data Ingestion
```sql
-- Connect to database
psql -d daily_profit_model

-- Set schema
SET search_path TO prop_trading_model;

-- Check record counts
SELECT 
    'accounts' as table_name, COUNT(*) as records,
    MIN(created_at::date) as oldest, MAX(created_at::date) as newest
FROM raw_accounts_data
UNION ALL
SELECT 
    'daily_metrics', COUNT(*),
    MIN(date), MAX(date)
FROM raw_metrics_daily
WHERE date >= CURRENT_DATE - INTERVAL '7 days';
```

### Check Feature Generation
```sql
-- Feature records by date
SELECT 
    feature_date,
    COUNT(DISTINCT account_id) as accounts,
    COUNT(*) as total_features
FROM feature_store_account_daily
WHERE feature_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY feature_date
ORDER BY feature_date DESC;
```

### Check Model & Predictions
```sql
-- Latest model
SELECT model_version, model_type, train_mae, val_mae, created_at
FROM model_registry
ORDER BY created_at DESC
LIMIT 1;

-- Recent predictions
SELECT prediction_date, COUNT(*) as predictions,
       AVG(predicted_net_profit) as avg_prediction
FROM model_predictions
WHERE model_version = (SELECT model_version FROM model_registry ORDER BY created_at DESC LIMIT 1)
GROUP BY prediction_date
ORDER BY prediction_date DESC;
```

## 7. Monitor Progress

### Pipeline Execution Log
```sql
SELECT 
    pipeline_stage,
    execution_date,
    status,
    records_processed,
    EXTRACT(EPOCH FROM (end_time - start_time)) as duration_seconds
FROM pipeline_execution_log
WHERE created_at >= NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

### Application Logs
```bash
# Watch logs in real-time
tail -f logs/daily_profit_model.log | grep -E "(ERROR|WARNING|completed)"

# Check for errors
grep ERROR logs/*.log | tail -20
```

## 8. Automated Test Script

Save as `test_pipeline.sh`:

```bash
#!/bin/bash
set -e  # Exit on error

# Detect OS and set date commands
if [[ "$OSTYPE" == "darwin"* ]]; then
    START_DATE=$(date -v-7d +%Y-%m-%d)
    END_DATE=$(date -v-1d +%Y-%m-%d)
else
    START_DATE=$(date -d "7 days ago" +%Y-%m-%d)
    END_DATE=$(date -d "yesterday" +%Y-%m-%d)
fi

echo "=== Daily Profit Model Pipeline Test ==="
echo "Date range: $START_DATE to $END_DATE"
echo ""

# Function to check status
check_status() {
    if [ $? -eq 0 ]; then
        echo "✅ $1 completed successfully"
    else
        echo "❌ $1 failed"
        exit 1
    fi
}

# Run  pipeline stages
echo "1.  metrics ingestion (only missing data)..."
uv run --env-file .env -- python -m src.data_ingestion.ingest_metrics \
    --start-date $START_DATE --end-date $END_DATE
check_status " metrics ingestion"

echo -e "\n2.  trades ingestion (only missing data)..."
uv run --env-file .env -- python -m src.data_ingestion.ingest_trades_ closed \
    --start-date $START_DATE --end-date $END_DATE
check_status " trades ingestion"

echo -e "\n3. Creating staging snapshots..."
uv run --env-file .env -- python -m src.preprocessing.create_staging_snapshots \
    --start-date $START_DATE --end-date $END_DATE
check_status "Staging snapshots"

echo -e "\n4. Engineering features..."
uv run --env-file .env -- python -m src.feature_engineering.engineer_features \
    --start-date $START_DATE --end-date $END_DATE --use-optimized
check_status "Feature engineering"

echo -e "\n5. Building training data..."
uv run --env-file .env -- python -m src.feature_engineering.build_training_data
check_status "Training data preparation"

echo -e "\n6. Training model..."
uv run --env-file .env -- python -m src.modeling.train_model
check_status "Model training"

echo -e "\n7. Generating predictions..."
uv run --env-file .env -- python -m src.modeling.predict_daily
check_status "Prediction generation"

echo -e "\n✅  pipeline test completed successfully!"
echo "Check logs in: logs/daily_profit_model.log"
```

Make executable: `chmod +x test_pipeline.sh`

## 9. Troubleshooting

### Database Connection Issues
```bash
# Test connection
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"

# Check .env variables
uv run --env-file .env -- python -c "
import os
print(f'DB_HOST: {os.getenv(\"DB_HOST\")}')
print(f'DB_NAME: {os.getenv(\"DB_NAME\")}')
"
```

### API Rate Limiting
- The enhanced API client handles this automatically
- Check logs for "Circuit breaker" or "Rate limit" messages
- Add `--resume-from-checkpoint` to resume failed ingestions

### Memory Issues (Unlikely with 1 week)
```bash
# Use smaller batches
uv run --env-file .env -- python -m src.data_ingestion.ingest_trades closed \
    --start-date $START_DATE --end-date $END_DATE \
    --batch-days 1
```

### No Data Returned
```sql
-- Check if accounts exist
SELECT COUNT(*) FROM prop_trading_model.raw_accounts_data;

-- Check API response in logs
grep "API response" logs/*.log | tail -10
```

### Feature Engineering Slow
```bash
# Always use optimized version for testing
uv run --env-file .env -- python -m src.feature_engineering.engineer_features \
    --use-optimized  # This flag enables N+1 query fix
```

## 10. Performance Expectations

### With  Data Ingestion (Recommended)
Using  missing data detection for 1 week of data:
- ** Metrics Ingestion**: 30-60 seconds (only fetches missing daily/hourly data with precise hour-level detection)
- ** Trades Ingestion**: 1-2 minutes (only fetches missing trades)
- **Preprocessing**: < 1 minute
- **Feature Engineering**: 1-3 minutes (optimized)
- **Model Training**: < 1 minute
- **Total  Pipeline**: 3-7 minutes

### Hourly Metrics Optimization
The new precise hourly detection brings significant improvements:
- **Precision**: Identifies exactly which (account_id, date, hour) tuples are missing
- **Efficiency**: 95%+ reduction in unnecessary hourly data fetching
- **Batching**: Optimized API batches group missing records by date with up to 25 accounts per batch
- **Example**: For 100 accounts with 1 missing hour each, fetches only 100 hours instead of 2,400 hours (24 hours × 100 accounts)

### Without Intelligence (Legacy Full Fetch)
- **Full Metrics Ingestion**: 10-20 minutes (fetches all data regardless of existence)
- **Full Trades Ingestion**: 15-30 minutes (fetches all trades)
- **Other stages**: Same as above
- **Total Legacy Pipeline**: 25-50 minutes

### Intelligence Efficiency Gains
- **Metrics ingestion**: 10-20x faster (only missing data vs. all records)
- **Hourly metrics**: 95%+ reduction through precise (account_id, date, hour) detection
- **Trades ingestion**: 10-15x faster (gap detection vs. full fetch)
- **API calls**: Reduced from thousands to dozens of requests
- **Data transfer**: Only fetch data that doesn't already exist
- **Database operations**:  upserts prevent duplicate processing
- **Recovery friendly**: Automatically resumes from crash points

## 11. Next Steps

After successful test:

1. **Expand Date Range**: Try 30 days, then 90 days
2. **Add More Data Sources**: Include trades, hourly metrics
3. **Enable Hyperparameter Tuning**: Add `--tune-hyperparameters`
4. **Set Up Monitoring**: 
   ```bash
   uv run --env-file .env -- python -m src.modeling.model_monitoring
   ```
5. **Schedule Daily Runs**: Use cron or Airflow DAG

## 12. Useful Commands

```bash
# Check system health
uv run --env-file .env -- python -m src.pipeline_orchestration.health_checks

#  metrics ingestion (only fetches missing data)
uv run --env-file .env -- python -m src.data_ingestion.ingest_metrics \
    --start-date 2024-01-01 --end-date 2024-01-07

#  trades ingestion (only fetches missing data)
uv run --env-file .env -- python -m src.data_ingestion.ingest_trades_ closed \
    --start-date 2024-01-01 --end-date 2024-01-07
uv run --env-file .env -- python -m src.data_ingestion.ingest_trades_ open

# Full  pipeline
uv run --env-file .env -- python -m src.pipeline_orchestration.run_pipeline_ \
    --start-date 2024-01-01 --end-date 2024-01-07

# Validate data quality
uv run --env-file .env -- python -m src.preprocessing.data_validator \
    --table stg_accounts_daily_snapshots

# Benchmark performance
uv run --env-file .env -- python -m src.feature_engineering.benchmark_performance

# Monitor features
uv run --env-file .env -- python -m src.feature_engineering.monitor_features
```

## Success Criteria

Your  pipeline test is successful when:
- ✅ All stages complete without errors
- ✅ `pipeline_execution_log` shows 'success' status
- ✅ Only missing data was fetched (check logs for "Found X missing..." messages)
- ✅ Features exist for all discovered accounts
- ✅ Model trains and saves metadata
- ✅ Predictions generated for next day
- ✅ No ERROR logs in last run
- ✅ Subsequent runs are much faster (no missing data to fetch)

## Support

1. Check logs: `logs/daily_profit_model.log`
2. Review pipeline status: `SELECT * FROM pipeline_execution_log ORDER BY created_at DESC LIMIT 10;`
3. Consult `CONSOLIDATED_SYSTEM_GUIDE.md` for architecture details
4. Use `--log-level DEBUG` for detailed troubleshooting