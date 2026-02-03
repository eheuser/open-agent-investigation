import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock
from app.services import chat_persistence


@pytest.mark.unit
class TestPersistUserMessage:
    """Test persist_user_message function."""

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_user_message_basic(self, mock_create):
        """
        Test persisting a basic user message.

        This unit test verifies that :func:`chat_persistence.persist_user_message` correctly creates a user-role message in the database and returns its identifier.

        The test sets up:
        - `investigation_id` as a new UUID.
        - `user_id` as an integer representing the author.
        - `content` containing the message text.

        A mock for the CRUD `create` function is configured to return a `MagicMock` with `message_id` set to `123`. An `AsyncMock` database connection is passed to the persistence function.

        The test asserts that:
        - The returned `message_id` matches the mocked ID (`123`).
        - The `create` method was called exactly once.
        - The call arguments include `role="user"`, the provided `content`, and `include_in_llm_context=True`.
        """
        investigation_id = uuid4()
        user_id = 1
        content = "What happened on this system?"

        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_create.return_value = mock_message

        db = AsyncMock()
        message_id = await chat_persistence.persist_user_message(
            db=db,
            investigation_id=investigation_id,
            user_id=user_id,
            content=content,
        )

        assert message_id == 123
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args["role"] == "user"
        assert call_args["content"] == content
        assert call_args["include_in_llm_context"] is True

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_user_message_with_metadata(self, mock_create):
        """
        Test that persisting a user message with additional metadata correctly forwards the metadata to the underlying CRUD create operation and returns the generated message identifier.

        Args:
            self: Test case instance.
            mock_create: Mocked `create` function from the CRUD layer, injected via patching.

        Procedure:
            1. Generate a random `investigation_id` and define a `metadata` dictionary.
            2. Configure `mock_create` to return a `MagicMock` with `message_id` set to `456`.
            3. Call :func:`chat_persistence.persist_user_message` with the mock database, investigation ID, user ID, content, and metadata.
            4. Verify that the returned `message_id` matches the mocked value.
            5. Inspect the call arguments of `mock_create` to ensure the `metadata` argument was passed unchanged.
        """
        investigation_id = uuid4()
        metadata = {"intent": "timeline_query", "confidence": 0.95}

        mock_message = MagicMock()
        mock_message.message_id = 456
        mock_create.return_value = mock_message

        db = AsyncMock()
        message_id = await chat_persistence.persist_user_message(
            db=db,
            investigation_id=investigation_id,
            user_id=1,
            content="Test",
            metadata=metadata,
        )

        assert message_id == 456
        call_args = mock_create.call_args[1]
        assert call_args["metadata"] == metadata


@pytest.mark.unit
class TestPersistAssistantMessage:
    """Test persist_assistant_message function."""

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_assistant_message_basic(self, mock_create):
        """
        Test that persisting a basic assistant message correctly calls the CRUD create function with role set to "assistant", the provided content, and default flags for inclusion in LLM context and UI visibility, and returns the generated message ID.
        """
        investigation_id = uuid4()
        content = "I found 5 suspicious events."

        mock_message = MagicMock()
        mock_message.message_id = 789
        mock_create.return_value = mock_message

        db = AsyncMock()
        message_id = await chat_persistence.persist_assistant_message(
            db=db,
            investigation_id=investigation_id,
            user_id=1,
            content=content,
        )

        assert message_id == 789
        call_args = mock_create.call_args[1]
        assert call_args["role"] == "assistant"
        assert call_args["content"] == content
        assert call_args["include_in_llm_context"] is True
        assert call_args["visible_in_ui"] is True

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_assistant_message_hidden(self, mock_create):
        """
        Test that persisting an assistant message with `include_in_llm_context` and `visible_in_ui` set to `False` correctly forwards these flags to the CRUD layer.

        Args:
            self: Test case instance.
            mock_create: Mock of the CRUD `create_message` function, injected by the test framework.

        The test creates a fake message object with a predefined `message_id`, configures the mock to return it, and calls `chat_persistence.persist_assistant_message` with `include_in_llm_context=False` and `visible_in_ui=False`. It then asserts that the mocked `create_message` was invoked with the same flag values, ensuring hidden assistant messages are persisted as intended.
        """
        mock_message = MagicMock()
        mock_message.message_id = 111
        mock_create.return_value = mock_message

        db = AsyncMock()
        await chat_persistence.persist_assistant_message(
            db=db,
            investigation_id=uuid4(),
            user_id=1,
            content="Internal reasoning",
            include_in_llm_context=False,
            visible_in_ui=False,
        )

        call_args = mock_create.call_args[1]
        assert call_args["include_in_llm_context"] is False
        assert call_args["visible_in_ui"] is False


@pytest.mark.unit
class TestPersistSystemMessage:
    """Test persist_system_message function."""

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_system_message_basic(self, mock_create):
        """
        Test that persisting a basic system message correctly invokes the CRUD layer with expected parameters and returns the generated message ID. The test creates a mock message with a predefined `message_id`, configures the mocked `create` method to return this mock, calls `persist_system_message` with a sample investigation ID, user ID, and content, then asserts that the returned ID matches the mock's ID. It also verifies that the underlying create call received the correct role ("system"), content, default `include_in_llm_context` set to False, and `visible_in_ui` set to True.
        """
        investigation_id = uuid4()
        content = "Agent job started"

        mock_message = MagicMock()
        mock_message.message_id = 222
        mock_create.return_value = mock_message

        db = AsyncMock()
        message_id = await chat_persistence.persist_system_message(
            db=db,
            investigation_id=investigation_id,
            user_id=1,
            content=content,
        )

        assert message_id == 222
        call_args = mock_create.call_args[1]
        assert call_args["role"] == "system"
        assert call_args["content"] == content
        assert call_args["include_in_llm_context"] is False  # Default
        assert call_args["visible_in_ui"] is True  # Default

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_system_message_for_llm(self, mock_create):
        """
        Test persisting a system message intended for inclusion in LLM context.

        This test verifies that `chat_persistence.persist_system_message` correctly forwards the
        `include_in_llm_context` flag to the underlying CRUD layer when called with
        `include_in_llm_context=True`.

        The test sets up a mock `create` function that returns a dummy message object,
        invokes `persist_system_message` with sample identifiers and content, and then
        asserts that the `include_in_llm_context` argument passed to the mocked `create`
        call is `True`.
        """
        mock_message = MagicMock()
        mock_message.message_id = 333
        mock_create.return_value = mock_message

        db = AsyncMock()
        await chat_persistence.persist_system_message(
            db=db,
            investigation_id=uuid4(),
            user_id=1,
            content="System prompt",
            include_in_llm_context=True,
        )

        call_args = mock_create.call_args[1]
        assert call_args["include_in_llm_context"] is True


@pytest.mark.unit
class TestPersistToolCall:
    """Test persist_tool_call function."""

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_tool_call(self, mock_create):
        """
        Test that persisting a tool-call message correctly delegates to the CRUD layer and returns the generated message identifier.

        The test constructs a mock `tool_calls` payload representing an assistant-generated function call, configures the mocked `create` coroutine to return a `MagicMock` with a predefined `message_id`, and invokes :func:`chat_persistence.persist_tool_call` with a dummy asynchronous database session, an investigation UUID, and a user identifier.

        Assertions verify that:
        - The returned `message_id` matches the mock's `message_id` (ensuring the service forwards the CRUD result).
        - The underlying `create` call receives the expected keyword arguments:
          - `role` set to `"assistant"`,
          - `content` is `None` (tool calls carry no textual content),
          - `tool_calls` contains the exact payload supplied to the test,
          - `include_in_llm_context` is `True` so the tool call participates in subsequent LLM prompts.
        """
        investigation_id = uuid4()
        tool_calls = {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "search_timeline",
                "arguments": '{"query": "suspicious"}',
            },
        }

        mock_message = MagicMock()
        mock_message.message_id = 444
        mock_create.return_value = mock_message

        db = AsyncMock()
        message_id = await chat_persistence.persist_tool_call(
            db=db,
            investigation_id=investigation_id,
            user_id=1,
            tool_calls=tool_calls,
        )

        assert message_id == 444
        call_args = mock_create.call_args[1]
        assert call_args["role"] == "assistant"
        assert call_args["content"] is None
        assert call_args["tool_calls"] == tool_calls
        assert call_args["include_in_llm_context"] is True


@pytest.mark.unit
class TestPersistToolResponse:
    """Test persist_tool_response function."""

    @patch("app.services.chat_persistence.crud.create_message")
    async def test_persist_tool_response(self, mock_create):
        """
        Test persisting a tool response message.

        This unit test verifies that `chat_persistence.persist_tool_response` correctly creates a
        tool-response entry in the database and returns its identifier.

        The test sets up:
        - A mock `create` function that simulates the CRUD layer, returning a `MagicMock`
          with `message_id = 555`.
        - An asynchronous mock database connection `db`.

        It then calls `persist_tool_response` with a generated investigation ID,
        user ID, tool call identifier, response content, and tool name.

        Assertions confirm:
        - The returned `message_id` matches the mocked value (555).
        - The underlying `create` call receives the expected keyword arguments:
          - `role` set to `"tool"`
          - `content` matching the supplied text
          - `name` equal to the tool name
          - `tool_call_id` matching the provided identifier
          - `include_in_llm_context` is `True`.
        """
        investigation_id = uuid4()
        tool_call_id = "call_123"
        content = "Found 3 events matching query"
        name = "search_timeline"

        mock_message = MagicMock()
        mock_message.message_id = 555
        mock_create.return_value = mock_message

        db = AsyncMock()
        message_id = await chat_persistence.persist_tool_response(
            db=db,
            investigation_id=investigation_id,
            user_id=1,
            tool_call_id=tool_call_id,
            content=content,
            name=name,
        )

        assert message_id == 555
        call_args = mock_create.call_args[1]
        assert call_args["role"] == "tool"
        assert call_args["content"] == content
        assert call_args["name"] == name
        assert call_args["tool_call_id"] == tool_call_id
        assert call_args["include_in_llm_context"] is True


@pytest.mark.unit
class TestBuildConversationContext:
    """Test build_conversation_context function."""

    @patch("app.services.chat_persistence.crud.get_llm_context")
    async def test_build_context_basic(self, mock_get_context):
        """
        Test that building a basic conversation context retrieves messages from the database and returns them unchanged.

        Args:
            self: TestCase instance.
            mock_get_context (unittest.mock.AsyncMock): Mock for the database call that fetches conversation messages.

        Returns:
            None

        The test creates a fake investigation ID and a list of user/assistant messages, configures the mock to return this list, invokes `chat_persistence.build_conversation_context` with an asynchronous database mock, and asserts that the returned context matches the expected messages while verifying that the underlying get-context function was called exactly once.
        """
        investigation_id = uuid4()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        mock_get_context.return_value = messages

        db = AsyncMock()
        context = await chat_persistence.build_conversation_context(
            db=db,
            investigation_id=investigation_id,
        )

        assert context == messages
        mock_get_context.assert_called_once()

    @patch("app.services.chat_persistence.crud.get_llm_context")
    async def test_build_context_with_system_prompt(self, mock_get_context):
        """
        Test that `build_conversation_context` correctly inserts a system prompt at the beginning of the conversation history.

        The test sets up:
        - A mock `get_context` call that returns a single user message.
        - A `system_prompt` string to be injected.
        - An `AsyncMock` database instance passed to the function under test.

        It then calls :func:`chat_persistence.build_conversation_context` with the mocked database, a generated `investigation_id` and the provided `system_prompt`.

        Assertions verify that:
        - The resulting context contains two messages (the system prompt plus the original user message).
        - The first message has role `"system"` and its content matches `system_prompt`.
        - The second message retains the original role `"user"` and content `"Hello"`.
        """
        investigation_id = uuid4()
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        mock_get_context.return_value = messages

        system_prompt = "You are a forensic investigator."

        db = AsyncMock()
        context = await chat_persistence.build_conversation_context(
            db=db,
            investigation_id=investigation_id,
            system_prompt=system_prompt,
        )

        # System prompt should be first
        assert len(context) == 2
        assert context[0]["role"] == "system"
        assert context[0]["content"] == system_prompt
        assert context[1]["role"] == "user"
        assert context[1]["content"] == "Hello"

    @patch("app.services.chat_persistence.crud.get_llm_context")
    async def test_build_context_with_max_messages(self, mock_get_context):
        """
        Test that building conversation context respects the maximum number of messages parameter.

        This test creates a mock investigation ID and configures the `get_context` mock to return an empty list. It then calls :func:`chat_persistence.build_conversation_context` with `max_messages=10` and verifies that the underlying `get_context` function receives `max_messages` set to 10 in its keyword arguments.
        """
        investigation_id = uuid4()
        mock_get_context.return_value = []

        db = AsyncMock()
        await chat_persistence.build_conversation_context(
            db=db,
            investigation_id=investigation_id,
            max_messages=10,
        )

        call_args = mock_get_context.call_args[1]
        assert call_args["max_messages"] == 10

    @patch("app.services.chat_persistence.crud.get_llm_context")
    async def test_build_context_empty(self, mock_get_context):
        """
        Test that building a conversation context with an empty message list returns an empty list.

        Args:
            self: The test case instance.
            mock_get_context (unittest.mock.Mock): Mocked `get_context` function returning an empty list.

        Returns:
            None - asserts that the returned context is an empty list.
        """
        mock_get_context.return_value = []

        db = AsyncMock()
        context = await chat_persistence.build_conversation_context(
            db=db,
            investigation_id=uuid4(),
        )

        assert context == []

    @patch("app.services.chat_persistence.crud.get_llm_context")
    async def test_build_context_system_prompt_only(self, mock_get_context):
        """
        Test building conversation context when only a system prompt is provided.

        This test verifies that:
        - When the database returns an empty list of prior messages,
        - And a non-empty `system_prompt` argument is supplied,
        the `build_conversation_context` function returns a single message dictionary containing the system role and the exact prompt text. The resulting context should have length one, with `"role"` set to `"system"` and `"content"` matching the provided prompt.
        """
        mock_get_context.return_value = []
        system_prompt = "System instructions"

        db = AsyncMock()
        context = await chat_persistence.build_conversation_context(
            db=db,
            investigation_id=uuid4(),
            system_prompt=system_prompt,
        )

        assert len(context) == 1
        assert context[0]["role"] == "system"
        assert context[0]["content"] == system_prompt
