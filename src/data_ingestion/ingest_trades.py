"""
Trades ingester that only fetches missing data.
Based on the original trades ingester but with smart data fetching logic.
"""

import os
import sys
from datetime import datetime, timedelta, date, UTC as _UTC
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock as _ThreadLock
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.api_client import RiskAnalyticsAPIClient
from utils.logging_config import get_logger, setup_logging, set_request_context
from data_ingestion.base_ingester import BaseIngester, IngestionMetrics, CheckpointManager, timed_operation

logger = get_logger(__name__)


class TradeType(Enum):
    """Enum for trade types."""
    CLOSED = "closed"
    OPEN = "open"


class TradesIngester(BaseIngester):
    """
    Enhanced trades ingester that fetches only missing data.
    
    Key features:
    - Checks existing data before making API calls
    - Only fetches missing closed trades by date range
    - Handles open trades as daily snapshots
    - Automatically resolves account IDs after ingestion
    - Optimized for both date-range and full ingestion scenarios
    """

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        enable_validation: bool = True,
        enable_deduplication: bool = True,
    ):
        """Initialize the trades ingester."""
        # Initialize base class with a dummy table name
        super().__init__(
            ingestion_type="trades",
            table_name="raw_trades_closed",  # Will be overridden based on trade type
            checkpoint_dir=checkpoint_dir,
            enable_validation=enable_validation,
            enable_deduplication=enable_deduplication,
        )

        self.checkpoint_dir = checkpoint_dir
        self.enable_validation = enable_validation
        self.enable_deduplication = enable_deduplication

        # Configuration
        self.config = type('Config', (), {
            'batch_size': 5000,  # Larger batch for trades
            'max_retries': 3,
            'timeout': 30,
            'date_batch_days': 1,  # Days to process at once for closed trades
        })()

        # Thread-safety helper for shared metrics
        self._lock = _ThreadLock()

        # Initialize API client
        self.api_client = RiskAnalyticsAPIClient()

        # Table mapping
        self.table_mapping = {
            TradeType.CLOSED: "prop_trading_model.raw_trades_closed",
            TradeType.OPEN: "prop_trading_model.raw_trades_open",
        }

        # Initialize checkpoint managers and metrics per trade type
        self.checkpoint_managers = {}
        self.metrics_by_type = {}

        for trade_type in TradeType:
            checkpoint_file = os.path.join(
                checkpoint_dir or os.path.join(os.path.dirname(__file__), "checkpoints"),
                f"trades_{trade_type.value}_checkpoint.json",
            )
            self.checkpoint_managers[trade_type.value] = CheckpointManager(
                checkpoint_file, f"trades_{trade_type.value}"
            )
            self.metrics_by_type[trade_type.value] = IngestionMetrics()

    @timed_operation("trades_ingest_main")
    def ingest_trades(
        self,
        trade_type: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        logins: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        force_full_refresh: bool = False,
    ) -> Dict[str, int]:
        """
        Trades ingestion that only fetches missing data.
        
        Args:
            trade_type: 'closed' or 'open'
            start_date: Start date for ingestion
            end_date: End date for ingestion
            logins: Optional list of specific logins
            symbols: Optional list of specific symbols
            force_full_refresh: If True, ignore existing data
            
        Returns:
            Dictionary with ingestion results
        """
        if trade_type not in ["closed", "open"]:
            raise ValueError(f"Invalid trade type: {trade_type}")
            
        trade_type_enum = TradeType(trade_type)
        self.metrics = self.metrics_by_type[trade_type]
        self.checkpoint_manager = self.checkpoint_managers[trade_type]
        
        # Update current table name and logging context so logs reflect the correct trade type
        self.table_name = self.table_mapping[trade_type_enum]
        try:
            set_request_context(table_name=self.table_name)
        except Exception:
            # Fail silently if logging context utilities unavailable
            pass
        
        # Set default dates
        if not end_date:
            end_date = datetime.now(_UTC).date() - timedelta(days=1)
        if not start_date:
            # Auto-discover earliest trade date via API, else fallback 30d
            earliest_api_date = self._find_first_trade_date_api(trade_type, logins, symbols)
            if earliest_api_date:
                start_date = earliest_api_date
            else:
                start_date = end_date - timedelta(days=30)
                
        logger.info(f"Starting {trade_type} trades ingestion for {start_date} to {end_date}")
        
        try:
            results = {}
            
            if trade_type == "closed":
                results = self._ingest_closed_trades(
                    start_date, end_date, logins, symbols, force_full_refresh
                )
            else:
                results = self._ingest_open_trades(
                    start_date, end_date, logins, symbols, force_full_refresh
                )
            
            # Batch resolve account IDs after ingestion
            logger.info(f"Resolving account IDs for {trade_type} trades...")
            trades_updated = self._batch_resolve_account_ids(self.table_name)
            results["account_ids_resolved"] = trades_updated
            
            # Log summary
            self._log_summary(trade_type, results)
            return results
            
        except Exception as e:
            logger.error(f"{trade_type} trades ingestion failed: {str(e)}", exc_info=True)
            raise

    def _ingest_closed_trades(
        self,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
        force_full_refresh: bool,
    ) -> Dict[str, int]:
        """
        Ingest closed trades by checking existing data first.
        """
        total_records = 0
        
        # Get missing date ranges
        if force_full_refresh:
            logger.warning("Force full refresh requested - will re-fetch all data")
            missing_ranges = [(start_date, end_date)]
        else:
            missing_ranges = self._get_missing_closed_trade_date_ranges(
                start_date, end_date, logins, symbols
            )
        
        if not missing_ranges:
            logger.info("All closed trades data already exists for the specified criteria")
            return {"closed_trades": 0}
        
        logger.info(f"Found {len(missing_ranges)} date ranges with missing data")

        # Decide number of workers (I/O bound – don't exceed 8 to keep DB safe)
        max_workers = min(8, len(missing_ranges))

        if max_workers > 1:
            logger.info(f"Processing missing ranges in parallel with {max_workers} workers")

            def process_range(rng: Tuple[date, date]) -> int:
                """Worker helper – new ingester instance avoids shared-state conflicts."""
                sub_ing = TradesIngester(
                    checkpoint_dir=self.checkpoint_dir,
                    enable_validation=self.enable_validation,
                    enable_deduplication=self.enable_deduplication,
                )
                try:
                    recs = sub_ing._fetch_and_insert_closed_trades(
                        rng[0], rng[1], logins, symbols
                    )
                    return recs
                finally:
                    sub_ing.close()

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                _submit = getattr(executor, "submit")
                futures = {_submit(process_range, rng): rng for rng in missing_ranges}
                for fut in as_completed(futures):
                    rng = futures[fut]
                    try:
                        recs = fut.result()
                        total_records += recs
                        logger.info(f"Completed range {rng[0]} to {rng[1]} – {recs} records")
                    except Exception as exc:
                        logger.error(f"Range {rng} failed: {exc}")
        else:
            # Sequential fallback
            for range_start, range_end in missing_ranges:
                logger.info(f"Processing closed trades for {range_start} to {range_end}")
                records = self._fetch_and_insert_closed_trades(
                    range_start, range_end, logins, symbols
                )
                total_records += records
        
        return {"closed_trades": total_records}

    def _ingest_open_trades(
        self,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
        force_full_refresh: bool,
    ) -> Dict[str, int]:
        """
        Ingest open trades (daily snapshot).
        """
        # Determine which dates need snapshots
        if force_full_refresh:
            missing_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        else:
            missing_dates = self._get_missing_open_trade_dates(start_date, end_date, logins, symbols)

        if not missing_dates:
            logger.info("All open-trade snapshots are up to date for the specified window")
            return {"open_trades": 0}

        total_inserted = 0

        for day in missing_dates:
            logger.info(f"Fetching open trades snapshot for {day}")
            inserted = self._fetch_and_insert_open_trades(day, day, logins, symbols)
            total_inserted += inserted

        return {"open_trades": total_inserted}

    def _get_missing_closed_trade_date_ranges(
        self,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
    ) -> List[Tuple[date, date]]:
        """
        Get date ranges that are missing closed trades data.
        Enhanced with API count checking to detect partial data.
        Returns list of (start, end) date tuples for missing ranges.
        """
        missing_dates = []
        
        # Check each day in the range
        current_date = start_date
        while current_date <= end_date:
            # First, check API count
            date_str = self.api_client.format_date(current_date)
            api_count = self.api_client.get_trade_count(
                trade_type="closed",
                trade_date=date_str
            )
            
            # Get database count
            db_count_query = """
                SELECT COUNT(*) as count
                FROM prop_trading_model.raw_trades_closed
                WHERE trade_date = %s
            """
            
            # Add filters if specified
            params = [current_date]
            if logins:
                db_count_query += " AND login = ANY(%s)"
                params.append(logins)
            if symbols:
                db_count_query += " AND std_symbol = ANY(%s)"
                params.append(symbols)
            
            db_result = self.db_manager.model_db.execute_query(db_count_query, params)
            db_count = db_result[0]["count"] if db_result else 0
            
            # Determine if this date needs data
            if api_count < 0:
                # API error, fall back to checking if we have any data
                if db_count == 0:
                    missing_dates.append(current_date)
                    logger.debug(f"{current_date}: No data in DB (API check failed)")
            elif api_count == 0:
                # No trades for this date according to API
                logger.debug(f"{current_date}: No trades according to API")
            elif db_count < api_count:
                # We have fewer trades than API reports
                missing_dates.append(current_date)
                logger.debug(f"{current_date}: Partial data - have {db_count}/{api_count} trades")
            else:
                # We have all the data
                logger.debug(f"{current_date}: Complete - have all {db_count} trades")
            
            current_date += timedelta(days=1)
        
        # Group consecutive dates into ranges
        if not missing_dates:
            return []
            
        ranges = []
        range_start = missing_dates[0]
        prev_date = missing_dates[0]
        
        for current_date in missing_dates[1:]:
            if (current_date - prev_date).days > 1:
                # Gap found, close current range
                ranges.append((range_start, prev_date))
                range_start = current_date
            prev_date = current_date
        
        # Add final range
        ranges.append((range_start, prev_date))
        
        return ranges

    @timed_operation("trades_fetch_and_insert_closed")
    def _fetch_and_insert_closed_trades(
        self,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
    ) -> int:
        """
        Fetch closed trades from API and insert into database.
        Now includes smart checking to avoid fetching already-complete data.
        """
        batch_data = []
        total_records = 0
        
        # Process in smaller date chunks for better control
        current_start = start_date
        while current_start <= end_date:
            current_end = min(
                current_start + timedelta(days=self.config.date_batch_days - 1),
                end_date
            )
            
            # For single-day ranges, check if we already have all the data
            if current_start == current_end:
                # Get count from API
                date_str = self.api_client.format_date(current_start)
                api_count = self.api_client.get_trade_count(
                    trade_type="closed",
                    trade_date=date_str
                )
                
                if api_count >= 0:  # Valid count returned
                    # Get count from database
                    db_count_query = """
                        SELECT COUNT(*) as count
                        FROM prop_trading_model.raw_trades_closed
                        WHERE trade_date = %s
                    """
                    db_result = self.db_manager.model_db.execute_query(
                        db_count_query, [current_start]
                    )
                    db_count = db_result[0]["count"] if db_result else 0
                    
                    logger.info(
                        f"Trade count check for {current_start}: "
                        f"API={api_count}, DB={db_count}"
                    )
                    
                    # If counts match, skip this date
                    if api_count == db_count and api_count > 0:
                        logger.info(
                            f"Skipping {current_start} - already have all {api_count} trades"
                        )
                        current_start += timedelta(days=1)
                        continue
                    elif db_count > 0 and api_count > db_count:
                        logger.info(
                            f"Partial data for {current_start}: have {db_count}/{api_count} trades"
                        )
            
            logger.info(f"Fetching closed trades for {current_start} to {current_end}")
            
            try:
                # Format dates for API
                start_str = self.api_client.format_date(current_start)
                end_str = self.api_client.format_date(current_end)
                
                for page_num, trades_page in enumerate(
                    self.api_client.get_trades(
                        trade_type="closed",
                        logins=logins,
                        symbols=symbols,
                        trade_date_from=start_str,
                        trade_date_to=end_str,
                    )
                ):
                    logger.info(f"Processing page {page_num + 1} with {len(trades_page)} trades")
                    
                    for trade in trades_page:
                        # Validate if enabled
                        if self.enable_validation:
                            is_valid, errors = self._validate_trade_record(trade, "closed")
                            if not is_valid:
                                with self._lock:
                                    self.metrics.invalid_records += 1
                                logger.debug(f"Invalid trade: {errors}")
                                continue
                        
                        # Transform and add to batch
                        record = self._transform_closed_trade(trade)
                        batch_data.append(record)
                        with self._lock:
                            self.metrics.total_records += 1
                        
                        # Insert when batch is full
                        if len(batch_data) >= self.config.batch_size:
                            self._insert_trades_batch(batch_data, TradeType.CLOSED)
                            total_records += len(batch_data)
                            batch_data = []
                            
                            # Log progress
                            if self.metrics.total_records % 10000 == 0:
                                logger.info(f"Progress: {self.metrics.total_records:,} records processed")
                
                # Save checkpoint
                self.checkpoint_manager.save_checkpoint({
                    "last_processed_date": str(current_end),
                    "total_records": self.metrics.total_records,
                    "new_records": self.metrics.new_records,
                })
                
            except Exception as e:
                logger.error(f"Error fetching closed trades: {str(e)}")
                raise
            
            current_start = current_end + timedelta(days=1)
        
        # Insert remaining records
        if batch_data:
            self._insert_trades_batch(batch_data, TradeType.CLOSED)
            total_records += len(batch_data)
        
        return self.metrics.new_records

    def _fetch_and_insert_open_trades(
        self,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
    ) -> int:
        """
        Fetch open trades from API and insert into database.
        Now includes smart checking to avoid fetching already-complete data.
        """
        batch_data = []
        total_records = 0
        
        # For single-day ranges, check if we already have all the data
        if start_date == end_date:
            # Get count from API
            date_str = self.api_client.format_date(start_date)
            api_count = self.api_client.get_trade_count(
                trade_type="open",
                trade_date=date_str
            )
            
            if api_count >= 0:  # Valid count returned
                # Get count from database
                db_count_query = """
                    SELECT COUNT(*) as count
                    FROM prop_trading_model.raw_trades_open
                    WHERE trade_date = %s
                """
                db_result = self.db_manager.model_db.execute_query(
                    db_count_query, [start_date]
                )
                db_count = db_result[0]["count"] if db_result else 0
                
                logger.info(
                    f"Open trade count check for {start_date}: "
                    f"API={api_count}, DB={db_count}"
                )
                
                # If counts match, skip this date
                if api_count == db_count and api_count > 0:
                    logger.info(
                        f"Skipping {start_date} - already have all {api_count} open trades"
                    )
                    return 0
        
        try:
            # Format dates for API
            start_str = self.api_client.format_date(start_date)
            end_str = self.api_client.format_date(end_date)
            
            logger.info(f"Fetching open trades for {start_date} to {end_date}")
            
            for page_num, trades_page in enumerate(
                self.api_client.get_trades(
                    trade_type="open",
                    logins=logins,
                    symbols=symbols,
                    trade_date_from=start_str,
                    trade_date_to=end_str,
                )
            ):
                logger.info(f"Processing page {page_num + 1} with {len(trades_page)} trades")
                
                for trade in trades_page:
                    # Validate if enabled
                    if self.enable_validation:
                        is_valid, errors = self._validate_trade_record(trade, "open")
                        if not is_valid:
                            with self._lock:
                                self.metrics.invalid_records += 1
                            logger.debug(f"Invalid trade: {errors}")
                            continue
                    
                    # Transform and add to batch
                    record = self._transform_open_trade(trade)
                    batch_data.append(record)
                    with self._lock:
                        self.metrics.total_records += 1
                    
                    # Insert when batch is full
                    if len(batch_data) >= self.config.batch_size:
                        self._insert_trades_batch(batch_data, TradeType.OPEN)
                        total_records += len(batch_data)
                        batch_data = []
            
            # Insert remaining records
            if batch_data:
                self._insert_trades_batch(batch_data, TradeType.OPEN)
                total_records += len(batch_data)
                
        except Exception as e:
            logger.error(f"Error fetching open trades: {str(e)}")
            raise
        
        return self.metrics.new_records

    @timed_operation("trades_insert_batch")
    def _insert_trades_batch(self, batch_data: List[Dict[str, Any]], trade_type: TradeType) -> int:
        """Insert batch with proper ON CONFLICT handling."""
        if not batch_data:
            return 0
            
        table_name = self.table_mapping[trade_type]
        
        try:
            columns = list(batch_data[0].keys())
            placeholders = ", ".join(["%s"] * len(columns))
            columns_str = ", ".join(columns)
            
            # Build ON CONFLICT clause
            if trade_type == TradeType.CLOSED:
                conflict_clause = """
                ON CONFLICT (platform, position, trade_date) DO UPDATE SET
                    manager = EXCLUDED.manager,
                    ticket = EXCLUDED.ticket,
                    account_id = EXCLUDED.account_id,
                    std_symbol = EXCLUDED.std_symbol,
                    side = EXCLUDED.side,
                    lots = EXCLUDED.lots,
                    contract_size = EXCLUDED.contract_size,
                    qty_in_base_ccy = EXCLUDED.qty_in_base_ccy,
                    volume_usd = EXCLUDED.volume_usd,
                    stop_loss = EXCLUDED.stop_loss,
                    take_profit = EXCLUDED.take_profit,
                    open_time = EXCLUDED.open_time,
                    open_price = EXCLUDED.open_price,
                    close_time = EXCLUDED.close_time,
                    close_price = EXCLUDED.close_price,
                    duration = EXCLUDED.duration,
                    profit = EXCLUDED.profit,
                    commission = EXCLUDED.commission,
                    fee = EXCLUDED.fee,
                    swap = EXCLUDED.swap,
                    comment = EXCLUDED.comment,
                    ingestion_timestamp = EXCLUDED.ingestion_timestamp,
                    source_api_endpoint = EXCLUDED.source_api_endpoint
                """
            else:  # OPEN
                conflict_clause = """
                ON CONFLICT (platform, position, trade_date) DO UPDATE SET
                    manager = EXCLUDED.manager,
                    ticket = EXCLUDED.ticket,
                    account_id = EXCLUDED.account_id,
                    std_symbol = EXCLUDED.std_symbol,
                    side = EXCLUDED.side,
                    lots = EXCLUDED.lots,
                    contract_size = EXCLUDED.contract_size,
                    qty_in_base_ccy = EXCLUDED.qty_in_base_ccy,
                    volume_usd = EXCLUDED.volume_usd,
                    stop_loss = EXCLUDED.stop_loss,
                    take_profit = EXCLUDED.take_profit,
                    open_time = EXCLUDED.open_time,
                    open_price = EXCLUDED.open_price,
                    duration = EXCLUDED.duration,
                    unrealized_profit = EXCLUDED.unrealized_profit,
                    commission = EXCLUDED.commission,
                    fee = EXCLUDED.fee,
                    swap = EXCLUDED.swap,
                    comment = EXCLUDED.comment,
                    ingestion_timestamp = EXCLUDED.ingestion_timestamp,
                    source_api_endpoint = EXCLUDED.source_api_endpoint
                """
            
            query = f"""
                INSERT INTO {table_name} ({columns_str})
                VALUES ({placeholders})
                {conflict_clause}
            """
            
            values = [
                tuple(record[col] for col in columns) for record in batch_data
            ]
            
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    from psycopg2.extras import execute_batch
                    execute_batch(cursor, query, values, page_size=1000)
                    rows_affected = cursor.rowcount
                    conn.commit()
                    
            # Update metrics
            with self._lock:
                self.metrics.new_records += len(batch_data)
            logger.debug(f"Inserted/updated {rows_affected} records into {table_name}")
            return len(batch_data)
            
        except Exception as e:
            logger.error(f"Failed to insert batch: {str(e)}")
            raise

    @timed_operation("trades_batch_resolve_account_ids")
    def _batch_resolve_account_ids(self, table_name: str) -> int:
        """
        Batch resolve account IDs for trades that don't have them.
        Groups trades by (login, platform, broker) and looks up account_id from raw_metrics_alltime.
        Returns the number of trades updated.
        """
        try:
            with self.db_manager.model_db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Set a longer timeout for this operation (30 minutes)
                    cursor.execute("SET statement_timeout = '1800000'")  # 30 minutes in milliseconds
                    # First check if there are any trades needing resolution
                    cursor.execute(f"""
                        SELECT COUNT(*)
                        FROM {table_name}
                        WHERE account_id IS NULL
                        AND login IS NOT NULL
                        AND platform IS NOT NULL
                        AND broker IS NOT NULL
                    """)
                    
                    total_null_count = cursor.fetchone()[0]
                    if total_null_count == 0:
                        logger.info("No trades need account_id resolution")
                        return 0
                    
                    logger.info(f"Found {total_null_count:,} trades needing account_id resolution")
                    
                    # Process in batches to avoid statement timeout
                    batch_size = 50000  # Process 50K rows at a time (reduced for better performance)
                    total_updated = 0
                    batch_num = 0
                    
                    # Create an index if it doesn't exist to speed up the lookup
                    try:
                        cursor.execute(f"""
                            CREATE INDEX IF NOT EXISTS idx_{table_name.split('.')[-1]}_account_lookup 
                            ON {table_name} (login, platform, broker) 
                            WHERE account_id IS NULL
                        """)
                        conn.commit()
                    except Exception as e:
                        logger.warning(f"Could not create index: {e}")
                        conn.rollback()
                    
                    while True:
                        batch_num += 1
                        
                        # First, create a temporary table with the batch of rows to update
                        cursor.execute(f"""
                            CREATE TEMP TABLE IF NOT EXISTS batch_update_{batch_num} AS
                            SELECT ctid AS row_ctid, login, platform, broker
                            FROM {table_name}
                            WHERE account_id IS NULL
                            AND login IS NOT NULL
                            AND platform IS NOT NULL
                            AND broker IS NOT NULL
                            LIMIT {batch_size}
                        """)
                        
                        # Check if we got any rows
                        cursor.execute(f"SELECT COUNT(*) FROM batch_update_{batch_num}")
                        batch_count = cursor.fetchone()[0]
                        
                        if batch_count == 0:
                            cursor.execute(f"DROP TABLE IF EXISTS batch_update_{batch_num}")
                            break
                        
                        # Update using the temporary table
                        cursor.execute(f"""
                            UPDATE {table_name} t
                            SET account_id = m.account_id
                            FROM batch_update_{batch_num} b
                            JOIN prop_trading_model.raw_metrics_alltime m
                                ON b.login = m.login
                                AND b.platform = m.platform
                                AND b.broker = m.broker
                            WHERE t.ctid = b.row_ctid
                        """)
                        
                        # Get the row count immediately after UPDATE
                        batch_updated = cursor.rowcount
                        
                        # Clean up temp table
                        cursor.execute(f"DROP TABLE batch_update_{batch_num}")
                    
                        # Handle the case where rowcount might be -1 (indeterminate)
                        if batch_updated < 0:
                            logger.warning(f"Batch {batch_num}: Row count indeterminate, assuming batch size was processed")
                            # When rowcount is -1, we can't determine exact count, but we know we processed batch_count rows
                            batch_updated = batch_count
                        
                        if batch_updated == 0:
                            break
                        
                        total_updated += batch_updated
                        conn.commit()
                        
                        logger.info(
                            f"Batch {batch_num}: Updated {batch_updated:,} trades "
                            f"(total: {total_updated:,})"
                        )
                        
                        # Small delay to prevent overwhelming the database
                        if batch_updated == batch_size:
                            time.sleep(0.1)
                    
                    logger.info(f"Successfully updated account_id for {total_updated:,} trades total")
                    
                    # Check for any remaining trades without account_id
                    cursor.execute(f"""
                        SELECT COUNT(DISTINCT (login, platform, broker))
                        FROM {table_name}
                        WHERE account_id IS NULL
                        AND login IS NOT NULL
                        AND platform IS NOT NULL
                        AND broker IS NOT NULL
                    """)
                    
                    missing_count = cursor.fetchone()[0]
                    if missing_count > 0:
                        logger.warning(
                            f"Found {missing_count} unique (login, platform, broker) combinations "
                            f"without matching account_id in raw_metrics_alltime"
                        )
                    
                    return total_updated
                    
        except Exception as e:
            logger.error(f"Failed to batch resolve account IDs: {str(e)}")
            raise

    def _transform_closed_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Transform closed trade record for database."""
        # Parse timestamps
        open_time = self._parse_timestamp(trade.get("openTime"))
        close_time = self._parse_timestamp(trade.get("closeTime"))

        # Parse trade date
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
            "account_id": None,  # Will be resolved later
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

        # Parse trade date
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
            "account_id": None,  # Will be resolved later
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
            "unrealized_profit": self._safe_float(trade.get("profit")),  # profit -> unrealized_profit
            "commission": self._safe_float(trade.get("commission")),
            "fee": self._safe_float(trade.get("fee")),
            "swap": self._safe_float(trade.get("swap")),
            "comment": trade.get("comment"),
            "ingestion_timestamp": datetime.now(),
            "source_api_endpoint": "/v2/trades/open",
        }

    def _validate_trade_record(self, trade: Dict[str, Any], trade_type: str) -> Tuple[bool, List[str]]:
        """Validate trade record and return validation errors."""
        errors = []

        # Required fields
        required_fields = [
            "tradeDate",
            "platform",
            "position",
            "login",
            "side",
            "openTime",
            "openPrice",
        ]
        
        # For closed trades, also require close fields
        if trade_type == "closed":
            required_fields.extend(["closeTime", "closePrice"])

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
        if trade.get("side"):
            side_lower = str(trade["side"]).lower()
            if side_lower not in ["buy", "sell"]:
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

    def _log_summary(self, trade_type: str, results: Dict[str, int]):
        """Log ingestion summary."""
        total_records = results.get(f"{trade_type}_trades", 0)
        account_ids_resolved = results.get("account_ids_resolved", 0)
        
        logger.info(f"\n{'=' * 60}")
        logger.info(f"{trade_type.upper()} TRADES INGESTION SUMMARY")
        logger.info(f"{'=' * 60}")
        logger.info(f"New records ingested: {total_records}")
        logger.info(f"Account IDs resolved: {account_ids_resolved}")
        if self.metrics:
            logger.info(f"Invalid records skipped: {self.metrics.invalid_records}")

    def close(self):
        """Close the ingester and clean up resources."""
        try:
            if hasattr(self.api_client, 'close'):
                self.api_client.close()
        except Exception as e:
            logger.error(f"Error closing API client: {str(e)}")

        # Clean up database connections if available
        try:
            if hasattr(self, 'db_manager') and hasattr(self.db_manager, 'close'):
                self.db_manager.close()
        except Exception as e:
            logger.error(f"Error closing database manager: {str(e)}")

    def _find_first_trade_date_api(
        self,
        trade_type: str,
        logins: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        max_years: int = 10,
    ) -> Optional[date]:
        """Discover the earliest trade_date available from the API.

        Fetches in 1-year windows moving backward until no data is found or
        the max_years limit is reached.  Uses limit=1 for speed.
        Returns the earliest date seen, or None on failure.
        """
        try:
            today = datetime.now(_UTC).date()
            earliest_seen: Optional[date] = None

            for year_back in range(max_years):
                to_date = today - timedelta(days=year_back * 365)
                from_date = to_date - timedelta(days=364)

                # Format for API (YYYYMMDD)
                from_str = self.api_client.format_date(from_date)
                to_str = self.api_client.format_date(to_date)

                pages = self.api_client.get_trades(
                    trade_type=trade_type,
                    logins=logins,
                    symbols=symbols,
                    trade_date_from=from_str,
                    trade_date_to=to_str,
                    limit=1,
                )
                try:
                    first_page = next(pages)
                except StopIteration:
                    first_page = []

                if not first_page:
                    # No data in this window – if we've already seen data,
                    # we can stop searching.
                    if earliest_seen is not None:
                        break
                    continue

                # Extract trade_date from the single record
                rec_date_str = first_page[0].get("tradeDate")
                if rec_date_str:
                    try:
                        rec_date = datetime.strptime(rec_date_str[:10], "%Y-%m-%d").date()
                        if earliest_seen is None or rec_date < earliest_seen:
                            earliest_seen = rec_date
                    except Exception:
                        pass

            return earliest_seen
        except Exception as e:
            logger.error(f"Failed to discover earliest trade date via API: {e}")
            return None

    def _get_missing_open_trade_dates(
        self,
        start_date: date,
        end_date: date,
        logins: Optional[List[str]],
        symbols: Optional[List[str]],
    ) -> List[date]:
        """
        Return individual dates between start_date and end_date for which we have incomplete open-trade snapshot.
        Enhanced with API count checking to detect partial data.
        """
        missing_dates = []
        
        # Check each day in the range
        current_date = start_date
        while current_date <= end_date:
            # First, check API count
            date_str = self.api_client.format_date(current_date)
            api_count = self.api_client.get_trade_count(
                trade_type="open",
                trade_date=date_str
            )
            
            # Get database count
            db_count_query = """
                SELECT COUNT(*) as count
                FROM prop_trading_model.raw_trades_open
                WHERE trade_date = %s
            """
            
            # Add filters if specified
            params = [current_date]
            if logins:
                db_count_query += " AND login = ANY(%s)"
                params.append(logins)
            if symbols:
                db_count_query += " AND std_symbol = ANY(%s)"
                params.append(symbols)
            
            db_result = self.db_manager.model_db.execute_query(db_count_query, params)
            db_count = db_result[0]["count"] if db_result else 0
            
            # Determine if this date needs data
            if api_count < 0:
                # API error, fall back to checking if we have any data
                if db_count == 0:
                    missing_dates.append(current_date)
                    logger.debug(f"{current_date}: No open trades in DB (API check failed)")
            elif api_count == 0:
                # No trades for this date according to API
                logger.debug(f"{current_date}: No open trades according to API")
            elif db_count < api_count:
                # We have fewer trades than API reports
                missing_dates.append(current_date)
                logger.debug(f"{current_date}: Partial open trades - have {db_count}/{api_count}")
            else:
                # We have all the data
                logger.debug(f"{current_date}: Complete - have all {db_count} open trades")
            
            current_date += timedelta(days=1)
        
        return missing_dates


def main():
    """Main function for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Trades ingestion - only fetches missing data"
    )
    
    parser.add_argument(
        "trade_type",
        choices=["closed", "open"],
        help="Type of trades to ingest",
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
        "--logins",
        nargs="+",
        help="Specific login IDs to fetch",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to fetch",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force full refresh (ignore existing data)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(log_level=args.log_level, log_file=f"trades_{args.trade_type}", enable_json=False, enable_structured=False)

    # Run ingestion
    ingester = TradesIngester()

    try:
        ingester.ingest_trades(
            trade_type=args.trade_type,
            start_date=args.start_date,
            end_date=args.end_date,
            logins=args.logins,
            symbols=args.symbols,
            force_full_refresh=args.force_refresh,
        )
        
        logger.info("Trades ingestion complete")
        
    except Exception as e:
        logger.error(f"Ingestion failed: {str(e)}", exc_info=True)
        raise
    finally:
        ingester.close()


if __name__ == "__main__":
    main()