"""Group migrator for Braintrust migration tool."""

from braintrust_api.types import Group

from braintrust_migrate.resources.base import ResourceMigrator


class GroupMigrator(ResourceMigrator[Group]):
    """Migrator for Braintrust groups.

    Handles group migration including group inheritance dependencies.
    Groups can inherit from other groups via the member_groups field,
    so parent groups must be migrated before child groups.

    Note: member_users are excluded from migration since users are
    organization-specific and cannot be migrated between organizations.
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Groups"

    async def get_dependencies(self, resource: Group) -> list[str]:
        """Get list of group IDs that this group depends on.

        Groups can depend on other groups via the member_groups field.

        Args:
            resource: Group to get dependencies for.

        Returns:
            List of group IDs this group inherits from.
        """
        dependencies = []

        # Check if group has member_groups (inheritance)
        if hasattr(resource, "member_groups") and resource.member_groups:
            for group_id in resource.member_groups:
                dependencies.append(group_id)
                self._logger.debug(
                    "Found group inheritance dependency",
                    group_id=resource.id,
                    group_name=resource.name,
                    parent_group_id=group_id,
                )

        return dependencies

    async def list_source_resources(self, project_id: str | None = None) -> list[Group]:
        """List all groups from the source organization.

        Args:
            project_id: Not used for groups (they are org-scoped).

        Returns:
            List of groups from the source organization.
        """
        try:
            # Groups are organization-scoped, not project-scoped
            # Use base class helper but without project_id
            return await self._list_resources_with_client(
                self.source_client, "groups", project_id=None
            )

        except Exception as e:
            self._logger.error("Failed to list source groups", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: Group) -> str | None:
        """Check if a group already exists in the destination.

        Args:
            resource: Source group to check.

        Returns:
            Destination group ID if it exists, None otherwise.
        """
        # Use base class helper method for organization-scoped resources
        additional_params = {"group_name": resource.name}
        # Override dest_project_id temporarily since groups are org-scoped
        original_dest_project_id = self.dest_project_id
        self.dest_project_id = None
        try:
            result = await self._check_resource_exists_by_name(
                resource, "groups", additional_params=additional_params
            )
            return result
        finally:
            # Restore original dest_project_id
            self.dest_project_id = original_dest_project_id

    async def migrate_resource(self, resource: Group) -> str:
        """Migrate a single group from source to destination.

        Args:
            resource: Source group to migrate.

        Returns:
            ID of the created group in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.info(
            "Migrating group",
            source_id=resource.id,
            name=resource.name,
            org_id=getattr(resource, "org_id", None),
        )

        # Create group in destination using base class serialization
        create_params = self.serialize_resource_for_insert(resource)

        # Handle member_groups with dependency resolution
        if hasattr(resource, "member_groups") and resource.member_groups:
            resolved_member_groups = []
            for group_id in resource.member_groups:
                # Resolve group dependency to destination ID
                dest_group_id = self.state.id_mapping.get(group_id)
                if dest_group_id:
                    resolved_member_groups.append(dest_group_id)
                    self._logger.debug(
                        "Resolved group inheritance dependency",
                        group_id=resource.id,
                        source_parent_group_id=group_id,
                        dest_parent_group_id=dest_group_id,
                    )
                else:
                    self._logger.warning(
                        "Could not resolve group inheritance dependency - parent group may not have been migrated",
                        group_id=resource.id,
                        group_name=resource.name,
                        source_parent_group_id=group_id,
                    )

            if resolved_member_groups:
                create_params["member_groups"] = resolved_member_groups

        # Note: member_users are intentionally excluded from migration
        # since users are organization-specific and cannot be migrated
        if hasattr(resource, "member_users") and resource.member_users:
            self._logger.info(
                "Skipping member_users migration - users are organization-specific",
                group_id=resource.id,
                group_name=resource.name,
                user_count=len(resource.member_users),
            )
            # Remove member_users from create_params to avoid trying to migrate them
            create_params.pop("member_users", None)

        dest_group = await self.dest_client.with_retry(
            "create_group",
            lambda: self.dest_client.client.groups.create(**create_params),
        )

        self._logger.info(
            "Created group in destination",
            source_id=resource.id,
            dest_id=dest_group.id,
            name=resource.name,
        )

        return dest_group.id
