"""
Integration tests for authentication endpoints.
Tests login, registration, and token verification.
"""

import pytest
from httpx import AsyncClient

from app.auth import hash_password
from tests.factories import UserFactory


@pytest.mark.integration
class TestLogin:
    """Test login endpoint."""

    async def test_login_success(self, async_client: AsyncClient, test_user):
        """
        Test that a user can successfully log in with valid credentials.

        The test sends a POST request to the `/api/v1/auth/login` endpoint using an asynchronous HTTP client. It supplies a JSON payload containing a known username and password (`testuser` / `testpass123`). The response is expected to have:

        * A status code of **200** indicating success.
        * A JSON body that includes:
          * An `access_token` field with a non-empty string value.
          * A `token_type` equal to `"bearer"`.
          * A `username` matching the supplied username (`testuser`).
          * A `role` of `0`, representing a regular user.

        The assertions verify both the HTTP status and the presence and correctness of these fields, confirming that the authentication flow works as intended for valid credentials.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "testuser", "password": "testpass123"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == "testuser"
        assert data["role"] == 0  # Regular user
        assert len(data["access_token"]) > 0

    async def test_login_invalid_username(self, async_client: AsyncClient):
        """
        Test that attempting to log in with a username that does not exist results in an HTTP 401 Unauthorized response and includes an appropriate error detail indicating invalid credentials. The request is sent to the login endpoint with a JSON payload containing a non-existent username and a password, then the response status code and error message are asserted.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "nonexistent", "password": "password123"}
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "username or password" in data["detail"].lower()

    async def test_login_invalid_password(self, async_client: AsyncClient, test_user):
        """
        Test that attempting to log in with an incorrect password returns a 401 Unauthorized response and includes an appropriate error detail indicating invalid credentials.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "testuser", "password": "wrongpassword"}
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "username or password" in data["detail"].lower()

    async def test_login_empty_credentials(self, async_client: AsyncClient):
        """
        Test that attempting to log in with empty username and password returns an HTTP 401 Unauthorized response.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "", "password": ""}
        )

        assert response.status_code == 401

    async def test_login_missing_fields(self, async_client: AsyncClient):
        """
        Test login endpoint with incomplete credentials.

        Verifies that submitting a request without all required fields (e.g., missing `password`) results in an HTTP 422 response, indicating validation failure for the login payload.
        """
        response = await async_client.post("/api/v1/auth/login", json={"username": "testuser"})

        assert response.status_code == 422  # Validation error

    async def test_login_admin_user(self, async_client: AsyncClient, admin_user):
        """
        Test that an admin user can successfully log in via the authentication endpoint.

        The test sends a POST request with valid admin credentials to `/api/v1/auth/login` and verifies:
        - The response status code is 200 (OK).
        - The returned JSON payload contains the expected `username` value.
        - The user's role is correctly identified as an administrator (role identifier `1`).
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "adminuser", "password": "adminpass123"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["username"] == "adminuser"
        assert data["role"] == 1  # Admin


@pytest.mark.integration
class TestRegister:
    """Test registration endpoint."""

    async def test_register_success(self, async_client: AsyncClient):
        """
        Test that a new user can register successfully via the `/api/v1/auth/register` endpoint.

        The request is sent with a JSON payload containing a unique `username` and a valid `password`.
        The test asserts that:

        - The HTTP status code returned is **201 Created**.
        - The response body includes an `access_token` field.
        - The `token_type` field equals `"bearer"`.
        - The `username` in the response matches the one supplied in the request.
        - The `role` field is set to `0`, indicating a standard user.
        """
        response = await async_client.post(
            "/api/v1/auth/register", json={"username": "newuser", "password": "newpass123"}
        )

        assert response.status_code == 201
        data = response.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == "newuser"
        assert data["role"] == 0  # Regular user by default

    async def test_register_duplicate_username(self, async_client: AsyncClient, test_user):
        """
        Test registration with an already existing username.

        Ensures that attempting to register a user whose username is already present in the system results in a 400 Bad Request response. The test verifies that:
        - The HTTP status code returned is 400.
        - The response JSON contains a "detail" field.
        - The detail message includes an indication that the username is already registered (case-insensitive check).
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "testuser", "password": "password123"},  # Already exists
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "already registered" in data["detail"].lower()

    async def test_register_invalid_username(self, async_client: AsyncClient):
        """
        Test the registration endpoint with an invalid username (empty string) and verify that the response status code reflects either successful creation or appropriate validation error.

        Args:
            self: Test case instance.
            async_client: An HTTPX AsyncClient configured for making requests to the API.

        The test sends a POST request to "/api/v1/auth/register" with a payload containing an empty username and a valid password, then asserts that the response status code is one of 201 (created), 400 (bad request), or 422 (unprocessable entity), depending on the server's validation behavior.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "", "password": "password123"},  # Empty username
        )

        # Should either reject or create (depending on validation)
        # Current implementation allows empty username
        assert response.status_code in [201, 400, 422]

    async def test_register_weak_password(self, async_client: AsyncClient):
        """
        Test the user registration endpoint with a weak password.

        This asynchronous test sends a POST request to `/api/v1/auth/register` using an `AsyncClient` instance, providing a JSON payload that contains a username and a deliberately weak password (e.g., `"123"`). The current implementation does not enforce password strength rules, so the registration is expected to succeed.

        Args:
            self: Test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make requests against the API.

        Asserts:
            The response status code is `201 Created`, indicating that the user was registered successfully despite the weak password. This behavior highlights a potential area for future improvement, such as adding password strength validation.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "weakpassuser", "password": "123"},  # Weak password
        )

        # Current implementation allows any password
        # Could add password strength validation in future
        assert response.status_code == 201

    async def test_register_special_characters(self, async_client: AsyncClient):
        """
        Test registration using a username that contains special characters (such as an email address), verifying that the endpoint accepts it and returns a 201 Created response.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "user@example.com", "password": "password123"},
        )

        assert response.status_code == 201

    async def test_register_unicode_username(self, async_client: AsyncClient):
        """
        Test that registering a new user with a Unicode username succeeds and returns HTTP 201 Created. The request sends a JSON payload containing a non-ASCII `username` and a valid `password`, then asserts the response status code is 201.
        """
        response = await async_client.post(
            "/api/v1/auth/register", json={"username": "用户名", "password": "password123"}
        )

        assert response.status_code == 201


@pytest.mark.integration
class TestGetMe:
    """Test /me endpoint for current user info."""

    async def test_get_me_authenticated(self, async_client: AsyncClient, test_user, auth_headers):
        """
        Test retrieving the authenticated user's information via the `/api/v1/auth/me` endpoint.

        The request is sent with valid authentication headers and expects a successful response containing the current user's details.

        Assertions:
        - The HTTP status code is 200.
        - The JSON payload includes an `id` matching `test_user.user_id`.
        - The `username` field matches `test_user.username`.
        - The `role` field matches `test_user.role`.
        """
        response = await async_client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == test_user.user_id
        assert data["username"] == test_user.username
        assert data["role"] == test_user.role

    async def test_get_me_unauthenticated(self, async_client: AsyncClient):
        """
        Test retrieving the current user's information without providing an authentication token, expecting the endpoint to respond with HTTP 401 Unauthorized.
        """
        response = await async_client.get("/api/v1/auth/me")

        assert response.status_code == 401

    async def test_get_me_invalid_token(self, async_client: AsyncClient):
        """
        Test that requesting the current user endpoint with an invalid JWT token results in an HTTP 401 Unauthorized response. The request includes an `Authorization` header containing a malformed or non-existent bearer token, and the assertion verifies that the API correctly rejects the request.
        """
        response = await async_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401

    async def test_get_me_expired_token(self, async_client: AsyncClient, test_user):
        """
        Test that accessing the current user endpoint with an expired JWT returns a 401 Unauthorized response and includes an error message indicating the token has expired. The test creates an access token with a negative expiration delta, sends a GET request to `/api/v1/auth/me` using the token in the `Authorization` header, and asserts that the status code is 401 and the response detail mentions expiration.
        """
        from datetime import timedelta
        from app.auth import create_access_token

        # Create expired token
        expired_token = create_access_token(
            user_id=test_user.user_id,
            username=test_user.username,
            role=test_user.role,
            expires_delta=timedelta(seconds=-1),
        )

        response = await async_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401
        data = response.json()
        assert "expired" in data["detail"].lower()

    async def test_get_me_admin_user(self, async_client: AsyncClient, admin_user, admin_headers):
        """
        Test that an authenticated admin user can retrieve their own profile information via the `/api/v1/auth/me` endpoint.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            admin_user: Fixture providing a pre-created admin user object (used implicitly for authentication).
            admin_headers: Dictionary containing authentication headers (e.g., JWT token) for the admin user.

        The test sends a GET request to `/api/v1/auth/me` with the admin's authorization headers, asserts that the response status code is 200 (OK), parses the JSON payload, and verifies that the returned `role` field equals `1`, indicating an admin role.
        """
        response = await async_client.get("/api/v1/auth/me", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["role"] == 1  # Admin role


@pytest.mark.integration
class TestAuthenticationFlow:
    """Test complete authentication workflows."""

    async def test_register_then_login(self, async_client: AsyncClient):
        """
        Test end-to-end registration and login flow.

        The test registers a new user via `/api/v1/auth/register` and asserts that
        the response returns status 201 and contains an access token. It then logs in
        with the same credentials using `/api/v1/auth/login`, checks for status 200,
        and retrieves the second access token. Finally it accesses the protected
        `/api/v1/auth/me` endpoint with the login token to verify that the returned
        username matches the newly registered user.

        No return value; failures are reported via assertions.
        """
        # Register
        register_response = await async_client.post(
            "/api/v1/auth/register", json={"username": "flowuser", "password": "flowpass123"}
        )

        assert register_response.status_code == 201
        register_data = register_response.json()
        register_token = register_data["access_token"]

        # Login with same credentials
        login_response = await async_client.post(
            "/api/v1/auth/login", json={"username": "flowuser", "password": "flowpass123"}
        )

        assert login_response.status_code == 200
        login_data = login_response.json()
        login_token = login_data["access_token"]

        # Both tokens should be valid (may be identical if created in same second)
        # Both tokens should work for /me
        me_response = await async_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {login_token}"}
        )

        assert me_response.status_code == 200
        assert me_response.json()["username"] == "flowuser"

    async def test_token_reuse(self, async_client: AsyncClient, test_user, auth_headers):
        """
        Test that an authentication token remains valid across multiple uses.

        The test performs three consecutive `GET` requests to the `/api/v1/auth/me` endpoint using the same
        `auth_headers` (which contain the token). For each request it asserts:

        * The response status code is `200`.
        * The returned JSON payload includes a `username` field equal to `"testuser"`.

        This verifies that tokens are not single-use and can be reused for subsequent authenticated calls.
        """
        # Make multiple requests with same token
        for _ in range(3):
            response = await async_client.get("/api/v1/auth/me", headers=auth_headers)
            assert response.status_code == 200
            assert response.json()["username"] == "testuser"
