"""Logs migrator for Braintrust migration tool."""

from braintrust_api.types import ProjectLogsEvent

from braintrust_migrate.resources.base import MigrationResult, ResourceMigrator


class LogsMigrator(ResourceMigrator[ProjectLogsEvent]):
    """Migrator for Braintrust project logs."""

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Logs"

    def get_resource_id(self, resource: ProjectLogsEvent) -> str:
        """Get the unique identifier for a log event.

        Args:
            resource: The log event resource.

        Returns:
            The unique identifier for the log event.
        """
        return resource.id

    async def list_source_resources(
        self, project_id: str | None = None
    ) -> list[ProjectLogsEvent]:
        """List all logs from the source organization.

        Args:
            project_id: Optional project ID to filter logs.

        Returns:
            List of logs from the source organization.
        """
        try:
            # Logs require special handling since they're fetched differently
            if not project_id:
                self._logger.warning("Project ID is required for logs migration")
                return []

            # Get logs for the specific project
            logs_response = await self.source_client.with_retry(
                "list_project_logs",
                lambda: self.source_client.client.projects.logs.fetch(
                    project_id=project_id
                ),
            )

            # The response is a FetchProjectLogsEventsResponse object
            # We need to extract the actual events from it
            if hasattr(logs_response, "events"):
                # If the response has an 'events' attribute, use it
                events = logs_response.events
            elif hasattr(logs_response, "data"):
                # If the response has a 'data' attribute, use it
                events = logs_response.data
            elif hasattr(logs_response, "__iter__"):
                # If the response is iterable, convert to list
                events = list(logs_response)
            else:
                # Fallback: try to convert the response directly
                self._logger.warning(
                    "Unknown logs response format, attempting direct conversion",
                    response_type=type(logs_response).__name__,
                    response_attrs=dir(logs_response),
                )
                events = [logs_response] if logs_response else []

            # Convert to list if needed
            if not isinstance(events, list):
                events = list(events) if events else []

            self._logger.info(
                f"Retrieved {len(events)} log events from project",
                project_id=project_id,
                response_type=type(logs_response).__name__,
            )

            return events

        except Exception as e:
            self._logger.error("Failed to list source logs", error=str(e))
            raise

    async def migrate_batch(
        self, resources: list[ProjectLogsEvent]
    ) -> list[MigrationResult]:
        """Migrate a batch of log events using bulk insert for better performance.

        This overrides the base migrate_batch to take advantage of the Braintrust API's
        ability to insert multiple log events in a single API call.

        Args:
            resources: List of log events to migrate.

        Returns:
            List of migration results.
        """
        if not resources:
            return []

        results = []
        events_to_insert = []
        resource_map = {}  # Maps array index to resource for result creation

        for resource in resources:
            source_id = self.get_resource_id(resource)

            # Prepare for bulk insert
            try:
                insert_event = self.serialize_resource_for_insert(resource)
                insert_index = len(events_to_insert)
                events_to_insert.append(insert_event)
                resource_map[insert_index] = resource
            except Exception as e:
                error_msg = f"Failed to serialize log event: {e}"
                self.record_failure(source_id, error_msg)
                results.append(
                    MigrationResult(
                        success=False,
                        source_id=source_id,
                        error=error_msg,
                    )
                )

        # Perform bulk insert if we have events to insert
        if events_to_insert:
            try:
                self._logger.info(
                    f"Bulk inserting {len(events_to_insert)} log events",
                    project_id=self.dest_project_id,
                )

                insert_response = await self.dest_client.with_retry(
                    "bulk_insert_log_events",
                    lambda: self.dest_client.client.projects.logs.insert(
                        project_id=self.dest_project_id, events=events_to_insert
                    ),
                )

                # Process the bulk insert response
                if hasattr(insert_response, "row_ids") and insert_response.row_ids:
                    row_ids = insert_response.row_ids

                    # Ensure we have the same number of row_ids as events inserted
                    if len(row_ids) != len(events_to_insert):
                        self._logger.warning(
                            f"Mismatch between inserted events ({len(events_to_insert)}) and returned row_ids ({len(row_ids)})"
                        )

                    # Create success results for each inserted event
                    for i, row_id in enumerate(row_ids):
                        if i in resource_map:
                            resource = resource_map[i]
                            source_id = self.get_resource_id(resource)

                            self._logger.debug(
                                "Created log event in destination",
                                source_id=source_id,
                                dest_id=row_id,
                            )

                            self.record_success(source_id, row_id, resource)
                            results.append(
                                MigrationResult(
                                    success=True,
                                    source_id=source_id,
                                    dest_id=row_id,
                                    metadata={},
                                )
                            )
                        else:
                            self._logger.warning(
                                f"No resource mapping found for index {i}"
                            )

                else:
                    # Fallback: create generic IDs if row_ids not available
                    self._logger.warning(
                        "No row_ids returned from bulk insert, using fallback IDs"
                    )
                    for i, resource in resource_map.items():
                        source_id = self.get_resource_id(resource)
                        dest_id = f"migrated_{source_id}"

                        self.record_success(source_id, dest_id, resource)
                        results.append(
                            MigrationResult(
                                success=True,
                                source_id=source_id,
                                dest_id=dest_id,
                                metadata={},
                            )
                        )

            except Exception as e:
                error_msg = f"Bulk insert failed: {e}"
                self._logger.error("Failed to bulk insert log events", error=str(e))

                # Mark all events as failed
                for resource in resource_map.values():
                    source_id = self.get_resource_id(resource)
                    self.record_failure(source_id, error_msg)
                    results.append(
                        MigrationResult(
                            success=False,
                            source_id=source_id,
                            error=error_msg,
                        )
                    )

        return results

    async def migrate_resource(self, resource: ProjectLogsEvent) -> str:
        """Migrate a single log event from source to destination.

        Note: This method is kept for compatibility but migrate_batch should be used
        for better performance when migrating multiple log events.

        Args:
            resource: Source log event to migrate.

        Returns:
            ID of the created log event in destination.

        Raises:
            Exception: If migration fails.
        """
        self._logger.debug(
            "Migrating log event",
            source_id=resource.id,
            project_id=getattr(resource, "project_id", "unknown"),
        )

        # Convert log event to insert format using base class method
        insert_event = self.serialize_resource_for_insert(resource)

        # Insert the log event into destination project
        insert_response = await self.dest_client.with_retry(
            "insert_log_event",
            lambda: self.dest_client.client.projects.logs.insert(
                project_id=self.dest_project_id, events=[insert_event]
            ),
        )

        # Extract the ID from the response
        if (
            hasattr(insert_response, "row_ids")
            and insert_response.row_ids
            and len(insert_response.row_ids) > 0
        ):
            dest_id = insert_response.row_ids[0]
        else:
            # Fallback if row_ids not available
            dest_id = f"migrated_{resource.id}"

        self._logger.debug(
            "Created log event in destination",
            source_id=resource.id,
            dest_id=dest_id,
        )

        return dest_id
