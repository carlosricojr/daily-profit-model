"""Utilities for Optuna study management and visualization.

This module provides helper functions for:
- Managing and resuming Optuna studies
- Creating comprehensive visualizations
- Analyzing hyperparameter importance
- Comparing multiple studies
"""

import optuna
from optuna.visualization import (
    plot_optimization_history,
    plot_param_importances,
    plot_parallel_coordinate,
    plot_contour,
    plot_slice,
    plot_edf,
    plot_intermediate_values
)
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import json
import logging
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)


class OptunaStudyManager:
    """Manager for Optuna studies with persistence and analysis capabilities."""
    
    def __init__(self, storage_dir: Union[str, Path]):
        """Initialize study manager.
        
        Args:
            storage_dir: Directory to store study databases and results
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True, parents=True)
        
    def create_or_load_study(self, study_name: str, direction: str = "minimize",
                           sampler: Optional[optuna.samplers.BaseSampler] = None,
                           pruner: Optional[optuna.pruners.BasePruner] = None) -> optuna.Study:
        """Create new study or load existing one.
        
        Args:
            study_name: Name of the study
            direction: Optimization direction ("minimize" or "maximize")
            sampler: Optuna sampler (defaults to TPESampler)
            pruner: Optuna pruner (defaults to MedianPruner)
            
        Returns:
            Optuna study object
        """
        storage = f"sqlite:///{self.storage_dir}/{study_name}.db"
        
        if sampler is None:
            sampler = optuna.samplers.TPESampler(seed=42)
        if pruner is None:
            pruner = optuna.pruners.MedianPruner(
                n_startup_trials=10,
                n_warmup_steps=50
            )
        
        try:
            # Try to load existing study
            study = optuna.load_study(
                study_name=study_name,
                storage=storage,
                sampler=sampler,
                pruner=pruner
            )
            logger.info(f"Loaded existing study '{study_name}' with {len(study.trials)} trials")
        except KeyError:
            # Create new study
            study = optuna.create_study(
                study_name=study_name,
                storage=storage,
                direction=direction,
                sampler=sampler,
                pruner=pruner
            )
            logger.info(f"Created new study '{study_name}'")
            
        return study
    
    def get_study_summary(self, study: optuna.Study) -> Dict:
        """Get comprehensive summary of a study.
        
        Args:
            study: Optuna study object
            
        Returns:
            Dictionary with study statistics
        """
        completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
        pruned_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED]
        failed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.FAIL]
        
        summary = {
            "study_name": study.study_name,
            "direction": study.direction.name,
            "n_trials": len(study.trials),
            "n_completed": len(completed_trials),
            "n_pruned": len(pruned_trials),
            "n_failed": len(failed_trials),
            "best_value": study.best_value if completed_trials else None,
            "best_params": study.best_params if completed_trials else None,
            "best_trial": study.best_trial.number if completed_trials else None,
        }
        
        if completed_trials:
            values = [t.value for t in completed_trials]
            summary.update({
                "mean_value": np.mean(values),
                "std_value": np.std(values),
                "min_value": np.min(values),
                "max_value": np.max(values),
                "median_value": np.median(values)
            })
            
        return summary
    
    def save_study_report(self, study: optuna.Study, output_dir: Optional[Path] = None):
        """Generate and save comprehensive study report with visualizations.
        
        Args:
            study: Optuna study object
            output_dir: Directory to save report (defaults to storage_dir/reports)
        """
        if output_dir is None:
            output_dir = self.storage_dir / "reports" / study.study_name
        output_dir.mkdir(exist_ok=True, parents=True)
        
        # Save summary
        summary = self.get_study_summary(study)
        with open(output_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        # Generate all visualizations
        try:
            # Optimization history
            fig = plot_optimization_history(study)
            fig.write_html(output_dir / "optimization_history.html")
            
            # Parameter importances
            fig = plot_param_importances(study)
            fig.write_html(output_dir / "param_importances.html")
            
            # Parallel coordinates
            fig = plot_parallel_coordinate(study)
            fig.write_html(output_dir / "parallel_coordinate.html")
            
            # Contour plots for top 2 important parameters
            if len(study.best_params) >= 2:
                fig = plot_contour(study)
                fig.write_html(output_dir / "contour.html")
            
            # Slice plots
            fig = plot_slice(study)
            fig.write_html(output_dir / "slice.html")
            
            # EDF plot
            fig = plot_edf(study)
            fig.write_html(output_dir / "edf.html")
            
            # Intermediate values (for pruning analysis)
            fig = plot_intermediate_values(study)
            fig.write_html(output_dir / "intermediate_values.html")
            
        except Exception as e:
            logger.warning(f"Failed to generate some visualizations: {e}")
        
        # Save trials dataframe
        trials_df = study.trials_dataframe()
        trials_df.to_csv(output_dir / "trials.csv", index=False)
        
        logger.info(f"Study report saved to {output_dir}")
    
    def compare_studies(self, study_names: List[str], metric_name: str = "value") -> pd.DataFrame:
        """Compare multiple studies.
        
        Args:
            study_names: List of study names to compare
            metric_name: Name of the metric being optimized
            
        Returns:
            DataFrame with comparison results
        """
        comparison_data = []
        
        for study_name in study_names:
            try:
                study = optuna.load_study(
                    study_name=study_name,
                    storage=f"sqlite:///{self.storage_dir}/{study_name}.db"
                )
                summary = self.get_study_summary(study)
                summary["study_name"] = study_name
                comparison_data.append(summary)
            except Exception as e:
                logger.warning(f"Failed to load study {study_name}: {e}")
                
        df = pd.DataFrame(comparison_data)
        return df
    
    def plot_study_comparison(self, study_names: List[str], save_path: Optional[Path] = None):
        """Create comparison plots for multiple studies.
        
        Args:
            study_names: List of study names to compare
            save_path: Path to save the plot
        """
        comparison_df = self.compare_studies(study_names)
        
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        fig.suptitle("Study Comparison", fontsize=16)
        
        # Best values
        ax = axes[0, 0]
        comparison_df.plot(x="study_name", y="best_value", kind="bar", ax=ax)
        ax.set_title("Best Values")
        ax.set_ylabel("Best Value")
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Number of trials
        ax = axes[0, 1]
        trial_data = comparison_df[["study_name", "n_completed", "n_pruned", "n_failed"]]
        trial_data.set_index("study_name").plot(kind="bar", stacked=True, ax=ax)
        ax.set_title("Trial Statistics")
        ax.set_ylabel("Number of Trials")
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Value distribution
        ax = axes[1, 0]
        value_stats = comparison_df[["study_name", "mean_value", "std_value"]]
        value_stats.plot(x="study_name", y="mean_value", yerr="std_value", 
                        kind="bar", ax=ax, capsize=5)
        ax.set_title("Value Distribution")
        ax.set_ylabel("Mean ± Std")
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Efficiency (best value / n_trials)
        ax = axes[1, 1]
        comparison_df["efficiency"] = comparison_df["best_value"] / comparison_df["n_completed"]
        comparison_df.plot(x="study_name", y="efficiency", kind="bar", ax=ax)
        ax.set_title("Optimization Efficiency")
        ax.set_ylabel("Best Value / Trials")
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()


class OptunaCallbacks:
    """Collection of useful callbacks for Optuna optimization."""
    
    @staticmethod
    def early_stopping_callback(study: optuna.Study, trial: optuna.Trial,
                               patience: int = 50, min_delta: float = 0.0001):
        """Early stopping callback based on no improvement.
        
        Args:
            study: Optuna study object
            trial: Current trial
            patience: Number of trials to wait for improvement
            min_delta: Minimum change to be considered improvement
        """
        best_trials = study.get_trials(deepcopy=False, states=[optuna.trial.TrialState.COMPLETE])
        if len(best_trials) < patience:
            return
        
        # Get best values from last patience trials
        recent_best_values = [t.value for t in best_trials[-patience:]]
        
        # Check if there's been improvement
        if study.direction == optuna.StudyDirection.MINIMIZE:
            improvement = min(recent_best_values[:-1]) - recent_best_values[-1]
        else:
            improvement = recent_best_values[-1] - max(recent_best_values[:-1])
            
        if improvement < min_delta:
            study.stop()
            logger.info(f"Early stopping triggered after {len(study.trials)} trials")
    
    @staticmethod
    def save_checkpoint_callback(study: optuna.Study, trial: optuna.Trial,
                               checkpoint_dir: Path, save_every: int = 10):
        """Save study checkpoint periodically.
        
        Args:
            study: Optuna study object
            trial: Current trial
            checkpoint_dir: Directory to save checkpoints
            save_every: Save checkpoint every N trials
        """
        if trial.number % save_every == 0:
            checkpoint_dir.mkdir(exist_ok=True, parents=True)
            
            checkpoint = {
                "study_name": study.study_name,
                "best_params": study.best_params,
                "best_value": study.best_value,
                "n_trials": len(study.trials),
                "timestamp": datetime.now().isoformat()
            }
            
            checkpoint_path = checkpoint_dir / f"checkpoint_trial_{trial.number}.json"
            with open(checkpoint_path, "w") as f:
                json.dump(checkpoint, f, indent=2)


def create_lgb_callback_for_optuna(trial: optuna.Trial, metric: str) -> callable:
    """Create a LightGBM callback that integrates with Optuna pruning.
    
    This is an enhanced version of LightGBMPruningCallback with additional features.
    
    Args:
        trial: Optuna trial object
        metric: Metric name to monitor
        
    Returns:
        LightGBM callback function
    """
    def callback(env):
        # Report intermediate value
        current_value = env.evaluation_result_list[0][2]
        trial.report(current_value, env.iteration)
        
        # Check if trial should be pruned
        if trial.should_prune():
            raise optuna.TrialPruned(f"Trial pruned at iteration {env.iteration}")
            
    return callback


def suggest_categorical_features(trial: optuna.Trial, 
                               feature_names: List[str],
                               min_features: int = 0,
                               max_features: Optional[int] = None) -> List[str]:
    """Suggest subset of categorical features to use.
    
    Useful for feature selection during hyperparameter optimization.
    
    Args:
        trial: Optuna trial object
        feature_names: List of all categorical feature names
        min_features: Minimum number of features to select
        max_features: Maximum number of features to select
        
    Returns:
        Selected categorical features
    """
    if max_features is None:
        max_features = len(feature_names)
    
    n_features = trial.suggest_int("n_categorical_features", min_features, max_features)
    
    if n_features == 0:
        return []
    
    # Suggest which features to include
    selected_features = []
    for i, feature in enumerate(feature_names):
        if trial.suggest_categorical(f"use_cat_feature_{i}", [True, False]):
            selected_features.append(feature)
            if len(selected_features) >= n_features:
                break
                
    return selected_features


def analyze_parameter_interactions(study: optuna.Study, 
                                 param1: str, param2: str,
                                 n_bins: int = 20) -> pd.DataFrame:
    """Analyze interaction between two parameters.
    
    Args:
        study: Completed Optuna study
        param1: First parameter name
        param2: Second parameter name
        n_bins: Number of bins for discretization
        
    Returns:
        DataFrame with interaction analysis
    """
    trials_df = study.trials_dataframe()
    completed_trials = trials_df[trials_df["state"] == "COMPLETE"].copy()
    
    if len(completed_trials) == 0:
        return pd.DataFrame()
    
    # Extract parameter columns
    param1_col = f"params_{param1}"
    param2_col = f"params_{param2}"
    
    if param1_col not in completed_trials.columns or param2_col not in completed_trials.columns:
        raise ValueError(f"Parameters {param1} or {param2} not found in study")
    
    # Discretize parameters
    completed_trials[f"{param1}_bin"] = pd.cut(completed_trials[param1_col], bins=n_bins)
    completed_trials[f"{param2}_bin"] = pd.cut(completed_trials[param2_col], bins=n_bins)
    
    # Calculate interaction statistics
    interaction_df = completed_trials.groupby([f"{param1}_bin", f"{param2}_bin"]).agg({
        "value": ["mean", "std", "count", "min", "max"]
    }).reset_index()
    
    interaction_df.columns = [f"{param1}_bin", f"{param2}_bin", 
                             "mean_value", "std_value", "count", "min_value", "max_value"]
    
    return interaction_df