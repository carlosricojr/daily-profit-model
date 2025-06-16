"""
Airflow DAG for the daily profit model pipeline.
Provides workflow orchestration with advanced monitoring and retry capabilities.
"""

from datetime import datetime, timedelta
from typing import Any
import logging
import sys
from pathlib import Path
from functools import partial

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))

# Set environment variables from parent .env if needed
import dotenv
parent_env_path = project_root / ".env"
if parent_env_path.exists():
    dotenv.load_dotenv(parent_env_path)

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.models import Variable
from airflow.utils.trigger_rule import TriggerRule
from airflow.timetables.trigger import CronTriggerTimetable

logger = logging.getLogger(__name__)

# DAG Configuration
DAG_ID = "daily_profit_model_pipeline"
DEFAULT_ARGS = {
    "owner": "Carlos",
    "depends_on_past": False,
    "start_date": datetime(2024, 4, 15),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email": ["carlos@eastontech.net"],
    "catchup": False,
}

# Pipeline configuration - moved Variable access to runtime to avoid top-level DB access
def get_pipeline_config():
    """Get pipeline configuration from Airflow Variables at runtime."""
    return {
        "environment": Variable.get("PIPELINE_ENV", default_var="development"),
        "data_start_date": Variable.get("DATA_START_DATE", default_var="2024-04-15"),
        "alert_email": Variable.get("ALERT_EMAIL", default_var="carlos@eastontech.net"),
        "max_parallel_tasks": int(Variable.get("MAX_PARALLEL_TASKS", default_var="3")),
        "enable_data_quality_checks": Variable.get(
            "ENABLE_DQ_CHECKS", default_var="true"
        ).lower()
        == "true",
        "enable_great_expectations": Variable.get(
            "ENABLE_GREAT_EXPECTATIONS", default_var="true"
        ).lower()
        == "true",
    }


def run_pipeline_stage(stage_name: str, module_path: str, **kwargs) -> Any:
    """Execute pipeline stage with direct Python imports."""
    # Get context from kwargs
    context = kwargs
    execution_date = context.get("execution_date") or context.get("logical_date")
    dag_run = context.get("dag_run")
    
    if not execution_date or not dag_run:
        raise ValueError("Missing required context variables: execution_date or dag_run")
    
    dag_run_id = dag_run.run_id
    logger.info(f"Starting stage {stage_name} for execution {dag_run_id}")
    
    try:
        # Import the module dynamically
        parts = module_path.split('.')
        module = __import__(module_path, fromlist=[parts[-1]])
        
        # Get the main function from the module
        if hasattr(module, 'main'):
            # Call the main function with appropriate arguments
            args_dict = {
                'execution_date': execution_date,
                'dag_run_id': dag_run_id,
                'log_level': 'INFO'
            }
            
            # Add any stage-specific arguments
            if 'stage_args' in kwargs:
                args_dict.update(kwargs['stage_args'])
            
            result = module.main(**args_dict)
            logger.info(f"Stage {stage_name} completed successfully")
            return {"status": "success", "result": result}
        else:
            raise AttributeError(f"Module {module_path} does not have a main() function")
            
    except Exception as e:
        logger.error(f"Stage {stage_name} failed with exception: {str(e)}")
        raise

# Create the DAG
dag = DAG(
    DAG_ID,
    default_args=DEFAULT_ARGS,
    description="Daily profit model pipeline with enhanced orchestration",
    schedule=CronTriggerTimetable(
        "0 1 * * *",
        timezone="America/New_York"
    ),
    catchup=False,
    max_active_runs=1,
    tags=["machine_learning", "daily"],
)

# Start and end operators
start_pipeline = EmptyOperator(
    task_id="start_pipeline",
    dag=dag,
)

testing = PythonOperator(
    task_id="testing",
    python_callable=partial(run_pipeline_stage, "testing", "pipeline_orchestration.run_pipeline"),
    dag=dag,
    retries=1,
)

# Data ingestion with parallel sub-tasks
ingestion = PythonOperator(
    task_id="ingestion",
    python_callable=partial(run_pipeline_stage, "ingestion", "pipeline_orchestration.run_pipeline"),
    dag=dag,
    retries=1,
)

preprocessing = PythonOperator(
    task_id="preprocessing",
    python_callable=partial(run_pipeline_stage, "preprocessing", "pipeline_orchestration.run_pipeline"),
    dag=dag,
)

validation = PythonOperator(
    task_id="validation",
    python_callable=partial(run_pipeline_stage, "validation", "pipeline_orchestration.run_pipeline"),
    dag=dag,
)

feature_engineering = PythonOperator(
    task_id="feature_engineering",
    python_callable=partial(run_pipeline_stage, "feature_engineering", "pipeline_orchestration.run_pipeline"),
    dag=dag,
)

training = PythonOperator(
    task_id="training",
    python_callable=partial(run_pipeline_stage, "training", "pipeline_orchestration.run_pipeline"),
    dag=dag,
)

# Model availability check for predictions
prediction = PythonOperator(
    task_id="prediction",
    python_callable=partial(run_pipeline_stage, "prediction", "pipeline_orchestration.run_pipeline"),
    dag=dag,
)

end_pipeline = EmptyOperator(
    task_id="end_pipeline",
    dag=dag,
    trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
)

# Define dependencies
start_pipeline >> testing >> ingestion >> preprocessing >> validation >> feature_engineering >> training >> prediction >> end_pipeline
