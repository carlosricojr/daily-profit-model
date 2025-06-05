"""
Version 1: Model Management and Versioning System
Handles model activation, deactivation, comparison, and lifecycle management.
"""

import os
import sys
import logging
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
import argparse

import pandas as pd
import numpy as np
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.utils.database import get_db_manager
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class ModelVersionManager:
    """Manages model versions, activation, and lifecycle."""
    
    def __init__(self):
        self.db_manager = get_db_manager()
    
    def list_models(self, limit: int = 20, include_inactive: bool = True) -> pd.DataFrame:
        """List all available models with their metadata."""
        # Try enhanced registry first
        try:
            query = """
            SELECT 
                model_version,
                model_type,
                test_mae,
                test_r2,
                test_direction_accuracy,
                improvement_over_baseline,
                training_duration_seconds,
                is_active,
                created_at
            FROM model_registry_enhanced
            """
            
            if not include_inactive:
                query += " WHERE is_active = true"
            
            query += " ORDER BY created_at DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            models_df = self.db_manager.model_db.execute_query_df(query)
            
        except:
            # Fallback to original registry
            query = """
            SELECT 
                model_version,
                model_type,
                test_mae,
                test_rmse,
                test_r2,
                is_active,
                created_at
            FROM model_registry
            """
            
            if not include_inactive:
                query += " WHERE is_active = true"
            
            query += " ORDER BY created_at DESC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            models_df = self.db_manager.model_db.execute_query_df(query)
        
        if models_df.empty:
            logger.warning("No models found in registry")
            return pd.DataFrame()
        
        return models_df
    
    def activate_model(self, model_version: str, 
                      deactivate_others: bool = True) -> Dict[str, Any]:
        """Activate a specific model version."""
        # Verify model exists
        check_query = "SELECT model_version FROM model_registry WHERE model_version = %s"
        result = self.db_manager.model_db.execute_query(check_query, (model_version,))
        
        if not result:
            # Check enhanced registry
            try:
                check_query = "SELECT model_version FROM model_registry_enhanced WHERE model_version = %s"
                result = self.db_manager.model_db.execute_query(check_query, (model_version,))
            except:
                pass
        
        if not result:
            raise ValueError(f"Model version '{model_version}' not found in registry")
        
        try:
            # Deactivate other models if requested
            if deactivate_others:
                deactivate_query = "UPDATE model_registry SET is_active = false"
                self.db_manager.model_db.execute_command(deactivate_query)
                
                try:
                    deactivate_query = "UPDATE model_registry_enhanced SET is_active = false"
                    self.db_manager.model_db.execute_command(deactivate_query)
                except:
                    pass  # Enhanced registry might not exist
            
            # Activate target model
            activate_query = "UPDATE model_registry SET is_active = true WHERE model_version = %s"
            self.db_manager.model_db.execute_command(activate_query, (model_version,))
            
            try:
                activate_query = "UPDATE model_registry_enhanced SET is_active = true WHERE model_version = %s"
                self.db_manager.model_db.execute_command(activate_query, (model_version,))
            except:
                pass
            
            # Log activation
            self._log_model_activation(model_version)
            
            logger.info(f"Model '{model_version}' activated successfully")
            
            return {
                "status": "success",
                "message": f"Model '{model_version}' activated",
                "active_model": model_version,
                "deactivated_others": deactivate_others
            }
            
        except Exception as e:
            logger.error(f"Failed to activate model '{model_version}': {e}")
            raise
    
    def deactivate_model(self, model_version: str) -> Dict[str, Any]:
        """Deactivate a specific model version."""
        try:
            # Deactivate in both registries
            deactivate_query = "UPDATE model_registry SET is_active = false WHERE model_version = %s"
            self.db_manager.model_db.execute_command(deactivate_query, (model_version,))
            
            try:
                deactivate_query = "UPDATE model_registry_enhanced SET is_active = false WHERE model_version = %s"
                self.db_manager.model_db.execute_command(deactivate_query, (model_version,))
            except:
                pass
            
            logger.info(f"Model '{model_version}' deactivated successfully")
            
            return {
                "status": "success",
                "message": f"Model '{model_version}' deactivated"
            }
            
        except Exception as e:
            logger.error(f"Failed to deactivate model '{model_version}': {e}")
            raise
    
    def compare_models(self, model_versions: List[str]) -> pd.DataFrame:
        """Compare multiple model versions."""
        if len(model_versions) < 2:
            raise ValueError("At least 2 models required for comparison")
        
        # Get model details
        placeholders = ', '.join(['%s'] * len(model_versions))
        
        # Try enhanced registry first
        try:
            query = f"""
            SELECT 
                model_version,
                test_mae,
                test_rmse,
                test_r2,
                test_direction_accuracy,
                improvement_over_baseline,
                training_duration_seconds,
                interval_coverage,
                created_at
            FROM model_registry_enhanced
            WHERE model_version IN ({placeholders})
            ORDER BY created_at DESC
            """
            
            comparison_df = self.db_manager.model_db.execute_query_df(query, tuple(model_versions))
            
        except:
            # Fallback to original registry
            query = f"""
            SELECT 
                model_version,
                test_mae,
                test_rmse,
                test_r2,
                created_at
            FROM model_registry
            WHERE model_version IN ({placeholders})
            ORDER BY created_at DESC
            """
            
            comparison_df = self.db_manager.model_db.execute_query_df(query, tuple(model_versions))
        
        if comparison_df.empty:
            logger.warning("No models found for comparison")
            return pd.DataFrame()
        
        # Add relative performance metrics
        if 'test_mae' in comparison_df.columns:
            best_mae = comparison_df['test_mae'].min()
            comparison_df['mae_relative_to_best'] = (comparison_df['test_mae'] / best_mae - 1) * 100
        
        if 'test_r2' in comparison_df.columns:
            best_r2 = comparison_df['test_r2'].max()
            comparison_df['r2_relative_to_best'] = (comparison_df['test_r2'] / best_r2 - 1) * 100
        
        return comparison_df
    
    def get_model_performance_over_time(self, model_version: str,
                                      days_back: int = 30) -> pd.DataFrame:
        """Get model performance metrics over time."""
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days_back)
        
        # Get evaluation results
        query = """
        SELECT 
            evaluation_date,
            mae,
            rmse,
            direction_accuracy,
            avg_calibration_error,
            interval_coverage,
            accounts_evaluated
        FROM model_evaluation_results
        WHERE model_version = %s
            AND evaluation_date BETWEEN %s AND %s
        ORDER BY evaluation_date
        """
        
        try:
            performance_df = self.db_manager.model_db.execute_query_df(
                query, (model_version, start_date, end_date)
            )
            
            if performance_df.empty:
                logger.warning(f"No performance data found for model '{model_version}'")
                return pd.DataFrame()
            
            # Calculate rolling averages
            performance_df['mae_rolling_7d'] = performance_df['mae'].rolling(window=7, min_periods=1).mean()
            performance_df['direction_accuracy_rolling_7d'] = performance_df['direction_accuracy'].rolling(window=7, min_periods=1).mean()
            
            return performance_df
            
        except Exception as e:
            logger.warning(f"Failed to get performance data for '{model_version}': {e}")
            return pd.DataFrame()
    
    def cleanup_old_models(self, keep_latest: int = 10, 
                          keep_active: bool = True,
                          dry_run: bool = True) -> Dict[str, Any]:
        """Clean up old model artifacts and registry entries."""
        # Get models to potentially remove
        query = """
        SELECT model_version, model_file_path, created_at, is_active
        FROM model_registry
        ORDER BY created_at DESC
        """
        
        models_df = self.db_manager.model_db.execute_query_df(query)
        
        if len(models_df) <= keep_latest:
            return {
                "status": "no_action",
                "message": f"Only {len(models_df)} models exist, keeping all"
            }
        
        # Determine models to remove
        models_to_remove = []
        
        for idx, row in models_df.iterrows():
            # Skip if it's in the keep_latest range
            if idx < keep_latest:
                continue
            
            # Skip if it's active and we're keeping active models
            if keep_active and row['is_active']:
                continue
            
            models_to_remove.append(row)
        
        if not models_to_remove:
            return {
                "status": "no_action",
                "message": "No models eligible for cleanup"
            }
        
        cleanup_summary = {
            "status": "planned" if dry_run else "executed",
            "models_to_remove": len(models_to_remove),
            "models_kept": len(models_df) - len(models_to_remove),
            "removed_models": []
        }
        
        if not dry_run:
            # Actually remove models
            for model in models_to_remove:
                try:
                    # Remove model files
                    model_path = Path(model['model_file_path'])
                    if model_path.exists():
                        # Remove entire model artifacts directory
                        artifacts_dir = model_path.parent
                        import shutil
                        shutil.rmtree(artifacts_dir, ignore_errors=True)
                    
                    # Remove from registry
                    delete_query = "DELETE FROM model_registry WHERE model_version = %s"
                    self.db_manager.model_db.execute_command(delete_query, (model['model_version'],))
                    
                    # Remove from enhanced registry if exists
                    try:
                        delete_query = "DELETE FROM model_registry_enhanced WHERE model_version = %s"
                        self.db_manager.model_db.execute_command(delete_query, (model['model_version'],))
                    except:
                        pass
                    
                    cleanup_summary["removed_models"].append(model['model_version'])
                    logger.info(f"Removed model: {model['model_version']}")
                    
                except Exception as e:
                    logger.error(f"Failed to remove model {model['model_version']}: {e}")
        else:
            # Dry run - just log what would be removed
            for model in models_to_remove:
                cleanup_summary["removed_models"].append(model['model_version'])
                logger.info(f"Would remove: {model['model_version']}")
        
        return cleanup_summary
    
    def get_active_model(self) -> Optional[Dict[str, Any]]:
        """Get the currently active model."""
        # Try enhanced registry first
        try:
            query = """
            SELECT * FROM model_registry_enhanced
            WHERE is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """
            result = self.db_manager.model_db.execute_query(query)
            
            if result:
                return result[0]
        except:
            pass
        
        # Fallback to original registry
        query = """
        SELECT * FROM model_registry
        WHERE is_active = true
        ORDER BY created_at DESC
        LIMIT 1
        """
        result = self.db_manager.model_db.execute_query(query)
        
        if result:
            return result[0]
        
        return None
    
    def validate_model_artifacts(self, model_version: str) -> Dict[str, Any]:
        """Validate that model artifacts exist and are loadable."""
        # Get model metadata
        query = "SELECT * FROM model_registry WHERE model_version = %s"
        result = self.db_manager.model_db.execute_query(query, (model_version,))
        
        if not result:
            # Check enhanced registry
            try:
                query = "SELECT * FROM model_registry_enhanced WHERE model_version = %s"
                result = self.db_manager.model_db.execute_query(query, (model_version,))
            except:
                pass
        
        if not result:
            return {
                "status": "error",
                "message": f"Model '{model_version}' not found in registry"
            }
        
        model_metadata = result[0]
        validation_results = {
            "status": "success",
            "model_version": model_version,
            "artifacts_found": {},
            "artifacts_loadable": {},
            "errors": []
        }
        
        # Check file existence
        required_files = {
            "model": model_metadata.get('model_file_path'),
            "scaler": model_metadata.get('scaler_file_path')
        }
        
        # Add optional files
        if model_metadata.get('model_file_path'):
            model_dir = Path(model_metadata['model_file_path']).parent
            optional_files = {
                "feature_columns": model_dir / 'feature_columns.json',
                "hyperparameters": model_dir / 'hyperparameters.json',
                "metrics": model_dir / 'metrics.json',
                "prediction_intervals": model_dir / 'prediction_intervals.pkl'
            }
            required_files.update({k: str(v) for k, v in optional_files.items()})
        
        # Check existence
        for artifact_name, file_path in required_files.items():
            if file_path and file_path != 'None':
                path_obj = Path(file_path)
                validation_results["artifacts_found"][artifact_name] = path_obj.exists()
                
                if not path_obj.exists():
                    validation_results["errors"].append(f"Missing {artifact_name}: {file_path}")
        
        # Try loading critical artifacts
        try:
            import joblib
            
            # Load model
            if validation_results["artifacts_found"].get("model", False):
                model = joblib.load(model_metadata['model_file_path'])
                validation_results["artifacts_loadable"]["model"] = True
            
            # Load scaler
            if validation_results["artifacts_found"].get("scaler", False):
                scaler = joblib.load(model_metadata['scaler_file_path'])
                validation_results["artifacts_loadable"]["scaler"] = True
            
        except Exception as e:
            validation_results["errors"].append(f"Failed to load artifacts: {str(e)}")
            validation_results["artifacts_loadable"]["model"] = False
            validation_results["artifacts_loadable"]["scaler"] = False
        
        # Update status based on validation
        if validation_results["errors"]:
            validation_results["status"] = "error"
        elif not all(validation_results["artifacts_found"].values()):
            validation_results["status"] = "warning"
        
        return validation_results
    
    def _log_model_activation(self, model_version: str):
        """Log model activation event."""
        # Create model events table if needed
        create_table_query = """
        CREATE TABLE IF NOT EXISTS model_events (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50) NOT NULL,
            model_version VARCHAR(50) NOT NULL,
            event_details JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        insert_query = """
        INSERT INTO model_events (event_type, model_version, event_details)
        VALUES (%s, %s, %s)
        """
        
        try:
            self.db_manager.model_db.execute_command(create_table_query)
            self.db_manager.model_db.execute_command(insert_query, (
                'activation',
                model_version,
                json.dumps({"activated_at": datetime.now().isoformat()})
            ))
        except Exception as e:
            logger.warning(f"Failed to log model activation: {e}")


def main():
    """Main function for model management."""
    parser = argparse.ArgumentParser(description='Model Version Manager v1')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List models
    list_parser = subparsers.add_parser('list', help='List available models')
    list_parser.add_argument('--limit', type=int, default=20, help='Maximum number of models to show')
    list_parser.add_argument('--include-inactive', action='store_true', help='Include inactive models')
    
    # Activate model
    activate_parser = subparsers.add_parser('activate', help='Activate a model')
    activate_parser.add_argument('model_version', help='Model version to activate')
    activate_parser.add_argument('--keep-others', action='store_true', help='Keep other models active')
    
    # Deactivate model
    deactivate_parser = subparsers.add_parser('deactivate', help='Deactivate a model')
    deactivate_parser.add_argument('model_version', help='Model version to deactivate')
    
    # Compare models
    compare_parser = subparsers.add_parser('compare', help='Compare model versions')
    compare_parser.add_argument('model_versions', nargs='+', help='Model versions to compare')
    
    # Performance over time
    performance_parser = subparsers.add_parser('performance', help='Show model performance over time')
    performance_parser.add_argument('model_version', help='Model version to analyze')
    performance_parser.add_argument('--days', type=int, default=30, help='Number of days to look back')
    
    # Cleanup
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old models')
    cleanup_parser.add_argument('--keep-latest', type=int, default=10, help='Number of latest models to keep')
    cleanup_parser.add_argument('--remove-active', action='store_true', help='Allow removing active models')
    cleanup_parser.add_argument('--execute', action='store_true', help='Actually execute cleanup (default is dry run)')
    
    # Validate
    validate_parser = subparsers.add_parser('validate', help='Validate model artifacts')
    validate_parser.add_argument('model_version', help='Model version to validate')
    
    # Active model
    active_parser = subparsers.add_parser('active', help='Show currently active model')
    
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Setup logging
    setup_logging(log_level=args.log_level, log_file='model_manager_v1')
    
    # Create manager
    manager = ModelVersionManager()
    
    try:
        if args.command == 'list':
            models_df = manager.list_models(
                limit=args.limit,
                include_inactive=args.include_inactive
            )
            
            if not models_df.empty:
                print("\nAvailable Models:")
                print("=" * 80)
                for _, model in models_df.iterrows():
                    active_status = "ACTIVE" if model.get('is_active', False) else "inactive"
                    print(f"{model['model_version']:20} | {active_status:8} | "
                          f"MAE: ${model.get('test_mae', 0):.2f} | "
                          f"R²: {model.get('test_r2', 0):.4f} | "
                          f"{model['created_at']}")
                print("=" * 80)
            else:
                print("No models found")
        
        elif args.command == 'activate':
            result = manager.activate_model(
                args.model_version,
                deactivate_others=not args.keep_others
            )
            print(f"✓ {result['message']}")
        
        elif args.command == 'deactivate':
            result = manager.deactivate_model(args.model_version)
            print(f"✓ {result['message']}")
        
        elif args.command == 'compare':
            comparison_df = manager.compare_models(args.model_versions)
            
            if not comparison_df.empty:
                print("\nModel Comparison:")
                print("=" * 100)
                print(comparison_df.to_string(index=False))
                print("=" * 100)
            else:
                print("No models found for comparison")
        
        elif args.command == 'performance':
            performance_df = manager.get_model_performance_over_time(
                args.model_version,
                days_back=args.days
            )
            
            if not performance_df.empty:
                print(f"\nPerformance over last {args.days} days:")
                print("=" * 80)
                print(performance_df.to_string(index=False))
                print("=" * 80)
                
                # Summary stats
                print(f"\nSummary:")
                print(f"Average MAE: ${performance_df['mae'].mean():.2f}")
                print(f"Average Direction Accuracy: {performance_df['direction_accuracy'].mean():.1%}")
                print(f"Total Accounts Evaluated: {performance_df['accounts_evaluated'].sum()}")
            else:
                print(f"No performance data found for {args.model_version}")
        
        elif args.command == 'cleanup':
            result = manager.cleanup_old_models(
                keep_latest=args.keep_latest,
                keep_active=not args.remove_active,
                dry_run=not args.execute
            )
            
            print(f"\nCleanup Results ({result['status']}):")
            print(f"Models to remove: {result['models_to_remove']}")
            print(f"Models kept: {result['models_kept']}")
            
            if result['removed_models']:
                print(f"\nModels {'removed' if not args.execute else 'to be removed'}:")
                for model in result['removed_models']:
                    print(f"  - {model}")
        
        elif args.command == 'validate':
            result = manager.validate_model_artifacts(args.model_version)
            
            print(f"\nValidation Results for {args.model_version}:")
            print(f"Status: {result['status']}")
            
            if result.get('artifacts_found'):
                print("\nArtifact Files:")
                for artifact, found in result['artifacts_found'].items():
                    status = "✓" if found else "✗"
                    print(f"  {status} {artifact}")
            
            if result.get('artifacts_loadable'):
                print("\nLoadable Artifacts:")
                for artifact, loadable in result['artifacts_loadable'].items():
                    status = "✓" if loadable else "✗"
                    print(f"  {status} {artifact}")
            
            if result.get('errors'):
                print("\nErrors:")
                for error in result['errors']:
                    print(f"  ✗ {error}")
        
        elif args.command == 'active':
            active_model = manager.get_active_model()
            
            if active_model:
                print(f"\nCurrently Active Model:")
                print(f"Version: {active_model['model_version']}")
                print(f"Type: {active_model.get('model_type', 'Unknown')}")
                print(f"Test MAE: ${active_model.get('test_mae', 0):.2f}")
                print(f"Test R²: {active_model.get('test_r2', 0):.4f}")
                print(f"Created: {active_model['created_at']}")
            else:
                print("No active model found")
    
    except Exception as e:
        logger.error(f"Command '{args.command}' failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()