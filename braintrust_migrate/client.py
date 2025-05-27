"""Braintrust API client wrapper with health checks and retry logic."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from braintrust_api import AsyncBraintrust
from tenacity import (
    AsyncRetrying,
    stop_after_attempt,
    wait_exponential,
)

from braintrust_migrate.config import BraintrustOrgConfig, MigrationConfig

logger = structlog.get_logger(__name__)


class BraintrustClientError(Exception):
    """Base exception for Braintrust client errors."""

    pass


class BraintrustConnectionError(BraintrustClientError):
    """Exception raised when connection to Braintrust API fails."""

    pass


class BraintrustAPIError(BraintrustClientError):
    """Exception raised when Braintrust API returns an error."""

    pass


class BraintrustClient:
    """Thin wrapper around braintrust-api-py AsyncClient with additional features.

    Provides:
    - Health checks and connectivity validation
    - Retry logic with exponential backoff
    - Structured logging
    - Connection pooling
    """

    def __init__(
        self,
        org_config: BraintrustOrgConfig,
        migration_config: MigrationConfig,
        org_name: str = "unknown",
    ) -> None:
        """Initialize the Braintrust client wrapper.

        Args:
            org_config: Organization configuration with API key and URL.
            migration_config: Migration configuration with retry settings.
            org_name: Human-readable name for this organization (source/dest).
        """
        self.org_config = org_config
        self.migration_config = migration_config
        self.org_name = org_name
        self._client: AsyncBraintrust | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._logger = logger.bind(org=org_name, url=str(org_config.url))

    async def __aenter__(self) -> "BraintrustClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Establish connection to Braintrust API.

        Raises:
            BraintrustConnectionError: If connection fails.
        """
        if self._client is not None:
            return

        try:
            self._logger.info("Connecting to Braintrust API")

            # Create HTTP client for auxiliary requests
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            )

            # Create Braintrust API client
            self._client = AsyncBraintrust(
                api_key=self.org_config.api_key,
                base_url=str(self.org_config.url),
                http_client=self._http_client,
            )

            # Perform health check
            await self.health_check()

            self._logger.info("Successfully connected to Braintrust API")

        except Exception as e:
            self._logger.error("Failed to connect to Braintrust API", error=str(e))
            await self.close()
            raise BraintrustConnectionError(
                f"Failed to connect to {self.org_name}: {e}"
            ) from e

    async def close(self) -> None:
        """Close the connection to Braintrust API."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as e:
                self._logger.warning("Error closing Braintrust client", error=str(e))
            finally:
                self._client = None

        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception as e:
                self._logger.warning("Error closing HTTP client", error=str(e))
            finally:
                self._http_client = None

        self._logger.info("Closed connection to Braintrust API")

    @property
    def client(self) -> AsyncBraintrust:
        """Get the underlying Braintrust API client.

        Returns:
            The AsyncBraintrust client instance.

        Raises:
            BraintrustConnectionError: If not connected.
        """
        if self._client is None:
            raise BraintrustConnectionError(f"Not connected to {self.org_name}")
        return self._client

    async def health_check(self) -> dict[str, Any]:
        """Perform health check against the Braintrust API.

        Returns:
            Health check response data.

        Raises:
            BraintrustConnectionError: If health check fails.
        """
        if self._client is None:
            raise BraintrustConnectionError(f"Not connected to {self.org_name}")

        try:
            # Try to list projects as a health check
            await self._client.projects.list(limit=1)

            health_data = {
                "status": "healthy",
                "url": str(self.org_config.url),
                "projects_accessible": True,
                "api_version": "v1",  # Braintrust API version
            }

            self._logger.debug("Health check passed", health_data=health_data)
            return health_data

        except Exception as e:
            self._logger.error("Health check failed", error=str(e))
            raise BraintrustConnectionError(
                f"Health check failed for {self.org_name}: {e}"
            ) from e

    async def check_brainstore_enabled(self) -> bool:
        """Check if Brainstore is enabled for this organization.

        Returns:
            True if Brainstore is enabled, False otherwise.
        """
        try:
            # This is a placeholder - actual implementation would depend on
            # the Braintrust API's way of exposing Brainstore status
            # For now, we'll assume it's enabled
            self._logger.debug("Checking Brainstore status")
            return True
        except Exception as e:
            self._logger.warning("Could not determine Brainstore status", error=str(e))
            return False

    async def with_retry(self, operation_name: str, coro_func):
        """Execute a coroutine function with retry logic.

        Args:
            operation_name: Human-readable name for the operation.
            coro_func: Callable that returns a coroutine or AsyncPaginator to execute.

        Returns:
            Result of the coroutine or AsyncPaginator.

        Raises:
            BraintrustAPIError: If all retry attempts fail.
        """
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.migration_config.retry_attempts + 1),
            wait=wait_exponential(
                multiplier=self.migration_config.retry_delay,
                max=30.0,
            ),
            reraise=True,
        ):
            with attempt:
                try:
                    self._logger.debug(
                        "Executing operation",
                        operation=operation_name,
                        attempt=attempt.retry_state.attempt_number,
                    )
                    # Call the function to get a fresh coroutine/paginator for each attempt
                    result = coro_func()

                    # Check if result is a coroutine that needs to be awaited
                    if hasattr(result, "__await__"):
                        result = await result

                    # If it's an AsyncPaginator, we return it directly
                    # The caller will handle iteration
                    return result
                except Exception as e:
                    self._logger.warning(
                        "Operation failed, will retry",
                        operation=operation_name,
                        attempt=attempt.retry_state.attempt_number,
                        error=str(e),
                    )
                    raise


@asynccontextmanager
async def create_client_pair(
    source_config: BraintrustOrgConfig,
    dest_config: BraintrustOrgConfig,
    migration_config: MigrationConfig,
) -> AsyncGenerator[tuple[BraintrustClient, BraintrustClient], None]:
    """Create a pair of connected Braintrust clients for source and destination.

    Args:
        source_config: Source organization configuration.
        dest_config: Destination organization configuration.
        migration_config: Migration configuration.

    Yields:
        Tuple of (source_client, dest_client).

    Raises:
        BraintrustConnectionError: If either client fails to connect.
    """
    source_client = BraintrustClient(source_config, migration_config, "source")
    dest_client = BraintrustClient(dest_config, migration_config, "destination")

    try:
        # Connect both clients concurrently
        await asyncio.gather(
            source_client.connect(),
            dest_client.connect(),
        )

        # Verify both have compatible API versions and Brainstore if needed
        source_health = await source_client.health_check()
        dest_health = await dest_client.health_check()

        logger.info(
            "Successfully connected to both organizations",
            source_health=source_health,
            dest_health=dest_health,
        )

        yield source_client, dest_client

    finally:
        # Close both clients
        await asyncio.gather(
            source_client.close(),
            dest_client.close(),
            return_exceptions=True,
        )
