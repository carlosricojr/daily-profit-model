"""
Comprehensive health check utilities for the pipeline.
Provides advanced health monitoring with SLA tracking, trend analysis, and alerting.
"""

import os
import logging
import psutil
import time
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import requests
from dataclasses import dataclass, asdict
from pathlib import Path

from utils.database import get_db_manager

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Structured health check result."""
    name: str
    status: str  # 'healthy', 'warning', 'unhealthy', 'error'
    message: str
    timestamp: datetime
    metrics: Dict[str, Any]
    duration_ms: float
    details: Optional[Dict[str, Any]] = None


@dataclass
class SLADefinition:
    """SLA definition for health checks."""
    name: str
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    unit: str
    direction: str  # 'above', 'below'


class HealthChecker:
    """Comprehensive health checker with SLA monitoring and trend analysis."""
    
    def __init__(self):
        """Initialize comprehensive health checker."""
        self.db_manager = get_db_manager()
        self.health_history_file = Path('./health_history.json')
        self.sla_definitions = self._load_sla_definitions()
        
        # Load historical data
        self.health_history = self._load_health_history()
        
        # Enhanced check registry
        self.checks = {
            'database_connectivity': self.check_database_connectivity,
            'database_performance': self.check_database_performance,
            'api_availability': self.check_api_availability,
            'api_performance': self.check_api_performance,
            'system_resources': self.check_system_resources,
            'data_freshness': self.check_data_freshness,
            'data_quality': self.check_data_quality,
            'pipeline_sla': self.check_pipeline_sla,
            'model_availability': self.check_model_availability,
            'disk_io_performance': self.check_disk_io_performance,
            'network_connectivity': self.check_network_connectivity,
        }
    
    def _load_sla_definitions(self) -> Dict[str, SLADefinition]:
        """Load SLA definitions for health checks."""
        return {
            'database_query_time': SLADefinition(
                name='Database Query Performance',
                metric_name='avg_query_time_ms',
                warning_threshold=1000.0,
                critical_threshold=5000.0,
                unit='milliseconds',
                direction='above'
            ),
            'api_response_time': SLADefinition(
                name='API Response Time',
                metric_name='response_time_ms',
                warning_threshold=2000.0,
                critical_threshold=10000.0,
                unit='milliseconds',
                direction='above'
            ),
            'disk_space': SLADefinition(
                name='Disk Space Usage',
                metric_name='percent_used',
                warning_threshold=80.0,
                critical_threshold=90.0,
                unit='percent',
                direction='above'
            ),
            'memory_usage': SLADefinition(
                name='Memory Usage',
                metric_name='percent_used',
                warning_threshold=85.0,
                critical_threshold=95.0,
                unit='percent',
                direction='above'
            ),
            'data_lag_hours': SLADefinition(
                name='Data Freshness',
                metric_name='hours_old',
                warning_threshold=25.0,
                critical_threshold=48.0,
                unit='hours',
                direction='above'
            ),
            'pipeline_duration': SLADefinition(
                name='Pipeline Execution Time',
                metric_name='duration_minutes',
                warning_threshold=240.0,  # 4 hours
                critical_threshold=360.0,  # 6 hours
                unit='minutes',
                direction='above'
            ),
        }
    
    def _load_health_history(self) -> List[Dict[str, Any]]:
        """Load historical health check data."""
        if self.health_history_file.exists():
            try:
                with open(self.health_history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load health history: {e}")
        return []
    
    def _save_health_history(self):
        """Save health check history to file."""
        try:
            # Keep only last 1000 entries
            if len(self.health_history) > 1000:
                self.health_history = self.health_history[-1000:]
            
            with open(self.health_history_file, 'w') as f:
                json.dump(self.health_history, f, default=str, indent=2)
        except Exception as e:
            logger.error(f"Failed to save health history: {e}")
    
    def run_all_checks(self, include_trends: bool = True) -> Dict[str, Any]:
        """
        Run all health checks with enhanced monitoring.
        
        Args:
            include_trends: Whether to include trend analysis
            
        Returns:
            Comprehensive health check results
        """
        start_time = datetime.now()
        results = {
            'timestamp': start_time.isoformat(),
            'overall_status': 'healthy',
            'checks': {},
            'sla_violations': [],
            'summary': {
                'total_checks': len(self.checks),
                'healthy': 0,
                'warnings': 0,
                'unhealthy': 0,
                'errors': 0
            }
        }
        
        # Run all health checks
        for check_name, check_func in self.checks.items():
            try:
                check_start = time.time()
                result = check_func()
                duration_ms = (time.time() - check_start) * 1000
                
                # Create structured result
                health_result = HealthCheckResult(
                    name=check_name,
                    status=result.get('status', 'error'),
                    message=result.get('message', 'No message'),
                    timestamp=datetime.now(),
                    metrics=result.get('metrics', {}),
                    duration_ms=duration_ms,
                    details=result.get('details')
                )
                
                results['checks'][check_name] = asdict(health_result)
                
                # Update summary
                status = health_result.status
                if status == 'healthy':
                    results['summary']['healthy'] += 1
                elif status == 'warning':
                    results['summary']['warnings'] += 1
                    if results['overall_status'] == 'healthy':
                        results['overall_status'] = 'warning'
                elif status == 'unhealthy':
                    results['summary']['unhealthy'] += 1
                    results['overall_status'] = 'unhealthy'
                elif status == 'error':
                    results['summary']['errors'] += 1
                    results['overall_status'] = 'unhealthy'
                
                # Check SLA violations
                sla_violations = self._check_sla_violations(health_result)
                results['sla_violations'].extend(sla_violations)
                
            except Exception as e:
                logger.error(f"Health check {check_name} failed with exception: {e}")
                results['checks'][check_name] = {
                    'name': check_name,
                    'status': 'error',
                    'message': f"Check failed: {str(e)}",
                    'timestamp': datetime.now().isoformat(),
                    'metrics': {},
                    'duration_ms': 0
                }
                results['summary']['errors'] += 1
                results['overall_status'] = 'unhealthy'
        
        # Add trend analysis if requested
        if include_trends:
            results['trends'] = self._analyze_trends()
        
        # Store in history
        self.health_history.append({
            'timestamp': start_time.isoformat(),
            'overall_status': results['overall_status'],
            'summary': results['summary'],
            'sla_violations': len(results['sla_violations'])
        })
        self._save_health_history()
        
        total_duration = (datetime.now() - start_time).total_seconds()
        results['total_duration_seconds'] = total_duration
        
        return results
    
    def _check_sla_violations(self, result: HealthCheckResult) -> List[Dict[str, Any]]:
        """Check for SLA violations in health check result."""
        violations = []
        
        for sla_key, sla in self.sla_definitions.items():
            if sla.metric_name in result.metrics:
                value = result.metrics[sla.metric_name]
                
                violation_level = None
                if sla.direction == 'above':
                    if value >= sla.critical_threshold:
                        violation_level = 'critical'
                    elif value >= sla.warning_threshold:
                        violation_level = 'warning'
                elif sla.direction == 'below':
                    if value <= sla.critical_threshold:
                        violation_level = 'critical'
                    elif value <= sla.warning_threshold:
                        violation_level = 'warning'
                
                if violation_level:
                    violations.append({
                        'sla_name': sla.name,
                        'check_name': result.name,
                        'metric_name': sla.metric_name,
                        'actual_value': value,
                        'threshold': sla.critical_threshold if violation_level == 'critical' else sla.warning_threshold,
                        'unit': sla.unit,
                        'level': violation_level,
                        'timestamp': result.timestamp.isoformat()
                    })
        
        return violations
    
    def _analyze_trends(self) -> Dict[str, Any]:
        """Analyze trends in health check data."""
        if len(self.health_history) < 10:
            return {'message': 'Insufficient data for trend analysis'}
        
        recent_history = self.health_history[-24:]  # Last 24 checks
        older_history = self.health_history[-48:-24] if len(self.health_history) >= 48 else []
        
        trends = {
            'degradation_detected': False,
            'improvement_detected': False,
            'stability_score': 0.0,
            'failure_rate_24h': 0.0,
            'average_sla_violations': 0.0
        }
        
        # Calculate failure rates
        recent_failures = sum(1 for h in recent_history if h['overall_status'] in ['unhealthy', 'error'])
        trends['failure_rate_24h'] = recent_failures / len(recent_history) if recent_history else 0
        
        # Calculate average SLA violations
        recent_violations = [h['sla_violations'] for h in recent_history]
        trends['average_sla_violations'] = sum(recent_violations) / len(recent_violations) if recent_violations else 0
        
        # Detect degradation/improvement
        if older_history:
            older_failures = sum(1 for h in older_history if h['overall_status'] in ['unhealthy', 'error'])
            older_failure_rate = older_failures / len(older_history)
            
            if trends['failure_rate_24h'] > older_failure_rate * 1.5:
                trends['degradation_detected'] = True
            elif trends['failure_rate_24h'] < older_failure_rate * 0.5:
                trends['improvement_detected'] = True
        
        # Calculate stability score (0-1, higher is better)
        status_weights = {'healthy': 1.0, 'warning': 0.7, 'unhealthy': 0.3, 'error': 0.0}
        total_score = sum(status_weights.get(h['overall_status'], 0) for h in recent_history)
        trends['stability_score'] = total_score / len(recent_history) if recent_history else 0
        
        return trends
    
    def check_database_connectivity(self) -> Dict[str, Any]:
        """Enhanced database connectivity check."""
        try:
            start_time = time.time()
            
            # Test model database
            model_result = self.db_manager.model_db.execute_query("SELECT 1 as test, current_timestamp as ts")
            model_time = time.time() - start_time
            
            # Test source database
            start_time = time.time()
            source_result = self.db_manager.source_db.execute_query("SELECT 1 as test, current_timestamp as ts")
            source_time = time.time() - start_time
            
            # Check connection pool status
            model_pool_size = getattr(self.db_manager.model_db.pool, '_used', 0)
            source_pool_size = getattr(self.db_manager.source_db.pool, '_used', 0)
            
            avg_query_time = (model_time + source_time) / 2 * 1000  # Convert to milliseconds
            
            status = 'healthy'
            if avg_query_time > 5000:
                status = 'unhealthy'
            elif avg_query_time > 1000:
                status = 'warning'
            
            return {
                'status': status,
                'message': f'Database connectivity verified (avg: {avg_query_time:.1f}ms)',
                'metrics': {
                    'model_db_response_time_ms': model_time * 1000,
                    'source_db_response_time_ms': source_time * 1000,
                    'avg_query_time_ms': avg_query_time,
                    'model_pool_connections': model_pool_size,
                    'source_pool_connections': source_pool_size
                }
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'message': f'Database connectivity failed: {str(e)}',
                'metrics': {}
            }
    
    def check_database_performance(self) -> Dict[str, Any]:
        """Check database performance metrics."""
        try:
            performance_queries = [
                {
                    'name': 'table_sizes',
                    'query': """
                        SELECT 
                            schemaname,
                            tablename,
                            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                        FROM pg_tables 
                        WHERE schemaname = 'prop_trading_model'
                        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                        LIMIT 5
                    """
                },
                {
                    'name': 'active_connections',
                    'query': """
                        SELECT count(*) as active_connections
                        FROM pg_stat_activity
                        WHERE state = 'active'
                    """
                },
                {
                    'name': 'slow_queries',
                    'query': """
                        SELECT count(*) as slow_queries
                        FROM pg_stat_activity
                        WHERE state = 'active' 
                        AND query_start < now() - interval '1 minute'
                    """
                }
            ]
            
            metrics = {}
            total_time = 0
            
            for query_info in performance_queries:
                start_time = time.time()
                try:
                    result = self.db_manager.model_db.execute_query(query_info['query'])
                    query_time = (time.time() - start_time) * 1000
                    total_time += query_time
                    
                    metrics[f"{query_info['name']}_time_ms"] = query_time
                    if query_info['name'] == 'active_connections':
                        metrics['active_connections'] = result[0]['active_connections'] if result else 0
                    elif query_info['name'] == 'slow_queries':
                        metrics['slow_queries'] = result[0]['slow_queries'] if result else 0
                        
                except Exception as e:
                    logger.warning(f"Performance query {query_info['name']} failed: {e}")
                    metrics[f"{query_info['name']}_error"] = str(e)
            
            avg_time = total_time / len(performance_queries)
            metrics['avg_performance_query_time_ms'] = avg_time
            
            status = 'healthy'
            if avg_time > 2000:
                status = 'unhealthy'
            elif avg_time > 500:
                status = 'warning'
            
            slow_queries = metrics.get('slow_queries', 0)
            if slow_queries > 5:
                status = 'warning'
            
            return {
                'status': status,
                'message': f'Database performance check completed (avg: {avg_time:.1f}ms)',
                'metrics': metrics
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Database performance check failed: {str(e)}',
                'metrics': {}
            }
    
    def check_api_availability(self) -> Dict[str, Any]:
        """Enhanced API availability check."""
        api_base_url = os.getenv('RISK_API_BASE_URL', 'https://d3m1s17i9h2y69.cloudfront.net')
        api_key = os.getenv('RISK_API_KEY', '')
        
        endpoints_to_test = [
            {'path': '/accounts', 'timeout': 10},
            {'path': '/v2/metrics/alltime', 'timeout': 15},
            {'path': '/v2/trades/open', 'timeout': 10}
        ]
        
        results = []
        total_time = 0
        
        for endpoint in endpoints_to_test:
            try:
                start_time = time.time()
                response = requests.get(
                    f"{api_base_url}{endpoint['path']}",
                    headers={'X-API-KEY': api_key},
                    timeout=endpoint['timeout']
                )
                
                response_time = (time.time() - start_time) * 1000
                total_time += response_time
                
                results.append({
                    'endpoint': endpoint['path'],
                    'status_code': response.status_code,
                    'response_time_ms': response_time,
                    'success': response.status_code == 200
                })
                
            except Exception as e:
                results.append({
                    'endpoint': endpoint['path'],
                    'status_code': 0,
                    'response_time_ms': 0,
                    'success': False,
                    'error': str(e)
                })
        
        successful_requests = sum(1 for r in results if r['success'])
        avg_response_time = total_time / len(results) if results else 0
        success_rate = successful_requests / len(results) if results else 0
        
        status = 'healthy'
        if success_rate < 0.5:
            status = 'unhealthy'
        elif success_rate < 0.8 or avg_response_time > 10000:
            status = 'warning'
        
        return {
            'status': status,
            'message': f'API availability: {success_rate:.1%} success rate',
            'metrics': {
                'success_rate': success_rate,
                'avg_response_time_ms': avg_response_time,
                'successful_endpoints': successful_requests,
                'total_endpoints': len(results),
                'response_time_ms': avg_response_time  # For SLA checking
            },
            'details': {'endpoint_results': results}
        }
    
    def check_api_performance(self) -> Dict[str, Any]:
        """Check API performance with load testing."""
        api_base_url = os.getenv('RISK_API_BASE_URL', 'https://d3m1s17i9h2y69.cloudfront.net')
        api_key = os.getenv('RISK_API_KEY', '')
        
        # Test with multiple concurrent requests
        import concurrent.futures
        
        def make_request():
            try:
                start = time.time()
                response = requests.get(
                    f"{api_base_url}/accounts",
                    headers={'X-API-KEY': api_key},
                    timeout=30
                )
                return {
                    'success': response.status_code == 200,
                    'response_time': (time.time() - start) * 1000,
                    'status_code': response.status_code
                }
            except Exception as e:
                return {
                    'success': False,
                    'response_time': 0,
                    'error': str(e)
                }
        
        # Run 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            responses = [f.result() for f in futures]
        
        successful = [r for r in responses if r['success']]
        response_times = [r['response_time'] for r in successful]
        
        metrics = {
            'concurrent_success_rate': len(successful) / len(responses),
            'avg_response_time_ms': sum(response_times) / len(response_times) if response_times else 0,
            'max_response_time_ms': max(response_times) if response_times else 0,
            'min_response_time_ms': min(response_times) if response_times else 0,
            'total_requests': len(responses)
        }
        
        status = 'healthy'
        if metrics['concurrent_success_rate'] < 0.8:
            status = 'unhealthy'
        elif metrics['avg_response_time_ms'] > 5000:
            status = 'warning'
        
        return {
            'status': status,
            'message': f"API performance: {metrics['concurrent_success_rate']:.1%} success under load",
            'metrics': metrics
        }
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Enhanced system resource monitoring."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage for multiple paths
            disk_info = {}
            paths_to_check = ['/', '/tmp', '/var/log']
            
            for path in paths_to_check:
                if os.path.exists(path):
                    usage = psutil.disk_usage(path)
                    disk_info[path] = {
                        'total_gb': usage.total / (1024**3),
                        'free_gb': usage.free / (1024**3),
                        'used_gb': usage.used / (1024**3),
                        'percent_used': (usage.used / usage.total) * 100
                    }
            
            # Network I/O
            net_io = psutil.net_io_counters()
            
            # Process information
            current_process = psutil.Process()
            process_memory = current_process.memory_info()
            
            metrics = {
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'memory_total_gb': memory.total / (1024**3),
                'memory_available_gb': memory.available / (1024**3),
                'memory_percent_used': memory.percent,
                'percent_used': memory.percent,  # For SLA checking
                'network_bytes_sent': net_io.bytes_sent,
                'network_bytes_recv': net_io.bytes_recv,
                'process_memory_mb': process_memory.rss / (1024**2),
                'process_cpu_percent': current_process.cpu_percent(),
                'disk_usage': disk_info
            }
            
            # Determine status based on resource usage
            status = 'healthy'
            issues = []
            
            if cpu_percent > 90:
                status = 'unhealthy'
                issues.append(f'High CPU usage: {cpu_percent:.1f}%')
            elif cpu_percent > 75:
                status = 'warning'
                issues.append(f'Elevated CPU usage: {cpu_percent:.1f}%')
            
            if memory.percent > 95:
                status = 'unhealthy'
                issues.append(f'Critical memory usage: {memory.percent:.1f}%')
            elif memory.percent > 85:
                if status == 'healthy':
                    status = 'warning'
                issues.append(f'High memory usage: {memory.percent:.1f}%')
            
            # Check disk usage for all monitored paths
            for path, disk_data in disk_info.items():
                if disk_data['percent_used'] > 90:
                    status = 'unhealthy'
                    issues.append(f'Critical disk usage on {path}: {disk_data["percent_used"]:.1f}%')
                elif disk_data['percent_used'] > 80:
                    if status == 'healthy':
                        status = 'warning'
                    issues.append(f'High disk usage on {path}: {disk_data["percent_used"]:.1f}%')
            
            message = 'System resources within normal limits'
            if issues:
                message = '; '.join(issues)
            
            return {
                'status': status,
                'message': message,
                'metrics': metrics
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'System resource check failed: {str(e)}',
                'metrics': {}
            }
    
    def check_data_freshness(self) -> Dict[str, Any]:
        """Enhanced data freshness check with multiple data sources."""
        try:
            freshness_checks = [
                {
                    'name': 'metrics_daily',
                    'query': """
                        SELECT MAX(metric_date) as latest_date,
                               MAX(ingestion_timestamp) as latest_ingestion
                        FROM prop_trading_model.raw_metrics_daily
                    """,
                    'expected_lag_hours': 24
                },
                {
                    'name': 'accounts_data',
                    'query': """
                        SELECT MAX(ingestion_timestamp) as latest_ingestion
                        FROM prop_trading_model.raw_accounts_data
                    """,
                    'expected_lag_hours': 4
                },
                {
                    'name': 'trades_data',
                    'query': """
                        SELECT MAX(ingestion_timestamp) as latest_ingestion
                        FROM prop_trading_model.raw_trades
                        WHERE trade_status = 'closed'
                    """,
                    'expected_lag_hours': 2
                }
            ]
            
            results = {}
            overall_status = 'healthy'
            max_lag_hours = 0
            
            for check in freshness_checks:
                try:
                    result = self.db_manager.model_db.execute_query(check['query'])
                    
                    if result and result[0]:
                        row = result[0]
                        latest_ingestion = row.get('latest_ingestion')
                        
                        if latest_ingestion:
                            lag_hours = (datetime.now() - latest_ingestion).total_seconds() / 3600
                            max_lag_hours = max(max_lag_hours, lag_hours)
                            
                            status = 'healthy'
                            if lag_hours > check['expected_lag_hours'] * 2:
                                status = 'unhealthy'
                                overall_status = 'unhealthy'
                            elif lag_hours > check['expected_lag_hours']:
                                status = 'warning'
                                if overall_status == 'healthy':
                                    overall_status = 'warning'
                            
                            results[check['name']] = {
                                'lag_hours': lag_hours,
                                'status': status,
                                'latest_ingestion': latest_ingestion.isoformat(),
                                'expected_lag_hours': check['expected_lag_hours']
                            }
                        else:
                            results[check['name']] = {
                                'status': 'error',
                                'message': 'No data found'
                            }
                            overall_status = 'unhealthy'
                    else:
                        results[check['name']] = {
                            'status': 'error', 
                            'message': 'Query returned no results'
                        }
                        overall_status = 'unhealthy'
                        
                except Exception as e:
                    results[check['name']] = {
                        'status': 'error',
                        'message': str(e)
                    }
                    overall_status = 'unhealthy'
            
            return {
                'status': overall_status,
                'message': f'Data freshness check completed, max lag: {max_lag_hours:.1f} hours',
                'metrics': {
                    'max_lag_hours': max_lag_hours,
                    'hours_old': max_lag_hours  # For SLA checking
                },
                'details': {'freshness_results': results}
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Data freshness check failed: {str(e)}',
                'metrics': {}
            }
    
    def check_data_quality(self) -> Dict[str, Any]:
        """Comprehensive data quality assessment."""
        try:
            quality_checks = [
                {
                    'name': 'duplicate_accounts',
                    'query': """
                        SELECT COUNT(*) as duplicates
                        FROM (
                            SELECT login, COUNT(*) 
                            FROM prop_trading_model.raw_accounts_data
                            WHERE DATE(ingestion_timestamp) = CURRENT_DATE
                            GROUP BY login 
                            HAVING COUNT(*) > 1
                        ) dup
                    """,
                    'threshold': 0,
                    'comparison': 'equal'
                },
                {
                    'name': 'null_profit_values',
                    'query': """
                        SELECT COUNT(*) as null_profits
                        FROM prop_trading_model.raw_metrics_daily
                        WHERE net_profit IS NULL
                        AND metric_date >= CURRENT_DATE - INTERVAL '7 days'
                    """,
                    'threshold': 10,
                    'comparison': 'less_than'
                },
                {
                    'name': 'account_metrics_consistency',
                    'query': """
                        SELECT COUNT(*) as inconsistent_accounts
                        FROM prop_trading_model.raw_accounts_data a
                        LEFT JOIN prop_trading_model.raw_metrics_daily m
                        ON a.login = m.login AND m.metric_date = CURRENT_DATE - INTERVAL '1 day'
                        WHERE DATE(a.ingestion_timestamp) = CURRENT_DATE
                        AND m.login IS NULL
                    """,
                    'threshold': 50,
                    'comparison': 'less_than'
                },
                {
                    'name': 'extreme_profit_values',
                    'query': """
                        SELECT COUNT(*) as extreme_values
                        FROM prop_trading_model.raw_metrics_daily
                        WHERE ABS(net_profit) > 100000
                        AND metric_date >= CURRENT_DATE - INTERVAL '1 day'
                    """,
                    'threshold': 5,
                    'comparison': 'less_than'
                }
            ]
            
            results = {}
            overall_status = 'healthy'
            total_issues = 0
            
            for check in quality_checks:
                try:
                    result = self.db_manager.model_db.execute_query(check['query'])
                    
                    if result:
                        value = list(result[0].values())[0]
                        
                        status = 'healthy'
                        if check['comparison'] == 'equal' and value != check['threshold']:
                            status = 'warning'
                            if value > check['threshold'] * 5:
                                status = 'unhealthy'
                        elif check['comparison'] == 'less_than' and value >= check['threshold']:
                            status = 'warning'
                            if value >= check['threshold'] * 2:
                                status = 'unhealthy'
                        
                        if status in ['warning', 'unhealthy']:
                            total_issues += 1
                            if status == 'unhealthy' or overall_status == 'healthy':
                                overall_status = status
                        
                        results[check['name']] = {
                            'value': value,
                            'threshold': check['threshold'],
                            'status': status,
                            'comparison': check['comparison']
                        }
                    else:
                        results[check['name']] = {
                            'status': 'error',
                            'message': 'No data returned'
                        }
                        overall_status = 'unhealthy'
                        
                except Exception as e:
                    results[check['name']] = {
                        'status': 'error',
                        'message': str(e)
                    }
                    overall_status = 'unhealthy'
                    total_issues += 1
            
            return {
                'status': overall_status,
                'message': f'Data quality check completed, {total_issues} issues found',
                'metrics': {
                    'total_quality_issues': total_issues,
                    'quality_score': max(0, 1 - (total_issues / len(quality_checks)))
                },
                'details': {'quality_results': results}
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Data quality check failed: {str(e)}',
                'metrics': {}
            }
    
    def check_pipeline_sla(self) -> Dict[str, Any]:
        """Check pipeline execution SLA compliance."""
        try:
            # Check recent pipeline execution times
            query = """
            SELECT 
                pipeline_stage,
                execution_date,
                start_time,
                end_time,
                EXTRACT(EPOCH FROM (end_time - start_time))/60 as duration_minutes,
                status
            FROM prop_trading_model.pipeline_execution_log
            WHERE execution_date >= CURRENT_DATE - INTERVAL '7 days'
            AND end_time IS NOT NULL
            ORDER BY execution_date DESC, start_time DESC
            """
            
            results = self.db_manager.model_db.execute_query(query)
            
            if not results:
                return {
                    'status': 'warning',
                    'message': 'No recent pipeline execution data found',
                    'metrics': {}
                }
            
            # Analyze execution times by stage
            stage_stats = {}
            total_durations = []
            failed_executions = 0
            
            for row in results:
                stage = row['pipeline_stage']
                duration = float(row['duration_minutes']) if row['duration_minutes'] else 0
                status = row['status']
                
                if status == 'failed':
                    failed_executions += 1
                
                if stage not in stage_stats:
                    stage_stats[stage] = []
                stage_stats[stage].append(duration)
                total_durations.append(duration)
            
            # Calculate metrics
            avg_duration = sum(total_durations) / len(total_durations) if total_durations else 0
            max_duration = max(total_durations) if total_durations else 0
            failure_rate = failed_executions / len(results) if results else 0
            
            # Determine status
            status = 'healthy'
            issues = []
            
            if avg_duration > 360:  # 6 hours
                status = 'unhealthy'
                issues.append(f'Average duration exceeds SLA: {avg_duration:.1f} minutes')
            elif avg_duration > 240:  # 4 hours
                status = 'warning'
                issues.append(f'Average duration approaching SLA limit: {avg_duration:.1f} minutes')
            
            if failure_rate > 0.1:  # 10% failure rate
                status = 'unhealthy'
                issues.append(f'High failure rate: {failure_rate:.1%}')
            elif failure_rate > 0.05:  # 5% failure rate
                if status == 'healthy':
                    status = 'warning'
                issues.append(f'Elevated failure rate: {failure_rate:.1%}')
            
            message = 'Pipeline SLA compliance verified'
            if issues:
                message = '; '.join(issues)
            
            return {
                'status': status,
                'message': message,
                'metrics': {
                    'avg_duration_minutes': avg_duration,
                    'max_duration_minutes': max_duration,
                    'failure_rate': failure_rate,
                    'total_executions': len(results),
                    'failed_executions': failed_executions,
                    'duration_minutes': avg_duration  # For SLA checking
                },
                'details': {'stage_stats': {k: {'avg': sum(v)/len(v), 'max': max(v)} for k, v in stage_stats.items()}}
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Pipeline SLA check failed: {str(e)}',
                'metrics': {}
            }
    
    def check_model_availability(self) -> Dict[str, Any]:
        """Check model availability and performance."""
        try:
            # Check active models
            query = """
            SELECT 
                model_version,
                model_type,
                created_at,
                is_active,
                model_file_path,
                val_mae,
                val_rmse,
                val_r2
            FROM prop_trading_model.model_registry
            WHERE is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """
            
            result = self.db_manager.model_db.execute_query(query)
            
            if not result:
                return {
                    'status': 'unhealthy',
                    'message': 'No active model found in registry',
                    'metrics': {'active_models': 0}
                }
            
            model = result[0]
            model_age_days = (datetime.now() - model['created_at']).days
            
            # Check model file exists if path is provided
            model_file_exists = True
            if model['model_file_path']:
                model_file_exists = os.path.exists(model['model_file_path'])
            
            # Check recent prediction activity
            pred_query = """
            SELECT COUNT(*) as recent_predictions
            FROM prop_trading_model.model_predictions
            WHERE prediction_date >= CURRENT_DATE - INTERVAL '3 days'
            AND model_version = %s
            """
            
            pred_result = self.db_manager.model_db.execute_query(pred_query, (model['model_version'],))
            recent_predictions = pred_result[0]['recent_predictions'] if pred_result else 0
            
            # Determine status
            status = 'healthy'
            issues = []
            
            if not model_file_exists:
                status = 'unhealthy'
                issues.append('Model file not found')
            
            if model_age_days > 30:
                status = 'warning'
                issues.append(f'Model is {model_age_days} days old')
            
            if recent_predictions == 0:
                status = 'warning'
                issues.append('No recent predictions found')
            
            # Check model performance
            if model['val_r2'] and model['val_r2'] < 0.1:
                status = 'warning'
                issues.append(f'Low model R² score: {model["val_r2"]:.3f}')
            
            message = f'Active model: {model["model_version"]} (age: {model_age_days} days)'
            if issues:
                message += f' - Issues: {"; ".join(issues)}'
            
            return {
                'status': status,
                'message': message,
                'metrics': {
                    'active_models': 1,
                    'model_age_days': model_age_days,
                    'recent_predictions': recent_predictions,
                    'model_file_exists': model_file_exists,
                    'model_r2_score': float(model['val_r2']) if model['val_r2'] else 0,
                    'model_mae': float(model['val_mae']) if model['val_mae'] else 0
                },
                'details': {
                    'model_info': {
                        'version': model['model_version'],
                        'type': model['model_type'],
                        'created_at': model['created_at'].isoformat(),
                        'file_path': model['model_file_path']
                    }
                }
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Model availability check failed: {str(e)}',
                'metrics': {}
            }
    
    def check_disk_io_performance(self) -> Dict[str, Any]:
        """Check disk I/O performance."""
        try:
            # Get disk I/O statistics
            disk_io_start = psutil.disk_io_counters()
            time.sleep(1)  # Wait 1 second
            disk_io_end = psutil.disk_io_counters()
            
            # Calculate rates
            read_rate = disk_io_end.read_bytes - disk_io_start.read_bytes
            write_rate = disk_io_end.write_bytes - disk_io_start.write_bytes
            read_ops_rate = disk_io_end.read_count - disk_io_start.read_count
            write_ops_rate = disk_io_end.write_count - disk_io_start.write_count
            
            # Convert to more readable units
            read_rate_mb = read_rate / (1024 * 1024)
            write_rate_mb = write_rate / (1024 * 1024)
            
            metrics = {
                'read_rate_mbps': read_rate_mb,
                'write_rate_mbps': write_rate_mb,
                'read_ops_per_sec': read_ops_rate,
                'write_ops_per_sec': write_ops_rate,
                'total_io_rate_mbps': read_rate_mb + write_rate_mb
            }
            
            # Simple performance test - write and read a small file
            test_file = Path('/tmp/disk_perf_test.txt')
            test_data = 'x' * 1024 * 1024  # 1MB of data
            
            start_time = time.time()
            with open(test_file, 'w') as f:
                f.write(test_data)
            write_time = time.time() - start_time
            
            start_time = time.time()
            with open(test_file, 'r') as f:
                _ = f.read()
            read_time = time.time() - start_time
            
            # Clean up
            test_file.unlink()
            
            metrics['write_test_time_ms'] = write_time * 1000
            metrics['read_test_time_ms'] = read_time * 1000
            
            # Determine status
            status = 'healthy'
            if write_time > 1.0 or read_time > 1.0:  # More than 1 second for 1MB
                status = 'warning'
            if write_time > 5.0 or read_time > 5.0:  # More than 5 seconds for 1MB
                status = 'unhealthy'
            
            return {
                'status': status,
                'message': f'Disk I/O performance: {read_rate_mb:.1f} MB/s read, {write_rate_mb:.1f} MB/s write',
                'metrics': metrics
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Disk I/O performance check failed: {str(e)}',
                'metrics': {}
            }
    
    def check_network_connectivity(self) -> Dict[str, Any]:
        """Check network connectivity to external services."""
        try:
            import socket
            
            endpoints_to_test = [
                {'host': 'google.com', 'port': 80, 'name': 'Internet'},
                {'host': 'github.com', 'port': 443, 'name': 'GitHub'},
                {'host': 'pypi.org', 'port': 443, 'name': 'PyPI'},
            ]
            
            results = []
            successful_connections = 0
            
            for endpoint in endpoints_to_test:
                try:
                    start_time = time.time()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((endpoint['host'], endpoint['port']))
                    sock.close()
                    connection_time = (time.time() - start_time) * 1000
                    
                    success = result == 0
                    if success:
                        successful_connections += 1
                    
                    results.append({
                        'name': endpoint['name'],
                        'host': endpoint['host'],
                        'port': endpoint['port'],
                        'success': success,
                        'connection_time_ms': connection_time if success else 0
                    })
                    
                except Exception as e:
                    results.append({
                        'name': endpoint['name'],
                        'host': endpoint['host'],
                        'port': endpoint['port'],
                        'success': False,
                        'error': str(e)
                    })
            
            success_rate = successful_connections / len(endpoints_to_test)
            avg_connection_time = sum(r['connection_time_ms'] for r in results if r['success']) / max(successful_connections, 1)
            
            status = 'healthy'
            if success_rate < 0.5:
                status = 'unhealthy'
            elif success_rate < 0.8:
                status = 'warning'
            
            return {
                'status': status,
                'message': f'Network connectivity: {success_rate:.1%} success rate',
                'metrics': {
                    'connectivity_success_rate': success_rate,
                    'avg_connection_time_ms': avg_connection_time,
                    'successful_connections': successful_connections,
                    'total_endpoints': len(endpoints_to_test)
                },
                'details': {'connection_results': results}
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Network connectivity check failed: {str(e)}',
                'metrics': {}
            }


def run_health_check(verbose: bool = True, include_trends: bool = True) -> Dict[str, Any]:
    """
    Run comprehensive health checks and return detailed results.
    
    Args:
        verbose: Whether to print detailed results
        include_trends: Whether to include trend analysis
        
    Returns:
        Comprehensive health check results
    """
    checker = HealthChecker()
    results = checker.run_all_checks(include_trends=include_trends)
    
    if verbose:
        logger.info("="*80)
        logger.info("ENHANCED PIPELINE HEALTH CHECK RESULTS")
        logger.info("="*80)
        logger.info(f"Timestamp: {results['timestamp']}")
        logger.info(f"Overall Status: {results['overall_status'].upper()}")
        logger.info(f"Total Duration: {results['total_duration_seconds']:.2f} seconds")
        logger.info("")
        
        # Summary
        summary = results['summary']
        logger.info(f"Check Summary: {summary['healthy']} healthy, {summary['warnings']} warnings, "
                   f"{summary['unhealthy']} unhealthy, {summary['errors']} errors")
        logger.info("")
        
        # SLA Violations
        if results['sla_violations']:
            logger.warning(f"SLA VIOLATIONS ({len(results['sla_violations'])}):")
            for violation in results['sla_violations']:
                logger.warning(f"  {violation['sla_name']}: {violation['actual_value']} {violation['unit']} "
                              f"(threshold: {violation['threshold']}) - {violation['level'].upper()}")
            logger.info("")
        
        # Individual checks
        for check_name, check_result in results['checks'].items():
            status_symbol = {
                'healthy': '✓',
                'warning': '⚠',
                'unhealthy': '✗',
                'error': '!'
            }.get(check_result['status'], '?')
            
            logger.info(f"{status_symbol} {check_name.upper()}: {check_result['status']}")
            logger.info(f"  Message: {check_result['message']}")
            logger.info(f"  Duration: {check_result['duration_ms']:.1f}ms")
            
            if check_result.get('metrics'):
                for metric, value in check_result['metrics'].items():
                    if isinstance(value, (int, float)):
                        logger.info(f"  {metric}: {value}")
            logger.info("")
        
        # Trends
        if include_trends and 'trends' in results:
            trends = results['trends']
            logger.info("TREND ANALYSIS:")
            logger.info(f"  Stability Score: {trends['stability_score']:.2f}/1.0")
            logger.info(f"  24h Failure Rate: {trends['failure_rate_24h']:.1%}")
            logger.info(f"  Avg SLA Violations: {trends['average_sla_violations']:.1f}")
            
            if trends['degradation_detected']:
                logger.warning("  ⚠ System degradation detected")
            elif trends['improvement_detected']:
                logger.info("  ✓ System improvement detected")
            
            logger.info("")
    
    return results


if __name__ == '__main__':
    # Example usage
    import sys
    include_trends = '--full-check' in sys.argv
    results = run_health_check(verbose=True, include_trends=include_trends)
    
    # Exit with appropriate code
    exit_code = 0 if results['overall_status'] == 'healthy' else 1
    sys.exit(exit_code)