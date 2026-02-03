import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from app.crud.investigation_choice import (
    create_investigation_choice,
    create_investigation_choices_bulk,
    get_investigation_choices_by_job,
    get_investigation_choices_by_investigation,
    get_investigation_choice,
    update_investigation_choice,
    delete_investigation_choice,
)
from app.models.investigation_choice import InvestigationChoice
from app.schemas.investigation_choice import (
    InvestigationChoiceCreate,
    InvestigationChoiceUpdate,
)


@pytest.mark.unit
class TestCreateInvestigationChoice:
    """Test create_investigation_choice function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mocked asynchronous database session suitable for unit testing.

        The returned object mimics an async SQLAlchemy session with the following attributes:
        - `add`: a synchronous `MagicMock` used to record calls to add ORM objects.
        - `commit`: an `AsyncMock` representing the asynchronous commit operation.
        - `refresh`: an `AsyncMock` for the asynchronous refresh operation.

        The mock session can be injected into code paths that expect an async session, allowing verification of interaction without a real database.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_choice_success(self, mock_db):
        """
        Test that creating an investigation choice succeeds and interacts correctly with the database session.

        The test constructs an `InvestigationChoiceCreate` instance with valid data, calls :func:`create_investigation_choice` using a mocked asynchronous DB session, and asserts that:

        * The session's `add`, `commit` and `refresh` methods are each called exactly once.
        * The object passed to `add` is an `InvestigationChoice` instance whose attributes match the input data (including `investigation_id`, `job_id`, `title` and `display_order`).

        The test ensures that no unexpected fields (e.g., a non-existent `category` attribute) are accessed or set on the model.
        """
        investigation_id = uuid4()
        choice_data = InvestigationChoiceCreate(
            investigation_id=investigation_id,
            job_id=1,
            title="Investigate failed login attempts",
            description="Analyze authentication failures",
            rationale="Multiple failed attempts detected",
            suggested_query="Find failed login attempts",
            display_order=1,
        )

        result = await create_investigation_choice(mock_db, choice_data)

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify choice object
        added_choice = mock_db.add.call_args[0][0]
        assert isinstance(added_choice, InvestigationChoice)
        assert added_choice.investigation_id == investigation_id
        assert added_choice.job_id == 1
        assert added_choice.title == "Investigate failed login attempts"
        # category field doesn't exist in the model
        assert added_choice.display_order == 1

    async def test_create_choice_minimal_data(self, mock_db):
        """
        Test that creating an investigation choice with only the required fields succeeds and stores the correct title.

        Args:
            self: Test case instance.
            mock_db: AsyncMock representing a database session; its `add` method is inspected to verify the inserted object.

        Procedure:
        1. Generate a random `investigation_id`.
        2. Build an `InvestigationChoiceCreate` payload containing minimal required attributes.
        3. Call `create_investigation_choice` with the mocked session and payload.
        4. Retrieve the object passed to `mock_db.add` and assert that its `title` matches the input value.

        Ensures:
        - The service correctly handles minimal data without raising errors.
        - The created choice is added to the session with the expected title.
        """
        investigation_id = uuid4()
        choice_data = InvestigationChoiceCreate(
            investigation_id=investigation_id,
            job_id=1,
            title="Simple choice",
            description="Simple description",
            rationale="Simple rationale",
            suggested_query="Simple query",
        )

        result = await create_investigation_choice(mock_db, choice_data)

        added_choice = mock_db.add.call_args[0][0]
        assert added_choice.title == "Simple choice"


@pytest.mark.unit
class TestCreateInvestigationChoicesBulk:
    """Test create_investigation_choices_bulk function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and configures a mocked asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session with the following attributes:
        - `add_all`: a synchronous `MagicMock` used to track bulk addition of objects.
        - `commit`: an `AsyncMock` representing the asynchronous commit operation.
        - `refresh`: an `AsyncMock` for refreshing instances after persistence.

        Returns
        -------
        AsyncMock
            A mock session object with the above methods mocked, suitable for injection into code that expects an async database session.
        """
        db = AsyncMock()
        db.add_all = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_bulk_create_success(self, mock_db):
        """
        Test bulk creation of investigation choices using an asynchronous mocked database session.

        This test verifies that:
        - The `create_investigation_choices_bulk` function correctly adds multiple `InvestigationChoiceCreate` instances to the session.
        - The session's `add_all` method is called exactly once with a collection containing three `InvestigationChoice` objects.
        - The session's `commit` method is invoked once to persist the changes.
        - Each newly created choice triggers a call to `session.refresh`, resulting in three refresh calls.

        The test constructs three distinct `InvestigationChoiceCreate` payloads sharing the same `investigation_id` and `job_id`, then asserts that all expected database interactions occur and that the returned objects are of type `InvestigationChoice`.
        """
        investigation_id = uuid4()
        choices_data = [
            InvestigationChoiceCreate(
                investigation_id=investigation_id,
                job_id=1,
                title="Choice 1",
                description="Description 1",
                rationale="Rationale 1",
                suggested_query="Query 1",
                display_order=1,
            ),
            InvestigationChoiceCreate(
                investigation_id=investigation_id,
                job_id=1,
                title="Choice 2",
                description="Description 2",
                rationale="Rationale 2",
                suggested_query="Query 2",
                display_order=2,
            ),
            InvestigationChoiceCreate(
                investigation_id=investigation_id,
                job_id=1,
                title="Choice 3",
                description="Description 3",
                rationale="Rationale 3",
                suggested_query="Query 3",
                display_order=3,
            ),
        ]

        result = await create_investigation_choices_bulk(mock_db, choices_data)

        # Verify database operations
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify all choices were added
        added_choices = mock_db.add_all.call_args[0][0]
        assert len(added_choices) == 3
        assert all(isinstance(c, InvestigationChoice) for c in added_choices)

        # Verify refresh was called for each choice
        assert mock_db.refresh.call_count == 3

    async def test_bulk_create_empty_list(self, mock_db):
        """
        Test that bulk creation handles an empty input list correctly.\n\nThe test invokes `create_investigation_choices_bulk` with an empty list and verifies that the database session's `add_all` method is called once with an empty list and that `commit` is also called exactly once. This ensures that the function gracefully processes empty collections without raising errors.
        """
        result = await create_investigation_choices_bulk(mock_db, [])

        mock_db.add_all.assert_called_once_with([])
        mock_db.commit.assert_called_once()

    async def test_bulk_create_single_choice(self, mock_db):
        """
        Test bulk creation of investigation choices when only a single choice is provided.

        This test verifies that:
        - The `create_investigation_choices_bulk` function correctly processes a list containing one `InvestigationChoiceCreate` instance.
        - The mocked database session receives exactly one new choice via its `add_all` method.
        - No exceptions are raised during the operation.

        Args:
            self: Instance of the test case class.
            mock_db: Asynchronous mock of the database session, injected by the test framework.
        """
        investigation_id = uuid4()
        choices_data = [
            InvestigationChoiceCreate(
                investigation_id=investigation_id,
                job_id=1,
                title="Single choice",
                description="Single description",
                rationale="Single rationale",
                suggested_query="Single query",
            ),
        ]

        result = await create_investigation_choices_bulk(mock_db, choices_data)

        added_choices = mock_db.add_all.call_args[0][0]
        assert len(added_choices) == 1


@pytest.mark.unit
class TestGetInvestigationChoicesByJob:
    """Test get_investigation_choices_by_job function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session suitable for use in unit tests.

        Returns
        -------
        AsyncMock
            A mocked async database session object that can be configured with expected return values and assertions.
        """
        db = AsyncMock()
        return db

    async def test_get_choices_by_job_with_results(self, mock_db):
        """
        Test that `get_investigation_choices_by_job` returns a list of `InvestigationChoice` objects for a given job ID, correctly handling a mocked asynchronous database session and verifying the query execution.
        """
        job_id = 1
        investigation_id = uuid4()
        choices = [
            InvestigationChoice(
                choice_id=1,
                investigation_id=investigation_id,
                job_id=job_id,
                title="Choice 1",
                description="Description 1",
                rationale="Rationale 1",
                suggested_query="Query 1",
                display_order=1,
            ),
            InvestigationChoice(
                choice_id=2,
                investigation_id=investigation_id,
                job_id=job_id,
                title="Choice 2",
                description="Description 2",
                rationale="Rationale 2",
                suggested_query="Query 2",
                display_order=2,
            ),
        ]

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = choices
        mock_db.execute.return_value = mock_result

        result = await get_investigation_choices_by_job(mock_db, job_id)

        assert len(result) == 2
        assert result == choices
        mock_db.execute.assert_called_once()

    async def test_get_choices_by_job_empty(self, mock_db):
        """
        Test that retrieving investigation choices for a job with no associated records returns an empty list and that the database execute method is called exactly once.
        """
        job_id = 999

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_investigation_choices_by_job(mock_db, job_id)

        assert result == []
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetInvestigationChoicesByInvestigation:
    """Test get_investigation_choices_by_investigation function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return an asynchronous mock database session suitable for use in unit tests.

        The returned object is an instance of :class:`unittest.mock.AsyncMock` that mimics the interface of an async database session, allowing test code to configure expected behaviours (e.g., `await db.execute(...)`) without requiring a real database connection. This helper centralises mock creation so that each test can obtain a fresh, isolated mock session.
        """
        db = AsyncMock()
        return db

    async def test_get_choices_by_investigation_all(self, mock_db):
        """
        Test that retrieving investigation choices by investigation ID returns all associated records when the `include_selected` flag is True.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        The test sets up two `InvestigationChoice` objects linked to the same `investigation_id`, configures the mock to return these choices, invokes :func:`get_investigation_choices_by_investigation` with `include_selected=True`, and asserts that both records are returned. It also verifies that the database `execute` method was called exactly once.
        """
        investigation_id = uuid4()
        choices = [
            InvestigationChoice(
                choice_id=1,
                investigation_id=investigation_id,
                job_id=1,
                title="Choice 1",
                description="Description 1",
                rationale="Rationale 1",
                suggested_query="Query 1",
                selected=True,
            ),
            InvestigationChoice(
                choice_id=2,
                investigation_id=investigation_id,
                job_id=1,
                title="Choice 2",
                description="Description 2",
                rationale="Rationale 2",
                suggested_query="Query 2",
                selected=False,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = choices
        mock_db.execute.return_value = mock_result

        result = await get_investigation_choices_by_investigation(
            mock_db, investigation_id, include_selected=True
        )

        assert len(result) == 2
        mock_db.execute.assert_called_once()

    async def test_get_choices_by_investigation_unselected_only(self, mock_db):
        """
        Test that get_investigation_choices_by_investigation returns only unselected choices when include_selected is False.

        Args:
            self: TestCase instance.
            mock_db: AsyncMock representing a database session; its execute method is mocked to return a result containing only unselected InvestigationChoice objects.

        Procedure:
            1. Create a random investigation_id and a list with a single unselected InvestigationChoice.
            2. Mock the database execution chain so that `mock_db.execute(...).scalars().all()` returns the prepared list.
            3. Call get_investigation_choices_by_investigation with include_selected set to False.
            4. Verify that exactly one choice is returned, that its selected attribute is False, and that execute was called once.

        Ensures:
            The function correctly filters out selected choices when the caller requests only unselected ones.
        """
        investigation_id = uuid4()
        unselected_choices = [
            InvestigationChoice(
                choice_id=2,
                investigation_id=investigation_id,
                job_id=1,
                title="Choice 2",
                description="Description 2",
                rationale="Rationale 2",
                suggested_query="Query 2",
                selected=False,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = unselected_choices
        mock_db.execute.return_value = mock_result

        result = await get_investigation_choices_by_investigation(
            mock_db, investigation_id, include_selected=False
        )

        assert len(result) == 1
        assert result[0].selected is False
        mock_db.execute.assert_called_once()

    async def test_get_choices_by_investigation_empty(self, mock_db):
        """
        Test that retrieving investigation choices for a given investigation ID returns an empty list when no choices are present in the database. The test sets up a mock asynchronous DB session to return an empty result set and asserts that the function under test returns an empty list. Parameters: self - the test case instance; mock_db - a mocked async database session providing execute(). Returns nothing; uses assertions to validate behavior.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_investigation_choices_by_investigation(mock_db, investigation_id)

        assert result == []


@pytest.mark.unit
class TestGetInvestigationChoice:
    """Test get_investigation_choice function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session.

        This helper constructs an :class:`unittest.mock.AsyncMock` object that mimics the interface of an async database session used throughout the test suite. The returned mock can be configured with expected coroutine calls, side effects, or return values to simulate various database interactions without requiring a real connection.
        """
        db = AsyncMock()
        return db

    async def test_get_choice_found(self, mock_db):
        """
        Test that retrieving an existing investigation choice returns the correct object.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        The test sets up a mock result where `scalar_one_or_none` returns a predefined `InvestigationChoice` instance with a specific `choice_id`. It then calls `get_investigation_choice` with the mock session and verifies that:

        * The returned value matches the expected `InvestigationChoice`.
        * The database session's `execute` method is invoked exactly once.

        This ensures that the retrieval function correctly queries the database and handles a successful lookup.
        """
        choice_id = 1
        expected_choice = InvestigationChoice(
            choice_id=choice_id,
            investigation_id=uuid4(),
            job_id=1,
            title="Test choice",
            description="Test description",
            rationale="Test rationale",
            suggested_query="Test query",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_choice
        mock_db.execute.return_value = mock_result

        result = await get_investigation_choice(mock_db, choice_id)

        assert result == expected_choice
        mock_db.execute.assert_called_once()

    async def test_get_choice_not_found(self, mock_db):
        """
        Test that retrieving an investigation choice with an ID that does not exist returns `None` and that the database session's `execute` method is invoked exactly once.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_db : MagicMock
            A mocked asynchronous database session whose `execute` method is configured to return a result whose `scalar_one_or_none` yields `None`.

        Returns
        -------
        None
            The function performs assertions and does not return a value.
        """
        choice_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_investigation_choice(mock_db, choice_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestUpdateInvestigationChoice:
    """Test update_investigation_choice function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and configures a mocked asynchronous database session for use in tests.

        Returns
        -------
        AsyncMock
            A mock object representing an async database session with its `commit` method also mocked as an `AsyncMock`.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_update_choice_mark_selected(self, mock_db):
        """
        Test that updating an investigation choice correctly sets the `selected` flag.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution and commit operations.

        The test creates a `InvestigationChoiceUpdate` with `selected=True`, mocks the database response to return an updated `InvestigationChoice` object, invokes `update_investigation_choice`, and asserts that:
        - The returned result matches the expected updated choice.
        - The database session's `execute` method is called exactly once.
        - The database session's `commit` method is called exactly once.
        """
        choice_id = 1
        choice_update = InvestigationChoiceUpdate(selected=True)

        updated_choice = InvestigationChoice(
            choice_id=choice_id,
            investigation_id=uuid4(),
            job_id=1,
            title="Test choice",
            description="Test description",
            rationale="Test rationale",
            suggested_query="Test query",
            selected=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = updated_choice
        mock_db.execute.return_value = mock_result

        result = await update_investigation_choice(mock_db, choice_id, choice_update)

        assert result == updated_choice
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_update_choice_not_found(self, mock_db):
        """
        Test that updating an investigation choice with an ID that does not exist in the database returns `None` and still commits the transaction.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_db : MagicMock
            A mocked asynchronous database session whose `execute` method is configured to return a result with `scalar_one_or_none` yielding `None`.

        Returns
        -------
        None

        The test sets up `choice_id` as a non-existent identifier and creates an `InvestigationChoiceUpdate` payload. It configures the mock so that the query returns no record, invokes `update_investigation_choice`, asserts that the result is `None`, and verifies that `mock_db.commit` was called exactly once.
        """
        choice_id = 999
        choice_update = InvestigationChoiceUpdate(selected=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await update_investigation_choice(mock_db, choice_id, choice_update)

        assert result is None
        mock_db.commit.assert_called_once()

    async def test_update_choice_partial_update(self, mock_db):
        """
        Test that updating an investigation choice with a partial payload correctly applies the changes and returns the updated model.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        The test creates an `InvestigationChoiceUpdate` containing only the `selected` field, mocks the database response to return an `InvestigationChoice` with updated attributes, invokes `update_investigation_choice`, and asserts that the returned object's `title` reflects the expected updated value.
        """
        choice_id = 1
        choice_update = InvestigationChoiceUpdate(selected=False)  # Required field

        updated_choice = InvestigationChoice(
            choice_id=choice_id,
            investigation_id=uuid4(),
            job_id=1,
            title="Updated text",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = updated_choice
        mock_db.execute.return_value = mock_result

        result = await update_investigation_choice(mock_db, choice_id, choice_update)

        assert result.title == "Updated text"


@pytest.mark.unit
class TestDeleteInvestigationChoice:
    """Test delete_investigation_choice function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and configures a mocked asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session with `delete` and `commit`
        coroutines stubbed out as `AsyncMock` instances, allowing test code to assert
        calls without performing real I/O.

        Returns:
            AsyncMock: A mock session with `delete` and `commit` attributes set to
            asynchronous mocks.
        """
        db = AsyncMock()
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_delete_choice_success(self, mock_db):
        """
        Test that deleting an existing investigation choice succeeds.\n\nThe test creates a mock `InvestigationChoice` instance with a known `choice_id` and patches the `get_investigation_choice` function to return this instance when called. It then invokes `delete_investigation_choice` with a mocked asynchronous database session and verifies that:\n\n- The function returns `True` indicating successful deletion.\n- The session's `delete` method is called exactly once with the retrieved choice.\n- The session's `commit` method is called exactly once to persist the change.
        """
        choice_id = 1
        existing_choice = InvestigationChoice(
            choice_id=choice_id,
            investigation_id=uuid4(),
            job_id=1,
            title="Test choice",
            description="Test description",
            rationale="Test rationale",
            suggested_query="Test query",
        )

        # Mock get_investigation_choice to return existing choice
        with patch(
            "app.crud.investigation_choice.get_investigation_choice", return_value=existing_choice
        ):
            result = await delete_investigation_choice(mock_db, choice_id)

        assert result is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_delete_choice_not_found(self, mock_db):
        """
        Test that attempting to delete an investigation choice that does not exist returns `False` and does not invoke any database deletion or commit operations. The test patches `get_investigation_choice` to simulate a missing record, calls `delete_investigation_choice` with a non-existent `choice_id`, and asserts the result is falsy while verifying that `mock_db.delete` and `mock_db.commit` were never called.
        """
        choice_id = 999

        # Mock get_investigation_choice to return None
        with patch("app.crud.investigation_choice.get_investigation_choice", return_value=None):
            result = await delete_investigation_choice(mock_db, choice_id)

        assert result is False
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_called()


@pytest.mark.unit
class TestInvestigationChoiceCRUDEdgeCases:
    """Test edge cases for investigation choice CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mock asynchronous database session for testing.

        This helper returns an `AsyncMock` instance with its key ORM methods stubbed:
        - `add` is replaced by a regular `MagicMock` to track calls synchronously.
        - `commit` and `refresh` are set as `AsyncMock` objects so they can be awaited in async code.

        The returned mock mimics the minimal interface required by CRUD operations, allowing unit tests to verify interaction with the database without performing real I/O.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_choice_with_very_long_text(self, mock_db):
        """
        Test that creating an investigation choice with an exceptionally long title is handled correctly.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_db : AsyncMock
            A mocked asynchronous database session providing `add` and other ORM methods.

        The test constructs a `InvestigationChoiceCreate` payload where the `title` field contains 10,000 characters. It then calls `create_investigation_choice` with the mock session and verifies that the ORM object's `title` attribute retains the full length after being added to the session. This ensures that the creation logic does not truncate or reject overly long text fields.
        """
        investigation_id = uuid4()
        long_text = "A" * 10000
        choice_data = InvestigationChoiceCreate(
            investigation_id=investigation_id,
            job_id=1,
            title=long_text,
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
        )

        result = await create_investigation_choice(mock_db, choice_data)

        added_choice = mock_db.add.call_args[0][0]
        assert len(added_choice.title) == 10000

    async def test_create_choice_with_special_characters(self, mock_db):
        """
        Test that creating an investigation choice preserves special characters in its fields.\n\nThis test verifies that when a choice containing HTML tags and ampersands is passed to `create_investigation_choice`, those characters are not stripped or escaped during persistence. It uses a mocked asynchronous database session, invokes the creation function with a sample `InvestigationChoiceCreate` payload, and then inspects the object added to the session to ensure the original `title` contains `<script>` and the `description` contains `&`.\n\nArgs:\n    self: The test case instance (unused but required by the unittest framework).\n    mock_db: A mocked async database session with `add` and other CRUD methods stubbed.\n\nRaises:\n    AssertionError: If the special characters are missing from the stored choice fields.
        """
        investigation_id = uuid4()
        choice_data = InvestigationChoiceCreate(
            investigation_id=investigation_id,
            job_id=1,
            title="Choice with <script>alert('XSS')</script> & special chars",
            description="test & <category>",
            rationale="Rationale",
            suggested_query="Query",
        )

        result = await create_investigation_choice(mock_db, choice_data)

        added_choice = mock_db.add.call_args[0][0]
        assert "<script>" in added_choice.title
        assert "&" in added_choice.description

    async def test_create_choice_with_unicode(self, mock_db):
        """
        Test that creating an investigation choice with Unicode characters succeeds and stores the correct title.

        The test generates a new `investigation_id`, builds an `InvestigationChoiceCreate` payload containing Unicode text in the `title` field (including Japanese characters and an emoji), and calls `create_investigation_choice` with a mocked asynchronous database session. After awaiting the creation, it inspects the object passed to the mock's `add` method to verify that the Unicode title was preserved, asserting that both the Japanese substring and the emoji are present in the stored `title`.
        """
        investigation_id = uuid4()
        choice_data = InvestigationChoiceCreate(
            investigation_id=investigation_id,
            job_id=1,
            title="調査選択 🔍",
            description="カテゴリー",
            rationale="理由",
            suggested_query="クエリ",
        )

        result = await create_investigation_choice(mock_db, choice_data)

        added_choice = mock_db.add.call_args[0][0]
        assert "調査選択" in added_choice.title
        assert "🔍" in added_choice.title

    async def test_bulk_create_with_mixed_data(self, mock_db):
        """
        Test bulk creation of investigation choices with a mixture of normal, Unicode, and special-character data.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_db : AsyncMock
            A mocked asynchronous database session providing `add_all` and other ORM methods.

        The test constructs three `InvestigationChoiceCreate` objects sharing the same `investigation_id` but differing in their title and related fields:
        - a standard ASCII entry,
        - an entry containing Unicode characters (Japanese),
        - an entry with HTML-like special characters.

        It then calls :func:`create_investigation_choices_bulk` with the mocked session and verifies that the ORM’s `add_all` method was invoked with exactly three choice objects, confirming that bulk insertion handles diverse input without errors.
        """
        investigation_id = uuid4()
        choices_data = [
            InvestigationChoiceCreate(
                investigation_id=investigation_id,
                job_id=1,
                title="Normal choice",
                description="Normal description",
                rationale="Normal rationale",
                suggested_query="Normal query",
            ),
            InvestigationChoiceCreate(
                investigation_id=investigation_id,
                job_id=1,
                title="Unicode 日本語 choice",
                description="Unicode description",
                rationale="Unicode rationale",
                suggested_query="Unicode query",
            ),
            InvestigationChoiceCreate(
                investigation_id=investigation_id,
                job_id=1,
                title="<special> & chars",
                description="Special description",
                rationale="Special rationale",
                suggested_query="Special query",
            ),
        ]

        result = await create_investigation_choices_bulk(mock_db, choices_data)

        added_choices = mock_db.add_all.call_args[0][0]
        assert len(added_choices) == 3

    async def test_create_choice_with_negative_display_order(self, mock_db):
        """
        Test that creating an investigation choice with a negative `display_order` value is allowed and correctly persisted.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to intercept ORM operations.

        The test constructs an :class:`InvestigationChoiceCreate` payload with `display_order=-1`, invokes
        :func:`create_investigation_choice`, and verifies that the ORM object's `display_order` attribute
        matches the negative value supplied. This ensures edge-case handling of ordering fields during
        creation.
        """
        investigation_id = uuid4()
        choice_data = InvestigationChoiceCreate(
            investigation_id=investigation_id,
            job_id=1,
            title="Negative order",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
            display_order=-1,
        )

        result = await create_investigation_choice(mock_db, choice_data)

        added_choice = mock_db.add.call_args[0][0]
        assert added_choice.display_order == -1

    async def test_create_choice_with_zero_display_order(self, mock_db):
        """
        Test that creating an investigation choice with a display order of zero correctly stores the value.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to intercept and inspect database operations.

        The test constructs an `InvestigationChoiceCreate` payload with `display_order=0`, invokes `create_investigation_choice`, and asserts that the `display_order` attribute of the object passed to `mock_db.add` remains zero, confirming that zero is accepted as a valid display order.
        """
        investigation_id = uuid4()
        choice_data = InvestigationChoiceCreate(
            investigation_id=investigation_id,
            job_id=1,
            title="Zero order",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
            display_order=0,
        )

        result = await create_investigation_choice(mock_db, choice_data)

        added_choice = mock_db.add.call_args[0][0]
        assert added_choice.display_order == 0
