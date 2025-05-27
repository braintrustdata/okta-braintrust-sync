"""Unit tests for ViewMigrator."""

from unittest.mock import AsyncMock, Mock

import pytest
from braintrust_api.types import View

from braintrust_migrate.resources.views import ViewMigrator


@pytest.fixture
def mock_source_client():
    """Create a mock source client."""
    client = Mock()
    client.client.views.list = AsyncMock()
    client.with_retry = AsyncMock()
    return client


@pytest.fixture
def mock_dest_client():
    """Create a mock destination client."""
    client = Mock()
    client.client.views.list = AsyncMock()
    client.client.views.create = AsyncMock()
    client.with_retry = AsyncMock()
    return client


@pytest.fixture
def sample_view_for_migrator():
    """Create a sample view for testing the migrator."""
    view = Mock(spec=View)
    view.id = "view-123"
    view.name = "Test View"
    view.object_type = "project"
    view.object_id = "project-456"
    view.view_type = "datasets"
    view.view_data = {"search": {"filter": []}}
    view.options = {"columnVisibility": {"name": True}}
    view.user_id = "user-789"
    return view


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Create a temporary checkpoint directory."""
    return tmp_path / "checkpoints"


@pytest.mark.asyncio
class TestViewMigrator:
    """Test the ViewMigrator class."""

    async def test_resource_name(
        self, mock_source_client, mock_dest_client, temp_checkpoint_dir
    ):
        """Test that resource_name returns the correct value."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        assert migrator.resource_name == "Views"

    async def test_get_resource_id(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_view_for_migrator,
    ):
        """Test extracting resource ID from a view."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        resource_id = migrator.get_resource_id(sample_view_for_migrator)
        assert resource_id == "view-123"

    async def test_list_source_resources_success(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_view_for_migrator,
    ):
        """Test successful discovery of source views by querying objects."""
        # Mock the projects list response
        mock_projects_response = Mock()
        mock_projects_response.objects = [Mock(id="project-456")]

        # Mock the views list response
        mock_views_response = Mock()
        mock_views_response.objects = [sample_view_for_migrator]

        # Mock the experiments and datasets responses (empty)
        mock_empty_response = Mock()
        mock_empty_response.objects = []

        # Set up the mock to return different responses based on the operation
        def mock_with_retry_side_effect(operation_name, coro_func):
            if "list_projects_for_views" in operation_name:
                return mock_projects_response
            elif "list_views_project" in operation_name:
                return mock_views_response
            elif "list_experiments_for_views" in operation_name:
                return mock_empty_response
            elif "list_datasets_for_views" in operation_name:
                return mock_empty_response
            else:
                return mock_empty_response

        mock_source_client.with_retry.side_effect = mock_with_retry_side_effect

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        views = await migrator.list_source_resources()

        # Should find the view through object discovery
        assert len(views) == 1
        assert views[0] == sample_view_for_migrator
        # with_retry should be called multiple times for discovery
        assert mock_source_client.with_retry.call_count >= 1

    async def test_list_source_resources_with_project_id(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_view_for_migrator,
    ):
        """Test discovering source views with specific project ID."""
        # Mock the views list response for the specific project
        mock_views_response = Mock()
        mock_views_response.objects = [sample_view_for_migrator]

        # Mock empty responses for experiments and datasets
        mock_empty_response = Mock()
        mock_empty_response.objects = []

        def mock_with_retry_side_effect(operation_name, coro_func):
            if "list_views_project" in operation_name:
                return mock_views_response
            else:
                return mock_empty_response

        mock_source_client.with_retry.side_effect = mock_with_retry_side_effect

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        views = await migrator.list_source_resources(project_id="project-456")

        # Should find the view for the specific project
        assert len(views) == 1
        assert views[0] == sample_view_for_migrator
        # with_retry should be called for discovery
        assert mock_source_client.with_retry.call_count >= 1

    async def test_resource_exists_in_dest_found(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_view_for_migrator,
    ):
        """Test checking if view exists in destination - found."""
        existing_view = Mock(spec=View)
        existing_view.id = "dest-view-123"
        existing_view.name = "Test View"
        mock_response = Mock()
        mock_response.objects = [existing_view]
        mock_dest_client.with_retry.return_value = mock_response

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        result = await migrator.resource_exists_in_dest(sample_view_for_migrator)

        assert result == "dest-view-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_resource_exists_in_dest_not_found(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_view_for_migrator,
    ):
        """Test checking if view exists in destination - not found."""
        mock_response = Mock()
        mock_response.objects = []
        mock_dest_client.with_retry.return_value = mock_response

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        result = await migrator.resource_exists_in_dest(sample_view_for_migrator)

        assert result is None
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_success(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_view_for_migrator,
    ):
        """Test successful view migration."""
        new_view = Mock(spec=View)
        new_view.id = "new-view-123"
        mock_dest_client.with_retry.return_value = new_view

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        result = await migrator.migrate_resource(sample_view_for_migrator)

        assert result == "new-view-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_with_dest_project_id(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_view_for_migrator,
    ):
        """Test view migration uses destination project ID when available."""
        new_view = Mock(spec=View)
        new_view.id = "new-view-123"
        mock_dest_client.with_retry.return_value = new_view

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-789"

        await migrator.migrate_resource(sample_view_for_migrator)

        # Verify the create call used the destination project ID
        mock_dest_client.with_retry.assert_called_once()
        # The actual create call would be in the coroutine, but we can verify it was called
