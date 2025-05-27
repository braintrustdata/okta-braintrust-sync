"""Unit tests for excluded_fields_for_insert property overrides."""

import pytest

from braintrust_migrate.resources.base import ResourceMigrator
from braintrust_migrate.resources.datasets import DatasetMigrator
from braintrust_migrate.resources.experiments import ExperimentMigrator
from braintrust_migrate.resources.functions import FunctionMigrator
from braintrust_migrate.resources.logs import LogsMigrator


@pytest.mark.asyncio
class TestExcludedFieldsOverrides:
    """Test that migrators properly override excluded_fields_for_insert."""

    async def test_base_migrator_excluded_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that base migrator has expected excluded fields."""

        # Create a simple concrete implementation for testing
        class TestMigrator(ResourceMigrator):
            @property
            def resource_name(self) -> str:
                return "Test"

            async def list_source_resources(self, project_id=None):
                return []

            async def resource_exists_in_dest(self, resource):
                return None

            async def migrate_resource(self, resource):
                return "test_id"

        migrator = TestMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        expected_base_fields = {
            "id",
            "created",
            "_xact_id",
            "xact_id",  # Alternative naming
            "_object_delete",
            "_pagination_key",
            "comparison_key",
            "project_id",
            "org_id",  # Added to base class
        }

        assert migrator.excluded_fields_for_insert == expected_base_fields

    async def test_dataset_migrator_excluded_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that DatasetMigrator includes dataset_id in excluded fields."""
        migrator = DatasetMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Should include all base fields plus dataset_id
        expected_fields = {
            "id",
            "created",
            "_xact_id",
            "xact_id",  # Alternative naming
            "_object_delete",
            "_pagination_key",
            "comparison_key",
            "project_id",
            "org_id",  # Added to base class
            "dataset_id",  # Added by DatasetMigrator
        }

        assert migrator.excluded_fields_for_insert == expected_fields
        assert "dataset_id" in migrator.excluded_fields_for_insert

    async def test_experiment_migrator_excluded_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that ExperimentMigrator includes experiment_id in excluded fields."""
        migrator = ExperimentMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Should include all base fields plus experiment_id
        expected_fields = {
            "id",
            "created",
            "_xact_id",
            "xact_id",  # Alternative naming
            "_object_delete",
            "_pagination_key",
            "comparison_key",
            "project_id",
            "org_id",  # Added to base class
            "experiment_id",  # Added by ExperimentMigrator
        }

        assert migrator.excluded_fields_for_insert == expected_fields
        assert "experiment_id" in migrator.excluded_fields_for_insert

    async def test_function_migrator_excluded_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that FunctionMigrator includes log_id in excluded fields."""
        migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Should include all base fields plus log_id
        expected_fields = {
            "id",
            "created",
            "_xact_id",
            "xact_id",  # Alternative naming
            "_object_delete",
            "_pagination_key",
            "comparison_key",
            "project_id",
            "org_id",  # Added to base class
            "log_id",  # Added by FunctionMigrator
        }

        assert migrator.excluded_fields_for_insert == expected_fields
        assert "log_id" in migrator.excluded_fields_for_insert

    async def test_logs_migrator_excluded_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that LogsMigrator includes log_id in excluded fields."""
        migrator = LogsMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Should include all base fields plus log_id
        expected_fields = {
            "id",
            "created",
            "_xact_id",
            "xact_id",  # Alternative naming
            "_object_delete",
            "_pagination_key",
            "comparison_key",
            "project_id",
            "org_id",  # Added to base class
            "log_id",  # Added by LogsMigrator
        }

        assert migrator.excluded_fields_for_insert == expected_fields
        assert "log_id" in migrator.excluded_fields_for_insert

    async def test_excluded_fields_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that the overrides properly inherit from base class."""
        dataset_migrator = DatasetMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        experiment_migrator = ExperimentMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        function_migrator = FunctionMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )
        logs_migrator = LogsMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # All specialized migrators should include base fields
        base_fields = {
            "id",
            "created",
            "_xact_id",
            "xact_id",  # Alternative naming
            "_object_delete",
            "_pagination_key",
            "comparison_key",
            "project_id",
            "org_id",  # Added to base class
        }

        assert base_fields.issubset(dataset_migrator.excluded_fields_for_insert)
        assert base_fields.issubset(experiment_migrator.excluded_fields_for_insert)
        assert base_fields.issubset(function_migrator.excluded_fields_for_insert)
        assert base_fields.issubset(logs_migrator.excluded_fields_for_insert)

        # But each should have their specific additional field
        assert "dataset_id" in dataset_migrator.excluded_fields_for_insert
        assert "dataset_id" not in experiment_migrator.excluded_fields_for_insert
        assert "dataset_id" not in function_migrator.excluded_fields_for_insert
        assert "dataset_id" not in logs_migrator.excluded_fields_for_insert

        assert "experiment_id" in experiment_migrator.excluded_fields_for_insert
        assert "experiment_id" not in dataset_migrator.excluded_fields_for_insert
        assert "experiment_id" not in function_migrator.excluded_fields_for_insert
        assert "experiment_id" not in logs_migrator.excluded_fields_for_insert

        assert "log_id" in function_migrator.excluded_fields_for_insert
        assert "log_id" in logs_migrator.excluded_fields_for_insert
        assert "log_id" not in dataset_migrator.excluded_fields_for_insert
        assert "log_id" not in experiment_migrator.excluded_fields_for_insert
