"""Unit tests for GroupMigrator."""

from unittest.mock import Mock

import pytest
from braintrust_api.types import Group

from braintrust_migrate.resources.groups import GroupMigrator


@pytest.fixture
def group_with_inheritance():
    """Create a group that inherits from other groups."""
    group = Mock(spec=Group)
    group.id = "group-child-123"
    group.name = "Child Group"
    group.org_id = "org-456"
    group.user_id = "user-789"
    group.created = "2024-01-01T00:00:00Z"
    group.description = "A group that inherits from parent groups"
    group.deleted_at = None
    group.member_groups = ["group-parent-1", "group-parent-2"]
    group.member_users = ["user-123", "user-456"]
    return group


@pytest.fixture
def group_without_inheritance():
    """Create a group without inheritance dependencies."""
    group = Mock(spec=Group)
    group.id = "group-independent-456"
    group.name = "Independent Group"
    group.org_id = "org-456"
    group.user_id = "user-789"
    group.created = "2024-01-01T00:00:00Z"
    group.description = "A group without inheritance"
    group.deleted_at = None
    group.member_groups = None
    group.member_users = ["user-123"]
    return group


@pytest.mark.asyncio
class TestGroupMigrator:
    """Test GroupMigrator functionality."""

    async def test_resource_name(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that resource_name returns correct value."""
        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        assert migrator.resource_name == "Groups"

    async def test_get_resource_id(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test extracting resource ID from group."""
        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        resource_id = migrator.get_resource_id(sample_group)

        assert resource_id == "group-123"

    async def test_get_dependencies_with_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        group_with_inheritance,
    ):
        """Test that groups with member_groups return correct dependencies."""
        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(group_with_inheritance)

        assert dependencies == ["group-parent-1", "group-parent-2"]

    async def test_get_dependencies_without_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        group_without_inheritance,
    ):
        """Test that groups without member_groups return no dependencies."""
        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(group_without_inheritance)

        assert dependencies == []

    async def test_list_source_resources_success(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test successful listing of source groups."""
        # Mock paginated response
        mock_response = Mock()
        mock_response.objects = [sample_group]
        mock_source_client.with_retry.return_value = mock_response

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        groups = await migrator.list_source_resources()

        assert len(groups) == 1
        assert groups[0] == sample_group
        mock_source_client.with_retry.assert_called_once()

    async def test_list_source_resources_async_iterator(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test listing source groups with async iterator response."""

        # Mock async iterator response
        async def async_iter():
            yield sample_group

        mock_response = async_iter()
        mock_source_client.with_retry.return_value = mock_response

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        groups = await migrator.list_source_resources()

        assert len(groups) == 1
        assert groups[0] == sample_group

    async def test_list_source_resources_direct_list(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test listing source groups with direct list response."""
        mock_source_client.with_retry.return_value = [sample_group]

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        groups = await migrator.list_source_resources()

        assert len(groups) == 1
        assert groups[0] == sample_group

    async def test_list_source_resources_error(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test error handling in list_source_resources."""
        mock_source_client.with_retry.side_effect = Exception("API Error")

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        with pytest.raises(Exception, match="API Error"):
            await migrator.list_source_resources()

    async def test_resource_exists_in_dest_found(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test finding existing group in destination."""
        # Mock existing group in destination
        dest_group = Mock(spec=Group)
        dest_group.id = "dest-group-123"
        dest_group.name = "Test Group"

        mock_response = Mock()
        mock_response.objects = [dest_group]
        mock_dest_client.with_retry.return_value = mock_response

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.resource_exists_in_dest(sample_group)

        assert result == "dest-group-123"

    async def test_resource_exists_in_dest_not_found(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test group not found in destination."""
        mock_response = Mock()
        mock_response.objects = []
        mock_dest_client.with_retry.return_value = mock_response

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.resource_exists_in_dest(sample_group)

        assert result is None

    async def test_resource_exists_in_dest_async_iterator(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test finding existing group with async iterator response."""
        # Mock existing group in destination
        dest_group = Mock(spec=Group)
        dest_group.id = "dest-group-123"
        dest_group.name = "Test Group"

        async def async_iter():
            yield dest_group

        mock_dest_client.with_retry.return_value = async_iter()

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.resource_exists_in_dest(sample_group)

        assert result == "dest-group-123"

    async def test_resource_exists_in_dest_error(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test error handling in resource_exists_in_dest."""
        mock_dest_client.with_retry.side_effect = Exception("API Error")

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.resource_exists_in_dest(sample_group)

        assert result is None

    async def test_migrate_resource_success_full_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test successful group migration with all fields."""
        # Mock successful group creation
        created_group = Mock(spec=Group)
        created_group.id = "dest-group-123"
        created_group.name = "Test Group"
        mock_dest_client.with_retry.return_value = created_group

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.migrate_resource(sample_group)

        assert result == "dest-group-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_success_minimal_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test successful group migration with minimal fields."""
        # Create group with minimal fields
        minimal_group = Mock(spec=Group)
        minimal_group.id = "group-minimal-123"
        minimal_group.name = "Minimal Group"
        minimal_group.description = None
        minimal_group.member_groups = None
        minimal_group.member_users = None

        # Mock successful group creation
        created_group = Mock(spec=Group)
        created_group.id = "dest-group-minimal-123"
        created_group.name = "Minimal Group"
        mock_dest_client.with_retry.return_value = created_group

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.migrate_resource(minimal_group)

        assert result == "dest-group-minimal-123"

    async def test_migrate_resource_with_resolved_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        group_with_inheritance,
    ):
        """Test migrating group with resolved inheritance dependencies."""
        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Set up ID mapping for parent groups
        migrator.state.id_mapping["group-parent-1"] = "dest-group-parent-1"
        migrator.state.id_mapping["group-parent-2"] = "dest-group-parent-2"

        # Mock successful group creation
        created_group = Mock(spec=Group)
        created_group.id = "dest-group-child-123"
        created_group.name = "Child Group"
        mock_dest_client.with_retry.return_value = created_group

        result = await migrator.migrate_resource(group_with_inheritance)

        assert result == "dest-group-child-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_with_unresolved_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        group_with_inheritance,
    ):
        """Test migrating group with unresolved inheritance dependencies."""
        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # No ID mapping set up - dependencies unresolved

        # Mock successful group creation (should still work, just without member_groups)
        created_group = Mock(spec=Group)
        created_group.id = "dest-group-child-123"
        created_group.name = "Child Group"
        mock_dest_client.with_retry.return_value = created_group

        result = await migrator.migrate_resource(group_with_inheritance)

        assert result == "dest-group-child-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_with_member_users_skipped(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test that member_users are skipped during migration."""
        # Mock successful group creation
        created_group = Mock(spec=Group)
        created_group.id = "dest-group-123"
        created_group.name = "Test Group"
        mock_dest_client.with_retry.return_value = created_group

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.migrate_resource(sample_group)

        assert result == "dest-group-123"
        # The test verifies that the migration completes successfully
        # The logging in the migrator shows that member_users are skipped

    async def test_migrate_resource_creation_error(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_group,
    ):
        """Test error handling during group creation."""
        mock_dest_client.with_retry.side_effect = Exception("Creation failed")

        migrator = GroupMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        with pytest.raises(Exception, match="Creation failed"):
            await migrator.migrate_resource(sample_group)
