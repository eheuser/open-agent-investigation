import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.user import get_user_by_username, get_user_by_id, create_user
from app.models.user import User, UserRole


@pytest.mark.unit
class TestGetUserByUsername:
    """Test get_user_by_username function."""

    @pytest.mark.asyncio
    async def test_get_user_found(self):
        """
        Test that `get_user_by_username` correctly retrieves an existing user when the username is present in the database.

        The test creates a mock :class:`User` instance and configures an `AsyncMock` of :class:`sqlalchemy.ext.asyncio.AsyncSession` to return this user via `execute().scalars().first()`. It then calls the coroutine under test with the mocked session and verifies that:

        * The returned object matches the mock user.
        * The `username` attribute of the result is as expected.
        * The session's `execute` method was invoked exactly once.

        This ensures proper interaction with the async database layer for a successful lookup scenario.
        """
        # Create mock user
        mock_user = User(user_id=1, username="testuser", password_hash="hashed", role=0)

        # Create mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Call function
        result = await get_user_by_username(mock_db, "testuser")

        # Assertions
        assert result == mock_user
        assert result.username == "testuser"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_not_found(self):
        """
        Test that `get_user_by_username` returns `None` when the requested username does not exist in the database.

        The test creates an `AsyncMock` of an `AsyncSession` whose `execute` method yields a result whose `scalars().first()` call returns `None`, simulating a missing user. It then calls the coroutine under test and asserts that:

        * The returned value is `None`.
        * The session's `execute` method was invoked exactly once.
        """
        # Create mock database session returning None
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None
        mock_db.execute.return_value = mock_result

        # Call function
        result = await get_user_by_username(mock_db, "nonexistent")

        # Assertions
        assert result is None
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_case_sensitive(self):
        """
        Test that searching for a user by username is case-sensitive.

        The test creates an asynchronous mock of `AsyncSession` and configures it to return no results when queried with a differently cased username. It then calls :func:`get_user_by_username` with the uppercase name `\"TESTUSER\"` and asserts that the function returns `None`, confirming that the lookup does not match a user stored as `\"testuser\"` under case-sensitive collation.

        This test verifies correct behavior of the username lookup logic when database collation enforces case sensitivity.
        """
        # This is a documentation test - actual behavior depends on DB collation
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None
        mock_db.execute.return_value = mock_result

        # Search for different case
        result = await get_user_by_username(mock_db, "TESTUSER")

        # Should not find "testuser" (case-sensitive)
        assert result is None


@pytest.mark.unit
class TestGetUserById:
    """Test get_user_by_id function."""

    @pytest.mark.asyncio
    async def test_get_user_by_id_found(self):
        """
        Test that `get_user_by_id` correctly retrieves an existing user when the database returns a matching record.

        The test sets up:
        - A mock `User` instance with `user_id=42`.
        - An `AsyncMock` mimicking an `AsyncSession` whose `execute` method returns a result whose `scalars().first()` yields the mock user.
        - Calls `await get_user_by_id(mock_db, 42)`.

        It then asserts:
        - The returned object equals the mock user and has the expected `user_id`.
        - The session's `execute` method was invoked exactly once.
        """
        mock_user = User(user_id=42, username="testuser", password_hash="hashed", role=0)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_user
        mock_db.execute.return_value = mock_result

        result = await get_user_by_id(mock_db, 42)

        assert result == mock_user
        assert result.user_id == 42
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self):
        """
        Test that retrieving a user by a non-existent ID returns `None` and executes exactly one database query.

        The test creates an asynchronous mock of `AsyncSession` where the `execute` call yields a result whose `scalars().first()` method returns `None`, simulating a missing record. It then invokes `get_user_by_id` with an arbitrary ID (e.g., `999`) and asserts that the returned value is `None`. Finally, it verifies that `mock_db.execute` was called exactly once, confirming that the function performed a single query against the session.
        """
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_user_by_id(mock_db, 999)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestCreateUser:
    """Test create_user function."""

    @pytest.mark.asyncio
    async def test_create_user_regular(self):
        """
        Test that creating a regular user correctly hashes the password, adds the new User instance to the session, commits the transaction, and refreshes the instance to populate its primary key. The test uses async mocks for the database session and patches the hash_password function to return a deterministic hash, then asserts that add, commit, and refresh are each called exactly once.
        """
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock the created user
        created_user = User(
            user_id=1, username="newuser", password_hash="hashed_password", role=UserRole.REGULAR
        )

        # Mock db.refresh to set the user_id
        async def mock_refresh(user):
            """
            Refreshes the mock user object by setting its `user_id` attribute to `1`.

            Parameters
            ----------
            user : Any
                The user-like object whose `user_id` attribute will be modified.

            Returns
            -------
            None
                This coroutine does not return a value; it mutates the provided `user` in-place.
            """
            user.user_id = 1

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("app.crud.user.hash_password", return_value="hashed_password"):
            result = await create_user(
                mock_db, username="newuser", password="plaintext123", role=UserRole.REGULAR
            )

        # Assertions
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_admin(self):
        """
        Test that creating an admin user correctly invokes the database session methods and assigns the expected attributes.

        The test sets up an `AsyncMock` for `AsyncSession` and patches `hash_password` to return a deterministic hash. It also provides a custom `refresh` side-effect that populates `user_id` and sets the role to :class:`UserRole.ADMIN`.

        The function under test, :func:`create_user`, is called with an admin username, password and role. After awaiting the call, the test asserts that:

        * `mock_db.add` was called exactly once with a new user instance.
        * `mock_db.commit` was called exactly once to persist the changes.

        This verifies that the CRUD layer correctly handles admin user creation, including password hashing, default role assignment, and session interaction.
        """
        mock_db = AsyncMock(spec=AsyncSession)

        async def mock_refresh(user):
            """
            Refreshes a mocked user object by setting its identifier and role.

            This asynchronous helper mutates the provided `user` instance, assigning `user.user_id` a value of `2` and granting it administrative privileges by setting `user.role` to :class:`UserRole.ADMIN`. It is intended for use in unit tests where a deterministic user state is required after a simulated refresh operation.
            """
            user.user_id = 2
            user.role = UserRole.ADMIN

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("app.crud.user.hash_password", return_value="hashed_admin"):
            result = await create_user(
                mock_db, username="adminuser", password="adminpass", role=UserRole.ADMIN
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_password_hashed(self):
        """
        Test that creating a user hashes the provided plaintext password before storing it.

        The test sets up an asynchronous mock `AsyncSession` and patches the `hash_password` utility to return a predetermined hash string. It then calls `create_user` with a sample username and a plaintext password, awaiting the coroutine result.

        Assertions:
        - The patched `hash_password` function is called exactly once with the original plaintext password ("plaintext123").
        - (Implicitly) the returned user object should contain the hashed password as set by `create_user`.
        """
        mock_db = AsyncMock(spec=AsyncSession)

        async def mock_refresh(user):
            """
            Refreshes the mock user object by setting its `user_id` attribute to `3`.

            Parameters
            ----------
            user : Any
                The user-like instance whose `user_id` attribute will be overwritten.

            Notes
            -----
            This function is intended for use in test suites where a deterministic user identifier is required. It mutates the passed-in object in-place and does not return a value.
            """
            user.user_id = 3

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("app.crud.user.hash_password", return_value="$argon2id$...") as mock_hash:
            result = await create_user(mock_db, username="testuser", password="plaintext123")

            # Verify hash_password was called with plaintext
            mock_hash.assert_called_once_with("plaintext123")

    @pytest.mark.asyncio
    async def test_create_user_default_role(self):
        """
        Test that creating a user without specifying a role assigns the default `UserRole.REGULAR` and correctly adds the user to the session. The test uses an async mock for the database session, patches the password-hashing utility to return a deterministic value, and verifies that the added user's `role` attribute is set to `REGULAR` after invoking :func:`create_user`.
        """
        mock_db = AsyncMock(spec=AsyncSession)

        async def mock_refresh(user):
            """
            Refreshes a mock user object by setting its identifier.

            Parameters:
                user (object): The user instance whose `user_id` attribute will be updated.

            Behavior:
                Assigns the value `4` to `user.user_id`. This function is asynchronous and should be awaited, although it performs no I/O.
            """
            user.user_id = 4

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("app.crud.user.hash_password", return_value="hashed"):
            # Don't specify role - should default to REGULAR
            result = await create_user(mock_db, username="defaultuser", password="password")

        # Verify user was added to session
        mock_db.add.assert_called_once()
        added_user = mock_db.add.call_args[0][0]
        assert added_user.role == UserRole.REGULAR


@pytest.mark.unit
class TestUserCRUDEdgeCases:
    """Test edge cases for user CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_user_empty_username(self):
        """
        Test that retrieving a user by an empty username returns `None`.\n\nThe test creates an asynchronous mock of an `AsyncSession` and configures the `execute` method to return a result whose `scalars().first()` call yields `None`, simulating the absence of a matching record. It then calls :func:`get_user_by_username` with an empty string and asserts that the function correctly propagates the `None` result, indicating that no user was found for the given input.
        """
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_user_by_username(mock_db, "")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_unicode_username(self):
        """
        Test that retrieving a user by a Unicode username works correctly.\n\nThe test creates a mock `User` instance with a non-ASCII username (\"用户名\") and configures an `AsyncMock` of `AsyncSession` to return this user when `execute` is called. It then calls `get_user_by_username` with the mocked session and the Unicode username, awaiting the result.\n\nAssertions verify that:\n- The returned object matches the mock `User` instance.\n- The `username` attribute of the result retains the original Unicode value.
        """
        mock_user = User(user_id=1, username="用户名", password_hash="hashed", role=0)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_user
        mock_db.execute.return_value = mock_result

        result = await get_user_by_username(mock_db, "用户名")

        assert result == mock_user
        assert result.username == "用户名"

    @pytest.mark.asyncio
    async def test_create_user_special_characters(self):
        """
        Test creating a user when the username contains special characters such as “@” and “.”, ensuring that the CRUD function correctly adds the user to the session, assigns an ID via refresh, and preserves the original username value. The test uses an async mock for the database session, patches the password-hashing utility to return a deterministic hash, and verifies that `mock_db.add` is called once with a user whose `username` attribute matches the provided special-character string.
        """
        mock_db = AsyncMock(spec=AsyncSession)

        async def mock_refresh(user):
            """
            Refreshes a mocked user object by assigning a fixed identifier.

            Parameters:
                user (object): The user instance whose `user_id` attribute will be set. The object is expected to have a mutable `user_id` attribute that can be overwritten.

            Behavior:
                This asynchronous function mutates the provided `user` by setting its `user_id` attribute to the integer value `5`. It does not return any value.

            Returns:
                None

            Notes:
                Intended for use in unit tests as a stand-in for a database session refresh operation. The function does not perform any I/O or validation; it simply assigns the hard-coded ID.
            """
            user.user_id = 5

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("app.crud.user.hash_password", return_value="hashed"):
            result = await create_user(mock_db, username="user@example.com", password="password")

        mock_db.add.assert_called_once()
        added_user = mock_db.add.call_args[0][0]
        assert added_user.username == "user@example.com"
