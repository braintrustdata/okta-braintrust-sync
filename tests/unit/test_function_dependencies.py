"""Unit tests for FunctionMigrator dependency resolution."""

from unittest.mock import Mock

import pytest
from braintrust_api.types import Function

from braintrust_migrate.resources.functions import FunctionMigrator


@pytest.fixture
def function_with_prompt_origin():
    """Create a function that depends on a prompt."""
    function = Mock(spec=Function)
    function.id = "func-123"
    function.name = "Test Function"
    function.slug = "test-function"
    function.project_id = "project-456"
    function.function_data = {"type": "code", "code": "def test(): pass"}
    function.description = "A test function"
    function.tags = ["test"]
    function.function_type = "tool"
    function.function_schema = {"parameters": {}, "returns": {}}

    # Mock origin that references a prompt
    origin = Mock()
    origin.object_type = "prompt"
    origin.object_id = "prompt-789"
    origin.internal = False
    function.origin = origin

    # Mock the to_dict method to return a proper dictionary
    function.to_dict.return_value = {
        "id": "func-123",
        "name": "Test Function",
        "slug": "test-function",
        "project_id": "project-456",
        "function_data": {"type": "code", "code": "def test(): pass"},
        "description": "A test function",
        "tags": ["test"],
        "function_type": "tool",
        "function_schema": {"parameters": {}, "returns": {}},
        "origin": {
            "object_type": "prompt",
            "object_id": "prompt-789",
            "internal": False,
        },
    }

    return function


@pytest.fixture
def function_with_dataset_origin():
    """Create a function that depends on a dataset."""
    function = Mock(spec=Function)
    function.id = "func-789"
    function.name = "Dataset Function"
    function.slug = "dataset-function"
    function.project_id = "project-456"
    function.function_data = {"type": "code", "code": "def dataset_func(): pass"}
    function.description = "A function with dataset origin"
    function.tags = ["dataset"]
    function.function_type = "tool"
    function.function_schema = {"parameters": {}, "returns": {}}

    # Mock origin that references a dataset
    origin = Mock()
    origin.object_type = "dataset"
    origin.object_id = "dataset-123"
    origin.internal = False
    function.origin = origin

    # Mock the to_dict method to return a proper dictionary
    function.to_dict.return_value = {
        "id": "func-789",
        "name": "Dataset Function",
        "slug": "dataset-function",
        "project_id": "project-456",
        "function_data": {"type": "code", "code": "def dataset_func(): pass"},
        "description": "A function with dataset origin",
        "tags": ["dataset"],
        "function_type": "tool",
        "function_schema": {"parameters": {}, "returns": {}},
        "origin": {
            "object_type": "dataset",
            "object_id": "dataset-123",
            "internal": False,
        },
    }

    return function


@pytest.fixture
def function_with_non_migratable_origin():
    """Create a function with origin pointing to a non-migratable resource."""
    function = Mock(spec=Function)
    function.id = "func-999"
    function.name = "Org Function"
    function.slug = "org-function"
    function.project_id = "project-456"
    function.function_data = {"type": "code", "code": "def org_func(): pass"}
    function.description = "A function with organization origin"
    function.tags = ["org"]
    function.function_type = "tool"
    function.function_schema = {"parameters": {}, "returns": {}}

    # Mock origin that references an organization (non-migratable)
    origin = Mock()
    origin.object_type = "organization"
    origin.object_id = "org-123"
    origin.internal = False
    function.origin = origin

    # Mock the to_dict method to return a proper dictionary
    function.to_dict.return_value = {
        "id": "func-999",
        "name": "Org Function",
        "slug": "org-function",
        "project_id": "project-456",
        "function_data": {"type": "code", "code": "def org_func(): pass"},
        "description": "A function with organization origin",
        "tags": ["org"],
        "function_type": "tool",
        "function_schema": {"parameters": {}, "returns": {}},
        "origin": {
            "object_type": "organization",
            "object_id": "org-123",
            "internal": False,
        },
    }

    return function


@pytest.fixture
def function_without_origin():
    """Create a function without origin dependencies."""
    function = Mock(spec=Function)
    function.id = "func-456"
    function.name = "Independent Function"
    function.slug = "independent-function"
    function.project_id = "project-456"
    function.function_data = {"type": "code", "code": "def independent(): pass"}
    function.description = "A function without dependencies"
    function.tags = ["independent"]
    function.function_type = "scorer"
    function.function_schema = {"parameters": {}, "returns": {}}
    function.origin = None

    # Mock the to_dict method to return a proper dictionary
    function.to_dict.return_value = {
        "id": "func-456",
        "name": "Independent Function",
        "slug": "independent-function",
        "project_id": "project-456",
        "function_data": {"type": "code", "code": "def independent(): pass"},
        "description": "A function without dependencies",
        "tags": ["independent"],
        "function_type": "scorer",
        "function_schema": {"parameters": {}, "returns": {}},
        "origin": None,
    }

    return function


@pytest.mark.asyncio
class TestFunctionDependencies:
    """Test FunctionMigrator dependency resolution."""

    async def test_get_dependencies_with_prompt_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_prompt_origin,
    ):
        """Test that functions with prompt origins return the prompt ID as dependency."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(function_with_prompt_origin)

        assert dependencies == ["prompt-789"]

    async def test_get_dependencies_without_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_without_origin,
    ):
        """Test that functions without origins return no dependencies."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(function_without_origin)

        assert dependencies == []

    async def test_migrate_resource_with_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_prompt_origin,
    ):
        """Test migrating a function with prompt origin resolves dependencies."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Set up ID mapping for the prompt dependency
        migrator.state.id_mapping["prompt-789"] = "dest-prompt-789"

        # Mock successful function creation
        created_function = Mock(spec=Function)
        created_function.id = "dest-func-123"
        created_function.name = "Test Function"
        created_function.slug = "test-function"
        mock_dest_client.with_retry.return_value = created_function

        result = await migrator.migrate_resource(function_with_prompt_origin)

        assert result == "dest-func-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_without_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_without_origin,
    ):
        """Test migrating a function without origin works correctly."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Mock successful function creation
        created_function = Mock(spec=Function)
        created_function.id = "dest-func-456"
        created_function.name = "Independent Function"
        created_function.slug = "independent-function"
        mock_dest_client.with_retry.return_value = created_function

        result = await migrator.migrate_resource(function_without_origin)

        assert result == "dest-func-456"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_unresolved_dependency(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_prompt_origin,
    ):
        """Test migrating a function with unresolved prompt dependency."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # No ID mapping set up - dependency unresolved

        # Mock successful function creation (should still work, just without origin)
        created_function = Mock(spec=Function)
        created_function.id = "dest-func-123"
        created_function.name = "Test Function"
        created_function.slug = "test-function"
        mock_dest_client.with_retry.return_value = created_function

        result = await migrator.migrate_resource(function_with_prompt_origin)

        assert result == "dest-func-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_get_dependencies_with_dataset_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_dataset_origin,
    ):
        """Test that functions with dataset origins return the dataset ID as dependency."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(function_with_dataset_origin)

        assert dependencies == ["dataset-123"]

    async def test_get_dependencies_with_non_migratable_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_non_migratable_origin,
    ):
        """Test that functions with non-migratable origins return no dependencies."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(
            function_with_non_migratable_origin
        )

        assert dependencies == []

    async def test_migrate_resource_with_dataset_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_dataset_origin,
    ):
        """Test migrating a function with dataset origin resolves dependencies."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Set up ID mapping for the dataset dependency
        migrator.state.id_mapping["dataset-123"] = "dest-dataset-123"

        # Mock successful function creation
        created_function = Mock(spec=Function)
        created_function.id = "dest-func-789"
        created_function.name = "Dataset Function"
        created_function.slug = "dataset-function"
        mock_dest_client.with_retry.return_value = created_function

        result = await migrator.migrate_resource(function_with_dataset_origin)

        assert result == "dest-func-789"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_with_non_migratable_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_non_migratable_origin,
    ):
        """Test migrating a function with non-migratable origin keeps the origin."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Mock successful function creation
        created_function = Mock(spec=Function)
        created_function.id = "dest-func-999"
        created_function.name = "Org Function"
        created_function.slug = "org-function"
        mock_dest_client.with_retry.return_value = created_function

        result = await migrator.migrate_resource(function_with_non_migratable_origin)

        assert result == "dest-func-999"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_with_on_demand_dependency_resolution(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_prompt_origin,
    ):
        """Test that function migrator can resolve dependencies on-demand by populating mappings."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Don't set up any ID mapping initially - this will trigger on-demand resolution

        # Mock the source prompt resource
        source_prompt = Mock()
        source_prompt.id = "prompt-789"
        source_prompt.name = "Test Prompt"

        # Mock the destination prompt resource
        dest_prompt = Mock()
        dest_prompt.id = "dest-prompt-789"
        dest_prompt.name = "Test Prompt"

        # Mock the API calls for dependency resolution
        async def mock_list_resources_with_client(client, resource_type, project_id):
            if client == migrator.source_client and resource_type == "prompts":
                return [source_prompt]
            elif client == migrator.dest_client and resource_type == "prompts":
                return [dest_prompt]
            return []

        migrator._list_resources_with_client = mock_list_resources_with_client

        # Mock successful function creation
        created_function = Mock(spec=Function)
        created_function.id = "dest-func-123"
        created_function.name = "Test Function"
        created_function.slug = "test-function"
        mock_dest_client.with_retry.return_value = created_function

        result = await migrator.migrate_resource(function_with_prompt_origin)

        assert result == "dest-func-123"
        # Verify that the dependency mapping was populated
        assert migrator.state.id_mapping["prompt-789"] == "dest-prompt-789"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_with_failed_on_demand_dependency_resolution(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        function_with_prompt_origin,
    ):
        """Test function migration when on-demand dependency resolution fails."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Mock the source prompt resource exists but destination doesn't
        source_prompt = Mock()
        source_prompt.id = "prompt-789"
        source_prompt.name = "Test Prompt"

        # Mock the API calls - source has prompt, destination doesn't
        async def mock_list_resources_with_client(client, resource_type, project_id):
            if client == migrator.source_client and resource_type == "prompts":
                return [source_prompt]
            elif client == migrator.dest_client and resource_type == "prompts":
                return []  # No matching prompt in destination
            return []

        migrator._list_resources_with_client = mock_list_resources_with_client

        # Mock successful function creation (should work even without resolved origin)
        created_function = Mock(spec=Function)
        created_function.id = "dest-func-123"
        created_function.name = "Test Function"
        created_function.slug = "test-function"
        mock_dest_client.with_retry.return_value = created_function

        result = await migrator.migrate_resource(function_with_prompt_origin)

        assert result == "dest-func-123"
        # Verify that no mapping was created since resolution failed
        assert "prompt-789" not in migrator.state.id_mapping
        mock_dest_client.with_retry.assert_called_once()

    async def test_ensure_dependency_mapping_caching(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that dependency mapping uses caching to avoid repeated API calls."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Mock the source and destination resources
        source_prompt1 = Mock()
        source_prompt1.id = "prompt-123"
        source_prompt1.name = "Test Prompt 1"

        source_prompt2 = Mock()
        source_prompt2.id = "prompt-456"
        source_prompt2.name = "Test Prompt 2"

        dest_prompt1 = Mock()
        dest_prompt1.id = "dest-prompt-123"
        dest_prompt1.name = "Test Prompt 1"

        dest_prompt2 = Mock()
        dest_prompt2.id = "dest-prompt-456"
        dest_prompt2.name = "Test Prompt 2"

        call_count = 0

        async def mock_list_resources_with_client(client, resource_type, project_id):
            nonlocal call_count
            call_count += 1
            if client == migrator.source_client and resource_type == "prompts":
                return [source_prompt1, source_prompt2]
            elif client == migrator.dest_client and resource_type == "prompts":
                return [dest_prompt1, dest_prompt2]
            return []

        migrator._list_resources_with_client = mock_list_resources_with_client

        # First call - should make API calls and cache results
        result1 = await migrator.ensure_dependency_mapping("prompts", "prompt-123")
        assert result1 == "dest-prompt-123"
        assert call_count == 2  # Called for both source and dest

        # Second call for different prompt - should use cache, no additional API calls
        result2 = await migrator.ensure_dependency_mapping("prompts", "prompt-456")
        assert result2 == "dest-prompt-456"
        assert call_count == 2  # Should still be 2, no additional API calls

        # Verify both mappings were created
        assert migrator.state.id_mapping["prompt-123"] == "dest-prompt-123"
        assert migrator.state.id_mapping["prompt-456"] == "dest-prompt-456"

    async def test_migration_integration_with_caching(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that caching works correctly during actual function migration with multiple origin references."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Create two functions that reference the same dataset type
        function1 = Mock(spec=Function)
        function1.id = "func-123"
        function1.name = "Function 1"
        function1.slug = "function-1"
        function1.project_id = "project-456"
        function1.function_data = {"type": "code", "code": "def func1(): pass"}

        # Mock origin that references dataset-1
        origin1 = Mock()
        origin1.object_type = "dataset"
        origin1.object_id = "dataset-123"
        origin1.internal = False
        function1.origin = origin1

        function1.to_dict.return_value = {
            "id": "func-123",
            "name": "Function 1",
            "slug": "function-1",
            "project_id": "project-456",
            "function_data": {"type": "code", "code": "def func1(): pass"},
            "origin": {
                "object_type": "dataset",
                "object_id": "dataset-123",
                "internal": False,
            },
        }

        function2 = Mock(spec=Function)
        function2.id = "func-456"
        function2.name = "Function 2"
        function2.slug = "function-2"
        function2.project_id = "project-456"
        function2.function_data = {"type": "code", "code": "def func2(): pass"}

        # Mock origin that references dataset-2 (same type, different ID)
        origin2 = Mock()
        origin2.object_type = "dataset"
        origin2.object_id = "dataset-456"
        origin2.internal = False
        function2.origin = origin2

        function2.to_dict.return_value = {
            "id": "func-456",
            "name": "Function 2",
            "slug": "function-2",
            "project_id": "project-456",
            "function_data": {"type": "code", "code": "def func2(): pass"},
            "origin": {
                "object_type": "dataset",
                "object_id": "dataset-456",
                "internal": False,
            },
        }

        # Mock the dataset resources
        source_dataset1 = Mock()
        source_dataset1.id = "dataset-123"
        source_dataset1.name = "Dataset 1"

        source_dataset2 = Mock()
        source_dataset2.id = "dataset-456"
        source_dataset2.name = "Dataset 2"

        dest_dataset1 = Mock()
        dest_dataset1.id = "dest-dataset-123"
        dest_dataset1.name = "Dataset 1"

        dest_dataset2 = Mock()
        dest_dataset2.id = "dest-dataset-456"
        dest_dataset2.name = "Dataset 2"

        # Track API call count
        api_call_count = 0

        async def mock_list_resources_with_client(client, resource_type, project_id):
            nonlocal api_call_count
            if resource_type == "datasets":
                api_call_count += 1
                if client == migrator.source_client:
                    return [source_dataset1, source_dataset2]
                elif client == migrator.dest_client:
                    return [dest_dataset1, dest_dataset2]
            return []

        migrator._list_resources_with_client = mock_list_resources_with_client

        # Mock successful function creations
        created_function1 = Mock(spec=Function)
        created_function1.id = "dest-func-123"

        created_function2 = Mock(spec=Function)
        created_function2.id = "dest-func-456"

        # Return different functions for different calls
        call_order = []

        def mock_with_retry(operation_name, func):
            call_order.append(operation_name)
            if len(call_order) == 1:  # First function creation
                return created_function1
            else:  # Second function creation
                return created_function2

        mock_dest_client.with_retry.side_effect = mock_with_retry

        # Migrate first function - should make API calls to fetch datasets
        result1 = await migrator.migrate_resource(function1)
        assert result1 == "dest-func-123"
        assert api_call_count == 2  # Called for both source and dest datasets

        # Migrate second function - should use cached datasets, no additional API calls
        result2 = await migrator.migrate_resource(function2)
        assert result2 == "dest-func-456"
        assert api_call_count == 2  # Should still be 2, cache was used

        # Verify both mappings were created correctly
        assert migrator.state.id_mapping["dataset-123"] == "dest-dataset-123"
        assert migrator.state.id_mapping["dataset-456"] == "dest-dataset-456"
