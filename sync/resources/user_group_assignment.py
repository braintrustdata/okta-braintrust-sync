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
            # Get recent invitation operations from state
            cutoff_time = datetime.utcnow() - timedelta(hours=check_window_hours)
            pending_invitations = await self._get_pending_invitations(braintrust_org, cutoff_time)
            
            if not pending_invitations:
                self._logger.info(
                    "No pending invitations to check",
                    braintrust_org=braintrust_org,
                )
                return results
            
            results["checked_users"] = len(pending_invitations)
            
            # Get current users in the organization
            current_users = await client.list_users()
            current_user_emails = {
                user.email if hasattr(user, 'email') else user.get('email', '')
                for user in current_users
            }
            
            # Check each pending invitation
            for invitation in pending_invitations:
                user_email = invitation.get("email")
                if not user_email:
                    continue
                
                # Check if user has accepted (appears in user list)
                if user_email in current_user_emails:
                    results["accepted_users"] += 1
                    
                    # Find the user in Braintrust
                    bt_user = await client.find_user_by_email(user_email)
                    if bt_user:
                        # Assign to groups based on Okta data
                        assigned = await self._assign_user_to_groups(
                            user_email=user_email,
                            bt_user=bt_user,
                            braintrust_org=braintrust_org,
                            invitation_data=invitation,
                        )
                        if assigned:
                            results["assigned_users"] += 1
                        
                        # Update state to mark invitation as accepted
                        await self._update_invitation_status(
                            invitation_id=invitation.get("id"),
                            status="accepted",
                            accepted_at=datetime.utcnow(),
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
    
    async def _assign_user_to_groups(
        self,
        user_email: str,
        bt_user: BraintrustUser,
        braintrust_org: str,
        invitation_data: Dict[str, Any],
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
            okta_user = await self._get_okta_user_by_email(user_email)
            if not okta_user:
                self._logger.warning(
                    "Could not find Okta user for group assignment",
                    email=user_email,
                )
                return False
            
            # Determine which groups the user should be in
            target_groups = await self._determine_user_groups(okta_user, braintrust_org)
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
        
        # 4. Get Okta groups for user
        try:
            okta_groups = await self.okta_client.get_user_groups(
                okta_user.id if hasattr(okta_user, 'id') else okta_user.get('id')
            )
            for okta_group in okta_groups:
                group_name = (
                    okta_group.profile.name 
                    if hasattr(okta_group, 'profile') 
                    else okta_group.get('profile', {}).get('name')
                )
                if group_name:
                    # Add Okta group names directly or with prefix
                    groups.append(f"Okta - {group_name}")
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