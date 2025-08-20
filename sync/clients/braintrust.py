"""Braintrust API client wrapper for user and group management."""

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import structlog
from braintrust_api import Braintrust
from braintrust_api.types import Group, User
from pydantic import SecretStr

from sync.security.validation import validate_api_token, validate_url, validate_organization_name
from sync.clients.exceptions import (
    APIError,
    BraintrustError,
    ResourceNotFoundError,
    ValidationError,
)
from sync.config.role_project_models import RoleDefinition, RolePermission

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
        # Validate API key format
        token_value = api_key.get_secret_value()
        if not validate_api_token(token_value, "braintrust"):
            raise ValueError(
                "Invalid Braintrust API token format. Token must be a valid UUID or secure token."
            )
        
        # Validate API URL
        if not validate_url(api_url, allowed_schemes=["https"]):
            raise ValueError(f"Invalid API URL: {api_url}. Only HTTPS URLs are allowed.")
        
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds
        self.rate_limit_per_minute = rate_limit_per_minute
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        
        # Initialize Braintrust client
        self.client = Braintrust(
            api_key=api_key.get_secret_value(),
            base_url=str(api_url),  # Convert HttpUrl to string
            timeout=timeout_seconds,
        )
        
        # Request tracking for monitoring
        self._request_count = 0
        self._error_count = 0
        self._last_request_time: Optional[float] = None
        
        # Extract organization name from API URL for logging
        parsed_url = urlparse(str(api_url))
        self.org_name = parsed_url.hostname or "unknown"
        
        # Logger with client context
        self._logger = logger.bind(
            client_type="BraintrustClient",
            api_url=str(api_url),
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
            # For health check, just try to list organizations to test connectivity
            # This is safer than trying to retrieve a specific org
            orgs = self.client.organizations.list()
            org_list = list(orgs)
            self._logger.debug("Retrieved organizations list", org_count=len(org_list))
            
            # Return info about the first org for health check purposes
            if org_list:
                first_org = org_list[0]
                return first_org.model_dump() if hasattr(first_org, 'model_dump') else dict(first_org)
            else:
                return {"organizations": [], "message": "No organizations found"}
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
            # Convert SyncListObjects to list to get actual data
            users = list(users_response)
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
            # Convert SyncListObjects to list to get actual data
            groups = list(groups_response)
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
            
            # Get current members as lists
            current_users = list(getattr(current_group, 'member_users', []) or [])
            current_groups = list(getattr(current_group, 'member_groups', []) or [])
            
            # Add new members to existing ones (avoid duplicates)
            if user_ids:
                for user_id in user_ids:
                    if user_id not in current_users:
                        current_users.append(user_id)
            if group_ids:
                for group_id_to_add in group_ids:
                    if group_id_to_add not in current_groups:
                        current_groups.append(group_id_to_add)
            
            # Use replace to set the complete membership
            self._request_count += 1
            group = self.client.groups.replace(
                name=current_group.name,
                description=getattr(current_group, 'description', None),
                member_users=current_users,
                member_groups=current_groups,
            )
            self._logger.info(
                "Updated group membership using replace",
                group_id=group.id,
                total_users=len(current_users),
                total_groups=len(current_groups),
            )
            return group
            
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
    
    # Organization Member Management Methods
    
    async def invite_organization_members(
        self,
        emails: Optional[List[str]] = None,
        user_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
        group_names: Optional[List[str]] = None,
        send_invite_emails: bool = True,
        org_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invite members to the organization.
        
        Args:
            emails: List of email addresses to invite
            user_ids: List of existing user IDs to add
            group_ids: List of group IDs to add invited users to
            group_names: List of group names to add invited users to
            send_invite_emails: Whether to send invitation emails
            org_name: Organization name (if API key has access to multiple orgs)
            
        Returns:
            API response with success status and any errors
            
        Raises:
            BraintrustError: If invitation fails
        """
        try:
            self._request_count += 1
            
            # Build invite_users payload
            invite_users = {}
            if emails:
                invite_users["emails"] = emails
            if user_ids:
                invite_users["ids"] = user_ids
            if group_ids:
                invite_users["group_ids"] = group_ids
            if group_names:
                invite_users["group_names"] = group_names
            invite_users["send_invite_emails"] = send_invite_emails
            
            # Build request payload
            payload = {"invite_users": invite_users}
            if org_name:
                payload["org_name"] = org_name
            
            # Use the organization members endpoint
            # Note: This uses the generic client request method since the SDK may not have this endpoint
            response = await self._make_request("PATCH", "/v1/organization/members", payload)
            
            self._logger.info(
                "Invited organization members",
                emails=emails or [],
                user_ids=user_ids or [],
                group_count=len(group_ids or []) + len(group_names or []),
                send_emails=send_invite_emails,
            )
            
            return response
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def remove_organization_members(
        self,
        emails: Optional[List[str]] = None,
        user_ids: Optional[List[str]] = None,
        org_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Remove members from the organization.
        
        Args:
            emails: List of email addresses to remove
            user_ids: List of user IDs to remove
            org_name: Organization name (if API key has access to multiple orgs)
            
        Returns:
            API response with success status
            
        Raises:
            BraintrustError: If removal fails
        """
        try:
            self._request_count += 1
            
            # Build remove_users payload
            remove_users = {}
            if emails:
                remove_users["emails"] = emails
            if user_ids:
                remove_users["ids"] = user_ids
            
            # Build request payload
            payload = {"remove_users": remove_users}
            if org_name:
                payload["org_name"] = org_name
            
            # Use the organization members endpoint
            response = await self._make_request("PATCH", "/v1/organization/members", payload)
            
            self._logger.info(
                "Removed organization members",
                emails=emails or [],
                user_ids=user_ids or [],
            )
            
            return response
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a raw HTTP request to the Braintrust API.
        
        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            endpoint: API endpoint path
            payload: Request body payload
            
        Returns:
            Response data as dictionary
            
        Raises:
            BraintrustError: If request fails
        """
        import httpx
        import asyncio
        
        try:
            # Get the base URL and API key from the client
            base_url = str(self.api_url).rstrip('/')
            api_key = self.client.api_key
            
            # Build full URL
            url = f"{base_url}{endpoint}"
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            
            # Make the request
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, headers=headers, json=payload)
                elif method.upper() == "PATCH":
                    response = await client.patch(url, headers=headers, json=payload)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Check response status
                response.raise_for_status()
                
                # Parse JSON response
                return response.json()
                
        except httpx.HTTPStatusError as e:
            self._logger.error(
                "HTTP request failed",
                method=method,
                endpoint=endpoint,
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            raise BraintrustError(
                message=f"HTTP {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
                response_text=e.response.text,
            ) from e
        except Exception as e:
            self._logger.error(
                "Request failed",
                method=method,
                endpoint=endpoint,
                error=str(e),
            )
            raise BraintrustError(
                message=f"Request failed: {e}",
                status_code=None,
                response_text=None,
            ) from e
    
    async def invite_user_to_organization(
        self,
        email: str,
        given_name: str,
        family_name: str,
        group_names: Optional[List[str]] = None,
        send_invite_email: bool = True,
        additional_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invite a single user to the organization with optional group assignment.
        
        This is a convenience method that wraps invite_organization_members for single user invitations.
        
        Args:
            email: User's email address
            given_name: User's first name (for logging/tracking)
            family_name: User's last name (for logging/tracking)
            group_names: List of group names to add the user to
            send_invite_email: Whether to send invitation email
            additional_fields: Additional user fields (for compatibility, not used in invitation)
            
        Returns:
            API response with success status
            
        Raises:
            BraintrustError: If invitation fails
        """
        try:
            response = await self.invite_organization_members(
                emails=[email],
                group_names=group_names,
                send_invite_emails=send_invite_email,
            )
            
            self._logger.info(
                "Invited user to organization",
                email=email,
                name=f"{given_name} {family_name}",
                groups=group_names or [],
                send_email=send_invite_email,
            )
            
            return response
            
        except Exception as e:
            self._logger.error(
                "Failed to invite user to organization",
                email=email,
                name=f"{given_name} {family_name}",
                error=str(e),
            )
            raise
    
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
                # Handle both dict and object formats
                user_email = (
                    user.get('email') if isinstance(user, dict)
                    else getattr(user, 'email', None)
                )
                if user_email == email:
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
                # Handle both dict and object formats
                group_name = (
                    group.get('name') if isinstance(group, dict)
                    else getattr(group, 'name', None)
                )
                if group_name == name:
                    return group
            return None
        except Exception as e:
            self._logger.warning("Error searching for group by name", name=name, error=str(e))
            return None
    
    # ========== Role Management Methods ==========
    
    async def create_role(self, role_definition: RoleDefinition) -> Dict[str, Any]:
        """Create a new role in the organization.
        
        Args:
            role_definition: Role definition with name, description, and permissions
            
        Returns:
            Created role object with ID
            
        Raises:
            BraintrustError: If role creation fails
        """
        try:
            self._request_count += 1
            
            # Convert RoleDefinition to API format
            member_permissions = []
            for perm in role_definition.member_permissions:
                perm_dict = {"permission": perm.permission.value}
                if perm.restrict_object_type:
                    perm_dict["restrict_object_type"] = perm.restrict_object_type.value
                else:
                    perm_dict["restrict_object_type"] = None
                member_permissions.append(perm_dict)
            
            payload = {
                "name": role_definition.name,
                "description": role_definition.description,
                "member_permissions": member_permissions
            }
            
            response = await self._make_request("POST", "/v1/role", payload)
            
            self._logger.info(
                "Created role",
                role_name=role_definition.name,
                permission_count=len(member_permissions),
                role_id=response.get('id'),
            )
            
            return response
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def get_role_by_name(self, role_name: str) -> Optional[Dict[str, Any]]:
        """Get a role by name.
        
        Args:
            role_name: Name of the role to find
            
        Returns:
            Role object if found, None otherwise
        """
        try:
            self._request_count += 1
            
            response = await self._make_request(
                "GET", 
                "/v1/role", 
                params={"role_name": role_name}
            )
            
            # API returns {objects: [...]} format
            roles = response.get("objects", [])
            if roles:
                return roles[0]
            return None
            
        except Exception as e:
            self._logger.warning(
                "Error getting role by name",
                role_name=role_name,
                error=str(e)
            )
            return None
    
    async def list_roles(self) -> List[Dict[str, Any]]:
        """List all roles in the organization.
        
        Returns:
            List of role objects
        """
        try:
            self._request_count += 1
            
            response = await self._make_request("GET", "/v1/role")
            
            return response.get("objects", [])
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def update_role(
        self,
        role_id: str,
        member_permissions: List[RolePermission],
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing role.
        
        Args:
            role_id: UUID of the role to update
            member_permissions: New set of permissions for the role
            name: Optional new name for the role
            description: Optional new description for the role
            
        Returns:
            Updated role object
            
        Raises:
            BraintrustError: If role update fails
        """
        try:
            self._request_count += 1
            
            # Convert permissions to API format
            api_permissions = []
            for perm in member_permissions:
                perm_dict = {"permission": perm.permission.value}
                if perm.restrict_object_type:
                    perm_dict["restrict_object_type"] = perm.restrict_object_type.value
                else:
                    perm_dict["restrict_object_type"] = None
                api_permissions.append(perm_dict)
            
            payload = {"member_permissions": api_permissions}
            if name:
                payload["name"] = name
            if description:
                payload["description"] = description
            
            response = await self._make_request("PATCH", f"/v1/role/{role_id}", payload)
            
            self._logger.info(
                "Updated role",
                role_id=role_id,
                permission_count=len(api_permissions),
            )
            
            return response
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def delete_role(self, role_id: str) -> bool:
        """Delete a role.
        
        Args:
            role_id: UUID of the role to delete
            
        Returns:
            True if deletion was successful
            
        Raises:
            BraintrustError: If role deletion fails
        """
        try:
            self._request_count += 1
            
            await self._make_request("DELETE", f"/v1/role/{role_id}")
            
            self._logger.info("Deleted role", role_id=role_id)
            
            return True
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    # ========== ACL Management Methods ==========
    
    async def create_acl(
        self,
        object_type: str,
        object_id: str,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        role_id: Optional[str] = None,
        permission: Optional[str] = None,
        restrict_object_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a single ACL entry.
        
        Args:
            object_type: Type of object (e.g., 'project', 'organization')
            object_id: UUID of the object
            group_id: UUID of group (exactly one of group_id/user_id required)
            user_id: UUID of user (exactly one of group_id/user_id required)
            role_id: UUID of role (exactly one of role_id/permission required)
            permission: Direct permission (exactly one of role_id/permission required)
            restrict_object_type: Optional restriction to specific object types
            
        Returns:
            Created ACL object
            
        Raises:
            BraintrustError: If ACL creation fails
        """
        try:
            self._request_count += 1
            
            payload = {
                "object_type": object_type,
                "object_id": object_id,
            }
            
            # Add user or group (exactly one required)
            if group_id:
                payload["group_id"] = group_id
            elif user_id:
                payload["user_id"] = user_id
            else:
                raise ValidationError("Either group_id or user_id must be provided")
            
            # Add role or permission (exactly one required)
            if role_id:
                payload["role_id"] = role_id
            elif permission:
                payload["permission"] = permission
            else:
                raise ValidationError("Either role_id or permission must be provided")
            
            if restrict_object_type:
                payload["restrict_object_type"] = restrict_object_type
            
            response = await self._make_request("POST", "/v1/acl", payload)
            
            self._logger.info(
                "Created ACL",
                object_type=object_type,
                group_id=group_id,
                user_id=user_id,
                role_id=role_id,
                permission=permission,
                acl_id=response.get('id'),
            )
            
            return response
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def batch_update_acls(
        self,
        add_acls: List[Dict[str, Any]],
        remove_acls: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Batch update ACLs (add and/or remove multiple ACLs).
        
        This is the preferred method for adding a group to multiple projects.
        
        Args:
            add_acls: List of ACL entries to add
            remove_acls: Optional list of ACL entries to remove
            
        Returns:
            Dictionary with added_acls and removed_acls lists
            
        Raises:
            BraintrustError: If batch update fails
        """
        try:
            self._request_count += 1
            
            payload = {
                "add_acls": add_acls,
                "remove_acls": remove_acls or []
            }
            
            response = await self._make_request("POST", "/v1/acl/batch_update", payload)
            
            self._logger.info(
                "Batch updated ACLs",
                added_count=len(response.get("added_acls", [])),
                removed_count=len(response.get("removed_acls", [])),
            )
            
            return response
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def list_acls(
        self,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List ACLs with optional filtering.
        
        Args:
            object_type: Filter by object type
            object_id: Filter by object ID
            group_id: Filter by group ID
            user_id: Filter by user ID
            
        Returns:
            List of ACL objects
        """
        try:
            self._request_count += 1
            
            params = {}
            if object_type:
                params["object_type"] = object_type
            if object_id:
                params["object_id"] = object_id
            if group_id:
                params["group_id"] = group_id
            if user_id:
                params["user_id"] = user_id
            
            response = await self._make_request("GET", "/v1/acl", params=params)
            
            return response.get("objects", [])
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def list_org_acls(
        self,
        org_name: str,
        object_type: Optional[str] = None,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all ACLs in an organization (requires read_acls permission at org level).
        
        Args:
            org_name: Organization name
            object_type: Optional filter by object type
            group_id: Optional filter by group ID
            user_id: Optional filter by user ID
            
        Returns:
            List of ACL objects
        """
        try:
            self._request_count += 1
            
            params = {"org_name": org_name}
            if object_type:
                params["object_type"] = object_type
            if group_id:
                params["group_id"] = group_id
            if user_id:
                params["user_id"] = user_id
            
            response = await self._make_request("GET", "/v1/acl/list_org", params=params)
            
            return response.get("objects", [])
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def delete_acl(self, acl_id: str) -> bool:
        """Delete an ACL entry.
        
        Args:
            acl_id: UUID of the ACL to delete
            
        Returns:
            True if deletion was successful
            
        Raises:
            BraintrustError: If ACL deletion fails
        """
        try:
            self._request_count += 1
            
            await self._make_request("DELETE", f"/v1/acl/{acl_id}")
            
            self._logger.info("Deleted ACL", acl_id=acl_id)
            
            return True
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    # ========== Project Management Methods ==========
    
    async def list_projects(self, org_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all projects in the organization.
        
        Args:
            org_name: Optional organization name filter
            
        Returns:
            List of project objects
        """
        try:
            self._request_count += 1
            
            params = {}
            if org_name:
                params["org_name"] = org_name
            
            response = await self._make_request("GET", "/v1/project", params=params)
            
            return response.get("objects", [])
            
        except Exception as e:
            self._error_count += 1
            raise self._convert_to_braintrust_error(e) from e
    
    async def get_project_by_name(
        self,
        project_name: str,
        org_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get a project by name.
        
        Args:
            project_name: Name of the project to find
            org_name: Optional organization name
            
        Returns:
            Project object if found, None otherwise
        """
        try:
            self._request_count += 1
            
            params = {"project_name": project_name}
            if org_name:
                params["org_name"] = org_name
            
            response = await self._make_request("GET", "/v1/project", params=params)
            
            projects = response.get("objects", [])
            if projects:
                return projects[0]
            return None
            
        except Exception as e:
            self._logger.warning(
                "Error getting project by name",
                project_name=project_name,
                error=str(e)
            )
            return None
    
    # ========== High-Level Workflow Methods ==========
    
    async def assign_group_role_to_projects(
        self,
        group_name: str,
        role_name: str,
        project_names: List[str],
        org_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assign a group with a role to multiple projects.
        
        This is a high-level method that combines multiple API calls to:
        1. Find the group by name
        2. Find the role by name
        3. Find projects by names (or use project IDs if provided)
        4. Create ACLs via batch update
        
        Args:
            group_name: Name of the group
            role_name: Name of the role
            project_names: List of project names or UUIDs
            org_name: Optional organization name
            
        Returns:
            Dictionary with success status and results
        """
        try:
            # Step 1: Get the group
            group = await self.find_group_by_name(group_name)
            if not group:
                raise ResourceNotFoundError(f"Group '{group_name}' not found")
            
            group_id = group.get('id') if isinstance(group, dict) else getattr(group, 'id')
            
            # Step 2: Get the role
            role = await self.get_role_by_name(role_name)
            if not role:
                raise ResourceNotFoundError(f"Role '{role_name}' not found")
            
            role_id = role.get('id')
            
            # Step 3: Get project IDs
            project_ids = []
            for project_name in project_names:
                # Check if it's already a UUID
                if self._is_uuid(project_name):
                    project_ids.append(project_name)
                else:
                    # Look up by name
                    project = await self.get_project_by_name(project_name, org_name)
                    if not project:
                        raise ResourceNotFoundError(f"Project '{project_name}' not found")
                    project_ids.append(project.get('id'))
            
            # Step 4: Build ACL entries
            acl_entries = []
            for project_id in project_ids:
                acl_entries.append({
                    "object_type": "project",
                    "object_id": project_id,
                    "group_id": group_id,
                    "role_id": role_id
                })
            
            # Step 5: Batch create ACLs
            result = await self.batch_update_acls(add_acls=acl_entries)
            
            return {
                "success": True,
                "group_name": group_name,
                "group_id": group_id,
                "role_name": role_name,
                "role_id": role_id,
                "project_count": len(project_ids),
                "added_acls": result.get("added_acls", []),
                "message": f"Successfully assigned group '{group_name}' with role '{role_name}' to {len(project_ids)} projects"
            }
            
        except Exception as e:
            return {
                "success": False,
                "group_name": group_name,
                "role_name": role_name,
                "error": str(e)
            }
    
    def _is_uuid(self, value: str) -> bool:
        """Check if a string looks like a UUID.
        
        Args:
            value: String to check
            
        Returns:
            True if the string looks like a UUID
        """
        import re
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        return bool(uuid_pattern.match(value))