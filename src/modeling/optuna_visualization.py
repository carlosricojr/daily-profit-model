#!/usr/bin/env python
"""Advanced visualization and reporting for Optuna studies.

This module provides comprehensive visualization capabilities including:
- Interactive dashboards
- Hyperparameter analysis
- Model performance tracking
- Ensemble optimization reports
"""

import optuna
from optuna.visualization import (
    plot_optimization_history,
    plot_param_importances,
    plot_parallel_coordinate,
    plot_contour,
    plot_slice,
    plot_edf,
    plot_intermediate_values,
    plot_pareto_front
)
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from pathlib import Path
import json
from typing import Dict, List, Optional, Union, Tuple
import logging
from datetime import datetime
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from optuna_utils import OptunaStudyManager

logger = logging.getLogger(__name__)


class OptunaVisualizer:
    """Advanced visualization for Optuna optimization results."""
    
    def __init__(self, storage_dir: Union[str, Path]):
        """Initialize visualizer.
        
        Args:
            storage_dir: Directory containing Optuna study databases
        """
        self.storage_dir = Path(storage_dir)
        self.study_manager = OptunaStudyManager(storage_dir)
        
    def create_optimization_dashboard(self, study: optuna.Study, 
                                    output_path: Optional[Path] = None) -> go.Figure:
        """Create comprehensive optimization dashboard.
        
        Args:
            study: Optuna study object
            output_path: Path to save HTML dashboard
            
        Returns:
            Plotly figure object
        """
        # Create subplots
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                "Optimization History",
                "Parameter Importances",
                "Parallel Coordinates",
                "Trial Distribution",
                "Best Parameters Evolution",
                "Pruning Analysis"
            ),
            specs=[
                [{"type": "scatter"}, {"type": "bar"}],
                [{"type": "scatter"}, {"type": "histogram"}],
                [{"type": "scatter"}, {"type": "scatter"}]
            ],
            vertical_spacing=0.1,
            horizontal_spacing=0.1
        )
        
        # Get trial data
        trials_df = study.trials_dataframe()
        completed_trials = trials_df[trials_df["state"] == "COMPLETE"]
        pruned_trials = trials_df[trials_df["state"] == "PRUNED"]
        
        # 1. Optimization History
        if len(completed_trials) > 0:
            best_values = []
            current_best = float('inf') if study.direction == optuna.StudyDirection.MINIMIZE else float('-inf')
            
            for value in completed_trials["value"]:
                if study.direction == optuna.StudyDirection.MINIMIZE:
                    current_best = min(current_best, value)
                else:
                    current_best = max(current_best, value)
                best_values.append(current_best)
            
            fig.add_trace(
                go.Scatter(
                    x=completed_trials["number"],
                    y=completed_trials["value"],
                    mode="markers",
                    name="Trial Values",
                    marker=dict(size=6, opacity=0.6)
                ),
                row=1, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=completed_trials["number"],
                    y=best_values,
                    mode="lines",
                    name="Best Value",
                    line=dict(color="red", width=2)
                ),
                row=1, col=1
            )
        
        # 2. Parameter Importances
        if len(study.best_params) > 0 and len(completed_trials) >= 10:
            try:
                importances = optuna.importance.get_param_importances(study)
                fig.add_trace(
                    go.Bar(
                        x=list(importances.values()),
                        y=list(importances.keys()),
                        orientation="h",
                        name="Importance"
                    ),
                    row=1, col=2
                )
            except:
                logger.warning("Could not calculate parameter importances")
        
        # 3. Parallel Coordinates (top trials)
        if len(completed_trials) >= 5:
            top_trials = completed_trials.nsmallest(10, "value") if study.direction == optuna.StudyDirection.MINIMIZE \
                        else completed_trials.nlargest(10, "value")
            
            param_cols = [col for col in top_trials.columns if col.startswith("params_")]
            if param_cols:
                # Normalize parameters for visualization
                normalized_data = []
                for col in param_cols:
                    if top_trials[col].dtype in [np.float64, np.int64]:
                        min_val = top_trials[col].min()
                        max_val = top_trials[col].max()
                        if max_val > min_val:
                            normalized_data.append(
                                (top_trials[col] - min_val) / (max_val - min_val)
                            )
                        else:
                            normalized_data.append(top_trials[col] * 0)
                
                if normalized_data:
                    for i, trial_idx in enumerate(top_trials.index):
                        fig.add_trace(
                            go.Scatter(
                                x=list(range(len(param_cols))),
                                y=[normalized_data[j].iloc[i] for j in range(len(normalized_data))],
                                mode="lines+markers",
                                name=f"Trial {top_trials.loc[trial_idx, 'number']}",
                                showlegend=False,
                                opacity=0.7
                            ),
                            row=2, col=1
                        )
        
        # 4. Trial Distribution
        trial_states = trials_df["state"].value_counts()
        fig.add_trace(
            go.Histogram(
                x=trials_df["state"],
                name="Trial States",
                showlegend=False
            ),
            row=2, col=2
        )
        
        # 5. Best Parameters Evolution
        if len(completed_trials) > 0 and len(study.best_params) > 0:
            # Track how best parameter values change over trials
            param_evolution = {}
            for param_name in study.best_params.keys():
                param_col = f"params_{param_name}"
                if param_col in completed_trials.columns:
                    param_evolution[param_name] = []
                    
                    current_best_value = float('inf') if study.direction == optuna.StudyDirection.MINIMIZE else float('-inf')
                    current_best_param = None
                    
                    for idx, row in completed_trials.iterrows():
                        if study.direction == optuna.StudyDirection.MINIMIZE:
                            if row["value"] < current_best_value:
                                current_best_value = row["value"]
                                current_best_param = row[param_col]
                        else:
                            if row["value"] > current_best_value:
                                current_best_value = row["value"]
                                current_best_param = row[param_col]
                        
                        param_evolution[param_name].append(current_best_param)
            
            # Plot evolution of most important parameters
            important_params = list(study.best_params.keys())[:3]  # Top 3 parameters
            for param in important_params:
                if param in param_evolution:
                    fig.add_trace(
                        go.Scatter(
                            x=completed_trials["number"],
                            y=param_evolution[param],
                            mode="lines",
                            name=param
                        ),
                        row=3, col=1
                    )
        
        # 6. Pruning Analysis
        if len(pruned_trials) > 0:
            # Show at which iteration trials were pruned
            fig.add_trace(
                go.Histogram(
                    x=pruned_trials["datetime_complete"] - pruned_trials["datetime_start"],
                    nbinsx=20,
                    name="Pruning Times",
                    showlegend=False
                ),
                row=3, col=2
            )
        
        # Update layout
        fig.update_layout(
            title=f"Optuna Optimization Dashboard - {study.study_name}",
            height=1200,
            showlegend=True,
            template="plotly_white"
        )
        
        # Update axes
        fig.update_xaxes(title_text="Trial Number", row=1, col=1)
        fig.update_yaxes(title_text="Objective Value", row=1, col=1)
        fig.update_xaxes(title_text="Importance", row=1, col=2)
        fig.update_xaxes(title_text="Parameter Index", row=2, col=1)
        fig.update_yaxes(title_text="Normalized Value", row=2, col=1)
        fig.update_xaxes(title_text="State", row=2, col=2)
        fig.update_yaxes(title_text="Count", row=2, col=2)
        fig.update_xaxes(title_text="Trial Number", row=3, col=1)
        fig.update_yaxes(title_text="Parameter Value", row=3, col=1)
        fig.update_xaxes(title_text="Duration", row=3, col=2)
        fig.update_yaxes(title_text="Count", row=3, col=2)
        
        if output_path:
            fig.write_html(output_path)
            logger.info(f"Dashboard saved to {output_path}")
            
        return fig
    
    def create_ensemble_report(self, study_names: List[str], 
                             output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Create comprehensive report for ensemble optimization.
        
        Args:
            study_names: List of study names for different targets
            output_dir: Directory to save report
            
        Returns:
            Report data dictionary
        """
        if output_dir is None:
            output_dir = self.storage_dir / "reports" / f"ensemble_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir.mkdir(exist_ok=True, parents=True)
        
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "studies": {},
            "summary": {}
        }
        
        # Create PDF for static plots
        pdf_path = output_dir / "ensemble_report.pdf"
        with PdfPages(pdf_path) as pdf:
            # Summary page
            fig, ax = plt.subplots(figsize=(10, 8))
            ax.text(0.5, 0.9, "Ensemble Optimization Report", 
                   ha='center', va='top', fontsize=20, weight='bold')
            ax.text(0.5, 0.8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                   ha='center', va='top', fontsize=12)
            ax.text(0.5, 0.7, f"Number of Models: {len(study_names)}", 
                   ha='center', va='top', fontsize=14)
            ax.axis('off')
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()
            
            # Individual study analyses
            for study_name in study_names:
                try:
                    study = optuna.load_study(
                        study_name=study_name,
                        storage=f"sqlite:///{self.storage_dir}/{study_name}.db"
                    )
                    
                    # Get study summary
                    summary = self.study_manager.get_study_summary(study)
                    report_data["studies"][study_name] = summary
                    
                    # Create study-specific plots
                    fig = plt.figure(figsize=(15, 10))
                    
                    # Plot 1: Optimization history
                    ax1 = plt.subplot(2, 3, 1)
                    trials_df = study.trials_dataframe()
                    completed = trials_df[trials_df["state"] == "COMPLETE"]
                    if len(completed) > 0:
                        ax1.scatter(completed["number"], completed["value"], alpha=0.6)
                        ax1.set_xlabel("Trial")
                        ax1.set_ylabel("Objective Value")
                        ax1.set_title(f"{study_name} - Optimization History")
                    
                    # Plot 2: Parameter distribution
                    ax2 = plt.subplot(2, 3, 2)
                    if len(study.best_params) > 0:
                        param_data = []
                        param_names = []
                        for param, value in study.best_params.items():
                            if isinstance(value, (int, float)):
                                param_data.append(value)
                                param_names.append(param)
                        
                        if param_data:
                            ax2.bar(param_names, param_data)
                            ax2.set_xlabel("Parameter")
                            ax2.set_ylabel("Best Value")
                            ax2.set_title("Best Parameters")
                            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
                    
                    # Plot 3: Trial state distribution
                    ax3 = plt.subplot(2, 3, 3)
                    state_counts = trials_df["state"].value_counts()
                    ax3.pie(state_counts.values, labels=state_counts.index, autopct='%1.1f%%')
                    ax3.set_title("Trial States")
                    
                    # Plot 4: Value distribution
                    ax4 = plt.subplot(2, 3, 4)
                    if len(completed) > 0:
                        ax4.hist(completed["value"], bins=20, alpha=0.7, edgecolor='black')
                        ax4.axvline(study.best_value, color='red', linestyle='--', 
                                   label=f'Best: {study.best_value:.4f}')
                        ax4.set_xlabel("Objective Value")
                        ax4.set_ylabel("Count")
                        ax4.set_title("Value Distribution")
                        ax4.legend()
                    
                    # Plot 5: Convergence analysis
                    ax5 = plt.subplot(2, 3, 5)
                    if len(completed) > 0:
                        # Calculate running best
                        running_best = []
                        current_best = float('inf') if study.direction == optuna.StudyDirection.MINIMIZE else float('-inf')
                        
                        for value in completed["value"]:
                            if study.direction == optuna.StudyDirection.MINIMIZE:
                                current_best = min(current_best, value)
                            else:
                                current_best = max(current_best, value)
                            running_best.append(current_best)
                        
                        ax5.plot(completed["number"], running_best, 'r-', linewidth=2)
                        ax5.set_xlabel("Trial")
                        ax5.set_ylabel("Best Value")
                        ax5.set_title("Convergence")
                        ax5.grid(True, alpha=0.3)
                    
                    # Plot 6: Time analysis
                    ax6 = plt.subplot(2, 3, 6)
                    if len(completed) > 0:
                        durations = (completed["datetime_complete"] - completed["datetime_start"]).dt.total_seconds()
                        ax6.scatter(completed["number"], durations, alpha=0.6)
                        ax6.set_xlabel("Trial")
                        ax6.set_ylabel("Duration (seconds)")
                        ax6.set_title("Trial Duration")
                    
                    plt.suptitle(f"Study: {study_name}", fontsize=16, weight='bold')
                    plt.tight_layout()
                    pdf.savefig(fig, bbox_inches='tight')
                    plt.close()
                    
                    # Save interactive visualizations
                    study_output_dir = output_dir / study_name
                    study_output_dir.mkdir(exist_ok=True)
                    
                    # Create dashboard
                    dashboard = self.create_optimization_dashboard(study)
                    dashboard.write_html(study_output_dir / "dashboard.html")
                    
                    # Save other visualizations
                    try:
                        plot_optimization_history(study).write_html(
                            study_output_dir / "optimization_history.html"
                        )
                        plot_param_importances(study).write_html(
                            study_output_dir / "param_importances.html"
                        )
                        plot_parallel_coordinate(study).write_html(
                            study_output_dir / "parallel_coordinate.html"
                        )
                        plot_slice(study).write_html(
                            study_output_dir / "slice.html"
                        )
                    except Exception as e:
                        logger.warning(f"Some visualizations failed for {study_name}: {e}")
                    
                except Exception as e:
                    logger.error(f"Failed to process study {study_name}: {e}")
                    report_data["studies"][study_name] = {"error": str(e)}
            
            # Ensemble comparison page
            if len(report_data["studies"]) > 1:
                fig, axes = plt.subplots(2, 2, figsize=(12, 10))
                fig.suptitle("Ensemble Model Comparison", fontsize=16, weight='bold')
                
                # Extract data for comparison
                study_names_valid = []
                best_values = []
                n_trials = []
                n_completed = []
                
                for name, data in report_data["studies"].items():
                    if "error" not in data and data.get("best_value") is not None:
                        study_names_valid.append(name)
                        best_values.append(data["best_value"])
                        n_trials.append(data["n_trials"])
                        n_completed.append(data["n_completed"])
                
                if study_names_valid:
                    # Best values comparison
                    ax = axes[0, 0]
                    ax.bar(study_names_valid, best_values)
                    ax.set_xlabel("Model")
                    ax.set_ylabel("Best Value")
                    ax.set_title("Best Values Across Models")
                    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
                    
                    # Trial counts
                    ax = axes[0, 1]
                    x = np.arange(len(study_names_valid))
                    width = 0.35
                    ax.bar(x - width/2, n_trials, width, label='Total')
                    ax.bar(x + width/2, n_completed, width, label='Completed')
                    ax.set_xlabel("Model")
                    ax.set_ylabel("Number of Trials")
                    ax.set_title("Trial Counts")
                    ax.set_xticks(x)
                    ax.set_xticklabels(study_names_valid, rotation=45, ha='right')
                    ax.legend()
                    
                    # Efficiency analysis
                    ax = axes[1, 0]
                    efficiency = [c/t if t > 0 else 0 for c, t in zip(n_completed, n_trials)]
                    ax.bar(study_names_valid, efficiency)
                    ax.set_xlabel("Model")
                    ax.set_ylabel("Completion Rate")
                    ax.set_title("Trial Completion Efficiency")
                    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
                    
                    # Summary statistics
                    ax = axes[1, 1]
                    ax.axis('off')
                    summary_text = "Ensemble Summary:\n\n"
                    summary_text += f"Total Models: {len(study_names_valid)}\n"
                    summary_text += f"Total Trials: {sum(n_trials)}\n"
                    summary_text += f"Total Completed: {sum(n_completed)}\n"
                    summary_text += f"Average Best Value: {np.mean(best_values):.4f}\n"
                    summary_text += f"Best Model: {study_names_valid[np.argmin(best_values)]}\n"
                    ax.text(0.1, 0.9, summary_text, fontsize=12, va='top')
                
                plt.tight_layout()
                pdf.savefig(fig, bbox_inches='tight')
                plt.close()
        
        # Calculate ensemble summary
        valid_studies = [s for s in report_data["studies"].values() if "error" not in s]
        if valid_studies:
            report_data["summary"] = {
                "total_models": len(study_names),
                "successful_models": len(valid_studies),
                "total_trials": sum(s["n_trials"] for s in valid_studies),
                "total_completed_trials": sum(s["n_completed"] for s in valid_studies),
                "average_best_value": np.mean([s["best_value"] for s in valid_studies if s["best_value"] is not None]),
                "report_path": str(output_dir)
            }
        
        # Save JSON report
        with open(output_dir / "report_data.json", "w") as f:
            json.dump(report_data, f, indent=2)
        
        logger.info(f"Ensemble report saved to {output_dir}")
        
        return report_data
    
    def create_hyperparameter_analysis(self, study: optuna.Study, 
                                     output_path: Optional[Path] = None) -> go.Figure:
        """Create detailed hyperparameter analysis visualization.
        
        Args:
            study: Optuna study object
            output_path: Path to save HTML file
            
        Returns:
            Plotly figure object
        """
        # Get trials data
        trials_df = study.trials_dataframe()
        completed_trials = trials_df[trials_df["state"] == "COMPLETE"]
        
        if len(completed_trials) == 0:
            logger.warning("No completed trials to analyze")
            return go.Figure()
        
        # Get parameter columns
        param_cols = [col for col in completed_trials.columns if col.startswith("params_")]
        n_params = len(param_cols)
        
        if n_params == 0:
            logger.warning("No parameters to analyze")
            return go.Figure()
        
        # Create subplots grid
        n_cols = min(3, n_params)
        n_rows = (n_params + n_cols - 1) // n_cols
        
        fig = make_subplots(
            rows=n_rows, cols=n_cols,
            subplot_titles=[col.replace("params_", "") for col in param_cols],
            vertical_spacing=0.1,
            horizontal_spacing=0.1
        )
        
        # Plot each parameter
        for idx, param_col in enumerate(param_cols):
            row = idx // n_cols + 1
            col = idx % n_cols + 1
            
            param_name = param_col.replace("params_", "")
            param_values = completed_trials[param_col]
            
            # Check if parameter is numeric
            if param_values.dtype in [np.float64, np.int64]:
                # Scatter plot of parameter vs objective
                fig.add_trace(
                    go.Scatter(
                        x=param_values,
                        y=completed_trials["value"],
                        mode="markers",
                        name=param_name,
                        marker=dict(
                            size=8,
                            color=completed_trials["value"],
                            colorscale="Viridis",
                            showscale=idx == 0,
                            colorbar=dict(title="Objective")
                        ),
                        showlegend=False
                    ),
                    row=row, col=col
                )
                
                # Add trend line
                if len(param_values.unique()) > 1:
                    z = np.polyfit(param_values, completed_trials["value"], 1)
                    p = np.poly1d(z)
                    x_trend = np.linspace(param_values.min(), param_values.max(), 100)
                    fig.add_trace(
                        go.Scatter(
                            x=x_trend,
                            y=p(x_trend),
                            mode="lines",
                            line=dict(color="red", dash="dash"),
                            showlegend=False
                        ),
                        row=row, col=col
                    )
            else:
                # Categorical parameter - box plot
                categories = param_values.unique()
                box_data = []
                for cat in categories:
                    cat_values = completed_trials[param_values == cat]["value"]
                    box_data.append(go.Box(
                        y=cat_values,
                        name=str(cat),
                        showlegend=False
                    ))
                
                for trace in box_data:
                    fig.add_trace(trace, row=row, col=col)
            
            # Update axes
            fig.update_xaxes(title_text=param_name, row=row, col=col)
            fig.update_yaxes(title_text="Objective Value" if col == 1 else "", row=row, col=col)
        
        # Update layout
        fig.update_layout(
            title=f"Hyperparameter Analysis - {study.study_name}",
            height=300 * n_rows,
            template="plotly_white"
        )
        
        if output_path:
            fig.write_html(output_path)
            logger.info(f"Hyperparameter analysis saved to {output_path}")
        
        return fig


def main():
    """Example usage of visualization tools."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Optuna visualization and reporting")
    parser.add_argument("--storage-dir", type=str, required=True,
                       help="Directory containing Optuna studies")
    parser.add_argument("--study-name", type=str,
                       help="Single study to visualize")
    parser.add_argument("--ensemble", nargs="+",
                       help="List of study names for ensemble report")
    parser.add_argument("--output-dir", type=str,
                       help="Output directory for reports")
    
    args = parser.parse_args()
    
    visualizer = OptunaVisualizer(args.storage_dir)
    
    if args.study_name:
        # Visualize single study
        study = optuna.load_study(
            study_name=args.study_name,
            storage=f"sqlite:///{args.storage_dir}/{args.study_name}.db"
        )
        
        output_dir = Path(args.output_dir or f"{args.storage_dir}/reports/{args.study_name}")
        output_dir.mkdir(exist_ok=True, parents=True)
        
        # Create dashboard
        visualizer.create_optimization_dashboard(study, output_dir / "dashboard.html")
        
        # Create hyperparameter analysis
        visualizer.create_hyperparameter_analysis(study, output_dir / "hyperparameter_analysis.html")
        
        # Save study report
        visualizer.study_manager.save_study_report(study, output_dir)
        
    elif args.ensemble:
        # Create ensemble report
        output_dir = Path(args.output_dir) if args.output_dir else None
        visualizer.create_ensemble_report(args.ensemble, output_dir)
    
    else:
        logger.error("Please specify either --study-name or --ensemble")


if __name__ == "__main__":
    main()