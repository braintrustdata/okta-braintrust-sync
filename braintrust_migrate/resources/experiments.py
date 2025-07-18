"""Experiment migrator for Braintrust migration tool."""

from typing import Any

from braintrust_api.types import Experiment

from braintrust_migrate.resources.base import MigrationResult, ResourceMigrator


class ExperimentMigrator(ResourceMigrator[Experiment]):
    """Migrator for Braintrust experiments.

    Features:
    - Migrates experiment metadata and settings
    - Migrates all experiment events (evaluations) for each experiment
    - Handles experiment dependencies (base_exp_id, dataset_id)
    - Uses bulk operations for better performance
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Experiments"

    @property
    def allowed_fields_for_event_insert(self) -> set[str] | None:
        """Fields that are allowed when inserting experiment events.

        Uses the InsertExperimentEvent schema from OpenAPI spec.

        Returns:
            Set of field names allowed for insertion, or None if schema not found.
        """
        from braintrust_migrate.openapi_utils import get_resource_create_fields

        return get_resource_create_fields("ExperimentEvent")

    def _sort_experiments_by_dependencies(
        self, experiments: list[Experiment]
    ) -> list[Experiment]:
        """Sort experiments using a simple two-pass approach.

        Pass 1: Experiments without base_exp_id (no dependencies)
        Pass 2: Experiments with base_exp_id (dependent experiments)

        Args:
            experiments: List of experiments to sort

        Returns:
            List of experiments sorted by dependency order
        """
        independent_experiments = []
        dependent_experiments = []

        for exp in experiments:
            if hasattr(exp, "base_exp_id") and exp.base_exp_id:
                dependent_experiments.append(exp)
            else:
                independent_experiments.append(exp)

        self._logger.info(
            "Split experiments by dependencies",
            independent=len(independent_experiments),
            dependent=len(dependent_experiments),
        )

        return independent_experiments + dependent_experiments

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[Experiment]:
        """List all experiments from the source organization, sorted by dependencies."""
        try:
            experiments = await self._list_resources_with_client(
                self.source_client, "experiments", project_id
            )

            if experiments:
                # Sort experiments by dependencies for proper migration order
                experiments = self._sort_experiments_by_dependencies(experiments)

                self._logger.info(
                    "Found experiments for migration",
                    total=len(experiments),
                    project_id=project_id,
                )

            return experiments

        except Exception as e:
            self._logger.error("Failed to list source experiments", error=str(e))
            raise

    async def get_dependencies(self, resource: Experiment) -> list[str]:
        """Get list of resource IDs that this experiment depends on."""
        dependencies = []

        if hasattr(resource, "dataset_id") and resource.dataset_id:
            dependencies.append(resource.dataset_id)

        if hasattr(resource, "base_exp_id") and resource.base_exp_id:
            dependencies.append(resource.base_exp_id)

        return dependencies

    async def get_dependency_types(self) -> list[str]:
        """Get list of resource types that experiments might depend on."""
        return ["datasets", "experiments"]

    async def migrate_batch(self, resources: list[Experiment]) -> list[MigrationResult]:
        """Migrate a batch of experiments with dependency-aware ordering.

        This handles base_exp_id dependencies by:
        1. Creating experiments without base_exp_id first
        2. Recording their new IDs
        3. Creating experiments with base_exp_id using the new mappings
        4. Migrating events for all experiments

        Args:
            resources: List of experiments to migrate.

        Returns:
            List of migration results.
        """
        if not resources:
            return []

        results = []
        experiments_to_create = []

        # Separate experiments by dependency (base_exp_id)
        independent_experiments = []  # No base_exp_id
        dependent_experiments = []  # Has base_exp_id

        for i, experiment in enumerate(resources):
            if hasattr(experiment, "base_exp_id") and experiment.base_exp_id:
                dependent_experiments.append((i, experiment))
            else:
                independent_experiments.append((i, experiment))

        self._logger.info(
            "Batch experiment creation plan",
            total=len(experiments_to_create),
            independent=len(independent_experiments),
            dependent=len(dependent_experiments),
        )

        # Phase 1: Create independent experiments (no base_exp_id)
        if independent_experiments:
            phase1_results = await self._create_experiments_batch(
                independent_experiments, "independent"
            )
            results.extend(phase1_results)

        # Phase 2: Create dependent experiments (with base_exp_id)
        if dependent_experiments:
            phase2_results = await self._create_experiments_batch(
                dependent_experiments, "dependent"
            )
            results.extend(phase2_results)

        # Phase 3: Migrate events for all successfully created experiments
        successful_migrations = [r for r in results if r.success and not r.skipped]
        if successful_migrations:
            await self._migrate_events_for_experiments(successful_migrations)

        return results

    async def _create_experiments_batch(
        self, indexed_experiments: list[tuple[int, Experiment]], phase_name: str
    ) -> list[MigrationResult]:
        """Create a batch of experiments of the same dependency type.

        Args:
            indexed_experiments: List of (index, experiment) tuples
            phase_name: Name for logging (independent/dependent)

        Returns:
            List of migration results for this batch
        """
        if not indexed_experiments:
            return []

        results = []

        self._logger.info(
            f"Creating {phase_name} experiments",
            count=len(indexed_experiments),
        )

        # Create experiments one by one but track results for bulk event migration
        for index, experiment in indexed_experiments:
            source_id = self.get_resource_id(experiment)

            try:
                # Prepare experiment for creation
                create_params = self.serialize_resource_for_insert(experiment)
                create_params["project_id"] = self.dest_project_id

                # Handle dependencies with ID mapping
                if hasattr(experiment, "base_exp_id") and experiment.base_exp_id:
                    dest_base_exp_id = self.state.id_mapping.get(experiment.base_exp_id)
                    if dest_base_exp_id:
                        create_params["base_exp_id"] = dest_base_exp_id
                    else:
                        self._logger.warning(
                            "Could not resolve base experiment dependency",
                            source_base_exp_id=experiment.base_exp_id,
                        )
                        create_params.pop("base_exp_id", None)

                if hasattr(experiment, "dataset_id") and experiment.dataset_id:
                    dest_dataset_id = self.state.id_mapping.get(experiment.dataset_id)
                    if dest_dataset_id:
                        create_params["dataset_id"] = dest_dataset_id
                    else:
                        self._logger.warning(
                            "Could not resolve dataset dependency",
                            source_dataset_id=experiment.dataset_id,
                        )
                        create_params.pop("dataset_id", None)

                # Create experiment
                dest_experiment = await self.dest_client.with_retry(
                    "create_experiment",
                    lambda: self.dest_client.client.experiments.create(**create_params),
                )

                self._logger.info(
                    f"✅ Created {phase_name} experiment",
                    source_id=source_id,
                    dest_id=dest_experiment.id,
                    name=experiment.name,
                )

                # Record success immediately for dependency resolution
                self.record_success(source_id, dest_experiment.id, experiment)

                results.append(
                    MigrationResult(
                        success=True,
                        source_id=source_id,
                        dest_id=dest_experiment.id,
                        metadata={"name": experiment.name, "events_pending": True},
                    )
                )

            except Exception as e:
                error_msg = f"Failed to create {phase_name} experiment: {e}"
                self._logger.error(
                    error_msg,
                    source_id=source_id,
                    name=experiment.name,
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

    async def _migrate_events_for_experiments(
        self, successful_migrations: list[MigrationResult]
    ) -> None:
        """Migrate events for all successfully created experiments.

        Args:
            successful_migrations: List of successful migration results
        """
        self._logger.info(
            "Starting bulk event migration",
            experiment_count=len(successful_migrations),
        )

        for result in successful_migrations:
            try:
                await self._migrate_experiment_events(result.source_id, result.dest_id)

                # Update metadata to indicate events are migrated
                if result.metadata:
                    result.metadata["events_pending"] = False
                    result.metadata["events_migrated"] = True

            except Exception as e:
                self._logger.error(
                    "Failed to migrate events for experiment",
                    source_id=result.source_id,
                    dest_id=result.dest_id,
                    error=str(e),
                )
                # Update metadata to indicate event migration failed
                if result.metadata:
                    result.metadata["events_pending"] = False
                    result.metadata["events_failed"] = True

        self._logger.info(
            "Completed bulk event migration",
            experiment_count=len(successful_migrations),
        )

    async def migrate_resource(self, resource: Experiment) -> str:
        """Migrate a single experiment from source to destination.

        Note: This method is kept for compatibility but migrate_batch should be used
        for better performance when migrating multiple experiments.
        """
        self._logger.info(
            "Migrating experiment",
            source_id=resource.id,
            name=resource.name,
        )

        # Create experiment in destination using base class serialization
        create_params = self.serialize_resource_for_insert(resource)
        create_params["project_id"] = self.dest_project_id

        # Handle dependencies with ID mapping
        if hasattr(resource, "base_exp_id") and resource.base_exp_id:
            dest_base_exp_id = self.state.id_mapping.get(resource.base_exp_id)
            if dest_base_exp_id:
                create_params["base_exp_id"] = dest_base_exp_id
            else:
                self._logger.warning(
                    "Could not resolve base experiment dependency",
                    source_base_exp_id=resource.base_exp_id,
                )
                create_params.pop("base_exp_id", None)

        if hasattr(resource, "dataset_id") and resource.dataset_id:
            dest_dataset_id = self.state.id_mapping.get(resource.dataset_id)
            if dest_dataset_id:
                create_params["dataset_id"] = dest_dataset_id
            else:
                self._logger.warning(
                    "Could not resolve dataset dependency",
                    source_dataset_id=resource.dataset_id,
                )
                create_params.pop("dataset_id", None)

        dest_experiment = await self.dest_client.with_retry(
            "create_experiment",
            lambda: self.dest_client.client.experiments.create(**create_params),
        )

        # Migrate experiment events
        await self._migrate_experiment_events(resource.id, dest_experiment.id)

        return dest_experiment.id

    async def _migrate_experiment_events(
        self, source_experiment_id: str, dest_experiment_id: str
    ) -> None:
        """Migrate events from source experiment to destination experiment."""
        try:
            # Get events from source experiment
            source_events = await self.source_client.with_retry(
                "fetch_experiment_events",
                lambda: self.source_client.client.experiments.fetch(
                    source_experiment_id
                ),
            )

            if (
                not source_events
                or not hasattr(source_events, "events")
                or not source_events.events
            ):
                self._logger.info("No events found in source experiment")
                return

            events_to_insert = []
            for event in source_events.events:
                prepared_event = self._prepare_event_for_insertion(event)
                if prepared_event:
                    events_to_insert.append(prepared_event)

            if events_to_insert:
                # Insert events in batches
                batch_size = min(self.batch_size, 100)
                for i in range(0, len(events_to_insert), batch_size):
                    batch = events_to_insert[i : i + batch_size]

                    await self.dest_client.with_retry(
                        "insert_experiment_events",
                        lambda batch=batch: self.dest_client.client.experiments.insert(
                            experiment_id=dest_experiment_id, events=batch
                        ),
                    )

                self._logger.info(
                    "Migrated experiment events",
                    source_experiment_id=source_experiment_id,
                    dest_experiment_id=dest_experiment_id,
                    event_count=len(events_to_insert),
                )
            else:
                self._logger.info("No valid events to migrate")

        except Exception as e:
            # Handle specific error cases gracefully
            error_str = str(e)
            if "Error code: 303" in error_str:
                self._logger.warning(
                    "Experiment events fetch returned HTTP 303 - skipping events migration",
                    source_experiment_id=source_experiment_id,
                )
                return
            elif "Error code: 404" in error_str:
                self._logger.info(
                    "No events found in source experiment (404)",
                    source_experiment_id=source_experiment_id,
                )
                return
            else:
                self._logger.error(
                    "Failed to migrate experiment events",
                    source_experiment_id=source_experiment_id,
                    error=str(e),
                )

    def _prepare_event_for_insertion(self, event) -> dict[str, Any] | None:
        """Prepare an experiment event for insertion into the destination.

        Uses the same serialization pattern as the base class but simplified for events.

        Args:
            event: Source experiment event to prepare.

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

            # Apply OpenAPI-based field filtering for InsertExperimentEvent schema
            allowed_fields = self.allowed_fields_for_event_insert
            if allowed_fields is None:
                self._logger.error(
                    "No InsertExperimentEvent schema found in OpenAPI spec"
                )
                return None

            filtered_event = {
                field: event_dict[field]
                for field in allowed_fields
                if field in event_dict
            }

            return filtered_event if filtered_event else None

        except Exception as e:
            self._logger.warning(
                "Failed to prepare event for insertion",
                error=str(e),
                event_type=type(event).__name__,
            )
            return None
