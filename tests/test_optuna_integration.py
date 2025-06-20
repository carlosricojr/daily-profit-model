"""Tests for Optuna integration with LightGBM.

This module tests:
- Basic Optuna optimization functionality
- Pruning and early stopping
- Parallel optimization
- Study management and persistence
- Visualization generation
"""

import pytest
import optuna
import lightgbm as lgb
import pandas as pd
import numpy as np
from pathlib import Path
import tempfile
import shutil
import json
from unittest.mock import Mock, patch, MagicMock
import multiprocessing as mp

# Import modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from modeling.train_with_optuna import (
    get_lgb_params_search_space,
    create_objective,
    optimize_hyperparameters,
    train_final_model,
    MODEL_CONFIGS
)
from modeling.optuna_utils import (
    OptunaStudyManager,
    OptunaCallbacks,
    suggest_categorical_features,
    analyze_parameter_interactions
)
from modeling.optuna_parallel_optimization import ParallelOptimizer
from modeling.optuna_visualization import OptunaVisualizer


@pytest.fixture
def sample_data():
    """Create sample data for testing."""
    np.random.seed(42)
    n_samples = 1000
    n_features = 10
    
    # Create features
    X = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        columns=[f"feature_{i}" for i in range(n_features)]
    )
    
    # Add categorical features
    X["cat_feature_1"] = np.random.choice(["A", "B", "C"], n_samples)
    X["cat_feature_2"] = np.random.choice(["X", "Y"], n_samples)
    
    # Initialize Woodwork
    X.ww.init(logical_types={
        "cat_feature_1": "categorical",
        "cat_feature_2": "categorical"
    })
    
    # Create target (with some noise)
    y = X["feature_0"] * 2 + X["feature_1"] * 1.5 + np.random.randn(n_samples) * 0.1
    
    return X, y


@pytest.fixture
def temp_storage_dir():
    """Create temporary directory for test storage."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


class TestOptunaHyperparameters:
    """Test hyperparameter search space and suggestions."""
    
    def test_lgb_params_search_space_regression(self):
        """Test parameter search space for regression."""
        trial = optuna.trial.FixedTrial({
            "boosting_type": "gbdt",
            "num_leaves": 50,
            "learning_rate": 0.1,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.7,
            "bagging_freq": 5,
            "min_child_samples": 20,
            "lambda_l1": 0.01,
            "lambda_l2": 0.1,
            "max_depth": 8,
            "min_gain_to_split": 0.1,
            "max_bin": 255
        })
        
        params = get_lgb_params_search_space(trial, "regression")
        
        assert params["objective"] == "regression"
        assert params["boosting_type"] == "gbdt"
        assert params["num_leaves"] == 50
        assert params["learning_rate"] == 0.1
        assert params["bagging_fraction"] == 0.7
        assert params["bagging_freq"] == 5
        assert params["min_gain_to_split"] == 0.1
        assert params["max_bin"] == 255
        assert params["verbose"] == -1
        assert params["random_state"] == 42
    
    def test_lgb_params_search_space_binary(self):
        """Test parameter search space for binary classification."""
        trial = optuna.trial.FixedTrial({
            "boosting_type": "dart",
            "num_leaves": 100,
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 7,
            "min_child_samples": 10,
            "lambda_l1": 0.001,
            "lambda_l2": 0.01,
            "max_depth": 10,
            "min_gain_to_split": 0.05,
            "max_bin": 128,
            "drop_rate": 0.1,
            "max_drop": 20,
            "skip_drop": 0.5
        })
        
        params = get_lgb_params_search_space(trial, "binary")
        
        assert params["objective"] == "binary"
        assert params["boosting_type"] == "dart"
        # Check DART-specific parameters
        assert "drop_rate" in params
        assert "max_drop" in params
        assert "skip_drop" in params
    
    def test_lgb_params_search_space_goss(self):
        """Test parameter search space for GOSS boosting."""
        trial = optuna.trial.FixedTrial({
            "boosting_type": "goss",
            "num_leaves": 75,
            "learning_rate": 0.08,
            "feature_fraction": 0.85,
            "bagging_fraction": 0.75,  # Should be overridden
            "bagging_freq": 6,  # Should be overridden
            "min_child_samples": 15,
            "lambda_l1": 0.005,
            "lambda_l2": 0.05,
            "max_depth": 9,
            "min_gain_to_split": 0.2,
            "max_bin": 200
        })
        
        params = get_lgb_params_search_space(trial, "regression")
        
        assert params["objective"] == "regression"
        assert params["boosting_type"] == "goss"
        # Check that bagging is disabled for GOSS
        assert params["bagging_fraction"] == 1.0
        assert params["bagging_freq"] == 0
    
    def test_suggest_categorical_features(self):
        """Test categorical feature selection."""
        trial = optuna.trial.FixedTrial({
            "n_categorical_features": 2,
            "use_cat_feature_0": True,
            "use_cat_feature_1": False,
            "use_cat_feature_2": True
        })
        
        feature_names = ["cat_1", "cat_2", "cat_3"]
        selected = suggest_categorical_features(trial, feature_names, min_features=1, max_features=3)
        
        assert len(selected) == 2
        assert "cat_1" in selected
        assert "cat_3" in selected
        assert "cat_2" not in selected


class TestOptunaObjective:
    """Test objective function creation and behavior."""
    
    def test_create_objective_regression(self, sample_data):
        """Test objective function for regression."""
        X, y = sample_data
        X_train = X[:800]
        y_train = y[:800]
        X_val = X[800:]
        y_val = y[800:]
        
        config = {"objective": "regression", "metric": "mae"}
        objective = create_objective("test_target", config, X_train, y_train, X_val, y_val, use_cv=False)
        
        # Create a trial
        study = optuna.create_study(direction="minimize")
        trial = study.ask()
        
        # Run objective
        result = objective(trial)
        
        assert isinstance(result, float)
        assert result > 0  # MAE should be positive
    
    @pytest.mark.slow
    def test_create_objective_with_cv(self, sample_data):
        """Test objective function with cross-validation."""
        X, y = sample_data
        config = {"objective": "regression", "metric": "rmse"}
        
        # Combine train and val for CV
        objective = create_objective("test_target", config, X, y, None, None, use_cv=True, n_folds=3)
        
        study = optuna.create_study(direction="minimize")
        trial = study.ask()
        
        result = objective(trial)
        
        assert isinstance(result, float)
        assert result > 0


class TestOptunaStudyManager:
    """Test study management functionality."""
    
    def test_create_new_study(self, temp_storage_dir):
        """Test creating a new study."""
        manager = OptunaStudyManager(temp_storage_dir)
        
        study = manager.create_or_load_study("test_study", direction="minimize")
        
        assert study.study_name == "test_study"
        assert study.direction == optuna.StudyDirection.MINIMIZE
        assert len(study.trials) == 0
    
    def test_load_existing_study(self, temp_storage_dir):
        """Test loading an existing study."""
        manager = OptunaStudyManager(temp_storage_dir)
        
        # Create study
        study1 = manager.create_or_load_study("test_study", direction="maximize")
        
        # Add a trial
        def objective(trial):
            return trial.suggest_float("x", 0, 1)
        
        study1.optimize(objective, n_trials=1)
        
        # Load the same study
        study2 = manager.create_or_load_study("test_study", direction="maximize")
        
        assert study2.study_name == "test_study"
        assert len(study2.trials) == 1
    
    def test_get_study_summary(self, temp_storage_dir):
        """Test getting study summary."""
        manager = OptunaStudyManager(temp_storage_dir)
        study = manager.create_or_load_study("test_study", direction="minimize")
        
        # Add some trials
        def objective(trial):
            x = trial.suggest_float("x", 0, 10)
            return (x - 2) ** 2
        
        study.optimize(objective, n_trials=10)
        
        summary = manager.get_study_summary(study)
        
        assert summary["study_name"] == "test_study"
        assert summary["direction"] == "MINIMIZE"
        assert summary["n_trials"] == 10
        assert summary["n_completed"] == 10
        assert summary["best_value"] is not None
        assert summary["best_params"] is not None
        assert "mean_value" in summary
        assert "std_value" in summary
    
    def test_save_study_report(self, temp_storage_dir):
        """Test saving study report."""
        manager = OptunaStudyManager(temp_storage_dir)
        study = manager.create_or_load_study("test_study", direction="minimize")
        
        # Add trial
        def objective(trial):
            x = trial.suggest_float("x", 0, 10)
            y = trial.suggest_int("y", 1, 10)
            return x * y
        
        study.optimize(objective, n_trials=5)
        
        # Save report
        report_dir = temp_storage_dir / "test_report"
        manager.save_study_report(study, report_dir)
        
        # Check files were created
        assert (report_dir / "summary.json").exists()
        assert (report_dir / "trials.csv").exists()
        assert (report_dir / "optimization_history.html").exists()
    
    def test_compare_studies(self, temp_storage_dir):
        """Test comparing multiple studies."""
        manager = OptunaStudyManager(temp_storage_dir)
        
        # Create multiple studies
        for i in range(3):
            study = manager.create_or_load_study(f"study_{i}", direction="minimize")
            
            def objective(trial):
                x = trial.suggest_float("x", 0, 10)
                return (x - i) ** 2  # Different optimum for each study
            
            study.optimize(objective, n_trials=20)
        
        # Compare studies
        comparison_df = manager.compare_studies([f"study_{i}" for i in range(3)])
        
        assert len(comparison_df) == 3
        assert "study_name" in comparison_df.columns
        assert "best_value" in comparison_df.columns
        assert "n_trials" in comparison_df.columns


class TestOptunaCallbacks:
    """Test Optuna callbacks."""
    
    def test_early_stopping_callback(self):
        """Test early stopping callback."""
        study = optuna.create_study(direction="minimize")
        
        # Add trials with no improvement
        for i in range(60):
            trial = optuna.trial.FixedTrial({"x": 1.0})
            study.add_trial(
                optuna.create_trial(
                    params={"x": 1.0},
                    distributions={"x": optuna.distributions.FloatDistribution(0, 10)},
                    value=1.0 + np.random.randn() * 0.0001  # Very small variation
                )
            )
        
        # Check if early stopping would trigger
        trial = study.ask()
        with pytest.raises(optuna.exceptions.TrialPruned):
            OptunaCallbacks.early_stopping_callback(study, trial, patience=50, min_delta=0.01)
    
    def test_save_checkpoint_callback(self, temp_storage_dir):
        """Test checkpoint saving callback."""
        study = optuna.create_study()
        checkpoint_dir = temp_storage_dir / "checkpoints"
        
        # Create mock trial
        trial = Mock()
        trial.number = 10
        
        # Add some trials to study
        for i in range(5):
            study.add_trial(
                optuna.create_trial(
                    params={"x": i},
                    distributions={"x": optuna.distributions.FloatDistribution(0, 10)},
                    value=i
                )
            )
        
        # Save checkpoint
        OptunaCallbacks.save_checkpoint_callback(study, trial, checkpoint_dir, save_every=10)
        
        # Check checkpoint was saved
        checkpoint_path = checkpoint_dir / "checkpoint_trial_10.json"
        assert checkpoint_path.exists()
        
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        
        assert checkpoint["n_trials"] == 5


class TestParallelOptimization:
    """Test parallel optimization functionality."""
    
    @patch('modeling.optuna_parallel_optimization.load_and_prepare_data')
    def test_parallel_optimizer_init(self, mock_load_data):
        """Test ParallelOptimizer initialization."""
        optimizer = ParallelOptimizer(storage_backend="sqlite", n_jobs=4)
        
        assert optimizer.storage_backend == "sqlite"
        assert optimizer.n_jobs == 4
        assert isinstance(optimizer.study_manager, OptunaStudyManager)
    
    def test_create_storage_sqlite(self, temp_storage_dir):
        """Test SQLite storage creation."""
        optimizer = ParallelOptimizer(storage_backend="sqlite")
        optimizer.study_manager = OptunaStudyManager(temp_storage_dir)
        
        storage_url = optimizer.create_storage("test_study")
        
        assert storage_url.startswith("sqlite:///")
        assert "test_study.db" in storage_url
    
    @patch.dict('os.environ', {
        'OPTUNA_POSTGRES_USER': 'testuser',
        'OPTUNA_POSTGRES_PASSWORD': 'testpass',
        'OPTUNA_POSTGRES_HOST': 'testhost',
        'OPTUNA_POSTGRES_PORT': '5432',
        'OPTUNA_POSTGRES_DB': 'testdb'
    })
    def test_create_storage_postgresql(self):
        """Test PostgreSQL storage creation."""
        optimizer = ParallelOptimizer(storage_backend="postgresql")
        
        storage_url = optimizer.create_storage("test_study")
        
        assert storage_url == "postgresql://testuser:testpass@testhost:5432/testdb"
    
    @patch('modeling.optuna_parallel_optimization.load_and_prepare_data')
    @patch('lightgbm.train')
    def test_optimize_single_target(self, mock_lgb_train, mock_load_data, temp_storage_dir):
        """Test single target optimization."""
        # Setup mocks
        X, y = pd.DataFrame(np.random.randn(100, 5)), pd.Series(np.random.randn(100))
        X.ww.init()
        mock_load_data.return_value = (X, y, X, y)
        
        mock_model = Mock()
        mock_model.best_score = {"valid_0": {"mae": 0.5}}
        mock_model.best_iteration = 100
        mock_lgb_train.return_value = mock_model
        
        # Create optimizer
        optimizer = ParallelOptimizer(storage_backend="sqlite")
        optimizer.study_manager = OptunaStudyManager(temp_storage_dir)
        
        # Run optimization
        config = {"objective": "regression", "metric": "mae"}
        results = optimizer.optimize_single_target(
            "test_target", config, n_trials=2, timeout=10
        )
        
        assert results["target"] == "test_target"
        assert results["status"] == "success"
        assert "best_params" in results
        assert "best_value" in results
        assert results["n_trials"] >= 1


class TestOptunaVisualization:
    """Test visualization functionality."""
    
    def test_visualizer_init(self, temp_storage_dir):
        """Test OptunaVisualizer initialization."""
        visualizer = OptunaVisualizer(temp_storage_dir)
        
        assert visualizer.storage_dir == temp_storage_dir
        assert isinstance(visualizer.study_manager, OptunaStudyManager)
    
    def test_create_optimization_dashboard(self, temp_storage_dir):
        """Test dashboard creation."""
        visualizer = OptunaVisualizer(temp_storage_dir)
        
        # Create a study with some trials
        study = optuna.create_study(direction="minimize")
        
        def objective(trial):
            x = trial.suggest_float("x", 0, 10)
            y = trial.suggest_int("y", 1, 10)
            return x * y
        
        study.optimize(objective, n_trials=20)
        
        # Create dashboard
        output_path = temp_storage_dir / "dashboard.html"
        fig = visualizer.create_optimization_dashboard(study, output_path)
        
        assert output_path.exists()
        assert fig is not None
    
    def test_create_hyperparameter_analysis(self, temp_storage_dir):
        """Test hyperparameter analysis visualization."""
        visualizer = OptunaVisualizer(temp_storage_dir)
        
        # Create study
        study = optuna.create_study(direction="minimize")
        
        def objective(trial):
            x = trial.suggest_float("x", 0, 10)
            y = trial.suggest_int("y", 1, 10)
            z = trial.suggest_categorical("z", ["A", "B", "C"])
            return x * y * (1 if z == "A" else 2)
        
        study.optimize(objective, n_trials=30)
        
        # Create analysis
        output_path = temp_storage_dir / "hyperparam_analysis.html"
        fig = visualizer.create_hyperparameter_analysis(study, output_path)
        
        assert output_path.exists()
        assert fig is not None
    
    def test_analyze_parameter_interactions(self, temp_storage_dir):
        """Test parameter interaction analysis."""
        # Create study with correlated parameters
        study = optuna.create_study(direction="minimize")
        
        def objective(trial):
            x = trial.suggest_float("x", 0, 10)
            y = trial.suggest_float("y", 0, 10)
            # Create interaction: best when x + y ≈ 10
            return abs((x + y) - 10)
        
        study.optimize(objective, n_trials=50)
        
        # Analyze interactions
        interaction_df = analyze_parameter_interactions(study, "x", "y", n_bins=5)
        
        assert not interaction_df.empty
        assert "x_bin" in interaction_df.columns
        assert "y_bin" in interaction_df.columns
        assert "mean_value" in interaction_df.columns


@pytest.mark.integration
class TestIntegration:
    """Integration tests for the full Optuna pipeline."""
    
    @patch('modeling.train_with_optuna.load_and_prepare_data')
    @patch('lightgbm.train')
    def test_full_optimization_pipeline(self, mock_lgb_train, mock_load_data, temp_storage_dir):
        """Test complete optimization pipeline."""
        # Setup mocks
        X, y = pd.DataFrame(np.random.randn(500, 10)), pd.Series(np.random.randn(500))
        X.ww.init()
        mock_load_data.return_value = (X[:400], y[:400], X[400:], y[400:])
        
        mock_model = Mock()
        mock_model.best_score = {"valid_0": {"mae": 0.3}}
        mock_model.best_iteration = 50
        mock_model.predict.return_value = np.random.randn(100)
        mock_model.feature_name.return_value = [f"feature_{i}" for i in range(10)]
        mock_lgb_train.return_value = mock_model
        
        # Run optimization
        from modeling.train_with_optuna import optimize_hyperparameters
        
        with patch('modeling.train_with_optuna.OPTUNA_DIR', temp_storage_dir):
            study, best_params = optimize_hyperparameters(
                target="test_target",
                config={"objective": "regression", "metric": "mae"},
                n_trials=5,
                timeout=30,
                n_jobs=1,
                use_cv=False
            )
        
        assert len(study.trials) == 5
        assert study.best_value is not None
        assert isinstance(best_params, dict)
        
        # Check that results were saved
        results_file = temp_storage_dir / "optimization_results_test_target.json"
        assert results_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])