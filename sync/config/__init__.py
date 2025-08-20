"""Configuration package for okta-braintrust-sync."""

from .models import SyncConfig
from .loader import ConfigLoader, find_config_file

# Re-export main configuration classes for backward compatibility
from .models import (
    # Main configuration
    SyncConfig,
    
    # API configurations
    OktaConfig,
    BraintrustOrgConfig,
    
    # Sync configurations
    SyncRulesConfig,
    SyncOptionsConfig,
    UserSyncConfig,
    GroupSyncConfig,
    IdentityMappingConfig,
    
    # Mode configurations
    SyncModesConfig,
    DeclarativeModeConfig,
    RealtimeModeConfig,
    
    # Audit and state configurations
    AuditConfig,
    StateManagementConfig,
    
    # Runtime state models
    SyncState,
    ResourceMapping,
)

# Re-export specialized configuration models
from .group_assignment_models import GroupAssignmentRules
from .role_project_models import RoleProjectRules

__all__ = [
    # Core classes
    "SyncConfig",
    "ConfigLoader",
    "find_config_file",
    
    # API configurations
    "OktaConfig",
    "BraintrustOrgConfig",
    
    # Sync configurations
    "SyncRulesConfig",
    "SyncOptionsConfig", 
    "UserSyncConfig",
    "GroupSyncConfig",
    "IdentityMappingConfig",
    
    # Mode configurations
    "SyncModesConfig",
    "DeclarativeModeConfig",
    "RealtimeModeConfig",
    
    # Audit and state configurations
    "AuditConfig",
    "StateManagementConfig",
    
    # Runtime state models
    "SyncState",
    "ResourceMapping",
    
    # Specialized models
    "GroupAssignmentRules",
    "RoleProjectRules",
]