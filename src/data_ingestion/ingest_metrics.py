"""
Enhanced metrics ingester with checkpoint support, validation, and metrics tracking.
Handles alltime, daily, and hourly metrics with production-ready features.
"""

import os
import sys
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import hashlib

# Ensure we can import from parent directories
try:
    from .base_ingester import BaseIngester, IngestionMetrics, CheckpointManager
    from ..utils.api_client import RiskAnalyticsAPIClient
    from ..utils.logging_config import get_logger
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data_ingestion.base_ingester import BaseIngester, IngestionMetrics, CheckpointManager
    from utils.api_client import RiskAnalyticsAPIClient
    from utils.logging_config import get_logger

logger = get_logger(__name__)


class MetricType(Enum):
    """Enum for metric types."""

    ALLTIME = "alltime"
    DAILY = "daily"
    HOURLY = "hourly"


class MetricsIngester(BaseIngester):
    """Enhanced metrics ingester with production-ready features."""

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        enable_validation: bool = True,
        enable_deduplication: bool = True,
    ):
        """Initialize the enhanced metrics ingester."""
        # Initialize base class with a dummy table name (we'll use multiple tables)
        super().__init__(
            ingestion_type="metrics",
            table_name="raw_metrics_alltime",  # Default table
            checkpoint_dir=checkpoint_dir,
            enable_validation=enable_validation,
            enable_deduplication=enable_deduplication,
        )

        # We'll initialize the base class for each metric type as needed
        self.checkpoint_dir = checkpoint_dir
        self.enable_validation = enable_validation
        self.enable_deduplication = enable_deduplication

        # Initialize API client
        self.api_client = RiskAnalyticsAPIClient()

        # Table mapping for different metric types
        self.table_mapping = {
            MetricType.ALLTIME: "raw_metrics_alltime",
            MetricType.DAILY: "raw_metrics_daily",
            MetricType.HOURLY: "raw_metrics_hourly",
        }

        # Initialize separate checkpoint managers and metrics for each type
        self.checkpoint_managers = {}
        self.metrics_by_type = {}

        for metric_type in MetricType:
            # Initialize base ingester components for each metric type
            checkpoint_file = os.path.join(
                checkpoint_dir
                or os.path.join(os.path.dirname(__file__), "checkpoints"),
                f"metrics_{metric_type.value}_checkpoint.json",
            )
            self.checkpoint_managers[metric_type.value] = CheckpointManager(
                checkpoint_file, f"metrics_{metric_type.value}"
            )
            self.metrics_by_type[metric_type.value] = IngestionMetrics()

    def _validate_record(
        self, record: Dict[str, Any], metric_type: MetricType
    ) -> Tuple[bool, List[str]]:
        """Validate a metric record based on type."""
        errors = []

        # Common validations
        if not record.get("accountId"):
            errors.append("missing_account_id")

        if not record.get("login"):
            errors.append("missing_login")

        # Validate numeric fields
        numeric_fields = [
            "netProfit",
            "grossProfit",
            "grossLoss",
            "totalTrades",
            "winningTrades",
            "losingTrades",
            "winRate",
            "profitFactor",
        ]

        for field in numeric_fields:
            if field in record:
                value = self._safe_float(record.get(field))
                if value is None and record.get(field) is not None:
                    errors.append(f"invalid_{field}")

        # Type-specific validations
        if metric_type in [MetricType.DAILY, MetricType.HOURLY]:
            # Validate date format (should be YYYYMMDD)
            date_str = str(record.get("date", ""))
            if not date_str or len(date_str) != 8:
                errors.append("invalid_date_format")
            else:
                try:
                    datetime.strptime(date_str, "%Y%m%d")
                except ValueError:
                    errors.append("invalid_date_value")

        if metric_type == MetricType.HOURLY:
            # Validate hour
            hour = record.get("hour")
            if hour is None:
                errors.append("missing_hour")
            elif not isinstance(hour, int) or hour < 0 or hour > 23:
                errors.append("invalid_hour")

        # Validate trade counts
        total_trades = self._safe_int(record.get("totalTrades"))
        winning_trades = self._safe_int(record.get("winningTrades"))
        losing_trades = self._safe_int(record.get("losingTrades"))

        if total_trades is not None and total_trades < 0:
            errors.append("negative_trade_count")

        if (
            total_trades is not None
            and winning_trades is not None
            and losing_trades is not None
        ):
            if winning_trades + losing_trades > total_trades:
                errors.append("inconsistent_trade_counts")

        return len(errors) == 0, errors

    def _get_record_key(
        self, record: Dict[str, Any], metric_type: MetricType
    ) -> Optional[str]:
        """Generate unique key for deduplication."""
        key_parts = [str(record.get("accountId", "")), str(record.get("login", ""))]

        if metric_type == MetricType.DAILY:
            key_parts.append(str(record.get("date", "")))
        elif metric_type == MetricType.HOURLY:
            key_parts.extend([str(record.get("date", "")), str(record.get("hour", ""))])

        # Create hash of key parts
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _bound_decimal_10_2(self, value: Any) -> Optional[float]:
        """Bound value to fit in DECIMAL(10,2) - max 99999999.99."""
        val = self._safe_float(value)
        if val is None:
            return None
        # DECIMAL(10,2) can hold max 8 digits before decimal
        if abs(val) >= 100000000:  # 10^8
            return None  # Too large to fit
        return val

    def _transform_alltime_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform all-time metric record for database."""
        # Calculate derived fields
        num_trades = self._safe_int(metric.get("numTrades"))
        gross_profit = self._safe_float(metric.get("grossProfit", 0))
        gross_loss = self._safe_float(metric.get("grossLoss", 0))
        
        # Calculate winning/losing trades if not provided
        success_rate = self._safe_float(metric.get("successRate", 0))
        winning_trades = None
        losing_trades = None
        if num_trades and success_rate is not None:
            winning_trades = int(num_trades * (success_rate / 100))
            losing_trades = num_trades - winning_trades
        
        # Calculate average win/loss
        average_win = None
        average_loss = None
        if winning_trades and winning_trades > 0 and gross_profit:
            average_win = gross_profit / winning_trades
        if losing_trades and losing_trades > 0 and gross_loss:
            average_loss = abs(gross_loss) / losing_trades
            
        return {
            "account_id": metric.get("accountId"),
            "login": metric.get("login"),
            "net_profit": self._safe_float(metric.get("netProfit")),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_trades": num_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": success_rate,  # API uses successRate
            "profit_factor": self._bound_decimal_10_2(metric.get("profitFactor")),
            "average_win": average_win,
            "average_loss": average_loss,
            "average_rrr": self._bound_decimal_10_2(metric.get("meanTPvsSL")),  # Risk-reward ratio
            "expectancy": self._safe_float(metric.get("expectancy")),
            "sharpe_ratio": self._bound_decimal_10_2(metric.get("dailySharpe")),  # Use daily sharpe
            "sortino_ratio": self._bound_decimal_10_2(metric.get("dailySortino")),  # Use daily sortino
            "max_drawdown": self._safe_float(metric.get("maxDrawDown")),  # Note capital D
            "max_drawdown_pct": self._safe_float(metric.get("relMaxDrawDown")),  # Relative = percentage
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/alltime",
        }

    def _transform_daily_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform daily metric record for database."""
        # Parse date from ISO format or YYYYMMDD
        date_str = metric.get("date", "")
        metric_date = None
        if date_str:
            if "T" in str(date_str):  # ISO format
                metric_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            elif len(str(date_str)) == 8:  # YYYYMMDD format
                metric_date = datetime.strptime(str(date_str), "%Y%m%d").date()

        # Calculate derived fields
        num_trades = self._safe_int(metric.get("numTrades"))
        gross_profit = self._safe_float(metric.get("grossProfit", 0))
        gross_loss = self._safe_float(metric.get("grossLoss", 0))
        
        # Calculate winning/losing trades if not provided
        success_rate = self._safe_float(metric.get("successRate", 0))
        winning_trades = None
        losing_trades = None
        if num_trades and success_rate is not None:
            winning_trades = int(num_trades * (success_rate / 100))
            losing_trades = num_trades - winning_trades

        return {
            "account_id": metric.get("accountId"),
            "login": metric.get("login"),
            "date": metric_date,
            "net_profit": self._safe_float(metric.get("netProfit")),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_trades": num_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": success_rate,  # API uses successRate
            "profit_factor": self._bound_decimal_10_2(metric.get("profitFactor")),
            "lots_traded": self._safe_float(metric.get("totalLots")),  # API uses totalLots
            "volume_traded": self._safe_float(metric.get("totalVolume")),  # API uses totalVolume
            "commission": self._safe_float(metric.get("commission")),
            "swap": self._safe_float(metric.get("swap")),
            "balance_start": self._safe_float(metric.get("priorDaysBalance")),  # Start of day balance
            "balance_end": self._safe_float(metric.get("currentBalance")),  # End of day balance
            "equity_start": self._safe_float(metric.get("priorDaysEquity")),  # Start of day equity
            "equity_end": self._safe_float(metric.get("currentEquity")),  # End of day equity
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/daily",
        }

    def _transform_hourly_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Transform hourly metric record for database."""
        # Parse date from ISO format or YYYYMMDD
        date_str = metric.get("date", "")
        metric_date = None
        if date_str:
            if "T" in str(date_str):  # ISO format
                metric_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            elif len(str(date_str)) == 8:  # YYYYMMDD format
                metric_date = datetime.strptime(str(date_str), "%Y%m%d").date()

        # Calculate derived fields
        num_trades = self._safe_int(metric.get("numTrades"))
        gross_profit = self._safe_float(metric.get("grossProfit", 0))
        gross_loss = self._safe_float(metric.get("grossLoss", 0))
        
        # Calculate winning/losing trades if not provided
        success_rate = self._safe_float(metric.get("successRate", 0))
        winning_trades = None
        losing_trades = None
        if num_trades and success_rate is not None:
            winning_trades = int(num_trades * (success_rate / 100))
            losing_trades = num_trades - winning_trades

        return {
            "account_id": metric.get("accountId"),
            "login": metric.get("login"),
            "date": metric_date,
            "hour": metric.get("hour"),
            "net_profit": self._safe_float(metric.get("netProfit")),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_trades": num_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": success_rate,  # API uses successRate
            "lots_traded": self._safe_float(metric.get("totalLots")),  # API uses totalLots
            "volume_traded": self._safe_float(metric.get("totalVolume")),  # API uses totalVolume
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/metrics/hourly",
        }

    def _get_conflict_clause(self, table_name: str) -> str:
        """Get ON CONFLICT clause based on table type."""
        if "alltime" in table_name:
            return "ON CONFLICT (account_id, ingestion_timestamp) DO NOTHING"
        elif "daily" in table_name:
            return "ON CONFLICT (account_id, date, ingestion_timestamp) DO NOTHING"
        else:  # hourly
            return (
                "ON CONFLICT (account_id, date, hour, ingestion_timestamp) DO NOTHING"
            )

    def ingest_metrics(
        self,
        metric_type: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        logins: Optional[List[str]] = None,
        accountids: Optional[List[str]] = None,
        force_full_refresh: bool = False,
        resume_from_checkpoint: bool = True,
        enable_validation: Optional[bool] = None,
        enable_deduplication: Optional[bool] = None,
    ) -> int:
        """
        Ingest metrics data from the API with enhanced features.

        Args:
            metric_type: Type of metrics ('alltime', 'daily', 'hourly')
            start_date: Start date for daily/hourly metrics
            end_date: End date for daily/hourly metrics
            logins: Optional list of specific login IDs
            accountids: Optional list of specific account IDs
            force_full_refresh: If True, truncate existing data and reload
            resume_from_checkpoint: If True, resume from last checkpoint
            enable_validation: Override validation setting
            enable_deduplication: Override deduplication setting

        Returns:
            Number of records ingested
        """
        # Validate metric type
        try:
            metric_type_enum = MetricType(metric_type)
        except ValueError:
            raise ValueError(f"Invalid metric type: {metric_type}")

        # Override validation/deduplication if specified
        if enable_validation is not None:
            self.enable_validation = enable_validation
        if enable_deduplication is not None:
            self.enable_deduplication = enable_deduplication

        # Update table name and ingestion type for this specific metric type
        self.table_name = self.table_mapping[metric_type_enum]
        self.ingestion_type = f"metrics_{metric_type}"

        # Use the specific checkpoint manager and metrics for this type
        self.checkpoint_manager = self.checkpoint_managers[metric_type]
        self.metrics = self.metrics_by_type[metric_type]

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
                    f"Force full refresh requested for {metric_type}. Truncating existing data."
                )
                self.db_manager.model_db.execute_command(
                    f"TRUNCATE TABLE {self.table_name}"
                )
                self.checkpoint_manager.clear_checkpoint()
                checkpoint = None

            # Ingest based on metric type
            if metric_type_enum == MetricType.ALLTIME:
                total_records = self._ingest_alltime_metrics(
                    logins, accountids, checkpoint
                )
            else:
                total_records = self._ingest_time_series_metrics(
                    metric_type_enum,
                    start_date,
                    end_date,
                    logins,
                    accountids,
                    checkpoint,
                )

            # Clear checkpoint on successful completion
            if resume_from_checkpoint:
                self.checkpoint_manager.clear_checkpoint()

            # Log successful completion
            self.log_pipeline_execution("success")

            logger.info(self.get_metrics_summary())
            return total_records

        except Exception as e:
            # Log failure
            self.log_pipeline_execution("failed", str(e))
            logger.error(f"Failed to ingest {metric_type} metrics: {str(e)}")
            raise

    def _ingest_alltime_metrics(
        self,
        logins: Optional[List[str]],
        accountids: Optional[List[str]],
        checkpoint: Optional[Dict[str, Any]],
    ) -> int:
        """Ingest all-time metrics data with checkpointing."""
        batch_data = []
        batch_size = 1000

        # Resume from checkpoint if available
        start_page = 0
        if checkpoint:
            start_page = checkpoint.get("last_processed_page", 0) + 1
            logger.info(f"Resuming from page {start_page}")

        logger.info(f"Starting all-time metrics ingestion... logins={logins}, accountids={accountids}")

        try:
            pages_received = 0
            for page_num, metrics_page in enumerate(
                self.api_client.get_metrics(
                    metric_type="alltime", logins=logins, accountids=accountids
                )
            ):
                pages_received += 1
                # Skip pages already processed
                if page_num < start_page:
                    logger.info(f"Skipping already processed page {page_num}")
                    continue

                self.metrics.api_calls += 1
                logger.info(
                    f"Processing page {page_num + 1} with {len(metrics_page)} metrics"
                )

                for metric in metrics_page:
                    self.metrics.total_records += 1

                    # Validate and process
                    if self.enable_validation:
                        is_valid, errors = self._validate_record(
                            metric, MetricType.ALLTIME
                        )
                        if not is_valid:
                            self.metrics.invalid_records += 1
                            for error in errors:
                                self.metrics.validation_errors[error] += 1
                            continue

                    # Check for duplicates
                    if self.enable_deduplication:
                        key = self._get_record_key(metric, MetricType.ALLTIME)
                        if key in self.seen_records:
                            self.metrics.duplicate_records += 1
                            continue
                        self.seen_records.add(key)

                    # Transform and add to batch
                    record = self._transform_alltime_metric(metric)
                    batch_data.append(record)
                    self.metrics.new_records += 1

                    if len(batch_data) >= batch_size:
                        self._insert_batch(batch_data)
                        batch_data = []

                        # Save checkpoint periodically
                        if self.metrics.new_records % 10000 == 0:
                            self.checkpoint_manager.save_checkpoint(
                                {
                                    "metric_type": "alltime",
                                    "last_processed_page": page_num,
                                    "total_records": self.metrics.total_records,
                                    "metrics": self.metrics.to_dict(),
                                }
                            )

            # Insert remaining records
            if batch_data:
                self._insert_batch(batch_data)

            if pages_received == 0:
                logger.warning(f"No data pages received from API for {self.ingestion_type}")
            
            return self.metrics.new_records
        except Exception as e:
            # Track API errors
            if "API" in str(e) or "rate limit" in str(e):
                self.metrics.api_errors += 1
            logger.error(f"Error during {self.ingestion_type} ingestion: {str(e)}", exc_info=True)
            raise

    def _ingest_time_series_metrics(
        self,
        metric_type: MetricType,
        start_date: Optional[date],
        end_date: Optional[date],
        logins: Optional[List[str]],
        accountids: Optional[List[str]],
        checkpoint: Optional[Dict[str, Any]],
    ) -> int:
        """Ingest daily or hourly metrics data with checkpointing."""
        # Determine date range
        if not end_date:
            end_date = datetime.now().date() - timedelta(days=1)
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Resume from checkpoint if available
        if checkpoint:
            checkpoint_date = checkpoint.get("last_processed_date")
            if checkpoint_date:
                start_date = datetime.strptime(checkpoint_date, "%Y-%m-%d").date()
                # Move to next day if last date was fully processed
                if checkpoint.get("last_processed_page", 0) == -1:
                    start_date += timedelta(days=1)
                logger.info(f"Resuming from date {start_date}")

        batch_data = []
        batch_size = 1000

        # Process date by date
        current_date = start_date
        while current_date <= end_date:
            date_str = self.api_client.format_date(current_date)
            logger.info(f"Processing {metric_type.value} metrics for date: {date_str}")

            # For hourly metrics, specify hours
            hours = list(range(24)) if metric_type == MetricType.HOURLY else None

            # Check if we need to resume from a specific page for this date
            start_page = 0
            if checkpoint and checkpoint.get(
                "last_processed_date"
            ) == current_date.strftime("%Y-%m-%d"):
                start_page = checkpoint.get("last_processed_page", 0) + 1

            for page_num, metrics_page in enumerate(
                self.api_client.get_metrics(
                    metric_type=metric_type.value,
                    logins=logins,
                    accountids=accountids,
                    dates=[date_str],
                    hours=hours,
                )
            ):
                # Skip pages already processed
                if page_num < start_page:
                    continue

                self.metrics.api_calls += 1
                logger.debug(
                    f"Date {date_str}, page {page_num + 1}: {len(metrics_page)} records"
                )

                for metric in metrics_page:
                    self.metrics.total_records += 1

                    # Validate and process
                    if self.enable_validation:
                        is_valid, errors = self._validate_record(metric, metric_type)
                        if not is_valid:
                            self.metrics.invalid_records += 1
                            for error in errors:
                                self.metrics.validation_errors[error] += 1
                            continue

                    # Check for duplicates
                    if self.enable_deduplication:
                        key = self._get_record_key(metric, metric_type)
                        if key in self.seen_records:
                            self.metrics.duplicate_records += 1
                            continue
                        self.seen_records.add(key)

                    # Transform and add to batch
                    if metric_type == MetricType.DAILY:
                        record = self._transform_daily_metric(metric)
                    else:
                        record = self._transform_hourly_metric(metric)

                    batch_data.append(record)
                    self.metrics.new_records += 1

                    if len(batch_data) >= batch_size:
                        self._insert_batch(batch_data)
                        batch_data = []

                # Save checkpoint after each page
                if self.metrics.new_records % 5000 == 0:
                    self.checkpoint_manager.save_checkpoint(
                        {
                            "metric_type": metric_type.value,
                            "last_processed_date": current_date.strftime("%Y-%m-%d"),
                            "last_processed_page": page_num,
                            "start_date": start_date.strftime("%Y-%m-%d"),
                            "end_date": end_date.strftime("%Y-%m-%d"),
                            "total_records": self.metrics.total_records,
                            "metrics": self.metrics.to_dict(),
                        }
                    )

            # Mark date as complete
            self.checkpoint_manager.save_checkpoint(
                {
                    "metric_type": metric_type.value,
                    "last_processed_date": current_date.strftime("%Y-%m-%d"),
                    "last_processed_page": -1,  # Indicates date is complete
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "total_records": self.metrics.total_records,
                    "metrics": self.metrics.to_dict(),
                }
            )

            current_date += timedelta(days=1)

        # Insert remaining records
        if batch_data:
            self._insert_batch(batch_data)

        return self.metrics.new_records

    def close(self):
        """Clean up resources."""
        if hasattr(self, "api_client"):
            self.api_client.close()


def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest metrics data with enhanced features"
    )
    parser.add_argument(
        "metric_type",
        choices=["alltime", "daily", "hourly"],
        help="Type of metrics to ingest",
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for daily/hourly metrics (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for daily/hourly metrics (YYYY-MM-DD)",
    )
    parser.add_argument("--logins", nargs="+", help="Specific login IDs to fetch")
    parser.add_argument("--accountids", nargs="+", help="Specific account IDs to fetch")
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

    setup_logging(
        log_level=args.log_level, log_file=f"ingest_metrics_{args.metric_type}"
    )

    # Run ingestion
    ingester = MetricsIngester(
        checkpoint_dir=args.checkpoint_dir,
        enable_validation=not args.no_validation,
        enable_deduplication=not args.no_deduplication,
    )

    try:
        records = ingester.ingest_metrics(
            metric_type=args.metric_type,
            start_date=args.start_date,
            end_date=args.end_date,
            logins=args.logins,
            accountids=args.accountids,
            force_full_refresh=args.force_refresh,
            resume_from_checkpoint=not args.no_resume,
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    finally:
        ingester.close()


if __name__ == "__main__":
    main()
