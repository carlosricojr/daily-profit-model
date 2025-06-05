# Daily Profit Model

A comprehensive machine learning pipeline for predicting daily profit/loss (PnL) for proprietary trading accounts. This model uses LightGBM to predict next-day PnL based on historical performance, behavioral patterns, and market regime features.

## Overview

This project implements a complete end-to-end machine learning pipeline that:

1. **Ingests data** from multiple API endpoints and CSV files
2. **Preprocesses and cleans** the data into a staging layer
3. **Engineers features** from account metrics, trading behavior, and market regimes
4. **Trains a LightGBM model** with time-series aware splitting and hyperparameter tuning
5. **Generates daily predictions** for all eligible funded accounts
6. **Evaluates predictions** against actual outcomes

The model is designed to support risk management decisions by identifying accounts likely to experience significant profits or losses.

## Project Structure

```
daily-profit-model/
├── src/
│   ├── db_schema/
│   │   └── schema.sql              # PostgreSQL database schema
│   ├── data_ingestion/
│   │   ├── ingest_accounts.py      # Ingest account data from API
│   │   ├── ingest_metrics.py       # Ingest metrics (alltime/daily/hourly)
│   │   ├── ingest_trades.py        # Ingest trades (open/closed)
│   │   ├── ingest_plans.py         # Ingest plan data from CSV
│   │   └── ingest_regimes.py       # Ingest market regime data
│   ├── preprocessing/
│   │   └── create_staging_snapshots.py  # Create daily account snapshots
│   ├── feature_engineering/
│   │   ├── engineer_features.py    # Calculate all features
│   │   └── build_training_data.py  # Align features with targets
│   ├── modeling/
│   │   ├── train_model.py          # Train LightGBM model
│   │   └── predict_daily.py        # Generate daily predictions
│   ├── pipeline_orchestration/
│   │   └── run_pipeline.py         # Main orchestration script
│   └── utils/
│       ├── database.py             # Database connection utilities
│       ├── api_client.py           # API client with pagination
│       └── logging_config.py       # Logging configuration
├── model_artifacts/                # Trained models and artifacts
├── logs/                          # Application logs
├── raw-data/
│   └── plans/                     # CSV files with plan data
├── ai-docs/                       # AI-focused documentation
├── pyproject.toml                 # Project dependencies
├── uv.lock                        # Locked dependencies
├── .env                           # Environment variables (not in git)
├── .gitignore
└── README.md                      # This file
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
# Train model with hyperparameter tuning
uv run --env-file .env -- python -m src.modeling.train_model --tune-hyperparameters --n-trials 50
```

#### Daily Predictions
```bash
# Generate predictions for today
uv run --env-file .env -- python -m src.modeling.predict_daily

# Generate predictions for specific date
uv run --env-file .env -- python -m src.modeling.predict_daily --prediction-date 2024-12-01

# Evaluate yesterday's predictions
uv run --env-file .env -- python -m src.modeling.predict_daily --evaluate
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

## Model Details

### Features

The model uses several categories of features:

1. **Static Account Features**: Plan details, risk parameters
2. **Dynamic Account State**: Current balance, equity, distances to targets
3. **Historical Performance**: Rolling PnL statistics, win rates, Sharpe ratios
4. **Behavioral Features**: Trading patterns, instrument concentration, risk management
5. **Market Regime Features**: Sentiment scores, volatility regimes, economic indicators
6. **Temporal Features**: Day of week, month, quarter effects

### Target Variable

The target variable is `net_profit` from the daily metrics, representing the PnL for day T+1.

### Model Configuration

- **Algorithm**: LightGBM (gradient boosting)
- **Objective**: MAE, Huber, or Fair (robust to outliers)
- **Hyperparameter Tuning**: Optuna with time-series cross-validation
- **Feature Scaling**: StandardScaler for numerical features
- **Categorical Handling**: Native LightGBM categorical feature support

## Database Schema

The pipeline uses a dedicated `prop_trading_model` schema with tables for:

- Raw data ingestion (`raw_*` tables)
- Staging/preprocessing (`stg_*` tables)
- Feature storage (`feature_store_account_daily`)
- Model training (`model_training_input`)
- Predictions (`model_predictions`)
- Model registry and pipeline logs

## Monitoring and Logging

- **Logs**: Stored in the `logs/` directory with timestamps
- **Pipeline Execution**: Tracked in `pipeline_execution_log` table
- **Model Performance**: Evaluated daily and stored in the database
- **Feature Importance**: Calculated and stored with each model version

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure you're running scripts with `uv run --env-file .env`
2. **Database connection**: Check credentials in `.env` file
3. **API rate limits**: The client implements rate limiting, but adjust if needed
4. **Memory issues**: For large datasets, consider increasing batch sizes in ingestion scripts
5. **Missing data**: Check pipeline logs for specific dates/accounts

### Debugging

Enable debug logging:
```bash
uv run --env-file .env -- python src/pipeline_orchestration/run_pipeline.py --log-level DEBUG
```

Check pipeline status:
```sql
SELECT * FROM prop_trading_model.pipeline_execution_log 
ORDER BY created_at DESC LIMIT 10;
```

## Contributing

1. Follow the existing code structure and naming conventions
2. Add appropriate logging and error handling
3. Update documentation for new features
4. Test thoroughly with time-series data

## License

[Specify your license here]

## Contact

For questions or issues, please contact the development team or create an issue in the repository.
