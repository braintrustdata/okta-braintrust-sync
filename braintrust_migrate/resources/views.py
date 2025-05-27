"""View migrator for Braintrust migration tool."""

from braintrust_api.types import View

from braintrust_migrate.resources.base import ResourceMigrator


class ViewMigrator(ResourceMigrator[View]):
    """Migrator for Braintrust views.

    Views are saved table configurations that define how data is displayed
    in the Braintrust UI, including filters, sorting, column visibility,
    and other display options.
    """

    @property
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        return "Views"

    async def get_dependencies(self, resource: View) -> list[str]:
        """Get list of resource IDs that this view depends on.

        Views can depend on other resources via object_id:
        - Projects (handled by dest_project_id mapping)
        - Experiments (need ID mapping)
        - Datasets (need ID mapping)
        - Other object types as they become available

        Args:
            resource: View to get dependencies for.

        Returns:
            List of resource IDs this view depends on.
        """
        dependencies = []

        # Check object_id dependency based on object_type
        if hasattr(resource, "object_id") and resource.object_id:
            object_type = getattr(resource, "object_type", None)

            # Only add as dependency if it's not a project (projects are handled separately)
            if object_type and object_type != "project":
                dependencies.append(resource.object_id)
                self._logger.debug(
                    "Found object dependency",
                    view_id=resource.id,
                    view_name=resource.name,
                    object_type=object_type,
                    object_id=resource.object_id,
                )

        return dependencies

    async def list_source_resources(self, project_id: str | None = None) -> list[View]:
        """List all views from the source organization.

        Since the Views API requires object_id and object_type parameters,
        we need to discover views by querying for each known object.

        Args:
            project_id: Optional project ID to filter views.

        Returns:
            List of views from the source organization.
        """
        try:
            all_views = []

            # Define object types we want to discover views for
            object_types_to_check = ["project", "experiment", "dataset"]

            for object_type in object_types_to_check:
                try:
                    # Get object IDs to check based on type
                    object_ids = await self._get_object_ids_for_type(
                        object_type, project_id
                    )

                    # Query views for each object
                    for object_id in object_ids:
                        try:
                            views_response = await self.source_client.with_retry(
                                f"list_views_{object_type}_{object_id}",
                                lambda object_id=object_id,
                                object_type=object_type: self.source_client.client.views.list(
                                    object_id=object_id, object_type=object_type
                                ),
                            )

                            # Convert response to list and add to results
                            views = await self._handle_api_response_to_list(
                                views_response
                            )
                            all_views.extend(views)

                            if views:
                                self._logger.debug(
                                    f"Found {len(views)} views for {object_type}",
                                    object_type=object_type,
                                    object_id=object_id,
                                    view_count=len(views),
                                )

                        except Exception as e:
                            # Log but continue - some objects might not have views
                            self._logger.debug(
                                f"No views found for {object_type} {object_id}",
                                object_type=object_type,
                                object_id=object_id,
                                error=str(e),
                            )
                            continue

                except Exception as e:
                    self._logger.warning(
                        f"Failed to get {object_type} IDs for view discovery",
                        object_type=object_type,
                        error=str(e),
                    )
                    continue

            # Remove duplicates (same view might be found multiple times)
            unique_views = self._deduplicate_views(all_views)

            self._logger.info(
                f"Discovered {len(unique_views)} unique views across all objects",
                total_views=len(unique_views),
                project_id=project_id,
            )

            return unique_views

        except Exception as e:
            self._logger.error("Failed to list source views", error=str(e))
            raise

    async def _get_object_ids_for_type(
        self, object_type: str, project_id: str | None = None
    ) -> list[str]:
        """Get all object IDs for a given object type.

        Args:
            object_type: Type of object ("project", "experiment", "dataset")
            project_id: Optional project ID to filter by

        Returns:
            List of object IDs for the given type
        """
        try:
            object_ids = []

            if object_type == "project":
                # Get all projects (or just the current one if project_id is specified)
                if project_id:
                    object_ids = [project_id]
                else:
                    # List all projects
                    projects_response = await self.source_client.with_retry(
                        "list_projects_for_views",
                        lambda: self.source_client.client.projects.list(),
                    )
                    projects = await self._handle_api_response_to_list(
                        projects_response
                    )
                    object_ids = [project.id for project in projects]

            elif object_type in ["experiment", "dataset"] and project_id:
                # Get experiments or datasets for the project
                resource_type = f"{object_type}s"  # "experiments" or "datasets"
                response = await self.source_client.with_retry(
                    f"list_{resource_type}_for_views",
                    lambda: getattr(self.source_client.client, resource_type).list(
                        project_id=project_id
                    ),
                )
                resources = await self._handle_api_response_to_list(response)
                object_ids = [resource.id for resource in resources]

            elif object_type in ["experiment", "dataset"] and not project_id:
                # If no project_id, we can't list experiments/datasets efficiently
                object_ids = []

            else:
                self._logger.warning(
                    f"Unknown object type for view discovery: {object_type}"
                )
                object_ids = []

            return object_ids

        except Exception as e:
            self._logger.warning(
                f"Failed to get {object_type} IDs",
                object_type=object_type,
                project_id=project_id,
                error=str(e),
            )
            return []

    def _deduplicate_views(self, views: list[View]) -> list[View]:
        """Remove duplicate views from the list.

        Args:
            views: List of views that may contain duplicates

        Returns:
            List of unique views
        """
        seen_ids = set()
        unique_views = []

        for view in views:
            if view.id not in seen_ids:
                seen_ids.add(view.id)
                unique_views.append(view)

        return unique_views

    async def resource_exists_in_dest(self, resource: View) -> str | None:
        """Check if a view already exists in the destination.

        Args:
            resource: Source view to check.

        Returns:
            Destination view ID if it exists, None otherwise.
        """
        try:
            # Views API requires object_id and object_type, so we need to check manually
            dest_object_id = self._resolve_object_id(resource)

            # List views for the specific object
            views_response = await self.dest_client.with_retry(
                "list_views",
                lambda: self.dest_client.client.views.list(
                    object_type=resource.object_type,
                    object_id=dest_object_id,
                ),
            )

            views = await self._handle_api_response_to_list(views_response)

            # Look for a view with the same name
            for view in views:
                if view.name == resource.name:
                    self._logger.debug(
                        "Found existing view in destination",
                        view_name=resource.name,
                        source_id=resource.id,
                        dest_id=view.id,
                    )
                    return view.id

            return None

        except Exception as e:
            self._logger.warning(
                "Error checking if view exists in destination",
                error=str(e),
                resource_name=resource.name,
            )
            return None

    def _resolve_object_id(self, resource: View) -> str:
        """Resolve the object_id for the destination based on object_type.

        Args:
            resource: Source view to resolve object_id for.

        Returns:
            Resolved destination object_id.
        """
        object_type = getattr(resource, "object_type", None)
        source_object_id = resource.object_id

        # Handle different object types
        if object_type == "project":
            # Use destination project ID
            return self.dest_project_id or source_object_id
        elif object_type in ["experiment", "dataset"]:
            # Look up in ID mapping
            dest_object_id = self.state.id_mapping.get(source_object_id)
            if dest_object_id:
                self._logger.debug(
                    "Resolved object dependency for view",
                    view_id=resource.id,
                    object_type=object_type,
                    source_object_id=source_object_id,
                    dest_object_id=dest_object_id,
                )
                return dest_object_id
            else:
                self._logger.warning(
                    "Could not resolve object dependency for view",
                    view_id=resource.id,
                    object_type=object_type,
                    source_object_id=source_object_id,
                )
                # Return source ID as fallback
                return source_object_id
        else:
            # For unknown object types, use source ID as fallback
            self._logger.debug(
                "Unknown object type for view, using source object_id",
                view_id=resource.id,
                object_type=object_type,
                object_id=source_object_id,
            )
            return source_object_id

    def _filter_view_options(self, options) -> dict | None:
        """Filter out unsupported fields from view options.

        Args:
            options: Original view options

        Returns:
            Filtered options dict or None if no valid options remain
        """
        if not options:
            return None

        # Convert to dict if needed
        if hasattr(options, "__dict__"):
            options_dict = options.__dict__.copy()
        elif hasattr(options, "model_dump"):
            options_dict = options.model_dump()
        else:
            options_dict = dict(options) if options else {}

        # List of fields that are known to be unsupported by the destination API
        unsupported_fields = {"column_order"}

        # Filter out unsupported fields
        filtered_options = {
            key: value
            for key, value in options_dict.items()
            if key not in unsupported_fields
        }

        if filtered_options:
            self._logger.debug(
                "Filtered view options",
                original_keys=list(options_dict.keys()),
                filtered_keys=list(filtered_options.keys()),
                removed_keys=list(
                    set(options_dict.keys()) - set(filtered_options.keys())
                ),
            )

        return filtered_options if filtered_options else None

    async def migrate_resource(self, resource: View) -> str:
        """Migrate a single view to the destination.

        Args:
            resource: Source view to migrate.

        Returns:
            ID of the migrated view in the destination.
        """
        try:
            # Resolve the destination object_id
            dest_object_id = self._resolve_object_id(resource)

            view_data = {
                "object_type": resource.object_type,
                "object_id": dest_object_id,
                "view_type": resource.view_type,
                "name": resource.name,
            }

            # Add optional fields if they exist
            if hasattr(resource, "view_data") and resource.view_data is not None:
                view_data["view_data"] = resource.view_data

            if hasattr(resource, "options") and resource.options is not None:
                # Filter out unsupported fields from options
                filtered_options = self._filter_view_options(resource.options)
                if filtered_options:
                    view_data["options"] = filtered_options

            if hasattr(resource, "user_id") and resource.user_id is not None:
                view_data["user_id"] = resource.user_id

            # Create the view in the destination
            new_view = await self.dest_client.with_retry(
                "create_view",
                lambda: self.dest_client.client.views.create(**view_data),
            )

            self._logger.info(
                "Successfully migrated view",
                source_id=resource.id,
                dest_id=new_view.id,
                name=resource.name,
                view_type=resource.view_type,
                object_type=resource.object_type,
                source_object_id=resource.object_id,
                dest_object_id=dest_object_id,
            )

            return new_view.id

        except Exception as e:
            self._logger.error(
                "Failed to migrate view",
                view_id=resource.id,
                view_name=resource.name,
                error=str(e),
            )
            raise
