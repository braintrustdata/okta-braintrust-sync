"""Project score migration functionality."""

import structlog
from braintrust_api.types import ProjectScore

from .base import ResourceMigrator

logger = structlog.get_logger(__name__)


class ProjectScoreMigrator(ResourceMigrator[ProjectScore]):
    """Migrator for project scores."""

    @property
    def resource_name(self) -> str:
        """Return the name of this resource type."""
        return "project_scores"

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[ProjectScore]:
        """List all project scores from the source organization.

        Args:
            project_id: Optional project ID to filter by

        Returns:
            List of project scores
        """
        logger.info("Listing project scores from source", project_id=project_id)

        try:
            # Use base class helper method with client-side filtering
            return await self._list_resources_with_client(
                self.source_client,
                "project_scores",
                project_id,
                client_side_filter_field="project_id",
            )

        except Exception as e:
            logger.error(
                "Failed to list project scores", error=str(e), project_id=project_id
            )
            raise

    async def resource_exists_in_dest(self, resource: ProjectScore) -> bool:
        """Check if a project score exists in the destination.

        Args:
            resource: The project score to check

        Returns:
            True if the project score exists in destination
        """
        try:
            # Try to find a project score with the same name in the same destination project
            dest_project_id = self.state.id_mapping.get(resource.project_id)
            if not dest_project_id:
                logger.warning(
                    "No destination project mapping found",
                    source_project_id=resource.project_id,
                    score_name=resource.name,
                )
                return False

            # Use base class helper with project score specific parameters
            additional_params = {"project_score_name": resource.name}
            dest_id = await self._check_resource_exists_by_name(
                resource, "project_scores", additional_params=additional_params
            )

            return dest_id is not None

        except Exception as e:
            logger.warning(
                "Error checking if project score exists in destination",
                error=str(e),
                score_name=resource.name,
                source_project_id=resource.project_id,
            )
            return False

    async def migrate_resource(self, resource: ProjectScore) -> str:
        """Migrate a single project score to the destination.

        Args:
            resource: The project score to migrate

        Returns:
            The ID of the migrated project score

        Raises:
            Exception: If migration fails or no destination project mapping found
        """
        # Get the destination project ID
        # First try the ID mapping, then fall back to the configured dest_project_id
        dest_project_id = self.state.id_mapping.get(resource.project_id)
        if not dest_project_id:
            dest_project_id = self.dest_project_id

        if not dest_project_id:
            error_msg = f"No destination project mapping found for project score '{resource.name}' (source project: {resource.project_id})"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            # Create the project score in the destination
            create_data = {
                "project_id": dest_project_id,
                "name": resource.name,
                "score_type": resource.score_type,
            }

            # Add optional fields if they exist
            if resource.description is not None:
                create_data["description"] = resource.description
            if resource.categories is not None:
                create_data["categories"] = resource.categories
            if resource.config is not None:
                # Handle config with potential function dependencies
                config = await self._resolve_config_dependencies(resource.config)
                create_data["config"] = config

            logger.info(
                "Creating project score in destination",
                score_name=resource.name,
                score_type=resource.score_type,
                dest_project_id=dest_project_id,
            )

            created_score = await self.dest_client.with_retry(
                "create_project_score",
                lambda: self.dest_client.client.project_scores.create(**create_data),
            )

            logger.info(
                "Successfully migrated project score",
                score_name=resource.name,
                source_id=resource.id,
                dest_id=created_score.id,
            )

            return created_score.id

        except Exception as e:
            error_msg = f"Failed to migrate project score '{resource.name}': {e}"
            logger.error(error_msg, source_id=resource.id)
            raise Exception(error_msg) from e

    async def _resolve_config_dependencies(self, config) -> dict:
        """Resolve function dependencies in project score config.

        Args:
            config: The project score config object

        Returns:
            Config with resolved function IDs
        """
        if not config:
            return config

        # Convert to dict if it's not already
        if hasattr(config, "__dict__"):
            config_dict = config.__dict__.copy()
        elif hasattr(config, "model_dump"):
            config_dict = config.model_dump()
        else:
            config_dict = dict(config) if config else {}

        # Handle online scoring config
        if config_dict.get("online"):
            online_config = config_dict["online"]
            if hasattr(online_config, "__dict__"):
                online_dict = online_config.__dict__.copy()
            elif hasattr(online_config, "model_dump"):
                online_dict = online_config.model_dump()
            else:
                online_dict = dict(online_config)

            # Resolve scorer function dependencies
            if online_dict.get("scorers"):
                resolved_scorers = []
                for scorer in online_dict["scorers"]:
                    resolved_scorer = await self._resolve_function_reference(scorer)
                    if resolved_scorer:
                        resolved_scorers.append(resolved_scorer)
                    else:
                        logger.warning(
                            "Failed to resolve scorer function reference",
                            scorer=scorer,
                        )
                online_dict["scorers"] = resolved_scorers
                config_dict["online"] = online_dict

        return config_dict

    async def _resolve_function_reference(self, function_ref) -> dict | None:
        """Resolve a function reference to destination function ID.

        Args:
            function_ref: SavedFunctionId reference

        Returns:
            Resolved function reference or None if resolution failed
        """
        if not function_ref:
            return None

        # Handle different function reference types
        if hasattr(function_ref, "__dict__"):
            ref_dict = function_ref.__dict__.copy()
        elif hasattr(function_ref, "model_dump"):
            ref_dict = function_ref.model_dump()
        else:
            ref_dict = dict(function_ref)

        # Handle function ID type reference
        if ref_dict.get("type") == "function" and "id" in ref_dict:
            source_function_id = ref_dict["id"]
            dest_function_id = self.state.id_mapping.get(source_function_id)
            if dest_function_id:
                return {"type": "function", "id": dest_function_id}
            else:
                logger.warning(
                    "No destination mapping found for function",
                    source_function_id=source_function_id,
                )
                return None

        # Handle global function type reference (no ID mapping needed)
        elif ref_dict.get("type") == "global" and "name" in ref_dict:
            return ref_dict

        else:
            logger.warning("Unknown function reference type", function_ref=ref_dict)
            return None

    async def get_dependencies(self, resource: ProjectScore) -> list[str]:
        """Get the dependencies for a project score.

        Project scores depend on:
        1. Projects (migrated first)
        2. Functions (for online scoring config)

        Args:
            resource: The project score to get dependencies for

        Returns:
            List of dependency IDs
        """
        dependencies = [resource.project_id]

        # Check for function dependencies in config
        if (
            resource.config
            and hasattr(resource.config, "online")
            and resource.config.online
        ):
            online_config = resource.config.online
            if hasattr(online_config, "scorers") and online_config.scorers:
                for scorer in online_config.scorers:
                    if hasattr(scorer, "type") and scorer.type == "function":
                        if hasattr(scorer, "id"):
                            dependencies.append(scorer.id)

        return dependencies

    def get_checksum(self, resource: ProjectScore) -> str:
        """Generate a checksum for a project score.

        Args:
            resource: The project score to generate checksum for

        Returns:
            Checksum string
        """
        # Include key fields that define the project score
        checksum_data = {
            "name": resource.name,
            "score_type": resource.score_type,
            "description": resource.description,
            "categories": resource.categories,
            "config": resource.config,
        }

        return self._compute_checksum(checksum_data)
