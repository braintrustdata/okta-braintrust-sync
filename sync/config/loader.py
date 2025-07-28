"""Configuration loader with YAML parsing and environment variable substitution."""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import ValidationError

from sync.config.models import SyncConfig


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""
    pass


class EnvironmentVariableError(ConfigurationError):
    """Raised when environment variable substitution fails."""
    pass


class ConfigLoader:
    """Configuration loader with environment variable substitution."""
    
    # Pattern for environment variable substitution: ${VAR_NAME} or ${VAR_NAME:default_value}
    ENV_VAR_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*?)(?::([^}]*))?\}')
    
    def __init__(self, require_env_vars: bool = True) -> None:
        """Initialize the configuration loader.
        
        Args:
            require_env_vars: Whether to require all environment variables to exist
                            (if False, missing vars without defaults will be left as-is)
        """
        self.require_env_vars = require_env_vars
    
    def load_config(self, config_path: Path) -> SyncConfig:
        """Load and validate configuration from YAML file.
        
        Args:
            config_path: Path to the YAML configuration file
            
        Returns:
            Validated SyncConfig instance
            
        Raises:
            ConfigurationError: If loading or validation fails
        """
        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        
        try:
            # Load raw YAML content
            with open(config_path, 'r', encoding='utf-8') as f:
                raw_content = f.read()
            
            # Substitute environment variables
            substituted_content = self._substitute_env_vars(raw_content)
            
            # Parse YAML
            config_data = yaml.safe_load(substituted_content)
            
            if not isinstance(config_data, dict):
                raise ConfigurationError("Configuration file must contain a YAML object")
            
            # Validate with Pydantic
            return SyncConfig.model_validate(config_data)
            
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML syntax: {e}") from e
        except ValidationError as e:
            raise ConfigurationError(f"Configuration validation failed: {e}") from e
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}") from e
    
    def _substitute_env_vars(self, content: str) -> str:
        """Substitute environment variables in the content.
        
        Supports patterns like:
        - ${VAR_NAME} - Required environment variable
        - ${VAR_NAME:default} - Environment variable with default value
        
        Args:
            content: Raw configuration content
            
        Returns:
            Content with environment variables substituted
            
        Raises:
            EnvironmentVariableError: If required environment variable is missing
        """
        def replace_env_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2)
            
            # Get environment variable value
            env_value = os.getenv(var_name)
            
            if env_value is not None:
                return env_value
            elif default_value is not None:
                return default_value
            elif self.require_env_vars:
                raise EnvironmentVariableError(
                    f"Required environment variable '{var_name}' is not set"
                )
            else:
                # Return original placeholder if not requiring env vars
                return match.group(0)
        
        try:
            return self.ENV_VAR_PATTERN.sub(replace_env_var, content)
        except EnvironmentVariableError:
            raise
        except Exception as e:
            raise EnvironmentVariableError(f"Failed to substitute environment variables: {e}") from e
    
    def validate_config_file(self, config_path: Path) -> tuple[bool, Optional[str]]:
        """Validate configuration file without loading.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.load_config(config_path)
            return True, None
        except ConfigurationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Unexpected error: {e}"
    
    def get_missing_env_vars(self, config_path: Path) -> list[str]:
        """Get list of missing environment variables from config file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            List of missing environment variable names
        """
        if not config_path.exists():
            return []
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            missing_vars = []
            
            for match in self.ENV_VAR_PATTERN.finditer(content):
                var_name = match.group(1)
                default_value = match.group(2)
                
                # Only consider it missing if no default and not set in environment
                if default_value is None and os.getenv(var_name) is None:
                    missing_vars.append(var_name)
            
            return sorted(list(set(missing_vars)))  # Remove duplicates and sort
            
        except Exception:
            return []
    
    def generate_env_template(self, config_path: Path) -> str:
        """Generate .env template from configuration file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            .env template content with all environment variables
        """
        if not config_path.exists():
            return "# Configuration file not found\n"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            env_vars = set()
            
            for match in self.ENV_VAR_PATTERN.finditer(content):
                var_name = match.group(1)
                default_value = match.group(2)
                
                if default_value is not None:
                    env_vars.add(f"{var_name}={default_value}")
                else:
                    env_vars.add(f"{var_name}=")
            
            if not env_vars:
                return "# No environment variables found in configuration\n"
            
            # Generate template with comments
            template = "# Environment variables for okta-braintrust-sync\n"
            template += "# Generated from configuration file\n\n"
            
            for var in sorted(env_vars):
                template += f"{var}\n"
            
            return template
            
        except Exception as e:
            return f"# Error generating template: {e}\n"


def load_config_from_path(config_path: Path, require_env_vars: bool = True) -> SyncConfig:
    """Convenience function to load configuration from path.
    
    Args:
        config_path: Path to configuration file
        require_env_vars: Whether to require all environment variables
        
    Returns:
        Validated SyncConfig instance
        
    Raises:
        ConfigurationError: If loading fails
    """
    loader = ConfigLoader(require_env_vars=require_env_vars)
    return loader.load_config(config_path)


def load_config_from_dict(config_data: Dict[str, Any]) -> SyncConfig:
    """Load configuration from dictionary (for testing).
    
    Args:
        config_data: Configuration dictionary
        
    Returns:
        Validated SyncConfig instance
        
    Raises:
        ConfigurationError: If validation fails
    """
    try:
        return SyncConfig.model_validate(config_data)
    except ValidationError as e:
        raise ConfigurationError(f"Configuration validation failed: {e}") from e


def find_config_file(start_path: Optional[Path] = None) -> Optional[Path]:
    """Find configuration file by searching up directory tree.
    
    Searches for the following files in order:
    1. sync-config.yaml
    2. sync-config.yml  
    3. config.yaml
    4. config.yml
    
    Args:
        start_path: Directory to start search from (defaults to current directory)
        
    Returns:
        Path to configuration file if found, None otherwise
    """
    if start_path is None:
        start_path = Path.cwd()
    
    config_filenames = [
        "sync-config.yaml",
        "sync-config.yml",
        "config.yaml", 
        "config.yml"
    ]
    
    current_path = start_path.resolve()
    
    # Search up the directory tree
    while True:
        for filename in config_filenames:
            config_path = current_path / filename
            if config_path.exists():
                return config_path
        
        parent = current_path.parent
        if parent == current_path:  # Reached root
            break
        current_path = parent
    
    return None


# Configuration validation utilities
def validate_braintrust_org_refs(config: SyncConfig) -> list[str]:
    """Validate that all Braintrust org references exist in config.
    
    Args:
        config: Configuration to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    configured_orgs = set(config.braintrust_orgs.keys())
    
    # Check user mappings
    if config.sync_rules.users:
        for i, mapping in enumerate(config.sync_rules.users.mappings):
            for org in mapping.braintrust_orgs:
                if org not in configured_orgs:
                    errors.append(f"User mapping {i}: unknown Braintrust org '{org}'")
    
    # Check group mappings
    if config.sync_rules.groups:
        for i, mapping in enumerate(config.sync_rules.groups.mappings):
            for org in mapping.braintrust_orgs:
                if org not in configured_orgs:
                    errors.append(f"Group mapping {i}: unknown Braintrust org '{org}'")
    
    return errors


def validate_cron_expressions(config: SyncConfig) -> list[str]:
    """Validate cron expressions in configuration.
    
    Args:
        config: Configuration to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    try:
        from croniter import croniter
        
        # Check declarative mode schedules
        if config.sync_modes.declarative.enabled:
            if config.sync_modes.declarative.schedule:
                try:
                    croniter(config.sync_modes.declarative.schedule)
                except Exception as e:
                    errors.append(f"Invalid cron expression in declarative.schedule: {e}")
            
            if config.sync_modes.declarative.full_reconciliation:
                try:
                    croniter(config.sync_modes.declarative.full_reconciliation)
                except Exception as e:
                    errors.append(f"Invalid cron expression in declarative.full_reconciliation: {e}")
    
    except ImportError:
        # croniter not available, skip validation
        pass
    
    return errors