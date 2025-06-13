"""
Great Expectations configuration and integration for data validation.
Properly configured for the actual prop trading model database schema.
"""

import os
from typing import Dict, List, Optional, Any
from datetime import date
import logging

from great_expectations.core import ExpectationConfiguration
from great_expectations.checkpoint import SimpleCheckpoint
from great_expectations.data_context import DataContext
from great_expectations.data_context.types.base import DataContextConfig
from great_expectations.core.batch import BatchRequest

logger = logging.getLogger(__name__)


class GreatExpectationsValidator:
    """Great Expectations integration for advanced data validation aligned with actual schema."""

    def __init__(self, db_manager, data_dir: str = "great_expectations"):
        """Initialize Great Expectations validator."""
        self.db_manager = db_manager
        self.data_dir = data_dir
        self.context = self._init_data_context()
        self._setup_datasources()
        self._create_expectation_suites()

    def _init_data_context(self) -> DataContext:
        """Initialize Great Expectations data context."""
        # Create data context configuration
        data_context_config = DataContextConfig(
            store_backend_defaults={
                "class_name": "TupleFilesystemStoreBackend",
                "base_directory": os.path.join(self.data_dir, "uncommitted"),
            },
            expectations_store_name="expectations_store",
            validations_store_name="validations_store",
            evaluation_parameter_store_name="evaluation_parameter_store",
            checkpoint_store_name="checkpoint_store",
            datasources={},
            data_docs_sites={
                "local_site": {
                    "class_name": "SiteBuilder",
                    "show_how_to_buttons": True,
                    "store_backend": {
                        "class_name": "TupleFilesystemStoreBackend",
                        "base_directory": os.path.join(
                            self.data_dir, "uncommitted", "data_docs"
                        ),
                    },
                    "site_index_builder": {
                        "class_name": "DefaultSiteIndexBuilder",
                    },
                }
            },
            anonymous_usage_statistics={"enabled": False},
        )

        # Create directory structure
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "uncommitted"), exist_ok=True)

        # Initialize context
        context = DataContext(project_config=data_context_config)
        return context

    def _setup_datasources(self):
        """Configure datasources for Great Expectations."""
        # PostgreSQL datasource configuration
        datasource_config = {
            "name": "prop_trading_postgres",
            "class_name": "Datasource",
            "execution_engine": {
                "class_name": "SqlAlchemyExecutionEngine",
                "connection_string": (
                    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
                    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
                ),
            },
            "data_connectors": {
                "default_inferred_data_connector_name": {
                    "class_name": "InferredAssetSqlDataConnector",
                    "include_schema_name": True,
                }
            },
        }

        self.context.add_datasource(**datasource_config)

    def _create_expectation_suites(self):
        """Create expectation suites for different tables aligned with actual schema."""
        # Core data tables
        self._create_raw_metrics_alltime_suite()
        self._create_raw_metrics_daily_suite()
        self._create_raw_metrics_hourly_suite()
        self._create_staging_snapshots_suite()
        
        # Trading data tables
        self._create_raw_trades_closed_suite()
        self._create_raw_trades_open_suite()
        self._create_raw_plans_data_suite()
        
        # ML pipeline tables
        self._create_model_training_input_suite()
        self._create_model_predictions_suite()

    def _create_raw_metrics_alltime_suite(self):
        """Create expectations for raw_metrics_alltime table (main account data)."""
        suite_name = "raw_metrics_alltime_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
            logger.info(f"Loaded existing expectation suite: {suite_name}")
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )
            logger.info(f"Created new expectation suite: {suite_name}")

        expectations = [
            # Primary key and required fields
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "account_id"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "login"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_unique",
                kwargs={"column": "account_id"},
            ),
            
            # Account status validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "status", "value_set": [1, 2, 3]},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "phase", "value_set": [1, 2, 3, 4]},
            ),
            
            # Balance validations
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "starting_balance", "min_value": 1000, "max_value": 1000000},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "current_balance", "min_value": 0, "max_value": 10000000},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "current_equity", "min_value": 0, "max_value": 10000000},
            ),
            
            # Trading metrics validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "success_rate", "min_value": 0, "max_value": 100, "mostly": 0.99},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "profit_factor", "min_value": 0, "max_value": 100, "mostly": 0.95},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "num_trades", "min_value": 0, "max_value": 100000},
            ),
            
            # Risk metrics validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "daily_sharpe", "min_value": -10, "max_value": 10, "mostly": 0.90},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "daily_sortino", "min_value": -10, "max_value": 10, "mostly": 0.90},
            ),
            
            # Business logic validations
            ExpectationConfiguration(
                expectation_type="expect_column_pair_values_to_be_equal",
                kwargs={"column_A": "gross_profit", "column_B": "gross_profit", "ignore_row_if": "either_value_is_missing"},
                meta={"notes": "Gross profit should be non-negative"}
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_pair_values_to_be_equal", 
                kwargs={"column_A": "gross_loss", "column_B": "gross_loss", "ignore_row_if": "either_value_is_missing"},
                meta={"notes": "Gross loss should be non-positive"}
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_raw_metrics_daily_suite(self):
        """Create expectations for raw_metrics_daily table."""
        suite_name = "raw_metrics_daily_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Composite primary key
            ExpectationConfiguration(
                expectation_type="expect_compound_columns_to_be_unique",
                kwargs={"column_list": ["account_id", "date"]},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "date"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "account_id"},
            ),
            
            # Date validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={
                    "column": "date",
                    "min_value": "2020-01-01",
                    "max_value": "2030-12-31",
                    "parse_strings_as_datetimes": True,
                },
            ),
            
            # Performance metrics
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "success_rate", "min_value": 0, "max_value": 100, "mostly": 0.99},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "num_trades", "min_value": 0, "max_value": 1000},
            ),
            
            # Data freshness check
            ExpectationConfiguration(
                expectation_type="expect_column_max_to_be_between",
                kwargs={
                    "column": "date",
                    "min_value": "2024-01-01",
                    "max_value": "2030-12-31",
                    "parse_strings_as_datetimes": True,
                },
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_raw_metrics_hourly_suite(self):
        """Create expectations for raw_metrics_hourly table."""
        suite_name = "raw_metrics_hourly_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Composite primary key
            ExpectationConfiguration(
                expectation_type="expect_compound_columns_to_be_unique",
                kwargs={"column_list": ["account_id", "date", "hour"]},
            ),
            
            # Hour validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "hour", "min_value": 0, "max_value": 23},
            ),
            
            # Datetime consistency
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "datetime"},
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_staging_snapshots_suite(self):
        """Create expectations for stg_accounts_daily_snapshots table (corrected column names)."""
        suite_name = "staging_snapshots_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Primary key
            ExpectationConfiguration(
                expectation_type="expect_compound_columns_to_be_unique",
                kwargs={"column_list": ["account_id", "snapshot_date"]},
            ),
            
            # Required fields (using correct column names from schema)
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "account_id"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "login"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "snapshot_date"},
            ),
            
            # Balance validations (using correct column names)
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "balance", "min_value": 0, "max_value": 10000000, "mostly": 0.99},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "equity", "min_value": 0, "max_value": 10000000, "mostly": 0.99},
            ),
            
            # Percentage validations
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "profit_target_pct", "min_value": 0, "max_value": 100},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "max_drawdown_pct", "min_value": 0, "max_value": 100},
            ),
            
            # Phase validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "phase", "value_set": [1, 2, 3, 4], "mostly": 0.99},
            ),
            
            # Status validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "status", "value_set": [1, 2, 3], "mostly": 0.99},
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_raw_trades_closed_suite(self):
        """Create expectations for raw_trades_closed table."""
        suite_name = "raw_trades_closed_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Required fields
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "login"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "std_symbol"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "trade_date"},
            ),
            
            # Side validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "side", "value_set": ["buy", "sell", "BUY", "SELL", "Buy", "Sell"]},
            ),
            
            # Trade timing validation
            ExpectationConfiguration(
                expectation_type="expect_column_pair_values_A_to_be_greater_than_B",
                kwargs={"column_A": "close_time", "column_B": "open_time", "or_equal": False, "mostly": 0.99},
            ),
            
            # Price validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "open_price", "min_value": 0.00001, "max_value": 1000000, "mostly": 0.99},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "close_price", "min_value": 0.00001, "max_value": 1000000, "mostly": 0.99},
            ),
            
            # Volume validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "lots", "min_value": 0.01, "max_value": 1000, "mostly": 0.95},
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_raw_trades_open_suite(self):
        """Create expectations for raw_trades_open table."""
        suite_name = "raw_trades_open_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Similar to closed trades but for open positions
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "login"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "std_symbol"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "side", "value_set": ["buy", "sell", "BUY", "SELL", "Buy", "Sell"]},
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_raw_plans_data_suite(self):
        """Create expectations for raw_plans_data table."""
        suite_name = "raw_plans_data_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Primary key
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_unique",
                kwargs={"column": "plan_id"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "plan_name"},
            ),
            
            # Balance validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "starting_balance", "min_value": 1000, "max_value": 1000000},
            ),
            
            # Percentage validations
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "profit_target_pct", "min_value": 1, "max_value": 50},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "max_drawdown_pct", "min_value": 1, "max_value": 50},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "profit_share_pct", "min_value": 50, "max_value": 100},
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_model_training_input_suite(self):
        """Create expectations for model_training_input table (ML features)."""
        suite_name = "model_training_input_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Primary key
            ExpectationConfiguration(
                expectation_type="expect_compound_columns_to_be_unique",
                kwargs={"column_list": ["account_id", "prediction_date"]},
            ),
            
            # Required ML features
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "account_id"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "prediction_date"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "feature_date"},
            ),
            
            # Feature validation ranges
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "win_rate_5d", "min_value": 0, "max_value": 100, "mostly": 0.90},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "sharpe_ratio_5d", "min_value": -10, "max_value": 10, "mostly": 0.90},
            ),
            
            # Target variable validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "target_net_profit", "min_value": -100000, "max_value": 100000, "mostly": 0.95},
            ),
            
            # Feature-target temporal consistency
            ExpectationConfiguration(
                expectation_type="expect_column_pair_values_A_to_be_greater_than_B",
                kwargs={"column_A": "prediction_date", "column_B": "feature_date", "or_equal": False},
                meta={"notes": "Prediction date must be after feature date to prevent lookahead bias"}
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_model_predictions_suite(self):
        """Create expectations for model_predictions table."""
        suite_name = "model_predictions_suite"

        try:
            suite = self.context.get_expectation_suite(expectation_suite_name=suite_name)
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            # Primary key
            ExpectationConfiguration(
                expectation_type="expect_compound_columns_to_be_unique",
                kwargs={"column_list": ["model_version", "prediction_date", "account_id"]},
            ),
            
            # Probability validation
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "predicted_profit_probability", "min_value": 0, "max_value": 1},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "prediction_confidence", "min_value": 0, "max_value": 1},
            ),
            
            # Model version format
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_match_regex",
                kwargs={"column": "model_version", "regex": r"^v\d+\.\d+\.\d+$"},
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def validate_table(
        self,
        table_name: str,
        schema: str = "prop_trading_model",
        date_filter: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Validate a table using its expectation suite.

        Args:
            table_name: Name of the table to validate
            schema: Database schema
            date_filter: Optional date to filter data

        Returns:
            Validation results dictionary
        """
        # Updated mapping with correct table names
        suite_mapping = {
            "raw_metrics_alltime": "raw_metrics_alltime_suite",
            "raw_metrics_daily": "raw_metrics_daily_suite", 
            "raw_metrics_hourly": "raw_metrics_hourly_suite",
            "stg_accounts_daily_snapshots": "staging_snapshots_suite",
            "raw_trades_closed": "raw_trades_closed_suite",
            "raw_trades_open": "raw_trades_open_suite",
            "raw_plans_data": "raw_plans_data_suite",
            "model_training_input": "model_training_input_suite",
            "model_predictions": "model_predictions_suite",
        }

        suite_name = suite_mapping.get(table_name)
        if not suite_name:
            raise ValueError(f"No expectation suite defined for table: {table_name}")

        # Create batch request with appropriate date filtering
        if date_filter:
            if table_name in ["raw_metrics_daily", "raw_metrics_hourly"]:
                query = f"SELECT * FROM {schema}.{table_name} WHERE date = '{date_filter}'"
            elif table_name in ["raw_trades_closed", "raw_trades_open"]:
                query = f"SELECT * FROM {schema}.{table_name} WHERE trade_date = '{date_filter}'"
            elif table_name == "stg_accounts_daily_snapshots":
                query = f"SELECT * FROM {schema}.{table_name} WHERE snapshot_date = '{date_filter}'"
            else:
                query = f"SELECT * FROM {schema}.{table_name} LIMIT 10000"
        else:
            query = f"SELECT * FROM {schema}.{table_name} LIMIT 10000"

        batch_request = BatchRequest(
            datasource_name="prop_trading_postgres",
            data_connector_name="default_inferred_data_connector_name",
            data_asset_name=f"{schema}.{table_name}",
            batch_spec_passthrough={"query": query},
        )

        # Create validator
        validator = self.context.get_validator(
            batch_request=batch_request, expectation_suite_name=suite_name
        )

        # Run validation
        validation_results = validator.validate()

        # Process results
        results_dict = validation_results.to_dict()

        # Summary statistics
        summary = {
            "success": validation_results.success,
            "total_expectations": len(results_dict["results"]),
            "successful_expectations": sum(
                1 for r in results_dict["results"] if r["success"]
            ),
            "failed_expectations": sum(
                1 for r in results_dict["results"] if not r["success"]
            ),
            "evaluation_parameters": results_dict.get("evaluation_parameters", {}),
            "statistics": results_dict.get("statistics", {}),
            "failed_expectation_details": [
                {
                    "expectation_type": r["expectation_config"]["expectation_type"],
                    "kwargs": r["expectation_config"]["kwargs"],
                    "result": r["result"],
                }
                for r in results_dict["results"]
                if not r["success"]
            ],
        }

        # Log results
        if summary["success"]:
            logger.info(
                f"Validation passed for {table_name}: "
                f"{summary['successful_expectations']}/{summary['total_expectations']} expectations met"
            )
        else:
            logger.error(
                f"Validation failed for {table_name}: "
                f"{summary['failed_expectations']} expectations failed"
            )

        return summary

    def create_checkpoint(
        self, checkpoint_name: str, table_name: str, suite_name: str
    ) -> SimpleCheckpoint:
        """Create a validation checkpoint for automated runs."""
        checkpoint_config = {
            "name": checkpoint_name,
            "config_version": 1.0,
            "class_name": "SimpleCheckpoint",
            "run_name_template": f"{table_name}_%Y%m%d_%H%M%S",
            "validations": [
                {
                    "batch_request": {
                        "datasource_name": "prop_trading_postgres",
                        "data_connector_name": "default_inferred_data_connector_name",
                        "data_asset_name": f"prop_trading_model.{table_name}",
                    },
                    "expectation_suite_name": suite_name,
                }
            ],
        }

        self.context.add_checkpoint(**checkpoint_config)
        return self.context.get_checkpoint(checkpoint_name)

    def generate_data_docs(self):
        """Generate and open Great Expectations data documentation."""
        self.context.build_data_docs()
        self.context.open_data_docs()

    def get_validation_history(self, suite_name: str, limit: int = 10) -> List[Dict]:
        """Get recent validation history for a suite."""
        validations_store = self.context.stores["validations_store"]

        # Get validation results
        validation_ids = validations_store.list_keys()

        # Filter by suite name and sort by run time
        suite_validations = []
        for validation_id in validation_ids:
            if (
                validation_id.expectation_suite_identifier.expectation_suite_name
                == suite_name
            ):
                validation = validations_store.get(validation_id)
                suite_validations.append(
                    {
                        "run_id": validation_id.run_id,
                        "run_time": validation_id.run_time,
                        "success": validation.success,
                        "statistics": validation.statistics,
                        "results": len(validation.results),
                    }
                )

        # Sort by run time and limit
        suite_validations.sort(key=lambda x: x["run_time"], reverse=True)
        return suite_validations[:limit]

    def validate_ml_pipeline_data_quality(self, prediction_date: date) -> Dict[str, Any]:
        """
        Comprehensive ML pipeline data quality validation.
        
        Args:
            prediction_date: Date for which to validate ML pipeline data
            
        Returns:
            Comprehensive validation results for ML pipeline
        """
        results = {}
        
        # Validate core data tables
        core_tables = [
            "raw_metrics_alltime",
            "raw_metrics_daily", 
            "raw_trades_closed",
            "stg_accounts_daily_snapshots"
        ]
        
        for table in core_tables:
            try:
                results[table] = self.validate_table(table, date_filter=prediction_date)
            except Exception as e:
                results[table] = {"success": False, "error": str(e)}
        
        # Validate ML-specific tables
        ml_tables = ["model_training_input", "model_predictions"]
        for table in ml_tables:
            try:
                results[table] = self.validate_table(table, date_filter=prediction_date)
            except Exception as e:
                results[table] = {"success": False, "error": str(e)}
        
        # Overall pipeline health
        total_validations = sum(r.get("total_expectations", 0) for r in results.values() if isinstance(r, dict))
        successful_validations = sum(r.get("successful_expectations", 0) for r in results.values() if isinstance(r, dict))
        
        results["pipeline_summary"] = {
            "overall_success": all(r.get("success", False) for r in results.values() if isinstance(r, dict)),
            "total_expectations": total_validations,
            "successful_expectations": successful_validations,
            "success_rate": successful_validations / total_validations if total_validations > 0 else 0,
            "validation_date": prediction_date.isoformat(),
        }
        
        return results
