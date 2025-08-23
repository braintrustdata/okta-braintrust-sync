"""Sync mode configuration models."""

from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

from .base_models import QueueBackend


class DeclarativeModeConfig(BaseModel):
    """Declarative sync mode configuration."""
    
    enabled: bool = Field(
        True,
        description="Whether declarative mode is enabled"
    )
    schedule: str | None = Field(
        "0 */4 * * *",
        description="Cron expression for scheduled syncs (every 4 hours by default)"
    )
    full_reconciliation: str | None = Field(
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