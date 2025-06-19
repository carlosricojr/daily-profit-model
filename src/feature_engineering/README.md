# Feature Engineering Module

This module contains the feature engineering pipeline for the daily profit prediction model.

## Overview

The feature engineering pipeline has been redesigned for better memory efficiency, splitting feature calculation and target addition into separate passes to avoid memory issues with large datasets.

## Core Components

### 1. Feature Definition (`ft_feature_engineering.py`)
- Defines the EntitySet structure using Featuretools
- Creates feature definitions using Deep Feature Synthesis (DFS)
- Generates and saves feature definitions to `artefacts/daily_feature_defs_v1.joblib`
- Uses sample data (LIMIT 1000) for quick feature definition generation

**Usage:**
```bash
uv run --env-file .env.local -- python -m src.feature_engineering.ft_feature_engineering
```

### 2. Feature Matrix Building (`ft_build_feature_matrix.py`)
- Loads full production data from database
- Recreates the EntitySet with identical structure
- Splits data chronologically (train/val/test)
- Materializes feature matrices using saved feature definitions
- **Memory optimization**: Training data processed in chunks, features saved without targets
- Outputs: Test/val matrices with targets, training chunks without targets

**Usage:**
```bash
uv run --env-file .env.local -- python -m src.feature_engineering.ft_build_feature_matrix
```

### 3. Target Addition (`add_targets_to_features.py`)
- Adds target variables to feature matrices in a memory-efficient way
- Processes files sequentially to avoid memory spikes
- Uses in-place column assignment instead of pandas concat
- Converts data to float32 for 50% memory savings
- Outputs: Feature matrices with targets (chunks remain separate)

**Usage:**
```bash
uv run --env-file .env.local -- python -m src.feature_engineering.add_targets_to_features
```

### 4. Training Chunk Concatenation (`concatenate_training_chunks.py`)
- Combines training chunks into final `train_matrix.parquet`
- Uses PyArrow for memory-efficient streaming concatenation
- Validates output before cleanup (row counts, target columns)
- Automatically removes intermediate chunks after successful validation

**Usage:**
```bash
# Default: concatenate with validation and cleanup
uv run --env-file .env.local -- python -m src.feature_engineering.concatenate_training_chunks

# Keep chunks after concatenation
uv run --env-file .env.local -- python -m src.feature_engineering.concatenate_training_chunks --no-cleanup

# Skip validation (not recommended)
uv run --env-file .env.local -- python -m src.feature_engineering.concatenate_training_chunks --no-validate
```

### 5. Pipeline Orchestration (`orchestrate_feature_engineering.py`)
- Coordinates the complete feature engineering workflow
- Handles all four steps automatically (definitions, matrices, targets, concatenation)
- Validates outputs and cleans up intermediate files
- Provides integration point for main pipeline

**Usage:**
```bash
# Run complete pipeline
uv run --env-file .env.local -- python -m src.feature_engineering.orchestrate_feature_engineering

# Force rebuild feature definitions
uv run --env-file .env.local -- python -m src.feature_engineering.orchestrate_feature_engineering --rebuild-definitions

# Keep intermediate files for debugging
uv run --env-file .env.local -- python -m src.feature_engineering.orchestrate_feature_engineering --skip-cleanup
```

### 6. Multi-Target Feature Analysis (`feature_analysis.py`)
- Analyzes features for each prediction target separately
- Uses Mutual Information and LightGBM importance scoring
- Creates model-ready datasets with selected features per target
- Outputs organized by target in `artefacts/model_inputs/`

**Usage:**
```bash
uv run --env-file .env.local -- python -m src.feature_engineering.feature_analysis
```

### Utility Modules

- **`dtype_utils.py`**: Data type conversion utilities
  - Float64 to float32 conversion (50% memory savings)
  - Memory usage analysis
  - Intelligent dtype optimization

- **`pipeline_integration.py`**: Integration with main pipeline
  - Provides `run_feature_engineering()` function
  - Handles configuration and subprocess management

## Feature Categories

See `feature_catalog.md` for detailed documentation of all features, including:
- Static Features (Account & Plan Characteristics)
- Dynamic Features (Current Account State)
- Rolling Performance Features (1, 3, 5, 10, 20-day windows)
- Behavioral Features (Trading patterns)
- Market Regime Features
- Temporal Features

## Key Design Principles

1. **No Lookahead Bias**: Features from day D predict targets for day D+1
2. **Memory Efficiency**: Chunked processing for large datasets
3. **Multi-Target Support**: Separate feature selection for each prediction target
4. **80/20 Principle**: Focus on most impactful features and methods

## Output Structure

```
artefacts/
├── daily_feature_defs_v1.joblib    # Feature definitions
├── train_matrix.parquet             # Full feature matrix for training
├── val_matrix.parquet               # Full feature matrix for validation
├── test_matrix.parquet              # Full feature matrix for testing
└── model_inputs/                    # Target-specific datasets
    ├── net_profit/
    │   ├── train_matrix.parquet
    │   ├── val_matrix.parquet
    │   └── test_matrix.parquet
    ├── gross_profit/
    │   └── ... (same structure)
    ├── feature_selection_metadata.json
    └── feature_selection_summary.txt
```

## Configuration

Key parameters in `ft_build_feature_matrix.py`:
- `CHUNK_SIZE`: 100,000 (for pandas processing)
- `DATE_CHUNK_DAYS`: 7 (for training data chunking - reduced for memory efficiency)
- `VAL_DAYS`: 15 (validation window)
- `TEST_DAYS`: 30 (test window)

## Memory Management

The pipeline is optimized for systems with limited memory:

1. **Two-pass approach**: Features and targets are processed separately
2. **Chunked processing**: Training data split into 7-day chunks
3. **Float32 conversion**: Automatic conversion reduces memory by 50%
4. **PyArrow streaming**: Memory-efficient concatenation
5. **Sequential file processing**: One chunk at a time to minimize memory usage
6. **In-place operations**: Avoids memory-intensive pandas concat operations

If you encounter memory issues:
- Reduce `DATE_CHUNK_DAYS` further (e.g., to 3 or 5)
- Close other applications
- Monitor memory with: `watch -n 1 free -h`
- Ensure swap space is available: `sudo swapon --show`

## Pipeline Integration

To integrate with the main pipeline:

```python
from src.feature_engineering.pipeline_integration import run_feature_engineering

config = {
    'env_file': '.env.local',
    'rebuild_feature_definitions': False,
    'skip_cleanup': False
}

success = run_feature_engineering(config)
```

## Dependencies

- `featuretools`: For automated feature engineering
- `pandas`: Data manipulation
- `lightgbm`: Feature importance scoring
- `scikit-learn`: Mutual information calculation
- `psutil`: Memory monitoring
- `xxhash`: Fast hashing for ID generation