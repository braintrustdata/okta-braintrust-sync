"""AI Secrets migrator for Braintrust migration tool."""

from braintrust_api.types.shared import AISecret

from braintrust_migrate.resources.base import ResourceMigrator


class AISecretMigrator(ResourceMigrator[AISecret]):
    """Migrator for Braintrust AI Secrets (AI Provider credentials).

    AI Secrets are organization-scoped and store credentials for AI providers
    like OpenAI, Anthropic, Google, etc. They have no dependencies on other
    resources and should be migrated early in the process.

    Note: Secret values are not exposed in API responses for security reasons.
    During migration, only the secret metadata and configuration are copied,
    not the actual secret values.
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "AISecrets"

    async def get_dependencies(self, resource: AISecret) -> list[str]:
        """Get list of resource IDs that this AI secret depends on.

        AI Secrets have no dependencies on other resources.

        Args:
            resource: AI Secret to get dependencies for.

        Returns:
            Empty list - AI Secrets have no dependencies.
        """
        return []

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[AISecret]:
        """List all AI secrets from the source organization.

        Args:
            project_id: Not used for AI secrets (they are org-scoped).

        Returns:
            List of AI secrets from the source organization.
        """
        try:
            # AI secrets are organization-scoped, not project-scoped
            # Use base class helper but without project_id
            return await self._list_resources_with_client(
                self.source_client, "ai_secrets", project_id=None
            )

        except Exception as e:
            self._logger.error("Failed to list source AI secrets", error=str(e))
            raise

    async def migrate_resource(self, resource: AISecret) -> str:
        """Migrate a single AI secret from source to destination.

        Args:
            resource: Source AI secret to migrate.

        Returns:
            ID of the created AI secret in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.info(
            "Migrating AI secret",
            source_id=resource.id,
            name=resource.name,
            type=getattr(resource, "type", None),
            org_id=getattr(resource, "org_id", None),
        )

        # Create AI secret in destination using base class serialization
        create_params = self.serialize_resource_for_insert(resource)

        # Note: We intentionally do NOT copy the secret value itself
        # for security reasons. The actual secret values must be manually
        # configured in the destination organization by administrators.
        self._logger.warning(
            "AI secret metadata copied - secret value must be manually configured in destination",
            ai_secret_id=resource.id,
            ai_secret_name=resource.name,
            ai_secret_type=getattr(resource, "type", None),
        )

        dest_ai_secret = await self.dest_client.with_retry(
            "create_ai_secret",
            lambda: self.dest_client.client.ai_secrets.create(**create_params),
        )

        self._logger.info(
            "Created AI secret in destination",
            source_id=resource.id,
            dest_id=dest_ai_secret.id,
            name=resource.name,
            type=getattr(resource, "type", None),
        )

        return dest_ai_secret.id
