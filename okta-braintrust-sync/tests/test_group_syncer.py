"""Tests for GroupSyncer functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from braintrust_api.types import Group as BraintrustGroup, User as BraintrustUser

from sync.clients.okta import OktaGroup
from sync.core.state import StateManager, ResourceMapping
from sync.resources.groups import GroupSyncer
from sync.resources.base import SyncAction


# Mock data classes
class MockOktaProfile:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description


class MockOktaGroup:
    def __init__(self, id: str, name: str, description: str = "", group_type: str = "OKTA_GROUP"):
        self.id = id
        self.type = group_type
        self.profile = MockOktaProfile(name=name, description=description)
        self.members = []


class MockOktaMember:
    def __init__(self, email: str):
        self.profile = MagicMock()
        self.profile.email = email
        self.email = email


class MockBraintrustGroup:
    def __init__(self, id: str, name: str, description: str = "", member_users=None, member_groups=None):
        self.id = id
        self.name = name
        self.description = description
        self.member_users = member_users or []
        self.member_groups = member_groups or []


class MockBraintrustUser:
    def __init__(self, id: str, email: str):
        self.id = id
        self.email = email


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
    mock_state.get_braintrust_id.return_value = None
    state_manager.get_current_state.return_value = mock_state
    return state_manager


@pytest.fixture
def group_syncer(mock_clients, mock_state_manager):
    """Create GroupSyncer instance."""
    okta_client, braintrust_clients = mock_clients
    return GroupSyncer(
        okta_client=okta_client,
        braintrust_clients=braintrust_clients,
        state_manager=mock_state_manager,
    )


class TestGroupSyncerInit:
    """Test GroupSyncer initialization."""
    
    def test_init_with_defaults(self, mock_clients, mock_state_manager):
        """Test initialization with default parameters."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = GroupSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
        )
        
        assert syncer.resource_type == "group"
        assert syncer.sync_group_memberships is True
        assert syncer.group_name_prefix == ""
        assert syncer.group_name_suffix == ""
    
    def test_init_with_custom_options(self, mock_clients, mock_state_manager):
        """Test initialization with custom parameters."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = GroupSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            sync_group_memberships=False,
            group_name_prefix="okta_",
            group_name_suffix="_sync",
        )
        
        assert syncer.sync_group_memberships is False
        assert syncer.group_name_prefix == "okta_"
        assert syncer.group_name_suffix == "_sync"


class TestGroupSyncerResourceOperations:
    """Test resource CRUD operations."""
    
    @pytest.mark.asyncio
    async def test_get_okta_resources(self, group_syncer):
        """Test retrieving Okta groups."""
        mock_groups = [
            MockOktaGroup("1", "Engineering", "Engineering team"),
            MockOktaGroup("2", "Marketing", "Marketing team"),
        ]
        
        group_syncer.okta_client.search_groups = AsyncMock(return_value=mock_groups)
        group_syncer.okta_client.list_groups = AsyncMock(return_value=mock_groups)
        
        # Test with filter
        result = await group_syncer.get_okta_resources(filter_expr="type eq \"OKTA_GROUP\"")
        assert len(result) == 2
        group_syncer.okta_client.search_groups.assert_called_once_with("type eq \"OKTA_GROUP\"", limit=None)
        
        # Test without filter
        result = await group_syncer.get_okta_resources()
        assert len(result) == 2
        group_syncer.okta_client.list_groups.assert_called_once_with(limit=None)
    
    @pytest.mark.asyncio
    async def test_get_braintrust_resources(self, group_syncer):
        """Test retrieving Braintrust groups."""
        mock_groups = [
            MockBraintrustGroup("bt1", "Engineering", "Engineering team"),
            MockBraintrustGroup("bt2", "Marketing", "Marketing team"),
        ]
        
        group_syncer.braintrust_clients["org1"].list_groups = AsyncMock(return_value=mock_groups)
        
        result = await group_syncer.get_braintrust_resources("org1")
        assert len(result) == 2
        group_syncer.braintrust_clients["org1"].list_groups.assert_called_once_with(limit=None)
    
    @pytest.mark.asyncio
    async def test_create_braintrust_resource(self, group_syncer):
        """Test creating Braintrust group."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        created_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team")
        
        group_syncer.braintrust_clients["org1"].create_group = AsyncMock(return_value=created_group)
        
        result = await group_syncer.create_braintrust_resource(okta_group, "org1")
        
        assert result == created_group
        group_syncer.braintrust_clients["org1"].create_group.assert_called_once_with(
            name="Engineering",
            description="Engineering team",
            member_users=[],
            member_groups=[],
        )
    
    @pytest.mark.asyncio
    async def test_create_braintrust_resource_with_prefix_suffix(self, mock_clients, mock_state_manager):
        """Test creating Braintrust group with name prefix/suffix."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = GroupSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            group_name_prefix="okta_",
            group_name_suffix="_sync",
        )
        
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        created_group = MockBraintrustGroup("bt1", "okta_Engineering_sync", "Engineering team")
        
        braintrust_clients["org1"].create_group = AsyncMock(return_value=created_group)
        
        result = await syncer.create_braintrust_resource(okta_group, "org1")
        
        assert result == created_group
        braintrust_clients["org1"].create_group.assert_called_once_with(
            name="okta_Engineering_sync",
            description="Engineering team",
            member_users=[],
            member_groups=[],
        )
    
    @pytest.mark.asyncio
    async def test_update_braintrust_resource(self, group_syncer):
        """Test updating Braintrust group."""
        okta_group = MockOktaGroup("1", "Engineering", "Updated engineering team")
        updated_group = MockBraintrustGroup("bt1", "Engineering", "Updated engineering team")
        updates = {"description": "Updated engineering team"}
        
        group_syncer.braintrust_clients["org1"].update_group = AsyncMock(return_value=updated_group)
        
        result = await group_syncer.update_braintrust_resource("bt1", okta_group, "org1", updates)
        
        assert result == updated_group
        group_syncer.braintrust_clients["org1"].update_group.assert_called_once_with("bt1", updates)
    
    @pytest.mark.asyncio
    async def test_update_braintrust_resource_with_membership(self, group_syncer):
        """Test updating group with membership changes."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        current_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team", ["user1"], [])
        
        updates = {"member_users": ["user1", "user2"]}
        
        # Mock the _sync_group_members method
        group_syncer._sync_group_members = AsyncMock(return_value=current_group)
        group_syncer.braintrust_clients["org1"].get_group = AsyncMock(return_value=current_group)
        
        result = await group_syncer.update_braintrust_resource("bt1", okta_group, "org1", updates)
        
        assert result == current_group
        group_syncer._sync_group_members.assert_called_once_with(
            "bt1", okta_group, "org1", target_member_users=["user1", "user2"], target_member_groups=None
        )


class TestGroupSyncerIdentityMapping:
    """Test identity mapping."""
    
    def test_get_resource_identifier(self, group_syncer):
        """Test group identifier extraction."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        
        identifier = group_syncer.get_resource_identifier(okta_group)
        assert identifier == "Engineering"


class TestGroupSyncerFiltering:
    """Test group filtering logic."""
    
    def test_should_sync_resource_group_type_filters(self, group_syncer):
        """Test filtering by group type."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team", group_type="OKTA_GROUP")
        ad_group = MockOktaGroup("2", "AD_Group", "AD imported group", group_type="AD_GROUP")
        
        sync_rules = {
            "group_type_filters": {
                "org1": {
                    "include": ["OKTA_GROUP"],
                    "exclude": ["AD_GROUP"],
                }
            }
        }
        
        assert group_syncer.should_sync_resource(okta_group, "org1", sync_rules) is True
        assert group_syncer.should_sync_resource(ad_group, "org1", sync_rules) is False
    
    def test_should_sync_resource_name_patterns(self, group_syncer):
        """Test filtering by group name patterns."""
        eng_group = MockOktaGroup("1", "Engineering-Team", "Engineering team")
        temp_group = MockOktaGroup("2", "temp_project_123", "Temporary project")
        
        sync_rules = {
            "group_name_patterns": {
                "org1": {
                    "include": [r".*Team$"],  # Groups ending with "Team"
                    "exclude": [r"^temp_"],   # Groups starting with "temp_"
                }
            }
        }
        
        assert group_syncer.should_sync_resource(eng_group, "org1", sync_rules) is True
        assert group_syncer.should_sync_resource(temp_group, "org1", sync_rules) is False
    
    def test_should_sync_resource_min_members(self, group_syncer):
        """Test filtering by minimum member count."""
        large_group = MockOktaGroup("1", "Engineering", "Engineering team")
        large_group.members = [MockOktaMember("user1@example.com"), MockOktaMember("user2@example.com")]
        
        small_group = MockOktaGroup("2", "OneUser", "Single user group")
        small_group.members = [MockOktaMember("user1@example.com")]
        
        sync_rules = {
            "min_group_members": {
                "org1": 2
            }
        }
        
        assert group_syncer.should_sync_resource(large_group, "org1", sync_rules) is True
        assert group_syncer.should_sync_resource(small_group, "org1", sync_rules) is False
    
    def test_should_sync_resource_profile_filters(self, group_syncer):
        """Test filtering by profile attributes."""
        business_group = MockOktaGroup("1", "Engineering", "Engineering team")
        business_group.profile.category = "business"
        
        system_group = MockOktaGroup("2", "System_Users", "System users")
        system_group.profile.category = "system"
        
        sync_rules = {
            "group_profile_filters": {
                "org1": {
                    "category": ["business"]
                }
            }
        }
        
        assert group_syncer.should_sync_resource(business_group, "org1", sync_rules) is True
        assert group_syncer.should_sync_resource(system_group, "org1", sync_rules) is False


class TestGroupSyncerUpdateCalculation:
    """Test update calculation logic."""
    
    def test_calculate_updates_description_change(self, group_syncer):
        """Test calculating updates for description changes."""
        okta_group = MockOktaGroup("1", "Engineering", "Updated engineering team")
        braintrust_group = MockBraintrustGroup("bt1", "Engineering", "Old engineering team")
        
        updates = group_syncer.calculate_updates(okta_group, braintrust_group)
        
        assert updates == {"description": "Updated engineering team"}
    
    def test_calculate_updates_no_changes(self, group_syncer):
        """Test calculating updates when no changes needed."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        braintrust_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team")
        
        updates = group_syncer.calculate_updates(okta_group, braintrust_group)
        
        assert updates == {}
    
    def test_calculate_updates_membership_changes(self, group_syncer):
        """Test calculating updates for membership changes."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        okta_group.members = [MockOktaMember("user1@example.com"), MockOktaMember("user2@example.com")]
        
        braintrust_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team", ["user1"])
        
        updates = group_syncer.calculate_updates(okta_group, braintrust_group)
        
        # Should include membership updates
        assert "member_users" in updates
        assert set(updates["member_users"]) == {"user1@example.com", "user2@example.com"}


class TestGroupSyncerDataExtraction:
    """Test group data extraction."""
    
    def test_extract_group_data_basic(self, group_syncer):
        """Test basic group data extraction."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        
        group_data = group_syncer._extract_group_data(okta_group)
        
        expected = {
            "name": "Engineering",
            "description": "Engineering team",
        }
        assert group_data == expected
    
    def test_extract_group_data_with_prefix_suffix(self, mock_clients, mock_state_manager):
        """Test group data extraction with prefix/suffix."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = GroupSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            group_name_prefix="okta_",
            group_name_suffix="_sync",
        )
        
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        
        group_data = syncer._extract_group_data(okta_group)
        
        expected = {
            "name": "okta_Engineering_sync",
            "description": "Engineering team",
        }
        assert group_data == expected
    
    def test_extract_group_data_with_members(self, group_syncer):
        """Test group data extraction with members."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        okta_group.members = [
            MockOktaMember("user1@example.com"),
            MockOktaMember("user2@example.com"),
        ]
        
        group_data = group_syncer._extract_group_data(okta_group)
        
        expected = {
            "name": "Engineering",
            "description": "Engineering team",
            "member_users": ["user1@example.com", "user2@example.com"],
        }
        assert group_data == expected
    
    def test_extract_group_data_no_description(self, group_syncer):
        """Test group data extraction with missing description."""
        okta_group = MockOktaGroup("1", "Engineering")
        okta_group.profile.description = None
        
        group_data = group_syncer._extract_group_data(okta_group)
        
        expected = {
            "name": "Engineering",
            "description": "Synced from Okta group: Engineering",
        }
        assert group_data == expected


class TestGroupSyncerMembershipManagement:
    """Test group membership management."""
    
    @pytest.mark.asyncio
    async def test_sync_group_members_add_users(self, group_syncer):
        """Test adding users to group."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        current_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team", [], [])
        target_users = ["user1@example.com", "user2@example.com"]
        
        # Mock finding users
        user1 = MockBraintrustUser("bt_user1", "user1@example.com")
        user2 = MockBraintrustUser("bt_user2", "user2@example.com")
        
        group_syncer.braintrust_clients["org1"].get_group = AsyncMock(return_value=current_group)
        group_syncer.braintrust_clients["org1"].find_user_by_email = AsyncMock(side_effect=[user1, user2])
        group_syncer.braintrust_clients["org1"].add_group_members = AsyncMock(return_value=current_group)
        
        result = await group_syncer._sync_group_members(
            "bt1", okta_group, "org1", target_member_users=target_users
        )
        
        assert result == current_group
        group_syncer.braintrust_clients["org1"].add_group_members.assert_called_once_with(
            "bt1", user_ids=["bt_user1", "bt_user2"], group_ids=None
        )
    
    @pytest.mark.asyncio
    async def test_sync_group_members_remove_users(self, group_syncer):
        """Test removing users from group."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        current_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team", ["bt_user1", "bt_user2"], [])
        target_users = ["user1@example.com"]  # Only keep user1
        
        # Mock finding users
        user1 = MockBraintrustUser("bt_user1", "user1@example.com")
        
        group_syncer.braintrust_clients["org1"].get_group = AsyncMock(return_value=current_group)
        group_syncer.braintrust_clients["org1"].find_user_by_email = AsyncMock(return_value=user1)
        group_syncer.braintrust_clients["org1"].remove_group_members = AsyncMock(return_value=current_group)
        
        result = await group_syncer._sync_group_members(
            "bt1", okta_group, "org1", target_member_users=target_users
        )
        
        assert result == current_group
        group_syncer.braintrust_clients["org1"].remove_group_members.assert_called_once_with(
            "bt1", user_ids=["bt_user2"], group_ids=None
        )
    
    @pytest.mark.asyncio
    async def test_sync_group_members_user_not_found(self, group_syncer):
        """Test handling when target user is not found in Braintrust."""
        okta_group = MockOktaGroup("1", "Engineering", "Engineering team")
        current_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team", [], [])
        target_users = ["nonexistent@example.com"]
        
        group_syncer.braintrust_clients["org1"].get_group = AsyncMock(return_value=current_group)
        group_syncer.braintrust_clients["org1"].find_user_by_email = AsyncMock(return_value=None)
        
        # Mock state manager to check for user in mappings
        mock_state = group_syncer.state_manager.get_current_state.return_value
        mock_state.get_braintrust_id.return_value = None
        
        result = await group_syncer._sync_group_members(
            "bt1", okta_group, "org1", target_member_users=target_users
        )
        
        assert result == current_group
        # Should not call add/remove since user wasn't found
        group_syncer.braintrust_clients["org1"].add_group_members.assert_not_called()


class TestGroupSyncerSearch:
    """Test group search functionality."""
    
    @pytest.mark.asyncio
    async def test_find_braintrust_group_by_name(self, group_syncer):
        """Test finding Braintrust group by name."""
        found_group = MockBraintrustGroup("bt1", "Engineering", "Engineering team")
        
        group_syncer.braintrust_clients["org1"].find_group_by_name = AsyncMock(return_value=found_group)
        
        result = await group_syncer.find_braintrust_group_by_name("Engineering", "org1")
        
        assert result == found_group
        group_syncer.braintrust_clients["org1"].find_group_by_name.assert_called_once_with("Engineering")
    
    @pytest.mark.asyncio
    async def test_find_braintrust_group_with_prefix_suffix(self, mock_clients, mock_state_manager):
        """Test finding group with prefix/suffix applied."""
        okta_client, braintrust_clients = mock_clients
        
        syncer = GroupSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            group_name_prefix="okta_",
            group_name_suffix="_sync",
        )
        
        found_group = MockBraintrustGroup("bt1", "okta_Engineering_sync", "Engineering team")
        braintrust_clients["org1"].find_group_by_name = AsyncMock(return_value=found_group)
        
        result = await syncer.find_braintrust_group_by_name("Engineering", "org1")
        
        assert result == found_group
        braintrust_clients["org1"].find_group_by_name.assert_called_once_with("okta_Engineering_sync")
    
    @pytest.mark.asyncio
    async def test_find_braintrust_group_invalid_org(self, group_syncer):
        """Test finding group in invalid organization."""
        result = await group_syncer.find_braintrust_group_by_name("Engineering", "invalid_org")
        
        assert result is None