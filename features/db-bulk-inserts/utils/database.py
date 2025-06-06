"""
Database connection utilities for the daily profit model.
Handles connections to both the source Supabase database and the model's PostgreSQL schema.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from psycopg2.extras import RealDictCursor, execute_batch
from psycopg2.pool import SimpleConnectionPool
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages PostgreSQL database connections with connection pooling."""
    
    def __init__(self, 
                 host: str,
                 port: int,
                 database: str,
                 user: str,
                 password: str,
                 schema: Optional[str] = None,
                 min_connections: int = 1,
                 max_connections: int = 10):
        """
        Initialize database connection manager.
        
        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            schema: Default schema to use (optional)
            min_connections: Minimum number of connections in pool
            max_connections: Maximum number of connections in pool
        """
        self.connection_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password
        }
        self.schema = schema
        self.pool = None
        self._initialize_pool(min_connections, max_connections)
    
    def _initialize_pool(self, min_connections: int, max_connections: int):
        """Initialize connection pool."""
        try:
            self.pool = SimpleConnectionPool(
                min_connections,
                max_connections,
                **self.connection_params
            )
            logger.info(f"Database connection pool initialized for {self.connection_params['host']}")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {str(e)}")
            raise
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        Automatically handles connection checkout/return from pool.
        """
        connection = None
        try:
            connection = self.pool.getconn()
            if self.schema:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET search_path TO {self.schema}")
            yield connection
            connection.commit()
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"Database error: {str(e)}")
            raise
        finally:
            if connection:
                self.pool.putconn(connection)
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as list of dictionaries.
        
        Args:
            query: SQL query to execute
            params: Query parameters (optional)
            
        Returns:
            List of dictionaries representing query results
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def execute_query_df(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """
        Execute a SELECT query and return results as pandas DataFrame.
        
        Args:
            query: SQL query to execute
            params: Query parameters (optional)
            
        Returns:
            pandas DataFrame with query results
        """
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)
    
    def execute_command(self, command: str, params: Optional[tuple] = None) -> int:
        """
        Execute an INSERT/UPDATE/DELETE command.
        
        Args:
            command: SQL command to execute
            params: Command parameters (optional)
            
        Returns:
            Number of affected rows
        """
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(command, params)
                return cursor.rowcount
    
    def insert_batch(self, table: str, data: List[Dict[str, Any]], 
                    page_size: int = 1000, returning: Optional[str] = None) -> List[Any]:
        """
        Insert multiple rows efficiently using execute_batch.
        
        Args:
            table: Table name
            data: List of dictionaries containing row data
            page_size: Batch size for inserts
            returning: Column to return after insert (optional)
            
        Returns:
            List of returned values if returning is specified
        """
        if not data:
            return []
        
        # Get column names from first row
        columns = list(data[0].keys())
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)
        
        query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
        if returning:
            query += f" RETURNING {returning}"
        
        values = [[row.get(col) for col in columns] for row in data]
        
        returned_values = []
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                if returning:
                    for batch in values:
                        cursor.execute(query, batch)
                        returned_values.extend([row[0] for row in cursor.fetchall()])
                else:
                    execute_batch(cursor, query, values, page_size=page_size)
        
        logger.info(f"Inserted {len(data)} rows into {table}")
        return returned_values
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = COALESCE(%s, 'public')
            AND table_name = %s
        )
        """
        result = self.execute_query(query, (self.schema, table_name))
        return result[0]['exists'] if result else False
    
    def get_table_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table."""
        query = f"SELECT COUNT(*) as count FROM {table_name}"
        result = self.execute_query(query)
        return result[0]['count'] if result else 0
    
    def close(self):
        """Close all connections in the pool."""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")


class DatabaseManager:
    """Manages connections to both source and model databases."""
    
    def __init__(self):
        """Initialize database manager with connections from environment variables."""
        # Model database connection (prop_trading_model schema)
        self.model_db = DatabaseConnection(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
            schema='prop_trading_model'
        )
        
        # Source database connection (for regimes_daily)
        self.source_db = DatabaseConnection(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
            schema='public'  # regimes_daily is in public schema
        )
        
        logger.info("Database manager initialized")
    
    def log_pipeline_execution(self, 
                             pipeline_stage: str,
                             execution_date: datetime,
                             status: str,
                             records_processed: Optional[int] = None,
                             error_message: Optional[str] = None,
                             execution_details: Optional[Dict[str, Any]] = None):
        """
        Log pipeline execution details to the database.
        
        Args:
            pipeline_stage: Name of the pipeline stage
            execution_date: Date of execution
            status: Execution status ('running', 'success', 'failed')
            records_processed: Number of records processed (optional)
            error_message: Error message if failed (optional)
            execution_details: Additional execution details as JSON (optional)
        """
        import json
        
        query = """
        INSERT INTO pipeline_execution_log 
        (pipeline_stage, execution_date, start_time, end_time, status, 
         records_processed, error_message, execution_details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (pipeline_stage, execution_date) DO UPDATE
        SET end_time = EXCLUDED.end_time,
            status = EXCLUDED.status,
            records_processed = EXCLUDED.records_processed,
            error_message = EXCLUDED.error_message,
            execution_details = EXCLUDED.execution_details
        """
        
        now = datetime.now()
        params = (
            pipeline_stage,
            execution_date,
            now if status == 'running' else None,
            now if status in ['success', 'failed'] else None,
            status,
            records_processed,
            error_message,
            json.dumps(execution_details) if execution_details else None
        )
        
        try:
            self.model_db.execute_command(query, params)
            logger.info(f"Logged pipeline execution: {pipeline_stage} - {status}")
        except Exception as e:
            logger.error(f"Failed to log pipeline execution: {str(e)}")
    
    def close(self):
        """Close all database connections."""
        self.model_db.close()
        self.source_db.close()


# Singleton instance
_db_manager = None


def get_db_manager() -> DatabaseManager:
    """Get or create the database manager singleton."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def close_db_connections():
    """Close all database connections."""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None