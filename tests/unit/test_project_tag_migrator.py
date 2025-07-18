"""Unit tests for ProjectTagMigrator."""

from unittest.mock import Mock

import pytest
from braintrust_api.types import ProjectTag

from braintrust_migrate.resources.project_tags import ProjectTagMigrator


@pytest.mark.asyncio
class TestProjectTagMigrator:
    """Test the ProjectTagMigrator class."""

    async def test_resource_name(
        self, mock_source_client, mock_dest_client, temp_checkpoint_dir
    ):
        """Test that resource_name returns the correct value."""
        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        assert migrator.resource_name == "ProjectTags"

    async def test_get_resource_id(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test getting the resource ID from a project tag."""
        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        assert migrator.get_resource_id(sample_project_tag) == "tag-123"

    async def test_list_source_resources_success(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test successfully listing project tags from source."""
        # Mock the response with objects attribute
        mock_response = Mock()
        mock_response.objects = [sample_project_tag]

        mock_source_client.with_retry.return_value = mock_response

        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.list_source_resources()

        assert len(result) == 1
        assert result[0] == sample_project_tag
        mock_source_client.with_retry.assert_called_once()

    async def test_list_source_resources_with_project_filter(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test listing project tags with project ID filter."""
        # Create tags for different projects
        tag1 = Mock(spec=ProjectTag)
        tag1.id = "tag-1"
        tag1.project_id = "project-456"
        tag1.name = "Tag 1"

        tag2 = Mock(spec=ProjectTag)
        tag2.id = "tag-2"
        tag2.project_id = "project-789"
        tag2.name = "Tag 2"

        mock_response = Mock()
        mock_response.objects = [tag1, tag2]
        mock_source_client.with_retry.return_value = mock_response

        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Filter by project ID
        result = await migrator.list_source_resources(project_id="project-456")

        assert len(result) == 1
        assert result[0].id == "tag-1"

    async def test_list_source_resources_async_iterator(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test listing project tags when response is an async iterator."""

        async def async_iter():
            yield sample_project_tag

        mock_response = Mock()
        mock_response.__aiter__ = lambda self: async_iter()
        mock_source_client.with_retry.return_value = mock_response

        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.list_source_resources()

        assert len(result) == 1
        assert result[0] == sample_project_tag

    async def test_list_source_resources_direct_list(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test listing project tags when response is a direct list."""
        mock_source_client.with_retry.return_value = [sample_project_tag]

        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.list_source_resources()

        assert len(result) == 1
        assert result[0] == sample_project_tag

    async def test_list_source_resources_error(
        self, mock_source_client, mock_dest_client, temp_checkpoint_dir
    ):
        """Test error handling when listing project tags fails."""
        mock_source_client.with_retry.side_effect = Exception("API Error")

        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        with pytest.raises(Exception, match="API Error"):
            await migrator.list_source_resources()

    async def test_migrate_resource_success_full_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test successful migration with all fields."""
        # Set up ID mapping
        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.state.id_mapping["project-456"] = "dest-project-456"

        # Mock successful creation
        new_tag = Mock(spec=ProjectTag)
        new_tag.id = "new-tag-123"
        mock_dest_client.with_retry.return_value = new_tag

        result = await migrator.migrate_resource(sample_project_tag)

        assert result == "new-tag-123"

        # Verify the create call was made
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_success_minimal_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test successful migration with minimal fields."""
        # Create a tag with minimal fields
        minimal_tag = Mock(spec=ProjectTag)
        minimal_tag.id = "tag-123"
        minimal_tag.name = "Minimal Tag"
        minimal_tag.project_id = "project-456"
        minimal_tag.user_id = "user-789"
        minimal_tag.created = "2023-01-01T00:00:00Z"
        minimal_tag.description = None
        minimal_tag.color = None

        # Mock the to_dict method
        minimal_tag.to_dict.return_value = {
            "id": "tag-123",
            "name": "Minimal Tag",
            "project_id": "project-456",
            "user_id": "user-789",
            "created": "2023-01-01T00:00:00Z",
            "description": None,
            "color": None,
        }

        # Set up ID mapping
        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.state.id_mapping["project-456"] = "dest-project-456"

        # Mock successful creation
        new_tag = Mock(spec=ProjectTag)
        new_tag.id = "new-tag-123"
        mock_dest_client.with_retry.return_value = new_tag

        result = await migrator.migrate_resource(minimal_tag)

        assert result == "new-tag-123"

    async def test_migrate_resource_no_project_mapping(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test migration failure when no project mapping exists."""
        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        # No ID mapping set up

        with pytest.raises(ValueError, match="No destination project mapping found"):
            await migrator.migrate_resource(sample_project_tag)

        mock_dest_client.with_retry.assert_not_called()

    async def test_migrate_resource_creation_error(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test migration failure when creation fails."""
        # Set up ID mapping
        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.state.id_mapping["project-456"] = "dest-project-456"

        # Mock creation failure
        mock_dest_client.with_retry.side_effect = Exception("Creation failed")

        with pytest.raises(Exception, match="Failed to migrate project tag"):
            await migrator.migrate_resource(sample_project_tag)

    async def test_get_dependencies(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_project_tag,
    ):
        """Test that project tags have no dependencies."""
        migrator = ProjectTagMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(sample_project_tag)

        assert dependencies == []
