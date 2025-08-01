"""User group assignment functionality for accepted invitations."""

from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta

import structlog
from braintrust_api.types import User as BraintrustUser

from sync.clients.braintrust import BraintrustClient
from sync.clients.okta import OktaClient, OktaUser
from sync.core.state import StateManager

logger = structlog.get_logger(__name__)


class UserGroupAssignmentManager:
    """Manages group assignments for users who have accepted invitations."""
    
    def __init__(
        self,
        okta_client: OktaClient,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
    ) -> None:
        """Initialize user group assignment manager.
        
        Args:
            okta_client: Okta API client
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
        """
        self.okta_client = okta_client
        self.braintrust_clients = braintrust_clients
        self.state_manager = state_manager
        
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
                        invitation_data={},  # No invitation data available without state tracking
                        okta_user=okta_user,  # Pass the Okta user data
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
    
    async def _get_pending_invitations(
        self,
        braintrust_org: str,
        cutoff_time: datetime,
    ) -> List[Dict[str, Any]]:
        """Get pending invitations from state.
        
        Args:
            braintrust_org: Braintrust organization
            cutoff_time: Only get invitations after this time
            
        Returns:
            List of pending invitation records
        """
        # This would query the state manager for invitations
        # For now, returning empty list as state tracking needs enhancement
        # TODO: Implement state query for pending invitations
        return []
    
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
        invitation_data: Dict[str, Any],
        okta_user: Optional[OktaUser] = None,
    ) -> bool:
        """Assign user to appropriate groups based on Okta data.
        
        Args:
            user_email: User's email address
            bt_user: Braintrust user object
            braintrust_org: Braintrust organization
            invitation_data: Original invitation data
            
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
    
    async def _determine_user_groups(
        self,
        okta_user: OktaUser,
        braintrust_org: str,
    ) -> List[str]:
        """Determine which groups a user should be assigned to.
        
        Args:
            okta_user: Okta user object
            braintrust_org: Braintrust organization
            
        Returns:
            List of group names to assign
        """
        groups = []
        
        # Get user's profile attributes
        profile = okta_user.profile if hasattr(okta_user, 'profile') else okta_user.get('profile', {})
        
        # Example logic - customize based on your needs:
        
        # 1. Department-based groups
        department = profile.get('department', '').lower()
        if department:
            # Map departments to Braintrust groups
            dept_group_mapping = {
                'engineering': 'Engineering Team',
                'product': 'Product Team',
                'sales': 'Sales Team',
                'marketing': 'Marketing Team',
            }
            if department in dept_group_mapping:
                groups.append(dept_group_mapping[department])
        
        # 2. Role-based groups
        title = profile.get('title', '').lower()
        if 'manager' in title:
            groups.append('Managers')
        if 'engineer' in title or 'developer' in title:
            groups.append('Developers')
        
        # 3. Location-based groups
        location = profile.get('location', '').lower()
        if location:
            groups.append(f"Location - {location.title()}")
        
        # 4. Get Okta groups for user and map to Braintrust groups using state
        try:
            okta_groups = await self.okta_client.get_user_groups(
                okta_user.id if hasattr(okta_user, 'id') else okta_user.get('id')
            )
            
            # Get group mappings from state to find corresponding Braintrust group names
            okta_to_braintrust_groups = self._get_group_mappings_from_state(braintrust_org)
            
            for okta_group in okta_groups:
                # Get Okta group ID and name for debugging
                okta_group_id = okta_group.id if hasattr(okta_group, 'id') else okta_group.get('id')
                okta_group_name = None
                if hasattr(okta_group, 'profile'):
                    group_profile = okta_group.profile
                    if hasattr(group_profile, 'name'):
                        okta_group_name = group_profile.name
                    else:
                        okta_group_name = group_profile.get('name') if isinstance(group_profile, dict) else None
                else:
                    okta_group_name = okta_group.get('profile', {}).get('name') if isinstance(okta_group, dict) else None
                
                self._logger.debug(
                    "Processing Okta group",
                    okta_group_id=okta_group_id,
                    okta_group_name=okta_group_name,
                    available_mappings=list(okta_to_braintrust_groups.keys()),
                )
                
                # Try matching by group ID first
                if okta_group_id in okta_to_braintrust_groups:
                    braintrust_group_name = okta_to_braintrust_groups[okta_group_id]
                    groups.append(braintrust_group_name)
                    self._logger.debug(
                        "Matched by group ID",
                        okta_group_id=okta_group_id,
                        braintrust_group_name=braintrust_group_name,
                    )
                # Try matching by group name as fallback
                elif okta_group_name and okta_group_name in okta_to_braintrust_groups:
                    braintrust_group_name = okta_to_braintrust_groups[okta_group_name]
                    groups.append(braintrust_group_name)
                    self._logger.debug(
                        "Matched by group name",
                        okta_group_name=okta_group_name,
                        braintrust_group_name=braintrust_group_name,
                    )
                else:
                    self._logger.debug(
                        "No mapping found for Okta group",
                        okta_group_id=okta_group_id,
                        okta_group_name=okta_group_name,
                    )
        except Exception as e:
            self._logger.warning(
                "Could not get Okta groups for user",
                user_id=okta_user.id if hasattr(okta_user, 'id') else okta_user.get('id'),
                error=str(e),
            )
        
        # Remove duplicates while preserving order
        seen = set()
        unique_groups = []
        for group in groups:
            if group not in seen:
                seen.add(group)
                unique_groups.append(group)
        
        return unique_groups
    
    async def _update_invitation_status(
        self,
        invitation_id: str,
        status: str,
        accepted_at: Optional[datetime] = None,
    ) -> None:
        """Update invitation status in state.
        
        Args:
            invitation_id: Invitation ID
            status: New status
            accepted_at: When the invitation was accepted
        """
        # TODO: Implement state update for invitation status
        # This would update the state manager with acceptance information
        pass
    
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
            # Determine groups automatically based on Okta data
            group_names = await self._determine_user_groups(okta_user, braintrust_org)
        
        return group_names