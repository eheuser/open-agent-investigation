import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from app.services import query_expander


@pytest.mark.unit
class TestQueryExpansion:
    """Test query expansion logic."""

    @patch("app.services.query_expander.LLMService")
    @patch("app.services.query_expander._get_chat_context")
    @patch("app.services.query_expander._get_graph_context")
    @patch("app.services.query_expander._get_investigation_context")
    async def test_expand_short_query(
        self,
        mock_inv_context,
        mock_graph_context,
        mock_chat_context,
        mock_llm_service_class,
    ):
        """
        Test that a short user query is expanded by the query expander service.

        This test verifies the end-to-end flow for expanding a brief query:

        * Sets up an asynchronous mock database and unique investigation identifier.
        * Provides a simple user query (`"show me more"`).
        * Mocks the three context-gathering helpers-chat, graph, and inventory-to return predetermined strings that simulate prior conversation, timeline entries, and event counts.
        * Replaces the LLM service class with a mock instance whose `call_llm` method returns a fabricated response payload and whose `extract_text_response` method yields the expected expanded text.
        * Calls `query_expander.expand_query` with the mocked dependencies.
        * Asserts that the returned query differs from the original short query and that its length is greater, confirming successful expansion.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_query = "show me more"
        user_id = 1

        # Mock context gathering
        mock_chat_context.return_value = "User: previous question\nAssistant: previous answer"
        mock_graph_context.return_value = "Timeline: 5 entries"
        mock_inv_context.return_value = "Events: 100 total"

        # Mock LLM service
        mock_llm = MagicMock()
        mock_llm.call_llm = AsyncMock(
            return_value={
                "choices": [
                    {"message": {"content": "Show me more details about the previous question"}}
                ]
            }
        )
        mock_llm.extract_text_response = AsyncMock(
            return_value="Show me more details about the previous question"
        )
        mock_llm_service_class.from_user_config = AsyncMock(return_value=mock_llm)

        result = await query_expander.expand_query(
            db=db,
            investigation_id=investigation_id,
            user_query=user_query,
            user_id=user_id,
        )

        assert result != user_query
        assert len(result) > len(user_query)

    async def test_skip_expansion_for_detailed_query(self):
        """
        Test that detailed queries are not expanded.

        Args:
            self: The test case instance.

        Ensures that when a user query exceeds the short-query length threshold (35 words in this case), the `expand_query` function returns the original query unchanged, confirming that no expansion is performed for detailed queries.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        long_query = " ".join(["word"] * 35)  # 35 words
        user_id = 1

        result = await query_expander.expand_query(
            db=db,
            investigation_id=investigation_id,
            user_query=long_query,
            user_id=user_id,
        )

        assert result == long_query

    async def test_skip_expansion_for_simple_commands(self):
        """
        Test that simple commands are passed through unchanged by the query expansion service.\n\nThis asynchronous unit test verifies that when the `expand_query` function is called with short, non-search commands such as \"help\", \"status\", \"summary\", or \"show graph\", it returns the original command string without performing any LLM-based expansion. The test sets up a mocked database connection, generates a unique investigation identifier, and uses a fixed user ID for consistency across iterations. Each simple command is sent to `query_expander.expand_query` with the required arguments, and the result is asserted to be identical to the input command, confirming that the service correctly skips expansion for these straightforward inputs.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        simple_commands = ["help", "status", "summary", "show graph"]

        for command in simple_commands:
            result = await query_expander.expand_query(
                db=db,
                investigation_id=investigation_id,
                user_query=command,
                user_id=user_id,
            )

            assert result == command

    @patch("app.services.query_expander.LLMService")
    @patch("app.services.query_expander._get_chat_context")
    @patch("app.services.query_expander._get_graph_context")
    @patch("app.services.query_expander._get_investigation_context")
    async def test_return_original_on_llm_failure(
        self,
        mock_inv_context,
        mock_graph_context,
        mock_chat_context,
        mock_llm_service_class,
    ):
        """
        Test that when the LLM service raises an exception during query expansion, the original user query is returned unchanged.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_inv_context : unittest.mock.AsyncMock
            Mock for the function retrieving investigation metadata context; returns a predefined string.
        mock_graph_context : unittest.mock.AsyncMock
            Mock for the function retrieving graph context; returns a predefined string.
        mock_chat_context : unittest.mock.AsyncMock
            Mock for the function retrieving chat history context; returns a predefined string.
        mock_llm_service_class : unittest.mock.Mock
            Mock for the LLM service class; its `from_user_config` method is set to raise an exception.

        The test sets up mock return values for all context-gathering functions, configures the LLM service mock to raise an `Exception` with the message "LLM error", invokes `query_expander.expand_query` with a sample query, and asserts that the result equals the original query string. This verifies graceful handling of LLM failures by falling back to the input query.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_query = "test query"
        user_id = 1

        mock_chat_context.return_value = "context"
        mock_graph_context.return_value = "graph"
        mock_inv_context.return_value = "metadata"

        # Mock LLM service to raise exception
        mock_llm_service_class.from_user_config = AsyncMock(side_effect=Exception("LLM error"))

        result = await query_expander.expand_query(
            db=db,
            investigation_id=investigation_id,
            user_query=user_query,
            user_id=user_id,
        )

        assert result == user_query

    @patch("app.services.query_expander.LLMService")
    @patch("app.services.query_expander._get_chat_context")
    @patch("app.services.query_expander._get_graph_context")
    @patch("app.services.query_expander._get_investigation_context")
    async def test_return_original_on_no_llm_config(
        self,
        mock_inv_context,
        mock_graph_context,
        mock_chat_context,
        mock_llm_service_class,
    ):
        """
        Test that the query expansion service returns the original user query unchanged when no LLM configuration is available for the given user. The test sets up mock contexts and a mock LLM service that resolves to `None` from `from_user_config`, invokes `expand_query` with sample inputs, and asserts that the result equals the input query.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_query = "test query"
        user_id = 1

        mock_chat_context.return_value = "context"
        mock_graph_context.return_value = "graph"
        mock_inv_context.return_value = "metadata"
        mock_llm_service_class.from_user_config = AsyncMock(return_value=None)

        result = await query_expander.expand_query(
            db=db,
            investigation_id=investigation_id,
            user_query=user_query,
            user_id=user_id,
        )

        assert result == user_query

    @patch("app.services.query_expander.LLMService")
    @patch("app.services.query_expander._get_chat_context")
    @patch("app.services.query_expander._get_graph_context")
    @patch("app.services.query_expander._get_investigation_context")
    async def test_reject_absurdly_long_expansion(
        self,
        mock_inv_context,
        mock_graph_context,
        mock_chat_context,
        mock_llm_service_class,
    ):
        """
        Test that the query expansion service rejects an expansion whose length exceeds acceptable limits, ensuring it falls back to returning the original user query unchanged. The test sets up mocks for context retrieval and the LLM service to produce an excessively long string (10,000 characters). It then calls `query_expander.expand_query` with a short input query and verifies that the result equals the original query because the generated expansion is considered absurdly long. This validates the length-checking logic within the expansion workflow.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_query = "test"
        user_id = 1

        mock_chat_context.return_value = "context"
        mock_graph_context.return_value = "graph"
        mock_inv_context.return_value = "metadata"

        # Mock LLM to return very long expansion
        very_long_expansion = "x" * 10000
        mock_llm = MagicMock()
        mock_llm.call_llm = AsyncMock(
            return_value={"choices": [{"message": {"content": very_long_expansion}}]}
        )
        mock_llm.extract_text_response = AsyncMock(return_value=very_long_expansion)
        mock_llm_service_class.from_user_config = AsyncMock(return_value=mock_llm)

        result = await query_expander.expand_query(
            db=db,
            investigation_id=investigation_id,
            user_query=user_query,
            user_id=user_id,
        )

        # Should return original due to absurd length
        assert result == user_query


@pytest.mark.unit
class TestContextGathering:
    """Test context gathering functions."""

    @patch("app.services.query_expander.get_investigation_messages")
    async def test_get_chat_context_with_messages(self, mock_get_messages):
        """
        Test that `_get_chat_context` correctly formats chat messages retrieved from the database into a single string containing each message prefixed by its role (e.g., "User:" and "Assistant:"). The test uses an asynchronous mock for the database, supplies a fake investigation ID, mocks two messages-one from a user and one from an assistant-and asserts that the resulting context string includes both formatted entries.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock messages
        mock_msg1 = MagicMock()
        mock_msg1.role = "user"
        mock_msg1.content = "Hello"

        mock_msg2 = MagicMock()
        mock_msg2.role = "assistant"
        mock_msg2.content = "Hi there"

        mock_get_messages.return_value = [mock_msg1, mock_msg2]

        context = await query_expander._get_chat_context(db, investigation_id)

        assert "User: Hello" in context
        assert "Assistant: Hi there" in context

    @patch("app.services.query_expander.get_investigation_messages")
    async def test_get_chat_context_empty(self, mock_get_messages):
        """
        Test that when there are no prior chat messages for a given investigation, the internal `_get_chat_context` helper returns a string indicating the absence of chat history. The test sets up an async mock database, provides a fresh investigation UUID, mocks the message retrieval to return an empty list, invokes the coroutine, and asserts that the resulting context contains the phrase “No previous chat history”. This verifies correct handling of empty conversation histories.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        mock_get_messages.return_value = []

        context = await query_expander._get_chat_context(db, investigation_id)

        assert "No previous chat history" in context

    @patch("app.services.query_expander.get_investigation_messages")
    async def test_get_chat_context_truncates_long_messages(self, mock_get_messages):
        """
        Test that `_get_chat_context` truncates messages exceeding the length limit by mocking a long user message and verifying the returned context contains an ellipsis indicating truncation.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        mock_msg = MagicMock()
        mock_msg.role = "user"
        mock_msg.content = "x" * 500

        mock_get_messages.return_value = [mock_msg]

        context = await query_expander._get_chat_context(db, investigation_id)

        assert "..." in context

    @patch("app.services.query_expander.get_investigation_messages")
    async def test_get_chat_context_skips_tool_messages(self, mock_get_messages):
        """
        Test that `_get_chat_context` correctly skips messages with role "tool" and includes only user messages in the returned context. The test mocks database message retrieval, provides one tool-role message and one user-role message, invokes the function, and asserts that the tool content is absent while the user content appears in the resulting chat context.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        mock_msg1 = MagicMock()
        mock_msg1.role = "tool"
        mock_msg1.content = "Tool result"

        mock_msg2 = MagicMock()
        mock_msg2.role = "user"
        mock_msg2.content = "User message"

        mock_get_messages.return_value = [mock_msg1, mock_msg2]

        context = await query_expander._get_chat_context(db, investigation_id)

        assert "Tool result" not in context
        assert "User message" in context

    async def test_get_graph_context_with_entries(self):
        """
        Test that _get_graph_context correctly retrieves timeline entries from the database and formats them into a context string containing the number of entries and their titles.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock timeline query result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "event", "Event 1", "Description", ["tag1"], None),
            (2, "finding", "Finding 1", "Description", [], None),
        ]
        db.execute = AsyncMock(return_value=mock_result)

        context = await query_expander._get_graph_context(db, investigation_id)

        assert "2 entries" in context
        assert "Event 1" in context

    async def test_get_graph_context_empty(self):
        """
        Test that `_get_graph_context` returns a placeholder message when the database query yields no timeline entries for the given investigation ID. The test creates an asynchronous mock database connection, configures its `execute` method to return an empty result set, invokes the private helper with a generated UUID, and asserts that the resulting context string contains the phrase "No timeline entries". This verifies proper handling of empty graph data scenarios.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        context = await query_expander._get_graph_context(db, investigation_id)

        assert "No timeline entries" in context

    async def test_get_investigation_context_with_events(self):
        """
        Test that `_get_investigation_context` correctly aggregates event counts and time range for a given investigation.

        The test creates an asynchronous mock database connection and supplies:
        - A mocked result set for the event count query containing two event types with their respective counts.
        - A mocked result for the investigation time-range query returning a start and end `datetime`.

        Both queries are queued as side effects of `db.execute`. The coroutine under test is then awaited, producing a context string.

        Assertions verify that:
        - The total number of events (the sum of the mock counts) appears in the generated context.
        - Individual event type names (e.g., `process_creation`) are included in the context.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        # Mock event counts
        mock_event_result = MagicMock()
        mock_event_result.fetchall.return_value = [
            ("process_creation", 50),
            ("network_connection", 30),
        ]

        # Mock time range
        from datetime import datetime

        mock_time_result = MagicMock()
        mock_time_result.fetchone.return_value = (
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )

        db.execute = AsyncMock(side_effect=[mock_event_result, mock_time_result])

        context = await query_expander._get_investigation_context(db, investigation_id)

        assert "80" in context  # Total events
        assert "process_creation" in context

    async def test_get_investigation_context_empty(self):
        """
        Test that `_get_investigation_context` returns a placeholder string when the specified investigation contains no events in the database. The test sets up an asynchronous mock database connection, configures `execute` to return an empty result set, invokes the private helper with a generated investigation ID, and asserts that the returned context includes the phrase “No events”.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        context = await query_expander._get_investigation_context(db, investigation_id)

        assert "No events" in context
