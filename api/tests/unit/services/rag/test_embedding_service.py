"""
Unit tests for embedding_service module.

Tests automatic embedding generation for events, chat messages, and timeline entries.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import numpy as np

from app.services.rag.embedding_service import (
    generate_embeddings_for_events,
    generate_embedding_for_chat_message,
    generate_embedding_for_timeline_entry,
)


@pytest.mark.unit
class TestGenerateEmbeddingsForEvents:
    """Test generate_embeddings_for_events function."""

    async def test_empty_event_list(self):
        """
        Test that `generate_embeddings_for_events` correctly handles an empty list of event IDs by returning `0`; the test creates a mocked asynchronous database connection, generates a unique investigation identifier, invokes the function with no events, and verifies the returned count is zero.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        result = await generate_embeddings_for_events(
            db=db, investigation_id=investigation_id, event_ids=[], user_id=1
        )

        assert result == 0

    async def test_no_llm_config(self):
        """
        Test that generate_embeddings_for_events returns zero when there is no active LLM configuration. The function mocks a database session and patches get_active_llm_config to return None, then calls generate_embeddings_for_events with sample identifiers and asserts the result equals 0. This verifies proper handling of missing configuration without raising errors.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        with patch("app.services.rag.embedding_service.get_active_llm_config", return_value=None):
            result = await generate_embeddings_for_events(
                db=db, investigation_id=investigation_id, event_ids=[1, 2, 3], user_id=1
            )

            assert result == 0

    async def test_no_embedding_provider(self):
        """
        Test that the embedding generation process aborts and returns zero when no embedding provider is configured in the active LLM configuration. The test mocks a database connection, creates a random investigation ID, and patches the `get_active_llm_config` function to return a config object whose `embedding_provider` attribute is `None`. It then calls `generate_embeddings_for_events` with sample event IDs and verifies that the result equals zero, indicating that no embeddings were attempted.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock LLM config without embedding provider
        mock_config = MagicMock()
        mock_config.embedding_provider = None

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            result = await generate_embeddings_for_events(
                db=db, investigation_id=investigation_id, event_ids=[1, 2, 3], user_id=1
            )

            assert result == 0

    async def test_no_embedding_api_url(self):
        """
        Test that `generate_embeddings_for_events` returns zero when the active LLM configuration lacks an embedding API URL, ensuring the function gracefully handles missing configuration without attempting any embedding calls.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock LLM config without API URL
        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = None

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            result = await generate_embeddings_for_events(
                db=db, investigation_id=investigation_id, event_ids=[1, 2, 3], user_id=1
            )

            assert result == 0

    async def test_no_timeline_entries(self):
        """
        Test case verifying that the embedding generation process correctly handles events without any associated timeline entries. The test sets up an asynchronous mock database connection, configures a mock LLM provider (OpenAI), and ensures that querying for timeline entries returns an empty list. It then patches the function retrieving the active LLM configuration to return the mocked settings and calls `generate_embeddings_for_events` with sample identifiers. The assertion confirms that the function returns `0` when there are no timeline entries to process, indicating graceful handling of this edge case.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock LLM config
        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        # Mock empty timeline entries result
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute.return_value = result_mock

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            result = await generate_embeddings_for_events(
                db=db, investigation_id=investigation_id, event_ids=[1, 2, 3], user_id=1
            )

            assert result == 0

    async def test_generate_embeddings_success(self):
        """
        Test that embeddings are generated successfully for multiple events.

        This test mocks the database connection, LLM configuration, timeline query results, and the embedder to verify that
        `generate_embeddings_for_events` inserts the correct number of embedding records and returns the count of processed
        events.

        The mock setup includes:
        - An asynchronous database mock (`db`) with side-effects for fetching timeline entries and inserting embeddings.
        - A fake LLM configuration specifying OpenAI as the provider and required API details.
        - Timeline query results returning two events.
        - Pre-computed embedding vectors returned by a mocked `Embedder`.
        - Expected insertion result returning an identifier for each new embedding.

        The function under test is called with:
        - `db`: the mocked database connection.
        - `investigation_id`: a randomly generated UUID.
        - `event_ids`: a list containing the IDs of the two events.
        - `user_id`: the ID of the user performing the operation.

        The assertion checks that the returned value equals `2`, indicating that embeddings were created for both events.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock LLM config
        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        # Mock timeline entries
        timeline_result = MagicMock()
        timeline_result.fetchall.return_value = [
            (1, "Event 1", "Description 1"),
            (2, "Event 2", "Description 2"),
        ]

        # Mock embedding insertion results
        insert_result = MagicMock()
        insert_result.fetchone.return_value = (100,)  # embedding_id

        db.execute.side_effect = [
            timeline_result,
            insert_result,
            AsyncMock(),
            insert_result,
            AsyncMock(),
        ]

        # Mock embedder
        mock_embeddings = [np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])]

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.rag.embedding_service.Embedder") as mock_embedder_class:
                mock_embedder = AsyncMock()
                mock_embedder.embed.return_value = mock_embeddings
                mock_embedder_class.return_value = mock_embedder

                result = await generate_embeddings_for_events(
                    db=db, investigation_id=investigation_id, event_ids=[1, 2], user_id=1
                )

                assert result == 2

    async def test_handles_exception(self):
        """
        Test that the embedding generation process correctly handles exceptions by returning zero when an error occurs during the creation of the Embedder instance. The test sets up mock configuration values, patches the active LLM config retrieval to return these mocks, forces the Embedder constructor to raise an exception, invokes `generate_embeddings_for_events` with sample identifiers, and asserts that the function returns `0` indicating graceful failure handling.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            with patch(
                "app.services.rag.embedding_service.Embedder",
                side_effect=Exception("Embedder error"),
            ):
                result = await generate_embeddings_for_events(
                    db=db, investigation_id=investigation_id, event_ids=[1, 2], user_id=1
                )

                # Should return 0 on error
                assert result == 0


@pytest.mark.unit
class TestGenerateEmbeddingForChatMessage:
    """Test generate_embedding_for_chat_message function."""

    async def test_empty_content(self):
        """
        Test that generating an embedding for a chat message with an empty `content` string returns `None` without raising errors, using a mocked asynchronous database connection.
        """
        db = AsyncMock()

        result = await generate_embedding_for_chat_message(
            db=db, message_id=1, content="", user_id=1
        )

        assert result is None

    async def test_short_content(self):
        """
        Test that generate_embedding_for_chat_message returns None when provided with content shorter than the minimum required length.
        """
        db = AsyncMock()

        result = await generate_embedding_for_chat_message(
            db=db, message_id=1, content="short", user_id=1
        )

        assert result is None

    async def test_no_llm_config(self):
        """
        Test that generate_embedding_for_chat_message returns `None` when there is no active LLM configuration. The test mocks the database and patches `get_active_llm_config` to return `None`, then asserts the function under test yields a `None` result.
        """
        db = AsyncMock()

        with patch("app.services.rag.embedding_service.get_active_llm_config", return_value=None):
            result = await generate_embedding_for_chat_message(
                db=db, message_id=1, content="This is a test message", user_id=1
            )

            assert result is None

    async def test_no_embedding_provider(self):
        """
        Test that when no embedding provider is configured, the chat message embedding generation function returns `None` without raising an error. The test sets up a mock database and configuration where `embedding_provider` is `None`, patches the service to return this configuration, invokes `generate_embedding_for_chat_message` with sample inputs, and asserts that the result is `None`.
        """
        db = AsyncMock()

        mock_config = MagicMock()
        mock_config.embedding_provider = None

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            result = await generate_embedding_for_chat_message(
                db=db, message_id=1, content="This is a test message", user_id=1
            )

            assert result is None

    async def test_generate_embedding_success(self):
        """
        Test that a chat message embedding is generated successfully and stored in the database.

        This test mocks all external dependencies:
        - The active LLM configuration returned by `get_active_llm_config`.
        - The `Embedder` class used to compute embeddings.
        - The asynchronous database connection `db`.

        The mock embedder returns a deterministic NumPy array, and the mocked
        database cursor simulates an INSERT statement that yields an embedding ID
        of `100`. After invoking :func:`generate_embedding_for_chat_message` with
        sample inputs, the test asserts that the function returns the expected
        embedding identifier.
        """
        db = AsyncMock()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        # Mock embedding insertion
        insert_result = MagicMock()
        insert_result.fetchone.return_value = (100,)  # embedding_id
        db.execute.side_effect = [insert_result, AsyncMock()]

        mock_embedding = np.array([0.1, 0.2, 0.3])

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.rag.embedding_service.Embedder") as mock_embedder_class:
                mock_embedder = AsyncMock()
                mock_embedder.embed.return_value = [mock_embedding]
                mock_embedder_class.return_value = mock_embedder

                result = await generate_embedding_for_chat_message(
                    db=db, message_id=1, content="This is a test message", user_id=1
                )

                assert result == 100

    async def test_handles_exception(self):
        """
        Test that the embedding generation workflow correctly handles an exception raised by the Embedder class and returns `None`.\n\nThe test creates a mock asynchronous database session and a configuration object mimicking an OpenAI provider. It patches `get_active_llm_config` to return this mock config and forces `Embedder` to raise an `Exception` when instantiated. The function under test, `generate_embedding_for_chat_message`, is then invoked with sample parameters. The assertion verifies that the result is `None`, indicating that the exception was caught and handled gracefully.
        """
        db = AsyncMock()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            with patch(
                "app.services.rag.embedding_service.Embedder", side_effect=Exception("Error")
            ):
                result = await generate_embedding_for_chat_message(
                    db=db, message_id=1, content="This is a test message", user_id=1
                )

                assert result is None


@pytest.mark.unit
class TestGenerateEmbeddingForTimelineEntry:
    """Test generate_embedding_for_timeline_entry function."""

    async def test_short_content(self):
        """
        Test that generate_embedding_for_timeline_entry returns `None` when the provided content (title and description) is too short to produce an embedding. The database dependency is mocked, and the function is called with a minimal title and an empty description; the assertion verifies that no embedding is generated.
        """
        db = AsyncMock()

        result = await generate_embedding_for_timeline_entry(
            db=db, entry_id=1, title="Short", description="", user_id=1
        )

        assert result is None

    async def test_no_llm_config(self):
        """
        Test that generate_embedding_for_timeline_entry returns None when no active LLM configuration is found. The test mocks the database and patches get_active_llm_config to return None, then asserts the function under test yields a falsy result.
        """
        db = AsyncMock()

        with patch("app.services.rag.embedding_service.get_active_llm_config", return_value=None):
            result = await generate_embedding_for_timeline_entry(
                db=db, entry_id=1, title="Timeline Entry", description="Description", user_id=1
            )

            assert result is None

    async def test_generate_embedding_success(self):
        """
        Test that a successful embedding is generated and stored for a timeline entry.

        The test creates mock configuration values for an OpenAI embedding provider and patches the
        `get_active_llm_config` function to return this configuration.  It also mocks the `Embedder`
        class so its `embed` coroutine returns a predefined NumPy array representing the embedding.
        A mocked asynchronous database connection is set up with an `execute` side-effect that first
        returns a result containing an `embedding_id` of `200` and then completes without error.

        The function under test, :func:`generate_embedding_for_timeline_entry`, is called with sample
        title, description, entry ID, and user ID.  The test asserts that the returned value matches the
        expected embedding identifier (`200`), confirming that the embedding was generated,
        inserted into the database, and the correct ID was propagated.
        """
        db = AsyncMock()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        # Mock embedding insertion
        insert_result = MagicMock()
        insert_result.fetchone.return_value = (200,)  # embedding_id
        db.execute.side_effect = [insert_result, AsyncMock()]

        mock_embedding = np.array([0.1, 0.2, 0.3])

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.rag.embedding_service.Embedder") as mock_embedder_class:
                mock_embedder = AsyncMock()
                mock_embedder.embed.return_value = [mock_embedding]
                mock_embedder_class.return_value = mock_embedder

                result = await generate_embedding_for_timeline_entry(
                    db=db,
                    entry_id=1,
                    title="Important Event",
                    description="This is a significant finding",
                    user_id=1,
                )

                assert result == 200

    async def test_handles_none_description(self):
        """
        Test that generate_embedding_for_timeline_entry correctly handles a None description by using only the title, invoking the embedding provider, inserting the resulting embedding into the database, and returning the expected status code.
        """
        db = AsyncMock()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        insert_result = MagicMock()
        insert_result.fetchone.return_value = (200,)
        db.execute.side_effect = [insert_result, AsyncMock()]

        mock_embedding = np.array([0.1, 0.2, 0.3])

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            with patch("app.services.rag.embedding_service.Embedder") as mock_embedder_class:
                mock_embedder = AsyncMock()
                mock_embedder.embed.return_value = [mock_embedding]
                mock_embedder_class.return_value = mock_embedder

                result = await generate_embedding_for_timeline_entry(
                    db=db, entry_id=1, title="Important Event Title", description=None, user_id=1
                )

                # Should still succeed with just title
                assert result == 200

    async def test_handles_exception(self):
        """
        Test that the embedding generation function gracefully handles exceptions raised by the Embedder class and returns `None` when an error occurs during processing. The test mocks the active LLM configuration and forces `Embedder` to raise an exception, then verifies that `generate_embedding_for_timeline_entry` does not propagate the error and yields a `None` result.
        """
        db = AsyncMock()

        mock_config = MagicMock()
        mock_config.embedding_provider = "openai"
        mock_config.embedding_api_url = "https://api.openai.com/v1/embeddings"
        mock_config.embedding_api_key = "test-key"
        mock_config.embedding_model_name = "text-embedding-ada-002"

        with patch(
            "app.services.rag.embedding_service.get_active_llm_config", return_value=mock_config
        ):
            with patch(
                "app.services.rag.embedding_service.Embedder", side_effect=Exception("Error")
            ):
                result = await generate_embedding_for_timeline_entry(
                    db=db, entry_id=1, title="Important Event", description="Description", user_id=1
                )

                assert result is None
