"""
Health check utilities for pipeline components.
Provides basic health checks for database connections, API availability, and system resources.
"""

import os
import logging
import psutil
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import requests

from utils.database import get_db_manager

logger = logging.getLogger(__name__)


class HealthChecker:
    """Performs health checks on pipeline components."""
    
    def __init__(self):
        """Initialize health checker."""
        self.db_manager = get_db_manager()
        self.checks = {
            'database': self.check_database,
            'api': self.check_api,
            'disk_space': self.check_disk_space,
            'memory': self.check_memory,
            'recent_executions': self.check_recent_executions
        }
    
    def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all health checks.
        
        Returns:
            Dictionary with health check results
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'checks': {}
        }
        
        for check_name, check_func in self.checks.items():
            try:
                check_result = check_func()
                results['checks'][check_name] = check_result
                
                if check_result['status'] != 'healthy':
                    results['overall_status'] = 'unhealthy'
                    
            except Exception as e:
                logger.error(f"Health check {check_name} failed: {str(e)}")
                results['checks'][check_name] = {
                    'status': 'error',
                    'message': str(e)
                }
                results['overall_status'] = 'unhealthy'
        
        return results
    
    def check_database(self) -> Dict[str, Any]:
        """Check database connectivity and basic functionality."""
        try:
            # Check model database
            model_result = self.db_manager.model_db.execute_query(
                "SELECT 1 as test, current_timestamp as ts"
            )
            
            # Check source database
            source_result = self.db_manager.source_db.execute_query(
                "SELECT 1 as test, current_timestamp as ts"
            )
            
            # Check critical tables exist
            critical_tables = [
                'raw_accounts_data',
                'raw_metrics_daily',
                'staging_daily_snapshots',
                'model_features',
                'model_training_input',
                'model_predictions'
            ]
            
            missing_tables = []
            for table in critical_tables:
                if not self.db_manager.model_db.table_exists(table):
                    missing_tables.append(table)
            
            status = 'healthy' if not missing_tables else 'warning'
            
            return {
                'status': status,
                'model_db': 'connected',
                'source_db': 'connected',
                'missing_tables': missing_tables,
                'message': f"Missing tables: {', '.join(missing_tables)}" if missing_tables else "All critical tables exist"
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'message': f"Database check failed: {str(e)}"
            }
    
    def check_api(self) -> Dict[str, Any]:
        """Check API availability."""
        api_base_url = os.getenv('API_BASE_URL', 'https://d3m1s17i9h2y69.cloudfront.net')
        
        try:
            # Test API connectivity with a simple endpoint
            response = requests.get(
                f"{api_base_url}/accounts",
                headers={'X-API-KEY': os.getenv('API_KEY', '')},
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    'status': 'healthy',
                    'message': 'API is accessible',
                    'response_time_ms': int(response.elapsed.total_seconds() * 1000)
                }
            else:
                return {
                    'status': 'warning',
                    'message': f'API returned status code: {response.status_code}',
                    'response_time_ms': int(response.elapsed.total_seconds() * 1000)
                }
                
        except Exception as e:
            return {
                'status': 'unhealthy',
                'message': f'API check failed: {str(e)}'
            }
    
    def check_disk_space(self) -> Dict[str, Any]:
        """Check available disk space."""
        try:
            disk_usage = psutil.disk_usage('/')
            free_gb = disk_usage.free / (1024 ** 3)
            percent_used = disk_usage.percent
            
            if percent_used > 90:
                status = 'unhealthy'
            elif percent_used > 80:
                status = 'warning'
            else:
                status = 'healthy'
            
            return {
                'status': status,
                'free_gb': round(free_gb, 2),
                'percent_used': round(percent_used, 2),
                'message': f'{free_gb:.2f} GB free ({percent_used:.1f}% used)'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Disk space check failed: {str(e)}'
            }
    
    def check_memory(self) -> Dict[str, Any]:
        """Check available memory."""
        try:
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024 ** 3)
            percent_used = memory.percent
            
            if percent_used > 90:
                status = 'unhealthy'
            elif percent_used > 80:
                status = 'warning'
            else:
                status = 'healthy'
            
            return {
                'status': status,
                'available_gb': round(available_gb, 2),
                'percent_used': round(percent_used, 2),
                'message': f'{available_gb:.2f} GB available ({percent_used:.1f}% used)'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Memory check failed: {str(e)}'
            }
    
    def check_recent_executions(self) -> Dict[str, Any]:
        """Check recent pipeline executions for failures."""
        try:
            # Check for failures in the last 24 hours
            query = """
            SELECT 
                pipeline_stage,
                COUNT(*) as execution_count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
                MAX(end_time) as last_execution
            FROM pipeline_execution_log
            WHERE execution_date >= CURRENT_DATE - INTERVAL '1 day'
            GROUP BY pipeline_stage
            """
            
            results = self.db_manager.model_db.execute_query(query)
            
            failed_stages = []
            stale_stages = []
            
            for row in results:
                if row['failed_count'] > 0:
                    failed_stages.append(row['pipeline_stage'])
                
                # Check if stage hasn't run in expected time
                if row['last_execution']:
                    hours_since_run = (datetime.now() - row['last_execution']).total_seconds() / 3600
                    if hours_since_run > 25:  # More than 25 hours since last run
                        stale_stages.append(row['pipeline_stage'])
            
            if failed_stages:
                status = 'warning'
                message = f"Failed stages: {', '.join(failed_stages)}"
            elif stale_stages:
                status = 'warning'
                message = f"Stale stages: {', '.join(stale_stages)}"
            else:
                status = 'healthy'
                message = "All recent executions successful"
            
            return {
                'status': status,
                'failed_stages': failed_stages,
                'stale_stages': stale_stages,
                'message': message,
                'execution_summary': [dict(row) for row in results]
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Recent executions check failed: {str(e)}'
            }


def run_health_check(verbose: bool = True) -> bool:
    """
    Run health checks and return overall status.
    
    Args:
        verbose: Whether to print detailed results
        
    Returns:
        True if all checks pass, False otherwise
    """
    checker = HealthChecker()
    results = checker.run_all_checks()
    
    if verbose:
        logger.info("="*60)
        logger.info("PIPELINE HEALTH CHECK RESULTS")
        logger.info("="*60)
        logger.info(f"Timestamp: {results['timestamp']}")
        logger.info(f"Overall Status: {results['overall_status'].upper()}")
        logger.info("")
        
        for check_name, check_result in results['checks'].items():
            logger.info(f"{check_name.upper()}:")
            logger.info(f"  Status: {check_result['status']}")
            logger.info(f"  Message: {check_result.get('message', 'OK')}")
            
            # Print additional details
            for key, value in check_result.items():
                if key not in ['status', 'message']:
                    logger.info(f"  {key}: {value}")
            logger.info("")
    
    return results['overall_status'] == 'healthy'