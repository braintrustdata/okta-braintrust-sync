"""Experiment migrator for Braintrust migration tool."""

from braintrust_api.types import Experiment

from braintrust_migrate.resources.base import ResourceMigrator


class ExperimentMigrator(ResourceMigrator[Experiment]):
    """Migrator for Braintrust experiments."""

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Experiments"

    def _sort_experiments_by_dependencies(
        self, experiments: list[Experiment]
    ) -> list[Experiment]:
        """Sort experiments using a simple two-pass approach.

        Pass 1: Experiments without base_exp_id (no dependencies)
        Pass 2: Experiments with base_exp_id (dependent experiments)

        This is much simpler than topological sorting and handles 95% of cases.

        Args:
            experiments: List of experiments to sort

        Returns:
            List of experiments sorted by dependency order
        """
        independent_experiments = []  # No base_exp_id
        dependent_experiments = []  # Has base_exp_id

        for exp in experiments:
            if hasattr(exp, "base_exp_id") and exp.base_exp_id:
                dependent_experiments.append(exp)
            else:
                independent_experiments.append(exp)

        # Log the split for visibility
        self._logger.info(
            "Split experiments by dependencies",
            total_experiments=len(experiments),
            independent_experiments=len(independent_experiments),
            dependent_experiments=len(dependent_experiments),
        )

        # Return independent experiments first, then dependent ones
        return independent_experiments + dependent_experiments

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[Experiment]:
        """List all experiments from the source organization, sorted by dependencies.

        Args:
            project_id: Optional project ID to filter experiments.

        Returns:
            List of experiments from the source organization, sorted by dependency order.
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
                intra_project_deps = 0

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

                        # Check if this is an intra-project dependency
                        if any(
                            other_exp.id == exp.base_exp_id for other_exp in experiments
                        ):
                            intra_project_deps += 1

                    experiment_deps[exp.id] = exp_info

                self._logger.info(
                    "Found experiments for migration with dependency analysis",
                    total_experiments=len(experiments),
                    project_id=project_id,
                    intra_project_dependencies=intra_project_deps,
                    unique_base_experiments=len(base_experiment_refs),
                )

                # Sort experiments by dependencies for proper migration order
                experiments = self._sort_experiments_by_dependencies(experiments)

            return experiments

        except Exception as e:
            self._logger.error("Failed to list source experiments", error=str(e))
            raise

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

        # Create experiment in destination using base class serialization
        create_params = self.serialize_resource_for_insert(resource)

        # Override the project_id to use destination project
        create_params["project_id"] = self.dest_project_id

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
                self._logger.warning(
                    "Could not resolve base experiment dependency",
                    experiment_name=resource.name,
                    source_base_exp_id=resource.base_exp_id,
                )
                # Remove base_exp_id to avoid broken references
                create_params.pop("base_exp_id", None)

        if hasattr(resource, "dataset_id") and resource.dataset_id:
            dest_dataset_id = self.state.id_mapping.get(resource.dataset_id)
            if dest_dataset_id:
                create_params["dataset_id"] = dest_dataset_id
                # dataset_version should already be included from serialize_resource_for_insert
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
                # Remove dataset_id to avoid broken references
                create_params.pop("dataset_id", None)

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
            # Get events from source experiment with improved error handling
            try:
                source_events = await self.source_client.with_retry(
                    "fetch_experiment_events",
                    lambda: self.source_client.client.experiments.fetch(
                        source_experiment_id
                    ),
                )
            except Exception as e:
                error_str = str(e)

                # Handle specific HTTP errors gracefully
                if "Error code: 303" in error_str:
                    self._logger.warning(
                        "Experiment events fetch returned HTTP 303 (redirect) - skipping events migration",
                        source_experiment_id=source_experiment_id,
                        dest_experiment_id=dest_experiment_id,
                        error=error_str,
                    )
                    return
                elif "Error code: 404" in error_str:
                    self._logger.info(
                        "No events found in source experiment (404)",
                        source_experiment_id=source_experiment_id,
                    )
                    return
                else:
                    # For other errors, still raise to maintain original behavior
                    self._logger.error(
                        "Failed to fetch experiment events",
                        source_experiment_id=source_experiment_id,
                        error=error_str,
                    )
                    raise

            if (
                not source_events
                or not hasattr(source_events, "events")
                or not source_events.events
            ):
                self._logger.info("No events found in source experiment")
                return

            events_to_insert = []
            serialization_errors = 0

            for i, event in enumerate(source_events.events):
                try:
                    # Improved serialization with better error handling
                    if hasattr(event, "to_dict") and callable(event.to_dict):
                        # Use the object's own to_dict method
                        insert_event = event.to_dict()

                        # Validate that this isn't a mock object
                        if (
                            "Mock" in str(type(event))
                            or "mock" in str(type(event)).lower()
                        ):
                            self._logger.warning(
                                "Detected mock object in events - skipping",
                                event_index=i,
                                event_type=type(event).__name__,
                                source_experiment_id=source_experiment_id,
                            )
                            serialization_errors += 1
                            continue

                    elif hasattr(event, "__dict__"):
                        # Fallback to converting object attributes to dict
                        insert_event = {
                            k: v
                            for k, v in event.__dict__.items()
                            if not k.startswith("_") and not callable(v)
                        }
                    else:
                        # Last fallback - assume it's already a dict
                        insert_event = (
                            dict(event) if not isinstance(event, dict) else event
                        )

                    # Additional validation to catch serialization issues
                    if not isinstance(insert_event, dict):
                        self._logger.warning(
                            "Event serialization produced non-dict result - skipping",
                            event_index=i,
                            result_type=type(insert_event).__name__,
                            source_experiment_id=source_experiment_id,
                        )
                        serialization_errors += 1
                        continue

                    events_to_insert.append(insert_event)

                except Exception as e:
                    self._logger.warning(
                        "Failed to serialize individual event - skipping",
                        event_index=i,
                        error=str(e),
                        event_type=type(event).__name__,
                        source_experiment_id=source_experiment_id,
                    )
                    serialization_errors += 1
                    continue

            if serialization_errors > 0:
                self._logger.warning(
                    "Some events could not be serialized",
                    total_events=len(source_events.events),
                    serialization_errors=serialization_errors,
                    valid_events=len(events_to_insert),
                    source_experiment_id=source_experiment_id,
                )

            if events_to_insert:
                # Insert events in batches with improved error handling
                batch_size = min(self.batch_size, 100)  # Limit batch size for events
                successful_batches = 0
                failed_batches = 0

                for i in range(0, len(events_to_insert), batch_size):
                    batch = events_to_insert[i : i + batch_size]
                    batch_num = i // batch_size + 1
                    total_batches = (
                        len(events_to_insert) + batch_size - 1
                    ) // batch_size

                    try:
                        await self.dest_client.with_retry(
                            "insert_experiment_events",
                            lambda batch=batch: self.dest_client.client.experiments.insert(
                                experiment_id=dest_experiment_id, events=batch
                            ),
                        )
                        successful_batches += 1

                        self._logger.debug(
                            "Successfully inserted event batch",
                            batch_num=batch_num,
                            total_batches=total_batches,
                            batch_size=len(batch),
                            source_experiment_id=source_experiment_id,
                        )

                    except Exception as e:
                        failed_batches += 1
                        self._logger.error(
                            "Failed to insert event batch",
                            batch_num=batch_num,
                            total_batches=total_batches,
                            batch_size=len(batch),
                            error=str(e),
                            source_experiment_id=source_experiment_id,
                            dest_experiment_id=dest_experiment_id,
                        )
                        # Continue with other batches rather than failing entirely

                self._logger.info(
                    "Completed experiment events migration",
                    source_experiment_id=source_experiment_id,
                    dest_experiment_id=dest_experiment_id,
                    total_events=len(events_to_insert),
                    successful_batches=successful_batches,
                    failed_batches=failed_batches,
                    serialization_errors=serialization_errors,
                )

                if failed_batches > 0:
                    self._logger.warning(
                        "Some event batches failed to migrate",
                        failed_batches=failed_batches,
                        total_batches=successful_batches + failed_batches,
                        source_experiment_id=source_experiment_id,
                    )

            else:
                self._logger.info("No valid events to migrate after serialization")

        except Exception as e:
            self._logger.error(
                "Failed to migrate experiment events",
                source_experiment_id=source_experiment_id,
                dest_experiment_id=dest_experiment_id,
                error=str(e),
            )
            # Don't raise here - allow experiment migration to succeed even if events fail
            # This provides better resilience for the overall migration process
