"""
Enhanced plans ingester with checkpoint support, validation, and metrics tracking.
Handles plan data ingestion from CSV files with production-ready features.
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path
import hashlib
import pandas as pd

# Ensure we can import from parent directories
try:
    from .base_ingester import BaseIngester
    from ..utils.logging_config import get_logger
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_ingestion.base_ingester import BaseIngester
    from utils.logging_config import get_logger

logger = get_logger(__name__)


class PlansIngester(BaseIngester):
    """Enhanced plans ingester for CSV data with production-ready features."""

    # Column mapping for flexible CSV formats
    COLUMN_MAPPING = {
        # Plan identification
        "plan_id": ["plan_id", "plan id", "planid", "plan_code", "plan code", "planId"],
        "plan_name": ["plan_name", "plan name", "planname", "name", "description"],
        "plan_type": ["plan_type", "plan type", "type", "plantype"],
        # Financial parameters
        "starting_balance": [
            "starting_balance",
            "starting balance",
            "startingbalance",
            "initial_balance",
            "balance",
            "startingBalance",
        ],
        "profit_target": ["profit_target", "profit target", "profittarget", "target", "profitTarget"],
        "profit_target_pct": [
            "profit_target_pct",
            "profit target %",
            "profit_target_%",
            "profit_target_percent",
            "profitTargetPct",
        ],
        "max_drawdown": ["max_drawdown", "max drawdown", "maxdrawdown", "maxDrawdown"],
        "max_drawdown_pct": [
            "max_drawdown_pct",
            "max drawdown %",
            "max_drawdown_%",
            "max_drawdown_percent",
            "maxDrawdownPct",
            "maxTrailingDrawdownPct",
        ],
        "max_daily_drawdown": [
            "max_daily_drawdown",
            "max daily drawdown",
            "maxdailydrawdown",
            "daily_drawdown",
            "maxDailyDrawdown",
        ],
        "max_daily_drawdown_pct": [
            "max_daily_drawdown_pct",
            "max daily drawdown %",
            "max_daily_drawdown_%",
            "daily_drawdown_pct",
            "maxDailyDrawdownPct",
            "dailyLossLimitPct",
        ],
        # Trading parameters
        "max_leverage": ["max_leverage", "max leverage", "maxleverage", "leverage"],
        "is_drawdown_relative": [
            "is_drawdown_relative",
            "is drawdown relative",
            "drawdown_relative",
            "relative_drawdown",
            "isDrawdownRelative",
            "makeDrawdownStatic",
        ],
        "min_trading_days": [
            "min_trading_days",
            "min trading days",
            "mintradingdays",
            "minimum_days",
            "minTradingDays",
            "minimumRequiredActiveTradingDays",
        ],
        "max_trading_days": [
            "max_trading_days",
            "max trading days",
            "maxtradingdays",
            "maximum_days",
            "maxTradingDays",
            "maximumTime",
        ],
        "profit_share_pct": [
            "profit_split_pct",
            "profit split %",
            "profit_split_%",
            "profit_split",
            "split",
            "profitSplitPct",
            "profitSharePct",
        ],
        # New columns
        "liquidate_friday": [
            "liquidate_friday",
            "liquidateFriday",
            "liquidate friday",
            "liquidatefriday",
        ],
        "inactivity_period": [
            "inactivity_period",
            "inactivityPeriod",
            "inactivity period",
            "inactivityperiod",
        ],
        "daily_drawdown_by_balance_equity": [
            "daily_drawdown_by_balance_equity",
            "dailyDrawdownByBalanceEquity",
            "daily drawdown by balance equity",
            "dailydrawdownbybalanceequity",
        ],
        "enable_consistency": [
            "enable_consistency",
            "enableConsistency",
            "enable consistency",
            "enableconsistency",
        ],
    }

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        enable_validation: bool = True,
        enable_deduplication: bool = True,
    ):
        """Initialize the enhanced plans ingester."""
        super().__init__(
            ingestion_type="plans",
            table_name="raw_plans_data",
            checkpoint_dir=checkpoint_dir,
            enable_validation=enable_validation,
            enable_deduplication=enable_deduplication,
        )

        self.source_endpoint = "csv_files"
        self.metrics.files_processed = 0

    def _normalize_column_name(self, col: str) -> str:
        """Normalize column name for matching."""
        return col.lower().strip().replace("_", " ")

    def _map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map CSV columns to expected column names."""
        mapped_df = df.copy()

        for target_col, possible_names in self.COLUMN_MAPPING.items():
            # Normalize possible names
            normalized_possible = [
                self._normalize_column_name(name) for name in possible_names
            ]

            # Find matching column in dataframe
            for col in df.columns:
                normalized_col = self._normalize_column_name(col)
                if normalized_col in normalized_possible:
                    if col != target_col:
                        mapped_df.rename(columns={col: target_col}, inplace=True)
                    break

        return mapped_df

    def _convert_boolean(self, value: Any) -> Optional[bool]:
        """Convert various boolean representations to bool."""
        if value is None or pd.isna(value):
            return None

        if isinstance(value, bool):
            return value
        
        # Handle numeric values
        if isinstance(value, (int, float)):
            return bool(value)

        str_val = str(value).lower().strip()
        if str_val in ["true", "yes", "1", "t", "y"]:
            return True
        elif str_val in ["false", "no", "0", "f", "n", ""]:
            return False

        return None

    def _convert_percentage(self, value: Any) -> Optional[float]:
        """Convert percentage string to float."""
        if value is None or pd.isna(value):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        # Handle string percentages
        str_val = str(value).strip()
        if str_val.endswith("%"):
            str_val = str_val[:-1]

        try:
            return float(str_val)
        except (ValueError, TypeError):
            return None

    def _validate_record(self, record: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a plan record."""
        errors = []

        # Check required fields
        plan_id = record.get("plan_id")
        if (
            plan_id is None
            or (isinstance(plan_id, str) and plan_id.strip() == "")
            or pd.isna(plan_id)
        ):
            errors.append("missing_plan_id")

        # Validate numeric fields
        starting_balance_raw = record.get("starting_balance")
        starting_balance = self._safe_float(starting_balance_raw)

        # Check if conversion failed for non-empty values
        if (
            starting_balance_raw is not None
            and starting_balance_raw != ""
            and pd.notna(starting_balance_raw)
        ):
            if starting_balance is None:
                errors.append("invalid_starting_balance")
            elif starting_balance < 0:
                errors.append("negative_starting_balance")

        # Validate percentage fields (0-100 range)
        percentage_fields = [
            "profit_target_pct",
            "max_drawdown_pct",
            "max_daily_drawdown_pct",
            "profit_share_pct",
        ]

        for field in percentage_fields:
            value = self._safe_float(record.get(field))
            if value is not None:
                if value < 0 or value > 100:
                    errors.append(f"{field}_out_of_range")
                # Check constraints that require > 0 for drawdown percentages
                elif field in ["max_drawdown_pct", "max_daily_drawdown_pct"] and value == 0:
                    errors.append(f"{field}_cannot_be_zero")

        # Validate leverage
        max_leverage = self._safe_int(record.get("max_leverage"))
        if max_leverage is not None and max_leverage <= 0:
            errors.append("invalid_leverage")

        # Validate trading days
        min_days = self._safe_int(record.get("min_trading_days"))
        max_days = self._safe_int(record.get("max_trading_days"))

        if min_days is not None and min_days < 0:
            errors.append("negative_min_trading_days")
        if max_days is not None and max_days < 0:
            errors.append("negative_max_trading_days")

        if min_days is not None and max_days is not None and min_days > max_days:
            errors.append("min_days_exceeds_max_days")

        return len(errors) == 0, errors

    def _get_record_key(self, record: Dict[str, Any]) -> Optional[str]:
        """Generate unique key for deduplication."""
        plan_id = str(record.get("plan_id", ""))
        if not plan_id:
            return None

        # Create hash of plan ID
        return hashlib.md5(plan_id.encode()).hexdigest()

    def _transform_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Transform CSV plan record to database format."""
        # Convert percentages
        for field in [
            "profit_target_pct",
            "max_drawdown_pct",
            "max_daily_drawdown_pct",
            "profit_share_pct",
        ]:
            if field in record:
                record[field] = self._convert_percentage(record[field])

        # Get base values
        starting_balance = self._safe_float(record.get("starting_balance"))
        profit_target_pct = self._convert_percentage(record.get("profit_target_pct"))
        max_drawdown_pct = self._convert_percentage(record.get("max_drawdown_pct"))
        max_daily_drawdown_pct = self._convert_percentage(record.get("max_daily_drawdown_pct"))
        
        # Calculate absolute values from percentages if they're NULL
        profit_target = self._safe_float(record.get("profit_target"))
        if profit_target is None and starting_balance is not None and profit_target_pct is not None:
            profit_target = starting_balance * (profit_target_pct / 100)
            
        max_drawdown = self._safe_float(record.get("max_drawdown"))
        if max_drawdown is None and starting_balance is not None and max_drawdown_pct is not None:
            max_drawdown = starting_balance * (max_drawdown_pct / 100)
            
        max_daily_drawdown = self._safe_float(record.get("max_daily_drawdown"))
        if max_daily_drawdown is None and starting_balance is not None and max_daily_drawdown_pct is not None:
            max_daily_drawdown = starting_balance * (max_daily_drawdown_pct / 100)

        # Handle is_drawdown_relative logic
        # If we have makeDrawdownStatic field, use NOT logic
        # makeDrawdownStatic = True means drawdown is static (not relative)
        # makeDrawdownStatic = False means drawdown is relative
        is_drawdown_relative = None
        if "makeDrawdownStatic" in record or "makeDrawdownStatic" in str(record.get("is_drawdown_relative", "")):
            make_drawdown_static = self._convert_boolean(record.get("makeDrawdownStatic")) or self._convert_boolean(record.get("is_drawdown_relative"))
            if make_drawdown_static is not None:
                is_drawdown_relative = not make_drawdown_static
        else:
            # Normal conversion if it's already is_drawdown_relative
            is_drawdown_relative = self._convert_boolean(record.get("is_drawdown_relative"))

        return {
            "plan_id": record.get("plan_id"),
            "plan_name": record.get("plan_name"),
            "plan_type": record.get("plan_type"),
            "starting_balance": starting_balance,
            "profit_target": profit_target,
            "profit_target_pct": profit_target_pct,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "max_daily_drawdown": max_daily_drawdown,
            "max_daily_drawdown_pct": max_daily_drawdown_pct,
            "max_leverage": self._safe_int(record.get("max_leverage")),
            "is_drawdown_relative": is_drawdown_relative,
            "min_trading_days": self._safe_int(record.get("min_trading_days")),
            "max_trading_days": self._safe_int(record.get("max_trading_days")),
            "profit_share_pct": self._convert_percentage(record.get("profit_share_pct")),
            "liquidate_friday": self._convert_boolean(record.get("liquidate_friday")),
            "inactivity_period": self._safe_int(record.get("inactivity_period")),
            "daily_drawdown_by_balance_equity": self._convert_boolean(record.get("daily_drawdown_by_balance_equity")),
            "enable_consistency": self._convert_boolean(record.get("enable_consistency")),
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": record.get("_source_file", "unknown"),
        }

    def _get_conflict_clause(self, table_name: str) -> str:
        """Get ON CONFLICT clause for plans table."""
        return "ON CONFLICT (plan_id, ingestion_timestamp) DO NOTHING"

    def _process_csv_file(
        self, file_path: Path, checkpoint: Optional[Dict[str, Any]] = None
    ) -> int:
        """Process a single CSV file."""
        logger.info(f"Processing CSV file: {file_path}")
        records_processed = 0

        try:
            # Read CSV file
            df = pd.read_csv(file_path)

            # Map columns
            df = self._map_columns(df)

            # Add source file to records
            df["_source_file"] = file_path.name

            # Determine starting row from checkpoint
            start_row = 0
            if checkpoint and checkpoint.get("last_processed_file") == file_path.name:
                start_row = checkpoint.get("last_processed_row", 0) + 1
                logger.info(f"Resuming from row {start_row}")

            # Convert to records
            records = df.iloc[start_row:].to_dict("records")

            batch_data = []
            batch_size = 1000

            for idx, record in enumerate(records):
                actual_row = start_row + idx
                self.metrics.total_records += 1

                # Validate if enabled
                if self.enable_validation:
                    is_valid, errors = self._validate_record(record)
                    if not is_valid:
                        self.metrics.invalid_records += 1
                        for error in errors:
                            self.metrics.validation_errors[error] += 1
                        continue

                # Check for duplicates if enabled
                if self.enable_deduplication:
                    key = self._get_record_key(record)
                    if key and key in self.seen_records:
                        self.metrics.duplicate_records += 1
                        continue
                    if key:
                        self.seen_records.add(key)

                # Transform and add to batch
                transformed = self._transform_record(record)
                batch_data.append(transformed)
                self.metrics.new_records += 1
                records_processed += 1

                # Insert batch when it reaches the size limit
                if len(batch_data) >= batch_size:
                    self._insert_batch(batch_data)
                    batch_data = []

                    # Save checkpoint periodically
                    if records_processed % 5000 == 0:
                        self.checkpoint_manager.save_checkpoint(
                            {
                                "last_processed_file": file_path.name,
                                "last_processed_row": actual_row,
                                "total_records": self.metrics.total_records,
                                "metrics": self.metrics.to_dict(),
                            }
                        )

            # Insert remaining records
            if batch_data:
                self._insert_batch(batch_data)

            return records_processed

        except Exception as e:
            logger.error(f"Error processing CSV file {file_path}: {str(e)}")
            raise

    def ingest_plans(
        self,
        csv_directory: Optional[str] = None,
        specific_files: Optional[List[Union[str, Path]]] = None,
        force_full_refresh: bool = False,
        resume_from_checkpoint: bool = True,
        enable_validation: Optional[bool] = None,
        enable_deduplication: Optional[bool] = None,
    ) -> int:
        """
        Ingest plans data from CSV files with enhanced features.

        Args:
            csv_directory: Directory containing CSV files
            specific_files: List of specific files to process
            force_full_refresh: If True, truncate existing data and reload
            resume_from_checkpoint: If True, resume from last checkpoint
            enable_validation: Override validation setting
            enable_deduplication: Override deduplication setting

        Returns:
            Number of records ingested
        """
        # Override validation/deduplication if specified
        if enable_validation is not None:
            self.enable_validation = enable_validation
        if enable_deduplication is not None:
            self.enable_deduplication = enable_deduplication

        try:
            # Log pipeline execution start
            self.log_pipeline_execution("running")

            # Handle checkpoint resume
            checkpoint = None
            if resume_from_checkpoint and not force_full_refresh:
                checkpoint = self.checkpoint_manager.load_checkpoint()
                if checkpoint:
                    logger.info(f"Resuming from checkpoint: {checkpoint}")
                    # Restore metrics from checkpoint
                    if "metrics" in checkpoint:
                        for key, value in checkpoint["metrics"].items():
                            if hasattr(self.metrics, key):
                                setattr(self.metrics, key, value)

            # Handle full refresh
            if force_full_refresh:
                logger.warning(
                    "Force full refresh requested. Truncating existing data."
                )
                self.db_manager.model_db.execute_command(
                    f"TRUNCATE TABLE {self.table_name}"
                )
                self.checkpoint_manager.clear_checkpoint()
                checkpoint = None

            # Determine files to process
            files_to_process = []

            if specific_files:
                # Process specific files
                files_to_process = [Path(f) for f in specific_files]
            elif csv_directory:
                # Find all CSV files in directory
                csv_dir = Path(csv_directory)
                if not csv_dir.exists():
                    raise ValueError(f"CSV directory does not exist: {csv_directory}")

                files_to_process = sorted(csv_dir.glob("*.csv"))

                # Skip files already processed if resuming
                if checkpoint and checkpoint.get("last_processed_file"):
                    last_file = checkpoint["last_processed_file"]
                    # Find the position of the last processed file
                    file_names = [f.name for f in files_to_process]
                    if last_file in file_names:
                        last_idx = file_names.index(last_file)
                        # If the file was fully processed, start from next file
                        if checkpoint.get("last_processed_row", -1) == -1:
                            files_to_process = files_to_process[last_idx + 1 :]
                        else:
                            # Otherwise, include this file for partial processing
                            files_to_process = files_to_process[last_idx:]
            else:
                raise ValueError(
                    "Either csv_directory or specific_files must be provided"
                )

            logger.info(f"Found {len(files_to_process)} CSV files to process")

            # Process each file
            total_records = 0
            for file_path in files_to_process:
                records = self._process_csv_file(file_path, checkpoint)
                total_records += records
                self.metrics.files_processed += 1

                # Save checkpoint after each file
                self.checkpoint_manager.save_checkpoint(
                    {
                        "last_processed_file": file_path.name,
                        "last_processed_row": -1,  # Indicates file is complete
                        "total_records": self.metrics.total_records,
                        "metrics": self.metrics.to_dict(),
                    }
                )

                # Clear checkpoint for next file
                checkpoint = None

            # Clear checkpoint on successful completion
            if resume_from_checkpoint:
                self.checkpoint_manager.clear_checkpoint()

            # Log successful completion
            self.log_pipeline_execution("success")

            logger.info(self.get_metrics_summary())
            logger.info(f"Files processed: {self.metrics.files_processed}")

            return self.metrics.new_records

        except Exception as e:
            # Log failure
            self.log_pipeline_execution("failed", str(e))
            logger.error(f"Failed to ingest plans data: {str(e)}")
            raise


def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest plans data from CSV files")
    parser.add_argument("--csv-dir", help="Directory containing CSV files")
    parser.add_argument("--files", nargs="+", help="Specific CSV files to process")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force full refresh (truncate and reload)",
    )
    parser.add_argument(
        "--no-resume", action="store_true", help="Do not resume from checkpoint"
    )
    parser.add_argument(
        "--no-validation", action="store_true", help="Disable data validation"
    )
    parser.add_argument(
        "--no-deduplication", action="store_true", help="Disable deduplication"
    )
    parser.add_argument("--checkpoint-dir", help="Directory for checkpoint files")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.csv_dir and not args.files:
        parser.error("Either --csv-dir or --files must be provided")

    # Set up logging
    from utils.logging_config import setup_logging

    setup_logging(log_level=args.log_level, log_file="ingest_plans")

    # Run ingestion
    ingester = PlansIngester(
        checkpoint_dir=args.checkpoint_dir,
        enable_validation=not args.no_validation,
        enable_deduplication=not args.no_deduplication,
    )

    try:
        records = ingester.ingest_plans(
            csv_directory=args.csv_dir,
            specific_files=args.files,
            force_full_refresh=args.force_refresh,
            resume_from_checkpoint=not args.no_resume,
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    except Exception as e:
        logger.error(f"Plans ingestion failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
