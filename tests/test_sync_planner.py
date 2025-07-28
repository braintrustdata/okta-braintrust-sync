"""Tests for SyncPlanner functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from sync.config.models import SyncConfig, OktaConfig, BraintrustOrgConfig, SyncRulesConfig, SyncModesConfig, UserSyncConfig, GroupSyncConfig, UserSyncMapping, GroupSyncMapping
from sync.core.planner import SyncPlanner, SyncPlan
from sync.core.state import StateManager
from sync.resources.base import SyncPlanItem, SyncAction
from pydantic import SecretStr


@pytest.fixture
def mock_sync_config():
    """Create mock sync configuration."""
    return SyncConfig(
        okta=OktaConfig(
            domain="test.okta.com",
            api_token=SecretStr("test-token"),
        ),
        braintrust_orgs={
            "org1": BraintrustOrgConfig(
                api_key=SecretStr("test-key-1"),
                api_url="https://api.braintrust.dev",
            ),
            "org2": BraintrustOrgConfig(
                api_key=SecretStr("test-key-2"),
                api_url="https://api.braintrust.dev",
            ),
        },
        sync_modes=SyncModesConfig(),
        sync_rules=SyncRulesConfig(
            users=UserSyncConfig(
                enabled=True,
                mappings=[
                    UserSyncMapping(
                        okta_filter='status eq "ACTIVE"',
                        braintrust_orgs=["org1", "org2"],
                    )
                ],
            ),
            groups=GroupSyncConfig(
                enabled=True,
                mappings=[
                    GroupSyncMapping(
                        okta_group_filter='type eq "OKTA_GROUP"',
                        braintrust_orgs=["org1", "org2"],
                    )
                ],
            ),
        ),
    )


@pytest.fixture
def mock_clients():
    """Create mock clients."""
    okta_client = MagicMock()
    okta_client.health_check = AsyncMock(return_value=True)
    
    braintrust_clients = {
        "org1": MagicMock(),
        "org2": MagicMock(),
    }
    
    # Set up health_check methods for braintrust clients
    for client in braintrust_clients.values():
        client.health_check = AsyncMock(return_value=True)
    
    return okta_client, braintrust_clients


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    state_manager = MagicMock(spec=StateManager)
    mock_state = MagicMock()
    state_manager.get_current_state.return_value = mock_state
    return state_manager


@pytest.fixture
def sync_planner(mock_sync_config, mock_clients, mock_state_manager):
    """Create SyncPlanner instance."""
    okta_client, braintrust_clients = mock_clients
    
    # Create a mock sync_rules with all required attributes
    from unittest.mock import MagicMock
    mock_sync_rules = MagicMock()
    mock_sync_rules.identity_mapping_strategy = "email"
    mock_sync_rules.custom_field_mappings = {}
    mock_sync_rules.sync_group_memberships = True
    mock_sync_rules.group_name_prefix = ""
    mock_sync_rules.group_name_suffix = ""
    
    # Add additional properties for other tests and planner methods
    mock_sync_rules.sync_all = True
    mock_sync_rules.create_missing = True
    mock_sync_rules.update_existing = True
    mock_sync_rules.only_active_users = True
    mock_sync_rules.email_domain_filters = {}
    mock_sync_rules.group_filters = {}
    mock_sync_rules.profile_filters = {}
    mock_sync_rules.group_type_filters = {}
    mock_sync_rules.group_name_patterns = {}
    mock_sync_rules.group_profile_filters = {}
    mock_sync_rules.min_group_members = {}
    mock_sync_rules.limit = None
    
    # Add properties that _get_sync_rules_dict method expects
    mock_sync_rules.create_missing_resources = True
    mock_sync_rules.update_existing_resources = True
    mock_sync_rules.max_resources_per_type = None
    
    # Add model_dump method for config hash calculation
    mock_sync_rules.model_dump.return_value = {
        "sync_all": True,
        "create_missing": True,
        "update_existing": True,
        "only_active_users": True,
    }
    
    # Replace the sync_rules in the config
    mock_sync_config.sync_rules = mock_sync_rules
    
    return SyncPlanner(
        config=mock_sync_config,
        okta_client=okta_client,
        braintrust_clients=braintrust_clients,
        state_manager=mock_state_manager,
    )


class TestSyncPlan:
    """Test SyncPlan model."""
    
    def test_sync_plan_creation(self):
        """Test sync plan creation with defaults."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1", "org2"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        assert plan.config_hash == "test-hash"
        assert plan.target_organizations == ["org1", "org2"]
        assert len(plan.user_items) == 0
        assert len(plan.group_items) == 0
        assert plan.total_items == 0
        assert plan.dependencies_resolved is False
    
    def test_add_items_users(self):
        """Test adding user items to plan."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        user_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New user",
            ),
            SyncPlanItem(
                okta_resource_id="user2@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.UPDATE,
                reason="Name changed",
            ),
        ]
        
        plan.add_items(user_items, "user")
        
        assert len(plan.user_items) == 2
        assert len(plan.group_items) == 0
        assert plan.total_items == 2
        assert plan.items_by_action["create"] == 1
        assert plan.items_by_action["update"] == 1
        assert plan.items_by_org["org1"] == 2
    
    def test_add_items_groups(self):
        """Test adding group items to plan."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        group_items = [
            SyncPlanItem(
                okta_resource_id="Engineering",
                okta_resource_type="group",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New group",
            ),
        ]
        
        plan.add_items(group_items, "group")
        
        assert len(plan.user_items) == 0
        assert len(plan.group_items) == 1
        assert plan.total_items == 1
        assert plan.items_by_action["create"] == 1
        assert plan.items_by_org["org1"] == 1
    
    def test_get_all_items(self):
        """Test getting all items in dependency order."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        user_item = SyncPlanItem(
            okta_resource_id="user1@example.com",
            okta_resource_type="user",
            braintrust_org="org1",
            action=SyncAction.CREATE,
            reason="New user",
        )
        
        group_item = SyncPlanItem(
            okta_resource_id="Engineering",
            okta_resource_type="group",
            braintrust_org="org1",
            action=SyncAction.CREATE,
            reason="New group",
        )
        
        plan.add_items([user_item], "user")
        plan.add_items([group_item], "group")
        
        all_items = plan.get_all_items()
        
        assert len(all_items) == 2
        # Users should come first (dependency order)
        assert all_items[0].okta_resource_type == "user"
        assert all_items[1].okta_resource_type == "group"
    
    def test_get_items_by_org(self):
        """Test getting items by organization."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1", "org2"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        org1_item = SyncPlanItem(
            okta_resource_id="user1@example.com",
            okta_resource_type="user",
            braintrust_org="org1",
            action=SyncAction.CREATE,
            reason="New user",
        )
        
        org2_item = SyncPlanItem(
            okta_resource_id="user1@example.com",
            okta_resource_type="user",
            braintrust_org="org2",
            action=SyncAction.CREATE,
            reason="New user",
        )
        
        plan.add_items([org1_item, org2_item], "user")
        
        org1_items = plan.get_items_by_org("org1")
        org2_items = plan.get_items_by_org("org2")
        
        assert len(org1_items) == 1
        assert len(org2_items) == 1
        assert org1_items[0].braintrust_org == "org1"
        assert org2_items[0].braintrust_org == "org2"
    
    def test_get_summary(self):
        """Test getting plan summary."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        user_item = SyncPlanItem(
            okta_resource_id="user1@example.com",
            okta_resource_type="user",
            braintrust_org="org1",
            action=SyncAction.CREATE,
            reason="New user",
        )
        
        plan.add_items([user_item], "user")
        plan.estimated_duration_minutes = 2.5
        plan.warnings = ["Test warning"]
        
        summary = plan.get_summary()
        
        assert summary["total_items"] == 1
        assert summary["user_items"] == 1
        assert summary["group_items"] == 0
        assert summary["target_organizations"] == ["org1"]
        assert summary["estimated_duration_minutes"] == 2.5
        assert summary["warnings"] == ["Test warning"]


class TestSyncPlannerInit:
    """Test SyncPlanner initialization."""
    
    def test_init(self, sync_planner, mock_sync_config, mock_clients):
        """Test planner initialization."""
        okta_client, braintrust_clients = mock_clients
        
        assert sync_planner.config == mock_sync_config
        assert sync_planner.okta_client == okta_client
        assert sync_planner.braintrust_clients == braintrust_clients
        assert sync_planner.user_syncer is not None
        assert sync_planner.group_syncer is not None


class TestSyncPlannerPlanGeneration:
    """Test sync plan generation."""
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_users_only(self, sync_planner):
        """Test generating plan for users only."""
        # Mock user syncer to return plan items
        user_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New user",
            ),
        ]
        
        sync_planner.user_syncer.generate_sync_plan = AsyncMock(return_value=user_items)
        sync_planner.group_syncer.generate_sync_plan = AsyncMock(return_value=[])
        
        plan = await sync_planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["user"],
        )
        
        assert plan.total_items == 1
        assert len(plan.user_items) == 1
        assert len(plan.group_items) == 0
        assert plan.target_organizations == ["org1"]
        assert plan.dependencies_resolved is True
        assert plan.estimated_duration_minutes is not None
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_groups_only(self, sync_planner):
        """Test generating plan for groups only."""
        # Mock group syncer to return plan items
        group_items = [
            SyncPlanItem(
                okta_resource_id="Engineering",
                okta_resource_type="group",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New group",
            ),
        ]
        
        sync_planner.user_syncer.generate_sync_plan = AsyncMock(return_value=[])
        sync_planner.group_syncer.generate_sync_plan = AsyncMock(return_value=group_items)
        
        plan = await sync_planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["group"],
        )
        
        assert plan.total_items == 1
        assert len(plan.user_items) == 0
        assert len(plan.group_items) == 1
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_both_types(self, sync_planner):
        """Test generating plan for both users and groups."""
        user_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New user",
            ),
        ]
        
        group_items = [
            SyncPlanItem(
                okta_resource_id="Engineering",
                okta_resource_type="group",
                braintrust_org="org1", 
                action=SyncAction.CREATE,
                reason="New group",
            ),
        ]
        
        sync_planner.user_syncer.generate_sync_plan = AsyncMock(return_value=user_items)
        sync_planner.group_syncer.generate_sync_plan = AsyncMock(return_value=group_items)
        
        plan = await sync_planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["user", "group"],
        )
        
        assert plan.total_items == 2
        assert len(plan.user_items) == 1
        assert len(plan.group_items) == 1
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_multiple_orgs(self, sync_planner):
        """Test generating plan for multiple organizations."""
        user_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New user",
            ),
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org2",
                action=SyncAction.CREATE,
                reason="New user",
            ),
        ]
        
        sync_planner.user_syncer.generate_sync_plan = AsyncMock(return_value=user_items)
        sync_planner.group_syncer.generate_sync_plan = AsyncMock(return_value=[])
        
        plan = await sync_planner.generate_sync_plan(
            target_organizations=["org1", "org2"],
            resource_types=["user"],
        )
        
        assert plan.total_items == 2
        assert plan.target_organizations == ["org1", "org2"]
        assert plan.items_by_org["org1"] == 1
        assert plan.items_by_org["org2"] == 1
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_with_filters(self, sync_planner):
        """Test generating plan with Okta filters."""
        user_items = [
            SyncPlanItem(
                okta_resource_id="user1@example.com",
                okta_resource_type="user",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                reason="New user",
            ),
        ]
        
        sync_planner.user_syncer.generate_sync_plan = AsyncMock(return_value=user_items)
        sync_planner.group_syncer.generate_sync_plan = AsyncMock(return_value=[])
        
        okta_filters = {
            "user": "status eq \"ACTIVE\"",
            "group": "type eq \"OKTA_GROUP\"",
        }
        
        plan = await sync_planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["user"],
            okta_filters=okta_filters,
        )
        
        assert plan.total_items == 1
        
        # Verify filters were passed to syncers
        sync_planner.user_syncer.generate_sync_plan.assert_called_once_with(
            braintrust_orgs=["org1"],
            sync_rules={
                "sync_all": True,
                "create_missing": True,
                "update_existing": True,
                "only_active_users": True,
                "email_domain_filters": {},
                "group_filters": {},
                "profile_filters": {},
                "group_type_filters": {},
                "group_name_patterns": {},
                "group_profile_filters": {},
                "min_group_members": {},
                "limit": None,
            },
            okta_filter="status eq \"ACTIVE\"",
        )
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_invalid_org(self, sync_planner):
        """Test generating plan with invalid organization."""
        with pytest.raises(ValueError, match="No Braintrust client configured for org: invalid_org"):
            await sync_planner.generate_sync_plan(
                target_organizations=["invalid_org"],
                resource_types=["user"],
            )
    
    @pytest.mark.asyncio
    async def test_generate_sync_plan_empty_result(self, sync_planner):
        """Test generating plan with no items."""
        sync_planner.user_syncer.generate_sync_plan = AsyncMock(return_value=[])
        sync_planner.group_syncer.generate_sync_plan = AsyncMock(return_value=[])
        
        plan = await sync_planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["user", "group"],
        )
        
        assert plan.total_items == 0
        assert len(plan.warnings) > 0
        assert any("No sync operations planned" in warning for warning in plan.warnings)


class TestSyncPlannerDependencyResolution:
    """Test dependency resolution."""
    
    def test_resolve_dependencies_user_group_order(self, sync_planner):
        """Test that dependencies are resolved with users before groups."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        user_item = SyncPlanItem(
            okta_resource_id="user1@example.com",
            okta_resource_type="user",
            braintrust_org="org1",
            action=SyncAction.CREATE,
            reason="New user",
        )
        
        group_item = SyncPlanItem(
            okta_resource_id="Engineering",
            okta_resource_type="group",
            braintrust_org="org1",
            action=SyncAction.CREATE,
            reason="New group",
        )
        
        plan.add_items([user_item], "user")
        plan.add_items([group_item], "group")
        
        resolved_plan = sync_planner._resolve_dependencies(plan)
        
        assert resolved_plan.dependencies_resolved is True
        
        # Groups should have user dependencies
        group_deps = resolved_plan.group_items[0].dependencies
        assert "user1@example.com" in group_deps
        assert resolved_plan.group_items[0].metadata["depends_on_users"] == 1


class TestSyncPlannerEstimation:
    """Test duration estimation and warning generation."""
    
    def test_estimate_duration(self, sync_planner):
        """Test duration estimation."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1", "org2"],
            created_at=datetime.utcnow().isoformat(),
        )
        
        # Add various actions
        plan.items_by_action = {
            "create": 5,
            "update": 3, 
            "skip": 10,
        }
        
        duration = sync_planner._estimate_duration(plan)
        
        assert duration is not None
        assert duration > 0
        # Should be roughly: (5 * 0.5) + (3 * 0.3) + (10 * 0.1) + overhead
        expected_base = (5 * 0.5) + (3 * 0.3) + (10 * 0.1)  # 4.4 minutes
        expected_with_overhead = expected_base * 1.2 + (2 * 0.5)  # +20% + org overhead
        assert abs(duration - expected_with_overhead) < 0.1
    
    def test_generate_warnings_large_plan(self, sync_planner):
        """Test warning generation for large plans."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        plan.total_items = 1500  # Large plan
        plan.items_by_action = {"create": 150}  # Many creates
        
        warnings = sync_planner._generate_warnings(plan)
        
        assert len(warnings) >= 2
        assert any("Large sync plan" in warning for warning in warnings)
        assert any("150 resource creations" in warning for warning in warnings)
    
    def test_generate_warnings_multi_org(self, sync_planner):
        """Test warning generation for multi-org sync."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1", "org2", "org3"],
            created_at=datetime.utcnow().isoformat(),
        )
        plan.total_items = 10
        
        warnings = sync_planner._generate_warnings(plan)
        
        assert any("multiple organizations" in warning for warning in warnings)
    
    def test_generate_warnings_no_changes(self, sync_planner):
        """Test warning generation for empty plan."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        plan.total_items = 0
        
        warnings = sync_planner._generate_warnings(plan)
        
        assert any("No sync operations planned" in warning for warning in warnings)
    
    def test_generate_warnings_only_skips(self, sync_planner):
        """Test warning generation for plan with only skips."""
        plan = SyncPlan(
            config_hash="test-hash",
            target_organizations=["org1"],
            created_at=datetime.utcnow().isoformat(),
        )
        plan.total_items = 5
        plan.items_by_action = {"skip": 5}
        
        warnings = sync_planner._generate_warnings(plan)
        
        assert any("All planned operations are skips" in warning for warning in warnings)


class TestSyncPlannerUtilities:
    """Test utility methods."""
    
    def test_calculate_config_hash(self, sync_planner):
        """Test configuration hash calculation."""
        hash1 = sync_planner._calculate_config_hash()
        hash2 = sync_planner._calculate_config_hash()
        
        # Same config should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 16  # MD5 hash truncated to 16 chars
    
    def test_get_sync_rules_dict(self, sync_planner):
        """Test sync rules dictionary conversion."""
        sync_rules = sync_planner._get_sync_rules_dict()
        
        assert isinstance(sync_rules, dict)
        assert "sync_all" in sync_rules
        assert "create_missing" in sync_rules
        assert "update_existing" in sync_rules
        assert "only_active_users" in sync_rules
        assert sync_rules["sync_all"] is True
    
    @pytest.mark.asyncio
    async def test_validate_plan_preconditions_success(self, sync_planner):
        """Test successful precondition validation."""
        # Mock healthy API clients
        sync_planner.okta_client.health_check = AsyncMock(return_value=True)
        for client in sync_planner.braintrust_clients.values():
            client.health_check = AsyncMock(return_value=True)
        
        errors = await sync_planner.validate_plan_preconditions(["org1", "org2"])
        
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_plan_preconditions_okta_fail(self, sync_planner):
        """Test precondition validation with Okta failure."""
        sync_planner.okta_client.health_check = AsyncMock(return_value=False)
        
        errors = await sync_planner.validate_plan_preconditions(["org1"])
        
        assert len(errors) == 1
        assert "Okta API health check failed" in errors[0]
    
    @pytest.mark.asyncio
    async def test_validate_plan_preconditions_braintrust_fail(self, sync_planner):
        """Test precondition validation with Braintrust failure."""
        sync_planner.okta_client.health_check = AsyncMock(return_value=True)
        sync_planner.braintrust_clients["org1"].health_check = AsyncMock(return_value=False)
        
        errors = await sync_planner.validate_plan_preconditions(["org1"])
        
        assert len(errors) == 1
        assert "Braintrust API health check failed for org: org1" in errors[0]
    
    @pytest.mark.asyncio
    async def test_validate_plan_preconditions_invalid_org(self, sync_planner):
        """Test precondition validation with invalid organization."""
        errors = await sync_planner.validate_plan_preconditions(["invalid_org"])
        
        assert len(errors) == 1
        assert "No Braintrust client configured for organization: invalid_org" in errors[0]