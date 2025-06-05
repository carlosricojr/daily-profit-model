"""
API client utilities for interacting with the risk analytics API endpoints.
Handles authentication, pagination, and rate limiting.
"""

import os
import time
import logging
from typing import Dict, List, Any, Optional, Iterator
from datetime import datetime, timedelta
import requests
from urllib.parse import urljoin, urlencode
import json

logger = logging.getLogger(__name__)


class APIClient:
    """Alias for backward compatibility."""
    pass


class RiskAnalyticsAPIClient:
    """Client for interacting with the Risk Analytics TFT External API."""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize API client.
        
        Args:
            api_key: API key for authentication (defaults to env var API_KEY)
            base_url: Base URL for the API (defaults to env var API_BASE_URL)
        """
        self.api_key = api_key or os.getenv('API_KEY')
        if not self.api_key:
            raise ValueError("API key is required. Set API_KEY environment variable.")
        
        self.base_url = base_url or os.getenv(
            'API_BASE_URL', 
            'https://easton.apis.arizet.io/risk-analytics/tft/external/'
        )
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'DailyProfitModel/1.0',
            'Accept': 'application/json'
        })
        
        # Rate limiting configuration
        self.requests_per_second = 10  # Adjust based on API limits
        self.last_request_time = 0
        
        logger.info(f"API client initialized for {self.base_url}")
    
    def _rate_limit(self):
        """Implement rate limiting to avoid overwhelming the API."""
        min_interval = 1.0 / self.requests_per_second
        elapsed = time.time() - self.last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_request_time = time.time()
    
    def _make_request(self, 
                     endpoint: str, 
                     method: str = 'GET',
                     params: Optional[Dict[str, Any]] = None,
                     data: Optional[Dict[str, Any]] = None,
                     timeout: int = 30) -> Dict[str, Any]:
        """
        Make an API request with error handling and retries.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            data: Request body data
            timeout: Request timeout in seconds
            
        Returns:
            Response data as dictionary
        """
        url = urljoin(self.base_url, endpoint)
        
        # Add API key to params
        if params is None:
            params = {}
        params['apiKey'] = self.api_key
        
        # Rate limiting
        self._rate_limit()
        
        # Retry configuration
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    timeout=timeout
                )
                
                # Log request details
                logger.debug(f"{method} {url} - Status: {response.status_code}")
                
                # Check for successful response
                response.raise_for_status()
                
                # Parse JSON response
                return response.json()
                
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
                    
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limit exceeded
                    logger.warning("Rate limit exceeded, backing off...")
                    time.sleep(retry_delay * 5)
                    retry_delay *= 2
                elif response.status_code >= 500:  # Server error
                    logger.warning(f"Server error {response.status_code} on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise
                else:
                    # Client error, don't retry
                    logger.error(f"Client error {response.status_code}: {response.text}")
                    raise
                    
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                raise
    
    def paginate(self,
                endpoint: str,
                params: Optional[Dict[str, Any]] = None,
                limit: int = 1000,
                max_pages: Optional[int] = None) -> Iterator[List[Dict[str, Any]]]:
        """
        Paginate through API results.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            limit: Number of results per page
            max_pages: Maximum number of pages to fetch (optional)
            
        Yields:
            Lists of results from each page
        """
        if params is None:
            params = {}
        
        params['limit'] = limit
        params['skip'] = 0
        page = 0
        
        while max_pages is None or page < max_pages:
            logger.info(f"Fetching page {page + 1}, skip={params['skip']}, limit={limit}")
            
            response = self._make_request(endpoint, params=params)
            
            # Handle different response formats
            if isinstance(response, list):
                results = response
            elif isinstance(response, dict) and 'data' in response:
                results = response['data']
            else:
                logger.warning(f"Unexpected response format: {type(response)}")
                results = []
            
            if not results:
                logger.info("No more results, stopping pagination")
                break
            
            yield results
            
            # Check if we got fewer results than limit (last page)
            if len(results) < limit:
                logger.info(f"Last page reached (got {len(results)} results)")
                break
            
            # Update pagination parameters
            params['skip'] += limit
            page += 1
            
            # Small delay between pages
            time.sleep(0.1)
    
    def get_accounts(self, 
                    logins: Optional[List[str]] = None,
                    traders: Optional[List[str]] = None,
                    **kwargs) -> Iterator[List[Dict[str, Any]]]:
        """
        Get accounts data with pagination.
        
        Args:
            logins: List of login IDs to filter
            traders: List of trader IDs to filter
            **kwargs: Additional parameters
            
        Yields:
            Lists of account records
        """
        params = {}
        if logins:
            params['logins'] = ','.join(logins)
        if traders:
            params['traders'] = ','.join(traders)
        params.update(kwargs)
        
        # Max limit for accounts endpoint is 500
        yield from self.paginate('accounts', params=params, limit=500)
    
    def get_metrics(self,
                   metric_type: str,
                   logins: Optional[List[str]] = None,
                   accountids: Optional[List[str]] = None,
                   dates: Optional[List[str]] = None,
                   hours: Optional[List[int]] = None,
                   **kwargs) -> Iterator[List[Dict[str, Any]]]:
        """
        Get metrics data with pagination.
        
        Args:
            metric_type: Type of metrics ('alltime', 'daily', 'hourly')
            logins: List of login IDs to filter
            accountids: List of account IDs to filter
            dates: List of dates in YYYYMMDD format
            hours: List of hours (0-23) for hourly metrics
            **kwargs: Additional parameters
            
        Yields:
            Lists of metrics records
        """
        endpoint = f'v2/metrics/{metric_type}'
        params = {}
        
        if logins:
            params['logins'] = ','.join(logins)
        if accountids:
            params['accountids'] = ','.join(accountids)
        if dates:
            params['dates'] = ','.join(dates)
        if hours and metric_type == 'hourly':
            params['hours'] = ','.join(map(str, hours))
        params.update(kwargs)
        
        # Max limit for metrics endpoints is 1000
        yield from self.paginate(endpoint, params=params, limit=1000)
    
    def get_trades(self,
                  trade_type: str,
                  logins: Optional[List[str]] = None,
                  symbols: Optional[List[str]] = None,
                  open_time_from: Optional[str] = None,
                  open_time_to: Optional[str] = None,
                  close_time_from: Optional[str] = None,
                  close_time_to: Optional[str] = None,
                  trade_date_from: Optional[str] = None,
                  trade_date_to: Optional[str] = None,
                  **kwargs) -> Iterator[List[Dict[str, Any]]]:
        """
        Get trades data with pagination.
        
        Args:
            trade_type: Type of trades ('closed' or 'open')
            logins: List of login IDs to filter
            symbols: List of symbols to filter
            open_time_from/to: Open time range in YYYYMMDD format
            close_time_from/to: Close time range in YYYYMMDD format (closed trades only)
            trade_date_from/to: Trade date range in YYYYMMDD format
            **kwargs: Additional parameters
            
        Yields:
            Lists of trade records
        """
        endpoint = f'v2/trades/{trade_type}'
        params = {}
        
        if logins:
            params['logins'] = ','.join(logins)
        if symbols:
            params['symbols'] = ','.join(symbols)
        
        # Date filters
        if open_time_from:
            params['open-time-from'] = open_time_from
        if open_time_to:
            params['open-time-to'] = open_time_to
        if close_time_from and trade_type == 'closed':
            params['close-time-from'] = close_time_from
        if close_time_to and trade_type == 'closed':
            params['close-time-to'] = close_time_to
        if trade_date_from:
            params['trade-date-from'] = trade_date_from
        if trade_date_to:
            params['trade-date-to'] = trade_date_to
        
        params.update(kwargs)
        
        # Max limit for trades endpoints is 1000
        yield from self.paginate(endpoint, params=params, limit=1000)
    
    def format_date(self, date: datetime) -> str:
        """Format date for API in YYYYMMDD format."""
        return date.strftime('%Y%m%d')
    
    def close(self):
        """Close the session."""
        self.session.close()
        logger.info("API client session closed")