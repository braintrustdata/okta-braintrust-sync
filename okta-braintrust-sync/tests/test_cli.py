"""Tests for CLI commands functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from pathlib import Path
from typer.testing import CliRunner

from sync.cli import app, _initialize_clients, _display_sync_plan, _display_execution_results
from sync.config.models import SyncConfig, OktaConfig, BraintrustOrgConfig, SyncRulesConfig, SyncModesConfig
from sync.core.planner import SyncPlan
from sync.core.executor import ExecutionProgress
from sync.resources.base import SyncPlanItem, SyncAction
from datetime import datetime, timezone
from pydantic import SecretStr


# Test configuration for CLI tests
TEST_CONFIG_CONTENT = """
okta:
  domain: "test.okta.com"
  api_token: "test-token"

braintrust_orgs:
  org1:
    api_key: "test-key-1"
    api_url: "https://api.braintrust.dev"

sync_modes:
  declarative:
    enabled: true
    
sync_rules:
  sync_all: true
"""


@pytest.fixture
def cli_runner():
    """Create CLI runner instance."""
    return CliRunner()


@pytest.fixture
def mock_config_file(tmp_path):
    """Create temporary config file."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(TEST_CONFIG_CONTENT)
    return config_file


@pytest.fixture
def sample_sync_plan():
    """Create sample sync plan for testing."""
    plan = SyncPlan(
        config_hash="test-hash",
        target_organizations=["org1"],
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Add some sample items
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
    
    group_items = [
        SyncPlanItem(
            okta_resource_id="Engineering",
            okta_resource_type="group",
            braintrust_org="org1",
            action=SyncAction.CREATE,
            reason="New group",
        ),
    ]
    
    plan.add_items(user_items, "user")
    plan.add_items(group_items, "group")
    plan.estimated_duration_minutes = 2.5
    plan.warnings = ["Test warning"]
    
    return plan


@pytest.fixture
def sample_execution_progress():
    """Create sample execution progress for testing."""
    progress = ExecutionProgress(
        execution_id="test-exec-123",
        plan_id="test-plan-456",
        started_at=datetime.now(timezone.utc),
        total_items=10,
    )
    
    progress.completed_items = 8
    progress.failed_items = 1
    progress.skipped_items = 1
    progress.current_phase = "completed"
    progress.completed_at = datetime.now(timezone.utc)
    progress.errors = ["User sync failed: API error"]
    progress.warnings = ["Group has no members"]
    
    return progress


class TestCLIValidateCommand:
    """Test validate command."""
    
    @patch('sync.cli.ConfigLoader')
    @patch('sync.cli._initialize_clients')
    def test_validate_success(self, mock_init_clients, mock_config_loader, cli_runner, mock_config_file):
        """Test successful validation command."""
        # Mock configuration loading
        mock_loader = MagicMock()
        mock_config = MagicMock(spec=SyncConfig)
        mock_loader.load_config.return_value = mock_config
        mock_config_loader.return_value = mock_loader
        
        # Mock client initialization and health checks
        mock_okta_client = MagicMock()
        mock_okta_client.health_check = AsyncMock(return_value=True)
        mock_braintrust_clients = {
            "org1": MagicMock()
        }
        mock_braintrust_clients["org1"].health_check = AsyncMock(return_value=True)
        
        async def mock_init():
            return mock_okta_client, mock_braintrust_clients
        
        mock_init_clients.return_value = asyncio.run(mock_init())
        
        # Run command
        result = cli_runner.invoke(app, ["validate", "--config", str(mock_config_file)])
        
        assert result.exit_code == 0
        assert "Configuration is valid" in result.stdout
        assert "Okta API connection successful" in result.stdout
        assert "Braintrust API connection successful" in result.stdout
    
    @patch('sync.cli.ConfigLoader')
    def test_validate_config_invalid(self, mock_config_loader, cli_runner, mock_config_file):
        """Test validation with invalid configuration."""
        # Mock configuration loading failure
        mock_loader = MagicMock()
        mock_loader.load_config.side_effect = Exception("Invalid config")
        mock_config_loader.return_value = mock_loader
        
        # Run command
        result = cli_runner.invoke(app, ["validate", "--config", str(mock_config_file)])
        
        assert result.exit_code == 1
        assert "Configuration validation failed" in result.stdout
    
    def test_validate_no_config_file(self, cli_runner):
        """Test validation when no config file found."""
        with patch('sync.cli.find_config_file', return_value=None):
            result = cli_runner.invoke(app, ["validate"])
            
            assert result.exit_code == 1
            assert "No configuration file found" in result.stdout


class TestCLIPlanCommand:
    """Test plan command."""
    
    @patch('sync.cli.ConfigLoader')
    @patch('sync.cli._initialize_clients')
    @patch('sync.cli.StateManager')
    @patch('sync.cli.SyncPlanner')
    @patch('sync.cli._display_sync_plan')
    def test_plan_success(self, mock_display_plan, mock_planner_class, mock_state_manager_class, 
                         mock_init_clients, mock_config_loader, cli_runner, mock_config_file, sample_sync_plan):
        """Test successful plan generation."""
        # Mock configuration loading
        mock_loader = MagicMock()
        mock_config = MagicMock(spec=SyncConfig)
        mock_loader.load_config.return_value = mock_config
        mock_config_loader.return_value = mock_loader
        
        # Mock client initialization
        mock_okta_client = MagicMock()
        mock_braintrust_clients = {"org1": MagicMock()}
        
        async def mock_init():
            return mock_okta_client, mock_braintrust_clients
        
        mock_init_clients.return_value = asyncio.run(mock_init())
        
        # Mock state manager
        mock_state_manager = MagicMock()
        mock_state_manager.get_current_state.return_value = None
        mock_state_manager.create_sync_state.return_value = MagicMock()
        mock_state_manager_class.return_value = mock_state_manager
        
        # Mock planner
        mock_planner = MagicMock()
        mock_planner.generate_sync_plan = AsyncMock(return_value=sample_sync_plan)
        mock_planner_class.return_value = mock_planner
        
        # Run command
        result = cli_runner.invoke(app, ["plan", "--config", str(mock_config_file)])
        
        assert result.exit_code == 0
        assert "Generating sync plan" in result.stdout
        mock_display_plan.assert_called_once_with(sample_sync_plan)
    
    @patch('sync.cli.ConfigLoader')
    def test_plan_config_load_failure(self, mock_config_loader, cli_runner, mock_config_file):
        """Test plan command with config loading failure."""
        # Mock configuration loading failure
        mock_loader = MagicMock()
        mock_loader.load_config.side_effect = Exception("Config load error")
        mock_config_loader.return_value = mock_loader
        
        # Run command
        result = cli_runner.invoke(app, ["plan", "--config", str(mock_config_file)])
        
        assert result.exit_code == 1
        assert "Failed to load configuration" in result.stdout
    
    @patch('sync.cli.find_config_file')
    @patch('sync.cli.ConfigLoader')
    @patch('sync.cli._initialize_clients')
    @patch('sync.cli.StateManager')
    @patch('sync.cli.SyncPlanner')
    def test_plan_with_filters(self, mock_planner_class, mock_state_manager_class, 
                              mock_init_clients, mock_config_loader, mock_find_config, 
                              cli_runner, mock_config_file, sample_sync_plan):
        """Test plan command with filters."""
        # Mock config file discovery
        mock_find_config.return_value = mock_config_file
        
        # Mock configuration loading
        mock_loader = MagicMock()
        mock_config = MagicMock(spec=SyncConfig)
        mock_loader.load_config.return_value = mock_config
        mock_config_loader.return_value = mock_loader
        
        # Mock client initialization
        mock_okta_client = MagicMock()
        mock_braintrust_clients = {"org1": MagicMock()}
        
        async def mock_init():
            return mock_okta_client, mock_braintrust_clients
        
        mock_init_clients.return_value = asyncio.run(mock_init())
        
        # Mock state manager
        mock_state_manager = MagicMock()
        mock_state_manager.get_current_state.return_value = None
        mock_state_manager.create_sync_state.return_value = MagicMock()
        mock_state_manager_class.return_value = mock_state_manager
        
        # Mock planner
        mock_planner = MagicMock()
        mock_planner.generate_sync_plan = AsyncMock(return_value=sample_sync_plan)
        mock_planner_class.return_value = mock_planner
        
        # Run command with filters
        result = cli_runner.invoke(app, [
            "plan", 
            "--org", "org1",
            "--resource", "user",
            "--user-filter", "status eq \"ACTIVE\"",
            "--group-filter", "type eq \"OKTA_GROUP\""
        ])
        
        assert result.exit_code == 0
        
        # Verify planner was called with correct filters
        call_args = mock_planner.generate_sync_plan.call_args
        assert call_args[1]["target_organizations"] == ["org1"]
        assert call_args[1]["resource_types"] == ["user"]
        assert call_args[1]["okta_filters"]["user"] == "status eq \"ACTIVE\""
        assert call_args[1]["okta_filters"]["group"] == "type eq \"OKTA_GROUP\""


class TestCLIApplyCommand:
    """Test apply command."""
    
    @patch('sync.cli.ConfigLoader')
    @patch('sync.cli._initialize_clients')
    @patch('sync.cli.StateManager')
    @patch('sync.cli.SyncPlanner')
    @patch('sync.cli.SyncExecutor')
    @patch('sync.cli._display_sync_plan')
    @patch('sync.cli._display_execution_results')
    def test_apply_with_auto_approve(self, mock_display_results, mock_display_plan, 
                                   mock_executor_class, mock_planner_class, mock_state_manager_class, 
                                   mock_init_clients, mock_config_loader, cli_runner, mock_config_file, 
                                   sample_sync_plan, sample_execution_progress):
        """Test apply command with auto approval."""
        # Mock configuration loading
        mock_loader = MagicMock()
        mock_config = MagicMock(spec=SyncConfig)
        mock_loader.load_config.return_value = mock_config
        mock_config_loader.return_value = mock_loader
        
        # Mock client initialization
        mock_okta_client = MagicMock()
        mock_braintrust_clients = {"org1": MagicMock()}
        
        async def mock_init():
            return mock_okta_client, mock_braintrust_clients
        
        mock_init_clients.return_value = asyncio.run(mock_init())
        
        # Mock state manager
        mock_state_manager = MagicMock()
        mock_state_manager.get_current_state.return_value = None
        mock_state_manager.create_sync_state.return_value = MagicMock()
        mock_state_manager_class.return_value = mock_state_manager
        
        # Mock planner
        mock_planner = MagicMock()
        mock_planner.generate_sync_plan = AsyncMock(return_value=sample_sync_plan)
        mock_planner_class.return_value = mock_planner
        
        # Mock executor
        mock_executor = MagicMock()
        mock_executor.execute_sync_plan = AsyncMock(return_value=sample_execution_progress)
        mock_executor_class.return_value = mock_executor
        
        # Run command
        result = cli_runner.invoke(app, [
            "apply", 
            "--config", str(mock_config_file),
            "--auto-approve"
        ])
        
        assert result.exit_code == 0
        assert "Generating sync plan" in result.stdout
        assert "Executing sync plan" in result.stdout
        mock_display_plan.assert_called_once_with(sample_sync_plan)
        mock_display_results.assert_called_once_with(sample_execution_progress, False)
    
    @patch('sync.cli.ConfigLoader')
    @patch('sync.cli._initialize_clients')
    @patch('sync.cli.StateManager')
    @patch('sync.cli.SyncPlanner')
    @patch('sync.cli.SyncExecutor')
    def test_apply_dry_run(self, mock_executor_class, mock_planner_class, mock_state_manager_class, 
                          mock_init_clients, mock_config_loader, cli_runner, mock_config_file, 
                          sample_sync_plan, sample_execution_progress):
        """Test apply command in dry run mode."""
        # Mock configuration loading
        mock_loader = MagicMock()
        mock_config = MagicMock(spec=SyncConfig)
        mock_loader.load_config.return_value = mock_config
        mock_config_loader.return_value = mock_loader
        
        # Mock client initialization
        mock_okta_client = MagicMock()
        mock_braintrust_clients = {"org1": MagicMock()}
        
        async def mock_init():
            return mock_okta_client, mock_braintrust_clients
        
        mock_init_clients.return_value = asyncio.run(mock_init())
        
        # Mock state manager
        mock_state_manager = MagicMock()
        mock_state_manager.get_current_state.return_value = None
        mock_state_manager.create_sync_state.return_value = MagicMock()
        mock_state_manager_class.return_value = mock_state_manager
        
        # Mock planner
        mock_planner = MagicMock()
        mock_planner.generate_sync_plan = AsyncMock(return_value=sample_sync_plan)
        mock_planner_class.return_value = mock_planner
        
        # Mock executor
        mock_executor = MagicMock()
        mock_executor.execute_sync_plan = AsyncMock(return_value=sample_execution_progress)
        mock_executor_class.return_value = mock_executor
        
        # Run command
        result = cli_runner.invoke(app, [
            "apply", 
            "--config", str(mock_config_file),
            "--dry-run"
        ])
        
        assert result.exit_code == 0
        assert "DRY RUN:" in result.stdout
        
        # Verify executor was called with dry_run=True
        call_args = mock_executor.execute_sync_plan.call_args
        assert call_args[1]["dry_run"] is True


class TestCLIShowCommand:
    """Test show command."""
    
    @patch('sync.cli.find_config_file')
    @patch('sync.cli.ConfigLoader')
    def test_show_success(self, mock_config_loader, mock_find_config, cli_runner, mock_config_file):
        """Test successful show command."""
        # Mock config file discovery
        mock_find_config.return_value = mock_config_file
        
        # Mock configuration loading
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_config.okta = MagicMock()
        mock_config.okta.domain = "test.okta.com"
        mock_config.braintrust_orgs = {"org1": MagicMock(), "org2": MagicMock()}
        mock_config.sync_modes = MagicMock()
        mock_config.sync_modes.declarative = MagicMock()
        mock_config.sync_modes.declarative.enabled = True
        mock_config.sync_modes.realtime = MagicMock()
        mock_config.sync_modes.realtime.enabled = False
        mock_config.sync_rules = MagicMock()
        mock_config.sync_rules.users = MagicMock()
        mock_config.sync_rules.users.enabled = True
        mock_config.sync_rules.groups = MagicMock()
        mock_config.sync_rules.groups.enabled = True
        mock_loader.load_config.return_value = mock_config
        mock_config_loader.return_value = mock_loader
        
        # Run command
        result = cli_runner.invoke(app, ["show"])
        
        assert result.exit_code == 0
        assert "Sync Configuration Summary" in result.stdout
        assert "test.okta.com" in result.stdout
        assert "org1, org2" in result.stdout
    
    @patch('sync.cli.find_config_file')
    def test_show_no_config(self, mock_find_config, cli_runner):
        """Test show command when no config file found."""
        mock_find_config.return_value = None
        
        result = cli_runner.invoke(app, ["show"])
        
        assert result.exit_code == 0
        assert "No configuration file found" in result.stdout


class TestCLIHelperFunctions:
    """Test CLI helper functions."""
    
    @pytest.mark.asyncio
    async def test_initialize_clients(self):
        """Test client initialization helper."""
        from sync.config.models import UserSyncConfig, GroupSyncConfig
        
        mock_config = SyncConfig(
            okta=OktaConfig(
                domain="test.okta.com",
                api_token=SecretStr("test-token"),
            ),
            braintrust_orgs={
                "org1": BraintrustOrgConfig(
                    api_key=SecretStr("test-key-1"),
                    url="https://api.braintrust.dev",
                ),
            },
            sync_modes=SyncModesConfig(),
            sync_rules=SyncRulesConfig(
                users=UserSyncConfig(
                    mappings=[{
                        "okta_filter": "status eq \"ACTIVE\"",
                        "braintrust_orgs": ["org1"]
                    }]
                ),
                groups=GroupSyncConfig(
                    mappings=[{
                        "okta_group_filter": "type eq \"OKTA_GROUP\"",
                        "braintrust_orgs": ["org1"]
                    }]
                )
            ),
        )
        
        with patch('sync.cli.OktaClient') as mock_okta_class, \
             patch('sync.cli.BraintrustClient') as mock_bt_class:
            
            mock_okta_client = MagicMock()
            mock_okta_class.return_value = mock_okta_client
            
            mock_bt_client = MagicMock()
            mock_bt_class.return_value = mock_bt_client
            
            okta_client, braintrust_clients = await _initialize_clients(mock_config)
            
            assert okta_client == mock_okta_client
            assert "org1" in braintrust_clients
            assert braintrust_clients["org1"] == mock_bt_client
            
            # Verify clients were initialized with correct parameters
            mock_okta_class.assert_called_once_with(
                domain="test.okta.com",
                api_token=mock_config.okta.api_token,
                timeout_seconds=mock_config.okta.timeout_seconds,
                rate_limit_per_minute=mock_config.okta.rate_limit_per_minute,
            )
            
            mock_bt_class.assert_called_once_with(
                api_key=mock_config.braintrust_orgs["org1"].api_key,
                api_url=mock_config.braintrust_orgs["org1"].url,
                timeout_seconds=mock_config.braintrust_orgs["org1"].timeout_seconds,
                rate_limit_per_minute=mock_config.braintrust_orgs["org1"].rate_limit_per_minute,
            )
    
    @patch('sync.cli.console')
    def test_display_sync_plan(self, mock_console, sample_sync_plan):
        """Test sync plan display function."""
        _display_sync_plan(sample_sync_plan)
        
        # Verify console.print was called (plan display logic)
        assert mock_console.print.call_count > 0
        
        # Check that plan information was displayed
        print_calls = [call[0] for call in mock_console.print.call_args_list]
        plan_output = " ".join(str(call) for call in print_calls)
        
        assert "Sync Plan" in plan_output
        assert "org1" in plan_output
    
    @patch('sync.cli.console')
    def test_display_execution_results(self, mock_console, sample_execution_progress):
        """Test execution results display function."""
        _display_execution_results(sample_execution_progress, dry_run=False)
        
        # Verify console.print was called (results display logic)
        assert mock_console.print.call_count > 0
        
        # Check that execution information was displayed
        print_calls = [call[0] for call in mock_console.print.call_args_list]
        results_output = " ".join(str(call) for call in print_calls)
        
        assert "Execution Results" in results_output
        assert "test-exec-123" in results_output
    
    @patch('sync.cli.console')
    def test_display_execution_results_dry_run(self, mock_console, sample_execution_progress):
        """Test execution results display function for dry run."""
        _display_execution_results(sample_execution_progress, dry_run=True)
        
        # Verify console.print was called
        assert mock_console.print.call_count > 0
        
        # Check that dry run information was displayed
        print_calls = [call[0] for call in mock_console.print.call_args_list]
        results_output = " ".join(str(call) for call in print_calls)
        
        assert "Dry Run" in results_output


class TestCLIVersionCommand:
    """Test version command."""
    
    def test_version_callback(self, cli_runner):
        """Test version display."""
        result = cli_runner.invoke(app, ["--version"])
        
        assert result.exit_code == 0
        assert "okta-braintrust-sync" in result.stdout


class TestCLIWebhookCommands:
    """Test webhook-related commands."""
    
    def test_webhook_start_command(self, cli_runner):
        """Test webhook start command (placeholder)."""
        result = cli_runner.invoke(app, ["webhook", "start"])
        
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout
    
    def test_webhook_status_command(self, cli_runner):
        """Test webhook status command (placeholder)."""
        result = cli_runner.invoke(app, ["webhook", "status"])
        
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout
    
    def test_webhook_test_command(self, cli_runner):
        """Test webhook test command (placeholder)."""
        result = cli_runner.invoke(app, ["webhook", "test"])
        
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout


class TestCLIPlaceholderCommands:
    """Test placeholder commands."""
    
    def test_start_command(self, cli_runner):
        """Test start command (placeholder)."""
        result = cli_runner.invoke(app, ["start"])
        
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout
    
    def test_status_command(self, cli_runner):
        """Test status command (placeholder)."""
        result = cli_runner.invoke(app, ["status"])
        
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout
    
    def test_reconcile_command(self, cli_runner):
        """Test reconcile command (placeholder)."""
        result = cli_runner.invoke(app, ["reconcile"])
        
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout