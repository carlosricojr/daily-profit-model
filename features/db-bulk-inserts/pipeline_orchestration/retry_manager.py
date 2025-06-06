"""
Retry management for pipeline operations.
Implements simple retry mechanisms with exponential backoff.
"""

import time
import logging
from typing import Callable, Any, Optional, Dict, Tuple
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(self,
                 max_attempts: int = 3,
                 initial_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter: bool = True):
        """
        Initialize retry configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add random jitter to delays
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


class RetryManager:
    """Manages retry logic for pipeline operations."""
    
    def __init__(self, default_config: Optional[RetryConfig] = None):
        """
        Initialize retry manager.
        
        Args:
            default_config: Default retry configuration
        """
        self.default_config = default_config or RetryConfig()
        self.retry_history: Dict[str, list] = {}
    
    def retry_operation(self,
                       operation: Callable,
                       operation_name: str,
                       args: tuple = (),
                       kwargs: dict = None,
                       config: Optional[RetryConfig] = None,
                       retriable_exceptions: Tuple[type, ...] = (Exception,)) -> Any:
        """
        Execute an operation with retry logic.
        
        Args:
            operation: The function to execute
            operation_name: Name of the operation for logging
            args: Positional arguments for the operation
            kwargs: Keyword arguments for the operation
            config: Retry configuration (uses default if None)
            retriable_exceptions: Tuple of exception types to retry on
            
        Returns:
            Result of the operation
            
        Raises:
            The last exception if all retries fail
        """
        config = config or self.default_config
        kwargs = kwargs or {}
        attempts = []
        last_exception = None
        
        for attempt in range(config.max_attempts):
            attempt_start = datetime.now()
            
            try:
                logger.info(f"Attempting {operation_name} (attempt {attempt + 1}/{config.max_attempts})")
                result = operation(*args, **kwargs)
                
                # Record successful attempt
                attempts.append({
                    'attempt': attempt + 1,
                    'timestamp': attempt_start,
                    'duration': (datetime.now() - attempt_start).total_seconds(),
                    'status': 'success',
                    'error': None
                })
                
                # Store in history
                if operation_name not in self.retry_history:
                    self.retry_history[operation_name] = []
                self.retry_history[operation_name].append({
                    'timestamp': attempt_start,
                    'attempts': attempts,
                    'final_status': 'success'
                })
                
                logger.info(f"{operation_name} succeeded on attempt {attempt + 1}")
                return result
                
            except retriable_exceptions as e:
                last_exception = e
                
                # Record failed attempt
                attempts.append({
                    'attempt': attempt + 1,
                    'timestamp': attempt_start,
                    'duration': (datetime.now() - attempt_start).total_seconds(),
                    'status': 'failed',
                    'error': str(e)
                })
                
                if attempt < config.max_attempts - 1:
                    # Calculate delay with exponential backoff
                    delay = min(
                        config.initial_delay * (config.exponential_base ** attempt),
                        config.max_delay
                    )
                    
                    # Add jitter if configured
                    if config.jitter:
                        import random
                        delay *= (0.5 + random.random())
                    
                    logger.warning(
                        f"{operation_name} failed on attempt {attempt + 1}/{config.max_attempts}: {str(e)}. "
                        f"Retrying in {delay:.1f} seconds..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"{operation_name} failed after {config.max_attempts} attempts: {str(e)}"
                    )
        
        # Store failure in history
        if operation_name not in self.retry_history:
            self.retry_history[operation_name] = []
        self.retry_history[operation_name].append({
            'timestamp': attempts[0]['timestamp'],
            'attempts': attempts,
            'final_status': 'failed'
        })
        
        raise last_exception
    
    def get_retry_stats(self, operation_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get retry statistics for operations.
        
        Args:
            operation_name: Specific operation to get stats for (None for all)
            
        Returns:
            Dictionary containing retry statistics
        """
        if operation_name:
            history = self.retry_history.get(operation_name, [])
            return self._calculate_stats(operation_name, history)
        else:
            stats = {}
            for name, history in self.retry_history.items():
                stats[name] = self._calculate_stats(name, history)
            return stats
    
    def _calculate_stats(self, operation_name: str, history: list) -> Dict[str, Any]:
        """Calculate statistics for a specific operation."""
        if not history:
            return {
                'operation': operation_name,
                'total_executions': 0,
                'success_rate': 0.0,
                'average_attempts': 0.0,
                'max_attempts': 0
            }
        
        total_executions = len(history)
        successful_executions = sum(1 for h in history if h['final_status'] == 'success')
        total_attempts = sum(len(h['attempts']) for h in history)
        max_attempts = max(len(h['attempts']) for h in history)
        
        return {
            'operation': operation_name,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': total_executions - successful_executions,
            'success_rate': successful_executions / total_executions if total_executions > 0 else 0.0,
            'average_attempts': total_attempts / total_executions if total_executions > 0 else 0.0,
            'max_attempts': max_attempts,
            'recent_executions': history[-5:]  # Last 5 executions
        }


def retry_on_failure(max_attempts: int = 3,
                    delay: float = 1.0,
                    backoff: float = 2.0,
                    exceptions: Tuple[type, ...] = (Exception,)):
    """
    Decorator for adding retry logic to functions.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier for each retry
        exceptions: Tuple of exception types to retry on
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {str(e)}. "
                            f"Retrying in {wait_time:.1f} seconds..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {str(e)}"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


# Global retry manager instance
_retry_manager = None


def get_retry_manager() -> RetryManager:
    """Get or create the global retry manager instance."""
    global _retry_manager
    if _retry_manager is None:
        _retry_manager = RetryManager()
    return _retry_manager