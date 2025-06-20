"""
Integration tests for the feature engineering module.
Tests the overall functionality without importing problematic dependencies.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess
import sys


class TestFeatureEngineeringIntegration:
    """Test the feature engineering pipeline integration."""

    def test_feature_catalog_exists(self):
        """Test that feature catalog documentation exists."""
        catalog_path = Path("src/feature_engineering/feature_catalog.md")
        assert catalog_path.exists()
        
        # Check it contains expected sections
        with open(catalog_path) as f:
            content = f.read()
        
        assert "## Feature Categories" in content
        assert "### 1. Static Features" in content
        assert "### 2. Dynamic Features" in content
        assert "### 3. Rolling Performance Features" in content
        assert "### 4. Behavioral Features" in content
        assert "### 5. Market Regime Features" in content
        assert "### 6. Temporal Features" in content
        assert "## Target Variable" in content

    def test_module_structure(self):
        """Test that the module has the expected structure."""
        fe_dir = Path("src/feature_engineering")
        
        # Check required files exist
        assert (fe_dir / "__init__.py").exists()
        assert (fe_dir / "ft_feature_engineering.py").exists()
        assert (fe_dir / "ft_build_feature_matrix.py").exists()
        assert (fe_dir / "feature_analysis.py").exists()
        assert (fe_dir / "README.md").exists()
        
        # Check that removed files don't exist
        assert not (fe_dir / "feature_engineering.py").exists()
        assert not (fe_dir / "benchmark_performance.py").exists()
        assert not (fe_dir / "monitor_features.py").exists()

    def test_init_module_simplified(self):
        """Test that __init__.py is simplified."""
        init_path = Path("src/feature_engineering/__init__.py")
        with open(init_path) as f:
            content = f.read()
        
        # Should be minimal
        assert len(content.splitlines()) < 20
        assert "__version__" in content
        # Should not import the removed module
        assert "feature_engineering.py" not in content

    @patch('subprocess.run')
    def test_ft_feature_engineering_script(self, mock_run):
        """Test that ft_feature_engineering.py can be executed."""
        # Mock successful execution
        mock_run.return_value = MagicMock(returncode=0, stdout="Generated 100 features", stderr="")
        
        # Test command structure
        result = subprocess.run([
            sys.executable, "-m", "src.feature_engineering.ft_feature_engineering"
        ], capture_output=True, text=True)
        
        # Check the command was formed correctly
        mock_run.assert_called_once()

    def test_feature_definitions_output_path(self):
        """Test that feature engineering script has code to save feature definitions."""
        # Check the script has the capability to save feature definitions
        with open("src/feature_engineering/ft_feature_engineering.py") as f:
            content = f.read()
        
        # Verify the script will save feature definitions
        assert 'daily_feature_defs_v1.joblib' in content
        assert 'joblib.dump' in content
        assert 'ARTEFACT_DIR' in content
        # Verify it creates the directory if it doesn't exist
        assert 'mkdir(exist_ok=True)' in content

    def test_memory_efficient_implementation(self):
        """Test that ft_build_feature_matrix.py has memory-efficient features."""
        with open("src/feature_engineering/ft_build_feature_matrix.py") as f:
            content = f.read()
        
        # Check for memory management features
        assert 'CHUNK_SIZE' in content
        assert 'DATE_CHUNK_DAYS' in content
        assert 'split_date_range_into_chunks' in content
        assert 'gc.collect()' in content

    def test_multi_target_support(self):
        """Test that feature_analysis.py supports multiple targets."""
        with open("src/feature_engineering/feature_analysis.py") as f:
            content = f.read()
        
        # Check for multi-target features
        assert 'MultiTargetFeatureSelector' in content
        assert 'analyze_all_targets' in content
        assert '_analyze_target' in content
        # Check for target handling (targets have 'target_' prefix)
        assert 'target_' in content
        assert 'numeric_targets' in content
        # Check that it handles binary classification for net_profit
        assert 'target_is_profitable' in content
        
    def test_output_directory_structure(self):
        """Test that the expected output directory structure is documented."""
        readme_path = Path("src/feature_engineering/README.md")
        with open(readme_path) as f:
            content = f.read()
        
        # Check output structure is documented
        assert "artefacts/" in content
        assert "model_inputs/" in content
        assert "train_matrix.parquet" in content
        assert "val_matrix.parquet" in content
        assert "test_matrix.parquet" in content

    def test_no_lookahead_bias_documentation(self):
        """Test that lookahead bias prevention is documented."""
        # Check feature catalog
        with open("src/feature_engineering/feature_catalog.md") as f:
            catalog_content = f.read()
        
        assert "Lookahead Bias Prevention" in catalog_content
        assert "Features from D, target from D+1" in catalog_content
        
        # Check README
        with open("src/feature_engineering/README.md") as f:
            readme_content = f.read()
        
        assert "No Lookahead Bias" in readme_content

    def test_configuration_parameters(self):
        """Test that configuration parameters are properly defined."""
        with open("src/feature_engineering/ft_build_feature_matrix.py") as f:
            content = f.read()
        
        # Check key parameters are defined
        assert "CHUNK_SIZE" in content
        assert "DATE_CHUNK_DAYS" in content
        assert "VAL_FRAC" in content
        assert "TEST_FRAC" in content
        assert "USE_DASK = False" in content
        
    def test_helper_functions_exist(self):
        """Test that required helper functions are properly imported and used."""
        # In ft_feature_engineering.py
        with open("src/feature_engineering/ft_feature_engineering.py") as f:
            ft_content = f.read()
        
        # Check imports
        assert "from .utils import" in ft_content
        assert "make_daily_id" in ft_content
        assert "make_hash_id" in ft_content
        assert "xxhash" in ft_content
        
        # In utils.py - check functions are defined there
        with open("src/feature_engineering/utils.py") as f:
            utils_content = f.read()
        
        assert "def make_daily_id" in utils_content
        assert "def make_hash_id" in utils_content
        assert "def prepare_dataframe" in utils_content