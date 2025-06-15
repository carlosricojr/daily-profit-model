# Production-Ready Logging Infrastructure

This document describes the enhanced logging infrastructure implemented for the Daily Profit Model project.

## Features Implemented

### 1. Structured Logging with JSON Format
- All logs are output in JSON format for easy parsing by log aggregation services
- Includes timestamp, log level, logger name, module, function, and line number
- Supports nested data structures and custom fields

### 2. Correlation IDs for Distributed Tracing
- Automatic correlation ID generation for request tracking
- Correlation IDs are maintained across all operations within a request
- Supports manual correlation ID setting for external integrations

### 3. Contextual Information
- Request context (user_id, account_id, operation type, etc.)
- Automatic context propagation using Python's contextvars
- Context manager for temporary context addition

### 4. Log Levels and Filtering
- Standard log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Environment-based configuration via LOG_LEVEL
- Automatic filtering of noisy third-party loggers

### 5. Performance Metrics in Logs
- Built-in performance metric logging
- Execution time tracking decorator
- Structured metrics output for monitoring systems

### 6. Log Rotation and Retention
- Automatic log file rotation based on size
- Configurable maximum file size and backup count
- Default: 10MB per file, 5 backup files

### 7. Integration Points for Log Aggregation
- Configuration templates for popular services:
  - Elasticsearch/ELK Stack
  - AWS CloudWatch
  - Datadog
  - Splunk
  - Fluentd
  - Grafana Loki
  - Kafka

## Usage Examples

### Basic Setup

```python
from src.utils.logging_config import setup_logging, get_logger

# Setup logging with JSON format and rotation
setup_logging(
    log_level="INFO",
    log_file="application",
    enable_json=True,
    enable_rotation=True,
    max_bytes=10485760,  # 10MB
    backup_count=5
)

# Get a logger instance
logger = get_logger(__name__)
```

### Structured Logging

```python
# Log with structured data
logger.info("Processing batch", 
           batch_id="BATCH123",
           record_count=1000,
           source="api",
           processing_stage="validation")

# Log with nested data
logger.info("API response received",
           response={
               "status_code": 200,
               "records": 50,
               "next_page": "page2"
           })
```

### Correlation ID Tracking

```python
from src.utils.logging_config import set_correlation_id, with_correlation_id

# Manual correlation ID
correlation_id = set_correlation_id()
logger.info("Starting request", correlation_id=correlation_id)

# Automatic with decorator
@with_correlation_id
def process_data():
    logger.info("Processing data")  # Correlation ID automatically included
```

### Context Management

```python
from src.utils.logging_config import LoggingContext, set_request_context

# Using context manager
with LoggingContext(user_id=123, account_id="ACC456", operation="sync"):
    logger.info("Syncing data")  # Context automatically included

# Manual context setting
set_request_context(
    ingestion_type="trades",
    source="api",
    batch_size=1000
)
```

### Performance Logging

```python
from src.utils.logging_config import log_execution_time, log_metrics

# Automatic execution time logging
@log_execution_time()
def slow_operation():
    # Your code here
    pass

# Manual metrics logging
log_metrics(
    logger=logger,
    operation="data_processing",
    metrics={
        "records_processed": 1000,
        "processing_time_ms": 250,
        "memory_usage_mb": 512
    },
    status="success"
)
```

## Environment Variables

### Core Configuration
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LOG_DIR`: Directory for log files (default: "logs")

### Log Aggregation Service Configuration
See `src/utils/logging_aggregation_config.py` for service-specific environment variables.

## Log File Locations

- Default directory: `./logs/`
- File naming: `{log_name}_{timestamp}.log`
- Rotated files: `{log_name}.log`, `{log_name}.log.1`, etc.

## Health Checks

Run the logging health check to verify configuration:

```bash
python -m src.utils.logging_health_check
```

This will test:
- Basic logging functionality
- Structured logging
- Correlation ID generation
- Context management
- File rotation
- Performance metrics
- JSON format validation

## Integration with Data Ingestion

The base ingester and all data ingestion modules have been updated to use the enhanced logging:

- Automatic correlation ID for each ingestion run
- Structured metrics logging at completion
- Context propagation throughout the ingestion pipeline
- Performance tracking for API calls and database operations

## Best Practices

1. **Always use structured logging** - Pass data as keyword arguments, not in message strings
2. **Include relevant context** - User IDs, account IDs, operation types
3. **Use correlation IDs** - For any operation that spans multiple function calls
4. **Log at appropriate levels** - DEBUG for detailed info, INFO for important events, ERROR for failures
5. **Include metrics** - Processing times, record counts, success rates
6. **Handle sensitive data** - Never log passwords, API keys, or PII directly

## Monitoring and Alerting

The structured JSON logs can be easily parsed by monitoring systems for:

- Error rate tracking
- Performance degradation detection
- Anomaly detection in processing patterns
- SLA monitoring
- Resource usage tracking

## Migration Guide

To migrate existing logging calls:

1. Replace string formatting with structured fields:
   ```python
   # Old
   logger.info(f"Processing {count} records")
   
   # New
   logger.info("Processing records", count=count)
   ```

2. Add correlation IDs to multi-step operations:
   ```python
   @with_correlation_id
   def ingest_data():
       # Your ingestion logic
   ```

3. Use context managers for request-scoped data:
   ```python
   with LoggingContext(user_id=user_id):
       # Process user request
   ```

## Troubleshooting

### Logs not appearing
- Check LOG_LEVEL environment variable
- Verify log directory permissions
- Run health check: `python -m src.utils.logging_health_check`

### JSON parsing errors
- Ensure enable_json=True in setup_logging()
- Check for non-serializable objects in log data

### Performance impact
- Adjust log level to reduce volume
- Increase rotation size to reduce I/O
- Consider async logging handlers for high-throughput scenarios