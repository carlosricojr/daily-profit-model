"""
Simple wrapper for PostgreSQL dynamic partitioning functions.
Replaces complex partition_migration_manager.py with database-native approach.
"""
import os
from typing import Dict, List, Optional, Any
from sqlalchemy import create_engine, text
import logging

logger = logging.getLogger(__name__)


class DynamicPartitionManager:
    """Simple wrapper for PostgreSQL dynamic partitioning functions."""
    
    def __init__(self, connection_string: Optional[str] = None):
        """Initialize with database connection."""
        self.connection_string = connection_string or os.getenv('DB_CONNECTION_STRING_SESSION_POOLER')
        if not self.connection_string:
            raise ValueError("Database connection string not provided")
        self.engine = create_engine(self.connection_string)
    
    def ensure_future_partitions(self, table_name: str, months_ahead: int = 3) -> int:
        """Ensure partitions exist for future months."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT prop_trading_model.ensure_partitions_exist(:table, :months)"),
                    {"table": table_name, "months": months_ahead}
                )
                count = result.scalar()
                logger.info(f"Ensured {count} partitions for {table_name}")
                return count
        except Exception as e:
            logger.error(f"Failed to ensure partitions for {table_name}: {e}")
            raise
    
    def analyze_table_conversion(self, table_name: str) -> Dict[str, Any]:
        """Analyze table for partition conversion (dry run)."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT prop_trading_model.analyze_table_conversion(:table)"),
                    {"table": table_name}
                )
                return result.scalar()  # Returns JSON
        except Exception as e:
            logger.error(f"Failed to analyze conversion for {table_name}: {e}")
            return {"error": str(e)}
    
    def convert_table_to_partitioned(self, table_name: str, batch_months: int = 1) -> str:
        """Convert existing table to partitioned table.
        
        Args:
            table_name: Name of table to convert
            batch_months: Number of months to process at once (default 1)
            
        Returns:
            Success message with details
        """
        try:
            with self.engine.connect() as conn:
                # Use a transaction for the entire conversion
                trans = conn.begin()
                try:
                    result = conn.execute(
                        text("SELECT prop_trading_model.convert_to_partitioned(:table, :batch_months)"),
                        {"table": table_name, "batch_months": batch_months}
                    )
                    message = result.scalar()
                    trans.commit()
                    logger.info(message)
                    return message
                except Exception:
                    trans.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error converting {table_name} to partitioned: {e}")
            raise
    
    def analyze_table_for_partitioning(self, table_name: str) -> Dict[str, Any]:
        """Analyze if table needs partitioning."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT * FROM prop_trading_model.analyze_table_for_partitioning(:table)"),
                    {"table": table_name}
                )
                row = result.fetchone()
                if row:
                    return {
                        "table_name": table_name,
                        "needs_partitioning": row.needs_partitioning,
                        "is_already_partitioned": row.is_already_partitioned,
                        "row_count": row.row_count,
                        "table_size": row.table_size,
                        "date_range": {
                            "min": row.min_date,
                            "max": row.max_date
                        },
                        "month_count": row.month_count,
                        "recommendation": row.recommendation
                    }
                return {"table_name": table_name, "error": "No data returned"}
        except Exception as e:
            logger.error(f"Failed to analyze {table_name}: {e}")
            return {"table_name": table_name, "error": str(e)}
    
    def analyze_partition_cleanup(self, table_name: str) -> List[Dict[str, Any]]:
        """Analyze which partitions can be safely cleaned up."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT * FROM prop_trading_model.cleanup_unused_partitions(:table)"),
                    {"table": table_name}
                )
                return [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to analyze cleanup for {table_name}: {e}")
            return []
    
    def get_partition_summary(self, table_name: str) -> Dict[str, Any]:
        """Get comprehensive partition summary."""
        try:
            with self.engine.connect() as conn:
                # Determine date column
                date_column = 'trade_date' if table_name in ['raw_trades_closed', 'raw_trades_open'] else 'date'
                
                # Get partition info
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as total_partitions,
                        COUNT(*) FILTER (WHERE pg_relation_size(
                            'prop_trading_model.' || tablename::regclass::text
                        ) = 0) as empty_partitions,
                        MIN(to_date(right(tablename, 7), 'YYYY_MM')) as oldest_partition,
                        MAX(to_date(right(tablename, 7), 'YYYY_MM')) as newest_partition
                    FROM pg_tables 
                    WHERE schemaname = 'prop_trading_model' 
                    AND tablename LIKE :pattern
                    AND tablename ~ '_20[0-9][0-9]_[0-9][0-9]$'
                """), {"pattern": f"{table_name}_%"})
                
                partition_data = result.fetchone()
                
                # Get actual data range
                result = conn.execute(text(f"""
                    SELECT MIN({date_column}) as min_data, MAX({date_column}) as max_data
                    FROM prop_trading_model.{table_name}
                """))
                
                data_range = result.fetchone()
                
                return {
                    "table_name": table_name,
                    "partitions": {
                        "total": partition_data.total_partitions if partition_data else 0,
                        "empty": partition_data.empty_partitions if partition_data else 0,
                        "oldest": partition_data.oldest_partition if partition_data else None,
                        "newest": partition_data.newest_partition if partition_data else None
                    },
                    "data_range": {
                        "min": data_range.min_data if data_range else None,
                        "max": data_range.max_data if data_range else None
                    }
                }
        except Exception as e:
            logger.error(f"Failed to get partition summary for {table_name}: {e}")
            return {
                "table_name": table_name,
                "error": str(e)
            }
    
    def execute_partition_cleanup(self, table_name: str, dry_run: bool = True) -> Dict[str, Any]:
        """Execute partition cleanup based on analysis."""
        try:
            cleanup_analysis = self.analyze_partition_cleanup(table_name)
            to_drop = [item for item in cleanup_analysis if item['action'] == 'DROP']
            
            if not to_drop:
                return {
                    "success": True,
                    "message": "No partitions need cleanup",
                    "partitions_dropped": 0
                }
            
            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "message": f"Would drop {len(to_drop)} empty partitions",
                    "partitions_to_drop": [p['partition_name'] for p in to_drop]
                }
            
            dropped = 0
            with self.engine.connect() as conn:
                for partition in to_drop:
                    try:
                        conn.execute(text(f"""
                            DROP TABLE IF EXISTS prop_trading_model.{partition['partition_name']}
                        """))
                        dropped += 1
                        logger.info(f"Dropped partition: {partition['partition_name']}")
                    except Exception as e:
                        logger.error(f"Failed to drop {partition['partition_name']}: {e}")
                
                conn.commit()
            
            return {
                "success": True,
                "message": f"Dropped {dropped} partitions",
                "partitions_dropped": dropped
            }
            
        except Exception as e:
            logger.error(f"Partition cleanup failed for {table_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Usage Examples
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize manager
    pm = DynamicPartitionManager()
    
    # Tables to process
    tables = ["raw_metrics_daily", "raw_metrics_hourly", "raw_trades_closed", "raw_trades_open"]
    
    for table in tables:
        print(f"\n{'='*60}")
        print(f"Processing: {table}")
        print('='*60)
        
        # Analyze if partitioning is needed
        analysis = pm.analyze_table_for_partitioning(table)
        print("\nPartitioning Analysis:")
        print(f"  Already partitioned: {analysis.get('is_already_partitioned', False)}")
        print(f"  Needs partitioning: {analysis.get('needs_partitioning', False)}")
        print(f"  Row count: {analysis.get('row_count', 0):,}")
        print(f"  Table size: {analysis.get('table_size', 'N/A')}")
        print(f"  Recommendation: {analysis.get('recommendation', 'N/A')}")
        
        # Get partition summary
        summary = pm.get_partition_summary(table)
        if 'error' not in summary:
            print("\nCurrent Partition Status:")
            print(f"  Total partitions: {summary['partitions']['total']}")
            print(f"  Empty partitions: {summary['partitions']['empty']}")
            print(f"  Partition range: {summary['partitions']['oldest']} to {summary['partitions']['newest']}")
            print(f"  Data range: {summary['data_range']['min']} to {summary['data_range']['max']}")
        
        # Ensure future partitions
        count = pm.ensure_future_partitions(table, months_ahead=6)
        print(f"\n✓ Ensured {count} future partitions")
        
        # Analyze cleanup opportunities
        cleanup_analysis = pm.analyze_partition_cleanup(table)
        if cleanup_analysis:
            print("\nPartition Cleanup Analysis:")
            keep_count = sum(1 for item in cleanup_analysis if item['action'] == 'KEEP')
            drop_count = sum(1 for item in cleanup_analysis if item['action'] == 'DROP')
            print(f"  Partitions to keep: {keep_count}")
            print(f"  Partitions to drop: {drop_count}")
            
            # Show details for partitions to drop
            for item in cleanup_analysis:
                if item['action'] == 'DROP':
                    print(f"    🗑️  {item['partition_name']}: {item['reason']} ({item['row_count']} rows)")
    
    print("\n" + "="*60)
    print("🎯 Partition Management Summary:")
    print("="*60)
    print("✅ All tables analyzed and future partitions ensured")
    print("✅ Intelligent cleanup preserves data integrity")
    print("✅ Empty partitions within data range are preserved")
    print("🗑️  Only empty partitions outside data range are marked for cleanup")
    
    # Example: Converting a table to partitioned
    print("\n" + "="*60)
    print("📊 Table Conversion Example (Dry Run):")
    print("="*60)
    
    # Analyze conversion requirements for raw_metrics_hourly
    conversion_analysis = pm.analyze_table_conversion("raw_metrics_hourly")
    if 'error' not in conversion_analysis:
        print("\nConversion Analysis for raw_metrics_hourly:")
        print(f"  Row count: {conversion_analysis.get('row_count', 0):,}")
        print(f"  Table size: {conversion_analysis.get('table_size', 'N/A')}")
        print(f"  Date range: {conversion_analysis['date_range']['min']} to {conversion_analysis['date_range']['max']}")
        print(f"  Months spanned: {conversion_analysis.get('months_spanned', 0)}")
        print(f"  Partitions needed: {conversion_analysis.get('partitions_needed', 0)}")
        print("\nTo convert this table to partitioned, run:")
        print("  result = pm.convert_table_to_partitioned('raw_metrics_hourly', batch_months=1)")
        print("  # This will migrate data month-by-month to avoid locks")