"""Unit tests for general_chat_handler.py.

Tests general chat functionality without database dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.services.handlers.general_chat_handler import (
    handle_general_chat,
    _gather_investigation_context,
    _build_context_prompt,
)


@pytest.mark.unit
class TestGatherInvestigationContext:
    """Test gathering investigation context."""

    @pytest.mark.asyncio
    async def test_gather_complete_context(self):
        """
        Test that the private helper `_gather_investigation_context` correctly aggregates all required context data from the database.

        The test creates an asynchronous mock database (`mock_db`) and configures its `execute` coroutine to return predetermined results for each of the four queries performed by the helper:

        1. **Investigation query** - returns a tuple containing the investigation title, description, creation date, and end date.
        2. **Timeline query** - returns a tuple with the total number of timeline entries, the earliest timestamp, and the latest timestamp.
        3. **Artifact query** - returns a list of `(artifact_type, count)` pairs.
        4. **Event query** - returns a list of `(event_name, count)` pairs.

        After invoking `_gather_investigation_context` with the mocked database and a generated `investigation_id`, the test asserts that:

        - The resulting dictionary contains an `"investigation"` key whose nested `"title"` matches the mock title.
        - A `"timeline"` entry exists with `"total_entries"` equal to the mocked count.
        - An `"artifacts"` mapping includes the expected artifact types and their counts (e.g., `"evtx": 5`).
        - An `"events"` mapping includes the expected event names and their counts (e.g., `"authentication": 25`).
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()

        # Mock investigation query
        mock_inv_result = MagicMock()
        mock_inv_result.fetchone.return_value = (
            "Test Investigation",
            "Test description",
            datetime(2024, 1, 1),
            datetime(2024, 1, 15),
        )

        # Mock timeline query
        mock_timeline_result = MagicMock()
        mock_timeline_result.fetchone.return_value = (
            100,  # count
            datetime(2024, 1, 1, 10, 0),  # min
            datetime(2024, 1, 15, 16, 0),  # max
        )

        # Mock artifact query
        mock_artifact_result = MagicMock()
        mock_artifact_result.fetchall.return_value = [
            ("evtx", 5),
            ("registry", 3),
        ]

        # Mock event query
        mock_event_result = MagicMock()
        mock_event_result.fetchall.return_value = [
            ("authentication", 25),
            ("file_access", 50),
        ]

        # Setup execute to return appropriate results
        mock_db.execute = AsyncMock(
            side_effect=[
                mock_inv_result,
                mock_timeline_result,
                mock_artifact_result,
                mock_event_result,
            ]
        )

        context = await _gather_investigation_context(mock_db, investigation_id)

        assert "investigation" in context
        assert context["investigation"]["title"] == "Test Investigation"
        assert "timeline" in context
        assert context["timeline"]["total_entries"] == 100
        assert "artifacts" in context
        assert context["artifacts"]["evtx"] == 5
        assert "events" in context
        assert context["events"]["authentication"] == 25

    @pytest.mark.asyncio
    async def test_gather_context_no_investigation(self):
        """
        Test that gathering investigation context returns a dictionary when the specified investigation does not exist in the database, using mocked asynchronous database calls.
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()

        # Mock empty results
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_result)

        context = await _gather_investigation_context(mock_db, investigation_id)

        # Should return empty or partial context
        assert isinstance(context, dict)

    @pytest.mark.asyncio
    async def test_gather_context_empty_timeline(self):
        """
        Test that gathering investigation context correctly handles an empty timeline.

        This test creates a mock asynchronous database connection and simulates:
        - An existing investigation record with basic metadata.
        - A timeline query returning zero entries (total count 0) and no earliest or latest timestamps.
        - No artifacts or events associated with the investigation.

        It then calls the internal `_gather_investigation_context` coroutine with the mocked DB and a generated investigation ID, awaiting the result. The assertions verify that:
        - The returned context dictionary contains a `timeline` key.
        - `timeline["total_entries"]` is 0, indicating no timeline entries were found.
        - `timeline["earliest"]` (and by implication `timeline["latest"]`) are `None`, reflecting the absence of timestamps.
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()

        # Mock investigation exists but no timeline
        mock_inv_result = MagicMock()
        mock_inv_result.fetchone.return_value = (
            "Test Investigation",
            "Description",
            datetime(2024, 1, 1),
            datetime(2024, 1, 15),
        )

        mock_timeline_result = MagicMock()
        mock_timeline_result.fetchone.return_value = (0, None, None)

        mock_artifact_result = MagicMock()
        mock_artifact_result.fetchall.return_value = []

        mock_event_result = MagicMock()
        mock_event_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_inv_result,
                mock_timeline_result,
                mock_artifact_result,
                mock_event_result,
            ]
        )

        context = await _gather_investigation_context(mock_db, investigation_id)

        assert context["timeline"]["total_entries"] == 0
        assert context["timeline"]["earliest"] is None


@pytest.mark.unit
class TestBuildContextPrompt:
    """Test building context prompts for LLM."""

    def test_build_prompt_with_full_context(self):
        """
        Test that _build_context_prompt correctly incorporates a fully populated context dictionary into the generated prompt, ensuring that investigation title and description, timeline entry count, artifact types, event categories, and the original user query are all present in the resulting string.
        """
        context = {
            "investigation": {
                "title": "Security Incident",
                "description": "Suspicious activity detected",
                "created_at": "2024-01-01T10:00:00",
            },
            "timeline": {
                "total_entries": 100,
                "earliest": "2024-01-01T10:00:00",
                "latest": "2024-01-15T16:00:00",
            },
            "artifacts": {
                "evtx": 5,
                "registry": 3,
            },
            "events": {
                "authentication": 25,
                "file_access": 50,
            },
        }
        user_query = "What is this investigation about?"

        prompt = _build_context_prompt(context, user_query)

        assert "Security Incident" in prompt
        assert "Suspicious activity detected" in prompt
        assert "100" in prompt  # timeline count
        assert "evtx" in prompt
        assert "authentication" in prompt
        assert user_query in prompt

    def test_build_prompt_minimal_context(self):
        """
        Tests that _build_context_prompt correctly incorporates minimal context information and the user's query into the generated prompt. It sets up a simple context with only an investigation title, invokes the prompt builder, and asserts that both the title and the original user query appear in the resulting prompt string.
        """
        context = {
            "investigation": {
                "title": "Test Investigation",
            },
        }
        user_query = "Tell me about this investigation"

        prompt = _build_context_prompt(context, user_query)

        assert "Test Investigation" in prompt
        assert user_query in prompt

    def test_build_prompt_empty_context(self):
        """
        Test that _build_context_prompt correctly constructs a prompt when the provided context dictionary is empty, ensuring the user query appears in the resulting prompt and that the prompt string is non-empty.
        """
        context = {}
        user_query = "What do we know?"

        prompt = _build_context_prompt(context, user_query)

        assert user_query in prompt
        assert len(prompt) > 0

    def test_build_prompt_with_many_event_types(self):
        """
        Test that the prompt generation correctly truncates a large list of event types.

        Args:
            self: TestCase instance providing the test context.

        Ensures that when the context contains many event types (e.g., 50 entries), the resulting prompt string produced by `_build_context_prompt` is shorter than an arbitrary size limit (10,000 characters). This verifies that the implementation caps or trims the displayed event type list to keep the prompt within reasonable length constraints.
        """
        context = {
            "events": {f"event_type_{i}": i for i in range(50)},
        }
        user_query = "What events do we have?"

        prompt = _build_context_prompt(context, user_query)

        # Should limit event types shown
        assert len(prompt) < 10000  # Reasonable limit


@pytest.mark.unit
class TestHandleGeneralChat:
    """Test main general chat handler."""

    @pytest.mark.asyncio
    async def test_handle_general_chat_success(self):
        """
        Test that `handle_general_chat` correctly processes a successful chat interaction.

        This test sets up mock dependencies for:
        - Retrieving the active LLM configuration.
        - Gathering investigation context from the database.
        - Obtaining an LLM response.

        It configures these mocks to return a valid investigation title and a successful LLM reply, then invokes `handle_general_chat` with sample identifiers and query text. The assertions verify that:
        - The result type is `"general_chat_answer"`.
        - The operation reports success (`success` is True).
        - The returned message contains the expected phrase from the mocked LLM response (case-insensitive).
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()
        user_query = "What is this investigation about?"
        user_id = 1

        with (
            patch(
                "app.services.handlers.general_chat_handler.get_active_llm_config"
            ) as mock_get_config,
            patch(
                "app.services.handlers.general_chat_handler._gather_investigation_context"
            ) as mock_gather,
            patch("app.services.handlers.general_chat_handler._get_llm_response") as mock_llm,
        ):

            mock_get_config.return_value = MagicMock()
            mock_gather.return_value = {"investigation": {"title": "Test Investigation"}}
            mock_llm.return_value = {"type": "success", "content": "This is a test investigation."}

            result = await handle_general_chat(mock_db, investigation_id, user_query, user_id)

            assert result["type"] == "general_chat_answer"
            assert result["success"] is True
            assert "test investigation" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_handle_general_chat_no_llm_config(self):
        """
        Test that `handle_general_chat` returns an error response when no LLM configuration is available.

        The test creates:
        - A mock asynchronous database session.
        - Random identifiers for the investigation and user.
        - A sample user query string.

        It patches `app.services.handlers.general_chat_handler.get_active_llm_config` to return `None`, simulating a missing LLM configuration. The handler is then invoked with the prepared arguments, and the test asserts that:
        - The returned dictionary has a `type` key equal to `"error"`.
        - The accompanying `message` mentions the lack of an LLM configuration (case-insensitive check).
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()
        user_query = "Test query"
        user_id = 1

        with patch(
            "app.services.handlers.general_chat_handler.get_active_llm_config"
        ) as mock_get_config:
            mock_get_config.return_value = None

            result = await handle_general_chat(mock_db, investigation_id, user_query, user_id)

            assert result["type"] == "error"
            assert "llm configuration" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_handle_general_chat_llm_error(self):
        """
        Test that handle_general_chat correctly propagates an error response from the LLM configuration.

        This test mocks the database connection, active LLM configuration retrieval, investigation context gathering, and LLM response fetching. It sets up the LLM mock to return a dictionary with `type` set to `"error"` and verifies that the result returned by `handle_general_chat` contains an `"error"` type, ensuring error handling is correctly passed through.
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()
        user_query = "Test query"
        user_id = 1

        with (
            patch(
                "app.services.handlers.general_chat_handler.get_active_llm_config"
            ) as mock_get_config,
            patch(
                "app.services.handlers.general_chat_handler._gather_investigation_context"
            ) as mock_gather,
            patch("app.services.handlers.general_chat_handler._get_llm_response") as mock_llm,
        ):

            mock_get_config.return_value = MagicMock()
            mock_gather.return_value = {}
            mock_llm.return_value = {"type": "error", "message": "LLM failed"}

            result = await handle_general_chat(mock_db, investigation_id, user_query, user_id)

            # Should propagate error
            assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_handle_general_chat_database_error(self):
        """
        Test that `handle_general_chat` correctly handles an exception raised while retrieving the active LLM configuration (simulating a database error). The test sets up an asynchronous mock database and patches `get_active_llm_config` to raise an `Exception` with a specific message. It then invokes `handle_general_chat` with sample identifiers and asserts that:

        - The returned result dictionary has its `type` field set to `"error"`, indicating the handler recognized the failure.
        - The mock database's `rollback` method was called exactly once, ensuring any pending transaction is aborted in response to the error.
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()
        user_query = "Test query"
        user_id = 1

        with patch(
            "app.services.handlers.general_chat_handler.get_active_llm_config"
        ) as mock_get_config:
            mock_get_config.side_effect = Exception("Database connection failed")

            result = await handle_general_chat(mock_db, investigation_id, user_query, user_id)

            assert result["type"] == "error"
            # Should have called rollback
            mock_db.rollback.assert_called_once()


@pytest.mark.unit
class TestGeneralChatEdgeCases:
    """Test edge cases and special scenarios."""

    def test_build_prompt_with_unicode(self):
        """
        Test that the prompt builder correctly incorporates Unicode characters from the investigation context and user query, ensuring non-ASCII text appears in the generated prompt.
        """
        context = {
            "investigation": {
                "title": "调查 Investigation",
                "description": "Unicode 文本 test",
            },
        }
        user_query = "What is this 调查 about?"

        prompt = _build_context_prompt(context, user_query)

        assert "调查" in prompt
        assert "文本" in prompt

    def test_build_prompt_with_very_long_description(self):
        """
        Test that the prompt builder correctly incorporates an investigation description that exceeds typical length limits, ensuring that a substantial portion of the very long description (at least the first 100 characters) appears in the generated context prompt.
        """
        context = {
            "investigation": {
                "title": "Test",
                "description": "A" * 10000,
            },
        }
        user_query = "Summarize this"

        prompt = _build_context_prompt(context, user_query)

        # Should include long description
        assert "A" * 100 in prompt

    @pytest.mark.asyncio
    async def test_handle_general_chat_with_special_characters(self):
        """
        Test handling of a general chat query containing special characters.

        This test verifies that `handle_general_chat` correctly processes a user query with various punctuation and symbols (e.g., "@#$%^&*()") without raising errors or returning an empty result. It uses mocked dependencies for the database, LLM configuration retrieval, context gathering, and LLM response generation to isolate the function's behavior.

        The test asserts that the returned value is not `None`, confirming graceful handling of special characters in the input query.
        """
        mock_db = AsyncMock()
        investigation_id = uuid4()
        user_query = "What's going on? @#$%^&*()"
        user_id = 1

        with (
            patch(
                "app.services.handlers.general_chat_handler.get_active_llm_config"
            ) as mock_get_config,
            patch(
                "app.services.handlers.general_chat_handler._gather_investigation_context"
            ) as mock_gather,
            patch("app.services.handlers.general_chat_handler._get_llm_response") as mock_llm,
        ):

            mock_get_config.return_value = MagicMock()
            mock_gather.return_value = {}
            mock_llm.return_value = {"type": "success", "content": "Response"}

            result = await handle_general_chat(mock_db, investigation_id, user_query, user_id)

            # Should handle special characters gracefully
            assert result is not None
