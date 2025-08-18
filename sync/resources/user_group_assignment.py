"""User group assignment functionality for accepted invitations."""

import re
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta

import structlog
from braintrust_api.types import User as BraintrustUser

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient, OktaUser
from sync.core.state import StateManager
from sync.config.group_assignment_models import (
    GroupAssignmentConfig,
    MappingStrategy,
    AttributeRule,
)

logger = structlog.get_logger(__name__)


class UserGroupAssignmentManager:
    """Manages group assignments for users who have accepted invitations."""
    
    def __init__(
        self,
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
        group_assignment_config: Optional[Dict[str, GroupAssignmentConfig]] = None,
    ) -> None:
        """Initialize user group assignment manager.
        
        Args:
            okta_client: Okta API client
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
            group_assignment_config: Optional group assignment configuration per org
        """
        self.okta_client = okta_client
        self.braintrust_clients = braintrust_clients
        self.state_manager = state_manager
        self.group_assignment_config = group_assignment_config or {}
        
        self._logger = logger.bind(
            component="UserGroupAssignmentManager",
        )
    
    async def check_and_assign_groups(
        self,
        braintrust_org: str,
        check_window_hours: int = 24,
    ) -> Dict[str, Any]:
        """Check for accepted invitations and assign users to groups.
        
        Args:
            braintrust_org: Braintrust organization to check
            check_window_hours: Only check invitations sent within this time window
            
        Returns:
            Dictionary with assignment results
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        client = self.braintrust_clients[braintrust_org]
        results = {
            "checked_users": 0,
            "accepted_users": 0,
            "assigned_users": 0,
            "errors": [],
        }
        
        try:
            # Get active users from Okta that should be in this Braintrust org
            # This focuses on users we expect to manage, not all Braintrust users
            okta_active_users = await self.okta_client.search_users('status eq "ACTIVE"')
            
            if not okta_active_users:
                self._logger.info(
                    "No active users found in Okta",
                    braintrust_org=braintrust_org,
                )
                return results
            
            results["checked_users"] = len(okta_active_users)
            
            # Check each Okta user to see if they're in Braintrust and need group assignments
            for okta_user in okta_active_users:
                user_email = self._get_user_email(okta_user)
                if not user_email:
                    continue
                
                # Check if this user exists in Braintrust (meaning they accepted)
                bt_user = await client.find_user_by_email(user_email)
                if bt_user:
                    # This user has accepted (they're in Braintrust)
                    results["accepted_users"] += 1
                    
                    self._logger.debug(
                        "Found accepted user in Braintrust",
                        email=user_email,
                        braintrust_org=braintrust_org,
                    )
                    
                    # Check if they need group assignments
                    assigned = await self._assign_user_to_groups(
                        user_email=user_email,
                        bt_user=bt_user,
                        braintrust_org=braintrust_org,
                        okta_user=okta_user,
                    )
                    if assigned:
                        results["assigned_users"] += 1
                else:
                    self._logger.debug(
                        "Okta user not found in Braintrust (invitation not accepted yet)",
                        email=user_email,
                        braintrust_org=braintrust_org,
                    )
            
            self._logger.info(
                "Group assignment check completed",
                braintrust_org=braintrust_org,
                **results,
            )
            
        except Exception as e:
            self._logger.error(
                "Error during group assignment check",
                braintrust_org=braintrust_org,
                error=str(e),
            )
            results["errors"].append(str(e))
        
        return results
    
    def _get_user_email(self, okta_user: OktaUser) -> str:
        """Get email from Okta user object."""
        if hasattr(okta_user, 'profile'):
            return okta_user.profile.get('email', '') if isinstance(okta_user.profile, dict) else ''
        elif isinstance(okta_user, dict):
            return okta_user.get('profile', {}).get('email', '')
        return ''
    
    def _get_group_mappings_from_state(self, braintrust_org: str) -> Dict[str, str]:
        """Get mapping of Okta group IDs to Braintrust group names from state.
        
        Args:
            braintrust_org: Braintrust organization name
            
        Returns:
            Dictionary mapping Okta group ID -> Braintrust group name
        """
        mappings = {}
        
        # Load persistent mappings from state
        try:
            persistent_mappings = self.state_manager._load_persistent_mappings()
            
            for mapping_key, mapping in persistent_mappings.items():
                if (mapping.resource_type == "group" and 
                    mapping.braintrust_org == braintrust_org):
                    # The mapping_key has format "GroupName:org:group", extract just the group name
                    group_name = mapping_key.split(':')[0] if ':' in mapping_key else mapping_key
                    mappings[mapping.okta_id] = group_name
            
            self._logger.debug(
                "Loaded group mappings from state",
                braintrust_org=braintrust_org,
                mapping_count=len(mappings),
                mappings=mappings,
            )
            
        except Exception as e:
            self._logger.warning(
                "Could not load group mappings from state",
                braintrust_org=braintrust_org,
                error=str(e),
            )
        
        return mappings
    
    async def _assign_user_to_groups(
        self,
        user_email: str,
        bt_user: BraintrustUser,
        braintrust_org: str,
        okta_user: Optional[OktaUser] = None,
    ) -> bool:
        """Assign user to appropriate groups based on Okta data.
        
        Args:
            user_email: User's email address
            bt_user: Braintrust user object
            braintrust_org: Braintrust organization
            okta_user: Okta user object
            
        Returns:
            True if groups were assigned successfully
        """
        try:
            client = self.braintrust_clients[braintrust_org]
            
            # Get user's Okta data to determine groups
            if okta_user is None:
                okta_user = await self._get_okta_user_by_email(user_email)
                if not okta_user:
                    self._logger.warning(
                        "Could not find Okta user for group assignment",
                        email=user_email,
                    )
                    return False
            
            # Determine which groups the user should be in
            target_groups = await self._determine_user_groups(okta_user, braintrust_org)
            
            self._logger.debug(
                "Determined target groups for user",
                email=user_email,
                target_groups=target_groups,
                braintrust_org=braintrust_org,
            )
            
            if not target_groups:
                self._logger.info(
                    "No groups to assign for user",
                    email=user_email,
                    braintrust_org=braintrust_org,
                )
                return False
            
            # Get user ID
            user_id = bt_user.id if hasattr(bt_user, 'id') else bt_user.get('id')
            if not user_id:
                self._logger.error(
                    "Could not get user ID for group assignment",
                    email=user_email,
                )
                return False
            
            # Add user to each group
            assigned_groups = []
            for group_name in target_groups:
                group = await client.find_group_by_name(group_name)
                if group:
                    group_id = group.id if hasattr(group, 'id') else group.get('id')
                    if group_id:
                        await client.add_group_members(
                            group_id=group_id,
                            user_ids=[user_id],
                        )
                        assigned_groups.append(group_name)
                elif self._should_auto_create_group(braintrust_org):
                    # Create group if auto-create is enabled
                    self._logger.info(
                        "Creating new group in Braintrust",
                        group_name=group_name,
                        braintrust_org=braintrust_org,
                    )
                    # TODO: Implement group creation
                    # new_group = await client.create_group(name=group_name)
                    # if new_group:
                    #     await client.add_group_members(...)
            
            self._logger.info(
                "Assigned user to groups",
                email=user_email,
                groups=assigned_groups,
                braintrust_org=braintrust_org,
            )
            
            return len(assigned_groups) > 0
            
        except Exception as e:
            self._logger.error(
                "Failed to assign user to groups",
                email=user_email,
                braintrust_org=braintrust_org,
                error=str(e),
            )
            return False
    
    async def _get_okta_user_by_email(self, email: str) -> Optional[OktaUser]:
        """Get Okta user by email address.
        
        Args:
            email: User's email address
            
        Returns:
            Okta user if found, None otherwise
        """
        try:
            users = await self.okta_client.search_users(f'profile.email eq "{email}"')
            return users[0] if users else None
        except Exception as e:
            self._logger.error(
                "Failed to get Okta user by email",
                email=email,
                error=str(e),
            )
            return None
    
    def _should_auto_create_group(self, braintrust_org: str) -> bool:
        """Check if auto-creation of groups is enabled for this org.
        
        Args:
            braintrust_org: Braintrust organization name
            
        Returns:
            True if auto-create is enabled
        """
        config = self.group_assignment_config.get(braintrust_org)
        return config.auto_create_groups if config else False
    
    def _is_group_excluded(self, group_name: str, exclude_patterns: List[str]) -> bool:
        """Check if a group name matches any exclusion pattern.
        
        Args:
            group_name: Group name to check
            exclude_patterns: List of regex patterns for exclusion
            
        Returns:
            True if the group should be excluded
        """
        for pattern in exclude_patterns:
            try:
                if re.match(pattern, group_name):
                    return True
            except re.error:
                self._logger.warning(
                    "Invalid regex pattern in exclude_groups",
                    pattern=pattern,
                )
        return False
    
    async def _determine_user_groups(
        self,
        okta_user: OktaUser,
        braintrust_org: str,
    ) -> List[str]:
        """Determine which groups a user should be assigned to using configuration.
        
        Args:
            okta_user: Okta user object
            braintrust_org: Braintrust organization
            
        Returns:
            List of group names to assign
        """
        groups = []
        
        # Get configuration for this org
        config = self.group_assignment_config.get(braintrust_org)
        if not config:
            self._logger.warning(
                "No group assignment configuration for org, using defaults",
                braintrust_org=braintrust_org,
            )
            return []
        
        # Get user's profile attributes
        profile = okta_user.profile if hasattr(okta_user, 'profile') else okta_user.get('profile', {})
        
        # ========== Process based on strategy ==========
        if config.strategy == MappingStrategy.OKTA_GROUPS:
            groups.extend(await self._process_okta_groups_strategy(okta_user, config, braintrust_org))
        
        elif config.strategy == MappingStrategy.ATTRIBUTES:
            groups.extend(self._process_attributes_strategy(profile, config))
        
        elif config.strategy == MappingStrategy.HYBRID:
            # Process both strategies based on hybrid mode
            okta_groups = await self._process_okta_groups_strategy(okta_user, config, braintrust_org)
            attr_groups = self._process_attributes_strategy(profile, config)
            
            if config.hybrid_mode == "merge":
                groups.extend(okta_groups)
                groups.extend(attr_groups)
            elif config.hybrid_mode == "attributes_first":
                groups.extend(attr_groups or okta_groups)
            elif config.hybrid_mode == "groups_first":
                groups.extend(okta_groups or attr_groups)
        
        # ========== Add default groups ==========
        if config.default_groups:
            groups.extend(config.default_groups)
        
        # ========== Remove duplicates and apply limits ==========
        seen = set()
        unique_groups = []
        for group in groups:
            if group not in seen:
                seen.add(group)
                unique_groups.append(group)
        
        # Apply max groups limit if configured
        if config.max_groups_per_user and len(unique_groups) > config.max_groups_per_user:
            self._logger.warning(
                "User exceeds max groups limit, truncating",
                user_email=self._get_user_email(okta_user),
                max_groups=config.max_groups_per_user,
                actual_groups=len(unique_groups),
            )
            unique_groups = unique_groups[:config.max_groups_per_user]
        
        return unique_groups
    
    async def _process_okta_groups_strategy(
        self,
        okta_user: OktaUser,
        config: GroupAssignmentConfig,
        braintrust_org: str,
    ) -> List[str]:
        """Process Okta groups strategy to determine group assignments.
        
        Args:
            okta_user: Okta user object
            config: Group assignment configuration
            braintrust_org: Braintrust organization
            
        Returns:
            List of group names based on Okta groups
        """
        groups = []
        
        try:
            # Get user's Okta groups
            okta_groups = await self.okta_client.get_user_groups(
                okta_user.id if hasattr(okta_user, 'id') else okta_user.get('id')
            )
            
            for okta_group in okta_groups:
                # Get Okta group name
                if hasattr(okta_group, 'profile'):
                    group_profile = okta_group.profile
                    if hasattr(group_profile, 'name'):
                        okta_group_name = group_profile.name
                    else:
                        okta_group_name = group_profile.get('name') if isinstance(group_profile, dict) else None
                else:
                    okta_group_name = okta_group.get('profile', {}).get('name') if isinstance(okta_group, dict) else None
                
                if not okta_group_name:
                    continue
                
                # Check if group is excluded
                if config.exclude_groups and self._is_group_excluded(okta_group_name, config.exclude_groups):
                    self._logger.debug(
                        "Skipping excluded Okta group",
                        okta_group_name=okta_group_name,
                    )
                    continue
                
                # Apply mappings if configured
                mapped_name = None
                if config.okta_group_mappings:
                    for mapping in config.okta_group_mappings:
                        if mapping.okta_group_name and mapping.okta_group_name == okta_group_name:
                            mapped_name = mapping.braintrust_group_name
                            break
                        elif mapping.okta_group_pattern:
                            try:
                                if re.match(mapping.okta_group_pattern, okta_group_name):
                                    mapped_name = mapping.braintrust_group_name
                                    break
                            except re.error:
                                self._logger.warning(
                                    "Invalid regex pattern in okta_group_pattern",
                                    pattern=mapping.okta_group_pattern,
                                )
                
                # Use mapped name or original name based on config
                if mapped_name:
                    groups.append(mapped_name)
                elif config.sync_group_names:
                    groups.append(okta_group_name)
                
        except Exception as e:
            self._logger.warning(
                "Could not get Okta groups for user",
                user_id=okta_user.id if hasattr(okta_user, 'id') else okta_user.get('id'),
                error=str(e),
            )
        
        return groups
    
    def _process_attributes_strategy(
        self,
        profile: Dict[str, Any],
        config: GroupAssignmentConfig,
    ) -> List[str]:
        """Process attributes strategy to determine group assignments.
        
        Args:
            profile: User's Okta profile attributes
            config: Group assignment configuration
            
        Returns:
            List of group names based on attributes
        """
        groups = []
        
        if not config.attribute_mappings:
            return groups
        
        # Sort mappings by priority (higher first)
        sorted_mappings = sorted(
            config.attribute_mappings,
            key=lambda x: x.priority,
            reverse=True
        )
        
        # Check each mapping rule
        for mapping in sorted_mappings:
            if mapping.rule.matches(profile):
                groups.append(mapping.braintrust_group_name)
                self._logger.debug(
                    "User matches attribute rule",
                    group=mapping.braintrust_group_name,
                    priority=mapping.priority,
                )
        
        return groups
    
    async def assign_groups_on_sync(
        self,
        okta_user: OktaUser,
        braintrust_org: str,
        group_names: Optional[List[str]] = None,
    ) -> List[str]:
        """Assign groups during initial user sync/invitation.
        
        This method can be called during the invitation process to specify
        which groups the user should be added to when they accept.
        
        Args:
            okta_user: Okta user being synced
            braintrust_org: Target Braintrust organization
            group_names: Optional specific groups, otherwise determine automatically
            
        Returns:
            List of group names that will be assigned
        """
        if group_names is None:
            # Determine groups automatically based on configuration
            group_names = await self._determine_user_groups(okta_user, braintrust_org)
        
        return group_names