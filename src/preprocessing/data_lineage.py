"""
Basic data lineage tracking for the preprocessing pipeline.
Tracks data flow from source to staging to features.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date
import json
import hashlib
from dataclasses import dataclass
from enum import Enum
import networkx as nx

logger = logging.getLogger(__name__)


class LineageNodeType(Enum):
    """Types of nodes in the lineage graph."""
    SOURCE_TABLE = "source_table"
    STAGING_TABLE = "staging_table"
    FEATURE_TABLE = "feature_table"
    TRANSFORMATION = "transformation"
    VALIDATION = "validation"
    MODEL_INPUT = "model_input"


@dataclass
class LineageNode:
    """Node in the data lineage graph."""
    node_id: str
    node_type: LineageNodeType
    name: str
    table_name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict] = None


@dataclass
class LineageEdge:
    """Edge in the data lineage graph."""
    source_node_id: str
    target_node_id: str
    transformation_type: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict] = None


@dataclass
class DataLineageRecord:
    """Record of data lineage for tracking."""
    lineage_id: str
    source_table: str
    target_table: str
    transformation_type: str
    processing_date: date
    record_count: int
    start_time: datetime
    end_time: datetime
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict] = None


class DataLineageTracker:
    """Tracks data lineage through the preprocessing pipeline."""
    
    def __init__(self, db_manager):
        """Initialize lineage tracker."""
        self.db_manager = db_manager
        self.graph = nx.DiGraph()
        self._ensure_lineage_tables()
        self._build_lineage_graph()
    
    def _ensure_lineage_tables(self):
        """Ensure lineage tracking tables exist."""
        # Table for lineage records
        create_lineage_table = """
        CREATE TABLE IF NOT EXISTS data_lineage_records (
            lineage_id VARCHAR(255) PRIMARY KEY,
            source_table VARCHAR(255),
            target_table VARCHAR(255),
            transformation_type VARCHAR(100),
            processing_date DATE,
            record_count INTEGER,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration_seconds FLOAT,
            success BOOLEAN,
            error_message TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.db_manager.model_db.execute_command(create_lineage_table)
        
        # Table for column-level lineage
        create_column_lineage_table = """
        CREATE TABLE IF NOT EXISTS column_lineage (
            id SERIAL PRIMARY KEY,
            source_table VARCHAR(255),
            source_column VARCHAR(255),
            target_table VARCHAR(255),
            target_column VARCHAR(255),
            transformation_logic TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_table, source_column, target_table, target_column)
        )
        """
        self.db_manager.model_db.execute_command(create_column_lineage_table)
        
        # Create indexes
        self.db_manager.model_db.execute_command(
            "CREATE INDEX IF NOT EXISTS idx_lineage_processing_date ON data_lineage_records(processing_date)"
        )
        self.db_manager.model_db.execute_command(
            "CREATE INDEX IF NOT EXISTS idx_lineage_tables ON data_lineage_records(source_table, target_table)"
        )
    
    def _build_lineage_graph(self):
        """Build the data lineage graph."""
        # Define nodes
        nodes = [
            # Source tables
            LineageNode("raw_accounts", LineageNodeType.SOURCE_TABLE, "Raw Accounts", "raw_accounts_data"),
            LineageNode("raw_metrics_daily", LineageNodeType.SOURCE_TABLE, "Raw Daily Metrics", "raw_metrics_daily"),
            LineageNode("raw_metrics_alltime", LineageNodeType.SOURCE_TABLE, "Raw Alltime Metrics", "raw_metrics_alltime"),
            LineageNode("raw_trades", LineageNodeType.SOURCE_TABLE, "Raw Trades", "raw_trades_closed"),
            LineageNode("raw_plans", LineageNodeType.SOURCE_TABLE, "Raw Plans", "raw_plans_data"),
            LineageNode("raw_regimes", LineageNodeType.SOURCE_TABLE, "Raw Regimes", "raw_regimes_daily"),
            
            # Staging tables
            LineageNode("stg_snapshots", LineageNodeType.STAGING_TABLE, "Staging Snapshots", "stg_accounts_daily_snapshots"),
            
            # Transformations
            LineageNode("snapshot_creation", LineageNodeType.TRANSFORMATION, "Snapshot Creation"),
            LineageNode("data_validation", LineageNodeType.VALIDATION, "Data Validation"),
            LineageNode("feature_engineering", LineageNodeType.TRANSFORMATION, "Feature Engineering"),
            
            # Feature tables
            LineageNode("feature_store", LineageNodeType.FEATURE_TABLE, "Feature Store", "feature_store_account_daily"),
            
            # Model input
            LineageNode("model_input", LineageNodeType.MODEL_INPUT, "Model Training Input", "model_training_input")
        ]
        
        # Add nodes to graph
        for node in nodes:
            self.graph.add_node(node.node_id, data=node)
        
        # Define edges (data flow)
        edges = [
            # Raw to staging
            LineageEdge("raw_accounts", "snapshot_creation", "join"),
            LineageEdge("raw_metrics_daily", "snapshot_creation", "join"),
            LineageEdge("raw_plans", "snapshot_creation", "join"),
            LineageEdge("snapshot_creation", "stg_snapshots", "insert"),
            
            # Validation
            LineageEdge("stg_snapshots", "data_validation", "validate"),
            
            # Staging to features
            LineageEdge("stg_snapshots", "feature_engineering", "aggregate"),
            LineageEdge("raw_metrics_daily", "feature_engineering", "aggregate"),
            LineageEdge("raw_trades", "feature_engineering", "aggregate"),
            LineageEdge("raw_regimes", "feature_engineering", "join"),
            LineageEdge("feature_engineering", "feature_store", "insert"),
            
            # Features to model
            LineageEdge("feature_store", "model_input", "select")
        ]
        
        # Add edges to graph
        for edge in edges:
            self.graph.add_edge(
                edge.source_node_id,
                edge.target_node_id,
                transformation_type=edge.transformation_type,
                data=edge
            )
    
    def track_transformation(self, source_table: str, target_table: str,
                           transformation_type: str, processing_date: date,
                           record_count: int, start_time: datetime,
                           success: bool = True, error_message: Optional[str] = None,
                           metadata: Optional[Dict] = None) -> str:
        """
        Track a data transformation in the lineage.
        
        Args:
            source_table: Source table name
            target_table: Target table name
            transformation_type: Type of transformation
            processing_date: Date being processed
            record_count: Number of records processed
            start_time: Transformation start time
            success: Whether transformation succeeded
            error_message: Error message if failed
            metadata: Additional metadata
            
        Returns:
            Lineage ID
        """
        end_time = datetime.now()
        duration_seconds = (end_time - start_time).total_seconds()
        
        # Generate lineage ID
        lineage_id = self._generate_lineage_id(
            source_table, target_table, transformation_type, processing_date
        )
        
        # Create lineage record
        record = DataLineageRecord(
            lineage_id=lineage_id,
            source_table=source_table,
            target_table=target_table,
            transformation_type=transformation_type,
            processing_date=processing_date,
            record_count=record_count,
            start_time=start_time,
            end_time=end_time,
            success=success,
            error_message=error_message,
            metadata=metadata
        )
        
        # Save to database
        self._save_lineage_record(record, duration_seconds)
        
        logger.info(f"Tracked lineage: {source_table} -> {target_table} "
                   f"({transformation_type}), {record_count} records")
        
        return lineage_id
    
    def _generate_lineage_id(self, source: str, target: str,
                           transformation: str, date: date) -> str:
        """Generate unique lineage ID."""
        components = f"{source}_{target}_{transformation}_{date}_{datetime.now().timestamp()}"
        return hashlib.md5(components.encode()).hexdigest()
    
    def _save_lineage_record(self, record: DataLineageRecord, duration_seconds: float):
        """Save lineage record to database."""
        query = """
        INSERT INTO data_lineage_records (
            lineage_id, source_table, target_table, transformation_type,
            processing_date, record_count, start_time, end_time,
            duration_seconds, success, error_message, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = (
            record.lineage_id,
            record.source_table,
            record.target_table,
            record.transformation_type,
            record.processing_date,
            record.record_count,
            record.start_time,
            record.end_time,
            duration_seconds,
            record.success,
            record.error_message,
            json.dumps(record.metadata) if record.metadata else None
        )
        
        self.db_manager.model_db.execute_command(query, params)
    
    def register_column_lineage(self, mappings: List[Dict[str, str]]):
        """
        Register column-level lineage mappings.
        
        Args:
            mappings: List of column mapping dictionaries
                     Each should have: source_table, source_column,
                     target_table, target_column, transformation_logic
        """
        for mapping in mappings:
            query = """
            INSERT INTO column_lineage (
                source_table, source_column, target_table, 
                target_column, transformation_logic
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_table, source_column, target_table, target_column)
            DO UPDATE SET transformation_logic = EXCLUDED.transformation_logic
            """
            
            params = (
                mapping['source_table'],
                mapping['source_column'],
                mapping['target_table'],
                mapping['target_column'],
                mapping.get('transformation_logic', 'direct')
            )
            
            self.db_manager.model_db.execute_command(query, params)
    
    def get_upstream_lineage(self, table_name: str, 
                           levels: int = 3) -> Dict[str, List[str]]:
        """
        Get upstream lineage for a table.
        
        Args:
            table_name: Table to trace lineage for
            levels: Number of levels to trace back
            
        Returns:
            Dictionary of upstream tables by level
        """
        upstream = {}
        current_tables = {table_name}
        
        for level in range(1, levels + 1):
            upstream_tables = set()
            
            for table in current_tables:
                query = """
                SELECT DISTINCT source_table
                FROM data_lineage_records
                WHERE target_table = %s
                AND success = TRUE
                """
                results = self.db_manager.model_db.execute_query(query, (table,))
                
                for result in results:
                    upstream_tables.add(result['source_table'])
            
            if upstream_tables:
                upstream[f"level_{level}"] = list(upstream_tables)
                current_tables = upstream_tables
            else:
                break
        
        return upstream
    
    def get_downstream_impact(self, table_name: str,
                            processing_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Get downstream impact of changes to a table.
        
        Args:
            table_name: Table to analyze impact for
            processing_date: Optional date filter
            
        Returns:
            Dictionary with downstream impact analysis
        """
        # Get directly impacted tables
        query = """
        SELECT 
            target_table,
            transformation_type,
            COUNT(*) as transformation_count,
            SUM(record_count) as total_records,
            MAX(processing_date) as last_processed
        FROM data_lineage_records
        WHERE source_table = %s
        """
        
        params = [table_name]
        if processing_date:
            query += " AND processing_date = %s"
            params.append(processing_date)
        
        query += " GROUP BY target_table, transformation_type"
        
        direct_impact = self.db_manager.model_db.execute_query(query, tuple(params))
        
        # Get indirect impact (2 levels deep)
        impacted_tables = set(row['target_table'] for row in direct_impact)
        indirect_impact = []
        
        for impacted_table in impacted_tables:
            indirect_query = """
            SELECT DISTINCT target_table
            FROM data_lineage_records
            WHERE source_table = %s
            AND success = TRUE
            """
            indirect_results = self.db_manager.model_db.execute_query(
                indirect_query, (impacted_table,)
            )
            indirect_impact.extend([r['target_table'] for r in indirect_results])
        
        return {
            'source_table': table_name,
            'direct_impact': direct_impact,
            'indirect_impact': list(set(indirect_impact)),
            'total_impacted_tables': len(impacted_tables) + len(set(indirect_impact))
        }
    
    def get_data_freshness(self, table_name: str) -> Dict[str, Any]:
        """
        Get data freshness information for a table.
        
        Args:
            table_name: Table to check freshness for
            
        Returns:
            Dictionary with freshness metrics
        """
        query = """
        SELECT 
            MAX(processing_date) as latest_date,
            MAX(end_time) as latest_update,
            COUNT(DISTINCT processing_date) as dates_processed,
            AVG(duration_seconds) as avg_processing_time
        FROM data_lineage_records
        WHERE target_table = %s
        AND success = TRUE
        """
        
        result = self.db_manager.model_db.execute_query(query, (table_name,))
        
        if result and result[0]['latest_date']:
            freshness = result[0]
            age_hours = (datetime.now() - freshness['latest_update']).total_seconds() / 3600
            
            return {
                'table_name': table_name,
                'latest_date': freshness['latest_date'],
                'latest_update': freshness['latest_update'],
                'age_hours': age_hours,
                'dates_processed': freshness['dates_processed'],
                'avg_processing_time_seconds': freshness['avg_processing_time'],
                'is_stale': age_hours > 24  # Consider stale if >24 hours old
            }
        
        return {
            'table_name': table_name,
            'latest_date': None,
            'is_stale': True,
            'error': 'No successful processing records found'
        }
    
    def visualize_lineage(self, table_name: str, output_file: Optional[str] = None):
        """
        Create a visualization of data lineage.
        
        Args:
            table_name: Table to visualize lineage for
            output_file: Optional file to save visualization
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            
            # Get subgraph for the table
            if table_name in self.graph:
                # Get ancestors and descendants
                ancestors = nx.ancestors(self.graph, table_name)
                descendants = nx.descendants(self.graph, table_name)
                
                # Create subgraph
                nodes = {table_name} | ancestors | descendants
                subgraph = self.graph.subgraph(nodes)
                
                # Set up plot
                plt.figure(figsize=(12, 8))
                pos = nx.spring_layout(subgraph, k=2, iterations=50)
                
                # Color nodes by type
                node_colors = []
                for node in subgraph.nodes():
                    node_data = self.graph.nodes[node]['data']
                    if node_data.node_type == LineageNodeType.SOURCE_TABLE:
                        node_colors.append('lightblue')
                    elif node_data.node_type == LineageNodeType.STAGING_TABLE:
                        node_colors.append('lightgreen')
                    elif node_data.node_type == LineageNodeType.FEATURE_TABLE:
                        node_colors.append('lightcoral')
                    elif node_data.node_type == LineageNodeType.TRANSFORMATION:
                        node_colors.append('lightyellow')
                    else:
                        node_colors.append('lightgray')
                
                # Draw graph
                nx.draw(subgraph, pos, node_color=node_colors, with_labels=True,
                       node_size=3000, font_size=8, font_weight='bold',
                       arrows=True, edge_color='gray', alpha=0.7)
                
                # Add legend
                source_patch = mpatches.Patch(color='lightblue', label='Source Tables')
                staging_patch = mpatches.Patch(color='lightgreen', label='Staging Tables')
                feature_patch = mpatches.Patch(color='lightcoral', label='Feature Tables')
                transform_patch = mpatches.Patch(color='lightyellow', label='Transformations')
                
                plt.legend(handles=[source_patch, staging_patch, feature_patch, transform_patch],
                          loc='upper left', bbox_to_anchor=(0, 1))
                
                plt.title(f"Data Lineage for {table_name}")
                plt.axis('off')
                
                if output_file:
                    plt.savefig(output_file, dpi=300, bbox_inches='tight')
                    logger.info(f"Lineage visualization saved to {output_file}")
                else:
                    plt.show()
                    
        except ImportError:
            logger.warning("Matplotlib not available for visualization")
    
    def generate_lineage_report(self, start_date: date, end_date: date,
                              output_file: Optional[str] = None) -> str:
        """Generate comprehensive lineage report."""
        report_lines = [
            "=" * 80,
            "DATA LINEAGE REPORT",
            f"Period: {start_date} to {end_date}",
            f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            ""
        ]
        
        # Processing summary
        summary_query = """
        SELECT 
            COUNT(*) as total_transformations,
            COUNT(DISTINCT source_table || '->' || target_table) as unique_flows,
            SUM(record_count) as total_records,
            AVG(duration_seconds) as avg_duration,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed
        FROM data_lineage_records
        WHERE processing_date BETWEEN %s AND %s
        """
        
        summary = self.db_manager.model_db.execute_query(
            summary_query, (start_date, end_date)
        )
        
        if summary:
            stats = summary[0]
            report_lines.extend([
                "PROCESSING SUMMARY",
                "-" * 40,
                f"Total Transformations: {stats['total_transformations']:,}",
                f"Unique Data Flows: {stats['unique_flows']}",
                f"Total Records Processed: {stats['total_records']:,}",
                f"Average Duration: {stats['avg_duration']:.2f} seconds",
                f"Success Rate: {stats['successful']/stats['total_transformations']*100:.1f}%",
                ""
            ])
        
        # Table freshness
        tables = ['stg_accounts_daily_snapshots', 'feature_store_account_daily']
        report_lines.extend([
            "TABLE FRESHNESS",
            "-" * 40
        ])
        
        for table in tables:
            freshness = self.get_data_freshness(table)
            status = "STALE" if freshness.get('is_stale') else "FRESH"
            report_lines.append(
                f"{table}: {status} "
                f"(Last update: {freshness.get('age_hours', 'N/A'):.1f} hours ago)"
            )
        
        report = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            logger.info(f"Lineage report saved to {output_file}")
        
        return report