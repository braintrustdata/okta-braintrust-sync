"""User synchronization between Okta and Braintrust organizations."""

from typing import Any, Dict, List, Optional

import structlog
from braintrust_api.types import User as BraintrustUser

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient, OktaUser
from sync.core.state import StateManager
from sync.resources.base import BaseResourceSyncer
from sync.resources.user_group_assignment import UserGroupAssignmentManager

logger = structlog.get_logger(__name__)


class UserSyncer(BaseResourceSyncer[OktaUser, BraintrustUser]):
    """Syncs users from Okta to Braintrust organizations."""
    
    def __init__(
        self,
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
        identity_mapping_strategy: str = "email",
        custom_field_mappings: Optional[Dict[str, str]] = None,
        enable_auto_group_assignment: bool = True,
    ) -> None:
        """Initialize user syncer.
        
        Args:
            okta_client: Okta API client
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
            identity_mapping_strategy: How to map user identities ("email", "custom_field", "mapping_file")
            custom_field_mappings: Custom field mappings for user attributes
            enable_auto_group_assignment: Whether to automatically assign groups based on Okta data
        """
        super().__init__(okta_client, braintrust_clients, state_manager)
        
        self.identity_mapping_strategy = identity_mapping_strategy
        self.custom_field_mappings = custom_field_mappings or {}
        self.enable_auto_group_assignment = enable_auto_group_assignment
        
        # Initialize group assignment manager if enabled
        self.group_assignment_manager = None
        if enable_auto_group_assignment:
            self.group_assignment_manager = UserGroupAssignmentManager(
                okta_client=okta_client,
                braintrust_clients=braintrust_clients,
                state_manager=state_manager,
            )
        
        self._logger = logger.bind(
            syncer_type="UserSyncer",
            identity_strategy=identity_mapping_strategy,
            auto_group_assignment=enable_auto_group_assignment,
        )
    
    @property
    def resource_type(self) -> str:
        return "user"
    
    async def get_okta_resources(
        self,
        filter_expr: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[OktaUser]:
        """Get users from Okta.
        
        Args:
            filter_expr: Optional SCIM filter expression
            limit: Maximum number of users to retrieve
            
        Returns:
            List of Okta users
        """
        try:
            self._logger.debug(
                "Retrieving Okta users",
                filter_expr=filter_expr,
                limit=limit,
            )
            
            if filter_expr:
                users = await self.okta_client.search_users(filter_expr, limit=limit)
            else:
                users = await self.okta_client.list_users(limit=limit)
            
            self._logger.info(
                "Retrieved Okta users",
                count=len(users),
                filter_applied=filter_expr is not None,
            )
            
            return users
            
        except Exception as e:
            self._logger.error("Failed to retrieve Okta users", error=str(e))
            raise
    
    async def get_braintrust_resources(
        self,
        braintrust_org: str,
        limit: Optional[int] = None,
    ) -> List[BraintrustUser]:
        """Get users from Braintrust organization.
        
        Args:
            braintrust_org: Braintrust organization name
            limit: Maximum number of users to retrieve
            
        Returns:
            List of Braintrust users
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        try:
            client = self.braintrust_clients[braintrust_org]
            
            self._logger.debug(
                "Retrieving Braintrust users",
                braintrust_org=braintrust_org,
                limit=limit,
            )
            
            users = await client.list_users(limit=limit)
            
            self._logger.info(
                "Retrieved Braintrust users",
                braintrust_org=braintrust_org,
                count=len(users),
            )
            
            return users
            
        except Exception as e:
            self._logger.error(
                "Failed to retrieve Braintrust users",
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
    async def create_braintrust_resource(
        self,
        okta_resource: OktaUser,
        braintrust_org: str,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invite a new user to Braintrust organization.
        
        Note: Changed from direct user creation to invitation due to API limitations.
        Returns invitation response instead of User object.
        
        Args:
            okta_resource: Source Okta user
            braintrust_org: Target Braintrust organization
            additional_data: Additional data for user invitation
            
        Returns:
            Invitation response dictionary
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        try:
            client = self.braintrust_clients[braintrust_org]
            
            # Extract user information from Okta user
            user_data = self._extract_user_data(okta_resource)
            
            # Apply additional data if provided
            if additional_data:
                user_data.update(additional_data)
            
            # Get group names if specified in additional data
            group_names = additional_data.get("group_names") if additional_data else None
            
            # If auto group assignment is enabled and no groups specified, determine groups
            if self.enable_auto_group_assignment and self.group_assignment_manager and not group_names:
                group_names = await self.group_assignment_manager.assign_groups_on_sync(
                    okta_user=okta_resource,
                    braintrust_org=braintrust_org,
                )
                self._logger.debug(
                    "Auto-determined groups for user",
                    email=user_data.get("email"),
                    groups=group_names,
                )
            
            # Get user ID safely
            okta_user_id = (
                okta_resource.get("id") if isinstance(okta_resource, dict)
                else okta_resource.id
            )
            
            self._logger.debug(
                "Inviting Braintrust user",
                okta_user_id=okta_user_id,
                email=user_data.get("email"),
                braintrust_org=braintrust_org,
                groups=group_names or [],
                auto_assigned=self.enable_auto_group_assignment and not additional_data.get("group_names"),
            )
            
            # Use invitation API instead of direct user creation
            invitation_response = await client.invite_user_to_organization(
                email=user_data["email"],
                given_name=user_data["given_name"],
                family_name=user_data["family_name"],
                group_names=group_names,
                send_invite_email=True,
                additional_fields=user_data.get("additional_fields"),
            )
            
            self._logger.info(
                "Invited Braintrust user",
                okta_user_id=okta_user_id,
                email=user_data["email"],
                braintrust_org=braintrust_org,
                groups=group_names or [],
            )
            
            # Create a standardized response that the base syncer expects
            # The invitation API response may not include an 'id', so we use email as identifier
            standardized_response = {
                "id": user_data["email"],  # Use email as identifier since invited users don't have Braintrust IDs yet
                "email": user_data["email"],
                "given_name": user_data["given_name"],
                "family_name": user_data["family_name"],
                "invitation_status": "sent",
                "groups": group_names or [],
                "raw_response": invitation_response,
            }
            
            return standardized_response
            
        except Exception as e:
            # Get user ID safely for error logging
            okta_user_id = (
                okta_resource.get("id") if isinstance(okta_resource, dict)
                else okta_resource.id
            )
            self._logger.error(
                "Failed to invite Braintrust user",
                okta_user_id=okta_user_id,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
    async def update_braintrust_resource(
        self,
        braintrust_resource_id: str,
        okta_resource: OktaUser,
        braintrust_org: str,
        updates: Dict[str, Any],
    ) -> BraintrustUser:
        """Update an existing user in Braintrust.
        
        Note: This method should never be called since calculate_updates() always
        returns empty dict. This is a safety check.
        
        Args:
            braintrust_resource_id: Braintrust user ID
            okta_resource: Source Okta user
            braintrust_org: Target Braintrust organization
            updates: Fields to update
            
        Returns:
            Updated Braintrust user
            
        Raises:
            NotImplementedError: Braintrust API doesn't support user updates
        """
        # Get user ID safely
        okta_user_id = (
            okta_resource.get("id") if isinstance(okta_resource, dict)
            else okta_resource.id
        )
        
        self._logger.error(
            "User update attempted but not supported",
            braintrust_user_id=braintrust_resource_id,
            okta_user_id=okta_user_id,
            braintrust_org=braintrust_org,
            updates=list(updates.keys()),
            note="Braintrust API doesn't support user updates"
        )
        
        raise NotImplementedError(
            "Braintrust API doesn't support user updates. "
            "This method should not be called due to calculate_updates() returning empty dict."
        )
    
    def get_resource_identifier(self, resource: OktaUser) -> str:
        """Get unique identifier for an Okta user.
        
        Args:
            resource: Okta user (may be dict or object)
            
        Returns:
            Unique identifier (usually email)
        """
        # Handle both dict and object formats
        def get_email():
            if isinstance(resource, dict):
                profile = resource.get("profile", {})
                if isinstance(profile, dict):
                    return profile.get("email", "")
                else:
                    # Profile might be an object
                    return getattr(profile, 'email', '') if profile else ''
            else:
                # For OktaUser objects, profile is a dictionary
                return resource.profile.get("email", "")
        
        def get_custom_field(field_name):
            if isinstance(resource, dict):
                profile = resource.get("profile", {})
                if isinstance(profile, dict):
                    return profile.get(field_name, profile.get("email", ""))
                else:
                    # Profile might be an object
                    return getattr(profile, field_name, getattr(profile, 'email', '')) if profile else ''
            else:
                # For OktaUser objects, profile is a dictionary
                return resource.profile.get(field_name, resource.profile.get("email", ""))
        
        if self.identity_mapping_strategy == "email":
            return get_email()
        elif self.identity_mapping_strategy == "custom_field":
            # Use a custom field from the user profile
            custom_field = self.custom_field_mappings.get("identity_field", "email")
            return get_custom_field(custom_field)
        elif self.identity_mapping_strategy == "mapping_file":
            # For mapping file strategy, use email as fallback
            # In practice, this would load from an external mapping file
            return get_email()
        else:
            # Default to email
            return get_email()
    
    def get_braintrust_resource_identifier(self, resource: BraintrustUser) -> str:
        """Get unique identifier for a Braintrust user.
        
        Args:
            resource: Braintrust user (may be dict or object)
            
        Returns:
            Unique identifier (usually email)
        """
        # Handle both dict and object formats
        if isinstance(resource, dict):
            return resource.get('email', '') or resource.get('id', '')
        else:
            # Braintrust users have email as a direct attribute, not under profile
            return getattr(resource, 'email', '') or getattr(resource, 'id', '')
    
    def should_sync_resource(
        self,
        okta_resource: OktaUser,
        braintrust_org: str,
        sync_rules: Dict[str, Any],
    ) -> bool:
        """Check if user should be synced to the given organization.
        
        Args:
            okta_resource: Okta user to check
            braintrust_org: Target Braintrust organization
            sync_rules: Sync rules configuration
            
        Returns:
            True if user should be synced
        """
        try:
            # Check if user is active
            if sync_rules.get("only_active_users", True):
                user_status = (
                    okta_resource.get("status") if isinstance(okta_resource, dict)
                    else okta_resource.status
                )
                if user_status != "ACTIVE":
                    user_id = (
                        okta_resource.get("id") if isinstance(okta_resource, dict)
                        else okta_resource.id
                    )
                    self._logger.debug(
                        "Skipping inactive user",
                        user_id=user_id,
                        status=user_status,
                        braintrust_org=braintrust_org,
                    )
                    return False
            
            # Check email domain filters
            email_domain_filters = sync_rules.get("email_domain_filters", {}).get(braintrust_org)
            if email_domain_filters:
                # Get user email safely
                if isinstance(okta_resource, dict):
                    user_email = okta_resource.get("profile", {}).get("email", "")
                else:
                    user_email = okta_resource.profile.get("email", "")
                
                if not user_email or "@" not in user_email:
                    return False
                    
                user_domain = user_email.split("@")[1].lower()
                
                # Include filters - if specified, user domain must be in the list
                include_domains = email_domain_filters.get("include", [])
                if include_domains and user_domain not in [d.lower() for d in include_domains]:
                    self._logger.debug(
                        "User domain not in include list",
                        user_email=user_email,
                        user_domain=user_domain,
                        include_domains=include_domains,
                        braintrust_org=braintrust_org,
                    )
                    return False
                
                # Exclude filters - if user domain is in exclude list, skip
                exclude_domains = email_domain_filters.get("exclude", [])
                if exclude_domains and user_domain in [d.lower() for d in exclude_domains]:
                    self._logger.debug(
                        "User domain in exclude list",
                        user_email=user_email,
                        user_domain=user_domain,
                        exclude_domains=exclude_domains,
                        braintrust_org=braintrust_org,
                    )
                    return False
            
            # Check group membership filters
            group_filters = sync_rules.get("group_filters", {}).get(braintrust_org)
            if group_filters:
                user_groups = getattr(okta_resource, "groups", [])
                user_group_names = [g.profile.name for g in user_groups if hasattr(g, "profile")]
                
                # Include groups - if specified, user must be in at least one
                include_groups = group_filters.get("include", [])
                if include_groups:
                    if not any(group in user_group_names for group in include_groups):
                        self._logger.debug(
                            "User not in required groups",
                            user_id=okta_resource.id,
                            user_groups=user_group_names,
                            required_groups=include_groups,
                            braintrust_org=braintrust_org,
                        )
                        return False
                
                # Exclude groups - if user is in any exclude group, skip
                exclude_groups = group_filters.get("exclude", [])
                if exclude_groups:
                    if any(group in user_group_names for group in exclude_groups):
                        self._logger.debug(
                            "User in excluded groups",
                            user_id=okta_resource.id,
                            user_groups=user_group_names,
                            excluded_groups=exclude_groups,
                            braintrust_org=braintrust_org,
                        )
                        return False
            
            # Check custom profile attribute filters
            profile_filters = sync_rules.get("profile_filters", {}).get(braintrust_org)
            if profile_filters:
                for attr_name, expected_values in profile_filters.items():
                    user_value = getattr(okta_resource.profile, attr_name, None)
                    if user_value not in expected_values:
                        self._logger.debug(
                            "User profile attribute doesn't match filter",
                            user_id=okta_resource.id,
                            attribute=attr_name,
                            user_value=user_value,
                            expected_values=expected_values,
                            braintrust_org=braintrust_org,
                        )
                        return False
            
            return True
            
        except Exception as e:
            self._logger.warning(
                "Error checking sync rules, defaulting to sync",
                user_id=okta_resource.id,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            return True
    
    def calculate_updates(
        self,
        okta_resource: OktaUser,
        braintrust_resource: BraintrustUser,
    ) -> Dict[str, Any]:
        """Calculate what updates are needed for a Braintrust user.
        
        Note: Braintrust API doesn't support user updates, so this always returns
        empty dict to force SKIP action instead of UPDATE action.
        
        Args:
            okta_resource: Source Okta user
            braintrust_resource: Existing Braintrust user
            
        Returns:
            Empty dictionary (no updates supported)
        """
        # Get user ID safely for logging
        okta_user_id = (
            okta_resource.get("id") if isinstance(okta_resource, dict)
            else okta_resource.id
        )
        
        def get_braintrust_field(field_name: str) -> str:
            if isinstance(braintrust_resource, dict):
                return braintrust_resource.get(field_name, "")
            else:
                return getattr(braintrust_resource, field_name, "")
        
        self._logger.debug(
            "Calculated user updates",
            okta_user_id=okta_user_id,
            braintrust_user_id=get_braintrust_field("id") or "unknown",
            updates=[], # Always empty due to API limitations
            note="User updates disabled - Braintrust API doesn't support user updates"
        )
        
        # Always return empty dict to prevent UPDATE actions
        # This forces the base class to generate SKIP actions for existing users
        return {}
    
    def _extract_user_data(self, okta_user: OktaUser) -> Dict[str, Any]:
        """Extract user data from Okta user for Braintrust creation/update.
        
        Args:
            okta_user: Okta user object (may be dict or object)
            
        Returns:
            Dictionary with user data for Braintrust
        """
        # Handle both dict and object formats
        if isinstance(okta_user, dict):
            profile = okta_user.get("profile", {})
            user_data = {
                "given_name": profile.get("firstName", ""),
                "family_name": profile.get("lastName", ""),
                "email": profile.get("email", ""),
            }
        else:
            user_data = {
                "given_name": okta_user.profile.get("firstName", ""),
                "family_name": okta_user.profile.get("lastName", ""),
                "email": okta_user.profile.get("email", ""),
            }
        
        # Add custom fields if configured
        additional_fields = {}
        if self.custom_field_mappings:
            for okta_field, braintrust_field in self.custom_field_mappings.items():
                if okta_field in ["firstName", "lastName", "email"]:
                    continue  # Already handled in main fields
                
                # Handle both dict and object formats
                if isinstance(okta_user, dict):
                    profile = okta_user.get("profile", {})
                    value = profile.get(okta_field)
                else:
                    value = okta_user.profile.get(okta_field)
                    
                if value is not None:
                    additional_fields[braintrust_field] = value
        
        if additional_fields:
            user_data["additional_fields"] = additional_fields
        
        return user_data
    
    async def remove_braintrust_resource(
        self,
        braintrust_resource_id: str,
        okta_resource: OktaUser,
        braintrust_org: str,
    ) -> Dict[str, Any]:
        """Remove a user from Braintrust organization.
        
        Args:
            braintrust_resource_id: Braintrust user ID or email
            okta_resource: Source Okta user (for logging)
            braintrust_org: Target Braintrust organization
            
        Returns:
            Removal response dictionary
            
        Raises:
            BraintrustError: If removal fails
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        try:
            client = self.braintrust_clients[braintrust_org]
            
            # Get user ID and email safely
            okta_user_id = (
                okta_resource.get("id") if isinstance(okta_resource, dict)
                else okta_resource.id
            )
            if isinstance(okta_resource, dict):
                user_email = okta_resource.get("profile", {}).get("email", "")
            else:
                user_email = okta_resource.profile.get("email", "")
            
            self._logger.debug(
                "Removing Braintrust user",
                okta_user_id=okta_user_id,
                braintrust_resource_id=braintrust_resource_id,
                email=user_email,
                braintrust_org=braintrust_org,
            )
            
            # Remove user from organization
            # Try to determine if braintrust_resource_id is an email or user ID
            if "@" in braintrust_resource_id:
                # It's an email address
                removal_response = await client.remove_organization_members(
                    emails=[braintrust_resource_id]
                )
            else:
                # It's a user ID
                removal_response = await client.remove_organization_members(
                    user_ids=[braintrust_resource_id]
                )
            
            self._logger.info(
                "Removed Braintrust user",
                okta_user_id=okta_user_id,
                braintrust_resource_id=braintrust_resource_id,
                email=user_email,
                braintrust_org=braintrust_org,
            )
            
            return removal_response
            
        except Exception as e:
            okta_user_id = (
                okta_resource.get("id") if isinstance(okta_resource, dict)
                else okta_resource.id
            )
            self._logger.error(
                "Failed to remove Braintrust user",
                okta_user_id=okta_user_id,
                braintrust_resource_id=braintrust_resource_id,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
    async def find_braintrust_user_by_email(
        self,
        email: str,
        braintrust_org: str,
    ) -> Optional[BraintrustUser]:
        """Find a Braintrust user by email address.
        
        Args:
            email: Email address to search for
            braintrust_org: Braintrust organization name
            
        Returns:
            Braintrust user if found, None otherwise
        """
        if braintrust_org not in self.braintrust_clients:
            return None
        
        try:
            client = self.braintrust_clients[braintrust_org]
            return await client.find_user_by_email(email)
        except Exception as e:
            self._logger.warning(
                "Error searching for Braintrust user by email",
                email=email,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            return None
    
    async def check_and_assign_groups_for_accepted_invitations(
        self,
        braintrust_org: str,
        check_window_hours: int = 24,
    ) -> Dict[str, Any]:
        """Check for accepted invitations and assign users to groups.
        
        This method is a convenience wrapper around the group assignment manager.
        
        Args:
            braintrust_org: Braintrust organization to check
            check_window_hours: Only check invitations sent within this time window
            
        Returns:
            Dictionary with assignment results
        """
        if not self.enable_auto_group_assignment or not self.group_assignment_manager:
            return {
                "error": "Auto group assignment is not enabled",
                "checked_users": 0,
                "accepted_users": 0,
                "assigned_users": 0,
            }
        
        return await self.group_assignment_manager.check_and_assign_groups(
            braintrust_org=braintrust_org,
            check_window_hours=check_window_hours,
        )