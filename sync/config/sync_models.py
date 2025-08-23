"""Synchronization configuration models."""

from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

from .base_models import IdentityMappingStrategy


class IdentityMappingConfig(BaseModel):
    """Identity mapping configuration."""
    
    strategy: IdentityMappingStrategy = Field(
        IdentityMappingStrategy.EMAIL,
        description="Strategy for mapping Okta users to Braintrust users"
    )
    custom_field: str | None = Field(
        None,
        description="Custom Okta profile field for identity mapping (when strategy=custom_field)"
    )
    mapping_file: Path | None = Field(
        None,
        description="Path to mapping file (when strategy=mapping_file)"
    )
    case_sensitive: bool = Field(
        False,
        description="Whether identity mapping should be case sensitive"
    )
    
    @model_validator(mode='after')
    def validate_strategy_config(self) -> 'IdentityMappingConfig':
        """Validate strategy-specific configuration."""
        if self.strategy == IdentityMappingStrategy.CUSTOM_FIELD and not self.custom_field:
            raise ValueError("custom_field is required when strategy=custom_field")
        
        if self.strategy == IdentityMappingStrategy.MAPPING_FILE and not self.mapping_file:
            raise ValueError("mapping_file is required when strategy=mapping_file")
        
        return self


class UserSyncMapping(BaseModel):
    """User sync mapping rule."""
    
    okta_filter: str = Field(
        ...,
        description="SCIM filter expression for selecting Okta users",
        min_length=1
    )
    braintrust_orgs: List[str] = Field(
        ...,
        description="List of Braintrust organization names to sync to",
        min_length=1
    )
    enabled: bool = Field(
        True,
        description="Whether this mapping is enabled"
    )


class GroupSyncMapping(BaseModel):
    """Group sync mapping rule."""
    
    okta_group_filter: str = Field(
        ...,
        description="SCIM filter expression for selecting Okta groups",
        min_length=1
    )
    braintrust_orgs: List[str] = Field(
        ...,
        description="List of Braintrust organization names to sync to",
        min_length=1
    )
    name_transform: str = Field(
        "{group.name}",
        description="Template for transforming group names (supports {group.name} placeholder)"
    )
    enabled: bool = Field(
        True,
        description="Whether this mapping is enabled"
    )


class UserSyncConfig(BaseModel):
    """User synchronization configuration."""
    
    enabled: bool = Field(
        True,
        description="Whether user sync is enabled"
    )
    mappings: List[UserSyncMapping] = Field(
        ...,
        description="User sync mapping rules",
        min_length=1
    )
    identity_mapping: IdentityMappingConfig = Field(
        default_factory=IdentityMappingConfig,
        description="Identity mapping configuration"
    )
    create_missing: bool = Field(
        True,
        description="Whether to create users that don't exist in Braintrust"
    )
    update_existing: bool = Field(
        True,
        description="Whether to update existing users in Braintrust"
    )
    sync_profile_fields: List[str] = Field(
        ["firstName", "lastName", "email", "login"],
        description="Okta profile fields to sync to Braintrust"
    )


class GroupSyncConfig(BaseModel):
    """Group synchronization configuration."""
    
    enabled: bool = Field(
        True,
        description="Whether group sync is enabled"
    )
    mappings: List[GroupSyncMapping] = Field(
        default_factory=list,
        description="Group sync mapping rules"
    )
    create_missing: bool = Field(
        True,
        description="Whether to create groups that don't exist in Braintrust"
    )
    update_existing: bool = Field(
        True,
        description="Whether to update existing groups in Braintrust"
    )
    sync_members: bool = Field(
        True,
        description="Whether to sync group memberships"
    )
    sync_description: bool = Field(
        True,
        description="Whether to sync group descriptions"
    )
    
    @model_validator(mode='after')
    def validate_mappings_when_enabled(self) -> 'GroupSyncConfig':
        """Ensure mappings are provided when group sync is enabled."""
        if self.enabled and not self.mappings:
            raise ValueError("mappings are required when group sync is enabled")
        return self


class SyncRulesConfig(BaseModel):
    """Sync rules configuration."""
    
    users: UserSyncConfig | None = Field(
        None,
        description="User sync configuration"
    )
    groups: GroupSyncConfig | None = Field(
        None,
        description="Group sync configuration"
    )
    
    @model_validator(mode='after')
    def validate_at_least_one_enabled(self) -> 'SyncRulesConfig':
        """Ensure at least one sync type is enabled."""
        if not self.users and not self.groups:
            raise ValueError("At least one of users or groups sync must be configured")
        
        if self.users and not self.users.enabled and self.groups and not self.groups.enabled:
            raise ValueError("At least one sync type must be enabled")
        
        return self


class SyncOptionsConfig(BaseModel):
    """General sync options configuration."""
    
    dry_run: bool = Field(
        False,
        description="Whether to run in dry-run mode (no actual changes)"
    )
    batch_size: int = Field(
        50,
        description="Number of resources to process in each batch",
        ge=1,
        le=1000
    )
    max_retries: int = Field(
        3,
        description="Maximum number of retry attempts for failed operations",
        ge=0
    )
    retry_delay_seconds: float = Field(
        1.0,
        description="Initial delay between retries in seconds",
        ge=0.1
    )
    remove_extra: bool = Field(
        False,
        description="Whether to remove users/groups not present in Okta (SCIM delete)"
    )
    continue_on_error: bool = Field(
        True,
        description="Whether to continue processing after individual errors"
    )