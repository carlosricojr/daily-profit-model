"""
Airflow DAG for the daily profit model pipeline.
Provides workflow orchestration with advanced monitoring and retry capabilities.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.models import Variable
from airflow.sensors.sql_sensor import SqlSensor
from airflow.sensors.filesystem import FileSensor
from airflow.hooks.postgres_hook import PostgresHook
from airflow.utils.decorators import apply_defaults
from airflow.utils.email import send_email
from airflow.utils.trigger_rule import TriggerRule
from airflow.exceptions import AirflowSkipException

logger = logging.getLogger(__name__)

# DAG Configuration
DAG_ID = 'daily_profit_model_pipeline'
DEFAULT_ARGS = {
    'owner': 'data-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'email': ['data-alerts@company.com'],
    'sla': timedelta(hours=4),  # Pipeline should complete within 4 hours
}

# Pipeline configuration from Airflow Variables
PIPELINE_CONFIG = {
    'environment': Variable.get('PIPELINE_ENV', default_var='development'),
    'data_start_date': Variable.get('DATA_START_DATE', default_var='2024-01-01'),
    'alert_email': Variable.get('ALERT_EMAIL', default_var='data-alerts@company.com'),
    'max_parallel_tasks': int(Variable.get('MAX_PARALLEL_TASKS', default_var='3')),
    'enable_data_quality_checks': Variable.get('ENABLE_DQ_CHECKS', default_var='true').lower() == 'true',
}


class PipelineOperator(PythonOperator):
    """Custom operator for pipeline stages with enhanced monitoring."""
    
    @apply_defaults
    def __init__(self, stage_name: str, module_path: str, stage_args: list = None, *args, **kwargs):
        self.stage_name = stage_name
        self.module_path = module_path
        self.stage_args = stage_args or []
        super().__init__(*args, **kwargs)
    
    def execute(self, context: Dict[str, Any]) -> Any:
        """Execute pipeline stage with monitoring."""
        import subprocess
        import sys
        from pathlib import Path
        
        execution_date = context['execution_date']
        dag_run_id = context['dag_run'].run_id
        
        logger.info(f"Starting stage {self.stage_name} for execution {dag_run_id}")
        
        # Prepare command
        src_dir = Path(__file__).parent.parent
        cmd = [sys.executable, '-m', self.module_path] + self.stage_args
        
        # Add execution context to arguments
        cmd.extend([
            '--execution-date', execution_date.strftime('%Y-%m-%d'),
            '--dag-run-id', dag_run_id,
            '--log-level', 'INFO'
        ])
        
        try:
            # Execute with timeout
            result = subprocess.run(
                cmd,
                cwd=src_dir,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Stage {self.stage_name} completed successfully")
                return {'status': 'success', 'output': result.stdout}
            else:
                logger.error(f"Stage {self.stage_name} failed: {result.stderr}")
                raise Exception(f"Stage failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error(f"Stage {self.stage_name} timed out")
            raise Exception("Stage execution timed out")
        except Exception as e:
            logger.error(f"Stage {self.stage_name} failed with exception: {str(e)}")
            raise


def check_data_freshness(**context) -> bool:
    """Check if source data is fresh enough for processing."""
    hook = PostgresHook(postgres_conn_id='postgres_model_db')
    
    # Check when data was last updated
    query = """
    SELECT MAX(ingestion_timestamp) as last_update
    FROM prop_trading_model.raw_metrics_daily
    WHERE DATE(ingestion_timestamp) >= CURRENT_DATE - INTERVAL '2 days'
    """
    
    result = hook.get_first(query)
    if not result or not result[0]:
        logger.warning("No recent data found in raw_metrics_daily")
        return False
    
    last_update = result[0]
    hours_old = (datetime.now() - last_update).total_seconds() / 3600
    
    if hours_old > 25:  # Data should be less than 25 hours old
        logger.warning(f"Data is {hours_old:.1f} hours old, may be stale")
        return False
    
    logger.info(f"Data freshness check passed - last update {hours_old:.1f} hours ago")
    return True


def check_model_availability(**context) -> bool:
    """Check if a trained model is available for predictions."""
    hook = PostgresHook(postgres_conn_id='postgres_model_db')
    
    query = """
    SELECT model_version, model_file_path, is_active
    FROM prop_trading_model.model_registry
    WHERE is_active = true
    ORDER BY created_at DESC
    LIMIT 1
    """
    
    result = hook.get_first(query)
    if not result:
        logger.warning("No active model found in registry")
        return False
    
    model_version, model_path, is_active = result
    logger.info(f"Active model found: {model_version} at {model_path}")
    return True


def send_pipeline_alert(context: Dict[str, Any], message: str, alert_type: str = 'error'):
    """Send pipeline alerts via email."""
    subject = f"[{alert_type.upper()}] Daily Profit Model Pipeline - {context['task_instance'].task_id}"
    
    html_content = f"""
    <h3>Pipeline Alert</h3>
    <p><strong>DAG:</strong> {context['dag'].dag_id}</p>
    <p><strong>Task:</strong> {context['task_instance'].task_id}</p>
    <p><strong>Execution Date:</strong> {context['execution_date']}</p>
    <p><strong>Run ID:</strong> {context['dag_run'].run_id}</p>
    <p><strong>Alert Type:</strong> {alert_type}</p>
    
    <h4>Message:</h4>
    <p>{message}</p>
    
    <h4>Context:</h4>
    <p>Log URL: {context['task_instance'].log_url}</p>
    """
    
    send_email(
        to=[PIPELINE_CONFIG['alert_email']],
        subject=subject,
        html_content=html_content
    )


def validate_data_quality(**context) -> bool:
    """Perform data quality checks on ingested data."""
    if not PIPELINE_CONFIG['enable_data_quality_checks']:
        logger.info("Data quality checks disabled")
        return True
    
    hook = PostgresHook(postgres_conn_id='postgres_model_db')
    execution_date = context['execution_date']
    
    checks = [
        {
            'name': 'accounts_data_completeness',
            'query': """
                SELECT COUNT(*) as count
                FROM prop_trading_model.raw_accounts_data
                WHERE DATE(ingestion_timestamp) = %s
            """,
            'min_threshold': 100,
            'params': [execution_date.date()]
        },
        {
            'name': 'metrics_data_completeness', 
            'query': """
                SELECT COUNT(DISTINCT login) as unique_logins
                FROM prop_trading_model.raw_metrics_daily
                WHERE metric_date = %s
            """,
            'min_threshold': 50,
            'params': [execution_date.date() - timedelta(days=1)]
        },
        {
            'name': 'data_consistency',
            'query': """
                SELECT COUNT(*) as count
                FROM prop_trading_model.raw_accounts_data a
                JOIN prop_trading_model.raw_metrics_daily m
                ON a.login = m.login
                WHERE DATE(a.ingestion_timestamp) = %s
                AND m.metric_date = %s
            """,
            'min_threshold': 30,
            'params': [execution_date.date(), execution_date.date() - timedelta(days=1)]
        }
    ]
    
    failed_checks = []
    
    for check in checks:
        try:
            result = hook.get_first(check['query'], parameters=check['params'])
            value = result[0] if result else 0
            
            if value < check['min_threshold']:
                failed_checks.append(f"{check['name']}: {value} < {check['min_threshold']}")
                logger.error(f"Data quality check failed: {check['name']} = {value}")
            else:
                logger.info(f"Data quality check passed: {check['name']} = {value}")
                
        except Exception as e:
            failed_checks.append(f"{check['name']}: Error - {str(e)}")
            logger.error(f"Data quality check error: {check['name']} - {str(e)}")
    
    if failed_checks:
        message = "Data quality checks failed:\n" + "\n".join(failed_checks)
        send_pipeline_alert(context, message, 'warning')
        return False
    
    return True


def cleanup_old_data(**context) -> None:
    """Clean up old data to prevent database bloat."""
    hook = PostgresHook(postgres_conn_id='postgres_model_db')
    
    cleanup_queries = [
        # Clean up old pipeline execution logs (keep 30 days)
        """
        DELETE FROM prop_trading_model.pipeline_execution_log
        WHERE execution_date < CURRENT_DATE - INTERVAL '30 days'
        """,
        
        # Clean up old raw data (keep 90 days)
        """
        DELETE FROM prop_trading_model.raw_metrics_daily
        WHERE metric_date < CURRENT_DATE - INTERVAL '90 days'
        """,
        
        # Clean up old predictions (keep 180 days)
        """
        DELETE FROM prop_trading_model.model_predictions
        WHERE prediction_date < CURRENT_DATE - INTERVAL '180 days'
        """
    ]
    
    for query in cleanup_queries:
        try:
            result = hook.run(query)
            logger.info(f"Cleanup query executed successfully")
        except Exception as e:
            logger.error(f"Cleanup query failed: {str(e)}")


# Create the DAG
dag = DAG(
    DAG_ID,
    default_args=DEFAULT_ARGS,
    description='Daily profit model pipeline with enhanced orchestration',
    schedule_interval='0 6 * * *',  # Run daily at 6 AM
    catchup=False,
    max_active_runs=1,
    tags=['machine_learning', 'trading', 'daily'],
)

# Start and end operators
start_pipeline = DummyOperator(
    task_id='start_pipeline',
    dag=dag,
)

end_pipeline = DummyOperator(
    task_id='end_pipeline',
    dag=dag,
    trigger_rule=TriggerRule.NONE_FAILED_OR_SKIPPED,
)

# Pre-flight checks
health_check = PythonOperator(
    task_id='health_check',
    python_callable=lambda **context: __import__('pipeline_orchestration.health_checks', fromlist=['run_health_check']).run_health_check(verbose=True, include_trends=False),
    dag=dag,
    retries=1,
)

data_freshness_check = PythonOperator(
    task_id='data_freshness_check',
    python_callable=check_data_freshness,
    dag=dag,
)

# Schema creation (idempotent)
create_schema = BashOperator(
    task_id='create_schema',
    bash_command="""
    cd {{ params.src_dir }} && python -m db_schema.create_schema --log-level INFO
    """,
    params={'src_dir': '/opt/airflow/dags/src'},
    dag=dag,
)

# Data ingestion with parallel sub-tasks
ingestion_start = DummyOperator(
    task_id='ingestion_start',
    dag=dag,
)

ingest_accounts = PipelineOperator(
    task_id='ingest_accounts',
    stage_name='ingest_accounts',
    module_path='data_ingestion.ingest_accounts',
    stage_args=['--log-level', 'INFO'],
    dag=dag,
    pool='ingestion_pool',
)

ingest_plans = PipelineOperator(
    task_id='ingest_plans',
    stage_name='ingest_plans',
    module_path='data_ingestion.ingest_plans',
    stage_args=['--log-level', 'INFO'],
    dag=dag,
    pool='ingestion_pool',
)

ingest_regimes = PipelineOperator(
    task_id='ingest_regimes',
    stage_name='ingest_regimes',
    module_path='data_ingestion.ingest_regimes',
    stage_args=[
        '--start-date', '{{ (execution_date - macros.timedelta(days=7)).strftime("%Y-%m-%d") }}',
        '--end-date', '{{ execution_date.strftime("%Y-%m-%d") }}',
        '--log-level', 'INFO'
    ],
    dag=dag,
    pool='ingestion_pool',
)

ingest_metrics_alltime = PipelineOperator(
    task_id='ingest_metrics_alltime',
    stage_name='ingest_metrics_alltime',
    module_path='data_ingestion.ingest_metrics',
    stage_args=['alltime', '--log-level', 'INFO'],
    dag=dag,
    pool='ingestion_pool',
)

ingest_metrics_daily = PipelineOperator(
    task_id='ingest_metrics_daily',
    stage_name='ingest_metrics_daily',
    module_path='data_ingestion.ingest_metrics',
    stage_args=[
        'daily',
        '--start-date', '{{ (execution_date - macros.timedelta(days=2)).strftime("%Y-%m-%d") }}',
        '--end-date', '{{ execution_date.strftime("%Y-%m-%d") }}',
        '--log-level', 'INFO'
    ],
    dag=dag,
    pool='ingestion_pool',
)

ingest_trades_open = PipelineOperator(
    task_id='ingest_trades_open',
    stage_name='ingest_trades_open',
    module_path='data_ingestion.ingest_trades',
    stage_args=[
        'open',
        '--end-date', '{{ execution_date.strftime("%Y-%m-%d") }}',
        '--log-level', 'INFO'
    ],
    dag=dag,
    pool='ingestion_pool',
)

ingest_trades_closed = PipelineOperator(
    task_id='ingest_trades_closed',
    stage_name='ingest_trades_closed',
    module_path='data_ingestion.ingest_trades',
    stage_args=[
        'closed',
        '--start-date', '{{ (execution_date - macros.timedelta(days=2)).strftime("%Y-%m-%d") }}',
        '--end-date', '{{ execution_date.strftime("%Y-%m-%d") }}',
        '--batch-days', '1',
        '--log-level', 'INFO'
    ],
    dag=dag,
    pool='ingestion_pool',
)

ingestion_complete = DummyOperator(
    task_id='ingestion_complete',
    dag=dag,
    trigger_rule=TriggerRule.ALL_SUCCESS,
)

# Data quality validation
data_quality_check = PythonOperator(
    task_id='data_quality_check',
    python_callable=validate_data_quality,
    dag=dag,
)

# Preprocessing
preprocessing = PipelineOperator(
    task_id='preprocessing',
    stage_name='preprocessing',
    module_path='preprocessing.create_staging_snapshots',
    stage_args=[
        '--start-date', '{{ (execution_date - macros.timedelta(days=2)).strftime("%Y-%m-%d") }}',
        '--end-date', '{{ execution_date.strftime("%Y-%m-%d") }}',
        '--clean-data',
        '--log-level', 'INFO'
    ],
    dag=dag,
)

# Feature engineering
feature_engineering = PipelineOperator(
    task_id='feature_engineering',
    stage_name='feature_engineering',
    module_path='feature_engineering.engineer_features',
    stage_args=[
        '--start-date', '{{ (execution_date - macros.timedelta(days=2)).strftime("%Y-%m-%d") }}',
        '--end-date', '{{ execution_date.strftime("%Y-%m-%d") }}',
        '--log-level', 'INFO'
    ],
    dag=dag,
)

build_training_data = PipelineOperator(
    task_id='build_training_data',
    stage_name='build_training_data',
    module_path='feature_engineering.build_training_data',
    stage_args=[
        '--start-date', '{{ (execution_date - macros.timedelta(days=2)).strftime("%Y-%m-%d") }}',
        '--end-date', '{{ (execution_date - macros.timedelta(days=1)).strftime("%Y-%m-%d") }}',
        '--validate',
        '--log-level', 'INFO'
    ],
    dag=dag,
)

# Model training (weekly)
model_training = PipelineOperator(
    task_id='model_training',
    stage_name='model_training',
    module_path='modeling.train_model',
    stage_args=[
        '--tune-hyperparameters',
        '--n-trials', '50',
        '--log-level', 'INFO'
    ],
    dag=dag,
    # Only run on Sundays
    execution_timeout=timedelta(hours=2),
)

# Model availability check for predictions
model_check = PythonOperator(
    task_id='model_availability_check',
    python_callable=check_model_availability,
    dag=dag,
)

# Daily predictions
daily_prediction = PipelineOperator(
    task_id='daily_prediction',
    stage_name='daily_prediction',
    module_path='modeling.predict_daily',
    stage_args=['--log-level', 'INFO'],
    dag=dag,
)

evaluate_predictions = PipelineOperator(
    task_id='evaluate_predictions',
    stage_name='evaluate_predictions',
    module_path='modeling.predict_daily',
    stage_args=['--evaluate', '--log-level', 'INFO'],
    dag=dag,
)

# Cleanup tasks
cleanup_old_data_task = PythonOperator(
    task_id='cleanup_old_data',
    python_callable=cleanup_old_data,
    dag=dag,
    trigger_rule=TriggerRule.ALL_DONE,
)

# Success notification
success_notification = PythonOperator(
    task_id='success_notification',
    python_callable=lambda **context: send_pipeline_alert(
        context, 
        "Daily profit model pipeline completed successfully", 
        'success'
    ),
    dag=dag,
    trigger_rule=TriggerRule.ALL_SUCCESS,
)

# Define dependencies
start_pipeline >> [health_check, data_freshness_check]

[health_check, data_freshness_check] >> create_schema

create_schema >> ingestion_start

ingestion_start >> [
    ingest_accounts,
    ingest_plans,
    ingest_regimes,
    ingest_metrics_alltime,
    ingest_metrics_daily,
    ingest_trades_open,
    ingest_trades_closed
]

[
    ingest_accounts,
    ingest_plans,
    ingest_regimes,
    ingest_metrics_alltime,
    ingest_metrics_daily,
    ingest_trades_open,
    ingest_trades_closed
] >> ingestion_complete

ingestion_complete >> data_quality_check

data_quality_check >> preprocessing

preprocessing >> feature_engineering

feature_engineering >> build_training_data

# Training branch (conditional on day of week)
build_training_data >> model_training

# Prediction branch
build_training_data >> model_check
model_check >> daily_prediction
daily_prediction >> evaluate_predictions

# Final tasks
[model_training, evaluate_predictions] >> cleanup_old_data_task
cleanup_old_data_task >> success_notification
success_notification >> end_pipeline