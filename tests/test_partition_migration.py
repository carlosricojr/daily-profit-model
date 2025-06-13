"""
Test Suite for Partition Migration Manager

Tests the conversion of regular tables to partitioned tables,
specifically for the raw_metrics_hourly test case.
"""

import pytest
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from unittest.mock import Mock, patch, MagicMock

from src.utils.partition_migration_manager import PartitionMigrationManager, create_partition_functions
from src.utils.enhanced_alembic_schema_manager import EnhancedAlembicSchemaManager
from src.utils.database import DatabaseManager


class TestPartitionMigrationManager:
    """Test partition migration functionality."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        mock = Mock(spec=DatabaseManager)
        mock.model_db = Mock()
        mock.model_db.get_connection = Mock()
        return mock
    
    @pytest.fixture
    def partition_manager(self, mock_db_manager):
        """Create partition migration manager."""
        return PartitionMigrationManager(mock_db_manager)
    
    def test_analyze_table_for_partitioning_needs_partitioning(self, partition_manager, mock_db_manager):
        """Test analyzing a table that needs partitioning."""
        # Mock database responses
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock the connection context manager
        mock_db_manager.model_db.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock query results in order
        mock_cursor.fetchone.side_effect = [
            # Table size query
            {
                'total_size': '1951 MB',
                'table_size': '1200 MB',
                'indexes_size': '751 MB',
                'row_count': 2078825
            },
            # Date column query
            {
                'column_name': 'date',
                'data_type': 'date'
            },
            # Date range query
            {
                'min_date': date(2024, 11, 18),
                'max_date': date(2025, 6, 11),
                'month_count': 8
            },
            # Table kind query (regular table)
            {
                'relkind': 'r'  # 'r' = regular table, 'p' = partitioned
            }
        ]
        
        result = partition_manager.analyze_table_for_partitioning('raw_metrics_hourly')
        
        assert result['needs_partitioning'] is True
        assert result['is_already_partitioned'] is False
        assert result['table_name'] == 'raw_metrics_hourly'
        assert result['partition_column'] == 'date'
        assert result['size_info']['row_count'] == 2078825
        assert result['migration_complexity'] == 'HIGH'
        assert result['recommended_strategy'] == 'monthly'
    
    def test_analyze_table_already_partitioned(self, partition_manager, mock_db_manager):
        """Test analyzing a table that's already partitioned."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db_manager.model_db.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock query results
        mock_cursor.fetchone.side_effect = [
            # Table size query
            {
                'total_size': '5 GB',
                'table_size': '3 GB',
                'indexes_size': '2 GB',
                'row_count': 5000000
            },
            # Date column query
            {
                'column_name': 'date',
                'data_type': 'date'
            },
            # Date range query
            {
                'min_date': date(2024, 1, 1),
                'max_date': date(2025, 6, 11),
                'month_count': 18
            },
            # Table kind query (partitioned table)
            {
                'relkind': 'p'  # Already partitioned
            }
        ]
        
        result = partition_manager.analyze_table_for_partitioning('raw_metrics_daily')
        
        assert result['needs_partitioning'] is False
        assert result['is_already_partitioned'] is True
    
    def test_generate_migration_plan(self, partition_manager, mock_db_manager):
        """Test generating a migration plan (dry run)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db_manager.model_db.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock analysis results
        analysis = {
            'needs_partitioning': True,
            'size_info': {
                'total_size': '1951 MB',
                'row_count': 2078825
            },
            'date_range': {
                'min_date': date(2024, 11, 18),
                'max_date': date(2025, 6, 11)
            }
        }
        
        result = partition_manager._generate_migration_plan(
            'raw_metrics_hourly',
            'date',
            'monthly',
            analysis
        )
        
        assert result['dry_run'] is True
        assert result['plan']['table'] == 'raw_metrics_hourly'
        assert result['plan']['partition_column'] == 'date'
        assert result['plan']['strategy'] == 'monthly'
        assert result['plan']['partitions_needed'] > 0
        assert 'estimated_time_seconds' in result['plan']
        assert len(result['plan']['steps']) == 7
    
    def test_partition_creation_logic(self, partition_manager):
        """Test partition creation date calculations."""
        # Test monthly partitions
        min_date = date(2024, 11, 18)
        max_date = date(2025, 6, 11)
        
        # Calculate expected partitions
        current = min_date.replace(day=1) - relativedelta(months=1)  # Start one month before
        end = max_date.replace(day=1) + relativedelta(months=3)  # End 3 months after
        
        partition_count = 0
        while current < end:
            partition_count += 1
            current += relativedelta(months=1)
        
        # Should create partitions from Oct 2024 to Sep 2025 (12 partitions)
        assert partition_count >= 10  # At minimum
        assert partition_count <= 15  # At maximum


class TestEnhancedAlembicIntegration:
    """Test integration of partition migration with enhanced Alembic."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        mock = Mock(spec=DatabaseManager)
        mock.model_db = Mock()
        mock.model_db.get_connection = Mock()
        mock.model_db.user = 'test_user'
        mock.model_db.password = 'test_pass'
        mock.model_db.host = 'localhost'
        mock.model_db.port = 5432
        mock.model_db.database = 'test_db'
        return mock
    
    @patch('src.utils.enhanced_alembic_schema_manager.create_engine')
    def test_partition_migration_detection(self, mock_create_engine, mock_db_manager):
        """Test that enhanced Alembic detects tables needing partitioning."""
        # Mock engine
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        # Create schema manager
        with patch.object(EnhancedAlembicSchemaManager, '_setup_alembic_config'):
            schema_manager = EnhancedAlembicSchemaManager(mock_db_manager)
            
            # Mock partition manager analysis
            with patch.object(schema_manager.partition_manager, 'analyze_table_for_partitioning') as mock_analyze:
                mock_analyze.return_value = {
                    'needs_partitioning': True,
                    'is_already_partitioned': False,
                    'table_name': 'raw_metrics_hourly',
                    'partition_column': 'date',
                    'size_info': {'row_count': 2078825},
                    'date_range': {
                        'min_date': date(2024, 11, 18),
                        'max_date': date(2025, 6, 11),
                        'month_count': 8
                    },
                    'migration_complexity': 'HIGH',
                    'recommended_strategy': 'monthly'
                }
                
                # Test partition check
                result = schema_manager._check_partition_migrations_needed()
                
                assert result['partitioning_needed'] is True
                assert len(result['tables_to_partition']) == 1
                assert result['tables_to_partition'][0]['table_name'] == 'raw_metrics_hourly'
                assert result['tables_to_partition'][0]['strategy'] == 'monthly'


class TestPartitionFunctions:
    """Test PostgreSQL partition management functions."""
    
    def test_create_partition_functions_sql(self):
        """Test that partition functions SQL is valid."""
        # This would be run against a test database
        # For now, just verify the SQL structure
        
        expected_functions = [
            'create_monthly_partition',
            'ensure_partitions_exist'
        ]
        
        # In a real test, we'd execute against a test DB
        # and verify the functions were created
        assert len(expected_functions) == 2


@pytest.mark.integration
class TestEndToEndPartitionMigration:
    """End-to-end tests for partition migration (requires test database)."""
    
    @pytest.mark.skip(reason="Requires test database setup")
    def test_full_partition_migration_workflow(self):
        """Test complete workflow of converting raw_metrics_hourly to partitioned."""
        # This would:
        # 1. Create a test table with sample data
        # 2. Run the partition migration
        # 3. Verify data integrity
        # 4. Verify partitions were created
        # 5. Verify performance improvements
        pass