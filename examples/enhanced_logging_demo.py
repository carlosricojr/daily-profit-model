#!/usr/bin/env python3
"""
Demonstration of enhanced production-ready logging features.
Shows structured logging, correlation IDs, context management, and metrics logging.
"""

import sys
import os
import time
import random
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.logging_config import (
    setup_logging, get_logger, set_correlation_id, set_request_context,
    LoggingContext, log_metrics, with_correlation_id, log_execution_time
)


def demo_basic_structured_logging():
    """Demonstrate basic structured logging with JSON output."""
    print("\n=== Basic Structured Logging Demo ===")
    
    # Setup logging with JSON format
    setup_logging(
        log_level="INFO",
        log_file="demo_structured",
        enable_json=True,
        enable_rotation=True
    )
    
    logger = get_logger("demo.basic")
    
    # Simple log messages with structured data
    logger.info("Starting data processing", 
               operation="demo",
               user_id=12345,
               environment="production")
    
    # Log with nested data
    logger.info("Processing batch",
               batch_info={
                   "size": 1000,
                   "source": "api",
                   "timestamp": datetime.utcnow().isoformat()
               })
    
    # Error logging with context
    try:
        1 / 0
    except ZeroDivisionError:
        logger.error("Math operation failed",
                    operation="division",
                    numerator=1,
                    denominator=0,
                    exc_info=True)


def demo_correlation_tracking():
    """Demonstrate correlation ID tracking across operations."""
    print("\n=== Correlation ID Tracking Demo ===")
    
    logger = get_logger("demo.correlation")
    
    # Set correlation ID for a request
    correlation_id = set_correlation_id()
    logger.info("Starting request processing", correlation_id=correlation_id)
    
    # Simulate multiple operations with same correlation ID
    def fetch_data():
        logger.info("Fetching data from API")
        time.sleep(0.1)
        return {"records": 100}
    
    def validate_data(data):
        logger.info("Validating data", record_count=data["records"])
        time.sleep(0.05)
        return True
    
    def save_data(data):
        logger.info("Saving data to database", record_count=data["records"])
        time.sleep(0.1)
    
    # All these operations will have the same correlation ID
    data = fetch_data()
    if validate_data(data):
        save_data(data)
    
    logger.info("Request completed", correlation_id=correlation_id)


def demo_context_management():
    """Demonstrate context management for logging."""
    print("\n=== Context Management Demo ===")
    
    logger = get_logger("demo.context")
    
    # Using LoggingContext for temporary context
    with LoggingContext(user_id=456, account_id="ACC789", operation="data_sync"):
        logger.info("Starting data synchronization")
        
        # Nested context
        with LoggingContext(batch_id="BATCH123"):
            logger.info("Processing batch")
            
            # Simulate processing
            for i in range(3):
                logger.info("Processing record", 
                          record_id=i, 
                          progress=f"{(i+1)/3*100:.0f}%")
                time.sleep(0.1)
        
        logger.info("Batch processing completed")
    
    # Context is automatically cleared
    logger.info("Outside context - no user/account info")


@with_correlation_id
def demo_decorator_usage():
    """Demonstrate decorator for automatic correlation ID."""
    print("\n=== Decorator Usage Demo ===")
    
    logger = get_logger("demo.decorator")
    
    # Correlation ID is automatically set by decorator
    logger.info("Function started")
    
    # Simulate some work
    time.sleep(0.2)
    
    logger.info("Function completed")


@log_execution_time()
def demo_performance_logging():
    """Demonstrate performance metric logging."""
    print("\n=== Performance Logging Demo ===")
    
    logger = get_logger("demo.performance")
    
    # Simulate variable processing time
    processing_time = random.uniform(0.1, 0.5)
    time.sleep(processing_time)
    
    # Log custom metrics
    metrics = {
        "records_processed": 1000,
        "processing_time_ms": processing_time * 1000,
        "records_per_second": 1000 / processing_time,
        "memory_usage_mb": 256,
        "cpu_usage_percent": 45.5
    }
    
    log_metrics(
        logger=logger,
        operation="batch_processing",
        metrics=metrics,
        status="success",
        batch_id="BATCH456"
    )


def demo_ingestion_logging():
    """Demonstrate logging for a data ingestion scenario."""
    print("\n=== Data Ingestion Logging Demo ===")
    
    # Set up structured logging
    setup_logging(
        log_level="INFO",
        log_file="demo_ingestion",
        enable_json=True,
        enable_rotation=True,
        max_bytes=5242880,  # 5MB
        backup_count=10
    )
    
    logger = get_logger("demo.ingestion")
    
    # Start ingestion with correlation ID and context
    correlation_id = set_correlation_id()
    set_request_context(
        ingestion_type="accounts",
        source="api",
        initiated_by="scheduler"
    )
    
    logger.info("Starting data ingestion",
               correlation_id=correlation_id,
               start_time=datetime.utcnow().isoformat())
    
    # Simulate ingestion steps
    try:
        # Step 1: Fetch data
        with LoggingContext(step="fetch_data"):
            logger.info("Fetching data from API")
            time.sleep(0.2)
            fetched_records = 500
            logger.info("Data fetched successfully", records_fetched=fetched_records)
        
        # Step 2: Validate data
        with LoggingContext(step="validate_data"):
            logger.info("Validating records")
            valid_records = 480
            invalid_records = 20
            logger.info("Validation completed",
                       valid_records=valid_records,
                       invalid_records=invalid_records,
                       validation_rate=f"{(valid_records/fetched_records)*100:.1f}%")
        
        # Step 3: Save data
        with LoggingContext(step="save_data"):
            logger.info("Saving records to database")
            time.sleep(0.3)
            logger.info("Records saved successfully", records_saved=valid_records)
        
        # Log final metrics
        total_time = 0.5
        metrics = {
            "total_records": fetched_records,
            "valid_records": valid_records,
            "invalid_records": invalid_records,
            "processing_time_seconds": total_time,
            "records_per_second": fetched_records / total_time,
            "success_rate": (valid_records / fetched_records) * 100
        }
        
        log_metrics(
            logger=logger,
            operation="data_ingestion",
            metrics=metrics,
            correlation_id=correlation_id,
            status="completed"
        )
        
    except Exception as e:
        logger.error("Ingestion failed",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    correlation_id=correlation_id,
                    exc_info=True)


def demo_log_aggregation_format():
    """Demonstrate log format suitable for aggregation services."""
    print("\n=== Log Aggregation Format Demo ===")
    
    # Setup with specific format for log aggregation
    setup_logging(
        log_level="INFO",
        log_file="demo_aggregation",
        enable_json=True
    )
    
    logger = get_logger("demo.aggregation")
    
    # Log with fields commonly used by aggregation services
    logger.info("Application started",
               service_name="daily-profit-model",
               service_version="1.0.0",
               deployment_environment="production",
               region="us-east-1",
               instance_id="i-1234567890",
               container_id="abc123def456")
    
    # Log with metrics for monitoring
    logger.info("Health check",
               health_status="healthy",
               uptime_seconds=3600,
               memory_usage_percent=65.2,
               cpu_usage_percent=32.5,
               active_connections=45,
               queue_depth=12)
    
    # Log with tags for filtering
    logger.info("Business event",
               event_type="account_created",
               account_id="ACC12345",
               plan_type="premium",
               tags=["new_user", "premium", "us_region"])


def main():
    """Run all logging demonstrations."""
    print("=" * 60)
    print("Enhanced Production Logging Demonstration")
    print("=" * 60)
    
    # Run all demos
    demo_basic_structured_logging()
    demo_correlation_tracking()
    demo_context_management()
    demo_decorator_usage()
    demo_performance_logging()
    demo_ingestion_logging()
    demo_log_aggregation_format()
    
    print("\n" + "=" * 60)
    print("Demo completed! Check the logs directory for output files.")
    print("=" * 60)


if __name__ == "__main__":
    main()