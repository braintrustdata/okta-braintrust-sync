"""Okta API client for user and group management."""

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import structlog
from pydantic import SecretStr

from sync.clients.base import BaseAPIClient
from sync.security.validation import validate_api_token, validate_url
from sync.clients.exceptions import (
    APIError,
    OktaError,
    ResourceNotFoundError,
    ValidationError,
)

logger = structlog.get_logger(__name__)


class OktaUser:
    """Okta user data model."""
    
    def __init__(self, data: Dict[str, Any]) -> None:
        """Initialize from Okta API response data."""
        self.data = data
        self.id = data.get("id")
        self.status = data.get("status")
        self.created = data.get("created")
        self.activated = data.get("activated")
        self.status_changed = data.get("statusChanged")
        self.last_login = data.get("lastLogin")
        self.last_updated = data.get("lastUpdated")
        self.password_changed = data.get("passwordChanged")
        self.profile = data.get("profile", {})
        self.credentials = data.get("credentials", {})
        self._links = data.get("_links", {})
    
    @property
    def login(self) -> Optional[str]:
        """User login/username."""
        return self.profile.get("login")
    
    @property
    def email(self) -> Optional[str]:
        """User email address."""
        return self.profile.get("email")
    
    @property
    def first_name(self) -> Optional[str]:
        """User first name."""
        return self.profile.get("firstName")
    
    @property
    def last_name(self) -> Optional[str]:
        """User last name."""
        return self.profile.get("lastName")
    
    @property
    def display_name(self) -> Optional[str]:
        """User display name."""
        return self.profile.get("displayName")
    
    @property
    def department(self) -> Optional[str]:
        """User department."""
        return self.profile.get("department")
    
    @property
    def title(self) -> Optional[str]:
        """User job title."""
        return self.profile.get("title")
    
    @property
    def is_active(self) -> bool:
        """Check if user is active."""
        return self.status == "ACTIVE"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.data


class OktaGroup:
    """Okta group data model."""
    
    def __init__(self, data: Dict[str, Any]) -> None:
        """Initialize from Okta API response data."""
        self.data = data
        self.id = data.get("id")
        self.created = data.get("created")
        self.last_updated = data.get("lastUpdated")
        self.last_membership_updated = data.get("lastMembershipUpdated")
        self.object_class = data.get("objectClass", [])
        self.type = data.get("type")
        self.profile = data.get("profile", {})
        self._links = data.get("_links", {})
    
    @property
    def name(self) -> Optional[str]:
        """Group name."""
        return self.profile.get("name")
    
    @property
    def description(self) -> Optional[str]:
        """Group description."""
        return self.profile.get("description")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.data


class OktaClient(BaseAPIClient):
    """Okta API client for user and group management."""
    
    def __init__(
        self,
        domain: str,
        api_token: SecretStr,
        timeout_seconds: int = 30,
        rate_limit_per_minute: int = 600,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        """Initialize Okta client.
        
        Args:
            domain: Okta domain (e.g., 'yourorg.okta.com')
            api_token: Okta API token
            timeout_seconds: Request timeout in seconds
            rate_limit_per_minute: Maximum requests per minute
            max_retries: Maximum retry attempts
            retry_delay_seconds: Initial retry delay
        """
        # Clean up domain
        self.domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
        if not self.domain.endswith(".okta.com") and not self.domain.endswith(".oktapreview.com"):
            raise ValueError(f"Invalid Okta domain: {domain}")
        
        # Store configuration - let the actual API calls validate credentials and URLs
        base_url = f"https://{self.domain}/api/v1"
        
        self._api_token = api_token
        
        super().__init__(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            rate_limit_per_minute=rate_limit_per_minute,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        
        self._logger = logger.bind(okta_domain=self.domain)
        
        # ========== Caching for performance optimization ==========
        # Cache users and groups to avoid repeated API calls during sync operations
        self._users_cache: Optional[List[OktaUser]] = None
        self._groups_cache: Optional[List[Dict[str, Any]]] = None
        self._users_cache_by_email: Optional[Dict[str, OktaUser]] = None
        self._groups_cache_by_name: Optional[Dict[str, Dict[str, Any]]] = None
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get Okta authentication headers."""
        return {
            "Authorization": f"SSWS {self._api_token.get_secret_value()}",
        }
    
    async def health_check(self) -> bool:
        """Check if Okta API is accessible.
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Try to get current user info (minimal request)
            await self.get("/users/me")
            return True
        except Exception as e:
            self._logger.error("Okta health check failed", error=str(e))
            return False
    
    # User Management Methods
    
    async def get_user(self, user_id: str) -> OktaUser:
        """Get a single user by ID.
        
        Args:
            user_id: Okta user ID
            
        Returns:
            OktaUser object
            
        Raises:
            ResourceNotFoundError: If user not found
            OktaError: If API call fails
        """
        try:
            response_data = await self.get_json(f"/users/{user_id}")
            return OktaUser(response_data)
        except APIError as e:
            if e.status_code == 404:
                raise ResourceNotFoundError(f"User not found: {user_id}") from e
            raise self._convert_to_okta_error(e) from e
    
    # ========== Caching Methods for Performance Optimization ==========
    
    async def _ensure_users_cache(self) -> None:
        """Ensure users cache is populated."""
        if self._users_cache is None or self._users_cache_by_email is None:
            self._logger.debug("Populating users cache")
            users = await self.list_users()  # Get all users without filters
            self._users_cache = users
            
            # Build email-to-user mapping for O(1) lookups
            self._users_cache_by_email = {}
            for user in users:
                if user.email:
                    self._users_cache_by_email[user.email] = user
            
            self._logger.debug(
                "Users cache populated",
                cached_users=len(self._users_cache),
                unique_emails=len(self._users_cache_by_email)
            )
    
    async def _ensure_groups_cache(self) -> None:
        """Ensure groups cache is populated."""
        if self._groups_cache is None or self._groups_cache_by_name is None:
            self._logger.debug("Populating groups cache")
            groups = await self.list_groups()  # Get all groups without filters
            self._groups_cache = [group.data for group in groups]  # Store raw data
            
            # Build name-to-group mapping for O(1) lookups
            self._groups_cache_by_name = {}
            for group in groups:
                if hasattr(group, 'name') and group.name:
                    self._groups_cache_by_name[group.name] = group.data
            
            self._logger.debug(
                "Groups cache populated",
                cached_groups=len(self._groups_cache),
                unique_names=len(self._groups_cache_by_name)
            )
    
    def clear_caches(self) -> None:
        """Clear all caches. Useful when data is modified during sync."""
        self._users_cache = None
        self._groups_cache = None
        self._users_cache_by_email = None
        self._groups_cache_by_name = None
        self._logger.debug("All Okta caches cleared")
    
    async def list_users(
        self,
        q: Optional[str] = None,
        filter_expr: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[OktaUser]:
        """List users with optional filtering.
        
        Args:
            q: Query string for simple user lookup
            filter_expr: SCIM filter expression
            search: Search expression
            limit: Maximum number of users to return
            
        Returns:
            List of OktaUser objects
        """
        params: Dict[str, Any] = {}
        if q:
            params["q"] = q
        if filter_expr:
            params["filter"] = filter_expr
        if search:
            params["search"] = search
        if limit:
            params["limit"] = min(limit, 200)  # Okta max is 200
        
        try:
            users_data = await self.paginate("/users", params=params, limit=limit)
            return [OktaUser(user_data) for user_data in users_data]
        except APIError as e:
            raise self._convert_to_okta_error(e) from e
    
    async def search_users(self, filter_expr: str, limit: Optional[int] = None) -> List[OktaUser]:
        """Search users using SCIM filter expression.
        
        Args:
            filter_expr: SCIM filter expression (e.g., 'profile.department eq "Engineering"')
            limit: Maximum number of users to return
            
        Returns:
            List of matching OktaUser objects
        """
        return await self.list_users(filter_expr=filter_expr, limit=limit)
    
    async def get_user_groups(self, user_id: str) -> List[OktaGroup]:
        """Get groups that a user belongs to.
        
        Args:
            user_id: Okta user ID
            
        Returns:
            List of OktaGroup objects
        """
        try:
            groups_data = await self.paginate(f"/users/{user_id}/groups")
            return [OktaGroup(group_data) for group_data in groups_data]
        except APIError as e:
            raise self._convert_to_okta_error(e) from e
    
    # Group Management Methods
    
    async def get_group(self, group_id: str) -> OktaGroup:
        """Get a single group by ID.
        
        Args:
            group_id: Okta group ID
            
        Returns:
            OktaGroup object
            
        Raises:
            ResourceNotFoundError: If group not found
            OktaError: If API call fails
        """
        try:
            response_data = await self.get_json(f"/groups/{group_id}")
            return OktaGroup(response_data)
        except APIError as e:
            if e.status_code == 404:
                raise ResourceNotFoundError(f"Group not found: {group_id}") from e
            raise self._convert_to_okta_error(e) from e
    
    async def list_groups(
        self,
        q: Optional[str] = None,
        filter_expr: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[OktaGroup]:
        """List groups with optional filtering.
        
        Args:
            q: Query string for simple group lookup
            filter_expr: SCIM filter expression
            search: Search expression
            limit: Maximum number of groups to return
            
        Returns:
            List of OktaGroup objects
        """
        params: Dict[str, Any] = {}
        if q:
            params["q"] = q
        if filter_expr:
            params["filter"] = filter_expr
        if search:
            params["search"] = search
        if limit:
            params["limit"] = min(limit, 200)  # Okta max is 200
        
        try:
            groups_data = await self.paginate("/groups", params=params, limit=limit)
            return [OktaGroup(group_data) for group_data in groups_data]
        except APIError as e:
            raise self._convert_to_okta_error(e) from e
    
    async def search_groups(self, filter_expr: str, limit: Optional[int] = None) -> List[OktaGroup]:
        """Search groups using SCIM filter expression.
        
        Args:
            filter_expr: SCIM filter expression (e.g., 'type eq "OKTA_GROUP"')
            limit: Maximum number of groups to return
            
        Returns:
            List of matching OktaGroup objects
        """
        return await self.list_groups(filter_expr=filter_expr, limit=limit)
    
    async def get_group_members(self, group_id: str) -> List[OktaUser]:
        """Get members of a group.
        
        Args:
            group_id: Okta group ID
            
        Returns:
            List of OktaUser objects
        """
        try:
            users_data = await self.paginate(f"/groups/{group_id}/users")
            return [OktaUser(user_data) for user_data in users_data]
        except APIError as e:
            raise self._convert_to_okta_error(e) from e
    
    # Event Hook Methods (for webhook setup)
    
    async def list_event_hooks(self) -> List[Dict[str, Any]]:
        """List configured event hooks.
        
        Returns:
            List of event hook configurations
        """
        try:
            return await self.paginate("/eventHooks")
        except APIError as e:
            raise self._convert_to_okta_error(e) from e
    
    async def create_event_hook(
        self,
        name: str,
        url: str,
        events: List[str],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a new event hook.
        
        Args:
            name: Name of the event hook
            url: Webhook URL to call
            events: List of event types to subscribe to
            headers: Optional headers to send with webhook
            
        Returns:
            Created event hook configuration
        """
        hook_data = {
            "name": name,
            "status": "ACTIVE",
            "verificationStatus": "UNVERIFIED",
            "events": {
                "type": "EVENT_TYPE",
                "items": events,
            },
            "channel": {
                "type": "HTTP",
                "version": "1.0.0",
                "config": {
                    "uri": url,
                    "headers": headers or [],
                    "method": "POST",
                }
            }
        }
        
        try:
            return await self.post_json("/eventHooks", json_data=hook_data)
        except APIError as e:
            raise self._convert_to_okta_error(e) from e
    
    async def verify_event_hook(self, hook_id: str) -> Dict[str, Any]:
        """Verify an event hook.
        
        Args:
            hook_id: Event hook ID
            
        Returns:
            Verification result
        """
        try:
            return await self.post_json(f"/eventHooks/{hook_id}/lifecycle/verify")
        except APIError as e:
            raise self._convert_to_okta_error(e) from e
    
    # Pagination Implementation
    
    async def paginate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Paginate through all results for an endpoint.
        
        Args:
            path: API endpoint path
            params: Query parameters
            limit: Maximum number of items to retrieve
            
        Returns:
            List of all items from all pages
        """
        all_items = []
        current_params = params.copy() if params else {}
        current_params.setdefault("limit", 200)  # Okta default page size
        
        next_url = None
        
        while True:
            if next_url:
                # Parse next URL to get path and params
                parsed = urlparse(next_url)
                path = parsed.path.replace("/api/v1", "")  # Remove base path
                current_params = parse_qs(parsed.query)
                # Convert single-item lists to strings
                current_params = {k: v[0] if len(v) == 1 else v for k, v in current_params.items()}
            
            response = await self.get(path, params=current_params)
            
            try:
                items = response.json()
                if not isinstance(items, list):
                    raise ValidationError(f"Expected list response, got {type(items)}")
                
                all_items.extend(items)
                
                # Check if we've hit the limit
                if limit and len(all_items) >= limit:
                    return all_items[:limit]
                
                # Check for next page link
                next_url = None
                link_header = response.headers.get("Link")
                if link_header:
                    links = self._parse_link_header(link_header)
                    next_url = links.get("next")
                
                if not next_url or not items:
                    break
                    
            except Exception as e:
                raise APIError(f"Failed to parse paginated response: {e}") from e
        
        return all_items
    
    def _parse_link_header(self, link_header: str) -> Dict[str, str]:
        """Parse HTTP Link header for pagination.
        
        Args:
            link_header: Link header value
            
        Returns:
            Dictionary mapping relation types to URLs
        """
        links = {}
        for link in link_header.split(","):
            parts = link.strip().split(";")
            if len(parts) >= 2:
                url = parts[0].strip("<>")
                for part in parts[1:]:
                    if "rel=" in part:
                        rel = part.split("=")[1].strip('"')
                        links[rel] = url
                        break
        return links
    
    def _convert_to_okta_error(self, api_error: APIError) -> OktaError:
        """Convert generic API error to Okta-specific error.
        
        Args:
            api_error: Generic API error
            
        Returns:
            Okta-specific error with additional context
        """
        error_code = None
        error_id = None
        
        # Try to parse Okta error response
        if api_error.response_text:
            try:
                error_data = json.loads(api_error.response_text)
                if isinstance(error_data, dict):
                    error_code = error_data.get("errorCode")
                    error_id = error_data.get("errorId")
                    # Use Okta's error message if available
                    if "errorSummary" in error_data:
                        api_error.message = error_data["errorSummary"]
            except (json.JSONDecodeError, TypeError):
                pass
        
        return OktaError(
            message=api_error.message,
            error_code=error_code,
            error_id=error_id,
            status_code=api_error.status_code,
            response_text=api_error.response_text,
        )