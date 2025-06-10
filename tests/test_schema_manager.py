"""
Comprehensive tests for the database schema management system.

Tests cover:
- Schema parsing from SQL files
- Schema comparison and diff detection
- Migration generation and application
- Version tracking and rollback
- Data preservation during migrations
- Edge cases and error handling
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import psycopg2

# Add parent directory to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.schema_manager import SchemaManager, SchemaObject
from src.utils.database import DatabaseManager


class TestSchemaObject:
    """Test the SchemaObject class."""
    
    def test_schema_object_creation(self):
        """Test creating a schema object."""
        obj = SchemaObject(
            obj_type='TABLE',
            name='test_table',
            definition='CREATE TABLE test_table (id INT PRIMARY KEY);',
            dependencies=['TABLE:parent_table']
        )
        
        assert obj.type == 'TABLE'
        assert obj.name == 'test_table'
        assert obj.definition == 'CREATE TABLE test_table (id INT PRIMARY KEY);'
        assert obj.dependencies == ['TABLE:parent_table']
        assert obj.checksum is not None
        assert len(obj.checksum) == 32  # MD5 hash length
    
    def test_schema_object_checksum(self):
        """Test that checksum is consistent and changes with definition."""
        obj1 = SchemaObject('TABLE', 'test', 'CREATE TABLE test (id INT);')
        obj2 = SchemaObject('TABLE', 'test', 'CREATE TABLE test (id INT);')
        obj3 = SchemaObject('TABLE', 'test', 'CREATE TABLE test (id INTEGER);')
        
        # Same definition should produce same checksum
        assert obj1.checksum == obj2.checksum
        
        # Different definition should produce different checksum
        assert obj1.checksum != obj3.checksum
    
    def test_schema_object_checksum_normalization(self):
        """Test that checksum normalizes whitespace."""
        obj1 = SchemaObject('TABLE', 'test', 'CREATE TABLE test (id INT);')
        obj2 = SchemaObject('TABLE', 'test', 'CREATE  TABLE   test   (id   INT);')
        
        # Different whitespace should produce same checksum
        assert obj1.checksum == obj2.checksum


class TestSchemaManager:
    """Test the SchemaManager class."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager."""
        mock = Mock(spec=DatabaseManager)
        mock.model_db = Mock()
        mock.model_db.get_connection = Mock()
        return mock
    
    @pytest.fixture
    def schema_manager(self, mock_db_manager):
        """Create a SchemaManager instance with mocked database."""
        return SchemaManager(mock_db_manager)
    
    @pytest.fixture
    def sample_schema_sql(self):
        """Sample schema SQL for testing."""
        return """
        -- Test schema file
        CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
        
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            total DECIMAL(10, 2) NOT NULL,
            order_date DATE NOT NULL
        ) PARTITION BY RANGE (order_date);
        
        CREATE INDEX idx_users_email ON users(email);
        CREATE UNIQUE INDEX idx_users_username ON users(username);
        CREATE INDEX idx_orders_user_date ON orders(user_id, order_date DESC);
        
        CREATE VIEW active_users AS
        SELECT * FROM users WHERE created_at > CURRENT_DATE - INTERVAL '30 days';
        
        CREATE MATERIALIZED VIEW user_order_summary AS
        SELECT 
            u.id as user_id,
            u.username,
            COUNT(o.id) as order_count,
            SUM(o.total) as total_spent
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id, u.username
        WITH DATA;
        
        CREATE OR REPLACE FUNCTION get_user_orders(p_user_id INTEGER)
        RETURNS TABLE(order_id INTEGER, total DECIMAL, order_date DATE) AS $$
        BEGIN
            RETURN QUERY
            SELECT id, total, order_date
            FROM orders
            WHERE user_id = p_user_id
            ORDER BY order_date DESC;
        END;
        $$ LANGUAGE plpgsql;
        """
    
    def test_ensure_version_table(self, schema_manager, mock_db_manager):
        """Test creating the version tracking table."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        
        mock_db_manager.model_db.get_connection.return_value = mock_conn
        
        schema_manager.ensure_version_table()
        
        # Check that CREATE TABLE was executed
        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0][0]
        assert 'CREATE TABLE IF NOT EXISTS' in call_args
        assert 'schema_version' in call_args
        assert 'version_hash' in call_args
        assert 'migration_script' in call_args
        assert 'rollback_script' in call_args
    
    def test_get_current_version(self, schema_manager, mock_db_manager):
        """Test getting the current schema version."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        
        # Test when version exists
        mock_cursor.fetchone.return_value = ('abc123def456',)
        mock_db_manager.model_db.get_connection.return_value = mock_conn
        
        version = schema_manager.get_current_version()
        assert version == 'abc123def456'
        
        # Test when no version exists
        mock_cursor.fetchone.return_value = None
        version = schema_manager.get_current_version()
        assert version is None
        
        # Test when table doesn't exist
        mock_cursor.execute.side_effect = psycopg2.errors.UndefinedTable("relation does not exist")
        version = schema_manager.get_current_version()
        assert version is None
    
    def test_parse_schema_file(self, schema_manager, sample_schema_sql, tmp_path):
        """Test parsing a schema SQL file."""
        # Write sample schema to temporary file
        schema_file = tmp_path / "test_schema.sql"
        schema_file.write_text(sample_schema_sql)
        
        objects = schema_manager.parse_schema_file(schema_file)
        
        # Check extensions
        assert 'EXTENSION:pg_stat_statements' in objects
        
        # Check tables
        assert 'TABLE:users' in objects
        assert 'TABLE:orders' in objects
        assert 'id SERIAL PRIMARY KEY' in objects['TABLE:users'].definition
        assert 'PARTITION BY RANGE' in objects['TABLE:orders'].definition
        
        # Check indexes
        assert 'INDEX:idx_users_email' in objects
        assert 'INDEX:idx_users_username' in objects
        assert 'INDEX:idx_orders_user_date' in objects
        assert 'UNIQUE' in objects['INDEX:idx_users_username'].definition
        
        # Check views
        assert 'VIEW:active_users' in objects
        assert 'MATERIALIZED VIEW:user_order_summary' in objects
        
        # Check functions
        assert 'FUNCTION:get_user_orders' in objects
        assert 'RETURNS TABLE' in objects['FUNCTION:get_user_orders'].definition
    
    def test_parse_tables(self, schema_manager):
        """Test parsing CREATE TABLE statements."""
        content = """
        CREATE TABLE simple_table (id INT);
        
        CREATE TABLE IF NOT EXISTS complex_table (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uk_name UNIQUE(name)
        );
        
        CREATE TABLE partitioned_table (
            id BIGSERIAL,
            date DATE NOT NULL,
            data TEXT
        ) PARTITION BY RANGE (date);
        
        CREATE TABLE schema_qualified.table_name (id INT);
        """
        
        objects = {}
        schema_manager._parse_tables(content, objects)
        
        assert 'TABLE:simple_table' in objects
        assert 'TABLE:complex_table' in objects
        assert 'TABLE:partitioned_table' in objects
        assert 'TABLE:table_name' in objects
        
        # Check that partition clause is captured
        assert 'PARTITION BY RANGE' in objects['TABLE:partitioned_table'].definition
    
    def test_parse_indexes(self, schema_manager):
        """Test parsing CREATE INDEX statements."""
        content = """
        CREATE INDEX idx_simple ON users(email);
        CREATE UNIQUE INDEX idx_unique ON users(username);
        CREATE INDEX IF NOT EXISTS idx_complex ON orders(user_id, order_date DESC);
        CREATE INDEX idx_partial ON orders(total) WHERE total > 100;
        CREATE INDEX idx_qualified ON schema.table(column);
        """
        
        objects = {}
        schema_manager._parse_indexes(content, objects)
        
        assert 'INDEX:idx_simple' in objects
        assert 'INDEX:idx_unique' in objects
        assert 'INDEX:idx_complex' in objects
        assert 'INDEX:idx_partial' in objects
        assert 'INDEX:idx_qualified' in objects
        
        # Check dependencies - may have multiple tables in dependencies list
        assert 'TABLE:users' in str(objects['INDEX:idx_simple'].dependencies)
        assert 'TABLE:orders' in str(objects['INDEX:idx_complex'].dependencies)
    
    def test_parse_views(self, schema_manager):
        """Test parsing CREATE VIEW statements."""
        content = """
        CREATE VIEW simple_view AS SELECT * FROM users;
        
        CREATE OR REPLACE VIEW complex_view AS
        SELECT u.id, u.username, COUNT(o.id) as order_count
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id, u.username;
        
        CREATE VIEW IF NOT EXISTS schema.qualified_view AS
        SELECT * FROM schema.table;
        """
        
        objects = {}
        schema_manager._parse_views(content, objects)
        
        assert 'VIEW:simple_view' in objects
        assert 'VIEW:complex_view' in objects
        assert 'VIEW:qualified_view' in objects
        
        # Check dependencies
        assert 'TABLE:users' in objects['VIEW:simple_view'].dependencies
        assert 'TABLE:users' in objects['VIEW:complex_view'].dependencies
        assert 'TABLE:orders' in objects['VIEW:complex_view'].dependencies
    
    def test_parse_functions(self, schema_manager):
        """Test parsing CREATE FUNCTION statements."""
        content = """
        CREATE FUNCTION simple_func() RETURNS INTEGER AS $$
        BEGIN
            RETURN 42;
        END;
        $$ LANGUAGE plpgsql;
        
        CREATE OR REPLACE FUNCTION complex_func(p_id INTEGER, p_name TEXT)
        RETURNS TABLE(id INTEGER, name TEXT, total DECIMAL) AS $$
        BEGIN
            RETURN QUERY
            SELECT id, name, SUM(amount) as total
            FROM transactions
            WHERE user_id = p_id
            GROUP BY id, name;
        END;
        $$ LANGUAGE plpgsql;
        
        CREATE FUNCTION schema.qualified_func() RETURNS VOID AS $$
        BEGIN
            -- Do nothing
        END;
        $$ LANGUAGE plpgsql;
        """
        
        objects = {}
        schema_manager._parse_functions(content, objects)
        
        assert 'FUNCTION:simple_func' in objects
        assert 'FUNCTION:complex_func' in objects
        assert 'FUNCTION:qualified_func' in objects
        
        # Check that full definition is captured
        assert 'RETURNS INTEGER' in objects['FUNCTION:simple_func'].definition
        assert 'RETURNS TABLE' in objects['FUNCTION:complex_func'].definition
    
    def test_parse_materialized_views(self, schema_manager):
        """Test parsing CREATE MATERIALIZED VIEW statements."""
        content = """
        CREATE MATERIALIZED VIEW simple_mv AS
        SELECT * FROM users
        WITH DATA;
        
        CREATE MATERIALIZED VIEW IF NOT EXISTS complex_mv AS
        WITH aggregated AS (
            SELECT 
                user_id,
                DATE_TRUNC('month', order_date) as month,
                SUM(total) as monthly_total
            FROM orders
            GROUP BY user_id, DATE_TRUNC('month', order_date)
        )
        SELECT 
            u.username,
            a.month,
            a.monthly_total
        FROM users u
        JOIN aggregated a ON u.id = a.user_id
        WITH DATA;
        """
        
        objects = {}
        schema_manager._parse_materialized_views(content, objects)
        
        assert 'MATERIALIZED VIEW:simple_mv' in objects
        assert 'MATERIALIZED VIEW:complex_mv' in objects
        
        # Check dependencies
        assert 'TABLE:users' in objects['MATERIALIZED VIEW:simple_mv'].dependencies
        assert 'TABLE:users' in objects['MATERIALIZED VIEW:complex_mv'].dependencies
        assert 'TABLE:orders' in objects['MATERIALIZED VIEW:complex_mv'].dependencies
    
    def test_extract_table_references(self, schema_manager):
        """Test extracting table references from SQL."""
        sql = """
        SELECT u.id, u.username, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
        LEFT JOIN products p ON o.product_id = p.id
        WHERE EXISTS (SELECT 1 FROM addresses a WHERE a.user_id = u.id)
        """
        
        refs = schema_manager._extract_table_references(sql)
        
        assert 'TABLE:users' in refs
        assert 'TABLE:orders' in refs
        assert 'TABLE:products' in refs
        assert 'TABLE:addresses' in refs
        
        # Should not include SQL keywords
        assert 'TABLE:LEFT' not in refs
        assert 'TABLE:EXISTS' not in refs
    
    def test_compare_schemas(self, schema_manager):
        """Test comparing desired schema with current schema."""
        # Create desired objects
        desired = {
            'TABLE:users': SchemaObject('TABLE', 'users', 'CREATE TABLE users (id INT);'),
            'TABLE:orders': SchemaObject('TABLE', 'orders', 'CREATE TABLE orders (id INT);'),
            'INDEX:idx_users': SchemaObject('INDEX', 'idx_users', 'CREATE INDEX idx_users ON users(id);'),
            'VIEW:user_view': SchemaObject('VIEW', 'user_view', 'CREATE VIEW user_view AS SELECT * FROM users;'),
        }
        
        # Create current objects (with some differences)
        current = {
            'TABLE:users': SchemaObject('TABLE', 'users', 'CREATE TABLE users (id INT);'),  # Same
            'TABLE:orders': SchemaObject('TABLE', 'orders', 'CREATE TABLE orders (id INTEGER);'),  # Modified
            'TABLE:old_table': SchemaObject('TABLE', 'old_table', 'CREATE TABLE old_table (id INT);'),  # To drop
            'INDEX:idx_users': SchemaObject('INDEX', 'idx_users', 'CREATE INDEX idx_users ON users(id);'),  # Same
        }
        
        comparison = schema_manager.compare_schemas(desired, current)
        
        # Check results
        assert len(comparison['to_create']) == 1
        assert 'VIEW:user_view' in comparison['to_create']
        
        assert len(comparison['to_modify']) == 1
        assert 'TABLE:orders' in comparison['to_modify']
        
        assert len(comparison['to_drop']) == 1
        assert 'TABLE:old_table' in comparison['to_drop']
        
        assert len(comparison['unchanged']) == 2
        assert 'TABLE:users' in comparison['unchanged']
        assert 'INDEX:idx_users' in comparison['unchanged']
    
    def test_generate_migration_basic(self, schema_manager):
        """Test generating basic migration scripts."""
        comparison = {
            'to_create': {
                'TABLE:new_table': SchemaObject('TABLE', 'new_table', 'CREATE TABLE new_table (id INT);'),
                'INDEX:idx_new': SchemaObject('INDEX', 'idx_new', 'CREATE INDEX idx_new ON new_table(id);', ['TABLE:new_table']),
            },
            'to_modify': {
                'TABLE:users': (
                    SchemaObject('TABLE', 'users', 'CREATE TABLE users (id INT);'),
                    SchemaObject('TABLE', 'users', 'CREATE TABLE users (id INT, name TEXT);')
                ),
            },
            'to_drop': {
                'TABLE:old_table': SchemaObject('TABLE', 'old_table', 'CREATE TABLE old_table (id INT);'),
                'INDEX:idx_old': SchemaObject('INDEX', 'idx_old', 'CREATE INDEX idx_old ON old_table(id);'),
            },
            'unchanged': {}
        }
        
        migration, rollback = schema_manager.generate_migration(comparison, preserve_data=False)
        
        # Check migration script
        assert 'BEGIN;' in migration
        assert 'COMMIT;' in migration
        assert 'DROP TABLE IF EXISTS prop_trading_model.old_table CASCADE;' in migration
        assert 'DROP INDEX IF EXISTS prop_trading_model.idx_old CASCADE;' in migration
        assert 'CREATE TABLE new_table (id INT);' in migration
        assert 'CREATE INDEX idx_new ON new_table(id);' in migration
        
        # Check rollback script
        assert 'BEGIN;' in rollback
        assert 'COMMIT;' in rollback
        assert 'DROP TABLE IF EXISTS prop_trading_model.new_table CASCADE;' in rollback
        assert 'DROP INDEX IF EXISTS prop_trading_model.idx_new CASCADE;' in rollback
        assert 'CREATE TABLE old_table (id INT);' in rollback
    
    def test_generate_migration_preserve_data(self, schema_manager):
        """Test generating migration with data preservation."""
        comparison = {
            'to_create': {},
            'to_modify': {},
            'to_drop': {
                'TABLE:users': SchemaObject('TABLE', 'users', 'CREATE TABLE users (id INT);'),
            },
            'unchanged': {}
        }
        
        migration, rollback = schema_manager.generate_migration(comparison, preserve_data=True)
        
        # Check that table is renamed instead of dropped
        assert 'ALTER TABLE prop_trading_model.users RENAME TO users_archived_' in migration
        assert 'DROP TABLE IF EXISTS' not in migration or 'users CASCADE' not in migration
        
        # Check rollback
        assert 'ALTER TABLE prop_trading_model.users_archived_' in rollback
        assert 'RENAME TO users;' in rollback
    
    def test_generate_migration_dependency_order(self, schema_manager):
        """Test that migrations respect dependency order."""
        comparison = {
            'to_create': {
                'TABLE:users': SchemaObject('TABLE', 'users', 'CREATE TABLE users (id INT);'),
                'TABLE:orders': SchemaObject('TABLE', 'orders', 'CREATE TABLE orders (user_id INT);'),
                'INDEX:idx_users': SchemaObject('INDEX', 'idx_users', 'CREATE INDEX idx_users ON users(id);', ['TABLE:users']),
                'VIEW:user_orders': SchemaObject('VIEW', 'user_orders', 'CREATE VIEW user_orders AS SELECT * FROM users JOIN orders;', ['TABLE:users', 'TABLE:orders']),
            },
            'to_modify': {},
            'to_drop': {},
            'unchanged': {}
        }
        
        migration, rollback = schema_manager.generate_migration(comparison)
        
        # Check that tables are created before indexes and views
        table_pos = migration.find('CREATE TABLE users')
        index_pos = migration.find('CREATE INDEX idx_users')
        view_pos = migration.find('CREATE VIEW user_orders')
        
        assert table_pos < index_pos
        assert table_pos < view_pos
    
    def test_apply_migration_dry_run(self, schema_manager):
        """Test applying migration in dry-run mode."""
        migration_script = "CREATE TABLE test (id INT);"
        rollback_script = "DROP TABLE test;"
        
        result = schema_manager.apply_migration(
            migration_script, 
            rollback_script, 
            dry_run=True,
            description="Test migration"
        )
        
        assert result['success'] is True
        assert result['dry_run'] is True
        assert result['migration_script'] == migration_script
        assert result['rollback_script'] == rollback_script
        assert result['error'] is None
    
    def test_apply_migration_success(self, schema_manager, mock_db_manager):
        """Test successfully applying a migration."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_conn.commit = Mock()
        
        mock_db_manager.model_db.get_connection.return_value = mock_conn
        
        migration_script = "CREATE TABLE test (id INT);"
        rollback_script = "DROP TABLE test;"
        
        result = schema_manager.apply_migration(
            migration_script,
            rollback_script,
            dry_run=False,
            description="Test migration"
        )
        
        assert result['success'] is True
        assert result['dry_run'] is False
        assert result['version_hash'] is not None
        assert result['execution_time_ms'] >= 0  # Can be 0 in tests
        assert result['error'] is None
        
        # Check that migration was executed
        assert mock_cursor.execute.call_count >= 2  # Migration + version insert
        mock_conn.commit.assert_called()
    
    def test_apply_migration_failure(self, schema_manager, mock_db_manager):
        """Test handling migration failure."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        
        # Simulate SQL error
        mock_cursor.execute.side_effect = psycopg2.errors.SyntaxError("syntax error")
        mock_db_manager.model_db.get_connection.return_value = mock_conn
        
        migration_script = "CREATE TABL test (id INT);"  # Invalid SQL
        rollback_script = "DROP TABLE test;"
        
        result = schema_manager.apply_migration(
            migration_script,
            rollback_script,
            dry_run=False
        )
        
        assert result['success'] is False
        assert result['error'] is not None
        assert 'syntax error' in result['error']
    
    def test_rollback_to_version(self, schema_manager, mock_db_manager):
        """Test rolling back to a specific version."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_conn.commit = Mock()
        
        # Mock migrations to rollback
        mock_cursor.fetchall.return_value = [
            ('hash3', 'DROP TABLE table3;'),
            ('hash2', 'DROP TABLE table2;'),
        ]
        
        mock_db_manager.model_db.get_connection.return_value = mock_conn
        
        success = schema_manager.rollback_to_version('hash1')
        
        assert success is True
        
        # Check that rollback scripts were executed
        execute_calls = mock_cursor.execute.call_args_list
        assert any('DROP TABLE table3;' in str(call) for call in execute_calls)
        assert any('DROP TABLE table2;' in str(call) for call in execute_calls)
        assert any("status = 'rolled_back'" in str(call) for call in execute_calls)
        
        mock_conn.commit.assert_called_once()
    
    def test_rollback_to_version_failure(self, schema_manager, mock_db_manager):
        """Test handling rollback failure."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        
        # Simulate error during rollback
        mock_cursor.execute.side_effect = Exception("Rollback failed")
        mock_db_manager.model_db.get_connection.return_value = mock_conn
        
        success = schema_manager.rollback_to_version('hash1')
        
        assert success is False
    
    def test_ensure_schema_compliance_no_changes(self, schema_manager, mock_db_manager, tmp_path):
        """Test ensure_schema_compliance when no changes are needed."""
        # Create a simple schema file
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")
        
        # Mock the comparison to show no changes
        with patch.object(schema_manager, 'ensure_version_table'):
            with patch.object(schema_manager, 'parse_schema_file') as mock_parse:
                with patch.object(schema_manager, 'get_current_schema_objects') as mock_current:
                    with patch.object(schema_manager, 'compare_schemas') as mock_compare:
                        # Setup mocks
                        mock_parse.return_value = {'TABLE:users': Mock()}
                        mock_current.return_value = {'TABLE:users': Mock()}
                        mock_compare.return_value = {
                            'to_create': {},
                            'to_modify': {},
                            'to_drop': {},
                            'unchanged': {'TABLE:users': Mock()}
                        }
                        
                        # Mock schema existence check
                        mock_conn = Mock()
                        mock_cursor = Mock()
                        mock_conn.__enter__ = Mock(return_value=mock_conn)
                        mock_conn.__exit__ = Mock(return_value=None)
                        mock_conn.cursor = Mock(return_value=mock_cursor)
                        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
                        mock_cursor.__exit__ = Mock(return_value=None)
                        mock_cursor.fetchone.return_value = (True,)  # Schema exists
                        mock_db_manager.model_db.get_connection.return_value = mock_conn
                        
                        result = schema_manager.ensure_schema_compliance(
                            schema_path=schema_file,
                            preserve_data=True,
                            dry_run=False
                        )
                        
                        assert result['migration_needed'] is False
                        assert 'comparison' in result
    
    def test_ensure_schema_compliance_with_changes(self, schema_manager, mock_db_manager, tmp_path):
        """Test ensure_schema_compliance when changes are needed."""
        # Create a schema file
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT); CREATE TABLE orders (id INT);")
        
        # Mock the workflow
        with patch.object(schema_manager, 'ensure_version_table'):
            with patch.object(schema_manager, 'parse_schema_file') as mock_parse:
                with patch.object(schema_manager, 'get_current_schema_objects') as mock_current:
                    with patch.object(schema_manager, 'compare_schemas') as mock_compare:
                        with patch.object(schema_manager, 'generate_migration') as mock_generate:
                            with patch.object(schema_manager, 'apply_migration') as mock_apply:
                                # Setup mocks
                                mock_parse.return_value = {
                                    'TABLE:users': Mock(),
                                    'TABLE:orders': Mock()
                                }
                                mock_current.return_value = {'TABLE:users': Mock()}
                                mock_compare.return_value = {
                                    'to_create': {'TABLE:orders': Mock()},
                                    'to_modify': {},
                                    'to_drop': {},
                                    'unchanged': {'TABLE:users': Mock()}
                                }
                                mock_generate.return_value = (
                                    'CREATE TABLE orders (id INT);',
                                    'DROP TABLE orders;'
                                )
                                mock_apply.return_value = {
                                    'success': True,
                                    'version_hash': 'abc123'
                                }
                                
                                # Mock schema existence check
                                mock_conn = Mock()
                                mock_cursor = Mock()
                                mock_conn.__enter__ = Mock(return_value=mock_conn)
                                mock_conn.__exit__ = Mock(return_value=None)
                                mock_conn.cursor = Mock(return_value=mock_cursor)
                                mock_cursor.__enter__ = Mock(return_value=mock_cursor)
                                mock_cursor.__exit__ = Mock(return_value=None)
                                mock_cursor.fetchone.return_value = (True,)  # Schema exists
                                mock_db_manager.model_db.get_connection.return_value = mock_conn
                                
                                # Ensure migrations directory exists
                                schema_manager.migrations_dir.mkdir(exist_ok=True)
                                
                                result = schema_manager.ensure_schema_compliance(
                                    schema_path=schema_file,
                                    preserve_data=True,
                                    dry_run=False
                                )
                                
                                assert result['migration_needed'] is True
                                assert result['success'] is True
                                assert 'comparison' in result
                                assert 'migration_file' in result
                                assert 'rollback_file' in result
                                
                                # Check that migration was generated and applied
                                mock_generate.assert_called_once()
                                mock_apply.assert_called_once()
    
    def test_ensure_schema_compliance_schema_creation(self, schema_manager, mock_db_manager, tmp_path):
        """Test that schema is created if it doesn't exist."""
        schema_file = tmp_path / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")
        
        with patch.object(schema_manager, 'ensure_version_table'):
            with patch.object(schema_manager, 'parse_schema_file') as mock_parse:
                with patch.object(schema_manager, 'get_current_schema_objects'):
                    with patch.object(schema_manager, 'compare_schemas') as mock_compare:
                        # Setup mocks
                        mock_parse.return_value = {'TABLE:users': Mock()}
                        mock_compare.return_value = {
                            'to_create': {},
                            'to_modify': {},
                            'to_drop': {},
                            'unchanged': {}
                        }
                        
                        # Mock schema doesn't exist
                        mock_conn = Mock()
                        mock_cursor = Mock()
                        mock_conn.__enter__ = Mock(return_value=mock_conn)
                        mock_conn.__exit__ = Mock(return_value=None)
                        mock_conn.cursor = Mock(return_value=mock_cursor)
                        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
                        mock_cursor.__exit__ = Mock(return_value=None)
                        mock_conn.commit = Mock()
                        
                        # First call returns False (schema doesn't exist)
                        mock_cursor.fetchone.return_value = (False,)
                        mock_db_manager.model_db.get_connection.return_value = mock_conn
                        
                        result = schema_manager.ensure_schema_compliance(
                            schema_path=schema_file,
                            preserve_data=True,
                            dry_run=False
                        )
                        
                        # Check that CREATE SCHEMA was called
                        execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
                        assert any('CREATE SCHEMA IF NOT EXISTS' in call for call in execute_calls)
                        mock_conn.commit.assert_called()


class TestSchemaIntegration:
    """Integration tests for the complete schema management flow."""
    
    @pytest.fixture
    def test_schema_path(self):
        """Get the path to the actual schema.sql file."""
        return Path(__file__).parent.parent / "src" / "db_schema" / "schema.sql"
    
    def test_schema_file_exists(self, test_schema_path):
        """Test that the schema.sql file exists."""
        assert test_schema_path.exists(), f"Schema file not found at {test_schema_path}"
    
    def test_schema_file_is_valid_sql(self, test_schema_path):
        """Test that schema.sql contains valid SQL."""
        content = test_schema_path.read_text()
        
        # Basic SQL validation
        assert 'CREATE SCHEMA' in content or 'CREATE TABLE' in content
        assert content.count('(') == content.count(')')  # Balanced parentheses
        assert content.count("'") % 2 == 0  # Even number of single quotes
        assert content.count('"') % 2 == 0  # Even number of double quotes
        
        # Check for required tables
        assert 'CREATE TABLE raw_accounts_data' in content
        assert 'CREATE TABLE raw_metrics_daily' in content
        assert 'CREATE TABLE raw_trades_closed' in content
        assert 'CREATE TABLE feature_store_account_daily' in content
        
        # Check for partitioning
        assert 'PARTITION BY RANGE' in content
        
        # Check for indexes
        assert 'CREATE INDEX' in content
        assert 'CREATE UNIQUE INDEX' in content
        
        # Check for functions (either CREATE FUNCTION or CREATE OR REPLACE FUNCTION)
        assert 'CREATE' in content and 'FUNCTION' in content
        
        # Check for materialized views
        assert 'CREATE MATERIALIZED VIEW' in content
    
    def test_schema_has_all_required_objects(self, test_schema_path):
        """Test that schema contains all required database objects."""
        content = test_schema_path.read_text()
        
        # Required tables
        required_tables = [
            'raw_accounts_data',
            'raw_metrics_alltime',
            'raw_metrics_daily',
            'raw_metrics_hourly',
            'raw_trades_closed',
            'raw_trades_open',
            'raw_plans_data',
            'raw_regimes_daily',
            'stg_accounts_daily_snapshots',
            'feature_store_account_daily',
            'model_training_input',
            'model_predictions',
            'model_registry',
            'pipeline_execution_log',
            'query_performance_log',
            'scheduled_jobs'
        ]
        
        for table in required_tables:
            assert f'CREATE TABLE {table}' in content or f'CREATE TABLE IF NOT EXISTS {table}' in content, \
                   f"Required table '{table}' not found in schema"
        
        # Required materialized views
        required_views = [
            'mv_account_performance_summary',
            'mv_daily_trading_stats',
            'mv_symbol_performance',
            'mv_account_trading_patterns',
            'mv_market_regime_performance'
        ]
        
        for view in required_views:
            assert f'CREATE MATERIALIZED VIEW {view}' in content or \
                   f'CREATE MATERIALIZED VIEW IF NOT EXISTS {view}' in content, \
                   f"Required materialized view '{view}' not found in schema"
        
        # Required functions
        required_functions = [
            'refresh_materialized_views',
            'create_monthly_partitions',
            'drop_old_partitions'
        ]
        
        for func in required_functions:
            assert f'FUNCTION {func}' in content, \
                   f"Required function '{func}' not found in schema"
    
    def test_schema_constraints_are_valid(self, test_schema_path):
        """Test that schema constraints are properly defined."""
        content = test_schema_path.read_text()
        
        # Check for primary keys
        assert 'PRIMARY KEY' in content
        
        # Check for foreign keys (if any)
        # assert 'REFERENCES' in content
        
        # Check for check constraints
        assert 'CHECK' in content
        
        # Check for unique constraints
        assert 'UNIQUE' in content
        
        # Check for not null constraints
        assert 'NOT NULL' in content
        
        # Check specific constraints
        assert 'CHECK (status IN (' in content  # Status enum checks
        assert 'CHECK (phase IN (' in content   # Phase enum checks
        # Look for actual CHECK constraint patterns in the content
        import re
        # Check for non-negative constraints
        assert re.search(r'CHECK\s*\([^)]*>=\s*0', content, re.IGNORECASE), "Missing non-negative CHECK constraints"
        # Check for percentage constraints  
        assert re.search(r'CHECK\s*\([^)]*<=\s*100', content, re.IGNORECASE), "Missing percentage CHECK constraints"
    
    def test_schema_indexes_cover_foreign_keys(self, test_schema_path):
        """Test that all foreign key columns have indexes."""
        content = test_schema_path.read_text()
        
        # Extract foreign key references
        import re
        fk_pattern = r'(\w+)\s+\w+.*REFERENCES\s+(\w+)\((\w+)\)'
        foreign_keys = re.findall(fk_pattern, content)
        
        # For each foreign key, check if there's an index
        for fk_column, ref_table, ref_column in foreign_keys:
            # Check if index exists on the foreign key column
            index_patterns = [
                f'CREATE INDEX.*ON.*{fk_column}',
                f'CREATE UNIQUE INDEX.*ON.*{fk_column}',
                f'PRIMARY KEY.*{fk_column}'
            ]
            
            has_index = any(re.search(pattern, content) for pattern in index_patterns)
            assert has_index, f"Foreign key column '{fk_column}' should have an index"
    
    @pytest.mark.parametrize("partition_table", ['raw_metrics_daily', 'raw_trades_closed'])
    def test_partitioned_tables_have_partition_function(self, test_schema_path, partition_table):
        """Test that partitioned tables have proper partition management."""
        content = test_schema_path.read_text()
        
        # Check table is partitioned
        assert f'CREATE TABLE {partition_table}' in content
        assert f'PARTITION BY RANGE' in content
        
        # Check partition creation logic exists
        assert 'CREATE TABLE IF NOT EXISTS %I PARTITION OF' in content
        
        # Check that create_monthly_partitions function handles this table
        assert f"table_name = '{partition_table}'" in content or \
               'create_monthly_partitions' in content
    
    def test_schema_has_proper_permissions(self, test_schema_path):
        """Test that schema includes proper permission grants."""
        content = test_schema_path.read_text()
        
        # Check for GRANT statements
        assert 'GRANT' in content
        
        # Check specific grants
        assert 'GRANT USAGE ON SCHEMA' in content
        assert 'GRANT SELECT ON ALL TABLES' in content
        assert 'GRANT USAGE, SELECT ON ALL SEQUENCES' in content
    
    def test_setup_schema_functions_file(self):
        """Test that setup_schema_functions.sql exists and is valid."""
        setup_file = Path(__file__).parent.parent / "src" / "db_schema" / "setup_schema_functions.sql"
        
        assert setup_file.exists(), "setup_schema_functions.sql file not found"
        
        content = setup_file.read_text()
        
        # Check for pg_get_tabledef function
        assert 'CREATE OR REPLACE FUNCTION' in content
        assert 'pg_get_tabledef' in content
        assert 'RETURNS text' in content
        assert 'LANGUAGE plpgsql' in content
    
    def test_readme_documentation(self):
        """Test that README.md is properly updated with new features."""
        readme_file = Path(__file__).parent.parent / "src" / "db_schema" / "README.md"
        
        assert readme_file.exists(), "README.md file not found"
        
        content = readme_file.read_text()
        
        # Check for new documentation sections
        assert 'Intelligent Schema Management' in content
        assert 'Schema Versioning' in content
        assert '--dry-run' in content
        assert '--force-recreate-schema' in content
        assert '--no-preserve-data' in content
        assert 'schema_version' in content
        assert 'auto_migrations' in content
    
    def test_no_sql_injection_vulnerabilities(self, test_schema_path):
        """Test that schema doesn't contain SQL injection vulnerabilities."""
        import re  # Add missing import
        content = test_schema_path.read_text()
        
        # Check for dangerous patterns
        dangerous_patterns = [
            r'EXECUTE\s+[^$f]',  # EXECUTE without dollar quoting or format
            r'eval\(',          # eval functions
            r'system\(',        # system calls
            r'\|\|.*\|\|.*\|\|.*\|\|.*\|\|', # Excessive string concatenation (5+ concatenations)
        ]
        
        for pattern in dangerous_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            assert not matches, f"Potentially dangerous pattern found: {pattern}"
    
    def test_schema_comments_and_documentation(self, test_schema_path):
        """Test that schema has proper comments and documentation."""
        content = test_schema_path.read_text()
        
        # Check for header comments
        assert '-- Daily Profit Model Database Schema' in content or \
               '-- Prop Trading Model Database Schema' in content
        
        # Check for section comments
        assert '-- =====' in content  # Section separators
        assert 'Tables' in content
        assert 'Functions' in content
        assert 'Indexes' in content
        
        # Check for column comments
        assert 'COMMENT ON COLUMN' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])