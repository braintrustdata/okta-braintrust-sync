"""Experiment migrator for Braintrust migration tool."""

from braintrust_api.types import Experiment

from braintrust_migrate.resources.base import ResourceMigrator


class ExperimentMigrator(ResourceMigrator[Experiment]):
    """Migrator for Braintrust experiments."""

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Experiments"

    @property
    def excluded_fields_for_insert(self) -> set[str]:
        """Fields to exclude when converting experiment events for API insertion.

        Includes base excluded fields plus experiment_id since it's specified
        in the API endpoint path when inserting experiment events.
        """
        return super().excluded_fields_for_insert | {"experiment_id"}

    async def get_dependencies(self, resource: Experiment) -> list[str]:
        """Get list of resource IDs that this experiment depends on.

        Experiments can depend on:
        1. Other experiments via base_exp_id (baseline experiment for comparisons)
        2. Datasets via dataset_id (linked dataset)

        Args:
            resource: Experiment to get dependencies for.

        Returns:
            List of resource IDs this experiment depends on.
        """
        dependencies = []

        # Include dataset dependencies
        if hasattr(resource, "dataset_id") and resource.dataset_id:
            dependencies.append(resource.dataset_id)
            self._logger.debug(
                "Found dataset dependency",
                experiment_id=resource.id,
                experiment_name=resource.name,
                dataset_id=resource.dataset_id,
            )

        # Include base experiment dependencies
        if hasattr(resource, "base_exp_id") and resource.base_exp_id:
            dependencies.append(resource.base_exp_id)
            self._logger.debug(
                "Found base experiment dependency",
                experiment_id=resource.id,
                base_exp_id=resource.base_exp_id,
            )

        return dependencies

    async def get_dependency_types(self) -> list[str]:
        """Get list of resource types that experiments might depend on.

        Returns:
            List of resource type names that experiments can depend on.
        """
        return ["datasets", "experiments"]

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[Experiment]:
        """List all experiments from the source organization.

        Args:
            project_id: Optional project ID to filter experiments.

        Returns:
            List of experiments from the source organization.
        """
        try:
            # Use base class helper method
            experiments = await self._list_resources_with_client(
                self.source_client, "experiments", project_id
            )

            # Log experiment dependency structure for debugging
            if experiments:
                experiment_deps = {}
                base_experiment_refs = {}

                for exp in experiments:
                    exp_info = {
                        "name": exp.name,
                        "project_id": exp.project_id,
                        "has_base_exp": hasattr(exp, "base_exp_id")
                        and exp.base_exp_id is not None,
                        "has_dataset": hasattr(exp, "dataset_id")
                        and exp.dataset_id is not None,
                    }

                    if hasattr(exp, "base_exp_id") and exp.base_exp_id:
                        exp_info["base_exp_id"] = exp.base_exp_id
                        base_experiment_refs[exp.base_exp_id] = (
                            base_experiment_refs.get(exp.base_exp_id, 0) + 1
                        )

                    experiment_deps[exp.id] = exp_info

                self._logger.info(
                    "Found experiments for migration",
                    total_experiments=len(experiments),
                    project_id=project_id,
                )

            return experiments

        except Exception as e:
            self._logger.error("Failed to list source experiments", error=str(e))
            raise

    async def resource_exists_in_dest(self, resource: Experiment) -> str | None:
        """Check if an experiment already exists in the destination.

        Args:
            resource: Source experiment to check.

        Returns:
            Destination experiment ID if it exists, None otherwise.
        """
        # Use base class helper method
        additional_params = {"experiment_name": resource.name}
        return await self._check_resource_exists_by_name(
            resource, "experiments", additional_params=additional_params
        )

    async def migrate_resource(self, resource: Experiment) -> str:
        """Migrate a single experiment from source to destination.

        Args:
            resource: Source experiment to migrate.

        Returns:
            ID of the created experiment in destination.

        Raises:
            Exception: If migration fails.
        """
        # Get dependencies first to log them
        dependencies = await self.get_dependencies(resource)

        self._logger.info(
            "Starting experiment migration with dependency analysis",
            source_id=resource.id,
            name=resource.name,
            project_id=resource.project_id,
            dependencies=dependencies,
            has_base_exp=hasattr(resource, "base_exp_id")
            and resource.base_exp_id is not None,
            has_dataset=hasattr(resource, "dataset_id")
            and resource.dataset_id is not None,
            base_exp_id=getattr(resource, "base_exp_id", None),
            dataset_id=getattr(resource, "dataset_id", None),
        )

        # Create experiment in destination
        create_params = {
            "project_id": self.dest_project_id,  # Use destination project ID
        }

        # Copy optional fields if they exist
        if hasattr(resource, "name") and resource.name:
            create_params["name"] = resource.name

        if hasattr(resource, "description") and resource.description:
            create_params["description"] = resource.description

        if hasattr(resource, "repo_info") and resource.repo_info:
            create_params["repo_info"] = resource.repo_info

        if hasattr(resource, "public") and resource.public is not None:
            create_params["public"] = resource.public

        if hasattr(resource, "metadata") and resource.metadata:
            create_params["metadata"] = resource.metadata

        # Handle dependencies with ID mapping
        if hasattr(resource, "base_exp_id") and resource.base_exp_id:
            dest_base_exp_id = self.state.id_mapping.get(resource.base_exp_id)
            if dest_base_exp_id:
                create_params["base_exp_id"] = dest_base_exp_id
                self._logger.debug(
                    "Resolved base experiment dependency",
                    experiment_name=resource.name,
                    dest_base_exp_id=dest_base_exp_id,
                )
            else:
                # Get some context about what mappings we DO have
                experiment_mappings = {
                    src_id: dst_id
                    for src_id, dst_id in self.state.id_mapping.items()
                    if src_id
                    != resource.base_exp_id  # Don't include the one we're looking for
                }

                # Find experiments in our current project
                project_experiment_mappings = {}
                dataset_mappings = {}
                other_mappings = {}

                for src_id, dst_id in self.state.id_mapping.items():
                    # Try to categorize mappings to understand what we have
                    if (
                        "experiment" in str(src_id).lower()
                        or len(
                            [
                                k
                                for k in self.state.id_mapping.keys()
                                if k.startswith(src_id[:8])
                            ]
                        )
                        > 1
                    ):
                        project_experiment_mappings[src_id] = dst_id
                    elif "dataset" in str(src_id).lower():
                        dataset_mappings[src_id] = dst_id
                    else:
                        other_mappings[src_id] = dst_id

                self._logger.warning(
                    "Could not resolve base experiment dependency",
                    experiment_name=resource.name,
                    source_base_exp_id=resource.base_exp_id,
                )
                # Continue without base_exp_id rather than fail

        if hasattr(resource, "dataset_id") and resource.dataset_id:
            dest_dataset_id = self.state.id_mapping.get(resource.dataset_id)
            if dest_dataset_id:
                create_params["dataset_id"] = dest_dataset_id
                # Also copy dataset_version if present
                if hasattr(resource, "dataset_version") and resource.dataset_version:
                    create_params["dataset_version"] = resource.dataset_version
                self._logger.debug(
                    "Resolved dataset dependency",
                    source_dataset_id=resource.dataset_id,
                    dest_dataset_id=dest_dataset_id,
                    dataset_version=getattr(resource, "dataset_version", None),
                )
            else:
                self._logger.warning(
                    "Could not resolve dataset dependency",
                    source_dataset_id=resource.dataset_id,
                )
                # Continue without dataset_id rather than fail

        dest_experiment = await self.dest_client.with_retry(
            "create_experiment",
            lambda: self.dest_client.client.experiments.create(**create_params),
        )

        self._logger.info(
            "Created experiment in destination",
            source_id=resource.id,
            dest_id=dest_experiment.id,
            name=resource.name,
        )

        # Migrate experiment events/logs
        await self._migrate_experiment_events(resource.id, dest_experiment.id)

        return dest_experiment.id

    async def _migrate_experiment_events(
        self, source_experiment_id: str, dest_experiment_id: str
    ) -> None:
        """Migrate events from source experiment to destination experiment.

        Args:
            source_experiment_id: Source experiment ID.
            dest_experiment_id: Destination experiment ID.
        """
        self._logger.info(
            "Migrating experiment events",
            source_experiment_id=source_experiment_id,
            dest_experiment_id=dest_experiment_id,
        )

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
                # Convert event to insert format using base class method
                try:
                    insert_event = self.serialize_resource_for_insert(event)
                except Exception as e:
                    self._logger.error(
                        "Failed to serialize event - this indicates a bug in serialize_resource_for_insert",
                        error=str(e),
                        event_type=type(event).__name__,
                        source_experiment_id=source_experiment_id,
                    )
                    raise

                events_to_insert.append(insert_event)

            if events_to_insert:
                # Insert events in batches
                batch_size = min(self.batch_size, 100)  # Limit batch size for events
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
            self._logger.error(
                "Failed to migrate experiment events",
                source_experiment_id=source_experiment_id,
                dest_experiment_id=dest_experiment_id,
                error=str(e),
            )
            raise
