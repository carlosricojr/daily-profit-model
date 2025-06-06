"""
Base ingester class with common functionality for all data ingesters.
Implements checkpoint management, metrics tracking, validation, and error handling.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import tempfile
import time

# Database optimization imports
from psycopg2.extras import execute_batch

from ..utils.database import get_db_manager
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class IngestionMetrics:
    """Tracks metrics for data ingestion operations."""
    total_records: int = 0
    new_records: int = 0
    duplicate_records: int = 0
    invalid_records: int = 0
    api_calls: int = 0
    api_errors: int = 0
    db_errors: int = 0
    validation_errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    start_time: float = field(default_factory=lambda: datetime.now().timestamp())
    
    @property
    def processing_time(self) -> float:
        """Calculate total processing time in seconds."""
        return datetime.now().timestamp() - self.start_time
    
    @property
    def records_per_second(self) -> float:
        """Calculate processing rate."""
        if self.processing_time > 0:
            return self.total_records / self.processing_time
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for logging."""
        return {
            **asdict(self),
            'processing_time': self.processing_time,
            'records_per_second': self.records_per_second
        }


class CheckpointManager:
    """Manages checkpoints for resumable data ingestion."""
    
    def __init__(self, checkpoint_file: str, ingestion_type: str):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_file: Path to checkpoint file
            ingestion_type: Type of ingestion (e.g., 'trades', 'metrics_daily')
        """
        self.checkpoint_file = Path(checkpoint_file)
        self.ingestion_type = ingestion_type
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save_checkpoint(self, checkpoint_data: Dict[str, Any]):
        """Save checkpoint to file."""
        try:
            checkpoint_data['timestamp'] = datetime.now().isoformat()
            checkpoint_data['ingestion_type'] = self.ingestion_type
            
            with open(self.checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            
            logger.debug(f"Checkpoint saved: {checkpoint_data}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {str(e)}")
    
    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load checkpoint from file."""
        try:
            if self.checkpoint_file.exists():
                with open(self.checkpoint_file, 'r') as f:
                    checkpoint = json.load(f)
                
                # Verify checkpoint is for correct ingestion type
                if checkpoint.get('ingestion_type') == self.ingestion_type:
                    logger.info(f"Loaded checkpoint from {checkpoint.get('timestamp')}")
                    return checkpoint
                else:
                    logger.warning(f"Checkpoint type mismatch: expected {self.ingestion_type}, "
                                 f"got {checkpoint.get('ingestion_type')}")
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {str(e)}")
        
        return None
    
    def clear_checkpoint(self):
        """Remove checkpoint file."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                logger.info("Checkpoint cleared")
        except Exception as e:
            logger.error(f"Failed to clear checkpoint: {str(e)}")


class BaseIngester:
    """Base class for all data ingesters with common functionality."""
    
    def __init__(self, 
                 ingestion_type: str,
                 table_name: str,
                 checkpoint_dir: Optional[str] = None,
                 enable_validation: bool = True,
                 enable_deduplication: bool = True):
        """
        Initialize base ingester.
        
        Args:
            ingestion_type: Type of data being ingested
            table_name: Target database table
            checkpoint_dir: Directory for checkpoint files
            enable_validation: Whether to validate records
            enable_deduplication: Whether to check for duplicates
        """
        self.ingestion_type = ingestion_type
        self.table_name = table_name
        self.enable_validation = enable_validation
        self.enable_deduplication = enable_deduplication
        
        # Initialize database manager
        self.db_manager = get_db_manager()
        
        # Set up checkpoint manager
        if checkpoint_dir is None:
            checkpoint_dir = tempfile.gettempdir()
        
        checkpoint_file = os.path.join(checkpoint_dir, f"{ingestion_type}_checkpoint.json")
        self.checkpoint_manager = CheckpointManager(checkpoint_file, ingestion_type)
        
        # Initialize metrics
        self.metrics = IngestionMetrics()
        
        # Cache for deduplication
        self.seen_records = set()
        self.max_cache_size = 100000  # Limit cache size
        
        logger.info(f"Initialized {ingestion_type} ingester for table {table_name}")
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None or value == '':
            return None
        
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.debug(f"Could not convert '{value}' to float")
            return None
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to integer."""
        if value is None or value == '':
            return None
        
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.debug(f"Could not convert '{value}' to int")
            return None
    
    def _validate_record(self, record: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Base validation method to be overridden by subclasses.
        
        Args:
            record: Record to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        # Subclasses should implement specific validation logic
        return True, []
    
    def _get_record_key(self, record: Dict[str, Any]) -> Optional[str]:
        """
        Get unique key for record (for deduplication).
        To be overridden by subclasses.
        
        Args:
            record: Record to get key for
            
        Returns:
            Unique key string or None
        """
        # Subclasses should implement specific key generation
        return None
    
    def _process_record(self, raw_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a single record with validation and deduplication.
        
        Args:
            raw_record: Raw record from source
            
        Returns:
            Processed record or None if invalid/duplicate
        """
        self.metrics.total_records += 1
        
        # Validate if enabled
        if self.enable_validation:
            is_valid, errors = self._validate_record(raw_record)
            if not is_valid:
                self.metrics.invalid_records += 1
                for error in errors:
                    self.metrics.validation_errors[error] += 1
                logger.debug(f"Invalid record: {errors}")
                return None
        
        # Check for duplicates if enabled
        if self.enable_deduplication:
            record_key = self._get_record_key(raw_record)
            if record_key and record_key in self.seen_records:
                self.metrics.duplicate_records += 1
                return None
            
            if record_key:
                self.seen_records.add(record_key)
                # Rotate cache if it gets too large
                if len(self.seen_records) > self.max_cache_size:
                    # Remove oldest entries (approximately)
                    self.seen_records = set(list(self.seen_records)[-self.max_cache_size//2:])
        
        # Transform record (to be implemented by subclasses)
        transformed = self._transform_record(raw_record)
        if transformed:
            self.metrics.new_records += 1
            return transformed
        
        return None
    
    def _transform_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform record for database insertion.
        To be overridden by subclasses.
        
        Args:
            record: Raw record
            
        Returns:
            Transformed record
        """
        # Default implementation just adds ingestion timestamp
        record['ingestion_timestamp'] = datetime.now()
        return record
    
    def _insert_batch(self, batch_data: List[Dict[str, Any]], table_name: Optional[str] = None):
        """
        Insert a batch of records into the database using optimized execute_batch.
        
        Performance improvements:
        - Uses execute_batch instead of executemany for ~10x performance gain
        - Configurable page_size for optimal memory/speed tradeoff
        - Tracks insertion timing for performance monitoring
        """
        if not batch_data:
            return
        
        if table_name is None:
            table_name = self.table_name
        
        start_time = time.time()
        
        try:
            # Get columns from first record
            columns = list(batch_data[0].keys())
            
            # Use the database manager's insert_batch method if available
            if hasattr(self.db_manager.model_db, 'insert_batch'):
                self.db_manager.model_db.insert_batch(
                    table=table_name,
                    data=batch_data
                )
            else:
                # Optimized manual insertion using execute_batch
                placeholders = ', '.join(['%s'] * len(columns))
                columns_str = ', '.join(columns)
                
                # Build ON CONFLICT clause based on table type
                conflict_clause = self._get_conflict_clause(table_name)
                
                query = f"""
                INSERT INTO {table_name} ({columns_str})
                VALUES ({placeholders})
                {conflict_clause}
                """
                
                values = [tuple(record[col] for col in columns) for record in batch_data]
                
                with self.db_manager.model_db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Use execute_batch for optimized bulk insert
                        # page_size controls how many records are sent per network round trip
                        execute_batch(
                            cursor, 
                            query, 
                            values,
                            page_size=1000  # Optimal for most data types
                        )
            
            # Performance metrics
            duration = time.time() - start_time
            records_per_sec = len(batch_data) / duration if duration > 0 else 0
            
            logger.debug(f"Inserted batch of {len(batch_data)} records into {table_name} "
                        f"in {duration:.2f}s ({records_per_sec:.0f} records/sec)")
            
        except Exception as e:
            self.metrics.db_errors += 1
            logger.error(f"Failed to insert batch: {str(e)}")
            raise
    
    def _get_conflict_clause(self, table_name: str) -> str:
        """
        Get ON CONFLICT clause for table.
        To be overridden by subclasses for specific conflict handling.
        
        Args:
            table_name: Name of the table
            
        Returns:
            ON CONFLICT clause
        """
        return "ON CONFLICT DO NOTHING"
    
    def log_pipeline_execution(self, status: str, error_message: Optional[str] = None):
        """Log pipeline execution details."""
        try:
            self.db_manager.log_pipeline_execution(
                pipeline_stage=f'ingest_{self.ingestion_type}',
                execution_date=datetime.now().date(),
                status=status,
                records_processed=self.metrics.new_records,
                error_message=error_message,
                execution_details=self.metrics.to_dict()
            )
        except Exception as e:
            logger.error(f"Failed to log pipeline execution: {str(e)}")
    
    def get_metrics_summary(self) -> str:
        """Get a summary of ingestion metrics."""
        return (
            f"Ingestion Summary for {self.ingestion_type}:\n"
            f"  Total records: {self.metrics.total_records}\n"
            f"  New records: {self.metrics.new_records}\n"
            f"  Duplicate records: {self.metrics.duplicate_records}\n"
            f"  Invalid records: {self.metrics.invalid_records}\n"
            f"  API calls: {self.metrics.api_calls}\n"
            f"  API errors: {self.metrics.api_errors}\n"
            f"  DB errors: {self.metrics.db_errors}\n"
            f"  Processing time: {self.metrics.processing_time:.2f}s\n"
            f"  Rate: {self.metrics.records_per_second:.2f} records/s"
        )
    
    def ingest(self, **kwargs) -> int:
        """
        Main ingestion method to be implemented by subclasses.
        
        Returns:
            Number of records ingested
        """
        raise NotImplementedError("Subclasses must implement the ingest method")