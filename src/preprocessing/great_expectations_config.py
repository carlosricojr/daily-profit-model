"""
Great Expectations configuration and integration for data validation.
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
    """Great Expectations integration for advanced data validation."""

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
        """Create expectation suites for different tables."""
        # Create suite for staging snapshots
        self._create_staging_snapshot_suite()

        # Create suite for raw accounts
        self._create_raw_accounts_suite()

        # Create suite for daily metrics
        self._create_daily_metrics_suite()

    def _create_staging_snapshot_suite(self):
        """Create expectations for staging snapshots table."""
        suite_name = "staging_snapshots_suite"

        try:
            suite = self.context.get_expectation_suite(
                expectation_suite_name=suite_name
            )
            logger.info(f"Loaded existing expectation suite: {suite_name}")
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )
            logger.info(f"Created new expectation suite: {suite_name}")

        # Define expectations
        expectations = [
            # Completeness expectations
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
                kwargs={"column": "date"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "starting_balance"},
            ),
            # Validity expectations
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={
                    "column": "current_balance",
                    "min_value": 0,
                    "max_value": 10000000,
                    "mostly": 0.99,
                },
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={
                    "column": "profit_target_pct",
                    "min_value": 0,
                    "max_value": 100,
                },
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={"column": "max_drawdown_pct", "min_value": 0, "max_value": 100},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={
                    "column": "phase",
                    "value_set": ["Funded", "Challenge", "Verification"],
                    "mostly": 0.99,
                },
            ),
            # Uniqueness expectations
            ExpectationConfiguration(
                expectation_type="expect_compound_columns_to_be_unique",
                kwargs={"column_list": ["account_id", "date"]},
            ),
            # Statistical expectations
            ExpectationConfiguration(
                expectation_type="expect_column_mean_to_be_between",
                kwargs={
                    "column": "current_balance",
                    "min_value": 10000,
                    "max_value": 100000,
                },
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_stdev_to_be_between",
                kwargs={
                    "column": "current_balance",
                    "min_value": 1000,
                    "max_value": 50000,
                },
            ),
            # Distribution expectations
            ExpectationConfiguration(
                expectation_type="expect_column_quantile_values_to_be_between",
                kwargs={
                    "column": "current_balance",
                    "quantile_ranges": {
                        "quantiles": [0.05, 0.25, 0.5, 0.75, 0.95],
                        "value_ranges": [
                            [1000, 10000],
                            [5000, 25000],
                            [10000, 50000],
                            [20000, 75000],
                            [30000, 150000],
                        ],
                    },
                },
            ),
            # Relationship expectations
            ExpectationConfiguration(
                expectation_type="expect_column_pair_values_A_to_be_greater_than_B",
                kwargs={
                    "column_A": "days_since_first_trade",
                    "column_B": "active_trading_days_count",
                    "or_equal": True,
                },
            ),
        ]

        # Add expectations to suite
        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_raw_accounts_suite(self):
        """Create expectations for raw accounts table."""
        suite_name = "raw_accounts_suite"

        try:
            suite = self.context.get_expectation_suite(
                expectation_suite_name=suite_name
            )
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "account_id"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "breached", "value_set": [0, 1]},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_in_set",
                kwargs={"column": "is_upgraded", "value_set": [0, 1]},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_match_regex",
                kwargs={"column": "account_id", "regex": "^[A-Za-z0-9_-]+$"},
            ),
        ]

        for expectation in expectations:
            suite.add_expectation(expectation_configuration=expectation)

        self.context.save_expectation_suite(expectation_suite=suite)

    def _create_daily_metrics_suite(self):
        """Create expectations for daily metrics table."""
        suite_name = "daily_metrics_suite"

        try:
            suite = self.context.get_expectation_suite(
                expectation_suite_name=suite_name
            )
        except Exception:
            suite = self.context.create_expectation_suite(
                expectation_suite_name=suite_name, overwrite_existing=True
            )

        expectations = [
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "date"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_not_be_null",
                kwargs={"column": "account_id"},
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={
                    "column": "win_rate",
                    "min_value": 0,
                    "max_value": 100,
                    "mostly": 1.0,
                },
            ),
            ExpectationConfiguration(
                expectation_type="expect_column_sum_to_be_between",
                kwargs={"column": "total_trades", "min_value": 0, "max_value": 1000000},
            ),
            # Custom expectation for trade consistency
            ExpectationConfiguration(
                expectation_type="expect_column_values_to_be_between",
                kwargs={
                    "column": "profit_factor",
                    "min_value": 0,
                    "max_value": 100,
                    "mostly": 0.95,
                },
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
        # Map table names to suite names
        suite_mapping = {
            "stg_accounts_daily_snapshots": "staging_snapshots_suite",
            "raw_accounts_data": "raw_accounts_suite",
            "raw_metrics_daily": "daily_metrics_suite",
        }

        suite_name = suite_mapping.get(table_name)
        if not suite_name:
            raise ValueError(f"No expectation suite defined for table: {table_name}")

        # Create batch request
        if date_filter:
            query = f"SELECT * FROM {schema}.{table_name} WHERE date = '{date_filter}'"
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
