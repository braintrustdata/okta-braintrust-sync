"""SpanIframe migrator for Braintrust migration tool."""

import structlog
from braintrust_api.types.shared.span_i_frame import SpanIFrame

from braintrust_migrate.resources.base import ResourceMigrator

logger = structlog.get_logger(__name__)


class SpanIframeMigrator(ResourceMigrator[SpanIFrame]):
    """Migrator for Braintrust span iframes.

    Handles migration of:
    - Span iframe metadata (name, description, url, etc.)
    - Iframe configuration (post_message settings)

    SpanIframes are project-scoped resources with no dependencies on other resources.
    They contain URLs for embedding project viewers in iframes.
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "SpanIFrames"

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[SpanIFrame]:
        """List all span iframes from the source organization.

        Args:
            project_id: Optional project ID to filter span iframes.

        Returns:
            List of span iframes from the source organization.
        """
        try:
            # Use base class helper method with client-side filtering
            return await self._list_resources_with_client(
                self.source_client,
                "span_iframes",
                project_id,
                client_side_filter_field="project_id",
            )

        except Exception as e:
            self._logger.error("Failed to list source span iframes", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: SpanIFrame) -> str | None:
        """Check if a span iframe already exists in the destination.

        Args:
            resource: Source span iframe to check.

        Returns:
            Destination span iframe ID if it exists, None otherwise.
        """
        # Use base class helper method
        additional_params = {"span_iframe_name": resource.name}
        return await self._check_resource_exists_by_name(
            resource, "span_iframes", additional_params=additional_params
        )

    async def migrate_resource(self, resource: SpanIFrame) -> str:
        """Migrate a single span iframe from source to destination.

        Args:
            resource: Source span iframe to migrate.

        Returns:
            ID of the created span iframe in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.info(
            "Migrating span iframe",
            source_id=resource.id,
            name=resource.name,
            project_id=resource.project_id,
        )

        # Create span iframe in destination using base class serialization
        create_params = self.serialize_resource_for_insert(resource)

        # Override the project_id to use destination project
        create_params["project_id"] = self.dest_project_id

        dest_span_iframe = await self.dest_client.with_retry(
            "create_span_iframe",
            lambda: self.dest_client.client.span_iframes.create(**create_params),
        )

        self._logger.info(
            "Created span iframe in destination",
            source_id=resource.id,
            dest_id=dest_span_iframe.id,
            name=resource.name,
        )

        return dest_span_iframe.id

    async def get_dependencies(self, resource: SpanIFrame) -> list[str]:
        """Get dependencies for a span iframe.

        SpanIframes only depend on projects, which are migrated first.
        No other resource dependencies.

        Args:
            resource: SpanIFrame to analyze.

        Returns:
            Empty list (no dependencies on other migratable resources).
        """
        return []
