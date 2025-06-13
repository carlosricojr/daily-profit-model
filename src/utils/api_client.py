"""
API client utilities for interacting with the risk analytics API endpoints.
Handles authentication, pagination, and rate limiting.
"""

import os
import time
import logging
import threading
from typing import Dict, List, Any, Optional, Iterator
from datetime import datetime
import requests
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from collections import defaultdict

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base class for API errors."""

    pass


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    pass


class APIClientError(APIError):
    """Client-side API error (4xx)."""

    pass


class APIServerError(APIError):
    """Server-side API error (5xx)."""

    pass


class CircuitBreaker:
    """Enhanced circuit breaker pattern with proper state management."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        self._lock = threading.RLock()

    def call_succeeded(self):
        """Record a successful call."""
        with self._lock:
            if self.failure_count > 0:
                logger.info("Circuit breaker reset after successful call")
            self.failure_count = 0
            self.state = "closed"

    def call_failed(self):
        """Record a failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.warning(
                    f"Circuit breaker opened after {self.failure_count} failures"
                )

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        with self._lock:
            if self.state == "closed":
                return False
            elif self.state == "open":
                # Check if recovery timeout has passed
                if (
                    self.last_failure_time
                    and (time.time() - self.last_failure_time) >= self.recovery_timeout
                ):
                    self.state = "half-open"
                    logger.info("Circuit breaker entering half-open state")
                    return False
                return True
            else:  # half-open
                return False

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        with self._lock:
            is_open = self.is_open()
            time_since_failure = (
                time.time() - self.last_failure_time if self.last_failure_time else 0
            )

            return {
                "state": self.state,
                "is_open": is_open,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "time_since_last_failure": time_since_failure,
                "timeout_remaining": max(0, self.recovery_timeout - time_since_failure)
                if is_open
                else 0,
            }


class TokenBucketRateLimiter:
    """Token bucket rate limiter for burst-capable rate limiting."""

    def __init__(self, tokens_per_second: float = 10, bucket_size: int = 20):
        """
        Initialize token bucket rate limiter.

        Args:
            tokens_per_second: Rate at which tokens are added
            bucket_size: Maximum number of tokens in bucket
        """
        self.tokens_per_second = tokens_per_second
        self.bucket_size = bucket_size
        self.tokens = bucket_size
        self.last_update = time.time()
        self._lock = threading.RLock()

    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False otherwise
        """
        with self._lock:
            now = time.time()
            time_passed = now - self.last_update

            # Add tokens based on time passed
            self.tokens = min(
                self.bucket_size, self.tokens + time_passed * self.tokens_per_second
            )
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_time(self, tokens: int = 1) -> float:
        """Calculate wait time to acquire tokens."""
        with self._lock:
            if self.tokens >= tokens:
                return 0.0

            needed_tokens = tokens - self.tokens
            return needed_tokens / self.tokens_per_second


class ConnectionPool:
    """Connection pool for managing HTTP sessions."""

    def __init__(
        self, pool_size: int = 10, max_retries: int = 3, backoff_factor: float = 1.0
    ):
        """
        Initialize connection pool.

        Args:
            pool_size: Maximum number of connections in pool
            max_retries: Maximum retry attempts
            backoff_factor: Backoff factor for retries
        """
        self.pool_size = pool_size
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._sessions = []
        self._stats = defaultdict(int)
        self._lock = threading.RLock()

        # Pre-create sessions
        for _ in range(pool_size):
            session = self._create_session()
            self._sessions.append(session)

    def _create_session(self) -> requests.Session:
        """Create a configured session with retry logic."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"],
            backoff_factor=self.backoff_factor,
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=20, pool_maxsize=20
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        session.headers.update(
            {
                "User-Agent": "DailyProfitModel/2.0",
                "Accept": "application/json",
                "Connection": "keep-alive",
            }
        )

        return session

    def get_session(self) -> requests.Session:
        """Get a session from the pool."""
        with self._lock:
            if self._sessions:
                session = self._sessions.pop()
                self._stats["sessions_acquired"] += 1
                return session
            else:
                # Pool exhausted, create temporary session
                self._stats["pool_exhausted"] += 1
                logger.warning("Connection pool exhausted, creating temporary session")
                return self._create_session()

    def return_session(self, session: requests.Session):
        """Return a session to the pool."""
        with self._lock:
            if len(self._sessions) < self.pool_size:
                self._sessions.append(session)
                self._stats["sessions_returned"] += 1
            else:
                # Pool full, close session
                session.close()
                self._stats["sessions_closed"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        with self._lock:
            return {
                "pool_size": self.pool_size,
                "available_sessions": len(self._sessions),
                "stats": dict(self._stats),
            }

    def close_all(self):
        """Close all sessions in the pool."""
        with self._lock:
            for session in self._sessions:
                session.close()
            self._sessions.clear()


class APIClient:
    """Alias for backward compatibility."""

    pass


class RiskAnalyticsAPIClient:
    """Enhanced API client with circuit breaker, connection pooling, and advanced rate limiting."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        requests_per_second: float = 15,
        burst_size: int = 20,
        pool_size: int = 10,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 60,
    ):
        """
        Initialize enhanced API client.

        Args:
            api_key: API key for authentication (defaults to env var RISK_API_KEY)
            base_url: Base URL for the API (defaults to env var RISK_API_BASE_URL)
            requests_per_second: Rate limit for requests
            burst_size: Maximum burst size for token bucket
            pool_size: Connection pool size
            max_retries: Maximum retry attempts
            backoff_factor: Backoff factor for retries
            circuit_breaker_threshold: Failure threshold for circuit breaker
            circuit_breaker_timeout: Circuit breaker timeout in seconds
        """
        self.api_key = api_key or os.getenv("RISK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key is required. Set RISK_API_KEY environment variable."
            )

        self.base_url = base_url or os.getenv(
            "RISK_API_BASE_URL",
            "https://easton.apis.arizet.io/risk-analytics/tft/external"
        )
        # Ensure base URL ends with /
        if not self.base_url.endswith('/'):
            self.base_url += '/'

        # Enhanced rate limiting with token bucket
        self.rate_limiter = TokenBucketRateLimiter(
            tokens_per_second=requests_per_second, bucket_size=burst_size
        )

        # Connection pooling for better performance
        self.connection_pool = ConnectionPool(
            pool_size=pool_size, max_retries=max_retries, backoff_factor=backoff_factor
        )

        # Circuit breaker for fault tolerance
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold,
            recovery_timeout=circuit_breaker_timeout,
        )

        # Enhanced statistics tracking
        self.total_requests = 0
        self.failed_requests = 0
        self.response_times = []
        self.error_counts = defaultdict(int)

        logger.info(f"Enhanced API client initialized for {self.base_url}")
        logger.info(f"API Key configured: {'Yes' if self.api_key else 'No'} (length: {len(self.api_key) if self.api_key else 0})")
        logger.info(
            f"Rate limit: {requests_per_second} req/s, Burst: {burst_size}, Pool: {pool_size}"
        )

    def _rate_limit(self):
        """Enhanced rate limiting using token bucket algorithm."""
        # Try to acquire a token
        if not self.rate_limiter.acquire():
            # Calculate wait time and sleep
            wait_time = self.rate_limiter.wait_time()
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)
                # Try again after waiting
                if not self.rate_limiter.acquire():
                    raise RateLimitError(
                        "Unable to acquire rate limit token after waiting"
                    )

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        Make an API request with connection pooling, circuit breaker, and enhanced error handling.

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            params: Query parameters
            data: Request body data
            timeout: Request timeout in seconds

        Returns:
            Response data as dictionary

        Raises:
            APIError: When circuit breaker is open or request fails
        """
        # Check circuit breaker
        if self.circuit_breaker.is_open():
            raise APIError("Circuit breaker is open - requests blocked")

        url = urljoin(self.base_url, endpoint)

        # Add API key as query parameter
        if params is None:
            params = {}
        params["apiKey"] = self.api_key

        # Log the request (hide API key in logs)
        log_params = {k: v for k, v in params.items() if k != "apiKey"}
        logger.info(f"API Request: {method} {url}", extra={
            "params": log_params,
            "has_request_body": data is not None,
            "full_url": f"{url}?{'&'.join([f'{k}={v}' for k, v in log_params.items()])}",
            "timeout": timeout
        })

        # Rate limiting
        self._rate_limit()

        # Update statistics
        self.total_requests += 1

        # Get session from connection pool
        session = self.connection_pool.get_session()
        start_time = time.time()

        try:
            response = session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=timeout,
            )

            # Record response time
            response_time = time.time() - start_time
            self.response_times.append(response_time)

            # Keep only last 1000 response times
            if len(self.response_times) > 1000:
                self.response_times = self.response_times[-1000:]

            # Log response details
            logger.info(
                f"API Response: {response.status_code} - Time: {response_time:.3f}s",
                extra={
                    "url": url,
                    "status_code": response.status_code,
                    "response_time": response_time,
                    "response_size": len(response.text) if response.text else 0,
                    "has_response_data": bool(response.text)
                }
            )

            # Enhanced error handling with specific exceptions
            if response.status_code == 429:  # Rate limit
                self.error_counts["rate_limit"] += 1
                retry_after = response.headers.get("Retry-After", "60")
                raise RateLimitError(
                    f"Rate limit exceeded. Retry after {retry_after} seconds"
                )

            elif 400 <= response.status_code < 500:  # Client errors
                self.error_counts["client_error"] += 1
                self.failed_requests += 1
                self.circuit_breaker.call_failed()
                error_msg = f"Client error {response.status_code}: {response.text}"
                raise APIClientError(error_msg)

            elif response.status_code >= 500:  # Server errors
                self.error_counts["server_error"] += 1
                self.failed_requests += 1
                self.circuit_breaker.call_failed()
                error_msg = f"Server error {response.status_code}: {response.text}"
                raise APIServerError(error_msg)

            # Check for successful response
            response.raise_for_status()

            # Success - record in circuit breaker
            self.circuit_breaker.call_succeeded()

            # Parse JSON response
            try:
                json_response = response.json()
                logger.debug(f"API JSON Response structure: {list(json_response.keys()) if isinstance(json_response, dict) else type(json_response)}")
                return json_response
            except ValueError as e:
                logger.error(f"Failed to parse JSON response: {e}, Response text: {response.text[:500]}")
                raise APIError(f"Invalid JSON response: {e}")

        except (RateLimitError, APIClientError, APIServerError):
            # Re-raise our custom exceptions
            raise

        except requests.exceptions.Timeout:
            self.error_counts["timeout"] += 1
            self.failed_requests += 1
            self.circuit_breaker.call_failed()
            raise APIError(f"Request timeout after {timeout} seconds")

        except requests.exceptions.ConnectionError as e:
            self.error_counts["connection_error"] += 1
            self.failed_requests += 1
            self.circuit_breaker.call_failed()
            raise APIError(f"Connection error: {str(e)}")

        except Exception as e:
            self.error_counts["unexpected_error"] += 1
            self.failed_requests += 1
            self.circuit_breaker.call_failed()
            raise APIError(f"Unexpected error: {str(e)}")

        finally:
            # Return session to pool
            self.connection_pool.return_session(session)

    def _validate_response(self, response: Dict[str, Any]) -> bool:
        """
        Validate API response status.

        Args:
            response: API response dictionary

        Returns:
            True if response is valid

        Raises:
            APIError: If response has error status
        """
        if not isinstance(response, dict):
            return False

        # Check for error status first (case-sensitive)
        status = response.get("Status", "")
        
        logger.debug(f"API response validation - Status: '{status}', Has Status field: {'Status' in response}")
        
        if status == "fail" or status == "error":
            error_msg = response.get("Error", response.get("Message", "Unknown error"))
            raise APIError(f"API error: {error_msg}")
        
        # If no Status field or Status is "ok", consider it valid
        # Many endpoints don't include a Status field when successful
        if not status or status == "ok":
            return True
        else:
            raise APIError(f"Unknown response status: {status}")

    def _extract_data_from_response(
        self, response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract data from various API response structures.

        Handles:
        - response['Data'] as a list (e.g., /accounts)
        - response['Data']['data'] as a list (e.g., paginated endpoints)
        - response['data'] as a list (legacy format)

        Args:
            response: API response dictionary

        Returns:
            List of data records
        """
        if not isinstance(response, dict):
            logger.warning(f"Response is not a dict: {type(response)}")
            return []

        # Check for 'Data' field (capital D)
        if "Data" in response:
            data_field = response["Data"]

            # If Data is a list, return it directly
            if isinstance(data_field, list):
                return data_field

            # If Data is a dict, look for nested 'data' field
            elif isinstance(data_field, dict) and "data" in data_field:
                return data_field["data"]

            # If Data is a dict without 'data', check if it's pagination metadata
            elif isinstance(data_field, dict):
                # Check if it looks like pagination metadata only
                if (
                    all(key in data_field for key in ["total", "skip", "limit"])
                    and "data" not in data_field
                ):
                    logger.warning(
                        "Response contains only pagination metadata, no data"
                    )
                    return []
                # Otherwise, wrap single record in a list
                return [data_field]

        # Check for lowercase 'data' field (legacy)
        elif "data" in response:
            data_field = response["data"]
            if isinstance(data_field, list):
                return data_field
            elif data_field is not None:
                return [data_field]

        logger.warning(
            f"Could not extract data from response. Keys: {list(response.keys())}, Sample: {str(response)[:300]}"
        )
        return []

    def _extract_pagination_metadata(self, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract pagination metadata from response.

        Args:
            response: API response dictionary

        Returns:
            Dictionary with total, skip, limit, count
        """
        metadata = {"total": None, "skip": 0, "limit": None, "count": 0}

        if not isinstance(response, dict):
            return metadata

        # Check if Data field contains pagination info
        if "Data" in response and isinstance(response["Data"], dict):
            data_field = response["Data"]
            metadata["total"] = data_field.get("total")
            metadata["skip"] = data_field.get("skip", 0)
            metadata["limit"] = data_field.get("limit")
            metadata["count"] = data_field.get("count", len(data_field.get("data", [])))

        return metadata

    def paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
        max_pages: Optional[int] = None,
        include_total: bool = True,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Enhanced pagination with termination.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            limit: Number of results per page
            max_pages: Maximum number of pages to fetch (optional)
            include_total: Whether to request total count metadata

        Yields:
            Lists of results from each page
        """
        if params is None:
            params = {}

        params["limit"] = limit
        params["skip"] = 0

        # Request total count if supported by endpoint
        if include_total:
            params["include-total"] = 1

        page = 0
        total_fetched = 0
        total_expected = None
        
        while max_pages is None or page < max_pages:
            logger.info(
                f"Fetching page {page + 1}, skip={params['skip']}, limit={limit}"
            )

            try:
                response = self._make_request(endpoint, params=params)

                # Validate response status
                self._validate_response(response)

                # Extract data from response
                results = self._extract_data_from_response(response)

                # Extract pagination metadata
                metadata = self._extract_pagination_metadata(response)

                # Update total if available
                if metadata["total"] is not None and total_expected is None:
                    total_expected = metadata["total"]
                    logger.info(f"Total records available: {total_expected}")

                # Track progress
                result_count = len(results)
                total_fetched += result_count
                
                logger.info(f"Page {page + 1}: Retrieved {result_count} records (total so far: {total_fetched})", extra={
                    "page_number": page + 1,
                    "records_this_page": result_count,
                    "total_records_fetched": total_fetched,
                    "has_data": result_count > 0
                })

                if not results:
                    logger.info("No results returned, stopping pagination")
                    break

                yield results

                # Termination conditions

                # 1. If we know the total and have fetched everything
                if total_expected is not None:
                    if total_fetched >= total_expected:
                        logger.info(f"Fetched all {total_expected} records")
                        break

                    # Also check skip + count >= total (server-side indication)
                    if metadata["skip"] + metadata["count"] >= total_expected:
                        logger.info(
                            f"Server indicates all data fetched (skip={metadata['skip']}, count={metadata['count']}, total={total_expected})"
                        )
                        break

                # 2. If we got fewer results than requested (traditional last page check)
                if result_count < limit:
                    logger.info(
                        f"Last page reached (got {result_count} results, expected {limit})"
                    )
                    break

                # 3. If the server explicitly returns count=0
                if metadata["count"] == 0:
                    logger.info("Server returned count=0, no more data")
                    break

                # Update pagination parameters
                params["skip"] += limit
                page += 1

                # Small delay between pages to be nice to the API
                time.sleep(0.1)

            except APIError as e:
                # API errors (including validation errors) should stop pagination
                logger.error(f"API error during pagination: {str(e)}")
                break
            except (APIClientError, APIServerError) as e:
                logger.error(f"Error during pagination: {str(e)}")
                # For client errors, stop pagination immediately
                if isinstance(e, APIClientError):
                    break
                # For server errors, the retry logic in _make_request should handle it
                # If we get here, all retries failed, so stop pagination
                break
            except Exception as e:
                logger.error(f"Unexpected error during pagination: {str(e)}")
                break

        logger.info(
            f"Pagination complete. Fetched {total_fetched} records in {page} pages"
        )

    def get_accounts(
        self,
        logins: Optional[List[str]] = None,
        traders: Optional[List[str]] = None,
        **kwargs,
    ) -> Iterator[List[Dict[str, Any]]]:
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
            params["logins"] = ",".join(logins)
        if traders:
            params["traders"] = ",".join(traders)
        params.update(kwargs)

        # Max limit for accounts endpoint is 500
        # Accounts endpoint doesn't support include-total
        yield from self.paginate(
            "accounts", params=params, limit=500, include_total=False
        )

    def get_metrics(
        self,
        metric_type: str,
        logins: Optional[List[str]] = None,
        account_ids: Optional[List[str]] = None,
        types: Optional[List[int]] = None,
        phases: Optional[List[int]] = None,
        providers: Optional[List[int]] = None,
        platforms: Optional[List[int]] = None,
        dates: Optional[List[str]] = None,
        hours: Optional[List[int]] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Get metrics data with pagination.

        Args:
            metric_type: Type of metrics ('alltime', 'daily', 'hourly')
            logins: List of login IDs to filter
            account_ids: List of account IDs to filter
            dates: List of dates in YYYYMMDD format
            hours: List of hours (0-23) for hourly metrics
            **kwargs: Additional parameters

        Yields:
            Lists of metrics records
        """
        endpoint = f"v2/metrics/{metric_type}"
        params = {}

        if logins:
            params["logins"] = ",".join(logins)
        if account_ids:
            params["accountIds"] = ",".join(account_ids)
        if types:
            params["types"] = ",".join(map(str, types))
        if phases:
            params["phases"] = ",".join(map(str, phases))
        if providers:
            params["providers"] = ",".join(map(str, providers))
        if platforms:
            params["platforms"] = ",".join(map(str, platforms))
        if dates and metric_type in ["hourly", "daily"]:
            params["dates"] = ",".join(dates)
        if hours and metric_type == "hourly":
            params["hours"] = ",".join(map(str, hours))
        params.update(kwargs)

        # Max limit for metrics endpoints is 1000, but can be overridden
        # Metrics endpoints support include-total
        api_limit = limit if limit is not None else 1000
        yield from self.paginate(
            endpoint, params=params, limit=api_limit, include_total=True
        )

    def get_trades(
        self,
        trade_type: str,
        logins: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        trade_date: Optional[str] = None,
        open_time_from: Optional[str] = None,
        open_time_to: Optional[str] = None,
        close_time_from: Optional[str] = None,
        close_time_to: Optional[str] = None,
        trade_date_from: Optional[str] = None,
        trade_date_to: Optional[str] = None,
        **kwargs,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Get trades data with pagination.

        Args:
            trade_type: Type of trades ('closed' or 'open')
            logins: List of login IDs to filter
            symbols: List of symbols to filter
            trade_date: Trade date in YYYYMMDD format
            open_time_from/to: Open time range in YYYYMMDD format
            close_time_from/to: Close time range in YYYYMMDD format (closed trades only)
            trade_date_from/to: Trade date range in YYYYMMDD format
            **kwargs: Additional parameters

        Yields:
            Lists of trade records
        """
        endpoint = f"v2/trades/{trade_type}"
        params = {}

        if logins:
            params["logins"] = ",".join(logins)
        if symbols:
            params["symbols"] = ",".join(symbols)

        # Date filters
        if trade_date:
            params["trade-date"] = trade_date
        if open_time_from:
            params["open-time-from"] = open_time_from
        if open_time_to:
            params["open-time-to"] = open_time_to
        if close_time_from and trade_type == "closed":
            params["close-time-from"] = close_time_from
        if close_time_to and trade_type == "closed":
            params["close-time-to"] = close_time_to
        if trade_date_from:
            params["trade-date-from"] = trade_date_from
        if trade_date_to:
            params["trade-date-to"] = trade_date_to

        params.update(kwargs)

        # Max limit for trades endpoints is 1000
        # Trades endpoints support include-total
        yield from self.paginate(
            endpoint, params=params, limit=1000, include_total=True
        )

    def format_date(self, date: datetime) -> str:
        """Format date for API in YYYYMMDD format."""
        return date.strftime("%Y%m%d")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive client statistics including performance metrics.

        Returns:
            Dictionary with detailed client statistics
        """
        success_rate = 0.0
        if self.total_requests > 0:
            success_rate = (
                (self.total_requests - self.failed_requests) / self.total_requests
            ) * 100

        avg_response_time = 0.0
        p95_response_time = 0.0
        p99_response_time = 0.0

        if self.response_times:
            avg_response_time = sum(self.response_times) / len(self.response_times)
            sorted_times = sorted(self.response_times)
            p95_idx = int(len(sorted_times) * 0.95)
            p99_idx = int(len(sorted_times) * 0.99)
            p95_response_time = (
                sorted_times[p95_idx] if p95_idx < len(sorted_times) else 0
            )
            p99_response_time = (
                sorted_times[p99_idx] if p99_idx < len(sorted_times) else 0
            )

        return {
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "success_rate": success_rate,
            "error_counts": dict(self.error_counts),
            "performance": {
                "avg_response_time_seconds": avg_response_time,
                "p95_response_time_seconds": p95_response_time,
                "p99_response_time_seconds": p99_response_time,
                "total_response_samples": len(self.response_times),
            },
            "circuit_breaker": self.circuit_breaker.get_status(),
            "circuit_breaker_state": self.circuit_breaker.state,
            "connection_pool": self.connection_pool.get_stats(),
            "rate_limiter": {
                "tokens_per_second": self.rate_limiter.tokens_per_second,
                "bucket_size": self.rate_limiter.bucket_size,
                "current_tokens": self.rate_limiter.tokens,
            },
        }

    def health_check(self) -> bool:
        """
        Perform a health check on the API.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Simple health check using accounts endpoint
            self._make_request("accounts", params={"limit": 1})
            logger.info("API health check passed")
            return True
        except Exception as e:
            logger.error(f"API health check failed: {str(e)}")
            return False

    def close(self):
        """Close all sessions and clean up resources."""
        try:
            # Close connection pool
            self.connection_pool.close_all()

            # Log final statistics
            final_stats = self.get_stats()
            logger.info(
                "API client closing",
                extra={
                    "extra_fields": {
                        "total_requests": final_stats["total_requests"],
                        "success_rate": final_stats["success_rate"],
                        "avg_response_time": final_stats["performance"][
                            "avg_response_time_seconds"
                        ],
                        "circuit_breaker_state": final_stats["circuit_breaker"][
                            "state"
                        ],
                    }
                },
            )

            logger.info("Enhanced API client closed successfully")

        except Exception as e:
            logger.error(f"Error during API client cleanup: {str(e)}")
