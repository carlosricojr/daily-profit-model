#!/usr/bin/env python3
"""Test script for Airflow health check and data freshness check functions."""

import sys
import os
from datetime import datetime

# Add src to path
sys.path.append('src')


def test_airflow_postgres_hook():
    """Test using Airflow's PostgresHook."""
    print("=== Testing Airflow PostgresHook ===")
    try:
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        
        # Set up the connection from environment variable
        conn_string = os.environ.get('DB_CONNECTION_STRING_SESSION_POOLER')
        if not conn_string:
            print("ERROR: DB_CONNECTION_STRING_SESSION_POOLER not found in environment")
            return False
            
        # Airflow expects this format
        os.environ['AIRFLOW_CONN_POSTGRES_MODEL_DB'] = conn_string
        print(f"Connection string set: {conn_string[:30]}...")
        
        # Test health check
        print("\n--- Testing health check ---")
        try:
            hook = PostgresHook(postgres_conn_id='postgres_model_db')
            conn = hook.get_conn()
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            print(f"Health check passed: {result}")
        except Exception as e:
            print(f"Health check failed: {e}")
            assert False, "Health check failed"
            
        # Test data freshness check
        print("\n--- Testing data freshness check ---")
        try:
            hook = PostgresHook(postgres_conn_id='postgres_model_db')
            query = """
            SELECT MAX(ingestion_timestamp) as last_update
            FROM prop_trading_model.raw_metrics_daily
            WHERE DATE(ingestion_timestamp) >= CURRENT_DATE - INTERVAL '2 days'
            """
            result = hook.get_first(query)
            print(f"Query result: {result}")
            
            if result and result[0]:
                last_update = result[0]
                hours_old = (datetime.now() - last_update).total_seconds() / 3600
                print(f" Data freshness: Last update was {hours_old:.1f} hours ago")
                if hours_old > 25:
                    print(" Warning: Data may be stale (>25 hours old)")
            else:
                print(" No recent data found in raw_metrics_daily")
                assert False, "Data freshness: no recent data"
                
        except Exception as e:
            print(f" Data freshness check failed: {e}")
            assert False, "Data freshness query error"
            
        # success
    except ImportError as e:
        print(f" Import error: {e}")
        print("Make sure apache-airflow-providers-postgres is installed")
        assert False, "Import error"
    except Exception as e:
        print(f" Unexpected error: {e}")
        assert False, "Unexpected error"


def test_database_manager():
    """Test using the custom DatabaseManager."""
    print("\n\n=== Testing DatabaseManager ===")
    try:
        from utils.database import get_db_manager
        
        db_manager = get_db_manager()
        
        # Test health check
        print("\n--- Testing health check ---")
        try:
            result = db_manager.model_db.execute_query('SELECT 1 as check')
            print(f" Health check passed: {result}")
        except Exception as e:
            print(f" Health check failed: {e}")
            assert False, "Health check failed"
            
        # Test data freshness
        print("\n--- Testing data freshness check ---")
        try:
            query = """
            SELECT MAX(ingestion_timestamp) as last_update
            FROM prop_trading_model.raw_metrics_daily
            WHERE DATE(ingestion_timestamp) >= CURRENT_DATE - INTERVAL '2 days'
            """
            result = db_manager.model_db.execute_query(query)
            print(f"Query result: {result}")
            
            if result and result[0]['last_update']:
                last_update = result[0]['last_update']
                hours_old = (datetime.now() - last_update).total_seconds() / 3600
                print(f" Data freshness: Last update was {hours_old:.1f} hours ago")
                if hours_old > 25:
                    print(" Warning: Data may be stale (>25 hours old)")
            else:
                print(" No recent data found in raw_metrics_daily")
                assert False, "Data freshness: no recent data"
                
        except Exception as e:
            print(f" Data freshness check failed: {e}")
            assert False, "Data freshness query error"
            
        # Test model availability check
        print("\n--- Testing model availability check ---")
        try:
            query = """
            SELECT model_version, model_path, is_active, created_at
            FROM prop_trading_model.model_registry
            WHERE is_active = true
            ORDER BY created_at DESC
            LIMIT 1
            """
            result = db_manager.model_db.execute_query(query)
            
            if result:
                row = result[0]
                model_version = row['model_version']
                model_path = row['model_path']
                created_at = row['created_at']
                
                days_old = (datetime.now() - created_at).days
                print(f" Active model found: {model_version}")
                print(f"  Path: {model_path}")
                print(f"  Created: {created_at} ({days_old} days ago)")
                
                if days_old > 30:
                    print(" Warning: Model is older than 30 days")
                    
                if os.path.exists(model_path):
                    print(f" Model file exists at {model_path}")
                else:
                    print(f" Model file NOT found at {model_path}")
            else:
                print(" No active model found in registry")
                
        except Exception as e:
            print(f"Model availability check failed: {e}")
            # This is not critical for health check
            
        # success
    except Exception as e:
        print(f"Unexpected error: {e}")
        assert False, "Unexpected error"


def main():
    """Run all tests."""
    print("Starting health check tests...")
    print(f"Current time: {datetime.now()}")
    
    # Check environment
    conn_string = os.environ.get('DB_CONNECTION_STRING_SESSION_POOLER')
    if conn_string:
        print("DB_CONNECTION_STRING_SESSION_POOLER is set")
    else:
        print("DB_CONNECTION_STRING_SESSION_POOLER not found")
        print("Please run with: uv run --env-file .env python test_health_check.py")
        return
    
    # Run tests
    airflow_success = False
    db_manager_success = False
    
    try:
        test_airflow_postgres_hook()
        airflow_success = True
    except:
        pass
        
    try:
        test_database_manager()
        db_manager_success = True
    except:
        pass
    
    print("\n\n=== Summary ===")
    print(f"Airflow PostgresHook: {'PASSED' if airflow_success else 'FAILED'}")
    print(f"DatabaseManager: {'PASSED' if db_manager_success else 'FAILED'}")
    
    if airflow_success and db_manager_success:
        print("\n All tests passed!")
    else:
        print("\n Some tests failed. Check the output above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()