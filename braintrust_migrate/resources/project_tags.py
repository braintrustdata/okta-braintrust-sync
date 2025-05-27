"""Project tag migration functionality."""

import structlog
from braintrust_api.types import ProjectTag

from .base import ResourceMigrator

logger = structlog.get_logger(__name__)


class ProjectTagMigrator(ResourceMigrator[ProjectTag]):
    """Migrator for project tags."""

    @property
    def resource_name(self) -> str:
        """Return the name of this resource type."""
        return "project_tags"

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[ProjectTag]:
        """List all project tags from the source organization.

        Args:
            project_id: Optional project ID to filter project tags.

        Returns:
            List of project tags from the source organization.
        """
        try:
            # Use base class helper method with client-side filtering
            return await self._list_resources_with_client(
                self.source_client,
                "project_tags",
                project_id,
                client_side_filter_field="project_id",
            )

        except Exception as e:
            self._logger.error("Failed to list source project tags", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: ProjectTag) -> str | None:
        """Check if a project tag already exists in the destination.

        Args:
            resource: Source project tag to check.

        Returns:
            Destination project tag ID if it exists, None otherwise.
        """
        # Use base class helper method
        additional_params = {"project_tag_name": resource.name}
        return await self._check_resource_exists_by_name(
            resource, "project_tags", additional_params=additional_params
        )

    async def migrate_resource(self, resource: ProjectTag) -> str:
        """Migrate a single project tag to the destination.

        Args:
            resource: The project tag to migrate

        Returns:
            The ID of the migrated project tag

        Raises:
            Exception: If migration fails or no destination project mapping found
        """
        # Get the destination project ID
        # First try the ID mapping, then fall back to the configured dest_project_id
        dest_project_id = self.state.id_mapping.get(resource.project_id)
        if not dest_project_id:
            dest_project_id = self.dest_project_id

        if not dest_project_id:
            error_msg = f"No destination project mapping found for project tag '{resource.name}' (source project: {resource.project_id})"
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            # Create the project tag in the destination
            create_data = {
                "project_id": dest_project_id,
                "name": resource.name,
            }

            # Add optional fields if they exist
            if resource.description is not None:
                create_data["description"] = resource.description
            if resource.color is not None:
                create_data["color"] = resource.color

            logger.info(
                "Creating project tag in destination",
                tag_name=resource.name,
                dest_project_id=dest_project_id,
            )

            created_tag = await self.dest_client.with_retry(
                "create_project_tag",
                lambda: self.dest_client.client.project_tags.create(**create_data),
            )

            logger.info(
                "Successfully migrated project tag",
                tag_name=resource.name,
                source_id=resource.id,
                dest_id=created_tag.id,
            )

            return created_tag.id

        except Exception as e:
            error_msg = f"Failed to migrate project tag '{resource.name}': {e}"
            logger.error(error_msg, source_id=resource.id)
            raise Exception(error_msg) from e

    async def get_dependencies(self, resource: ProjectTag) -> list[str]:
        """Get the dependencies for a project tag.

        Project tags only depend on projects, which are migrated first.

        Args:
            resource: The project tag to get dependencies for

        Returns:
            Empty list since project tags have no dependencies on other migratable resources
        """
        return []
