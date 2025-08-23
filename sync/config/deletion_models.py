"""Deletion policy configuration models for stateless sync approach."""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DeletionCondition(BaseModel):
    """A single condition that must be met for resource deletion."""
    
    # Okta-based conditions
    status: Optional[str] = Field(
        None,
        description="Okta status condition (e.g., 'DEPROVISIONED', 'SUSPENDED')"
    )
    
    # Braintrust-based conditions  
    inactive_days: Optional[int] = Field(
        None,
        description="Number of days of inactivity before deletion is allowed",
        ge=0
    )
    
    # Custom conditions could be added here in the future
    custom_condition: Optional[str] = Field(
        None,
        description="Custom deletion condition (for future extension)"
    )


class ResourceDeletionPolicy(BaseModel):
    """Deletion policy for a specific resource type."""
    
    enabled: bool = Field(
        False,
        description="Whether deletion is enabled for this resource type"
    )
    
    okta_conditions: List[DeletionCondition] = Field(
        default_factory=list,
        description="Conditions based on Okta resource state"
    )
    
    braintrust_conditions: List[DeletionCondition] = Field(
        default_factory=list,
        description="Conditions based on Braintrust resource state"
    )
    
    scope: Optional[str] = Field(
        None,
        description="Deletion scope restriction (e.g., 'managed_roles_only', 'sync_created_only')"
    )


class UserDeletionPolicy(ResourceDeletionPolicy):
    """Deletion policy specifically for users."""
    
    # User-specific deletion options could be added here
    preserve_admin_users: bool = Field(
        True,
        description="Whether to preserve users with admin privileges"
    )
    
    require_confirmation: bool = Field(
        True,
        description="Whether user deletion requires additional confirmation"
    )


class GroupDeletionPolicy(ResourceDeletionPolicy):
    """Deletion policy specifically for groups."""
    
    # Group-specific deletion options
    preserve_system_groups: bool = Field(
        True,
        description="Whether to preserve built-in system groups"
    )
    
    min_member_threshold: Optional[int] = Field(
        None,
        description="Minimum number of members required before group can be deleted",
        ge=0
    )
    
    target_groups: Optional[List[str]] = Field(
        None,
        description="Specific list of group names to consider for deletion. If None, all groups are considered."
    )


class ACLDeletionPolicy(ResourceDeletionPolicy):
    """Deletion policy specifically for ACLs."""
    
    # ACL-specific deletion options
    preserve_manual_acls: bool = Field(
        True,
        description="Whether to preserve ACLs created manually (not via sync)"
    )


class DeletionPoliciesConfig(BaseModel):
    """Container for all resource deletion policies."""
    
    users: UserDeletionPolicy = Field(
        default_factory=UserDeletionPolicy,
        description="User deletion policy configuration"
    )
    
    groups: GroupDeletionPolicy = Field(
        default_factory=GroupDeletionPolicy,
        description="Group deletion policy configuration"
    )
    
    acls: ACLDeletionPolicy = Field(
        default_factory=ACLDeletionPolicy,
        description="ACL deletion policy configuration"
    )
    
    # Global deletion settings
    global_dry_run: bool = Field(
        False,
        description="Global dry run mode for all deletions (safety override)"
    )
    
    require_explicit_enable: bool = Field(
        True,
        description="Require explicit enabling of deletion for each resource type"
    )


# For backward compatibility and easier imports
__all__ = [
    "DeletionCondition",
    "ResourceDeletionPolicy", 
    "UserDeletionPolicy",
    "GroupDeletionPolicy",
    "ACLDeletionPolicy",
    "DeletionPoliciesConfig",
]