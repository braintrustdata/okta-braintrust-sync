"""Main configuration models for okta-braintrust-sync."""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field, model_validator

# Import all specialized configuration models
from .api_models import OktaConfig, BraintrustOrgConfig
from .sync_models import SyncRulesConfig, SyncOptionsConfig
from .mode_models import SyncModesConfig
from .audit_models import AuditConfig, StateManagementConfig
from .group_assignment_models import GroupAssignmentRules
from .role_project_models import RoleProjectRules
from .deletion_models import DeletionPoliciesConfig

# Re-export commonly used models for backward compatibility
from .base_models import SyncState, ResourceMapping
from .api_models import OktaConfig, BraintrustOrgConfig
from .sync_models import (
    IdentityMappingConfig, UserSyncMapping, GroupSyncMapping,
    UserSyncConfig, GroupSyncConfig, SyncRulesConfig, SyncOptionsConfig
)
from .mode_models import (
    DeclarativeModeConfig, RealtimeModeConfig, PriorityRule, SyncModesConfig
)
from .audit_models import AuditConfig, StateManagementConfig
from .deletion_models import (
    DeletionCondition, ResourceDeletionPolicy, UserDeletionPolicy,
    GroupDeletionPolicy, ACLDeletionPolicy, DeletionPoliciesConfig
)



class SyncConfig(BaseModel):
    """Main synchronization configuration."""
    
    # API configurations
    okta: OktaConfig = Field(
        ...,
        description="Okta API configuration"
    )
    braintrust_orgs: Dict[str, BraintrustOrgConfig] = Field(
        ...,
        description="Braintrust organizations configuration",
        min_length=1
    )
    
    # Sync configuration
    sync_modes: SyncModesConfig = Field(
        default_factory=SyncModesConfig,
        description="Sync modes configuration"
    )
    sync_rules: SyncRulesConfig = Field(
        ...,
        description="Sync rules configuration"
    )
    sync_options: SyncOptionsConfig = Field(
        default_factory=SyncOptionsConfig,
        description="General sync options"
    )
    
    # Group assignment configuration
    group_assignment: GroupAssignmentRules | None = Field(
        None,
        description="Group assignment rules for users after invitation acceptance"
    )
    
    # Role-project assignment configuration
    role_project_assignment: RoleProjectRules | None = Field(
        None,
        description="Role and project assignment rules for Groups → Roles → Projects workflow"
    )
    
    # Deletion policy configuration (stateless approach)
    deletion_policies: DeletionPoliciesConfig = Field(
        default_factory=DeletionPoliciesConfig,
        description="Explicit deletion policies for stateless sync approach"
    )
    
    # Audit configuration
    audit: AuditConfig = Field(
        default_factory=AuditConfig,
        description="Audit and logging configuration"
    )
    
    # State management configuration
    state_management: StateManagementConfig = Field(
        default_factory=StateManagementConfig,
        description="State management configuration"
    )
    
    @model_validator(mode='after')
    def validate_braintrust_orgs_exist(self) -> 'SyncConfig':
        """Validate that referenced Braintrust orgs exist in configuration."""
        configured_orgs = set(self.braintrust_orgs.keys())
        
        # Check user mappings
        if self.sync_rules.users:
            for mapping in self.sync_rules.users.mappings:
                for org in mapping.braintrust_orgs:
                    if org not in configured_orgs:
                        raise ValueError(f"User mapping references unknown Braintrust org: {org}")
        
        # Check group mappings
        if self.sync_rules.groups:
            for mapping in self.sync_rules.groups.mappings:
                for org in mapping.braintrust_orgs:
                    if org not in configured_orgs:
                        raise ValueError(f"Group mapping references unknown Braintrust org: {org}")
        
        return self