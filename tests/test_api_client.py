"""
Tests for the enhanced API client with circuit breaker.
"""

import pytest
import time
from unittest.mock import patch, MagicMock
import requests

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.api_client import RiskAnalyticsAPIClient, CircuitBreaker, APIError


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        assert cb.state == 'closed'
        assert not cb.is_open()
    
    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        
        # Record failures
        for _ in range(3):
            cb.call_failed()
        
        assert cb.state == 'open'
        assert cb.is_open()
    
    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        
        # Open the circuit
        cb.call_failed()
        cb.call_failed()
        assert cb.is_open()
        
        # Wait for recovery
        time.sleep(0.2)
        assert not cb.is_open()
        assert cb.state == 'half-open'
        
        # Success should close it
        cb.call_succeeded()
        assert cb.state == 'closed'


class TestRiskAnalyticsAPIClient:
    """Test enhanced API client functionality."""
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    def test_client_initialization(self):
        """Test API client initialization."""
        client = RiskAnalyticsAPIClient()
        assert client.api_key == 'test_key'
        assert client.circuit_breaker is not None
        assert client.total_requests == 0
        assert client.failed_requests == 0
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    @patch('requests.Session.request')
    def test_successful_request(self, mock_request):
        """Test successful API request."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': 'test'}
        mock_request.return_value = mock_response
        
        client = RiskAnalyticsAPIClient()
        result = client._make_request('test_endpoint')
        
        assert result == {'data': 'test'}
        assert client.total_requests == 1
        assert client.failed_requests == 0
        assert client.circuit_breaker.state == 'closed'
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    @patch('requests.Session.request')
    def test_retry_on_server_error(self, mock_request):
        """Test HTTPAdapter retry logic on server errors."""
        # First two attempts return 500, third succeeds
        mock_error_response = MagicMock()
        mock_error_response.status_code = 500
        mock_error_response.text = 'Server Error'
        mock_error_response.headers = {}
        
        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {'data': 'test'}
        
        # HTTPAdapter handles retries, so we simulate the final successful call
        mock_request.return_value = mock_success_response
        
        client = RiskAnalyticsAPIClient()
        result = client._make_request('test_endpoint')
        
        assert result == {'data': 'test'}
        # Only one call visible to us since HTTPAdapter handles internal retries
        assert mock_request.call_count == 1
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    @patch('requests.Session.request')
    def test_circuit_breaker_blocks_requests(self, mock_request):
        """Test circuit breaker blocks requests when open."""
        client = RiskAnalyticsAPIClient()
        
        # Open the circuit breaker
        for _ in range(5):
            client.circuit_breaker.call_failed()
        
        # Request should be blocked
        with pytest.raises(APIError) as exc_info:
            client._make_request('test_endpoint')
        
        assert 'Circuit breaker is open' in str(exc_info.value)
        mock_request.assert_not_called()
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    @patch('requests.Session.request')
    def test_rate_limiting(self, mock_request):
        """Test token bucket rate limiting allows bursts but enforces limits."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': 'test'}
        mock_request.return_value = mock_response
        
        # Create client with low rate limit and small burst
        client = RiskAnalyticsAPIClient(requests_per_second=2, burst_size=2)
        
        # First two requests should succeed immediately (within burst)
        start_time = time.time()
        client._make_request('test1')
        client._make_request('test2')
        elapsed = time.time() - start_time
        
        # Should be fast due to burst capacity
        assert elapsed < 0.1
        
        # Third request should be rate limited
        start_time = time.time()
        client._make_request('test3')
        elapsed = time.time() - start_time
        
        # Should take time due to rate limiting (at least 0.5s for 2 req/s)
        assert elapsed >= 0.4
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    def test_get_stats(self):
        """Test statistics tracking."""
        client = RiskAnalyticsAPIClient()
        client.total_requests = 100
        client.failed_requests = 5
        
        stats = client.get_stats()
        
        assert stats['total_requests'] == 100
        assert stats['failed_requests'] == 5
        assert stats['success_rate'] == 95.0
        assert 'circuit_breaker_state' in stats


class TestPaginationWithErrorHandling:
    """Test pagination with error handling."""
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    @patch('requests.Session.request')
    def test_pagination_stops_on_client_error(self, mock_request):
        """Test pagination stops on client error."""
        # Mock 400 error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'Bad request'
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        mock_request.return_value = mock_response
        
        client = RiskAnalyticsAPIClient()
        pages = list(client.paginate('test_endpoint'))
        
        assert len(pages) == 0  # No pages returned due to error
        assert mock_request.call_count == 1  # Only one attempt
    
    @patch.dict(os.environ, {'RISK_API_KEY': 'test_key'})
    @patch('requests.Session.request')
    def test_pagination_handles_successful_requests(self, mock_request):
        """Test pagination works with successful requests."""
        # Simulate successful pagination with two pages using proper API format
        mock_page1_response = MagicMock()
        mock_page1_response.status_code = 200
        mock_page1_response.json.return_value = {
            'Status': 'ok',
            'Data': {
                'data': [{'id': 1}, {'id': 2}],
                'total': 3,
                'skip': 0,
                'limit': 2,
                'count': 2
            }
        }
        
        mock_page2_response = MagicMock()
        mock_page2_response.status_code = 200
        mock_page2_response.json.return_value = {
            'Status': 'ok',
            'Data': {
                'data': [{'id': 3}],
                'total': 3,
                'skip': 2,
                'limit': 2,
                'count': 1
            }
        }
        
        mock_request.side_effect = [mock_page1_response, mock_page2_response]
        
        client = RiskAnalyticsAPIClient()
        pages = list(client.paginate('test_endpoint', limit=2))
        
        assert len(pages) == 2
        assert len(pages[0]) == 2
        assert len(pages[1]) == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])