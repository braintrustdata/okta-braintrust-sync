"""Function migrator for Braintrust migration tool."""

from braintrust_api.types import Function

from braintrust_migrate.resources.base import ResourceMigrator


class FunctionMigrator(ResourceMigrator[Function]):
    """Migrator for Braintrust functions (including tools, scorers, tasks, and LLMs)."""

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Functions"

    async def get_dependencies(self, resource: Function) -> list[str]:
        """Get list of resource IDs that this function depends on.

        Functions can depend on other migratable resources via the origin field.

        Args:
            resource: Function to get dependencies for.

        Returns:
            List of resource IDs this function depends on.
        """
        dependencies = []

        # Check if function has an origin that references a migratable resource
        if hasattr(resource, "origin") and resource.origin:
            origin = resource.origin
            if (
                hasattr(origin, "object_type")
                and hasattr(origin, "object_id")
                and origin.object_type in {"prompt", "dataset", "experiment", "project"}
            ):
                dependencies.append(origin.object_id)
                self._logger.debug(
                    "Found origin dependency",
                    function_id=resource.id,
                    function_name=resource.name,
                    origin_type=origin.object_type,
                    origin_id=origin.object_id,
                )

        return dependencies

    async def get_dependency_types(self) -> list[str]:
        """Get list of resource types that functions might depend on.

        Returns:
            List of resource type names that functions can depend on.
        """
        return ["prompts", "datasets", "experiments"]

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[Function]:
        """List all functions from the source organization.

        Args:
            project_id: Optional project ID to filter functions.

        Returns:
            List of functions from the source organization.
        """
        try:
            # Use base class helper method
            return await self._list_resources_with_client(
                self.source_client, "functions", project_id
            )

        except Exception as e:
            self._logger.error("Failed to list source functions", error=str(e))
            raise

    async def migrate_resource(self, resource: Function) -> str:
        """Migrate a single function from source to destination.

        Args:
            resource: Source function to migrate.

        Returns:
            ID of the created function in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.info(
            "Migrating function",
            source_id=resource.id,
            name=resource.name,
            slug=resource.slug,
            project_id=resource.project_id,
            function_type=getattr(resource, "function_type", None),
        )

        # Create function in destination using base class serialization
        create_params = self.serialize_resource_for_insert(resource)

        # Override the project_id to use destination project
        create_params["project_id"] = self.dest_project_id

        # Resolve origin dependencies if present
        if hasattr(resource, "origin") and resource.origin:
            origin = resource.origin
            if (
                hasattr(origin, "object_type")
                and hasattr(origin, "object_id")
                and origin.object_type in {"prompt", "dataset", "experiment", "project"}
            ):
                # Resolve dependency to destination ID
                if origin.object_type == "project":
                    # Use destination project ID
                    dest_object_id = self.dest_project_id
                else:
                    # Map origin object_type to resource type for API calls
                    resource_type_mapping = {
                        "prompt": "prompts",
                        "dataset": "datasets",
                        "experiment": "experiments",
                    }
                    resource_type = resource_type_mapping.get(origin.object_type)

                    if resource_type:
                        # Ensure dependency mapping exists, populate if necessary
                        dest_object_id = await self.ensure_dependency_mapping(
                            resource_type, origin.object_id, project_id=None
                        )
                    else:
                        # This shouldn't happen given our checks above, but be safe
                        dest_object_id = None

                if dest_object_id:
                    # Update the origin object_id in create_params
                    if "origin" in create_params and isinstance(
                        create_params["origin"], dict
                    ):
                        create_params["origin"]["object_id"] = dest_object_id

                else:
                    self._logger.warning(
                        "Could not resolve origin dependency - referenced resource may not have been migrated",
                        function_id=resource.id,
                        function_name=resource.name,
                        origin_type=origin.object_type,
                        source_object_id=origin.object_id,
                    )
                    # Remove origin field to avoid broken references
                    create_params.pop("origin", None)

        dest_function = await self.dest_client.with_retry(
            "create_function",
            lambda: self.dest_client.client.functions.create(**create_params),
        )

        self._logger.info(
            "Created function in destination",
            source_id=resource.id,
            dest_id=dest_function.id,
            name=resource.name,
            slug=resource.slug,
            function_type=getattr(dest_function, "function_type", None),
        )

        return dest_function.id
