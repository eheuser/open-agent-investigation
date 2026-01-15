"""
Unit tests for chat history CRUD operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.crud.chat_history import (
    create_message,
    get_investigation_messages,
    get_llm_context,
    get_message_by_id,
    update_message,
    soft_delete_message,
    hard_delete_message,
    delete_message,
    delete_investigation_messages,
    get_message_count,
    get_message_with_tool_executions,
)
from app.models.chat_history import ChatMessage


@pytest.mark.unit
class TestCreateMessage:
    """Test create_message function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mocked asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session with:
        - `add` as a synchronous `MagicMock` to record added entities.
        - `commit` and `refresh` as `AsyncMock` instances to simulate asynchronous commit and refresh operations.

        Returns
        -------
        AsyncMock
            A mock session object with the described methods attached.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_message_minimal(self, mock_db):
        """
        Test that creating a chat message with only the required fields succeeds and populates default values.

        The test constructs minimal input parameters (investigation ID, user ID, and role) and calls :func:`create_message` with a mocked asynchronous database session. It then asserts that:

        * The database `add`, `commit` and `refresh` methods are each called exactly once.
        * The object passed to `add` is an instance of :class:`ChatMessage`.
        * The created message stores the supplied `investigation_id`, `user_id`, and `role`.
        * Optional fields receive their default values: `content` is `None`, `message_metadata` is an empty dict, `include_in_llm_context` is `True`, and `visible_in_ui` is `True`.

        This verifies that the function correctly handles minimal input while applying defaults for unspecified attributes.
        """
        investigation_id = uuid4()
        user_id = 1
        role = "user"

        result = await create_message(
            db=mock_db, investigation_id=investigation_id, user_id=user_id, role=role
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify message object
        added_message = mock_db.add.call_args[0][0]
        assert isinstance(added_message, ChatMessage)
        assert added_message.investigation_id == investigation_id
        assert added_message.user_id == user_id
        assert added_message.role == role
        assert added_message.content is None
        assert added_message.message_metadata == {}
        assert added_message.include_in_llm_context is True
        assert added_message.visible_in_ui is True

    async def test_create_message_full(self, mock_db):
        """
        Test creating a chat message with all optional fields populated.

        This test verifies that `create_message` correctly constructs and persists a
        message when every possible argument is provided:

        * `investigation_id` - unique identifier for the investigation.
        * `user_id` - identifier of the user who created the message.
        * `role` - role of the sender (e.g., `assistant`).
        * `content` - textual content of the message.
        * `name` - optional name associated with the sender.
        * `tool_calls` - dictionary describing any tool calls made by the assistant.
        * `tool_call_id` - identifier linking the message to a specific tool call.
        * `metadata` - arbitrary key-value pairs storing additional context.
        * `include_in_llm_context` - flag indicating whether the message should be
          included in prompts sent to LLMs.
        * `visible_in_ui` - flag controlling visibility of the message in the UI.
        * `message_type` - categorisation of the message (e.g., `assistant_answer`).
        * `parent_message_id` - identifier of the parent message, if any.

        The test asserts that the ORM object passed to `mock_db.add` contains the
        exact values supplied to `create_message`, ensuring proper field mapping and
        that no data is lost during creation.
        """
        investigation_id = uuid4()

        result = await create_message(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            role="assistant",
            content="Response text",
            name="agent",
            tool_calls={"calls": []},
            tool_call_id="call_123",
            metadata={"intent": "search", "confidence": 0.95},
            include_in_llm_context=True,
            visible_in_ui=True,
            message_type="assistant_answer",
            parent_message_id=1,
        )

        added_message = mock_db.add.call_args[0][0]
        assert added_message.role == "assistant"
        assert added_message.content == "Response text"
        assert added_message.name == "agent"
        assert added_message.tool_calls == {"calls": []}
        assert added_message.tool_call_id == "call_123"
        assert added_message.message_metadata == {"intent": "search", "confidence": 0.95}
        assert added_message.message_type == "assistant_answer"
        assert added_message.parent_message_id == 1

    async def test_create_message_system_role(self, mock_db):
        """
        Test that creating a message with the role set to `system` correctly stores the role in the database entry.

        The test invokes :func:`create_message` with a mock asynchronous database connection, a random investigation identifier, a user identifier of `1`, the role `"system"`, and sample content. It then inspects the arguments passed to `mock_db.add` to verify that the resulting message object has its `role` attribute set to `"system"`.

        Parameters
        ----------
        self : unittest.TestCase
            The test case instance.
        mock_db : AsyncMock
            A mocked asynchronous database interface providing `add` and other coroutine methods used by :func:`create_message`.
        """
        result = await create_message(
            db=mock_db, investigation_id=uuid4(), user_id=1, role="system", content="System prompt"
        )

        added_message = mock_db.add.call_args[0][0]
        assert added_message.role == "system"

    async def test_create_message_tool_role(self, mock_db):
        """
        Test that creating a message with the role set to `tool` correctly stores the tool-specific attributes.\n\nThe test invokes :func:`create_message` with `role=\"tool\"` and provides a JSON string for `content`, along with `name` and `tool_call_id` values. After awaiting the creation, it inspects the object passed to the mocked database's `add` method and asserts that:\n\n* The `role` attribute of the added message is `\"tool\"`.\n* The `name` attribute matches the supplied tool name (e.g., `\"search_events\"`).\n* The `tool_call_id` attribute matches the supplied identifier (e.g., `\"call_123\"`).\n\nThis ensures that messages representing tool responses are persisted with the correct metadata.
        """
        result = await create_message(
            db=mock_db,
            investigation_id=uuid4(),
            user_id=1,
            role="tool",
            content='{"result": "success"}',
            name="search_events",
            tool_call_id="call_123",
        )

        added_message = mock_db.add.call_args[0][0]
        assert added_message.role == "tool"
        assert added_message.name == "search_events"
        assert added_message.tool_call_id == "call_123"


@pytest.mark.unit
class TestGetInvestigationMessages:
    """Test get_investigation_messages function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session.

        Returns:
            AsyncMock: A mock object simulating an async database connection/session.
        """
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_messages(self):
        """
        Create and return a list of example chat message objects for testing purposes.

        The function generates a unique `investigation_id` using :func:`uuid4` and constructs two mock
        message instances:

        * A user-originated message with `message_id` 1 and the content `"Hello"`.
        * An assistant-originated message with `message_id` 2 and the content `"Hi there"`.

        Both messages are associated with the same `investigation_id` and have `deleted_at` set to
        `None`, indicating they are not soft-deleted.

        Returns:
            list[MagicMock]: A list containing the two mock message objects.
        """
        investigation_id = uuid4()
        messages = [
            MagicMock(
                message_id=1,
                investigation_id=investigation_id,
                role="user",
                content="Hello",
                deleted_at=None,
            ),
            MagicMock(
                message_id=2,
                investigation_id=investigation_id,
                role="assistant",
                content="Hi there",
                deleted_at=None,
            ),
        ]
        return messages

    async def test_get_messages_all(self, mock_db, sample_messages):
        """
        Test retrieving all messages associated with a given investigation.

        Args:
            self: Test case instance.
            mock_db (MagicMock): Mocked asynchronous database session used to execute queries.
            sample_messages (list): Predefined list of message objects returned by the mocked query.

        Returns:
            None

        The test creates a unique investigation identifier, configures the mock database to return `sample_messages` when queried, invokes `get_investigation_messages`, and asserts that the result contains exactly two messages matching the sample data. It also verifies that the database execute method was called once.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_messages
        mock_db.execute.return_value = mock_result

        result = await get_investigation_messages(db=mock_db, investigation_id=investigation_id)

        assert len(result) == 2
        assert result == sample_messages
        mock_db.execute.assert_called_once()

    async def test_get_messages_with_limit(self, mock_db, sample_messages):
        """
        Test that retrieving investigation messages respects the specified limit.

        Args:
            self: TestCase instance.
            mock_db (MagicMock): Mocked asynchronous database session with an execute method.
            sample_messages (list): List of pre-created message objects used as fixture data.

        The test creates a unique investigation ID, configures the mock to return only the first message when the query is executed, calls `get_investigation_messages` with `limit=1`, and asserts that exactly one message is returned. It also verifies that the database's `execute` method was invoked once.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_messages[:1]
        mock_db.execute.return_value = mock_result

        result = await get_investigation_messages(
            db=mock_db, investigation_id=investigation_id, limit=1
        )

        assert len(result) == 1
        mock_db.execute.assert_called_once()

    async def test_get_messages_with_offset(self, mock_db, sample_messages):
        """
        Test that retrieving investigation messages with an offset correctly skips the specified number of initial records and returns the remaining messages.

        Args:
            self: Test case instance.
            mock_db (MagicMock): Mocked asynchronous database session used to simulate query execution.
            sample_messages (list): A list of pre-created message objects representing the full set of messages for an investigation.

        Returns:
            None: The test asserts that the result contains only the expected subset of messages after applying the offset.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_messages[1:]
        mock_db.execute.return_value = mock_result

        result = await get_investigation_messages(
            db=mock_db, investigation_id=investigation_id, offset=1
        )

        assert len(result) == 1
        mock_db.execute.assert_called_once()

    async def test_get_messages_llm_only(self, mock_db):
        """
        Test that `get_investigation_messages` correctly retrieves only messages marked for inclusion in the LLM context.

        The test sets up:
        - A random `investigation_id`.
        - Two mock message objects with `include_in_llm_context=True` and `deleted_at=None`.
        - A mocked database execution returning these messages.

        It then calls `get_investigation_messages` with `include_in_llm_only=True` and verifies that:
        - The returned list contains exactly the two LLM-eligible messages.
        - The database's `execute` method is invoked once.
        """
        investigation_id = uuid4()

        llm_messages = [
            MagicMock(include_in_llm_context=True, deleted_at=None),
            MagicMock(include_in_llm_context=True, deleted_at=None),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = llm_messages
        mock_db.execute.return_value = mock_result

        result = await get_investigation_messages(
            db=mock_db, investigation_id=investigation_id, include_in_llm_only=True
        )

        assert len(result) == 2
        mock_db.execute.assert_called_once()

    async def test_get_messages_visible_only(self, mock_db):
        """
        Test that `get_investigation_messages` returns only messages marked as visible in the UI when the `visible_in_ui_only` flag is set.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_db : MagicMock
            Mocked asynchronous database session used to simulate query execution.

        The test sets up a mock investigation ID and a list containing a single message with `visible_in_ui=True` and `deleted_at=None`. It configures the mock database to return this list when queried, invokes `get_investigation_messages` with `visible_in_ui_only=True`, and asserts that exactly one message is returned. Additionally, it verifies that the database's `execute` method was called exactly once.
        """
        investigation_id = uuid4()

        visible_messages = [MagicMock(visible_in_ui=True, deleted_at=None)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = visible_messages
        mock_db.execute.return_value = mock_result

        result = await get_investigation_messages(
            db=mock_db, investigation_id=investigation_id, visible_in_ui_only=True
        )

        assert len(result) == 1
        mock_db.execute.assert_called_once()

    async def test_get_messages_exclude_deleted(self, mock_db):
        """
        Test that retrieving messages for a given investigation excludes entries marked as deleted when the `include_deleted` flag is False.

        Args:
            self: Test case instance.
            mock_db: Asynchronous database session mock used to simulate query execution.

        The test creates a unique investigation identifier, mocks a list containing a single non-deleted message (`deleted_at=None`), and configures the database mock to return this list when `execute` is called. It then calls `get_investigation_messages` with `include_deleted=False` and asserts that only the non-deleted message is returned and that the database execute method was invoked exactly once.
        """
        investigation_id = uuid4()

        non_deleted_messages = [MagicMock(deleted_at=None)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = non_deleted_messages
        mock_db.execute.return_value = mock_result

        result = await get_investigation_messages(
            db=mock_db, investigation_id=investigation_id, include_deleted=False
        )

        assert len(result) == 1
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetLLMContext:
    """Test get_llm_context function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session using `AsyncMock`. This helper is intended for use in unit tests where a lightweight stand-in for an async DB connection is required. Returns an `AsyncMock` instance that mimics the interface of the real database session.
        """
        db = AsyncMock()
        return db

    @patch("app.crud.chat_history.get_investigation_messages")
    async def test_get_llm_context(self, mock_get_messages, mock_db):
        """
        Test that `get_llm_context` returns messages formatted for OpenAI and respects the provided query parameters.

        The test creates a temporary investigation identifier and mocks two message objects whose `to_openai_format` method yields dictionaries representing user and assistant roles. The mock for `get_investigation_messages` is configured to return these mocked messages.

        The function under test is called with a mock database connection, the generated investigation ID, and a maximum of ten messages. Assertions verify that:
        - Exactly two formatted messages are returned.
        - The first message matches the expected user payload.
        - The second message matches the expected assistant payload.
        - `get_investigation_messages` was invoked once with `include_in_llm_only=True` and `include_deleted=False`, confirming correct filtering behavior.
        """
        investigation_id = uuid4()

        # Create mock messages with to_openai_format method
        msg1 = MagicMock()
        msg1.to_openai_format.return_value = {"role": "user", "content": "Hello"}
        msg2 = MagicMock()
        msg2.to_openai_format.return_value = {"role": "assistant", "content": "Hi"}

        mock_get_messages.return_value = [msg1, msg2]

        result = await get_llm_context(
            db=mock_db, investigation_id=investigation_id, max_messages=10
        )

        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi"}

        # Verify get_investigation_messages was called with correct params
        mock_get_messages.assert_called_once()
        call_kwargs = mock_get_messages.call_args.kwargs
        assert call_kwargs["include_in_llm_only"] is True
        assert call_kwargs["include_deleted"] is False


@pytest.mark.unit
class TestGetMessageByID:
    """Test get_message_by_id function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mocked asynchronous database session using AsyncMock for use in unit tests. This mock simulates the behavior of an async DB connection without performing real I/O.
        """
        db = AsyncMock()
        return db

    async def test_get_message_found(self, mock_db):
        """
        Test that retrieving an existing message by its identifier returns the correct message object and invokes the database execute method exactly once. The test sets up a mock database session, configures the expected scalar result, calls `get_message_by_id` with the mock session and a sample `message_id`, then asserts that the returned value matches the mocked message and that the `execute` method was called a single time.
        """
        message_id = 1
        expected_message = MagicMock(message_id=message_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_message
        mock_db.execute.return_value = mock_result

        result = await get_message_by_id(mock_db, message_id)

        assert result == expected_message
        mock_db.execute.assert_called_once()

    async def test_get_message_not_found(self, mock_db):
        """
        Test that retrieving a message by an ID that does not exist returns `None` and that the database execute method is called exactly once.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate the query.

        Returns:
            None - this function asserts expectations rather than returning a value.
        """
        message_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_message_by_id(mock_db, message_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestUpdateMessage:
    """Test update_message function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure an asynchronous mock database session for testing.

        The returned object mimics an async SQLAlchemy session with `commit` and `refresh` methods also mocked as coroutines, allowing test code to await these operations without performing real I/O. This helper isolates unit tests from the actual database layer while preserving the expected async interface.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_update_message_content(self, mock_get_message, mock_db):
        """
        Test that updating a message's content correctly modifies the stored message object, triggers a database commit, and refreshes the entity.

        The test sets up a mock message with an initial `content` value, patches the retrieval function to return this mock, and then calls :func:`update_message` with new content. After awaiting the update, it asserts that:

        * The mock message's `content` attribute has been updated to the provided new string.
        * The database session's `commit` method was called exactly once.
        * The database session's `refresh` method was called exactly once.

        This ensures the update logic performs in-place modification and persists changes as expected.
        """
        message_id = 1
        existing_message = MagicMock(message_id=message_id, content="Old content")
        mock_get_message.return_value = existing_message

        result = await update_message(db=mock_db, message_id=message_id, content="New content")

        assert existing_message.content == "New content"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_update_message_metadata(self, mock_get_message, mock_db):
        """
        Test that updating a message's metadata replaces the existing metadata with the new values and commits the change to the database. The test mocks retrieval of an existing message, invokes `update_message` with new metadata, asserts that the message object's `message_metadata` attribute matches the provided dictionary, and verifies that `db.commit` is called exactly once.
        """
        message_id = 1
        existing_message = MagicMock(message_id=message_id, message_metadata={"old": "data"})
        mock_get_message.return_value = existing_message

        new_metadata = {"new": "data", "key": "value"}
        result = await update_message(db=mock_db, message_id=message_id, metadata=new_metadata)

        # Metadata should be replaced
        assert existing_message.message_metadata == new_metadata
        mock_db.commit.assert_called_once()

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_update_message_flags(self, mock_get_message, mock_db):
        """
        Test updating message flags.\n\nThis test verifies that the `update_message` coroutine correctly modifies the `include_in_llm_context` and `visible_in_ui` attributes of an existing message record. It uses a mocked `get_message` call to return a pre-populated `MagicMock` instance, then calls `update_message` with new flag values. After awaiting the update, the test asserts that the original mock object's flags have been set to `False`, confirming that the function mutates the persisted message as expected. The database interaction itself is mocked via `mock_db` to isolate the logic under test.
        """
        message_id = 1
        existing_message = MagicMock(
            message_id=message_id, include_in_llm_context=True, visible_in_ui=True
        )
        mock_get_message.return_value = existing_message

        result = await update_message(
            db=mock_db, message_id=message_id, include_in_llm_context=False, visible_in_ui=False
        )

        assert existing_message.include_in_llm_context is False
        assert existing_message.visible_in_ui is False

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_update_message_not_found(self, mock_get_message, mock_db):
        """
        Test that attempting to update a message that does not exist returns `None` and does not commit any changes to the database.

        Args:
            self: The test case instance.
            mock_get_message: Mock for the function that retrieves a message by ID; configured to return `None` to simulate a missing record.
            mock_db: Mocked asynchronous database session used by `update_message`.

        Returns:
            None. The function asserts that the result of `update_message` is `None` and verifies that `mock_db.commit` was never called.
        """
        message_id = 999
        mock_get_message.return_value = None

        result = await update_message(db=mock_db, message_id=message_id, content="New content")

        assert result is None
        mock_db.commit.assert_not_called()


@pytest.mark.unit
class TestSoftDeleteMessage:
    """Test soft_delete_message function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mocked asynchronous database session.

        The returned object mimics an async SQLAlchemy session with coroutine methods
        `commit()` and `refresh()`, each implemented as `AsyncMock` instances. This mock
        can be used in unit tests to simulate database interactions without requiring
        a real database connection. The function takes no arguments and always returns
        the same type of mock session.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_soft_delete_message(self, mock_get_message, mock_db):
        """
        Test the soft-delete operation for a chat message.

        This test verifies that invoking :func:`soft_delete_message` with a valid `message_id` updates the corresponding
        message record as follows:

        * Sets `deleted_at` to a non-null timestamp, indicating the message is marked as deleted.
        * Clears `include_in_llm_context` (sets it to `False`) so the message will no longer be included in LLM prompts.
        * Commits the transaction and refreshes the object via the provided asynchronous database session.

        The test uses mocks for the underlying `get_message` call and the database session to ensure that:
        * The retrieved message is correctly mutated.
        * `commit` and `refresh` are each called exactly once.
        """
        message_id = 1
        existing_message = MagicMock(
            message_id=message_id, deleted_at=None, include_in_llm_context=True
        )
        mock_get_message.return_value = existing_message

        result = await soft_delete_message(mock_db, message_id)

        assert existing_message.deleted_at is not None
        assert existing_message.include_in_llm_context is False
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_soft_delete_not_found(self, mock_get_message, mock_db):
        """
        Test that attempting to soft-delete a message that does not exist returns `None` and leaves the database unchanged (i.e., no commit is issued). The test sets up a mock `get_message` call to return `None` for the given `message_id`, invokes :func:`soft_delete_message`, and asserts both the return value and that `mock_db.commit` was never called.
        """
        message_id = 999
        mock_get_message.return_value = None

        result = await soft_delete_message(mock_db, message_id)

        assert result is None
        mock_db.commit.assert_not_called()


@pytest.mark.unit
class TestHardDeleteMessage:
    """Test hard_delete_message function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for testing.\n\nThis helper constructs an :class:`unittest.mock.AsyncMock` instance representing a database connection. The returned object includes a `commit` attribute that is itself an `AsyncMock`, allowing test code to await `db.commit()` without performing any real I/O. This mock can be injected into services or repositories that expect an async DB session, enabling isolated unit tests of CRUD logic.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_hard_delete_message_success(self, mock_db):
        """
        Test that hard deleting an existing message returns True and triggers the appropriate database calls.

        Parameters:
            self: Test case instance.
            mock_db: Mocked asynchronous database connection providing execute and commit methods.

        The test sets up a mock result with a rowcount of 1 to simulate a successful deletion, invokes `hard_delete_message` with the mocked DB and a sample message ID, asserts that the function returns `True`, and verifies that `execute` and `commit` were each called exactly once.
        """
        message_id = 1

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await hard_delete_message(mock_db, message_id)

        assert result is True
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_hard_delete_message_not_found(self, mock_db):
        """
        Test that attempting to hard-delete a message that does not exist returns `False` and still commits the transaction.

        Args:
            self: The unittest.TestCase instance.
            mock_db: A mocked asynchronous database connection providing `execute` and `commit` methods.

        The test sets up `mock_db.execute` to return a result with `rowcount` equal to 0, indicating that no rows were affected. It then calls :func:`hard_delete_message` with a non-existent `message_id` and asserts that the function returns `False` while ensuring `mock_db.commit` is invoked exactly once.
        """
        message_id = 999

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await hard_delete_message(mock_db, message_id)

        assert result is False
        mock_db.commit.assert_called_once()


@pytest.mark.unit
class TestDeleteInvestigationMessages:
    """Test delete_investigation_messages function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session with its `commit` method also mocked as an awaitable. This allows test code to invoke `await db.commit()` without performing any real I/O.

        Returns:
            AsyncMock: A mock object representing the database session, with an asynchronous `commit` attribute ready for awaiting.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_delete_investigation_messages(self, mock_db):
        """
        Test that deleting all messages associated with a given investigation ID invokes the database execution and commit operations, returns the number of rows affected, and correctly handles the mocked asynchronous DB interaction. Parameters: self - test case instance; mock_db - MagicMock simulating an async database connection with execute and commit methods. The function creates a random investigation_id, configures the mock to return a result with rowcount 10, calls delete_investigation_messages, asserts that the returned count equals 10, and verifies that execute and commit were each called exactly once.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 10
        mock_db.execute.return_value = mock_result

        result = await delete_investigation_messages(mock_db, investigation_id)

        assert result == 10
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_delete_investigation_messages_none_found(self, mock_db):
        """
        Test that deleting investigation messages returns zero when no matching records are found.

        Args:
            self: Test case instance.
            mock_db: Mocked asynchronous database connection used to simulate the execute call.

        Returns:
            None (assertions validate that the function under test returns 0).
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await delete_investigation_messages(mock_db, investigation_id)

        assert result == 0


@pytest.mark.unit
class TestGetMessageCount:
    """Test get_message_count function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for use in tests.

        Parameters
            self: The instance invoking the method, typically a test case or helper object.

        Returns
            AsyncMock: A mocked async database session that can be configured with expected calls and return values.
        """
        db = AsyncMock()
        return db

    async def test_get_message_count_all(self, mock_db):
        """
        Test that `get_message_count` correctly retrieves the total number of messages for a given investigation ID by mocking the database execution and verifying the returned scalar value and that the execute method is called exactly once.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_db.execute.return_value = mock_result

        result = await get_message_count(mock_db, investigation_id)

        assert result == 10
        mock_db.execute.assert_called_once()

    async def test_get_message_count_llm_only(self, mock_db):
        """
        Test that `get_message_count` correctly returns the number of messages marked as LLM-only when `include_in_llm_only` is set to `True`. The test creates a mock database session, configures its `execute` method to return a result whose `scalar_one` call yields `5`, invokes `get_message_count` with a randomly generated `investigation_id` and the flag enabled, and asserts that the returned count matches the mocked value.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_db.execute.return_value = mock_result

        result = await get_message_count(mock_db, investigation_id, include_in_llm_only=True)

        assert result == 5

    async def test_get_message_count_zero(self, mock_db):
        """
        Test that `get_message_count` correctly returns zero when the database contains no messages for the given investigation ID.

        Args:
            self: Test case instance (unused).
            mock_db: A mocked asynchronous database session whose `execute` method returns a result with `scalar_one` set to 0.

        Returns:
            None. The test asserts that the function under test returns `0`.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db.execute.return_value = mock_result

        result = await get_message_count(mock_db, investigation_id)

        assert result == 0


@pytest.mark.unit
class TestGetMessageWithToolExecutions:
    """Test get_message_with_tool_executions function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session for use in tests.

        Returns
        -------
        AsyncMock
            A mocked async database object that mimics the interface of the real DB session.
        """
        db = AsyncMock()
        return db

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_get_message_with_executions(self, mock_get_message, mock_db):
        """
        Test retrieving a chat message along with its associated tool executions.

        Args:
            self: The test case instance.
            mock_get_message (unittest.mock.AsyncMock): Mock for the function that fetches a message by ID, configured to return a MagicMock representing the message.
            mock_db (unittest.mock.AsyncMock): Mocked asynchronous database session used to execute queries for tool executions.

        The test sets up:
        - A fake message with `message_id` equal to 1.
        - A mocked tool execution object whose `to_dict` method returns a dictionary containing `execution_id`, `tool_name`, and `status`.
        - The database mock to return the list of mocked tool executions when queried.

        Calls `await get_message_with_tool_executions(mock_db, message_id)` and asserts that:
        - The result is not None.
        - The `"message"` key in the result matches the mocked message object.
        - Exactly one tool execution is present in the `"tool_executions"` list.
        - The first tool execution's `"tool_name"` equals `"search_events"`.
        """
        message_id = 1
        message = MagicMock(message_id=message_id)
        mock_get_message.return_value = message

        # Mock tool executions
        tool_exec = MagicMock()
        tool_exec.to_dict.return_value = {
            "execution_id": 1,
            "tool_name": "search_events",
            "status": "completed",
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tool_exec]
        mock_db.execute.return_value = mock_result

        result = await get_message_with_tool_executions(mock_db, message_id)

        assert result is not None
        assert result["message"] == message
        assert len(result["tool_executions"]) == 1
        assert result["tool_executions"][0]["tool_name"] == "search_events"

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_get_message_with_no_executions(self, mock_get_message, mock_db):
        """
        Test that retrieving a message without associated tool executions returns an empty list for the "tool_executions" key. The test sets up mocks for the database query and the `get_message` helper, invokes `get_message_with_tool_executions`, and asserts that the resulting dictionary contains `"tool_executions": []`.
        """
        message_id = 1
        message = MagicMock(message_id=message_id)
        mock_get_message.return_value = message

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_message_with_tool_executions(mock_db, message_id)

        assert result["tool_executions"] == []

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_get_message_with_executions_not_found(self, mock_get_message, mock_db):
        """
        Test that retrieving a message with its tool executions returns `None` when the specified message ID does not exist in the database. The mock for `get_message` is configured to return `None`, and the function under test should propagate this result without raising an exception.
        """
        message_id = 999
        mock_get_message.return_value = None

        result = await get_message_with_tool_executions(mock_db, message_id)

        assert result is None


@pytest.mark.unit
class TestChatHistoryCRUDEdgeCases:
    """Test edge cases for chat history CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mocked asynchronous database session for testing.

        The returned object mimics an async SQLAlchemy session with:
        * `add` - a synchronous `MagicMock` used to record added entities.
        * `commit` - an `AsyncMock` representing the commit coroutine.
        * `refresh` - an `AsyncMock` representing the refresh coroutine.

        This mock enables unit tests to verify CRUD operations without requiring a real database.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_message_with_unicode(self, mock_db):
        """
        Test creating a chat message containing Unicode characters.

        This test verifies that `create_message` correctly stores messages with non-ASCII content, such as Japanese text and emoji. It:

        - Calls `create_message` with a Unicode string for the `content` parameter.
        - Retrieves the message object passed to the mocked database's `add` method.
        - Asserts that the expected Unicode substrings ("質問" and "🔍") are present in the stored message content.
        """
        result = await create_message(
            db=mock_db,
            investigation_id=uuid4(),
            user_id=1,
            role="user",
            content="質問: データを検索 🔍",
        )

        added_message = mock_db.add.call_args[0][0]
        assert "質問" in added_message.content
        assert "🔍" in added_message.content

    async def test_create_message_with_complex_metadata(self, mock_db):
        """
        Test creating a chat message with complex nested metadata.

        This test verifies that `create_message` correctly stores and preserves deeply nested metadata structures when inserting a new message into the database.

        Steps:
        1. Define a `complex_metadata` dictionary containing multiple nesting levels, including strings, floats, and list values.
        2. Call `create_message` with a mock asynchronous database connection, passing the investigation ID, user ID, role, and the complex metadata.
        3. Retrieve the message object that was passed to the mocked `db.add` method.
        4. Assert that the nested list under `message_metadata["nested"]["level1"]["level2"]` matches the original list `["item1", "item2"]`.

        Ensures that metadata is not altered or flattened during the creation process.
        """
        complex_metadata = {
            "intent": "search",
            "confidence": 0.95,
            "nested": {"level1": {"level2": ["item1", "item2"]}},
        }

        result = await create_message(
            db=mock_db, investigation_id=uuid4(), user_id=1, role="user", metadata=complex_metadata
        )

        added_message = mock_db.add.call_args[0][0]
        assert added_message.message_metadata["nested"]["level1"]["level2"] == ["item1", "item2"]

    async def test_create_message_with_very_long_content(self, mock_db):
        """
        Test that creating a message with an extremely long content string succeeds and stores the full text.

        The test generates a payload consisting of 100 000 characters, invokes `create_message` with typical parameters (a mock database connection, a random investigation ID, a user identifier, and the role `"user"`), and then verifies that the `add` method on the mock DB was called with a message whose `content` attribute retains the original length. This ensures that the implementation does not truncate or otherwise mishandle very large message bodies.
        """
        long_content = "A" * 100000

        result = await create_message(
            db=mock_db, investigation_id=uuid4(), user_id=1, role="user", content=long_content
        )

        added_message = mock_db.add.call_args[0][0]
        assert len(added_message.content) == 100000

    @patch("app.crud.chat_history.get_message_by_id")
    async def test_update_message_with_none_values(self, mock_get_message, mock_db):
        """
        Test that providing `None` for optional update fields leaves the existing message attributes unchanged.

        Args:
            self: Test case instance.
            mock_get_message: Mocked coroutine that retrieves the current message from the database.
            mock_db: Mocked asynchronous database connection used by :func:`update_message`.

        The test sets up a fake message with `message_id` 1, `content` set to `"Original content"`, and `include_in_llm_context` set to `True`. It then calls :func:`update_message` with all optional update parameters (`content`, `metadata`, `include_in_llm_context`, `visible_in_ui`) passed as `None`.

        Assertions:
            * The original `content` remains `"Original content"`.
            * The original `include_in_llm_context` flag remains `True`.
        """
        message_id = 1
        existing_message = MagicMock(
            message_id=message_id, content="Original content", include_in_llm_context=True
        )
        mock_get_message.return_value = existing_message

        # Update with all None values
        result = await update_message(
            db=mock_db,
            message_id=message_id,
            content=None,
            metadata=None,
            include_in_llm_context=None,
            visible_in_ui=None,
        )

        # Original values should be preserved
        assert existing_message.content == "Original content"
        assert existing_message.include_in_llm_context is True
