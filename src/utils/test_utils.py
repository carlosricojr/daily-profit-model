"""
Tests for Version 1 Conservative utilities.
"""

import unittest
import os
import time
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import utilities to test
from logging_config import setup_logging, get_logger, log_execution_time
from metrics import MetricsCollector, track_execution_time, Timer
from config_validation import ConfigValidator, ConfigField, ConfigurationError


class TestLoggingConfig(unittest.TestCase):
    """Test structured logging functionality."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def test_json_logging(self):
        """Test JSON format logging."""
        log_file = os.path.join(self.temp_dir, "test.log")
        logger = setup_logging(
            log_level="INFO",
            log_file="test",
            log_dir=self.temp_dir,
            json_format=True,
            enable_console=False
        )
        
        test_logger = get_logger("test_module", {"request_id": "123"})
        test_logger.info("Test message", extra={'extra_fields': {'user': 'test'}})
        
        # Read log file and verify JSON format
        with open(log_file, 'r') as f:
            log_line = f.readline()
            log_data = json.loads(log_line)
            
            self.assertEqual(log_data['level'], 'INFO')
            self.assertEqual(log_data['message'], 'Test message')
            self.assertEqual(log_data['request_id'], '123')
            self.assertEqual(log_data['user'], 'test')
            self.assertIn('timestamp', log_data)
    
    def test_log_execution_time_decorator(self):
        """Test execution time logging decorator."""
        @log_execution_time()
        def slow_function():
            time.sleep(0.1)
            return "done"
        
        result = slow_function()
        self.assertEqual(result, "done")
    
    def test_log_execution_time_decorator_with_error(self):
        """Test execution time logging decorator with exception."""
        @log_execution_time()
        def failing_function():
            raise ValueError("Test error")
        
        with self.assertRaises(ValueError):
            failing_function()


class TestMetrics(unittest.TestCase):
    """Test metrics collection functionality."""
    
    def setUp(self):
        self.metrics = MetricsCollector()
    
    def test_counter_metrics(self):
        """Test counter metric functionality."""
        self.metrics.increment_counter("test_counter", 1)
        self.metrics.increment_counter("test_counter", 2)
        
        metrics_data = self.metrics.get_metrics()
        counter_data = metrics_data['counters']['test_counter']
        
        self.assertEqual(counter_data['total'], 3)
        self.assertGreater(counter_data['rate_per_second'], 0)
    
    def test_gauge_metrics(self):
        """Test gauge metric functionality."""
        self.metrics.set_gauge("test_gauge", 42.5)
        
        metrics_data = self.metrics.get_metrics()
        self.assertEqual(metrics_data['gauges']['test_gauge'], 42.5)
    
    def test_timing_metrics(self):
        """Test timing metric functionality."""
        self.metrics.record_timing("test_timing", 0.1)
        self.metrics.record_timing("test_timing", 0.2)
        self.metrics.record_timing("test_timing", 0.15)
        
        metrics_data = self.metrics.get_metrics()
        timing_data = metrics_data['timings']['test_timing']
        
        self.assertEqual(timing_data['count'], 3)
        self.assertEqual(timing_data['min'], 0.1)
        self.assertEqual(timing_data['max'], 0.2)
        self.assertAlmostEqual(timing_data['avg'], 0.15, places=2)
    
    def test_metrics_with_labels(self):
        """Test metrics with labels."""
        self.metrics.increment_counter("api_requests", 1, {"endpoint": "/users", "method": "GET"})
        self.metrics.increment_counter("api_requests", 1, {"endpoint": "/users", "method": "POST"})
        
        metrics_data = self.metrics.get_metrics()
        self.assertIn('api_requests{endpoint=/users,method=GET}', metrics_data['counters'])
        self.assertIn('api_requests{endpoint=/users,method=POST}', metrics_data['counters'])
    
    def test_track_execution_time_decorator(self):
        """Test execution time tracking decorator."""
        @track_execution_time("test_function")
        def test_func():
            time.sleep(0.05)
            return "result"
        
        result = test_func()
        self.assertEqual(result, "result")
        
        metrics_data = self.metrics.get_metrics()
        self.assertIn('function_duration_test_function', metrics_data['timings'])
        self.assertIn('function_duration_test_function_success', metrics_data['counters'])
    
    def test_timer_context_manager(self):
        """Test Timer context manager."""
        with Timer("test_block"):
            time.sleep(0.05)
        
        metrics_data = self.metrics.get_metrics()
        self.assertIn('test_block', metrics_data['timings'])
        self.assertIn('test_block_success', metrics_data['counters'])


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation functionality."""
    
    def setUp(self):
        self.validator = ConfigValidator()
        # Save original environment
        self.original_env = os.environ.copy()
    
    def tearDown(self):
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_required_field_validation(self):
        """Test required field validation."""
        field = ConfigField(name="TEST_REQUIRED", required=True, type=str)
        
        # Test missing required field
        with self.assertRaises(AttributeError):
            value = self.validator.validate_field(field)
            self.assertIsNone(value)
            self.assertIn("Required configuration 'TEST_REQUIRED' is missing", self.validator.errors)
    
    def test_optional_field_with_default(self):
        """Test optional field with default value."""
        field = ConfigField(name="TEST_OPTIONAL", required=False, default="default_value", type=str)
        
        value = self.validator.validate_field(field)
        self.assertEqual(value, "default_value")
    
    def test_type_conversion(self):
        """Test type conversion for different types."""
        # Test integer conversion
        os.environ["TEST_INT"] = "42"
        field_int = ConfigField(name="TEST_INT", type=int)
        self.assertEqual(self.validator.validate_field(field_int), 42)
        
        # Test float conversion
        os.environ["TEST_FLOAT"] = "3.14"
        field_float = ConfigField(name="TEST_FLOAT", type=float)
        self.assertAlmostEqual(self.validator.validate_field(field_float), 3.14)
        
        # Test boolean conversion
        os.environ["TEST_BOOL"] = "true"
        field_bool = ConfigField(name="TEST_BOOL", type=bool)
        self.assertTrue(self.validator.validate_field(field_bool))
        
        # Test list conversion
        os.environ["TEST_LIST"] = "item1, item2, item3"
        field_list = ConfigField(name="TEST_LIST", type=list)
        self.assertEqual(self.validator.validate_field(field_list), ["item1", "item2", "item3"])
    
    def test_choices_validation(self):
        """Test choices validation."""
        os.environ["TEST_CHOICE"] = "option2"
        field = ConfigField(name="TEST_CHOICE", type=str, choices=["option1", "option2", "option3"])
        
        self.assertEqual(self.validator.validate_field(field), "option2")
        
        # Test invalid choice
        os.environ["TEST_CHOICE"] = "invalid_option"
        self.validator.errors.clear()
        value = self.validator.validate_field(field)
        self.assertIsNone(value)
        self.assertTrue(any("not in" in error for error in self.validator.errors))
    
    def test_numeric_range_validation(self):
        """Test numeric range validation."""
        os.environ["TEST_RANGE"] = "50"
        field = ConfigField(name="TEST_RANGE", type=int, min_value=1, max_value=100)
        
        self.assertEqual(self.validator.validate_field(field), 50)
        
        # Test below minimum
        os.environ["TEST_RANGE"] = "0"
        self.validator.errors.clear()
        value = self.validator.validate_field(field)
        self.assertIsNone(value)
        self.assertTrue(any("below minimum" in error for error in self.validator.errors))
        
        # Test above maximum
        os.environ["TEST_RANGE"] = "101"
        self.validator.errors.clear()
        value = self.validator.validate_field(field)
        self.assertIsNone(value)
        self.assertTrue(any("above maximum" in error for error in self.validator.errors))
    
    def test_custom_validator(self):
        """Test custom validator function."""
        def is_even(value):
            return value % 2 == 0
        
        os.environ["TEST_CUSTOM"] = "42"
        field = ConfigField(name="TEST_CUSTOM", type=int, validator=is_even)
        
        self.assertEqual(self.validator.validate_field(field), 42)
        
        # Test validation failure
        os.environ["TEST_CUSTOM"] = "43"
        self.validator.errors.clear()
        value = self.validator.validate_field(field)
        self.assertIsNone(value)
        self.assertTrue(any("Custom validation failed" in error for error in self.validator.errors))
    
    def test_validate_all(self):
        """Test validating multiple fields."""
        os.environ["FIELD1"] = "value1"
        os.environ["FIELD2"] = "42"
        
        fields = [
            ConfigField(name="FIELD1", type=str),
            ConfigField(name="FIELD2", type=int),
            ConfigField(name="FIELD3", required=False, default="default3")
        ]
        
        config = self.validator.validate_all(fields)
        
        self.assertEqual(config["FIELD1"], "value1")
        self.assertEqual(config["FIELD2"], 42)
        self.assertEqual(config["FIELD3"], "default3")
    
    def test_validate_all_with_errors(self):
        """Test validate_all with validation errors."""
        os.environ["FIELD1"] = "not_a_number"
        
        fields = [
            ConfigField(name="FIELD1", type=int),
            ConfigField(name="FIELD2", required=True)
        ]
        
        with self.assertRaises(ConfigurationError) as context:
            self.validator.validate_all(fields)
        
        self.assertIn("Configuration validation failed", str(context.exception))


class TestDatabaseEnhancements(unittest.TestCase):
    """Test enhanced database functionality."""
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_connection_retry(self, mock_pool_class):
        """Test database connection retry logic."""
        from database import DatabaseConnection
        
        # Simulate connection failure then success
        mock_pool_class.side_effect = [
            psycopg2.OperationalError("Connection failed"),
            Mock()  # Success on second attempt
        ]
        
        # Should succeed after retry
        db = DatabaseConnection(
            host="localhost",
            port=5432,
            database="test",
            user="test",
            password="test",
            max_retries=2
        )
        
        self.assertEqual(mock_pool_class.call_count, 2)
    
    @patch('psycopg2.pool.SimpleConnectionPool')
    def test_health_check(self, mock_pool_class):
        """Test database health check."""
        from database import DatabaseConnection
        
        mock_pool = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        mock_pool_class.return_value = mock_pool
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        db = DatabaseConnection(
            host="localhost",
            port=5432,
            database="test",
            user="test",
            password="test"
        )
        
        # Test successful health check
        self.assertTrue(db.health_check())
        mock_cursor.execute.assert_called_with("SELECT 1")
        
        # Test failed health check
        mock_cursor.execute.side_effect = Exception("Connection lost")
        self.assertFalse(db.health_check())


class TestAPIClientEnhancements(unittest.TestCase):
    """Test enhanced API client functionality."""
    
    def setUp(self):
        os.environ["API_KEY"] = "test_key"
    
    @patch('requests.Session')
    def test_circuit_breaker(self, mock_session_class):
        """Test circuit breaker pattern."""
        from api_client import RiskAnalyticsAPIClient, APIError
        
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        # Simulate server errors
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_response.raise_for_status.side_effect = requests.HTTPError()
        mock_session.request.return_value = mock_response
        
        client = RiskAnalyticsAPIClient()
        
        # Trigger circuit breaker
        for _ in range(5):
            try:
                client._make_request("test_endpoint")
            except Exception:
                pass
        
        # Circuit breaker should be open
        with self.assertRaises(APIError) as context:
            client._make_request("test_endpoint")
        
        self.assertIn("Circuit breaker is open", str(context.exception))
    
    @patch('requests.Session')
    def test_rate_limiting(self, mock_session_class):
        """Test rate limiting functionality."""
        from api_client import RiskAnalyticsAPIClient
        
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_session.request.return_value = mock_response
        
        client = RiskAnalyticsAPIClient(requests_per_second=10)
        
        # Make rapid requests
        start_time = time.time()
        for _ in range(3):
            client._make_request("test_endpoint")
        elapsed = time.time() - start_time
        
        # Should take at least 0.2 seconds (3 requests at 10/sec)
        self.assertGreaterEqual(elapsed, 0.2)


if __name__ == "__main__":
    unittest.main()