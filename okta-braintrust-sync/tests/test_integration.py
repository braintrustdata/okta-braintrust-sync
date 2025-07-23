"""Integration tests for Phase 2 components working together."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient
from sync.core.state import StateManager, SyncState
from sync.resources.base import BaseResourceSyncer, SyncAction, SyncPlanItem


# Mock data models for testing
class MockOktaUser:
    def __init__(self, id: str, email: str, first_name: str, last_name: str):
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name


class MockBraintrustUser:
    def __init__(self, id: str, email: str, given_name: str, family_name: str):
        self.id = id
        self.email = email
        self.given_name = given_name
        self.family_name = family_name


class IntegrationTestSyncer(BaseResourceSyncer[MockOktaUser, MockBraintrustUser]):
    """Test syncer for integration testing."""
    
    @property
    def resource_type(self) -> str:
        return "user"
    
    async def get_okta_resources(self, filter_expr=None, limit=None):
        return self._okta_resources
    
    async def get_braintrust_resources(self, braintrust_org, limit=None):
        return self._braintrust_resources.get(braintrust_org, [])
    
    async def create_braintrust_resource(self, okta_resource, braintrust_org, additional_data=None):
        created_user = MockBraintrustUser(
            id=f"bt-{len(self._created_resources)}",
            email=okta_resource.email,
            given_name=okta_resource.first_name,
            family_name=okta_resource.last_name,
        )
        self._created_resources.append(created_user)
        return created_user
    
    async def update_braintrust_resource(self, braintrust_resource_id, okta_resource, braintrust_org, updates):
        # Find existing resource and update it
        for resource in self._braintrust_resources.get(braintrust_org, []):
            if resource.id == braintrust_resource_id:
                if "given_name" in updates:
                    resource.given_name = updates["given_name"]
                if "family_name" in updates:
                    resource.family_name = updates["family_name"]
                return resource
        
        # If not found, create a new one
        return MockBraintrustUser(
            id=braintrust_resource_id,
            email=okta_resource.email,
            given_name=updates.get("given_name", okta_resource.first_name),
            family_name=updates.get("family_name", okta_resource.last_name),
        )
    
    def get_resource_identifier(self, resource):
        return resource.email
    
    def should_sync_resource(self, okta_resource, braintrust_org, sync_rules):
        return sync_rules.get("sync_all", True)
    
    def calculate_updates(self, okta_resource, braintrust_resource):
        updates = {}
        if okta_resource.first_name != braintrust_resource.given_name:
            updates["given_name"] = okta_resource.first_name
        if okta_resource.last_name != braintrust_resource.family_name:
            updates["family_name"] = okta_resource.last_name
        return updates
    
    def set_test_data(self, okta_resources, braintrust_resources):
        """Set test data for the syncer."""
        self._okta_resources = okta_resources
        self._braintrust_resources = braintrust_resources
        self._created_resources = []


@pytest.fixture
def temp_state_dir():
    """Create temporary directory for state files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def state_manager(temp_state_dir):
    """Create real state manager for integration testing."""
    return StateManager(state_dir=temp_state_dir)


@pytest.fixture
def mock_clients():
    """Create mock API clients."""
    okta_client = MagicMock(spec=OktaClient)
    braintrust_clients = {
        "org1": MagicMock(spec=BraintrustClient),
        "org2": MagicMock(spec=BraintrustClient),
    }
    return okta_client, braintrust_clients


@pytest.fixture
def integration_syncer(mock_clients, state_manager):
    """Create integration test syncer."""
    okta_client, braintrust_clients = mock_clients
    syncer = IntegrationTestSyncer(
        okta_client=okta_client,
        braintrust_clients=braintrust_clients,
        state_manager=state_manager,
    )
    return syncer


class TestComponentIntegration:
    """Test integration between all Phase 2 components."""
    
    def test_state_manager_and_syncer_initialization(self, integration_syncer, state_manager):
        """Test that components can be initialized together."""
        assert integration_syncer.state_manager == state_manager
        assert integration_syncer.resource_type == "user"
        assert state_manager._current_state is None
    
    @pytest.mark.asyncio
    async def test_full_sync_workflow_new_resources(self, integration_syncer, state_manager):
        """Test complete sync workflow with new resources."""
        # Set up test data
        okta_users = [
            MockOktaUser("okta-1", "john@example.com", "John", "Doe"),
            MockOktaUser("okta-2", "jane@example.com", "Jane", "Smith"),
        ]
        
        braintrust_resources = {
            "org1": [],  # No existing resources
            "org2": [],
        }
        
        integration_syncer.set_test_data(okta_users, braintrust_resources)
        
        # Create sync state
        sync_state = state_manager.create_sync_state("test-sync")
        
        # Generate sync plan
        sync_rules = {"sync_all": True, "create_missing": True}
        plan_items = await integration_syncer.generate_sync_plan(
            braintrust_orgs=["org1", "org2"],
            sync_rules=sync_rules
        )
        
        # Should have 4 plan items (2 users × 2 orgs)
        assert len(plan_items) == 4
        
        # All should be CREATE actions
        for item in plan_items:
            assert item.action == SyncAction.CREATE
            assert item.reason == "New resource from Okta"
        
        # Execute sync plan
        results = await integration_syncer.execute_sync_plan(plan_items)
        
        # All should succeed
        assert len(results) == 4
        for result in results:
            assert result.success is True
            assert result.action == SyncAction.CREATE
            assert result.braintrust_resource_id is not None
        
        # Verify state was updated with mappings
        john_org1_mapping = sync_state.get_mapping("john@example.com", "org1", "user")
        john_org2_mapping = sync_state.get_mapping("john@example.com", "org2", "user")
        jane_org1_mapping = sync_state.get_mapping("jane@example.com", "org1", "user")
        jane_org2_mapping = sync_state.get_mapping("jane@example.com", "org2", "user")
        
        assert john_org1_mapping is not None
        assert john_org2_mapping is not None
        assert jane_org1_mapping is not None
        assert jane_org2_mapping is not None
        
        # Each mapping should have different Braintrust IDs
        assert john_org1_mapping.braintrust_id != john_org2_mapping.braintrust_id
        assert jane_org1_mapping.braintrust_id != jane_org2_mapping.braintrust_id
    
    @pytest.mark.asyncio
    async def test_full_sync_workflow_with_updates(self, integration_syncer, state_manager):
        """Test complete sync workflow with resource updates."""
        # Set up test data with existing resources
        okta_users = [
            MockOktaUser("okta-1", "john@example.com", "John", "Doe"),  # Name changed
        ]
        
        existing_braintrust_user = MockBraintrustUser(
            id="bt-existing",
            email="john@example.com",
            given_name="Johnny",  # Old name
            family_name="Doe"
        )
        
        braintrust_resources = {
            "org1": [existing_braintrust_user],
        }
        
        integration_syncer.set_test_data(okta_users, braintrust_resources)
        
        # Create sync state with existing mapping
        sync_state = state_manager.create_sync_state("test-sync-update")
        sync_state.add_mapping("john@example.com", "bt-existing", "org1", "user")
        
        # Generate sync plan
        sync_rules = {"sync_all": True}
        plan_items = await integration_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules=sync_rules
        )
        
        # Should have 1 plan item for update
        assert len(plan_items) == 1
        assert plan_items[0].action == SyncAction.UPDATE
        assert plan_items[0].existing_braintrust_id == "bt-existing"
        assert plan_items[0].proposed_changes == {"given_name": "John"}
        
        # Execute sync plan
        results = await integration_syncer.execute_sync_plan(plan_items)
        
        # Should succeed
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].action == SyncAction.UPDATE
        assert results[0].braintrust_resource_id == "bt-existing"
    
    @pytest.mark.asyncio
    async def test_state_persistence_across_syncs(self, integration_syncer, state_manager, temp_state_dir):
        """Test that state persists across multiple sync operations."""
        # First sync - create resources
        okta_users = [
            MockOktaUser("okta-1", "john@example.com", "John", "Doe"),
        ]
        
        integration_syncer.set_test_data(okta_users, {"org1": []})
        
        # Create and save initial state
        sync_state1 = state_manager.create_sync_state("sync-1")
        
        plan_items = await integration_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules={"sync_all": True, "create_missing": True}
        )
        
        results = await integration_syncer.execute_sync_plan(plan_items)
        assert len(results) == 1
        assert results[0].success is True
        
        # Save state
        saved = state_manager.save_sync_state(sync_state1)
        assert saved is True
        
        # Create new state manager (simulating restart)
        new_state_manager = StateManager(state_dir=temp_state_dir)
        
        # Create new syncer with the new state manager
        okta_client, braintrust_clients = mock_clients
        new_syncer = IntegrationTestSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=new_state_manager,
        )
        
        # Set up for second sync with updated resource
        updated_okta_users = [
            MockOktaUser("okta-1", "john@example.com", "Johnny", "Doe"),  # Name changed
        ]
        
        existing_bt_user = MockBraintrustUser("bt-0", "john@example.com", "John", "Doe")
        new_syncer.set_test_data(updated_okta_users, {"org1": [existing_bt_user]})
        
        # Create new sync state - should load previous mappings
        sync_state2 = new_state_manager.create_sync_state("sync-2")
        
        # Should have loaded previous mapping
        mapping = sync_state2.get_mapping("john@example.com", "org1", "user")
        assert mapping is not None
        assert mapping.braintrust_id == "bt-0"  # From first sync
        
        # Generate plan - should detect update needed
        plan_items = await new_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules={"sync_all": True}
        )
        
        assert len(plan_items) == 1
        assert plan_items[0].action == SyncAction.UPDATE
        assert plan_items[0].existing_braintrust_id == "bt-0"
    
    @pytest.mark.asyncio
    async def test_sync_plan_with_dependencies(self, integration_syncer, state_manager):
        """Test sync plan generation with resource dependencies."""
        # This test demonstrates how the framework handles dependencies
        # In a real implementation, groups might depend on users
        
        okta_users = [
            MockOktaUser("okta-1", "john@example.com", "John", "Doe"),
        ]
        
        integration_syncer.set_test_data(okta_users, {"org1": []})
        
        sync_state = state_manager.create_sync_state("test-dependencies")
        
        plan_items = await integration_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules={"sync_all": True, "create_missing": True}
        )
        
        # Manually add dependency information (in real impl, this would be automatic)
        if plan_items:
            plan_items[0].dependencies = ["some-group-resource"]
            plan_items[0].metadata = {"depends_on": "group creation"}
        
        # Execute plan
        results = await integration_syncer.execute_sync_plan(plan_items)
        
        assert len(results) == 1
        assert results[0].success is True
        
        # Verify the dependency information was preserved
        assert results[0].metadata is not None
    
    @pytest.mark.asyncio
    async def test_error_recovery_and_state_consistency(self, integration_syncer, state_manager):
        """Test error handling and state consistency."""
        okta_users = [
            MockOktaUser("okta-1", "john@example.com", "John", "Doe"),
            MockOktaUser("okta-2", "jane@example.com", "Jane", "Smith"),
        ]
        
        integration_syncer.set_test_data(okta_users, {"org1": []})
        
        sync_state = state_manager.create_sync_state("test-error-recovery")
        
        # Mock error on second resource creation
        original_create = integration_syncer.create_braintrust_resource
        call_count = 0
        
        async def create_with_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call fails
                raise Exception("Simulated network error")
            return await original_create(*args, **kwargs)
        
        integration_syncer.create_braintrust_resource = create_with_error
        
        plan_items = await integration_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules={"sync_all": True, "create_missing": True}
        )
        
        results = await integration_syncer.execute_sync_plan(plan_items)
        
        # Should have one success and one error
        assert len(results) == 2
        success_results = [r for r in results if r.success]
        error_results = [r for r in results if not r.success]
        
        assert len(success_results) == 1
        assert len(error_results) == 1
        
        # Successful resource should have mapping in state
        successful_result = success_results[0]
        mapping = sync_state.get_mapping(
            successful_result.okta_resource_id, "org1", "user"
        )
        assert mapping is not None
        assert mapping.braintrust_id == successful_result.braintrust_resource_id
        
        # Failed resource should not have mapping
        failed_result = error_results[0]
        failed_mapping = sync_state.get_mapping(
            failed_result.okta_resource_id, "org1", "user"
        )
        assert failed_mapping is None  # Should not exist due to failure
    
    @pytest.mark.asyncio
    async def test_dry_run_preserves_state(self, integration_syncer, state_manager):
        """Test that dry run mode doesn't modify persistent state."""
        okta_users = [
            MockOktaUser("okta-1", "john@example.com", "John", "Doe"),
        ]
        
        integration_syncer.set_test_data(okta_users, {"org1": []})
        
        sync_state = state_manager.create_sync_state("test-dry-run")
        initial_mapping_count = len(sync_state.resource_mappings)
        
        plan_items = await integration_syncer.generate_sync_plan(
            braintrust_orgs=["org1"],
            sync_rules={"sync_all": True, "create_missing": True}
        )
        
        # Execute in dry run mode
        results = await integration_syncer.execute_sync_plan(plan_items, dry_run=True)
        
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].metadata.get("dry_run") is True
        assert results[0].braintrust_resource_id == "dry_run_id"
        
        # State should not have new mappings
        assert len(sync_state.resource_mappings) == initial_mapping_count
        
        # No real resources should have been created
        assert len(integration_syncer._created_resources) == 0


class TestBraintrustClientIntegration:
    """Test Braintrust client integration patterns."""
    
    @pytest.mark.asyncio
    async def test_braintrust_client_context_manager(self):
        """Test Braintrust client async context manager integration."""
        with patch('sync.clients.braintrust.Braintrust') as mock_braintrust:
            api_key = SecretStr("test-key")
            
            async with BraintrustClient(api_key=api_key) as client:
                assert client is not None
                assert client.api_url == "https://api.braintrust.dev"
                
                # Mock a health check
                mock_org_info = MagicMock()
                mock_org_info.model_dump.return_value = {"id": "test-org"}
                client.client.organizations.retrieve = AsyncMock(return_value=mock_org_info)
                
                health = await client.health_check()
                assert health is True
    
    def test_braintrust_client_error_conversion(self):
        """Test error conversion in Braintrust client."""
        with patch('sync.clients.braintrust.Braintrust'):
            api_key = SecretStr("test-key")
            client = BraintrustClient(api_key=api_key)
            
            # Test not found detection
            not_found_error = Exception("User not found")
            assert client._is_not_found_error(not_found_error) is True
            
            status_404_error = Exception("HTTP 404 Client Error")
            assert client._is_not_found_error(status_404_error) is True
            
            other_error = Exception("Connection timeout")
            assert client._is_not_found_error(other_error) is False
            
            # Test error conversion
            converted = client._convert_to_braintrust_error(other_error)
            assert str(converted) == "Connection timeout"


class TestStateManagerIntegration:
    """Test state manager integration with file system."""
    
    def test_state_directory_creation(self, temp_state_dir):
        """Test that state manager creates directories as needed."""
        state_dir = temp_state_dir / "nested" / "state"
        
        # Directory doesn't exist initially
        assert not state_dir.exists()
        
        # Creating state manager should create directory
        state_manager = StateManager(state_dir=state_dir)
        assert state_dir.exists()
        assert state_manager.state_dir == state_dir
    
    def test_concurrent_state_access(self, temp_state_dir):
        """Test handling of concurrent state access patterns."""
        # This test simulates patterns that might occur in production
        state_manager1 = StateManager(state_dir=temp_state_dir)
        state_manager2 = StateManager(state_dir=temp_state_dir)
        
        # Both managers can create states
        state1 = state_manager1.create_sync_state("concurrent-1")
        state2 = state_manager2.create_sync_state("concurrent-2")
        
        # Both can save independently
        success1 = state_manager1.save_sync_state(state1)
        success2 = state_manager2.save_sync_state(state2)
        
        assert success1 is True
        assert success2 is True
        
        # Both can list all states
        states1 = state_manager1.list_sync_states()
        states2 = state_manager2.list_sync_states()
        
        assert len(states1) == 2
        assert len(states2) == 2
        assert set(states1) == set(states2)
        assert "concurrent-1" in states1
        assert "concurrent-2" in states1
    
    def test_state_backup_and_recovery(self, temp_state_dir):
        """Test state backup and recovery functionality."""
        state_manager = StateManager(state_dir=temp_state_dir)
        
        # Create initial state
        state = state_manager.create_sync_state("backup-test")
        state.add_mapping("test-okta", "test-bt", "test-org", "user")
        
        # Save initial state
        state_manager.save_sync_state(state)
        
        # Modify and save again (should create backup)
        state.add_mapping("test-okta-2", "test-bt-2", "test-org", "user")
        state_manager.save_sync_state(state)
        
        # Backup file should exist
        backup_file = temp_state_dir / "backup-test.json.backup"
        assert backup_file.exists()
        
        # Backup should contain the initial state
        import json
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
        
        assert len(backup_data["resource_mappings"]) == 1
        
        # Current state should have both mappings
        current_state = state_manager.load_sync_state("backup-test")
        assert len(current_state.resource_mappings) == 2