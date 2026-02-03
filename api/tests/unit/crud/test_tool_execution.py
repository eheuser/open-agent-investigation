import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.crud.tool_execution import (
    create_tool_execution,
    update_tool_execution,
    complete_tool_execution,
    get_tool_execution,
    get_message_tool_executions,
    get_latest_executing_tool,
)
from app.models.tool_execution import ToolExecution


@pytest.mark.unit
class TestCreateToolExecution:
    """Test create_tool_execution function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for testing.

        This helper constructs an `AsyncMock` instance that mimics the essential
        behaviour of a SQLAlchemy async session used in the application. The mock
        provides:

        * `add` - a regular :class:`unittest.mock.MagicMock` to record calls to
          `session.add(...)`.
        * `commit` - an :class:`unittest.mock.AsyncMock` representing the asynchronous
          commit operation.
        * `refresh` - an :class:`unittest.mock.AsyncMock` for the async refresh call.

        The returned object can be injected into functions that expect an async DB
        session, allowing unit tests to verify interaction without requiring a real
        database connection.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_tool_execution_minimal(self, mock_db):
        """
        Test creating a tool execution record with only the required parameters.

        This test verifies that `create_tool_execution` correctly:
        - Calls the database session methods `add`, `commit`, and `refresh` exactly once.
        - Constructs a `ToolExecution` instance with the supplied `chat_message_id` and `tool_name`.
        - Sets default values for optional fields: `display_name` defaults to the provided `tool_name`, `arguments` defaults to an empty dictionary, and `status` defaults to `"executing"`.

        The test uses a mocked database session (`mock_db`) to isolate the function's behavior from actual persistence logic.
        """
        chat_message_id = 1
        tool_name = "search_events"

        result = await create_tool_execution(
            db=mock_db,
            chat_message_id=chat_message_id,
            tool_name=tool_name,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify tool execution object
        added_execution = mock_db.add.call_args[0][0]
        assert isinstance(added_execution, ToolExecution)
        assert added_execution.chat_message_id == chat_message_id
        assert added_execution.tool_name == tool_name
        assert added_execution.display_name == tool_name  # Defaults to tool_name
        assert added_execution.arguments == {}
        assert added_execution.status == "executing"

    async def test_create_tool_execution_full(self, mock_db):
        """
        Test that creating a tool execution with all possible arguments correctly constructs and persists a ToolExecution record.

        Parameters
        ----------
        self : object
            The test case instance (unused directly in the test logic).
        mock_db : unittest.mock.AsyncMock or similar
            A mock database session whose `add` method is inspected to verify that the created
            ToolExecution instance contains the expected attribute values.

        The test invokes `create_tool_execution` with a full set of parameters:
        - `chat_message_id` - identifier of the related chat message.
        - `tool_name` - internal name of the tool being executed.
        - `display_name` - human-readable name for display purposes.
        - `arguments` - dictionary of arguments passed to the tool.
        - `execution_number` - sequential number of this execution within the conversation.
        - `max_tools` - maximum allowed concurrent tool executions.

        After awaiting the function, the test extracts the object passed to `mock_db.add` and asserts that each attribute on the resulting
        ToolExecution instance matches the corresponding input value. No explicit return value is checked; the primary verification is performed via these assertions.
        """
        chat_message_id = 1
        tool_name = "search_events"
        display_name = "Search Events"
        arguments = {"query": "failed login", "limit": 100}
        execution_number = 1
        max_tools = 10

        result = await create_tool_execution(
            db=mock_db,
            chat_message_id=chat_message_id,
            tool_name=tool_name,
            display_name=display_name,
            arguments=arguments,
            execution_number=execution_number,
            max_tools=max_tools,
        )

        added_execution = mock_db.add.call_args[0][0]
        assert added_execution.tool_name == tool_name
        assert added_execution.display_name == display_name
        assert added_execution.arguments == arguments
        assert added_execution.execution_number == execution_number
        assert added_execution.max_tools == max_tools

    async def test_create_tool_execution_with_complex_arguments(self, mock_db):
        """
        Test that creating a tool execution with a nested argument structure correctly stores the provided arguments in the database mock.

        The test builds a complex `arguments` dictionary containing strings, nested dictionaries, and lists, then calls :func:`create_tool_execution` with a mocked database connection, a chat message identifier, and a tool name. After awaiting the coroutine, it inspects the call made to `mock_db.add` and asserts that the `arguments` attribute of the added execution object matches the original complex dictionary, ensuring that argument serialization and storage behave as expected.
        """
        arguments = {
            "query": "test",
            "filters": {
                "event_type": ["login", "logout"],
                "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            },
            "nested_list": [1, 2, [3, 4]],
        }

        result = await create_tool_execution(
            db=mock_db,
            chat_message_id=1,
            tool_name="complex_search",
            arguments=arguments,
        )

        added_execution = mock_db.add.call_args[0][0]
        assert added_execution.arguments == arguments


@pytest.mark.unit
class TestUpdateToolExecution:
    """Test update_tool_execution function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session.

        The returned object mimics an async SQLAlchemy session with `commit` and `refresh` methods also mocked as asynchronous callables. This allows unit tests to simulate database interactions without requiring a real database connection.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_update_tool_execution_result(self, mock_db):
        """
        Test that updating a tool execution record correctly stores the provided result and triggers database commit and refresh operations. The test mocks the retrieval of an existing `ToolExecution` instance, invokes `update_tool_execution` with a sample result payload, and asserts that the execution object's `result` attribute is updated while ensuring the mock database's `commit` and `refresh` methods are called exactly once.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        # Mock get_tool_execution
        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            result = {"events": [{"id": 1}, {"id": 2}]}
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result=result,
            )

        assert existing_execution.result == result
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_update_tool_execution_summary(self, mock_db):
        """
        Test that updating a tool execution record correctly stores the provided result summary.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_db : AsyncMock or similar
            A mocked database session/connection used by the CRUD function.

        The test creates a `ToolExecution` instance representing an existing execution, patches the `get_tool_execution` function to return this instance, and then calls `update_tool_execution` with a new `result_summary`. After awaiting the update, it asserts that the original `ToolExecution` object's `result_summary` attribute has been updated to the supplied summary.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            summary = "Found 42 events"
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result_summary=summary,
            )

        assert existing_execution.result_summary == summary

    async def test_update_tool_execution_status_completed(self, mock_db):
        """
        Test that updating a tool execution's status to "completed" correctly modifies the stored record.

        Args:
            self: The test case instance.
            mock_db: A mocked database session injected by the test framework.

        The test creates a `ToolExecution` object with an initial status of `"executing"` and patches the `get_tool_execution` function to return this object. It then calls `update_tool_execution` with `status="completed"` and verifies that:
        - The execution object's `status` attribute is updated to `"completed"`.
        - The `finished_at` timestamp is set (i.e., not `None`).
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                status="completed",
            )

        assert existing_execution.status == "completed"
        assert existing_execution.finished_at is not None

    async def test_update_tool_execution_status_failed(self, mock_db):
        """
        Test that updating a tool execution's status to "failed" correctly modifies the existing `ToolExecution` instance, setting its `status` field to "failed" and populating the `finished_at` timestamp. The test uses a mocked database session (`mock_db`) and patches the `get_tool_execution` function to return a predefined `ToolExecution` object with an initial status of "executing". It then calls `update_tool_execution` with the target execution ID and new status, and asserts that the object's status and completion time have been updated as expected.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                status="failed",
            )

        assert existing_execution.status == "failed"
        assert existing_execution.finished_at is not None

    async def test_update_tool_execution_not_found(self, mock_db):
        """
        Test that updating a tool execution that does not exist returns `None` and does not commit any changes to the database. The function patches `get_tool_execution` to simulate a missing record, calls `update_tool_execution` with a sample result payload, and asserts that the returned value is `None` while verifying that `db.commit` was never invoked.
        """
        execution_id = 999

        with patch("app.crud.tool_execution.get_tool_execution", return_value=None):
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result={"data": "test"},
            )

        assert updated is None
        mock_db.commit.assert_not_called()

    async def test_update_tool_execution_all_fields(self, mock_db):
        """
        Test that updating a tool execution with all possible fields correctly modifies the stored record.

        This test:
        - Creates a `ToolExecution` instance representing an existing execution.
        - Mocks `app.crud.tool_execution.get_tool_execution` to return the created instance.
        - Calls `update_tool_execution` with a new result dictionary, a summary string, and a status of `"completed"`.
        - Verifies that the original `ToolExecution` object's `result`, `result_summary`, and `status` attributes are updated to the supplied values.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            result = {"events": []}
            summary = "No events found"
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result=result,
                result_summary=summary,
                status="completed",
            )

        assert existing_execution.result == result
        assert existing_execution.result_summary == summary
        assert existing_execution.status == "completed"


@pytest.mark.unit
class TestCompleteToolExecution:
    """Test complete_tool_execution function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mocked asynchronous database session for testing.

        The returned object is an `AsyncMock` instance with its `commit` and `refresh` attributes also set to `AsyncMock` objects, mimicking the async methods of a real database session. This allows unit tests to verify CRUD logic without requiring a live database connection.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_complete_tool_execution_success(self, mock_db):
        """
        Test that completing a tool execution updates its status and stores the result.

        Args:
            self: Test case instance.
            mock_db: Mocked database session injected by the test framework.

        The test creates a `ToolExecution` object in an "executing" state, patches the
        `get_tool_execution` function to return this object, and then calls
        `complete_tool_execution` with a successful result payload. After awaiting the
        call, it asserts that:

        * The execution's status is changed to `"completed"`.
        * The `result` attribute matches the supplied dictionary.
        * The `result_summary` attribute matches the provided summary string.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            result = {"events": [1, 2, 3]}
            summary = "Found 3 events"
            updated = await complete_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result=result,
                result_summary=summary,
                success=True,
            )

        assert existing_execution.status == "completed"
        assert existing_execution.result == result
        assert existing_execution.result_summary == summary

    async def test_complete_tool_execution_failure(self, mock_db):
        """
        Test that completing a tool execution with a failure updates the stored execution record's status to "failed", stores the provided error result and summary, and returns the updated execution object. This verifies proper handling of unsuccessful executions when `success` is False.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            result = {"error": "Database connection failed"}
            summary = "Execution failed"
            updated = await complete_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result=result,
                result_summary=summary,
                success=False,
            )

        assert existing_execution.status == "failed"
        assert existing_execution.result == result
        assert existing_execution.result_summary == summary


@pytest.mark.unit
class TestGetToolExecution:
    """Test get_tool_execution function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session.\n\nThis helper constructs an :class:`unittest.mock.AsyncMock` instance that mimics the behavior of a real async DB session, allowing test cases to simulate database interactions without requiring a live connection. The returned object can be configured with expected method calls and return values as needed by the tests.
        """
        db = AsyncMock()
        return db

    async def test_get_tool_execution_found(self, mock_db):
        """
        Test that retrieving an existing tool execution returns the correct `ToolExecution` instance.

        Args:
            self: The test case instance.
            mock_db: A mocked database session used to simulate the query.

        The test sets up a mock result where `scalar_one_or_none` returns a predefined `ToolExecution` object with the given `execution_id`. It then calls :func:`get_tool_execution` with the mock database and asserts that the returned value matches the expected execution and that the database's `execute` method was called exactly once.
        """
        execution_id = 1
        expected_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="completed",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_execution
        mock_db.execute.return_value = mock_result

        result = await get_tool_execution(mock_db, execution_id)

        assert result == expected_execution
        mock_db.execute.assert_called_once()

    async def test_get_tool_execution_not_found(self, mock_db):
        """
        Test that retrieving a tool execution with an ID that does not exist returns `None` and that the database execute method is called exactly once. The test sets up a mock database where `execute().scalar_one_or_none()` yields `None`, invokes `get_tool_execution` with a non-existent ID, asserts the result is `None`, and verifies the call count on the mocked `execute` method.
        """
        execution_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_tool_execution(mock_db, execution_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetMessageToolExecutions:
    """Test get_message_tool_executions function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return an asynchronous mock database session.\n\nThis helper constructs an `AsyncMock` instance that mimics the interface of a real async database session, allowing unit tests to simulate database interactions without requiring a live connection. The returned mock can be configured with expected return values or side effects as needed for each test scenario.
        """
        db = AsyncMock()
        return db

    async def test_get_message_tool_executions_with_results(self, mock_db):
        """
        Test that `get_message_tool_executions` correctly queries the database for all tool execution records associated with a given message ID and returns them.

        Args:
            self: The test case instance (unused but required by the unittest method signature).
            mock_db: A mocked asynchronous database session whose `execute` method is stubbed to return a predefined result set.

        The test sets up two `ToolExecution` objects linked to `chat_message_id` = 1, configures the mock to return these objects when `scalars().all()` is called, invokes `get_message_tool_executions` with the mock session and message ID, and then asserts that:
        * Exactly two executions are returned.
        * The returned list matches the predefined `executions` collection.
        * The database `execute` method was called exactly once.
        """
        chat_message_id = 1
        executions = [
            ToolExecution(
                execution_id=1,
                chat_message_id=chat_message_id,
                tool_name="search_events",
                status="completed",
            ),
            ToolExecution(
                execution_id=2,
                chat_message_id=chat_message_id,
                tool_name="aggregate",
                status="completed",
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = executions
        mock_db.execute.return_value = mock_result

        result = await get_message_tool_executions(mock_db, chat_message_id)

        assert len(result) == 2
        assert result == executions
        mock_db.execute.assert_called_once()

    async def test_get_message_tool_executions_empty(self, mock_db):
        """
        Test that `get_message_tool_executions` returns an empty list when there are no tool execution records associated with the specified `chat_message_id`. It sets up a mock database session to return an empty result set, invokes the function under test, and asserts that the returned value is an empty list while also verifying that the database `execute` method was called exactly once.
        """
        chat_message_id = 999

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_message_tool_executions(mock_db, chat_message_id)

        assert result == []
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetLatestExecutingTool:
    """Test get_latest_executing_tool function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return an asynchronous mock database session used in unit tests. This helper instantiates an `AsyncMock` object representing the database connection, allowing test cases to simulate async CRUD operations without requiring a real database.
        """
        db = AsyncMock()
        return db

    async def test_get_latest_executing_tool_found(self, mock_db):
        """
        Test that `get_latest_executing_tool` correctly retrieves the most recent execution record with status `executing` when such a record exists for the given `chat_message_id` and `tool_name`. The test sets up a mock database session, configures its `execute` method to return a mocked result whose `scalar_one_or_none` yields the expected :class:`ToolExecution` instance, invokes the function under test, and asserts that the returned value matches the expected execution object while also verifying that the database execute call was made exactly once.
        """
        chat_message_id = 1
        tool_name = "search_events"
        expected_execution = ToolExecution(
            execution_id=3,
            chat_message_id=chat_message_id,
            tool_name=tool_name,
            status="executing",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_execution
        mock_db.execute.return_value = mock_result

        result = await get_latest_executing_tool(mock_db, chat_message_id, tool_name)

        assert result == expected_execution
        mock_db.execute.assert_called_once()

    async def test_get_latest_executing_tool_not_found(self, mock_db):
        """
        Test that `get_latest_executing_tool` returns `None` when the database query finds no matching executing tool record.

        Parameters
        ----------
        self : object
            The test case instance (unused in this test).
        mock_db : MagicMock
            A mocked asynchronous database session whose `execute` method is configured to return a result whose `scalar_one_or_none` method yields `None`.

        Steps
        -----
        1. Define identifiers for the chat message and tool name.
        2. Configure the mock so that `execute` returns an object whose `scalar_one_or_none` returns `None`, simulating no matching record.
        3. Call `get_latest_executing_tool` with the mocked database, `chat_message_id` and `tool_name`.
        4. Assert that the returned value is `None`.
        5. Verify that `mock_db.execute` was called exactly once.

        This test validates the function's handling of the “no result” case without raising errors.
        """
        chat_message_id = 1
        tool_name = "search_events"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_latest_executing_tool(mock_db, chat_message_id, tool_name)

        assert result is None
        mock_db.execute.assert_called_once()

    async def test_get_latest_executing_tool_only_returns_executing(self, mock_db):
        """
        Test that `get_latest_executing_tool` returns only tools with a status of `"executing"`, ensuring the database query is filtered correctly and that the function handles a case where no matching record is found. The test sets up a mock DB session, configures the `scalar_one_or_none` result to `None`, invokes the coroutine, and asserts that the `execute` method was called exactly once.
        """
        chat_message_id = 1
        tool_name = "search_events"

        # Should only return tools with status="executing"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_latest_executing_tool(mock_db, chat_message_id, tool_name)

        # Verify the query filters by status="executing"
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestToolExecutionCRUDEdgeCases:
    """Test edge cases for tool execution CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mocked asynchronous database session.

        The returned object mimics an async SQLAlchemy session with the following attributes:
        - `add`: a synchronous :class:`unittest.mock.MagicMock` used to record calls to `session.add(...)`.
        - `commit`: an :class:`unittest.mock.AsyncMock` representing the asynchronous commit operation.
        - `refresh`: an :class:`unittest.mock.AsyncMock` representing the asynchronous refresh operation.

        This mock is intended for use in unit tests that require a database session without performing real I/O.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_tool_execution_with_empty_arguments(self, mock_db):
        """
        Test that creating a tool execution with an empty arguments dictionary succeeds and stores the empty arguments correctly in the database mock. The test invokes `create_tool_execution` with a mock DB session, verifies the call to `add` on the mock, and asserts that the `arguments` attribute of the added execution object is an empty dict. This ensures that the function handles empty input without errors or unintended modifications.
        """
        result = await create_tool_execution(
            db=mock_db,
            chat_message_id=1,
            tool_name="test_tool",
            arguments={},
        )

        added_execution = mock_db.add.call_args[0][0]
        assert added_execution.arguments == {}

    async def test_create_tool_execution_with_unicode_tool_name(self, mock_db):
        """
        Test that creating a tool execution record correctly stores a Unicode tool name in the database mock. The test invokes `create_tool_execution` with a sample chat message ID and a tool name containing non-ASCII characters, then verifies that the `tool_name` attribute of the object passed to `mock_db.add` matches the provided Unicode string. This ensures proper handling of Unicode input throughout the creation workflow.
        """
        tool_name = "検索_イベント"

        result = await create_tool_execution(
            db=mock_db,
            chat_message_id=1,
            tool_name=tool_name,
        )

        added_execution = mock_db.add.call_args[0][0]
        assert added_execution.tool_name == tool_name

    async def test_create_tool_execution_with_zero_execution_number(self, mock_db):
        """
        Test that creating a tool execution with an explicit execution_number of zero correctly stores the record with execution_number set to 0. The test invokes `create_tool_execution` using a mocked database session, then inspects the object passed to `mock_db.add` to verify that its `execution_number` attribute equals 0. No return value is expected; assertions validate the behavior.
        """
        result = await create_tool_execution(
            db=mock_db,
            chat_message_id=1,
            tool_name="test_tool",
            execution_number=0,
        )

        added_execution = mock_db.add.call_args[0][0]
        assert added_execution.execution_number == 0

    async def test_create_tool_execution_with_negative_max_tools(self, mock_db):
        """
        Test that creating a tool execution with a negative `max_tools` value correctly stores the provided value in the database record.

        The test invokes :func:`create_tool_execution` with `max_tools=-1` and verifies that the resulting
        `ToolExecution` instance added to the mocked database has its `max_tools` attribute set to `-1`.
        """
        result = await create_tool_execution(
            db=mock_db,
            chat_message_id=1,
            tool_name="test_tool",
            max_tools=-1,
        )

        added_execution = mock_db.add.call_args[0][0]
        assert added_execution.max_tools == -1

    async def test_update_tool_execution_with_none_values(self, mock_db):
        """
        Test that providing `None` for optional update fields does not modify the existing values of a :class:`ToolExecution` record.

        The test creates a mock `ToolExecution` instance with preset values and patches
        :func:`app.crud.tool_execution.get_tool_execution` to return this instance.
        It then calls :func:`update_tool_execution` with `result`, `result_summary` and
        `status` set to `None`.

        Assertions verify that the original `result`, `result_summary` and `status`
        attributes remain unchanged after the update call. The function does not return a
        value; its purpose is to ensure the update logic correctly ignores `None` inputs.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
            result={"old": "data"},
            result_summary="Old summary",
        )

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            # Update with all None values
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result=None,
                result_summary=None,
                status=None,
            )

        # Original values should be preserved
        assert existing_execution.result == {"old": "data"}
        assert existing_execution.result_summary == "Old summary"
        assert existing_execution.status == "executing"

    async def test_update_tool_execution_with_very_large_result(self, mock_db):
        """
        Test that updating a tool execution record with an extremely large result payload correctly stores the result in the existing execution object. The test creates a mock `ToolExecution` instance, generates a sizable dictionary containing 1,000 events each with a 1 KB data string, patches the retrieval function to return the mock execution, invokes `update_tool_execution`, and asserts that the `result` attribute of the original execution matches the large payload. This validates handling of large result sizes without truncation or errors.
        """
        execution_id = 1
        existing_execution = ToolExecution(
            execution_id=execution_id,
            chat_message_id=1,
            tool_name="search_events",
            status="executing",
        )

        # Create a large result
        large_result = {"events": [{"id": i, "data": "x" * 1000} for i in range(1000)]}

        with patch("app.crud.tool_execution.get_tool_execution", return_value=existing_execution):
            updated = await update_tool_execution(
                db=mock_db,
                execution_id=execution_id,
                result=large_result,
            )

        assert existing_execution.result == large_result
