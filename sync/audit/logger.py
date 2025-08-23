"""Comprehensive audit logging for sync operations."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import structlog
from pydantic import BaseModel, Field

from sync.resources.base import SyncOperation, SyncResult, SyncPlanItem


class AuditEvent(BaseModel):
    """Individual audit event."""
    
    event_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str  # sync_start, sync_complete, resource_create, resource_update, etc.
    execution_id: str
    
    # Resource information
    resource_type: Optional[str] = None  # user, group
    resource_id: str  # okta resource ID
    braintrust_org: str
    braintrust_resource_id: Optional[str] = None
    
    # Operation details
    operation: str  # CREATE, UPDATE, SKIP, ERROR
    success: bool
    error_message: Optional[str] = None
    
    # Context information
    user_agent: str = "okta-braintrust-sync"
    source_system: str = "okta"
    target_system: str = "braintrust"
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Data before/after for updates
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    
    def to_log_record(self) -> Dict[str, Any]:
        """Convert to structured log record format."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "execution_id": self.execution_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "braintrust_org": self.braintrust_org,
            "braintrust_resource_id": self.braintrust_resource_id,
            "operation": self.operation,
            "success": self.success,
            "error_message": self.error_message,
            "user_agent": self.user_agent,
            "source_system": self.source_system,
            "target_system": self.target_system,
            "metadata": self.metadata,
            "before_state": self.before_state,
            "after_state": self.after_state,
        }


class AuditSummary(BaseModel):
    """Summary of audit events for a sync execution."""
    
    execution_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    total_events: int = 0
    success_events: int = 0
    error_events: int = 0
    
    # Breakdown by operation type
    operations: Dict[str, int] = Field(default_factory=dict)
    
    # Breakdown by resource type
    resource_types: Dict[str, int] = Field(default_factory=dict)
    
    # Breakdown by organization
    organizations: Dict[str, int] = Field(default_factory=dict)
    
    # Error summary
    error_types: Dict[str, int] = Field(default_factory=dict)
    
    def add_event(self, event: AuditEvent) -> None:
        """Add an event to the summary statistics."""
        self.total_events += 1
        
        if event.success:
            self.success_events += 1
        else:
            self.error_events += 1
            
            # Categorize error type
            if event.error_message:
                error_type = self._categorize_error(event.error_message)
                self.error_types[error_type] = self.error_types.get(error_type, 0) + 1
        
        # Update operation breakdown
        self.operations[event.operation] = self.operations.get(event.operation, 0) + 1
        
        # Update resource type breakdown
        if event.resource_type:
            self.resource_types[event.resource_type] = self.resource_types.get(event.resource_type, 0) + 1
        
        # Update organization breakdown
        self.organizations[event.braintrust_org] = self.organizations.get(event.braintrust_org, 0) + 1
    
    def _categorize_error(self, error_message: str) -> str:
        """Categorize error message into error type."""
        error_lower = error_message.lower()
        
        if "network" in error_lower or "connection" in error_lower:
            return "network_error"
        elif "authentication" in error_lower or "401" in error_lower:
            return "authentication_error"
        elif "rate limit" in error_lower or "429" in error_lower:
            return "rate_limit_error"
        elif "not found" in error_lower or "404" in error_lower:
            return "not_found_error"
        elif "validation" in error_lower or "400" in error_lower:
            return "validation_error"
        elif "permission" in error_lower or "403" in error_lower:
            return "permission_error"
        else:
            return "other_error"
    
    def get_success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_events == 0:
            return 0.0
        return (self.success_events / self.total_events) * 100.0


class AuditLogger:
    """Comprehensive audit logger for sync operations."""
    
    def __init__(
        self,
        audit_dir: Path = Path("./logs/audit"),
        max_file_size_mb: int = 100,
        retention_days: int = 90,
        structured_logging: bool = True,
    ) -> None:
        """Initialize audit logger.
        
        Args:
            audit_dir: Directory to store audit logs
            max_file_size_mb: Maximum size per audit file in MB
            retention_days: Number of days to retain audit logs
            structured_logging: Whether to use structured JSON logging
        """
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.retention_days = retention_days
        self.structured_logging = structured_logging
        
        # Current audit file
        self.current_file: Optional[Path] = None
        self.file_handle: Optional[Any] = None
        
        # In-memory event tracking for summary
        self.current_summary: Optional[AuditSummary] = None
        
        # Set up structured logger
        self._logger = structlog.get_logger(__name__)
    
    def start_execution_audit(self, execution_id: str) -> AuditSummary:
        """Start audit logging for a sync execution.
        
        Args:
            execution_id: Unique execution identifier
            
        Returns:
            AuditSummary for tracking events
        """
        self.current_summary = AuditSummary(
            execution_id=execution_id,
            started_at=datetime.now(timezone.utc),
        )
        
        # Create new audit file for this execution
        self._rotate_audit_file(execution_id)
        
        # Log execution start event
        start_event = AuditEvent(
            event_id=f"{execution_id}_start",
            event_type="sync_start",
            execution_id=execution_id,
            resource_id="system",
            braintrust_org="system",
            operation="START",
            success=True,
            metadata={"execution_started": True},
        )
        
        self.log_event(start_event)
        
        self._logger.info(
            "Started audit logging for execution",
            execution_id=execution_id,
            audit_file=str(self.current_file),
        )
        
        return self.current_summary
    
    def complete_execution_audit(
        self,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> Optional[AuditSummary]:
        """Complete audit logging for a sync execution.
        
        Args:
            success: Whether the execution was successful
            error_message: Error message if execution failed
            
        Returns:
            Final AuditSummary if available
        """
        if not self.current_summary:
            return None
        
        self.current_summary.completed_at = datetime.now(timezone.utc)
        
        # Log execution complete event
        complete_event = AuditEvent(
            event_id=f"{self.current_summary.execution_id}_complete",
            event_type="sync_complete",
            execution_id=self.current_summary.execution_id,
            resource_id="system",
            braintrust_org="system",
            operation="COMPLETE" if success else "FAILED",
            success=success,
            error_message=error_message,
            metadata={
                "execution_completed": True,
                "total_events": self.current_summary.total_events,
                "success_rate": self.current_summary.get_success_rate(),
                "duration_seconds": (
                    self.current_summary.completed_at - self.current_summary.started_at
                ).total_seconds(),
            },
        )
        
        self.log_event(complete_event)
        
        # Write summary to separate file
        self._write_execution_summary()
        
        # Close current file
        self._close_current_file()
        
        self._logger.info(
            "Completed audit logging for execution",
            execution_id=self.current_summary.execution_id,
            total_events=self.current_summary.total_events,
            success_rate=self.current_summary.get_success_rate(),
        )
        
        final_summary = self.current_summary
        self.current_summary = None
        return final_summary
    
    def log_event(self, event: AuditEvent) -> None:
        """Log an audit event.
        
        Args:
            event: AuditEvent to log
        """
        try:
            # Add to summary if available
            if self.current_summary:
                self.current_summary.add_event(event)
            
            # Write to audit file
            self._write_event_to_file(event)
            
            # Log to structured logger
            self._logger.info(
                "Audit event",
                **event.to_log_record(),
            )
            
        except Exception as e:
            self._logger.error(
                "Failed to log audit event",
                event_id=event.event_id,
                error=str(e),
            )
    
    def log_sync_plan_item(
        self,
        plan_item: SyncPlanItem,
        execution_id: str,
        phase: str = "planning",
    ) -> None:
        """Log a sync plan item.
        
        Args:
            plan_item: SyncPlanItem to log
            execution_id: Current execution ID
            phase: Current phase (planning, execution)
        """
        event = AuditEvent(
            event_id=f"{execution_id}_{plan_item.okta_resource_id}_{phase}",
            event_type=f"sync_plan_{phase}",
            execution_id=execution_id,
            resource_type=plan_item.okta_resource_type,
            resource_id=plan_item.okta_resource_id,
            braintrust_org=plan_item.braintrust_org,
            braintrust_resource_id=plan_item.existing_braintrust_id,
            operation=str(plan_item.action),
            success=True,
            metadata={
                "phase": phase,
                "reason": plan_item.reason,
                "proposed_changes": plan_item.proposed_changes,
                "dependencies": plan_item.dependencies,
                "plan_metadata": plan_item.metadata,
            },
        )
        
        self.log_event(event)
    
    def log_sync_result(
        self,
        result: SyncResult,
        okta_resource_data: Optional[Dict[str, Any]] = None,
        braintrust_resource_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a sync operation result.
        
        Args:
            result: SyncResult to log
            okta_resource_data: Optional Okta resource data for before_state
            braintrust_resource_data: Optional Braintrust resource data for after_state
        """
        event = AuditEvent(
            event_id=f"{result.operation_id}_result",
            event_type="sync_result",
            execution_id=result.operation_id.split("_")[0],  # Extract execution ID
            resource_type="user" if "user" in result.okta_resource_id else "group",
            resource_id=result.okta_resource_id,
            braintrust_org=result.braintrust_org,
            braintrust_resource_id=result.braintrust_resource_id,
            operation=str(result.action),
            success=result.success,
            error_message=result.error_message,
            metadata=result.metadata,
            before_state=okta_resource_data,
            after_state=braintrust_resource_data,
        )
        
        self.log_event(event)
    
    def log_sync_operation(
        self,
        operation: SyncOperation,
        execution_id: str,
    ) -> None:
        """Log a sync operation from state.
        
        Args:
            operation: SyncOperation to log
            execution_id: Current execution ID
        """
        event = AuditEvent(
            event_id=f"{operation.operation_id}_operation",
            event_type="sync_operation",
            execution_id=execution_id,
            resource_type=operation.resource_type,
            resource_id=operation.okta_id,
            braintrust_org=operation.braintrust_org,
            braintrust_resource_id=operation.braintrust_id,
            operation=operation.operation_type.upper(),
            success=operation.status == "completed",
            error_message=operation.error_message,
            metadata={
                "operation_status": operation.status,
                "started_at": operation.started_at.isoformat() if operation.started_at else None,
                "completed_at": operation.completed_at.isoformat() if operation.completed_at else None,
                "operation_metadata": operation.metadata,
            },
        )
        
        self.log_event(event)
    
    def _rotate_audit_file(self, execution_id: str) -> None:
        """Rotate to a new audit file.
        
        Args:
            execution_id: Execution ID for file naming
        """
        # Close current file if open
        self._close_current_file()
        
        # Create new audit file
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"audit_{timestamp}_{execution_id}.jsonl"
        self.current_file = self.audit_dir / filename
        
        # Open new file
        self.file_handle = open(self.current_file, 'w', encoding='utf-8')
        
        self._logger.debug("Rotated to new audit file", file=str(self.current_file))
    
    def _write_event_to_file(self, event: AuditEvent) -> None:
        """Write event to current audit file.
        
        Args:
            event: AuditEvent to write
        """
        if not self.file_handle:
            return
        
        try:
            if self.structured_logging:
                # Write as JSON Lines format
                json_record = event.to_log_record()
                self.file_handle.write(json.dumps(json_record) + "\n")
            else:
                # Write as plain text
                timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                line = (
                    f"[{timestamp}] {event.event_type.upper()} "
                    f"{event.resource_type or 'system'}:{event.resource_id} "
                    f"{event.operation} -> {event.braintrust_org} "
                    f"{'SUCCESS' if event.success else 'FAILED'}"
                )
                if event.error_message:
                    line += f" ({event.error_message})"
                line += "\n"
                self.file_handle.write(line)
            
            self.file_handle.flush()
            
            # Check file size for rotation
            if self.current_file and self.current_file.stat().st_size > self.max_file_size_bytes:
                self._logger.info("Audit file size limit reached, rotation needed")
                
        except Exception as e:
            self._logger.error("Failed to write audit event to file", error=str(e))
    
    def _write_execution_summary(self) -> None:
        """Write execution summary to separate file."""
        if not self.current_summary:
            return
        
        try:
            summary_file = self.audit_dir / f"summary_{self.current_summary.execution_id}.json"
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(
                    self.current_summary.model_dump(mode='json'),
                    f,
                    indent=2,
                    default=str,
                )
            
            self._logger.debug("Wrote execution summary", file=str(summary_file))
            
        except Exception as e:
            self._logger.error("Failed to write execution summary", error=str(e))
    
    def _close_current_file(self) -> None:
        """Close current audit file."""
        if self.file_handle:
            try:
                self.file_handle.close()
                self.file_handle = None
            except Exception as e:
                self._logger.error("Failed to close audit file", error=str(e))
    
    def cleanup_old_files(self) -> int:
        """Clean up old audit files based on retention policy.
        
        Returns:
            Number of files cleaned up
        """
        try:
            cutoff_time = time.time() - (self.retention_days * 24 * 60 * 60)
            cleaned_count = 0
            
            for audit_file in self.audit_dir.glob("audit_*.jsonl"):
                if audit_file.stat().st_mtime < cutoff_time:
                    audit_file.unlink()
                    cleaned_count += 1
                    
                    # Also remove corresponding summary file
                    summary_file = audit_file.with_name(
                        audit_file.name.replace("audit_", "summary_").replace(".jsonl", ".json")
                    )
                    if summary_file.exists():
                        summary_file.unlink()
            
            if cleaned_count > 0:
                self._logger.info(f"Cleaned up {cleaned_count} old audit files")
            
            return cleaned_count
            
        except Exception as e:
            self._logger.error("Failed to cleanup old audit files", error=str(e))
            return 0
    
    def get_execution_summaries(self, limit: int = 10) -> List[AuditSummary]:
        """Get recent execution summaries.
        
        Args:
            limit: Maximum number of summaries to return
            
        Returns:
            List of recent AuditSummary objects
        """
        try:
            summaries = []
            summary_files = sorted(
                self.audit_dir.glob("summary_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            for summary_file in summary_files[:limit]:
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        summary_data = json.load(f)
                    
                    summary = AuditSummary.model_validate(summary_data)
                    summaries.append(summary)
                    
                except Exception as e:
                    self._logger.warning(
                        "Failed to load summary file",
                        file=str(summary_file),
                        error=str(e),
                    )
            
            return summaries
            
        except Exception as e:
            self._logger.error("Failed to get execution summaries", error=str(e))
            return []