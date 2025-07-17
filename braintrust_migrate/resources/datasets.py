"""Dataset migrator for Braintrust migration tool."""

from typing import Any

import structlog
from braintrust_api.types import Dataset

from braintrust_migrate.resources.base import MigrationResult, ResourceMigrator

logger = structlog.get_logger(__name__)


class DatasetMigrator(ResourceMigrator[Dataset]):
    """Migrator for Braintrust datasets.

    Handles migration of:
    - Dataset metadata (name, description, etc.)
    - Dataset records/items
    - Brainstore blobs if enabled
    - Uses bulk operations for better performance
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Datasets"

    @property
    def allowed_fields_for_event_insert(self) -> set[str] | None:
        """Fields that are allowed when inserting dataset events.

        Uses the InsertDatasetEvent schema from OpenAPI spec.

        Returns:
            Set of field names allowed for insertion, or None if schema not found.
        """
        from braintrust_migrate.openapi_utils import get_resource_create_fields

        return get_resource_create_fields("DatasetEvent")

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

    async def migrate_batch(self, resources: list[Dataset]) -> list[MigrationResult]:
        """Migrate a batch of datasets using bulk operations for better performance.

        This overrides the base migrate_batch to:
        1. Create all datasets in the batch
        2. Migrate records for all successfully created datasets

        Args:
            resources: List of datasets to migrate.

        Returns:
            List of migration results.
        """
        if not resources:
            return []

        results = []
        datasets_to_create = []

        # First pass: check for already migrated datasets
        for resource in resources:
            source_id = self.get_resource_id(resource)

            # Check if already migrated
            if source_id in self.state.id_mapping:
                dest_id = self.state.id_mapping[source_id]
                resource_name = getattr(resource, "name", None)

                self._logger.info(
                    "⏭️  Skipped dataset (already migrated)",
                    source_id=source_id,
                    dest_id=dest_id,
                    name=resource_name,
                )

                results.append(
                    MigrationResult(
                        success=True,
                        source_id=source_id,
                        dest_id=dest_id,
                        skipped=True,
                        metadata={
                            "name": resource_name,
                            "skip_reason": "already_migrated",
                        }
                        if resource_name
                        else {"skip_reason": "already_migrated"},
                    )
                )
                continue

            # Prepare for creation
            datasets_to_create.append(resource)

        if not datasets_to_create:
            return results

        # Phase 1: Create all datasets
        self._logger.info(
            "Creating datasets in batch",
            count=len(datasets_to_create),
        )

        dataset_creation_results = await self._create_datasets_batch(datasets_to_create)
        results.extend(dataset_creation_results)

        # Phase 2: Migrate records for all successfully created datasets
        successful_migrations = [
            r for r in dataset_creation_results if r.success and not r.skipped
        ]
        if successful_migrations:
            await self._migrate_records_for_datasets(successful_migrations)

        return results

    async def _create_datasets_batch(
        self, datasets: list[Dataset]
    ) -> list[MigrationResult]:
        """Create a batch of datasets.

        Args:
            datasets: List of datasets to create

        Returns:
            List of migration results for dataset creation
        """
        results = []

        for dataset in datasets:
            source_id = self.get_resource_id(dataset)

            try:
                # Create dataset in destination using base class serialization
                create_params = self.serialize_resource_for_insert(dataset)
                create_params["project_id"] = self.dest_project_id

                dest_dataset = await self.dest_client.with_retry(
                    "create_dataset",
                    lambda: self.dest_client.client.datasets.create(**create_params),
                )

                self._logger.info(
                    "✅ Created dataset",
                    source_id=source_id,
                    dest_id=dest_dataset.id,
                    name=dataset.name,
                )

                # Record success immediately for any potential dependencies
                self.record_success(source_id, dest_dataset.id, dataset)

                results.append(
                    MigrationResult(
                        success=True,
                        source_id=source_id,
                        dest_id=dest_dataset.id,
                        metadata={"name": dataset.name, "records_pending": True},
                    )
                )

            except Exception as e:
                error_msg = f"Failed to create dataset: {e}"
                self._logger.error(
                    error_msg,
                    source_id=source_id,
                    name=dataset.name,
                )

                self.record_failure(source_id, error_msg)
                results.append(
                    MigrationResult(
                        success=False,
                        source_id=source_id,
                        error=error_msg,
                    )
                )

        return results

    async def _migrate_records_for_datasets(
        self, successful_migrations: list[MigrationResult]
    ) -> None:
        """Migrate records for all successfully created datasets.

        Args:
            successful_migrations: List of successful dataset migration results
        """
        self._logger.info(
            "Starting bulk record migration",
            dataset_count=len(successful_migrations),
        )

        for result in successful_migrations:
            try:
                await self._migrate_dataset_records(result.source_id, result.dest_id)

                # Update metadata to indicate records are migrated
                if result.metadata:
                    result.metadata["records_pending"] = False
                    result.metadata["records_migrated"] = True

            except Exception as e:
                self._logger.error(
                    "Failed to migrate records for dataset",
                    source_id=result.source_id,
                    dest_id=result.dest_id,
                    error=str(e),
                )
                # Update metadata to indicate record migration failed
                if result.metadata:
                    result.metadata["records_pending"] = False
                    result.metadata["records_failed"] = True

        self._logger.info(
            "Completed bulk record migration",
            dataset_count=len(successful_migrations),
        )

    async def migrate_resource(self, resource: Dataset) -> str:
        """Migrate a single dataset from source to destination.

        Note: This method is kept for compatibility but migrate_batch should be used
        for better performance when migrating multiple datasets.

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

        # Create dataset in destination using base class serialization
        create_params = self.serialize_resource_for_insert(resource)

        # Override the project_id to use destination project
        create_params["project_id"] = self.dest_project_id

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
                # Convert record to insert format using dataset event-specific method
                prepared_record = self._prepare_event_for_insertion(record)
                if prepared_record:
                    records_to_insert.append(prepared_record)

            if records_to_insert:
                # Insert records in batches using bulk insert API
                self._logger.info(
                    "Bulk inserting dataset records",
                    record_count=len(records_to_insert),
                    dataset_id=dest_dataset_id,
                )

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

    def _prepare_event_for_insertion(self, event) -> dict[str, Any] | None:
        """Prepare a dataset event for insertion into the destination.

        Uses the same serialization pattern as the base class but for dataset events.

        Args:
            event: Source dataset event to prepare.

        Returns:
            Dictionary ready for insertion, or None if preparation failed.
        """
        try:
            # Serialize using to_dict (all Braintrust API objects have this method)
            event_dict = event.to_dict(
                mode="json",
                exclude_unset=True,
                exclude_none=True,
            )

            if not event_dict:
                return None

            # Apply OpenAPI-based field filtering for InsertDatasetEvent schema
            allowed_fields = self.allowed_fields_for_event_insert
            if allowed_fields is None:
                self._logger.error("No InsertDatasetEvent schema found in OpenAPI spec")
                return None

            filtered_event = {
                field: event_dict[field]
                for field in allowed_fields
                if field in event_dict
            }

            return filtered_event if filtered_event else None

        except Exception as e:
            self._logger.warning(
                "Failed to prepare dataset event for insertion",
                error=str(e),
                event_type=type(event).__name__,
            )
            return None
