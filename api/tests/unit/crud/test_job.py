import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.crud.job import (
    enqueue_parsing_job,
    enqueue_agent_job,
    get_parsing_job,
    get_agent_job,
    set_parsing_job_status,
    set_agent_job_status,
)
from app.models.job_parsing import ParsingJob, JobStatus as ParseStatus
from app.models.job_agent import AgentJob, JobStatus as AgentStatus


@pytest.mark.unit
class TestEnqueueParsingJob:
    """Test enqueue_parsing_job function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mocked asynchronous database session.

        The returned object mimics an async SQLAlchemy session:
        - `add` is a regular `MagicMock` used to record calls to add ORM instances.
        - `commit` and `refresh` are `AsyncMock` objects that can be awaited in tests.
        This mock enables unit tests to verify interactions with the database without requiring a real connection.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_enqueue_parsing_job(self, mock_db):
        """
        Test that enqueuing a parsing job correctly creates a `ParsingJob` record with the provided investigation and artifact identifiers, sets its status to :class:`ParseStatus.PENDING`, and performs the expected database operations (add, commit, refresh).
        """
        investigation_id = uuid4()
        artifact_id = 123

        result = await enqueue_parsing_job(
            db=mock_db, investigation_id=investigation_id, artifact_id=artifact_id
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify job object
        added_job = mock_db.add.call_args[0][0]
        assert isinstance(added_job, ParsingJob)
        assert added_job.investigation_id == investigation_id
        assert added_job.artifact_id == artifact_id
        assert added_job.status == ParseStatus.PENDING


@pytest.mark.unit
class TestEnqueueAgentJob:
    """Test enqueue_agent_job function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and configures a mock asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session:
        - `add` is a synchronous `MagicMock` used to record calls to `session.add`.
        - `commit` and `refresh` are `AsyncMock` instances representing the async methods `session.commit()` and `session.refresh()`.

        Returns
        -------
        AsyncMock
            A mock session object with `add`, `commit` and `refresh` attributes configured for asynchronous testing.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_enqueue_agent_job(self, mock_db):
        """
        Test the successful enqueuing of an agent job.

        This coroutine creates a new :class:`AgentJob` by calling :func:`enqueue_agent_job` with a mock database session and verifies that:

        - The database `add`, `commit` and `refresh` methods are each called exactly once.
        - The added object is an instance of :class:`AgentJob`.
        - All fields on the created job (`investigation_id`, `user_id`, `policy_id`, `rule_values`, `seed_instructions`) match the input values.
        - The initial status of the job is set to :attr:`ParseStatus.PENDING`.

        The test uses the `mock_db` fixture, which provides an async-compatible mock implementing the required SQLAlchemy session methods.
        """
        investigation_id = uuid4()
        user_id = 1
        policy_id = "event_search"
        rule_values = {"effort": "medium"}
        seed_instructions = "Search for suspicious events"

        result = await enqueue_agent_job(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            policy_id=policy_id,
            rule_values=rule_values,
            seed_instructions=seed_instructions,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify job object
        added_job = mock_db.add.call_args[0][0]
        assert isinstance(added_job, AgentJob)
        assert added_job.investigation_id == investigation_id
        assert added_job.user_id == user_id
        assert added_job.policy_id == policy_id
        assert added_job.rule_values == rule_values
        assert added_job.seed_instructions == seed_instructions
        assert added_job.status == ParseStatus.PENDING

    async def test_enqueue_agent_job_complex_rules(self, mock_db):
        """
        Test that enqueuing an agent job correctly stores complex rule values in the database.

        The test creates a unique investigation identifier and defines a set of nested rule values including effort level, maximum turns, tool list, and filter criteria with event types and date range. It then calls `enqueue_agent_job` with these parameters using a mocked database connection.

        After awaiting the function, the test inspects the job object passed to `mock_db.add` and asserts that:
        - The `rule_values` attribute of the added job matches the original complex rules dictionary.
        - The nested `event_type` filter within `rule_values["filters"]` retains the expected list of event types (`["login", "logout"]`).
        """
        investigation_id = uuid4()
        complex_rules = {
            "effort": "high",
            "max_turns": 15,
            "tools": ["search_events", "aggregate"],
            "filters": {
                "event_type": ["login", "logout"],
                "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            },
        }

        result = await enqueue_agent_job(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            policy_id="advanced_search",
            rule_values=complex_rules,
            seed_instructions="Advanced investigation",
        )

        added_job = mock_db.add.call_args[0][0]
        assert added_job.rule_values == complex_rules
        assert added_job.rule_values["filters"]["event_type"] == ["login", "logout"]


@pytest.mark.unit
class TestGetParsingJob:
    """Test get_parsing_job function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mocked asynchronous database session.

        This helper constructs an :class:`unittest.mock.AsyncMock` object that simulates the
        behaviour of a database session used throughout the test suite. The returned mock
        can be configured with expected coroutine calls and return values to verify CRUD
        operations without requiring a real database connection.
        """
        db = AsyncMock()
        return db

    async def test_get_parsing_job_found(self, mock_db):
        """
        Test that retrieving an existing parsing job returns the correct `ParsingJob` instance.

        The test sets up:
        - A mock database session (`mock_db`) with its `execute` method configured to return a result whose `scalars().first()` yields a predefined `ParsingJob`.
        - An expected job ID and corresponding `ParsingJob` object with sample values for `investigation_id`, `artifact_id`, and `status`.

        The test then:
        1. Calls the asynchronous `get_parsing_job` function with the mock database and the job ID.
        2. Asserts that the returned value matches the expected `ParsingJob`.
        3. Verifies that the database's `execute` method was invoked exactly once.

        Parameters
        ----------
        self: object
            The test case instance (unused in the body but required by the class-based test structure).
        mock_db: MagicMock
            A mock of the asynchronous database session used to simulate query execution.
        """
        job_id = 1
        expected_job = ParsingJob(
            job_id=job_id, investigation_id=uuid4(), artifact_id=123, status=ParseStatus.PENDING
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = expected_job
        mock_db.execute.return_value = mock_result

        result = await get_parsing_job(mock_db, job_id)

        assert result == expected_job
        mock_db.execute.assert_called_once()

    async def test_get_parsing_job_not_found(self, mock_db):
        """
        Test that retrieving a parsing job with an ID that does not exist in the database returns `None` and that the database execute method is called exactly once. The test sets up a mock database session where the query result yields `None` for `first()`, invokes `get_parsing_job` with a non-existent job ID, asserts the returned value is `None`, and verifies the expected call count on the mock.
        """
        job_id = 999

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_parsing_job(mock_db, job_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetAgentJob:
    """Test get_agent_job function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for use in tests.

        The returned object is an :class:`unittest.mock.AsyncMock` instance that mimics the
        behaviour of an async database connection, allowing test code to configure
        awaitable methods and inspect calls without requiring a real database.
        """
        db = AsyncMock()
        return db

    async def test_get_agent_job_found(self, mock_db):
        """
        Test that retrieving an existing agent job returns the correct `AgentJob` instance.\n\nThe test sets up a mock database session (`mock_db`) to return a predefined `AgentJob` object when queried with a specific `job_id`. It then calls the asynchronous `get_agent_job` function and asserts that:\n- The returned value matches the expected `AgentJob` instance.\n- The database execute method is invoked exactly once.\n\nParameters\n----------\nself: object\n    Instance of the test class containing this method.\nmock_db: MagicMock\n    Mocked asynchronous database session used to simulate the query execution.\n\nRaises\n------\nAssertionError\n    If the returned job does not match the expected job or if `execute` is not called exactly once.
        """
        job_id = 1
        expected_job = AgentJob(
            job_id=job_id,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="event_search",
            rule_values={},
            seed_instructions="Test",
            status=AgentStatus.PENDING,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = expected_job
        mock_db.execute.return_value = mock_result

        result = await get_agent_job(mock_db, job_id)

        assert result == expected_job
        mock_db.execute.assert_called_once()

    async def test_get_agent_job_not_found(self, mock_db):
        """
        Test that retrieving an agent job with an ID that does not exist returns `None` and that the database execute method is called exactly once.

        Args:
            self: The test case instance.
            mock_db (MagicMock): Asynchronous mock of the database session used by `get_agent_job`.

        Returns:
            None - this test asserts behavior rather than returning a value.
        """
        job_id = 999

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_agent_job(mock_db, job_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestSetParsingJobStatus:
    """Test set_parsing_job_status function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for use in tests.

        The returned object is an `AsyncMock` instance that mimics a database
        session and includes a mocked `commit` coroutine, allowing test code to
        await `db.commit()` without performing any real I/O.

        Returns:
            AsyncMock: A mock async DB session with a `commit` attribute also set
            to an `AsyncMock`.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_set_status_to_running(self, mock_db):
        """
        Test that setting a parsing job's status to `RUNNING` updates the database correctly and returns `True`.

        The test creates a mock asynchronous database connection, configures its `execute` method to return a result with `rowcount` set to 1 (indicating one row was affected), and then calls :func:`set_parsing_job_status` with the mock DB, a sample job ID, and `ParseStatus.RUNNING`.

        Assertions verify that:
        - The function returns `True`.
        - `execute` and `commit` are each called exactly once on the mock DB.
        - The SQL statement passed to `execute` includes an update of the `started_at` column.
        """
        job_id = 1

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_parsing_job_status(
            db=mock_db, job_id=job_id, new_status=ParseStatus.RUNNING
        )

        assert result is True
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify started_at was set
        call_args = mock_db.execute.call_args[0][0]
        # The update statement should have started_at in values

    async def test_set_status_to_completed(self, mock_db):
        """
        Test that setting a parsing job's status to `ParseStatus.COMPLETED` updates the database correctly and returns `True`.

        The test uses an asynchronous mock database (`mock_db`) where:
        - `execute` is configured to return a result object with `rowcount` set to `1`, indicating one row was affected.
        - After calling :func:`set_parsing_job_status` with the job ID and new status, the function should commit the transaction.

        Assertions verify that:
        - The returned value is `True`.
        - `mock_db.commit` was called exactly once.
        """
        job_id = 1

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_parsing_job_status(
            db=mock_db, job_id=job_id, new_status=ParseStatus.COMPLETED
        )

        assert result is True
        mock_db.commit.assert_called_once()

    async def test_set_status_to_failed_with_error(self, mock_db):
        """
        Test that setting the status of a parsing job to `FAILED` updates the database correctly and records the provided error message.\n\nThe test creates a mock database connection, configures its `execute` method to return a result with `rowcount` set to `1` (indicating one row was affected), and then calls :func:`set_parsing_job_status` with `new_status` equal to :class:`ParseStatus.FAILED` and an `error_msg` describing the failure.\n\nAssertions verify that the function returns `True` (signalling a successful update) and that the database transaction is committed exactly once.\"""
        """
        job_id = 1
        error_msg = "Parsing failed: Invalid file format"

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_parsing_job_status(
            db=mock_db, job_id=job_id, new_status=ParseStatus.FAILED, error_msg=error_msg
        )

        assert result is True
        mock_db.commit.assert_called_once()

    async def test_set_status_job_not_found(self, mock_db):
        """
        Test that setting the status of a parsing job that does not exist returns `False` and commits the transaction.

        Args:
            self: The test case instance (unused).
            mock_db: An async mock representing the database connection; its `execute` method is configured to return a result with `rowcount` set to `0`.

        The test creates a non-existent job identifier, configures the mock to simulate no rows being affected, invokes :func:`set_parsing_job_status` with `ParseStatus.RUNNING`, and asserts that the function returns `False`. It also verifies that `mock_db.commit` is called exactly once.
        """
        job_id = 999

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await set_parsing_job_status(
            db=mock_db, job_id=job_id, new_status=ParseStatus.RUNNING
        )

        assert result is False
        mock_db.commit.assert_called_once()


@pytest.mark.unit
class TestSetAgentJobStatus:
    """Test set_agent_job_status function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for testing.

        This helper returns an `AsyncMock` instance configured with an async `commit` method,
        allowing unit tests to simulate database interactions without requiring a real
        database connection.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_set_status_to_running(self, mock_db):
        """
        Test that setting an agent job's status to `RUNNING` updates the database correctly and returns `True`.

        The test creates a mock database connection where `execute` returns a result with `rowcount` set to 1, indicating one row was affected. It then calls :func:`set_agent_job_status` with the mock DB, a sample job ID, and `AgentStatus.RUNNING` as the new status.

        Assertions verify that:
        - The function returns `True`.
        - `execute` is called exactly once on the mock database.
        - `commit` is also called exactly once to persist the change.
        """
        job_id = 1

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_agent_job_status(
            db=mock_db, job_id=job_id, new_status=AgentStatus.RUNNING
        )

        assert result is True
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_set_status_to_completed(self, mock_db):
        """
        Test that setting an agent job's status to `COMPLETED` updates the database correctly and returns `True`.

        Args:
            self: The test case instance.
            mock_db: An async mock representing the database connection used by `set_agent_job_status`.

        Returns:
            None - assertions are performed within the test.
        """
        job_id = 1

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_agent_job_status(
            db=mock_db, job_id=job_id, new_status=AgentStatus.COMPLETED
        )

        assert result is True
        mock_db.commit.assert_called_once()

    async def test_set_status_to_failed_with_error(self, mock_db):
        """
        Test that setting an agent job's status to `FAILED` updates the database correctly and records the provided error message.\n\nThe test:\n- Mocks a database connection and configures its `execute` method to return a result with `rowcount` set to `1`, indicating one row was affected.\n- Calls :func:`set_agent_job_status` with the mocked DB, a job identifier, the `AgentStatus.FAILED` enum value, and an error message.\n- Asserts that the function returns `True` to signal success.\n- Verifies that the database transaction is committed exactly once.
        """
        job_id = 1
        error_msg = "Agent execution failed: Timeout"

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_agent_job_status(
            db=mock_db, job_id=job_id, new_status=AgentStatus.FAILED, error_msg=error_msg
        )

        assert result is True
        mock_db.commit.assert_called_once()

    async def test_set_status_job_not_found(self, mock_db):
        """
        Test that attempting to set the status of a non-existent agent job returns `False` and triggers a database commit. The test mocks the database execute call to indicate zero rows were affected (rowcount = 0), invokes `set_agent_job_status` with a nonexistent `job_id`, verifies the result is falsy, and ensures `commit` was called exactly once.
        """
        job_id = 999

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await set_agent_job_status(
            db=mock_db, job_id=job_id, new_status=AgentStatus.RUNNING
        )

        assert result is False
        mock_db.commit.assert_called_once()


@pytest.mark.unit
class TestJobCRUDEdgeCases:
    """Test edge cases for job CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mock asynchronous database session for testing.

        The returned object mimics an async SQLAlchemy session:
        - `add` is a regular :class:`unittest.mock.MagicMock` used to record calls to add entities.
        - `commit` and `refresh` are :class:`unittest.mock.AsyncMock` instances representing the corresponding async methods.
        - The mock itself can be awaited if needed, matching typical async session behavior.

        Returns
        -------
        AsyncMock
            A configured mock object with `add`, `commit` and `refresh` attributes ready for use in unit tests.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_enqueue_agent_job_with_unicode(self, mock_db):
        """
        Test that enqueue_agent_job correctly stores Unicode characters in the seed_instructions field.

        Args:
            self: The test case instance.
            mock_db: An async mock of the database session used to capture calls to add().

        The test creates a unique investigation_id and a seed_instructions string containing Japanese text and an emoji. It then calls enqueue_agent_job with these parameters and asserts that the job added to the mock database contains the original Unicode characters in its seed_instructions attribute. This verifies proper handling of non-ASCII input throughout the enqueue process.
        """
        investigation_id = uuid4()
        seed_instructions = "調査を実行: データを検索 🔍"

        result = await enqueue_agent_job(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            policy_id="test",
            rule_values={},
            seed_instructions=seed_instructions,
        )

        added_job = mock_db.add.call_args[0][0]
        assert "調査" in added_job.seed_instructions
        assert "🔍" in added_job.seed_instructions

    async def test_enqueue_agent_job_with_empty_rules(self, mock_db):
        """
        Test that enqueuing an agent job with an empty `rule_values` dictionary succeeds and stores a job whose `rule_values` attribute is an empty dict. The test creates a mock database, calls :func:`enqueue_agent_job` with minimal parameters, and asserts that the job added to the database reflects the empty rule set.
        """
        investigation_id = uuid4()

        result = await enqueue_agent_job(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            policy_id="simple_policy",
            rule_values={},
            seed_instructions="Simple task",
        )

        added_job = mock_db.add.call_args[0][0]
        assert added_job.rule_values == {}

    async def test_enqueue_agent_job_with_very_long_instructions(self, mock_db):
        """
        Test that enqueuing an agent job correctly handles extremely long seed instructions without truncation or errors.

        The test creates a unique investigation identifier and generates a string of 100 000 characters to simulate very large instruction input. It then calls :func:`enqueue_agent_job` with the mock database, passing the generated `seed_instructions` along with standard parameters (user ID, policy ID, empty rule values). After awaiting the coroutine, the test inspects the job object that was added to the mock DB and asserts that its `seed_instructions` attribute retains the full length of 100 000 characters, confirming that the function stores long instruction payloads intact.
        """
        investigation_id = uuid4()
        long_instructions = "A" * 100000

        result = await enqueue_agent_job(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            policy_id="test",
            rule_values={},
            seed_instructions=long_instructions,
        )

        added_job = mock_db.add.call_args[0][0]
        assert len(added_job.seed_instructions) == 100000

    async def test_set_parsing_job_status_with_very_long_error(self, mock_db):
        """
        Test that setting a parsing job's status to FAILED with an exceptionally long error message succeeds and returns `True`. The mock database simulates a successful update (rowcount = 1), and the function under test is called with a 10 000-character error string to verify handling of large messages.
        """
        job_id = 1
        long_error = "Error: " + ("A" * 10000)

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_parsing_job_status(
            db=mock_db, job_id=job_id, new_status=ParseStatus.FAILED, error_msg=long_error
        )

        assert result is True

    async def test_set_agent_job_status_with_unicode_error(self, mock_db):
        """
        Test setting an agent job's status to FAILED while providing a Unicode error message.

        This test verifies that `set_agent_job_status` correctly handles error messages containing non-ASCII characters. It mocks the database execution to simulate a successful update (rowcount = 1) and asserts that the function returns `True` indicating the status was set.
        """
        job_id = 1
        unicode_error = "エラー: 処理失敗 🚫"

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await set_agent_job_status(
            db=mock_db, job_id=job_id, new_status=AgentStatus.FAILED, error_msg=unicode_error
        )

        assert result is True

    async def test_enqueue_agent_job_with_nested_rule_values(self, mock_db):
        """
        Test that enqueue_agent_job correctly stores deeply nested rule values in the created job record. The test creates a unique investigation identifier and a multi-level dictionary representing rule values, then calls enqueue_agent_job with a mock database session. After awaiting the coroutine, it inspects the job object passed to the mock's add method and asserts that the nested value under "level1 → level2 → level3 → level4 → data" matches the expected string. This verifies proper handling of complex rule value structures during job enqueuing.
        """
        investigation_id = uuid4()
        nested_rules = {"level1": {"level2": {"level3": {"level4": {"data": "deep value"}}}}}

        result = await enqueue_agent_job(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            policy_id="test",
            rule_values=nested_rules,
            seed_instructions="Test",
        )

        added_job = mock_db.add.call_args[0][0]
        assert added_job.rule_values["level1"]["level2"]["level3"]["level4"]["data"] == "deep value"
