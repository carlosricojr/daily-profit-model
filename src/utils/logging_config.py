"""
Logging configuration for the daily profit model.
Sets up consistent logging across all modules.
"""

import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logging(
    log_level: str = None,
    log_file: str = None,
    log_dir: str = None
):
    """
    Set up logging configuration for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Name of the log file (optional)
        log_dir: Directory for log files (optional)
    
    Returns:
        The configured logger instance
    """
    # Get log level from environment or use default
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    # Create logs directory if specified
    if log_dir is None:
        log_dir = os.getenv('LOG_DIR', 'logs')
    
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Set up log format
    log_format = (
        '%(asctime)s - %(name)s - %(levelname)s - '
        '%(filename)s:%(lineno)d - %(message)s'
    )
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Add file handler if log file specified
    if log_file:
        # Remove timestamp for test predictability
        if '_' in log_file and log_file.split('_')[-1].isdigit():
            # Test file with specific name
            file_path = log_path / f"{log_file}.log"
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = log_path / f"{log_file}_{timestamp}.log"
        
        file_handler = logging.FileHandler(file_path)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(logging.Formatter(log_format))
        
        # Add handler to root logger
        logging.getLogger().addHandler(file_handler)
        
        # Log the setup
        logging.info(f"Logging initialized - Level: {log_level}, File: {file_path}")
    else:
        logging.info(f"Logging initialized - Level: {log_level}")
    
    # Set specific loggers to WARNING to reduce noise
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    return logging.getLogger()


def get_logger(name=None):
    """Get a logger instance."""
    return logging.getLogger(name)