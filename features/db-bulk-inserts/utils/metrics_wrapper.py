"""
Wrapper classes to provide backward compatibility with the test suite.
Bridges the gap between test expectations and the Prometheus-style metrics.
"""

import time
from typing import Dict, Any, Optional
from collections import defaultdict, deque
from functools import wraps

from .metrics import (
    get_prometheus_metrics, 
    get_aggregated_metrics
)


class MetricsCollector:
    """Backward-compatible metrics collector that wraps Prometheus metrics."""
    
    def __init__(self, max_history: int = 1000):
        """Initialize metrics collector."""
        self.max_history = max_history
        self._counters = defaultdict(int)
        self._gauges = defaultdict(float)
        self._timings = defaultdict(lambda: deque(maxlen=max_history))
        self._start_time = time.time()
        
        # Get references to the global instances
        self._prometheus = get_prometheus_metrics()
        self._aggregated = get_aggregated_metrics()
    
    def increment_counter(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self._counters[key] += value
        
        # Also track in aggregated metrics
        self._aggregated.record(name, value)
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        key = self._make_key(name, labels)
        self._gauges[key] = value
        
        # Also track in aggregated metrics
        self._aggregated.record(f"{name}_gauge", value)
    
    def record_timing(self, name: str, duration: float, labels: Optional[Dict[str, str]] = None):
        """Record a timing measurement."""
        key = self._make_key(name, labels)
        self._timings[key].append({
            'timestamp': time.time(),
            'duration': duration
        })
        
        # Also track in aggregated metrics
        self._aggregated.record(f"{name}_duration", duration)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics."""
        elapsed = time.time() - self._start_time
        
        metrics = {
            'counters': {},
            'gauges': dict(self._gauges),
            'timings': {}
        }
        
        # Process counters
        for key, value in self._counters.items():
            metrics['counters'][key] = {
                'total': value,
                'rate_per_second': value / elapsed if elapsed > 0 else 0
            }
        
        # Process timings
        for key, timing_list in self._timings.items():
            if timing_list:
                durations = [t['duration'] for t in timing_list]
                metrics['timings'][key] = {
                    'count': len(durations),
                    'min': min(durations),
                    'max': max(durations),
                    'avg': sum(durations) / len(durations),
                    'last': durations[-1]
                }
        
        return metrics
    
    def reset(self):
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._timings.clear()
        self._start_time = time.time()
    
    @staticmethod
    def _make_key(name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name
        
        label_str = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


def track_execution_time(metric_name: Optional[str] = None, 
                        labels: Optional[Dict[str, str]] = None,
                        metrics_collector: Optional[MetricsCollector] = None):
    """
    Decorator to track function execution time.
    
    Args:
        metric_name: Custom metric name (defaults to function name)
        labels: Optional labels for the metric
        metrics_collector: Optional metrics collector instance
    """
    def decorator(func):
        nonlocal metric_name
        if metric_name is None:
            metric_name = func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                if metrics_collector:
                    metrics_collector.record_timing(metric_name, duration, labels)
                    metrics_collector.increment_counter(f"{metric_name}_success", 1, labels)
                
                return result
            
            except Exception:
                duration = time.time() - start_time
                
                if metrics_collector:
                    metrics_collector.record_timing(metric_name, duration, labels)
                    metrics_collector.increment_counter(f"{metric_name}_error", 1, labels)
                
                raise
        
        return wrapper
    return decorator


class Timer:
    """Context manager for timing code blocks."""
    
    def __init__(self, metric_name: str, 
                 labels: Optional[Dict[str, str]] = None,
                 metrics_collector: Optional[MetricsCollector] = None):
        self.metric_name = metric_name
        self.labels = labels
        self.metrics_collector = metrics_collector
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if self.metrics_collector:
            self.metrics_collector.record_timing(self.metric_name, duration, self.labels)
            
            if exc_type is not None:
                self.metrics_collector.increment_counter(f"{self.metric_name}_error", 1, self.labels)
            else:
                self.metrics_collector.increment_counter(f"{self.metric_name}_success", 1, self.labels)