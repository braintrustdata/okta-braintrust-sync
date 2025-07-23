"""Tests for base resource syncer functionality."""

import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient, OktaUser, OktaGroup
from sync.core.state import StateManager, SyncState, ResourceMapping
from sync.resources.base import (
    BaseResourceSyncer,
    SyncAction,
    SyncPlanItem,
    SyncResult,
)


# Mock implementations for testing
class MockOktaUser:
    """Mock Okta user for testing."""
    def __init__(self, id: str, email: str, first_name: str, last_name: str):
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name


class MockBraintrustUser:
    """Mock Braintrust user for testing."""
    def __init__(self, id: str, email: str, given_name: str, family_name: str):
        self.id = id
        self.email = email
        self.given_name = given_name
        self.family_name = family_name


class TestResourceSyncer(BaseResourceSyncer[MockOktaUser, MockBraintrustUser]):
    """Test implementation of BaseResourceSyncer."""
    
    @property
    def resource_type(self) -> str:
        return "user"
    
    async def get_okta_resources(
        self,
        filter_expr: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[MockOktaUser]:
        # Mock implementation - will be overridden in tests
        return []
    
    async def get_braintrust_resources(
        self,
        braintrust_org: str,
        limit: Optional[int] = None,
    ) -> List[MockBraintrustUser]:
        # Mock implementation - will be overridden in tests
        return []
    
    async def create_braintrust_resource(
        self,
        okta_resource: MockOktaUser,
        braintrust_org: str,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> MockBraintrustUser:
        # Mock implementation - will be overridden in tests
        return MockBraintrustUser(
            id=f"bt-{okta_resource.id}",
            email=okta_resource.email,
            given_name=okta_resource.first_name,
            family_name=okta_resource.last_name,
        )
    
    async def update_braintrust_resource(
        self,
        braintrust_resource_id: str,
        okta_resource: MockOktaUser,
        braintrust_org: str,
        updates: Dict[str, Any],
    ) -> MockBraintrustUser:
        # Mock implementation - will be overridden in tests
        return MockBraintrustUser(
            id=braintrust_resource_id,
            email=okta_resource.email,
            given_name=updates.get("given_name", okta_resource.first_name),
            family_name=updates.get("family_name", okta_resource.last_name),
        )
    
    def get_resource_identifier(self, resource: MockOktaUser) -> str:
        return resource.email
    
    def should_sync_resource(
        self,
        okta_resource: MockOktaUser,
        braintrust_org: str,
        sync_rules: Dict[str, Any],
    ) -> bool:
        # Simple mock implementation
        return sync_rules.get("sync_all", True)
    
    def calculate_updates(
        self,
        okta_resource: MockOktaUser,
        braintrust_resource: MockBraintrustUser,
    ) -> Dict[str, Any]:
        updates = {}
        if okta_resource.first_name != braintrust_resource.given_name:
            updates["given_name"] = okta_resource.first_name
        if okta_resource.last_name != braintrust_resource.family_name:
            updates["family_name"] = okta_resource.last_name
        return updates


@pytest.fixture
def mock_okta_client():
    """Create a mock Okta client."""
    return MagicMock(spec=OktaClient)


@pytest.fixture
def mock_braintrust_clients():
    """Create mock Braintrust clients."""
    return {
        "org1": MagicMock(spec=BraintrustClient),
        "org2": MagicMock(spec=BraintrustClient),
    }


@pytest.fixture
def mock_state_manager():
    """Create a mock state manager."""
    state_manager = MagicMock(spec=StateManager)
    
    # Create a mock state
    mock_state = MagicMock(spec=SyncState)
    mock_state.get_mapping.return_value = None
    mock_state.add_mapping = MagicMock()
    mock_state.add_operation = MagicMock()
    
    state_manager.get_current_state.return_value = mock_state
    
    return state_manager


@pytest.fixture
def test_syncer(mock_okta_client, mock_braintrust_clients, mock_state_manager):
    """Create a test resource syncer."""
    return TestResourceSyncer(
        okta_client=mock_okta_client,
        braintrust_clients=mock_braintrust_clients,
        state_manager=mock_state_manager,
    )


class TestSyncPlanItem:
    """Test SyncPlanItem model."""
    
    def test_sync_plan_item_creation(self):
        """Test sync plan item creation."""
        item = SyncPlanItem(
            okta_resource_id="okta-123",
            okta_resource_type="user",
            braintrust_org="test-org",
            action=SyncAction.CREATE,
            reason="New user from Okta"
        )
        
        assert item.okta_resource_id == "okta-123"
        assert item.okta_resource_type == "user"
        assert item.braintrust_org == "test-org"
        assert item.action == SyncAction.CREATE
        assert item.reason == "New user from Okta"
        assert item.existing_braintrust_id is None
        assert len(item.proposed_changes) == 0
        assert len(item.dependencies) == 0
        assert len(item.metadata) == 0
    
    def test_sync_plan_item_with_optional_fields(self):
        """Test sync plan item with optional fields."""
        item = SyncPlanItem(
            okta_resource_id="okta-123",
            okta_resource_type="user",
            braintrust_org="test-org",
            action=SyncAction.UPDATE,
            reason="Name changed",
            existing_braintrust_id="bt-456",
            proposed_changes={"given_name": "John"},
            dependencies=["dep-1", "dep-2"],
            metadata={"source": "okta"}
        )
        
        assert item.existing_braintrust_id == "bt-456"
        assert item.proposed_changes == {"given_name": "John"}
        assert item.dependencies == ["dep-1", "dep-2"]
        assert item.metadata == {"source": "okta"}


class TestSyncResult:
    """Test SyncResult model."""
    
    def test_sync_result_creation(self):
        """Test sync result creation."""
        result = SyncResult(
            operation_id="op-123",
            okta_resource_id="okta-123",
            braintrust_org="test-org",
            action=SyncAction.CREATE,
            success=True
        )
        
        assert result.operation_id == "op-123"
        assert result.okta_resource_id == "okta-123"
        assert result.braintrust_resource_id is None
        assert result.braintrust_org == "test-org"
        assert result.action == SyncAction.CREATE
        assert result.success is True
        assert result.error_message is None
        assert len(result.metadata) == 0
    
    def test_sync_result_with_error(self):
        """Test sync result with error."""
        result = SyncResult(
            operation_id="op-123",
            okta_resource_id="okta-123",
            braintrust_org="test-org",
            action=SyncAction.ERROR,
            success=False,
            error_message="Network timeout",
            metadata={"retry_count": 3}
        )
        
        assert result.success is False
        assert result.error_message == "Network timeout"
        assert result.metadata == {"retry_count": 3}


class TestBaseResourceSyncer:
    """Test BaseResourceSyncer functionality."""
    
    def test_syncer_initialization(self, test_syncer, mock_okta_client, mock_braintrust_clients, mock_state_manager):
        """Test syncer initialization."""
        assert test_syncer.okta_client == mock_okta_client
        assert test_syncer.braintrust_clients == mock_braintrust_clients
        assert test_syncer.state_manager == mock_state_manager
        assert test_syncer.resource_type == "user"
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_empty(self, test_syncer):
        """Test sync plan generation with no resources."""
        # Mock empty Okta resources
        test_syncer.get_okta_resources = AsyncMock(return_value=[])
        
        sync_rules = {"sync_all": True}
        plan_items = await test_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules=sync_rules
        )
        
        assert len(plan_items) == 0
        test_syncer.get_okta_resources.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_new_resources(self, test_syncer, mock_state_manager):
        """Test sync plan generation with new resources."""
        # Mock Okta resources
        okta_users = [
            MockOktaUser("okta-1", "user1@example.com", "John", "Doe"),
            MockOktaUser("okta-2", "user2@example.com", "Jane", "Smith"),
        ]
        test_syncer.get_okta_resources = AsyncMock(return_value=okta_users)
        test_syncer.get_braintrust_resources = AsyncMock(return_value=[])
        
        # Mock state with no existing mappings
        mock_state = mock_state_manager.get_current_state.return_value
        mock_state.get_mapping.return_value = None
        
        sync_rules = {"sync_all": True, "create_missing": True}
        plan_items = await test_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules=sync_rules
        )
        
        assert len(plan_items) == 2
        
        # Both should be CREATE actions
        for item in plan_items:
            assert item.action == SyncAction.CREATE
            assert item.reason == "New resource from Okta"
            assert item.braintrust_org == "org1"
            assert item.okta_resource_type == "user"
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_existing_resources_no_updates(self, test_syncer, mock_state_manager):
        """Test sync plan with existing resources that don't need updates."""
        # Mock Okta resources
        okta_users = [
            MockOktaUser("okta-1", "user1@example.com", "John", "Doe"),
        ]
        test_syncer.get_okta_resources = AsyncMock(return_value=okta_users)
        
        # Mock Braintrust resources
        braintrust_users = [
            MockBraintrustUser("bt-1", "user1@example.com", "John", "Doe"),
        ]
        test_syncer.get_braintrust_resources = AsyncMock(return_value=braintrust_users)
        
        # Mock existing mapping
        mock_state = mock_state_manager.get_current_state.return_value
        mock_mapping = MagicMock()
        mock_mapping.braintrust_id = "bt-1"
        mock_state.get_mapping.return_value = mock_mapping
        
        sync_rules = {"sync_all": True}
        plan_items = await test_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules=sync_rules
        )
        
        assert len(plan_items) == 1
        assert plan_items[0].action == SyncAction.SKIP
        assert plan_items[0].reason == "Resource is up to date"
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_existing_resources_with_updates(self, test_syncer, mock_state_manager):
        """Test sync plan with existing resources that need updates."""
        # Mock Okta resources
        okta_users = [
            MockOktaUser("okta-1", "user1@example.com", "John", "Doe"),
        ]
        test_syncer.get_okta_resources = AsyncMock(return_value=okta_users)
        
        # Mock Braintrust resources with different name
        braintrust_users = [
            MockBraintrustUser("bt-1", "user1@example.com", "Johnny", "Doe"),
        ]
        test_syncer.get_braintrust_resources = AsyncMock(return_value=braintrust_users)
        
        # Mock existing mapping
        mock_state = mock_state_manager.get_current_state.return_value
        mock_mapping = MagicMock()
        mock_mapping.braintrust_id = "bt-1"
        mock_state.get_mapping.return_value = mock_mapping
        
        sync_rules = {"sync_all": True}
        plan_items = await test_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules=sync_rules
        )
        
        assert len(plan_items) == 1
        assert plan_items[0].action == SyncAction.UPDATE
        assert plan_items[0].existing_braintrust_id == "bt-1"
        assert plan_items[0].proposed_changes == {"given_name": "John"}
        assert "given_name" in plan_items[0].reason
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_missing_braintrust_resource(self, test_syncer, mock_state_manager):
        """Test sync plan when mapped resource is missing from Braintrust."""
        # Mock Okta resources
        okta_users = [
            MockOktaUser("okta-1", "user1@example.com", "John", "Doe"),
        ]
        test_syncer.get_okta_resources = AsyncMock(return_value=okta_users)
        test_syncer.get_braintrust_resources = AsyncMock(return_value=[])  # No Braintrust resources
        
        # Mock existing mapping
        mock_state = mock_state_manager.get_current_state.return_value
        mock_mapping = MagicMock()
        mock_mapping.braintrust_id = "bt-1"
        mock_state.get_mapping.return_value = mock_mapping
        
        sync_rules = {"sync_all": True}
        plan_items = await test_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules=sync_rules
        )
        
        assert len(plan_items) == 1
        assert plan_items[0].action == SyncAction.CREATE
        assert plan_items[0].reason == "Mapped resource missing in Braintrust"
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_create_disabled(self, test_syncer, mock_state_manager):
        """Test sync plan when resource creation is disabled."""
        # Mock Okta resources
        okta_users = [
            MockOktaUser("okta-1", "user1@example.com", "John", "Doe"),
        ]
        test_syncer.get_okta_resources = AsyncMock(return_value=okta_users)
        test_syncer.get_braintrust_resources = AsyncMock(return_value=[])
        
        # Mock state with no existing mappings
        mock_state = mock_state_manager.get_current_state.return_value
        mock_state.get_mapping.return_value = None
        
        sync_rules = {"sync_all": True, "create_missing": False}
        plan_items = await test_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules=sync_rules
        )
        
        assert len(plan_items) == 1
        assert plan_items[0].action == SyncAction.SKIP
        assert plan_items[0].reason == "Creation disabled in sync rules"
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_multiple_orgs(self, test_syncer, mock_state_manager):
        """Test sync plan generation for multiple organizations."""
        # Mock Okta resources
        okta_users = [
            MockOktaUser("okta-1", "user1@example.com", "John", "Doe"),
        ]
        test_syncer.get_okta_resources = AsyncMock(return_value=okta_users)
        test_syncer.get_braintrust_resources = AsyncMock(return_value=[])
        
        # Mock state with no existing mappings
        mock_state = mock_state_manager.get_current_state.return_value
        mock_state.get_mapping.return_value = None
        
        sync_rules = {"sync_all": True, "create_missing": True}
        plan_items = await test_syncer.generate_sync_plan(
            braintrust_orgs=["org1", "org2"],
            sync_rules=sync_rules
        )
        
        assert len(plan_items) == 2
        
        # Should have one item per org
        org_names = [item.braintrust_org for item in plan_items]
        assert "org1" in org_names
        assert "org2" in org_names
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_skip_action(self, test_syncer, mock_state_manager):
        """Test executing sync plan with SKIP action."""
        plan_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.SKIP,
                reason="Resource is up to date",
                existing_braintrust_id="bt-1"
            )
        ]
        
        results = await test_syncer.execute_sync_plan(plan_items)
        
        assert len(results) == 1
        assert results[0].action == SyncAction.SKIP
        assert results[0].success is True
        assert results[0].braintrust_resource_id == "bt-1"
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_create_action(self, test_syncer, mock_state_manager):
        """Test executing sync plan with CREATE action."""
        # Mock Okta resource retrieval
        okta_user = MockOktaUser("okta-1", "user1@example.com", "John", "Doe")
        test_syncer.get_okta_resources = AsyncMock(return_value=[okta_user])
        
        # Mock resource creation
        created_user = MockBraintrustUser("bt-new", "user1@example.com", "John", "Doe")
        test_syncer.create_braintrust_resource = AsyncMock(return_value=created_user)
        
        plan_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New resource from Okta"
            )
        ]
        
        results = await test_syncer.execute_sync_plan(plan_items)
        
        assert len(results) == 1
        assert results[0].action == SyncAction.CREATE
        assert results[0].success is True
        assert results[0].braintrust_resource_id == "bt-new"
        
        # Verify mapping was added to state
        mock_state = mock_state_manager.get_current_state.return_value
        mock_state.add_mapping.assert_called_once_with(
            "user1@example.com", "bt-new", "org1", "user"
        )
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_update_action(self, test_syncer, mock_state_manager):
        """Test executing sync plan with UPDATE action."""
        # Mock Okta resource retrieval
        okta_user = MockOktaUser("okta-1", "user1@example.com", "John", "Doe")
        test_syncer.get_okta_resources = AsyncMock(return_value=[okta_user])
        
        # Mock resource update
        updated_user = MockBraintrustUser("bt-1", "user1@example.com", "John", "Doe")
        test_syncer.update_braintrust_resource = AsyncMock(return_value=updated_user)
        
        plan_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.UPDATE,
                reason="Name changed",
                existing_braintrust_id="bt-1",
                proposed_changes={"given_name": "John"}
            )
        ]
        
        results = await test_syncer.execute_sync_plan(plan_items)
        
        assert len(results) == 1
        assert results[0].action == SyncAction.UPDATE
        assert results[0].success is True
        assert results[0].braintrust_resource_id == "bt-1"
        
        # Verify update was called with correct parameters
        test_syncer.update_braintrust_resource.assert_called_once_with(
            "bt-1", okta_user, "org1", {"given_name": "John"}
        )
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_dry_run(self, test_syncer, mock_state_manager):
        """Test executing sync plan in dry run mode."""
        plan_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New resource from Okta"
            ),
            SyncPlanItem(
                okta_resource_id="user2@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.UPDATE,
                reason="Name changed",
                existing_braintrust_id="bt-2",
                proposed_changes={"given_name": "Jane"}
            )
        ]
        
        results = await test_syncer.execute_sync_plan(plan_items, dry_run=True)
        
        assert len(results) == 2
        
        # All results should be successful with dry_run metadata
        for result in results:
            assert result.success is True
            assert result.metadata.get("dry_run") is True
        
        # CREATE action should have dry_run_id
        create_result = next(r for r in results if r.action == SyncAction.CREATE)
        assert create_result.braintrust_resource_id == "dry_run_id"
        
        # UPDATE action should preserve existing ID
        update_result = next(r for r in results if r.action == SyncAction.UPDATE)
        assert update_result.braintrust_resource_id == "bt-2"
        assert update_result.metadata["proposed_changes"] == {"given_name": "Jane"}
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_error_handling(self, test_syncer, mock_state_manager):
        """Test error handling during sync plan execution."""
        # Mock error during resource creation
        test_syncer.get_okta_resources = AsyncMock(side_effect=Exception("Network error"))
        
        plan_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New resource from Okta"
            )
        ]
        
        results = await test_syncer.execute_sync_plan(plan_items)
        
        assert len(results) == 1
        assert results[0].action == SyncAction.ERROR
        assert results[0].success is False
        assert "Network error" in results[0].error_message
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_unknown_action(self, test_syncer, mock_state_manager):
        """Test handling unknown sync action."""
        plan_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action="UNKNOWN_ACTION",  # Invalid action
                reason="Test"
            )
        ]
        
        results = await test_syncer.execute_sync_plan(plan_items)
        
        assert len(results) == 1
        assert results[0].action == SyncAction.ERROR
        assert results[0].success is False
        assert "Unknown sync action" in results[0].error_message