"""Role migrator for Braintrust migration tool."""

from braintrust_api.types import Role

from braintrust_migrate.resources.base import ResourceMigrator


class RoleMigrator(ResourceMigrator[Role]):
    """Migrator for Braintrust roles.

    Handles role migration including role inheritance dependencies.
    Roles can inherit from other roles via the member_roles field,
    so parent roles must be migrated before child roles.
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Roles"

    async def get_dependencies(self, resource: Role) -> list[str]:
        """Get list of role IDs that this role depends on.

        Roles can depend on other roles via the member_roles field.

        Args:
            resource: Role to get dependencies for.

        Returns:
            List of role IDs this role inherits from.
        """
        dependencies = []

        # Check if role has member_roles (inheritance)
        if hasattr(resource, "member_roles") and resource.member_roles:
            for role_id in resource.member_roles:
                dependencies.append(role_id)
                self._logger.debug(
                    "Found role inheritance dependency",
                    role_id=resource.id,
                    role_name=resource.name,
                    parent_role_id=role_id,
                )

        return dependencies

    async def list_source_resources(self, project_id: str | None = None) -> list[Role]:
        """List all roles from the source organization.

        Args:
            project_id: Not used for roles (they are org-scoped).

        Returns:
            List of roles from the source organization.
        """
        try:
            # Roles are organization-scoped, not project-scoped
            # Use base class helper but without project_id
            return await self._list_resources_with_client(
                self.source_client, "roles", project_id=None
            )

        except Exception as e:
            self._logger.error("Failed to list source roles", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: Role) -> str | None:
        """Check if a role already exists in the destination.

        Args:
            resource: Source role to check.

        Returns:
            Destination role ID if it exists, None otherwise.
        """
        # Use base class helper method for organization-scoped resources
        additional_params = {"role_name": resource.name}
        # Override dest_project_id temporarily since roles are org-scoped
        original_dest_project_id = self.dest_project_id
        self.dest_project_id = None
        try:
            result = await self._check_resource_exists_by_name(
                resource, "roles", additional_params=additional_params
            )
            return result
        finally:
            # Restore original dest_project_id
            self.dest_project_id = original_dest_project_id

    async def migrate_resource(self, resource: Role) -> str:
        """Migrate a single role from source to destination.

        Args:
            resource: Source role to migrate.

        Returns:
            ID of the created role in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.info(
            "Migrating role",
            source_id=resource.id,
            name=resource.name,
            org_id=getattr(resource, "org_id", None),
        )

        # Create role in destination
        create_params = {
            "name": resource.name,
        }

        # Copy optional fields if they exist
        if hasattr(resource, "description") and resource.description:
            create_params["description"] = resource.description

        if hasattr(resource, "member_permissions") and resource.member_permissions:
            create_params["member_permissions"] = resource.member_permissions

        # Handle member_roles with dependency resolution
        if hasattr(resource, "member_roles") and resource.member_roles:
            resolved_member_roles = []
            for role_id in resource.member_roles:
                # Resolve role dependency to destination ID
                dest_role_id = self.state.id_mapping.get(role_id)
                if dest_role_id:
                    resolved_member_roles.append(dest_role_id)
                    self._logger.debug(
                        "Resolved role inheritance dependency",
                        role_id=resource.id,
                        source_parent_role_id=role_id,
                        dest_parent_role_id=dest_role_id,
                    )
                else:
                    self._logger.warning(
                        "Could not resolve role inheritance dependency - parent role may not have been migrated",
                        role_id=resource.id,
                        role_name=resource.name,
                        source_parent_role_id=role_id,
                    )

            if resolved_member_roles:
                create_params["member_roles"] = resolved_member_roles

        dest_role = await self.dest_client.with_retry(
            "create_role", lambda: self.dest_client.client.roles.create(**create_params)
        )

        self._logger.info(
            "Created role in destination",
            source_id=resource.id,
            dest_id=dest_role.id,
            name=resource.name,
        )

        return dest_role.id
