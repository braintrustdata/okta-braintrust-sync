"""Tests for state management functionality."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from sync.core.state import (
    ResourceMapping,
    SyncOperation,
    SyncState,
    StateManager,
)


@pytest.fixture
def temp_state_dir():
    """Create a temporary directory for state files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def state_manager(temp_state_dir):
    """Create a state manager with temporary directory."""
    return StateManager(state_dir=temp_state_dir)


class TestResourceMapping:
    """Test ResourceMapping model."""
    
    def test_resource_mapping_creation(self):
        """Test resource mapping creation with defaults."""
        mapping = ResourceMapping(
            okta_id="okta-123",
            braintrust_id="bt-456",
            braintrust_org="test-org",
            resource_type="user"
        )
        
        assert mapping.okta_id == "okta-123"
        assert mapping.braintrust_id == "bt-456"
        assert mapping.braintrust_org == "test-org"
        assert mapping.resource_type == "user"
        assert isinstance(mapping.created_at, datetime)
        assert isinstance(mapping.updated_at, datetime)
    
    def test_resource_mapping_update_timestamp(self):
        """Test timestamp update functionality."""
        mapping = ResourceMapping(
            okta_id="okta-123",
            braintrust_id="bt-456",
            braintrust_org="test-org",
            resource_type="user"
        )
        
        original_updated_at = mapping.updated_at
        
        # Small delay to ensure timestamp changes
        import time
        time.sleep(0.001)
        
        mapping.update_timestamp()
        assert mapping.updated_at > original_updated_at


class TestSyncOperation:
    """Test SyncOperation model."""
    
    def test_sync_operation_creation(self):
        """Test sync operation creation."""
        operation = SyncOperation(
            operation_id="op-123",
            operation_type="create",
            resource_type="user",
            okta_id="okta-123",
            braintrust_org="test-org",
            status="pending"
        )
        
        assert operation.operation_id == "op-123"
        assert operation.operation_type == "create"
        assert operation.resource_type == "user"
        assert operation.okta_id == "okta-123"
        assert operation.braintrust_id is None
        assert operation.braintrust_org == "test-org"
        assert operation.status == "pending"
        assert operation.error_message is None
        assert operation.completed_at is None
        assert isinstance(operation.started_at, datetime)
    
    def test_sync_operation_mark_completed(self):
        """Test marking operation as completed."""
        operation = SyncOperation(
            operation_id="op-123",
            operation_type="create",
            resource_type="user",
            okta_id="okta-123",
            braintrust_org="test-org",
            status="in_progress"
        )
        
        operation.mark_completed("bt-456")
        
        assert operation.status == "completed"
        assert operation.braintrust_id == "bt-456"
        assert isinstance(operation.completed_at, datetime)
    
    def test_sync_operation_mark_failed(self):
        """Test marking operation as failed."""
        operation = SyncOperation(
            operation_id="op-123",
            operation_type="create",
            resource_type="user",
            okta_id="okta-123",
            braintrust_org="test-org",
            status="in_progress"
        )
        
        operation.mark_failed("Network error")
        
        assert operation.status == "failed"
        assert operation.error_message == "Network error"
        assert isinstance(operation.completed_at, datetime)


class TestSyncState:
    """Test SyncState model."""
    
    def test_sync_state_creation(self):
        """Test sync state creation with defaults."""
        state = SyncState(sync_id="sync-123")
        
        assert state.sync_id == "sync-123"
        assert state.status == "in_progress"
        assert state.completed_at is None
        assert isinstance(state.started_at, datetime)
        assert len(state.resource_mappings) == 0
        assert len(state.operations) == 0
        assert len(state.stats) == 0
        assert len(state.config_snapshot) == 0
    
    def test_add_mapping(self):
        """Test adding resource mappings."""
        state = SyncState(sync_id="sync-123")
        
        state.add_mapping(
            okta_id="okta-123",
            braintrust_id="bt-456",
            braintrust_org="test-org",
            resource_type="user"
        )
        
        mapping_key = "okta-123:test-org:user"
        assert mapping_key in state.resource_mappings
        
        mapping = state.resource_mappings[mapping_key]
        assert mapping.okta_id == "okta-123"
        assert mapping.braintrust_id == "bt-456"
        assert mapping.braintrust_org == "test-org"
        assert mapping.resource_type == "user"
    
    def test_update_existing_mapping(self):
        """Test updating existing resource mapping."""
        state = SyncState(sync_id="sync-123")
        
        # Add initial mapping
        state.add_mapping(
            okta_id="okta-123",
            braintrust_id="bt-456",
            braintrust_org="test-org",
            resource_type="user"
        )
        
        mapping_key = "okta-123:test-org:user"
        original_updated_at = state.resource_mappings[mapping_key].updated_at
        
        # Small delay to ensure timestamp changes
        import time
        time.sleep(0.001)
        
        # Update mapping with new Braintrust ID
        state.add_mapping(
            okta_id="okta-123",
            braintrust_id="bt-789",
            braintrust_org="test-org",
            resource_type="user"
        )
        
        # Should still be one mapping
        assert len(state.resource_mappings) == 1
        
        mapping = state.resource_mappings[mapping_key]
        assert mapping.braintrust_id == "bt-789"
        assert mapping.updated_at > original_updated_at
    
    def test_get_mapping(self):
        """Test retrieving resource mappings."""
        state = SyncState(sync_id="sync-123")
        
        state.add_mapping(
            okta_id="okta-123",
            braintrust_id="bt-456",
            braintrust_org="test-org",
            resource_type="user"
        )
        
        # Test successful retrieval
        mapping = state.get_mapping("okta-123", "test-org", "user")
        assert mapping is not None
        assert mapping.braintrust_id == "bt-456"
        
        # Test non-existent mapping
        mapping = state.get_mapping("okta-999", "test-org", "user")
        assert mapping is None
    
    def test_get_braintrust_id(self):
        """Test getting Braintrust ID by Okta ID."""
        state = SyncState(sync_id="sync-123")
        
        state.add_mapping(
            okta_id="okta-123",
            braintrust_id="bt-456",
            braintrust_org="test-org",
            resource_type="user"
        )
        
        # Test successful retrieval
        braintrust_id = state.get_braintrust_id("okta-123", "test-org", "user")
        assert braintrust_id == "bt-456"
        
        # Test non-existent mapping
        braintrust_id = state.get_braintrust_id("okta-999", "test-org", "user")
        assert braintrust_id is None
    
    def test_add_operation(self):
        """Test adding sync operations."""
        state = SyncState(sync_id="sync-123")
        
        operation = SyncOperation(
            operation_id="op-123",
            operation_type="create",
            resource_type="user",
            okta_id="okta-123",
            braintrust_org="test-org",
            status="pending"
        )
        
        state.add_operation(operation)
        
        assert "op-123" in state.operations
        assert state.operations["op-123"] == operation
    
    def test_get_operation(self):
        """Test retrieving sync operations."""
        state = SyncState(sync_id="sync-123")
        
        operation = SyncOperation(
            operation_id="op-123",
            operation_type="create",
            resource_type="user",
            okta_id="okta-123",
            braintrust_org="test-org",
            status="pending"
        )
        
        state.add_operation(operation)
        
        # Test successful retrieval
        retrieved_op = state.get_operation("op-123")
        assert retrieved_op == operation
        
        # Test non-existent operation
        retrieved_op = state.get_operation("op-999")
        assert retrieved_op is None
    
    def test_update_stats(self):
        """Test updating sync statistics."""
        state = SyncState(sync_id="sync-123")
        
        state.update_stats({"users_created": 5, "groups_created": 2})
        assert state.stats["users_created"] == 5
        assert state.stats["groups_created"] == 2
        
        # Test updating existing stats
        state.update_stats({"users_created": 7, "errors": 1})
        assert state.stats["users_created"] == 7
        assert state.stats["groups_created"] == 2  # Should remain
        assert state.stats["errors"] == 1
    
    def test_mark_completed(self):
        """Test marking sync as completed."""
        state = SyncState(sync_id="sync-123")
        
        state.mark_completed()
        
        assert state.status == "completed"
        assert isinstance(state.completed_at, datetime)
    
    def test_mark_failed(self):
        """Test marking sync as failed."""
        state = SyncState(sync_id="sync-123")
        
        state.mark_failed("Connection timeout")
        
        assert state.status == "failed"
        assert isinstance(state.completed_at, datetime)
        assert state.stats["error_message"] == "Connection timeout"
    
    def test_get_summary(self):
        """Test getting sync summary."""
        state = SyncState(sync_id="sync-123")
        
        # Add some operations
        completed_op = SyncOperation(
            operation_id="op-1",
            operation_type="create",
            resource_type="user",
            okta_id="okta-1",
            braintrust_org="test-org",
            status="completed"
        )
        
        failed_op = SyncOperation(
            operation_id="op-2",
            operation_type="create",
            resource_type="user",
            okta_id="okta-2",
            braintrust_org="test-org",
            status="failed"
        )
        
        state.add_operation(completed_op)
        state.add_operation(failed_op)
        
        # Add some stats
        state.update_stats({"test_stat": "test_value"})
        
        summary = state.get_summary()
        
        assert summary["sync_id"] == "sync-123"
        assert summary["status"] == "in_progress"
        assert summary["total_operations"] == 2
        assert summary["completed_operations"] == 1
        assert summary["failed_operations"] == 1
        assert summary["total_mappings"] == 0
        assert summary["stats"]["test_stat"] == "test_value"
        assert "duration_seconds" in summary


class TestStateManager:
    """Test StateManager functionality."""
    
    def test_state_manager_init(self, state_manager, temp_state_dir):
        """Test state manager initialization."""
        assert state_manager.state_dir == temp_state_dir
        assert temp_state_dir.exists()
        assert state_manager._current_state is None
    
    def test_create_sync_state(self, state_manager):
        """Test creating new sync state."""
        config_snapshot = {"test_config": "test_value"}
        
        state = state_manager.create_sync_state(
            sync_id="test-sync",
            config_snapshot=config_snapshot
        )
        
        assert state.sync_id == "test-sync"
        assert state.config_snapshot == config_snapshot
        assert state_manager._current_state == state
    
    def test_create_sync_state_auto_id(self, state_manager):
        """Test creating sync state with auto-generated ID."""
        with patch('time.time', return_value=1234567890):
            state = state_manager.create_sync_state()
            assert state.sync_id == "sync_1234567890"
    
    def test_save_and_load_sync_state(self, state_manager, temp_state_dir):
        """Test saving and loading sync state."""
        # Create and save state
        state = state_manager.create_sync_state(sync_id="test-sync")
        state.add_mapping("okta-1", "bt-1", "org1", "user")
        
        success = state_manager.save_sync_state(state)
        assert success is True
        
        # Verify file was created
        state_file = temp_state_dir / "test-sync.json"
        assert state_file.exists()
        
        # Load state
        loaded_state = state_manager.load_sync_state("test-sync")
        assert loaded_state is not None
        assert loaded_state.sync_id == "test-sync"
        assert len(loaded_state.resource_mappings) == 1
        
        # Should be current state
        assert state_manager._current_state == loaded_state
    
    def test_load_nonexistent_sync_state(self, state_manager):
        """Test loading non-existent sync state."""
        state = state_manager.load_sync_state("nonexistent-sync")
        assert state is None
    
    def test_save_sync_state_creates_backup(self, state_manager, temp_state_dir):
        """Test that saving creates backup of existing file."""
        # Create initial state file
        state = state_manager.create_sync_state(sync_id="test-sync")
        state_manager.save_sync_state(state)
        
        state_file = temp_state_dir / "test-sync.json"
        backup_file = temp_state_dir / "test-sync.json.backup"
        
        # Modify and save again
        state.add_mapping("okta-1", "bt-1", "org1", "user")
        state_manager.save_sync_state(state)
        
        # Backup should exist
        assert backup_file.exists()
    
    def test_persistent_mappings(self, state_manager, temp_state_dir):
        """Test persistent mapping storage and loading."""
        # Create state with mappings
        state1 = state_manager.create_sync_state(sync_id="sync-1")
        state1.add_mapping("okta-1", "bt-1", "org1", "user")
        state1.add_mapping("okta-2", "bt-2", "org1", "group")
        state_manager.save_sync_state(state1)
        
        # Create new state - should load existing mappings
        state2 = state_manager.create_sync_state(sync_id="sync-2")
        
        # Should have loaded previous mappings
        assert len(state2.resource_mappings) == 2
        assert state2.get_braintrust_id("okta-1", "org1", "user") == "bt-1"
        assert state2.get_braintrust_id("okta-2", "org1", "group") == "bt-2"
    
    def test_list_sync_states(self, state_manager):
        """Test listing sync states."""
        # Initially empty
        sync_ids = state_manager.list_sync_states()
        assert len(sync_ids) == 0
        
        # Create some states
        state1 = state_manager.create_sync_state(sync_id="sync_1000")
        state2 = state_manager.create_sync_state(sync_id="sync_2000")
        state_manager.save_sync_state(state1)
        state_manager.save_sync_state(state2)
        
        sync_ids = state_manager.list_sync_states()
        assert len(sync_ids) == 2
        assert "sync_1000" in sync_ids
        assert "sync_2000" in sync_ids
        assert sync_ids == sorted(sync_ids)  # Should be sorted
    
    def test_get_latest_sync_state(self, state_manager):
        """Test getting latest sync state."""
        # Initially None
        latest = state_manager.get_latest_sync_state()
        assert latest is None
        
        # Create states in order
        state1 = state_manager.create_sync_state(sync_id="sync_1000")
        state2 = state_manager.create_sync_state(sync_id="sync_2000")
        state_manager.save_sync_state(state1)
        state_manager.save_sync_state(state2)
        
        latest = state_manager.get_latest_sync_state()
        assert latest is not None
        assert latest.sync_id == "sync_2000"
    
    def test_cleanup_old_states(self, state_manager, temp_state_dir):
        """Test cleaning up old sync states."""
        # Create multiple states
        states = []
        for i in range(5):
            state = state_manager.create_sync_state(sync_id=f"sync_{i}")
            state_manager.save_sync_state(state)
            states.append(state)
        
        # Should have 5 files
        sync_files = list(temp_state_dir.glob("sync_*.json"))
        assert len(sync_files) == 5
        
        # Cleanup, keeping only 3
        cleaned_count = state_manager.cleanup_old_states(keep_count=3)
        assert cleaned_count == 2
        
        # Should have 3 files remaining
        sync_files = list(temp_state_dir.glob("sync_*.json"))
        assert len(sync_files) == 3
    
    def test_create_checkpoint(self, state_manager, temp_state_dir):
        """Test creating checkpoints."""
        # No current state
        success = state_manager.create_checkpoint()
        assert success is False
        
        # Create state
        state = state_manager.create_sync_state(sync_id="test-sync")
        state.add_mapping("okta-1", "bt-1", "org1", "user")
        
        # Create checkpoint
        success = state_manager.create_checkpoint("before_groups")
        assert success is True
        
        # Verify checkpoint file
        checkpoint_file = temp_state_dir / "test-sync_before_groups.json"
        assert checkpoint_file.exists()
        
        # Verify checkpoint content
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)
        
        assert checkpoint_data["sync_id"] == "test-sync"
        assert len(checkpoint_data["resource_mappings"]) == 1
    
    def test_error_handling_invalid_json(self, state_manager, temp_state_dir):
        """Test error handling for invalid JSON files."""
        # Create invalid JSON file
        state_file = temp_state_dir / "invalid-sync.json"
        with open(state_file, 'w') as f:
            f.write("invalid json content")
        
        state = state_manager.load_sync_state("invalid-sync")
        assert state is None
    
    def test_get_current_state(self, state_manager):
        """Test getting current state."""
        # Initially None
        assert state_manager.get_current_state() is None
        
        # After creating state
        state = state_manager.create_sync_state(sync_id="test-sync")
        assert state_manager.get_current_state() == state
        
        # After loading different state
        loaded_state = SyncState(sync_id="loaded-sync")
        state_manager._current_state = loaded_state
        assert state_manager.get_current_state() == loaded_state