"""
Ingest trades data from the /trades API endpoints (closed and open).
Handles the large volume of closed trades (81M records) efficiently.
"""

import os
import sys
import json
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
from pathlib import Path
import argparse

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_manager
from utils.api_client import RiskAnalyticsAPIClient
from utils.logging_config import setup_logging, get_logger

logger = get_logger(__name__)


@dataclass
class IngestionMetrics:
    """Track comprehensive ingestion metrics."""

    total_records: int = 0
    new_records: int = 0
    duplicate_records: int = 0
    invalid_records: int = 0
    api_calls: int = 0
    api_errors: int = 0
    db_errors: int = 0
    validation_errors: Dict[str, int] = None
    processing_time: float = 0.0
    records_per_second: float = 0.0

    def __post_init__(self):
        if self.validation_errors is None:
            self.validation_errors = defaultdict(int)

    def calculate_rate(self):
        """Calculate processing rate."""
        if self.processing_time > 0:
            self.records_per_second = self.total_records / self.processing_time


class CheckpointManager:
    """Simple JSON-based checkpoint manager for resilience."""

    def __init__(self, checkpoint_dir: str = ".checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)

    def save_checkpoint(self, stage: str, data: Dict[str, Any]):
        """Save checkpoint to JSON file."""
        checkpoint_file = self.checkpoint_dir / f"{stage}_checkpoint.json"
        with open(checkpoint_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug("Checkpoint saved", stage=stage, data_keys=list(data.keys()))

    def load_checkpoint(self, stage: str) -> Optional[Dict[str, Any]]:
        """Load checkpoint if exists."""
        checkpoint_file = self.checkpoint_dir / f"{stage}_checkpoint.json"
        if checkpoint_file.exists():
            with open(checkpoint_file, "r") as f:
                return json.load(f)
        return None

    def clear_checkpoint(self, stage: str):
        """Clear checkpoint after successful completion."""
        checkpoint_file = self.checkpoint_dir / f"{stage}_checkpoint.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.debug("Checkpoint cleared", stage=stage)


class TradesIngester:
    """Handles ingestion of trades data from the API."""

    def __init__(self, enable_validation: bool = True):
        """Initialize the trades ingester with enhanced features."""
        self.db_manager = get_db_manager()
        self.api_client = RiskAnalyticsAPIClient()
        self.checkpoint_manager = CheckpointManager()
        self.metrics = IngestionMetrics()
        self.enable_validation = enable_validation

        # Table mapping for trade types
        self.table_mapping = {"closed": "raw_trades_closed", "open": "raw_trades_open"}

    def ingest_trades(
        self,
        trade_type: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        logins: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        batch_days: int = 7,
        force_full_refresh: bool = False,
        resume_from_checkpoint: bool = True,
    ) -> int:
        """
        Ingest trades data from the API.

        Args:
            trade_type: Type of trades ('closed' or 'open')
            start_date: Start date for trade ingestion
            end_date: End date for trade ingestion
            logins: Optional list of specific login IDs
            symbols: Optional list of specific symbols
            batch_days: Number of days to process at once (for closed trades)
            force_full_refresh: If True, truncate existing data and reload
            resume_from_checkpoint: If True, resume from last checkpoint if available

        Returns:
            Number of records ingested
        """
        if trade_type not in self.table_mapping:
            raise ValueError(f"Invalid trade type: {trade_type}")

        table_name = self.table_mapping[trade_type]
        start_time = datetime.now()
        self.metrics = IngestionMetrics()  # Reset metrics

        try:
            # Log pipeline execution start
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f"ingest_trades_{trade_type}",
                execution_date=datetime.now().date(),
                status="running",
            )

            # Handle checkpoint resume
            if resume_from_checkpoint and not force_full_refresh:
                checkpoint = self.checkpoint_manager.load_checkpoint(
                    f"trades_{trade_type}"
                )
                if checkpoint:
                    logger.info(
                        "Resuming from checkpoint",
                        last_processed_date=checkpoint.get("last_processed_date"),
                        total_records=checkpoint.get("total_records", 0),
                        new_records=checkpoint.get("new_records", 0),
                    )
                    if checkpoint.get("last_processed_date"):
                        # Resume from day after last processed
                        start_date = datetime.strptime(
                            checkpoint["last_processed_date"], "%Y-%m-%d"
                        ).date() + timedelta(days=1)
                    self.metrics.total_records = checkpoint.get("total_records", 0)
                    self.metrics.new_records = checkpoint.get("new_records", 0)

            # Handle full refresh
            if force_full_refresh:
                logger.warning(
                    f"Force full refresh requested for {trade_type} trades. Truncating existing data."
                )
                self.db_manager.model_db.execute_command(f"TRUNCATE TABLE {table_name}")
                self.checkpoint_manager.clear_checkpoint(f"trades_{trade_type}")

            # Determine date range
            if not end_date:
                end_date = datetime.now().date() - timedelta(days=1)  # Yesterday
            if not start_date:
                if trade_type == "open":
                    # For open trades, we only need recent data
                    start_date = end_date
                else:
                    # For closed trades, default to last 30 days for initial load
                    start_date = end_date - timedelta(days=30)

            # Ingest trades
            if trade_type == "closed":
                self._ingest_closed_trades(
                    table_name, start_date, end_date, logins, symbols, batch_days
                )
            else:
                self._ingest_open_trades(
                    table_name, start_date, end_date, logins, symbols
                )

            # Batch resolve account IDs after ingestion
            logger.info(f"Starting batch account_id resolution for {trade_type} trades")
            trades_updated = self._batch_resolve_account_ids(table_name)
            logger.info(f"Account resolution complete: {trades_updated} trades updated")

            # Calculate final metrics
            self.metrics.processing_time = (datetime.now() - start_time).total_seconds()
            self.metrics.calculate_rate()

            # Log successful completion
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f"ingest_trades_{trade_type}",
                execution_date=datetime.now().date(),
                status="success",
                records_processed=self.metrics.new_records,
                execution_details={
                    "duration_seconds": self.metrics.processing_time,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "batch_days": batch_days if trade_type == "closed" else None,
                    "force_full_refresh": force_full_refresh,
                    "metrics": asdict(self.metrics),
                },
            )

            # Clear checkpoint on success
            self.checkpoint_manager.clear_checkpoint(f"trades_{trade_type}")

            # Log detailed metrics
            logger.info(f"""Successfully ingested {trade_type} trades:
            - Total records: {self.metrics.total_records:,}
            - New records: {self.metrics.new_records:,}
            - Duplicates: {self.metrics.duplicate_records:,}
            - Invalid: {self.metrics.invalid_records:,}
            - Rate: {self.metrics.records_per_second:.2f} records/s""")

            return self.metrics.new_records

        except Exception as e:
            # Log failure
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f"ingest_trades_{trade_type}",
                execution_date=datetime.now().date(),
                status="failed",
                error_message=str(e),
                records_processed=self.metrics.new_records,
            )
            logger.error(f"Failed to ingest {trade_type} trades: {str(e)}")
            raise

    def _ingest_closed_trades(
        self,
        table_name: str,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
        batch_days: int,
    ) -> int:
        """
        Ingest closed trades data in date batches to handle large volume.

        Critical: 81M records require careful handling
        """
        batch_data = []
        batch_size = 5000  # Larger batch for closed trades
        total_records = 0

        # Process in date chunks to manage volume
        current_start = start_date
        while current_start <= end_date:
            current_end = min(current_start + timedelta(days=batch_days - 1), end_date)

            logger.info(
                f"Processing closed trades from {current_start} to {current_end}"
            )

            # Format dates for API
            start_str = self.api_client.format_date(current_start)
            end_str = self.api_client.format_date(current_end)

            # Fetch trades for this date range
            try:
                self.metrics.api_calls += 1
                for page_num, trades_page in enumerate(
                    self.api_client.get_trades(
                        trade_type="closed",
                        logins=logins,
                        symbols=symbols,
                        trade_date_from=start_str,
                        trade_date_to=end_str,
                    )
                ):
                    if page_num % 10 == 0:  # Log progress every 10 pages
                        logger.info(
                            f"Processing page {page_num + 1} for dates {start_str}-{end_str}"
                        )

                    for trade in trades_page:
                        # Validate trade if enabled
                        if self.enable_validation:
                            is_valid, errors = self._validate_trade_record(
                                trade, "closed"
                            )
                            if not is_valid:
                                self.metrics.invalid_records += 1
                                for error in errors:
                                    self.metrics.validation_errors[error] += 1
                                logger.debug(
                                    f"Invalid closed trade {trade.get('position')}: {errors}"
                                )
                                continue

                        record = self._transform_closed_trade(trade)
                        batch_data.append(record)
                        self.metrics.total_records += 1

                        if len(batch_data) >= batch_size:
                            self._insert_trades_batch(batch_data, table_name)
                            total_records += len(batch_data)
                            batch_data = []

                            # Log progress for large datasets
                            if self.metrics.total_records % 50000 == 0:
                                logger.info(
                                    f"Progress: {self.metrics.total_records:,} records processed"
                                )

                # Save checkpoint after each date batch
                self._save_checkpoint("closed", current_end)

            except Exception as e:
                self.metrics.api_errors += 1
                logger.error(
                    f"API error for closed trades {current_start} to {current_end}: {str(e)}"
                )
                # Re-raise to maintain existing behavior
                raise

            # Move to next date batch
            current_start = current_end + timedelta(days=1)

        # Insert remaining records
        if batch_data:
            self._insert_trades_batch(batch_data, table_name)
            total_records += len(batch_data)

        return self.metrics.new_records

    def _ingest_open_trades(
        self,
        table_name: str,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
    ) -> int:
        """Ingest open trades data (typically much smaller volume)."""
        batch_data = []
        batch_size = 1000
        total_records = 0

        # For open trades, we typically only need the latest snapshot
        logger.info(f"Processing open trades for {end_date}")

        # Format date for API
        date_str = self.api_client.format_date(end_date)

        try:
            self.metrics.api_calls += 1
            for page_num, trades_page in enumerate(
                self.api_client.get_trades(
                    trade_type="open",
                    logins=logins,
                    symbols=symbols,
                    trade_date_from=date_str,
                    trade_date_to=date_str,
                )
            ):
                logger.info(
                    f"Processing page {page_num + 1} with {len(trades_page)} open trades"
                )

                for trade in trades_page:
                    # Validate trade if enabled
                    if self.enable_validation:
                        is_valid, errors = self._validate_trade_record(trade, "open")
                        if not is_valid:
                            self.metrics.invalid_records += 1
                            for error in errors:
                                self.metrics.validation_errors[error] += 1
                            logger.debug(
                                f"Invalid open trade {trade.get('position')}: {errors}"
                            )
                            continue

                    record = self._transform_open_trade(trade)
                    batch_data.append(record)
                    self.metrics.total_records += 1

                    if len(batch_data) >= batch_size:
                        self._insert_trades_batch(batch_data, table_name)
                        total_records += len(batch_data)
                        batch_data = []
        except Exception as e:
            self.metrics.api_errors += 1
            logger.error(f"API error for open trades on {end_date}: {str(e)}")
            # Re-raise to maintain existing behavior
            raise

        # Insert remaining records
        if batch_data:
            self._insert_trades_batch(batch_data, table_name)
            total_records += len(batch_data)

        return self.metrics.new_records

    def _transform_closed_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Transform closed trade record for database."""
        # Parse timestamps
        open_time = self._parse_timestamp(trade.get("openTime"))
        close_time = self._parse_timestamp(trade.get("closeTime"))

        # Parse trade date from ISO format (e.g. "2025-06-09T00:00:00.000Z")
        trade_date_str = trade.get("tradeDate", "")
        if trade_date_str:
            try:
                trade_date = datetime.strptime(trade_date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError, IndexError):
                trade_date = None
        else:
            trade_date = None

        return {
            "trade_date": trade_date,
            "broker": trade.get("broker"),
            "manager": trade.get("mngr"),
            "platform": trade.get("platform"),
            "ticket": trade.get("ticket"),
            "position": trade.get("position"),
            "login": trade.get("login"),
            "account_id": None,
            "std_symbol": trade.get("stdSymbol"),
            "side": trade.get("side"),
            "lots": self._safe_float(trade.get("lots")),
            "contract_size": trade.get("contractSize"),
            "qty_in_base_ccy": trade.get("qtyInBaseCrncy"),
            "volume_usd": self._safe_float(trade.get("volumeUSD")),
            "stop_loss": self._safe_float(trade.get("stopLoss")),
            "take_profit": self._safe_float(trade.get("takeProfit")),
            "open_time": open_time,
            "open_price": self._safe_float(trade.get("openPrice")),
            "close_time": close_time,
            "close_price": self._safe_float(trade.get("closePrice")),
            "duration": self._safe_float(trade.get("duration")),
            "profit": self._safe_float(trade.get("profit")),
            "commission": self._safe_float(trade.get("commission")),
            "fee": self._safe_float(trade.get("fee")),
            "swap": self._safe_float(trade.get("swap")),
            "comment": trade.get("comment"),
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/trades/closed",
        }

    def _transform_open_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Transform open trade record for database."""
        # Parse timestamps
        open_time = self._parse_timestamp(trade.get("openTime"))

        # Parse trade date from ISO format (e.g. "2025-06-09T00:00:00.000Z")
        trade_date_str = trade.get("tradeDate", "")
        if trade_date_str:
            try:
                trade_date = datetime.strptime(trade_date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError, IndexError):
                trade_date = None
        else:
            trade_date = None

        return {
            "trade_date": trade_date,
            "broker": trade.get("broker"),
            "manager": trade.get("mngr"),
            "platform": trade.get("platform"),
            "ticket": trade.get("ticket"),
            "position": trade.get("position"),
            "login": trade.get("login"),
            "account_id": None,
            "std_symbol": trade.get("stdSymbol"),
            "side": trade.get("side"),
            "lots": self._safe_float(trade.get("lots")),
            "contract_size": trade.get("contractSize"),
            "qty_in_base_ccy": trade.get("qtyInBaseCrncy"),
            "volume_usd": self._safe_float(trade.get("volumeUSD")),
            "stop_loss": self._safe_float(trade.get("stopLoss")),
            "take_profit": self._safe_float(trade.get("takeProfit")),
            "open_time": open_time,
            "open_price": self._safe_float(trade.get("openPrice")),
            "duration": self._safe_float(trade.get("duration")),
            "unrealized_profit": self._safe_float(trade.get("profit")),
            "commission": self._safe_float(trade.get("commission")),
            "fee": self._safe_float(trade.get("fee")),
            "swap": self._safe_float(trade.get("swap")),
            "comment": trade.get("comment"),
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/trades/open",
        }

    def _validate_trade_record(
        self, trade: Dict[str, Any], trade_type: str
    ) -> Tuple[bool, List[str]]:
        """Validate trade record and return validation errors."""
        errors = []

        # Required fields - updated to match actual API response
        required_fields = [
            "tradeDate",
            "broker",
            "mngr",
            "platform",
            "ticket",
            "position",
            "login",
            "trdSymbol",
            "stdSymbol",
            "side",
            "lots",
            "contractSize",
            "qtyInBaseCrncy",
            "volumeUSD",
            "stopLoss",
            "takeProfit",
            "openTime",
            "openPrice",
            "closeTime",
            "closePrice",
            "duration",
            "profit",
            "commission",
            "fee",
            "swap",
            "comment",
            "client_margin",
            "firm_margin",
        ]

        for field in required_fields:
            if field not in trade:
                errors.append(f"Missing required field: {field}")

        # Validate numeric fields
        if trade.get("lots") is not None:
            try:
                lots = float(trade["lots"])
                if lots <= 0:
                    errors.append("Lots must be positive")
            except (ValueError, TypeError):
                errors.append("Invalid lots value")

        # Validate side
        if trade.get("side") and str(trade["side"]).lower() not in ["Buy", "Sell", "buy", "sell", "BUY", "SELL"]:
            errors.append(f"Invalid side: {trade.get('side')}")

        # Validate timestamps
        if trade_type == "closed" and trade.get("openTime") and trade.get("closeTime"):
            open_time = self._parse_timestamp(trade["openTime"])
            close_time = self._parse_timestamp(trade["closeTime"])
            if open_time and close_time and close_time < open_time:
                errors.append("Close time cannot be before open time")

        return len(errors) == 0, errors

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert to float with validation."""
        if value is None:
            return None
        try:
            result = float(value)
            # Check for invalid values
            if result != result:  # NaN check
                return None
            if result == float("inf") or result == float("-inf"):
                return None
            return result
        except (ValueError, TypeError):
            return None

    def _batch_resolve_account_ids(self, table_name: str) -> int:
        """
        Batch resolve account IDs for trades that don't have them.
        Groups trades by (login, platform, broker) and looks up account_id from raw_metrics_alltime.
        Returns the number of trades updated.
        """
        try:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # First check if there are any trades needing resolution
                    cursor.execute(f"""
                        SELECT COUNT(*)
                        FROM {table_name}
                        WHERE account_id IS NULL
                        AND login IS NOT NULL
                        AND platform IS NOT NULL
                        AND broker IS NOT NULL
                        LIMIT 1
                    """)
                    
                    if cursor.fetchone()[0] == 0:
                        logger.info("No trades need account_id resolution")
                        return 0
                    
                    # Use a more efficient approach: join directly with raw_metrics_alltime
                    # This avoids loading all distinct combinations into memory
                    logger.info("Performing batch account_id resolution using direct UPDATE JOIN")
                    
                    cursor.execute(f"""
                        UPDATE {table_name} t
                        SET account_id = m.account_id
                        FROM raw_metrics_alltime m
                        WHERE t.login = m.login
                        AND t.platform = m.platform
                        AND t.broker = m.broker
                        AND t.account_id IS NULL
                        AND t.login IS NOT NULL
                        AND t.platform IS NOT NULL
                        AND t.broker IS NOT NULL
                    """)
                    
                    updated_count = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"Successfully updated account_id for {updated_count:,} trades")
                    
                    # Now check for any remaining trades without account_id (failed lookups)
                    cursor.execute(f"""
                        SELECT DISTINCT login, platform, broker
                        FROM {table_name}
                        WHERE account_id IS NULL
                        AND login IS NOT NULL
                        AND platform IS NOT NULL
                        AND broker IS NOT NULL
                        LIMIT 100
                    """)
                    
                    missing_mappings = cursor.fetchall()
                    
                    if missing_mappings:
                        logger.warning(
                            f"Found {len(missing_mappings)} unique (login, platform, broker) combinations "
                            f"without matching account_id in raw_metrics_alltime. "
                            f"These trades will remain without account_id."
                        )
                        # Log a sample of failed lookups for debugging
                        for login, platform, broker in missing_mappings[:5]:
                            logger.debug(f"No account_id found for: login={login}, platform={platform}, broker={broker}")
                        if len(missing_mappings) > 5:
                            logger.debug(f"... and {len(missing_mappings) - 5} more")
                    
                    # Validate that no (login, platform, broker) maps to multiple account_ids
                    logger.info("Validating account_id uniqueness constraints")
                    cursor.execute("""
                        SELECT login, platform, broker, COUNT(DISTINCT account_id) as account_count
                        FROM raw_metrics_alltime
                        WHERE login IS NOT NULL 
                        AND platform IS NOT NULL 
                        AND broker IS NOT NULL
                        GROUP BY login, platform, broker
                        HAVING COUNT(DISTINCT account_id) > 1
                        LIMIT 10
                    """)
                    
                    duplicates = cursor.fetchall()
                    if duplicates:
                        error_msg = "Multiple account_ids found for the following (login, platform, broker) combinations:\n"
                        for login, platform, broker, count in duplicates:
                            error_msg += f"  - login={login}, platform={platform}, broker={broker}: {count} account_ids\n"
                        raise AssertionError(error_msg)
                    
                    return updated_count
                    
        except Exception as e:
            logger.error(f"Failed to batch resolve account IDs: {str(e)}")
            raise

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse various timestamp formats from the API."""
        if not timestamp_str:
            return None

        # Try different formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y%m%d%H%M%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse timestamp: {timestamp_str}")
        return None

    def _save_checkpoint(self, trade_type: str, last_date: date):
        """Save current progress to checkpoint."""
        checkpoint_data = {
            "last_processed_date": str(last_date),
            "total_records": self.metrics.total_records,
            "new_records": self.metrics.new_records,
            "metrics": asdict(self.metrics),
        }
        self.checkpoint_manager.save_checkpoint(f"trades_{trade_type}", checkpoint_data)

    def _insert_trades_batch(
        self, batch_data: List[Dict[str, Any]], table_name: str
    ) -> bool:
        """Insert a batch of trade records into the database."""
        if not batch_data:
            return True

        new_records = 0  # Initialize to avoid reference error
        try:
            # Build the insert query
            columns = list(batch_data[0].keys())
            placeholders = ", ".join(["%s"] * len(columns))
            columns_str = ", ".join(columns)

            query = f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            """

            # Use ON CONFLICT to handle duplicates gracefully
            # Using composite key from schema: (platform, position, trade_date) for closed trades
            if table_name == "raw_trades_closed":
                query += """
                ON CONFLICT (platform, position, trade_date) DO NOTHING
                """
            else:
                # For open trades: (platform, position, ingestion_timestamp)
                query += """
                ON CONFLICT (platform, position, ingestion_timestamp) DO NOTHING
                """

            # Convert to list of tuples
            values = [tuple(record[col] for col in columns) for record in batch_data]

            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get count before insert
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    before_count = cursor.fetchone()[0]

                    # Insert batch
                    cursor.executemany(query, values)

                    # Get count after insert
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    after_count = cursor.fetchone()[0]

                    # Calculate new vs duplicate records
                    new_records = after_count - before_count
                    self.metrics.new_records += new_records
                    self.metrics.duplicate_records += len(batch_data) - new_records

            logger.debug(
                f"Inserted {new_records} new records from batch of {len(batch_data)}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to insert batch into {table_name}: {str(e)}")
            self.metrics.db_errors += 1
            # Log sample of problematic data for debugging
            if batch_data:
                logger.error(f"Sample record: {batch_data[0]}")
            return False

    def close(self):
        """Clean up resources."""
        self.api_client.close()


def ingest_trades_closed(**kwargs):
    """Convenience function for backward compatibility."""
    ingester = TradesIngester()
    try:
        return ingester.ingest_trades(trade_type="closed", **kwargs)
    finally:
        ingester.close()


def main():
    """Main function for command-line execution."""
    parser = argparse.ArgumentParser(
        description="Ingest trades data from Risk Analytics API"
    )
    parser.add_argument(
        "trade_type", choices=["closed", "open"], help="Type of trades to ingest"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="Start date for trades (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="End date for trades (YYYY-MM-DD)",
    )
    parser.add_argument("--logins", nargs="+", help="Specific login IDs to fetch")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to fetch")
    parser.add_argument(
        "--batch-days",
        type=int,
        default=7,
        help="Number of days to process at once for closed trades",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force full refresh (truncate and reload)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file=f"ingest_trades_{args.trade_type}")

    # Run ingestion
    ingester = TradesIngester()
    try:
        records = ingester.ingest_trades(
            trade_type=args.trade_type,
            start_date=args.start_date,
            end_date=args.end_date,
            logins=args.logins,
            symbols=args.symbols,
            batch_days=args.batch_days,
            force_full_refresh=args.force_refresh,
        )
        logger.info(f"Ingestion complete. Total records: {records}")
    finally:
        ingester.close()


if __name__ == "__main__":
    main()
