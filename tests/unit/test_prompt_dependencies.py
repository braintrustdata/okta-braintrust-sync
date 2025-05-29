"""Unit tests for PromptMigrator dependency resolution."""

from unittest.mock import AsyncMock, Mock

import pytest
from braintrust_api.types import Prompt

from braintrust_migrate.resources.prompts import PromptMigrator


@pytest.fixture
def mock_source_client():
    """Create a mock source client."""
    client = Mock()
    client.client.prompts.list = AsyncMock()
    client.with_retry = AsyncMock()
    return client


@pytest.fixture
def mock_dest_client():
    """Create a mock destination client."""
    client = Mock()
    client.client.prompts.list = AsyncMock()
    client.client.prompts.create = AsyncMock()
    client.with_retry = AsyncMock()
    return client


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Create a temporary checkpoint directory."""
    return tmp_path / "checkpoints"


@pytest.fixture
def prompt_with_function_dependency():
    """Create a prompt that depends on a function."""
    prompt = Mock(spec=Prompt)
    prompt.id = "prompt-123"
    prompt.name = "Test Prompt with Function"
    prompt.slug = "test-prompt-function"
    prompt.project_id = "project-456"
    prompt.description = "A test prompt with function dependency"
    prompt.tags = ["test"]
    prompt.function_type = "llm"

    # Mock prompt_data with tool_functions dependency
    prompt_data = Mock()
    func = Mock()
    func.type = "function"
    func.id = "function-789"
    prompt_data.tool_functions = [func]
    prompt_data.origin = None
    prompt.prompt_data = prompt_data

    # Mock the to_dict method to return a proper dictionary
    prompt.to_dict.return_value = {
        "id": "prompt-123",
        "name": "Test Prompt with Function",
        "slug": "test-prompt-function",
        "project_id": "project-456",
        "description": "A test prompt with function dependency",
        "tags": ["test"],
        "function_type": "llm",
        "prompt_data": {
            "tool_functions": [{"type": "function", "id": "function-789"}],
            "origin": None,
        },
    }

    return prompt


@pytest.fixture
def prompt_with_prompt_dependency():
    """Create a prompt that depends on another prompt."""
    prompt = Mock(spec=Prompt)
    prompt.id = "prompt-456"
    prompt.name = "Derived Prompt"
    prompt.slug = "derived-prompt"
    prompt.project_id = "project-456"
    prompt.description = "A prompt derived from another"
    prompt.tags = ["derived"]
    prompt.function_type = "llm"

    # Mock prompt_data with origin dependency
    prompt_data = Mock()
    prompt_data.tool_functions = None
    origin = Mock()
    origin.prompt_id = "prompt-base-123"
    origin.project_id = "project-456"
    origin.prompt_version = "v1"
    prompt_data.origin = origin
    prompt.prompt_data = prompt_data

    # Mock the to_dict method to return a proper dictionary
    prompt.to_dict.return_value = {
        "id": "prompt-456",
        "name": "Derived Prompt",
        "slug": "derived-prompt",
        "project_id": "project-456",
        "description": "A prompt derived from another",
        "tags": ["derived"],
        "function_type": "llm",
        "prompt_data": {
            "tool_functions": None,
            "origin": {
                "prompt_id": "prompt-base-123",
                "project_id": "project-456",
                "prompt_version": "v1",
            },
        },
    }

    return prompt


@pytest.fixture
def prompt_without_dependencies():
    """Create a prompt without any dependencies."""
    prompt = Mock(spec=Prompt)
    prompt.id = "prompt-789"
    prompt.name = "Independent Prompt"
    prompt.slug = "independent-prompt"
    prompt.project_id = "project-456"
    prompt.description = "A prompt without dependencies"
    prompt.tags = ["independent"]
    prompt.function_type = "llm"

    # Mock prompt_data without dependencies
    prompt_data = Mock()
    prompt_data.tool_functions = None
    prompt_data.origin = None
    prompt.prompt_data = prompt_data

    # Mock the to_dict method to return a proper dictionary
    prompt.to_dict.return_value = {
        "id": "prompt-789",
        "name": "Independent Prompt",
        "slug": "independent-prompt",
        "project_id": "project-456",
        "description": "A prompt without dependencies",
        "tags": ["independent"],
        "function_type": "llm",
        "prompt_data": {
            "tool_functions": None,
            "origin": None,
        },
    }

    return prompt


@pytest.mark.asyncio
class TestPromptDependencies:
    """Test dependency resolution in PromptMigrator."""

    async def test_get_dependencies_with_function(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        prompt_with_function_dependency,
    ):
        """Test that prompts with function dependencies return correct dependencies."""
        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(prompt_with_function_dependency)

        assert dependencies == ["function-789"]

    async def test_get_dependencies_with_prompt_origin(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        prompt_with_prompt_dependency,
    ):
        """Test that prompts with origin dependencies return correct dependencies."""
        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(prompt_with_prompt_dependency)

        assert dependencies == ["prompt-base-123"]

    async def test_get_dependencies_without_dependencies(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        prompt_without_dependencies,
    ):
        """Test that prompts without dependencies return no dependencies."""
        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(prompt_without_dependencies)

        assert dependencies == []

    async def test_should_migrate_resource_first_pass(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        prompt_without_dependencies,
        prompt_with_function_dependency,
    ):
        """Test that first pass only migrates prompts without dependencies."""
        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        # First pass (default)
        migrator.set_final_pass(False)

        # Should migrate prompt without dependencies
        should_migrate = await migrator.should_migrate_resource(
            prompt_without_dependencies
        )
        assert should_migrate is True

        # Should NOT migrate prompt with dependencies
        should_migrate = await migrator.should_migrate_resource(
            prompt_with_function_dependency
        )
        assert should_migrate is False

    async def test_should_migrate_resource_final_pass(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        prompt_without_dependencies,
        prompt_with_function_dependency,
    ):
        """Test that final pass only migrates prompts with dependencies."""
        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        # Final pass
        migrator.set_final_pass(True)

        # Should NOT migrate prompt without dependencies
        should_migrate = await migrator.should_migrate_resource(
            prompt_without_dependencies
        )
        assert should_migrate is False

        # Should migrate prompt with dependencies
        should_migrate = await migrator.should_migrate_resource(
            prompt_with_function_dependency
        )
        assert should_migrate is True

    async def test_resolve_prompt_data_dependencies(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test resolving dependencies in prompt_data."""
        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Mock ID mappings
        migrator.state.id_mapping["function-789"] = "dest-function-789"
        migrator.state.id_mapping["prompt-base-123"] = "dest-prompt-base-123"

        # Create prompt_data with dependencies as a dictionary
        prompt_data = {
            "tool_functions": [
                {"type": "function", "id": "function-789"},
                {"type": "global", "name": "global_func"},  # Should be kept as-is
            ],
            "origin": {
                "prompt_id": "prompt-base-123",
                "project_id": "project-456",
                "prompt_version": "v1",
            },
            "other_field": "should_be_preserved",
        }

        resolved_data = migrator._resolve_prompt_data_dependencies(prompt_data)

        # Check tool functions were resolved
        assert len(resolved_data["tool_functions"]) == len(
            prompt_data["tool_functions"]
        )
        assert resolved_data["tool_functions"][0]["id"] == "dest-function-789"
        assert resolved_data["tool_functions"][1]["name"] == "global_func"  # Unchanged

        # Check origin was resolved
        assert resolved_data["origin"]["prompt_id"] == "dest-prompt-base-123"
        assert resolved_data["origin"]["project_id"] == "dest-project-456"
        assert resolved_data["origin"]["prompt_version"] == "v1"  # Unchanged

        # Check other fields preserved
        assert resolved_data["other_field"] == "should_be_preserved"

    async def test_migrate_resource_with_resolved_dependencies(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        prompt_with_function_dependency,
    ):
        """Test migration with resolved dependencies."""
        # Mock successful prompt creation
        new_prompt = Mock(spec=Prompt)
        new_prompt.id = "new-prompt-123"
        mock_dest_client.with_retry.return_value = new_prompt

        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        # Mock that the function dependency has been resolved
        migrator.state.id_mapping["function-789"] = "dest-function-789"

        result = await migrator.migrate_resource(prompt_with_function_dependency)

        assert result == "new-prompt-123"
        mock_dest_client.with_retry.assert_called_once()
