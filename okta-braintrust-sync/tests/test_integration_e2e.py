"""End-to-end integration tests for okta-braintrust-sync."""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from sync.config.loader import ConfigLoader
from sync.config.models import SyncConfig, OktaConfig, BraintrustOrgConfig, SyncRulesConfig, SyncModesConfig
from sync.config.models import UserSyncConfig, GroupSyncConfig, UserSyncMapping, GroupSyncMapping
from sync.clients.okta import OktaClient
from sync.clients.braintrust import BraintrustClient
from sync.core.state import StateManager
from sync.core.planner import SyncPlanner
from sync.core.executor import SyncExecutor
from sync.resources.base import SyncAction
from sync.audit.logger import AuditLogger
from pydantic import SecretStr


# Sample configuration for integration tests
INTEGRATION_CONFIG = """
okta:
  domain: "test.okta.com"
  api_token: "test-okta-token"
  rate_limit_per_minute: 600
  timeout_seconds: 30

braintrust_orgs:
  org1:
    api_key: "test-bt-key-1"
    url: "https://api.braintrust.dev"
    rate_limit_per_minute: 300
    timeout_seconds: 30
  org2:
    api_key: "test-bt-key-2"
    url: "https://api.braintrust.dev"
    rate_limit_per_minute: 300
    timeout_seconds: 30

sync_modes:
  declarative:
    enabled: true
    schedule: "0 */4 * * *"
    max_concurrent_orgs: 2

sync_rules:
  users:
    enabled: true
    mappings:
      - okta_filter: "status eq \\"ACTIVE\\""
        braintrust_orgs: ["org1", "org2"]
        enabled: true
  groups:
    enabled: true
    mappings:
      - okta_group_filter: "type eq \\"OKTA_GROUP\\""
        braintrust_orgs: ["org1"]
        enabled: true
"""


@pytest.fixture
def temp_config_file():
    """Create temporary config file for integration tests."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(INTEGRATION_CONFIG)
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_work_dir():
    """Create temporary working directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_okta_data():
    """Sample Okta data for integration tests."""
    return {
        "users": [
            {
                "id": "okta_user_1",
                "status": "ACTIVE",
                "profile": {
                    "email": "john.doe@example.com",
                    "firstName": "John",
                    "lastName": "Doe",
                    "login": "john.doe@example.com"
                },
                "groups": []
            },
            {
                "id": "okta_user_2", 
                "status": "ACTIVE",
                "profile": {
                    "email": "jane.smith@example.com",
                    "firstName": "Jane",
                    "lastName": "Smith",
                    "login": "jane.smith@example.com"
                },
                "groups": []
            },
            {
                "id": "okta_user_3",
                "status": "SUSPENDED",
                "profile": {
                    "email": "inactive.user@example.com",
                    "firstName": "Inactive",
                    "lastName": "User",
                    "login": "inactive.user@example.com"
                },
                "groups": []
            }
        ],
        "groups": [
            {
                "id": "okta_group_1",
                "type": "OKTA_GROUP",
                "profile": {
                    "name": "Engineering",
                    "description": "Engineering team"
                },
                "members": [
                    {"profile": {"email": "john.doe@example.com"}},
                    {"profile": {"email": "jane.smith@example.com"}}
                ]
            },
            {
                "id": "okta_group_2",
                "type": "OKTA_GROUP", 
                "profile": {
                    "name": "Marketing",
                    "description": "Marketing team"
                },
                "members": [
                    {"profile": {"email": "jane.smith@example.com"}}
                ]
            },
            {
                "id": "okta_group_3",
                "type": "AD_GROUP",
                "profile": {
                    "name": "AD_Imported",
                    "description": "AD imported group"
                },
                "members": []
            }
        ]
    }


@pytest.fixture
def mock_braintrust_data():
    """Sample Braintrust data for integration tests."""
    return {
        "org1": {
            "users": [
                {
                    "id": "bt_user_1",
                    "email": "john.doe@example.com",
                    "given_name": "John",
                    "family_name": "Doe"
                }
            ],
            "groups": [
                {
                    "id": "bt_group_1",
                    "name": "Engineering",
                    "description": "Engineering team",
                    "member_users": ["bt_user_1"],
                    "member_groups": []
                }
            ]
        },
        "org2": {
            "users": [],
            "groups": []
        }
    }


class TestConfigurationLoading:
    """Test configuration loading and validation."""
    
    def test_load_config_from_file(self, temp_config_file):
        """Test loading configuration from file."""
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        assert isinstance(config, SyncConfig)
        assert config.okta.domain == "test.okta.com"
        assert len(config.braintrust_orgs) == 2
        assert "org1" in config.braintrust_orgs
        assert "org2" in config.braintrust_orgs
        assert config.sync_modes.declarative.enabled is True
        assert config.sync_rules.users.enabled is True
        assert config.sync_rules.groups.enabled is True
    
    def test_config_validation_okta_settings(self, temp_config_file):
        """Test Okta configuration validation."""
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        assert config.okta.domain == "test.okta.com"
        assert config.okta.api_token.get_secret_value() == "test-okta-token"
        assert config.okta.rate_limit_per_minute == 600
        assert config.okta.timeout_seconds == 30
    
    def test_config_validation_braintrust_orgs(self, temp_config_file):
        """Test Braintrust organization configuration validation."""
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        org1_config = config.braintrust_orgs["org1"]
        assert org1_config.api_key.get_secret_value() == "test-bt-key-1"
        assert str(org1_config.url) == "https://api.braintrust.dev/"
        assert org1_config.rate_limit_per_minute == 300
        
        org2_config = config.braintrust_orgs["org2"]
        assert org2_config.api_key.get_secret_value() == "test-bt-key-2"
    
    def test_config_validation_sync_rules(self, temp_config_file):
        """Test sync rules configuration validation."""
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # User sync rules
        assert config.sync_rules.users.enabled is True
        assert len(config.sync_rules.users.mappings) == 1
        user_mapping = config.sync_rules.users.mappings[0]
        assert user_mapping.okta_filter == 'status eq "ACTIVE"'
        assert set(user_mapping.braintrust_orgs) == {"org1", "org2"}
        
        # Group sync rules
        assert config.sync_rules.groups.enabled is True
        assert len(config.sync_rules.groups.mappings) == 1
        group_mapping = config.sync_rules.groups.mappings[0]
        assert group_mapping.okta_group_filter == 'type eq "OKTA_GROUP"'
        assert group_mapping.braintrust_orgs == ["org1"]


class TestClientInitialization:
    """Test client initialization and health checks."""
    
    @pytest.mark.asyncio
    async def test_okta_client_initialization(self, temp_config_file):
        """Test Okta client initialization."""
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock the health check
        with patch('sync.clients.okta.OktaClient.health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            
            okta_client = OktaClient(
                domain=config.okta.domain,
                api_token=config.okta.api_token,
                timeout_seconds=config.okta.timeout_seconds,
                rate_limit_per_minute=config.okta.rate_limit_per_minute,
            )
            
            # Test health check
            is_healthy = await okta_client.health_check()
            assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_braintrust_client_initialization(self, temp_config_file):
        """Test Braintrust client initialization."""
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock the health check
        with patch('sync.clients.braintrust.BraintrustClient.health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            
            for org_name, org_config in config.braintrust_orgs.items():
                # Mock the actual Braintrust client initialization
                with patch('braintrust_api.Braintrust'):
                    bt_client = BraintrustClient(
                        api_key=org_config.api_key,
                        api_url=str(org_config.url),
                        timeout_seconds=org_config.timeout_seconds,
                        rate_limit_per_minute=org_config.rate_limit_per_minute,
                    )
                
                # Test health check
                is_healthy = await bt_client.health_check()
                assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_client_connectivity_failure(self, temp_config_file):
        """Test handling of client connectivity failures."""
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock failed health check
        with patch('sync.clients.okta.OktaClient.health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = False
            
            okta_client = OktaClient(
                domain=config.okta.domain,
                api_token=config.okta.api_token,
            )
            
            is_healthy = await okta_client.health_check()
            assert is_healthy is False


class TestEndToEndSyncPipeline:
    """Test complete end-to-end sync pipeline."""
    
    @pytest.mark.asyncio
    async def test_complete_sync_workflow(self, temp_config_file, temp_work_dir, mock_okta_data, mock_braintrust_data):
        """Test complete sync workflow from config to execution."""
        # Load configuration
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Initialize state manager with temp directory
        state_manager = StateManager(state_dir=str(temp_work_dir / "state"))
        
        # Initialize audit logger with temp directory  
        audit_logger = AuditLogger(audit_dir=temp_work_dir / "audit")
        
        # Mock clients and their responses
        mock_okta_client = MagicMock(spec=OktaClient)
        mock_bt_clients = {
            "org1": MagicMock(spec=BraintrustClient),
            "org2": MagicMock(spec=BraintrustClient),
        }
        
        # Mock Okta client responses
        mock_okta_client.health_check = AsyncMock(return_value=True)
        mock_okta_client.search_users = AsyncMock(return_value=[
            MagicMock(
                id=user["id"],
                status=user["status"],
                profile=MagicMock(**user["profile"])
            ) for user in mock_okta_data["users"] if user["status"] == "ACTIVE"
        ])
        mock_okta_client.search_groups = AsyncMock(return_value=[
            MagicMock(
                id=group["id"],
                type=group["type"],
                profile=MagicMock(**group["profile"]),
                members=[MagicMock(profile=MagicMock(**member["profile"])) for member in group["members"]]
            ) for group in mock_okta_data["groups"] if group["type"] == "OKTA_GROUP"
        ])
        
        # Mock Braintrust client responses
        for org_name, bt_client in mock_bt_clients.items():
            bt_client.health_check = AsyncMock(return_value=True)
            
            org_data = mock_braintrust_data[org_name]
            bt_client.list_users = AsyncMock(return_value=[
                MagicMock(**user) for user in org_data["users"]
            ])
            bt_client.list_groups = AsyncMock(return_value=[
                MagicMock(**group) for group in org_data["groups"]
            ])
            
            # Mock create operations
            bt_client.create_user = AsyncMock(side_effect=lambda **kwargs: MagicMock(
                id=f"bt_user_{len(org_data['users']) + 1}",
                **kwargs
            ))
            bt_client.create_group = AsyncMock(side_effect=lambda **kwargs: MagicMock(
                id=f"bt_group_{len(org_data['groups']) + 1}",
                **kwargs
            ))
            
            # Mock find operations
            bt_client.find_user_by_email = AsyncMock(return_value=None)
            bt_client.find_group_by_name = AsyncMock(return_value=None)
        
        # Create sync state
        sync_state = state_manager.create_sync_state("integration_test")
        
        # Initialize planner
        planner = SyncPlanner(
            config=config,
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        # Generate sync plan
        plan = await planner.generate_sync_plan(
            target_organizations=["org1", "org2"],
            resource_types=["user", "group"],
            dry_run=False,
        )
        
        # Verify plan contents
        assert plan.total_items > 0
        assert len(plan.user_items) > 0  # Should have active users
        assert len(plan.group_items) > 0  # Should have OKTA_GROUP groups
        assert plan.target_organizations == ["org1", "org2"]
        
        # Verify filtering worked (only active users)
        user_emails = [item.okta_resource_id for item in plan.user_items]
        assert "john.doe@example.com" in user_emails
        assert "jane.smith@example.com" in user_emails
        assert "inactive.user@example.com" not in user_emails  # Should be filtered out
        
        # Verify group filtering (only OKTA_GROUP groups)
        group_names = [item.okta_resource_id for item in plan.group_items]
        assert "Engineering" in group_names
        assert "Marketing" in group_names
        assert "AD_Imported" not in group_names  # Should be filtered out
        
        # Initialize executor with progress tracking
        progress_updates = []
        def progress_callback(progress):
            progress_updates.append({
                "phase": progress.current_phase,
                "completed": progress.completed_items,
                "failed": progress.failed_items,
                "total": progress.total_items,
            })
        
        executor = SyncExecutor(
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
            audit_logger=audit_logger,
            progress_callback=progress_callback,
        )
        
        # Execute sync plan
        final_progress = await executor.execute_sync_plan(
            plan=plan,
            dry_run=False,
            continue_on_error=True,
            max_concurrent_operations=3,
        )
        
        # Verify execution results
        assert final_progress.total_items == plan.total_items
        assert final_progress.current_phase == "completed"
        assert final_progress.completed_items > 0
        assert final_progress.get_completion_percentage() == 100.0
        
        # Verify progress callbacks were called
        assert len(progress_updates) > 0
        assert any(update["phase"] == "executing" for update in progress_updates)
        assert any(update["phase"] == "completed" for update in progress_updates)
        
        # Verify state was persisted
        final_state = state_manager.get_current_state()
        assert final_state is not None
        assert len(final_state.operations) > 0
        
        # Verify audit logs were created
        audit_files = list(audit_logger.audit_dir.glob("audit_*.jsonl"))
        assert len(audit_files) > 0
        
        summary_files = list(audit_logger.audit_dir.glob("summary_*.json"))
        assert len(summary_files) > 0
        
        # Verify audit summary
        summaries = audit_logger.get_execution_summaries(limit=1)
        assert len(summaries) == 1
        assert summaries[0].total_events > 0
        assert summaries[0].success_events > 0
    
    @pytest.mark.asyncio
    async def test_dry_run_workflow(self, temp_config_file, temp_work_dir, mock_okta_data, mock_braintrust_data):
        """Test dry run workflow doesn't make actual changes."""
        # Load configuration
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock clients (same setup as above but simpler)
        mock_okta_client = MagicMock(spec=OktaClient)
        mock_bt_clients = {"org1": MagicMock(spec=BraintrustClient)}
        
        # Setup basic mocks
        mock_okta_client.health_check = AsyncMock(return_value=True)
        mock_okta_client.search_users = AsyncMock(return_value=[
            MagicMock(
                id="user1",
                status="ACTIVE", 
                profile=MagicMock(email="test@example.com", firstName="Test", lastName="User")
            )
        ])
        mock_okta_client.search_groups = AsyncMock(return_value=[])
        
        mock_bt_clients["org1"].health_check = AsyncMock(return_value=True)
        mock_bt_clients["org1"].list_users = AsyncMock(return_value=[])
        mock_bt_clients["org1"].list_groups = AsyncMock(return_value=[])
        
        # Initialize components
        state_manager = StateManager(state_dir=temp_work_dir / "state")
        sync_state = state_manager.create_sync_state("dry_run_test")
        
        planner = SyncPlanner(
            config=config,
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        executor = SyncExecutor(
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        # Generate and execute dry run plan
        plan = await planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["user"],
            dry_run=True,
        )
        
        final_progress = await executor.execute_sync_plan(
            plan=plan,
            dry_run=True,
        )
        
        # Verify dry run completed without actual API calls
        assert final_progress.current_phase == "completed"
        
        # Verify no create/update calls were made
        mock_bt_clients["org1"].create_user.assert_not_called()
        mock_bt_clients["org1"].update_user.assert_not_called()
        
        # Verify results marked as dry run
        if final_progress.results:
            for result in final_progress.results:
                assert result.metadata.get("dry_run") is True
    
    @pytest.mark.asyncio 
    async def test_error_handling_and_recovery(self, temp_config_file, temp_work_dir):
        """Test error handling and recovery during sync."""
        # Load configuration
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock clients with some failures
        mock_okta_client = MagicMock(spec=OktaClient)
        mock_bt_clients = {"org1": MagicMock(spec=BraintrustClient)}
        
        # Setup Okta mock
        mock_okta_client.health_check = AsyncMock(return_value=True)
        mock_okta_client.search_users = AsyncMock(return_value=[
            MagicMock(
                id="user1",
                status="ACTIVE",
                profile=MagicMock(email="success@example.com", firstName="Success", lastName="User")
            ),
            MagicMock(
                id="user2", 
                status="ACTIVE",
                profile=MagicMock(email="failure@example.com", firstName="Failure", lastName="User")
            )
        ])
        mock_okta_client.search_groups = AsyncMock(return_value=[])
        mock_okta_client.get_user = AsyncMock(side_effect=lambda user_id: 
            MagicMock(
                id=user_id,
                profile=MagicMock(
                    email="success@example.com" if user_id == "user1" else "failure@example.com",
                    firstName="Success" if user_id == "user1" else "Failure",
                    lastName="User"
                )
            )
        )
        
        # Setup Braintrust mock with failures
        mock_bt_clients["org1"].health_check = AsyncMock(return_value=True)
        mock_bt_clients["org1"].list_users = AsyncMock(return_value=[])
        mock_bt_clients["org1"].list_groups = AsyncMock(return_value=[])
        
        # Mock create_user to succeed for first user, fail for second
        def create_user_side_effect(**kwargs):
            if kwargs.get("email") == "success@example.com":
                return MagicMock(id="bt_user_1", **kwargs)
            else:
                raise Exception("Simulated API failure")
        
        mock_bt_clients["org1"].create_user = AsyncMock(side_effect=create_user_side_effect)
        
        # Initialize components
        state_manager = StateManager(state_dir=temp_work_dir / "state")
        audit_logger = AuditLogger(audit_dir=temp_work_dir / "audit")
        sync_state = state_manager.create_sync_state("error_test")
        
        planner = SyncPlanner(
            config=config,
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        executor = SyncExecutor(
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
            audit_logger=audit_logger,
        )
        
        # Generate and execute plan with continue_on_error=True
        plan = await planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["user"],
        )
        
        final_progress = await executor.execute_sync_plan(
            plan=plan,
            continue_on_error=True,
        )
        
        # Verify mixed results
        assert final_progress.completed_items > 0  # At least one success
        assert final_progress.failed_items > 0     # At least one failure
        assert len(final_progress.errors) > 0      # Errors recorded
        assert final_progress.current_phase == "completed"  # Completed despite errors
        
        # Verify audit logging captured the errors
        summaries = audit_logger.get_execution_summaries(limit=1)
        assert len(summaries) == 1
        assert summaries[0].error_events > 0


class TestMultiOrganizationSync:
    """Test synchronization across multiple Braintrust organizations."""
    
    @pytest.mark.asyncio
    async def test_multi_org_user_sync(self, temp_config_file, temp_work_dir):
        """Test syncing users to multiple organizations."""
        # Load configuration
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock clients
        mock_okta_client = MagicMock(spec=OktaClient)
        mock_bt_clients = {
            "org1": MagicMock(spec=BraintrustClient),
            "org2": MagicMock(spec=BraintrustClient),
        }
        
        # Setup Okta mock
        mock_okta_client.health_check = AsyncMock(return_value=True)
        mock_okta_client.search_users = AsyncMock(return_value=[
            MagicMock(
                id="user1",
                status="ACTIVE",
                profile=MagicMock(email="multi@example.com", firstName="Multi", lastName="User")
            )
        ])
        mock_okta_client.search_groups = AsyncMock(return_value=[])
        mock_okta_client.get_user = AsyncMock(return_value=MagicMock(
            id="user1",
            profile=MagicMock(email="multi@example.com", firstName="Multi", lastName="User")
        ))
        
        # Setup Braintrust mocks
        create_call_count = {"org1": 0, "org2": 0}
        
        for org_name, bt_client in mock_bt_clients.items():
            bt_client.health_check = AsyncMock(return_value=True)
            bt_client.list_users = AsyncMock(return_value=[])
            bt_client.list_groups = AsyncMock(return_value=[])
            
            def make_create_user(org):
                def create_user(**kwargs):
                    create_call_count[org] += 1
                    return MagicMock(id=f"bt_user_{org}_{create_call_count[org]}", **kwargs)
                return AsyncMock(side_effect=create_user)
            
            bt_client.create_user = make_create_user(org_name)
        
        # Initialize components
        state_manager = StateManager(state_dir=temp_work_dir / "state")
        sync_state = state_manager.create_sync_state("multi_org_test")
        
        planner = SyncPlanner(
            config=config,
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        executor = SyncExecutor(
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        # Generate and execute plan for both orgs
        plan = await planner.generate_sync_plan(
            target_organizations=["org1", "org2"],
            resource_types=["user"],
        )
        
        final_progress = await executor.execute_sync_plan(plan=plan)
        
        # Verify user was created in both organizations
        assert create_call_count["org1"] > 0
        assert create_call_count["org2"] > 0
        
        # Verify plan items for both orgs
        org_items = {}
        for item in plan.user_items:
            if item.braintrust_org not in org_items:
                org_items[item.braintrust_org] = []
            org_items[item.braintrust_org].append(item)
        
        assert "org1" in org_items
        assert "org2" in org_items
        assert len(org_items["org1"]) > 0
        assert len(org_items["org2"]) > 0


class TestCLIIntegration:
    """Test CLI integration with the sync system."""
    
    def test_cli_import_structure(self):
        """Test that CLI imports work correctly."""
        try:
            from sync.cli import app, _initialize_clients, _display_sync_plan, _display_execution_results
            
            # Verify CLI app is initialized
            assert app is not None
            assert hasattr(app, 'commands')
            
            # Verify helper functions exist
            assert callable(_initialize_clients)
            assert callable(_display_sync_plan) 
            assert callable(_display_execution_results)
        except ImportError as e:
            pytest.skip(f"CLI imports failed: {e}")
    
    @pytest.mark.asyncio
    async def test_cli_client_initialization(self, temp_config_file):
        """Test CLI client initialization helper."""
        from sync.cli import _initialize_clients
        
        # Load config
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock client classes
        with patch('sync.cli.OktaClient') as mock_okta_class, \
             patch('sync.cli.BraintrustClient') as mock_bt_class:
            
            mock_okta_client = MagicMock()
            mock_okta_class.return_value = mock_okta_client
            
            mock_bt_client = MagicMock()
            mock_bt_class.return_value = mock_bt_client
            
            # Test initialization 
            okta_client, braintrust_clients = await _initialize_clients(config)
            
            # Verify clients were created
            assert okta_client == mock_okta_client
            assert len(braintrust_clients) == 2
            assert "org1" in braintrust_clients
            assert "org2" in braintrust_clients
            
            # Verify clients were initialized with correct parameters
            mock_okta_class.assert_called_once()
            assert mock_bt_class.call_count == 2  # Two organizations


class TestStateManagement:
    """Test state management across sync operations."""
    
    def test_state_persistence(self, temp_work_dir):
        """Test that state is properly persisted between operations."""
        # Initialize state manager
        state_manager = StateManager(state_dir=temp_work_dir / "state")
        
        # Create initial state
        sync_state = state_manager.create_sync_state("persistence_test")
        initial_state_id = sync_state.sync_id
        
        # Add some operations
        from sync.core.state import SyncOperation
        operation = SyncOperation(
            operation_id="test_op_1",
            resource_type="user",
            okta_id="user1@example.com",
            braintrust_org="org1",
            operation_type="create",
            status="pending",
        )
        sync_state.add_operation(operation)
        
        # Save state
        state_manager.save_state()
        
        # Create new state manager instance (simulating restart)
        new_state_manager = StateManager(state_dir=temp_work_dir / "state")
        
        # Load state
        loaded_state = new_state_manager.get_current_state()
        
        # Verify state was persisted
        assert loaded_state is not None
        assert loaded_state.sync_id == initial_state_id
        assert len(loaded_state.operations) == 1
        assert loaded_state.operations[0].operation_id == "test_op_1"
    
    def test_state_recovery_after_failure(self, temp_work_dir):
        """Test state recovery after sync failure."""
        # Initialize state manager
        state_manager = StateManager(state_dir=temp_work_dir / "state")
        
        # Create state with mixed operations
        sync_state = state_manager.create_sync_state("recovery_test")
        
        from sync.core.state import SyncOperation
        from datetime import datetime, timezone
        
        # Add completed operation
        completed_op = SyncOperation(
            operation_id="completed_op",
            resource_type="user",
            okta_id="completed@example.com",
            braintrust_org="org1",
            braintrust_id="bt_user_1",
            operation_type="create",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        sync_state.add_operation(completed_op)
        
        # Add failed operation
        failed_op = SyncOperation(
            operation_id="failed_op",
            resource_type="user", 
            okta_id="failed@example.com",
            braintrust_org="org1",
            operation_type="create",
            status="failed",
            started_at=datetime.now(timezone.utc),
            error_message="Simulated failure",
        )
        sync_state.add_operation(failed_op)
        
        # Add pending operation
        pending_op = SyncOperation(
            operation_id="pending_op",
            resource_type="user",
            okta_id="pending@example.com", 
            braintrust_org="org1",
            operation_type="create",
            status="pending",
        )
        sync_state.add_operation(pending_op)
        
        # Save state
        state_manager.save_state()
        
        # Verify state contains all operations
        assert len(sync_state.operations) == 3
        
        # Verify operations by status
        completed_ops = [op for op in sync_state.operations if op.status == "completed"]
        failed_ops = [op for op in sync_state.operations if op.status == "failed"]
        pending_ops = [op for op in sync_state.operations if op.status == "pending"]
        
        assert len(completed_ops) == 1
        assert len(failed_ops) == 1
        assert len(pending_ops) == 1
        
        # Verify specific operation details
        assert completed_ops[0].braintrust_id == "bt_user_1"
        assert failed_ops[0].error_message == "Simulated failure"
        assert pending_ops[0].status == "pending"


class TestPerformanceAndScalability:
    """Test performance characteristics and scalability."""
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, temp_config_file, temp_work_dir):
        """Test concurrent sync operations."""
        # Load configuration  
        loader = ConfigLoader()
        config = loader.load_config(temp_config_file)
        
        # Mock clients with delays to test concurrency
        mock_okta_client = MagicMock(spec=OktaClient)
        mock_bt_clients = {"org1": MagicMock(spec=BraintrustClient)}
        
        # Create multiple users for concurrent processing
        mock_users = []
        for i in range(5):
            mock_users.append(MagicMock(
                id=f"user_{i}",
                status="ACTIVE",
                profile=MagicMock(
                    email=f"user{i}@example.com",
                    firstName=f"User{i}",
                    lastName="Test"
                )
            ))
        
        mock_okta_client.health_check = AsyncMock(return_value=True)
        mock_okta_client.search_users = AsyncMock(return_value=mock_users)
        mock_okta_client.search_groups = AsyncMock(return_value=[])
        mock_okta_client.get_user = AsyncMock(side_effect=lambda user_id: next(
            user for user in mock_users if user.id == user_id
        ))
        
        # Mock Braintrust client with simulated delay
        mock_bt_clients["org1"].health_check = AsyncMock(return_value=True)
        mock_bt_clients["org1"].list_users = AsyncMock(return_value=[])
        mock_bt_clients["org1"].list_groups = AsyncMock(return_value=[])
        
        create_times = []
        async def create_user_with_delay(**kwargs):
            import asyncio
            start_time = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)  # Simulate API delay
            end_time = asyncio.get_event_loop().time()
            create_times.append((start_time, end_time))
            return MagicMock(id=f"bt_{len(create_times)}", **kwargs)
        
        mock_bt_clients["org1"].create_user = AsyncMock(side_effect=create_user_with_delay)
        
        # Initialize components
        state_manager = StateManager(state_dir=temp_work_dir / "state")
        sync_state = state_manager.create_sync_state("concurrent_test")
        
        planner = SyncPlanner(
            config=config,
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        executor = SyncExecutor(
            okta_client=mock_okta_client,
            braintrust_clients=mock_bt_clients,
            state_manager=state_manager,
        )
        
        # Execute with concurrency
        start_time = asyncio.get_event_loop().time()
        
        plan = await planner.generate_sync_plan(
            target_organizations=["org1"],
            resource_types=["user"],
        )
        
        final_progress = await executor.execute_sync_plan(
            plan=plan,
            max_concurrent_operations=3,
        )
        
        end_time = asyncio.get_event_loop().time()
        total_duration = end_time - start_time
        
        # Verify all operations completed
        assert final_progress.completed_items == 5
        assert len(create_times) == 5
        
        # Verify concurrent execution (should be faster than sequential)
        # With 3 concurrent operations and 0.1s delay each, total time should be < 5 * 0.1s
        assert total_duration < 0.4  # Allow some overhead
        
        # Verify operations overlapped in time
        overlaps = 0
        for i in range(len(create_times)):
            for j in range(i + 1, len(create_times)):
                start1, end1 = create_times[i]
                start2, end2 = create_times[j]
                # Check if operations overlapped
                if not (end1 <= start2 or end2 <= start1):
                    overlaps += 1
        
        # Should have some overlapping operations due to concurrency
        assert overlaps > 0


# Performance marker for optional performance tests
pytestmark = pytest.mark.asyncio