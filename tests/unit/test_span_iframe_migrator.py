"""Tests for SpanIframeMigrator."""

import pytest
from braintrust_api.types.shared.span_i_frame import SpanIFrame

from braintrust_migrate.resources.span_iframes import SpanIframeMigrator
from tests.conftest import TEST_DEST_PROJECT_ID


@pytest.fixture
def span_iframe_migrator(mock_source_client, mock_dest_client, temp_checkpoint_dir):
    """Create a SpanIframeMigrator instance for testing."""
    migrator = SpanIframeMigrator(
        source_client=mock_source_client,
        dest_client=mock_dest_client,
        checkpoint_dir=temp_checkpoint_dir,
        batch_size=10,
    )
    migrator.set_destination_project_id(TEST_DEST_PROJECT_ID)
    return migrator


@pytest.mark.asyncio
class TestSpanIframeMigrator:
    """Test the SpanIframeMigrator class."""

    async def test_resource_name(self, span_iframe_migrator):
        """Test the resource_name property."""
        assert span_iframe_migrator.resource_name == "SpanIframes"

    async def test_list_source_resources_all(
        self, span_iframe_migrator, mock_source_client, sample_span_iframe
    ):
        """Test listing all span iframes from source."""
        # Mock the API response
        mock_source_client.with_retry.return_value = [sample_span_iframe]

        result = await span_iframe_migrator.list_source_resources()

        assert len(result) == 1
        assert result[0] == sample_span_iframe
        mock_source_client.with_retry.assert_called_once()

    async def test_list_source_resources_filtered_by_project(
        self, span_iframe_migrator, mock_source_client
    ):
        """Test listing span iframes filtered by project ID."""
        # Create span iframes for different projects
        iframe1 = SpanIFrame(
            id="iframe-1",
            project_id="project-456",
            name="Iframe 1",
            url="https://example.com/iframe1",
        )
        iframe2 = SpanIFrame(
            id="iframe-2",
            project_id="other-project",
            name="Iframe 2",
            url="https://example.com/iframe2",
        )

        mock_source_client.with_retry.return_value = [iframe1, iframe2]

        result = await span_iframe_migrator.list_source_resources(
            project_id="project-456"
        )

        assert len(result) == 1
        assert result[0].id == "iframe-1"
        assert result[0].project_id == "project-456"

    async def test_list_source_resources_async_iterator(
        self, span_iframe_migrator, mock_source_client, sample_span_iframe
    ):
        """Test listing span iframes when API returns async iterator."""

        # Mock async iterator
        class AsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        mock_response = AsyncIterator([sample_span_iframe])
        mock_source_client.with_retry.return_value = mock_response

        result = await span_iframe_migrator.list_source_resources()

        assert len(result) == 1
        assert result[0] == sample_span_iframe

    async def test_list_source_resources_error(
        self, span_iframe_migrator, mock_source_client
    ):
        """Test error handling when listing source span iframes fails."""
        mock_source_client.with_retry.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            await span_iframe_migrator.list_source_resources()

    async def test_get_resource_id(self, span_iframe_migrator, sample_span_iframe):
        """Test extracting resource ID."""
        resource_id = span_iframe_migrator.get_resource_id(sample_span_iframe)
        assert resource_id == "span-iframe-123"

    async def test_resource_exists_in_dest_found(
        self, span_iframe_migrator, mock_dest_client, sample_span_iframe
    ):
        """Test checking if span iframe exists in destination - found."""
        # Mock existing span iframe in destination
        dest_iframe = SpanIFrame(
            id="dest-iframe-123",
            project_id=TEST_DEST_PROJECT_ID,
            name="Test Span Iframe",
            url="https://dest.example.com/iframe",
        )
        mock_dest_client.with_retry.return_value = [dest_iframe]

        result = await span_iframe_migrator.resource_exists_in_dest(sample_span_iframe)

        assert result == "dest-iframe-123"
        mock_dest_client.with_retry.assert_called_once()

    async def test_resource_exists_in_dest_not_found(
        self, span_iframe_migrator, mock_dest_client, sample_span_iframe
    ):
        """Test checking if span iframe exists in destination - not found."""
        mock_dest_client.with_retry.return_value = []

        result = await span_iframe_migrator.resource_exists_in_dest(sample_span_iframe)

        assert result is None

    async def test_resource_exists_in_dest_different_project(
        self, span_iframe_migrator, mock_dest_client, sample_span_iframe
    ):
        """Test checking if span iframe exists but in different project."""
        # Mock span iframe with same name but different project
        dest_iframe = SpanIFrame(
            id="dest-iframe-123",
            project_id="other-project-789",
            name="Test Span Iframe",
            url="https://dest.example.com/iframe",
        )
        mock_dest_client.with_retry.return_value = [dest_iframe]

        result = await span_iframe_migrator.resource_exists_in_dest(sample_span_iframe)

        assert result is None

    async def test_resource_exists_in_dest_async_iterator(
        self, span_iframe_migrator, mock_dest_client, sample_span_iframe
    ):
        """Test checking existence when API returns async iterator."""
        dest_iframe = SpanIFrame(
            id="dest-iframe-123",
            project_id=TEST_DEST_PROJECT_ID,
            name="Test Span Iframe",
            url="https://dest.example.com/iframe",
        )

        class AsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        mock_response = AsyncIterator([dest_iframe])
        mock_dest_client.with_retry.return_value = mock_response

        result = await span_iframe_migrator.resource_exists_in_dest(sample_span_iframe)

        assert result == "dest-iframe-123"

    async def test_resource_exists_in_dest_error(
        self, span_iframe_migrator, mock_dest_client, sample_span_iframe
    ):
        """Test error handling when checking if span iframe exists."""
        mock_dest_client.with_retry.side_effect = Exception("API Error")

        result = await span_iframe_migrator.resource_exists_in_dest(sample_span_iframe)

        assert result is None

    async def test_migrate_resource_full(
        self, span_iframe_migrator, mock_dest_client, sample_span_iframe
    ):
        """Test migrating a span iframe with all fields."""
        # Mock successful creation
        dest_iframe = SpanIFrame(
            id="dest-iframe-123",
            project_id=TEST_DEST_PROJECT_ID,
            name="Test Span Iframe",
            url="https://example.com/iframe",
            description="A test span iframe",
            post_message=True,
        )
        mock_dest_client.with_retry.return_value = dest_iframe

        result = await span_iframe_migrator.migrate_resource(sample_span_iframe)

        assert result == "dest-iframe-123"
        mock_dest_client.with_retry.assert_called_once()

        # Verify create parameters
        call_args = mock_dest_client.with_retry.call_args
        assert call_args[0][0] == "create_span_iframe"

    async def test_migrate_resource_minimal(
        self, span_iframe_migrator, mock_dest_client
    ):
        """Test migrating a span iframe with minimal fields."""
        # Create minimal span iframe
        minimal_iframe = SpanIFrame(
            id="span-iframe-123",
            project_id="project-456",
            name="Minimal Iframe",
            url="https://example.com/minimal",
        )

        dest_iframe = SpanIFrame(
            id="dest-iframe-123",
            project_id=TEST_DEST_PROJECT_ID,
            name="Minimal Iframe",
            url="https://example.com/minimal",
        )
        mock_dest_client.with_retry.return_value = dest_iframe

        result = await span_iframe_migrator.migrate_resource(minimal_iframe)

        assert result == "dest-iframe-123"

    async def test_migrate_resource_error(
        self, span_iframe_migrator, mock_dest_client, sample_span_iframe
    ):
        """Test error handling when migrating span iframe fails."""
        mock_dest_client.with_retry.side_effect = Exception("Creation failed")

        with pytest.raises(Exception, match="Creation failed"):
            await span_iframe_migrator.migrate_resource(sample_span_iframe)

    async def test_get_dependencies(self, span_iframe_migrator, sample_span_iframe):
        """Test getting dependencies for a span iframe."""
        dependencies = await span_iframe_migrator.get_dependencies(sample_span_iframe)
        assert dependencies == []

    async def test_migrate_resource_preserves_optional_fields(
        self, span_iframe_migrator, mock_dest_client
    ):
        """Test that optional fields are preserved during migration."""
        # Create span iframe with optional fields
        iframe_with_options = SpanIFrame(
            id="span-iframe-123",
            project_id="project-456",
            name="Test Iframe",
            url="https://example.com/iframe",
            description="Test description",
            post_message=False,  # Explicitly False
        )

        dest_iframe = SpanIFrame(
            id="dest-iframe-123",
            project_id=TEST_DEST_PROJECT_ID,
            name="Test Iframe",
            url="https://example.com/iframe",
            description="Test description",
            post_message=False,
        )
        mock_dest_client.with_retry.return_value = dest_iframe

        await span_iframe_migrator.migrate_resource(iframe_with_options)

        # Verify the create call was made with correct parameters
        mock_dest_client.with_retry.assert_called_once()

    async def test_migrate_resource_skips_none_optional_fields(
        self, span_iframe_migrator, mock_dest_client
    ):
        """Test that None optional fields are not included in create params."""
        # Create span iframe with None optional fields
        iframe_minimal = SpanIFrame(
            id="span-iframe-123",
            project_id="project-456",
            name="Test Iframe",
            url="https://example.com/iframe",
            description=None,
            post_message=None,
        )

        dest_iframe = SpanIFrame(
            id="dest-iframe-123",
            project_id=TEST_DEST_PROJECT_ID,
            name="Test Iframe",
            url="https://example.com/iframe",
        )
        mock_dest_client.with_retry.return_value = dest_iframe

        await span_iframe_migrator.migrate_resource(iframe_minimal)

        mock_dest_client.with_retry.assert_called_once()
