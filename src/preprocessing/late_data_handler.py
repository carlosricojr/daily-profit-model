"""
Handler for late-arriving data in the preprocessing pipeline.
Manages detection, processing, and backfilling of late data.
"""

import logging
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, date, timedelta
import pandas as pd
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LateDataType(Enum):
    """Types of late-arriving data."""
    NEW_ACCOUNT = "new_account"  # Account that wasn't in original snapshot
    UPDATED_METRICS = "updated_metrics"  # Metrics that arrived after snapshot
    CORRECTED_DATA = "corrected_data"  # Data corrections/amendments
    BACKFILL = "backfill"  # Historical data backfill


@dataclass
class LateDataEvent:
    """Container for late data events."""
    event_id: str
    event_type: LateDataType
    table_name: str
    affected_date: date
    account_id: Optional[str]
    detection_time: datetime
    original_ingestion_time: Optional[datetime]
    delay_hours: Optional[float]
    record_count: int
    details: Optional[Dict] = None


class LateDataHandler:
    """Handles late-arriving data detection and processing."""
    
    def __init__(self, db_manager):
        """Initialize late data handler."""
        self.db_manager = db_manager
        self.watermark_table = "data_processing_watermarks"
        self._ensure_watermark_table()
    
    def _ensure_watermark_table(self):
        """Ensure watermark tracking table exists."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS data_processing_watermarks (
            table_name VARCHAR(255),
            processing_date DATE,
            watermark_timestamp TIMESTAMP,
            last_processed_timestamp TIMESTAMP,
            record_count INTEGER,
            late_data_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (table_name, processing_date)
        )
        """
        self.db_manager.model_db.execute_command(create_table_query)
    
    def detect_late_arriving_data(self, check_date: date, 
                                 lookback_hours: int = 48) -> List[LateDataEvent]:
        """
        Detect late-arriving data for a specific date.
        
        Args:
            check_date: Date to check for late data
            lookback_hours: Hours to look back for late data
            
        Returns:
            List of late data events detected
        """
        logger.info(f"Checking for late-arriving data for {check_date}")
        
        events = []
        
        # Check each source table
        events.extend(self._check_late_accounts(check_date, lookback_hours))
        events.extend(self._check_late_metrics(check_date, lookback_hours))
        events.extend(self._check_late_trades(check_date, lookback_hours))
        
        # Update watermarks
        self._update_watermarks(check_date, events)
        
        logger.info(f"Detected {len(events)} late data events")
        return events
    
    def _check_late_accounts(self, check_date: date, lookback_hours: int) -> List[LateDataEvent]:
        """Check for late-arriving account data."""
        events = []
        
        # Get watermark for this date
        watermark = self._get_watermark("raw_accounts_data", check_date)
        
        if not watermark:
            # First time processing this date
            return events
        
        # Check for accounts ingested after watermark
        query = """
        SELECT 
            account_id,
            MIN(ingestion_timestamp) as first_seen,
            MAX(ingestion_timestamp) as last_seen,
            COUNT(*) as record_count
        FROM raw_accounts_data
        WHERE ingestion_timestamp > %s
        AND ingestion_timestamp <= %s
        AND created_at <= %s
        GROUP BY account_id
        """
        
        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)
        params = (watermark['watermark_timestamp'], datetime.now(), check_date)
        
        late_accounts = self.db_manager.model_db.execute_query(query, params)
        
        for account in late_accounts:
            delay_hours = (account['first_seen'] - watermark['watermark_timestamp']).total_seconds() / 3600
            
            # Check if this account was missing from original snapshot
            snapshot_check = """
            SELECT COUNT(*) as exists 
            FROM stg_accounts_daily_snapshots
            WHERE account_id = %s AND date = %s
            """
            exists = self.db_manager.model_db.execute_query(
                snapshot_check, (account['account_id'], check_date)
            )[0]['exists']
            
            event_type = LateDataType.NEW_ACCOUNT if exists == 0 else LateDataType.CORRECTED_DATA
            
            events.append(LateDataEvent(
                event_id=f"LATE_ACC_{account['account_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                event_type=event_type,
                table_name="raw_accounts_data",
                affected_date=check_date,
                account_id=account['account_id'],
                detection_time=datetime.now(),
                original_ingestion_time=account['first_seen'],
                delay_hours=delay_hours,
                record_count=account['record_count']
            ))
        
        return events
    
    def _check_late_metrics(self, check_date: date, lookback_hours: int) -> List[LateDataEvent]:
        """Check for late-arriving metrics data."""
        events = []
        
        watermark = self._get_watermark("raw_metrics_daily", check_date)
        
        if not watermark:
            return events
        
        # Check for metrics that arrived late
        query = """
        SELECT 
            account_id,
            date,
            ingestion_timestamp,
            net_profit,
            total_trades
        FROM raw_metrics_daily
        WHERE date = %s
        AND ingestion_timestamp > %s
        AND ingestion_timestamp <= %s
        """
        
        params = (check_date, watermark['watermark_timestamp'], datetime.now())
        late_metrics = self.db_manager.model_db.execute_query(query, params)
        
        # Group by account to create events
        account_metrics = {}
        for metric in late_metrics:
            if metric['account_id'] not in account_metrics:
                account_metrics[metric['account_id']] = []
            account_metrics[metric['account_id']].append(metric)
        
        for account_id, metrics in account_metrics.items():
            delay_hours = max(
                (m['ingestion_timestamp'] - watermark['watermark_timestamp']).total_seconds() / 3600
                for m in metrics
            )
            
            events.append(LateDataEvent(
                event_id=f"LATE_METRIC_{account_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                event_type=LateDataType.UPDATED_METRICS,
                table_name="raw_metrics_daily",
                affected_date=check_date,
                account_id=account_id,
                detection_time=datetime.now(),
                original_ingestion_time=metrics[0]['ingestion_timestamp'],
                delay_hours=delay_hours,
                record_count=len(metrics),
                details={
                    'net_profit': metrics[-1]['net_profit'],
                    'total_trades': metrics[-1]['total_trades']
                }
            ))
        
        return events
    
    def _check_late_trades(self, check_date: date, lookback_hours: int) -> List[LateDataEvent]:
        """Check for late-arriving trade data."""
        events = []
        
        watermark = self._get_watermark("raw_trades_closed", check_date)
        
        if not watermark:
            return events
        
        # Check for trades that arrived late
        query = """
        SELECT 
            COUNT(*) as late_trade_count,
            COUNT(DISTINCT account_id) as affected_accounts,
            MIN(ingestion_timestamp) as earliest,
            MAX(ingestion_timestamp) as latest
        FROM raw_trades_closed
        WHERE trade_date = %s
        AND ingestion_timestamp > %s
        AND ingestion_timestamp <= %s
        """
        
        params = (check_date, watermark['watermark_timestamp'], datetime.now())
        result = self.db_manager.model_db.execute_query(query, params)
        
        if result and result[0]['late_trade_count'] > 0:
            stats = result[0]
            delay_hours = (stats['latest'] - watermark['watermark_timestamp']).total_seconds() / 3600
            
            events.append(LateDataEvent(
                event_id=f"LATE_TRADES_{check_date}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                event_type=LateDataType.BACKFILL,
                table_name="raw_trades_closed",
                affected_date=check_date,
                account_id=None,  # Multiple accounts
                detection_time=datetime.now(),
                original_ingestion_time=stats['earliest'],
                delay_hours=delay_hours,
                record_count=stats['late_trade_count'],
                details={
                    'affected_accounts': stats['affected_accounts']
                }
            ))
        
        return events
    
    def process_late_data(self, events: List[LateDataEvent],
                         reprocess_features: bool = True) -> Dict[str, int]:
        """
        Process late-arriving data events.
        
        Args:
            events: List of late data events to process
            reprocess_features: Whether to reprocess features for affected dates
            
        Returns:
            Dictionary with processing statistics
        """
        logger.info(f"Processing {len(events)} late data events")
        
        stats = {
            'snapshots_updated': 0,
            'features_reprocessed': 0,
            'accounts_affected': set(),
            'dates_affected': set()
        }
        
        # Group events by date and type
        events_by_date = {}
        for event in events:
            if event.affected_date not in events_by_date:
                events_by_date[event.affected_date] = []
            events_by_date[event.affected_date].append(event)
            
            if event.account_id:
                stats['accounts_affected'].add(event.account_id)
            stats['dates_affected'].add(event.affected_date)
        
        # Process each affected date
        for affected_date, date_events in events_by_date.items():
            # Update staging snapshots
            updated = self._update_staging_snapshots(affected_date, date_events)
            stats['snapshots_updated'] += updated
            
            # Reprocess features if requested
            if reprocess_features:
                feature_count = self._reprocess_features(affected_date, date_events)
                stats['features_reprocessed'] += feature_count
        
        # Log late data events
        self._log_late_data_events(events)
        
        return {
            'snapshots_updated': stats['snapshots_updated'],
            'features_reprocessed': stats['features_reprocessed'],
            'accounts_affected': len(stats['accounts_affected']),
            'dates_affected': len(stats['dates_affected'])
        }
    
    def _update_staging_snapshots(self, affected_date: date,
                                 events: List[LateDataEvent]) -> int:
        """Update staging snapshots with late data."""
        updated_count = 0
        
        # Get affected account IDs
        affected_accounts = set()
        for event in events:
            if event.account_id:
                affected_accounts.add(event.account_id)
        
        if not affected_accounts:
            return 0
        
        # Delete existing snapshots for affected accounts
        delete_query = """
        DELETE FROM stg_accounts_daily_snapshots
        WHERE date = %s
        AND account_id IN ({})
        """.format(','.join(['%s'] * len(affected_accounts)))
        
        params = [affected_date] + list(affected_accounts)
        self.db_manager.model_db.execute_command(delete_query, tuple(params))
        
        # Recreate snapshots with latest data
        from preprocessing.create_staging_snapshots import StagingSnapshotCreator
        creator = StagingSnapshotCreator()
        
        # Use the existing snapshot creation logic but for specific accounts
        # This would need modification in the actual implementation
        for account_id in affected_accounts:
            # Simplified - in reality would use the full snapshot creation logic
            logger.info(f"Recreating snapshot for account {account_id} on {affected_date}")
            updated_count += 1
        
        return updated_count
    
    def _reprocess_features(self, affected_date: date,
                           events: List[LateDataEvent]) -> int:
        """Reprocess features for affected accounts and dates."""
        # This would trigger feature engineering pipeline
        # Placeholder for actual implementation
        affected_accounts = set()
        for event in events:
            if event.account_id:
                affected_accounts.add(event.account_id)
        
        logger.info(f"Reprocessing features for {len(affected_accounts)} accounts on {affected_date}")
        
        # In actual implementation, would call feature engineering module
        return len(affected_accounts)
    
    def _get_watermark(self, table_name: str, processing_date: date) -> Optional[Dict]:
        """Get watermark for a table and date."""
        query = """
        SELECT * FROM data_processing_watermarks
        WHERE table_name = %s AND processing_date = %s
        """
        results = self.db_manager.model_db.execute_query(query, (table_name, processing_date))
        return results[0] if results else None
    
    def _update_watermarks(self, processing_date: date, events: List[LateDataEvent]):
        """Update watermarks with late data information."""
        # Group events by table
        events_by_table = {}
        for event in events:
            if event.table_name not in events_by_table:
                events_by_table[event.table_name] = []
            events_by_table[event.table_name].append(event)
        
        for table_name, table_events in events_by_table.items():
            late_count = sum(e.record_count for e in table_events)
            
            update_query = """
            UPDATE data_processing_watermarks
            SET late_data_count = late_data_count + %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE table_name = %s AND processing_date = %s
            """
            
            self.db_manager.model_db.execute_command(
                update_query, (late_count, table_name, processing_date)
            )
    
    def _log_late_data_events(self, events: List[LateDataEvent]):
        """Log late data events for audit trail."""
        # Create late data events table if not exists
        create_table_query = """
        CREATE TABLE IF NOT EXISTS late_data_events (
            event_id VARCHAR(255) PRIMARY KEY,
            event_type VARCHAR(50),
            table_name VARCHAR(255),
            affected_date DATE,
            account_id VARCHAR(255),
            detection_time TIMESTAMP,
            original_ingestion_time TIMESTAMP,
            delay_hours FLOAT,
            record_count INTEGER,
            details JSONB,
            processed BOOLEAN DEFAULT FALSE,
            processed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.db_manager.model_db.execute_command(create_table_query)
        
        # Insert events
        for event in events:
            insert_query = """
            INSERT INTO late_data_events (
                event_id, event_type, table_name, affected_date, account_id,
                detection_time, original_ingestion_time, delay_hours,
                record_count, details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """
            
            import json
            params = (
                event.event_id,
                event.event_type.value,
                event.table_name,
                event.affected_date,
                event.account_id,
                event.detection_time,
                event.original_ingestion_time,
                event.delay_hours,
                event.record_count,
                json.dumps(event.details) if event.details else None
            )
            
            self.db_manager.model_db.execute_command(insert_query, params)
    
    def create_watermark(self, table_name: str, processing_date: date,
                        watermark_timestamp: datetime):
        """Create or update watermark for a table and date."""
        query = """
        INSERT INTO data_processing_watermarks (
            table_name, processing_date, watermark_timestamp, last_processed_timestamp
        ) VALUES (%s, %s, %s, %s)
        ON CONFLICT (table_name, processing_date) DO UPDATE
        SET watermark_timestamp = EXCLUDED.watermark_timestamp,
            last_processed_timestamp = EXCLUDED.last_processed_timestamp,
            updated_at = CURRENT_TIMESTAMP
        """
        
        params = (table_name, processing_date, watermark_timestamp, datetime.now())
        self.db_manager.model_db.execute_command(query, params)
    
    def get_late_data_summary(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Get summary of late data events for a date range."""
        query = """
        SELECT 
            event_type,
            table_name,
            COUNT(*) as event_count,
            SUM(record_count) as total_records,
            AVG(delay_hours) as avg_delay_hours,
            MAX(delay_hours) as max_delay_hours,
            COUNT(DISTINCT account_id) as affected_accounts,
            COUNT(DISTINCT affected_date) as affected_dates
        FROM late_data_events
        WHERE affected_date BETWEEN %s AND %s
        GROUP BY event_type, table_name
        ORDER BY event_count DESC
        """
        
        results = self.db_manager.model_db.execute_query(query, (start_date, end_date))
        
        summary = {
            'date_range': {'start': start_date, 'end': end_date},
            'by_type': {},
            'by_table': {},
            'total_events': 0,
            'total_records': 0,
            'avg_delay_hours': 0
        }
        
        for row in results:
            event_type = row['event_type']
            table_name = row['table_name']
            
            if event_type not in summary['by_type']:
                summary['by_type'][event_type] = {
                    'count': 0,
                    'records': 0,
                    'avg_delay': 0
                }
            
            if table_name not in summary['by_table']:
                summary['by_table'][table_name] = {
                    'count': 0,
                    'records': 0,
                    'avg_delay': 0
                }
            
            summary['by_type'][event_type]['count'] += row['event_count']
            summary['by_type'][event_type]['records'] += row['total_records']
            summary['by_table'][table_name]['count'] += row['event_count']
            summary['by_table'][table_name]['records'] += row['total_records']
            
            summary['total_events'] += row['event_count']
            summary['total_records'] += row['total_records']
        
        if summary['total_events'] > 0:
            # Calculate weighted average delay
            total_delay_query = """
            SELECT SUM(delay_hours * record_count) / SUM(record_count) as weighted_avg_delay
            FROM late_data_events
            WHERE affected_date BETWEEN %s AND %s
            AND delay_hours IS NOT NULL
            """
            delay_result = self.db_manager.model_db.execute_query(
                total_delay_query, (start_date, end_date)
            )
            if delay_result and delay_result[0]['weighted_avg_delay']:
                summary['avg_delay_hours'] = float(delay_result[0]['weighted_avg_delay'])
        
        return summary