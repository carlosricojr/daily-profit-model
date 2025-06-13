"""
Simplified database connection utilities using SQLAlchemy.
Provides all functionality required by the data pipeline modules.
"""
import os
import logging
from typing import Optional, Any, Dict, List, Tuple
from contextlib import contextmanager
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import pandas as pd
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Connection strings from environment
MODEL_DATABASE_URL = os.getenv('DB_CONNECTION_STRING_SESSION_POOLER')
SOURCE_DATABASE_URL = os.getenv('DB_CONNECTION_STRING_SESSION_POOLER')  # Same DB, different schema

if not MODEL_DATABASE_URL:
    raise ValueError("DB_CONNECTION_STRING_SESSION_POOLER not set in environment")


class DatabaseConnection:
    """Manages a single database connection with all required functionality."""
    
    def __init__(self, connection_string: str, schema: str = "prop_trading_model"):
        """Initialize database connection."""
        self.connection_string = connection_string
        self.schema = schema
        
        # Create SQLAlchemy engine
        # Use up to 75% of available connections (150 out of 200)
        self.engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=50,           # Base pool size
            max_overflow=100,       # Additional connections when needed (50+100=150)
            pool_pre_ping=True,     # Test connections before use
            pool_recycle=3600,      # Recycle connections after 1 hour
            echo=False
        )
        
        # Session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Set default schema
        self._ensure_schema()
    
    def _ensure_schema(self):
        """Ensure the schema exists."""
        with self.engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {self.schema}"))
    
    @contextmanager
    def get_connection(self):
        """Get a raw psycopg2 connection with automatic transaction handling."""
        conn = self.engine.raw_connection()
        try:
            # Set search path for this connection
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {self.schema}, public")
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or {})
                return [dict(row) for row in cur.fetchall()]
    
    def execute_query_df(self, query: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Execute a SELECT query and return results as pandas DataFrame."""
        with self.engine.connect() as conn:
            return pd.read_sql_query(text(query), conn, params=params)
    
    def execute_command(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE command and return affected rows."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or {})
                return cur.rowcount
    
    def insert_batch(self, table: str, data: List[Dict[str, Any]], 
                    returning: Optional[str] = None) -> Optional[List[Any]]:
        """Batch insert data into a table."""
        if not data:
            return [] if returning else None
        
        # Get column names from first record
        columns = list(data[0].keys())
        
        # Build the INSERT query
        placeholders = ", ".join([f"%({col})s" for col in columns])
        query = f"""
            INSERT INTO {self.schema}.{table} ({", ".join(columns)})
            VALUES ({placeholders})
        """
        
        if returning:
            query += f" RETURNING {returning}"
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if returning:
                    results = []
                    for record in data:
                        cur.execute(query, record)
                        results.extend([row[0] for row in cur.fetchall()])
                    return results
                else:
                    execute_batch(cur, query, data)
                    return None
    
    def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """Check if a table exists."""
        schema = schema or self.schema
        query = """
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = %(schema)s 
                AND table_name = %(table_name)s
            ) as exists
        """
        result = self.execute_query(query, {"schema": schema, "table_name": table_name})
        return result[0]["exists"] if result else False
    
    def get_table_row_count(self, table_name: str, schema: Optional[str] = None) -> int:
        """Get the row count of a table."""
        schema = schema or self.schema
        query = f"SELECT COUNT(*) as count FROM {schema}.{table_name}"
        result = self.execute_query(query)
        return result[0]["count"] if result else 0
    
    def close(self):
        """Close all connections in the pool."""
        self.engine.dispose()


class DatabaseManager:
    """Manages both model and source database connections."""
    
    def __init__(self):
        """Initialize database manager with both connections."""
        # Model database (prop_trading_model schema)
        self.model_db = DatabaseConnection(MODEL_DATABASE_URL, "prop_trading_model")
        
        # Source database (public schema) - same physical database
        self.source_db = DatabaseConnection(SOURCE_DATABASE_URL, "public")
        
        logger.info("Database manager initialized")
    
    def log_pipeline_execution(
        self,
        pipeline_stage: str,
        status: str,
        execution_time_seconds: float,
        records_processed: int = 0,
        error_message: Optional[str] = None,
        records_failed: int = 0,
    ) -> None:
        """Insert a row into prop_trading_model.pipeline_execution_log.

        Simplest fix: write into the existing columns and stash the duration
        inside execution_details JSON so we do **not** need to alter the table.
        """

        now_ts = datetime.utcnow()
        end_ts: Optional[datetime]

        if status.lower() == "running":
            # No end-time yet – set to NULL so a later call can update / append
            end_ts = None
        else:
            end_ts = now_ts + timedelta(seconds=execution_time_seconds)

        execution_details = json.dumps({"execution_time_seconds": execution_time_seconds})

        query = """
            INSERT INTO prop_trading_model.pipeline_execution_log (
                pipeline_stage,
                execution_date,
                start_time,
                end_time,
                status,
                records_processed,
                records_failed,
                error_message,
                execution_details
            ) VALUES (
                %(pipeline_stage)s,
                CURRENT_DATE,
                %(start_time)s,
                %(end_time)s,
                %(status)s,
                %(records_processed)s,
                %(records_failed)s,
                %(error_message)s,
                %(execution_details)s::jsonb
            )
        """

        params = {
            "pipeline_stage": pipeline_stage,
            "start_time": now_ts,
            "end_time": end_ts,
            "status": status,
            "records_processed": records_processed,
            "records_failed": records_failed,
            "error_message": error_message,
            "execution_details": execution_details,
        }

        try:
            self.model_db.execute_command(query, params)
        except Exception as e:
            logger.error(f"Failed to log pipeline execution: {e}")
    
    def close(self):
        """Close all database connections."""
        self.model_db.close()
        self.source_db.close()
        logger.info("Database connections closed")


# Singleton instance
_db_manager = None


def get_db_manager() -> DatabaseManager:
    """Get or create the singleton database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def close_db_connections():
    """Close all database connections."""
    global _db_manager
    if _db_manager is not None:
        _db_manager.close()
        _db_manager = None


# Utility functions for common operations
def get_latest_date(table_name: str, date_column: Optional[str] = None) -> Optional[str]:
    """Get the latest date from a table."""
    if date_column is None:
        date_column = "trade_date" if table_name in ["raw_trades_closed", "raw_trades_open"] else "date"
    
    db = get_db_manager().model_db
    query = f"""
        SELECT MAX({date_column})::text as max_date
        FROM prop_trading_model.{table_name}
        WHERE {date_column} IS NOT NULL
    """
    result = db.execute_query(query)
    return result[0]["max_date"] if result and result[0]["max_date"] else None


def execute_query(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a query using the model database."""
    return get_db_manager().model_db.execute_query(query, params)


def execute_query_df(query: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """Execute a query and return DataFrame using the model database."""
    return get_db_manager().model_db.execute_query_df(query, params)


def read_sql(query: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """Alias for execute_query_df for pandas compatibility."""
    return execute_query_df(query, params)


def to_sql(df: pd.DataFrame, table_name: str, schema: str = "prop_trading_model", 
          if_exists: str = "append", index: bool = False) -> None:
    """Write a DataFrame to a database table."""
    db = get_db_manager().model_db
    df.to_sql(
        name=table_name,
        con=db.engine,
        schema=schema,
        if_exists=if_exists,
        index=index,
        method="multi"
    )


# For testing
if __name__ == "__main__":
    print("Testing database connection...")
    
    # Get database manager
    db_manager = get_db_manager()
    
    # Test query execution
    result = db_manager.model_db.execute_query("SELECT version() as version")
    print(f"PostgreSQL version: {result[0]['version']}")
    
    # Test table operations
    tables = ["raw_metrics_daily", "raw_metrics_hourly", "raw_trades_closed"]
    for table in tables:
        if db_manager.model_db.table_exists(table):
            count = db_manager.model_db.get_table_row_count(table)
            latest = get_latest_date(table)
            print(f"\n{table}:")
            print(f"  Rows: {count:,}")
            print(f"  Latest: {latest}")
        else:
            print(f"\n{table}: Does not exist")
    
    # Close connections
    close_db_connections()
    print("\n✅ Database connection working!")