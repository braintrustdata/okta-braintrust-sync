"""Audit and state management configuration models."""

from pathlib import Path

from pydantic import BaseModel, Field

from .base_models import LogLevel, LogFormat


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
    log_file: Path | None = Field(
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


class StateManagementConfig(BaseModel):
    """State management configuration."""
    
    enable_enhanced_tracking: bool = Field(
        True,
        description="Enable enhanced state tracking"
    )
    state_directory: Path = Field(
        Path("./state"),
        description="Directory to store state files"
    )
    max_state_retention_days: int = Field(
        30,
        description="Maximum number of days to retain old state files",
        ge=1
    )
    enable_state_backup: bool = Field(
        True,
        description="Create backup copies of state files before updates"
    )
    auto_cleanup_stale_resources: bool = Field(
        False,
        description="Automatically clean up stale resources from state (use with caution)"
    )
    stale_resource_threshold_days: int = Field(
        7,
        description="Number of days before marking resources as stale",
        ge=1
    )