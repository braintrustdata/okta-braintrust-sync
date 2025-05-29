"""Unit tests for OpenAPI-based inclusion approach."""

from unittest.mock import Mock

import pytest

from braintrust_migrate.openapi_utils import get_resource_create_fields
from braintrust_migrate.resources.prompts import PromptMigrator


@pytest.mark.asyncio
class TestOpenAPIInclusion:
    """Test the inclusion approach using OpenAPI schemas."""

    async def test_prompt_migrator_serialization_with_inclusion(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that PromptMigrator only includes allowed fields during serialization."""
        migrator = PromptMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Create a mock prompt with various fields
        mock_prompt = Mock()
        mock_prompt.id = "prompt-123"
        mock_prompt.name = "Test Prompt"
        mock_prompt.slug = "test-prompt"
        mock_prompt.description = "A test prompt"
        mock_prompt.created = "2024-01-01T00:00:00Z"
        mock_prompt.log_id = "p"
        mock_prompt.function_data = {"type": "code"}
        mock_prompt.metadata = {"version": "1.0"}
        mock_prompt.prompt_data = {"template": "Hello {{name}}"}
        mock_prompt.tags = ["test"]
        mock_prompt.function_type = "llm"
        mock_prompt.project_id = "project-456"
        mock_prompt.org_id = "org-789"
        mock_prompt._xact_id = "xact-123"

        # Mock the to_dict method to return all fields
        mock_prompt.to_dict.return_value = {
            "id": "prompt-123",
            "name": "Test Prompt",
            "slug": "test-prompt",
            "description": "A test prompt",
            "created": "2024-01-01T00:00:00Z",
            "log_id": "p",
            "function_data": {"type": "code"},
            "metadata": {"version": "1.0"},
            "prompt_data": {"template": "Hello {{name}}"},
            "tags": ["test"],
            "function_type": "llm",
            "project_id": "project-456",
            "org_id": "org-789",
            "_xact_id": "xact-123",
        }

        # Serialize the resource
        serialized = migrator.serialize_resource_for_insert(mock_prompt)

        # Should only include fields allowed by CreatePrompt schema
        expected_fields = {
            "name",
            "slug",
            "description",
            "prompt_data",
            "tags",
            "function_type",
            "project_id",
        }

        assert set(serialized.keys()) == expected_fields

        # Verify specific exclusions
        assert "id" not in serialized  # Server-generated
        assert "created" not in serialized  # Server-generated
        assert "log_id" not in serialized  # Internal field
        assert "function_data" not in serialized  # Not in CreatePrompt schema
        assert "metadata" not in serialized  # Not in CreatePrompt schema
        assert "org_id" not in serialized  # Not in CreatePrompt schema
        assert "_xact_id" not in serialized  # Internal field

        # Verify included fields have correct values
        assert serialized["name"] == "Test Prompt"
        assert serialized["slug"] == "test-prompt"
        assert serialized["description"] == "A test prompt"
        assert serialized["prompt_data"] == {"template": "Hello {{name}}"}
        assert serialized["tags"] == ["test"]
        assert serialized["function_type"] == "llm"
        assert serialized["project_id"] == "project-456"

    async def test_fallback_when_no_schema_found(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that migrators fall back gracefully when no OpenAPI schema is found."""

        # Create a migrator for a non-existent resource type
        class UnknownMigrator(PromptMigrator):
            @property
            def resource_name(self) -> str:
                return "UnknownResources"  # This won't exist in OpenAPI spec

        migrator = UnknownMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Should not have allowed fields (no schema found)
        assert migrator.allowed_fields_for_insert is None

        # Create a mock resource
        mock_resource = Mock()
        mock_resource.id = "unknown-123"
        mock_resource.name = "Test Resource"
        mock_resource.some_field = "some_value"

        # Mock the to_dict method
        mock_resource.to_dict.return_value = {
            "id": "unknown-123",
            "name": "Test Resource",
            "some_field": "some_value",
        }

        # Should return all fields with a warning (fallback behavior)
        serialized = migrator.serialize_resource_for_insert(mock_resource)

        # Should include all original fields since no schema filtering is applied
        expected_fields = {"id", "name", "some_field"}
        assert set(serialized.keys()) == expected_fields

    def test_openapi_field_extraction_accuracy(self):
        """Test that the OpenAPI field extraction matches the actual spec."""
        # Get allowed fields for CreatePrompt
        allowed = get_resource_create_fields("Prompt")

        # These should match exactly what we see in the OpenAPI spec
        expected_allowed = {
            "project_id",
            "name",
            "slug",
            "description",
            "prompt_data",
            "tags",
            "function_type",
        }

        assert allowed == expected_allowed

    def test_openapi_handles_missing_schema_gracefully(self):
        """Test that missing schemas are handled gracefully."""
        # Try to get fields for a non-existent schema
        allowed = get_resource_create_fields("NonExistentResource")

        # Should return None for missing schema
        assert allowed is None
