"""
Enhanced accounts ingester with checkpoint support, validation, and metrics tracking.
Handles account data ingestion with production-ready features.
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import hashlib

# Ensure we can import from parent directories
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .base_ingester import BaseIngester
    from ..utils.api_client import RiskAnalyticsAPIClient
    from ..utils.logging_config import get_logger
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_ingestion.base_ingester import BaseIngester
    from utils.api_client import RiskAnalyticsAPIClient
    from utils.logging_config import get_logger

logger = get_logger(__name__)

# Valid values for phase and status fields
VALID_PHASES = ["evaluation", "challenge", "funded", "express"]
VALID_STATUSES = ["active", "inactive", "suspended", "terminated"]


class AccountsIngester(BaseIngester):
    """Enhanced accounts ingester with production-ready features."""

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        enable_validation: bool = True,
        enable_deduplication: bool = True,
    ):
        """Initialize the enhanced accounts ingester."""
        super().__init__(
            ingestion_type="accounts",
            table_name="raw_accounts_data",
            checkpoint_dir=checkpoint_dir,
            enable_validation=enable_validation,
            enable_deduplication=enable_deduplication,
        )

        # Initialize API client
        self.api_client = RiskAnalyticsAPIClient()
        self.source_endpoint = "/accounts"

    def _validate_record(self, record: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate an account record."""
        errors = []

        # Check required fields
        required_fields = ["accountId", "login"]
        for field in required_fields:
            if not record.get(field):
                errors.append(f"missing_{field}")

        # Validate balances
        starting_balance = self._safe_float(record.get("startingBalance"))
        current_balance = self._safe_float(record.get("currentBalance"))

        if starting_balance is not None and starting_balance < 0:
            errors.append("negative_starting_balance")

        if current_balance is not None and current_balance < 0:
            errors.append("negative_balance")

        # Check balance consistency
        breached = record.get("breached", 0)
        if (
            starting_balance is not None
            and current_balance is not None
            and current_balance < starting_balance
            and not breached
        ):
            errors.append("balance_inconsistency")

        # Validate percentages
        percentage_fields = ["profitTargetPct", "maxDailyDrawdownPct", "maxDrawdownPct"]
        for field in percentage_fields:
            value = self._safe_float(record.get(field))
            if value is not None and (value < 0 or value > 100):
                errors.append(f"invalid_{field}")

        # Validate leverage
        max_leverage = self._safe_int(record.get("maxLeverage"))
        if max_leverage is not None and max_leverage <= 0:
            errors.append("invalid_leverage")

        # Validate phase
        phase = record.get("phase")
        if phase and phase not in VALID_PHASES:
            errors.append("invalid_phase")

        # Validate status
        status = record.get("status")
        if status and status not in VALID_STATUSES:
            errors.append("invalid_status")

        return len(errors) == 0, errors

    def _get_record_key(self, record: Dict[str, Any]) -> Optional[str]:
        """Generate unique key for deduplication."""
        account_id = str(record.get("accountId", ""))
        if not account_id:
            return None

        # Create hash of account ID
        return hashlib.md5(account_id.encode()).hexdigest()

    def _transform_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Transform API account record to database format."""
        return {
            "account_id": record.get("accountId"),
            "login": record.get("login"),
            "trader_id": record.get("traderId"),
            "plan_id": record.get("planId"),
            "starting_balance": self._safe_float(record.get("startingBalance")),
            "current_balance": self._safe_float(record.get("currentBalance")),
            "current_equity": self._safe_float(record.get("currentEquity")),
            "profit_target_pct": self._safe_float(record.get("profitTargetPct")),
            "max_daily_drawdown_pct": self._safe_float(
                record.get("maxDailyDrawdownPct")
            ),
            "max_drawdown_pct": self._safe_float(record.get("maxDrawdownPct")),
            "max_leverage": self._safe_int(record.get("maxLeverage")),
            "is_drawdown_relative": record.get("isDrawdownRelative"),
            "breached": record.get("breached", 0),
            "is_upgraded": record.get("isUpgraded", 0),
            "phase": record.get("phase"),
            "status": record.get("status"),
            "created_at": record.get("createdAt"),
            "updated_at": record.get("updatedAt"),
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": self.source_endpoint,
        }

    def _get_conflict_clause(self, table_name: str) -> str:
        """Get ON CONFLICT clause for accounts table."""
        return "ON CONFLICT (account_id, ingestion_timestamp) DO NOTHING"

    def ingest_accounts(
        self,
        logins: Optional[List[str]] = None,
        traders: Optional[List[str]] = None,
        force_full_refresh: bool = False,
        resume_from_checkpoint: bool = True,
        enable_validation: Optional[bool] = None,
        enable_deduplication: Optional[bool] = None,
    ) -> int:
        """
        Ingest accounts data from the API with enhanced features.

        Args:
            logins: Optional list of specific login IDs to fetch
            traders: Optional list of specific trader IDs to fetch
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
            
            # Auto-discover active logins if none provided
            if not logins and not traders:
                logger.info("No logins or traders specified, discovering active logins...")
                try:
                    from .discover_active_logins import ActiveLoginDiscoverer
                    discoverer = ActiveLoginDiscoverer()
                    logins = discoverer.get_active_logins_for_ingestion()
                    discoverer.close()
                    
                    if logins:
                        logger.info(f"Discovered {len(logins)} active logins for ingestion")
                    else:
                        logger.warning("No active logins discovered. Will fetch all accounts.")
                except Exception as e:
                    logger.warning(f"Could not discover active logins: {e}. Will fetch all accounts.")
                    logins = None

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

            # Prepare batch for insertion
            batch_data = []
            batch_size = 1000

            # Resume from checkpoint if available
            start_page = 0
            if checkpoint:
                start_page = checkpoint.get("last_processed_page", 0) + 1
                logger.info(f"Resuming from page {start_page}")

            # Fetch accounts data with pagination
            logger.info("Starting accounts data ingestion...")

            try:
                for page_num, accounts_page in enumerate(
                    self.api_client.get_accounts(logins=logins, traders=traders)
                ):
                    # Skip pages already processed
                    if page_num < start_page:
                        continue

                    self.metrics.api_calls += 1
                    logger.info(
                        f"Processing page {page_num + 1} with {len(accounts_page)} accounts"
                    )

                    for account in accounts_page:
                        self.metrics.total_records += 1

                        # Validate if enabled
                        if self.enable_validation:
                            is_valid, errors = self._validate_record(account)
                            if not is_valid:
                                self.metrics.invalid_records += 1
                                for error in errors:
                                    self.metrics.validation_errors[error] += 1
                                continue

                        # Check for duplicates if enabled
                        if self.enable_deduplication:
                            key = self._get_record_key(account)
                            if key and key in self.seen_records:
                                self.metrics.duplicate_records += 1
                                continue
                            if key:
                                self.seen_records.add(key)

                        # Transform and add to batch
                        record = self._transform_record(account)
                        batch_data.append(record)
                        self.metrics.new_records += 1

                        # Insert batch when it reaches the size limit
                        if len(batch_data) >= batch_size:
                            self._insert_batch(batch_data)
                            batch_data = []

                            # Save checkpoint periodically
                            if self.metrics.new_records % 5000 == 0:
                                self.checkpoint_manager.save_checkpoint(
                                    {
                                        "last_processed_page": page_num,
                                        "total_records": self.metrics.total_records,
                                        "metrics": self.metrics.to_dict(),
                                    }
                                )

                # Insert any remaining records
                if batch_data:
                    self._insert_batch(batch_data)

                # Clear checkpoint on successful completion
                if resume_from_checkpoint:
                    self.checkpoint_manager.clear_checkpoint()

                # Log successful completion
                self.log_pipeline_execution("success")

                logger.info(self.get_metrics_summary())
                return self.metrics.new_records

            except Exception as e:
                # Track API errors
                if "API" in str(e) or "rate limit" in str(e):
                    self.metrics.api_errors += 1
                raise

        except Exception as e:
            # Log failure
            self.log_pipeline_execution("failed", str(e))
            logger.error(f"Failed to ingest accounts data: {str(e)}")
            raise

    def close(self):
        """Clean up resources."""
        if hasattr(self, "api_client"):
            self.api_client.close()


def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest accounts data with enhanced features"
    )
    parser.add_argument("--logins", nargs="+", help="Specific login IDs to fetch")
    parser.add_argument("--traders", nargs="+", help="Specific trader IDs to fetch")
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

    # Set up logging
    from utils.logging_config import setup_logging

    setup_logging(log_level=args.log_level, log_file="ingest_accounts")

    # Run ingestion
    ingester = AccountsIngester(
        checkpoint_dir=args.checkpoint_dir,
        enable_validation=not args.no_validation,
        enable_deduplication=not args.no_deduplication,
    )

    try:
        records = ingester.ingest_accounts(
            logins=args.logins,
            traders=args.traders,
            force_full_refresh=args.force_refresh,
            resume_from_checkpoint=not args.no_resume,
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    finally:
        ingester.close()


if __name__ == "__main__":
    main()
