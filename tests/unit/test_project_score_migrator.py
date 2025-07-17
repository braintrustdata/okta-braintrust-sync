"""Tests for ProjectScoreMigrator."""

from unittest.mock import Mock

import pytest

from braintrust_migrate.resources.base import MigrationState
from braintrust_migrate.resources.project_scores import ProjectScoreMigrator


@pytest.fixture
def migration_state():
    """Create a migration state for testing."""
    state = MigrationState()
    state.id_mapping = {
        "project-456": "dest-project-789",
        "function-123": "dest-function-456",
    }
    return state


@pytest.fixture
def project_score_migrator(
    mock_source_client, mock_dest_client, migration_state, temp_checkpoint_dir
):
    """Create a ProjectScoreMigrator for testing."""
    migrator = ProjectScoreMigrator(
        source_client=mock_source_client,
        dest_client=mock_dest_client,
        checkpoint_dir=temp_checkpoint_dir,
        batch_size=10,
    )
    # Manually set the state for testing
    migrator.state = migration_state
    migrator.set_destination_project_id("dest-project-789")
    return migrator


class TestProjectScoreMigrator:
    """Test cases for ProjectScoreMigrator."""

    def test_resource_name(self, project_score_migrator):
        """Test that resource_name returns the correct value."""
        assert project_score_migrator.resource_name == "ProjectScores"

    def test_get_resource_id(self, project_score_migrator, sample_project_score):
        """Test getting resource ID from a project score."""
        resource_id = project_score_migrator.get_resource_id(sample_project_score)
        assert resource_id == "score-123"

    @pytest.mark.asyncio
    async def test_list_source_resources_no_filter(
        self, project_score_migrator, mock_source_client, sample_project_score
    ):
        """Test listing all project scores without project filter."""
        # Mock the response
        mock_response = Mock()
        mock_response.objects = [sample_project_score]
        mock_source_client.with_retry.return_value = mock_response

        # Call the method
        result = await project_score_migrator.list_source_resources()

        # Verify the call
        mock_source_client.with_retry.assert_called_once()
        assert result == [sample_project_score]

    @pytest.mark.asyncio
    async def test_list_source_resources_with_project_filter(
        self, project_score_migrator, mock_source_client, sample_project_score
    ):
        """Test listing project scores with project filter."""
        # Mock the response
        mock_response = Mock()
        mock_response.objects = [sample_project_score]
        mock_source_client.with_retry.return_value = mock_response

        # Call the method
        result = await project_score_migrator.list_source_resources(
            project_id="project-456"
        )

        # Verify the call
        mock_source_client.with_retry.assert_called_once()
        assert result == [sample_project_score]

    @pytest.mark.asyncio
    async def test_list_source_resources_async_iterator(
        self, project_score_migrator, mock_source_client, sample_project_score
    ):
        """Test listing project scores with async iterator response."""

        async def async_iter():
            yield sample_project_score

        mock_response = async_iter()
        mock_source_client.with_retry.return_value = mock_response

        # Call the method
        result = await project_score_migrator.list_source_resources()

        # Verify the result
        assert result == [sample_project_score]

    @pytest.mark.asyncio
    async def test_list_source_resources_direct_list(
        self, project_score_migrator, mock_source_client, sample_project_score
    ):
        """Test listing project scores with direct list response."""
        mock_response = [sample_project_score]
        mock_source_client.with_retry.return_value = mock_response

        # Call the method
        result = await project_score_migrator.list_source_resources()

        # Verify the result
        assert result == [sample_project_score]

    @pytest.mark.asyncio
    async def test_list_source_resources_error(
        self, project_score_migrator, mock_source_client
    ):
        """Test error handling in list_source_resources."""
        mock_source_client.with_retry.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            await project_score_migrator.list_source_resources()

    @pytest.mark.asyncio
    async def test_migrate_resource_success(
        self, project_score_migrator, mock_dest_client, sample_project_score
    ):
        """Test successful project score migration."""
        # Mock successful creation
        new_score = Mock()
        new_score.id = "new-score-456"
        mock_dest_client.with_retry.return_value = new_score

        # Call the method
        result = await project_score_migrator.migrate_resource(sample_project_score)

        # Verify the result
        assert result == "new-score-456"

        # Verify the create call
        mock_dest_client.with_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_migrate_resource_with_config(
        self, project_score_migrator, mock_dest_client, sample_project_score
    ):
        """Test project score migration with config containing function references."""
        # Set up project score with config that has to_dict method
        config = Mock()
        config.to_dict.return_value = {
            "online": {
                "sampling_rate": 0.5,
                "scorers": [
                    {"type": "function", "id": "function-123"},
                    {"type": "global", "name": "global_scorer"},
                ],
            },
            "multi_select": True,
        }

        sample_project_score.config = config

        # Mock successful creation
        new_score = Mock()
        new_score.id = "new-score-456"
        mock_dest_client.with_retry.return_value = new_score

        # Call the method
        result = await project_score_migrator.migrate_resource(sample_project_score)

        # Verify the result
        assert result == "new-score-456"

        # Verify that create was called with the resolved config
        mock_dest_client.with_retry.assert_called_once()
        call_args = mock_dest_client.with_retry.call_args[0]
        assert call_args[0] == "create_project_score"

    @pytest.mark.asyncio
    async def test_migrate_resource_no_project_mapping(
        self, project_score_migrator, mock_dest_client, sample_project_score
    ):
        """Test project score migration when no project mapping exists but dest_project_id is available."""
        # Create a project score with unmapped project ID
        sample_project_score.project_id = "unmapped-project"

        # Set up the dest_project_id (this would be set by the orchestrator)
        project_score_migrator.dest_project_id = "dest-project-789"

        # Mock successful creation
        new_score = Mock()
        new_score.id = "new-score-456"
        mock_dest_client.with_retry.return_value = new_score

        # Call the method
        result = await project_score_migrator.migrate_resource(sample_project_score)

        # Verify the result - it should succeed using the dest_project_id
        assert result == "new-score-456"

    @pytest.mark.asyncio
    async def test_migrate_resource_no_project_mapping_or_dest_id(
        self, project_score_migrator, mock_dest_client, sample_project_score
    ):
        """Test project score migration when neither project mapping nor dest_project_id exists."""
        # Create a project score with unmapped project ID
        sample_project_score.project_id = "unmapped-project"

        # Don't set dest_project_id (it's None by default)
        project_score_migrator.dest_project_id = None

        # Call the method and expect an exception
        with pytest.raises(ValueError, match="No destination project mapping found"):
            await project_score_migrator.migrate_resource(sample_project_score)

        # Verify that create was never called
        mock_dest_client.with_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_resource_error(
        self, project_score_migrator, mock_dest_client, sample_project_score
    ):
        """Test error handling in migrate_resource."""
        mock_dest_client.with_retry.side_effect = Exception("API Error")

        # Call the method and expect an exception
        with pytest.raises(Exception, match="Failed to migrate project score"):
            await project_score_migrator.migrate_resource(sample_project_score)

    @pytest.mark.asyncio
    async def test_resolve_config_dependencies_none(self, project_score_migrator):
        """Test resolving config dependencies when config is None."""
        result = await project_score_migrator._resolve_config_dependencies(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_config_dependencies_no_online(self, project_score_migrator):
        """Test resolving config dependencies when no online config exists."""
        config = Mock()
        config.to_dict.return_value = {"multi_select": True}

        result = await project_score_migrator._resolve_config_dependencies(config)
        assert result == {"multi_select": True}

    @pytest.mark.asyncio
    async def test_resolve_config_dependencies_with_scorers(
        self, project_score_migrator
    ):
        """Test resolving config dependencies with scorer functions."""
        # Create mock scorer objects with to_dict methods (as they would be in production)
        scorer1 = Mock()
        scorer1.to_dict.return_value = {"type": "function", "id": "function-123"}

        scorer2 = Mock()
        scorer2.to_dict.return_value = {"type": "global", "name": "global_scorer"}

        config = Mock()
        config.to_dict.return_value = {
            "online": {
                "sampling_rate": 0.5,
                "scorers": [
                    scorer1,
                    scorer2,
                ],  # These are still objects with to_dict methods
            }
        }

        result = await project_score_migrator._resolve_config_dependencies(config)

        # Verify function ID was mapped
        expected_scorers = [
            {"type": "function", "id": "dest-function-456"},
            {"type": "global", "name": "global_scorer"},
        ]
        assert result["online"]["scorers"] == expected_scorers

    @pytest.mark.asyncio
    async def test_resolve_function_reference_function_type(
        self, project_score_migrator
    ):
        """Test resolving function reference of type 'function'."""
        function_ref = Mock()
        function_ref.to_dict.return_value = {"type": "function", "id": "function-123"}

        result = project_score_migrator._resolve_function_reference_generic(
            function_ref
        )
        assert result == {"type": "function", "id": "dest-function-456"}

    @pytest.mark.asyncio
    async def test_resolve_function_reference_global_type(self, project_score_migrator):
        """Test resolving function reference of type 'global'."""
        function_ref = Mock()
        function_ref.to_dict.return_value = {"type": "global", "name": "global_scorer"}

        result = project_score_migrator._resolve_function_reference_generic(
            function_ref
        )
        assert result == {"type": "global", "name": "global_scorer"}

    @pytest.mark.asyncio
    async def test_resolve_function_reference_unmapped_function(
        self, project_score_migrator
    ):
        """Test resolving function reference with unmapped function ID."""
        function_ref = Mock()
        function_ref.to_dict.return_value = {
            "type": "function",
            "id": "unmapped-function",
        }

        result = project_score_migrator._resolve_function_reference_generic(
            function_ref
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_function_reference_unknown_type(
        self, project_score_migrator
    ):
        """Test resolving function reference with unknown type."""
        function_ref = Mock()
        function_ref.to_dict.return_value = {"type": "unknown", "id": "some-id"}

        result = project_score_migrator._resolve_function_reference_generic(
            function_ref
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_function_reference_none(self, project_score_migrator):
        """Test resolving None function reference."""
        result = project_score_migrator._resolve_function_reference_generic(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_dependencies_basic(
        self, project_score_migrator, sample_project_score
    ):
        """Test getting dependencies for a basic project score."""
        dependencies = await project_score_migrator.get_dependencies(
            sample_project_score
        )
        assert dependencies == ["project-456"]

    @pytest.mark.asyncio
    async def test_get_dependencies_with_function_scorers(
        self, project_score_migrator, sample_project_score
    ):
        """Test getting dependencies for project score with function scorers."""
        # Set up project score with function dependencies
        scorer1 = Mock()
        scorer1.type = "function"
        scorer1.id = "function-123"

        scorer2 = Mock()
        scorer2.type = "global"
        scorer2.name = "global_scorer"

        online_config = Mock()
        online_config.scorers = [scorer1, scorer2]

        config = Mock()
        config.online = online_config

        sample_project_score.config = config

        dependencies = await project_score_migrator.get_dependencies(
            sample_project_score
        )
        assert set(dependencies) == {"project-456", "function-123"}

    @pytest.mark.asyncio
    async def test_get_dependencies_no_config(
        self, project_score_migrator, sample_project_score
    ):
        """Test getting dependencies when config is None."""
        sample_project_score.config = None
        dependencies = await project_score_migrator.get_dependencies(
            sample_project_score
        )
        assert dependencies == ["project-456"]
