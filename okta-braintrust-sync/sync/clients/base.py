"""Base client with retry logic, error handling, and rate limiting."""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import httpx
import structlog
from asyncio_throttle import Throttler
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from sync.clients.exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    ClientError,
    ServerError,
    NetworkError,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class BaseAPIClient(ABC):
    """Abstract base class for API clients with common functionality."""
    
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = 30,
        rate_limit_per_minute: int = 600,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
        user_agent: Optional[str] = None,
    ) -> None:
        """Initialize the base API client.
        
        Args:
            base_url: Base URL for the API
            timeout_seconds: Request timeout in seconds
            rate_limit_per_minute: Maximum requests per minute
            max_retries: Maximum retry attempts for failed requests
            retry_delay_seconds: Initial delay between retries
            user_agent: Custom user agent string
        """
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        
        # Set up HTTP client
        headers = {
            "User-Agent": user_agent or self._get_default_user_agent(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers=headers,
            follow_redirects=True,
        )
        
        # Set up rate limiting
        self._throttler = Throttler(rate_limit=rate_limit_per_minute, period=60)
        
        # Request tracking for logging and debugging
        self._request_count = 0
        self._error_count = 0
        self._last_request_time: Optional[float] = None
        
        # Logger with client context
        self._logger = logger.bind(
            client_type=self.__class__.__name__,
            base_url=self.base_url,
        )
    
    async def __aenter__(self) -> "BaseAPIClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._client:
            await self._client.aclose()
        # asyncio-throttle doesn't have a close method, just let it be garbage collected
    
    @abstractmethod
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for requests.
        
        Returns:
            Dictionary of authentication headers
        """
        pass
    
    def _get_default_user_agent(self) -> str:
        """Get default user agent string."""
        from sync.version import __version__
        return f"okta-braintrust-sync/{__version__}"
    
    async def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make an HTTP request with rate limiting and error handling.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: API endpoint path (relative to base URL)
            params: Query parameters
            json_data: JSON request body
            headers: Additional headers
            
        Returns:
            HTTP response object
            
        Raises:
            APIError: If the request fails
        """
        # Apply rate limiting
        async with self._throttler:
            # Prepare request
            url = f"{self.base_url}/{path.lstrip('/')}"
            request_headers = self._get_auth_headers()
            if headers:
                request_headers.update(headers)
            
            self._request_count += 1
            self._last_request_time = time.time()
            
            request_id = f"req_{self._request_count}"
            
            self._logger.debug(
                "Making API request",
                request_id=request_id,
                method=method,
                url=url,
                params=params,
                has_json_data=json_data is not None,
            )
            
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=request_headers,
                )
                
                # Log response
                self._logger.debug(
                    "API request completed",
                    request_id=request_id,
                    status_code=response.status_code,
                    response_size=len(response.content),
                )
                
                # Handle different response status codes
                if response.is_success:
                    return response
                elif response.status_code == 401:
                    self._error_count += 1
                    raise AuthenticationError(
                        "Authentication failed",
                        status_code=response.status_code,
                        response_text=response.text,
                    )
                elif response.status_code == 429:
                    self._error_count += 1
                    raise RateLimitError(
                        "Rate limit exceeded",
                        status_code=response.status_code,
                        response_text=response.text,
                        retry_after=self._get_retry_after(response),
                    )
                elif 400 <= response.status_code < 500:
                    self._error_count += 1
                    raise ClientError(
                        f"Client error: {response.status_code}",
                        status_code=response.status_code,
                        response_text=response.text,
                    )
                elif 500 <= response.status_code < 600:
                    self._error_count += 1
                    raise ServerError(
                        f"Server error: {response.status_code}",
                        status_code=response.status_code,
                        response_text=response.text,
                    )
                else:
                    self._error_count += 1
                    raise APIError(
                        f"Unexpected status code: {response.status_code}",
                        status_code=response.status_code,
                        response_text=response.text,
                    )
                    
            except httpx.RequestError as e:
                self._error_count += 1
                self._logger.error(
                    "Network error during API request",
                    request_id=request_id,
                    error=str(e),
                )
                raise NetworkError(f"Network error: {e}") from e
            except Exception as e:
                self._error_count += 1
                self._logger.error(
                    "Unexpected error during API request",
                    request_id=request_id,
                    error=str(e),
                )
                raise APIError(f"Unexpected error: {e}") from e
    
    def _get_retry_after(self, response: httpx.Response) -> Optional[int]:
        """Extract retry-after value from response headers.
        
        Args:
            response: HTTP response
            
        Returns:
            Retry-after value in seconds, or None if not present
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                pass
        return None
    
    async def with_retry(
        self,
        operation_name: str,
        operation: Callable[[], T],
        retry_on_rate_limit: bool = True,
    ) -> T:
        """Execute an operation with automatic retry logic.
        
        Args:
            operation_name: Name of the operation for logging
            operation: Callable to execute
            retry_on_rate_limit: Whether to retry on rate limit errors
            
        Returns:
            Result of the operation
            
        Raises:
            APIError: If the operation fails after all retries
        """
        retry_conditions = [
            retry_if_exception_type(ServerError),
            retry_if_exception_type(NetworkError),
        ]
        
        if retry_on_rate_limit:
            retry_conditions.append(retry_if_exception_type(RateLimitError))
        
        try:
            async for attempt in Retrying(
                stop=stop_after_attempt(self.max_retries + 1),
                wait=wait_exponential(
                    multiplier=self.retry_delay_seconds,
                    min=self.retry_delay_seconds,
                    max=60,
                ),
                retry=retry_if_exception_type(tuple([
                    ServerError,
                    NetworkError,
                    RateLimitError if retry_on_rate_limit else type(None)
                ])),
                reraise=True,
            ):
                with attempt:
                    self._logger.debug(
                        "Executing operation with retry",
                        operation=operation_name,
                        attempt_number=attempt.retry_state.attempt_number,
                    )
                    
                    # Handle rate limit delays
                    if (attempt.retry_state.outcome and 
                        isinstance(attempt.retry_state.outcome.exception(), RateLimitError)):
                        rate_limit_error = attempt.retry_state.outcome.exception()
                        if rate_limit_error.retry_after:
                            self._logger.info(
                                "Rate limit hit, waiting before retry",
                                operation=operation_name,
                                retry_after=rate_limit_error.retry_after,
                            )
                            await asyncio.sleep(rate_limit_error.retry_after)
                    
                    if asyncio.iscoroutinefunction(operation):
                        return await operation()
                    else:
                        return operation()
                        
        except Exception as e:
            self._logger.error(
                "Operation failed after all retries",
                operation=operation_name,
                error=str(e),
                error_type=type(e).__name__,
                attempts=self.max_retries + 1,
            )
            raise
    
    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make a GET request.
        
        Args:
            path: API endpoint path
            params: Query parameters
            headers: Additional headers
            
        Returns:
            HTTP response
        """
        return await self._make_request("GET", path, params=params, headers=headers)
    
    async def post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make a POST request.
        
        Args:
            path: API endpoint path
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers
            
        Returns:
            HTTP response
        """
        return await self._make_request(
            "POST", path, params=params, json_data=json_data, headers=headers
        )
    
    async def put(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make a PUT request.
        
        Args:
            path: API endpoint path
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers
            
        Returns:
            HTTP response
        """
        return await self._make_request(
            "PUT", path, params=params, json_data=json_data, headers=headers
        )
    
    async def patch(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make a PATCH request.
        
        Args:
            path: API endpoint path
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers
            
        Returns:
            HTTP response
        """
        return await self._make_request(
            "PATCH", path, params=params, json_data=json_data, headers=headers
        )
    
    async def delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make a DELETE request.
        
        Args:
            path: API endpoint path
            params: Query parameters
            headers: Additional headers
            
        Returns:
            HTTP response
        """
        return await self._make_request("DELETE", path, params=params, headers=headers)
    
    async def get_json(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a GET request and return JSON response.
        
        Args:
            path: API endpoint path
            params: Query parameters
            headers: Additional headers
            
        Returns:
            JSON response data
            
        Raises:
            APIError: If response is not valid JSON
        """
        response = await self.get(path, params=params, headers=headers)
        try:
            return response.json()
        except Exception as e:
            raise APIError(f"Failed to parse JSON response: {e}") from e
    
    async def post_json(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a POST request and return JSON response.
        
        Args:
            path: API endpoint path
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers
            
        Returns:
            JSON response data
            
        Raises:
            APIError: If response is not valid JSON
        """
        response = await self.post(path, json_data=json_data, params=params, headers=headers)
        try:
            return response.json()
        except Exception as e:
            raise APIError(f"Failed to parse JSON response: {e}") from e
    
    async def paginate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Paginate through all results for an endpoint.
        
        This is an abstract method that should be implemented by subclasses
        based on their specific pagination mechanisms.
        
        Args:
            path: API endpoint path
            params: Query parameters
            limit: Maximum number of items to retrieve
            
        Returns:
            List of all items from all pages
        """
        raise NotImplementedError("Subclasses must implement pagination logic")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics for monitoring.
        
        Returns:
            Dictionary with client statistics
        """
        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(self._request_count, 1),
            "last_request_time": self._last_request_time,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "base_url": self.base_url,
        }
    
    async def health_check(self) -> bool:
        """Perform a basic health check against the API.
        
        This is an abstract method that should be implemented by subclasses.
        
        Returns:
            True if the API is healthy, False otherwise
        """
        raise NotImplementedError("Subclasses must implement health check logic")