"""Unit tests for RoleMigrator."""

from unittest.mock import Mock

import pytest
from braintrust_api.types import Role

from braintrust_migrate.resources.roles import RoleMigrator


@pytest.fixture
def role_with_inheritance():
    """Create a role that inherits from other roles."""
    role = Mock(spec=Role)
    role.id = "role-child-123"
    role.name = "Child Role"
    role.org_id = "org-456"
    role.user_id = "user-789"
    role.created = "2024-01-01T00:00:00Z"
    role.description = "A role that inherits from parent roles"
    role.deleted_at = None
    role.member_permissions = [{"permission": "read", "restrict_object_type": None}]
    role.member_roles = ["role-parent-1", "role-parent-2"]

    # Mock the to_dict method
    role.to_dict.return_value = {
        "id": "role-child-123",
        "name": "Child Role",
        "org_id": "org-456",
        "user_id": "user-789",
        "created": "2024-01-01T00:00:00Z",
        "description": "A role that inherits from parent roles",
        "deleted_at": None,
        "member_permissions": [{"permission": "read", "restrict_object_type": None}],
        "member_roles": ["role-parent-1", "role-parent-2"],
    }

    return role


@pytest.fixture
def role_without_inheritance():
    """Create a role without inheritance dependencies."""
    role = Mock(spec=Role)
    role.id = "role-independent-456"
    role.name = "Independent Role"
    role.org_id = "org-456"
    role.user_id = "user-789"
    role.created = "2024-01-01T00:00:00Z"
    role.description = "A role without inheritance"
    role.deleted_at = None
    role.member_permissions = [
        {"permission": "create", "restrict_object_type": "project"},
        {"permission": "update", "restrict_object_type": "experiment"},
    ]
    role.member_roles = None

    # Mock the to_dict method
    role.to_dict.return_value = {
        "id": "role-independent-456",
        "name": "Independent Role",
        "org_id": "org-456",
        "user_id": "user-789",
        "created": "2024-01-01T00:00:00Z",
        "description": "A role without inheritance",
        "deleted_at": None,
        "member_permissions": [
            {"permission": "create", "restrict_object_type": "project"},
            {"permission": "update", "restrict_object_type": "experiment"},
        ],
        "member_roles": None,
    }

    return role


@pytest.mark.asyncio
class TestRoleMigrator:
    """Test RoleMigrator functionality."""

    async def test_resource_name(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test that resource_name returns correct value."""
        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        assert migrator.resource_name == "Roles"

    async def test_get_resource_id(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_role,
    ):
        """Test extracting resource ID from role."""
        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        resource_id = migrator.get_resource_id(sample_role)

        assert resource_id == "role-123"

    async def test_get_dependencies_with_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        role_with_inheritance,
    ):
        """Test that roles with member_roles return correct dependencies."""
        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(role_with_inheritance)

        assert dependencies == ["role-parent-1", "role-parent-2"]

    async def test_get_dependencies_without_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        role_without_inheritance,
    ):
        """Test that roles without member_roles return no dependencies."""
        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        dependencies = await migrator.get_dependencies(role_without_inheritance)

        assert dependencies == []

    async def test_list_source_resources_success(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_role,
    ):
        """Test successful listing of source roles."""
        # Mock paginated response
        mock_response = Mock()
        mock_response.objects = [sample_role]
        mock_source_client.with_retry.return_value = mock_response

        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        roles = await migrator.list_source_resources()

        assert len(roles) == 1
        assert roles[0] == sample_role
        mock_source_client.with_retry.assert_called_once()

    async def test_list_source_resources_async_iterator(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_role,
    ):
        """Test listing source roles with async iterator response."""

        # Mock async iterator response
        async def async_iter():
            yield sample_role

        mock_response = async_iter()
        mock_source_client.with_retry.return_value = mock_response

        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        roles = await migrator.list_source_resources()

        assert len(roles) == 1
        assert roles[0] == sample_role

    async def test_list_source_resources_direct_list(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_role,
    ):
        """Test listing source roles with direct list response."""
        mock_source_client.with_retry.return_value = [sample_role]

        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        roles = await migrator.list_source_resources()

        assert len(roles) == 1
        assert roles[0] == sample_role

    async def test_list_source_resources_error(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test error handling in list_source_resources."""
        mock_source_client.with_retry.side_effect = Exception("API Error")

        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        with pytest.raises(Exception, match="API Error"):
            await migrator.list_source_resources()

    async def test_migrate_resource_success_full_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_role,
    ):
        """Test successful role migration with all fields."""
        # Mock successful role creation
        created_role = Mock(spec=Role)
        created_role.id = "dest-role-123"
        created_role.name = "Test Role"
        mock_dest_client.with_retry.return_value = created_role

        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.migrate_resource(sample_role)

        assert result == "dest-role-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_success_minimal_fields(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
    ):
        """Test successful role migration with minimal fields."""
        # Create role with minimal fields
        minimal_role = Mock(spec=Role)
        minimal_role.id = "role-minimal-123"
        minimal_role.name = "Minimal Role"
        minimal_role.description = None
        minimal_role.member_permissions = None
        minimal_role.member_roles = None

        # Mock the to_dict method
        minimal_role.to_dict.return_value = {
            "id": "role-minimal-123",
            "name": "Minimal Role",
            "description": None,
            "member_permissions": None,
            "member_roles": None,
        }

        # Mock successful role creation
        created_role = Mock(spec=Role)
        created_role.id = "dest-role-minimal-123"
        created_role.name = "Minimal Role"
        mock_dest_client.with_retry.return_value = created_role

        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        result = await migrator.migrate_resource(minimal_role)

        assert result == "dest-role-minimal-123"

    async def test_migrate_resource_with_resolved_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        role_with_inheritance,
    ):
        """Test migrating role with resolved inheritance dependencies."""
        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # Set up ID mapping for parent roles
        migrator.state.id_mapping["role-parent-1"] = "dest-role-parent-1"
        migrator.state.id_mapping["role-parent-2"] = "dest-role-parent-2"

        # Mock successful role creation
        created_role = Mock(spec=Role)
        created_role.id = "dest-role-child-123"
        created_role.name = "Child Role"
        mock_dest_client.with_retry.return_value = created_role

        result = await migrator.migrate_resource(role_with_inheritance)

        assert result == "dest-role-child-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_with_unresolved_inheritance(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        role_with_inheritance,
    ):
        """Test migrating role with unresolved inheritance dependencies."""
        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        # No ID mapping set up - dependencies unresolved

        # Mock successful role creation (should still work, just without member_roles)
        created_role = Mock(spec=Role)
        created_role.id = "dest-role-child-123"
        created_role.name = "Child Role"
        mock_dest_client.with_retry.return_value = created_role

        result = await migrator.migrate_resource(role_with_inheritance)

        assert result == "dest-role-child-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_creation_error(
        self,
        mock_source_client,
        mock_dest_client,
        temp_checkpoint_dir,
        sample_role,
    ):
        """Test error handling during role creation."""
        mock_dest_client.with_retry.side_effect = Exception("Creation failed")

        migrator = RoleMigrator(
            mock_source_client, mock_dest_client, temp_checkpoint_dir
        )

        with pytest.raises(Exception, match="Creation failed"):
            await migrator.migrate_resource(sample_role)
