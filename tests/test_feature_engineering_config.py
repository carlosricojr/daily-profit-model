#!/usr/bin/env python3
"""
Comprehensive tests for feature engineering configuration management.
Tests dynamic configuration based on system resources with ML best practices.
"""

import unittest
from unittest.mock import patch, Mock
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.feature_engineering.feature_engineering import get_optimal_config


class TestConfigurationManagement(unittest.TestCase):
    """Test configuration management with ML engineering best practices."""

    def test_minimum_batch_size_threshold(self):
        """Test that batch_size never goes below 100."""
        with patch('multiprocessing.cpu_count', return_value=4):
            with patch('psutil.virtual_memory') as mock_mem:
                # Test with very low memory (should still give batch_size=100)
                mock_mem.return_value = Mock(total=2 * 1024**3)  # 2GB
                config = get_optimal_config()
                
                # batch_size = min(3000, total_ram_mb // 40)
                # 2GB = 2048MB, 2048 // 40 = 51, but should be at least 100
                expected = max(100, min(3000, 2048 // 40))
                self.assertEqual(config["batch_size"], expected)
                self.assertGreaterEqual(config["batch_size"], 100)

    def test_low_cpu_count_handling(self):
        """Test max_workers with systems having less than 4 cores."""
        with patch('psutil.virtual_memory') as mock_mem:
            mock_mem.return_value = Mock(total=16 * 1024**3)  # 16GB
            
            # Test with 1 CPU core
            with patch('multiprocessing.cpu_count', return_value=1):
                config = get_optimal_config()
                # max_workers = max(1, cpu_count - 4) = max(1, -3) = 1
                self.assertEqual(config["max_workers"], 1)
            
            # Test with 2 CPU cores
            with patch('multiprocessing.cpu_count', return_value=2):
                config = get_optimal_config()
                self.assertEqual(config["max_workers"], 1)
            
            # Test with 4 CPU cores (boundary)
            with patch('multiprocessing.cpu_count', return_value=4):
                config = get_optimal_config()
                self.assertEqual(config["max_workers"], 1)
            
            # Test with 8 CPU cores
            with patch('multiprocessing.cpu_count', return_value=8):
                config = get_optimal_config()
                self.assertEqual(config["max_workers"], 4)

    def test_large_ram_system_caps(self):
        """Test configuration with 128GB RAM system."""
        with patch('multiprocessing.cpu_count', return_value=32):
            with patch('psutil.virtual_memory') as mock_mem:
                # 128GB system
                mock_mem.return_value = Mock(total=128 * 1024**3)
                config = get_optimal_config()
                
                # batch_size = min(3000, 131072 // 40) = min(3000, 3276) = 3000
                self.assertEqual(config["batch_size"], 3000)
                
                # chunk_size = min(8000, 131072 // 15) = min(8000, 8738) = 8000
                self.assertEqual(config["chunk_size"], 8000)
                
                # For 128GB RAM, batch_size caps at 3000 and chunk_size at 8000
                # This is reasonable as performance gains become negligible beyond these points
                # due to Python's GIL and database connection limits

    def test_memory_limit_calculation(self):
        """Test memory limit is 85% of total RAM."""
        test_cases = [
            (8 * 1024**3, 8 * 1024, int(8 * 1024 * 0.85)),      # 8GB
            (16 * 1024**3, 16 * 1024, int(16 * 1024 * 0.85)),   # 16GB
            (32 * 1024**3, 32 * 1024, int(32 * 1024 * 0.85)),   # 32GB
            (64 * 1024**3, 64 * 1024, int(64 * 1024 * 0.85)),   # 64GB
            (128 * 1024**3, 128 * 1024, int(128 * 1024 * 0.85)), # 128GB
        ]
        
        with patch('multiprocessing.cpu_count', return_value=16):
            for total_bytes, total_mb, expected_limit in test_cases:
                with patch('psutil.virtual_memory') as mock_mem:
                    mock_mem.return_value = Mock(total=total_bytes)
                    config = get_optimal_config()
                    self.assertEqual(config["memory_limit_mb"], expected_limit)

    def test_all_config_keys_present(self):
        """Test that all required configuration keys are present."""
        with patch('multiprocessing.cpu_count', return_value=8):
            with patch('psutil.virtual_memory') as mock_mem:
                mock_mem.return_value = Mock(total=16 * 1024**3)
                config = get_optimal_config()
                
                required_keys = [
                    "batch_size",
                    "chunk_size", 
                    "max_workers",
                    "memory_limit_mb",
                    "enable_monitoring",
                    "enable_bias_validation",
                    "quality_threshold"
                ]
                
                for key in required_keys:
                    self.assertIn(key, config)
                
                # Check boolean values
                self.assertTrue(config["enable_monitoring"])
                self.assertTrue(config["enable_bias_validation"])
                self.assertEqual(config["quality_threshold"], 0.95)

    def test_edge_cases(self):
        """Test edge cases for configuration."""
        with patch('multiprocessing.cpu_count', return_value=64):
            # Test with extremely low memory
            with patch('psutil.virtual_memory') as mock_mem:
                mock_mem.return_value = Mock(total=1 * 1024**3)  # 1GB
                config = get_optimal_config()
                
                # Should handle gracefully
                self.assertGreaterEqual(config["batch_size"], 1)
                self.assertGreaterEqual(config["chunk_size"], 1)
                self.assertGreaterEqual(config["memory_limit_mb"], 1)

    def test_performance_scaling(self):
        """Test that configuration scales appropriately with resources."""
        ram_sizes = [8, 16, 32, 64, 128]  # GB
        
        previous_batch_size = 0
        previous_chunk_size = 0
        
        for ram in ram_sizes:
            with patch('multiprocessing.cpu_count', return_value=32):
                with patch('psutil.virtual_memory') as mock_mem:
                    mock_mem.return_value = Mock(total=ram * 1024**3)
                    config = get_optimal_config()
                    
                    # Batch size should increase with RAM (up to cap)
                    self.assertGreaterEqual(config["batch_size"], previous_batch_size)
                    previous_batch_size = config["batch_size"]
                    
                    # Chunk size should increase with RAM (up to cap)
                    self.assertGreaterEqual(config["chunk_size"], previous_chunk_size)
                    previous_chunk_size = config["chunk_size"]
                    
                    # But should respect caps
                    self.assertLessEqual(config["batch_size"], 3000)
                    self.assertLessEqual(config["chunk_size"], 8000)


if __name__ == "__main__":
    unittest.main()