"""Base configuration models and enums."""

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


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
    # Redis and database backends not implemented


class IdentityMappingStrategy(str, Enum):
    """Identity mapping strategies."""
    EMAIL = "email"
    CUSTOM_FIELD = "custom_field"
    MAPPING_FILE = "mapping_file"


# Runtime State Models (for internal use)
class SyncState(BaseModel):
    """Runtime sync state."""
    
    last_sync_time: str | None = None
    last_full_sync_time: str | None = None
    total_users_synced: int = 0
    total_groups_synced: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    is_running: bool = False
    current_operation: str | None = None


class ResourceMapping(BaseModel):
    """Resource ID mapping between Okta and Braintrust."""
    
    okta_id: str
    braintrust_id: str
    braintrust_org: str
    resource_type: Literal["user", "group"]
    created_at: str
    updated_at: str