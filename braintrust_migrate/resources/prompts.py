"""Prompt migrator for Braintrust migration tool."""

from braintrust_api.types import Prompt

from braintrust_migrate.resources.base import ResourceMigrator


class PromptMigrator(ResourceMigrator[Prompt]):
    """Migrator for Braintrust prompts."""

    def __init__(self, *args, **kwargs):
        """Initialize the prompt migrator."""
        super().__init__(*args, **kwargs)
        self._final_pass = False

    def set_final_pass(self, final_pass: bool) -> None:
        """Set whether this is the final pass for prompt migration.

        In the first pass, we only migrate prompts without dependencies.
        In the final pass, we migrate prompts with dependencies.

        Args:
            final_pass: True if this is the final pass.
        """
        self._final_pass = final_pass
        self._logger.debug(
            "Set prompt migration pass",
            final_pass=final_pass,
        )

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Prompts"

    async def should_migrate_resource(self, resource: Prompt) -> bool:
        """Determine if a resource should be migrated in this pass.

        Args:
            resource: Prompt to check.

        Returns:
            True if the resource should be migrated in this pass.
        """
        dependencies = await self.get_dependencies(resource)
        has_dependencies = len(dependencies) > 0

        if self._final_pass:
            # Final pass: only migrate prompts WITH dependencies
            should_migrate = has_dependencies
            if should_migrate:
                self._logger.debug(
                    "Prompt scheduled for final pass (has dependencies)",
                    prompt_id=resource.id,
                    prompt_name=resource.name,
                    dependencies=dependencies,
                )
        else:
            # First pass: only migrate prompts WITHOUT dependencies
            should_migrate = not has_dependencies
            if should_migrate:
                self._logger.debug(
                    "Prompt scheduled for first pass (no dependencies)",
                    prompt_id=resource.id,
                    prompt_name=resource.name,
                )

        return should_migrate

    async def get_dependencies(self, resource: Prompt) -> list[str]:
        """Get list of resource IDs that this prompt depends on.

        Prompts can depend on:
        1. Functions/tools via prompt_data.tool_functions
        2. Other prompts via prompt_data.origin.prompt_id

        Args:
            resource: Prompt to get dependencies for.

        Returns:
            List of resource IDs this prompt depends on.
        """
        dependencies = []

        # Check prompt_data for dependencies
        if hasattr(resource, "prompt_data") and resource.prompt_data:
            prompt_data = resource.prompt_data

            # Check for tool function dependencies
            if hasattr(prompt_data, "tool_functions") and prompt_data.tool_functions:
                for tool_func in prompt_data.tool_functions:
                    if (
                        hasattr(tool_func, "type")
                        and hasattr(tool_func, "id")
                        and tool_func.type == "function"
                    ):
                        dependencies.append(tool_func.id)
                        self._logger.debug(
                            "Found function dependency",
                            prompt_id=resource.id,
                            prompt_name=resource.name,
                            function_id=tool_func.id,
                        )
                    # Note: We skip "global" type functions as they don't need migration

            # Check for prompt origin dependencies
            if hasattr(prompt_data, "origin") and prompt_data.origin:
                origin = prompt_data.origin
                if hasattr(origin, "prompt_id") and origin.prompt_id:
                    dependencies.append(origin.prompt_id)
                    self._logger.debug(
                        "Found prompt dependency",
                        prompt_id=resource.id,
                        prompt_name=resource.name,
                        origin_prompt_id=origin.prompt_id,
                    )

        return dependencies

    async def get_dependency_types(self) -> list[str]:
        """Get list of resource types that prompts might depend on.

        Returns:
            List of resource type names that prompts can depend on.
        """
        return ["functions", "prompts"]

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[Prompt]:
        """List all prompts from the source organization.

        Args:
            project_id: Optional project ID to filter prompts.

        Returns:
            List of prompts from the source organization.
        """
        try:
            # Use base class helper method
            return await self._list_resources_with_client(
                self.source_client, "prompts", project_id
            )

        except Exception as e:
            self._logger.error("Failed to list source prompts", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: Prompt) -> str | None:
        """Check if a prompt already exists in the destination.

        Args:
            resource: Source prompt to check.

        Returns:
            Destination prompt ID if it exists, None otherwise.
        """
        # Use base class helper method with slug matching
        additional_params = {"prompt_name": resource.name}
        return await self._check_resource_exists_by_name(
            resource,
            "prompts",
            additional_match_fields=["slug"],
            additional_params=additional_params,
        )

    def _resolve_prompt_data_dependencies(self, prompt_data: dict) -> dict:
        """Resolve dependencies within prompt_data and return updated version.

        Args:
            prompt_data: Original prompt data.

        Returns:
            Updated prompt data with resolved dependencies.
        """
        if not prompt_data:
            return prompt_data

        # Create a deep copy to avoid modifying the original
        import copy

        resolved_data = copy.deepcopy(prompt_data)

        # Resolve tool_functions dependencies
        if resolved_data.get("tool_functions"):
            resolved_tool_functions = []
            for tool_func in resolved_data["tool_functions"]:
                if (
                    isinstance(tool_func, dict)
                    and tool_func.get("type") == "function"
                    and "id" in tool_func
                ):
                    # Resolve function ID to destination ID
                    dest_function_id = self.state.id_mapping.get(tool_func["id"])
                    if dest_function_id:
                        resolved_tool_func = tool_func.copy()
                        resolved_tool_func["id"] = dest_function_id
                        resolved_tool_functions.append(resolved_tool_func)

                    else:
                        self._logger.warning(
                            "Could not resolve tool function dependency",
                            source_function_id=tool_func["id"],
                        )
                        # Skip this tool function rather than break the prompt
                else:
                    # Keep global functions and other types as-is
                    resolved_tool_functions.append(tool_func)

            resolved_data["tool_functions"] = resolved_tool_functions

        # Resolve origin prompt dependencies
        if resolved_data.get("origin"):
            origin = resolved_data["origin"]
            if isinstance(origin, dict) and "prompt_id" in origin:
                dest_prompt_id = self.state.id_mapping.get(origin["prompt_id"])
                if dest_prompt_id:
                    resolved_data["origin"]["prompt_id"] = dest_prompt_id
                    # Also update project_id if present
                    if "project_id" in origin:
                        resolved_data["origin"]["project_id"] = self.dest_project_id

                else:
                    self._logger.warning(
                        "Could not resolve prompt origin dependency",
                        source_prompt_id=origin["prompt_id"],
                    )
                    # Remove the origin to avoid broken references
                    del resolved_data["origin"]

        return resolved_data

    async def migrate_resource(self, resource: Prompt) -> str:
        """Migrate a single prompt from source to destination.

        Args:
            resource: Source prompt to migrate.

        Returns:
            ID of the created prompt in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.info(
            "Migrating prompt",
            source_id=resource.id,
            name=resource.name,
            slug=resource.slug,
            project_id=resource.project_id,
        )

        # Create prompt in destination
        create_params = {
            "name": resource.name,
            "slug": resource.slug,
            "project_id": self.dest_project_id,  # Use destination project ID
        }

        # Copy optional fields if they exist
        if hasattr(resource, "description") and resource.description:
            create_params["description"] = resource.description

        if hasattr(resource, "tags") and resource.tags:
            create_params["tags"] = resource.tags

        if hasattr(resource, "function_type") and resource.function_type:
            create_params["function_type"] = resource.function_type

        # Handle prompt_data with dependency resolution
        if hasattr(resource, "prompt_data") and resource.prompt_data:
            # Convert to dict if needed for processing
            prompt_data_dict = resource.prompt_data
            if hasattr(resource.prompt_data, "__dict__"):
                prompt_data_dict = resource.prompt_data.__dict__
            elif hasattr(resource.prompt_data, "model_dump"):
                prompt_data_dict = resource.prompt_data.model_dump()

            # Resolve dependencies in prompt_data
            resolved_prompt_data = self._resolve_prompt_data_dependencies(
                prompt_data_dict
            )
            create_params["prompt_data"] = resolved_prompt_data

        dest_prompt = await self.dest_client.with_retry(
            "create_prompt",
            lambda: self.dest_client.client.prompts.create(**create_params),
        )

        self._logger.info(
            "Created prompt in destination",
            source_id=resource.id,
            dest_id=dest_prompt.id,
            name=resource.name,
            slug=resource.slug,
        )

        return dest_prompt.id
