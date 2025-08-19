"""Sync plan execution with comprehensive error handling and progress tracking."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable

import structlog
from pydantic import BaseModel, Field

from sync.audit.logger import AuditLogger, AuditSummary
from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient
from sync.core.planner import SyncPlan
from sync.core.state import StateManager, SyncState
from sync.resources.base import SyncResult, SyncAction
from sync.resources.users import UserSyncer
from sync.resources.groups import GroupSyncer

logger = structlog.get_logger(__name__)


class ExecutionProgress(BaseModel):
    """Progress tracking for sync execution."""
    
    execution_id: str
    plan_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    skipped_items: int = 0
    
    current_phase: str = "initializing"  # initializing, users, groups, finalizing, completed, failed
    current_item: Optional[str] = None
    
    # Progress by organization
    org_progress: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    
    # Timing information
    phase_start_times: Dict[str, datetime] = Field(default_factory=dict)
    estimated_completion: Optional[datetime] = None
    
    # Error tracking
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    def get_completion_percentage(self) -> float:
        """Get completion percentage (0-100)."""
        if self.total_items == 0:
            return 100.0
        return (self.completed_items / self.total_items) * 100.0
    
    def add_error(self, error: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Add an error to the progress tracking."""
        error_msg = error
        if context:
            error_msg += f" (Context: {context})"
        self.errors.append(error_msg)
    
    def add_warning(self, warning: str) -> None:
        """Add a warning to the progress tracking."""
        self.warnings.append(warning)
    
    def start_phase(self, phase_name: str) -> None:
        """Mark the start of a new execution phase."""
        self.current_phase = phase_name
        self.phase_start_times[phase_name] = datetime.now(timezone.utc)
    
    def update_org_progress(self, org_name: str, action: str, increment: int = 1) -> None:
        """Update progress for a specific organization."""
        if org_name not in self.org_progress:
            self.org_progress[org_name] = {
                "completed": 0,
                "failed": 0,
                "skipped": 0,
            }
        
        if action in self.org_progress[org_name]:
            self.org_progress[org_name][action] += increment


class SyncExecutor:
    """Executes sync plans with comprehensive error handling and progress tracking."""
    
    def __init__(
        self,
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
        audit_logger: Optional[AuditLogger] = None,
        progress_callback: Optional[Callable[[ExecutionProgress], None]] = None,
    ) -> None:
        """Initialize sync executor.
        
        Args:
            okta_client: Okta API client
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
            audit_logger: Optional audit logger for comprehensive audit trails
            progress_callback: Optional callback for progress updates
        """
        self.okta_client = okta_client
        self.braintrust_clients = braintrust_clients
        self.state_manager = state_manager
        self.audit_logger = audit_logger or AuditLogger()
        self.progress_callback = progress_callback
        
        # Initialize resource syncers
        self.user_syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=state_manager,
        )
        
        self.group_syncer = GroupSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=state_manager,
        )
        
        self._logger = logger.bind(
            executor_type="SyncExecutor",
            target_orgs=list(braintrust_clients.keys()),
        )
    
    async def execute_sync_plan(
        self,
        plan: SyncPlan,
        dry_run: bool = False,
        continue_on_error: bool = True,
        max_concurrent_operations: int = 5,
    ) -> ExecutionProgress:
        """Execute a complete sync plan.
        
        Args:
            plan: Sync plan to execute
            dry_run: Whether to perform a dry run (no actual changes)
            continue_on_error: Whether to continue execution after individual item failures
            max_concurrent_operations: Maximum number of concurrent operations per phase
            
        Returns:
            Execution progress with final results
        """
        execution_id = f"exec_{int(time.time())}"
        
        progress = ExecutionProgress(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            started_at=datetime.now(timezone.utc),
            total_items=plan.total_items,
        )
        
        # Initialize org progress tracking
        for org_name in plan.target_organizations:
            progress.org_progress[org_name] = {
                "completed": 0,
                "failed": 0,
                "skipped": 0,
            }
        
        self._logger.info(
            "Starting sync plan execution",
            execution_id=execution_id,
            plan_id=plan.plan_id,
            total_items=plan.total_items,
            dry_run=dry_run,
        )
        
        # Start audit logging for this execution
        audit_summary = self.audit_logger.start_execution_audit(execution_id)
        
        try:
            # Log all plan items for audit trail
            for item in plan.get_all_items():
                self.audit_logger.log_sync_plan_item(item, execution_id, "planning")
            
            # Initialization phase
            progress.start_phase("initializing")
            self._notify_progress(progress)
            
            await self._initialize_execution(plan, progress)
            
            # Execute user sync phase
            if plan.user_items:
                progress.start_phase("users")
                self._notify_progress(progress)
                
                await self._execute_resource_phase(
                    items=plan.user_items,
                    syncer=self.user_syncer,
                    progress=progress,
                    dry_run=dry_run,
                    continue_on_error=continue_on_error,
                    max_concurrent=max_concurrent_operations,
                )
            
            # Execute group sync phase
            if plan.group_items:
                progress.start_phase("groups")
                self._notify_progress(progress)
                
                await self._execute_resource_phase(
                    items=plan.group_items,
                    syncer=self.group_syncer,
                    progress=progress,
                    dry_run=dry_run,
                    continue_on_error=continue_on_error,
                    max_concurrent=max_concurrent_operations,
                )
            
            # Finalization phase
            progress.start_phase("finalizing")
            self._notify_progress(progress)
            
            await self._finalize_execution(plan, progress, dry_run)
            
            # Drift detection phase
            progress.start_phase("drift_detection")
            self._notify_progress(progress)
            
            await self._run_drift_detection(plan, progress)
            
            # Mark as completed
            progress.start_phase("completed")
            progress.completed_at = datetime.now(timezone.utc)
            
            self._logger.info(
                "Sync plan execution completed",
                execution_id=execution_id,
                plan_id=plan.plan_id,
                completed_items=progress.completed_items,
                failed_items=progress.failed_items,
                skipped_items=progress.skipped_items,
                duration_seconds=(progress.completed_at - progress.started_at).total_seconds(),
            )
            
            # Complete audit logging successfully
            final_audit_summary = self.audit_logger.complete_execution_audit(
                success=True
            )
            
        except Exception as e:
            progress.start_phase("failed")
            progress.completed_at = datetime.now(timezone.utc)
            progress.add_error(f"Sync execution failed: {e}")
            
            self._logger.error(
                "Sync plan execution failed",
                execution_id=execution_id,
                plan_id=plan.plan_id,
                error=str(e),
            )
            
            # Complete audit logging with failure
            final_audit_summary = self.audit_logger.complete_execution_audit(
                success=False,
                error_message=str(e)
            )
        
        finally:
            self._notify_progress(progress)
        
        return progress
    
    async def _initialize_execution(
        self,
        plan: SyncPlan,
        progress: ExecutionProgress,
    ) -> None:
        """Initialize sync execution.
        
        Args:
            plan: Sync plan being executed
            progress: Progress tracker to update
        """
        try:
            # Ensure sync state is available
            current_state = self.state_manager.get_current_state()
            if current_state is None:
                # Create new sync state for this execution
                current_state = self.state_manager.create_sync_state(
                    sync_id=progress.execution_id,
                    config_snapshot={"plan_id": plan.plan_id},
                )
            
            # Update state with execution metadata
            current_state.update_stats({
                "execution_id": progress.execution_id,
                "plan_id": plan.plan_id,
                "total_planned_items": plan.total_items,
                "target_organizations": plan.target_organizations,
            })
            
            # Save initial state
            self.state_manager.save_sync_state(current_state)
            
            self._logger.debug(
                "Initialized sync execution",
                execution_id=progress.execution_id,
                sync_state_id=current_state.sync_id,
            )
            
        except Exception as e:
            progress.add_error(f"Initialization failed: {e}")
            raise
    
    async def _execute_resource_phase(
        self,
        items: List[Any],  # SyncPlanItem but avoiding circular import
        syncer: Any,  # BaseResourceSyncer
        progress: ExecutionProgress,
        dry_run: bool,
        continue_on_error: bool,
        max_concurrent: int,
    ) -> None:
        """Execute a phase of resource synchronization.
        
        Args:
            items: List of sync plan items to execute
            syncer: Resource syncer to use for execution
            progress: Progress tracker to update
            dry_run: Whether to perform dry run
            continue_on_error: Whether to continue on individual failures
            max_concurrent: Maximum concurrent operations
        """
        if not items:
            return
        
        resource_type = syncer.resource_type
        
        self._logger.info(
            f"Starting {resource_type} sync phase",
            items=len(items),
            dry_run=dry_run,
        )
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def execute_item(item):
            async with semaphore:
                return await self._execute_single_item(
                    item, syncer, progress, dry_run, continue_on_error
                )
        
        # Execute items with controlled concurrency
        results = await asyncio.gather(
            *[execute_item(item) for item in items],
            return_exceptions=True
        )
        
        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                progress.add_error(
                    f"Failed to execute {resource_type} item: {result}",
                    {"item_index": i, "item_id": items[i].okta_resource_id}
                )
                progress.failed_items += 1
            elif result:
                # Update progress based on result
                if result.success:
                    progress.completed_items += 1
                    progress.update_org_progress(result.braintrust_org, "completed")
                else:
                    progress.failed_items += 1
                    progress.update_org_progress(result.braintrust_org, "failed")
            
            # Notify progress periodically
            if i % 10 == 0:
                self._notify_progress(progress)
        
        self._logger.info(
            f"Completed {resource_type} sync phase",
            total_items=len(items),
            successful=progress.completed_items,
            failed=progress.failed_items,
        )
    
    async def _execute_single_item(
        self,
        item: Any,  # SyncPlanItem
        syncer: Any,  # BaseResourceSyncer
        progress: ExecutionProgress,
        dry_run: bool,
        continue_on_error: bool,
    ) -> Optional[SyncResult]:
        """Execute a single sync plan item.
        
        Args:
            item: Sync plan item to execute
            syncer: Resource syncer to use
            progress: Progress tracker
            dry_run: Whether to perform dry run
            continue_on_error: Whether to continue on error
            
        Returns:
            Sync result if successful, None if failed and continue_on_error is False
        """
        try:
            progress.current_item = f"{syncer.resource_type}:{item.okta_resource_id}"
            
            self._logger.debug(
                "Executing sync item",
                resource_type=syncer.resource_type,
                okta_resource_id=item.okta_resource_id,
                action=item.action,
                braintrust_org=item.braintrust_org,
                dry_run=dry_run,
            )
            
            # Execute the item
            results = await syncer.execute_sync_plan([item], dry_run=dry_run)
            
            if results:
                result = results[0]
                
                # Log audit event for this sync operation
                self.audit_logger.log_sync_result(result)
                
                if result.success:
                    self._logger.debug(
                        "Successfully executed sync item",
                        resource_type=syncer.resource_type,
                        okta_resource_id=item.okta_resource_id,
                        braintrust_resource_id=result.braintrust_resource_id,
                        action=result.action,
                    )
                else:
                    self._logger.warning(
                        "Sync item execution failed",
                        resource_type=syncer.resource_type,
                        okta_resource_id=item.okta_resource_id,
                        error=result.error_message,
                        continue_on_error=continue_on_error,
                    )
                    
                    if not continue_on_error:
                        raise Exception(f"Sync item failed: {result.error_message}")
                
                return result
            
            return None
            
        except Exception as e:
            error_msg = f"Failed to execute {syncer.resource_type} item {item.okta_resource_id}: {e}"
            progress.add_error(error_msg)
            
            self._logger.error(
                "Sync item execution error",
                resource_type=syncer.resource_type,
                okta_resource_id=item.okta_resource_id,
                error=str(e),
                continue_on_error=continue_on_error,
            )
            
            if not continue_on_error:
                raise
            
            return None
    
    async def _finalize_execution(
        self,
        plan: SyncPlan,
        progress: ExecutionProgress,
        dry_run: bool,
    ) -> None:
        """Finalize sync execution.
        
        Args:
            plan: Executed sync plan
            progress: Progress tracker
            dry_run: Whether this was a dry run
        """
        try:
            # Update sync state with final statistics
            current_state = self.state_manager.get_current_state()
            if current_state:
                current_state.update_stats({
                    "execution_completed_at": datetime.now(timezone.utc).isoformat(),
                    "total_completed": progress.completed_items,
                    "total_failed": progress.failed_items,
                    "total_skipped": progress.skipped_items,
                    "dry_run": dry_run,
                    "org_progress": progress.org_progress,
                })
                
                if progress.failed_items == 0:
                    current_state.mark_completed()
                else:
                    current_state.mark_failed(f"{progress.failed_items} items failed")
                
                # Save final state
                self.state_manager.save_sync_state(current_state)
                
                # Create checkpoint
                checkpoint_name = f"execution_{progress.execution_id}_completed"
                self.state_manager.create_checkpoint(checkpoint_name)
            
            # Generate execution summary
            execution_summary = {
                "plan_id": plan.plan_id,
                "execution_id": progress.execution_id,
                "total_items": progress.total_items,
                "completed_items": progress.completed_items,
                "failed_items": progress.failed_items,
                "skipped_items": progress.skipped_items,
                "completion_percentage": progress.get_completion_percentage(),
                "duration_seconds": (
                    progress.completed_at - progress.started_at
                ).total_seconds() if progress.completed_at else None,
                "dry_run": dry_run,
                "organizations": progress.org_progress,
                "errors": progress.errors,
                "warnings": progress.warnings,
            }
            
            self._logger.info(
                "Finalized sync execution",
                **execution_summary,
            )
            
        except Exception as e:
            progress.add_error(f"Finalization failed: {e}")
            self._logger.error("Failed to finalize execution", error=str(e))
    
    async def _run_drift_detection(
        self,
        plan: SyncPlan,
        progress: ExecutionProgress,
    ) -> None:
        """Run drift detection for managed resources.
        
        Args:
            plan: Executed sync plan
            progress: Progress tracker
        """
        try:
            self._logger.info("Starting drift detection")
            
            # Run drift detection for each organization
            for org_name in plan.target_organizations:
                if org_name not in self.braintrust_clients:
                    continue
                
                client = self.braintrust_clients[org_name]
                
                try:
                    # Get current state from Braintrust
                    current_roles = await client.list_roles()
                    current_acls = await client.list_org_acls(org_name=org_name, object_type="project")
                    
                    # Detect drift
                    drift_warnings = self.state_manager.detect_drift(
                        current_roles=current_roles,
                        current_acls=current_acls,
                        braintrust_org=org_name,
                    )
                    
                    # Log drift warnings
                    for warning in drift_warnings:
                        progress.add_warning(
                            f"Drift detected in {org_name}: {warning.drift_type} - {warning.details}"
                        )
                        
                        self._logger.warning(
                            "Resource drift detected",
                            braintrust_org=org_name,
                            resource_type=warning.resource_type,
                            resource_id=warning.resource_id,
                            drift_type=warning.drift_type,
                            details=warning.details,
                            severity=warning.severity,
                        )
                    
                    if drift_warnings:
                        self._logger.info(
                            "Drift detection completed",
                            braintrust_org=org_name,
                            warnings_count=len(drift_warnings),
                        )
                    else:
                        self._logger.debug(
                            "No drift detected",
                            braintrust_org=org_name,
                        )
                
                except Exception as e:
                    error_msg = f"Drift detection failed for {org_name}: {str(e)}"
                    progress.add_error(error_msg)
                    self._logger.error(
                        "Drift detection error",
                        braintrust_org=org_name,
                        error=str(e),
                    )
            
            self._logger.info("Drift detection phase completed")
            
        except Exception as e:
            progress.add_error(f"Drift detection phase failed: {e}")
            self._logger.error("Failed to run drift detection", error=str(e))
    
    def _notify_progress(self, progress: ExecutionProgress) -> None:
        """Notify progress callback if available.
        
        Args:
            progress: Current progress state
        """
        if self.progress_callback:
            try:
                self.progress_callback(progress)
            except Exception as e:
                self._logger.warning(
                    "Progress callback failed",
                    error=str(e),
                )
    
    async def validate_execution_preconditions(
        self,
        plan: SyncPlan,
    ) -> List[str]:
        """Validate that preconditions are met for plan execution.
        
        Args:
            plan: Sync plan to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        try:
            self._logger.debug("Validating execution preconditions", plan_id=plan.plan_id)
            
            # Validate plan is not empty
            if plan.total_items == 0:
                errors.append("Cannot execute empty sync plan")
            
            # Validate target organizations
            for org_name in plan.target_organizations:
                if org_name not in self.braintrust_clients:
                    errors.append(f"No Braintrust client configured for organization: {org_name}")
            
            # Validate API connectivity
            try:
                okta_healthy = await self.okta_client.health_check()
                if not okta_healthy:
                    errors.append("Okta API is not accessible")
            except Exception as e:
                errors.append(f"Okta API health check failed: {e}")
            
            for org_name in plan.target_organizations:
                if org_name in self.braintrust_clients:
                    try:
                        client = self.braintrust_clients[org_name]
                        bt_healthy = await client.health_check()
                        if not bt_healthy:
                            errors.append(f"Braintrust API not accessible for org: {org_name}")
                    except Exception as e:
                        errors.append(f"Braintrust API health check failed for org {org_name}: {e}")
            
            # Validate state management
            current_state = self.state_manager.get_current_state()
            if current_state is None:
                errors.append("No sync state available for execution tracking")
            
            self._logger.debug(
                "Completed execution precondition validation",
                plan_id=plan.plan_id,
                errors=len(errors),
            )
            
        except Exception as e:
            errors.append(f"Precondition validation failed: {e}")
        
        return errors
    
    async def get_execution_stats(self) -> Dict[str, Any]:
        """Get current execution statistics from state.
        
        Returns:
            Dictionary with execution statistics
        """
        try:
            current_state = self.state_manager.get_current_state()
            if not current_state:
                return {"error": "No current sync state available"}
            
            return current_state.get_summary()
            
        except Exception as e:
            self._logger.error("Failed to get execution stats", error=str(e))
            return {"error": f"Failed to get stats: {e}"}