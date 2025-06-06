"""
Query Performance Monitoring Utility
Tracks and logs database query performance for optimization analysis.
"""

import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from contextlib import contextmanager
import json
import os

logger = logging.getLogger(__name__)


class QueryPerformanceMonitor:
    """Monitor and log database query performance."""
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize query performance monitor.
        
        Args:
            log_file: Optional file path to write performance logs
        """
        self.query_stats = {
            'total_queries': 0,
            'total_time': 0.0,
            'queries_by_type': {},
            'slow_queries': [],
            'query_log': []
        }
        self.log_file = log_file or 'query_performance.json'
        self.slow_query_threshold = 1.0  # seconds
        
    @contextmanager
    def track_query(self, query_type: str, query: str, params: Any = None):
        """
        Context manager to track query execution time.
        
        Args:
            query_type: Type/category of query (e.g., 'fetch_features', 'bulk_insert')
            query: The SQL query being executed
            params: Query parameters
        
        Yields:
            Dict with query tracking info
        """
        start_time = time.time()
        query_info = {
            'type': query_type,
            'query': query[:200],  # Truncate long queries
            'params_count': len(params) if params else 0,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            yield query_info
        finally:
            execution_time = time.time() - start_time
            query_info['execution_time'] = execution_time
            
            # Update statistics
            self._update_stats(query_type, execution_time, query_info)
            
            # Log slow queries
            if execution_time > self.slow_query_threshold:
                self._log_slow_query(query_info, query, params)
    
    def _update_stats(self, query_type: str, execution_time: float, query_info: Dict):
        """Update performance statistics."""
        self.query_stats['total_queries'] += 1
        self.query_stats['total_time'] += execution_time
        
        # Track by query type
        if query_type not in self.query_stats['queries_by_type']:
            self.query_stats['queries_by_type'][query_type] = {
                'count': 0,
                'total_time': 0.0,
                'avg_time': 0.0,
                'max_time': 0.0,
                'min_time': float('inf')
            }
        
        type_stats = self.query_stats['queries_by_type'][query_type]
        type_stats['count'] += 1
        type_stats['total_time'] += execution_time
        type_stats['avg_time'] = type_stats['total_time'] / type_stats['count']
        type_stats['max_time'] = max(type_stats['max_time'], execution_time)
        type_stats['min_time'] = min(type_stats['min_time'], execution_time)
        
        # Keep last 100 queries in log
        self.query_stats['query_log'].append(query_info)
        if len(self.query_stats['query_log']) > 100:
            self.query_stats['query_log'].pop(0)
    
    def _log_slow_query(self, query_info: Dict, query: str, params: Any):
        """Log slow queries for analysis."""
        slow_query_info = {
            **query_info,
            'full_query': query,
            'params_sample': str(params)[:100] if params else None
        }
        
        self.query_stats['slow_queries'].append(slow_query_info)
        
        # Keep only last 50 slow queries
        if len(self.query_stats['slow_queries']) > 50:
            self.query_stats['slow_queries'].pop(0)
        
        logger.warning(f"Slow query detected ({query_info['execution_time']:.2f}s): {query_info['type']}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        summary = {
            'total_queries': self.query_stats['total_queries'],
            'total_time': round(self.query_stats['total_time'], 2),
            'avg_query_time': round(
                self.query_stats['total_time'] / self.query_stats['total_queries'], 3
            ) if self.query_stats['total_queries'] > 0 else 0,
            'slow_queries_count': len(self.query_stats['slow_queries']),
            'queries_by_type': {}
        }
        
        # Summarize by type
        for query_type, stats in self.query_stats['queries_by_type'].items():
            summary['queries_by_type'][query_type] = {
                'count': stats['count'],
                'avg_time': round(stats['avg_time'], 3),
                'total_time': round(stats['total_time'], 2),
                'max_time': round(stats['max_time'], 3)
            }
        
        return summary
    
    def save_performance_log(self):
        """Save performance log to file."""
        try:
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'summary': self.get_summary(),
                'slow_queries': self.query_stats['slow_queries'][-10:],  # Last 10 slow queries
                'recent_queries': self.query_stats['query_log'][-20:]  # Last 20 queries
            }
            
            # Create logs directory if it doesn't exist
            log_dir = os.path.dirname(self.log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            with open(self.log_file, 'w') as f:
                json.dump(log_data, f, indent=2)
            
            logger.info(f"Performance log saved to {self.log_file}")
            
        except Exception as e:
            logger.error(f"Failed to save performance log: {str(e)}")
    
    def log_summary(self):
        """Log performance summary to logger."""
        summary = self.get_summary()
        
        logger.info("=" * 60)
        logger.info("QUERY PERFORMANCE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total queries: {summary['total_queries']}")
        logger.info(f"Total time: {summary['total_time']}s")
        logger.info(f"Average query time: {summary['avg_query_time']}s")
        logger.info(f"Slow queries: {summary['slow_queries_count']}")
        
        logger.info("\nQueries by type:")
        for query_type, stats in summary['queries_by_type'].items():
            logger.info(f"  {query_type}:")
            logger.info(f"    - Count: {stats['count']}")
            logger.info(f"    - Avg time: {stats['avg_time']}s")
            logger.info(f"    - Max time: {stats['max_time']}s")
        logger.info("=" * 60)


class DatabaseConnectionPool:
    """
    Enhanced database connection pool with query performance monitoring.
    This would replace or enhance the existing database connection handling.
    """
    
    def __init__(self, db_manager, enable_monitoring: bool = True):
        self.db_manager = db_manager
        self.enable_monitoring = enable_monitoring
        self.monitor = QueryPerformanceMonitor() if enable_monitoring else None
    
    def execute_query(self, query: str, params: Any = None, query_type: str = "generic") -> List[Dict]:
        """Execute query with performance monitoring."""
        if self.enable_monitoring and self.monitor:
            with self.monitor.track_query(query_type, query, params) as query_info:
                result = self.db_manager.execute_query(query, params)
                query_info['rows_returned'] = len(result) if result else 0
                return result
        else:
            return self.db_manager.execute_query(query, params)
    
    def execute_query_df(self, query: str, params: Any = None, query_type: str = "generic"):
        """Execute query returning DataFrame with performance monitoring."""
        if self.enable_monitoring and self.monitor:
            with self.monitor.track_query(query_type, query, params) as query_info:
                df = self.db_manager.execute_query_df(query, params)
                query_info['rows_returned'] = len(df) if df is not None else 0
                return df
        else:
            return self.db_manager.execute_query_df(query, params)
    
    def get_performance_summary(self) -> Optional[Dict[str, Any]]:
        """Get performance summary if monitoring is enabled."""
        if self.monitor:
            return self.monitor.get_summary()
        return None


def compare_query_patterns(original_log: str, optimized_log: str) -> Dict[str, Any]:
    """
    Compare query patterns between original and optimized implementations.
    
    Args:
        original_log: Path to original implementation performance log
        optimized_log: Path to optimized implementation performance log
        
    Returns:
        Comparison results
    """
    try:
        with open(original_log, 'r') as f:
            original_data = json.load(f)
        
        with open(optimized_log, 'r') as f:
            optimized_data = json.load(f)
        
        comparison = {
            'original': original_data['summary'],
            'optimized': optimized_data['summary'],
            'improvements': {}
        }
        
        # Calculate improvements
        orig_summary = original_data['summary']
        opt_summary = optimized_data['summary']
        
        comparison['improvements'] = {
            'query_reduction': round(
                (1 - opt_summary['total_queries'] / orig_summary['total_queries']) * 100, 2
            ) if orig_summary['total_queries'] > 0 else 0,
            'time_reduction': round(
                (1 - opt_summary['total_time'] / orig_summary['total_time']) * 100, 2
            ) if orig_summary['total_time'] > 0 else 0,
            'avg_query_speedup': round(
                orig_summary['avg_query_time'] / opt_summary['avg_query_time'], 2
            ) if opt_summary['avg_query_time'] > 0 else 0
        }
        
        return comparison
        
    except Exception as e:
        logger.error(f"Failed to compare query patterns: {str(e)}")
        return {}


if __name__ == '__main__':
    # Example usage
    monitor = QueryPerformanceMonitor()
    
    # Simulate some queries
    with monitor.track_query('select_features', 'SELECT * FROM features WHERE account_id = %s'):
        time.sleep(0.1)  # Simulate query execution
    
    with monitor.track_query('bulk_insert', 'INSERT INTO features VALUES ...'):
        time.sleep(0.05)
    
    with monitor.track_query('select_features', 'SELECT * FROM features WHERE date = %s'):
        time.sleep(2.0)  # Simulate slow query
    
    # Log summary
    monitor.log_summary()
    monitor.save_performance_log()