"""Group synchronization between Okta and Braintrust organizations."""

from typing import Any, Dict, List, Optional, Set

import structlog
from braintrust_api.types import Group as BraintrustGroup, User as BraintrustUser

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient, OktaGroup, OktaUser
from sync.core.state import StateManager
from sync.resources.base import BaseResourceSyncer

logger = structlog.get_logger(__name__)


class GroupSyncer(BaseResourceSyncer[OktaGroup, BraintrustGroup]):
    """Syncs groups from Okta to Braintrust organizations."""
    
    def __init__(
        self,
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
        sync_group_memberships: bool = True,
        group_name_prefix: Optional[str] = None,
        group_name_suffix: Optional[str] = None,
    ) -> None:
        """Initialize group syncer.
        
        Args:
            okta_client: Okta API client
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
            sync_group_memberships: Whether to sync group memberships
            group_name_prefix: Optional prefix to add to Braintrust group names
            group_name_suffix: Optional suffix to add to Braintrust group names
        """
        super().__init__(okta_client, braintrust_clients, state_manager)
        
        self.sync_group_memberships = sync_group_memberships
        self.group_name_prefix = group_name_prefix or ""
        self.group_name_suffix = group_name_suffix or ""
        
        self._logger = logger.bind(
            syncer_type="GroupSyncer",
            sync_memberships=sync_group_memberships,
        )
    
    @property
    def resource_type(self) -> str:
        return "group"
    
    async def get_okta_resources(
        self,
        filter_expr: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[OktaGroup]:
        """Get groups from Okta.
        
        Args:
            filter_expr: Optional SCIM filter expression
            limit: Maximum number of groups to retrieve
            
        Returns:
            List of Okta groups
        """
        try:
            self._logger.debug(
                "Retrieving Okta groups",
                filter_expr=filter_expr,
                limit=limit,
            )
            
            if filter_expr:
                groups = await self.okta_client.search_groups(filter_expr, limit=limit)
            else:
                groups = await self.okta_client.list_groups(limit=limit)
            
            self._logger.info(
                "Retrieved Okta groups",
                count=len(groups),
                filter_applied=filter_expr is not None,
            )
            
            return groups
            
        except Exception as e:
            self._logger.error("Failed to retrieve Okta groups", error=str(e))
            raise
    
    async def get_braintrust_resources(
        self,
        braintrust_org: str,
        limit: Optional[int] = None,
    ) -> List[BraintrustGroup]:
        """Get groups from Braintrust organization.
        
        Args:
            braintrust_org: Braintrust organization name
            limit: Maximum number of groups to retrieve
            
        Returns:
            List of Braintrust groups
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        try:
            client = self.braintrust_clients[braintrust_org]
            
            self._logger.debug(
                "Retrieving Braintrust groups",
                braintrust_org=braintrust_org,
                limit=limit,
            )
            
            groups = await client.list_groups(limit=limit)
            
            self._logger.info(
                "Retrieved Braintrust groups",
                braintrust_org=braintrust_org,
                count=len(groups),
            )
            
            return groups
            
        except Exception as e:
            self._logger.error(
                "Failed to retrieve Braintrust groups",
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
    async def create_braintrust_resource(
        self,
        okta_resource: OktaGroup,
        braintrust_org: str,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> BraintrustGroup:
        """Create a new group in Braintrust.
        
        Args:
            okta_resource: Source Okta group
            braintrust_org: Target Braintrust organization
            additional_data: Additional data for group creation
            
        Returns:
            Created Braintrust group
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        try:
            client = self.braintrust_clients[braintrust_org]
            
            # Extract group information from Okta group
            group_data = self._extract_group_data(okta_resource)
            
            # Apply additional data if provided
            if additional_data:
                group_data.update(additional_data)
            
            self._logger.debug(
                "Creating Braintrust group",
                okta_group_id=okta_resource.id,
                group_name=group_data["name"],
                braintrust_org=braintrust_org,
                member_count=len(group_data.get("member_users", [])),
            )
            
            # Create group without members first
            braintrust_group = await client.create_group(
                name=group_data["name"],
                description=group_data.get("description"),
                member_users=[],  # Add members separately to handle dependency resolution
                member_groups=[],
            )
            
            # Add members if requested and available
            if self.sync_group_memberships and group_data.get("member_users"):
                try:
                    braintrust_group = await self._sync_group_members(
                        braintrust_group.id,
                        okta_resource,
                        braintrust_org,
                        target_member_users=group_data["member_users"],
                    )
                except Exception as e:
                    self._logger.warning(
                        "Group created but failed to sync members",
                        braintrust_group_id=braintrust_group.id,
                        okta_group_id=okta_resource.id,
                        error=str(e),
                    )
            
            self._logger.info(
                "Created Braintrust group",
                okta_group_id=okta_resource.id,
                braintrust_group_id=braintrust_group.id,
                group_name=group_data["name"],
                braintrust_org=braintrust_org,
            )
            
            return braintrust_group
            
        except Exception as e:
            self._logger.error(
                "Failed to create Braintrust group",
                okta_group_id=okta_resource.id,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
    async def update_braintrust_resource(
        self,
        braintrust_resource_id: str,
        okta_resource: OktaGroup,
        braintrust_org: str,
        updates: Dict[str, Any],
    ) -> BraintrustGroup:
        """Update an existing group in Braintrust.
        
        Args:
            braintrust_resource_id: Braintrust group ID
            okta_resource: Source Okta group
            braintrust_org: Target Braintrust organization
            updates: Fields to update
            
        Returns:
            Updated Braintrust group
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        try:
            client = self.braintrust_clients[braintrust_org]
            
            self._logger.debug(
                "Updating Braintrust group",
                braintrust_group_id=braintrust_resource_id,
                okta_group_id=okta_resource.id,
                updates=list(updates.keys()),
                braintrust_org=braintrust_org,
            )
            
            # Handle membership updates separately
            member_updates = {}
            basic_updates = {}
            
            for key, value in updates.items():
                if key in ["member_users", "member_groups"]:
                    member_updates[key] = value
                else:
                    basic_updates[key] = value
            
            # Update basic fields first
            braintrust_group = None
            if basic_updates:
                braintrust_group = await client.update_group(braintrust_resource_id, basic_updates)
            
            # Update memberships if requested
            if self.sync_group_memberships and member_updates:
                braintrust_group = await self._sync_group_members(
                    braintrust_resource_id,
                    okta_resource,
                    braintrust_org,
                    target_member_users=member_updates.get("member_users"),
                    target_member_groups=member_updates.get("member_groups"),
                )
            
            # If no updates were made, get current group
            if braintrust_group is None:
                braintrust_group = await client.get_group(braintrust_resource_id)
            
            self._logger.info(
                "Updated Braintrust group",
                braintrust_group_id=braintrust_resource_id,
                okta_group_id=okta_resource.id,
                updated_fields=list(updates.keys()),
                braintrust_org=braintrust_org,
            )
            
            return braintrust_group
            
        except Exception as e:
            self._logger.error(
                "Failed to update Braintrust group",
                braintrust_group_id=braintrust_resource_id,
                okta_group_id=okta_resource.id,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
    def get_resource_identifier(self, resource: OktaGroup) -> str:
        """Get unique identifier for an Okta group.
        
        Args:
            resource: Okta group (may be dict or object)
            
        Returns:
            Unique identifier (group name)
        """
        # Handle both dict and object formats
        if isinstance(resource, dict):
            profile = resource.get("profile", {})
            return profile.get("name", "")
        else:
            # For OktaGroup objects, profile is a dictionary
            return resource.profile.get("name", "")
    
    def get_braintrust_resource_identifier(self, resource: BraintrustGroup) -> str:
        """Get unique identifier for a Braintrust group.
        
        Args:
            resource: Braintrust group (may be dict or object)
            
        Returns:
            Unique identifier (group name)
        """
        # Handle both dict and object formats
        if isinstance(resource, dict):
            return resource.get('name', '') or resource.get('id', '')
        else:
            # Braintrust groups have name as a direct attribute, not under profile
            return getattr(resource, 'name', '') or getattr(resource, 'id', '')
    
    def should_sync_resource(
        self,
        okta_resource: OktaGroup,
        braintrust_org: str,
        sync_rules: Dict[str, Any],
    ) -> bool:
        """Check if group should be synced to the given organization.
        
        Args:
            okta_resource: Okta group to check (may be dict or object)
            braintrust_org: Target Braintrust organization
            sync_rules: Sync rules configuration
            
        Returns:
            True if group should be synced
        """
        try:
            # Helper to safely get group name
            def get_group_name():
                if isinstance(okta_resource, dict):
                    profile = okta_resource.get("profile", {})
                    return profile.get("name", "")
                else:
                    return okta_resource.profile.get("name", "")
            
            # Helper to safely get group ID
            def get_group_id():
                if isinstance(okta_resource, dict):
                    return okta_resource.get("id", "")
                else:
                    return okta_resource.id
            
            group_name = get_group_name()
            group_id = get_group_id()
            # Check group type filters
            group_type_filters = sync_rules.get("group_type_filters", {}).get(braintrust_org)
            if group_type_filters:
                group_type = getattr(okta_resource, "type", "OKTA_GROUP")
                
                include_types = group_type_filters.get("include", [])
                if include_types and group_type not in include_types:
                    self._logger.debug(
                        "Group type not in include list",
                        group_id=group_id,
                        group_name=group_name,
                        group_type=group_type,
                        include_types=include_types,
                        braintrust_org=braintrust_org,
                    )
                    return False
                
                exclude_types = group_type_filters.get("exclude", [])
                if exclude_types and group_type in exclude_types:
                    self._logger.debug(
                        "Group type in exclude list",
                        group_id=group_id,
                        group_name=group_name,
                        group_type=group_type,
                        exclude_types=exclude_types,
                        braintrust_org=braintrust_org,
                    )
                    return False
            
            # Check group name patterns
            name_patterns = sync_rules.get("group_name_patterns", {}).get(braintrust_org)
            if name_patterns:
                
                # Include patterns - if specified, group name must match at least one
                include_patterns = name_patterns.get("include", [])
                if include_patterns:
                    import re
                    if not any(re.search(pattern, group_name) for pattern in include_patterns):
                        self._logger.debug(
                            "Group name doesn't match include patterns",
                            group_id=group_id,
                            group_name=group_name,
                            include_patterns=include_patterns,
                            braintrust_org=braintrust_org,
                        )
                        return False
                
                # Exclude patterns - if group name matches any exclude pattern, skip
                exclude_patterns = name_patterns.get("exclude", [])
                if exclude_patterns:
                    import re
                    if any(re.search(pattern, group_name) for pattern in exclude_patterns):
                        self._logger.debug(
                            "Group name matches exclude pattern",
                            group_id=group_id,
                            group_name=group_name,
                            exclude_patterns=exclude_patterns,
                            braintrust_org=braintrust_org,
                        )
                        return False
            
            # Check minimum member count
            min_members = sync_rules.get("min_group_members", {}).get(braintrust_org, 0)
            if min_members > 0:
                # Get group members if available
                member_count = len(getattr(okta_resource, "members", []))
                if member_count < min_members:
                    self._logger.debug(
                        "Group has too few members",
                        group_id=okta_resource.id,
                        group_name=okta_resource.profile.name,
                        member_count=member_count,
                        min_members=min_members,
                        braintrust_org=braintrust_org,
                    )
                    return False
            
            # Check custom profile attribute filters
            profile_filters = sync_rules.get("group_profile_filters", {}).get(braintrust_org)
            if profile_filters:
                for attr_name, expected_values in profile_filters.items():
                    # Handle both dict and object formats for profile attribute access
                    if isinstance(okta_resource, dict):
                        profile = okta_resource.get("profile", {})
                        group_value = profile.get(attr_name)
                    else:
                        group_value = okta_resource.profile.get(attr_name)
                        
                    if group_value not in expected_values:
                        self._logger.debug(
                            "Group profile attribute doesn't match filter",
                            group_id=group_id,
                            group_name=group_name,
                            attribute=attr_name,
                            group_value=group_value,
                            expected_values=expected_values,
                            braintrust_org=braintrust_org,
                        )
                        return False
            
            return True
            
        except Exception as e:
            # Safe access for error logging
            group_id = (
                okta_resource.get("id") if isinstance(okta_resource, dict)
                else okta_resource.id
            )
            group_name = (
                okta_resource.get("profile", {}).get("name", "") if isinstance(okta_resource, dict)
                else okta_resource.profile.get("name", "")
            )
            self._logger.warning(
                "Error checking group sync rules, defaulting to sync",
                group_id=group_id,
                group_name=group_name,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            return True
    
    def calculate_updates(
        self,
        okta_resource: OktaGroup,
        braintrust_resource: BraintrustGroup,
    ) -> Dict[str, Any]:
        """Calculate what updates are needed for a Braintrust group.
        
        Args:
            okta_resource: Source Okta group
            braintrust_resource: Existing Braintrust group
            
        Returns:
            Dictionary of fields that need updating
        """
        updates = {}
        
        try:
            # Extract current Okta group data
            okta_data = self._extract_group_data(okta_resource)
            
            # Compare group name
            if okta_data["name"] != getattr(braintrust_resource, "name", ""):
                updates["name"] = okta_data["name"]
            
            # Compare description
            okta_description = okta_data.get("description", "")
            braintrust_description = getattr(braintrust_resource, "description", "") or ""
            if okta_description != braintrust_description:
                updates["description"] = okta_description
            
            # Compare membership if enabled
            if self.sync_group_memberships:
                current_members = set(getattr(braintrust_resource, "member_users", []) or [])
                target_members = set(okta_data.get("member_users", []))
                
                if current_members != target_members:
                    updates["member_users"] = list(target_members)
                
                # Handle nested groups if supported
                current_groups = set(getattr(braintrust_resource, "member_groups", []) or [])
                target_groups = set(okta_data.get("member_groups", []))
                
                if current_groups != target_groups:
                    updates["member_groups"] = list(target_groups)
            
            # Safe access for logging
            okta_group_id = (
                okta_resource.get("id") if isinstance(okta_resource, dict)
                else okta_resource.id
            )
            braintrust_group_id = (
                braintrust_resource.get("id", "unknown") if isinstance(braintrust_resource, dict)
                else getattr(braintrust_resource, "id", "unknown")
            )
            
            self._logger.debug(
                "Calculated group updates",
                okta_group_id=okta_group_id,
                braintrust_group_id=braintrust_group_id,
                updates=list(updates.keys()),
            )
            
            return updates
            
        except Exception as e:
            self._logger.error(
                "Failed to calculate group updates",
                okta_group_id=okta_resource.id,
                braintrust_group_id=getattr(braintrust_resource, "id", "unknown"),
                error=str(e),
            )
            return {}
    
    def _extract_group_data(self, okta_group: OktaGroup) -> Dict[str, Any]:
        """Extract group data from Okta group for Braintrust creation/update.
        
        Args:
            okta_group: Okta group object (may be dict or object)
            
        Returns:
            Dictionary with group data for Braintrust
        """
        # Handle both dict and object formats
        if isinstance(okta_group, dict):
            profile = okta_group.get("profile", {})
            group_name = profile.get("name", "")
            description = profile.get("description", "")
        else:
            group_name = okta_group.profile.get("name", "")
            description = okta_group.profile.get("description", "")
        
        # Generate Braintrust group name with prefix/suffix
        braintrust_name = f"{self.group_name_prefix}{group_name}{self.group_name_suffix}"
        
        group_data = {
            "name": braintrust_name,
            "description": description or f"Synced from Okta group: {group_name}",
        }
        
        # Add member information if available and membership sync is enabled
        if self.sync_group_memberships:
            # Get members from the group object if available
            members = getattr(okta_group, "members", [])
            if members:
                # Extract user emails/identifiers for Braintrust user lookup
                member_users = []
                for member in members:
                    if hasattr(member, "profile") and hasattr(member.profile, "email"):
                        member_users.append(member.profile.email)
                    elif isinstance(member, dict) and "email" in member:
                        member_users.append(member["email"])
                    elif hasattr(member, "email"):
                        member_users.append(member.email)
                
                group_data["member_users"] = member_users
        
        return group_data
    
    async def _sync_group_members(
        self,
        braintrust_group_id: str,
        okta_group: OktaGroup,
        braintrust_org: str,
        target_member_users: Optional[List[str]] = None,
        target_member_groups: Optional[List[str]] = None,
    ) -> BraintrustGroup:
        """Sync group memberships with Braintrust.
        
        Args:
            braintrust_group_id: Braintrust group ID
            okta_group: Source Okta group
            braintrust_org: Braintrust organization name
            target_member_users: Target user list (emails)
            target_member_groups: Target group list (names)
            
        Returns:
            Updated Braintrust group
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        client = self.braintrust_clients[braintrust_org]
        
        try:
            # Get current group to see existing members
            current_group = await client.get_group(braintrust_group_id)
            current_user_ids = set(getattr(current_group, "member_users", []) or [])
            current_group_ids = set(getattr(current_group, "member_groups", []) or [])
            
            # Convert target user emails to Braintrust user IDs
            target_user_ids = set()
            if target_member_users:
                for email in target_member_users:
                    # Try to find the user in Braintrust
                    bt_user = await client.find_user_by_email(email)
                    if bt_user:
                        target_user_ids.add(bt_user.id)
                    else:
                        # Check if user exists in our state mappings
                        current_state = self.state_manager.get_current_state()
                        if current_state:
                            bt_user_id = current_state.get_braintrust_id(email, braintrust_org, "user")
                            if bt_user_id:
                                target_user_ids.add(bt_user_id)
                            else:
                                self._logger.warning(
                                    "User not found in Braintrust for group membership",
                                    user_email=email,
                                    braintrust_group_id=braintrust_group_id,
                                    braintrust_org=braintrust_org,
                                )
            
            # Convert target group names to Braintrust group IDs
            target_group_ids = set()
            if target_member_groups:
                for group_name in target_member_groups:
                    # Try to find the group in Braintrust
                    bt_group = await client.find_group_by_name(group_name)
                    if bt_group:
                        target_group_ids.add(bt_group.id)
                    else:
                        # Check if group exists in our state mappings
                        current_state = self.state_manager.get_current_state()
                        if current_state:
                            bt_group_id = current_state.get_braintrust_id(group_name, braintrust_org, "group")
                            if bt_group_id:
                                target_group_ids.add(bt_group_id)
                            else:
                                self._logger.warning(
                                    "Group not found in Braintrust for nested membership",
                                    group_name=group_name,
                                    braintrust_group_id=braintrust_group_id,
                                    braintrust_org=braintrust_org,
                                )
            
            # Calculate membership changes
            users_to_add = target_user_ids - current_user_ids
            users_to_remove = current_user_ids - target_user_ids
            groups_to_add = target_group_ids - current_group_ids
            groups_to_remove = current_group_ids - target_group_ids
            
            # Apply membership changes
            updated_group = current_group
            
            if users_to_add or groups_to_add:
                updated_group = await client.add_group_members(
                    braintrust_group_id,
                    user_ids=list(users_to_add) if users_to_add else None,
                    group_ids=list(groups_to_add) if groups_to_add else None,
                )
                
                self._logger.debug(
                    "Added group members",
                    braintrust_group_id=braintrust_group_id,
                    users_added=len(users_to_add),
                    groups_added=len(groups_to_add),
                )
            
            if users_to_remove or groups_to_remove:
                updated_group = await client.remove_group_members(
                    braintrust_group_id,
                    user_ids=list(users_to_remove) if users_to_remove else None,
                    group_ids=list(groups_to_remove) if groups_to_remove else None,
                )
                
                self._logger.debug(
                    "Removed group members",
                    braintrust_group_id=braintrust_group_id,
                    users_removed=len(users_to_remove),
                    groups_removed=len(groups_to_remove),
                )
            
            return updated_group
            
        except Exception as e:
            self._logger.error(
                "Failed to sync group members",
                braintrust_group_id=braintrust_group_id,
                okta_group_id=okta_group.id,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            raise
    
    async def find_braintrust_group_by_name(
        self,
        name: str,
        braintrust_org: str,
    ) -> Optional[BraintrustGroup]:
        """Find a Braintrust group by name.
        
        Args:
            name: Group name to search for (with prefix/suffix applied)
            braintrust_org: Braintrust organization name
            
        Returns:
            Braintrust group if found, None otherwise
        """
        if braintrust_org not in self.braintrust_clients:
            return None
        
        try:
            client = self.braintrust_clients[braintrust_org]
            # Apply prefix/suffix to match how groups are created
            search_name = f"{self.group_name_prefix}{name}{self.group_name_suffix}"
            return await client.find_group_by_name(search_name)
        except Exception as e:
            self._logger.warning(
                "Error searching for Braintrust group by name",
                name=name,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            return None