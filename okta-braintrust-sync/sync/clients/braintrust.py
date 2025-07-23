"""Braintrust API client wrapper for user and group management."""

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import structlog
from braintrust_api import Braintrust
from braintrust_api.types import Group, User
from pydantic import SecretStr

from sync.clients.exceptions import (
    APIError,
    BraintrustError,
    ResourceNotFoundError,
    ValidationError,
)

logger = structlog.get_logger(__name__)


class BraintrustClient:
    """Braintrust API client wrapper with sync-specific functionality."""
    
    def __init__(
        self,
        api_key: SecretStr,
        api_url: str = "https://api.braintrust.dev",
        timeout_seconds: int = 30,
        rate_limit_per_minute: int = 300,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        """Initialize Braintrust client.
        
        Args:
            api_key: Braintrust API key
            api_url: Braintrust API URL
            timeout_seconds: Request timeout in seconds
            rate_limit_per_minute: Maximum requests per minute
            max_retries: Maximum retry attempts
            retry_delay_seconds: Initial retry delay
        """
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        
        # Initialize Braintrust client
        self.client = Braintrust(
            api_key=api_key.get_secret_value(),
            base_url=api_url,
            timeout=timeout_seconds,
        )
        
        # Request tracking for monitoring
        self._request_count = 0
        self._error_count = 0
        self._last_request_time: Optional[float] = None
        
        # Extract organization name from API URL for logging
        parsed_url = urlparse(api_url)
        self.org_name = parsed_url.hostname or "unknown"
        
        # Logger with client context
        self._logger = logger.bind(
            client_type="BraintrustClient",
            api_url=api_url,
            org_name=self.org_name,
        )
    
    async def __aenter__(self) -> "BraintrustClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def close(self) -> None:
        """Close the client and cleanup resources."""
        # Braintrust client doesn't require explicit cleanup
        self._logger.debug("Braintrust client closed")
    
    # Health Check and Connectivity
    
    async def health_check(self) -> bool:
        """Check if Braintrust API is accessible.
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Try to get organization info as a basic connectivity test
            await self.get_organization_info()
            return True
        except Exception as e:
            self._logger.error("Braintrust health check failed", error=str(e))
            return False
    
    async def get_organization_info(self) -> Dict[str, Any]:
        """Get organization information.
        
        Returns:
            Organization information dictionary
            
        Raises:
            BraintrustError: If API call fails
        """
        try:
            self._request_count += 1
            # Note: Actual API endpoint may vary - this is conceptual
            org_info = self.client.organizations.retrieve()
            self._logger.debug("Retrieved organization info", org_id=getattr(org_info, 'id', None))
            return org_info.model_dump() if hasattr(org_info, 'model_dump') else dict(org_info)
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    # User Management Methods
    
    async def get_user(self, user_id: str) -> User:
        """Get a single user by ID.
        
        Args:
            user_id: Braintrust user ID
            
        Returns:
            User object
            
        Raises:
            ResourceNotFoundError: If user not found
            BraintrustError: If API call fails
        """
        try:
            self._request_count += 1
            user = self.client.users.retrieve(user_id)
            self._logger.debug("Retrieved user", user_id=user_id, user_name=getattr(user, 'name', 'unknown'))
            return user
        except Exception as e:
            self._error_count += 1
            if self._is_not_found_error(e):
                raise ResourceNotFoundError(f"User not found: {user_id}") from e
            raise self._convert_to_braintrust_error(e) from e
    
    async def list_users(
        self,
        limit: Optional[int] = None,
        starting_after: Optional[str] = None,
    ) -> List[User]:
        """List users in the organization.
        
        Args:
            limit: Maximum number of users to return
            starting_after: Cursor for pagination
            
        Returns:
            List of User objects
        """
        try:
            self._request_count += 1
            users_response = self.client.users.list(
                limit=limit,
                starting_after=starting_after,
            )
            users = users_response.data if hasattr(users_response, 'data') else users_response
            self._logger.debug("Listed users", count=len(users))
            return users
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def create_user(
        self,
        given_name: str,
        family_name: str,
        email: str,
        additional_fields: Optional[Dict[str, Any]] = None,
    ) -> User:
        """Create a new user.
        
        Args:
            given_name: User's first name
            family_name: User's last name
            email: User's email address
            additional_fields: Additional user fields
            
        Returns:
            Created User object
            
        Raises:
            BraintrustError: If creation fails
        """
        try:
            self._request_count += 1
            user_data = {
                "given_name": given_name,
                "family_name": family_name,
                "email": email,
            }
            if additional_fields:
                user_data.update(additional_fields)
            
            user = self.client.users.create(**user_data)
            self._logger.info(
                "Created user",
                user_id=user.id,
                email=email,
                name=f"{given_name} {family_name}",
            )
            return user
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def update_user(
        self,
        user_id: str,
        updates: Dict[str, Any],
    ) -> User:
        """Update an existing user.
        
        Args:
            user_id: Braintrust user ID
            updates: Fields to update
            
        Returns:
            Updated User object
            
        Raises:
            ResourceNotFoundError: If user not found
            BraintrustError: If update fails
        """
        try:
            self._request_count += 1
            user = self.client.users.update(user_id, **updates)
            self._logger.info("Updated user", user_id=user_id, fields=list(updates.keys()))
            return user
        except Exception as e:
            self._error_count += 1
            if self._is_not_found_error(e):
                raise ResourceNotFoundError(f"User not found: {user_id}") from e
            raise self._convert_to_braintrust_error(e) from e
    
    # Group Management Methods
    
    async def get_group(self, group_id: str) -> Group:
        """Get a single group by ID.
        
        Args:
            group_id: Braintrust group ID
            
        Returns:
            Group object
            
        Raises:
            ResourceNotFoundError: If group not found
            BraintrustError: If API call fails
        """
        try:
            self._request_count += 1
            group = self.client.groups.retrieve(group_id)
            self._logger.debug("Retrieved group", group_id=group_id, group_name=getattr(group, 'name', 'unknown'))
            return group
        except Exception as e:
            self._error_count += 1
            if self._is_not_found_error(e):
                raise ResourceNotFoundError(f"Group not found: {group_id}") from e
            raise self._convert_to_braintrust_error(e) from e
    
    async def list_groups(
        self,
        limit: Optional[int] = None,
        starting_after: Optional[str] = None,
    ) -> List[Group]:
        """List groups in the organization.
        
        Args:
            limit: Maximum number of groups to return
            starting_after: Cursor for pagination
            
        Returns:
            List of Group objects
        """
        try:
            self._request_count += 1
            groups_response = self.client.groups.list(
                limit=limit,
                starting_after=starting_after,
            )
            groups = groups_response.data if hasattr(groups_response, 'data') else groups_response
            self._logger.debug("Listed groups", count=len(groups))
            return groups
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def create_group(
        self,
        name: str,
        description: Optional[str] = None,
        member_users: Optional[List[str]] = None,
        member_groups: Optional[List[str]] = None,
    ) -> Group:
        """Create a new group.
        
        Args:
            name: Group name
            description: Group description
            member_users: List of user IDs to add as members
            member_groups: List of group IDs to add as member groups
            
        Returns:
            Created Group object
            
        Raises:
            BraintrustError: If creation fails
        """
        try:
            self._request_count += 1
            group_data = {"name": name}
            if description:
                group_data["description"] = description
            if member_users:
                group_data["member_users"] = member_users
            if member_groups:
                group_data["member_groups"] = member_groups
            
            group = self.client.groups.create(**group_data)
            self._logger.info(
                "Created group",
                group_id=group.id,
                name=name,
                member_count=(len(member_users or []) + len(member_groups or [])),
            )
            return group
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def update_group(
        self,
        group_id: str,
        updates: Dict[str, Any],
    ) -> Group:
        """Update an existing group.
        
        Args:
            group_id: Braintrust group ID
            updates: Fields to update
            
        Returns:
            Updated Group object
            
        Raises:
            ResourceNotFoundError: If group not found
            BraintrustError: If update fails
        """
        try:
            self._request_count += 1
            group = self.client.groups.update(group_id, **updates)
            self._logger.info("Updated group", group_id=group_id, fields=list(updates.keys()))
            return group
        except Exception as e:
            self._error_count += 1
            if self._is_not_found_error(e):
                raise ResourceNotFoundError(f"Group not found: {group_id}") from e
            raise self._convert_to_braintrust_error(e) from e
    
    async def add_group_members(
        self,
        group_id: str,
        user_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> Group:
        """Add members to a group.
        
        Args:
            group_id: Braintrust group ID
            user_ids: User IDs to add as members
            group_ids: Group IDs to add as member groups
            
        Returns:
            Updated Group object
            
        Raises:
            ResourceNotFoundError: If group not found
            BraintrustError: If operation fails
        """
        try:
            # Get current group to merge members
            current_group = await self.get_group(group_id)
            
            # Merge current and new members
            current_users = set(getattr(current_group, 'member_users', []) or [])
            current_groups = set(getattr(current_group, 'member_groups', []) or [])
            
            if user_ids:
                current_users.update(user_ids)
            if group_ids:
                current_groups.update(group_ids)
            
            # Update group with merged membership
            updates = {}
            if current_users:
                updates['member_users'] = list(current_users)
            if current_groups:
                updates['member_groups'] = list(current_groups)
            
            return await self.update_group(group_id, updates)
            
        except Exception as e:
            self._error_count += 1
            if self._is_not_found_error(e):
                raise ResourceNotFoundError(f"Group not found: {group_id}") from e
            raise self._convert_to_braintrust_error(e) from e
    
    async def remove_group_members(
        self,
        group_id: str,
        user_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> Group:
        """Remove members from a group.
        
        Args:
            group_id: Braintrust group ID
            user_ids: User IDs to remove from membership
            group_ids: Group IDs to remove from member groups
            
        Returns:
            Updated Group object
            
        Raises:
            ResourceNotFoundError: If group not found
            BraintrustError: If operation fails
        """
        try:
            # Get current group to filter members
            current_group = await self.get_group(group_id)
            
            # Filter out removed members
            current_users = set(getattr(current_group, 'member_users', []) or [])
            current_groups = set(getattr(current_group, 'member_groups', []) or [])
            
            if user_ids:
                current_users -= set(user_ids)
            if group_ids:
                current_groups -= set(group_ids)
            
            # Update group with filtered membership
            updates = {
                'member_users': list(current_users),
                'member_groups': list(current_groups),
            }
            
            return await self.update_group(group_id, updates)
            
        except Exception as e:
            self._error_count += 1
            if self._is_not_found_error(e):
                raise ResourceNotFoundError(f"Group not found: {group_id}") from e
            raise self._convert_to_braintrust_error(e) from e
    
    # Utility Methods
    
    def _is_not_found_error(self, error: Exception) -> bool:
        """Check if error represents a resource not found condition.
        
        Args:
            error: Exception to check
            
        Returns:
            True if error indicates resource not found
        """
        # This would need to be customized based on actual Braintrust API error patterns
        error_str = str(error).lower()
        return "not found" in error_str or "404" in error_str
    
    def _convert_to_braintrust_error(self, error: Exception) -> BraintrustError:
        """Convert generic exception to Braintrust-specific error.
        
        Args:
            error: Generic exception
            
        Returns:
            Braintrust-specific error with additional context
        """
        return BraintrustError(
            message=str(error),
            status_code=getattr(error, 'status_code', None),
            response_text=getattr(error, 'response_text', None),
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics for monitoring.
        
        Returns:
            Dictionary with client statistics
        """
        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(self._request_count, 1),
            "last_request_time": self._last_request_time,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "api_url": self.api_url,
            "org_name": self.org_name,
        }
    
    # Search and Query Methods
    
    async def find_user_by_email(self, email: str) -> Optional[User]:
        """Find a user by email address.
        
        Args:
            email: Email address to search for
            
        Returns:
            User object if found, None otherwise
        """
        try:
            users = await self.list_users()
            for user in users:
                if getattr(user, 'email', None) == email:
                    return user
            return None
        except Exception as e:
            self._logger.warning("Error searching for user by email", email=email, error=str(e))
            return None
    
    async def find_group_by_name(self, name: str) -> Optional[Group]:
        """Find a group by name.
        
        Args:
            name: Group name to search for
            
        Returns:
            Group object if found, None otherwise
        """
        try:
            groups = await self.list_groups()
            for group in groups:
                if getattr(group, 'name', None) == name:
                    return group
            return None
        except Exception as e:
            self._logger.warning("Error searching for group by name", name=name, error=str(e))
            return None