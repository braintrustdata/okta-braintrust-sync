"""Abstract base class for Braintrust resource migrators."""

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

import structlog

from braintrust_migrate.client import BraintrustClient

logger = structlog.get_logger(__name__)

T = TypeVar("T")  # Type variable for resource data


@dataclass(slots=True)
class MigrationResult:
    """Result of a resource migration operation."""

    success: bool
    source_id: str
    dest_id: str | None = None
    skipped: bool = False
    error: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MigrationState:
    """State of a migration operation for checkpointing."""

    completed_ids: set[str] = field(default_factory=set)
    failed_ids: set[str] = field(default_factory=set)
    id_mapping: dict[str, str] = field(default_factory=dict)  # source_id -> dest_id
    checksums: dict[str, str] = field(default_factory=dict)  # source_id -> checksum
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "completed_ids": list(self.completed_ids),
            "failed_ids": list(self.failed_ids),
            "id_mapping": self.id_mapping,
            "checksums": self.checksums,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MigrationState":
        """Create from dictionary loaded from JSON."""
        return cls(
            completed_ids=set(data.get("completed_ids", [])),
            failed_ids=set(data.get("failed_ids", [])),
            id_mapping=data.get("id_mapping", {}),
            checksums=data.get("checksums", {}),
            metadata=data.get("metadata", {}),
        )


class ResourceMigrator(ABC, Generic[T]):
    """Abstract base class for resource migrators.

    Provides common functionality for:
    - Checkpointing and state management
    - Dependency tracking and resolution
    - Resource comparison and deduplication
    - Batch processing
    - Error handling and retry logic
    - Serialization for API insertion
    """

    def __init__(
        self,
        source_client: BraintrustClient,
        dest_client: BraintrustClient,
        checkpoint_dir: Path,
        batch_size: int = 100,
    ) -> None:
        """Initialize the resource migrator.

        Args:
            source_client: Client for source organization.
            dest_client: Client for destination organization.
            checkpoint_dir: Directory for storing checkpoints.
            batch_size: Number of resources to process in each batch.
        """
        self.source_client = source_client
        self.dest_client = dest_client
        self.checkpoint_dir = checkpoint_dir
        self.batch_size = batch_size
        self._logger = logger.bind(migrator=self.__class__.__name__)

        # Project ID mapping for cross-references
        self.dest_project_id: str | None = None

        # Cache for dependency resources to avoid repeated API calls
        self._dependency_cache: dict[str, list[T]] = {}

        # Ensure checkpoint directory exists
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state
        self.state = self._load_state()

    def set_destination_project_id(self, dest_project_id: str) -> None:
        """Set the destination project ID for this migration.

        Args:
            dest_project_id: Destination project ID to use when creating resources.
        """
        self.dest_project_id = dest_project_id

    @property
    @abstractmethod
    def resource_name(self) -> str:
        """Human-readable name for this resource type."""
        pass

    @property
    def checkpoint_file(self) -> Path:
        """Path to the checkpoint file for this resource type."""
        return self.checkpoint_dir / f"{self.resource_name.lower()}_state.json"

    def _load_state(self) -> MigrationState:
        """Load migration state from checkpoint file."""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file) as f:
                    data = json.load(f)
                state = MigrationState.from_dict(data)
                self._logger.info(
                    "Loaded migration state from checkpoint",
                    completed_count=len(state.completed_ids),
                    failed_count=len(state.failed_ids),
                    mapping_count=len(state.id_mapping),
                )
                return state
            except Exception as e:
                self._logger.warning(
                    "Failed to load migration state, starting fresh",
                    error=str(e),
                )

        return MigrationState()

    def _save_state(self) -> None:
        """Save migration state to checkpoint file."""
        try:
            with open(self.checkpoint_file, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
            self._logger.debug("Saved migration state to checkpoint")
        except Exception as e:
            self._logger.error("Failed to save migration state", error=str(e))

    def _compute_checksum(self, data: Any) -> str:
        """Compute checksum for resource data to detect changes.

        Args:
            data: Resource data to compute checksum for.

        Returns:
            SHA-256 checksum of the resource data.
        """
        # Convert resource object to a serializable dictionary
        if hasattr(data, "__dict__"):
            # Handle pydantic models and dataclass objects
            if hasattr(data, "model_dump"):
                # Pydantic v2 model
                serializable_data = data.model_dump()
            elif hasattr(data, "dict"):
                # Pydantic v1 model
                serializable_data = data.dict()
            else:
                # Generic object with __dict__
                serializable_data = {
                    k: v
                    for k, v in data.__dict__.items()
                    if not k.startswith("_") and not callable(v)
                }
        else:
            # Primitive types or already serializable
            serializable_data = data

        # Convert to JSON string with sorted keys for consistent hashing
        try:
            json_str = json.dumps(
                serializable_data, sort_keys=True, separators=(",", ":"), default=str
            )
        except (TypeError, ValueError) as e:
            # Fallback: convert to string representation
            self._logger.warning(
                "Failed to serialize data for checksum, using string representation",
                error=str(e),
                data_type=type(data).__name__,
            )
            json_str = str(serializable_data)

        return hashlib.sha256(json_str.encode()).hexdigest()

    def should_skip_resource(self, source_id: str, current_data: Any) -> bool:
        """Check if a resource should be skipped based on existing state.

        Args:
            source_id: Source resource ID.
            current_data: Current resource data.

        Returns:
            True if resource should be skipped, False otherwise.
        """
        # Skip if already completed
        if source_id in self.state.completed_ids:
            # Check if data has changed by comparing checksums
            current_checksum = self._compute_checksum(current_data)
            stored_checksum = self.state.checksums.get(source_id)

            if stored_checksum == current_checksum:
                self._logger.debug("Skipping unchanged resource", source_id=source_id)
                return True
            else:
                self._logger.info(
                    "Resource has changed, will re-migrate",
                    source_id=source_id,
                    old_checksum=stored_checksum,
                    new_checksum=current_checksum,
                )
                # Remove from completed set to force re-migration
                self.state.completed_ids.discard(source_id)

        return False

    def record_success(
        self,
        source_id: str,
        dest_id: str,
        data: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record successful migration of a resource.

        Args:
            source_id: Source resource ID.
            dest_id: Destination resource ID.
            data: Resource data that was migrated.
            metadata: Optional metadata about the migration.
        """
        checksum = self._compute_checksum(data)

        self.state.completed_ids.add(source_id)
        self.state.failed_ids.discard(source_id)
        self.state.id_mapping[source_id] = dest_id
        self.state.checksums[source_id] = checksum

        if metadata:
            self.state.metadata[source_id] = metadata

        self._logger.info(
            "Recorded successful migration",
            source_id=source_id,
            dest_id=dest_id,
            checksum=checksum,
        )

    def record_failure(self, source_id: str, error: str) -> None:
        """Record failed migration of a resource.

        Args:
            source_id: Source resource ID.
            error: Error message describing the failure.
        """
        self.state.failed_ids.add(source_id)
        self.state.completed_ids.discard(source_id)

        # Store error in metadata
        self.state.metadata[source_id] = {
            "error": error,
            "failed_at": str(Path(__file__).stat().st_mtime),  # Timestamp
        }

        self._logger.error(
            "Recorded migration failure", source_id=source_id, error=error
        )

    @abstractmethod
    async def list_source_resources(self, project_id: str | None = None) -> list[T]:
        """List all resources of this type from the source organization.

        Args:
            project_id: Optional project ID to filter resources.

        Returns:
            List of source resources.
        """
        pass

    def get_resource_id(self, resource: T) -> str:
        """Extract the unique ID from a resource.

        Default implementation returns resource.id. Override if different logic needed.

        Args:
            resource: Resource object.

        Returns:
            Unique identifier for the resource.
        """
        if hasattr(resource, "id"):
            return resource.id
        else:
            raise AttributeError(
                f"Resource {type(resource)} does not have an 'id' attribute"
            )

    @abstractmethod
    async def resource_exists_in_dest(self, resource: T) -> str | None:
        """Check if a resource already exists in the destination.

        Args:
            resource: Source resource to check.

        Returns:
            Destination resource ID if it exists, None otherwise.
        """
        pass

    @abstractmethod
    async def migrate_resource(self, resource: T) -> str:
        """Migrate a single resource from source to destination.

        Args:
            resource: Source resource to migrate.

        Returns:
            ID of the created resource in destination.

        Raises:
            Exception: If migration fails.
        """
        pass

    def _get_client_resource_attr(self, client, resource_type: str):
        """Get the resource attribute from a client (e.g., client.datasets).

        Args:
            client: Braintrust client instance
            resource_type: Resource type name (e.g., 'datasets', 'experiments')

        Returns:
            Resource client attribute
        """
        return getattr(client.client, resource_type)

    async def _handle_api_response_to_list(self, response) -> list[T]:
        """Convert various API response formats to a list.

        Handles:
        - Async iterators
        - Paginated responses with .objects
        - Direct lists

        Args:
            response: API response in various formats

        Returns:
            List of resources
        """
        # Handle None or empty response
        if response is None:
            return []

        # Handle async iterator
        if hasattr(response, "__aiter__"):
            result_list = []
            async for item in response:
                result_list.append(item)
            return result_list

        # Handle paginated response with objects
        elif hasattr(response, "objects"):
            return list(response.objects)

        # Handle already a list
        elif isinstance(response, list):
            return response

        # Handle direct iterable (convert to list)
        else:
            try:
                return list(response)
            except (TypeError, ValueError) as e:
                self._logger.warning(
                    "Could not convert API response to list",
                    response_type=type(response).__name__,
                    error=str(e),
                )
                return []

    async def _list_resources_with_client(
        self,
        client,
        resource_type: str,
        project_id: str | None = None,
        additional_params: dict | None = None,
        client_side_filter_field: str | None = None,
    ) -> list[T]:
        """Generic method to list resources from a client.

        Args:
            client: Source or destination client
            resource_type: Resource type name (e.g., 'datasets', 'experiments')
            project_id: Optional project ID to filter by
            additional_params: Additional parameters for the API call
            client_side_filter_field: Field name to filter by project_id client-side

        Returns:
            List of resources
        """
        try:
            # Build parameters
            params = {}
            if project_id and not client_side_filter_field:
                # Use server-side filtering if no client-side field specified
                params["project_id"] = project_id
            if additional_params:
                params.update(additional_params)

            # Get the resource client
            resource_client = self._get_client_resource_attr(client, resource_type)

            # Make the API call
            response = await client.with_retry(
                f"list_{resource_type}", lambda: resource_client.list(**params)
            )

            # Convert response to list
            resources = await self._handle_api_response_to_list(response)

            # Apply client-side filtering if needed
            if project_id and client_side_filter_field:
                resources = [
                    resource
                    for resource in resources
                    if getattr(resource, client_side_filter_field, None) == project_id
                ]

            return resources

        except Exception as e:
            self._logger.error(
                f"Failed to list {resource_type}", error=str(e), project_id=project_id
            )
            raise

    async def _check_resource_exists_by_name(
        self,
        resource: T,
        resource_type: str,
        name_field: str = "name",
        additional_match_fields: list[str] | None = None,
        additional_params: dict | None = None,
    ) -> str | None:
        """Generic method to check if a resource exists in destination by name.

        Args:
            resource: Source resource to check
            resource_type: Resource type name (e.g., 'datasets', 'experiments')
            name_field: Field name to use for name matching (default: 'name')
            additional_match_fields: Additional fields that must match (e.g., ['slug'])
            additional_params: Additional parameters for the API call

        Returns:
            Destination resource ID if found, None otherwise
        """
        try:
            # Build search parameters
            params = {}
            if self.dest_project_id:
                params["project_id"] = self.dest_project_id

            # Add name-based filtering if supported by API
            resource_name = getattr(resource, name_field)
            params[f"{resource_type[:-1]}_name"] = (
                resource_name  # e.g., dataset_name, experiment_name
            )

            if additional_params:
                params.update(additional_params)

            # Get destination resources
            dest_resources = await self._list_resources_with_client(
                self.dest_client, resource_type, additional_params=params
            )

            # Check for matches
            for dest_resource in dest_resources:
                # Check primary name field
                if getattr(dest_resource, name_field) != resource_name:
                    continue

                # Check additional match fields if specified
                if additional_match_fields:
                    match = True
                    for field in additional_match_fields:
                        if getattr(dest_resource, field, None) != getattr(
                            resource, field, None
                        ):
                            match = False
                            break
                    if not match:
                        continue

                # Check project ID if applicable
                if (
                    self.dest_project_id
                    and hasattr(dest_resource, "project_id")
                    and dest_resource.project_id != self.dest_project_id
                ):
                    continue

                self._logger.debug(
                    f"Found existing {resource_type[:-1]} in destination",
                    source_id=self.get_resource_id(resource),
                    dest_id=dest_resource.id,
                    name=resource_name,
                )
                return dest_resource.id

            return None

        except Exception as e:
            self._logger.warning(
                f"Error checking if {resource_type[:-1]} exists in destination",
                error=str(e),
                resource_name=getattr(resource, name_field, "unknown"),
            )
            return None

    async def get_dependencies(self, resource: T) -> list[str]:
        """Get list of resource IDs that this resource depends on.

        Override this method in subclasses that have dependencies.

        Args:
            resource: Resource to get dependencies for.

        Returns:
            List of resource IDs this resource depends on.
        """
        return []

    async def get_dependency_types(self) -> list[str]:
        """Get list of resource types that this migrator's resources might depend on.

        This is used to pre-populate ID mappings for dependencies that aren't being
        migrated but are needed for resolving dependencies.

        Override this method in subclasses that have dependencies on other resource types.

        Returns:
            List of resource type names (e.g., ['datasets', 'prompts']).
        """
        return []

    async def populate_dependency_mappings(
        self,
        source_client: BraintrustClient,
        dest_client: BraintrustClient,
        project_id: str | None = None,
        shared_cache: dict[str, Any] | None = None,
    ) -> None:
        """Pre-populate ID mappings for dependency resources.

        This method fetches existing resources from both source and destination
        for dependency types and populates the id_mapping so that dependencies
        can be resolved even if those resource types aren't being migrated.

        Args:
            source_client: Source organization client.
            dest_client: Destination organization client.
            project_id: Optional project ID to filter resources.
            shared_cache: Optional shared cache to avoid duplicate API calls.
        """
        dependency_types = await self.get_dependency_types()
        if not dependency_types:
            return

        # Initialize shared cache if not provided
        if shared_cache is None:
            shared_cache = {}

        self._logger.info(
            "Pre-populating dependency mappings",
            dependency_types=dependency_types,
            migrator=self.__class__.__name__,
        )

        for dep_type in dependency_types:
            try:
                # Check shared cache first
                cache_key_source = f"{dep_type}_source_{project_id}"
                cache_key_dest = f"{dep_type}_dest_{project_id}"

                if cache_key_source in shared_cache:
                    source_resources = shared_cache[cache_key_source]
                    self._logger.debug(f"Using cached source {dep_type}")
                else:
                    # Get source resources
                    source_resources = await self._list_resources_with_client(
                        source_client, dep_type, project_id
                    )
                    shared_cache[cache_key_source] = source_resources

                if cache_key_dest in shared_cache:
                    dest_resources = shared_cache[cache_key_dest]
                    self._logger.debug(f"Using cached destination {dep_type}")
                else:
                    # Get destination resources
                    dest_resources = await self._list_resources_with_client(
                        dest_client, dep_type, project_id
                    )
                    shared_cache[cache_key_dest] = dest_resources

                self._logger.info(
                    "Found dependency resources for mapping",
                    resource_type=dep_type,
                    source_count=len(source_resources),
                    dest_count=len(dest_resources),
                )

                # Create mapping from source to destination by name matching
                dest_by_name = {}
                for dest_resource in dest_resources:
                    # Handle different name fields
                    name = getattr(dest_resource, "name", None)
                    if name:
                        dest_by_name[name] = dest_resource.id

                # Map source IDs to destination IDs
                mapped_count = 0
                unmapped_count = 0
                for source_resource in source_resources:
                    source_id = self.get_resource_id(source_resource)
                    source_name = getattr(source_resource, "name", None)

                    if source_name and source_name in dest_by_name:
                        dest_id = dest_by_name[source_name]
                        self.state.id_mapping[source_id] = dest_id
                        mapped_count += 1

                    else:
                        unmapped_count += 1

                self._logger.info(
                    f"Pre-populated {mapped_count} {dep_type} dependency mappings",
                    mapped=mapped_count,
                    unmapped=unmapped_count,
                )

            except Exception as e:
                self._logger.warning(
                    f"Failed to pre-populate {dep_type} dependency mappings",
                    error=str(e),
                )
                # Continue with other dependency types

        # Save state after populating mappings
        self._save_state()

    async def ensure_dependency_mapping(
        self,
        resource_type: str,
        dependency_id: str,
        project_id: str | None = None,
    ) -> str | None:
        """Ensure that a specific dependency mapping exists, populating it if necessary.

        This method checks if the given dependency_id already has a mapping in the state.
        If not, it will attempt to populate the mapping for that specific resource type
        by fetching and matching resources from source and destination.

        Uses caching to avoid repeated API calls for the same resource types.

        Args:
            resource_type: Type of resource (e.g., 'prompts', 'datasets', 'experiments').
            dependency_id: Source resource ID that needs to be mapped.
            project_id: Optional project ID to filter resources.

        Returns:
            Destination resource ID if mapping is found/created, None otherwise.
        """
        # Check if mapping already exists
        if dependency_id in self.state.id_mapping:
            return self.state.id_mapping[dependency_id]

        try:
            # Create cache keys
            source_cache_key = f"{resource_type}_source_{project_id}"
            dest_cache_key = f"{resource_type}_dest_{project_id}"

            # Get source resources (use cache if available)
            if source_cache_key in self._dependency_cache:
                source_resources = self._dependency_cache[source_cache_key]
            else:
                source_resources = await self._list_resources_with_client(
                    self.source_client, resource_type, project_id
                )
                self._dependency_cache[source_cache_key] = source_resources

            # Find the specific source resource we need
            source_resource = None
            for resource in source_resources:
                if self.get_resource_id(resource) == dependency_id:
                    source_resource = resource
                    break

            if not source_resource:
                self._logger.warning(
                    "Source dependency resource not found",
                    resource_type=resource_type,
                    dependency_id=dependency_id,
                )
                return None

            # Get destination resources (use cache if available)
            if dest_cache_key in self._dependency_cache:
                dest_resources = self._dependency_cache[dest_cache_key]
            else:
                dest_resources = await self._list_resources_with_client(
                    self.dest_client, resource_type, project_id
                )
                self._dependency_cache[dest_cache_key] = dest_resources

            # Look for a matching resource in destination by name
            source_name = getattr(source_resource, "name", None)
            if not source_name:
                self._logger.warning(
                    "Source dependency resource has no name field for matching",
                    resource_type=resource_type,
                    dependency_id=dependency_id,
                )
                return None

            for dest_resource in dest_resources:
                dest_name = getattr(dest_resource, "name", None)
                if dest_name == source_name:
                    dest_id = dest_resource.id
                    # Add to mapping
                    self.state.id_mapping[dependency_id] = dest_id
                    self._save_state()

                    self._logger.debug(
                        "Successfully populated dependency mapping",
                        resource_type=resource_type,
                        source_id=dependency_id,
                        dest_id=dest_id,
                    )
                    return dest_id

            self._logger.warning(
                "No matching destination resource found for dependency",
                resource_type=resource_type,
                dependency_id=dependency_id,
                source_name=source_name,
            )
            return None

        except Exception as e:
            self._logger.error(
                "Failed to populate dependency mapping",
                resource_type=resource_type,
                dependency_id=dependency_id,
                error=str(e),
            )
            return None

    def update_id_mappings(self, additional_mappings: dict[str, str]) -> None:
        """Update ID mappings with additional mappings from other migrators.

        This allows sharing of ID mappings between different resource migrators
        so that dependencies can be resolved even across resource types.

        Args:
            additional_mappings: Dictionary of source_id -> dest_id mappings to add.
        """
        before_count = len(self.state.id_mapping)
        self.state.id_mapping.update(additional_mappings)
        after_count = len(self.state.id_mapping)
        added_count = after_count - before_count

        self._logger.debug(
            "Updated ID mappings",
            added_count=added_count,
            total_mappings=after_count,
        )

    @property
    def excluded_fields_for_insert(self) -> set[str]:
        """Fields to exclude when converting resources for API insertion.

        Override this property in subclasses to customize which fields are excluded.

        Returns:
            Set of field names to exclude from serialization for API insertion.
        """
        return {
            "id",  # Auto-generated by destination
            "created",  # Auto-generated by destination
            "_xact_id",  # Internal field
            "xact_id",  # Internal field (alternative naming)
            "_object_delete",  # Internal field
            "_pagination_key",  # Internal field
            "comparison_key",  # Internal field
            "project_id",  # Will be set to destination project
            "org_id",  # Inferred from project_id
        }

    def serialize_resource_for_insert(self, resource: T) -> dict[str, Any]:
        """Convert a Braintrust resource to a dictionary suitable for API insertion.

        This method handles the serialization of Braintrust BaseModel objects using
        their to_dict() method with JSON mode for proper serialization, and excludes
        fields that shouldn't be included in API insert operations.

        Args:
            resource: Resource object to serialize (typically a Braintrust BaseModel).

        Returns:
            Dictionary representation suitable for API insertion.

        Raises:
            ValueError: If the resource cannot be serialized.
        """
        if resource is None:
            raise ValueError("Cannot serialize None resource")

        resource_type = type(resource).__name__
        resource_id = getattr(resource, "id", "unknown")

        try:
            serialized = None

            if hasattr(resource, "to_dict") and callable(resource.to_dict):
                # Use Braintrust BaseModel's to_dict method with JSON mode for serialization
                try:
                    serialized = resource.to_dict(
                        mode="json",  # Ensures all objects are JSON-serializable
                        exclude_unset=True,  # Don't include unset fields
                        exclude_none=True,  # Don't include None values
                        use_api_names=True,  # Use API field names
                    )
                    self._logger.debug(
                        "Successfully serialized using to_dict method",
                        resource_type=resource_type,
                        resource_id=resource_id,
                    )
                except Exception as e:
                    self._logger.debug(
                        "to_dict method failed, trying alternatives",
                        error=str(e),
                        resource_type=resource_type,
                    )
                    # Continue to try other methods

            if (
                serialized is None
                and hasattr(resource, "model_dump")
                and callable(resource.model_dump)
            ):
                # Fallback to standard Pydantic model_dump for non-Braintrust models
                try:
                    serialized = resource.model_dump(
                        exclude=self.excluded_fields_for_insert,
                        exclude_none=True,
                    )
                    self._logger.debug(
                        "Successfully serialized using model_dump method",
                        resource_type=resource_type,
                        resource_id=resource_id,
                    )
                except Exception as e:
                    self._logger.debug(
                        "model_dump method failed, trying __dict__",
                        error=str(e),
                        resource_type=resource_type,
                    )
                    # Continue to try __dict__ approach

            if serialized is None:
                # Final fallback using __dict__
                if hasattr(resource, "__dict__"):
                    serialized = {
                        k: v
                        for k, v in resource.__dict__.items()
                        if not k.startswith("_")
                        and k not in self.excluded_fields_for_insert
                        and v is not None
                        and not callable(v)
                    }
                    self._logger.debug(
                        "Successfully serialized using __dict__ method",
                        resource_type=resource_type,
                        resource_id=resource_id,
                    )
                else:
                    raise ValueError(
                        f"Resource of type {resource_type} has no serializable attributes"
                    )

            # Remove excluded fields (for methods that don't support exclude parameter)
            if serialized and hasattr(resource, "to_dict"):
                for field in self.excluded_fields_for_insert:
                    serialized.pop(field, None)

            if not serialized:
                raise ValueError(
                    f"Serialization resulted in empty dictionary for {resource_type}"
                )

            if not isinstance(serialized, dict):
                raise ValueError(
                    f"Serialization did not return a dictionary, got {type(serialized)}"
                )

            self._logger.debug(
                "Resource serialization successful",
                resource_type=resource_type,
                resource_id=resource_id,
                fields_count=len(serialized),
            )

            return serialized

        except Exception as e:
            self._logger.error(
                "Failed to serialize resource for insertion",
                error=str(e),
                resource_type=resource_type,
                resource_id=resource_id,
                resource_attributes=list(dir(resource))
                if hasattr(resource, "__dict__")
                else "no __dict__",
            )
            raise ValueError(
                f"Failed to serialize {resource_type} resource: {e}"
            ) from e

    async def resolve_dependencies(
        self, dependencies: list[str], strict: bool = True
    ) -> dict[str, str]:
        """Resolve dependencies by mapping source IDs to destination IDs.

        Args:
            dependencies: List of source resource IDs.
            strict: If True, raises error for unresolved dependencies.
                   If False, logs warnings and continues.

        Returns:
            Mapping from source IDs to destination IDs.

        Raises:
            ValueError: If any dependency is not resolved and strict=True.
        """
        resolved = {}
        unresolved = []

        for dep_id in dependencies:
            dest_id = self.state.id_mapping.get(dep_id)
            if dest_id:
                resolved[dep_id] = dest_id
            else:
                unresolved.append(dep_id)

        if unresolved:
            self._logger.warning(
                "Some dependencies could not be resolved",
                unresolved_count=len(unresolved),
                resolved_count=len(resolved),
            )

            if strict:
                raise ValueError(f"Unresolved dependencies: {unresolved}")

        return resolved

    async def migrate_batch(self, resources: list[T]) -> list[MigrationResult]:
        """Migrate a batch of resources.

        Args:
            resources: List of resources to migrate.

        Returns:
            List of migration results.
        """
        results = []

        for resource in resources:
            source_id = None  # Initialize source_id before try block
            try:
                source_id = self.get_resource_id(resource)

                # Check if this resource should be migrated in this pass
                if hasattr(self, "should_migrate_resource"):
                    should_migrate = await self.should_migrate_resource(resource)
                    if not should_migrate:
                        resource_name = getattr(resource, "name", None)
                        self._logger.info(
                            f"⏭️  Skipped {self.resource_name[:-1].lower()} (wrong pass)",
                            source_id=source_id,
                            name=resource_name,
                        )
                        results.append(
                            MigrationResult(
                                success=True,
                                source_id=source_id,
                                dest_id=self.state.id_mapping.get(source_id),
                                skipped=True,
                                metadata={
                                    "name": resource_name,
                                    "skip_reason": "wrong_pass",
                                }
                                if resource_name
                                else {"skip_reason": "wrong_pass"},
                            )
                        )
                        continue

                # Check if should skip
                if self.should_skip_resource(source_id, resource):
                    resource_name = getattr(resource, "name", None)
                    self._logger.info(
                        f"⏭️  Skipped {self.resource_name[:-1].lower()} (unchanged)",
                        source_id=source_id,
                        name=resource_name,
                    )
                    results.append(
                        MigrationResult(
                            success=True,
                            source_id=source_id,
                            dest_id=self.state.id_mapping.get(source_id),
                            skipped=True,
                            metadata={"name": resource_name, "skip_reason": "unchanged"}
                            if resource_name
                            else {"skip_reason": "unchanged"},
                        )
                    )
                    continue

                # Check if already exists in destination
                existing_dest_id = await self.resource_exists_in_dest(resource)
                if existing_dest_id:
                    resource_name = getattr(resource, "name", None)
                    self._logger.info(
                        f"⏭️  Skipped {self.resource_name[:-1].lower()} (already exists)",
                        source_id=source_id,
                        dest_id=existing_dest_id,
                        name=resource_name,
                    )
                    self.record_success(source_id, existing_dest_id, resource)
                    results.append(
                        MigrationResult(
                            success=True,
                            source_id=source_id,
                            dest_id=existing_dest_id,
                            skipped=True,
                            metadata={
                                "name": resource_name,
                                "skip_reason": "already_exists",
                            }
                            if resource_name
                            else {"skip_reason": "already_exists"},
                        )
                    )
                    continue

                # Check dependencies
                dependencies = await self.get_dependencies(resource)
                if dependencies:
                    try:
                        # Use non-strict mode for dependency resolution to allow migration
                        # even when some dependencies haven't been migrated yet
                        await self.resolve_dependencies(dependencies, strict=False)
                    except ValueError as e:
                        # This should rarely happen now with strict=False, but keep as fallback
                        self.record_failure(source_id, str(e))
                        results.append(
                            MigrationResult(
                                success=False,
                                source_id=source_id,
                                error=str(e),
                            )
                        )
                        continue

                # Perform migration
                dest_id = await self.migrate_resource(resource)
                checksum = self._compute_checksum(resource)

                # Log successful creation
                resource_name = getattr(resource, "name", None)
                self._logger.info(
                    f"✅ Created {self.resource_name[:-1].lower()}",
                    source_id=source_id,
                    dest_id=dest_id,
                    name=resource_name,
                )

                self.record_success(source_id, dest_id, resource)
                results.append(
                    MigrationResult(
                        success=True,
                        source_id=source_id,
                        dest_id=dest_id,
                        checksum=checksum,
                        metadata={"name": resource_name} if resource_name else {},
                    )
                )

            except Exception as e:
                error_msg = f"Failed to migrate resource: {e}"
                # Use source_id if available, otherwise use a fallback
                resource_id = source_id if source_id else f"unknown_{id(resource)}"
                self.record_failure(resource_id, error_msg)
                results.append(
                    MigrationResult(
                        success=False,
                        source_id=resource_id,
                        error=error_msg,
                    )
                )

        return results

    async def migrate_all(self, project_id: str | None = None) -> dict[str, Any]:
        """Migrate all resources of this type.

        Args:
            project_id: Optional project ID to filter resources.

        Returns:
            Summary of migration results.
        """
        self._logger.info(f"Starting migration of {self.resource_name}")

        # List all source resources
        resources = await self.list_source_resources(project_id)
        total_count = len(resources)

        self._logger.info(f"Found {total_count} {self.resource_name} to migrate")

        if total_count == 0:
            return {
                "resource_type": self.resource_name,
                "total": 0,
                "migrated": 0,
                "skipped": 0,
                "failed": 0,
                "errors": [],
            }

        # Process in batches
        migrated_count = 0
        skipped_count = 0
        failed_count = 0
        errors = []
        skipped_details = []
        migrated_details = []

        for i in range(0, total_count, self.batch_size):
            batch = resources[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (total_count + self.batch_size - 1) // self.batch_size

            self._logger.info(
                f"Processing batch {batch_num}/{total_batches}",
                batch_size=len(batch),
            )

            batch_results = await self.migrate_batch(batch)

            # Aggregate results with details
            for result in batch_results:
                if result.success:
                    if result.skipped:
                        skipped_count += 1
                        skipped_details.append(
                            {
                                "source_id": result.source_id,
                                "dest_id": result.dest_id,
                                "name": result.metadata.get("name")
                                if result.metadata
                                else None,
                                "skip_reason": result.metadata.get("skip_reason")
                                if result.metadata
                                else "unknown",
                            }
                        )
                    else:
                        migrated_count += 1
                        migrated_details.append(
                            {
                                "source_id": result.source_id,
                                "dest_id": result.dest_id,
                                "name": result.metadata.get("name")
                                if result.metadata
                                else None,
                            }
                        )
                else:
                    failed_count += 1
                    if result.error:
                        errors.append(
                            {
                                "source_id": result.source_id,
                                "error": result.error,
                                "name": result.metadata.get("name")
                                if result.metadata
                                else None,
                            }
                        )

            # Save state after each batch
            self._save_state()

        # Log detailed summary
        self._logger.info(
            f"Completed migration of {self.resource_name}",
            total=total_count,
            migrated=migrated_count,
            skipped=skipped_count,
            failed=failed_count,
        )

        # Log skipped details if any
        if skipped_details:
            skip_reasons = {}
            for detail in skipped_details:
                reason = detail["skip_reason"]
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

            self._logger.info(
                f"Skipped {self.resource_name} breakdown",
                skip_reasons=skip_reasons,
                sample_skipped=[
                    d for d in skipped_details[:3]
                ],  # Show first 3 as examples
            )

        return {
            "resource_type": self.resource_name,
            "total": total_count,
            "migrated": migrated_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "errors": errors,
            "skipped_details": skipped_details,
            "migrated_details": migrated_details,
        }

    def clear_dependency_cache(self) -> None:
        """Clear the dependency cache to force fresh API calls.

        This can be useful when the cache becomes stale or for testing purposes.
        """
        self._dependency_cache.clear()
        self._logger.debug("Cleared dependency cache")
