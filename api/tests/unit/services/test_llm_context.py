"""
Unit tests for LLM context building utilities.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.llm_context import (
    estimate_tokens,
    message_to_openai_format,
    build_context,
    build_general_context,
    build_timeline_context,
    build_agent_seed_context,
    MAX_CONTEXT_PERCENT,
    DEFAULT_MAX_TOKENS,
    CHARS_PER_TOKEN_ESTIMATE,
)
from app.models.llm_config import LLMProviderConfig
from app.models.chat_history import ChatMessage


@pytest.mark.unit
class TestEstimateTokens:
    """Test estimate_tokens function."""

    def test_estimate_tokens_empty_string(self):
        """
        Test that `estimate_tokens` returns zero when given an empty string, verifying correct handling of the edge case where no characters are present.
        """
        result = estimate_tokens("")
        assert result == 0

    def test_estimate_tokens_none(self):
        """
        Test that `estimate_tokens` returns 0 when given `None` as input, ensuring the function handles null values gracefully.
        """
        result = estimate_tokens(None)
        assert result == 0

    def test_estimate_tokens_simple_text(self):
        """
        Test estimating token count for a simple short string.

        This test verifies that `estimate_tokens` returns the expected number of tokens when given a basic piece of text. It calculates the expected value using the `CHARS_PER_TOKEN_ESTIMATE` constant and asserts that the function's output matches this expectation.
        """
        text = "Hello world"
        result = estimate_tokens(text)
        expected = len(text) // CHARS_PER_TOKEN_ESTIMATE
        assert result == expected

    def test_estimate_tokens_long_text(self):
        """
        Test that `estimate_tokens` correctly calculates the number of tokens for a long string by dividing the character count by :data:`CHARS_PER_TOKEN_ESTIMATE` and returning the integer quotient. The test creates a 1000-character input, calls `estimate_tokens`, computes the expected token count using floor division, and asserts that the result matches this expectation.
        """
        text = "A" * 1000
        result = estimate_tokens(text)
        expected = 1000 // CHARS_PER_TOKEN_ESTIMATE
        assert result == expected

    def test_estimate_tokens_unicode(self):
        """
        Test that token estimation correctly handles Unicode characters by verifying the result is a non-negative integer for a string containing both ASCII and non-ASCII symbols.
        """
        text = "Hello 世界 🌍"
        result = estimate_tokens(text)
        assert result >= 0
        assert isinstance(result, int)

    def test_estimate_tokens_multiline(self):
        """
        Test estimating tokens for multiline text.

        This test verifies that the `estimate_tokens` function correctly calculates the number of tokens for a string containing multiple lines separated by newline characters. It constructs a sample multiline string, computes the token count using `estimate_tokens`, and asserts that the result matches the expected value based on the `CHARS_PER_TOKEN_ESTIMATE` constant.
        """
        text = "Line 1\nLine 2\nLine 3"
        result = estimate_tokens(text)
        expected = len(text) // CHARS_PER_TOKEN_ESTIMATE
        assert result == expected


@pytest.mark.unit
class TestMessageToOpenAIFormat:
    """Test message_to_openai_format function."""

    def test_message_with_content_only(self):
        """
        Test converting a message object that contains only role and content fields into the OpenAI API format, ensuring the resulting dictionary includes exactly those keys without any optional fields.
        """
        msg = MagicMock()
        msg.role = "user"
        msg.content = "Hello"
        msg.name = None
        msg.tool_calls = None
        msg.tool_call_id = None

        result = message_to_openai_format(msg)

        assert result == {"role": "user", "content": "Hello"}

    def test_message_with_all_fields(self):
        """
        Test converting a message object with all possible fields into OpenAI format.

        Creates a mock message with role, content, name, tool_calls, and tool_call_id set.
        Calls `message_to_openai_format` to transform the mock.
        Asserts that the resulting dictionary contains the same values for
        `role`, `content`, `name`, `tool_calls` and `tool_call_id`.
        """
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "Response"
        msg.name = "agent"
        msg.tool_calls = [{"id": "call_123", "function": {"name": "search"}}]
        msg.tool_call_id = "call_123"

        result = message_to_openai_format(msg)

        assert result["role"] == "assistant"
        assert result["content"] == "Response"
        assert result["name"] == "agent"
        assert result["tool_calls"] == [{"id": "call_123", "function": {"name": "search"}}]
        assert result["tool_call_id"] == "call_123"

    def test_message_with_none_content(self):
        """
        Test that `message_to_openai_format` correctly handles a message object whose `content` attribute is `None`. The test creates a mock message with role set to "assistant", no content or name, and includes a non-empty `tool_calls` list while leaving `tool_call_id` unset. After conversion, the resulting dictionary should omit the `"content"` key, preserve the original `"role"`, and retain the provided `"tool_calls"` entry. This verifies that messages without textual content are serialized according to OpenAI's expected format without including a null or empty content field.
        """
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = None
        msg.name = None
        msg.tool_calls = [{"id": "call_123"}]
        msg.tool_call_id = None

        result = message_to_openai_format(msg)

        assert "content" not in result
        assert result["role"] == "assistant"
        assert result["tool_calls"] == [{"id": "call_123"}]

    def test_message_system_role(self):
        """
        Test that a message with the "system" role is correctly converted to the OpenAI API format.

        The test creates a mock message object with:
        - `role` set to `"system"`
        - `content` containing a sample system prompt
        - all optional fields (`name`, `tool_calls`, `tool_call_id`) left as `None`

        It then passes this mock to :func:`message_to_openai_format` and asserts that the returned dictionary contains only the required keys `role` and `content` with the expected values, confirming that no extraneous fields are included for system-role messages.
        """
        msg = MagicMock()
        msg.role = "system"
        msg.content = "You are a helpful assistant"
        msg.name = None
        msg.tool_calls = None
        msg.tool_call_id = None

        result = message_to_openai_format(msg)

        assert result == {"role": "system", "content": "You are a helpful assistant"}

    def test_message_tool_role(self):
        """
        Test converting a tool response message to OpenAI format, verifying that the resulting dictionary preserves the role, content, name, and tool_call_id fields from the original mock message.
        """
        msg = MagicMock()
        msg.role = "tool"
        msg.content = '{"result": "success"}'
        msg.name = "search_events"
        msg.tool_calls = None
        msg.tool_call_id = "call_123"

        result = message_to_openai_format(msg)

        assert result["role"] == "tool"
        assert result["content"] == '{"result": "success"}'
        assert result["name"] == "search_events"
        assert result["tool_call_id"] == "call_123"


@pytest.mark.unit
class TestBuildContext:
    """Test build_context function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for testing purposes.

        Returns
        -------
        AsyncMock
            An async mock object simulating the database session interface.
        """
        return AsyncMock()

    @pytest.fixture
    def mock_llm_config(self):
        """
        Create and return a mock LLM provider configuration with a predefined maximum context length for testing purposes. The returned MagicMock adheres to the LLMProviderConfig interface and has its max_context_length attribute set to 8192.
        """
        config = MagicMock(spec=LLMProviderConfig)
        config.max_context_length = 8192
        return config

    @pytest.fixture
    def mock_messages(self):
        """
        Creates a list of two mock chat message objects for use in tests.

        The first message simulates a user request with role set to `"user"`, content `"Hello"`, and all optional fields (`name`, `tool_calls`, `tool_call_id`) left as `None`.

        The second message simulates an assistant reply with role set to `"assistant"`, content `"Hi there"`, and the same optional fields set to `None`.

        Returns
        -------
        list[MagicMock]
            A list containing the two configured `MagicMock` instances representing chat messages.
        """
        msg1 = MagicMock()
        msg1.role = "user"
        msg1.content = "Hello"
        msg1.name = None
        msg1.tool_calls = None
        msg1.tool_call_id = None

        msg2 = MagicMock()
        msg2.role = "assistant"
        msg2.content = "Hi there"
        msg2.name = None
        msg2.tool_calls = None
        msg2.tool_call_id = None

        return [msg1, msg2]

    @patch("app.services.llm_context.get_active_llm_config")
    @patch("app.services.llm_context.crud.get_investigation_messages")
    async def test_build_context_basic(
        self, mock_get_messages, mock_get_config, mock_db, mock_llm_config, mock_messages
    ):
        """
        Test the basic functionality of `build_context` by verifying that it correctly assembles a context list containing the system prompt followed by user and assistant messages.

        Parameters
        ----------
        self : object
            The test case instance (typically a subclass of `unittest.IsolatedAsyncioTestCase` or similar).
        mock_get_messages : unittest.mock.Mock
            Mock for the function that retrieves conversation messages from the database. It is configured to return `mock_messages`.
        mock_get_config : unittest.mock.Mock
            Mock for the function that fetches LLM configuration settings. It is set to return `mock_llm_config`.
        mock_db : unittest.mock.Mock
            Mock representing the database connection or session passed to `build_context`.
        mock_llm_config : dict
            A dictionary containing placeholder LLM configuration values used by the context builder.
        mock_messages : list[dict]
            A pre-defined list of message dictionaries that simulate stored user and assistant messages.

        The test constructs a random `investigation_id` and a static `user_id`, then calls `await build_context` with the mocked dependencies and a simple system prompt. It asserts that:

        * The resulting context contains exactly three entries.
        * The first entry is a system message whose content matches `system_prompt`.
        * The second entry has the role `"user"`.
        * The third entry has the role `"assistant"`.

        No value is returned; the function raises an assertion error if any of the conditions are not met.
        """
        investigation_id = uuid4()
        user_id = 1
        system_prompt = "You are a helpful assistant"

        mock_get_config.return_value = mock_llm_config
        mock_get_messages.return_value = mock_messages

        result = await build_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            system_prompt=system_prompt,
        )

        # Should have system prompt + 2 messages
        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[0]["content"] == system_prompt
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"

    @patch("app.services.llm_context.get_active_llm_config")
    @patch("app.services.llm_context.crud.get_investigation_messages")
    async def test_build_context_with_additional_context(
        self, mock_get_messages, mock_get_config, mock_db, mock_llm_config, mock_messages
    ):
        """
        Test that :func:`build_context` correctly incorporates an additional system-level context string when assembling the full message list.

        The test sets up:
        - A unique `investigation_id` and a dummy `user_id`.
        - A base `system_prompt` and an `additional_context` string representing extra information (e.g., timeline entries).
        - Mocked return values for configuration retrieval (`mock_get_config`) and message fetching (`mock_get_messages`), supplying pre-defined LLM config and a list of messages.

        The function under test is invoked with the mocked database connection and the prepared parameters. The expected result is a list of four message dictionaries:
        1. The original system prompt (role `system`).
        2. The additional context string (also role `system`).
        3. Two user/assistant messages returned by `mock_get_messages`.

        Assertions verify that the total length matches expectations, that the first two entries have the correct roles and contents, and implicitly confirm that the remaining messages are preserved unchanged.
        """
        investigation_id = uuid4()
        user_id = 1
        system_prompt = "System prompt"
        additional_context = "Timeline entries: Event 1, Event 2"

        mock_get_config.return_value = mock_llm_config
        mock_get_messages.return_value = mock_messages

        result = await build_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            system_prompt=system_prompt,
            additional_context=additional_context,
        )

        # Should have system prompt + additional context + 2 messages
        assert len(result) == 4
        assert result[0]["role"] == "system"
        assert result[0]["content"] == system_prompt
        assert result[1]["role"] == "system"
        assert result[1]["content"] == additional_context

    @patch("app.services.llm_context.get_active_llm_config")
    @patch("app.services.llm_context.crud.get_investigation_messages")
    async def test_build_context_no_llm_config(
        self, mock_get_messages, mock_get_config, mock_db, mock_messages
    ):
        """
        Test that :func:`build_context` correctly constructs a context when no LLM configuration is present.

        Parameters
        ----------
        self: object
            The test case instance.
        mock_get_messages: unittest.mock.Mock
            Mock for the function that retrieves messages from the database; returns `mock_messages`.
        mock_get_config: unittest.mock.Mock
            Mock for the function that fetches the LLM configuration; set to return `None` to simulate a missing config.
        mock_db: unittest.mock.AsyncMock
            Mocked asynchronous database session passed to :func:`build_context`.
        mock_messages: list[dict]
            A predefined list of message dictionaries used as the source messages for context building.

        The test creates a random investigation ID and uses a static user ID and system prompt. It verifies that `build_context` falls back to default token limits when no LLM config is found, returns at least one message, and that the first message has the role `"system"`.
        """
        investigation_id = uuid4()
        user_id = 1
        system_prompt = "System prompt"

        mock_get_config.return_value = None  # No config
        mock_get_messages.return_value = mock_messages

        result = await build_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            system_prompt=system_prompt,
        )

        # Should still work with default token limit
        assert len(result) >= 1
        assert result[0]["role"] == "system"

    @patch("app.services.llm_context.get_active_llm_config")
    @patch("app.services.llm_context.crud.get_investigation_messages")
    async def test_build_context_token_budget_exceeded(
        self, mock_get_messages, mock_get_config, mock_db
    ):
        """
        Test that the context-building routine respects the provider's token budget by truncating messages when their combined length exceeds the maximum allowed context size.

        The test sets up:
        - A mock configuration with an artificially low `max_context_length` (100 tokens).
        - Ten synthetic user messages, each containing 1 000 characters, guaranteeing that the total token count far surpasses the budget.
        - Mocked database and retrieval functions to supply these messages and the configuration.

        It then invokes :func:`build_context` with the mocked dependencies and verifies:
        - The resulting context contains at least the system prompt entry (role `system`).
        - The total number of entries in the returned context is fewer than the original eleven items (system prompt plus ten user messages), confirming that excess messages were omitted to stay within the token budget.
        """
        investigation_id = uuid4()
        user_id = 1
        system_prompt = "System prompt"

        # Create config with very small context
        small_config = MagicMock(spec=LLMProviderConfig)
        small_config.max_context_length = 100
        mock_get_config.return_value = small_config

        # Create many large messages
        large_messages = []
        for i in range(10):
            msg = MagicMock()
            msg.role = "user"
            msg.content = "A" * 1000  # Large message
            msg.name = None
            msg.tool_calls = None
            msg.tool_call_id = None
            large_messages.append(msg)

        mock_get_messages.return_value = large_messages

        result = await build_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            system_prompt=system_prompt,
        )

        # Should truncate messages to fit budget
        # At minimum, should have system prompt
        assert len(result) >= 1
        assert result[0]["role"] == "system"
        # Should have fewer than all 10 messages due to budget
        assert len(result) < 11

    @patch("app.services.llm_context.get_active_llm_config")
    @patch("app.services.llm_context.crud.get_investigation_messages")
    async def test_build_context_empty_messages(
        self, mock_get_messages, mock_get_config, mock_db, mock_llm_config
    ):
        """
        Test that building context with an empty message list returns only the system prompt.

        Parameters:
            self: Test case instance.
            mock_get_messages: Mock for the function retrieving messages; configured to return an empty list.
            mock_get_config: Mock for the configuration retrieval function; its return value is set to `mock_llm_config`.
            mock_db: Mock database object passed to `build_context`.
            mock_lll_config: Mock LLM configuration object used by `mock_get_config`.

        The test creates a new investigation ID and user ID, defines a system prompt, configures the mocks, invokes `build_context`, and asserts that:
        * The resulting context contains exactly one entry.
        * That entry has its role set to `"system"` and includes the provided system prompt.
        """
        investigation_id = uuid4()
        user_id = 1
        system_prompt = "System prompt"

        mock_get_config.return_value = mock_llm_config
        mock_get_messages.return_value = []

        result = await build_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            system_prompt=system_prompt,
        )

        # Should only have system prompt
        assert len(result) == 1
        assert result[0]["role"] == "system"


@pytest.mark.unit
class TestBuildGeneralContext:
    """Test build_general_context function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return an asynchronous mock of a database session.

        This helper method constructs an :class:`unittest.mock.AsyncMock` instance that mimics the
        behaviour of an async database session, allowing tests to run without requiring a real
        database connection. The returned mock can be configured in test cases to simulate
        queries, commits, rollbacks, and other asynchronous operations.
        """
        return AsyncMock()

    @patch("app.services.llm_context.build_context")
    async def test_build_general_context(self, mock_build_context, mock_db):
        """
        Test that the general context builder assembles the correct system prompt and invokes `build_context` with the appropriate mode.

        The test creates a dummy investigation ID and user ID, mocks the `build_context` function to return a minimal system message, then calls :func:`build_general_context` with the mocked database session. After awaiting the result, it asserts that:

        * `build_context` was called exactly once.
        * The call used `mode="general"`.
        * The supplied `system_prompt` contains the phrase “forensic investigation assistant”, ensuring the prompt is correctly constructed for the general mode.
        """
        investigation_id = uuid4()
        user_id = 1

        mock_build_context.return_value = [{"role": "system", "content": "System prompt"}]

        result = await build_general_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
        )

        # Verify build_context was called with general mode
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        assert call_args.kwargs["mode"] == "general"
        assert "forensic investigation assistant" in call_args.kwargs["system_prompt"].lower()


@pytest.mark.unit
class TestBuildTimelineContext:
    """Test build_timeline_context function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for testing purposes.

        Returns:
            AsyncMock: A mock object simulating an async database session.
        """
        return AsyncMock()

    @patch("app.services.llm_context.build_context")
    async def test_build_timeline_context_without_entries(self, mock_build_context, mock_db):
        """
        Test that `build_timeline_context` correctly constructs a timeline-mode context when the investigation contains no entries.

        The test sets up:
        - A mock `build_context` that returns a minimal system prompt.
        - Dummy identifiers for an investigation (generated via `uuid4`) and a user.

        It then calls `build_timeline_context` with the mocked database, investigation ID, and user ID, awaiting the coroutine result.

        Assertions verify that:
        - `build_context` is invoked exactly once.
        - The call uses `mode="timeline"`.
        - The supplied system prompt contains the phrase “timeline analyst” (case-insensitive).
        - No additional context is passed (i.e., `additional_context` is `None`).
        """
        investigation_id = uuid4()
        user_id = 1

        mock_build_context.return_value = [{"role": "system", "content": "System prompt"}]

        result = await build_timeline_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
        )

        # Verify build_context was called with timeline mode
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        assert call_args.kwargs["mode"] == "timeline"
        assert "timeline analyst" in call_args.kwargs["system_prompt"].lower()
        assert call_args.kwargs["additional_context"] is None

    @patch("app.services.llm_context.build_context")
    async def test_build_timeline_context_with_entries(self, mock_build_context, mock_db):
        """
        Test building timeline context with entries.

        Ensures that `build_timeline_context` receives the supplied `timeline_entries` string as the `additional_context` argument when delegating to `build_context`. The test mocks `build_context` to return a minimal system prompt, invokes the coroutine with a generated investigation ID, user ID and a multiline timeline string, then asserts that:

        * `build_context` is called exactly once.
        * The `additional_context` keyword argument passed to `build_context` matches the original `timeline_entries` value.
        """
        investigation_id = uuid4()
        user_id = 1
        timeline_entries = "2024-01-01 10:00: Event 1\n2024-01-01 11:00: Event 2"

        mock_build_context.return_value = [{"role": "system", "content": "System prompt"}]

        result = await build_timeline_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            timeline_entries=timeline_entries,
        )

        # Verify timeline entries were passed as additional context
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        assert call_args.kwargs["additional_context"] == timeline_entries


@pytest.mark.unit
class TestBuildAgentSeedContext:
    """Test build_agent_seed_context function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mocked asynchronous database session for testing purposes.

        Returns:
            AsyncMock: An async mock object that simulates a database session, allowing coroutine calls to be awaited without performing real I/O.
        """
        return AsyncMock()

    @patch("app.services.llm_context.build_context")
    async def test_build_agent_seed_context(self, mock_build_context, mock_db):
        """
        Test that `build_agent_seed_context` constructs the correct context for an agent seed scenario.

        The test sets up a mock `build_context` function to return a minimal system message and then calls `build_agent_seed_context` with a generated investigation ID, a user identifier, and specific agent instructions. After awaiting the result, it verifies that:

        - `build_context` was invoked exactly once.
        - The call used the `mode` argument set to `"agent_seed"`.
        - The automatically generated system prompt contains the phrase “autonomous forensic investigation agent” (case-insensitive).
        - The provided `agent_instructions` appear verbatim within the system prompt.
        """
        investigation_id = uuid4()
        user_id = 1
        agent_instructions = "Investigate suspicious login attempts"

        mock_build_context.return_value = [{"role": "system", "content": "System prompt"}]

        result = await build_agent_seed_context(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            agent_instructions=agent_instructions,
        )

        # Verify build_context was called with agent_seed mode
        mock_build_context.assert_called_once()
        call_args = mock_build_context.call_args
        assert call_args.kwargs["mode"] == "agent_seed"
        assert (
            "autonomous forensic investigation agent" in call_args.kwargs["system_prompt"].lower()
        )
        assert agent_instructions in call_args.kwargs["system_prompt"]


@pytest.mark.unit
class TestLLMContextConstants:
    """Test module constants."""

    def test_max_context_percent(self):
        """
        Test that the MAX_CONTEXT_PERCENT constant is within a valid range (greater than 0 and at most 1) and matches the expected default value of 0.85.
        """
        assert 0 < MAX_CONTEXT_PERCENT <= 1.0
        assert MAX_CONTEXT_PERCENT == 0.85

    def test_default_max_tokens(self):
        """
        Test that the constant DEFAULT_MAX_TOKENS is a positive integer and matches the expected value of 8192.
        """
        assert DEFAULT_MAX_TOKENS > 0
        assert DEFAULT_MAX_TOKENS == 8192

    def test_chars_per_token_estimate(self):
        """
        Test that the constant CHARS_PER_TOKEN_ESTIMATE is a positive integer and matches the expected value of 4 characters per token.
        """
        assert CHARS_PER_TOKEN_ESTIMATE > 0
        assert CHARS_PER_TOKEN_ESTIMATE == 4


@pytest.mark.unit
class TestLLMContextEdgeCases:
    """Test edge cases for LLM context building."""

    def test_estimate_tokens_with_special_characters(self):
        """
        Test token estimation with special characters.

        Verify that the `estimate_tokens` function correctly handles a string containing a variety of punctuation and symbols. The test supplies a sample text composed solely of special characters and asserts that the returned token count is a non-negative integer, ensuring that no exception is raised and that the function's output remains within expected bounds.
        """
        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        result = estimate_tokens(text)
        assert result >= 0

    def test_estimate_tokens_with_newlines(self):
        """
        Test that the token estimation function correctly handles strings containing different newline characters, ensuring it returns a non-negative token count for mixed line endings.
        """
        text = "Line 1\n\nLine 2\r\nLine 3"
        result = estimate_tokens(text)
        assert result >= 0

    def test_message_to_openai_format_with_empty_tool_calls(self):
        """
        Test that `message_to_openai_format` correctly handles an assistant message whose `tool_calls` attribute is an empty list, ensuring the resulting dictionary includes an empty `"tool_calls"` entry.
        """
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "Response"
        msg.name = None
        msg.tool_calls = []
        msg.tool_call_id = None

        result = message_to_openai_format(msg)

        assert result["tool_calls"] == []

    @patch("app.services.llm_context.get_active_llm_config")
    @patch("app.services.llm_context.crud.get_investigation_messages")
    async def test_build_context_with_very_long_system_prompt(
        self, mock_get_messages, mock_get_config
    ):
        """
        Test that the context builder includes an extremely long system prompt even when the configured maximum context length is limited.

        The test sets up:
        - An asynchronous mock database (`db`).
        - A unique investigation identifier and a user ID.
        - A system prompt consisting of 10,000 characters.
        - A mocked `LLMProviderConfig` with `max_context_length` set to 8192 tokens.
        - Mocked return values for configuration retrieval and message fetching (empty message list).

        It then calls `build_context` with the prepared arguments and asserts that:
        1. The returned context contains at least one entry.
        2. The first entry has a role of `"system"`, confirming that the long system prompt was not omitted despite exceeding typical length limits.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1
        system_prompt = "A" * 10000  # Very long prompt

        config = MagicMock(spec=LLMProviderConfig)
        config.max_context_length = 8192
        mock_get_config.return_value = config
        mock_get_messages.return_value = []

        result = await build_context(
            db=db,
            investigation_id=investigation_id,
            user_id=user_id,
            system_prompt=system_prompt,
        )

        # Should still include system prompt
        assert len(result) >= 1
        assert result[0]["role"] == "system"
