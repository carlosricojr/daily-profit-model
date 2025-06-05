"""
Version 2: Balanced - Comprehensive metrics with Prometheus integration.
Implements Prometheus metrics, custom metric types, and metric aggregation.
"""

import time
import os
from typing import Dict, Any, Optional, List, Callable, Union
from collections import defaultdict, deque
from datetime import datetime
import threading
from functools import wraps
from contextlib import contextmanager

# Prometheus client
try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary,
        CollectorRegistry, generate_latest,
        push_to_gateway, REGISTRY
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Fallback implementations
    class Counter:
        def __init__(self, name, documentation, labelnames=()):
            self.name = name
            self._value = 0
        def inc(self, amount=1): self._value += amount
        def labels(self, **kwargs): return self
    
    class Gauge:
        def __init__(self, name, documentation, labelnames=()):
            self.name = name
            self._value = 0
        def set(self, value): self._value = value
        def inc(self, amount=1): self._value += amount
        def dec(self, amount=1): self._value -= amount
        def labels(self, **kwargs): return self
    
    class Histogram:
        def __init__(self, name, documentation, labelnames=(), buckets=None):
            self.name = name
        def observe(self, value): pass
        def labels(self, **kwargs): return self
    
    class Summary:
        def __init__(self, name, documentation, labelnames=()):
            self.name = name
        def observe(self, value): pass
        def labels(self, **kwargs): return self

from .logging_config import get_logger


logger = get_logger(__name__)


class MetricType:
    """Enum for metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class PrometheusMetrics:
    """Prometheus metrics collection with fallback support."""
    
    def __init__(self, namespace: str = "daily_profit_model", subsystem: str = ""):
        self.namespace = namespace
        self.subsystem = subsystem
        self._metrics = {}
        self._registry = CollectorRegistry() if PROMETHEUS_AVAILABLE else None
        
        # Initialize core metrics
        self._initialize_core_metrics()
        
        logger.info(
            "Prometheus metrics initialized",
            extra={'extra_fields': {
                'prometheus_available': PROMETHEUS_AVAILABLE,
                'namespace': namespace,
                'subsystem': subsystem
            }}
        )
    
    def _initialize_core_metrics(self):
        """Initialize core application metrics."""
        # Request metrics
        self.request_counter = self.create_counter(
            'requests_total',
            'Total number of requests',
            ['method', 'endpoint', 'status']
        )
        
        self.request_duration = self.create_histogram(
            'request_duration_seconds',
            'Request duration in seconds',
            ['method', 'endpoint'],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
        
        # Database metrics
        self.db_connections_active = self.create_gauge(
            'db_connections_active',
            'Number of active database connections',
            ['database']
        )
        
        self.db_operations_total = self.create_counter(
            'db_operations_total',
            'Total number of database operations',
            ['operation', 'table', 'status']
        )
        
        self.db_operation_duration = self.create_histogram(
            'db_operation_duration_seconds',
            'Database operation duration in seconds',
            ['operation', 'table'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
        )
        
        # API client metrics
        self.api_requests_total = self.create_counter(
            'api_requests_total',
            'Total number of API requests',
            ['endpoint', 'method', 'status_code']
        )
        
        self.api_request_duration = self.create_histogram(
            'api_request_duration_seconds',
            'API request duration in seconds',
            ['endpoint', 'method'],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
        )
        
        # Pipeline metrics
        self.pipeline_executions_total = self.create_counter(
            'pipeline_executions_total',
            'Total number of pipeline executions',
            ['stage', 'status']
        )
        
        self.pipeline_records_processed = self.create_counter(
            'pipeline_records_processed_total',
            'Total number of records processed',
            ['stage']
        )
        
        self.pipeline_duration = self.create_histogram(
            'pipeline_duration_seconds',
            'Pipeline execution duration in seconds',
            ['stage'],
            buckets=[1.0, 10.0, 60.0, 300.0, 600.0, 1800.0, 3600.0]
        )
        
        # System metrics
        self.memory_usage_bytes = self.create_gauge(
            'memory_usage_bytes',
            'Memory usage in bytes'
        )
        
        self.cpu_usage_percent = self.create_gauge(
            'cpu_usage_percent',
            'CPU usage percentage'
        )
    
    def create_counter(self, name: str, description: str, labelnames: List[str] = None) -> Counter:
        """Create a counter metric."""
        labelnames = labelnames or []
        full_name = f"{self.namespace}_{self.subsystem}_{name}" if self.subsystem else f"{self.namespace}_{name}"
        
        if PROMETHEUS_AVAILABLE:
            metric = Counter(full_name, description, labelnames, registry=self._registry)
        else:
            metric = Counter(full_name, description, labelnames)
        
        self._metrics[name] = metric
        return metric
    
    def create_gauge(self, name: str, description: str, labelnames: List[str] = None) -> Gauge:
        """Create a gauge metric."""
        labelnames = labelnames or []
        full_name = f"{self.namespace}_{self.subsystem}_{name}" if self.subsystem else f"{self.namespace}_{name}"
        
        if PROMETHEUS_AVAILABLE:
            metric = Gauge(full_name, description, labelnames, registry=self._registry)
        else:
            metric = Gauge(full_name, description, labelnames)
        
        self._metrics[name] = metric
        return metric
    
    def create_histogram(self, name: str, description: str, labelnames: List[str] = None, 
                        buckets: List[float] = None) -> Histogram:
        """Create a histogram metric."""
        labelnames = labelnames or []
        full_name = f"{self.namespace}_{self.subsystem}_{name}" if self.subsystem else f"{self.namespace}_{name}"
        
        if PROMETHEUS_AVAILABLE:
            metric = Histogram(full_name, description, labelnames, buckets=buckets, registry=self._registry)
        else:
            metric = Histogram(full_name, description, labelnames, buckets=buckets)
        
        self._metrics[name] = metric
        return metric
    
    def create_summary(self, name: str, description: str, labelnames: List[str] = None) -> Summary:
        """Create a summary metric."""
        labelnames = labelnames or []
        full_name = f"{self.namespace}_{self.subsystem}_{name}" if self.subsystem else f"{self.namespace}_{name}"
        
        if PROMETHEUS_AVAILABLE:
            metric = Summary(full_name, description, labelnames, registry=self._registry)
        else:
            metric = Summary(full_name, description, labelnames)
        
        self._metrics[name] = metric
        return metric
    
    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format."""
        if PROMETHEUS_AVAILABLE:
            return generate_latest(self._registry).decode('utf-8')
        else:
            # Simple fallback format
            lines = []
            for name, metric in self._metrics.items():
                if hasattr(metric, '_value'):
                    lines.append(f"# TYPE {name} gauge")
                    lines.append(f"{name} {metric._value}")
            return '\n'.join(lines)
    
    def push_to_gateway(self, gateway_url: str, job: str):
        """Push metrics to Prometheus Pushgateway."""
        if PROMETHEUS_AVAILABLE and gateway_url:
            try:
                push_to_gateway(gateway_url, job=job, registry=self._registry)
                logger.info(f"Pushed metrics to gateway {gateway_url}")
            except Exception as e:
                logger.error(f"Failed to push metrics to gateway: {str(e)}")


# Global metrics instance
_prometheus_metrics = PrometheusMetrics()


def get_prometheus_metrics() -> PrometheusMetrics:
    """Get the global Prometheus metrics instance."""
    return _prometheus_metrics


# Enhanced metrics collector with aggregation
class AggregatedMetrics:
    """Advanced metrics with aggregation and percentiles."""
    
    def __init__(self, window_size: int = 300):  # 5 minutes default
        self.window_size = window_size
        self._metrics = defaultdict(lambda: deque(maxlen=1000))
        self._aggregates = {}
        self._lock = threading.Lock()
        self._last_aggregation = time.time()
        
        # Start aggregation thread
        self._aggregation_thread = threading.Thread(target=self._aggregation_loop, daemon=True)
        self._aggregation_thread.start()
    
    def record(self, metric_name: str, value: float, timestamp: Optional[float] = None):
        """Record a metric value."""
        if timestamp is None:
            timestamp = time.time()
        
        with self._lock:
            self._metrics[metric_name].append((timestamp, value))
    
    def _aggregation_loop(self):
        """Background thread for metric aggregation."""
        while True:
            try:
                self._aggregate_metrics()
                time.sleep(10)  # Aggregate every 10 seconds
            except Exception as e:
                logger.error(f"Error in aggregation loop: {str(e)}")
    
    def _aggregate_metrics(self):
        """Aggregate metrics within the time window."""
        current_time = time.time()
        window_start = current_time - self.window_size
        
        with self._lock:
            for metric_name, values in self._metrics.items():
                # Filter values within window
                window_values = [(ts, val) for ts, val in values if ts >= window_start]
                
                if window_values:
                    values_only = [val for _, val in window_values]
                    
                    # Calculate aggregates
                    self._aggregates[metric_name] = {
                        'count': len(values_only),
                        'sum': sum(values_only),
                        'min': min(values_only),
                        'max': max(values_only),
                        'avg': sum(values_only) / len(values_only),
                        'p50': self._percentile(values_only, 50),
                        'p90': self._percentile(values_only, 90),
                        'p95': self._percentile(values_only, 95),
                        'p99': self._percentile(values_only, 99),
                        'rate': len(values_only) / min(self.window_size, current_time - values_only[0][0])
                    }
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        
        if index >= len(sorted_values):
            return sorted_values[-1]
        
        return sorted_values[index]
    
    def get_aggregate(self, metric_name: str) -> Dict[str, float]:
        """Get aggregated metrics for a specific metric."""
        with self._lock:
            return self._aggregates.get(metric_name, {})
    
    def get_all_aggregates(self) -> Dict[str, Dict[str, float]]:
        """Get all aggregated metrics."""
        with self._lock:
            return dict(self._aggregates)


# Global aggregated metrics instance
_aggregated_metrics = AggregatedMetrics()


def get_aggregated_metrics() -> AggregatedMetrics:
    """Get the global aggregated metrics instance."""
    return _aggregated_metrics


# Decorators and context managers
def track_time(metric_name: str, labels: Optional[Dict[str, str]] = None):
    """Decorator to track function execution time."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Record in Prometheus
                if hasattr(_prometheus_metrics, 'request_duration'):
                    if labels:
                        _prometheus_metrics.request_duration.labels(**labels).observe(duration)
                    else:
                        _prometheus_metrics.request_duration.observe(duration)
                
                # Record in aggregated metrics
                _aggregated_metrics.record(f"{metric_name}_duration", duration)
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                # Record error metrics
                error_labels = {**(labels or {}), 'error': type(e).__name__}
                if hasattr(_prometheus_metrics, 'request_counter'):
                    _prometheus_metrics.request_counter.labels(**{**error_labels, 'status': 'error'}).inc()
                
                _aggregated_metrics.record(f"{metric_name}_errors", 1)
                
                raise
        
        return wrapper
    return decorator


@contextmanager
def timer(metric_name: str, labels: Optional[Dict[str, str]] = None):
    """Context manager for timing code blocks."""
    start_time = time.time()
    
    try:
        yield
        duration = time.time() - start_time
        
        # Record success
        if labels:
            _prometheus_metrics.request_duration.labels(**labels).observe(duration)
        
        _aggregated_metrics.record(f"{metric_name}_duration", duration)
        
    except Exception:
        duration = time.time() - start_time
        _aggregated_metrics.record(f"{metric_name}_error_duration", duration)
        raise


# System metrics collection
class SystemMetricsCollector:
    """Collects system-level metrics."""
    
    def __init__(self, collection_interval: int = 60):
        self.collection_interval = collection_interval
        self._running = False
        self._thread = None
    
    def start(self):
        """Start collecting system metrics."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
        
        logger.info("System metrics collection started")
    
    def stop(self):
        """Stop collecting system metrics."""
        self._running = False
        if self._thread:
            self._thread.join()
    
    def _collect_loop(self):
        """Main collection loop."""
        while self._running:
            try:
                self._collect_metrics()
                time.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"Error collecting system metrics: {str(e)}")
    
    def _collect_metrics(self):
        """Collect system metrics."""
        try:
            import psutil
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            _prometheus_metrics.cpu_usage_percent.set(cpu_percent)
            _aggregated_metrics.record('system_cpu_percent', cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            _prometheus_metrics.memory_usage_bytes.set(memory.used)
            _aggregated_metrics.record('system_memory_bytes', memory.used)
            _aggregated_metrics.record('system_memory_percent', memory.percent)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            _aggregated_metrics.record('system_disk_used_bytes', disk.used)
            _aggregated_metrics.record('system_disk_percent', disk.percent)
            
            # Process-specific metrics
            process = psutil.Process(os.getpid())
            _aggregated_metrics.record('process_cpu_percent', process.cpu_percent())
            _aggregated_metrics.record('process_memory_bytes', process.memory_info().rss)
            _aggregated_metrics.record('process_threads', process.num_threads())
            
        except ImportError:
            logger.warning("psutil not available, system metrics collection disabled")
            self._running = False
        except Exception as e:
            logger.error(f"Error collecting system metrics: {str(e)}")


# Global system metrics collector
_system_metrics = SystemMetricsCollector()


def start_system_metrics_collection():
    """Start collecting system metrics."""
    _system_metrics.start()


def stop_system_metrics_collection():
    """Stop collecting system metrics."""
    _system_metrics.stop()


# Metric helpers for specific use cases
def track_db_metrics(operation: str, table: str, rows: int, duration: float, success: bool = True):
    """Track database operation metrics."""
    status = 'success' if success else 'error'
    
    _prometheus_metrics.db_operations_total.labels(
        operation=operation,
        table=table,
        status=status
    ).inc()
    
    _prometheus_metrics.db_operation_duration.labels(
        operation=operation,
        table=table
    ).observe(duration)
    
    _aggregated_metrics.record(f'db_{operation}_{table}_duration', duration)
    _aggregated_metrics.record(f'db_{operation}_{table}_rows', rows)


def track_api_metrics(endpoint: str, method: str, status_code: int, duration: float):
    """Track API request metrics."""
    _prometheus_metrics.api_requests_total.labels(
        endpoint=endpoint,
        method=method,
        status_code=str(status_code)
    ).inc()
    
    _prometheus_metrics.api_request_duration.labels(
        endpoint=endpoint,
        method=method
    ).observe(duration)
    
    _aggregated_metrics.record(f'api_{endpoint}_{method}_duration', duration)
    
    if status_code >= 400:
        _aggregated_metrics.record(f'api_{endpoint}_{method}_errors', 1)


def track_pipeline_metrics(stage: str, status: str, records: int, duration: float):
    """Track pipeline execution metrics."""
    _prometheus_metrics.pipeline_executions_total.labels(
        stage=stage,
        status=status
    ).inc()
    
    if records > 0:
        _prometheus_metrics.pipeline_records_processed.labels(stage=stage).inc(records)
    
    _prometheus_metrics.pipeline_duration.labels(stage=stage).observe(duration)
    
    _aggregated_metrics.record(f'pipeline_{stage}_duration', duration)
    _aggregated_metrics.record(f'pipeline_{stage}_records', records)