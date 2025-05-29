"""Configuration models and environment variable parsing for Braintrust migration tool."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl, field_validator

# Load environment variables from .env file if it exists
load_dotenv()


class BraintrustOrgConfig(BaseModel):
    """Configuration for a Braintrust organization."""

    api_key: str = Field(..., description="Braintrust API key")
    url: HttpUrl = Field(
        default="https://api.braintrust.dev", description="Braintrust API base URL"
    )

    @field_validator("api_key")
    def validate_api_key(cls, v: str) -> str:
        """Validate that API key is not empty."""
        if not v or v.strip() == "":
            raise ValueError("API key cannot be empty")
        return v.strip()


class MigrationConfig(BaseModel):
    """Configuration for migration behavior."""

    batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of items to process in each batch",
    )
    retry_attempts: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of retry attempts for failed operations",
    )
    retry_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=30.0,
        description="Initial delay between retries in seconds",
    )
    max_concurrent: int = Field(
        default=10, ge=1, le=50, description="Maximum number of concurrent operations"
    )
    checkpoint_interval: int = Field(
        default=50, ge=1, description="Write checkpoint every N successful operations"
    )


class LoggingConfig(BaseModel):
    """Configuration for structured logging."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json or text)")

    @field_validator("level")
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v.upper()

    @field_validator("format")
    def validate_log_format(cls, v: str) -> str:
        """Validate log format."""
        if v.lower() not in {"json", "text"}:
            raise ValueError("Log format must be 'json' or 'text'")
        return v.lower()


class Config(BaseModel):
    """Main configuration class for the Braintrust migration tool."""

    source: BraintrustOrgConfig
    destination: BraintrustOrgConfig
    migration: MigrationConfig = Field(default_factory=MigrationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    state_dir: Path = Field(
        default=Path("./checkpoints"),
        description="Directory for storing migration state and checkpoints",
    )
    resources: list[str] = Field(
        default=["all"], description="List of resources to migrate"
    )
    project_names: list[str] | None = Field(
        default=None,
        description="List of project names to migrate (if None, migrate all projects)",
    )

    class Config:
        """Pydantic config."""

        validate_assignment = True
        use_enum_values = True

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables.

        Returns:
            Config instance populated from environment variables.

        Raises:
            ValueError: If required environment variables are missing.
        """
        # Required environment variables
        source_api_key = os.getenv("BT_SOURCE_API_KEY")
        dest_api_key = os.getenv("BT_DEST_API_KEY")

        if not source_api_key:
            raise ValueError("BT_SOURCE_API_KEY environment variable is required")
        if not dest_api_key:
            raise ValueError("BT_DEST_API_KEY environment variable is required")

        # Optional environment variables with defaults
        source_url = os.getenv("BT_SOURCE_URL", "https://api.braintrust.dev")
        dest_url = os.getenv("BT_DEST_URL", "https://api.braintrust.dev")

        # Migration settings
        batch_size = int(os.getenv("MIGRATION_BATCH_SIZE", "100"))
        retry_attempts = int(os.getenv("MIGRATION_RETRY_ATTEMPTS", "3"))
        retry_delay = float(os.getenv("MIGRATION_RETRY_DELAY", "1.0"))
        max_concurrent = int(os.getenv("MIGRATION_MAX_CONCURRENT", "10"))
        checkpoint_interval = int(os.getenv("MIGRATION_CHECKPOINT_INTERVAL", "50"))

        # Logging settings
        log_level = os.getenv("LOG_LEVEL", "INFO")
        log_format = os.getenv("LOG_FORMAT", "json")

        # State directory
        state_dir = Path(os.getenv("MIGRATION_STATE_DIR", "./checkpoints"))

        return cls(
            source=BraintrustOrgConfig(
                api_key=source_api_key,
                url=source_url,
            ),
            destination=BraintrustOrgConfig(
                api_key=dest_api_key,
                url=dest_url,
            ),
            migration=MigrationConfig(
                batch_size=batch_size,
                retry_attempts=retry_attempts,
                retry_delay=retry_delay,
                max_concurrent=max_concurrent,
                checkpoint_interval=checkpoint_interval,
            ),
            logging=LoggingConfig(
                level=log_level,
                format=log_format,
            ),
            state_dir=state_dir,
        )

    @classmethod
    def from_file(cls, config_path: Path) -> "Config":
        """Create configuration from a YAML or JSON file.

        Args:
            config_path: Path to the configuration file

        Returns:
            Config instance populated from the file

        Raises:
            ValueError: If the file format is unsupported or required fields are missing
            FileNotFoundError: If the configuration file doesn't exist
        """
        import json

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        file_extension = config_path.suffix.lower()

        try:
            if file_extension == ".json":
                with open(config_path) as f:
                    config_data = json.load(f)
            elif file_extension in [".yaml", ".yml"]:
                try:
                    import yaml
                except ImportError:
                    raise ValueError(
                        "PyYAML is required to load YAML configuration files. Install with: pip install PyYAML"
                    ) from None

                with open(config_path) as f:
                    config_data = yaml.safe_load(f)
            else:
                raise ValueError(
                    f"Unsupported configuration file format: {file_extension}. Supported formats: .json, .yaml, .yml"
                )

            # Validate and create Config instance
            return cls(**config_data)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to load configuration file: {e}") from e

    def get_checkpoint_dir(self, project_name: str | None = None) -> Path:
        """Get the checkpoint directory for a specific project or general use.

        Args:
            project_name: Optional project name for project-specific checkpoints.

        Returns:
            Path to the checkpoint directory.
        """
        if project_name:
            return self.state_dir / project_name
        return self.state_dir

    def ensure_checkpoint_dir(self, project_name: str | None = None) -> Path:
        """Ensure checkpoint directory exists and return the path.

        Args:
            project_name: Optional project name for project-specific checkpoints.

        Returns:
            Path to the checkpoint directory.
        """
        checkpoint_dir = self.get_checkpoint_dir(project_name)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        return checkpoint_dir
