"""Enhanced state management with drift detection and managed resource tracking."""

import hashlib
import json
import time
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
    
    def update_stats(self, stats_dict: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """Update statistics for the sync state.
        
        Args:
            stats_dict: Dictionary of statistics to update (optional)
            **kwargs: Additional statistics to update as keyword arguments
        """
        # Handle both dict argument and kwargs
        if stats_dict:
            self.stats.update(stats_dict)
            # Check status in the provided dict
            if stats_dict.get('status') == 'completed':
                self.completed_at = datetime.now(timezone.utc)
                self.status = 'completed'
            elif stats_dict.get('status') == 'failed':
                self.completed_at = datetime.now(timezone.utc)
                self.status = 'failed'
        
        # Also handle kwargs
        if kwargs:
            self.stats.update(kwargs)
            # Check status in kwargs
            if kwargs.get('status') == 'completed':
                self.completed_at = datetime.now(timezone.utc)
                self.status = 'completed'
            elif kwargs.get('status') == 'failed':
                self.completed_at = datetime.now(timezone.utc)
                self.status = 'failed'
    
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
    
    def get_braintrust_id(self, okta_resource_id: str, braintrust_org: str, resource_type: str) -> Optional[str]:
        """Get Braintrust ID for an Okta resource (legacy compatibility method).
        
        Args:
            okta_resource_id: Okta resource ID
            braintrust_org: Braintrust organization 
            resource_type: Type of resource (user, group, etc.)
            
        Returns:
            Braintrust ID if mapping exists, None otherwise
        """
        # Check legacy mappings first for backward compatibility
        if braintrust_org in self.resource_mappings:
            if resource_type in self.resource_mappings[braintrust_org]:
                for mapping in self.resource_mappings[braintrust_org][resource_type]:
                    if mapping.get('okta_id') == okta_resource_id:
                        return mapping.get('braintrust_id')
        
        # Check enhanced managed resources
        for resource in self.managed_resources.values():
            if (resource.resource_type.value == resource_type and 
                resource.braintrust_org == braintrust_org):
                # Check if this resource was created from the Okta resource
                # Use a simple mapping approach - store okta_id in resource metadata
                resource_name = getattr(resource, 'resource_name', None)
                if resource_name == okta_resource_id:
                    return resource.resource_id
        
        return None
    
    def add_mapping(self, okta_id: str, braintrust_id: str, braintrust_org: str, resource_type: str, **kwargs) -> None:
        """Add resource mapping for tracking Okta to Braintrust relationships (legacy compatibility method).
        
        Args:
            okta_id: Okta resource ID
            braintrust_id: Braintrust resource ID
            braintrust_org: Braintrust organization name
            resource_type: Type of resource (user, group, etc.)
            **kwargs: Additional mapping metadata
        """
        # Initialize org mappings if needed
        if braintrust_org not in self.resource_mappings:
            self.resource_mappings[braintrust_org] = {}
        
        if resource_type not in self.resource_mappings[braintrust_org]:
            self.resource_mappings[braintrust_org][resource_type] = []
        
        # Add mapping
        mapping = {
            'okta_id': okta_id,
            'braintrust_id': braintrust_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
            **kwargs
        }
        
        # Check if mapping already exists and update it
        existing_mapping = None
        for i, existing in enumerate(self.resource_mappings[braintrust_org][resource_type]):
            if existing.get('okta_id') == okta_id:
                existing_mapping = i
                break
        
        if existing_mapping is not None:
            self.resource_mappings[braintrust_org][resource_type][existing_mapping] = mapping
        else:
            self.resource_mappings[braintrust_org][resource_type].append(mapping)
    
    def mark_failed(self, resource_id: str, resource_type: str, error_message: str) -> None:
        """Mark a resource operation as failed (legacy compatibility method).
        
        Args:
            resource_id: Resource ID that failed
            resource_type: Type of resource
            error_message: Error message
        """
        # Update stats to track failures
        if 'failed_operations' not in self.stats:
            self.stats['failed_operations'] = []
        
        failure_record = {
            'resource_id': resource_id,
            'resource_type': resource_type,
            'error_message': error_message,
            'failed_at': datetime.now(timezone.utc).isoformat()
        }
        
        self.stats['failed_operations'].append(failure_record)
        
        # Update failure counts
        failure_key = f'failed_{resource_type}s'
        self.stats[failure_key] = self.stats.get(failure_key, 0) + 1
    
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
    
    def mark_completed(self) -> None:
        """Mark the sync state as completed."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error_message: str) -> None:
        """Mark the sync state as failed.
        
        Args:
            error_message: Error message describing the failure
        """
        self.status = "failed"
        self.completed_at = datetime.now(timezone.utc)
        if 'error_message' not in self.stats:
            self.stats['error_message'] = error_message


class StateManager:
    """Manages enhanced sync state with resource tracking and drift detection."""
    
    def __init__(
        self, 
        state_dir: Path = Path("./state"),
    ) -> None:
        """Initialize state manager.
        
        Args:
            state_dir: Directory to store state files
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self._current_state: Optional[EnhancedSyncState] = None
        self._logger = logger.bind(state_dir=str(self.state_dir))
    
    def create_sync_state(
        self,
        sync_id: Optional[str] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> EnhancedSyncState:
        """Create a new enhanced sync state.
        
        Args:
            sync_id: Optional sync ID (generates timestamp-based if not provided)
            config_snapshot: Configuration snapshot for this sync
            
        Returns:
            New EnhancedSyncState instance
        """
        if sync_id is None:
            sync_id = f"sync_{int(time.time())}"
        
        # Create enhanced state
        self._current_state = EnhancedSyncState(
            sync_id=sync_id,
            config_snapshot=config_snapshot or {},
        )
        
        self._logger.info(
            "Created new enhanced sync state", 
            sync_id=sync_id,
        )
        return self._current_state
    
    def get_current_state(self) -> Optional[EnhancedSyncState]:
        """Get current enhanced sync state.
        
        Returns:
            Current EnhancedSyncState instance or None
        """
        return self._current_state
    
    def load_sync_state(self, sync_id: str) -> Optional[EnhancedSyncState]:
        """Load enhanced sync state from disk.
        
        Args:
            sync_id: Sync ID to load
            
        Returns:
            Loaded EnhancedSyncState instance or None if not found
        """
        state_file = self.state_dir / f"{sync_id}.json"
        
        if not state_file.exists():
            self._logger.warning("Sync state file not found", sync_id=sync_id, file=str(state_file))
            return None
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            self._current_state = EnhancedSyncState.model_validate(state_data)
            
            self._logger.info(
                "Loaded enhanced sync state", 
                sync_id=sync_id,
                managed_resources=len(self._current_state.managed_resources),
                managed_roles=len(self._current_state.managed_roles),
                managed_acls=len(self._current_state.managed_acls),
                drift_warnings=len(self._current_state.drift_warnings),
            )
            return self._current_state
            
        except Exception as e:
            self._logger.error("Failed to load sync state", sync_id=sync_id, error=str(e))
            return None
    
    def save_sync_state(self, state: Optional[EnhancedSyncState] = None) -> bool:
        """Save enhanced sync state to disk.
        
        Args:
            state: State to save (uses current state if not provided)
            
        Returns:
            True if saved successfully, False otherwise
        """
        if state is None:
            state = self._current_state
        
        if state is None:
            self._logger.error("No sync state to save")
            return False
        
        state_file = self.state_dir / f"{state.sync_id}.json"
        
        try:
            # Create backup of existing file
            if state_file.exists():
                backup_file = state_file.with_suffix('.json.backup')
                state_file.rename(backup_file)
            
            # Save enhanced state
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(
                    state.model_dump(mode='json'),
                    f,
                    indent=2,
                    default=str,  # Handle datetime serialization
                )
            
            self._logger.debug(
                "Saved enhanced sync state", 
                sync_id=state.sync_id, 
                file=str(state_file),
                managed_resources=len(state.managed_resources),
                managed_roles=len(state.managed_roles),
                managed_acls=len(state.managed_acls),
            )
            return True
            
        except Exception as e:
            self._logger.error("Failed to save sync state", sync_id=state.sync_id, error=str(e))
            return False
    
    def list_sync_states(self) -> List[str]:
        """List all available sync state IDs.
        
        Returns:
            List of sync IDs
        """
        try:
            sync_files = list(self.state_dir.glob("sync_*.json"))
            sync_ids = [f.stem for f in sync_files]
            return sorted(sync_ids)
        except Exception as e:
            self._logger.error("Failed to list sync states", error=str(e))
            return []
    
    def cleanup_old_states(self, keep_count: int = 10) -> int:
        """Clean up old sync states, keeping only the most recent ones.
        
        Args:
            keep_count: Number of recent states to keep
            
        Returns:
            Number of states cleaned up
        """
        try:
            sync_files = list(self.state_dir.glob("sync_*.json"))
            
            # Sort by modification time (newest first)
            sync_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # Remove old files
            cleaned_count = 0
            for old_file in sync_files[keep_count:]:
                old_file.unlink()
                # Also remove backup if it exists
                backup_file = old_file.with_suffix('.json.backup')
                if backup_file.exists():
                    backup_file.unlink()
                cleaned_count += 1
            
            if cleaned_count > 0:
                self._logger.info("Cleaned up old sync states", count=cleaned_count)
            
            return cleaned_count
            
        except Exception as e:
            self._logger.error("Failed to cleanup old states", error=str(e))
            return 0
    
    def get_latest_sync_state(self) -> Optional[EnhancedSyncState]:
        """Get the most recent sync state.
        
        Returns:
            Latest EnhancedSyncState instance or None
        """
        sync_ids = self.list_sync_states()
        if not sync_ids:
            return None
        
        # Sync IDs are timestamp-based, so the last one is most recent
        latest_sync_id = sync_ids[-1]
        return self.load_sync_state(latest_sync_id)
    
    def create_checkpoint(self, checkpoint_name: str = "checkpoint") -> bool:
        """Create a checkpoint of the current state.
        
        Args:
            checkpoint_name: Name for the checkpoint
            
        Returns:
            True if checkpoint created successfully
        """
        if self._current_state is None:
            return False
        
        checkpoint_file = self.state_dir / f"{self._current_state.sync_id}_{checkpoint_name}.json"
        
        try:
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(
                    self._current_state.model_dump(mode='json'),
                    f,
                    indent=2,
                    default=str,
                )
            
            self._logger.info(
                "Created checkpoint",
                sync_id=self._current_state.sync_id,
                checkpoint=checkpoint_name,
            )
            return True
            
        except Exception as e:
            self._logger.error("Failed to create checkpoint", error=str(e))
            return False
    
    def track_managed_resource(
        self,
        resource_id: str,
        resource_type: ResourceType,
        braintrust_org: str,
        created_by_sync: bool = False,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Optional[ManagedResource]:
        """Track a managed resource in enhanced state.
        
        Args:
            resource_id: Unique resource ID
            resource_type: Type of resource
            braintrust_org: Braintrust organization
            created_by_sync: Whether resource was created by sync
            config: Configuration that created this resource
            **kwargs: Additional resource metadata
            
        Returns:
            ManagedResource instance
        """
        if not self._current_state:
            return None
        
        return self._current_state.add_managed_resource(
            resource_id=resource_id,
            resource_type=resource_type,
            braintrust_org=braintrust_org,
            created_by_sync=created_by_sync,
            config=config,
            **kwargs
        )
    
    def track_role_state(
        self,
        role_id: str,
        role_name: str,
        braintrust_org: str,
        role_definition: Dict[str, Any],
        created_by_sync: bool = False,
    ) -> Optional[RoleState]:
        """Track role state in enhanced tracking.
        
        Args:
            role_id: Role ID
            role_name: Role name
            braintrust_org: Braintrust organization
            role_definition: Role definition
            created_by_sync: Whether role was created by sync
            
        Returns:
            RoleState instance
        """
        if not self._current_state:
            return None
        
        return self._current_state.add_role_state(
            role_id=role_id,
            role_name=role_name,
            braintrust_org=braintrust_org,
            role_definition=role_definition,
            created_by_sync=created_by_sync,
        )
    
    def track_acl_state(
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
        created_by_sync: bool = True,
    ) -> Optional[ACLState]:
        """Track ACL state in enhanced tracking.
        
        Args:
            acl_id: ACL ID
            group_id: Group ID
            group_name: Group name
            role_id: Role ID
            role_name: Role name
            project_id: Project ID
            project_name: Project name
            braintrust_org: Braintrust organization
            permissions: List of permissions
            assignment_rule: Assignment rule that created this ACL
            created_by_sync: Whether ACL was created by sync
            
        Returns:
            ACLState instance
        """
        if not self._current_state:
            return None
        
        return self._current_state.add_acl_state(
            acl_id=acl_id,
            group_id=group_id,
            group_name=group_name,
            role_id=role_id,
            role_name=role_name,
            project_id=project_id,
            project_name=project_name,
            braintrust_org=braintrust_org,
            permissions=permissions,
            assignment_rule=assignment_rule,
            created_by_sync=created_by_sync,
        )
    
    def track_project(
        self,
        project_id: str,
        project_name: str,
        braintrust_org: str,
        matched_patterns: Optional[List[str]] = None,
    ) -> Optional[ProjectState]:
        """Track discovered project in enhanced tracking.
        
        Args:
            project_id: Project ID
            project_name: Project name
            braintrust_org: Braintrust organization
            matched_patterns: Patterns that matched this project
            
        Returns:
            ProjectState instance
        """
        if not self._current_state:
            return None
        
        return self._current_state.track_project(
            project_id=project_id,
            project_name=project_name,
            braintrust_org=braintrust_org,
            matched_patterns=matched_patterns,
        )
    
    def detect_drift(
        self,
        current_roles: List[Dict[str, Any]],
        current_acls: List[Dict[str, Any]],
        braintrust_org: str,
    ) -> List[DriftWarning]:
        """Detect drift between managed state and current state.
        
        Args:
            current_roles: Current roles from Braintrust API
            current_acls: Current ACLs from Braintrust API
            braintrust_org: Braintrust organization
            
        Returns:
            List of drift warnings
        """
        if not self._current_state:
            return []
        
        return self._current_state.detect_drift(
            current_roles=current_roles,
            current_acls=current_acls,
            braintrust_org=braintrust_org,
        )
    
    def get_managed_resource_summary(self) -> Dict[str, Any]:
        """Get summary of managed resources.
        
        Returns:
            Summary dictionary
        """
        if not self._current_state:
            return {"no_current_state": True}
        
        return self._current_state.get_managed_resource_summary()
    
    def cleanup_stale_resources(self, max_age_days: int = 30) -> int:
        """Remove stale resources from enhanced state.
        
        Args:
            max_age_days: Maximum age for resources
            
        Returns:
            Number of resources cleaned up
        """
        if not self._current_state:
            return 0
        
        return self._current_state.cleanup_stale_resources(max_age_days)
    
    def get_braintrust_id(self, okta_resource_id: str, resource_type: str) -> Optional[str]:
        """Get Braintrust ID for an Okta resource.
        
        Args:
            okta_resource_id: Okta resource ID
            resource_type: Type of resource (user, group, etc.)
            
        Returns:
            Braintrust ID if mapping exists, None otherwise
        """
        if not self._current_state:
            return None
        
        # Check legacy mappings first for backward compatibility
        for org_mappings in self._current_state.resource_mappings.values():
            if resource_type in org_mappings:
                for mapping in org_mappings[resource_type]:
                    if mapping.get('okta_id') == okta_resource_id:
                        return mapping.get('braintrust_id')
        
        # Check enhanced managed resources
        for resource in self._current_state.managed_resources.values():
            if resource.resource_type.value == resource_type:
                # Check if this resource was created from the Okta resource
                # Use a simple mapping approach - store okta_id in resource metadata
                resource_name = getattr(resource, 'resource_name', None)
                if resource_name == okta_resource_id:
                    return resource.resource_id
        
        return None
    
    def add_mapping(self, org_name: str, resource_type: str, okta_id: str, braintrust_id: str, **kwargs) -> None:
        """Add resource mapping for tracking Okta to Braintrust relationships.
        
        Args:
            org_name: Braintrust organization name
            resource_type: Type of resource (user, group, etc.)
            okta_id: Okta resource ID
            braintrust_id: Braintrust resource ID
            **kwargs: Additional mapping metadata
        """
        if not self._current_state:
            return
        
        # Initialize org mappings if needed
        if org_name not in self._current_state.resource_mappings:
            self._current_state.resource_mappings[org_name] = {}
        
        if resource_type not in self._current_state.resource_mappings[org_name]:
            self._current_state.resource_mappings[org_name][resource_type] = []
        
        # Add mapping
        mapping = {
            'okta_id': okta_id,
            'braintrust_id': braintrust_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
            **kwargs
        }
        
        # Check if mapping already exists and update it
        existing_mapping = None
        for i, existing in enumerate(self._current_state.resource_mappings[org_name][resource_type]):
            if existing.get('okta_id') == okta_id:
                existing_mapping = i
                break
        
        if existing_mapping is not None:
            self._current_state.resource_mappings[org_name][resource_type][existing_mapping] = mapping
        else:
            self._current_state.resource_mappings[org_name][resource_type].append(mapping)
    
    def mark_failed(self, resource_id: str, resource_type: str, error_message: str) -> None:
        """Mark a resource operation as failed.
        
        Args:
            resource_id: Resource ID that failed
            resource_type: Type of resource
            error_message: Error message
        """
        if not self._current_state:
            return
        
        # Update stats to track failures
        if 'failed_operations' not in self._current_state.stats:
            self._current_state.stats['failed_operations'] = []
        
        failure_record = {
            'resource_id': resource_id,
            'resource_type': resource_type,
            'error_message': error_message,
            'failed_at': datetime.now(timezone.utc).isoformat()
        }
        
        self._current_state.stats['failed_operations'].append(failure_record)
        
        # Update failure counts
        failure_key = f'failed_{resource_type}s'
        self._current_state.stats[failure_key] = self._current_state.stats.get(failure_key, 0) + 1