"""Base resource syncer with common sync patterns and operations."""

import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, TypeVar, Generic

import structlog
from pydantic import BaseModel, Field

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient, OktaUser, OktaGroup
from sync.core.enhanced_state import StateManager

logger = structlog.get_logger(__name__)

# Type variables for generic resource handling
OktaResourceType = TypeVar('OktaResourceType', OktaUser, OktaGroup)
BraintrustResourceType = TypeVar('BraintrustResourceType')


class SyncOperation(BaseModel):
    """Represents a sync operation for tracking."""
    operation_id: str
    operation_type: str
    resource_type: str
    okta_id: Optional[str] = None
    braintrust_id: Optional[str] = None
    braintrust_org: str
    status: str = "pending"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    
    def mark_completed(self, braintrust_id: Optional[str] = None):
        """Mark operation as completed.
        
        Args:
            braintrust_id: Optional Braintrust resource ID to update
        """
        self.status = "completed"
        if braintrust_id:
            self.braintrust_id = braintrust_id
    
    def mark_failed(self, error: str):
        """Mark operation as failed."""
        self.status = "failed"
        self.error_message = error


class SyncAction(str, Enum):
    """Possible sync actions for a resource."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"
    ERROR = "error"


class SyncPlanItem(BaseModel):
    """A single item in a sync plan."""
    
    okta_resource_id: str
    okta_resource_type: str  # "user" or "group"
    okta_resource: Dict[str, Any] = Field(default_factory=dict)  # Full Okta resource data
    braintrust_org: str
    action: SyncAction
    reason: str
    existing_braintrust_id: Optional[str] = None
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)  # Other resource IDs this depends on
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SyncResult(BaseModel):
    """Result of a sync operation."""
    
    operation_id: str
    okta_resource_id: str
    braintrust_resource_id: Optional[str] = None
    braintrust_org: str
    action: SyncAction
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseResourceSyncer(ABC, Generic[OktaResourceType, BraintrustResourceType]):
    """Abstract base class for resource synchronization."""
    
    def __init__(
        self,
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
    ) -> None:
        """Initialize base resource syncer.
        
        Args:
            okta_client: Okta API client
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
        """
        self.okta_client = okta_client
        self.braintrust_clients = braintrust_clients
        self.state_manager = state_manager
        
        self._logger = logger.bind(
            syncer_type=self.__class__.__name__,
            resource_type=self.resource_type,
        )
    
    @property
    @abstractmethod
    def resource_type(self) -> str:
        """Get the resource type name (e.g., 'user', 'group')."""
        pass
    
    @abstractmethod
    async def get_okta_resources(
        self,
        filter_expr: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[OktaResourceType]:
        """Get resources from Okta.
        
        Args:
            filter_expr: Optional SCIM filter expression
            limit: Maximum number of resources to retrieve
            
        Returns:
            List of Okta resources
        """
        pass
    
    @abstractmethod
    async def get_braintrust_resources(
        self,
        braintrust_org: str,
        limit: Optional[int] = None,
    ) -> List[BraintrustResourceType]:
        """Get resources from Braintrust.
        
        Args:
            braintrust_org: Braintrust organization name
            limit: Maximum number of resources to retrieve
            
        Returns:
            List of Braintrust resources
        """
        pass
    
    @abstractmethod
    async def create_braintrust_resource(
        self,
        okta_resource: OktaResourceType,
        braintrust_org: str,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> BraintrustResourceType:
        """Create a new resource in Braintrust.
        
        Args:
            okta_resource: Source Okta resource
            braintrust_org: Target Braintrust organization
            additional_data: Additional data for resource creation
            
        Returns:
            Created Braintrust resource
        """
        pass
    
    @abstractmethod
    async def update_braintrust_resource(
        self,
        braintrust_resource_id: str,
        okta_resource: OktaResourceType,
        braintrust_org: str,
        updates: Dict[str, Any],
    ) -> BraintrustResourceType:
        """Update an existing resource in Braintrust.
        
        Args:
            braintrust_resource_id: Braintrust resource ID
            okta_resource: Source Okta resource
            braintrust_org: Target Braintrust organization
            updates: Fields to update
            
        Returns:
            Updated Braintrust resource
        """
        pass
    
    @abstractmethod
    def get_resource_identifier(self, resource: OktaResourceType) -> str:
        """Get unique identifier for an Okta resource.
        
        Args:
            resource: Okta resource
            
        Returns:
            Unique identifier (usually ID or email)
        """
        pass
    
    @abstractmethod
    def get_braintrust_resource_identifier(self, resource: BraintrustResourceType) -> str:
        """Get unique identifier for a Braintrust resource.
        
        Args:
            resource: Braintrust resource
            
        Returns:
            Unique identifier (usually ID or email)
        """
        pass
    
    @abstractmethod
    def should_sync_resource(
        self,
        okta_resource: OktaResourceType,
        braintrust_org: str,
        sync_rules: Dict[str, Any],
    ) -> bool:
        """Check if resource should be synced to the given organization.
        
        Args:
            okta_resource: Okta resource to check
            braintrust_org: Target Braintrust organization
            sync_rules: Sync rules configuration
            
        Returns:
            True if resource should be synced
        """
        pass
    
    @abstractmethod
    async def calculate_updates(
        self,
        okta_resource: OktaResourceType,
        braintrust_resource: BraintrustResourceType,
    ) -> Dict[str, Any]:
        """Calculate what updates are needed for a Braintrust resource.
        
        Args:
            okta_resource: Source Okta resource
            braintrust_resource: Existing Braintrust resource
            
        Returns:
            Dictionary of fields that need updating
        """
        pass
    
    @abstractmethod
    async def delete_braintrust_resource(
        self,
        resource_id: str,
        braintrust_org: str,
    ) -> None:
        """Delete a resource from Braintrust.
        
        Args:
            resource_id: Braintrust resource ID to delete
            braintrust_org: Target Braintrust organization
        """
        pass
    
    @abstractmethod
    def _get_resource_id(self, okta_resource: OktaResourceType) -> Optional[str]:
        """Get the ID from an Okta resource.
        
        Args:
            okta_resource: Okta resource
            
        Returns:
            Resource ID or None
        """
        pass
    
    @abstractmethod
    def _get_braintrust_resource_id(self, braintrust_resource: BraintrustResourceType) -> Optional[str]:
        """Get the ID from a Braintrust resource.
        
        Args:
            braintrust_resource: Braintrust resource
            
        Returns:
            Resource ID or None
        """
        pass
    
    # Common sync orchestration methods
    
    async def generate_sync_plan(
        self,
        braintrust_orgs: List[str],
        sync_rules: Dict[str, Any],
        okta_filter: Optional[str] = None,
    ) -> List[SyncPlanItem]:
        """Generate a sync plan for the given organizations.
        
        Args:
            braintrust_orgs: List of Braintrust organization names
            sync_rules: Sync rules configuration
            okta_filter: Optional Okta filter expression
            
        Returns:
            List of sync plan items
        """
        plan_items = []
        
        self._logger.info(
            "Generating sync plan",
            resource_type=self.resource_type,
            braintrust_orgs=braintrust_orgs,
        )
        
        try:
            # Get Okta resources
            okta_resources = await self.get_okta_resources(
                filter_expr=okta_filter,
                limit=sync_rules.get('limit'),
            )
            
            self._logger.debug(
                "Retrieved Okta resources",
                count=len(okta_resources),
                resource_type=self.resource_type,
            )
            
            # Generate plan items for each organization
            for braintrust_org in braintrust_orgs:
                org_plan_items = await self._generate_org_sync_plan(
                    okta_resources,
                    braintrust_org,
                    sync_rules,
                )
                plan_items.extend(org_plan_items)
                
                # Generate deletion plan items for resources that exist in Braintrust but not in Okta
                deletion_plan_items = await self._generate_deletion_plan(
                    okta_resources,
                    braintrust_org,
                    sync_rules,
                )
                plan_items.extend(deletion_plan_items)
            
            self._logger.info(
                "Generated sync plan",
                total_items=len(plan_items),
                resource_type=self.resource_type,
            )
            
            return plan_items
            
        except Exception as e:
            self._logger.error(
                "Failed to generate sync plan",
                error=str(e),
                resource_type=self.resource_type,
            )
            raise
    
    async def _generate_org_sync_plan(
        self,
        okta_resources: List[OktaResourceType],
        braintrust_org: str,
        sync_rules: Dict[str, Any],
    ) -> List[SyncPlanItem]:
        """Generate sync plan for a specific organization.
        
        Args:
            okta_resources: List of Okta resources
            braintrust_org: Target Braintrust organization
            sync_rules: Sync rules configuration
            
        Returns:
            List of sync plan items for this organization
        """
        plan_items = []
        
        try:
            # Get current state - create empty state if none exists (first run)
            current_state = self.state_manager.get_current_state()
            if current_state is None:
                self._logger.warning("No current sync state available - continuing with empty state for first run")
            
            # Get existing Braintrust resources for comparison
            braintrust_resources = await self.get_braintrust_resources(braintrust_org)
            braintrust_resource_map = {
                self.get_braintrust_resource_identifier(res): res for res in braintrust_resources
            }
            
            # Process each Okta resource
            for okta_resource in okta_resources:
                if not self.should_sync_resource(okta_resource, braintrust_org, sync_rules):
                    continue
                
                okta_id = self.get_resource_identifier(okta_resource)
                
                # Check if resource already exists in Braintrust
                existing_mapping = None
                if current_state:
                    existing_mapping = current_state.get_mapping(
                        okta_id, braintrust_org, self.resource_type
                    )
                
                if existing_mapping:
                    # Resource exists - check if update is needed
                    # Try to find the resource by braintrust_id first, then by identifier
                    braintrust_resource = None
                    for identifier, resource in braintrust_resource_map.items():
                        # Handle both dict and object formats
                        resource_id = (
                            resource.get('id') if isinstance(resource, dict)
                            else getattr(resource, 'id', None)
                        )
                        if (resource_id == existing_mapping.braintrust_id or
                            identifier == okta_id):
                            braintrust_resource = resource
                            break
                    
                    if braintrust_resource:
                        updates = await self.calculate_updates(okta_resource, braintrust_resource)
                        if updates:
                            plan_items.append(SyncPlanItem(
                                okta_resource_id=okta_id,
                                okta_resource_type=self.resource_type,
                                okta_resource=getattr(okta_resource, 'data', {}),
                                braintrust_org=braintrust_org,
                                action=SyncAction.UPDATE,
                                reason=f"Updates needed: {', '.join(updates.keys())}",
                                existing_braintrust_id=existing_mapping.braintrust_id,
                                proposed_changes=updates,
                            ))
                        else:
                            plan_items.append(SyncPlanItem(
                                okta_resource_id=okta_id,
                                okta_resource_type=self.resource_type,
                                okta_resource=getattr(okta_resource, 'data', {}),
                                braintrust_org=braintrust_org,
                                action=SyncAction.SKIP,
                                reason="Resource is up to date",
                                existing_braintrust_id=existing_mapping.braintrust_id,
                            ))
                    else:
                        # Mapping exists but resource is missing - recreate
                        plan_items.append(SyncPlanItem(
                            okta_resource_id=okta_id,
                            okta_resource_type=self.resource_type,
                            okta_resource=getattr(okta_resource, 'data', {}),
                            braintrust_org=braintrust_org,
                            action=SyncAction.CREATE,
                            reason="Mapped resource missing in Braintrust",
                        ))
                else:
                    # No mapping in state - check if resource exists in Braintrust
                    braintrust_resource = braintrust_resource_map.get(okta_id)
                    
                    if braintrust_resource:
                        # Resource exists in Braintrust but not tracked in state
                        # Check if updates are needed
                        updates = await self.calculate_updates(okta_resource, braintrust_resource)
                        braintrust_id = self._get_braintrust_resource_id(braintrust_resource)
                        
                        if updates:
                            plan_items.append(SyncPlanItem(
                                okta_resource_id=okta_id,
                                okta_resource_type=self.resource_type,
                                okta_resource=getattr(okta_resource, 'data', {}),
                                braintrust_org=braintrust_org,
                                action=SyncAction.UPDATE,
                                reason=f"Untracked resource needs updates: {', '.join(updates.keys())}",
                                existing_braintrust_id=braintrust_id,
                                proposed_changes=updates,
                            ))
                        else:
                            plan_items.append(SyncPlanItem(
                                okta_resource_id=okta_id,
                                okta_resource_type=self.resource_type,
                                okta_resource=getattr(okta_resource, 'data', {}),
                                braintrust_org=braintrust_org,
                                action=SyncAction.SKIP,
                                reason="Untracked resource is up to date",
                                existing_braintrust_id=braintrust_id,
                            ))
                    else:
                        # New resource - create
                        if sync_rules.get('create_missing', True):
                            plan_items.append(SyncPlanItem(
                                okta_resource_id=okta_id,
                                okta_resource_type=self.resource_type,
                                okta_resource=getattr(okta_resource, 'data', {}),
                                braintrust_org=braintrust_org,
                                action=SyncAction.CREATE,
                                reason="New resource from Okta",
                            ))
                        else:
                            plan_items.append(SyncPlanItem(
                                okta_resource_id=okta_id,
                                okta_resource_type=self.resource_type,
                                okta_resource=getattr(okta_resource, 'data', {}),
                                braintrust_org=braintrust_org,
                                action=SyncAction.SKIP,
                                reason="Creation disabled in sync rules",
                            ))
            
            self._logger.debug(
                "Generated organization sync plan",
                braintrust_org=braintrust_org,
                plan_items=len(plan_items),
            )
            
            return plan_items
            
        except Exception as e:
            import traceback
            self._logger.error(
                "Failed to generate organization sync plan",
                braintrust_org=braintrust_org,
                error=str(e),
                traceback=traceback.format_exc(),
            )
            raise
    
    async def _generate_deletion_plan(
        self,
        okta_resources: List[OktaResourceType],
        braintrust_org: str,
        sync_rules: Dict[str, Any],
    ) -> List[SyncPlanItem]:
        """Generate deletion plan for resources that exist in Braintrust but not in Okta.
        
        Args:
            okta_resources: List of current Okta resources (source of truth)
            braintrust_org: Target Braintrust organization
            sync_rules: Sync rules configuration
            
        Returns:
            List of deletion plan items
        """
        plan_items = []
        
        try:
            # Check if remove_extra is enabled - if not, skip deletion planning
            if not sync_rules.get('remove_extra', False):
                self._logger.debug(
                    "Skipping deletion planning - remove_extra is disabled",
                    braintrust_org=braintrust_org,
                    resource_type=self.resource_type,
                )
                return []
            
            # Get state mappings to identify resources managed by this sync tool
            managed_resources = self._get_managed_resources(braintrust_org)
            
            if not managed_resources:
                # No managed resources, nothing to delete
                return []
            
            # Create sets of Okta resource identifiers for quick lookup
            okta_resource_identifiers = set()
            for okta_resource in okta_resources:
                resource_identifier = self.get_resource_identifier(okta_resource)
                if resource_identifier:
                    okta_resource_identifiers.add(resource_identifier)
            
            self._logger.debug(
                "Checking managed resources for deletion",
                braintrust_org=braintrust_org,
                okta_resources=len(okta_resource_identifiers),
                managed_resources=len(managed_resources),
            )
            
            # Check each managed resource to see if it should be deleted
            for bt_resource_id, okta_identifier in managed_resources.items():
                # If the Okta resource no longer exists, plan for deletion
                if okta_identifier not in okta_resource_identifiers:
                    plan_items.append(SyncPlanItem(
                        okta_resource_id=okta_identifier,
                        okta_resource_type=self.resource_type,
                        okta_resource={},  # No Okta resource for deletion
                        braintrust_org=braintrust_org,
                        action=SyncAction.DELETE,
                        reason=f"Resource exists in Braintrust but not in Okta (managed by sync tool)",
                        existing_braintrust_id=bt_resource_id,
                        braintrust_resource_id=bt_resource_id,  # Set this for DELETE operations
                    ))
            
            self._logger.debug(
                "Generated deletion plan",
                braintrust_org=braintrust_org,
                deletion_items=len(plan_items),
            )
            
            return plan_items
            
        except Exception as e:
            self._logger.error(
                "Failed to generate deletion plan",
                braintrust_org=braintrust_org,
                error=str(e),
            )
            # Don't raise - deletion plan generation should not fail the whole sync
            return []
    
    def _get_managed_resources(self, braintrust_org: str) -> Dict[str, str]:
        """Get mapping of Braintrust resource IDs to Okta resource IDs for resources managed by this sync tool.
        
        Args:
            braintrust_org: Braintrust organization name
            
        Returns:
            Dictionary mapping Braintrust resource ID -> Okta resource ID
        """
        managed_resources = {}
        
        try:
            # Get current state from state manager, fall back to latest if none loaded
            current_state = self.state_manager.get_current_state()
            if not current_state:
                current_state = self.state_manager.get_latest_sync_state()
            
            if not current_state:
                self._logger.debug(
                    "No current or latest state available for managed resources",
                    braintrust_org=braintrust_org,
                    resource_type=self.resource_type,
                )
                return managed_resources
            
            # Look through resource mappings for this org and resource type
            # Structure: resource_mappings[org_name][resource_type] = [list of mappings]
            if braintrust_org in current_state.resource_mappings:
                org_mappings = current_state.resource_mappings[braintrust_org]
                if self.resource_type in org_mappings:
                    type_mappings = org_mappings[self.resource_type]
                    if isinstance(type_mappings, list):
                        for mapping in type_mappings:
                            if isinstance(mapping, dict) and 'okta_id' in mapping and 'braintrust_id' in mapping:
                                managed_resources[mapping['braintrust_id']] = mapping['okta_id']
            
            # Also check managed_resources collection if available
            if hasattr(current_state, 'managed_resources'):
                for resource_id, resource in current_state.managed_resources.items():
                    if (resource.resource_type == self.resource_type and 
                        resource.braintrust_org == braintrust_org and
                        resource.created_by_sync):
                        # For managed resources, we might not have the okta_id directly
                        # Try to find it from the resource_mappings
                        for mapping in current_state.resource_mappings.values():
                            if (mapping.braintrust_id == resource_id and 
                                mapping.resource_type == self.resource_type and
                                mapping.braintrust_org == braintrust_org):
                                managed_resources[resource_id] = mapping.okta_id
                                break
            
            self._logger.debug(
                "Loaded managed resources",
                braintrust_org=braintrust_org,
                resource_type=self.resource_type,
                count=len(managed_resources),
            )
            
        except Exception as e:
            self._logger.warning(
                "Could not load managed resources from state",
                braintrust_org=braintrust_org,
                error=str(e),
            )
        
        return managed_resources
    
    def _estimate_duration(self, action: SyncAction) -> float:
        """Estimate duration for a sync action in seconds.
        
        Args:
            action: The sync action to estimate
            
        Returns:
            Estimated duration in seconds
        """
        # Basic estimates - subclasses can override for more specific estimates
        duration_estimates = {
            SyncAction.CREATE: 5.0,
            SyncAction.UPDATE: 3.0,
            SyncAction.DELETE: 2.0,
            SyncAction.SKIP: 0.1,
            SyncAction.ERROR: 0.1,
        }
        return duration_estimates.get(action, 3.0)
    
    async def execute_sync_plan(
        self,
        plan_items: List[SyncPlanItem],
        dry_run: bool = False,
    ) -> List[SyncResult]:
        """Execute a sync plan.
        
        Args:
            plan_items: List of sync plan items to execute
            dry_run: If True, don't make actual changes
            
        Returns:
            List of sync results
        """
        results = []
        
        self._logger.info(
            "Executing sync plan",
            total_items=len(plan_items),
            dry_run=dry_run,
            resource_type=self.resource_type,
        )
        
        # Group plan items by action for better logging
        actions_count = {}
        for item in plan_items:
            actions_count[item.action] = actions_count.get(item.action, 0) + 1
        
        self._logger.info("Sync plan breakdown", actions=actions_count)
        
        if dry_run:
            self._logger.info("DRY RUN: No actual changes will be made")
        
        # Execute each plan item
        for plan_item in plan_items:
            try:
                result = await self._execute_plan_item(plan_item, dry_run)
                results.append(result)
                
            except Exception as e:
                self._logger.error(
                    "Failed to execute plan item",
                    okta_resource_id=plan_item.okta_resource_id,
                    action=plan_item.action,
                    error=str(e),
                )
                
                results.append(SyncResult(
                    operation_id=str(uuid.uuid4()),
                    okta_resource_id=plan_item.okta_resource_id,
                    braintrust_org=plan_item.braintrust_org,
                    action=SyncAction.ERROR,
                    success=False,
                    error_message=str(e),
                ))
        
        # Log summary
        success_count = sum(1 for r in results if r.success)
        error_count = len(results) - success_count
        
        self._logger.info(
            "Sync plan execution completed",
            total=len(results),
            success=success_count,
            errors=error_count,
            resource_type=self.resource_type,
        )
        
        return results
    
    async def _execute_plan_item(
        self,
        plan_item: SyncPlanItem,
        dry_run: bool,
    ) -> SyncResult:
        """Execute a single sync plan item.
        
        Args:
            plan_item: Plan item to execute
            dry_run: If True, don't make actual changes
            
        Returns:
            Sync result
        """
        operation_id = str(uuid.uuid4())
        
        # Create sync operation for tracking
        operation = SyncOperation(
            operation_id=operation_id,
            operation_type=plan_item.action.value,
            resource_type=self.resource_type,
            okta_id=plan_item.okta_resource_id,
            braintrust_id=plan_item.existing_braintrust_id,
            braintrust_org=plan_item.braintrust_org,
            status="in_progress",
            metadata=plan_item.metadata,
        )
        
        # Add to state (commented out - add_operation method not yet implemented)
        # current_state = self.state_manager.get_current_state()
        # if current_state:
        #     current_state.add_operation(operation)
        
        try:
            if plan_item.action == SyncAction.SKIP:
                operation.mark_completed()
                return SyncResult(
                    operation_id=operation_id,
                    okta_resource_id=plan_item.okta_resource_id,
                    braintrust_resource_id=plan_item.existing_braintrust_id,
                    braintrust_org=plan_item.braintrust_org,
                    action=SyncAction.SKIP,
                    success=True,
                    metadata={"reason": plan_item.reason},
                )
            
            elif plan_item.action == SyncAction.CREATE:
                return await self._execute_create(plan_item, operation, dry_run)
            
            elif plan_item.action == SyncAction.UPDATE:
                return await self._execute_update(plan_item, operation, dry_run)
            
            elif plan_item.action == SyncAction.DELETE:
                return await self._execute_delete(plan_item, operation, dry_run)
            
            else:
                raise ValueError(f"Unknown sync action: {plan_item.action}")
                
        except Exception as e:
            operation.mark_failed(str(e))
            raise
    
    async def _execute_create(
        self,
        plan_item: SyncPlanItem,
        operation: SyncOperation,
        dry_run: bool,
    ) -> SyncResult:
        """Execute a create operation.
        
        Args:
            plan_item: Plan item to execute
            operation: Sync operation for tracking
            dry_run: If True, don't make actual changes
            
        Returns:
            Sync result
        """
        # Get the Okta resource
        okta_resources = await self.get_okta_resources()
        okta_resource = None
        for resource in okta_resources:
            if self.get_resource_identifier(resource) == plan_item.okta_resource_id:
                okta_resource = resource
                break
        
        if okta_resource is None:
            raise ValueError(f"Okta resource not found: {plan_item.okta_resource_id}")
        
        if dry_run:
            self._logger.info(
                "DRY RUN: Would create resource",
                okta_resource_id=plan_item.okta_resource_id,
                braintrust_org=plan_item.braintrust_org,
            )
            operation.mark_completed("dry_run_id")
            return SyncResult(
                operation_id=operation.operation_id,
                okta_resource_id=plan_item.okta_resource_id,
                braintrust_resource_id="dry_run_id",
                braintrust_org=plan_item.braintrust_org,
                action=SyncAction.CREATE,
                success=True,
                metadata={"dry_run": True},
            )
        
        # Create the resource
        braintrust_resource = await self.create_braintrust_resource(
            okta_resource,
            plan_item.braintrust_org,
        )
        
        # Handle both dict and object formats
        if isinstance(braintrust_resource, dict):
            braintrust_id = braintrust_resource.get('id', str(braintrust_resource))
        else:
            braintrust_id = getattr(braintrust_resource, 'id', str(braintrust_resource))
        
        # Update state mapping
        current_state = self.state_manager.get_current_state()
        if current_state:
            current_state.add_mapping(
                plan_item.okta_resource_id,
                braintrust_id,
                plan_item.braintrust_org,
                self.resource_type,
            )
        
        operation.mark_completed(braintrust_id)
        
        self._logger.info(
            "Created resource",
            okta_resource_id=plan_item.okta_resource_id,
            braintrust_resource_id=braintrust_id,
            braintrust_org=plan_item.braintrust_org,
        )
        
        return SyncResult(
            operation_id=operation.operation_id,
            okta_resource_id=plan_item.okta_resource_id,
            braintrust_resource_id=braintrust_id,
            braintrust_org=plan_item.braintrust_org,
            action=SyncAction.CREATE,
            success=True,
        )
    
    async def _execute_update(
        self,
        plan_item: SyncPlanItem,
        operation: SyncOperation,
        dry_run: bool,
    ) -> SyncResult:
        """Execute an update operation.
        
        Args:
            plan_item: Plan item to execute
            operation: Sync operation for tracking
            dry_run: If True, don't make actual changes
            
        Returns:
            Sync result
        """
        if plan_item.existing_braintrust_id is None:
            raise ValueError("Update operation requires existing Braintrust ID")
        
        # Get the Okta resource
        okta_resources = await self.get_okta_resources()
        okta_resource = None
        for resource in okta_resources:
            if self.get_resource_identifier(resource) == plan_item.okta_resource_id:
                okta_resource = resource
                break
        
        if okta_resource is None:
            raise ValueError(f"Okta resource not found: {plan_item.okta_resource_id}")
        
        if dry_run:
            self._logger.info(
                "DRY RUN: Would update resource",
                okta_resource_id=plan_item.okta_resource_id,
                braintrust_resource_id=plan_item.existing_braintrust_id,
                updates=plan_item.proposed_changes,
            )
            operation.mark_completed(plan_item.existing_braintrust_id)
            return SyncResult(
                operation_id=operation.operation_id,
                okta_resource_id=plan_item.okta_resource_id,
                braintrust_resource_id=plan_item.existing_braintrust_id,
                braintrust_org=plan_item.braintrust_org,
                action=SyncAction.UPDATE,
                success=True,
                metadata={"dry_run": True, "proposed_changes": plan_item.proposed_changes},
            )
        
        # Update the resource
        braintrust_resource = await self.update_braintrust_resource(
            plan_item.existing_braintrust_id,
            okta_resource,
            plan_item.braintrust_org,
            plan_item.proposed_changes,
        )
        
        operation.mark_completed(plan_item.existing_braintrust_id)
        
        self._logger.info(
            "Updated resource",
            okta_resource_id=plan_item.okta_resource_id,
            braintrust_resource_id=plan_item.existing_braintrust_id,
            updates=plan_item.proposed_changes,
        )
        
        return SyncResult(
            operation_id=operation.operation_id,
            okta_resource_id=plan_item.okta_resource_id,
            braintrust_resource_id=plan_item.existing_braintrust_id,
            braintrust_org=plan_item.braintrust_org,
            action=SyncAction.UPDATE,
            success=True,
            metadata={"applied_changes": plan_item.proposed_changes},
        )
    
    async def _execute_delete(
        self,
        plan_item: SyncPlanItem,
        operation: SyncOperation,
        dry_run: bool,
    ) -> SyncResult:
        """Execute a delete operation.
        
        Args:
            plan_item: Plan item to execute
            operation: Sync operation for tracking
            dry_run: If True, don't make actual changes
            
        Returns:
            Sync result
        """
        if dry_run:
            operation.mark_completed()
            return SyncResult(
                operation_id=operation.operation_id,
                okta_resource_id=plan_item.okta_resource_id,
                braintrust_resource_id=plan_item.braintrust_resource_id,
                braintrust_org=plan_item.braintrust_org,
                action=SyncAction.DELETE,
                success=True,
                metadata={"dry_run": True, "reason": plan_item.reason},
            )
        
        # Delete the resource from Braintrust
        await self.delete_braintrust_resource(
            plan_item.braintrust_resource_id,
            plan_item.braintrust_org,
        )
        
        # Remove the resource mapping from state
        current_state = self.state_manager.get_current_state()
        if current_state:
            # Find and remove the mapping
            mapping_key = f"{plan_item.okta_resource_id}:{plan_item.braintrust_org}:{self.resource_type}"
            if mapping_key in current_state.resource_mappings:
                del current_state.resource_mappings[mapping_key]
                self._logger.debug(
                    "Removed resource mapping from state",
                    mapping_key=mapping_key,
                )
        
        operation.mark_completed()
        
        self._logger.info(
            "Deleted resource",
            okta_resource_id=plan_item.okta_resource_id,
            braintrust_resource_id=plan_item.braintrust_resource_id,
            braintrust_org=plan_item.braintrust_org,
        )
        
        return SyncResult(
            operation_id=operation.operation_id,
            okta_resource_id=plan_item.okta_resource_id,
            braintrust_resource_id=plan_item.braintrust_resource_id,
            braintrust_org=plan_item.braintrust_org,
            action=SyncAction.DELETE,
            success=True,
            metadata={"reason": plan_item.reason},
        )