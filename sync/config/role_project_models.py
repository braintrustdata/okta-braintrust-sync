"""Configuration models for role and project assignment workflow."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class BraintrustPermission(str, Enum):
    """Available Braintrust permissions for roles.
    
    These are the 8 core permissions available in Braintrust:
    - CRUD operations: create, read, update, delete
    - ACL management: create_acls, read_acls, update_acls, delete_acls
    """
    CREATE = "create"           # Create new objects (projects, experiments, datasets, etc.)
    READ = "read"               # View/read objects and their data
    UPDATE = "update"           # Modify existing objects
    DELETE = "delete"           # Delete objects
    CREATE_ACLS = "create_acls" # Create new ACL entries (grant permissions to others)
    READ_ACLS = "read_acls"     # View existing ACL entries
    UPDATE_ACLS = "update_acls" # Modify existing ACL entries
    DELETE_ACLS = "delete_acls" # Remove ACL entries


class BraintrustObjectType(str, Enum):
    """Valid object types for restrict_object_type in permissions.
    
    These determine what specific objects a permission applies to.
    When null/None, the permission applies to all object types.
    """
    ORGANIZATION = "organization"
    PROJECT = "project"
    EXPERIMENT = "experiment"
    DATASET = "dataset"
    PROMPT = "prompt"
    PROMPT_SESSION = "prompt_session"
    GROUP = "group"
    ROLE = "role"
    ORG_MEMBER = "org_member"
    PROJECT_LOG = "project_log"
    ORG_PROJECT = "org_project"


class RolePermission(BaseModel):
    """Individual permission within a role.
    
    Represents one permission that can optionally be restricted to
    specific object types for fine-grained access control.
    
    Examples:
        - Read everything: {"permission": "read", "restrict_object_type": null}
        - Create only datasets: {"permission": "create", "restrict_object_type": "dataset"}
        - Delete only experiments: {"permission": "delete", "restrict_object_type": "experiment"}
    """
    
    permission: BraintrustPermission = Field(
        ...,
        description="The permission type"
    )
    restrict_object_type: Optional[BraintrustObjectType] = Field(
        None,
        description="Optional restriction to specific object types (null = all types)"
    )


class RoleDefinition(BaseModel):
    """Complete role definition with permissions and metadata.
    
    Defines a reusable role that can be assigned to groups via ACLs.
    Roles are organization-scoped and contain a collection of permissions.
    
    Example:
        Engineer role with CRUD but no ACL management:
        {
            "name": "Engineer",
            "description": "Standard engineering permissions",
            "member_permissions": [
                {"permission": "create", "restrict_object_type": null},
                {"permission": "read", "restrict_object_type": null},
                {"permission": "update", "restrict_object_type": null},
                {"permission": "delete", "restrict_object_type": null}
            ]
        }
    """
    
    name: str = Field(
        ...,
        description="Role name (must be unique within organization)",
        min_length=1,
        max_length=255
    )
    description: str = Field(
        "",
        description="Human-readable description of the role's purpose"
    )
    member_permissions: List[RolePermission] = Field(
        ...,
        description="List of permissions included in this role",
        min_length=1
    )
    
    @field_validator("member_permissions")
    @classmethod
    def validate_permissions_not_empty(cls, v: List[RolePermission]) -> List[RolePermission]:
        """Ensure at least one permission is provided."""
        if not v:
            raise ValueError("Role must have at least one permission")
        return v


class ProjectMatchRule(BaseModel):
    """Rule for matching projects to assign roles to.
    
    Supports different methods of specifying which projects should
    receive role assignments for a group.
    """
    
    # ========== Explicit Project Lists ==========
    project_names: Optional[List[str]] = Field(
        None,
        description="Explicit list of project names"
    )
    project_ids: Optional[List[str]] = Field(
        None,
        description="Explicit list of project UUIDs"
    )
    
    # ========== Pattern-Based Matching ==========
    name_pattern: Optional[str] = Field(
        None,
        description="Regex pattern to match project names"
    )
    name_contains: Optional[List[str]] = Field(
        None,
        description="List of strings that project names must contain (OR logic)"
    )
    name_starts_with: Optional[str] = Field(
        None,
        description="String that project names must start with"
    )
    name_ends_with: Optional[str] = Field(
        None,
        description="String that project names must end with"
    )
    
    # ========== Tag-Based Matching ==========
    # Note: This would require project tagging functionality
    required_tags: Optional[Dict[str, str]] = Field(
        None,
        description="Project tags that must match (key-value pairs)"
    )
    
    # ========== Special Selectors ==========
    all_projects: bool = Field(
        False,
        description="Whether to match ALL projects in the organization"
    )
    exclude_patterns: Optional[List[str]] = Field(
        None,
        description="Regex patterns for projects to exclude"
    )
    
    @model_validator(mode='after')
    def validate_at_least_one_rule(self) -> 'ProjectMatchRule':
        """Ensure at least one matching rule is specified."""
        has_explicit = bool(self.project_names or self.project_ids)
        has_pattern = bool(self.name_pattern or self.name_contains or 
                          self.name_starts_with or self.name_ends_with)
        has_tags = bool(self.required_tags)
        has_all = self.all_projects
        
        if not (has_explicit or has_pattern or has_tags or has_all):
            raise ValueError(
                "At least one project matching rule must be specified: "
                "project_names, project_ids, patterns, tags, or all_projects"
            )
        
        return self


class GroupRoleAssignment(BaseModel):
    """Assignment of a role to a group with project targeting.
    
    This defines that a specific group should be given a specific role
    on a set of projects determined by the matching rules.
    
    Example:
        Give Engineering group the Engineer role on all ML projects:
        {
            "group_name": "Engineering",
            "role_name": "Engineer",
            "project_match": {
                "name_pattern": "(?i).*ml.*|.*machine.learning.*"
            },
            "enabled": true
        }
    """
    
    group_name: str = Field(
        ...,
        description="Name of the group to assign the role to",
        min_length=1
    )
    role_name: str = Field(
        ...,
        description="Name of the role to assign",
        min_length=1
    )
    project_match: ProjectMatchRule = Field(
        ...,
        description="Rules for determining which projects to assign the role on"
    )
    enabled: bool = Field(
        True,
        description="Whether this assignment is active"
    )
    priority: int = Field(
        0,
        description="Priority for assignment order (higher = processed first)"
    )


class RoleProjectConfig(BaseModel):
    """Configuration for role and project assignment workflow.
    
    This enables the Groups → Roles → Projects workflow by defining:
    1. Standard roles that should exist in the organization
    2. Rules for assigning groups to roles on specific projects
    
    The workflow:
    1. Ensure all defined roles exist in Braintrust
    2. For each group assignment, find matching projects
    3. Create ACLs granting the group the role on those projects
    """
    
    # ========== Role Management ==========
    standard_roles: Optional[List[RoleDefinition]] = Field(
        None,
        description="Standard roles to ensure exist in the organization"
    )
    auto_create_roles: bool = Field(
        True,
        description="Whether to automatically create missing roles"
    )
    update_existing_roles: bool = Field(
        False,
        description="Whether to update existing roles if permissions differ"
    )
    
    # ========== Group → Role → Project Assignments ==========
    group_assignments: List[GroupRoleAssignment] = Field(
        ...,
        description="Rules for assigning groups to roles on projects",
        min_length=1
    )
    
    # ========== Sync Behavior ==========
    remove_unmanaged_acls: bool = Field(
        False,
        description="Whether to remove ACLs not defined in configuration (DANGEROUS)"
    )
    dry_run: bool = Field(
        False,
        description="Preview changes without applying them"
    )
    
    @field_validator("group_assignments")
    @classmethod
    def validate_unique_assignments(cls, v: List[GroupRoleAssignment]) -> List[GroupRoleAssignment]:
        """Ensure no duplicate group-role-project combinations."""
        # Note: This is a simplified validation - full validation would need
        # to resolve project matches to detect overlaps
        return v


class BraintrustOrgRoleConfig(BaseModel):
    """Role and project configuration for a specific Braintrust organization.
    
    Allows per-organization customization of roles and project assignments.
    """
    
    braintrust_org: str = Field(
        ...,
        description="Braintrust organization name",
        min_length=1
    )
    role_project_config: RoleProjectConfig = Field(
        ...,
        description="Role and project configuration for this org"
    )
    enabled: bool = Field(
        True,
        description="Whether role-project management is enabled for this org"
    )


class RoleProjectRules(BaseModel):
    """Complete role-project assignment rules for all organizations.
    
    Top-level configuration that can define:
    - A global configuration that applies to all orgs
    - Per-org configurations that override the global config
    
    Similar structure to GroupAssignmentRules but for role-project workflow.
    """
    
    global_config: Optional[RoleProjectConfig] = Field(
        None,
        description="Global role-project config (can be overridden per org)"
    )
    org_configs: Optional[List[BraintrustOrgRoleConfig]] = Field(
        None,
        description="Per-organization role-project configurations"
    )
    
    @model_validator(mode='after')
    def validate_at_least_one_config(self) -> 'RoleProjectRules':
        """Ensure at least one configuration is provided."""
        if not self.global_config and not self.org_configs:
            raise ValueError("Either global_config or org_configs must be provided")
        return self
    
    def get_config_for_org(self, org_name: str) -> Optional[RoleProjectConfig]:
        """Get the role-project config for a specific org.
        
        Returns org-specific config if available, otherwise returns global config.
        
        Args:
            org_name: Braintrust organization name
            
        Returns:
            RoleProjectConfig if found, None otherwise
        """
        # Check for org-specific config first
        if self.org_configs:
            for org_config in self.org_configs:
                if org_config.braintrust_org == org_name and org_config.enabled:
                    return org_config.role_project_config
        
        # Fall back to global config
        return self.global_config


# ========== Predefined Common Roles ==========
# These can be used as templates or defaults

# Administrative role with full permissions
ADMIN_ROLE = RoleDefinition(
    name="Admin",
    description="Full administrative access including ACL management",
    member_permissions=[
        RolePermission(permission=BraintrustPermission.CREATE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.READ, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.UPDATE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.DELETE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.CREATE_ACLS, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.READ_ACLS, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.UPDATE_ACLS, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.DELETE_ACLS, restrict_object_type=None),
    ]
)

# Standard engineer role with CRUD but no ACL management
ENGINEER_ROLE = RoleDefinition(
    name="Engineer",
    description="Standard engineering permissions - CRUD operations without ACL management",
    member_permissions=[
        RolePermission(permission=BraintrustPermission.CREATE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.READ, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.UPDATE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.DELETE, restrict_object_type=None),
    ]
)

# Data scientist role with focus on experiments and datasets
DATA_SCIENTIST_ROLE = RoleDefinition(
    name="DataScientist",
    description="Data science permissions - read all, create/modify experiments and datasets",
    member_permissions=[
        RolePermission(permission=BraintrustPermission.READ, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.CREATE, restrict_object_type=BraintrustObjectType.EXPERIMENT),
        RolePermission(permission=BraintrustPermission.CREATE, restrict_object_type=BraintrustObjectType.DATASET),
        RolePermission(permission=BraintrustPermission.UPDATE, restrict_object_type=BraintrustObjectType.EXPERIMENT),
        RolePermission(permission=BraintrustPermission.UPDATE, restrict_object_type=BraintrustObjectType.DATASET),
        RolePermission(permission=BraintrustPermission.DELETE, restrict_object_type=BraintrustObjectType.EXPERIMENT),
        RolePermission(permission=BraintrustPermission.DELETE, restrict_object_type=BraintrustObjectType.DATASET),
    ]
)

# Read-only viewer role
VIEWER_ROLE = RoleDefinition(
    name="Viewer",
    description="Read-only access to all content",
    member_permissions=[
        RolePermission(permission=BraintrustPermission.READ, restrict_object_type=None),
    ]
)

# Project manager role with project-level permissions
PROJECT_MANAGER_ROLE = RoleDefinition(
    name="ProjectManager",
    description="Project management permissions - full project control including team management",
    member_permissions=[
        RolePermission(permission=BraintrustPermission.CREATE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.READ, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.UPDATE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.DELETE, restrict_object_type=None),
        RolePermission(permission=BraintrustPermission.CREATE_ACLS, restrict_object_type=BraintrustObjectType.PROJECT),
        RolePermission(permission=BraintrustPermission.READ_ACLS, restrict_object_type=BraintrustObjectType.PROJECT),
        RolePermission(permission=BraintrustPermission.UPDATE_ACLS, restrict_object_type=BraintrustObjectType.PROJECT),
        RolePermission(permission=BraintrustPermission.DELETE_ACLS, restrict_object_type=BraintrustObjectType.PROJECT),
    ]
)

# Collection of all predefined roles for easy access
STANDARD_ROLES = [
    ADMIN_ROLE,
    ENGINEER_ROLE,
    DATA_SCIENTIST_ROLE,
    VIEWER_ROLE,
    PROJECT_MANAGER_ROLE,
]