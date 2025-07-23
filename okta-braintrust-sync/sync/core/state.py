"""State management for sync operations with checkpointing and ID mapping."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class ResourceMapping(BaseModel):
    """Resource ID mapping between Okta and Braintrust."""
    
    okta_id: str
    braintrust_id: str 
    braintrust_org: str
    resource_type: str  # "user" or "group"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)


class SyncOperation(BaseModel):
    """Record of a sync operation."""
    
    operation_id: str
    operation_type: str  # "create", "update", "skip", "error"
    resource_type: str   # "user", "group"
    okta_id: str
    braintrust_id: Optional[str] = None
    braintrust_org: str
    status: str  # "pending", "in_progress", "completed", "failed"
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    
    def mark_completed(self, braintrust_id: Optional[str] = None) -> None:
        """Mark operation as completed."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        if braintrust_id:
            self.braintrust_id = braintrust_id
    
    def mark_failed(self, error_message: str) -> None:
        """Mark operation as failed."""
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = datetime.now(timezone.utc)


class SyncState(BaseModel):
    """Comprehensive sync state with checkpointing."""
    
    sync_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: str = "in_progress"  # "in_progress", "completed", "failed"
    
    # Resource mappings - persistent across syncs
    resource_mappings: Dict[str, ResourceMapping] = Field(default_factory=dict)
    
    # Current sync operations
    operations: Dict[str, SyncOperation] = Field(default_factory=dict)
    
    # Statistics
    stats: Dict[str, Any] = Field(default_factory=dict)
    
    # Configuration snapshot
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    
    def add_mapping(
        self,
        okta_id: str,
        braintrust_id: str,
        braintrust_org: str,
        resource_type: str,
    ) -> None:
        """Add or update a resource mapping."""
        mapping_key = f"{okta_id}:{braintrust_org}:{resource_type}"
        
        if mapping_key in self.resource_mappings:
            # Update existing mapping
            mapping = self.resource_mappings[mapping_key]
            mapping.braintrust_id = braintrust_id
            mapping.update_timestamp()
        else:
            # Create new mapping
            self.resource_mappings[mapping_key] = ResourceMapping(
                okta_id=okta_id,
                braintrust_id=braintrust_id,
                braintrust_org=braintrust_org,
                resource_type=resource_type,
            )
    
    def get_mapping(
        self,
        okta_id: str,
        braintrust_org: str,
        resource_type: str,
    ) -> Optional[ResourceMapping]:
        """Get a resource mapping."""
        mapping_key = f"{okta_id}:{braintrust_org}:{resource_type}"
        return self.resource_mappings.get(mapping_key)
    
    def get_braintrust_id(
        self,
        okta_id: str,
        braintrust_org: str,
        resource_type: str,
    ) -> Optional[str]:
        """Get Braintrust ID for an Okta resource."""
        mapping = self.get_mapping(okta_id, braintrust_org, resource_type)
        return mapping.braintrust_id if mapping else None
    
    def add_operation(self, operation: SyncOperation) -> None:
        """Add a sync operation."""
        self.operations[operation.operation_id] = operation
    
    def get_operation(self, operation_id: str) -> Optional[SyncOperation]:
        """Get a sync operation by ID."""
        return self.operations.get(operation_id)
    
    def update_stats(self, stats_update: Dict[str, Any]) -> None:
        """Update sync statistics."""
        self.stats.update(stats_update)
    
    def mark_completed(self) -> None:
        """Mark sync as completed."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error_message: str) -> None:
        """Mark sync as failed."""
        self.status = "failed"
        self.completed_at = datetime.now(timezone.utc)
        self.stats["error_message"] = error_message
    
    def get_summary(self) -> Dict[str, Any]:
        """Get sync summary statistics."""
        completed_ops = [op for op in self.operations.values() if op.status == "completed"]
        failed_ops = [op for op in self.operations.values() if op.status == "failed"]
        
        return {
            "sync_id": self.sync_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": (
                (self.completed_at or datetime.now(timezone.utc)) - self.started_at
            ).total_seconds(),
            "total_operations": len(self.operations),
            "completed_operations": len(completed_ops),
            "failed_operations": len(failed_ops),
            "total_mappings": len(self.resource_mappings),
            "stats": self.stats,
        }


class StateManager:
    """Manages sync state with persistent checkpointing."""
    
    def __init__(self, state_dir: Path = Path("./state")) -> None:
        """Initialize state manager.
        
        Args:
            state_dir: Directory to store state files
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self._current_state: Optional[SyncState] = None
        self._logger = logger.bind(state_dir=str(self.state_dir))
    
    def create_sync_state(
        self,
        sync_id: Optional[str] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> SyncState:
        """Create a new sync state.
        
        Args:
            sync_id: Optional sync ID (generates timestamp-based if not provided)
            config_snapshot: Configuration snapshot for this sync
            
        Returns:
            New SyncState instance
        """
        if sync_id is None:
            sync_id = f"sync_{int(time.time())}"
        
        # Load any existing mappings from previous syncs
        existing_mappings = self._load_persistent_mappings()
        
        self._current_state = SyncState(
            sync_id=sync_id,
            resource_mappings=existing_mappings,
            config_snapshot=config_snapshot or {},
        )
        
        self._logger.info("Created new sync state", sync_id=sync_id)
        return self._current_state
    
    def get_current_state(self) -> Optional[SyncState]:
        """Get current sync state.
        
        Returns:
            Current SyncState instance or None
        """
        return self._current_state
    
    def load_sync_state(self, sync_id: str) -> Optional[SyncState]:
        """Load sync state from disk.
        
        Args:
            sync_id: Sync ID to load
            
        Returns:
            Loaded SyncState instance or None if not found
        """
        state_file = self.state_dir / f"{sync_id}.json"
        
        if not state_file.exists():
            self._logger.warning("Sync state file not found", sync_id=sync_id, file=str(state_file))
            return None
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            self._current_state = SyncState.model_validate(state_data)
            self._logger.info("Loaded sync state", sync_id=sync_id)
            return self._current_state
            
        except Exception as e:
            self._logger.error("Failed to load sync state", sync_id=sync_id, error=str(e))
            return None
    
    def save_sync_state(self, state: Optional[SyncState] = None) -> bool:
        """Save sync state to disk.
        
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
            
            # Save new state
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(
                    state.model_dump(mode='json'),
                    f,
                    indent=2,
                    default=str,  # Handle datetime serialization
                )
            
            # Save persistent mappings separately
            self._save_persistent_mappings(state.resource_mappings)
            
            self._logger.debug("Saved sync state", sync_id=state.sync_id, file=str(state_file))
            return True
            
        except Exception as e:
            self._logger.error("Failed to save sync state", sync_id=state.sync_id, error=str(e))
            return False
    
    def _load_persistent_mappings(self) -> Dict[str, ResourceMapping]:
        """Load persistent resource mappings from previous syncs.
        
        Returns:
            Dictionary of resource mappings
        """
        mappings_file = self.state_dir / "resource_mappings.json"
        
        if not mappings_file.exists():
            return {}
        
        try:
            with open(mappings_file, 'r', encoding='utf-8') as f:
                mappings_data = json.load(f)
            
            mappings = {}
            for key, mapping_data in mappings_data.items():
                mappings[key] = ResourceMapping.model_validate(mapping_data)
            
            self._logger.debug("Loaded persistent mappings", count=len(mappings))
            return mappings
            
        except Exception as e:
            self._logger.error("Failed to load persistent mappings", error=str(e))
            return {}
    
    def _save_persistent_mappings(self, mappings: Dict[str, ResourceMapping]) -> bool:
        """Save persistent resource mappings.
        
        Args:
            mappings: Resource mappings to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        mappings_file = self.state_dir / "resource_mappings.json"
        
        try:
            # Create backup
            if mappings_file.exists():
                backup_file = mappings_file.with_suffix('.json.backup')
                mappings_file.rename(backup_file)
            
            # Save mappings
            mappings_data = {}
            for key, mapping in mappings.items():
                mappings_data[key] = mapping.model_dump(mode='json')
            
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(mappings_data, f, indent=2, default=str)
            
            self._logger.debug("Saved persistent mappings", count=len(mappings))
            return True
            
        except Exception as e:
            self._logger.error("Failed to save persistent mappings", error=str(e))
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
    
    def get_latest_sync_state(self) -> Optional[SyncState]:
        """Get the most recent sync state.
        
        Returns:
            Latest SyncState instance or None
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