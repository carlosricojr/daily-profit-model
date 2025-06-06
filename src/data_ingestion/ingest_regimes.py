"""
Enhanced regimes ingester with checkpoint support, validation, and metrics tracking.
Handles regimes_daily data ingestion from Supabase with production-ready features.
"""

import os
import sys
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
import hashlib
import json
import numpy as np

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

# Expected vector dimension for regime data
EXPECTED_VECTOR_DIMENSION = 5  # Adjust based on actual vector size


class RegimesIngester(BaseIngester):
    """Enhanced regimes ingester for Supabase data with production-ready features."""

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        enable_validation: bool = True,
        enable_deduplication: bool = True,
    ):
        """Initialize the enhanced regimes ingester."""
        super().__init__(
            ingestion_type="regimes",
            table_name="raw_regimes_daily",
            checkpoint_dir=checkpoint_dir,
            enable_validation=enable_validation,
            enable_deduplication=enable_deduplication,
        )

        self.source_table = "regimes_daily"

    def _parse_vector(self, vector_value: Any) -> List[float]:
        """Parse vector from various formats to list."""
        if vector_value is None:
            return []

        # Already a list
        if isinstance(vector_value, list):
            return [float(v) for v in vector_value]

        # Numpy array
        if isinstance(vector_value, np.ndarray):
            return vector_value.tolist()

        # String representation
        if isinstance(vector_value, str):
            vector_str = vector_value.strip()

            # JSON array format: "[0.1, 0.2, 0.3]"
            if vector_str.startswith("[") and vector_str.endswith("]"):
                try:
                    return json.loads(vector_str)
                except (json.JSONDecodeError, ValueError):
                    pass

            # Space-separated format: "0.1 0.2 0.3"
            try:
                return [float(v) for v in vector_str.split()]
            except (ValueError, TypeError):
                pass

        # Try to convert whatever it is to a list
        try:
            return list(vector_value)
        except (TypeError, ValueError):
            return []

    def _validate_record(self, record: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a regime record."""
        errors = []

        # Check required date field
        if not record.get("date"):
            errors.append("missing_date")

        # Validate vector dimension
        vector = record.get("vector_daily_regime")
        if vector is not None:
            parsed_vector = self._parse_vector(vector)
            if len(parsed_vector) != EXPECTED_VECTOR_DIMENSION:
                errors.append("invalid_vector_dimension")

            # Check vector values are in valid range [0, 1] or [-1, 1]
            for val in parsed_vector:
                if val < -1 or val > 1:
                    errors.append("vector_values_out_of_range")
                    break

        # Validate JSON fields
        json_fields = [
            "market_news",
            "instruments",
            "country_economic_indicators",
            "news_analysis",
            "summary",
        ]

        for field in json_fields:
            value = record.get(field)
            if value is not None and not isinstance(
                value, (dict, list, str, type(None))
            ):
                errors.append(f"invalid_{field}_format")

        return len(errors) == 0, errors

    def _get_record_key(self, record: Dict[str, Any]) -> Optional[str]:
        """Generate unique key for deduplication based on date."""
        record_date = record.get("date")
        if not record_date:
            return None

        # Create hash of date
        date_str = str(record_date)
        return hashlib.md5(date_str.encode()).hexdigest()

    def _serialize_json_field(self, value: Any) -> Optional[str]:
        """Serialize JSON field to string if needed."""
        if value is None:
            return None

        if isinstance(value, str):
            return value

        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError, AttributeError):
            return str(value)

    def _transform_regime_record(self, row: Tuple) -> Dict[str, Any]:
        """Transform regime record from database row to target format."""
        # Extract fields from row tuple
        # Expected order: date, market_news, instruments, country_economic_indicators,
        # news_analysis, summary, vector_daily_regime, created_at, updated_at

        record = {
            "date": row[0],
            "market_news": self._serialize_json_field(row[1]),
            "instruments": self._serialize_json_field(row[2]),
            "country_economic_indicators": self._serialize_json_field(row[3]),
            "news_analysis": self._serialize_json_field(row[4]),
            "summary": self._serialize_json_field(row[5]),
            "vector_daily_regime": self._parse_vector(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
            "ingestion_timestamp": datetime.now(),
            "source_table": self.source_table,
        }

        return record

    def _get_conflict_clause(self, table_name: str) -> str:
        """Get ON CONFLICT clause for regimes table."""
        return "ON CONFLICT (date, ingestion_timestamp) DO NOTHING"

    def _get_latest_date(self) -> Optional[date]:
        """Get the latest date in the target table."""
        query = f"""
        SELECT MAX(date) as max_date 
        FROM {self.table_name}
        """

        result = self.db_manager.model_db.execute_query(query)
        if result and result[0]["max_date"]:
            return result[0]["max_date"]

        return None

    def ingest_regimes(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        incremental: bool = False,
        force_full_refresh: bool = False,
        resume_from_checkpoint: bool = True,
        enable_validation: Optional[bool] = None,
        enable_deduplication: Optional[bool] = None,
    ) -> int:
        """
        Ingest regimes data from Supabase with enhanced features.

        Args:
            start_date: Start date for ingestion
            end_date: End date for ingestion
            incremental: If True, ingest from latest date in target table
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

            # Determine date range
            if incremental and not start_date:
                # Get latest date from target table
                latest_date = self._get_latest_date()
                if latest_date:
                    start_date = latest_date + timedelta(days=1)
                    logger.info(f"Incremental load: starting from {start_date}")
                else:
                    logger.info("No existing data found, loading all available data")

            # Resume from checkpoint if available
            if checkpoint and checkpoint.get("last_processed_date"):
                checkpoint_date = datetime.strptime(
                    checkpoint["last_processed_date"], "%Y-%m-%d"
                ).date()
                start_date = checkpoint_date + timedelta(days=1)
                logger.info(f"Resuming from checkpoint date: {start_date}")

            # Default date range if not specified
            if not end_date:
                end_date = datetime.now().date()
            if not start_date:
                start_date = end_date - timedelta(days=30)

            # Query regimes data from source database
            query = """
            SELECT date, market_news, instruments, country_economic_indicators,
                   news_analysis, summary, vector_daily_regime, created_at, updated_at
            FROM regimes_daily
            WHERE date >= %s AND date <= %s
            ORDER BY date
            """

            logger.info(f"Querying regimes data from {start_date} to {end_date}")

            batch_data = []
            batch_size = 100  # Smaller batch size for regime data
            total_records = 0

            with self.db_manager.source_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (start_date, end_date))

                    while True:
                        rows = cursor.fetchmany(1000)
                        if not rows:
                            break

                        for row in rows:
                            self.metrics.total_records += 1

                            # Transform row to record
                            try:
                                record = self._transform_regime_record(row)
                            except Exception as e:
                                logger.error(f"Error transforming record: {e}")
                                self.metrics.invalid_records += 1
                                continue

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

                            # Add to batch
                            batch_data.append(record)
                            self.metrics.new_records += 1

                            # Insert batch when it reaches the size limit
                            if len(batch_data) >= batch_size:
                                self._insert_batch(batch_data)
                                batch_data = []
                                total_records += batch_size

                                # Save checkpoint periodically
                                if total_records % 1000 == 0:
                                    last_date = record["date"]
                                    self.checkpoint_manager.save_checkpoint(
                                        {
                                            "last_processed_date": str(last_date),
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
            # Log failure
            self.log_pipeline_execution("failed", str(e))
            logger.error(f"Failed to ingest regimes data: {str(e)}")
            raise


def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest regimes data with enhanced features"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for ingestion (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for ingestion (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Perform incremental load from latest date",
    )
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

    setup_logging(log_level=args.log_level, log_file="ingest_regimes")

    # Run ingestion
    ingester = RegimesIngester(
        checkpoint_dir=args.checkpoint_dir,
        enable_validation=not args.no_validation,
        enable_deduplication=not args.no_deduplication,
    )

    try:
        records = ingester.ingest_regimes(
            start_date=args.start_date,
            end_date=args.end_date,
            incremental=args.incremental,
            force_full_refresh=args.force_refresh,
            resume_from_checkpoint=not args.no_resume,
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    except Exception as e:
        logger.error(f"Regimes ingestion failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
