"""Tests for UserSyncer functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from braintrust_api.types import User as BraintrustUser

from sync.clients.okta import OktaUser
from sync.core.state import StateManager, ResourceMapping
from sync.resources.users import UserSyncer
from sync.resources.base import SyncAction


# Mock data classes
class MockOktaProfile:
    def __init__(self, email: str, firstName: str, lastName: str, **kwargs):
        self.email = email
        self.firstName = firstName
        self.lastName = lastName
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockOktaUser:
    def __init__(self, id: str, email: str, firstName: str, lastName: str, status: str = "ACTIVE", **profile_attrs):
        self.id = id
        self.status = status
        self.profile = MockOktaProfile(email=email, firstName=firstName, lastName=lastName, **profile_attrs)
        self.groups = []


class MockBraintrustUser:
    def __init__(self, id: str, email: str, given_name: str, family_name: str):
        self.id = id
        self.email = email
        self.given_name = given_name
        self.family_name = family_name


@pytest.fixture
def mock_clients():
    """Create mock clients."""
    okta_client = MagicMock()
    braintrust_clients = {
        "org1": MagicMock(),
        "org2": MagicMock(),
    }
    return okta_client, braintrust_clients


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    state_manager = MagicMock(spec=StateManager)
    mock_state = MagicMock()
    mock_state.get_mapping.return_value = None
    mock_state.add_mapping = MagicMock()
    state_manager.get_current_state.return_value = mock_state
    return state_manager


@pytest.fixture
def user_syncer(mock_clients, mock_state_manager):
    """Create UserSyncer instance."""
    okta_client, braintrust_clients = mock_clients
    return UserSyncer(
        okta_client=okta_client,
        braintrust_clients=braintrust_clients,
        state_manager=mock_state_manager,
        identity_mapping_strategy="email",
    )


class TestUserSyncerInit:
    """Test UserSyncer initialization."""
    
    def test_init_with_defaults(self, mock_clients, mock_state_manager):
        """Test initialization with default parameters."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
        )
        
        assert syncer.resource_type == "user"
        assert syncer.identity_mapping_strategy == "email"
        assert syncer.custom_field_mappings == {}
    
    def test_init_with_custom_options(self, mock_clients, mock_state_manager):
        """Test initialization with custom parameters."""
        okta_client, braintrust_clients = mock_clients
        custom_mappings = {"department": "dept", "title": "job_title"}
        
        syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            identity_mapping_strategy="custom_field",
            custom_field_mappings=custom_mappings,
        )
        
        assert syncer.identity_mapping_strategy == "custom_field"
        assert syncer.custom_field_mappings == custom_mappings


class TestUserSyncerResourceOperations:
    """Test resource CRUD operations."""
    
    @pytest.mark.asyncio
    async def test_get_okta_resources(self, user_syncer):
        """Test retrieving Okta users."""
        mock_users = [
            MockOktaUser("1", "user1@example.com", "John", "Doe"),
            MockOktaUser("2", "user2@example.com", "Jane", "Smith"),
        ]
        
        user_syncer.okta_client.search_users = AsyncMock(return_value=mock_users)
        user_syncer.okta_client.list_users = AsyncMock(return_value=mock_users)
        
        # Test with filter
        result = await user_syncer.get_okta_resources(filter_expr="status eq \"ACTIVE\"")
        assert len(result) == 2
        user_syncer.okta_client.search_users.assert_called_once_with("status eq \"ACTIVE\"", limit=None)
        
        # Test without filter
        result = await user_syncer.get_okta_resources()
        assert len(result) == 2
        user_syncer.okta_client.list_users.assert_called_once_with(limit=None)
    
    @pytest.mark.asyncio
    async def test_get_braintrust_resources(self, user_syncer):
        """Test retrieving Braintrust users."""
        mock_users = [
            MockBraintrustUser("bt1", "user1@example.com", "John", "Doe"),
            MockBraintrustUser("bt2", "user2@example.com", "Jane", "Smith"),
        ]
        
        user_syncer.braintrust_clients["org1"].list_users = AsyncMock(return_value=mock_users)
        
        result = await user_syncer.get_braintrust_resources("org1")
        assert len(result) == 2
        user_syncer.braintrust_clients["org1"].list_users.assert_called_once_with(limit=None)
    
    @pytest.mark.asyncio
    async def test_get_braintrust_resources_invalid_org(self, user_syncer):
        """Test retrieving from invalid organization."""
        with pytest.raises(ValueError, match="No Braintrust client configured for org: invalid_org"):
            await user_syncer.get_braintrust_resources("invalid_org")
    
    @pytest.mark.asyncio
    async def test_create_braintrust_resource(self, user_syncer):
        """Test creating Braintrust user."""
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe")
        created_user = MockBraintrustUser("bt1", "user1@example.com", "John", "Doe")
        
        user_syncer.braintrust_clients["org1"].create_user = AsyncMock(return_value=created_user)
        
        result = await user_syncer.create_braintrust_resource(okta_user, "org1")
        
        assert result == created_user
        user_syncer.braintrust_clients["org1"].create_user.assert_called_once_with(
            given_name="John",
            family_name="Doe",
            email="user1@example.com",
            additional_fields=None,
        )
    
    @pytest.mark.asyncio
    async def test_create_braintrust_resource_with_additional_data(self, user_syncer):
        """Test creating Braintrust user with additional data."""
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe")
        created_user = MockBraintrustUser("bt1", "user1@example.com", "John", "Doe")
        additional_data = {"department": "Engineering"}
        
        user_syncer.braintrust_clients["org1"].create_user = AsyncMock(return_value=created_user)
        
        result = await user_syncer.create_braintrust_resource(
            okta_user, "org1", additional_data=additional_data
        )
        
        assert result == created_user
        user_syncer.braintrust_clients["org1"].create_user.assert_called_once_with(
            given_name="John",
            family_name="Doe",
            email="user1@example.com",
            additional_fields={"department": "Engineering"},
        )
    
    @pytest.mark.asyncio
    async def test_update_braintrust_resource(self, user_syncer):
        """Test updating Braintrust user."""
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe")
        updated_user = MockBraintrustUser("bt1", "user1@example.com", "John", "Doe")
        updates = {"given_name": "Johnny"}
        
        user_syncer.braintrust_clients["org1"].update_user = AsyncMock(return_value=updated_user)
        
        result = await user_syncer.update_braintrust_resource("bt1", okta_user, "org1", updates)
        
        assert result == updated_user
        user_syncer.braintrust_clients["org1"].update_user.assert_called_once_with("bt1", updates)


class TestUserSyncerIdentityMapping:
    """Test identity mapping strategies."""
    
    def test_get_resource_identifier_email_strategy(self, user_syncer):
        """Test email identity mapping strategy."""
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe")
        
        identifier = user_syncer.get_resource_identifier(okta_user)
        assert identifier == "user1@example.com"
    
    def test_get_resource_identifier_custom_field_strategy(self, mock_clients, mock_state_manager):
        """Test custom field identity mapping strategy."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            identity_mapping_strategy="custom_field",
            custom_field_mappings={"identity_field": "employeeId"},
        )
        
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe", employeeId="EMP123")
        
        identifier = syncer.get_resource_identifier(okta_user)
        assert identifier == "EMP123"
    
    def test_get_resource_identifier_fallback_to_email(self, mock_clients, mock_state_manager):
        """Test fallback to email when custom field is missing."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            identity_mapping_strategy="custom_field",
            custom_field_mappings={"identity_field": "employeeId"},
        )
        
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe")  # No employeeId
        
        identifier = syncer.get_resource_identifier(okta_user)
        assert identifier == "user1@example.com"


class TestUserSyncerFiltering:
    """Test user filtering logic."""
    
    def test_should_sync_resource_active_users_only(self, user_syncer):
        """Test filtering by user status."""
        active_user = MockOktaUser("1", "user1@example.com", "John", "Doe", status="ACTIVE")
        inactive_user = MockOktaUser("2", "user2@example.com", "Jane", "Smith", status="SUSPENDED")
        
        sync_rules = {"only_active_users": True}
        
        assert user_syncer.should_sync_resource(active_user, "org1", sync_rules) is True
        assert user_syncer.should_sync_resource(inactive_user, "org1", sync_rules) is False
    
    def test_should_sync_resource_email_domain_filters(self, user_syncer):
        """Test filtering by email domain."""
        internal_user = MockOktaUser("1", "user1@company.com", "John", "Doe")
        external_user = MockOktaUser("2", "user2@external.com", "Jane", "Smith")
        
        sync_rules = {
            "email_domain_filters": {
                "org1": {
                    "include": ["company.com"],
                    "exclude": ["external.com"],
                }
            }
        }
        
        assert user_syncer.should_sync_resource(internal_user, "org1", sync_rules) is True
        assert user_syncer.should_sync_resource(external_user, "org1", sync_rules) is False
    
    def test_should_sync_resource_group_filters(self, user_syncer):
        """Test filtering by group membership."""
        # Mock group objects
        engineering_group = MagicMock()
        engineering_group.profile.name = "Engineering"
        
        marketing_group = MagicMock()
        marketing_group.profile.name = "Marketing"
        
        engineer = MockOktaUser("1", "user1@company.com", "John", "Doe")
        engineer.groups = [engineering_group]
        
        marketer = MockOktaUser("2", "user2@company.com", "Jane", "Smith")
        marketer.groups = [marketing_group]
        
        sync_rules = {
            "group_filters": {
                "org1": {
                    "include": ["Engineering"],
                    "exclude": ["Marketing"],
                }
            }
        }
        
        assert user_syncer.should_sync_resource(engineer, "org1", sync_rules) is True
        assert user_syncer.should_sync_resource(marketer, "org1", sync_rules) is False
    
    def test_should_sync_resource_profile_filters(self, user_syncer):
        """Test filtering by profile attributes."""
        full_time_user = MockOktaUser("1", "user1@company.com", "John", "Doe", userType="Employee")
        contractor_user = MockOktaUser("2", "user2@company.com", "Jane", "Smith", userType="Contractor")
        
        sync_rules = {
            "profile_filters": {
                "org1": {
                    "userType": ["Employee"]
                }
            }
        }
        
        assert user_syncer.should_sync_resource(full_time_user, "org1", sync_rules) is True
        assert user_syncer.should_sync_resource(contractor_user, "org1", sync_rules) is False


class TestUserSyncerUpdateCalculation:
    """Test update calculation logic."""
    
    def test_calculate_updates_name_changes(self, user_syncer):
        """Test calculating updates for name changes."""
        okta_user = MockOktaUser("1", "user1@example.com", "Johnny", "Doe")
        braintrust_user = MockBraintrustUser("bt1", "user1@example.com", "John", "Doe")
        
        updates = user_syncer.calculate_updates(okta_user, braintrust_user)
        
        assert updates == {"given_name": "Johnny"}
    
    def test_calculate_updates_no_changes(self, user_syncer):
        """Test calculating updates when no changes needed."""
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe")
        braintrust_user = MockBraintrustUser("bt1", "user1@example.com", "John", "Doe")
        
        updates = user_syncer.calculate_updates(okta_user, braintrust_user)
        
        assert updates == {}
    
    def test_calculate_updates_with_custom_fields(self, mock_clients, mock_state_manager):
        """Test calculating updates with custom field mappings."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            custom_field_mappings={"department": "dept"},
        )
        
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe", department="Engineering")
        braintrust_user = MockBraintrustUser("bt1", "user1@example.com", "John", "Doe")
        braintrust_user.dept = "Marketing"  # Different department
        
        updates = syncer.calculate_updates(okta_user, braintrust_user)
        
        assert updates == {"dept": "Engineering"}


class TestUserSyncerDataExtraction:
    """Test user data extraction."""
    
    def test_extract_user_data_basic(self, user_syncer):
        """Test basic user data extraction."""
        okta_user = MockOktaUser("1", "user1@example.com", "John", "Doe")
        
        user_data = user_syncer._extract_user_data(okta_user)
        
        expected = {
            "given_name": "John",
            "family_name": "Doe",
            "email": "user1@example.com",
        }
        assert user_data == expected
    
    def test_extract_user_data_with_custom_fields(self, mock_clients, mock_state_manager):
        """Test user data extraction with custom fields."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            custom_field_mappings={"department": "dept", "title": "job_title"},
        )
        
        okta_user = MockOktaUser(
            "1", "user1@example.com", "John", "Doe",
            department="Engineering",
            title="Software Engineer"
        )
        
        user_data = syncer._extract_user_data(okta_user)
        
        expected = {
            "given_name": "John",
            "family_name": "Doe",
            "email": "user1@example.com",
            "additional_fields": {
                "dept": "Engineering",
                "job_title": "Software Engineer",
            },
        }
        assert user_data == expected
    
    def test_extract_user_data_missing_names(self, user_syncer):
        """Test user data extraction with missing names."""
        okta_user = MockOktaUser("1", "user1@example.com", None, None)
        
        user_data = user_syncer._extract_user_data(okta_user)
        
        expected = {
            "given_name": "",
            "family_name": "",
            "email": "user1@example.com",
        }
        assert user_data == expected


class TestUserSyncerSearch:
    """Test user search functionality."""
    
    @pytest.mark.asyncio
    async def test_find_braintrust_user_by_email(self, user_syncer):
        """Test finding Braintrust user by email."""
        found_user = MockBraintrustUser("bt1", "user1@example.com", "John", "Doe")
        
        user_syncer.braintrust_clients["org1"].find_user_by_email = AsyncMock(return_value=found_user)
        
        result = await user_syncer.find_braintrust_user_by_email("user1@example.com", "org1")
        
        assert result == found_user
        user_syncer.braintrust_clients["org1"].find_user_by_email.assert_called_once_with("user1@example.com")
    
    @pytest.mark.asyncio
    async def test_find_braintrust_user_by_email_not_found(self, user_syncer):
        """Test finding Braintrust user when not found."""
        user_syncer.braintrust_clients["org1"].find_user_by_email = AsyncMock(return_value=None)
        
        result = await user_syncer.find_braintrust_user_by_email("user1@example.com", "org1")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_find_braintrust_user_invalid_org(self, user_syncer):
        """Test finding user in invalid organization."""
        result = await user_syncer.find_braintrust_user_by_email("user1@example.com", "invalid_org")
        
        assert result is None