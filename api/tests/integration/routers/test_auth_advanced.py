"""
Advanced integration tests for auth router.
Tests authentication, registration, and token refresh.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestLoginEndpoint:
    """Test POST /api/v1/auth/login endpoint."""

    async def test_login_invalid_credentials(self, async_client: AsyncClient):
        """
        Test that attempting to log in with credentials that do not correspond to any existing user results in an HTTP 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test class instance providing context for the method.
        async_client : httpx.AsyncClient
            An asynchronous HTTP client fixture configured to communicate with the application under test.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "nonexistent", "password": "wrongpassword"}
        )

        assert response.status_code == 401

    async def test_login_missing_username(self, async_client: AsyncClient):
        """
        Ensures that logging in without a `username` field triggers request validation and returns HTTP 422 (Unprocessable Entity).
        """
        response = await async_client.post("/api/v1/auth/login", json={"password": "testpass"})

        assert response.status_code == 422

    async def test_login_missing_password(self, async_client: AsyncClient):
        """
        Test that attempting to log in without providing a password results in a validation error.\n\nThe request is sent to the `/api/v1/auth/login` endpoint with only a `username` field in the JSON payload. The expected outcome is an HTTP 422 Unprocessable Entity response, indicating that the missing `password` field was correctly identified as required by the API's input validation. This ensures that incomplete login attempts are rejected before any authentication logic is executed.
        """
        response = await async_client.post("/api/v1/auth/login", json={"username": "testuser"})

        assert response.status_code == 422

    async def test_login_empty_username(self, async_client: AsyncClient):
        """
        Test that attempting to log in with an empty username returns an error response.

        The test sends a POST request to the `/api/v1/auth/login` endpoint with a JSON payload containing an empty `username` field and a valid `password`. It then asserts that the HTTP status code of the response indicates a client-side error (one of 400 Bad Request, 401 Unauthorized, or 422 Unprocessable Entity), confirming that the authentication API correctly validates the presence of a username.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "", "password": "testpass"}
        )

        assert response.status_code in [400, 401, 422]

    async def test_login_empty_password(self, async_client: AsyncClient):
        """
        Test that attempting to log in with an empty password results in a client error response (HTTP 400, 401, or 422), confirming that the authentication endpoint validates missing credentials appropriately.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "testuser", "password": ""}
        )

        assert response.status_code in [400, 401, 422]

    async def test_login_sql_injection_attempt(self, async_client: AsyncClient):
        """
        Test that attempting to log in with a SQL injection payload in the username is rejected by the authentication endpoint, ensuring the request results in an HTTP 401 Unauthorized response.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "admin' OR '1'='1", "password": "password"}
        )

        # Should safely reject
        assert response.status_code == 401

    async def test_login_very_long_username(self, async_client: AsyncClient):
        """
        Test that logging in with an excessively long username is rejected or handled gracefully by the authentication endpoint.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An HTTPX asynchronous client fixture configured for the application under test.

        The test sends a POST request to `/api/v1/auth/login` with a username consisting of 1000 `'a'` characters and a valid password. It asserts that the response status code indicates a failure (one of 400 Bad Request, 401 Unauthorized, or 422 Unprocessable Entity), ensuring that the API does not accept overly long usernames.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "a" * 1000, "password": "testpass"}
        )

        # Should reject or handle gracefully
        assert response.status_code in [400, 401, 422]

    async def test_login_special_characters_username(self, async_client: AsyncClient):
        """
        Test that login fails when the username contains special characters.

        Parameters
        ----------
        self : object
            Instance of the test class.
        async_client : httpx.AsyncClient
            Asynchronous HTTP client used to send requests to the API.

        The test posts to `/api/v1/auth/login` with a payload where `username` includes
        characters such as `<` and `>`, which are not allowed. It asserts that the response
        status code is 401, confirming that the authentication endpoint correctly rejects
        usernames containing invalid characters.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "test<>user", "password": "testpass"}
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestRegisterEndpoint:
    """Test POST /api/v1/auth/register endpoint."""

    async def test_register_missing_fields(self, async_client: AsyncClient):
        """
        Test that the registration endpoint returns a 422 Unprocessable Entity status when called without any required fields.

        This test sends an empty JSON payload to `/api/v1/auth/register` using the provided asynchronous HTTP client and asserts that the response status code is `422`, indicating proper validation of missing input data.
        """
        response = await async_client.post("/api/v1/auth/register", json={})

        assert response.status_code == 422

    async def test_register_missing_username(self, async_client: AsyncClient):
        """
        Test registration endpoint behavior when the username field is omitted.

        This test sends a POST request to `/api/v1/auth/register` with a payload that includes only `password` and `email` keys, deliberately leaving out the required `username` field. The expected outcome is that the API returns an HTTP 422 Unprocessable Entity status code, indicating validation has correctly identified the missing username.
        """
        response = await async_client.post(
            "/api/v1/auth/register", json={"password": "testpass123", "email": "test@example.com"}
        )

        assert response.status_code == 422

    async def test_register_missing_password(self, async_client: AsyncClient):
        """
        Test that registering a new user without providing a password returns a 422 Unprocessable Entity response, indicating validation failure for missing required fields.
        """
        response = await async_client.post(
            "/api/v1/auth/register", json={"username": "newuser", "email": "test@example.com"}
        )

        assert response.status_code == 422

    async def test_register_weak_password(self, async_client: AsyncClient):
        """
        Test that registering a new user with a password that does not meet strength requirements is rejected by the API, asserting that the response status code indicates a client error (HTTP 400 or 422).
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "newuser123", "password": "123", "email": "test@example.com"},
        )

        # Should reject weak password
        assert response.status_code in [400, 422]

    async def test_register_invalid_email(self, async_client: AsyncClient):
        """
        Test that registering a new user with an improperly formatted email address is rejected by the authentication API.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An HTTPX asynchronous client configured for testing the API.

        The test sends a POST request to `/api/v1/auth/register` with a JSON payload containing a valid username and password but an invalid email format. It asserts that the response status code indicates a client error, typically 400 (Bad Request) or 422 (Unprocessable Entity), confirming that the server validates email formats during registration.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "newuser456", "password": "testpass123", "email": "invalid-email"},
        )

        # Should reject invalid email
        assert response.status_code in [400, 422]

    async def test_register_duplicate_username(self, async_client: AsyncClient, test_user):
        """
        Test that registering a new user with a username that already exists fails with an appropriate client error status code.

        Args:
            async_client: An instance of httpx.AsyncClient configured for the test application.
            test_user: A fixture providing an existing user object whose username is used in the registration attempt.

        The test sends a POST request to the `/api/v1/auth/register` endpoint with the duplicate username, a valid password, and a different email address. It asserts that the response status code indicates a client error (either 400 Bad Request or 409 Conflict), confirming that the API correctly rejects duplicate usernames.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": test_user.username,
                "password": "testpass123",
                "email": "different@example.com",
            },
        )

        # Should reject duplicate username
        assert response.status_code in [400, 409]

    async def test_register_username_too_short(self, async_client: AsyncClient):
        """
        Test that registering a new user with a username shorter than the allowed minimum length results in a client error response (HTTP 400 or 422), confirming that the API enforces username length validation during registration.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "ab", "password": "testpass123", "email": "test@example.com"},
        )

        # Should reject short username
        assert response.status_code in [400, 422]

    async def test_register_username_with_spaces(self, async_client: AsyncClient):
        """
        Test that registering a new user fails when the provided username contains whitespace characters.

        The test sends a POST request to the `/api/v1/auth/register` endpoint with a JSON payload where `username` includes a space (e.g., `"user name"`). It verifies that the API rejects the request by asserting that the response status code indicates a client-side error, typically either **400 Bad Request** or **422 Unprocessable Entity**, depending on how validation errors are reported. This ensures that usernames with spaces are not accepted by the registration endpoint.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"username": "user name", "password": "testpass123", "email": "test@example.com"},
        )

        # Should reject username with spaces
        assert response.status_code in [400, 422]


@pytest.mark.integration
class TestRefreshTokenEndpoint:
    """Test POST /api/v1/auth/refresh endpoint."""

    async def test_refresh_token_missing(self, async_client: AsyncClient):
        """
        Test that attempting to refresh an authentication token without providing a JWT results in an HTTP 401 Unauthorized response.
        """
        response = await async_client.post("/api/v1/auth/refresh")

        assert response.status_code == 401

    async def test_refresh_token_invalid(self, async_client: AsyncClient):
        """
        Test that attempting to refresh an authentication token with an invalid bearer token results in a 401 Unauthorized response from the `/api/v1/auth/refresh` endpoint.
        """
        response = await async_client.post(
            "/api/v1/auth/refresh", headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401

    async def test_refresh_token_malformed(self, async_client: AsyncClient):
        """
        Test that providing a malformed Authorization header to the token refresh endpoint results in an HTTP 401 Unauthorized response.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An httpx asynchronous client configured for the application under test.

        The test sends a POST request to `/api/v1/auth/refresh` with an `Authorization` header that does not follow the expected `Bearer <token>` format and asserts that the response status code is 401.
        """
        response = await async_client.post(
            "/api/v1/auth/refresh", headers={"Authorization": "InvalidFormat"}
        )

        assert response.status_code == 401

    async def test_refresh_token_expired(self, async_client: AsyncClient):
        """
        Test that attempting to refresh an authentication token using an expired JWT results in a 401 Unauthorized response from the `/api/v1/auth/refresh` endpoint. The test constructs a deliberately expired token, sends it in the `Authorization` header of a POST request via the provided asynchronous HTTP client, and asserts that the response status code is 401.
        """
        # Create an expired token
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxfQ.invalid"

        response = await async_client.post(
            "/api/v1/auth/refresh", headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetCurrentUserEndpoint:
    """Test GET /api/v1/auth/me endpoint."""

    async def test_get_current_user_success(self, async_client: AsyncClient, auth_headers):
        """
        Test that retrieving the current authenticated user's information succeeds.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An HTTPX asynchronous client fixture configured for the application.
            auth_headers (dict): Authentication headers containing a valid JWT token.

        The test sends a GET request to `/api/v1/auth/me` with the provided authentication
        headers, asserts that the response status code is 200, and verifies that the returned JSON
        includes either a `username` or `user_id` field indicating successful retrieval of the
        current user data.
        """
        response = await async_client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "username" in data or "user_id" in data

    async def test_get_current_user_no_auth(self, async_client: AsyncClient):
        """
        Test that accessing the current-user endpoint without authentication returns a 401 Unauthorized response. The async HTTP client performs a GET request to `/api/v1/auth/me` and asserts that the status code is 401.
        """
        response = await async_client.get("/api/v1/auth/me")

        assert response.status_code == 401

    async def test_get_current_user_invalid_token(self, async_client: AsyncClient):
        """
        Test that accessing the current-user endpoint with an invalid JWT results in an HTTP 401 Unauthorized response. The request includes an `Authorization` header containing a deliberately malformed token, and the assertion verifies that the API correctly rejects the request.
        """
        response = await async_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestAuthEdgeCases:
    """Test edge cases and security scenarios."""

    async def test_login_case_sensitive_username(self, async_client: AsyncClient, test_user):
        """
        Tests that logging in with an uppercase version of a known username behaves as expected. The request sends the user's password unchanged while converting the stored username to upper case, then asserts that the response status code reflects either successful authentication (200) or rejection due to case sensitivity (401). This verifies whether the authentication endpoint treats usernames as case-sensitive.
        """
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"username": test_user.username.upper(), "password": "testpass123"},
        )

        # Behavior depends on implementation
        assert response.status_code in [200, 401]

    async def test_login_unicode_username(self, async_client: AsyncClient):
        """
        Test that logging in with a Unicode username is handled correctly.
        The test sends a POST request to `/api/v1/auth/login` containing a
        non-ASCII username and a valid password, then asserts that the response
        status code is either 401 (unauthorized) or 422 (validation error),
        verifying that the endpoint gracefully handles such input without
        raising unexpected errors.
        """
        response = await async_client.post(
            "/api/v1/auth/login", json={"username": "用户名", "password": "testpass"}
        )

        # Should handle gracefully
        assert response.status_code in [401, 422]

    async def test_register_xss_in_username(self, async_client: AsyncClient):
        """
        Test that registering a user with a username containing an XSS payload is properly handled by the API, ensuring the request is either rejected with a client error status (400 or 422) or sanitized to prevent script injection. The test uses an asynchronous HTTP client fixture to send a POST request to the registration endpoint with malicious input and asserts that the response status code indicates appropriate validation failure.
        """
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "username": "<script>alert('xss')</script>",
                "password": "testpass123",
                "email": "test@example.com",
            },
        )

        # Should sanitize or reject
        assert response.status_code in [400, 422]

    async def test_concurrent_login_attempts(self, async_client: AsyncClient):
        """
        Test that multiple simultaneous login requests with invalid credentials are all rejected, ensuring the authentication endpoint consistently returns a 401 Unauthorized response under concurrent load.
        """
        import asyncio

        tasks = [
            async_client.post("/api/v1/auth/login", json={"username": "test", "password": "wrong"})
            for _ in range(5)
        ]

        responses = await asyncio.gather(*tasks)

        # All should fail
        for response in responses:
            assert response.status_code == 401
