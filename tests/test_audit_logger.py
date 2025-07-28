"""Tests for AuditLogger functionality."""

import pytest
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from sync.audit.logger import AuditLogger, AuditEvent, AuditSummary
from sync.resources.base import SyncPlanItem, SyncAction, SyncResult
from sync.core.state import SyncOperation


@pytest.fixture
def temp_audit_dir():
    """Create temporary directory for audit logs."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def audit_logger(temp_audit_dir):
    """Create AuditLogger instance with temporary directory."""
    return AuditLogger(
        audit_dir=temp_audit_dir,
        max_file_size_mb=1,  # Small size for testing
        retention_days=7,
        structured_logging=True,
    )


@pytest.fixture
def sample_audit_event():
    """Create sample audit event."""
    return AuditEvent(
        event_id="test-event-123",
        event_type="sync_start",
        execution_id="exec-456",
        resource_id="user1@example.com",
        braintrust_org="org1",
        operation="CREATE",
        success=True,
        metadata={"test": "data"},
    )


@pytest.fixture
def sample_sync_plan_item():
    """Create sample sync plan item."""
    return SyncPlanItem(
        okta_resource_id="user1@example.com",
        okta_resource_type="user",
        braintrust_org="org1",
        action=SyncAction.CREATE,
        reason="New user",
        proposed_changes={"name": "John Doe"},
        dependencies=["dep1"],
        metadata={"sync": "test"},
    )


@pytest.fixture
def sample_sync_result():
    """Create sample sync result."""
    return SyncResult(
        operation_id="op-123",
        okta_resource_id="user1@example.com",
        braintrust_org="org1",
        action=SyncAction.CREATE,
        success=True,
        braintrust_resource_id="bt-user-456",
        metadata={"created": True},
    )


@pytest.fixture
def sample_sync_operation():
    """Create sample sync operation."""
    return SyncOperation(
        operation_id="op-789",
        resource_type="user",
        okta_id="user1@example.com",
        braintrust_org="org1",
        braintrust_id="bt-user-456",
        operation_type="create",
        status="completed",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        metadata={"test": "operation"},
    )


class TestAuditEvent:
    """Test AuditEvent model."""
    
    def test_audit_event_creation(self):
        """Test AuditEvent creation with required fields."""
        event = AuditEvent(
            event_id="test-123",
            event_type="sync_start",
            execution_id="exec-456",
            resource_id="system",
            braintrust_org="system",
            operation="START",
            success=True,
        )
        
        assert event.event_id == "test-123"
        assert event.event_type == "sync_start"
        assert event.execution_id == "exec-456"
        assert event.resource_id == "system"
        assert event.braintrust_org == "system"
        assert event.operation == "START"
        assert event.success is True
        assert event.user_agent == "okta-braintrust-sync"
        assert event.source_system == "okta"
        assert event.target_system == "braintrust"
        assert isinstance(event.timestamp, datetime)
    
    def test_audit_event_with_optional_fields(self):
        """Test AuditEvent with optional fields."""
        event = AuditEvent(
            event_id="test-123",
            event_type="resource_create",
            execution_id="exec-456",
            resource_type="user",
            resource_id="user1@example.com",
            braintrust_org="org1",
            braintrust_resource_id="bt-user-123",
            operation="CREATE",
            success=True,
            error_message="Test error",
            metadata={"test": "data"},
            before_state={"old": "state"},
            after_state={"new": "state"},
        )
        
        assert event.resource_type == "user"
        assert event.braintrust_resource_id == "bt-user-123"
        assert event.error_message == "Test error"
        assert event.metadata == {"test": "data"}
        assert event.before_state == {"old": "state"}
        assert event.after_state == {"new": "state"}
    
    def test_to_log_record(self, sample_audit_event):
        """Test converting audit event to log record."""
        log_record = sample_audit_event.to_log_record()
        
        assert isinstance(log_record, dict)
        assert log_record["event_id"] == "test-event-123"
        assert log_record["event_type"] == "sync_start"
        assert log_record["execution_id"] == "exec-456"
        assert log_record["resource_id"] == "user1@example.com"
        assert log_record["braintrust_org"] == "org1"
        assert log_record["operation"] == "CREATE"
        assert log_record["success"] is True
        assert log_record["user_agent"] == "okta-braintrust-sync"
        assert log_record["source_system"] == "okta"
        assert log_record["target_system"] == "braintrust"
        assert "timestamp" in log_record


class TestAuditSummary:
    """Test AuditSummary model."""
    
    def test_audit_summary_creation(self):
        """Test AuditSummary creation."""
        started_at = datetime.now(timezone.utc)
        summary = AuditSummary(
            execution_id="exec-123",
            started_at=started_at,
        )
        
        assert summary.execution_id == "exec-123"
        assert summary.started_at == started_at
        assert summary.completed_at is None
        assert summary.total_events == 0
        assert summary.success_events == 0
        assert summary.error_events == 0
        assert summary.operations == {}
        assert summary.resource_types == {}
        assert summary.organizations == {}
        assert summary.error_types == {}
    
    def test_add_event_success(self):
        """Test adding successful event to summary."""
        summary = AuditSummary(
            execution_id="exec-123",
            started_at=datetime.now(timezone.utc),
        )
        
        event = AuditEvent(
            event_id="test-123",
            event_type="resource_create",
            execution_id="exec-123",
            resource_type="user",
            resource_id="user1@example.com",
            braintrust_org="org1",
            operation="CREATE",
            success=True,
        )
        
        summary.add_event(event)
        
        assert summary.total_events == 1
        assert summary.success_events == 1
        assert summary.error_events == 0
        assert summary.operations["CREATE"] == 1
        assert summary.resource_types["user"] == 1
        assert summary.organizations["org1"] == 1
    
    def test_add_event_failure(self):
        """Test adding failed event to summary."""
        summary = AuditSummary(
            execution_id="exec-123",
            started_at=datetime.now(timezone.utc),
        )
        
        event = AuditEvent(
            event_id="test-123",
            event_type="resource_create",
            execution_id="exec-123",
            resource_type="user",
            resource_id="user1@example.com",
            braintrust_org="org1",
            operation="CREATE",
            success=False,
            error_message="Network connection failed",
        )
        
        summary.add_event(event)
        
        assert summary.total_events == 1
        assert summary.success_events == 0
        assert summary.error_events == 1
        assert summary.error_types["network_error"] == 1
    
    def test_categorize_error(self):
        """Test error categorization."""
        summary = AuditSummary(
            execution_id="exec-123",
            started_at=datetime.now(timezone.utc),
        )
        
        test_cases = [
            ("Network connection timeout", "network_error"),
            ("Authentication failed with 401", "authentication_error"),
            ("Rate limit exceeded (429)", "rate_limit_error"),
            ("Resource not found (404)", "not_found_error"),
            ("Validation error: invalid data (400)", "validation_error"),
            ("Permission denied (403)", "permission_error"),
            ("Unknown system error", "other_error"),
        ]
        
        for error_msg, expected_category in test_cases:
            category = summary._categorize_error(error_msg)
            assert category == expected_category
    
    def test_get_success_rate(self):
        """Test success rate calculation."""
        summary = AuditSummary(
            execution_id="exec-123",
            started_at=datetime.now(timezone.utc),
        )
        
        # No events
        assert summary.get_success_rate() == 0.0
        
        # Add successful events
        summary.success_events = 8
        summary.error_events = 2
        summary.total_events = 10
        
        assert summary.get_success_rate() == 80.0


class TestAuditLoggerInit:
    """Test AuditLogger initialization."""
    
    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        logger = AuditLogger()
        
        assert logger.audit_dir == Path("./logs/audit")
        assert logger.max_file_size_bytes == 100 * 1024 * 1024  # 100MB
        assert logger.retention_days == 90
        assert logger.structured_logging is True
        assert logger.current_file is None
        assert logger.file_handle is None
        assert logger.current_summary is None
    
    def test_init_with_custom_options(self, temp_audit_dir):
        """Test initialization with custom parameters."""
        logger = AuditLogger(
            audit_dir=temp_audit_dir,
            max_file_size_mb=50,
            retention_days=30,
            structured_logging=False,
        )
        
        assert logger.audit_dir == temp_audit_dir
        assert logger.max_file_size_bytes == 50 * 1024 * 1024  # 50MB
        assert logger.retention_days == 30
        assert logger.structured_logging is False


class TestAuditLoggerExecutionLifecycle:
    """Test audit logging execution lifecycle."""
    
    def test_start_execution_audit(self, audit_logger):
        """Test starting execution audit."""
        execution_id = "test-exec-123"
        
        summary = audit_logger.start_execution_audit(execution_id)
        
        assert isinstance(summary, AuditSummary)
        assert summary.execution_id == execution_id
        assert summary.started_at is not None
        assert audit_logger.current_summary == summary
        assert audit_logger.current_file is not None
        assert audit_logger.file_handle is not None
        
        # Verify audit file was created
        assert audit_logger.current_file.exists()
        assert execution_id in audit_logger.current_file.name
    
    def test_complete_execution_audit_success(self, audit_logger):
        """Test completing execution audit successfully."""
        execution_id = "test-exec-123"
        
        # Start audit
        summary = audit_logger.start_execution_audit(execution_id)
        
        # Add some events
        event = AuditEvent(
            event_id="test-event",
            event_type="resource_create",
            execution_id=execution_id,
            resource_id="user1@example.com",
            braintrust_org="org1",
            operation="CREATE",
            success=True,
        )
        audit_logger.log_event(event)
        
        # Complete audit
        final_summary = audit_logger.complete_execution_audit(success=True)
        
        assert final_summary == summary
        assert final_summary.completed_at is not None
        assert final_summary.total_events >= 2  # start + complete events + our event
        assert audit_logger.current_summary is None
        assert audit_logger.file_handle is None
        
        # Verify summary file was created
        summary_files = list(audit_logger.audit_dir.glob(f"summary_{execution_id}.json"))
        assert len(summary_files) == 1
    
    def test_complete_execution_audit_failure(self, audit_logger):
        """Test completing execution audit with failure."""
        execution_id = "test-exec-123"
        
        # Start audit
        audit_logger.start_execution_audit(execution_id)
        
        # Complete with failure
        final_summary = audit_logger.complete_execution_audit(
            success=False,
            error_message="Test failure",
        )
        
        assert final_summary.completed_at is not None
        
        # Verify failure was logged in audit file
        with open(audit_logger.current_file or "", 'r') as f:
            lines = f.readlines()
            complete_event = None
            for line in lines:
                event_data = json.loads(line)
                if event_data.get("event_type") == "sync_complete":
                    complete_event = event_data
                    break
            
            assert complete_event is not None
            assert complete_event["operation"] == "FAILED"
            assert complete_event["error_message"] == "Test failure"


class TestAuditLoggerEventLogging:
    """Test audit event logging."""
    
    def test_log_event_structured(self, audit_logger, sample_audit_event):
        """Test logging event in structured format."""
        # Start execution to initialize file
        audit_logger.start_execution_audit("test-exec")
        
        # Log event
        audit_logger.log_event(sample_audit_event)
        
        # Verify event was written to file
        with open(audit_logger.current_file, 'r') as f:
            lines = f.readlines()
            # Should have start event + our event
            assert len(lines) >= 2
            
            # Find our event
            our_event = None
            for line in lines:
                event_data = json.loads(line)
                if event_data.get("event_id") == "test-event-123":
                    our_event = event_data
                    break
            
            assert our_event is not None
            assert our_event["event_type"] == "sync_start"
            assert our_event["resource_id"] == "user1@example.com"
    
    def test_log_event_plain_text(self, temp_audit_dir, sample_audit_event):
        """Test logging event in plain text format."""
        # Create logger with plain text logging
        logger = AuditLogger(
            audit_dir=temp_audit_dir,
            structured_logging=False,
        )
        
        # Start execution to initialize file
        logger.start_execution_audit("test-exec")
        
        # Log event
        logger.log_event(sample_audit_event)
        
        # Verify event was written as plain text
        with open(logger.current_file, 'r') as f:
            content = f.read()
            assert "SYNC_START" in content
            assert "user1@example.com" in content
            assert "CREATE" in content
            assert "SUCCESS" in content
    
    def test_log_event_updates_summary(self, audit_logger, sample_audit_event):
        """Test that logging event updates summary."""
        # Start execution
        summary = audit_logger.start_execution_audit("test-exec")
        initial_count = summary.total_events
        
        # Log event
        audit_logger.log_event(sample_audit_event)
        
        # Verify summary was updated
        assert summary.total_events == initial_count + 1
        assert summary.success_events >= 1
        assert "CREATE" in summary.operations


class TestAuditLoggerSpecializedLogging:
    """Test specialized logging methods."""
    
    def test_log_sync_plan_item(self, audit_logger, sample_sync_plan_item):
        """Test logging sync plan item."""
        execution_id = "test-exec-123"
        audit_logger.start_execution_audit(execution_id)
        
        audit_logger.log_sync_plan_item(
            plan_item=sample_sync_plan_item,
            execution_id=execution_id,
            phase="planning",
        )
        
        # Verify event was logged
        assert audit_logger.current_summary.total_events >= 2  # start + plan item
        
        # Check audit file
        with open(audit_logger.current_file, 'r') as f:
            lines = f.readlines()
            plan_event = None
            for line in lines:
                event_data = json.loads(line)
                if event_data.get("event_type") == "sync_plan_planning":
                    plan_event = event_data
                    break
            
            assert plan_event is not None
            assert plan_event["resource_type"] == "user"
            assert plan_event["resource_id"] == "user1@example.com"
            assert plan_event["operation"] == "SyncAction.CREATE"
            assert plan_event["metadata"]["phase"] == "planning"
            assert plan_event["metadata"]["reason"] == "New user"
    
    def test_log_sync_result(self, audit_logger, sample_sync_result):
        """Test logging sync result."""
        audit_logger.start_execution_audit("test-exec-123")
        
        okta_data = {"name": "John Doe", "email": "john@example.com"}
        braintrust_data = {"id": "bt-123", "name": "John Doe"}
        
        audit_logger.log_sync_result(
            result=sample_sync_result,
            okta_resource_data=okta_data,
            braintrust_resource_data=braintrust_data,
        )
        
        # Check audit file
        with open(audit_logger.current_file, 'r') as f:
            lines = f.readlines()
            result_event = None
            for line in lines:
                event_data = json.loads(line)
                if event_data.get("event_type") == "sync_result":
                    result_event = event_data
                    break
            
            assert result_event is not None
            assert result_event["resource_type"] == "user"
            assert result_event["braintrust_resource_id"] == "bt-user-456"
            assert result_event["before_state"] == okta_data
            assert result_event["after_state"] == braintrust_data
    
    def test_log_sync_operation(self, audit_logger, sample_sync_operation):
        """Test logging sync operation."""
        execution_id = "test-exec-123"
        audit_logger.start_execution_audit(execution_id)
        
        audit_logger.log_sync_operation(
            operation=sample_sync_operation,
            execution_id=execution_id,
        )
        
        # Check audit file
        with open(audit_logger.current_file, 'r') as f:
            lines = f.readlines()
            op_event = None
            for line in lines:
                event_data = json.loads(line)
                if event_data.get("event_type") == "sync_operation":
                    op_event = event_data
                    break
            
            assert op_event is not None
            assert op_event["resource_type"] == "user"
            assert op_event["operation"] == "CREATE"
            assert op_event["metadata"]["operation_status"] == "completed"


class TestAuditLoggerFileManagement:
    """Test audit file management."""
    
    def test_file_rotation(self, audit_logger):
        """Test audit file rotation."""
        # Start first execution
        audit_logger.start_execution_audit("exec-1")
        first_file = audit_logger.current_file
        
        # Complete first execution
        audit_logger.complete_execution_audit()
        
        # Start second execution
        audit_logger.start_execution_audit("exec-2")
        second_file = audit_logger.current_file
        
        # Files should be different
        assert first_file != second_file
        assert first_file.exists()
        assert second_file.exists()
        assert "exec-1" in first_file.name
        assert "exec-2" in second_file.name
    
    def test_cleanup_old_files(self, audit_logger):
        """Test cleanup of old audit files."""
        import os
        
        # Create some old files
        old_time = time.time() - (10 * 24 * 60 * 60)  # 10 days ago
        
        old_audit_file = audit_logger.audit_dir / "audit_old_exec.jsonl"
        old_summary_file = audit_logger.audit_dir / "summary_old_exec.json"
        
        old_audit_file.touch()
        old_summary_file.touch()
        
        # Set old modification times using os.utime
        os.utime(old_audit_file, (old_time, old_time))
        os.utime(old_summary_file, (old_time, old_time))
        
        # Create recent file
        recent_file = audit_logger.audit_dir / "audit_recent_exec.jsonl"
        recent_file.touch()
        
        # Set retention to 7 days
        audit_logger.retention_days = 7
        
        # Cleanup
        cleaned_count = audit_logger.cleanup_old_files()
        
        # Old files should be removed, recent file should remain
        assert not old_audit_file.exists()
        assert not old_summary_file.exists()
        assert recent_file.exists()
        assert cleaned_count == 1  # Only audit file counts


class TestAuditLoggerSummaryRetrieval:
    """Test audit summary retrieval."""
    
    def test_get_execution_summaries_empty(self, audit_logger):
        """Test getting summaries when none exist."""
        summaries = audit_logger.get_execution_summaries()
        assert summaries == []
    
    def test_get_execution_summaries_with_data(self, audit_logger):
        """Test getting execution summaries with data."""
        # Create a few executions
        executions = ["exec-1", "exec-2", "exec-3"]
        
        for exec_id in executions:
            audit_logger.start_execution_audit(exec_id)
            
            # Add some events
            event = AuditEvent(
                event_id=f"event-{exec_id}",
                event_type="resource_create",
                execution_id=exec_id,
                resource_id="user1@example.com",
                braintrust_org="org1",
                operation="CREATE",
                success=True,
            )
            audit_logger.log_event(event)
            
            audit_logger.complete_execution_audit()
        
        # Get summaries
        summaries = audit_logger.get_execution_summaries(limit=2)
        
        assert len(summaries) == 2
        assert all(isinstance(s, AuditSummary) for s in summaries)
        assert all(s.execution_id in executions for s in summaries)
        
        # Should be sorted by most recent first
        assert summaries[0].started_at >= summaries[1].started_at
    
    def test_get_execution_summaries_with_corrupted_file(self, audit_logger, temp_audit_dir):
        """Test handling corrupted summary files gracefully."""
        # Create a corrupted summary file
        corrupted_file = temp_audit_dir / "summary_corrupted.json"
        corrupted_file.write_text("invalid json content")
        
        # Create a valid execution
        audit_logger.start_execution_audit("valid-exec")
        audit_logger.complete_execution_audit()
        
        # Get summaries (should skip corrupted file)
        summaries = audit_logger.get_execution_summaries()
        
        assert len(summaries) == 1
        assert summaries[0].execution_id == "valid-exec"


class TestAuditLoggerErrorHandling:
    """Test audit logger error handling."""
    
    def test_log_event_error_handling(self, audit_logger, sample_audit_event):
        """Test error handling when logging events."""
        # Start execution
        audit_logger.start_execution_audit("test-exec")
        
        # Mock the logger's error method
        with patch.object(audit_logger._logger, 'error') as mock_error:
            # Simulate file write error
            with patch.object(audit_logger, '_write_event_to_file', side_effect=Exception("Write error")):
                # Should not raise exception
                audit_logger.log_event(sample_audit_event)
                
                # Should log error
                mock_error.assert_called_once()
    
    def test_summary_with_no_current_execution(self, audit_logger):
        """Test completing audit when no execution is active."""
        summary = audit_logger.complete_execution_audit()
        assert summary is None