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
        return "ProjectScores"

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
            create_data = self.serialize_resource_for_insert(resource)

            # Override the project_id with the destination project ID
            create_data["project_id"] = dest_project_id

            # Handle config with potential function dependencies
            if resource.config is not None:
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

        # Convert config to dict and resolve dependencies - all Braintrust objects have to_dict()
        config_dict = config.to_dict()

        # Handle online scoring config with dependency resolution
        if config_dict.get("online"):
            online_config = config_dict["online"]

            # Resolve scorer function dependencies if present
            if online_config.get("scorers"):
                resolved_scorers = []
                for scorer in online_config["scorers"]:
                    resolved_scorer = self._resolve_function_reference_generic(scorer)
                    if resolved_scorer:
                        resolved_scorers.append(resolved_scorer)
                    else:
                        logger.warning(
                            "Failed to resolve scorer function reference",
                            scorer=scorer,
                        )
                online_config["scorers"] = resolved_scorers
                config_dict["online"] = online_config

        return config_dict

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
