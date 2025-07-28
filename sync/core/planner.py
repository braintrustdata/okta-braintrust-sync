"""Sync planning orchestration for coordinating resource synchronization."""

import uuid
from typing import Any, Dict, List, Optional, Set

import structlog
from pydantic import BaseModel, Field

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient
from sync.config.models import SyncConfig
from sync.core.state import StateManager
from sync.resources.base import SyncPlanItem, SyncAction
from sync.resources.users import UserSyncer
from sync.resources.groups import GroupSyncer

logger = structlog.get_logger(__name__)


class SyncPlan(BaseModel):
    """Complete sync plan for all resources and organizations."""
    
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    config_hash: str
    target_organizations: List[str]
    
    # Plan items organized by resource type and dependency order
    user_items: List[SyncPlanItem] = Field(default_factory=list)
    group_items: List[SyncPlanItem] = Field(default_factory=list)
    
    # Summary statistics
    total_items: int = 0
    items_by_action: Dict[str, int] = Field(default_factory=dict)
    items_by_org: Dict[str, int] = Field(default_factory=dict)
    
    # Dependency information
    dependencies_resolved: bool = False
    dependency_graph: Dict[str, List[str]] = Field(default_factory=dict)
    
    # Metadata
    created_at: str
    estimated_duration_minutes: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    
    def add_items(self, items: List[SyncPlanItem], resource_type: str) -> None:
        """Add sync plan items to the plan.
        
        Args:
            items: List of sync plan items to add
            resource_type: Type of resource ("user" or "group")
        """
        if resource_type == "user":
            self.user_items.extend(items)
        elif resource_type == "group":
            self.group_items.extend(items)
        else:
            raise ValueError(f"Unknown resource type: {resource_type}")
        
        # Update statistics
        self.total_items = len(self.user_items) + len(self.group_items)
        
        for item in items:
            action = item.action.value if hasattr(item.action, 'value') else str(item.action)
            self.items_by_action[action] = self.items_by_action.get(action, 0) + 1
            self.items_by_org[item.braintrust_org] = self.items_by_org.get(item.braintrust_org, 0) + 1
    
    def get_all_items(self) -> List[SyncPlanItem]:
        """Get all sync plan items in dependency order.
        
        Returns:
            List of all sync plan items, users first (groups depend on users)
        """
        return self.user_items + self.group_items
    
    def get_items_by_org(self, org_name: str) -> List[SyncPlanItem]:
        """Get all sync plan items for a specific organization.
        
        Args:
            org_name: Organization name
            
        Returns:
            List of sync plan items for the organization
        """
        return [item for item in self.get_all_items() if item.braintrust_org == org_name]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get plan summary statistics.
        
        Returns:
            Dictionary with plan summary information
        """
        return {
            "plan_id": self.plan_id,
            "total_items": self.total_items,
            "user_items": len(self.user_items),
            "group_items": len(self.group_items),
            "target_organizations": self.target_organizations,
            "actions": self.items_by_action,
            "organizations": self.items_by_org,
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "warnings": self.warnings,
            "dependencies_resolved": self.dependencies_resolved,
        }


class SyncPlanner:
    """Plans and orchestrates sync operations across multiple resources and organizations."""
    
    def __init__(
        self,
        config: SyncConfig,
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
    ) -> None:
        """Initialize sync planner.
        
        Args:
            config: Sync configuration
            okta_client: Okta API client
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
        """
        self.config = config
        self.okta_client = okta_client
        self.braintrust_clients = braintrust_clients
        self.state_manager = state_manager
        
        # Initialize resource syncers
        # Use default identity mapping strategy since it's not in the current config model
        identity_strategy = "email"  # Default strategy
        custom_mappings = {}  # Default empty mappings
        
        # If user sync is configured, we could get these from the user config in the future
        if config.sync_rules.users:
            # For now, use defaults. In the future, these could be part of UserSyncConfig
            pass
            
        self.user_syncer = UserSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=state_manager,
            identity_mapping_strategy=identity_strategy,
            custom_field_mappings=custom_mappings,
        )
        
        # Use default group sync settings since they're not in the current config model
        sync_memberships = True  # Default to syncing group memberships
        name_prefix = ""  # Default no prefix
        name_suffix = ""  # Default no suffix
        
        # If group sync is configured, we could get these from the group config in the future
        if config.sync_rules.groups:
            # For now, use defaults. In the future, these could be part of GroupSyncConfig
            pass
            
        self.group_syncer = GroupSyncer(
            okta_client=okta_client,
            braintrust_clients=braintrust_clients,
            state_manager=state_manager,
            sync_group_memberships=sync_memberships,
            group_name_prefix=name_prefix,
            group_name_suffix=name_suffix,
        )
        
        self._logger = logger.bind(
            planner_type="SyncPlanner",
            target_orgs=list(braintrust_clients.keys()),
        )
    
    async def generate_sync_plan(
        self,
        target_organizations: Optional[List[str]] = None,
        resource_types: Optional[List[str]] = None,
        okta_filters: Optional[Dict[str, str]] = None,
        dry_run: bool = True,
    ) -> SyncPlan:
        """Generate a comprehensive sync plan.
        
        Args:
            target_organizations: List of Braintrust organizations to sync to
            resource_types: List of resource types to sync ("user", "group")
            okta_filters: Optional Okta filters by resource type
            dry_run: Whether this is a dry run planning
            
        Returns:
            Complete sync plan
        """
        from datetime import datetime
        
        # Set defaults
        if target_organizations is None:
            target_organizations = list(self.braintrust_clients.keys())
        
        if resource_types is None:
            resource_types = ["user", "group"]
        
        if okta_filters is None:
            okta_filters = {}
        
        # Validate organizations
        for org in target_organizations:
            if org not in self.braintrust_clients:
                raise ValueError(f"No Braintrust client configured for org: {org}")
        
        self._logger.info(
            "Generating sync plan",
            target_organizations=target_organizations,
            resource_types=resource_types,
            dry_run=dry_run,
        )
        
        try:
            # Create sync plan
            plan = SyncPlan(
                config_hash=self._calculate_config_hash(),
                target_organizations=target_organizations,
                created_at=datetime.utcnow().isoformat(),
            )
            
            # Generate user sync plan
            if "user" in resource_types:
                user_items = await self._generate_user_plan(
                    target_organizations,
                    okta_filters.get("user"),
                )
                plan.add_items(user_items, "user")
                
                self._logger.debug(
                    "Generated user sync plan",
                    user_items=len(user_items),
                )
            
            # Generate group sync plan
            if "group" in resource_types:
                group_items = await self._generate_group_plan(
                    target_organizations,
                    okta_filters.get("group"),
                )
                plan.add_items(group_items, "group")
                
                self._logger.debug(
                    "Generated group sync plan",
                    group_items=len(group_items),
                )
            
            # Resolve dependencies
            plan = self._resolve_dependencies(plan)
            
            # Calculate estimated duration
            plan.estimated_duration_minutes = self._estimate_duration(plan)
            
            # Add warnings
            plan.warnings.extend(self._generate_warnings(plan))
            
            self._logger.info(
                "Generated sync plan",
                plan_id=plan.plan_id,
                total_items=plan.total_items,
                estimated_duration=plan.estimated_duration_minutes,
                warnings=len(plan.warnings),
            )
            
            return plan
            
        except Exception as e:
            self._logger.error("Failed to generate sync plan", error=str(e))
            raise
    
    async def _generate_user_plan(
        self,
        target_organizations: List[str],
        okta_filter: Optional[str] = None,
    ) -> List[SyncPlanItem]:
        """Generate sync plan for users.
        
        Args:
            target_organizations: List of target Braintrust organizations
            okta_filter: Optional Okta filter expression
            
        Returns:
            List of user sync plan items
        """
        try:
            sync_rules = self._get_sync_rules_dict()
            
            user_items = await self.user_syncer.generate_sync_plan(
                braintrust_orgs=target_organizations,
                sync_rules=sync_rules,
                okta_filter=okta_filter,
            )
            
            self._logger.debug(
                "Generated user plan",
                items=len(user_items),
                organizations=target_organizations,
            )
            
            return user_items
            
        except Exception as e:
            self._logger.error("Failed to generate user plan", error=str(e))
            raise
    
    async def _generate_group_plan(
        self,
        target_organizations: List[str],
        okta_filter: Optional[str] = None,
    ) -> List[SyncPlanItem]:
        """Generate sync plan for groups.
        
        Args:
            target_organizations: List of target Braintrust organizations
            okta_filter: Optional Okta filter expression
            
        Returns:
            List of group sync plan items
        """
        try:
            sync_rules = self._get_sync_rules_dict()
            
            group_items = await self.group_syncer.generate_sync_plan(
                braintrust_orgs=target_organizations,
                sync_rules=sync_rules,
                okta_filter=okta_filter,
            )
            
            self._logger.debug(
                "Generated group plan",
                items=len(group_items),
                organizations=target_organizations,
            )
            
            return group_items
            
        except Exception as e:
            self._logger.error("Failed to generate group plan", error=str(e))
            raise
    
    def _resolve_dependencies(self, plan: SyncPlan) -> SyncPlan:
        """Resolve dependencies between sync plan items.
        
        Args:
            plan: Sync plan to resolve dependencies for
            
        Returns:
            Plan with resolved dependencies
        """
        try:
            # Users must be synced before groups (since groups can contain users)
            # This is already handled by our ordering in get_all_items()
            
            # Within groups, we need to handle nested group dependencies
            # For now, we'll sync groups in the order they appear
            # In a more sophisticated implementation, we'd build a proper dependency graph
            
            # Mark group items that depend on user creation
            for group_item in plan.group_items:
                if group_item.action in [SyncAction.CREATE, SyncAction.UPDATE]:
                    # Find user dependencies based on group membership
                    user_dependencies = []
                    for user_item in plan.user_items:
                        if (user_item.braintrust_org == group_item.braintrust_org and
                            user_item.action == SyncAction.CREATE):
                            user_dependencies.append(user_item.okta_resource_id)
                    
                    if user_dependencies:
                        group_item.dependencies.extend(user_dependencies)
                        group_item.metadata["depends_on_users"] = len(user_dependencies)
            
            plan.dependencies_resolved = True
            
            self._logger.debug(
                "Resolved dependencies",
                plan_id=plan.plan_id,
                group_dependencies=sum(len(item.dependencies) for item in plan.group_items),
            )
            
            return plan
            
        except Exception as e:
            self._logger.error("Failed to resolve dependencies", error=str(e))
            plan.warnings.append(f"Failed to resolve dependencies: {e}")
            return plan
    
    def _estimate_duration(self, plan: SyncPlan) -> float:
        """Estimate sync plan execution duration in minutes.
        
        Args:
            plan: Sync plan to estimate
            
        Returns:
            Estimated duration in minutes
        """
        try:
            # Rough estimates based on operation type
            time_estimates = {
                "create": 0.5,  # 30 seconds per create
                "update": 0.3,  # 18 seconds per update  
                "skip": 0.1,    # 6 seconds per skip (validation time)
            }
            
            total_minutes = 0.0
            
            for action, count in plan.items_by_action.items():
                estimate = time_estimates.get(action.lower(), 0.5)
                total_minutes += estimate * count
            
            # Add overhead for API rate limiting and network delays
            overhead_factor = 1.2
            total_minutes *= overhead_factor
            
            # Add organization setup overhead
            org_overhead = len(plan.target_organizations) * 0.5
            total_minutes += org_overhead
            
            return round(total_minutes, 2)
            
        except Exception as e:
            self._logger.warning("Failed to estimate duration", error=str(e))
            return None
    
    def _generate_warnings(self, plan: SyncPlan) -> List[str]:
        """Generate warnings for potential issues in the sync plan.
        
        Args:
            plan: Sync plan to analyze
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        try:
            # Large plan warning
            if plan.total_items > 1000:
                warnings.append(
                    f"Large sync plan with {plan.total_items} items. "
                    "Consider running in smaller batches for better error recovery."
                )
            
            # Many creates warning
            create_count = plan.items_by_action.get("create", 0)
            if create_count > 100:
                warnings.append(
                    f"Plan includes {create_count} resource creations. "
                    "Ensure sufficient API rate limits and consider dry-run first."
                )
            
            # Cross-org consistency warning
            if len(plan.target_organizations) > 1:
                warnings.append(
                    "Syncing to multiple organizations. "
                    "Ensure consistent identity mapping across organizations."
                )
            
            # Group dependency warning
            group_creates = len([item for item in plan.group_items if item.action == SyncAction.CREATE])
            user_creates = len([item for item in plan.user_items if item.action == SyncAction.CREATE])
            
            if group_creates > 0 and user_creates > 0:
                warnings.append(
                    f"Plan includes {group_creates} group creations and {user_creates} user creations. "
                    "Users will be created before groups to resolve membership dependencies."
                )
            
            # No changes warning
            if plan.total_items == 0:
                warnings.append("No sync operations planned. All resources may already be up to date.")
            
            # Only skips warning
            skip_count = plan.items_by_action.get("skip", 0)
            if skip_count == plan.total_items and plan.total_items > 0:
                warnings.append("All planned operations are skips. No actual changes will be made.")
            
        except Exception as e:
            self._logger.warning("Failed to generate warnings", error=str(e))
            warnings.append(f"Warning generation failed: {e}")
        
        return warnings
    
    def _calculate_config_hash(self) -> str:
        """Calculate a hash of the current configuration for plan validation.
        
        Returns:
            Configuration hash string
        """
        import hashlib
        import json
        
        try:
            # Create a simplified config representation for hashing
            config_data = {
                "okta_domain": self.config.okta.domain,
                "braintrust_orgs": list(self.config.braintrust_orgs.keys()),
                "sync_rules": self.config.sync_rules.model_dump(),
            }
            
            config_str = json.dumps(config_data, sort_keys=True)
            return hashlib.md5(config_str.encode()).hexdigest()[:16]
            
        except Exception as e:
            self._logger.warning("Failed to calculate config hash", error=str(e))
            return "unknown"
    
    def _get_sync_rules_dict(self) -> Dict[str, Any]:
        """Get sync rules as a dictionary for syncer compatibility.
        
        Returns:
            Sync rules dictionary with safe defaults
        """
        # Use safe defaults since the current config model doesn't have these fields
        return {
            "sync_all": True,
            "create_missing": True,  # Default: create missing resources
            "update_existing": True,  # Default: update existing resources
            "only_active_users": True,  # Default: only sync active users
            "email_domain_filters": {},  # Default: no domain filters (dict by org)
            "group_filters": {},  # Default: no group filters (dict by org)
            "profile_filters": {},  # Default: no profile filters (dict by org)
            "group_type_filters": {},  # Default: no group type filters (dict by org)
            "group_name_patterns": {},  # Default: no name patterns (dict by org)
            "group_profile_filters": {},  # Default: no group profile filters (dict by org)
            "min_group_members": {},  # Default: no minimum members (dict by org)
            "limit": None,  # Default: no limit
        }
    
    async def validate_plan_preconditions(
        self,
        target_organizations: List[str],
    ) -> List[str]:
        """Validate that preconditions are met for sync plan execution.
        
        Args:
            target_organizations: Organizations to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        try:
            self._logger.debug("Validating plan preconditions", organizations=target_organizations)
            
            # Validate Okta connectivity
            try:
                okta_healthy = await self.okta_client.health_check()
                if not okta_healthy:
                    errors.append("Okta API health check failed")
            except Exception as e:
                errors.append(f"Okta API connectivity error: {e}")
            
            # Validate Braintrust connectivity for each org
            for org_name in target_organizations:
                if org_name not in self.braintrust_clients:
                    errors.append(f"No Braintrust client configured for organization: {org_name}")
                    continue
                
                try:
                    client = self.braintrust_clients[org_name]
                    bt_healthy = await client.health_check()
                    if not bt_healthy:
                        errors.append(f"Braintrust API health check failed for org: {org_name}")
                except Exception as e:
                    errors.append(f"Braintrust API connectivity error for org {org_name}: {e}")
            
            # Validate state manager
            current_state = self.state_manager.get_current_state()
            if current_state is None:
                errors.append("No current sync state available. Run 'sync validate' first.")
            
            self._logger.debug(
                "Completed precondition validation",
                errors=len(errors),
            )
            
        except Exception as e:
            errors.append(f"Precondition validation failed: {e}")
        
        return errors