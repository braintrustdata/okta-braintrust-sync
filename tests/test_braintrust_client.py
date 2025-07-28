"""Tests for Braintrust client functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import SecretStr

from sync.clients.braintrust import BraintrustClient
from sync.clients.exceptions import BraintrustError, ResourceNotFoundError


@pytest.fixture
def mock_braintrust():
    """Mock braintrust API client."""
    with patch('sync.clients.braintrust.Braintrust') as mock:
        yield mock


@pytest.fixture
def braintrust_client(mock_braintrust):
    """Create a test Braintrust client."""
    api_key = SecretStr("test-api-key")
    client = BraintrustClient(
        api_key=api_key,
        api_url="https://api.braintrust.dev",
        timeout_seconds=10,
        rate_limit_per_minute=100,
    )
    return client


class TestBraintrustClientInit:
    """Test Braintrust client initialization."""
    
    def test_init_with_defaults(self, mock_braintrust):
        """Test client initialization with default values."""
        api_key = SecretStr("test-key")
        client = BraintrustClient(api_key=api_key)
        
        assert client.api_url == "https://api.braintrust.dev"
        assert client.timeout_seconds == 30
        assert client.rate_limit_per_minute == 300
        assert client.max_retries == 3
        assert client.retry_delay_seconds == 1.0
        
        # Check that Braintrust client was initialized correctly
        mock_braintrust.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.braintrust.dev",
            timeout=30,
        )
    
    def test_init_with_custom_values(self, mock_braintrust):
        """Test client initialization with custom values."""
        api_key = SecretStr("custom-key")
        client = BraintrustClient(
            api_key=api_key,
            api_url="https://custom.braintrust.dev",
            timeout_seconds=60,
            rate_limit_per_minute=600,
            max_retries=5,
            retry_delay_seconds=2.0,
        )
        
        assert client.api_url == "https://custom.braintrust.dev"
        assert client.timeout_seconds == 60
        assert client.rate_limit_per_minute == 600
        assert client.max_retries == 5
        assert client.retry_delay_seconds == 2.0
        
        mock_braintrust.assert_called_once_with(
            api_key="custom-key",
            base_url="https://custom.braintrust.dev",
            timeout=60,
        )


class TestBraintrustClientContext:
    """Test async context manager functionality."""
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self, braintrust_client):
        """Test async context manager behavior."""
        async with braintrust_client as client:
            assert client is braintrust_client
            # Client should be usable within context
            assert client._request_count == 0
        
        # Client should be closed after context


class TestBraintrustClientHealthCheck:
    """Test health check functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, braintrust_client):
        """Test successful health check."""
        # Mock organization info retrieval
        mock_org_info = MagicMock()
        mock_org_info.model_dump.return_value = {"id": "test-org", "name": "Test Org"}
        braintrust_client.client.organizations.retrieve = AsyncMock(return_value=mock_org_info)
        
        result = await braintrust_client.health_check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, braintrust_client):
        """Test failed health check."""
        braintrust_client.client.organizations.retrieve = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        
        result = await braintrust_client.health_check()
        assert result is False


class TestBraintrustClientUsers:
    """Test user management methods."""
    
    @pytest.mark.asyncio
    async def test_get_user_success(self, braintrust_client):
        """Test successful user retrieval."""
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.name = "Test User"
        braintrust_client.client.users.retrieve = AsyncMock(return_value=mock_user)
        
        user = await braintrust_client.get_user("user-123")
        assert user == mock_user
        assert braintrust_client._request_count == 1
        braintrust_client.client.users.retrieve.assert_called_once_with("user-123")
    
    @pytest.mark.asyncio
    async def test_get_user_not_found(self, braintrust_client):
        """Test user not found error."""
        error = Exception("User not found")
        braintrust_client.client.users.retrieve = AsyncMock(side_effect=error)
        
        # Mock the not found detection
        with patch.object(braintrust_client, '_is_not_found_error', return_value=True):
            with pytest.raises(ResourceNotFoundError, match="User not found: user-123"):
                await braintrust_client.get_user("user-123")
    
    @pytest.mark.asyncio
    async def test_list_users(self, braintrust_client):
        """Test user listing."""
        mock_users = [MagicMock(), MagicMock()]
        mock_response = MagicMock()
        mock_response.data = mock_users
        braintrust_client.client.users.list = AsyncMock(return_value=mock_response)
        
        users = await braintrust_client.list_users(limit=10)
        assert users == mock_users
        braintrust_client.client.users.list.assert_called_once_with(
            limit=10, starting_after=None
        )
    
    @pytest.mark.asyncio
    async def test_create_user(self, braintrust_client):
        """Test user creation."""
        mock_user = MagicMock()
        mock_user.id = "new-user-123"
        braintrust_client.client.users.create = AsyncMock(return_value=mock_user)
        
        user = await braintrust_client.create_user(
            given_name="John",
            family_name="Doe",
            email="john.doe@example.com",
            additional_fields={"department": "Engineering"}
        )
        
        assert user == mock_user
        braintrust_client.client.users.create.assert_called_once_with(
            given_name="John",
            family_name="Doe",
            email="john.doe@example.com",
            department="Engineering"
        )
    
    @pytest.mark.asyncio
    async def test_update_user(self, braintrust_client):
        """Test user update."""
        mock_user = MagicMock()
        mock_user.id = "user-123"
        braintrust_client.client.users.update = AsyncMock(return_value=mock_user)
        
        updates = {"given_name": "Jane", "department": "Marketing"}
        user = await braintrust_client.update_user("user-123", updates)
        
        assert user == mock_user
        braintrust_client.client.users.update.assert_called_once_with(
            "user-123", **updates
        )
    
    @pytest.mark.asyncio
    async def test_find_user_by_email(self, braintrust_client):
        """Test finding user by email."""
        mock_user1 = MagicMock()
        mock_user1.email = "user1@example.com"
        mock_user2 = MagicMock()
        mock_user2.email = "user2@example.com"
        
        braintrust_client.list_users = AsyncMock(return_value=[mock_user1, mock_user2])
        
        # Test finding existing user
        user = await braintrust_client.find_user_by_email("user2@example.com")
        assert user == mock_user2
        
        # Test user not found
        user = await braintrust_client.find_user_by_email("nonexistent@example.com")
        assert user is None


class TestBraintrustClientGroups:
    """Test group management methods."""
    
    @pytest.mark.asyncio
    async def test_get_group_success(self, braintrust_client):
        """Test successful group retrieval."""
        mock_group = MagicMock()
        mock_group.id = "group-123"
        mock_group.name = "Test Group"
        braintrust_client.client.groups.retrieve = AsyncMock(return_value=mock_group)
        
        group = await braintrust_client.get_group("group-123")
        assert group == mock_group
        braintrust_client.client.groups.retrieve.assert_called_once_with("group-123")
    
    @pytest.mark.asyncio
    async def test_list_groups(self, braintrust_client):
        """Test group listing."""
        mock_groups = [MagicMock(), MagicMock()]
        mock_response = MagicMock()
        mock_response.data = mock_groups
        braintrust_client.client.groups.list = AsyncMock(return_value=mock_response)
        
        groups = await braintrust_client.list_groups()
        assert groups == mock_groups
        braintrust_client.client.groups.list.assert_called_once_with(
            limit=None, starting_after=None
        )
    
    @pytest.mark.asyncio
    async def test_create_group(self, braintrust_client):
        """Test group creation."""
        mock_group = MagicMock()
        mock_group.id = "new-group-123"
        braintrust_client.client.groups.create = AsyncMock(return_value=mock_group)
        
        group = await braintrust_client.create_group(
            name="Engineering Team",
            description="All engineers",
            member_users=["user1", "user2"],
            member_groups=["subgroup1"]
        )
        
        assert group == mock_group
        braintrust_client.client.groups.create.assert_called_once_with(
            name="Engineering Team",
            description="All engineers",
            member_users=["user1", "user2"],
            member_groups=["subgroup1"]
        )
    
    @pytest.mark.asyncio
    async def test_add_group_members(self, braintrust_client):
        """Test adding group members."""
        # Mock current group
        mock_current_group = MagicMock()
        mock_current_group.member_users = ["existing-user"]
        mock_current_group.member_groups = ["existing-group"]
        
        # Mock updated group
        mock_updated_group = MagicMock()
        mock_updated_group.id = "group-123"
        
        braintrust_client.get_group = AsyncMock(return_value=mock_current_group)
        braintrust_client.update_group = AsyncMock(return_value=mock_updated_group)
        
        result = await braintrust_client.add_group_members(
            "group-123",
            user_ids=["new-user"],
            group_ids=["new-group"]
        )
        
        assert result == mock_updated_group
        
        # Verify update was called with merged members
        expected_updates = {
            'member_users': ['existing-user', 'new-user'],
            'member_groups': ['existing-group', 'new-group']
        }
        braintrust_client.update_group.assert_called_once_with("group-123", expected_updates)
    
    @pytest.mark.asyncio
    async def test_find_group_by_name(self, braintrust_client):
        """Test finding group by name."""
        mock_group1 = MagicMock()
        mock_group1.name = "Group One"
        mock_group2 = MagicMock()
        mock_group2.name = "Group Two"
        
        braintrust_client.list_groups = AsyncMock(return_value=[mock_group1, mock_group2])
        
        # Test finding existing group
        group = await braintrust_client.find_group_by_name("Group Two")
        assert group == mock_group2
        
        # Test group not found
        group = await braintrust_client.find_group_by_name("Nonexistent Group")
        assert group is None


class TestBraintrustClientUtilities:
    """Test utility methods."""
    
    def test_is_not_found_error(self, braintrust_client):
        """Test not found error detection."""
        # Test with "not found" message
        error1 = Exception("User not found")
        assert braintrust_client._is_not_found_error(error1) is True
        
        # Test with "404" status
        error2 = Exception("HTTP 404 error")
        assert braintrust_client._is_not_found_error(error2) is True
        
        # Test with other error
        error3 = Exception("Connection timeout")
        assert braintrust_client._is_not_found_error(error3) is False
    
    def test_convert_to_braintrust_error(self, braintrust_client):
        """Test error conversion."""
        original_error = Exception("Test error")
        braintrust_error = braintrust_client._convert_to_braintrust_error(original_error)
        
        assert isinstance(braintrust_error, BraintrustError)
        assert str(braintrust_error) == "Test error"
    
    def test_get_stats(self, braintrust_client):
        """Test client statistics."""
        braintrust_client._request_count = 10
        braintrust_client._error_count = 2
        
        stats = braintrust_client.get_stats()
        
        assert stats["request_count"] == 10
        assert stats["error_count"] == 2
        assert stats["error_rate"] == 0.2
        assert stats["api_url"] == "https://api.braintrust.dev"
        assert stats["rate_limit_per_minute"] == 100