"""Configuration loader with YAML parsing and environment variable substitution."""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Set

import yaml
from pydantic import ValidationError

from sync.config.models import SyncConfig
from sync.security.validation import (
    sanitize_log_input, validate_environment_variable_name, validate_file_path,
    validate_cron_expression
)


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""


class SecurityError(Exception):
    """Raised when security validation fails."""
    pass


class EnvironmentVariableError(ConfigurationError):
    """Raised when environment variable substitution fails."""
    pass


# Security: Allowlist of permitted environment variables
ALLOWED_ENV_VARS: Set[str] = {
    # API Credentials
    "OKTA_API_TOKEN",
    "BRAINTRUST_API_KEY",
    "BRAINTRUST_PROD_API_KEY",
    "BRAINTRUST_DEV_API_KEY",
    
    # Organization Configuration
    "BRAINTRUST_ORG_ID",
    "BRAINTRUST_ORG_NAME",
    "OKTA_DOMAIN",
    "OKTA_ORG_NAME",
    
    # Logging and Monitoring
    "LOG_LEVEL",
    "LOG_FORMAT",
    "AUDIT_LOG_FILE",
    
    # Rate Limiting
    "OKTA_RATE_LIMIT_PER_MINUTE",
    "BRAINTRUST_RATE_LIMIT_PER_MINUTE",
    
    # Sync Configuration
    "DRY_RUN",
    "BATCH_SIZE",
    "MAX_CONCURRENT_OPERATIONS",
    
    # State Management
    "STATE_DIR",
    "ENABLE_ENHANCED_TRACKING",
    "ENABLE_DRIFT_DETECTION",
    
    # Security
    "REQUIRE_HTTPS",
    "VERIFY_SSL",
    
    # Webhook Configuration
    "WEBHOOK_SECRET",
    "WEBHOOK_PORT",
    
    # Common Environment Variables
    "HOME",
    "USER",
    "PATH",
    "PWD",
    "SHELL",
    "TMPDIR",
    "TMP",
    "TEMP",
}


def _validate_env_var_name(var_name: str) -> None:
    """Validate that an environment variable is allowed.
    
    Args:
        var_name: Environment variable name to validate
        
    Raises:
        SecurityError: If the environment variable is not in the allowlist
    """
    # First validate the format of the environment variable name
    if not validate_environment_variable_name(var_name):
        raise SecurityError(
            f"Invalid environment variable name format: '{sanitize_log_input(var_name)}'. "
            "Environment variable names must contain only letters, digits, and underscores, "
            "and cannot start with a digit."
        )
    
    # Then check against allowlist
    if var_name not in ALLOWED_ENV_VARS:
        raise SecurityError(
            f"Unauthorized environment variable '{sanitize_log_input(var_name)}' is not in allowlist. "
            f"Allowed variables: {sorted(ALLOWED_ENV_VARS)}"
        )


def _sanitize_env_value(value: str) -> str:
    """Sanitize environment variable value to prevent injection attacks.
    
    Args:
        value: Raw environment variable value
        
    Returns:
        Sanitized value safe for use in configuration
    """
    # Remove any potential YAML injection characters
    sanitized = value.strip()
    
    # Prevent YAML injection by escaping special characters
    dangerous_chars = ['${', '#{', '&', '*', '!', '|', '>', "'", '"', '`']
    for char in dangerous_chars:
        if char in sanitized:
            # For now, we'll be strict and reject values with dangerous characters
            # In production, you might want to escape them instead
            raise SecurityError(
                f"Environment variable contains potentially dangerous character '{char}'. "
                "Values with special YAML characters are not allowed for security reasons."
            )
    
    return sanitized


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
        missing_vars = []
        security_errors = []
        
        def replace_env_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2)
            
            # Security: Validate environment variable name against allowlist
            try:
                _validate_env_var_name(var_name)
            except SecurityError as e:
                security_errors.append(str(e))
                return match.group(0)  # Return original placeholder
            
            # Get environment variable value
            env_value = os.getenv(var_name)
            
            if env_value is not None:
                # Security: Sanitize environment variable value
                return _sanitize_env_value(env_value)
            elif default_value is not None:
                # Security: Sanitize default value as well
                return _sanitize_env_value(default_value)
            elif self.require_env_vars:
                missing_vars.append(var_name)
                return match.group(0)  # Return original placeholder for now
            else:
                # Return original placeholder if not requiring env vars
                return match.group(0)
        
        try:
            result = self.ENV_VAR_PATTERN.sub(replace_env_var, content)
            
            # Check for any security errors first
            if security_errors:
                raise SecurityError(f"Security validation failed: {'; '.join(security_errors)}")
            
            # Check for missing variables
            if missing_vars:
                if len(missing_vars) == 1:
                    raise EnvironmentVariableError(
                        f"Required environment variable '{missing_vars[0]}' is not set"
                    )
                else:
                    sorted_vars = sorted(missing_vars)
                    raise EnvironmentVariableError(
                        f"Required environment variables are not set: {', '.join(sorted_vars)}"
                    )
            
            return result
            
        except (EnvironmentVariableError, SecurityError):
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