"""
Version 2: Balanced - Performance profiling and optimization utilities.
Implements decorators and tools for performance monitoring and optimization.
"""

import time
import cProfile
import pstats
import io
import functools
import threading
import psutil
import gc
from typing import Callable, Dict, Any, Optional, List, Tuple
from contextlib import contextmanager
from datetime import datetime
import tracemalloc
import numpy as np

from .logging_config import get_logger
from .metrics import get_aggregated_metrics, timer


logger = get_logger(__name__)
aggregated_metrics = get_aggregated_metrics()


class PerformanceProfiler:
    """Advanced performance profiler with memory tracking."""
    
    def __init__(self, name: str):
        self.name = name
        self.profiler = cProfile.Profile()
        self.memory_tracking = False
        self.start_memory = 0
        self.peak_memory = 0
        self.gc_stats_before = None
        
    def start(self, track_memory: bool = True):
        """Start profiling."""
        self.profiler.enable()
        
        if track_memory:
            self.memory_tracking = True
            tracemalloc.start()
            self.start_memory = self._get_memory_usage()
            self.gc_stats_before = gc.get_stats()
            
        logger.info(f"Started profiling: {self.name}")
    
    def stop(self) -> Dict[str, Any]:
        """Stop profiling and return results."""
        self.profiler.disable()
        
        # Get profiling stats
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s)
        ps.strip_dirs()
        ps.sort_stats('cumulative')
        ps.print_stats(20)  # Top 20 functions
        
        profile_output = s.getvalue()
        
        results = {
            'name': self.name,
            'profile': profile_output
        }
        
        # Memory tracking results
        if self.memory_tracking:
            current_memory = self._get_memory_usage()
            memory_delta = current_memory - self.start_memory
            
            # Get top memory allocations
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')[:10]
            
            memory_stats = {
                'start_memory_mb': self.start_memory / 1024 / 1024,
                'current_memory_mb': current_memory / 1024 / 1024,
                'memory_delta_mb': memory_delta / 1024 / 1024,
                'top_allocations': [
                    {
                        'file': stat.filename,
                        'line': stat.lineno,
                        'size_mb': stat.size / 1024 / 1024,
                        'count': stat.count
                    }
                    for stat in top_stats
                ]
            }
            
            # GC statistics
            gc_stats_after = gc.get_stats()
            gc_info = {
                'collections': sum(s['collections'] for s in gc_stats_after) - 
                              sum(s['collections'] for s in self.gc_stats_before),
                'collected': sum(s['collected'] for s in gc_stats_after) - 
                            sum(s['collected'] for s in self.gc_stats_before)
            }
            
            memory_stats['gc'] = gc_info
            results['memory'] = memory_stats
            
            tracemalloc.stop()
        
        logger.info(
            f"Stopped profiling: {self.name}",
            extra={'extra_fields': results}
        )
        
        return results
    
    def _get_memory_usage(self) -> int:
        """Get current memory usage in bytes."""
        process = psutil.Process()
        return process.memory_info().rss


def profile_function(
    name: Optional[str] = None,
    track_memory: bool = True,
    log_results: bool = True
):
    """
    Decorator for profiling function performance.
    
    Args:
        name: Profile name (defaults to function name)
        track_memory: Whether to track memory usage
        log_results: Whether to log profiling results
    """
    def decorator(func):
        nonlocal name
        if name is None:
            name = f"{func.__module__}.{func.__name__}"
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            profiler = PerformanceProfiler(name)
            profiler.start(track_memory)
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                profile_results = profiler.stop()
                
                if log_results:
                    logger.info(
                        f"Performance profile for {name}",
                        extra={'extra_fields': {'profile_results': profile_results}}
                    )
                
                # Record metrics
                if 'memory' in profile_results:
                    aggregated_metrics.record(
                        f"{name}_memory_delta_mb",
                        profile_results['memory']['memory_delta_mb']
                    )
        
        return wrapper
    return decorator


class MemoryMonitor:
    """Monitor memory usage over time."""
    
    def __init__(self, interval: float = 1.0, max_samples: int = 1000):
        self.interval = interval
        self.max_samples = max_samples
        self.samples = []
        self._running = False
        self._thread = None
        
    def start(self):
        """Start monitoring."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
        logger.info("Memory monitoring started")
    
    def stop(self) -> Dict[str, Any]:
        """Stop monitoring and return statistics."""
        self._running = False
        if self._thread:
            self._thread.join()
        
        if not self.samples:
            return {}
        
        memory_values = [s['memory_mb'] for s in self.samples]
        
        stats = {
            'samples': len(self.samples),
            'duration_seconds': self.samples[-1]['timestamp'] - self.samples[0]['timestamp'],
            'memory_mb': {
                'min': min(memory_values),
                'max': max(memory_values),
                'mean': np.mean(memory_values),
                'std': np.std(memory_values),
                'p50': np.percentile(memory_values, 50),
                'p90': np.percentile(memory_values, 90),
                'p99': np.percentile(memory_values, 99)
            }
        }
        
        logger.info("Memory monitoring stopped", extra={'extra_fields': stats})
        return stats
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        start_time = time.time()
        
        while self._running:
            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                
                sample = {
                    'timestamp': time.time() - start_time,
                    'memory_mb': memory_mb,
                    'cpu_percent': process.cpu_percent()
                }
                
                self.samples.append(sample)
                
                # Trim old samples
                if len(self.samples) > self.max_samples:
                    self.samples = self.samples[-self.max_samples:]
                
                # Record in metrics
                aggregated_metrics.record('memory_usage_mb', memory_mb)
                
                time.sleep(self.interval)
                
            except Exception as e:
                logger.error(f"Error in memory monitoring: {str(e)}")


@contextmanager
def memory_monitor(name: str):
    """Context manager for monitoring memory usage."""
    monitor = MemoryMonitor()
    monitor.start()
    
    try:
        yield monitor
    finally:
        stats = monitor.stop()
        
        logger.info(
            f"Memory usage for {name}",
            extra={'extra_fields': stats}
        )


class TimeoutError(Exception):
    """Timeout error for function execution."""
    pass


def timeout(seconds: float):
    """
    Decorator to add timeout to function execution.
    
    Args:
        seconds: Timeout in seconds
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            exception = [None]
            
            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e
            
            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(seconds)
            
            if thread.is_alive():
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds} seconds")
            
            if exception[0]:
                raise exception[0]
            
            return result[0]
        
        return wrapper
    return decorator


class ResourceLimiter:
    """Limit resource usage for functions."""
    
    def __init__(self,
                 max_memory_mb: Optional[float] = None,
                 max_cpu_percent: Optional[float] = None,
                 check_interval: float = 0.1):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_percent = max_cpu_percent
        self.check_interval = check_interval
        
    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            process = psutil.Process()
            
            def check_resources():
                while True:
                    # Check memory
                    if self.max_memory_mb:
                        memory_mb = process.memory_info().rss / 1024 / 1024
                        if memory_mb > self.max_memory_mb:
                            raise MemoryError(
                                f"Memory limit exceeded: {memory_mb:.1f}MB > {self.max_memory_mb}MB"
                            )
                    
                    # Check CPU
                    if self.max_cpu_percent:
                        cpu_percent = process.cpu_percent()
                        if cpu_percent > self.max_cpu_percent:
                            logger.warning(
                                f"High CPU usage: {cpu_percent:.1f}% > {self.max_cpu_percent}%"
                            )
                    
                    time.sleep(self.check_interval)
            
            # Start resource monitoring thread
            monitor_thread = threading.Thread(target=check_resources, daemon=True)
            monitor_thread.start()
            
            try:
                return func(*args, **kwargs)
            finally:
                # Thread will die with the process
                pass
        
        return wrapper


def optimize_dataframe_memory(df):
    """
    Optimize pandas DataFrame memory usage.
    
    Args:
        df: pandas DataFrame
        
    Returns:
        Optimized DataFrame
    """
    import pandas as pd
    
    initial_memory = df.memory_usage(deep=True).sum() / 1024 / 1024
    
    for col in df.columns:
        col_type = df[col].dtype
        
        if col_type != 'object':
            c_min = df[col].min()
            c_max = df[col].max()
            
            # Integer optimization
            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
            
            # Float optimization
            elif str(col_type)[:5] == 'float':
                if c_min > np.finfo(np.float16).min and c_max < np.finfo(np.float16).max:
                    df[col] = df[col].astype(np.float16)
                elif c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
        
        # Category optimization for object columns
        else:
            num_unique_values = len(df[col].unique())
            num_total_values = len(df[col])
            if num_unique_values / num_total_values < 0.5:
                df[col] = df[col].astype('category')
    
    final_memory = df.memory_usage(deep=True).sum() / 1024 / 1024
    
    logger.info(
        f"DataFrame memory optimized",
        extra={'extra_fields': {
            'initial_memory_mb': initial_memory,
            'final_memory_mb': final_memory,
            'reduction_percent': (1 - final_memory / initial_memory) * 100
        }}
    )
    
    return df


class BatchProcessor:
    """Process data in optimized batches."""
    
    def __init__(self,
                 batch_size: int = 1000,
                 max_workers: int = 4,
                 memory_limit_mb: Optional[float] = None):
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.memory_limit_mb = memory_limit_mb
        
    def process(self,
                data: List[Any],
                process_func: Callable,
                progress_callback: Optional[Callable] = None) -> List[Any]:
        """
        Process data in batches.
        
        Args:
            data: List of items to process
            process_func: Function to process each item
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of results
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = [None] * len(data)
        total_items = len(data)
        processed = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit batches
            futures = {}
            
            for i in range(0, total_items, self.batch_size):
                batch = data[i:i + self.batch_size]
                batch_start = i
                
                future = executor.submit(self._process_batch, batch, process_func)
                futures[future] = batch_start
            
            # Collect results
            for future in as_completed(futures):
                batch_start = futures[future]
                
                try:
                    batch_results = future.result()
                    
                    # Store results
                    for j, result in enumerate(batch_results):
                        results[batch_start + j] = result
                    
                    processed += len(batch_results)
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(processed, total_items)
                    
                    # Check memory usage
                    if self.memory_limit_mb:
                        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                        if memory_mb > self.memory_limit_mb:
                            logger.warning(
                                f"Memory limit approaching: {memory_mb:.1f}MB / {self.memory_limit_mb}MB"
                            )
                            gc.collect()
                    
                except Exception as e:
                    logger.error(f"Error processing batch at {batch_start}: {str(e)}")
                    # Fill with None or handle error appropriately
                    batch_size = min(self.batch_size, total_items - batch_start)
                    for j in range(batch_size):
                        results[batch_start + j] = None
        
        return results
    
    def _process_batch(self, batch: List[Any], process_func: Callable) -> List[Any]:
        """Process a single batch."""
        return [process_func(item) for item in batch]


# Performance tips logging
def log_performance_tips(operation: str, duration: float, item_count: int):
    """Log performance tips based on operation metrics."""
    items_per_second = item_count / duration if duration > 0 else 0
    
    tips = []
    
    # Slow operation tips
    if items_per_second < 100:
        tips.append("Consider batch processing or parallelization")
    
    if duration > 60:
        tips.append("Long operation - consider adding progress tracking")
    
    if item_count > 10000 and items_per_second < 1000:
        tips.append("Large dataset - consider using generators or chunking")
    
    if tips:
        logger.info(
            f"Performance tips for {operation}",
            extra={'extra_fields': {
                'duration_seconds': duration,
                'item_count': item_count,
                'items_per_second': items_per_second,
                'tips': tips
            }}
        )