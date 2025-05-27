"""Unit tests for the BraintrustClient wrapper."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from braintrust_api import AsyncBraintrust

from braintrust_migrate.client import BraintrustClient, BraintrustConnectionError
from braintrust_migrate.config import BraintrustOrgConfig, MigrationConfig

# Test constants
EXPECTED_HEALTH_CHECK_CALLS = 2  # Once during connect(), once explicitly
EXPECTED_TIMEOUT_SECONDS = 30.0


@pytest.fixture
def org_config():
    """Create a test organization configuration."""
    return BraintrustOrgConfig(
        api_key="test-api-key", url="https://test.braintrust.dev"
    )


@pytest.fixture
def migration_config():
    """Create a test migration configuration."""
    return MigrationConfig(
        batch_size=50,
        max_retries=3,
        retry_delay=1.0,
        timeout=30.0,
    )


@pytest.fixture
def mock_braintrust_client():
    """Create a mock Braintrust client."""
    client = Mock(spec=AsyncBraintrust)
    client.projects = Mock()
    client.projects.list = AsyncMock()
    client.datasets = AsyncMock()
    client.prompts = AsyncMock()
    client.tools = AsyncMock()
    client.functions = AsyncMock()
    client.experiments = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.mark.asyncio
class TestBraintrustClient:
    """Test the BraintrustClient wrapper."""

    async def test_initialization(self, org_config, migration_config):
        """Test client initialization."""
        client = BraintrustClient(org_config, migration_config, "test-org")

        assert client.org_config == org_config
        assert client.migration_config == migration_config
        assert client.org_name == "test-org"
        assert client._client is None
        assert client._http_client is None

    async def test_context_manager(
        self, org_config, migration_config, mock_braintrust_client
    ):
        """Test async context manager behavior."""
        with patch("braintrust_migrate.client.AsyncBraintrust") as mock_bt:
            mock_bt.return_value = mock_braintrust_client

            async with BraintrustClient(
                org_config, migration_config, "test-org"
            ) as client:
                assert client.client == mock_braintrust_client

            mock_braintrust_client.close.assert_called_once()

    async def test_health_check_success(self, org_config, migration_config):
        """Test successful health check."""
        with patch("braintrust_migrate.client.AsyncBraintrust") as mock_bt:
            mock_client = Mock(spec=AsyncBraintrust)
            mock_client.projects = Mock()
            mock_client.projects.list = AsyncMock(return_value=[])
            mock_bt.return_value = mock_client

            client = BraintrustClient(org_config, migration_config, "test-org")
            await client.connect()

            result = await client.health_check()

            assert result["status"] == "healthy"
            assert result["projects_accessible"] is True
            # Health check is called once during connect() and once explicitly
            assert mock_client.projects.list.call_count == EXPECTED_HEALTH_CHECK_CALLS

    async def test_health_check_failure(self, org_config, migration_config):
        """Test health check failure."""
        with patch("braintrust_migrate.client.AsyncBraintrust") as mock_bt:
            mock_client = Mock(spec=AsyncBraintrust)
            mock_client.projects = Mock()
            mock_client.projects.list = AsyncMock(side_effect=Exception("API Error"))
            mock_bt.return_value = mock_client

            client = BraintrustClient(org_config, migration_config, "test-org")
            client._client = mock_client  # Set directly to bypass connect()

            with pytest.raises(BraintrustConnectionError):
                await client.health_check()

    async def test_http_client_configuration(self, org_config, migration_config):
        """Test HTTP client is properly configured."""
        with patch("braintrust_migrate.client.AsyncBraintrust") as mock_bt:
            mock_client = Mock(spec=AsyncBraintrust)
            mock_client.projects = Mock()
            mock_client.projects.list = AsyncMock(return_value=[])
            mock_bt.return_value = mock_client

            client = BraintrustClient(org_config, migration_config, "test-org")
            await client.connect()

            # Check HTTP client configuration
            assert isinstance(client._http_client, httpx.AsyncClient)
            # httpx.Timeout doesn't have a 'total' attribute, check timeout property
            assert client._http_client.timeout.connect == EXPECTED_TIMEOUT_SECONDS
            # Note: httpx.AsyncClient doesn't expose limits as a public attribute
            # The limits are set during construction but not accessible for testing

    async def test_client_property_not_connected(self, org_config, migration_config):
        """Test that client property raises error when not connected."""
        client = BraintrustClient(org_config, migration_config, "test-org")

        with pytest.raises(BraintrustConnectionError, match="Not connected"):
            _ = client.client

    async def test_with_retry(self, org_config, migration_config):
        """Test the with_retry method."""
        client = BraintrustClient(org_config, migration_config, "test-org")

        # Mock a successful operation
        async def mock_operation():
            return "success"

        result = await client.with_retry("test_operation", mock_operation)
        assert result == "success"
