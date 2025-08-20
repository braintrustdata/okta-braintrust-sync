"""Input validation and sanitization utilities."""

import re
import html
from typing import Any, Dict, Union, List
from urllib.parse import urlparse


class SecurityError(Exception):
    """Raised when security validation fails."""
    pass


def sanitize_log_input(data: Any) -> Any:
    """Sanitize data before logging to prevent log injection attacks.
    
    Args:
        data: Data to be logged (string, dict, list, or other types)
        
    Returns:
        Sanitized data safe for logging
    """
    if isinstance(data, str):
        # Remove or escape dangerous characters that could be used for log injection
        sanitized = data.replace('\n', '\\n').replace('\r', '\\r')
        sanitized = sanitized.replace('\t', '\\t')
        
        # Remove ANSI escape sequences that could be used to manipulate terminal output
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        sanitized = ansi_escape.sub('', sanitized)
        
        # Truncate extremely long strings to prevent log flooding
        if len(sanitized) > 1000:
            sanitized = sanitized[:997] + "..."
            
        return sanitized
        
    elif isinstance(data, dict):
        return {key: sanitize_log_input(value) for key, value in data.items()}
        
    elif isinstance(data, list):
        return [sanitize_log_input(item) for item in data]
        
    else:
        # For other types, convert to string and sanitize
        return sanitize_log_input(str(data))


def sanitize_user_input(input_str: str, max_length: int = 255) -> str:
    """Sanitize user input to prevent injection attacks.
    
    Args:
        input_str: User input string
        max_length: Maximum allowed length
        
    Returns:
        Sanitized input string
        
    Raises:
        SecurityError: If input contains dangerous content
    """
    if not isinstance(input_str, str):
        raise SecurityError("Input must be a string")
    
    # Remove leading/trailing whitespace
    sanitized = input_str.strip()
    
    # Check length
    if len(sanitized) > max_length:
        raise SecurityError(f"Input too long (max {max_length} characters)")
    
    # Check for potentially dangerous characters
    dangerous_patterns = [
        r'<script[^>]*>',  # Script tags
        r'javascript:',    # JavaScript URLs
        r'data:',         # Data URLs
        r'vbscript:',     # VBScript URLs
        r'\x00',          # Null bytes
        r'\.\./',         # Path traversal
        r'\\x[0-9a-fA-F]{2}',  # Hex encoded characters
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            raise SecurityError(f"Input contains potentially dangerous pattern: {pattern}")
    
    # HTML escape the input
    sanitized = html.escape(sanitized, quote=True)
    
    return sanitized


def validate_email(email: str) -> bool:
    """Validate email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email is valid, False otherwise
    """
    if not isinstance(email, str):
        return False
    
    # Basic email regex - not RFC 5322 compliant but good enough for most cases
    email_pattern = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    return bool(email_pattern.match(email)) and len(email) <= 254


def validate_api_token(token: str, token_type: str = "generic") -> bool:
    """Validate API token format.
    
    Args:
        token: API token to validate
        token_type: Type of token ("okta", "braintrust", or "generic")
        
    Returns:
        True if token format is valid, False otherwise
    """
    if not isinstance(token, str):
        return False
    
    # Remove any whitespace
    token = token.strip()
    
    if token_type.lower() == "okta":
        # Okta tokens should start with "ssws" and be followed by base64-like characters
        return bool(re.match(r'^ssws[A-Za-z0-9_-]{32,}$', token))
    
    elif token_type.lower() == "braintrust":
        # Braintrust tokens should be UUID format or specific pattern
        uuid_pattern = re.compile(
            r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        )
        # Also allow other common token formats (base64-like)
        token_pattern = re.compile(r'^[A-Za-z0-9_-]{20,}$')
        
        return bool(uuid_pattern.match(token) or token_pattern.match(token))
    
    else:
        # Generic token validation
        if len(token) < 8:
            return False
        if len(token) > 512:
            return False
        
        # Should contain only safe characters
        safe_pattern = re.compile(r'^[A-Za-z0-9_.-]+$')
        return bool(safe_pattern.match(token))


def validate_url(url: str, allowed_schemes: List[str] = None) -> bool:
    """Validate URL format and scheme.
    
    Args:
        url: URL to validate
        allowed_schemes: List of allowed URL schemes (default: ["https", "http"])
        
    Returns:
        True if URL is valid, False otherwise
    """
    if not isinstance(url, str):
        return False
    
    if allowed_schemes is None:
        allowed_schemes = ["https", "http"]
    
    try:
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme.lower() not in [s.lower() for s in allowed_schemes]:
            return False
        
        # Check if hostname exists
        if not parsed.netloc:
            return False
        
        # Check for dangerous characters
        if any(char in url for char in ['"', "'", '<', '>', '`']):
            return False
        
        return True
        
    except Exception:
        return False


def validate_organization_name(org_name: str) -> bool:
    """Validate organization name format.
    
    Args:
        org_name: Organization name to validate
        
    Returns:
        True if organization name is valid, False otherwise
    """
    if not isinstance(org_name, str):
        return False
    
    # Organization names should be alphanumeric with limited special characters
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}[a-zA-Z0-9]$', org_name):
        return False
    
    # Check length (1-64 characters)
    if len(org_name) < 1 or len(org_name) > 64:
        return False
    
    return True


def validate_project_name(project_name: str) -> bool:
    """Validate project name format.
    
    Args:
        project_name: Project name to validate
        
    Returns:
        True if project name is valid, False otherwise
    """
    if not isinstance(project_name, str):
        return False
    
    # Project names should allow more flexibility than org names
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9 ._-]{0,126}[a-zA-Z0-9]$', project_name):
        return False
    
    # Check length (1-128 characters)
    if len(project_name) < 1 or len(project_name) > 128:
        return False
    
    return True


def validate_group_name(group_name: str) -> bool:
    """Validate group name format.
    
    Args:
        group_name: Group name to validate
        
    Returns:
        True if group name is valid, False otherwise
    """
    if not isinstance(group_name, str):
        return False
    
    # Group names should allow spaces and common special characters
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9 ._-]{0,126}[a-zA-Z0-9]$', group_name):
        return False
    
    # Check length (1-128 characters)
    if len(group_name) < 1 or len(group_name) > 128:
        return False
    
    return True


def validate_role_name(role_name: str) -> bool:
    """Validate role name format.
    
    Args:
        role_name: Role name to validate
        
    Returns:
        True if role name is valid, False otherwise
    """
    if not isinstance(role_name, str):
        return False
    
    # Role names should be simple identifiers
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$', role_name):
        return False
    
    # Check length (1-64 characters)
    if len(role_name) < 1 or len(role_name) > 64:
        return False
    
    return True