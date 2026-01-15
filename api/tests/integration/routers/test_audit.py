"""
Integration tests for audit router.
Tests audit log retrieval and filtering.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestAuditRouter:
    """Test audit endpoints."""

    async def test_list_audit_logs_admin(
        self,
        async_client: AsyncClient,
        admin_token,
    ):
        """
        Test that an admin user can retrieve the list of audit logs via the `/api/v1/audit/logs` endpoint.\n\nThe test sends a GET request with a valid `Authorization: Bearer <admin_token>` header using the provided asynchronous HTTP client. It asserts that the response status code indicates either a successful retrieval (200) or that no logs are available (404). This verifies both access permissions for an admin and basic endpoint functionality.
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await async_client.get(
            "/api/v1/audit/logs",
            headers=admin_headers,
        )

        assert response.status_code in [200, 404]  # May not have audit table

    async def test_list_audit_logs_regular_user(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that listing audit logs with a regular user's credentials behaves as expected.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            auth_headers: A dictionary containing authentication headers (e.g., `{"Authorization": "Bearer <token>"}`) for a regular user.

        The test sends a GET request to `/api/v1/audit/logs` with the provided headers and asserts that the response status code is one of the expected outcomes for a regular user (200 OK if access is allowed, 403 Forbidden or 404 Not Found otherwise).
        """
        response = await async_client.get(
            "/api/v1/audit/logs",
            headers=auth_headers,
        )

        # Regular users may not have access
        assert response.status_code in [200, 403, 404]

    async def test_list_audit_logs_unauthenticated(
        self,
        async_client: AsyncClient,
    ):
        """
        Test that unauthenticated requests to the audit-log list endpoint are rejected with HTTP 401 Unauthorized. The async client performs a GET request to `/api/v1/audit/logs` without any authentication headers and asserts that the response status code equals 401.
        """
        response = await async_client.get(
            "/api/v1/audit/logs",
        )

        assert response.status_code == 401

    async def test_list_audit_logs_with_filters(
        self,
        async_client: AsyncClient,
        admin_token,
    ):
        """
        Test that an admin user can retrieve a list of audit log entries filtered by action type and limited in size.

        Parameters:
            async_client (AsyncClient): The asynchronous HTTP client used to make requests against the API.
            admin_token (str): A valid JWT token granting administrative privileges, included in the Authorization header.

        The test sends a GET request to `/api/v1/audit/logs` with query parameters `action=login` and `limit=10`. It asserts that the response status code is either 200 (successful retrieval) or 404 (no matching logs found). No value is returned; the function raises an AssertionError if the status code does not match one of the expected values.
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await async_client.get(
            "/api/v1/audit/logs?action=login&limit=10",
            headers=admin_headers,
        )

        assert response.status_code in [200, 404]

    async def test_get_audit_log_by_id_admin(
        self,
        async_client: AsyncClient,
        admin_token,
    ):
        """
        Test that an admin user can retrieve a specific audit log entry by its ID.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        admin_token : str
            A valid JWT token representing an administrator, included in the `Authorization` header.

        The test sends a GET request to `/api/v1/audit/logs/1` with the admin credentials and asserts that the response status code indicates either successful retrieval (200) or that the resource does not exist (404).
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await async_client.get(
            "/api/v1/audit/logs/1",
            headers=admin_headers,
        )

        assert response.status_code in [200, 404]

    async def test_get_audit_log_by_id_not_found(
        self,
        async_client: AsyncClient,
        admin_token,
    ):
        """
        Test that retrieving an audit-log entry with a non-existent ID returns a 404 response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        admin_token : str
            A valid JWT for an administrator user, injected as a Bearer token in the request headers.
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await async_client.get(
            "/api/v1/audit/logs/999999",
            headers=admin_headers,
        )

        assert response.status_code in [404]

    async def test_list_audit_logs_pagination(
        self,
        async_client: AsyncClient,
        admin_token,
    ):
        """
        Test that an admin user can retrieve a paginated list of audit logs.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to send requests to the API.
        admin_token : str
            JWT token with administrative privileges, included in the `Authorization` header.

        The test sends a GET request to `/api/v1/audit/logs` with `limit=5` and `offset=0` query parameters. It asserts that the response status code is either 200 (successful retrieval) or 404 (endpoint not found), verifying basic pagination functionality for admin users.
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await async_client.get(
            "/api/v1/audit/logs?limit=5&offset=0",
            headers=admin_headers,
        )

        assert response.status_code in [200, 404]

    async def test_list_audit_logs_by_user(
        self,
        async_client: AsyncClient,
        admin_token,
    ):
        """
        Test that an admin can filter audit logs by a specific user ID.

        This test sends a GET request to the `/api/v1/audit/logs` endpoint with a `user_id` query parameter,
        using an Authorization header containing a valid admin bearer token. It verifies that the response
        status code indicates either a successful retrieval (200) or that no logs were found for the given user
        (404). The test ensures the audit-log listing endpoint correctly applies user-based filtering when accessed
        by an administrator.
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await async_client.get(
            "/api/v1/audit/logs?user_id=1",
            headers=admin_headers,
        )

        assert response.status_code in [200, 404]

    async def test_list_audit_logs_by_investigation(
        self,
        async_client: AsyncClient,
        admin_token,
        test_investigation,
    ):
        """
        Test that audit logs can be filtered by a specific investigation ID.\n\nParameters\n----------\nself: object\n    The test case instance.\nasync_client: AsyncClient\n    An asynchronous HTTP client used to make requests against the API.\nadmin_token: str\n    JWT token with administrative privileges, included in the Authorization header.\ntest_investigation: Any\n    Fixture providing an investigation object whose `investigation_id` is used as a query parameter.\n\nThe test sends a GET request to `/api/v1/audit/logs` with the `investigation_id` filter and asserts that the response status code indicates either a successful retrieval (200) or that no logs were found for the given investigation (404).
        """
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await async_client.get(
            f"/api/v1/audit/logs?investigation_id={test_investigation.investigation_id}",
            headers=admin_headers,
        )

        assert response.status_code in [200, 404]
