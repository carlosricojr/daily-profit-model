#!/usr/bin/env python
"""Parallel hyperparameter optimization with Optuna.

This script demonstrates best practices for running Optuna optimization
in parallel, including:
- Multi-process optimization with shared storage
- Distributed optimization across machines
- GPU-aware trial distribution
- Resource management
"""

import optuna
from optuna.storages import RDBStorage
import lightgbm as lgb
import pandas as pd
import numpy as np
from pathlib import Path
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import psutil
import logging
from typing import Dict, List, Optional, Tuple, Any
import json
import time
from datetime import datetime
import os
import gc

from train_with_optuna import (
    MODEL_CONFIGS, 
    load_and_prepare_data,
    get_lgb_params_search_space
)
from optuna_utils import OptunaStudyManager, OptunaCallbacks

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(processName)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"
OPTUNA_DIR = ARTEFACT_DIR / "optuna_studies"


class ParallelOptimizer:
    """Manages parallel optimization of multiple models."""
    
    def __init__(self, storage_backend: str = "sqlite", n_jobs: int = None):
        """Initialize parallel optimizer.
        
        Args:
            storage_backend: Storage backend ("sqlite" or "postgresql")
            n_jobs: Number of parallel jobs (None for CPU count)
        """
        self.storage_backend = storage_backend
        self.n_jobs = n_jobs or mp.cpu_count()
        self.study_manager = OptunaStudyManager(OPTUNA_DIR)
        
    def create_storage(self, study_name: str) -> str:
        """Create storage URL for study.
        
        Args:
            study_name: Name of the study
            
        Returns:
            Storage URL
        """
        if self.storage_backend == "sqlite":
            return f"sqlite:///{OPTUNA_DIR}/{study_name}.db"
        elif self.storage_backend == "postgresql":
            # Use environment variables for PostgreSQL connection
            user = os.getenv("OPTUNA_POSTGRES_USER", "optuna")
            password = os.getenv("OPTUNA_POSTGRES_PASSWORD", "optuna")
            host = os.getenv("OPTUNA_POSTGRES_HOST", "localhost")
            port = os.getenv("OPTUNA_POSTGRES_PORT", "5432")
            db = os.getenv("OPTUNA_POSTGRES_DB", "optuna")
            return f"postgresql://{user}:{password}@{host}:{port}/{db}"
        else:
            raise ValueError(f"Unknown storage backend: {self.storage_backend}")
    
    def optimize_single_target(self, target: str, config: Dict[str, str],
                             n_trials: int = 100, 
                             timeout: Optional[int] = None) -> Dict[str, Any]:
        """Optimize hyperparameters for a single target.
        
        This function is designed to be called in parallel processes.
        
        Args:
            target: Target variable name
            config: Model configuration
            n_trials: Number of trials
            timeout: Timeout in seconds
            
        Returns:
            Optimization results
        """
        # Set process-specific logging
        process_logger = logging.getLogger(f"{__name__}.{target}")
        process_logger.info(f"Starting optimization for {target} (PID: {os.getpid()})")
        
        try:
            # Load data
            X_train, y_train, X_val, y_val = load_and_prepare_data(target)
            process_logger.info(f"Loaded data - Train: {X_train.shape}, Val: {X_val.shape}")
            
            # Create study
            study_name = f"{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            storage = self.create_storage(study_name)
            
            # Determine optimization direction
            direction = "minimize" if config["metric"] in ["mae", "rmse", "mse"] else "maximize"
            
            # Create study with parallel-safe storage
            study = optuna.create_study(
                study_name=study_name,
                storage=storage,
                direction=direction,
                load_if_exists=True,  # Important for parallel execution
                sampler=optuna.samplers.TPESampler(seed=42),
                pruner=optuna.pruners.MedianPruner(
                    n_startup_trials=5,  # Reduced for parallel
                    n_warmup_steps=20
                )
            )
            
            # Create objective function
            def objective(trial: optuna.Trial) -> float:
                # Get hyperparameters
                params = get_lgb_params_search_space(trial, config["objective"])
                params["metric"] = config["metric"]
                
                # Add resource constraints for parallel execution
                params["num_threads"] = max(1, psutil.cpu_count() // self.n_jobs)
                
                # Get categorical features
                cat_features = X_train.ww.select(include=["categorical", "boolean"]).columns.tolist()
                
                # Create datasets
                lgb_train = lgb.Dataset(X_train, label=y_train, categorical_feature=cat_features)
                lgb_val = lgb.Dataset(X_val, label=y_val, reference=lgb_train, categorical_feature=cat_features)
                
                # Add pruning callback
                try:
                    from optuna.integration import LightGBMPruningCallback
                    pruning_callback = LightGBMPruningCallback(
                        trial, config["metric"], valid_name="valid_0"
                    )
                except (ImportError, ModuleNotFoundError):
                    # Use custom callback if integration not available
                    class CustomPruningCallback:
                        def __init__(self, trial, metric, valid_name="valid_0"):
                            self.trial = trial
                            self.metric = metric
                            self.valid_name = valid_name
                            
                        def __call__(self, env):
                            for eval_result in env.evaluation_result_list:
                                if eval_result[0] == self.valid_name and eval_result[1] == self.metric:
                                    value = eval_result[2]
                                    self.trial.report(value, env.iteration)
                                    if self.trial.should_prune():
                                        raise optuna.TrialPruned()
                    
                    pruning_callback = CustomPruningCallback(
                        trial, config["metric"], valid_name="valid_0"
                    )
                
                # Train model
                model = lgb.train(
                    params,
                    lgb_train,
                    valid_sets=[lgb_val],
                    valid_names=["valid_0"],
                    num_boost_round=1000,
                    callbacks=[
                        lgb.early_stopping(50),
                        pruning_callback,
                        lgb.log_evaluation(0)  # Disable logging in parallel
                    ]
                )
                
                best_score = model.best_score["valid_0"][config["metric"]]
                
                # Clean up to free memory
                del model
                gc.collect()
                
                # Return score (negate if maximizing)
                return best_score if config["metric"] in ["mae", "rmse", "mse"] else -best_score
            
            # Add callbacks
            callbacks = []
            
            # Early stopping callback
            early_stop_callback = lambda study, trial: OptunaCallbacks.early_stopping_callback(
                study, trial, patience=30, min_delta=0.0001
            )
            callbacks.append(early_stop_callback)
            
            # Checkpoint callback
            checkpoint_dir = OPTUNA_DIR / "checkpoints" / target
            checkpoint_callback = lambda study, trial: OptunaCallbacks.save_checkpoint_callback(
                study, trial, checkpoint_dir, save_every=10
            )
            callbacks.append(checkpoint_callback)
            
            # Run optimization
            start_time = time.time()
            study.optimize(
                objective,
                n_trials=n_trials,
                timeout=timeout,
                callbacks=callbacks,
                gc_after_trial=True,  # Important for memory management
                show_progress_bar=False  # Disable in parallel
            )
            end_time = time.time()
            
            # Get results
            results = {
                "target": target,
                "status": "success",
                "best_params": study.best_params,
                "best_value": study.best_value,
                "best_trial": study.best_trial.number,
                "n_trials": len(study.trials),
                "n_completed": len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]),
                "n_pruned": len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED]),
                "optimization_time": end_time - start_time,
                "study_name": study_name
            }
            
            # Save study report
            self.study_manager.save_study_report(study)
            
            process_logger.info(
                f"Completed {target}: best_value={study.best_value:.4f}, "
                f"trials={len(study.trials)}, time={end_time-start_time:.1f}s"
            )
            
            # Clean up
            del X_train, y_train, X_val, y_val
            gc.collect()
            
            return results
            
        except Exception as e:
            process_logger.error(f"Failed to optimize {target}: {e}")
            return {
                "target": target,
                "status": "failed",
                "error": str(e)
            }
    
    def optimize_ensemble_parallel(self, targets: Optional[List[str]] = None,
                                 n_trials_per_target: int = 100,
                                 timeout_per_target: Optional[int] = None,
                                 max_workers: Optional[int] = None) -> Dict[str, Any]:
        """Optimize multiple targets in parallel.
        
        Args:
            targets: List of targets to optimize
            n_trials_per_target: Number of trials per target
            timeout_per_target: Timeout per target in seconds
            max_workers: Maximum number of parallel workers
            
        Returns:
            Dictionary with optimization results
        """
        if targets is None:
            targets = list(MODEL_CONFIGS.keys())
            
        if max_workers is None:
            max_workers = min(self.n_jobs, len(targets))
            
        logger.info(f"Starting parallel optimization for {len(targets)} targets with {max_workers} workers")
        
        results = {}
        start_time = time.time()
        
        # Use ProcessPoolExecutor for true parallelism
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all optimization tasks
            future_to_target = {
                executor.submit(
                    self.optimize_single_target,
                    target,
                    MODEL_CONFIGS[target],
                    n_trials_per_target,
                    timeout_per_target
                ): target
                for target in targets
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_target):
                target = future_to_target[future]
                try:
                    result = future.result()
                    results[target] = result
                    
                    if result["status"] == "success":
                        logger.info(
                            f"✓ {target}: best_value={result['best_value']:.4f}, "
                            f"trials={result['n_trials']}, time={result['optimization_time']:.1f}s"
                        )
                    else:
                        logger.error(f"✗ {target}: {result.get('error', 'Unknown error')}")
                        
                except Exception as e:
                    logger.error(f"Failed to get result for {target}: {e}")
                    results[target] = {
                        "target": target,
                        "status": "failed",
                        "error": str(e)
                    }
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Summary statistics
        successful = [r for r in results.values() if r["status"] == "success"]
        failed = [r for r in results.values() if r["status"] == "failed"]
        
        summary = {
            "total_targets": len(targets),
            "successful": len(successful),
            "failed": len(failed),
            "total_time": total_time,
            "avg_time_per_target": total_time / len(targets),
            "total_trials": sum(r.get("n_trials", 0) for r in successful),
            "results": results
        }
        
        # Save summary
        summary_path = OPTUNA_DIR / f"parallel_optimization_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
            
        logger.info(f"\nParallel optimization complete:")
        logger.info(f"  Total time: {total_time:.1f}s")
        logger.info(f"  Successful: {len(successful)}/{len(targets)}")
        logger.info(f"  Total trials: {summary['total_trials']}")
        logger.info(f"  Results saved to: {summary_path}")
        
        return summary


def distributed_optimization_worker(worker_id: int, targets: List[str],
                                  n_trials: int = 100,
                                  storage_url: Optional[str] = None):
    """Worker function for distributed optimization.
    
    This function can be run on multiple machines to contribute to the same study.
    
    Args:
        worker_id: Unique identifier for this worker
        targets: List of targets to optimize
        n_trials: Number of trials to contribute
        storage_url: Shared storage URL (e.g., PostgreSQL)
    """
    logger.info(f"Worker {worker_id} starting on host {os.uname().nodename}")
    
    for target in targets:
        if target not in MODEL_CONFIGS:
            continue
            
        config = MODEL_CONFIGS[target]
        
        try:
            # Load existing study from shared storage
            study = optuna.load_study(
                study_name=f"{target}_distributed",
                storage=storage_url or f"sqlite:///{OPTUNA_DIR}/{target}_distributed.db"
            )
            
            logger.info(f"Worker {worker_id}: Contributing {n_trials} trials to {target}")
            
            # Create objective (same as in optimize_single_target)
            X_train, y_train, X_val, y_val = load_and_prepare_data(target)
            
            def objective(trial):
                params = get_lgb_params_search_space(trial, config["objective"])
                params["metric"] = config["metric"]
                params["num_threads"] = 1  # Single thread per trial in distributed mode
                
                cat_features = X_train.ww.select(include=["categorical", "boolean"]).columns.tolist()
                
                lgb_train = lgb.Dataset(X_train, label=y_train, categorical_feature=cat_features)
                lgb_val = lgb.Dataset(X_val, label=y_val, reference=lgb_train)
                
                try:
                    from optuna.integration import LightGBMPruningCallback
                    pruning_callback = LightGBMPruningCallback(
                        trial, config["metric"], valid_name="valid_0"
                    )
                except (ImportError, ModuleNotFoundError):
                    # Use custom callback if integration not available
                    class CustomPruningCallback:
                        def __init__(self, trial, metric, valid_name="valid_0"):
                            self.trial = trial
                            self.metric = metric
                            self.valid_name = valid_name
                            
                        def __call__(self, env):
                            for eval_result in env.evaluation_result_list:
                                if eval_result[0] == self.valid_name and eval_result[1] == self.metric:
                                    value = eval_result[2]
                                    self.trial.report(value, env.iteration)
                                    if self.trial.should_prune():
                                        raise optuna.TrialPruned()
                    
                    pruning_callback = CustomPruningCallback(
                        trial, config["metric"], valid_name="valid_0"
                    )
                
                model = lgb.train(
                    params,
                    lgb_train,
                    valid_sets=[lgb_val],
                    valid_names=["valid_0"],
                    num_boost_round=1000,
                    callbacks=[lgb.early_stopping(50), pruning_callback, lgb.log_evaluation(0)]
                )
                
                best_score = model.best_score["valid_0"][config["metric"]]
                
                del model
                gc.collect()
                
                return best_score if config["metric"] in ["mae", "rmse", "mse"] else -best_score
            
            # Run optimization
            study.optimize(objective, n_trials=n_trials, gc_after_trial=True)
            
            logger.info(
                f"Worker {worker_id}: Completed {n_trials} trials for {target}. "
                f"Study now has {len(study.trials)} total trials."
            )
            
            # Clean up
            del X_train, y_train, X_val, y_val
            gc.collect()
            
        except Exception as e:
            logger.error(f"Worker {worker_id} failed on {target}: {e}")


def main():
    """Main entry point for parallel optimization."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Parallel Optuna optimization")
    parser.add_argument("--mode", choices=["parallel", "distributed"], default="parallel",
                       help="Optimization mode")
    parser.add_argument("--targets", nargs="+", help="Targets to optimize")
    parser.add_argument("--n-trials", type=int, default=100, 
                       help="Number of trials per target")
    parser.add_argument("--timeout", type=int, help="Timeout per target in seconds")
    parser.add_argument("--max-workers", type=int, help="Maximum parallel workers")
    parser.add_argument("--storage-backend", choices=["sqlite", "postgresql"], 
                       default="sqlite", help="Storage backend")
    parser.add_argument("--worker-id", type=int, help="Worker ID for distributed mode")
    parser.add_argument("--storage-url", help="Storage URL for distributed mode")
    
    args = parser.parse_args()
    
    if args.mode == "parallel":
        # Run parallel optimization on single machine
        optimizer = ParallelOptimizer(
            storage_backend=args.storage_backend,
            n_jobs=args.max_workers
        )
        
        results = optimizer.optimize_ensemble_parallel(
            targets=args.targets,
            n_trials_per_target=args.n_trials,
            timeout_per_target=args.timeout,
            max_workers=args.max_workers
        )
        
    elif args.mode == "distributed":
        # Run as distributed worker
        if args.worker_id is None:
            raise ValueError("Worker ID required for distributed mode")
            
        distributed_optimization_worker(
            worker_id=args.worker_id,
            targets=args.targets or list(MODEL_CONFIGS.keys()),
            n_trials=args.n_trials,
            storage_url=args.storage_url
        )


if __name__ == "__main__":
    main()