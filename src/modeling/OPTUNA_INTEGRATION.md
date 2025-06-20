# Optuna Integration for LightGBM Hyperparameter Optimization

This document describes the Optuna integration for optimizing LightGBM models in the daily profit prediction pipeline.

## Overview

The Optuna integration provides state-of-the-art hyperparameter optimization for LightGBM models with the following features:

- **Automatic hyperparameter search** with Bayesian optimization
- **Early stopping and pruning** of unpromising trials
- **Parallel and distributed optimization** support
- **Comprehensive visualization and reporting**
- **Study persistence and resumability**

## Quick Start

### Basic Optimization

```python
# Run optimization for a single target
python -m src.modeling.train_with_optuna --targets net_profit --n-trials 100

# Run optimization for all targets
python -m src.modeling.train_with_optuna --n-trials 100 --use-cv
```

### Parallel Optimization

```python
# Run parallel optimization on single machine
python -m src.modeling.optuna_parallel_optimization --mode parallel --n-trials 200 --max-workers 4

# Run distributed worker (requires PostgreSQL backend)
python -m src.modeling.optuna_parallel_optimization --mode distributed --worker-id 1 --storage-url postgresql://user:pass@host:5432/optuna
```

### Visualization and Reporting

```python
# Generate report for single study
python -m src.modeling.optuna_visualization --storage-dir artefacts/optuna_studies --study-name net_profit_20240101_120000

# Generate ensemble report
python -m src.modeling.optuna_visualization --storage-dir artefacts/optuna_studies --ensemble net_profit gross_profit num_trades
```

## Architecture

### Core Components

1. **train_with_optuna.py**: Main optimization module
   - Defines hyperparameter search spaces
   - Creates objective functions
   - Manages optimization process
   - Trains final models with best parameters

2. **optuna_utils.py**: Utility functions and classes
   - `OptunaStudyManager`: Study persistence and management
   - `OptunaCallbacks`: Custom callbacks for optimization
   - Helper functions for parameter analysis

3. **optuna_parallel_optimization.py**: Parallel execution
   - `ParallelOptimizer`: Manages parallel trials
   - Support for distributed optimization
   - Resource management

4. **optuna_visualization.py**: Visualization and reporting
   - `OptunaVisualizer`: Creates interactive dashboards
   - Generates comprehensive reports
   - Parameter importance analysis

## Hyperparameter Search Spaces

### LightGBM Parameters

The integration searches over the following hyperparameters:

```python
{
    "boosting_type": ["gbdt", "dart", "goss"],
    "num_leaves": [10, 200],
    "learning_rate": [0.01, 0.3] (log scale),
    "feature_fraction": [0.5, 1.0],
    "bagging_fraction": [0.5, 1.0],
    "bagging_freq": [1, 10],
    "min_child_samples": [5, 100],
    "lambda_l1": [1e-8, 10.0] (log scale),
    "lambda_l2": [1e-8, 10.0] (log scale),
    "max_depth": [3, 12],
    "min_gain_to_split": [0.0, 1.0],
    "max_bin": [32, 512]
}
```

Additional parameters for DART boosting:
- `drop_rate`: [0.0, 0.2]
- `max_drop`: [3, 50]
- `skip_drop`: [0.0, 1.0]

Note: When GOSS (Gradient-based One-Side Sampling) is selected, bagging is automatically disabled as GOSS doesn't support bagging.

### Model-Specific Configurations

Each target has its own optimization configuration:

- **Regression targets** (net_profit, gross_profit, etc.): MAE or RMSE metric
- **Classification targets** (is_profitable, is_highly_profitable): AUC metric

## Best Practices

### 1. Pruning Strategy

The integration uses MedianPruner with:
- `n_startup_trials`: 10 (don't prune first 10 trials)
- `n_warmup_steps`: 50 (wait 50 iterations before pruning)

This balances exploration vs. early stopping of bad trials.

### 2. Parallel Execution

For multi-target optimization:
```python
# Optimize all targets in parallel
optimizer = ParallelOptimizer(n_jobs=8)
optimizer.optimize_ensemble_parallel(
    targets=["net_profit", "gross_profit", "num_trades"],
    n_trials_per_target=100,
    max_workers=3  # 3 targets in parallel
)
```

### 3. Cross-Validation

Use cross-validation for more robust hyperparameter selection:
```python
study, best_params = optimize_hyperparameters(
    target="net_profit",
    config=MODEL_CONFIGS["net_profit"],
    n_trials=100,
    use_cv=True,  # Enable cross-validation
    n_folds=5     # 5-fold CV
)
```

### 4. Study Management

Resume interrupted optimization:
```python
manager = OptunaStudyManager("artefacts/optuna_studies")
study = manager.create_or_load_study("net_profit_optimization")
# Study will resume from where it left off
```

### 5. Resource Management

The integration includes automatic resource management:
- Memory cleanup after each trial
- CPU thread limiting in parallel mode
- Garbage collection between trials

## Visualization Examples

### Optimization Dashboard

The dashboard includes:
- Optimization history with best value tracking
- Parameter importance analysis
- Parallel coordinate plots for top trials
- Trial state distribution
- Parameter evolution over time
- Pruning analysis

### Ensemble Reports

Comprehensive PDF and HTML reports showing:
- Individual model performance
- Cross-model comparisons
- Hyperparameter distributions
- Convergence analysis

## Advanced Usage

### Custom Objective Functions

```python
def custom_objective(trial, X_train, y_train, X_val, y_val):
    # Custom parameter suggestions
    params = {
        "num_leaves": trial.suggest_int("num_leaves", 20, 300),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.5, log=True),
        # Add custom parameters
        "custom_param": trial.suggest_float("custom_param", 0.0, 1.0)
    }
    
    # Custom training logic
    model = train_custom_model(params, X_train, y_train)
    
    # Custom evaluation
    score = evaluate_custom_metric(model, X_val, y_val)
    
    return score
```

### Distributed Optimization

Set up distributed optimization across multiple machines:

1. Set up shared storage (PostgreSQL recommended):
```bash
export OPTUNA_POSTGRES_USER=optuna
export OPTUNA_POSTGRES_PASSWORD=secure_password
export OPTUNA_POSTGRES_HOST=db.example.com
export OPTUNA_POSTGRES_PORT=5432
export OPTUNA_POSTGRES_DB=optuna_db
```

2. Start workers on different machines:
```bash
# Machine 1
python -m src.modeling.optuna_parallel_optimization --mode distributed --worker-id 1 --targets net_profit --n-trials 100

# Machine 2
python -m src.modeling.optuna_parallel_optimization --mode distributed --worker-id 2 --targets net_profit --n-trials 100
```

### Custom Callbacks

```python
# Create custom callback
def performance_tracking_callback(study, trial):
    if trial.number % 10 == 0:
        # Log to external tracking system
        mlflow.log_metric("best_value", study.best_value, step=trial.number)
        mlflow.log_params(study.best_params)

# Use in optimization
study.optimize(objective, n_trials=100, callbacks=[performance_tracking_callback])
```

## Troubleshooting

### Common Issues

1. **Out of Memory**: Reduce `n_jobs` or use memory-optimized data loading
2. **Slow Optimization**: Increase pruning aggressiveness or reduce search space
3. **Database Lock (SQLite)**: Use PostgreSQL for true parallel optimization
4. **Visualization Failures**: Ensure sufficient completed trials (minimum 10)

### Performance Tips

1. Start with fewer trials (50-100) to get baseline results quickly
2. Use parallel optimization for multiple targets
3. Enable pruning to stop unpromising trials early
4. Use CV only for final hyperparameter validation
5. Monitor memory usage and adjust workers accordingly

## Integration with Production Pipeline

After optimization, use the best models in production:

```python
# Load optimized model
model_path = "artefacts/models/lgb_net_profit_optuna_v1.txt"
model = lgb.Booster(model_file=model_path)

# Load optimization metadata
with open("artefacts/models/lgb_net_profit_optuna_metadata.json") as f:
    metadata = json.load(f)
    
print(f"Model trained with {metadata['training_samples']} samples")
print(f"Test {metadata['metric']}: {metadata['test_score']}")
print(f"Best hyperparameters: {metadata['hyperparameters']}")
```

## Future Enhancements

Planned improvements include:
- Integration with MLflow for experiment tracking
- AutoML capabilities for feature engineering
- Multi-objective optimization support
- GPU acceleration for trials
- Advanced ensemble strategies