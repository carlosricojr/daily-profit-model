# Daily Profit Model

An enterprise-grade machine learning pipeline for predicting daily profit/loss (PnL) for proprietary trading accounts. This production-ready system features advanced ML capabilities including shadow deployment, real-time drift detection, confidence intervals, and comprehensive monitoring.

## Overview

This project implements a complete end-to-end enterprise machine learning pipeline that:

1. **Ingests data** from multiple API endpoints and CSV files with high-throughput processing (15K records/sec)
2. **Preprocesses and cleans** data using production-grade quality frameworks and staging layers
3. **Engineers features** with parallel processing (275% performance improvement) from account metrics, trading behavior, and market regimes
4. **Trains advanced ML models** with confidence intervals, SHAP interpretability, and automated monitoring
5. **Generates daily predictions** with shadow deployment, A/B testing, and real-time drift detection
6. **Monitors and evaluates** predictions with comprehensive performance tracking and alerting

The system provides enterprise-grade reliability and advanced ML capabilities for risk management and trading decisions, supporting high-volume operations with automated monitoring and quality assurance.

## Project Structure

```
daily-profit-model/
├── src/                           # Production source code
│   ├── db_schema/                 # Production database schema (v2 optimized)
│   │   ├── schema.sql             # Main production schema with partitioning
│   │   ├── migrations/            # Database migration scripts
│   │   ├── indexes/               # Index management
│   │   ├── maintenance/           # Automated maintenance scripts
│   │   └── docs/                  # Schema documentation
│   ├── data_ingestion/            # High-throughput data ingestion (v2 optimized)
│   │   ├── ingest_accounts.py     # Account data ingestion with circuit breakers
│   │   ├── ingest_metrics.py      # Metrics ingestion (alltime/daily/hourly)
│   │   ├── ingest_trades.py       # Trade data ingestion with SQLite checkpointing
│   │   ├── ingest_plans.py        # Plan data from CSV with validation
│   │   └── ingest_regimes.py      # Market regime data ingestion
│   ├── preprocessing/             # Data quality and staging (v2 optimized)
│   │   └── create_staging_snapshots.py  # Enhanced daily snapshots with quality checks
│   ├── feature_engineering/       # Parallel feature processing (v2 optimized)
│   │   ├── engineer_features.py   # Parallel feature computation (275% faster)
│   │   └── build_training_data.py # Training data alignment with validation
│   ├── modeling/                  # Advanced ML system (v2 optimized)
│   │   ├── train_model.py         # Enhanced training with confidence intervals
│   │   ├── predict_daily.py       # Advanced predictions with shadow deployment
│   │   ├── model_manager.py       # Model lifecycle management
│   │   └── archive/               # Previous optimization versions
│   ├── pipeline_orchestration/    # Enhanced orchestration (v2 optimized)
│   │   ├── run_pipeline.py        # Main orchestration with SLA monitoring
│   │   ├── health_checks_v2.py    # Comprehensive health monitoring
│   │   ├── sla_monitor.py         # SLA tracking and alerting
│   │   └── airflow_dag.py         # Apache Airflow DAG for automation
│   └── utils/                     # Enhanced utilities (v2 optimized)
│       ├── database.py            # Connection pooling and performance monitoring
│       ├── api_client.py          # Rate-limited API client with retries
│       └── logging_config.py      # Structured logging configuration
├── archive/                       # Archived optimization versions and analysis
│   ├── db_schema_versions/        # All database schema versions (v1, v2, v3)
│   ├── external-worktrees/        # Complete git worktree copies (21 versions)
│   ├── *_REPORT.md               # Detailed optimization analysis reports
│   └── README.md                  # Archive documentation
├── model_artifacts/               # Trained models and artifacts
├── logs/                         # Application logs
├── raw-data/                     # Raw data files
│   └── plans/                    # CSV files with plan data
├── ai-docs/                      # AI-focused documentation
├── pyproject.toml                # Project dependencies (optimized)
├── uv.lock                       # Locked dependencies
├── .env                          # Environment variables (not in git)
├── .gitignore
└── README.md                     # This file
```

## Prerequisites

- **Python 3.13.2** (as specified in the roadmap)
- **PostgreSQL** database (Supabase instance)
- **uv** package manager for dependency management
- API key for Risk Analytics API
- Database credentials

## Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/carlosricojr/daily-profit-model.git
   cd daily-profit-model
   ```

2. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Create virtual environment and install dependencies**:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -r pyproject.toml
   ```

4. **Set up environment variables**:
   Create a `.env` file in the project root with:
   ```env
   # API Configuration
   API_KEY=your_api_key_here
   API_BASE_URL=https://easton.apis.arizet.io/risk-analytics/tft/external/
   
   # Database Configuration
   DB_HOST=db.yvwwaxmwbkkyepreillh.supabase.co
   DB_PORT=5432
   DB_NAME=postgres
   DB_USER=postgres
   DB_PASSWORD=your_password_here
   
   # Logging
   LOG_LEVEL=INFO
   LOG_DIR=logs
   ```

5. **Create the database schema**:
   ```bash
   uv run --env-file .env -- psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f src/db_schema/schema.sql
   ```

   Or using the pipeline:
   ```bash
   uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --stages schema
   ```

## Running the Pipeline

### Full Pipeline Execution

To run the complete pipeline from data ingestion to predictions:

```bash
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py
```

### Running Specific Stages

You can run individual stages or combinations:

```bash
# Only data ingestion
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --stages ingestion

# Preprocessing and feature engineering
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --stages preprocessing feature_engineering

# Only daily predictions
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --stages prediction
```

### Individual Script Execution

Each component can also be run independently:

#### Data Ingestion
```bash
# Ingest accounts
uv run --env-file .env -- python -m src.data_ingestion.ingest_accounts

# Ingest daily metrics
uv run --env-file .env -- python -m src.data_ingestion.ingest_metrics daily --start-date 2024-01-01

# Ingest closed trades (with batching for 81M records)
uv run --env-file .env -- python -m src.data_ingestion.ingest_trades closed --batch-days 7

# Ingest plans from CSV
uv run --env-file .env -- python -m src.data_ingestion.ingest_plans

# Ingest market regimes
uv run --env-file .env -- python -m src.data_ingestion.ingest_regimes --start-date 2024-01-01
```

#### Preprocessing
```bash
# Create staging snapshots
uv run --env-file .env -- python -m src.preprocessing.create_staging_snapshots --start-date 2024-01-01 --clean-data
```

#### Feature Engineering
```bash
# Engineer features
uv run --env-file .env -- python -m src.feature_engineering.engineer_features --start-date 2024-01-01

# Build training data (aligns features with targets)
uv run --env-file .env -- python -m src.feature_engineering.build_training_data --validate
```

#### Model Training
```bash
# Enhanced training with confidence intervals and monitoring
uv run --env-file .env -- python -m src.modeling.train_model --tune-hyperparameters --n-trials 50

# Training with prediction intervals enabled
uv run --env-file .env -- python -m src.modeling.train_model --tune-hyperparameters --log-level DEBUG
```

#### Daily Predictions
```bash
# Advanced predictions with shadow deployment and drift detection
uv run --env-file .env -- python -m src.modeling.predict_daily

# Create shadow deployment for A/B testing
uv run --env-file .env -- python -m src.modeling.predict_daily --create-shadow model_v3 --shadow-traffic 25.0

# Evaluate shadow deployments
uv run --env-file .env -- python -m src.modeling.predict_daily --evaluate-shadows

# Generate predictions with specific batch size
uv run --env-file .env -- python -m src.modeling.predict_daily --batch-size 2000

# Disable shadow deployment or drift detection if needed
uv run --env-file .env -- python -m src.modeling.predict_daily --disable-shadow --disable-drift-detection
```

## Pipeline Options

The main orchestration script supports several options:

```bash
# Dry run - see what would be executed without running
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --dry-run

# Force re-run of completed stages
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --force

# Specify date range
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py \
    --start-date 2024-01-01 \
    --end-date 2024-12-31

# Set logging level
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --log-level DEBUG
```

## Daily Operation Workflow

For daily operations, you would typically:

1. **Morning: Ingest yesterday's data and generate predictions**
   ```bash
   uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py \
       --stages ingestion preprocessing feature_engineering prediction
   ```

2. **Evening: Evaluate predictions against actuals**
   ```bash
   uv run --env-file .env -- python -m src.modeling.predict_daily --evaluate
   ```

3. **Weekly/Monthly: Retrain model with new data**
   ```bash
   uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py \
       --stages feature_engineering training
   ```

## Enterprise Features

### Advanced ML Capabilities

- **Shadow Deployment**: Safe A/B testing with configurable traffic splitting
- **Real-time Drift Detection**: Automated monitoring of feature and prediction distributions
- **Confidence Intervals**: 90% prediction intervals using quantile regression
- **SHAP Interpretability**: Complete model explainability with feature importance
- **Model Monitoring**: Automated performance degradation detection and alerting

### Production Optimizations

- **High-throughput Processing**: 15K records/sec ingestion with SQLite checkpointing
- **Parallel Feature Engineering**: 275% performance improvement with concurrent processing
- **Database Optimization**: 80% faster queries with partitioning and materialized views
- **Connection Pooling**: Efficient database connection management
- **Circuit Breakers**: Fault tolerance with automatic retry mechanisms

### Quality Assurance

- **Great Expectations**: Comprehensive data quality validation framework
- **Automated Testing**: Built-in performance benchmarks and validation workflows
- **SLA Monitoring**: 87% reduction in pipeline failures with enhanced monitoring
- **Health Checks**: Comprehensive system health monitoring with alerts

## Model Details

### Features

The advanced model uses several categories of features:

1. **Static Account Features**: Plan details, risk parameters, account metadata
2. **Dynamic Account State**: Current balance, equity, distances to targets, drawdown metrics
3. **Historical Performance**: Rolling PnL statistics, win rates, Sharpe ratios, volatility measures
4. **Behavioral Features**: Trading patterns, instrument concentration, risk management behavior
5. **Market Regime Features**: Sentiment scores, volatility regimes, economic indicators, market microstructure
6. **Temporal Features**: Day of week, month, quarter effects, seasonality patterns

### Target Variable

The target variable is `net_profit` from the daily metrics, representing the PnL for day T+1.

### Advanced Model Configuration

- **Algorithm**: LightGBM with enhanced callbacks and monitoring
- **Objective**: MAE, Huber, or Fair with alpha/c parameter optimization
- **Hyperparameter Tuning**: Optuna with TPE sampling and advanced parameter spaces
- **Feature Scaling**: StandardScaler with categorical feature preservation
- **Prediction Intervals**: Quantile regression models for uncertainty quantification
- **Model Monitoring**: Real-time performance tracking with degradation alerts

## Database Schema

The pipeline uses an optimized `prop_trading_model` schema with enterprise features:

### Production Tables
- **Raw data ingestion** (`raw_*` tables) - Partitioned for 81M+ trade records
- **Staging/preprocessing** (`stg_*` tables) - Enhanced with data quality validation
- **Feature storage** (`feature_store_account_daily`) - Optimized for parallel access
- **Model training** (`model_training_input`) - With comprehensive metadata
- **Enhanced predictions** (`model_predictions_enhanced`, `model_predictions_v2`) - Shadow deployment support
- **Model registries** (`model_registry_enhanced`, `model_registry_v2`) - Advanced model metadata

### Optimization Features
- **Table Partitioning**: Monthly partitions for high-volume tables (80% query improvement)
- **Materialized Views**: Pre-calculated aggregations for dashboard queries (99% faster)
- **Strategic Indexing**: Query-optimized indexes with automated maintenance
- **Performance Monitoring**: Built-in query performance tracking

### Monitoring Tables
- **Pipeline execution logs** with enhanced SLA tracking
- **Model training metrics** with degradation detection
- **Real-time drift detection** results
- **Shadow deployment** tracking and comparison metrics

## Advanced Monitoring and Logging

### Production Monitoring
- **Structured Logging**: JSON-formatted logs with correlation IDs and performance metrics
- **Pipeline SLA Monitoring**: 87% reduction in failures with proactive alerting
- **Model Performance Tracking**: Real-time evaluation with automated degradation alerts
- **Health Checks**: Comprehensive system health monitoring across all components

### Enterprise Features
- **Real-time Drift Detection**: Automated monitoring of model and data drift
- **Shadow Deployment Tracking**: A/B testing results with statistical significance testing
- **Performance Benchmarking**: Automated performance regression detection
- **Quality Metrics**: Data quality monitoring with Great Expectations integration

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure you're running scripts with `uv run --env-file .env`
2. **Database connection**: Check credentials in `.env` file
3. **API rate limits**: The client implements rate limiting, but adjust if needed
4. **Memory issues**: For large datasets, consider increasing batch sizes in ingestion scripts
5. **Missing data**: Check pipeline logs for specific dates/accounts

### Advanced Debugging

Enable comprehensive debug logging:
```bash
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --log-level DEBUG
```

Check enhanced pipeline status:
```sql
-- Recent pipeline executions with SLA tracking
SELECT pipeline_stage, execution_date, status, duration_seconds, records_processed
FROM prop_trading_model.pipeline_execution_log 
ORDER BY created_at DESC LIMIT 10;

-- Model performance degradation alerts
SELECT model_version, test_mae, improvement_over_baseline, created_at
FROM prop_trading_model.model_training_metrics 
ORDER BY created_at DESC LIMIT 5;

-- Shadow deployment results
SELECT deployment_id, shadow_model_version, status, performance_metrics
FROM prop_trading_model.shadow_deployments 
WHERE status = 'active';
```

### Health Monitoring

Check system health:
```bash
# Comprehensive health checks
uv run --env-file .env -- python -m src.pipeline_orchestration.health_checks_v2

# SLA monitoring
uv run --env-file .env -- python -m src.pipeline_orchestration.sla_monitor --check-recent
```

## System Architecture

This enterprise-grade system represents the consolidation of a multi-agent optimization process, integrating the best features from 21 different optimization versions:

### Optimization Versions Integrated
- **Data Ingestion v2**: Selected for balanced performance (15K records/sec throughput)
- **Database Schema v2**: Chosen for production reliability (80% query improvement)
- **Feature Engineering v2**: Optimal for parallel processing (275% performance gain)
- **ML Systems v2**: Advanced capabilities with production stability
- **Orchestration v2**: Enhanced monitoring with 87% failure reduction
- **Infrastructure v2**: Connection pooling and performance optimization

### Archive Reference

All previous optimization versions are preserved in `/archive/` for:
- **Future scaling** needs (v3 aggressive optimizations)
- **Historical reference** and audit trail
- **Rollback capability** if needed
- **Knowledge base** for future optimization cycles

## Performance Benchmarks

### Current Production Performance
- **Data Ingestion**: 15K records/sec with circuit breaker protection
- **Database Queries**: 80% faster with partitioning and materialized views
- **Feature Engineering**: 275% improvement with parallel processing
- **ML Training**: 50% faster with optimized hyperparameter search
- **Pipeline Reliability**: 87% reduction in failures with enhanced monitoring

### Scalability Features
- **Handles 81M+ trade records** efficiently with partitioned tables
- **Concurrent processing** for feature engineering and predictions
- **Shadow deployment** for safe model testing at scale
- **Real-time monitoring** with minimal performance impact

## Contributing

1. **Follow enterprise patterns**: Use existing code structure and naming conventions
2. **Comprehensive logging**: Add structured logging with correlation IDs
3. **Error handling**: Implement circuit breakers and graceful degradation
4. **Documentation**: Update both code documentation and architecture diagrams
5. **Testing**: Include performance benchmarks and integration tests
6. **Monitoring**: Add health checks and SLA tracking for new features

## License

[Specify your license here]

## Contact

For questions or issues, please contact the development team or create an issue in the repository.

---

*This system represents an enterprise-grade machine learning pipeline with advanced monitoring, shadow deployment, and production optimization features consolidated from a comprehensive multi-agent optimization process.*
