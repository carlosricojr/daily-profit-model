"""
Test backward compatibility for deprecated metrics ingester.
The original metrics ingester is deprecated in favor of ingest_metrics_v2.py
which provides comprehensive risk metrics support.
"""

import pytest
import warnings
from unittest.mock import patch


class TestDeprecatedMetricsIngester:
    """Test backward compatibility and deprecation warnings."""

    def test_deprecation_warning_on_import(self):
        """Test that importing the old module issues a deprecation warning."""
        with pytest.warns(DeprecationWarning, match="ingest_metrics.py is deprecated"):
            from src.data_ingestion.ingest_metrics import MetricsIngester

    def test_backward_compatibility_class_alias(self):
        """Test that the old class name works as an alias."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.data_ingestion.ingest_metrics import MetricsIngester
            from src.data_ingestion.ingest_metrics_v2 import MetricsIngesterV2
            
            # Should be the same class (alias)
            assert MetricsIngester is MetricsIngesterV2

    def test_backward_compatibility_enum(self):
        """Test that the MetricType enum is available."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.data_ingestion.ingest_metrics import MetricType
            from src.data_ingestion.ingest_metrics_v2 import MetricType as MetricTypeV2
            
            # Should be the same enum
            assert MetricType is MetricTypeV2

    @patch('src.data_ingestion.base_ingester.get_db_manager')
    @patch('src.utils.api_client.RiskAnalyticsAPIClient') 
    def test_instantiation_works_with_v2(self, mock_api_client, mock_db_manager):
        """Test that instantiating through the old module works."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.data_ingestion.ingest_metrics import MetricsIngester
            
            # Should be able to instantiate successfully
            ingester = MetricsIngester(
                checkpoint_dir="/tmp/test",
                enable_validation=True,
                enable_deduplication=True
            )
            
            # Should have v2 functionality
            assert hasattr(ingester, 'alltime_field_mapping')
            assert len(ingester.alltime_field_mapping) > 100  # Has comprehensive fields

    def test_main_function_deprecation_warning(self):
        """Test that the main function issues deprecation warning."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.data_ingestion.ingest_metrics import main
            
            # Should be a function that warns about deprecation
            assert callable(main)


class TestCheckpointManager:
    """Test checkpoint manager functionality (from base_ingester)."""
    
    def test_save_and_load_checkpoint(self):
        """Test basic checkpoint functionality."""
        import tempfile
        import os
        from src.data_ingestion.base_ingester import CheckpointManager
        
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_file = os.path.join(temp_dir, "test_checkpoint.json")
            manager = CheckpointManager(checkpoint_file, "test")
            
            # Save checkpoint
            data = {"key": "value", "number": 42}
            manager.save_checkpoint(data)
            
            # Load checkpoint
            loaded = manager.load_checkpoint()
            assert loaded == data

    def test_load_nonexistent_checkpoint(self):
        """Test loading non-existent checkpoint."""
        import tempfile
        import os
        from src.data_ingestion.base_ingester import CheckpointManager
        
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_file = os.path.join(temp_dir, "nonexistent.json")
            manager = CheckpointManager(checkpoint_file, "test")
            
            # Should return None for non-existent file
            assert manager.load_checkpoint() is None

    def test_clear_checkpoint(self):
        """Test clearing checkpoint."""
        import tempfile
        import os
        from src.data_ingestion.base_ingester import CheckpointManager
        
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_file = os.path.join(temp_dir, "test_checkpoint.json")
            manager = CheckpointManager(checkpoint_file, "test")
            
            # Save and clear
            manager.save_checkpoint({"key": "value"})
            assert os.path.exists(checkpoint_file)
            
            manager.clear_checkpoint()
            assert not os.path.exists(checkpoint_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])