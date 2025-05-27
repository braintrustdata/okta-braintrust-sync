"""Agent migrator for Braintrust migration tool."""

from typing import Any

from braintrust_migrate.resources.base import ResourceMigrator


class AgentMigrator(ResourceMigrator[Any]):
    """Migrator for Braintrust agents.

    Note: Agents don't appear to have dedicated API endpoints in the current
    Braintrust API, so this migrator serves as a placeholder for future
    implementation when agent endpoints become available.
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Agents"

    async def list_source_resources(self, project_id: str | None = None) -> list[Any]:
        """List all agents from the source organization.

        Args:
            project_id: Optional project ID to filter agents.

        Returns:
            Empty list since agent endpoints are not yet available.
        """
        self._logger.info(
            "Agent migration not yet implemented - no dedicated agent API endpoints found"
        )
        return []

    async def get_resource_id(self, resource: Any) -> str:
        """Extract the unique ID from an agent.

        Args:
            resource: Agent object.

        Returns:
            Unique identifier for the agent.
        """
        return resource.id if hasattr(resource, "id") else str(resource)

    async def resource_exists_in_dest(self, resource: Any) -> str | None:
        """Check if an agent already exists in the destination.

        Args:
            resource: Source agent to check.

        Returns:
            None since agent migration is not yet implemented.
        """
        return None

    async def migrate_resource(self, resource: Any) -> str:
        """Migrate a single agent from source to destination.

        Args:
            resource: Source agent to migrate.

        Returns:
            ID of the created agent in destination.

        Raises:
            NotImplementedError: Agent migration is not yet implemented.
        """
        raise NotImplementedError(
            "Agent migration not yet implemented - no dedicated agent API endpoints found. "
            "Agents may be implemented as functions or prompts in the current API."
        )
