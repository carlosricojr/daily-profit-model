"""
Data quality validation wrapper for pipeline orchestration.
Provides a simple interface to run Great Expectations validation.
"""

import sys
import logging
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.database import get_db_manager, close_db_connections
from utils.logging_config import setup_logging
from preprocessing.great_expectations_config import GreatExpectationsValidator

logger = logging.getLogger(__name__)


def run_data_quality_validation(
    validation_date: date,
    enable_great_expectations: bool = True,
    log_level: str = "INFO"
) -> bool:
    """
    Run comprehensive data quality validation.
    
    Args:
        validation_date: Date to validate data for
        enable_great_expectations: Whether to use Great Expectations
        log_level: Logging level
        
    Returns:
        True if validation passes, False otherwise
    """
    setup_logging(log_level=log_level, log_file="data_quality_validation")
    
    logger.info(f"Starting data quality validation for {validation_date}")
    logger.info(f"Great Expectations enabled: {enable_great_expectations}")
    
    db_manager = get_db_manager()
    
    try:
        if enable_great_expectations:
            logger.info("Running comprehensive data validation with Great Expectations")
            
            # Initialize Great Expectations validator
            ge_validator = GreatExpectationsValidator(db_manager)
            
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
                return False
            elif warning_tables:
                logger.warning(f"Data validation warnings: {warning_tables}")
                # Continue execution for warnings
            else:
                logger.info("All data validation checks passed successfully")
            
            return True
            
        else:
            # Fallback to basic validation
            logger.info("Running basic data validation (Great Expectations disabled)")
            return run_basic_data_validation(db_manager, validation_date)
            
    except Exception as e:
        logger.error(f"Data validation failed with exception: {str(e)}")
        logger.warning("Falling back to basic data validation")
        
        # Fallback to basic validation
        try:
            return run_basic_data_validation(db_manager, validation_date)
        except Exception as fallback_error:
            logger.error(f"Basic data validation also failed: {str(fallback_error)}")
            return False
    
    finally:
        close_db_connections()


def run_basic_data_validation(db_manager, validation_date: date) -> bool:
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
                result = db_manager.model_db.execute_query(
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


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(
        description="Run data quality validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--validation-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today() - timedelta(days=1),
        help="Date to validate data for (YYYY-MM-DD, default: yesterday)",
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
    
    # Run validation
    success = run_data_quality_validation(
        validation_date=args.validation_date,
        enable_great_expectations=not args.no_great_expectations,
        log_level=args.log_level
    )
    
    if success:
        logger.info("Data quality validation completed successfully")
        sys.exit(0)
    else:
        logger.error("Data quality validation failed")
        sys.exit(1)


if __name__ == "__main__":
    main() 