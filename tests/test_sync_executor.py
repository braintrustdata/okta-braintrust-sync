"""Tests for SyncExecutor functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sync.config.models import SyncConfig, OktaConfig, BraintrustOrgConfig, SyncRulesConfig, SyncModesConfig
from sync.core.executor import SyncExecutor, ExecutionProgress
from sync.core.planner import SyncPlan, SyncPlanner
from sync.core.state import StateManager, SyncState
from sync.resources.base import SyncPlanItem, SyncAction, SyncResult
from sync.audit.logger import AuditLogger
from pydantic import SecretStr


# Mock data classes
class MockOktaUser:
    def __init__(self, id: str, email: str, first_name: str, last_name: str):
        self.id = id
        self.profile = MagicMock()
        self.profile.email = email
        self.profile.firstName = first_name
        self.profile.lastName = last_name


class MockOktaGroup:
    def __init__(self, id: str, name: str, description: str = ""):
        self.id = id
        self.profile = MagicMock()
        self.profile.name = name
        self.profile.description = description


class MockBraintrustUser:
    def __init__(self, id: str, email: str, given_name: str, family_name: str):
        self.id = id
        self.email = email
        self.given_name = given_name
        self.family_name = family_name


class MockBraintrustGroup:
    def __init__(self, id: str, name: str, description: str = ""):
        self.id = id
        self.name = name
        self.description = description


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
        },
        sync_modes=SyncModesConfig(),
        sync_rules=SyncRulesConfig(),
    )


@pytest.fixture
def mock_clients():
    """Create mock clients."""
    okta_client = MagicMock()
    braintrust_clients = {
        "org1": MagicMock(),
    }
    return okta_client, braintrust_clients


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    state_manager = MagicMock(spec=StateManager)
    mock_state = MagicMock(spec=SyncState)
    mock_state.sync_id = "test-sync-123"
    mock_state.update_stats = MagicMock()
    mock_state.mark_completed = MagicMock()
    mock_state.mark_failed = MagicMock()
    mock_state.get_summary = MagicMock(return_value={
        "total_items": 0,
        "completed_items": 0,
        "failed_items": 0,
    })
    
    state_manager.get_current_state.return_value = mock_state
    state_manager.create_sync_state.return_value = mock_state
    state_manager.save_sync_state = MagicMock()
    state_manager.create_checkpoint = MagicMock()
    return state_manager


@pytest.fixture
def mock_audit_logger():
    """Create mock audit logger."""
    audit_logger = MagicMock(spec=AuditLogger)
    audit_logger.start_execution_audit = MagicMock()
    audit_logger.complete_execution_audit = MagicMock()
    audit_logger.log_sync_result = MagicMock()
    return audit_logger


@pytest.fixture
def sync_executor(mock_clients, mock_state_manager):
    """Create SyncExecutor instance."""
    okta_client, braintrust_clients = mock_clients
    return SyncExecutor(
        okta_client=okta_client,
        braintrust_clients=braintrust_clients,
        state_manager=mock_state_manager,
    )


@pytest.fixture
def sample_sync_plan():
    """Create sample sync plan."""
    plan = SyncPlan(
        config_hash="test-hash",
        target_organizations=["org1"],
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Add user items
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
    
    # Add group items
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
    
    return plan


class TestExecutionProgress:
    """Test ExecutionProgress model."""
    
    def test_execution_progress_creation(self):
        """Test ExecutionProgress creation with defaults."""
        progress = ExecutionProgress(
            execution_id="test-exec-123",
            plan_id="test-plan-123",
            started_at=datetime.now(timezone.utc),
            total_items=10,
        )
        
        assert progress.execution_id == "test-exec-123"
        assert progress.plan_id == "test-plan-123"
        assert progress.total_items == 10
        assert progress.completed_items == 0
        assert progress.failed_items == 0
        assert progress.skipped_items == 0
        assert progress.current_phase == "initializing"
    
    def test_get_completion_percentage(self):
        """Test completion percentage calculation."""
        progress = ExecutionProgress(
            execution_id="test-exec-123",
            plan_id="test-plan-123",
            started_at=datetime.now(timezone.utc),
            total_items=10,
            completed_items=7,
            failed_items=2,
            skipped_items=1,
        )
        
        assert progress.get_completion_percentage() == 70.0
        
        # Test partial completion
        progress.completed_items = 5
        progress.failed_items = 1
        progress.skipped_items = 0
        assert progress.get_completion_percentage() == 50.0
        
        # Test zero total
        progress.total_items = 0
        assert progress.get_completion_percentage() == 100.0
    
    def test_add_error(self):
        """Test adding errors."""
        progress = ExecutionProgress(
            execution_id="test-exec-123",
            plan_id="test-plan-123",
            started_at=datetime.now(timezone.utc),
            total_items=5,
        )
        
        progress.add_error("Test error")
        
        assert len(progress.errors) == 1
        assert progress.errors[0] == "Test error"
        
        # Test adding error with context
        progress.add_error("Another error", {"context": "test"})
        assert len(progress.errors) == 2
        assert "Another error" in progress.errors[1]
        assert "Context: {'context': 'test'}" in progress.errors[1]
    
    def test_add_warning(self):
        """Test adding warnings."""
        progress = ExecutionProgress(
            execution_id="test-exec-123",
            plan_id="test-plan-123",
            started_at=datetime.now(timezone.utc),
            total_items=5,
        )
        
        progress.add_warning("Test warning")
        
        assert len(progress.warnings) == 1
        assert progress.warnings[0] == "Test warning"
    
    def test_start_phase(self):
        """Test starting execution phases."""
        progress = ExecutionProgress(
            execution_id="test-exec-123",
            plan_id="test-plan-123",
            started_at=datetime.now(timezone.utc),
            total_items=5,
        )
        
        progress.start_phase("users")
        assert progress.current_phase == "users"
        assert "users" in progress.phase_start_times
        
        progress.start_phase("groups")
        assert progress.current_phase == "groups"
        assert "groups" in progress.phase_start_times
    
    def test_completion_percentage_calculation(self):
        """Test completion percentage calculation with different scenarios."""
        progress = ExecutionProgress(
            execution_id="test-exec-123",
            plan_id="test-plan-123",
            started_at=datetime.now(timezone.utc),
            total_items=10,
            completed_items=7,
            failed_items=2,
            skipped_items=1,
        )
        
        # All items processed (7 completed + 2 failed + 1 skipped = 10 total)
        assert progress.get_completion_percentage() == 70.0
        
        # Test with no items completed
        progress.completed_items = 0
        assert progress.get_completion_percentage() == 0.0
        
        # Test with all items completed
        progress.completed_items = 10
        progress.failed_items = 0
        progress.skipped_items = 0
        assert progress.get_completion_percentage() == 100.0


class TestSyncExecutorInit:
    """Test SyncExecutor initialization."""
    
    def test_init_with_defaults(self, mock_clients, mock_state_manager):
        """Test initialization with default parameters."""
        okta_client, braintrust_clients = mock_clients
        
        executor = SyncExecutor(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
        )
        
        assert executor.okta_client == okta_client
        assert executor.braintrust_clients == braintrust_clients
        assert executor.state_manager == mock_state_manager
        assert executor.progress_callback is None
        assert hasattr(executor, 'user_syncer')
        assert hasattr(executor, 'group_syncer')
    
    def test_init_with_progress_callback(self, mock_clients, mock_state_manager):
        """Test initialization with progress callback."""
        okta_client, braintrust_clients = mock_clients
        progress_callback = MagicMock()
        
        executor = SyncExecutor(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=mock_state_manager,
            progress_callback=progress_callback,
        )
        
        assert executor.progress_callback == progress_callback


class TestSyncExecutorPlanExecution:
    """Test sync plan execution."""
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_success(self, sync_executor, sample_sync_plan):
        """Test successful plan execution."""
        # Mock successful resource syncer operations
        sync_executor.user_syncer.execute_sync_plan = AsyncMock(return_value=[
            SyncResult(
                operation_id="op1",
                okta_resource_id="user1@example.com",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                success=True,
            ),
            SyncResult(
                operation_id="op2",
                okta_resource_id="user2@example.com",
                braintrust_org="org1",
                action=SyncAction.UPDATE,
                success=True,
            ),
        ])
        
        sync_executor.group_syncer.execute_sync_plan = AsyncMock(return_value=[
            SyncResult(
                operation_id="op3",
                okta_resource_id="Engineering",
                braintrust_org="org1",
                action=SyncAction.CREATE,
                success=True,
            ),
        ])
        
        progress = await sync_executor.execute_sync_plan(
            plan=sample_sync_plan,
            dry_run=False,
        )
        
        assert progress.total_items == 3
        assert progress.completed_items == 3  # All items completed successfully
        assert progress.current_phase == "completed"
    
    @pytest.mark.asyncio
    async def test_execute_sync_plan_dry_run(self, sync_executor, sample_sync_plan):
        """Test dry run execution."""
        # Mock dry run operations
        sync_executor.user_syncer.execute_sync_plan = AsyncMock(return_value=[])
        sync_executor.group_syncer.execute_sync_plan = AsyncMock(return_value=[])
        
        progress = await sync_executor.execute_sync_plan(
            plan=sample_sync_plan,
            dry_run=True,
        )
        
        assert progress.total_items == 3
        assert progress.completed_items == 0  # Dry run doesn't actually complete items
        assert progress.current_phase == "completed"
        
        # Verify dry_run flag was passed to syncers
        # User syncer is called twice (once per user item)
        assert sync_executor.user_syncer.execute_sync_plan.call_count == 2
        sync_executor.group_syncer.execute_sync_plan.assert_called_once()
        
        # Check that dry_run=True was passed to all calls
        for call in sync_executor.user_syncer.execute_sync_plan.call_args_list:
            assert call.kwargs.get('dry_run') is True
        
        group_call_args = sync_executor.group_syncer.execute_sync_plan.call_args
        assert group_call_args.kwargs.get('dry_run') is True
    
    @pytest.mark.asyncio
    async def test_validate_execution_preconditions(self, sync_executor, sample_sync_plan):
        """Test execution precondition validation."""
        # Mock healthy clients
        sync_executor.okta_client.health_check = AsyncMock(return_value=True)
        sync_executor.braintrust_clients["org1"].health_check = AsyncMock(return_value=True)
        
        errors = await sync_executor.validate_execution_preconditions(sample_sync_plan)
        assert len(errors) == 0
        
        # Mock unhealthy Okta client
        sync_executor.okta_client.health_check = AsyncMock(return_value=False)
        
        errors = await sync_executor.validate_execution_preconditions(sample_sync_plan)
        assert len(errors) == 1
        assert "okta" in errors[0].lower()
        
    @pytest.mark.asyncio
    async def test_get_execution_stats(self, sync_executor):
        """Test getting execution statistics."""
        # Mock state manager
        mock_state = MagicMock()
        mock_state.get_summary.return_value = {
            "total_items": 10,
            "completed_items": 7,
            "failed_items": 2,
        }
        sync_executor.state_manager.get_current_state.return_value = mock_state
        
        stats = await sync_executor.get_execution_stats()
        
        assert stats["total_items"] == 10
        assert stats["completed_items"] == 7
        assert stats["failed_items"] == 2