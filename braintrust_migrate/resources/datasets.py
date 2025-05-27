"""Dataset migrator for Braintrust migration tool."""

import structlog
from braintrust_api.types import Dataset

from braintrust_migrate.resources.base import ResourceMigrator

logger = structlog.get_logger(__name__)


class DatasetMigrator(ResourceMigrator[Dataset]):
    """Migrator for Braintrust datasets.

    Handles migration of:
    - Dataset metadata (name, description, etc.)
    - Dataset records/items
    - Brainstore blobs if enabled
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Datasets"

    @property
    def excluded_fields_for_insert(self) -> set[str]:
        """Fields to exclude when converting dataset records for API insertion.

        Includes base excluded fields plus dataset_id since it's specified
        in the API endpoint path when inserting dataset records.
        """
        return super().excluded_fields_for_insert | {"dataset_id"}

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[Dataset]:
        """List all datasets from the source organization.

        Args:
            project_id: Optional project ID to filter datasets.

        Returns:
            List of source datasets.
        """
        self._logger.info("Listing datasets from source organization")

        try:
            # Use base class helper method
            return await self._list_resources_with_client(
                self.source_client, "datasets", project_id
            )

        except Exception as e:
            self._logger.error("Failed to list source datasets", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: Dataset) -> str | None:
        """Check if a dataset already exists in the destination.

        Args:
            resource: Source dataset to check.

        Returns:
            Destination dataset ID if it exists, None otherwise.
        """
        # Use base class helper method
        additional_params = {"dataset_name": resource.name}
        return await self._check_resource_exists_by_name(
            resource, "datasets", additional_params=additional_params
        )

    async def migrate_resource(self, resource: Dataset) -> str:
        """Migrate a single dataset from source to destination.

        Args:
            resource: Source dataset to migrate.

        Returns:
            ID of the created dataset in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.info(
            "Migrating dataset",
            source_id=resource.id,
            name=resource.name,
            project_id=resource.project_id,
        )

        # Create dataset in destination
        create_params = {
            "name": resource.name,
            "project_id": self.dest_project_id,  # Use destination project ID
        }

        # Copy optional fields if they exist
        if hasattr(resource, "description") and resource.description:
            create_params["description"] = resource.description

        if hasattr(resource, "metadata") and resource.metadata:
            create_params["metadata"] = resource.metadata

        dest_dataset = await self.dest_client.with_retry(
            "create_dataset",
            lambda: self.dest_client.client.datasets.create(**create_params),
        )

        self._logger.info(
            "Created dataset in destination",
            source_id=resource.id,
            dest_id=dest_dataset.id,
            name=resource.name,
        )

        # Migrate dataset records/items
        await self._migrate_dataset_records(resource.id, dest_dataset.id)

        return dest_dataset.id

    async def _migrate_dataset_records(
        self, source_dataset_id: str, dest_dataset_id: str
    ) -> None:
        """Migrate records from source dataset to destination dataset.

        Args:
            source_dataset_id: Source dataset ID.
            dest_dataset_id: Destination dataset ID.
        """
        self._logger.info(
            "Migrating dataset records",
            source_dataset_id=source_dataset_id,
            dest_dataset_id=dest_dataset_id,
        )

        try:
            # Get records from source dataset
            source_records = await self.source_client.with_retry(
                "list_dataset_records",
                lambda: self.source_client.client.datasets.fetch(source_dataset_id),
            )

            if (
                not source_records
                or not hasattr(source_records, "events")
                or not source_records.events
            ):
                self._logger.info("No records found in source dataset")
                return

            records_to_insert = []
            for record in source_records.events:
                # Convert record to insert format using base class method
                try:
                    insert_record = self.serialize_resource_for_insert(record)
                except Exception as e:
                    self._logger.error(
                        "Failed to serialize dataset record - this indicates a bug in serialize_resource_for_insert",
                        error=str(e),
                        record_type=type(record).__name__,
                        source_dataset_id=source_dataset_id,
                    )
                    raise

                records_to_insert.append(insert_record)

            if records_to_insert:
                # Insert records in batches
                batch_size = min(self.batch_size, 100)  # Limit batch size for records
                for i in range(0, len(records_to_insert), batch_size):
                    batch = records_to_insert[i : i + batch_size]

                    await self.dest_client.with_retry(
                        "insert_dataset_records",
                        lambda batch=batch: self.dest_client.client.datasets.insert(
                            dataset_id=dest_dataset_id, events=batch
                        ),
                    )

                self._logger.info(
                    "Migrated dataset records",
                    source_dataset_id=source_dataset_id,
                    dest_dataset_id=dest_dataset_id,
                    record_count=len(records_to_insert),
                )
            else:
                self._logger.info("No valid records to migrate")

        except Exception as e:
            self._logger.error(
                "Failed to migrate dataset records",
                source_dataset_id=source_dataset_id,
                dest_dataset_id=dest_dataset_id,
                error=str(e),
            )
            raise
