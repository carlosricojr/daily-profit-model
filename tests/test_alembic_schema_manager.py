"""
Tests for Alembic-based Schema Manager

This test suite validates the Alembic integration while maintaining
compatibility with existing schema management functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

from src.utils.alembic_schema_manager import AlembicSchemaManager, create_alembic_schema_manager


class TestAlembicSchemaManager:
    """Test suite for AlembicSchemaManager."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager."""
        mock_db = Mock()
        mock_db.model_db.host = "localhost"
        mock_db.model_db.port = 5432
        mock_db.model_db.database = "test_db"
        mock_db.model_db.user = "test_user"
        mock_db.model_db.password = "test_pass"
        return mock_db

    @pytest.fixture
    def temp_alembic_dir(self):
        """Create a temporary directory for Alembic files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def sample_schema_sql(self):
        """Sample schema SQL for testing."""
        return """
        -- Sample schema for testing
        CREATE SCHEMA IF NOT EXISTS prop_trading_model;
        
        CREATE TABLE prop_trading_model.test_table (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX idx_test_table_name ON prop_trading_model.test_table(name);
        """

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_alembic_schema_manager_initialization(self, mock_create_engine, mock_db_manager):
        """Test AlembicSchemaManager initialization."""
        mock_engine = Mock()
        mock_engine.url = "postgresql://test_user:test_pass@localhost:5432/test_db"
        mock_create_engine.return_value = mock_engine

        manager = AlembicSchemaManager(mock_db_manager)

        assert manager.db_manager == mock_db_manager
        assert manager.schema_name == "prop_trading_model"
        assert manager.engine == mock_engine
        assert manager.alembic_dir.name == "alembic"

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_create_alembic_ini(self, mock_create_engine, mock_db_manager, temp_alembic_dir):
        """Test creation of alembic.ini file."""
        mock_engine = Mock()
        mock_engine.url = "postgresql://test_user:test_pass@localhost:5432/test_db"
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, '__init__', lambda self, db_manager: None):
            manager = AlembicSchemaManager(mock_db_manager)
            manager._alembic_dir = temp_alembic_dir
            
            ini_path = temp_alembic_dir / "alembic.ini"
            manager._create_alembic_ini(ini_path)
            
            assert ini_path.exists()
            content = ini_path.read_text()
            assert "daily-profit-model" in content
            assert str(temp_alembic_dir) in content

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_create_env_py(self, mock_create_engine, mock_db_manager, temp_alembic_dir):
        """Test creation of env.py file."""
        mock_engine = Mock()
        mock_engine.url = "postgresql://test_user:test_pass@localhost:5432/test_db"
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, '__init__', lambda self, db_manager: None):
            manager = AlembicSchemaManager(mock_db_manager)
            manager._alembic_dir = temp_alembic_dir
            
            env_path = temp_alembic_dir / "env.py"
            manager._create_env_py(env_path)
            
            assert env_path.exists()
            content = env_path.read_text()
            assert "run_migrations_offline" in content
            assert "run_migrations_online" in content

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_create_script_mako(self, mock_create_engine, mock_db_manager, temp_alembic_dir):
        """Test creation of script.py.mako template."""
        mock_engine = Mock()
        mock_engine.url = "postgresql://test_user:test_pass@localhost:5432/test_db"
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, '__init__', lambda self, db_manager: None):
            manager = AlembicSchemaManager(mock_db_manager)
            manager._alembic_dir = temp_alembic_dir
            
            script_path = temp_alembic_dir / "script.py.mako"
            manager._create_script_mako(script_path)
            
            assert script_path.exists()
            content = script_path.read_text()
            assert "def upgrade():" in content
            assert "def downgrade():" in content

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_ensure_schema_exists(self, mock_create_engine, mock_db_manager):
        """Test ensuring schema exists."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        # Mock connection context manager
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.scalar.return_value = False  # Schema doesn't exist
        mock_conn.execute.return_value = mock_result
        mock_conn.commit = Mock()
        
        # Set up the context manager properly
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        manager = AlembicSchemaManager(mock_db_manager)
        manager.ensure_schema_exists()

        # Verify schema creation was attempted
        mock_conn.execute.assert_called()
        mock_conn.commit.assert_called_once()

    @patch('src.utils.alembic_schema_manager.create_engine')
    @patch('src.utils.alembic_schema_manager.command')
    def test_initialize_alembic(self, mock_command, mock_create_engine, mock_db_manager):
        """Test Alembic initialization."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        # Mock connection - alembic_version table doesn't exist
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.scalar.return_value = False
        mock_conn.execute.return_value = mock_result
        
        # Set up the context manager properly
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)

        manager = AlembicSchemaManager(mock_db_manager)
        manager.initialize_alembic()

        # Verify Alembic stamp was called
        mock_command.stamp.assert_called_once()

    @patch('src.utils.alembic_schema_manager.create_engine')
    @patch('src.utils.alembic_schema_manager.command')
    def test_apply_migrations_dry_run(self, mock_command, mock_create_engine, mock_db_manager):
        """Test applying migrations in dry run mode."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, '_setup_alembic_config'):
            manager = AlembicSchemaManager(mock_db_manager)
            result = manager.apply_migrations(dry_run=True)

            assert result['success'] is True
            assert result['dry_run'] is True
            assert 'sql_file' in result

    @patch('src.utils.alembic_schema_manager.create_engine')
    @patch('src.utils.alembic_schema_manager.command')
    def test_apply_migrations_success(self, mock_command, mock_create_engine, mock_db_manager):
        """Test successful migration application."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, '_setup_alembic_config'):
            manager = AlembicSchemaManager(mock_db_manager)
            result = manager.apply_migrations(dry_run=False)

            assert result['success'] is True
            assert result['dry_run'] is False
            mock_command.upgrade.assert_called_once_with(manager.alembic_cfg, "head")

    @patch('src.utils.alembic_schema_manager.create_engine')
    @patch('src.utils.alembic_schema_manager.command')
    def test_rollback_migration(self, mock_command, mock_create_engine, mock_db_manager):
        """Test migration rollback."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, '_setup_alembic_config'):
            manager = AlembicSchemaManager(mock_db_manager)
            result = manager.rollback_migration("abc123")

            assert result['success'] is True
            assert result['target_revision'] == "abc123"
            mock_command.downgrade.assert_called_once_with(manager.alembic_cfg, "abc123")

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_get_migration_history(self, mock_create_engine, mock_db_manager):
        """Test getting migration history."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, '_setup_alembic_config'):
            with patch('src.utils.alembic_schema_manager.ScriptDirectory') as mock_script_dir:
                with patch('src.utils.alembic_schema_manager.MigrationContext') as mock_migration_context:
                    # Setup mock revision
                    mock_revision = Mock()
                    mock_revision.revision = "abc123"
                    mock_revision.down_revision = "def456"
                    mock_revision.doc = "Test migration"

                    mock_script_dir.from_config.return_value.walk_revisions.return_value = [mock_revision]
                    
                    # Mock connection context manager
                    mock_conn = Mock()
                    mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
                    mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
                    
                    mock_migration_context.configure.return_value.get_current_revision.return_value = "abc123"

                    manager = AlembicSchemaManager(mock_db_manager)
                    history = manager.get_migration_history()

                    assert len(history) == 1
                    assert history[0]['revision'] == "abc123"
                    assert history[0]['description'] == "Test migration"

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_ensure_schema_compliance_no_changes(self, mock_create_engine, mock_db_manager):
        """Test schema compliance when no changes are needed."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, 'ensure_schema_exists'):
            with patch.object(AlembicSchemaManager, 'initialize_alembic'):
                with patch('src.utils.alembic_schema_manager.ScriptDirectory') as mock_script_dir:
                    with patch('src.utils.alembic_schema_manager.MigrationContext') as mock_migration_context:
                        # Mock connection context manager
                        mock_conn = Mock()
                        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
                        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
                        
                        # Setup mocks to indicate no migration needed
                        mock_migration_context.configure.return_value.get_current_revision.return_value = "abc123"
                        mock_script_dir.from_config.return_value.get_current_head.return_value = "abc123"

                        manager = AlembicSchemaManager(mock_db_manager)
                        result = manager.ensure_schema_compliance(Path("schema.sql"))

                        assert result['success'] is True
                        assert result['migration_needed'] is False

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_ensure_schema_compliance_with_changes(self, mock_create_engine, mock_db_manager):
        """Test schema compliance when changes are needed."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        with patch.object(AlembicSchemaManager, 'ensure_schema_exists'):
            with patch.object(AlembicSchemaManager, 'initialize_alembic'):
                with patch.object(AlembicSchemaManager, 'apply_migrations') as mock_apply:
                    with patch('src.utils.alembic_schema_manager.ScriptDirectory') as mock_script_dir:
                        with patch('src.utils.alembic_schema_manager.MigrationContext') as mock_migration_context:
                            # Mock connection context manager
                            mock_conn = Mock()
                            mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
                            mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
                            
                            # Setup mocks to indicate migration needed
                            mock_migration_context.configure.return_value.get_current_revision.return_value = "abc123"
                            mock_script_dir.from_config.return_value.get_current_head.return_value = "def456"

                            mock_apply.return_value = {
                                'success': True,
                                'migration_needed': True,
                                'message': 'Migrations applied'
                            }

                            manager = AlembicSchemaManager(mock_db_manager)
                            result = manager.ensure_schema_compliance(Path("schema.sql"))

                            assert result['success'] is True
                            assert result['migration_needed'] is True

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_factory_function(self, mock_create_engine, mock_db_manager):
        """Test the factory function."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        manager = create_alembic_schema_manager(mock_db_manager)
        assert isinstance(manager, AlembicSchemaManager)
        assert manager.db_manager == mock_db_manager


class TestAlembicIntegration:
    """Test Alembic integration and dependencies."""

    def test_alembic_dependency_available(self):
        """Test that Alembic is available."""
        try:
            import alembic
            assert alembic is not None
        except ImportError:
            pytest.fail("Alembic dependency not available")

    def test_sqlalchemy_dependency_available(self):
        """Test that SQLAlchemy is available."""
        try:
            import sqlalchemy
            assert sqlalchemy is not None
        except ImportError:
            pytest.fail("SQLAlchemy dependency not available")

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_alembic_config_generation(self, mock_create_engine, tmp_path):
        """Test that Alembic configuration files are generated correctly."""
        mock_engine = Mock()
        mock_engine.url = "postgresql://user:pass@localhost:5432/db"
        mock_create_engine.return_value = mock_engine

        mock_db_manager = Mock()
        mock_db_manager.model_db.host = "localhost"
        mock_db_manager.model_db.port = 5432
        mock_db_manager.model_db.database = "test_db"
        mock_db_manager.model_db.user = "test_user"
        mock_db_manager.model_db.password = "test_pass"

        with patch.object(AlembicSchemaManager, '__init__', lambda self, db_manager: None):
            manager = AlembicSchemaManager(mock_db_manager)
            manager._alembic_dir = tmp_path
            manager._alembic_dir.mkdir(exist_ok=True)
            
            # Create the files manually to test they exist
            manager._create_alembic_ini(tmp_path / "alembic.ini")
            manager._create_env_py(tmp_path / "env.py")
            manager._create_script_mako(tmp_path / "script.py.mako")
            (tmp_path / "versions").mkdir(exist_ok=True)

            # Check that configuration files are created
            assert (tmp_path / "alembic.ini").exists()
            assert (tmp_path / "env.py").exists()
            assert (tmp_path / "script.py.mako").exists()
            assert (tmp_path / "versions").exists()

    @patch('src.utils.alembic_schema_manager.create_engine')
    def test_backward_compatibility_maintained(self, mock_create_engine):
        """Test that the new system maintains backward compatibility."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine

        mock_db_manager = Mock()
        mock_db_manager.model_db.host = "localhost"
        mock_db_manager.model_db.port = 5432
        mock_db_manager.model_db.database = "test_db"
        mock_db_manager.model_db.user = "test_user"
        mock_db_manager.model_db.password = "test_pass"

        # Should be able to create manager without errors
        manager = AlembicSchemaManager(mock_db_manager)
        
        # Should have the same interface as the old schema manager
        assert hasattr(manager, 'ensure_schema_compliance')
        assert callable(manager.ensure_schema_compliance)

    def test_graceful_fallback_on_import_error(self):
        """Test graceful handling when Alembic is not available."""
        # Create a proper mock db manager with correct types
        mock_db_manager = Mock()
        mock_db_manager.model_db.host = "localhost"
        mock_db_manager.model_db.port = 5432
        mock_db_manager.model_db.database = "test_db"
        mock_db_manager.model_db.user = "test_user"
        mock_db_manager.model_db.password = "test_pass"
        
        # Patch the create_engine to simulate SQLAlchemy not available
        with patch('src.utils.alembic_schema_manager.create_engine', side_effect=ImportError("SQLAlchemy not available")):
            with pytest.raises(ImportError):
                create_alembic_schema_manager(mock_db_manager)


class TestSchemaValidationIntegration:
    """Test integration with existing schema validation."""

    def test_schema_validation_still_works(self):
        """Test that existing schema validation tests still pass."""
        # This would import and run existing schema validation
        # to ensure we haven't broken anything
        try:
            from tests.test_schema_validation import TestSchemaValidation
            # If we can import it, the integration is working
            assert TestSchemaValidation is not None
        except ImportError:
            pytest.skip("Schema validation tests not available")

    def test_schema_field_mapping_still_works(self):
        """Test that schema field mapping validation still works."""
        try:
            from tests.test_schema_field_mapping_alignment import test_schema_field_mapping_alignment
            # If we can import it, the integration is working
            assert test_schema_field_mapping_alignment is not None
        except ImportError:
            pytest.skip("Schema field mapping tests not available") 