"""Logs migrator for Braintrust migration tool."""

from braintrust_api.types import ProjectLogsEvent

from braintrust_migrate.resources.base import ResourceMigrator


class LogsMigrator(ResourceMigrator[ProjectLogsEvent]):
    """Migrator for Braintrust project logs."""

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Logs"

    @property
    def excluded_fields_for_insert(self) -> set[str]:
        """Fields to exclude when converting log events for API insertion.

        Includes base excluded fields plus log_id since it's specified
        in the API endpoint path when inserting log events.
        """
        return super().excluded_fields_for_insert | {"log_id"}

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

    async def resource_exists_in_dest(self, resource: ProjectLogsEvent) -> str | None:
        """Check if a log event already exists in the destination.

        Args:
            resource: Source log event to check.

        Returns:
            Destination log event ID if it exists, None otherwise.

        Note:
            For logs, we typically don't check for existence since each log
            event is unique and should be migrated. This method returns None
            to ensure all logs are migrated.
        """
        # Log events are typically unique and should all be migrated
        # We don't check for duplicates to avoid missing any log data
        return None

    async def migrate_resource(self, resource: ProjectLogsEvent) -> str:
        """Migrate a single log event from source to destination.

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
