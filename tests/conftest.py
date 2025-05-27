"""Shared pytest fixtures for the migration tool tests."""

from unittest.mock import AsyncMock, Mock

import pytest
from braintrust_api import AsyncBraintrust
from braintrust_api.types import (
    ACL,
    Dataset,
    Experiment,
    Group,
    Project,
    ProjectScore,
    ProjectTag,
    Prompt,
    Role,
    SpanIFrame,
    View,
)

from braintrust_migrate.config import BraintrustOrgConfig, MigrationConfig


@pytest.fixture
def org_config():
    """Create a test organization configuration."""
    return BraintrustOrgConfig(
        api_key="test-api-key", url="https://test.braintrust.dev"
    )


@pytest.fixture
def migration_config():
    """Create a test migration configuration."""
    return MigrationConfig(
        batch_size=50,
        retry_attempts=3,
        retry_delay=1.0,
        max_concurrent=10,
        checkpoint_interval=50,
    )


@pytest.fixture
def mock_source_client():
    """Create a mock source client with common API endpoints."""
    client = Mock()
    client.with_retry = AsyncMock()

    # Mock the underlying braintrust client
    client.client = Mock(spec=AsyncBraintrust)
    client.client.projects = Mock()
    client.client.projects.list = AsyncMock()
    client.client.datasets = Mock()
    client.client.datasets.list = AsyncMock()
    client.client.experiments = Mock()
    client.client.experiments.list = AsyncMock()
    client.client.prompts = Mock()
    client.client.prompts.list = AsyncMock()
    client.client.functions = Mock()
    client.client.functions.list = AsyncMock()
    client.client.roles = Mock()
    client.client.roles.list = AsyncMock()
    client.client.groups = Mock()
    client.client.groups.list = AsyncMock()
    client.client.acls = Mock()
    client.client.acls.list_org = AsyncMock()
    client.client.span_iframes = Mock()
    client.client.span_iframes.list = AsyncMock()
    client.client.views = Mock()
    client.client.views.list = AsyncMock()
    client.client.logs = Mock()
    client.client.logs.list = AsyncMock()
    client.client.project_tags = Mock()
    client.client.project_tags.list = AsyncMock()
    client.client.project_tags.create = AsyncMock()
    client.client.project_scores = Mock()
    client.client.project_scores.list = AsyncMock()

    return client


@pytest.fixture
def mock_dest_client():
    """Create a mock destination client with common API endpoints."""
    client = Mock()
    client.with_retry = AsyncMock()

    # Mock the underlying braintrust client
    client.client = Mock(spec=AsyncBraintrust)
    client.client.projects = Mock()
    client.client.projects.list = AsyncMock()
    client.client.projects.create = AsyncMock()
    client.client.datasets = Mock()
    client.client.datasets.list = AsyncMock()
    client.client.datasets.create = AsyncMock()
    client.client.experiments = Mock()
    client.client.experiments.list = AsyncMock()
    client.client.experiments.create = AsyncMock()
    client.client.prompts = Mock()
    client.client.prompts.list = AsyncMock()
    client.client.prompts.create = AsyncMock()
    client.client.functions = Mock()
    client.client.functions.list = AsyncMock()
    client.client.functions.create = AsyncMock()
    client.client.roles = Mock()
    client.client.roles.list = AsyncMock()
    client.client.roles.create = AsyncMock()
    client.client.groups = Mock()
    client.client.groups.list = AsyncMock()
    client.client.groups.create = AsyncMock()
    client.client.acls = Mock()
    client.client.acls.list_org = AsyncMock()
    client.client.acls.create = AsyncMock()
    client.client.span_iframes = Mock()
    client.client.span_iframes.list = AsyncMock()
    client.client.span_iframes.create = AsyncMock()
    client.client.views = Mock()
    client.client.views.list = AsyncMock()
    client.client.views.create = AsyncMock()
    client.client.logs = Mock()
    client.client.logs.list = AsyncMock()
    client.client.logs.create = AsyncMock()
    client.client.project_tags = Mock()
    client.client.project_tags.list = AsyncMock()
    client.client.project_tags.create = AsyncMock()
    client.client.project_scores = Mock()
    client.client.project_scores.list = AsyncMock()
    client.client.project_scores.create = AsyncMock()

    return client


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Create a temporary checkpoint directory for testing."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir


@pytest.fixture
def sample_project():
    """Create a sample Project for testing."""
    return Project(
        id="project-123",
        name="Test Project",
        description="A test project",
        user_id="user-456",
        created="2024-01-01T00:00:00Z",
        deleted_at=None,
    )


@pytest.fixture
def sample_dataset():
    """Create a sample Dataset for testing."""
    return Dataset(
        id="dataset-123",
        project_id="project-456",
        name="Test Dataset",
        description="A test dataset",
        user_id="user-789",
        created="2024-01-01T00:00:00Z",
        deleted_at=None,
    )


@pytest.fixture
def sample_experiment():
    """Create a sample Experiment for testing."""
    return Experiment(
        id="experiment-123",
        project_id="project-456",
        name="Test Experiment",
        description="A test experiment",
        user_id="user-789",
        created="2024-01-01T00:00:00Z",
        deleted_at=None,
    )


@pytest.fixture
def sample_prompt():
    """Create a sample Prompt for testing."""
    return Prompt(
        id="prompt-123",
        project_id="project-456",
        name="Test Prompt",
        description="A test prompt",
        prompt_data={"prompt": "Hello, world!"},
        user_id="user-789",
        created="2024-01-01T00:00:00Z",
        deleted_at=None,
    )


@pytest.fixture
def sample_span_iframe():
    """Create a sample SpanIFrame for testing."""
    return SpanIFrame(
        id="span-iframe-123",
        project_id="project-456",
        name="Test Span Iframe",
        url="https://example.com/iframe",
        description="A test span iframe",
        post_message=True,
        user_id="user-789",
        created="2024-01-01T00:00:00Z",
        deleted_at=None,
    )


@pytest.fixture
def sample_view():
    """Create a sample View for testing."""
    return View(
        id="view-123",
        project_id="project-456",
        name="Test View",
        description="A test view",
        view_type="project",
        object_type="project",
        object_id="project-456",
        user_id="user-789",
        created="2024-01-01T00:00:00Z",
        deleted_at=None,
    )


@pytest.fixture
def sample_project_tag():
    """Create a sample project tag for testing."""
    project_tag = Mock(spec=ProjectTag)
    project_tag.id = "tag-123"
    project_tag.name = "Test Tag"
    project_tag.project_id = "project-456"
    project_tag.user_id = "user-789"
    project_tag.created = "2024-01-01T00:00:00Z"
    project_tag.description = "A test project tag"
    project_tag.color = "#FF0000"
    return project_tag


@pytest.fixture
def sample_role():
    """Create a sample role for testing."""
    role = Mock(spec=Role)
    role.id = "role-123"
    role.name = "Test Role"
    role.org_id = "org-456"
    role.user_id = "user-789"
    role.created = "2024-01-01T00:00:00Z"
    role.description = "A test role"
    role.deleted_at = None
    role.member_permissions = [
        {"permission": "read", "restrict_object_type": None},
        {"permission": "create", "restrict_object_type": "project"},
    ]
    role.member_roles = None
    return role


@pytest.fixture
def sample_group():
    """Create a sample group for testing."""
    group = Mock(spec=Group)
    group.id = "group-123"
    group.name = "Test Group"
    group.org_id = "org-456"
    group.user_id = "user-789"
    group.created = "2024-01-01T00:00:00Z"
    group.description = "A test group"
    group.deleted_at = None
    group.member_groups = None
    group.member_users = ["user-123", "user-456"]
    return group


@pytest.fixture
def sample_acl():
    """Create a sample ACL for testing."""
    acl = Mock(spec=ACL)
    acl.id = "acl-123"
    acl.object_type = "project"
    acl.object_id = "project-456"
    acl.group_id = "group-789"
    acl.user_id = None
    acl.permission = "read"
    acl.role_id = None
    acl.restrict_object_type = None
    acl.object_org_id = "org-456"
    acl.created = "2024-01-01T00:00:00Z"
    return acl


@pytest.fixture
def sample_project_score():
    """Create a sample project score for testing."""
    project_score = Mock(spec=ProjectScore)
    project_score.id = "score-123"
    project_score.name = "Test Score"
    project_score.project_id = "project-456"
    project_score.user_id = "user-789"
    project_score.created = "2024-01-01T00:00:00Z"
    project_score.description = "A test project score"
    project_score.score_type = "slider"
    project_score.categories = None
    project_score.config = None
    project_score.position = None
    return project_score


# Test constants that can be reused across tests
TEST_PROJECT_ID = "test-project-123"
TEST_DEST_PROJECT_ID = "dest-project-456"
TEST_USER_ID = "test-user-789"
TEST_BATCH_SIZE = 10
