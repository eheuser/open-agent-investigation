import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from uuid import uuid4, UUID
from pathlib import Path
from fastapi import HTTPException

from app.crud.investigation import (
    create_investigation,
    get_investigation,
    list_investigations,
    update_investigation,
    delete_investigation,
    check_investigation_access,
    set_parsing_lock,
    is_parsing_locked,
)
from app.models.investigation import Investigation
from app.models.user import User


@pytest.mark.unit
class TestCreateInvestigation:
    """Test create_investigation function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session suitable for unit testing.

        The returned object mimics the interface of an async SQLAlchemy session:

        * `add` - a :class:`unittest.mock.MagicMock` that records calls to add ORM objects.
        * `flush` - an :class:`unittest.mock.AsyncMock` representing the asynchronous flush operation.
        * `commit` - an :class:`unittest.mock.AsyncMock` representing the asynchronous commit operation.
        * `refresh` - an :class:`unittest.mock.AsyncMock` representing the asynchronous refresh operation.

        The mock session can be injected into code paths that expect an async database session, allowing tests to verify interaction without requiring a real database.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    async def test_create_investigation_minimal(self, mock_settings, mock_path, mock_db):
        """
        Test creating an investigation with only the required fields.

        This test verifies that:
        - An investigation can be created when only a title is provided and no owner ID.
        - The settings object correctly supplies the base path for investigations.
        - Path handling creates the appropriate directory structure using mocked `Path` objects.
        - Database session methods (`add`, `flush`, `commit`, and `refresh`) are called exactly once.
        - The resulting investigation instance has the expected title, a generated UUID as `investigation_id`, and is of type :class:`Investigation`.
        """
        title = "Test Investigation"

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir

        result = await create_investigation(
            db=mock_db,
            title=title,
            owner_user_id=None,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify investigation object
        added_investigation = mock_db.add.call_args[0][0]
        assert isinstance(added_investigation, Investigation)
        assert added_investigation.title == title
        assert isinstance(added_investigation.investigation_id, UUID)

        # Verify directory creation
        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    async def test_create_investigation_with_owner(self, mock_settings, mock_path, mock_db):
        """
        Test that creating an investigation correctly assigns the specified owner.

        The test sets up a mock settings object with a temporary base path for investigations and configures the mocked `Path` objects to simulate directory creation without touching the filesystem. It then calls :func:`create_investigation` with a title and an `owner_user_id` and verifies that the investigation instance added to the mocked database session has its `owner_user_id` attribute set to the expected value.

        Parameters
        ----------
        self: object
            The test case instance (unused directly in the test logic).
        mock_settings: unittest.mock.Mock
            Mocked settings providing the `investigations_base_path` configuration.
        mock_path: unittest.mock.patch
            Patched `pathlib.Path` used to intercept filesystem path operations.
        mock_db: unittest.mock.Mock
            Mocked database session with an `add` method that records the added entity.

        Raises
        ------
        AssertionError
            If the `owner_user_id` of the investigation added to the mock database does not match the expected value.
        """
        title = "Test Investigation"
        owner_user_id = 1

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir

        result = await create_investigation(
            db=mock_db,
            title=title,
            owner_user_id=owner_user_id,
        )

        added_investigation = mock_db.add.call_args[0][0]
        assert added_investigation.owner_user_id == owner_user_id

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    @patch("app.crud.investigation.logger")
    async def test_create_investigation_directory_creation_fails(
        self, mock_logger, mock_settings, mock_path, mock_db
    ):
        """
        Test that creating an investigation succeeds even when the underlying directory creation raises an exception.

        The test sets up a mock settings object with `investigations_base_path` pointing to a temporary location and configures the mocked `Path` object's division operator (`__truediv__`) to raise an `Exception` simulating a permission error during directory creation. It then calls :func:`create_investigation` with a sample title and owner ID.

        The expectations are:
        - No exception propagates from `create_investigation`; the operation completes successfully.
        - A warning is emitted via the provided logger, indicating the failure to create the directory.
        - The database session's `commit` method is called exactly once, confirming that the investigation record was persisted despite the filesystem error.
        """
        title = "Test Investigation"

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path to raise exception
        mock_path.return_value.__truediv__.side_effect = Exception("Permission denied")

        # Should not raise, but log warning
        result = await create_investigation(
            db=mock_db,
            title=title,
            owner_user_id=1,
        )

        # Verify warning was logged
        mock_logger.warning.assert_called_once()

        # Verify database operations still completed
        mock_db.commit.assert_called_once()


@pytest.mark.unit
class TestGetInvestigation:
    """Test get_investigation function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session for use in tests.

        Returns
        -------
        AsyncMock
            An instance of `AsyncMock` that mimics an async database session, allowing coroutine methods to be awaited without performing real I/O.
        """
        db = AsyncMock()
        return db

    async def test_get_investigation_found(self, mock_db):
        """
        Test that `get_investigation` correctly retrieves an existing investigation from the database.\n\nThe test creates a mock `Investigation` instance with a known `investigation_id` and configures the mocked DB session to return it when queried. It then calls `await get_investigation` with the mock session and verifies that:\n\n* The returned value matches the expected `Investigation` object.\n* The database `execute` method is invoked exactly once.\n\nParameters\n----------\nself: object\n    The test case instance (unused, required by the unittest framework).\nmock_db: MagicMock\n    A mocked asynchronous database session that mimics the `execute` method and its chained calls.\n\nReturns\n-------\nNone\n    Assertions are used to validate behavior; no value is returned.
        """
        investigation_id = uuid4()
        expected_investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            owner_user_id=1,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = expected_investigation
        mock_db.execute.return_value = mock_result

        result = await get_investigation(mock_db, investigation_id)

        assert result == expected_investigation
        mock_db.execute.assert_called_once()

    async def test_get_investigation_not_found(self, mock_db):
        """
        Test that retrieving an investigation that does not exist returns `None` and that the database session's `execute` method is called exactly once.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        Returns:
            None - this function performs assertions rather than returning a value.
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_investigation(mock_db, investigation_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestListInvestigations:
    """Test list_investigations function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session for use in tests.

        Returns
        -------
        AsyncMock
            A mock object that mimics an asynchronous database session, allowing coroutine methods to be awaited during testing.
        """
        db = AsyncMock()
        return db

    async def test_list_investigations_as_admin(self, mock_db):
        """
        Test that an admin user can retrieve the full list of investigations.

        The test sets up two sample `Investigation` objects and configures a mock database session to return them when queried. It then calls :func:`list_investigations` with `user_id=1` and `is_admin=True` and asserts that:

        * The returned collection contains exactly two items.
        * The returned list matches the predefined investigations.
        * The database `execute` method was invoked exactly once.

        Parameters
        ----------
        self: object
            The test case instance (unused directly in this method).
        mock_db: MagicMock
            A mocked asynchronous database session whose `execute` method is stubbed to return the prepared investigations.
        """
        investigations = [
            Investigation(
                investigation_id=uuid4(),
                title="Investigation 1",
                owner_user_id=1,
            ),
            Investigation(
                investigation_id=uuid4(),
                title="Investigation 2",
                owner_user_id=2,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = investigations
        mock_db.execute.return_value = mock_result

        result = await list_investigations(mock_db, user_id=1, is_admin=True)

        assert len(result) == 2
        assert result == investigations
        mock_db.execute.assert_called_once()

    async def test_list_investigations_as_regular_user(self, mock_db):
        """
        Test listing investigations as a regular user, ensuring only investigations owned by the given user are returned.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        The function creates a mock investigation belonging to `user_id`, configures the mock database to return this investigation, calls `list_investigations` with `is_admin=False`, and asserts that:
        - Exactly one investigation is returned.
        - The returned investigation's `owner_user_id` matches the provided user ID.
        - The database execute method was called exactly once.
        """
        user_id = 1
        user_investigations = [
            Investigation(
                investigation_id=uuid4(),
                title="User Investigation",
                owner_user_id=user_id,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = user_investigations
        mock_db.execute.return_value = mock_result

        result = await list_investigations(mock_db, user_id=user_id, is_admin=False)

        assert len(result) == 1
        assert result[0].owner_user_id == user_id
        mock_db.execute.assert_called_once()

    async def test_list_investigations_empty(self, mock_db):
        """
        Test that listing investigations returns an empty list when the database contains no records for the specified user and non-admin context. Mocks the database execute call to return an empty result set, invokes `list_investigations` with a user ID of 1 and `is_admin=False`, asserts the returned value is an empty list, and verifies that the database `execute` method was called exactly once.
        """
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await list_investigations(mock_db, user_id=1, is_admin=False)

        assert result == []
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestUpdateInvestigation:
    """Test update_investigation function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and configures a mock asynchronous database session for use in tests.

        Returns
            AsyncMock: A mock object representing an async database session with `commit` and `refresh` methods also mocked as asynchronous calls.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_update_investigation_title(self, mock_db):
        """
        Test updating the title of an existing investigation.

        This test creates a mock investigation with an initial title, patches the
        `get_investigation` CRUD helper to return it, and then calls
        `update_investigation` with a new title. After awaiting the update,
        the test asserts that:

        * The investigation object's `title` attribute has been changed to the
          provided new value.
        * The database session's `commit` method was called exactly once.
        * The database session's `refresh` method was called exactly once.

        The function verifies that the update logic correctly modifies the model,
        persists the change, and refreshes the instance from the database.
        """
        investigation_id = uuid4()
        existing_investigation = Investigation(
            investigation_id=investigation_id,
            title="Old Title",
            owner_user_id=1,
        )

        with patch("app.crud.investigation.get_investigation", return_value=existing_investigation):
            result = await update_investigation(
                db=mock_db,
                investigation_id=investigation_id,
                title="New Title",
            )

        assert existing_investigation.title == "New Title"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_update_investigation_not_found(self, mock_db):
        """
        Test that updating an investigation that does not exist raises an HTTPException with a 404 status code.

        Args:
            self: The test case instance.
            mock_db: A mocked database session injected by the test fixture.

        The test generates a random UUID for an investigation ID, patches the `get_investigation` function to return `None` (simulating a missing record), and asserts that calling `update_investigation` raises an `HTTPException`. It verifies that:
        - The exception status code is 404.
        - The exception detail contains the phrase “not found”.
        - No commit operation is performed on the mocked database session.
        """
        investigation_id = uuid4()

        with patch("app.crud.investigation.get_investigation", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await update_investigation(
                    db=mock_db,
                    investigation_id=investigation_id,
                    title="New Title",
                )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()
        mock_db.commit.assert_not_called()

    async def test_update_investigation_no_changes(self, mock_db):
        """
        Test that updating an investigation without providing any new values leaves the existing fields unchanged and still commits the transaction.

        Parameters
        ----------
        self: object
            The test case instance.
        mock_db: MagicMock
            A mocked database session with `commit` method to verify commit behavior.

        The test creates a mock investigation, patches the retrieval function to return it, calls `update_investigation` with `title=None` (indicating no change), and asserts that the title remains as originally set while confirming that `mock_db.commit` was called exactly once.
        """
        investigation_id = uuid4()
        existing_investigation = Investigation(
            investigation_id=investigation_id,
            title="Original Title",
            owner_user_id=1,
        )

        with patch("app.crud.investigation.get_investigation", return_value=existing_investigation):
            result = await update_investigation(
                db=mock_db,
                investigation_id=investigation_id,
                title=None,  # No change
            )

        assert existing_investigation.title == "Original Title"
        mock_db.commit.assert_called_once()


@pytest.mark.unit
class TestDeleteInvestigation:
    """Test delete_investigation function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session for testing purposes.

        The returned object mimics an async SQLAlchemy session with its `execute` and `commit` methods also mocked as coroutines, allowing test code to await these calls without performing any real I/O.

        Returns:
            AsyncMock: A fully mocked async database session with `execute` and `commit` attributes set to AsyncMock instances.
        """
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    async def test_delete_investigation_success(self, mock_settings, mock_path, mock_db):
        """
        Test that an investigation is successfully deleted, ensuring the database delete operation and commit are invoked, while handling filesystem path resolution using mocked settings and path objects.
        """
        investigation_id = uuid4()
        deleted_by_user_id = 1

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_dir.exists.return_value = True
        mock_path.return_value.__truediv__.return_value = mock_dir

        await delete_investigation(
            db=mock_db,
            investigation_id=investigation_id,
            deleted_by_user_id=deleted_by_user_id,
        )

        # Verify database deletion
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    @patch("app.crud.investigation.logger")
    async def test_delete_investigation_filesystem_cleanup_fails(
        self, mock_logger, mock_settings, mock_path, mock_db
    ):
        """
        Test that an investigation can be deleted even when the filesystem cleanup step raises an exception.

        The test sets up a mock environment where:
        - `mock_settings.investigations_base_path` points to a temporary directory.
        - The `Path.__truediv__` operation is mocked to raise an `Exception` simulating a permission error during file removal.
        - A call to the `delete_investigation` service function is made with a generated investigation ID and a user identifier for the deletion actor.

        The test asserts that:
        - No exception propagates from `delete_investigation`; the operation completes successfully.
        - A warning message is logged exactly once, indicating the filesystem cleanup failure.
        - The database transaction is still committed, confirming that the investigation record was removed despite the cleanup issue.
        """
        investigation_id = uuid4()
        deleted_by_user_id = 1

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path to raise exception
        mock_path.return_value.__truediv__.side_effect = Exception("Permission denied")

        # Should not raise, but log warning
        await delete_investigation(
            db=mock_db,
            investigation_id=investigation_id,
            deleted_by_user_id=deleted_by_user_id,
        )

        # Verify warning was logged
        mock_logger.warning.assert_called_once()

        # Verify database deletion still completed
        mock_db.commit.assert_called_once()

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    async def test_delete_investigation_directory_not_exists(
        self, mock_settings, mock_path, mock_db
    ):
        """
        Test deletion of an investigation when its directory does not exist on the filesystem.

        This test verifies that:
        - The `delete_investigation` service correctly handles a missing investigation directory without raising errors.
        - The database transaction is still committed, ensuring the investigation record is removed even though no file cleanup occurs.

        Parameters
        ----------
        self : object
            Instance of the test class containing this method.
        mock_settings : MagicMock
            Mocked settings object where `investigations_base_path` is set to a temporary path.
        mock_path : MagicMock
            Mocked pathlib.Path constructor used to simulate filesystem paths; configured to return a mock directory whose `exists()` returns `False`.
        mock_db : MagicMock
            Mocked database session that records calls to `commit()` and other ORM operations.

        The test creates a random `investigation_id` and a dummy `deleted_by_user_id`, configures the mocks, invokes `delete_investigation` with these arguments, and asserts that `mock_db.commit` was called exactly once.
        """
        investigation_id = uuid4()
        deleted_by_user_id = 1

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock directory doesn't exist
        mock_dir = MagicMock()
        mock_dir.exists.return_value = False
        mock_path.return_value.__truediv__.return_value = mock_dir

        await delete_investigation(
            db=mock_db,
            investigation_id=investigation_id,
            deleted_by_user_id=deleted_by_user_id,
        )

        # Verify database deletion completed
        mock_db.commit.assert_called_once()


@pytest.mark.unit
class TestCheckInvestigationAccess:
    """Test check_investigation_access function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session.

        This helper constructs an :class:`unittest.mock.AsyncMock` instance that mimics the behavior of an async
        database session used throughout the test suite. The returned mock can be configured with
        desired side effects or return values by the caller.

        Returns
        -------
        AsyncMock
            A fresh mock object representing an asynchronous database connection.
        """
        db = AsyncMock()
        return db

    async def test_check_access_admin_user(self, mock_db):
        """
        Test that an admin user (role=1) has permission to access any investigation regardless of ownership.

        Args:
            self: Test case instance.
            mock_db: Mocked database session fixture injected by the test framework.

        Creates a dummy Investigation with a specific `investigation_id` and an owner different from the admin user. Mocks the `get_investigation` CRUD function to return this investigation when called.

        Calls `check_investigation_access` with the mocked DB, investigation ID, and the admin user.

        Asserts that the returned value is exactly the mocked Investigation instance, confirming that admin access bypasses ownership checks.
        """
        investigation_id = uuid4()
        investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            owner_user_id=2,  # Different user
        )
        admin_user = User(user_id=1, username="admin", role=1)

        with patch("app.crud.investigation.get_investigation", return_value=investigation):
            result = await check_investigation_access(
                db=mock_db,
                investigation_id=investigation_id,
                user=admin_user,
            )

        assert result == investigation

    async def test_check_access_owner(self, mock_db):
        """
        Test that an investigation owner is granted access.\n\nArgs:\n    self: The test case instance.\n    mock_db: A mocked database session fixture used by the test.\n\nThe test creates a dummy Investigation object with a specific `investigation_id` and assigns it to a user identified by `user_id`. It also constructs a User object representing the owner (role 0). By patching `app.crud.investigation.get_investigation` to return the dummy investigation, the test invokes `check_investigation_access` with the mock database, investigation ID, and user.\n\nThe function should return the same Investigation instance when the requesting user is the owner. The test asserts that the returned value matches the expected investigation.\"""
        """
        investigation_id = uuid4()
        user_id = 1
        investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            owner_user_id=user_id,
        )
        user = User(user_id=user_id, username="user", role=0)

        with patch("app.crud.investigation.get_investigation", return_value=investigation):
            result = await check_investigation_access(
                db=mock_db,
                investigation_id=investigation_id,
                user=user,
            )

        assert result == investigation

    async def test_check_access_denied(self, mock_db):
        """
        Test that a user who is not the owner of an investigation receives a 403 HTTPException when attempting to access it.

        Args:
            self: The test case instance.
            mock_db: A mocked database session fixture injected by pytest.

        Raises:
            AssertionError: If the expected HTTPException is not raised, or if its status code is not 403, or if the exception detail does not contain "access denied".
        """
        investigation_id = uuid4()
        investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            owner_user_id=2,  # Different user
        )
        user = User(user_id=1, username="user", role=0)

        with patch("app.crud.investigation.get_investigation", return_value=investigation):
            with pytest.raises(HTTPException) as exc_info:
                await check_investigation_access(
                    db=mock_db,
                    investigation_id=investigation_id,
                    user=user,
                )

        assert exc_info.value.status_code == 403
        assert "access denied" in exc_info.value.detail.lower()

    async def test_check_access_not_found(self, mock_db):
        """
        Test that attempting to access an investigation that does not exist raises a 404 HTTPException.\n\nThe test generates a random UUID for the investigation ID and creates a dummy `User` instance.\nIt patches `app.crud.investigation.get_investigation` to return `None`, simulating a missing record.\nWhen `check_investigation_access` is called with these arguments, the function should raise an\n`HTTPException` whose status code is 404 and whose detail message contains the phrase \"not found\".
        """
        investigation_id = uuid4()
        user = User(user_id=1, username="user", role=0)

        with patch("app.crud.investigation.get_investigation", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await check_investigation_access(
                    db=mock_db,
                    investigation_id=investigation_id,
                    user=user,
                )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


@pytest.mark.unit
class TestSetParsingLock:
    """Test set_parsing_lock function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return an asynchronous mock database session.

        The returned object mimics the essential async methods used by the application:
        - `commit` - an :class:`unittest.mock.AsyncMock` representing a commit operation.
        - `refresh` - an :class:`unittest.mock.AsyncMock` representing a refresh operation.

        This helper is intended for use in unit tests where a real database session is not required. It provides a lightweight, fully asynchronous mock that can be awaited and inspected for call assertions.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_set_parsing_lock_true(self, mock_db):
        """
        Test that the `set_parsing_lock` coroutine correctly updates an investigation's `parsing_locked` flag to `True`.

        The test creates a mock `Investigation` instance with `parsing_locked=False`, patches the `get_investigation` function to return this instance, and then calls `set_parsing_lock` with `locked=True`. After awaiting the call, it asserts that the investigation's `parsing_locked` attribute has been set to `True` and verifies that the database session's `commit` and `refresh` methods were each invoked exactly once.

        Parameters
        ----------
        self : object
            The test case instance (provided by the testing framework).
        mock_db : unittest.mock.AsyncMock
            A mocked asynchronous database session exposing `commit` and `refresh` methods used to verify that changes are persisted.

        Raises
        ------
        AssertionError
            If the investigation's `parsing_locked` attribute is not `True` after the call, or if `commit`/`refresh` were not called exactly once.
        """
        investigation_id = uuid4()
        investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            parsing_locked=False,
        )

        with patch("app.crud.investigation.get_investigation", return_value=investigation):
            result = await set_parsing_lock(
                db=mock_db,
                investigation_id=investigation_id,
                locked=True,
            )

        assert investigation.parsing_locked is True
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_set_parsing_lock_false(self, mock_db):
        """
        Test that `set_parsing_lock` correctly updates an investigation's `parsing_locked` flag to `False` and commits the change to the database. The test creates a mock investigation with `parsing_locked=True`, patches the `get_investigation` call to return it, invokes `set_parsing_lock` with `locked=False`, then asserts that the investigation's attribute is set to `False` and that `db.commit` was called exactly once.
        """
        investigation_id = uuid4()
        investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            parsing_locked=True,
        )

        with patch("app.crud.investigation.get_investigation", return_value=investigation):
            result = await set_parsing_lock(
                db=mock_db,
                investigation_id=investigation_id,
                locked=False,
            )

        assert investigation.parsing_locked is False
        mock_db.commit.assert_called_once()

    async def test_set_parsing_lock_not_found(self, mock_db):
        """
        Test that attempting to set a parsing lock on an investigation that does not exist returns `None` and does not commit any changes to the database.

        The test:
        - Generates a random UUID for an investigation ID.
        - Mocks `app.crud.investigation.get_investigation` to return `None`, simulating a missing record.
        - Calls `set_parsing_lock` with `locked=True`.
        - Asserts that the result is `None`.
        - Verifies that `mock_db.commit` was never invoked, ensuring no unintended database writes occur.
        """
        investigation_id = uuid4()

        with patch("app.crud.investigation.get_investigation", return_value=None):
            result = await set_parsing_lock(
                db=mock_db,
                investigation_id=investigation_id,
                locked=True,
            )

        assert result is None
        mock_db.commit.assert_not_called()


@pytest.mark.unit
class TestIsParsingLocked:
    """Test is_parsing_locked function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session.

        Returns
        -------
        AsyncMock
            A mocked async database session that can be used in tests.
        """
        db = AsyncMock()
        return db

    async def test_is_parsing_locked_true(self, mock_db):
        """
        Test that `is_parsing_locked` correctly reports a locked state.\n\nThe test creates an :class:`~app.models.Investigation` instance with `parsing_locked` set to `True` and patches `app.crud.investigation.get_investigation` to return this object. It then calls the asynchronous `is_parsing_locked` function with a mocked database session and verifies that the result is `True`.\n\nArgs:\n    self: The test case instance (unused).\n    mock_db: A fixture providing a mocked database session.\n\nReturns:\n    None - assertions are used to validate behavior.
        """
        investigation_id = uuid4()
        investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            parsing_locked=True,
        )

        with patch("app.crud.investigation.get_investigation", return_value=investigation):
            result = await is_parsing_locked(mock_db, investigation_id)

        assert result is True

    async def test_is_parsing_locked_false(self, mock_db):
        """
        Test that `is_parsing_locked` correctly reports a false lock status when the investigation's `parsing_locked` flag is set to `False`.

        The test creates a mock investigation with a unique identifier and `parsing_locked=False`, patches the `get_investigation` CRUD call to return this object, invokes `is_parsing_locked` with a mocked database session, and asserts that the returned value is `False`.

        Parameters
        ----------
        self: unittest.TestCase instance
            The test case instance providing context for the async test method.
        mock_db: MagicMock
            A mock of the asynchronous database session passed to the CRUD function.

        Returns
        -------
        None
            The function uses assertions to validate behavior rather than returning a value.
        """
        investigation_id = uuid4()
        investigation = Investigation(
            investigation_id=investigation_id,
            title="Test Investigation",
            parsing_locked=False,
        )

        with patch("app.crud.investigation.get_investigation", return_value=investigation):
            result = await is_parsing_locked(mock_db, investigation_id)

        assert result is False

    async def test_is_parsing_locked_not_found(self, mock_db):
        """
        Test that `is_parsing_locked` returns `False` when the requested investigation does not exist in the database. The test creates a random UUID, patches the `get_investigation` CRUD call to return `None`, invokes the async function with a mocked DB session, and asserts that the result is `False`.
        """
        investigation_id = uuid4()

        with patch("app.crud.investigation.get_investigation", return_value=None):
            result = await is_parsing_locked(mock_db, investigation_id)

        assert result is False


@pytest.mark.unit
class TestInvestigationCRUDEdgeCases:
    """Test edge cases for investigation CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mock asynchronous database session for testing.

        The returned object mimics an async SQLAlchemy session with the following attributes:
        - `add`: a :class:`unittest.mock.MagicMock` used to record calls to `session.add(...)`.
        - `flush`: an :class:`unittest.mock.AsyncMock` representing the asynchronous `session.flush()` method.
        - `commit`: an :class:`unittest.mock.AsyncMock` for the asynchronous `session.commit()` method.
        - `refresh`: an :class:`unittest.mock.AsyncMock` used to simulate `session.refresh(...)`.

        The mock session can be injected into code under test to verify that CRUD operations interact with the database as expected without requiring a real connection.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    async def test_create_investigation_with_unicode_title(self, mock_settings, mock_path, mock_db):
        """
        Test that creating an investigation with a Unicode title correctly stores the title in the database.

        The test sets up a mock settings object to define the base path for investigations and configures the mocked Path objects to simulate directory creation. It then calls `create_investigation` with a Unicode title containing Japanese characters, an emoji, and Cyrillic text, along with an owner user ID.

        After the coroutine completes, the test verifies that the investigation instance added to the mock database session has its `title` attribute set exactly to the provided Unicode string. This ensures that Unicode titles are handled without data loss or encoding errors.
        """
        title = "調査 🔍 расследование"

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir

        result = await create_investigation(
            db=mock_db,
            title=title,
            owner_user_id=1,
        )

        added_investigation = mock_db.add.call_args[0][0]
        assert added_investigation.title == title

    @patch("app.crud.investigation.Path")
    @patch("app.crud.investigation.settings")
    async def test_create_investigation_with_very_long_title(
        self, mock_settings, mock_path, mock_db
    ):
        """
        Test creating an investigation when the title exceeds typical length limits.

        This test verifies that:
        - A very long title (1,000 characters) can be passed to `create_investigation` without raising errors.
        - The settings object correctly provides the base path for investigations.
        - Path handling is mocked so no real filesystem interaction occurs.
        - After calling `create_investigation`, the investigation instance added to the mock database has a title whose length matches the input (1000 characters).

        Args:
            self: Test case instance (unused directly in the test logic).
            mock_settings: Fixture that provides a mock settings object; its `investigations_base_path` attribute is set to a temporary directory.
            mock_path: Fixture that patches `pathlib.Path`; returns a mocked directory path used by the function under test.
            mock_db: Fixture that supplies a mock database session with an `add` method captured for inspection.
        """
        title = "A" * 1000

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir

        result = await create_investigation(
            db=mock_db,
            title=title,
            owner_user_id=1,
        )

        added_investigation = mock_db.add.call_args[0][0]
        assert len(added_investigation.title) == 1000
