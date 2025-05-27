"""Unit tests for ViewMigrator dependency resolution."""

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
def temp_checkpoint_dir(tmp_path):
    """Create a temporary checkpoint directory."""
    return tmp_path / "checkpoints"


@pytest.fixture
def project_view():
    """Create a view that references a project."""
    view = Mock(spec=View)
    view.id = "view-123"
    view.name = "Project Overview"
    view.object_type = "project"
    view.object_id = "project-456"
    view.view_type = "experiments"
    view.view_data = {"filters": []}
    view.options = {"columnVisibility": {}}
    view.user_id = "user-789"
    return view


@pytest.fixture
def experiment_view():
    """Create a view that references an experiment."""
    view = Mock(spec=View)
    view.id = "view-456"
    view.name = "Experiment Details"
    view.object_type = "experiment"
    view.object_id = "experiment-123"
    view.view_type = "logs"
    view.view_data = {"sort": [{"field": "timestamp", "order": "desc"}]}
    view.options = {"pageSize": 50}
    view.user_id = "user-789"
    return view


@pytest.fixture
def dataset_view():
    """Create a view that references a dataset."""
    view = Mock(spec=View)
    view.id = "view-789"
    view.name = "Dataset Analysis"
    view.object_type = "dataset"
    view.object_id = "dataset-456"
    view.view_type = "dataset"
    view.view_data = {"filters": [{"field": "score", "op": ">", "value": 0.8}]}
    view.options = {"groupBy": ["category"]}
    view.user_id = "user-789"
    return view


@pytest.fixture
def unknown_object_view():
    """Create a view that references an unknown object type."""
    view = Mock(spec=View)
    view.id = "view-999"
    view.name = "Unknown Object View"
    view.object_type = "unknown_type"
    view.object_id = "unknown-123"
    view.view_type = "custom"
    view.view_data = {}
    view.options = {}
    view.user_id = "user-789"
    return view


@pytest.mark.asyncio
class TestViewDependencies:
    """Test dependency resolution in ViewMigrator."""

    async def test_get_dependencies_project_view(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        project_view,
    ):
        """Test that project views return no dependencies (handled separately)."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(project_view)

        # Project views don't return dependencies since projects are handled separately
        assert dependencies == []

    async def test_get_dependencies_experiment_view(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        experiment_view,
    ):
        """Test that experiment views return experiment dependencies."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(experiment_view)

        assert dependencies == ["experiment-123"]

    async def test_get_dependencies_dataset_view(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        dataset_view,
    ):
        """Test that dataset views return dataset dependencies."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(dataset_view)

        assert dependencies == ["dataset-456"]

    async def test_get_dependencies_unknown_object_view(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        unknown_object_view,
    ):
        """Test that unknown object type views return dependencies."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(unknown_object_view)

        assert dependencies == ["unknown-123"]

    async def test_resolve_object_id_project(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        project_view,
    ):
        """Test resolving object_id for project views."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        resolved_id = migrator._resolve_object_id(project_view)

        assert resolved_id == "dest-project-456"

    async def test_resolve_object_id_experiment_resolved(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        experiment_view,
    ):
        """Test resolving object_id for experiment views with mapping."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.state.id_mapping["experiment-123"] = "dest-experiment-123"

        resolved_id = migrator._resolve_object_id(experiment_view)

        assert resolved_id == "dest-experiment-123"

    async def test_resolve_object_id_experiment_unresolved(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        experiment_view,
    ):
        """Test resolving object_id for experiment views without mapping."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        resolved_id = migrator._resolve_object_id(experiment_view)

        # Should return original ID when no mapping exists
        assert resolved_id == "experiment-123"

    async def test_resolve_object_id_dataset_resolved(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        dataset_view,
    ):
        """Test resolving object_id for dataset views with mapping."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.state.id_mapping["dataset-456"] = "dest-dataset-456"

        resolved_id = migrator._resolve_object_id(dataset_view)

        assert resolved_id == "dest-dataset-456"

    async def test_resolve_object_id_unknown_type(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        unknown_object_view,
    ):
        """Test resolving object_id for unknown object types."""
        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        resolved_id = migrator._resolve_object_id(unknown_object_view)

        # Should return original ID for unknown types
        assert resolved_id == "unknown-123"

    async def test_migrate_resource_project_view(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        project_view,
    ):
        """Test migrating a project view."""
        # Mock successful view creation
        new_view = Mock(spec=View)
        new_view.id = "new-view-123"
        mock_dest_client.with_retry.return_value = new_view

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        result = await migrator.migrate_resource(project_view)

        assert result == "new-view-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_experiment_view_resolved(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        experiment_view,
    ):
        """Test migrating an experiment view with resolved dependency."""
        # Mock successful view creation
        new_view = Mock(spec=View)
        new_view.id = "new-view-456"
        mock_dest_client.with_retry.return_value = new_view

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"
        migrator.state.id_mapping["experiment-123"] = "dest-experiment-123"

        result = await migrator.migrate_resource(experiment_view)

        assert result == "new-view-456"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_dataset_view_unresolved(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        dataset_view,
    ):
        """Test migrating a dataset view with unresolved dependency."""
        # Mock successful view creation
        new_view = Mock(spec=View)
        new_view.id = "new-view-789"
        mock_dest_client.with_retry.return_value = new_view

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"
        # Don't add dataset mapping - dependency remains unresolved

        result = await migrator.migrate_resource(dataset_view)

        assert result == "new-view-789"
        mock_dest_client.with_retry.assert_called_once()

    async def test_resource_exists_in_dest_with_resolved_object_id(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        experiment_view,
    ):
        """Test checking if view exists with resolved object_id."""
        # Mock existing view in destination
        existing_view = Mock(spec=View)
        existing_view.id = "existing-view-456"
        existing_view.name = "Experiment Details"
        existing_view.object_id = "dest-experiment-123"
        mock_dest_client.with_retry.return_value = [existing_view]

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"
        migrator.state.id_mapping["experiment-123"] = "dest-experiment-123"

        result = await migrator.resource_exists_in_dest(experiment_view)

        assert result == "existing-view-456"

    async def test_resource_exists_in_dest_not_found(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        project_view,
    ):
        """Test checking if view exists when not found."""
        mock_dest_client.with_retry.return_value = []

        migrator = ViewMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        migrator.dest_project_id = "dest-project-456"

        result = await migrator.resource_exists_in_dest(project_view)

        assert result is None
