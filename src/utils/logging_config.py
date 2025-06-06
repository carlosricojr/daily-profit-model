"""
Production-ready logging configuration for the daily profit model.
Implements structured logging, correlation IDs, log rotation, and enhanced context.
"""

import logging
import logging.handlers
import os
import sys
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Union
from contextvars import ContextVar
from functools import wraps

try:
    import structlog
    from structlog.processors import JSONRenderer, TimeStamper, add_log_level
    from structlog.stdlib import BoundLogger, LoggerFactory

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    BoundLogger = None

# Context variables for request tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)
request_context_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "request_context", default=None
)


class StructuredFormatter(logging.Formatter):
    """Custom JSON formatter for standard logging that includes context."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with context information."""
        # Base log data
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if available
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add request context if available
        request_context = request_context_var.get()
        if request_context:
            log_data["context"] = request_context

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields from the record
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
            ]:
                log_data[key] = value

        return json.dumps(log_data)


class ContextFilter(logging.Filter):
    """Add context information to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context variables to the record."""
        record.correlation_id = correlation_id_var.get() or "no-correlation-id"

        context = request_context_var.get()
        if context:
            for key, value in context.items():
                setattr(record, f"ctx_{key}", value)

        return True


def setup_structlog():
    """Configure structlog for structured logging."""
    if not STRUCTLOG_AVAILABLE:
        return

    timestamper = TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            add_context_processor,
            JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def add_context_processor(logger, log_method, event_dict):
    """Add correlation ID and request context to structlog events."""
    correlation_id = correlation_id_var.get()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id

    context = request_context_var.get()
    if context:
        event_dict["context"] = context

    return event_dict


def setup_logging(
    log_level: str = None,
    log_file: str = None,
    log_dir: str = None,
    enable_json: bool = True,
    enable_rotation: bool = True,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 5,
    enable_structured: bool = True,
):
    """
    Set up production-ready logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Name of the log file (optional)
        log_dir: Directory for log files (optional)
        enable_json: Use JSON formatting for logs
        enable_rotation: Enable log rotation
        max_bytes: Maximum size of log file before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 5)
        enable_structured: Use structlog for structured logging

    Returns:
        The configured logger instance
    """
    # Get log level from environment or use default
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO")

    # Create logs directory if specified
    if log_dir is None:
        log_dir = os.getenv("LOG_DIR", "logs")

    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers = []

    # Create formatters
    if enable_json:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(correlation_id)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Add context filter
    context_filter = ContextFilter()

    # Console handler with structured output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        file_path = log_path / f"{log_file}.log"

        if enable_rotation:
            file_handler = logging.handlers.RotatingFileHandler(
                file_path, maxBytes=max_bytes, backupCount=backup_count
            )
        else:
            file_handler = logging.FileHandler(file_path)

        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        root_logger.addHandler(file_handler)

        # Log the setup
        root_logger.info(
            "Logging initialized",
            extra={
                "log_level": log_level,
                "log_file": str(file_path),
                "rotation_enabled": enable_rotation,
                "max_bytes": max_bytes if enable_rotation else None,
                "backup_count": backup_count if enable_rotation else None,
            },
        )
    else:
        root_logger.info(
            "Logging initialized", extra={"log_level": log_level, "console_only": True}
        )

    # Set specific loggers to WARNING to reduce noise
    for noisy_logger in ["urllib3", "requests", "urllib3.connectionpool"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # Setup structlog if enabled
    if enable_structured:
        setup_structlog()

    return root_logger


def get_logger(
    name: Optional[str] = None, **kwargs
) -> Union[logging.Logger, BoundLogger]:
    """
    Get a logger instance with optional context binding.

    Args:
        name: Logger name (defaults to module name)
        **kwargs: Additional context to bind to the logger

    Returns:
        Logger instance (structlog BoundLogger if available, else standard logger)
    """
    if STRUCTLOG_AVAILABLE:
        try:
            # Try to get structlog logger
            logger = structlog.get_logger(name)
            if kwargs:
                logger = logger.bind(**kwargs)
            return logger
        except Exception:
            pass

    # Fallback to standard logging
    return logging.getLogger(name)


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """
    Set correlation ID for the current context.

    Args:
        correlation_id: Correlation ID to set (generates new one if not provided)

    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return correlation_id_var.get()


def set_request_context(**kwargs):
    """
    Set request context for the current execution.

    Args:
        **kwargs: Context key-value pairs (e.g., user_id, account_id, etc.)
    """
    current_context = request_context_var.get() or {}
    current_context.update(kwargs)
    request_context_var.set(current_context)


def clear_request_context():
    """Clear the request context."""
    request_context_var.set(None)


def with_correlation_id(func):
    """
    Decorator to automatically set correlation ID for a function.

    Usage:
        @with_correlation_id
        def process_data():
            logger.info("Processing data")  # Will include correlation ID
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Set new correlation ID if not already set
        existing_id = get_correlation_id()
        if not existing_id:
            set_correlation_id()

        try:
            return func(*args, **kwargs)
        finally:
            # Clear if we set it
            if not existing_id:
                correlation_id_var.set(None)

    return wrapper


def log_execution_time(logger: Optional[Union[logging.Logger, BoundLogger]] = None):
    """
    Decorator to log function execution time.

    Args:
        logger: Logger instance to use (creates one if not provided)

    Usage:
        @log_execution_time()
        def slow_function():
            time.sleep(1)
    """

    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = datetime.now()

            try:
                result = func(*args, **kwargs)
                execution_time = (datetime.now() - start_time).total_seconds()

                logger.info(
                    "Function executed successfully",
                    extra={
                        "function": func.__name__,
                        "execution_time_seconds": execution_time,
                        "status": "success",
                    },
                )

                return result
            except Exception as e:
                execution_time = (datetime.now() - start_time).total_seconds()

                logger.error(
                    "Function execution failed",
                    extra={
                        "function": func.__name__,
                        "execution_time_seconds": execution_time,
                        "status": "error",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


class LoggingContext:
    """
    Context manager for temporary logging context.

    Usage:
        with LoggingContext(user_id=123, operation='data_ingestion'):
            logger.info("Processing data")  # Will include context
    """

    def __init__(self, correlation_id: Optional[str] = None, **context):
        self.correlation_id = correlation_id
        self.context = context
        self.old_correlation_id = None
        self.old_context = None

    def __enter__(self):
        # Save current values
        self.old_correlation_id = get_correlation_id()
        self.old_context = request_context_var.get()

        # Set new values
        if self.correlation_id:
            set_correlation_id(self.correlation_id)
        elif not self.old_correlation_id:
            set_correlation_id()

        if self.context:
            set_request_context(**self.context)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore previous values
        correlation_id_var.set(self.old_correlation_id)
        request_context_var.set(self.old_context)


# Performance metrics logging helpers
def log_metrics(
    logger: Union[logging.Logger, BoundLogger],
    operation: str,
    metrics: Dict[str, Any],
    **extra_context,
):
    """
    Log performance metrics in a structured format.

    Args:
        logger: Logger instance
        operation: Name of the operation
        metrics: Dictionary of metrics to log
        **extra_context: Additional context to include
    """
    log_data = {
        "operation": operation,
        "metrics": metrics,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **extra_context,
    }

    logger.info(f"Performance metrics for {operation}", extra=log_data)


# Initialize module logger
logger = get_logger(__name__)
