"""Base resource syncer with common sync patterns and operations."""

import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, TypeVar, Generic

import structlog
from pydantic import BaseModel, Field

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient, OktaUser, OktaGroup
from sync.core.state import StateManager, SyncOperation, SyncState

logger = structlog.get_logger(__name__)

# Type variables for generic resource handling
OktaResourceType = TypeVar('OktaResourceType', OktaUser, OktaGroup)
BraintrustResourceType = TypeVar('BraintrustResourceType')


class SyncAction(str, Enum):
    """Possible sync actions for a resource."""
    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"
    ERROR = "error"


class SyncPlanItem(BaseModel):
    """A single item in a sync plan."""
    
    okta_resource_id: str
    okta_resource_type: str  # "user" or "group"
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
    def calculate_updates(
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
            # Get current state
            current_state = self.state_manager.get_current_state()
            if current_state is None:
                self._logger.warning("No current sync state available")
                return plan_items
            
            # Get existing Braintrust resources for comparison
            braintrust_resources = await self.get_braintrust_resources(braintrust_org)
            braintrust_resource_map = {
                self.get_resource_identifier(res): res for res in braintrust_resources
            }
            
            # Process each Okta resource
            for okta_resource in okta_resources:
                if not self.should_sync_resource(okta_resource, braintrust_org, sync_rules):
                    continue
                
                okta_id = self.get_resource_identifier(okta_resource)
                
                # Check if resource already exists in Braintrust
                existing_mapping = current_state.get_mapping(
                    okta_id, braintrust_org, self.resource_type
                )
                
                if existing_mapping:
                    # Resource exists - check if update is needed
                    braintrust_resource = braintrust_resource_map.get(
                        existing_mapping.braintrust_id
                    )
                    
                    if braintrust_resource:
                        updates = self.calculate_updates(okta_resource, braintrust_resource)
                        if updates:
                            plan_items.append(SyncPlanItem(
                                okta_resource_id=okta_id,
                                okta_resource_type=self.resource_type,
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
                            braintrust_org=braintrust_org,
                            action=SyncAction.CREATE,
                            reason="Mapped resource missing in Braintrust",
                        ))
                else:
                    # New resource - create
                    if sync_rules.get('create_missing', True):
                        plan_items.append(SyncPlanItem(
                            okta_resource_id=okta_id,
                            okta_resource_type=self.resource_type,
                            braintrust_org=braintrust_org,
                            action=SyncAction.CREATE,
                            reason="New resource from Okta",
                        ))
                    else:
                        plan_items.append(SyncPlanItem(
                            okta_resource_id=okta_id,
                            okta_resource_type=self.resource_type,
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
            self._logger.error(
                "Failed to generate organization sync plan",
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
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
        
        # Add to state
        current_state = self.state_manager.get_current_state()
        if current_state:
            current_state.add_operation(operation)
        
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