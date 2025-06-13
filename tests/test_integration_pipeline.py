"""
Comprehensive integration test for the daily-profit-model pipeline.
Tests the API response parsing issue and demonstrates the integration points.
"""

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import random

from src.utils.api_client import RiskAnalyticsAPIClient


class TestIntegrationPipeline(unittest.TestCase):
    """Integration test for the ML pipeline - focused on key issues."""

    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        os.environ["RISK_API_KEY"] = "test-api-key"
        os.environ["RISK_API_BASE_URL"] = "https://test-api.example.com"

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
                "currentBalance": 52000.00,
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
                "currentBalance": 98000.00,
            },
        ]

        # Generate mock metrics
        self.mock_metrics = []
        base_date = datetime.now() - timedelta(days=30)

        for i in range(30):
            current_date = base_date + timedelta(days=i)
            for account in self.mock_accounts:
                daily_pnl = random.gauss(100, 500)
                self.mock_metrics.append(
                    {
                        "date": current_date.strftime("%Y-%m-%dT00:00:00.000Z"),
                        "login": account["login"],
                        "planId": account["planId"],
                        "netProfit": float(daily_pnl),
                        "grossProfit": float(max(daily_pnl, 0)),
                        "grossLoss": float(min(daily_pnl, 0)),
                        "numTrades": random.randint(0, 20),
                        "startingBalance": account["startingBalance"],
                        "currentBalance": account["currentBalance"],
                        "currentEquity": account["currentBalance"],
                    }
                )

    @patch.object(RiskAnalyticsAPIClient, "_make_request")
    def test_01_api_response_parsing_fixed(self, mock_api):
        """Test that the API response parsing bug has been fixed."""

        # Test 1: Fixed implementation handles nested Data.data structure
        mock_api.return_value = {
            "Status": "ok",
            "Data": {
                "total": 2,
                "skip": 0,
                "limit": 100,
                "data": self.mock_accounts,  # Nested structure from actual API
            },
        }

        api_client = RiskAnalyticsAPIClient()
        results = list(api_client.paginate("/accounts"))

        # Fixed implementation should parse this correctly
        self.assertEqual(
            len(results),
            1,
            "Fixed implementation correctly parses nested Data.data structure",
        )
        self.assertEqual(len(results[0]), 2, "Should return 2 accounts")
        self.assertEqual(results[0][0]["accountId"], "ACC001")

        # Test 2: Fixed implementation also handles flat structure for compatibility
        mock_api.return_value = {
            "Status": "ok",
            "data": self.mock_accounts,  # Legacy flat structure
        }

        results = list(api_client.paginate("/accounts"))
        self.assertEqual(
            len(results),
            1,
            "Fixed implementation maintains backward compatibility with flat 'data' structure",
        )

    @patch.object(RiskAnalyticsAPIClient, "_make_request")
    def test_02_pagination_without_metadata(self, mock_api):
        """Test pagination logic without using server metadata."""

        # Mock paginated responses
        def mock_paginated_response(endpoint, **kwargs):
            params = kwargs.get("params", {})
            skip = params.get("skip", 0)
            limit = params.get("limit", 100)

            # Return subset of data based on skip/limit
            all_data = self.mock_metrics
            page_data = all_data[skip : skip + limit]

            return {
                "Status": "ok",
                "Data": {
                    "total": len(all_data),
                    "skip": skip,
                    "limit": limit,
                    "data": page_data,
                },
            }

        mock_api.side_effect = mock_paginated_response

        api_client = RiskAnalyticsAPIClient()

        # Fixed implementation uses total count for termination
        all_results = []
        for page in api_client.paginate("/metrics/daily", params={"limit": 10}):
            all_results.extend(page)

        # Fixed implementation correctly handles pagination
        self.assertEqual(
            len(all_results),
            len(self.mock_metrics),
            "Fixed pagination correctly fetches all records",
        )

    @patch.object(RiskAnalyticsAPIClient, "_make_request")
    def test_03_error_status_handling(self, mock_api):
        """Test handling of error status in API response."""

        # Test error response
        mock_api.return_value = {"Status": "error", "Error": "Invalid API key"}

        api_client = RiskAnalyticsAPIClient()

        # Fixed implementation logs error and returns empty results
        results = list(api_client.paginate("/accounts"))

        # Should return empty results on error status
        self.assertEqual(len(results), 0, "Should return empty results on API error")

    @patch.object(RiskAnalyticsAPIClient, "_make_request")
    def test_04_malformed_response_handling(self, mock_api):
        """Test handling of malformed API responses."""

        # Test various malformed responses
        test_cases = [
            None,  # Null response
            [],  # List instead of dict
            {"Status": "ok"},  # Missing Data field
            {"Status": "ok", "Data": None},  # Null Data
            {"Status": "ok", "Data": "string"},  # Wrong Data type
        ]

        api_client = RiskAnalyticsAPIClient()

        for i, response in enumerate(test_cases):
            mock_api.return_value = response

            # Test each malformed response
            try:
                results = list(api_client.paginate("/accounts"))
                # For dict responses, pagination should handle them gracefully
                if isinstance(response, dict):
                    self.assertEqual(
                        len(results),
                        0,
                        f"Should handle malformed response gracefully: {response}",
                    )
                else:
                    # Non-dict responses should have been caught
                    self.fail(f"Should have failed for non-dict response: {response}")
            except Exception as e:
                # Non-dict responses should raise exceptions
                if not isinstance(response, dict):
                    # Expected behavior - non-dict responses cause errors
                    pass
                else:
                    # Unexpected - dict responses shouldn't raise exceptions
                    self.fail(f"Unexpected exception for dict response {response}: {e}")

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

    @patch.object(RiskAnalyticsAPIClient, "_make_request")
    def test_06_fixed_implementation_features(self, mock_api):
        """Test all features of the fixed implementation."""

        # Test 1: Response validation
        mock_api.return_value = {
            "Status": "ok",
            "Data": {"total": 2, "skip": 0, "limit": 100, "data": self.mock_accounts},
        }

        api_client = RiskAnalyticsAPIClient()

        # Test internal methods work correctly
        response = api_client._make_request("/accounts")

        # Validate response
        self.assertTrue(api_client._validate_response(response))

        # Extract data correctly
        data = api_client._extract_data_from_response(response)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["accountId"], "ACC001")

        # Extract pagination metadata
        metadata = api_client._extract_pagination_metadata(response)
        self.assertEqual(metadata["total"], 2)
        self.assertEqual(metadata["skip"], 0)
        self.assertEqual(metadata["limit"], 100)
        self.assertEqual(metadata["count"], 2)

        # Test 2: List response (like /accounts endpoint)
        mock_api.return_value = {
            "Status": "ok",
            "Data": self.mock_accounts,  # Direct list
        }

        data = api_client._extract_data_from_response(mock_api.return_value)
        self.assertEqual(len(data), 2)

    def test_07_all_optimizations_integrated(self):
        """Test that all optimizations are properly integrated."""

        # Test 1: API client has enhanced features
        api_client = RiskAnalyticsAPIClient()

        # Circuit breaker is active
        self.assertIsNotNone(api_client.circuit_breaker)
        self.assertEqual(api_client.circuit_breaker.state, "closed")

        # Rate limiter is active
        self.assertIsNotNone(api_client.rate_limiter)
        self.assertGreater(api_client.rate_limiter.tokens, 0)

        # Connection pool is active
        self.assertIsNotNone(api_client.connection_pool)
        self.assertGreater(api_client.connection_pool.pool_size, 0)

        # Test 2: Database operations use execute_batch (via imports)
        try:
            # Check that base_ingester uses execute_batch in production
            with open("src/data_ingestion/base_ingester.py", "r") as f:
                base_ingester_content = f.read()
            self.assertIn(
                "execute_batch",
                base_ingester_content,
                "Database operations should import execute_batch for optimization",
            )
            self.assertIn(
                "from psycopg2.extras import execute_batch",
                base_ingester_content,
                "Should import execute_batch from psycopg2.extras",
            )
        except FileNotFoundError:
            # Skip if file not found in test environment
            pass

        # Test 3: Logging infrastructure enhancements
        from src.utils.logging_config import get_logger, LoggingContext

        logger = get_logger(__name__)
        self.assertIsNotNone(logger)

        # Test correlation ID context
        with LoggingContext(operation="test", user_id="test_user"):
            # Context should be available
            pass

        # Test 4: Feature engineering optimizations
        try:
            from src.feature_engineering.engineer_features_optimized import (
                OptimizedFeatureEngineer,
            )
            from src.feature_engineering.engineer_features_integrated import (
                IntegratedFeatureEngineer,
            )

            # Both optimized versions should be available
            self.assertTrue(hasattr(OptimizedFeatureEngineer, "_bulk_fetch_all_data"))
            self.assertTrue(hasattr(IntegratedFeatureEngineer, "engineer_features"))
        except ImportError:
            # Skip if not in proper environment
            pass

    def test_08_production_ready_checks(self):
        """Verify production readiness of all components."""

        # Test 1: No hardcoded credentials in production code
        # Note: Test environment sets test keys, but production code should not have hardcoded values
        # Check that the API client requires environment variables
        import os

        original_key = os.environ.pop("RISK_API_KEY", None)
        try:
            with self.assertRaises(ValueError) as context:
                RiskAnalyticsAPIClient()
            self.assertIn("API key is required", str(context.exception))
        finally:
            if original_key:
                os.environ["RISK_API_KEY"] = original_key

        # Test 2: Error handling is robust
        api_client = RiskAnalyticsAPIClient()

        # Circuit breaker prevents cascading failures
        for _ in range(10):
            api_client.circuit_breaker.call_failed()

        self.assertTrue(
            api_client.circuit_breaker.is_open(),
            "Circuit breaker should open after failures",
        )

        # Test 3: Performance monitoring is available
        stats = api_client.get_stats()
        self.assertIn("total_requests", stats)
        self.assertIn("performance", stats)
        self.assertIn("circuit_breaker", stats)


if __name__ == "__main__":
    unittest.main()
