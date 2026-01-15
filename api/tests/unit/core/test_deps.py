"""
Unit tests for dependency injection functions.
Tests authentication and authorization dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.deps import get_current_user, require_admin, get_current_user_optional
from app.models.user import User


@pytest.mark.unit
class TestGetCurrentUser:
    """Test get_current_user dependency."""

    @patch("app.deps.verify_jwt_token")
    @patch("app.deps.get_user_by_id")
    async def test_get_current_user_success(
        self,
        mock_get_user,
        mock_verify_token,
    ):
        """
        Test that `get_current_user` correctly extracts user information when provided with a valid JWT token.

        Args:
            self: The test case instance.
            mock_get_user: Mock for the database function that retrieves a user by ID.
            mock_verify_token: Mock for the JWT verification function.

        The test sets up an asynchronous mock database and a dummy token, configures the mocks to return a payload containing `sub` set to `"1"`, and provides a fake `User` instance. It then calls `get_current_user` with the token and verifies that the returned object's `username` is `"testuser"` and its `user_id` is `1`.
        """
        db = AsyncMock()
        token = "valid_token"

        # Mock token verification
        mock_verify_token.return_value = {
            "sub": "1",
        }

        # Mock user retrieval
        mock_user = User(
            user_id=1,
            username="testuser",
            password_hash="hash",
            role=0,
        )
        mock_get_user.return_value = mock_user

        user = await get_current_user(token=token, db=db)

        assert user.username == "testuser"
        assert user.user_id == 1

    @patch("app.deps.verify_jwt_token")
    async def test_get_current_user_no_token(
        self,
        mock_verify_token,
    ):
        """
        Test that `get_current_user` raises an `HTTPException` with a 401 status code when no JWT token is provided.

        Args:
            self: The test class instance.
            mock_verify_token: Fixture that patches the token verification logic (unused in this test).

        The test creates an asynchronous mock database, passes `None` as the token, and asserts that invoking `get_current_user` results in an `HTTPException` whose `status_code` attribute equals 401.
        """
        db = AsyncMock()
        token = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=db)

        assert exc_info.value.status_code == 401

    @patch("app.deps.verify_jwt_token")
    @patch("app.deps.get_user_by_id")
    async def test_get_current_user_not_found(
        self,
        mock_get_user,
        mock_verify_token,
    ):
        """
        Test that `get_current_user` raises an `HTTPException` with status code 401 when the JWT token is valid but the corresponding user cannot be found in the database. The test mocks the token verification to return a payload containing a user identifier and mocks the database call to return `None`, then asserts that the exception raised has the expected status code.
        """
        db = AsyncMock()
        token = "valid_token"

        mock_verify_token.return_value = {"sub": "1"}
        mock_get_user.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=db)

        assert exc_info.value.status_code == 401


@pytest.mark.unit
class TestRequireAdmin:
    """Test require_admin dependency."""

    async def test_require_admin_success(self):
        """
        Test that require_admin returns the provided admin user when called with a user object whose role indicates administrative privileges. The function creates an admin User instance, invokes require_admin with it, and asserts that the result matches the original admin_user. This verifies successful authorization for admin users without raising errors.
        """
        admin_user = User(
            user_id=1,
            username="admin",
            password_hash="hash",
            role=1,
        )

        result = await require_admin(user=admin_user)
        assert result == admin_user

    async def test_require_admin_failure(self):
        """
        Test that the `require_admin` dependency raises an HTTP 403 error when called with a user who does not have admin privileges. The test creates a regular user (role set to `0`), invokes `require_admin` with this user, and asserts that a `HTTPException` is raised with a status code of 403.
        """
        regular_user = User(
            user_id=1,
            username="user",
            password_hash="hash",
            role=0,
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=regular_user)

        assert exc_info.value.status_code == 403


@pytest.mark.unit
class TestGetCurrentUserOptional:
    """Test get_current_user_optional dependency."""

    @patch("app.deps.verify_jwt_token")
    @patch("app.deps.get_user_by_id")
    async def test_get_optional_user_with_token(
        self,
        mock_get_user,
        mock_verify_token,
    ):
        """
        Test that `get_current_user_optional` correctly retrieves and returns a user object when provided with a valid JWT token.

        Args:
            self: The test case instance.
            mock_get_user: Mock for the database function that fetches a user by ID.
            mock_verify_token: Mock for the JWT verification utility.

        The test sets up an asynchronous mock database, supplies a dummy valid token, and configures the mocks to return a decoded payload with `sub` equal to `"1"` and a corresponding `User` instance. It then calls `get_current_user_optional` with the token and asserts that the returned user is not `None` and that its `username` matches the expected value.
        """
        db = AsyncMock()
        token = "valid_token"

        mock_verify_token.return_value = {"sub": "1"}
        mock_user = User(
            user_id=1,
            username="testuser",
            password_hash="hash",
            role=0,
        )
        mock_get_user.return_value = mock_user

        user = await get_current_user_optional(token=token, db=db)

        assert user is not None
        assert user.username == "testuser"

    async def test_get_optional_user_no_token(self):
        """
        Test that get_current_user_optional returns None when no JWT token is provided, ensuring optional authentication does not raise errors.
        """
        db = AsyncMock()
        token = None

        user = await get_current_user_optional(token=token, db=db)

        assert user is None

    @patch("app.deps.verify_jwt_token")
    async def test_get_optional_user_invalid_token(
        self,
        mock_verify_token,
    ):
        """
        Test that `get_current_user_optional` returns `None` when the provided JWT token is invalid.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_verify_token : unittest.mock.Mock
            Mocked dependency for token verification; configured to raise an exception indicating an invalid token.

        Behavior
        --------
        * Sets up a mock asynchronous database session.
        * Provides an intentionally invalid token string.
        * Configures `mock_verify_token` to raise `Exception("Invalid token")` when called.
        * Calls `get_current_user_optional` with the invalid token and mocked DB.
        * Asserts that the function returns `None`, confirming graceful handling of authentication failures without propagating errors.
        """
        db = AsyncMock()
        token = "invalid_token"

        mock_verify_token.side_effect = Exception("Invalid token")

        user = await get_current_user_optional(token=token, db=db)

        assert user is None
