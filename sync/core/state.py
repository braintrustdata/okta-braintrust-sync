"""State management for sync operations with enhanced resource tracking and drift detection."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from sync.core.enhanced_state import (
    EnhancedSyncState,
    ManagedResource,
    RoleState,
    ACLState,
    ProjectState,
    DriftWarning,
    ResourceType,
    ManagementStatus,
)

logger = structlog.get_logger(__name__)


class StateManager:
    """Manages sync state with enhanced resource tracking and drift detection."""
    
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
        
        # Use enhanced state only
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