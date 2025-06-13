"""
Pipeline orchestration that only fetches missing data.
Replaces the original run_pipeline.py with smarter data fetching logic.
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional
import subprocess
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager, close_db_connections
from utils.logging_config import setup_logging
from utils.schema_manager import SchemaManager

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the execution of the daily profit model pipeline with metrics data fetching."""

    def __init__(self):
        """Initialize the pipeline orchestrator."""
        self.db_manager = get_db_manager()
        self.src_dir = Path(__file__).parent.parent

        # Pipeline stages configuration
        self.stages = {
            "schema": {
                "name": "Database Schema Management",
                "script": None,  # Special handling - schema migration
                "module": None,
            },
            "ingestion": {
                "name": "Data Ingestion",
                "scripts": [
                    ("ingest_plans", "data_ingestion.ingest_plans"),
                    ("ingest_metrics", "data_ingestion.ingest_metrics"),
                    ("ingest_trades", "data_ingestion.ingest_trades"),
                    ("ingest_regimes", "data_ingestion.ingest_regimes"),
                ],
            },
            "preprocessing": {
                "name": "Data Preprocessing",
                "scripts": [
                    (
                        "create_staging_snapshots",
                        "preprocessing.create_staging_snapshots",
                    )
                ],
            },
            "validation": {
                "name": "Data Quality Validation",
                "scripts": [
                    ("validate_data_quality", "preprocessing.data_quality_validation"),
                ],
            },
            "feature_engineering": {
                "name": "Feature Engineering",
                "scripts": [
                    ("engineer_features", "feature_engineering.feature_engineering"),
                    ("build_training_data", "feature_engineering.build_training_data"),
                ],
            },
            "training": {
                "name": "Model Training",
                "scripts": [("train_model", "modeling.train_model")],
            },
            "prediction": {
                "name": "Daily Prediction",
                "scripts": [("predict_daily", "modeling.predict_daily")],
            },
        }

    def run_pipeline(
        self,
        stages: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip_completed: bool = True,
        dry_run: bool = False,
        force_recreate_schema: bool = False,
        preserve_data: bool = True,
        force_full_refresh: bool = False,
        enable_great_expectations: bool = True,
    ) -> Dict[str, Any]:
        """
        Run the pipeline stages with data fetching.

        Args:
            stages: List of stages to run. If None, runs all stages.
            start_date: Start date for data processing
            end_date: End date for data processing
            skip_completed: Skip stages that have already completed successfully today
            dry_run: If True, only show what would be executed
            force_recreate_schema: If True, drop and recreate schema (loses all data!)
            preserve_data: If True, preserve existing data during schema migrations
            force_full_refresh: If True, ignore existing data and fetch everything
            enable_great_expectations: If True, use Great Expectations for validation

        Returns:
            Dictionary containing execution results
        """
        start_time = datetime.now()
        results = {}

        # Determine stages to run
        if stages is None:
            stages = list(self.stages.keys())

        # Validate stages
        invalid_stages = set(stages) - set(self.stages.keys())
        if invalid_stages:
            raise ValueError(f"Invalid stages: {invalid_stages}")

        logger.info(f"Pipeline execution started at {start_time}")
        logger.info(f"Stages to run: {stages}")
        logger.info("Mode: Only fetching missing data")
        logger.info(f"Great Expectations enabled: {enable_great_expectations}")

        if dry_run:
            logger.info("DRY RUN MODE - No actual execution")

        # Execute each stage
        for stage_name in stages:
            stage_start = datetime.now()

            logger.info(f"\n{'=' * 60}")
            logger.info(f"Stage: {self.stages[stage_name]['name']}")
            logger.info(f"{'=' * 60}")

            try:
                if stage_name == "schema":
                    # Special handling for schema management
                    self._create_schema(
                        force_recreate=force_recreate_schema,
                        preserve_data=preserve_data,
                        dry_run=dry_run
                    )
                    results[stage_name] = {"status": "success", "duration": 0}

                elif stage_name == "ingestion":
                    results[stage_name] = self._run_ingestion(
                        start_date, end_date, skip_completed, dry_run, force_full_refresh
                    )

                elif stage_name == "preprocessing":
                    results[stage_name] = self._run_preprocessing(
                        start_date, end_date, skip_completed, dry_run
                    )

                elif stage_name == "validation":
                    results[stage_name] = self._run_data_validation(
                        start_date, end_date, skip_completed, dry_run, enable_great_expectations
                    )

                elif stage_name == "feature_engineering":
                    results[stage_name] = self._run_feature_engineering(
                        start_date, end_date, skip_completed, dry_run
                    )

                elif stage_name == "training":
                    results[stage_name] = self._run_training(dry_run)

                elif stage_name == "prediction":
                    results[stage_name] = self._run_prediction(dry_run)

                stage_duration = (datetime.now() - stage_start).total_seconds()
                results[stage_name]["duration"] = stage_duration
                logger.info(f"Stage completed in {stage_duration:.2f} seconds")

            except Exception as e:
                logger.error(f"Stage {stage_name} failed: {str(e)}")
                results[stage_name] = {
                    "status": "failed",
                    "error": str(e),
                    "duration": (datetime.now() - stage_start).total_seconds(),
                }

                # Stop pipeline on failure
                break

        # Summary
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"\n{'=' * 60}")
        logger.info("PIPELINE EXECUTION SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"Total duration: {total_duration:.2f} seconds")

        for stage_name, result in results.items():
            status = result.get("status", "unknown")
            duration = result.get("duration", 0)
            logger.info(f"{stage_name}: {status} ({duration:.2f}s)")

        return results

    def _create_schema(self, force_recreate=False, preserve_data=True, dry_run=False):
        """
        Ensure database schema compliance with desired state.
        
        Args:
            force_recreate: If True, drop and recreate schema (old behavior)
            preserve_data: If True, preserve existing data during migrations
            dry_run: If True, only show what would be done
        """
        schema_file = self.src_dir / "db_schema" / "schema.sql"

        if not schema_file.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_file}")

        logger.info(f"Checking database schema compliance with {schema_file}")
        
        if force_recreate:
            logger.warning("FORCE RECREATE: This will DROP and recreate the entire prop_trading_model schema!")
            if not dry_run:
                # Read schema file
                with open(schema_file, "r") as f:
                    schema_sql = f.read()
                
                # Execute schema creation (old behavior)
                with self.db_manager.model_db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(schema_sql)
                        conn.commit()
                
                logger.info("Database schema recreated successfully")
            else:
                logger.info("DRY RUN: Would drop and recreate entire schema")
        else:
            # Use Enhanced Alembic-based schema management
            try:
                from utils.enhanced_alembic_schema_manager import create_enhanced_alembic_schema_manager
                schema_manager = create_enhanced_alembic_schema_manager(self.db_manager)
                
                logger.info("Using Enhanced Alembic for production-grade schema management...")
                result = schema_manager.ensure_schema_compliance(
                    schema_path=schema_file,
                    preserve_data=preserve_data,
                    dry_run=dry_run
                )
                
                if result['migration_needed']:
                    if result['success']:
                        logger.info("Schema migration completed successfully with Alembic")
                        if 'new_revision' in result:
                            logger.info(f"  - New migration revision: {result['new_revision']}")
                        if dry_run:
                            logger.info("DRY RUN MODE - Review pending migrations")
                    else:
                        raise RuntimeError(f"Alembic schema migration failed: {result.get('error', 'Unknown error')}")
                else:
                    logger.info("Database schema is already compliant. No migration needed.")
                    
            except ImportError as e:
                logger.warning(f"Alembic not available ({str(e)}), falling back to custom schema manager")
                # Fallback to custom schema manager
                from utils.schema_manager import SchemaManager
                schema_manager = SchemaManager(self.db_manager)
                
                logger.info("Analyzing current database state and comparing with desired schema...")
                result = schema_manager.ensure_schema_compliance(
                    schema_path=schema_file,
                    preserve_data=preserve_data,
                    dry_run=dry_run
                )
                
                if result['migration_needed']:
                    if result['success']:
                        logger.info("Schema migration completed successfully")
                        logger.info(f"  - Objects created: {len(result.get('comparison', {}).get('to_create', {}))}")
                        logger.info(f"  - Objects modified: {len(result.get('comparison', {}).get('to_modify', {}))}")
                        logger.info(f"  - Objects dropped: {len(result.get('comparison', {}).get('to_drop', {}))}")
                        if dry_run:
                            logger.info("DRY RUN MODE - Review migration script:")
                            logger.info(f"  Migration file: {result.get('migration_file', 'N/A')}")
                            logger.info(f"  Rollback file: {result.get('rollback_file', 'N/A')}")
                    else:
                        raise RuntimeError(f"Schema migration failed: {result.get('error', 'Unknown error')}")
                else:
                    logger.info("Database schema is already compliant. No changes needed.")

    def _run_ingestion(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
        skip_completed: bool,
        dry_run: bool,
        force_full_refresh: bool,
    ) -> Dict[str, Any]:
        """Run data ingestion scripts with data fetching."""
        results = {"status": "success", "scripts": {}}

        # Get the actual module paths from configuration
        script_modules = dict(self.stages["ingestion"]["scripts"])

        # Ingestion commands - optimized order
        commands = []

        # Plans first - from CSV (no dependencies)
        commands.append(
            ("ingest_plans", ["--csv-dir", "../raw-data/plans", "--log-level", "INFO"])
        )

        # Metrics ingestion
        metrics_args = ["--log-level", "INFO"]
        if start_date:
            metrics_args.extend(["--start-date", str(start_date)])
        if end_date:
            metrics_args.extend(["--end-date", str(end_date)])
        if force_full_refresh:
            metrics_args.append("--force-refresh")
        
        commands.append(("ingest_metrics", metrics_args))

        # Trades ingestion
        if start_date and end_date:
            # Trades open - only recent
            commands.append(
                (
                    "ingest_trades",
                    [
                        "open",
                        "--end-date",
                        str(end_date),
                        "--log-level",
                        "INFO",
                    ],
                )
            )
            # Trades closed - with date range
            commands.append(
                (
                    "ingest_trades",
                    [
                        "closed",
                        "--start-date",
                        str(start_date),
                        "--end-date",
                        str(end_date),
                        "--log-level",
                        "INFO",
                    ],
                )
            )
        else:
            # Without date range, get all recent trades
            commands.append(
                (
                    "ingest_trades",
                    [
                        "open",
                        "--log-level",
                        "INFO",
                    ],
                )
            )
            commands.append(
                (
                    "ingest_trades",
                    [
                        "closed",
                        "--log-level",
                        "INFO",
                    ],
                )
            )

        # Regimes - with date range
        regime_args = ["--log-level", "INFO"]
        if start_date:
            regime_args.extend(["--start-date", str(start_date)])
        if end_date:
            regime_args.extend(["--end-date", str(end_date)])
        
        commands.append(("ingest_regimes", regime_args))

        # Note: Accounts ingestion removed - account IDs are now resolved batch-wise 
        # after trades ingestion using data from raw_metrics_alltime

        for script_name, args in commands:
            if skip_completed and self._is_stage_completed(script_name):
                logger.info(f"Skipping {script_name} - already completed today")
                results["scripts"][script_name] = "skipped"
                continue

            # Get the actual module path from configuration
            module_path = script_modules.get(script_name)
            
            # Handle metrics and trades separately
            if script_name == "ingest_metrics":
                module_path = "data_ingestion.ingest_metrics"
            elif script_name == "ingest_trades":
                module_path = "data_ingestion.ingest_trades"
            elif not module_path:
                module_path = f"data_ingestion.{script_name}"

            if dry_run:
                logger.info(
                    f"Would run: python -m {module_path} {' '.join(args)}"
                )
                results["scripts"][script_name] = "dry_run"
            else:
                success = self._run_python_module(module_path, args)
                results["scripts"][script_name] = "success" if success else "failed"
                if not success:
                    results["status"] = "failed"
                    break

        return results

    def _run_preprocessing(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
        skip_completed: bool,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Run preprocessing scripts."""
        results = {"status": "success", "scripts": {}}

        # Get the actual module paths from configuration
        script_modules = dict(self.stages["preprocessing"]["scripts"])

        # Preprocessing commands
        commands = [
            (
                "create_staging_snapshots",
                [
                    "--start-date",
                    str(start_date) if start_date else "2024-01-01",
                    "--end-date",
                    str(end_date)
                    if end_date
                    else str(date.today() - timedelta(days=1)),
                    "--clean-data",
                    "--log-level",
                    "INFO",
                ],
            )
        ]

        for script_name, args in commands:
            if skip_completed and self._is_stage_completed(script_name):
                logger.info(f"Skipping {script_name} - already completed today")
                results["scripts"][script_name] = "skipped"
                continue

            # Get the actual module path from configuration
            module_path = script_modules.get(script_name, f"preprocessing.{script_name}")

            if dry_run:
                logger.info(
                    f"Would run: python -m {module_path} {' '.join(args)}"
                )
                results["scripts"][script_name] = "dry_run"
            else:
                success = self._run_python_module(module_path, args)
                results["scripts"][script_name] = "success" if success else "failed"
                if not success:
                    results["status"] = "failed"

        return results

    def _run_data_validation(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
        skip_completed: bool,
        dry_run: bool,
        enable_great_expectations: bool = True,
    ) -> Dict[str, Any]:
        """Run comprehensive data validation using Great Expectations."""
        results = {"status": "success", "scripts": {}}

        validation_date = end_date if end_date else date.today() - timedelta(days=1)

        if skip_completed and self._is_stage_completed("validate_data_quality"):
            logger.info("Skipping data validation - already completed today")
            results["scripts"]["validate_data_quality"] = "skipped"
            return results

        if dry_run:
            logger.info("Would run: Great Expectations data quality validation")
            results["scripts"]["validate_data_quality"] = "dry_run"
            return results

        try:
            if enable_great_expectations:
                logger.info("Running comprehensive data validation with Great Expectations")
                
                # Import Great Expectations validator
                from preprocessing.great_expectations_config import GreatExpectationsValidator
                
                # Initialize validator
                ge_validator = GreatExpectationsValidator(self.db_manager)
                
                # Run ML pipeline validation
                validation_results = ge_validator.validate_ml_pipeline_data_quality(validation_date)
                
                # Process results
                pipeline_summary = validation_results.get("pipeline_summary", {})
                overall_success = pipeline_summary.get("overall_success", False)
                success_rate = pipeline_summary.get("success_rate", 0)
                
                logger.info(f"Great Expectations validation completed for {validation_date}")
                logger.info(f"Overall success: {overall_success}")
                logger.info(f"Success rate: {success_rate:.2%}")
                logger.info(f"Total expectations: {pipeline_summary.get('total_expectations', 0)}")
                logger.info(f"Successful expectations: {pipeline_summary.get('successful_expectations', 0)}")
                
                # Check for critical failures
                failed_tables = []
                warning_tables = []
                
                for table_name, table_result in validation_results.items():
                    if table_name == "pipeline_summary":
                        continue
                        
                    if isinstance(table_result, dict):
                        table_success = table_result.get("success", False)
                        failed_expectations = table_result.get("failed_expectations", 0)
                        total_expectations = table_result.get("total_expectations", 0)
                        
                        if not table_success and failed_expectations > 0:
                            # Determine if this is critical or warning based on table importance
                            if table_name in ["stg_accounts_daily_snapshots", "raw_metrics_daily", "raw_metrics_alltime"]:
                                failed_tables.append(f"{table_name}: {failed_expectations}/{total_expectations} expectations failed")
                            else:
                                warning_tables.append(f"{table_name}: {failed_expectations}/{total_expectations} expectations failed")
                        elif table_result.get("error"):
                            warning_tables.append(f"{table_name}: {table_result['error']}")
                
                # Determine overall result
                if failed_tables:
                    logger.error(f"Critical data validation failures: {failed_tables}")
                    results["status"] = "failed"
                    results["scripts"]["validate_data_quality"] = "failed"
                    results["error"] = f"Critical validation failures: {'; '.join(failed_tables)}"
                elif warning_tables:
                    logger.warning(f"Data validation warnings: {warning_tables}")
                    results["scripts"]["validate_data_quality"] = "warning"
                    results["warnings"] = warning_tables
                else:
                    logger.info("All data validation checks passed successfully")
                    results["scripts"]["validate_data_quality"] = "success"
                
                # Store detailed results for reporting
                results["validation_details"] = validation_results
                
            else:
                # Fallback to basic validation
                logger.info("Running basic data validation (Great Expectations disabled)")
                success = self._run_basic_data_validation(validation_date)
                results["scripts"]["validate_data_quality"] = "success" if success else "failed"
                if not success:
                    results["status"] = "failed"
                    
        except Exception as e:
            logger.error(f"Data validation failed with exception: {str(e)}")
            logger.warning("Falling back to basic data validation")
            
            # Fallback to basic validation
            try:
                success = self._run_basic_data_validation(validation_date)
                results["scripts"]["validate_data_quality"] = "success" if success else "failed"
                if not success:
                    results["status"] = "failed"
            except Exception as fallback_error:
                logger.error(f"Basic data validation also failed: {str(fallback_error)}")
                results["status"] = "failed"
                results["scripts"]["validate_data_quality"] = "failed"
                results["error"] = f"Both Great Expectations and basic validation failed: {str(e)}, {str(fallback_error)}"

        return results

    def _run_basic_data_validation(self, validation_date: date) -> bool:
        """Run basic data validation as fallback."""
        logger.info(f"Running basic data validation for {validation_date}")
        
        try:
            # Basic completeness checks
            checks = [
                {
                    "name": "alltime_metrics_completeness",
                    "query": """
                        SELECT COUNT(*) as count
                        FROM prop_trading_model.raw_metrics_alltime
                        WHERE DATE(ingestion_timestamp) = %s
                    """,
                    "min_threshold": 100,
                    "params": [validation_date],
                },
                {
                    "name": "daily_metrics_completeness",
                    "query": """
                        SELECT COUNT(DISTINCT login) as unique_logins
                        FROM prop_trading_model.raw_metrics_daily
                        WHERE date = %s
                    """,
                    "min_threshold": 50,
                    "params": [validation_date - timedelta(days=1)],
                },
                {
                    "name": "staging_snapshots_completeness",
                    "query": """
                        SELECT COUNT(*) as count
                        FROM prop_trading_model.stg_accounts_daily_snapshots
                        WHERE snapshot_date = %s
                    """,
                    "min_threshold": 30,
                    "params": [validation_date - timedelta(days=1)],
                },
            ]
            
            failed_checks = []
            
            for check in checks:
                try:
                    result = self.db_manager.model_db.execute_query(
                        check["query"], check["params"]
                    )
                    value = result[0]["count"] if result else 0
                    
                    if value < check["min_threshold"]:
                        failed_checks.append(
                            f"{check['name']}: {value} < {check['min_threshold']}"
                        )
                        logger.error(f"Basic validation check failed: {check['name']} = {value}")
                    else:
                        logger.info(f"Basic validation check passed: {check['name']} = {value}")
                        
                except Exception as e:
                    failed_checks.append(f"{check['name']}: Error - {str(e)}")
                    logger.error(f"Basic validation check error: {check['name']} - {str(e)}")
            
            if failed_checks:
                logger.error(f"Basic data validation failed: {failed_checks}")
                return False
            
            logger.info("Basic data validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Basic data validation failed with exception: {str(e)}")
            return False

    def _run_feature_engineering(
        self,
        start_date: Optional[date],
        end_date: Optional[date],
        skip_completed: bool,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Run feature engineering scripts."""
        results = {"status": "success", "scripts": {}}

        # Get the actual module paths from configuration
        script_modules = dict(self.stages["feature_engineering"]["scripts"])

        # Feature engineering commands
        commands = [
            (
                "engineer_features",
                [
                    "--start-date",
                    str(start_date) if start_date else "2024-01-01",
                    "--end-date",
                    str(end_date)
                    if end_date
                    else str(date.today() - timedelta(days=1)),
                    "--log-level",
                    "INFO",
                ],
            ),
            (
                "build_training_data",
                [
                    "--start-date",
                    str(start_date) if start_date else "2024-01-01",
                    "--end-date",
                    str(end_date)
                    if end_date
                    else str(date.today() - timedelta(days=2)),
                    "--validate",
                    "--log-level",
                    "INFO",
                ],
            ),
        ]

        for script_name, args in commands:
            if skip_completed and self._is_stage_completed(script_name):
                logger.info(f"Skipping {script_name} - already completed today")
                results["scripts"][script_name] = "skipped"
                continue

            # Get the actual module path from configuration
            module_path = script_modules.get(script_name, f"feature_engineering.{script_name}")

            if dry_run:
                logger.info(
                    f"Would run: python -m {module_path} {' '.join(args)}"
                )
                results["scripts"][script_name] = "dry_run"
            else:
                success = self._run_python_module(module_path, args)
                results["scripts"][script_name] = "success" if success else "failed"
                if not success:
                    results["status"] = "failed"

        return results

    def _run_training(self, dry_run: bool) -> Dict[str, Any]:
        """Run model training."""
        results = {"status": "success", "scripts": {}}

        # Get the actual module paths from configuration
        script_modules = dict(self.stages["training"]["scripts"])

        # Training command
        script_name = "train_model"
        args = ["--tune-hyperparameters", "--n-trials", "50", "--log-level", "INFO"]

        # Get the actual module path from configuration
        module_path = script_modules.get(script_name, f"modeling.{script_name}")

        if dry_run:
            logger.info(f"Would run: python -m {module_path} {' '.join(args)}")
            results["scripts"][script_name] = "dry_run"
        else:
            success = self._run_python_module(module_path, args)
            results["scripts"][script_name] = "success" if success else "failed"
            if not success:
                results["status"] = "failed"

        return results

    def _run_prediction(self, dry_run: bool) -> Dict[str, Any]:
        """Run daily predictions."""
        results = {"status": "success", "scripts": {}}

        # Get the actual module paths from configuration
        script_modules = dict(self.stages["prediction"]["scripts"])

        # Prediction command - predict for today based on yesterday's features
        script_name = "predict_daily"
        args = ["--log-level", "INFO"]

        # Get the actual module path from configuration
        module_path = script_modules.get(script_name, f"modeling.{script_name}")

        if dry_run:
            logger.info(f"Would run: python -m {module_path} {' '.join(args)}")
            results["scripts"][script_name] = "dry_run"
        else:
            success = self._run_python_module(module_path, args)
            results["scripts"][script_name] = "success" if success else "failed"
            if not success:
                results["status"] = "failed"

        # Also run evaluation of previous predictions
        eval_args = ["--evaluate", "--log-level", "INFO"]
        if dry_run:
            logger.info(
                f"Would run: python -m {module_path} {' '.join(eval_args)}"
            )
            results["scripts"]["evaluate_predictions"] = "dry_run"
        else:
            success = self._run_python_module(module_path, eval_args)
            results["scripts"]["evaluate_predictions"] = (
                "success" if success else "failed"
            )

        return results

    def _run_python_module(self, module: str, args: List[str]) -> bool:
        """
        Run a Python module as a subprocess.

        Args:
            module: Module to run (e.g., 'data_ingestion.ingest_accounts')
            args: Command line arguments

        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = [sys.executable, "-m", module] + args
            logger.info(f"Running: {' '.join(cmd)}")

            # Run with environment variables
            env = os.environ.copy()

            # Run without capturing output - let it flow to console
            result = subprocess.run(
                cmd, cwd=self.src_dir, env=env
            )

            if result.returncode == 0:
                logger.info(f"Successfully executed {module}")
                return True
            else:
                logger.error(f"Failed to execute {module}")
                return False

        except Exception as e:
            logger.error(f"Exception running {module}: {str(e)}")
            return False

    def _is_stage_completed(self, stage_name: str) -> bool:
        """Check if a stage has completed successfully today."""
        query = """
        SELECT COUNT(*) as count
        FROM pipeline_execution_log
        WHERE pipeline_stage = %s
            AND execution_date = %s
            AND status = 'success'
        """

        result = self.db_manager.model_db.execute_query(
            query, (stage_name, date.today())
        )

        return result[0]["count"] > 0 if result else False


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(
        description="Run the daily profit model pipeline with metrics data fetching",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available stages:
  schema              - Ensure database schema compliance (migrates without data loss)
  ingestion          - Ingest only missing data from APIs and CSV files
  preprocessing      - Create staging snapshots and clean data
  validation         - Comprehensive data quality validation with Great Expectations
  feature_engineering - Engineer features and build training data
  training           - Train the LightGBM model
  prediction         - Generate daily predictions

Key differences from original pipeline:
  - Metrics ingestion only fetches missing data
  - Daily metrics are checked first, then only required alltime/hourly data is fetched
  - Trades ingestion will be optimized to skip existing records (coming soon)
  - Advanced data validation with Great Expectations
  - Overall much faster execution when data already exists

Examples:
  # Run the entire pipeline with date range (only fetches missing data)
  python run_pipeline.py --start-date 2025-06-05 --end-date 2025-06-10
  
  # Check what schema changes would be made without applying them
  python run_pipeline.py --stages schema --dry-run
  
  # Force recreate schema from scratch (DESTROYS ALL DATA!)
  python run_pipeline.py --stages schema --force-recreate-schema
  
  # Run only ingestion and preprocessing with date range
  python run_pipeline.py --stages ingestion preprocessing --start-date 2025-06-05 --end-date 2025-06-10
  
  # Run with data validation
  python run_pipeline.py --stages ingestion preprocessing validation --start-date 2025-06-05 --end-date 2025-06-10
  
  # Force full refresh (ignore existing data)
  python run_pipeline.py --stages ingestion --force-full-refresh
  
  # Run daily prediction only
  python run_pipeline.py --stages prediction
  
  # Disable Great Expectations (use basic validation)
  python run_pipeline.py --no-great-expectations
  
  # Dry run to see what would be executed
  python run_pipeline.py --start-date 2025-06-05 --end-date 2025-06-10 --dry-run
        """,
    )

    parser.add_argument(
        "--stages",
        nargs="+",
        choices=[
            "schema",
            "ingestion",
            "preprocessing",
            "validation",
            "feature_engineering",
            "training",
            "prediction",
        ],
        help="Specific stages to run (default: all stages)",
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for data processing (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for data processing (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-run of completed stages"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without running",
    )
    parser.add_argument(
        "--force-recreate-schema",
        action="store_true",
        help="Force drop and recreate schema (DESTROYS ALL DATA!)",
    )
    parser.add_argument(
        "--no-preserve-data",
        action="store_true",
        help="Don't preserve data during schema migrations (faster but destructive)",
    )
    parser.add_argument(
        "--force-full-refresh",
        action="store_true",
        help="Force full data refresh (ignore existing data)",
    )
    parser.add_argument(
        "--no-great-expectations",
        action="store_true",
        help="Disable Great Expectations validation (use basic validation)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file="pipeline_orchestration")

    # Run pipeline
    orchestrator = PipelineOrchestrator()
    try:
        results = orchestrator.run_pipeline(
            stages=args.stages,
            start_date=args.start_date,
            end_date=args.end_date,
            skip_completed=not args.force,
            dry_run=args.dry_run,
            force_recreate_schema=args.force_recreate_schema,
            preserve_data=not args.no_preserve_data,
            force_full_refresh=args.force_full_refresh,
            enable_great_expectations=not args.no_great_expectations,
        )

        # Exit with appropriate code
        failed_stages = [s for s, r in results.items() if r.get("status") == "failed"]
        if failed_stages:
            logger.error(f"Pipeline failed. Failed stages: {failed_stages}")
            sys.exit(1)
        else:
            logger.info("Pipeline completed successfully")

    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}")
        raise
    finally:
        # Clean up database connections
        close_db_connections()


if __name__ == "__main__":
    main()