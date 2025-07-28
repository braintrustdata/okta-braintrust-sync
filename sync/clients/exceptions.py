"""Exception classes for API clients."""

from typing import Optional


class APIError(Exception):
    """Base exception for API-related errors."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ) -> None:
        """Initialize API error.
        
        Args:
            message: Error message
            status_code: HTTP status code if available
            response_text: Response body text if available
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_text = response_text
    
    def __str__(self) -> str:
        """String representation of the error."""
        parts = [self.message]
        if self.status_code:
            parts.append(f"Status: {self.status_code}")
        if self.response_text:
            # Truncate response text for readability
            response_preview = self.response_text[:200]
            if len(self.response_text) > 200:
                response_preview += "..."
            parts.append(f"Response: {response_preview}")
        return " | ".join(parts)


class AuthenticationError(APIError):
    """Raised when authentication fails (401)."""
    pass


class AuthorizationError(APIError):
    """Raised when authorization fails (403)."""
    pass


class RateLimitError(APIError):
    """Raised when rate limit is exceeded (429)."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        """Initialize rate limit error.
        
        Args:
            message: Error message
            status_code: HTTP status code
            response_text: Response body text
            retry_after: Seconds to wait before retrying
        """
        super().__init__(message, status_code, response_text)
        self.retry_after = retry_after


class ClientError(APIError):
    """Raised for 4xx client errors."""
    pass


class ServerError(APIError):
    """Raised for 5xx server errors."""
    pass


class NetworkError(APIError):
    """Raised for network-related errors."""
    pass


class ConfigurationError(Exception):
    """Raised when client configuration is invalid."""
    pass


class ValidationError(Exception):
    """Raised when data validation fails."""
    pass


class ResourceNotFoundError(ClientError):
    """Raised when a requested resource is not found (404)."""
    pass


class ConflictError(ClientError):
    """Raised when there's a conflict with the current state (409)."""
    pass


class OktaError(APIError):
    """Okta-specific error."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        error_id: Optional[str] = None,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ) -> None:
        """Initialize Okta error.
        
        Args:
            message: Error message
            error_code: Okta error code
            error_id: Okta error ID for support
            status_code: HTTP status code
            response_text: Response body text
        """
        super().__init__(message, status_code, response_text)
        self.error_code = error_code
        self.error_id = error_id


class BraintrustError(APIError):
    """Braintrust-specific error."""
    pass


class SyncError(Exception):
    """Base exception for sync-related errors."""
    
    def __init__(
        self,
        message: str,
        source_resource_id: Optional[str] = None,
        destination_resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> None:
        """Initialize sync error.
        
        Args:
            message: Error message
            source_resource_id: ID of source resource (Okta)
            destination_resource_id: ID of destination resource (Braintrust)
            resource_type: Type of resource being synced
        """
        super().__init__(message)
        self.message = message
        self.source_resource_id = source_resource_id
        self.destination_resource_id = destination_resource_id
        self.resource_type = resource_type


class UserSyncError(SyncError):
    """Error during user synchronization."""
    pass


class GroupSyncError(SyncError):
    """Error during group synchronization."""
    pass


class MappingError(SyncError):
    """Error during identity mapping."""
    pass


class StateError(Exception):
    """Error with sync state management."""
    pass


class WebhookError(Exception):
    """Error processing webhooks."""
    
    def __init__(
        self,
        message: str,
        event_type: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        """Initialize webhook error.
        
        Args:
            message: Error message
            event_type: Type of webhook event
            event_id: ID of webhook event
        """
        super().__init__(message)
        self.message = message
        self.event_type = event_type
        self.event_id = event_id


class QueueError(Exception):
    """Error with event queue operations."""
    pass