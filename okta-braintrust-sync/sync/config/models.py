"""Configuration models for okta-braintrust-sync using Pydantic."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator, model_validator


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogFormat(str, Enum):
    """Log output formats."""
    JSON = "json"
    TEXT = "text"


class QueueBackend(str, Enum):
    """Queue backend types."""
    MEMORY = "memory"
    REDIS = "redis"
    DATABASE = "database"


class IdentityMappingStrategy(str, Enum):
    """Identity mapping strategies."""
    EMAIL = "email"
    CUSTOM_FIELD = "custom_field"
    MAPPING_FILE = "mapping_file"


# Okta Configuration
class OktaConfig(BaseModel):
    """Okta API configuration."""
    
    domain: str = Field(
        ..., 
        description="Okta domain (e.g., 'yourorg.okta.com')",
        min_length=1
    )
    api_token: SecretStr = Field(
        ...,
        description="Okta API token with appropriate permissions"
    )
    webhook_secret: Optional[SecretStr] = Field(
        None,
        description="Secret for webhook signature verification"
    )
    rate_limit_per_minute: int = Field(
        600,
        description="Rate limit for Okta API calls per minute",
        ge=1
    )
    timeout_seconds: int = Field(
        30,
        description="Timeout for Okta API calls in seconds",
        ge=1
    )
    
    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate Okta domain format."""
        # Remove protocol if present
        v = v.replace("https://", "").replace("http://", "")
        # Remove trailing slash
        v = v.rstrip("/")
        
        if not v.endswith(".okta.com") and not v.endswith(".oktapreview.com"):
            raise ValueError("Domain must be a valid Okta domain (.okta.com or .oktapreview.com)")
        
        return v


# Braintrust Configuration
class BraintrustOrgConfig(BaseModel):
    """Individual Braintrust organization configuration."""
    
    api_key: SecretStr = Field(
        ...,
        description="Braintrust API key for this organization"
    )
    url: HttpUrl = Field(
        HttpUrl("https://api.braintrust.dev"),
        description="Braintrust API URL"
    )
    timeout_seconds: int = Field(
        30,
        description="Timeout for Braintrust API calls in seconds",
        ge=1
    )
    rate_limit_per_minute: int = Field(
        300,
        description="Rate limit for Braintrust API calls per minute",
        ge=1
    )


# Sync Rules Configuration
class IdentityMappingConfig(BaseModel):
    """Identity mapping configuration."""
    
    strategy: IdentityMappingStrategy = Field(
        IdentityMappingStrategy.EMAIL,
        description="Strategy for mapping Okta users to Braintrust users"
    )
    custom_field: Optional[str] = Field(
        None,
        description="Custom Okta profile field for identity mapping (when strategy=custom_field)"
    )
    mapping_file: Optional[Path] = Field(
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
        ...,
        description="Group sync mapping rules",
        min_length=1
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


class SyncRulesConfig(BaseModel):
    """Sync rules configuration."""
    
    users: Optional[UserSyncConfig] = Field(
        None,
        description="User sync configuration"
    )
    groups: Optional[GroupSyncConfig] = Field(
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


# Sync Modes Configuration
class DeclarativeModeConfig(BaseModel):
    """Declarative sync mode configuration."""
    
    enabled: bool = Field(
        True,
        description="Whether declarative mode is enabled"
    )
    schedule: Optional[str] = Field(
        "0 */4 * * *",
        description="Cron expression for scheduled syncs (every 4 hours by default)"
    )
    full_reconciliation: Optional[str] = Field(
        "0 2 * * 0",
        description="Cron expression for full reconciliation (weekly by default)"
    )
    max_concurrent_orgs: int = Field(
        3,
        description="Maximum concurrent organizations to sync",
        ge=1
    )


class RealtimeModeConfig(BaseModel):
    """Real-time webhook mode configuration."""
    
    enabled: bool = Field(
        False,
        description="Whether real-time mode is enabled"
    )
    webhook_port: int = Field(
        8080,
        description="Port for webhook server",
        ge=1,
        le=65535
    )
    webhook_host: str = Field(
        "0.0.0.0",
        description="Host for webhook server"
    )
    queue_backend: QueueBackend = Field(
        QueueBackend.MEMORY,
        description="Backend for event queue"
    )
    max_queue_size: int = Field(
        10000,
        description="Maximum events in queue",
        ge=1
    )
    worker_count: int = Field(
        4,
        description="Number of event processing workers",
        ge=1
    )
    critical_events_only: bool = Field(
        True,
        description="Only process security-critical events in real-time"
    )


class PriorityRule(BaseModel):
    """Priority rule for determining which mode handles which events."""
    
    event_types: List[str] = Field(
        ...,
        description="List of Okta event types",
        min_length=1
    )
    mode: Literal["declarative", "realtime", "both"] = Field(
        ...,
        description="Which mode should handle these events"
    )


class SyncModesConfig(BaseModel):
    """Sync modes configuration."""
    
    declarative: DeclarativeModeConfig = Field(
        default_factory=DeclarativeModeConfig,
        description="Declarative mode configuration"
    )
    realtime: RealtimeModeConfig = Field(
        default_factory=RealtimeModeConfig,
        description="Real-time mode configuration"
    )
    priority_rules: List[PriorityRule] = Field(
        default_factory=list,
        description="Rules for determining which mode handles which events"
    )
    
    @model_validator(mode='after')
    def validate_at_least_one_mode(self) -> 'SyncModesConfig':
        """Ensure at least one sync mode is enabled."""
        if not self.declarative.enabled and not self.realtime.enabled:
            raise ValueError("At least one sync mode must be enabled")
        return self


# Sync Options
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


# Audit Configuration
class AuditConfig(BaseModel):
    """Audit and logging configuration."""
    
    enabled: bool = Field(
        True,
        description="Whether audit logging is enabled"
    )
    log_level: LogLevel = Field(
        LogLevel.INFO,
        description="Logging level"
    )
    log_format: LogFormat = Field(
        LogFormat.JSON,
        description="Log output format"
    )
    log_file: Optional[Path] = Field(
        None,
        description="Path to log file (uses stdout if not specified)"
    )
    retention_days: int = Field(
        90,
        description="Number of days to retain audit logs",
        ge=1
    )
    include_sensitive_data: bool = Field(
        False,
        description="Whether to include sensitive data in logs (not recommended for production)"
    )


# Main Configuration
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
    
    # Audit configuration
    audit: AuditConfig = Field(
        default_factory=AuditConfig,
        description="Audit and logging configuration"
    )
    
    # Optional external configurations
    redis_url: Optional[str] = Field(
        None,
        description="Redis URL for queue backend (when queue_backend=redis)"
    )
    database_url: Optional[str] = Field(
        None,
        description="Database URL for state persistence"
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
    
    @model_validator(mode='after') 
    def validate_queue_backend_config(self) -> 'SyncConfig':
        """Validate queue backend configuration."""
        if (self.sync_modes.realtime.enabled and 
            self.sync_modes.realtime.queue_backend == QueueBackend.REDIS and 
            not self.redis_url):
            raise ValueError("redis_url is required when queue_backend=redis")
        
        return self


# Runtime State Models (for internal use)
class SyncState(BaseModel):
    """Runtime sync state."""
    
    last_sync_time: Optional[str] = None
    last_full_sync_time: Optional[str] = None
    total_users_synced: int = 0
    total_groups_synced: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    is_running: bool = False
    current_operation: Optional[str] = None


class ResourceMapping(BaseModel):
    """Resource ID mapping between Okta and Braintrust."""
    
    okta_id: str
    braintrust_id: str
    braintrust_org: str
    resource_type: Literal["user", "group"]
    created_at: str
    updated_at: str