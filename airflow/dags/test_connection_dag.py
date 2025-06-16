"""
Minimal test DAG to debug connection issues.
"""

from datetime import datetime
import logging
import os
import sys

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.empty import EmptyOperator

logger = logging.getLogger(__name__)

def test_environment(**context):
    """Test basic environment setup."""
    print("=== Environment Test ===")
    print(f"Python version: {sys.version}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    
    # Check environment variables
    print("\n=== Environment Variables ===")
    for key in ['AIRFLOW_CONN_POSTGRES_MODEL_DB', 'DB_CONNECTION_STRING_SESSION_POOLER']:
        value = os.environ.get(key)
        if value:
            print(f"{key}: {value[:30]}...")
        else:
            print(f"{key}: NOT SET")
    
    return True

def test_postgres_hook(**context):
    """Test PostgresHook connection."""
    print("=== PostgresHook Test ===")
    
    try:
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        print("PostgresHook imported successfully")
        
        # Try to get the hook
        hook = PostgresHook(postgres_conn_id="postgres_model_db")
        print("PostgresHook created successfully")
        
        # Try to get connection
        conn = hook.get_conn()
        print("Connection obtained successfully")
        
        # Try a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(account_id) FROM prop_trading_model.raw_metrics_alltime")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        print(f"Query result (current count of rows in raw_metrics_alltime): {result}")
        return True
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_database_manager(**context):
    """Test DatabaseManager connection."""
    print("=== DatabaseManager Test ===")
    
    try:
        # Add src to path
        src_path = "/opt/airflow/src"
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        print(f"Added to path: {src_path}")
        print(f"current sys.path: {sys.path[:5]}...")
        
        # Try to import
        from utils.database import get_db_manager
        print("DatabaseManager imported successfully")
        
        # Try to connect
        db_manager = get_db_manager()
        print("DatabaseManager created successfully")
        
        # Try a simple query
        result = db_manager.model_db.execute_query("SELECT COUNT(account_id) FROM prop_trading_model.raw_metrics_alltime")
        print(f"Query result (current count of rows in raw_metrics_alltime): {result}")
        return True
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# Create test DAG
dag = DAG(
    "test_environment",
    default_args={
        "owner": "Carlos",
        "start_date": datetime(2024, 1, 1),
        "retries": 0,
    },
    schedule=None,
    catchup=False,
    tags=["test"],
)

# Define tasks
start = EmptyOperator(task_id="start", dag=dag)

env_test = PythonOperator(
    task_id="test_environment",
    python_callable=test_environment,
    dag=dag,
)

postgres_test = PythonOperator(
    task_id="test_postgres_hook",
    python_callable=test_postgres_hook,
    dag=dag,
)

db_manager_test = PythonOperator(
    task_id="test_database_manager",
    python_callable=test_database_manager,
    dag=dag,
)

end = EmptyOperator(task_id="end", dag=dag)

# Dependencies
start >> env_test >> [postgres_test, db_manager_test] >> end