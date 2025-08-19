"""Role-project assignment manager for Groups → Roles → Projects workflow."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from sync.clients.braintrust import BraintrustClient
from sync.config.role_project_models import (
    RoleProjectConfig,
    RoleDefinition,
    GroupRoleAssignment,
    ProjectMatchRule,
    STANDARD_ROLES,
)
from sync.core.state import StateManager
from sync.core.enhanced_state import ResourceType

logger = structlog.get_logger(__name__)


class RoleProjectAssignmentManager:
    """Manages the Groups → Roles → Projects workflow.
    
    This manager implements granular and reusable ACLs by:
    1. Ensuring standard roles exist in Braintrust organizations
    2. Matching projects based on configuration rules
    3. Creating ACLs that assign groups to roles on specific projects
    
    The workflow enables fine-grained permission management where:
    - Groups are assigned to roles (collections of permissions)
    - Roles are assigned to specific projects via ACLs
    - Changes to roles automatically apply to all assigned groups/projects
    """
    
    def __init__(
        self,
        braintrust_clients: Dict[str, BraintrustClient],
        state_manager: StateManager,
        role_project_configs: Optional[Dict[str, RoleProjectConfig]] = None,
    ) -> None:
        """Initialize role-project assignment manager.
        
        Args:
            braintrust_clients: Dictionary of Braintrust clients by org name
            state_manager: State manager for tracking sync operations
            role_project_configs: Optional role-project configurations per org
        """
        self.braintrust_clients = braintrust_clients
        self.state_manager = state_manager
        self.role_project_configs = role_project_configs or {}
        
        self._logger = logger.bind(
            component="RoleProjectAssignmentManager",
        )
    
    async def sync_roles_and_projects(
        self,
        braintrust_org: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Synchronize roles and project assignments for an organization.
        
        This is the main entry point for the Groups → Roles → Projects workflow.
        It performs the following steps:
        1. Ensure all standard roles exist
        2. Process group role assignments to projects
        3. Create/update ACLs as needed
        
        Args:
            braintrust_org: Braintrust organization name
            dry_run: If True, preview changes without applying them
            
        Returns:
            Dictionary with sync results and statistics
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        config = self.role_project_configs.get(braintrust_org)
        if not config:
            self._logger.warning(
                "No role-project configuration found for org",
                braintrust_org=braintrust_org,
            )
            return {"success": False, "error": "No configuration found"}
        
        client = self.braintrust_clients[braintrust_org]
        results = {
            "braintrust_org": braintrust_org,
            "dry_run": dry_run or config.dry_run,
            "roles_processed": 0,
            "roles_created": 0,
            "roles_updated": 0,
            "assignments_processed": 0,
            "acls_created": 0,
            "acls_removed": 0,
            "errors": [],
            "warnings": [],
        }
        
        try:
            # Step 1: Ensure standard roles exist
            if config.standard_roles:
                role_results = await self._ensure_roles_exist(
                    client=client,
                    roles=config.standard_roles,
                    auto_create=config.auto_create_roles,
                    update_existing=config.update_existing_roles,
                    dry_run=results["dry_run"],
                )
                results.update(role_results)
            
            # Step 2: Process group role assignments
            assignment_results = await self._process_group_assignments(
                client=client,
                braintrust_org=braintrust_org,
                assignments=config.group_assignments,
                dry_run=results["dry_run"],
            )
            results.update(assignment_results)
            
            # Step 3: Remove unmanaged ACLs if configured
            if config.remove_unmanaged_acls and not results["dry_run"]:
                removal_results = await self._remove_unmanaged_acls(
                    client=client,
                    braintrust_org=braintrust_org,
                    managed_assignments=config.group_assignments,
                )
                results.update(removal_results)
            
            self._logger.info(
                "Role-project sync completed",
                braintrust_org=braintrust_org,
                **{k: v for k, v in results.items() if k not in ["errors", "warnings"]},
            )
            
            results["success"] = True
            
        except Exception as e:
            self._logger.error(
                "Error during role-project sync",
                braintrust_org=braintrust_org,
                error=str(e),
            )
            results["errors"].append(str(e))
            results["success"] = False
        
        return results
    
    async def _ensure_roles_exist(
        self,
        client: BraintrustClient,
        roles: List[RoleDefinition],
        auto_create: bool,
        update_existing: bool,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Ensure that all required roles exist in the organization.
        
        Args:
            client: Braintrust client
            roles: List of role definitions to ensure exist
            auto_create: Whether to create missing roles
            update_existing: Whether to update existing roles
            dry_run: Whether to preview changes only
            
        Returns:
            Dictionary with role management results
        """
        results = {
            "roles_processed": 0,
            "roles_created": 0,
            "roles_updated": 0,
            "role_errors": [],
        }
        
        for role_def in roles:
            try:
                results["roles_processed"] += 1
                
                # Check if role already exists
                existing_role = await client.get_role_by_name(role_def.name)
                
                if existing_role:
                    # Track existing role in enhanced state
                    self.state_manager.track_role_state(
                        role_id=existing_role["id"],
                        role_name=role_def.name,
                        braintrust_org=client.org_name,
                        role_definition=role_def.model_dump(),
                        created_by_sync=False,  # Pre-existing role
                    )
                    
                    # Role exists - check if update is needed
                    if update_existing and self._role_needs_update(existing_role, role_def):
                        if not dry_run:
                            await client.update_role(
                                role_id=existing_role["id"],
                                member_permissions=role_def.member_permissions,
                                description=role_def.description,
                            )
                            results["roles_updated"] += 1
                            
                            # Update tracking to reflect sync modification
                            self.state_manager.track_role_state(
                                role_id=existing_role["id"],
                                role_name=role_def.name,
                                braintrust_org=client.org_name,
                                role_definition=role_def.model_dump(),
                                created_by_sync=True,  # Now managed by sync
                            )
                            
                        self._logger.info(
                            "Role updated" if not dry_run else "Role would be updated",
                            role_name=role_def.name,
                            dry_run=dry_run,
                        )
                    else:
                        self._logger.debug(
                            "Role already exists and is current",
                            role_name=role_def.name,
                        )
                
                else:
                    # Role doesn't exist - create if enabled
                    if auto_create:
                        if not dry_run:
                            created_role = await client.create_role(role_def)
                            results["roles_created"] += 1
                            
                            # Track newly created role
                            if created_role and created_role.get("id"):
                                self.state_manager.track_role_state(
                                    role_id=created_role["id"],
                                    role_name=role_def.name,
                                    braintrust_org=client.org_name,
                                    role_definition=role_def.model_dump(),
                                    created_by_sync=True,  # Created by sync
                                )
                            
                        self._logger.info(
                            "Role created" if not dry_run else "Role would be created",
                            role_name=role_def.name,
                            permission_count=len(role_def.member_permissions),
                            dry_run=dry_run,
                        )
                    else:
                        self._logger.warning(
                            "Role missing but auto_create is disabled",
                            role_name=role_def.name,
                        )
                        results["role_errors"].append(
                            f"Role '{role_def.name}' not found and auto_create is disabled"
                        )
                
            except Exception as e:
                error_msg = f"Error processing role '{role_def.name}': {str(e)}"
                self._logger.error(error_msg)
                results["role_errors"].append(error_msg)
        
        return results
    
    def _role_needs_update(
        self,
        existing_role: Dict[str, Any],
        role_def: RoleDefinition,
    ) -> bool:
        """Check if an existing role needs to be updated.
        
        Args:
            existing_role: Current role from Braintrust API
            role_def: Desired role definition
            
        Returns:
            True if the role needs updating
        """
        # Check description
        if existing_role.get("description", "") != role_def.description:
            return True
        
        # Check permissions
        existing_perms = existing_role.get("member_permissions", [])
        desired_perms = []
        
        for perm in role_def.member_permissions:
            perm_dict = {"permission": perm.permission.value}
            if perm.restrict_object_type:
                perm_dict["restrict_object_type"] = perm.restrict_object_type.value
            else:
                perm_dict["restrict_object_type"] = None
            desired_perms.append(perm_dict)
        
        # Compare permission sets (order doesn't matter)
        existing_set = {
            (p["permission"], p.get("restrict_object_type"))
            for p in existing_perms
        }
        desired_set = {
            (p["permission"], p.get("restrict_object_type"))
            for p in desired_perms
        }
        
        return existing_set != desired_set
    
    async def _process_group_assignments(
        self,
        client: BraintrustClient,
        braintrust_org: str,
        assignments: List[GroupRoleAssignment],
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Process group role assignments to projects.
        
        Args:
            client: Braintrust client
            braintrust_org: Braintrust organization name
            assignments: List of group role assignments
            dry_run: Whether to preview changes only
            
        Returns:
            Dictionary with assignment processing results
        """
        results = {
            "assignments_processed": 0,
            "acls_created": 0,
            "assignment_errors": [],
        }
        
        # Sort assignments by priority (higher first)
        sorted_assignments = sorted(
            [a for a in assignments if a.enabled],
            key=lambda x: x.priority,
            reverse=True
        )
        
        for assignment in sorted_assignments:
            try:
                results["assignments_processed"] += 1
                
                self._logger.debug(
                    "Processing group assignment",
                    group_name=assignment.group_name,
                    role_name=assignment.role_name,
                    priority=assignment.priority,
                )
                
                # Find matching projects
                projects = await self._find_matching_projects(
                    client=client,
                    project_match=assignment.project_match,
                    braintrust_org=braintrust_org,
                )
                
                # Track discovered projects in enhanced state
                for project in projects:
                    self.state_manager.track_project(
                        project_id=project.get("id"),
                        project_name=project.get("name"),
                        braintrust_org=braintrust_org,
                        matched_patterns=[
                            pattern for pattern in [
                                assignment.project_match.name_pattern,
                                assignment.project_match.name_contains,
                                assignment.project_match.name_starts_with,
                                assignment.project_match.name_ends_with,
                            ] if pattern
                        ],
                    )
                
                if not projects:
                    self._logger.warning(
                        "No projects matched for assignment",
                        group_name=assignment.group_name,
                        role_name=assignment.role_name,
                    )
                    continue
                
                # Create ACLs for the group-role-projects combination
                acl_result = await self._create_group_role_acls(
                    client=client,
                    group_name=assignment.group_name,
                    role_name=assignment.role_name,
                    projects=projects,
                    assignment_rule=assignment.model_dump(),
                    dry_run=dry_run,
                )
                
                results["acls_created"] += acl_result.get("acls_created", 0)
                
                if acl_result.get("errors"):
                    results["assignment_errors"].extend(acl_result["errors"])
                
            except Exception as e:
                error_msg = (
                    f"Error processing assignment for group '{assignment.group_name}' "
                    f"with role '{assignment.role_name}': {str(e)}"
                )
                self._logger.error(error_msg)
                results["assignment_errors"].append(error_msg)
        
        return results
    
    async def _find_matching_projects(
        self,
        client: BraintrustClient,
        project_match: ProjectMatchRule,
        braintrust_org: str,
    ) -> List[Dict[str, Any]]:
        """Find projects that match the given rules.
        
        Args:
            client: Braintrust client
            project_match: Project matching rules
            braintrust_org: Braintrust organization name
            
        Returns:
            List of matching project objects
        """
        # Get all projects in the organization
        all_projects = await client.list_projects(org_name=braintrust_org)
        
        matching_projects = []
        
        # ========== Explicit project lists ==========
        if project_match.project_names:
            for project_name in project_match.project_names:
                project = await client.get_project_by_name(project_name, braintrust_org)
                if project:
                    matching_projects.append(project)
                else:
                    self._logger.warning(
                        "Project not found by name",
                        project_name=project_name,
                        braintrust_org=braintrust_org,
                    )
        
        if project_match.project_ids:
            for project_id in project_match.project_ids:
                # Find project by ID in all_projects list
                project = next(
                    (p for p in all_projects if p.get("id") == project_id),
                    None
                )
                if project:
                    matching_projects.append(project)
                else:
                    self._logger.warning(
                        "Project not found by ID",
                        project_id=project_id,
                        braintrust_org=braintrust_org,
                    )
        
        # ========== Pattern-based matching ==========
        if any([
            project_match.name_pattern,
            project_match.name_contains,
            project_match.name_starts_with,
            project_match.name_ends_with,
            project_match.all_projects,
        ]):
            for project in all_projects:
                project_name = project.get("name", "")
                
                # Check if already added from explicit lists
                if project in matching_projects:
                    continue
                
                # Apply pattern matching
                if self._project_matches_patterns(project_name, project_match):
                    matching_projects.append(project)
        
        # ========== Apply exclusion patterns ==========
        if project_match.exclude_patterns:
            filtered_projects = []
            for project in matching_projects:
                project_name = project.get("name", "")
                excluded = False
                
                for exclude_pattern in project_match.exclude_patterns:
                    try:
                        if re.match(exclude_pattern, project_name):
                            excluded = True
                            self._logger.debug(
                                "Project excluded by pattern",
                                project_name=project_name,
                                exclude_pattern=exclude_pattern,
                            )
                            break
                    except re.error:
                        self._logger.warning(
                            "Invalid exclude pattern",
                            pattern=exclude_pattern,
                        )
                
                if not excluded:
                    filtered_projects.append(project)
            
            matching_projects = filtered_projects
        
        # Remove duplicates while preserving order
        seen_ids = set()
        unique_projects = []
        for project in matching_projects:
            project_id = project.get("id")
            if project_id not in seen_ids:
                seen_ids.add(project_id)
                unique_projects.append(project)
        
        self._logger.debug(
            "Found matching projects",
            project_count=len(unique_projects),
            project_names=[p.get("name") for p in unique_projects],
        )
        
        return unique_projects
    
    def _project_matches_patterns(
        self,
        project_name: str,
        project_match: ProjectMatchRule,
    ) -> bool:
        """Check if a project name matches the pattern rules.
        
        Args:
            project_name: Name of the project to check
            project_match: Project matching rules
            
        Returns:
            True if the project matches the patterns
        """
        # All projects selector
        if project_match.all_projects:
            return True
        
        # Regex pattern matching
        if project_match.name_pattern:
            try:
                if re.match(project_match.name_pattern, project_name):
                    return True
            except re.error:
                self._logger.warning(
                    "Invalid regex pattern",
                    pattern=project_match.name_pattern,
                )
        
        # Contains matching (OR logic)
        if project_match.name_contains:
            for contains_str in project_match.name_contains:
                if contains_str.lower() in project_name.lower():
                    return True
        
        # Starts with matching
        if project_match.name_starts_with:
            if project_name.lower().startswith(project_match.name_starts_with.lower()):
                return True
        
        # Ends with matching
        if project_match.name_ends_with:
            if project_name.lower().endswith(project_match.name_ends_with.lower()):
                return True
        
        return False
    
    async def _create_group_role_acls(
        self,
        client: BraintrustClient,
        group_name: str,
        role_name: str,
        projects: List[Dict[str, Any]],
        assignment_rule: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Create ACLs for a group-role-projects combination.
        
        Args:
            client: Braintrust client
            group_name: Name of the group
            role_name: Name of the role
            projects: List of project objects
            assignment_rule: Assignment rule that created this ACL
            dry_run: Whether to preview changes only
            
        Returns:
            Dictionary with ACL creation results
        """
        results = {
            "acls_created": 0,
            "errors": [],
        }
        
        if not projects:
            return results
        
        try:
            # Use the high-level method from BraintrustClient
            project_names = [p.get("name") for p in projects]
            
            if not dry_run:
                result = await client.assign_group_role_to_projects(
                    group_name=group_name,
                    role_name=role_name,
                    project_names=project_names,
                )
                
                if result.get("success"):
                    results["acls_created"] = result.get("project_count", 0)
                    
                    # Track created ACLs in enhanced state
                    created_acls = result.get("created_acls", [])
                    for acl_info in created_acls:
                        if all(key in acl_info for key in ["acl_id", "group_id", "role_id", "project_id"]):
                            # Get role details for permissions
                            role = await client.get_role_by_name(role_name)
                            permissions = []
                            if role and role.get("member_permissions"):
                                permissions = [p.get("permission") for p in role["member_permissions"]]
                            
                            self.state_manager.track_acl_state(
                                acl_id=acl_info["acl_id"],
                                group_id=acl_info["group_id"], 
                                group_name=group_name,
                                role_id=acl_info["role_id"],
                                role_name=role_name,
                                project_id=acl_info["project_id"],
                                project_name=acl_info.get("project_name", ""),
                                braintrust_org=client.org_name,
                                permissions=permissions,
                                assignment_rule=assignment_rule,
                                created_by_sync=True,
                            )
                    
                    self._logger.info(
                        "Created ACLs for group-role-projects",
                        group_name=group_name,
                        role_name=role_name,
                        project_count=results["acls_created"],
                    )
                else:
                    error_msg = result.get("error", "Unknown error")
                    results["errors"].append(error_msg)
                    self._logger.error(
                        "Failed to create ACLs",
                        group_name=group_name,
                        role_name=role_name,
                        error=error_msg,
                    )
            else:
                # Dry run - just log what would be done
                results["acls_created"] = len(projects)
                self._logger.info(
                    "Would create ACLs for group-role-projects",
                    group_name=group_name,
                    role_name=role_name,
                    project_count=len(projects),
                    project_names=project_names,
                    dry_run=True,
                )
        
        except Exception as e:
            error_msg = f"Error creating ACLs for {group_name}-{role_name}: {str(e)}"
            results["errors"].append(error_msg)
            self._logger.error(error_msg)
        
        return results
    
    async def _remove_unmanaged_acls(
        self,
        client: BraintrustClient,
        braintrust_org: str,
        managed_assignments: List[GroupRoleAssignment],
    ) -> Dict[str, Any]:
        """Remove ACLs that are not defined in the configuration.
        
        WARNING: This is a destructive operation that removes ACLs not managed
        by this configuration. Use with caution.
        
        Args:
            client: Braintrust client
            braintrust_org: Braintrust organization name
            managed_assignments: List of assignments that should be preserved
            
        Returns:
            Dictionary with removal results
        """
        # This is a placeholder for the removal logic
        # Implementation would need to:
        # 1. Get all current ACLs in the org
        # 2. Determine which ones are managed by this config
        # 3. Remove the unmanaged ones
        
        self._logger.warning(
            "ACL removal not implemented - this would be a destructive operation",
            braintrust_org=braintrust_org,
        )
        
        return {
            "acls_removed": 0,
            "removal_errors": ["ACL removal not implemented"],
        }
    
    async def get_assignment_status(
        self,
        braintrust_org: str,
    ) -> Dict[str, Any]:
        """Get the current status of role-project assignments.
        
        Args:
            braintrust_org: Braintrust organization name
            
        Returns:
            Dictionary with current assignment status
        """
        if braintrust_org not in self.braintrust_clients:
            raise ValueError(f"No Braintrust client configured for org: {braintrust_org}")
        
        client = self.braintrust_clients[braintrust_org]
        config = self.role_project_configs.get(braintrust_org)
        
        status = {
            "braintrust_org": braintrust_org,
            "has_config": config is not None,
            "roles": {},
            "assignments": {},
            "projects": {},
        }
        
        try:
            # Get current roles
            roles = await client.list_roles()
            status["roles"] = {
                "total_count": len(roles),
                "roles": [{"name": r.get("name"), "id": r.get("id")} for r in roles],
            }
            
            # Get current projects
            projects = await client.list_projects(org_name=braintrust_org)
            status["projects"] = {
                "total_count": len(projects),
                "projects": [{"name": p.get("name"), "id": p.get("id")} for p in projects],
            }
            
            # Get current ACLs (if we have read_acls permission)
            try:
                acls = await client.list_org_acls(org_name=braintrust_org, object_type="project")
                status["assignments"] = {
                    "total_acl_count": len(acls),
                    "project_acls": len([a for a in acls if a.get("object_type") == "project"]),
                }
            except Exception:
                status["assignments"] = {
                    "error": "Cannot read ACLs - insufficient permissions"
                }
            
            if config:
                status["config_summary"] = {
                    "standard_roles_count": len(config.standard_roles or []),
                    "group_assignments_count": len(config.group_assignments),
                    "auto_create_roles": config.auto_create_roles,
                    "update_existing_roles": config.update_existing_roles,
                }
        
        except Exception as e:
            status["error"] = str(e)
        
        return status