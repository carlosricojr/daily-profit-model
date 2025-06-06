"""
Comprehensive integration test for the daily-profit-model pipeline.
Tests the API response parsing issue and demonstrates the integration points.
"""

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import numpy as np

from src.utils.api_client import RiskAnalyticsAPIClient


class TestIntegrationPipeline(unittest.TestCase):
    """Integration test for the ML pipeline - focused on key issues."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        os.environ['RISK_API_KEY'] = 'test-api-key'
        os.environ['RISK_API_BASE_URL'] = 'https://test-api.example.com'
        
    def setUp(self):
        """Set up before each test."""
        self._setup_mock_data()
        
    def _setup_mock_data(self):
        """Set up mock data for testing."""
        self.mock_accounts = [
            {
                "accountId": "ACC001",
                "login": "12345",
                "planId": 100,
                "type": 1,
                "phase": 1,
                "status": 1,
                "country": "US",
                "startingBalance": 50000.00,
                "currentBalance": 52000.00
            },
            {
                "accountId": "ACC002", 
                "login": "67890",
                "planId": 200,
                "type": 2,
                "phase": 2,
                "status": 1,
                "country": "UK",
                "startingBalance": 100000.00,
                "currentBalance": 98000.00
            }
        ]
        
        # Generate mock metrics
        self.mock_metrics = []
        base_date = datetime.now() - timedelta(days=30)
        
        for i in range(30):
            current_date = base_date + timedelta(days=i)
            for account in self.mock_accounts:
                daily_pnl = np.random.normal(100, 500)
                self.mock_metrics.append({
                    "date": current_date.strftime("%Y-%m-%dT00:00:00.000Z"),
                    "login": account["login"],
                    "planId": account["planId"],
                    "netProfit": float(daily_pnl),
                    "grossProfit": float(max(daily_pnl, 0)),
                    "grossLoss": float(min(daily_pnl, 0)),
                    "numTrades": np.random.randint(0, 20),
                    "startingBalance": account["startingBalance"],
                    "currentBalance": account["currentBalance"],
                    "currentEquity": account["currentBalance"]
                })
                
    @patch.object(RiskAnalyticsAPIClient, '_make_request')
    def test_01_api_response_parsing_bug(self, mock_api):
        """Test the API response parsing bug identified in code review."""
        
        # Test 1: Current implementation fails with nested structure
        mock_api.return_value = {
            "Status": "ok",
            "Data": {
                "total": 2,
                "skip": 0,
                "limit": 100,
                "data": self.mock_accounts  # Nested structure from actual API
            }
        }
        
        api_client = RiskAnalyticsAPIClient()
        results = list(api_client.paginate('/accounts'))
        
        # This should fail with current implementation
        self.assertEqual(len(results), 0, 
                        "BUG CONFIRMED: API client cannot parse nested Data.data structure")
        
        # Test 2: Current implementation works with flat structure
        mock_api.return_value = {
            "Status": "ok",
            "data": self.mock_accounts  # What current code expects
        }
        
        results = list(api_client.paginate('/accounts'))
        self.assertEqual(len(results), 1, 
                        "Current code works with flat 'data' structure")
        
    @patch.object(RiskAnalyticsAPIClient, '_make_request')
    def test_02_pagination_without_metadata(self, mock_api):
        """Test pagination logic without using server metadata."""
        
        # Mock paginated responses
        def mock_paginated_response(endpoint, **kwargs):
            params = kwargs.get('params', {})
            skip = params.get('skip', 0)
            limit = params.get('limit', 100)
            
            # Return subset of data based on skip/limit
            all_data = self.mock_metrics
            page_data = all_data[skip:skip+limit]
            
            return {
                "Status": "ok",
                "Data": {
                    "total": len(all_data),
                    "skip": skip,
                    "limit": limit,
                    "data": page_data
                }
            }
        
        mock_api.side_effect = mock_paginated_response
        
        api_client = RiskAnalyticsAPIClient()
        
        # Current implementation doesn't use total count
        all_results = []
        for page in api_client.paginate('/metrics/daily', params={'limit': 10}):
            all_results.extend(page)
            
        # Current implementation fails due to parsing bug
        self.assertEqual(len(all_results), 0, 
                        "Pagination also affected by parsing bug")
        
    @patch.object(RiskAnalyticsAPIClient, '_make_request')
    def test_03_error_status_handling(self, mock_api):
        """Test handling of error status in API response."""
        
        # Test error response
        mock_api.return_value = {
            "Status": "error",
            "Data": {"message": "Invalid API key"}
        }
        
        api_client = RiskAnalyticsAPIClient()
        results = list(api_client.paginate('/accounts'))
        
        # Should return empty results on error status
        self.assertEqual(len(results), 0)
        
    @patch.object(RiskAnalyticsAPIClient, '_make_request')
    def test_04_malformed_response_handling(self, mock_api):
        """Test handling of malformed API responses."""
        
        # Test various malformed responses
        test_cases = [
            None,  # Null response
            [],    # List instead of dict
            {"Status": "ok"},  # Missing Data field
            {"Status": "ok", "Data": None},  # Null Data
            {"Status": "ok", "Data": "string"},  # Wrong Data type
        ]
        
        api_client = RiskAnalyticsAPIClient()
        
        for response in test_cases:
            mock_api.return_value = response
            results = list(api_client.paginate('/accounts'))
            self.assertEqual(len(results), 0, 
                           f"Should handle malformed response: {response}")
            
    def test_05_integration_components(self):
        """Test that key components can be initialized."""
        
        # Test API client
        api_client = RiskAnalyticsAPIClient()
        self.assertIsNotNone(api_client)
        
        # Test circuit breaker initialization
        self.assertIsNotNone(api_client.circuit_breaker)
        self.assertEqual(api_client.circuit_breaker.failure_threshold, 5)
        
        # Test rate limiter initialization
        self.assertIsNotNone(api_client.rate_limiter)
        
    @patch.object(RiskAnalyticsAPIClient, '_make_request')
    def test_06_demonstrate_correct_parsing(self, mock_api):
        """Demonstrate how the API response should be parsed correctly."""
        
        # This is what the fixed implementation should handle
        mock_api.return_value = {
            "Status": "ok",
            "Data": {
                "total": 2,
                "skip": 0,
                "limit": 100,
                "data": self.mock_accounts
            }
        }
        
        api_client = RiskAnalyticsAPIClient()
        
        # Manual parsing to show correct approach
        response = api_client._make_request('/accounts')
        
        # Check status
        self.assertEqual(response.get('Status'), 'ok')
        
        # Extract nested data correctly
        data_wrapper = response.get('Data', {})
        self.assertIsInstance(data_wrapper, dict)
        
        actual_data = data_wrapper.get('data', [])
        self.assertEqual(len(actual_data), 2)
        self.assertEqual(actual_data[0]['accountId'], 'ACC001')
        
        # Extract pagination metadata
        total = data_wrapper.get('total', 0)
        self.assertEqual(total, 2)
        

if __name__ == '__main__':
    unittest.main()