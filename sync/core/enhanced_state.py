"""Enhanced state management with drift detection and managed resource tracking."""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)


class ResourceType(str, Enum):
    """Types of resources tracked in state."""
    USER = "user"
    GROUP = "group"
    ROLE = "role"
    PROJECT = "project"
    ACL = "acl"
    GROUP_ASSIGNMENT = "group_assignment"


class ManagementStatus(str, Enum):
    """How a resource is managed."""
    SYNC_MANAGED = "sync_managed"      # Created and managed by sync
    SYNC_MODIFIED = "sync_modified"    # Modified by sync but not created
    EXTERNAL = "external"              # Created externally, not managed
    DRIFT_DETECTED = "drift_detected"  # Was managed but has external changes


class ManagedResource(BaseModel):
    """Enhanced resource tracking with management metadata."""
    
    # Identity
    resource_id: str                   # Unique ID in Braintrust
    resource_type: ResourceType
    resource_name: Optional[str] = None
    braintrust_org: str
    
    # Management metadata
    management_status: ManagementStatus
    created_by_sync: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_synced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Configuration tracking
    config_hash: Optional[str] = None  # Hash of the config that created this
    config_source: Optional[str] = None  # Which config section created this
    
    # Drift detection
    last_known_state: Optional[Dict[str, Any]] = None
    external_modifications_detected: bool = False
    drift_details: Optional[List[str]] = None
    
    # Relationships
    parent_resource_id: Optional[str] = None  # E.g., role that created this ACL
    child_resource_ids: List[str] = Field(default_factory=list)
    
    def calculate_config_hash(self, config: Dict[str, Any]) -> str:
        """Calculate hash of configuration for drift detection."""
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]
    
    def update_sync_time(self) -> None:
        """Update the last synced timestamp."""
        self.last_synced_at = datetime.now(timezone.utc)
    
    def mark_drift(self, details: List[str]) -> None:
        """Mark that drift has been detected."""
        self.management_status = ManagementStatus.DRIFT_DETECTED
        self.external_modifications_detected = True
        self.drift_details = details


class RoleState(ManagedResource):
    """State tracking for roles."""
    
    role_definition: Dict[str, Any] = Field(default_factory=dict)
    assigned_groups: List[str] = Field(default_factory=list)
    assigned_projects: List[str] = Field(default_factory=list)
    acl_ids: List[str] = Field(default_factory=list)


class ACLState(ManagedResource):
    """State tracking for ACLs."""
    
    group_id: str
    group_name: str
    role_id: str
    role_name: str
    project_id: str
    project_name: str
    permissions: List[str] = Field(default_factory=list)
    
    # Track the assignment rule that created this
    assignment_rule: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None


class ProjectState(BaseModel):
    """Lightweight project tracking (projects are external)."""
    
    project_id: str
    project_name: str
    braintrust_org: str
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Track which ACLs we've applied
    managed_acl_ids: List[str] = Field(default_factory=list)
    
    # Pattern matches (for debugging)
    matched_patterns: List[str] = Field(default_factory=list)


class DriftWarning(BaseModel):
    """Warning about detected drift."""
    
    resource_type: ResourceType
    resource_id: str
    resource_name: Optional[str] = None
    drift_type: str  # "modified", "deleted", "permission_changed"
    details: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Suggested action
    suggested_action: Optional[str] = None
    severity: str = "warning"  # warning, error, info


class EnhancedSyncState(BaseModel):
    """Enhanced sync state with comprehensive resource tracking."""
    
    # Existing fields (backward compatible)
    sync_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: str = "in_progress"
    
    # Legacy mappings (keep for compatibility)
    resource_mappings: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Enhanced resource tracking
    managed_resources: Dict[str, ManagedResource] = Field(default_factory=dict)
    managed_roles: Dict[str, RoleState] = Field(default_factory=dict)
    managed_acls: Dict[str, ACLState] = Field(default_factory=dict)
    discovered_projects: Dict[str, ProjectState] = Field(default_factory=dict)
    
    # Drift detection
    drift_warnings: List[DriftWarning] = Field(default_factory=list)
    last_drift_check: Optional[datetime] = None
    
    # Statistics
    stats: Dict[str, Any] = Field(default_factory=dict)
    
    # Configuration snapshot
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    config_version: Optional[str] = None
    
    def add_managed_resource(
        self,
        resource_id: str,
        resource_type: ResourceType,
        braintrust_org: str,
        created_by_sync: bool = False,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ManagedResource:
        """Add or update a managed resource."""
        resource_key = f"{resource_type}:{resource_id}:{braintrust_org}"
        
        if resource_key in self.managed_resources:
            # Update existing
            resource = self.managed_resources[resource_key]
            resource.update_sync_time()
            if config:
                resource.config_hash = resource.calculate_config_hash(config)
        else:
            # Create new
            resource = ManagedResource(
                resource_id=resource_id,
                resource_type=resource_type,
                braintrust_org=braintrust_org,
                created_by_sync=created_by_sync,
                management_status=ManagementStatus.SYNC_MANAGED if created_by_sync else ManagementStatus.SYNC_MODIFIED,
                **kwargs
            )
            if config:
                resource.config_hash = resource.calculate_config_hash(config)
            
            self.managed_resources[resource_key] = resource
        
        return resource
    
    def add_role_state(
        self,
        role_id: str,
        role_name: str,
        braintrust_org: str,
        role_definition: Dict[str, Any],
        created_by_sync: bool = False
    ) -> RoleState:
        """Add or update role state."""
        role_key = f"{role_id}:{braintrust_org}"
        
        if role_key in self.managed_roles:
            role = self.managed_roles[role_key]
            role.update_sync_time()
            role.role_definition = role_definition
        else:
            role = RoleState(
                resource_id=role_id,
                resource_type=ResourceType.ROLE,
                resource_name=role_name,
                braintrust_org=braintrust_org,
                created_by_sync=created_by_sync,
                management_status=ManagementStatus.SYNC_MANAGED if created_by_sync else ManagementStatus.SYNC_MODIFIED,
                role_definition=role_definition,
                config_hash=hashlib.sha256(
                    json.dumps(role_definition, sort_keys=True).encode()
                ).hexdigest()[:16]
            )
            self.managed_roles[role_key] = role
        
        return role
    
    def add_acl_state(
        self,
        acl_id: str,
        group_id: str,
        group_name: str,
        role_id: str,
        role_name: str,
        project_id: str,
        project_name: str,
        braintrust_org: str,
        permissions: List[str],
        assignment_rule: Optional[Dict[str, Any]] = None,
        created_by_sync: bool = True
    ) -> ACLState:
        """Add or update ACL state."""
        acl_key = f"{acl_id}:{braintrust_org}"
        
        if acl_key in self.managed_acls:
            acl = self.managed_acls[acl_key]
            acl.update_sync_time()
            acl.permissions = permissions
        else:
            acl = ACLState(
                resource_id=acl_id,
                resource_type=ResourceType.ACL,
                resource_name=f"{group_name}:{role_name}:{project_name}",
                braintrust_org=braintrust_org,
                group_id=group_id,
                group_name=group_name,
                role_id=role_id,
                role_name=role_name,
                project_id=project_id,
                project_name=project_name,
                permissions=permissions,
                assignment_rule=assignment_rule,
                created_by_sync=created_by_sync,
                management_status=ManagementStatus.SYNC_MANAGED if created_by_sync else ManagementStatus.SYNC_MODIFIED
            )
            self.managed_acls[acl_key] = acl
            
            # Update role's ACL list
            role_key = f"{role_id}:{braintrust_org}"
            if role_key in self.managed_roles:
                if acl_id not in self.managed_roles[role_key].acl_ids:
                    self.managed_roles[role_key].acl_ids.append(acl_id)
        
        return acl
    
    def track_project(
        self,
        project_id: str,
        project_name: str,
        braintrust_org: str,
        matched_patterns: Optional[List[str]] = None
    ) -> ProjectState:
        """Track a discovered project."""
        project_key = f"{project_id}:{braintrust_org}"
        
        if project_key in self.discovered_projects:
            project = self.discovered_projects[project_key]
            project.last_seen_at = datetime.now(timezone.utc)
            if matched_patterns:
                project.matched_patterns = matched_patterns
        else:
            project = ProjectState(
                project_id=project_id,
                project_name=project_name,
                braintrust_org=braintrust_org,
                matched_patterns=matched_patterns or []
            )
            self.discovered_projects[project_key] = project
        
        return project
    
    def add_drift_warning(
        self,
        resource_type: ResourceType,
        resource_id: str,
        drift_type: str,
        details: str,
        resource_name: Optional[str] = None,
        severity: str = "warning"
    ) -> None:
        """Add a drift warning."""
        warning = DriftWarning(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            drift_type=drift_type,
            details=details,
            severity=severity
        )
        self.drift_warnings.append(warning)
        
        # Update resource if tracked
        resource_key = f"{resource_type}:{resource_id}:{self.sync_id}"
        if resource_key in self.managed_resources:
            self.managed_resources[resource_key].mark_drift([details])
    
    def detect_drift(
        self,
        current_roles: List[Dict[str, Any]],
        current_acls: List[Dict[str, Any]],
        braintrust_org: str
    ) -> List[DriftWarning]:
        """Detect drift between managed state and current state."""
        warnings = []
        
        # Check managed roles
        for role_key, role_state in self.managed_roles.items():
            if not role_state.braintrust_org == braintrust_org:
                continue
                
            # Find current role
            current_role = next(
                (r for r in current_roles if r.get("id") == role_state.resource_id),
                None
            )
            
            if not current_role:
                if role_state.created_by_sync:
                    warnings.append(DriftWarning(
                        resource_type=ResourceType.ROLE,
                        resource_id=role_state.resource_id,
                        resource_name=role_state.resource_name,
                        drift_type="deleted",
                        details=f"Managed role '{role_state.resource_name}' was deleted externally",
                        severity="error"
                    ))
            else:
                # Check for modifications
                current_hash = hashlib.sha256(
                    json.dumps(current_role.get("member_permissions", []), sort_keys=True).encode()
                ).hexdigest()[:16]
                
                if current_hash != role_state.config_hash:
                    warnings.append(DriftWarning(
                        resource_type=ResourceType.ROLE,
                        resource_id=role_state.resource_id,
                        resource_name=role_state.resource_name,
                        drift_type="modified",
                        details=f"Role '{role_state.resource_name}' permissions were modified externally",
                        severity="warning"
                    ))
        
        # Check managed ACLs
        for acl_key, acl_state in self.managed_acls.items():
            if not acl_state.braintrust_org == braintrust_org:
                continue
                
            # Find current ACL
            current_acl = next(
                (a for a in current_acls if a.get("id") == acl_state.resource_id),
                None
            )
            
            if not current_acl:
                if acl_state.created_by_sync:
                    warnings.append(DriftWarning(
                        resource_type=ResourceType.ACL,
                        resource_id=acl_state.resource_id,
                        resource_name=acl_state.resource_name,
                        drift_type="deleted",
                        details=f"Managed ACL for '{acl_state.group_name}' on '{acl_state.project_name}' was deleted",
                        severity="warning"
                    ))
            else:
                # Check for permission changes
                current_perms = set(current_acl.get("permissions", []))
                expected_perms = set(acl_state.permissions)
                
                if current_perms != expected_perms:
                    warnings.append(DriftWarning(
                        resource_type=ResourceType.ACL,
                        resource_id=acl_state.resource_id,
                        resource_name=acl_state.resource_name,
                        drift_type="permission_changed",
                        details=f"ACL permissions changed. Expected: {expected_perms}, Found: {current_perms}",
                        severity="warning"
                    ))
        
        self.drift_warnings.extend(warnings)
        self.last_drift_check = datetime.now(timezone.utc)
        
        return warnings
    
    def get_managed_resource_summary(self) -> Dict[str, Any]:
        """Get summary of managed resources."""
        return {
            "total_managed_resources": len(self.managed_resources),
            "managed_roles": len(self.managed_roles),
            "managed_acls": len(self.managed_acls),
            "discovered_projects": len(self.discovered_projects),
            "drift_warnings": len(self.drift_warnings),
            "resources_with_drift": len([
                r for r in self.managed_resources.values()
                if r.external_modifications_detected
            ]),
            "last_drift_check": self.last_drift_check.isoformat() if self.last_drift_check else None
        }
    
    def cleanup_stale_resources(self, max_age_days: int = 30) -> int:
        """Remove resources not seen in recent syncs."""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
        removed_count = 0
        
        # Clean up old managed resources
        for key in list(self.managed_resources.keys()):
            resource = self.managed_resources[key]
            if resource.last_synced_at.timestamp() < cutoff_time:
                del self.managed_resources[key]
                removed_count += 1
        
        # Clean up old projects
        for key in list(self.discovered_projects.keys()):
            project = self.discovered_projects[key]
            if project.last_seen_at.timestamp() < cutoff_time:
                del self.discovered_projects[key]
                removed_count += 1
        
        return removed_count