"""ACL migrator for Braintrust migration tool."""

from braintrust_api.types import ACL

from braintrust_migrate.resources.base import ResourceMigrator


class ACLMigrator(ResourceMigrator[ACL]):
    """Migrator for Braintrust ACLs.

    Handles ACL migration including complex dependency resolution:
    - object_id references to various resource types (projects, experiments, datasets, etc.)
    - role_id references to roles
    - group_id references to groups

    Note: user_id references are handled specially since users are
    organization-specific and cannot be migrated between organizations.
    ACLs with user_id will be skipped with a warning.
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "ACLs"

    async def get_dependencies(self, resource: ACL) -> list[str]:
        """Get list of resource IDs that this ACL depends on.

        ACLs can depend on:
        - object_id: The resource the ACL applies to
        - role_id: The role being granted (if not a direct permission)
        - group_id: The group receiving the ACL (if not a user)

        Args:
            resource: ACL to get dependencies for.

        Returns:
            List of resource IDs this ACL depends on.
        """
        dependencies = []

        # Add object dependency
        if hasattr(resource, "object_id") and resource.object_id:
            dependencies.append(resource.object_id)
            self._logger.debug(
                "Found ACL object dependency",
                acl_id=resource.id,
                object_type=getattr(resource, "object_type", None),
                object_id=resource.object_id,
            )

        # Add role dependency if present
        if hasattr(resource, "role_id") and resource.role_id:
            dependencies.append(resource.role_id)
            self._logger.debug(
                "Found ACL role dependency",
                acl_id=resource.id,
                role_id=resource.role_id,
            )

        # Add group dependency if present
        if hasattr(resource, "group_id") and resource.group_id:
            dependencies.append(resource.group_id)
            self._logger.debug(
                "Found ACL group dependency",
                acl_id=resource.id,
                group_id=resource.group_id,
            )

        return dependencies

    async def list_source_resources(self, project_id: str | None = None) -> list[ACL]:
        """List all ACLs from the source organization.

        Args:
            project_id: Not used for ACLs (they are org-scoped).

        Returns:
            List of ACLs from the source organization.
        """
        try:
            # ACLs API requires object_id and object_type parameters
            # We can't list all ACLs at once, so return empty list for now
            # ACLs will need to be migrated per-object basis in a future implementation
            self._logger.warning(
                "ACL migration not fully implemented - ACLs API requires object_id and object_type"
            )
            return []

        except Exception as e:
            self._logger.error("Failed to list source ACLs", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: ACL) -> str | None:
        """Check if an ACL already exists in the destination.

        ACLs are considered equivalent if they have the same:
        - object_type and object_id (after ID mapping)
        - user_id or group_id (after ID mapping)
        - permission or role_id (after ID mapping)
        - restrict_object_type

        Args:
            resource: Source ACL to check.

        Returns:
            Destination ACL ID if it exists, None otherwise.
        """
        try:
            # ACLs need custom existence checking due to complex matching logic
            # Use the existing custom implementation for now
            acls = await self.dest_client.with_retry(
                "list_dest_acls",
                lambda: self.dest_client.client.acls.list_org(),
            )

            # Convert to list using base class helper
            dest_acls = await self._handle_api_response_to_list(acls)

            # Check for equivalent ACL after ID mapping
            for dest_acl in dest_acls:
                if await self._acls_equivalent(resource, dest_acl):
                    self._logger.debug(
                        "Found equivalent ACL in destination",
                        source_id=resource.id,
                        dest_id=dest_acl.id,
                    )
                    return dest_acl.id

            return None

        except Exception as e:
            self._logger.warning(
                "Error checking if ACL exists in destination",
                error=str(e),
                acl_id=resource.id,
            )
            return None

    async def _acls_equivalent(self, source_acl: ACL, dest_acl: ACL) -> bool:
        """Check if two ACLs are equivalent after ID mapping.

        Args:
            source_acl: Source ACL.
            dest_acl: Destination ACL.

        Returns:
            True if ACLs are equivalent, False otherwise.
        """
        # Check object_type and object_id (with mapping)
        mapped_object_id = self.state.id_mapping.get(source_acl.object_id)
        object_match = (
            source_acl.object_type == dest_acl.object_type
            and mapped_object_id == dest_acl.object_id
        )

        if not object_match:
            return False

        # Check user_id or group_id (with mapping for groups)
        user_group_match = True
        if hasattr(source_acl, "user_id") and source_acl.user_id:
            # Users can't be mapped, so this should not match
            user_group_match = False
        elif hasattr(source_acl, "group_id") and source_acl.group_id:
            mapped_group_id = self.state.id_mapping.get(source_acl.group_id)
            user_group_match = mapped_group_id == getattr(dest_acl, "group_id", None)
        else:
            # Neither user_id nor group_id - this shouldn't happen
            user_group_match = False

        if not user_group_match:
            return False

        # Check permission or role_id (with mapping for roles)
        permission_role_match = True
        if hasattr(source_acl, "permission") and source_acl.permission:
            permission_role_match = source_acl.permission == getattr(
                dest_acl, "permission", None
            )
        elif hasattr(source_acl, "role_id") and source_acl.role_id:
            mapped_role_id = self.state.id_mapping.get(source_acl.role_id)
            permission_role_match = mapped_role_id == getattr(dest_acl, "role_id", None)

        if not permission_role_match:
            return False

        # Check restrict_object_type
        source_restrict = getattr(source_acl, "restrict_object_type", None)
        dest_restrict = getattr(dest_acl, "restrict_object_type", None)
        return source_restrict == dest_restrict

    async def migrate_resource(self, resource: ACL) -> str:
        """Migrate a single ACL from source to destination.

        Args:
            resource: Source ACL to migrate.

        Returns:
            ID of the created ACL in destination.

        Raises:
            Exception: If migration fails.
        """
        # Skip ACLs with user_id since users can't be migrated
        if hasattr(resource, "user_id") and resource.user_id:
            self._logger.warning(
                "Skipping ACL with user_id - users are organization-specific",
                acl_id=resource.id,
                user_id=resource.user_id,
                object_type=resource.object_type,
                object_id=resource.object_id,
            )
            raise Exception(f"ACL {resource.id} has user_id and cannot be migrated")

        self._logger.info(
            "Migrating ACL",
            source_id=resource.id,
            object_type=resource.object_type,
            object_id=resource.object_id,
        )

        # Create ACL in destination
        create_params = {
            "object_type": resource.object_type,
        }

        # Resolve object_id dependency
        mapped_object_id = self.state.id_mapping.get(resource.object_id)
        if mapped_object_id:
            create_params["object_id"] = mapped_object_id
            self._logger.debug(
                "Resolved ACL object dependency",
                acl_id=resource.id,
                source_object_id=resource.object_id,
                dest_object_id=mapped_object_id,
            )
        else:
            self._logger.error(
                "Could not resolve ACL object dependency",
                acl_id=resource.id,
                object_type=resource.object_type,
                object_id=resource.object_id,
            )
            raise Exception(
                f"Could not resolve object dependency for ACL {resource.id}"
            )

        # Handle group_id with dependency resolution
        if hasattr(resource, "group_id") and resource.group_id:
            mapped_group_id = self.state.id_mapping.get(resource.group_id)
            if mapped_group_id:
                create_params["group_id"] = mapped_group_id
                self._logger.debug(
                    "Resolved ACL group dependency",
                    acl_id=resource.id,
                    source_group_id=resource.group_id,
                    dest_group_id=mapped_group_id,
                )
            else:
                self._logger.error(
                    "Could not resolve ACL group dependency",
                    acl_id=resource.id,
                    group_id=resource.group_id,
                )
                raise Exception(
                    f"Could not resolve group dependency for ACL {resource.id}"
                )

        # Handle permission or role_id
        if hasattr(resource, "permission") and resource.permission:
            create_params["permission"] = resource.permission
        elif hasattr(resource, "role_id") and resource.role_id:
            mapped_role_id = self.state.id_mapping.get(resource.role_id)
            if mapped_role_id:
                create_params["role_id"] = mapped_role_id
                self._logger.debug(
                    "Resolved ACL role dependency",
                    acl_id=resource.id,
                    source_role_id=resource.role_id,
                    dest_role_id=mapped_role_id,
                )
            else:
                self._logger.error(
                    "Could not resolve ACL role dependency",
                    acl_id=resource.id,
                    role_id=resource.role_id,
                )
                raise Exception(
                    f"Could not resolve role dependency for ACL {resource.id}"
                )

        # Copy optional fields
        if hasattr(resource, "restrict_object_type") and resource.restrict_object_type:
            create_params["restrict_object_type"] = resource.restrict_object_type

        dest_acl = await self.dest_client.with_retry(
            "create_acl", lambda: self.dest_client.client.acls.create(**create_params)
        )

        self._logger.info(
            "Created ACL in destination",
            source_id=resource.id,
            dest_id=dest_acl.id,
            object_type=resource.object_type,
        )

        return dest_acl.id
