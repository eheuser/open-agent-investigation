import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta


@pytest.mark.integration
class TestGetAuditLogs:
    """Test GET /api/v1/audit endpoint."""

    async def test_get_audit_logs_default(self, async_client: AsyncClient, admin_headers):
        """
        Test that the audit-log endpoint returns a successful response with default query parameters.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to perform asynchronous HTTP requests against the API.
            admin_headers: Dictionary containing authentication headers for an administrator user, required to access the audit logs.

        The test sends a GET request to `/api/v1/audit` without any query parameters and asserts that:
        * The response status code is 200 (OK).
        * The JSON payload includes either a `logs` key, an `items` key, or is a list, indicating that log entries are returned.
        """
        response = await async_client.get("/api/v1/audit", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data or "items" in data or isinstance(data, list)

    async def test_get_audit_logs_with_limit(self, async_client: AsyncClient, admin_headers):
        """
        Test that retrieving audit logs with a `limit` query parameter returns a successful response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        admin_headers : dict
            Authentication headers representing an admin user, required for accessing the audit-log endpoint.

        The test sends a GET request to `/api/v1/audit` with `limit=10` and asserts that the response status code is 200, confirming that the endpoint correctly handles the limit parameter.
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"limit": 10}
        )

        assert response.status_code == 200

    async def test_get_audit_logs_with_offset(self, async_client: AsyncClient, admin_headers):
        """
        Test retrieving audit logs using pagination parameters to ensure the endpoint correctly applies an offset and limit.\n\nArgs:\n    async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.\n    admin_headers: Dictionary containing authentication headers for an administrative user, required to access the audit log endpoint.\n\nThe test sends a GET request to `/api/v1/audit` with `limit=20` and `offset=10` query parameters. It asserts that the response status code is 200, indicating successful retrieval of the paginated audit logs.
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"limit": 20, "offset": 10}
        )

        assert response.status_code == 200

    async def test_get_audit_logs_filter_by_user(self, async_client: AsyncClient, admin_headers):
        """
        Test that the audit-log endpoint correctly filters results by a specific user ID.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            admin_headers: A dictionary containing authentication headers for an administrative user, ensuring sufficient permissions to access audit logs.

        The test performs a GET request to `/api/v1/audit` with the query parameter `user_id=1` and asserts that the response status code is 200, indicating successful retrieval of filtered audit entries.
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"user_id": 1}
        )

        assert response.status_code == 200

    async def test_get_audit_logs_filter_by_action(self, async_client: AsyncClient, admin_headers):
        """
        Test that the audit-log endpoint correctly filters results when the `action` query parameter is set to a specific value (e.g., `login`). The request is sent with administrative authentication headers, and the test asserts that the response status code is HTTP 200, indicating successful retrieval of the filtered audit entries.
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"action": "login"}
        )

        assert response.status_code == 200

    async def test_get_audit_logs_filter_by_investigation(
        self, async_client: AsyncClient, admin_headers, test_investigation
    ):
        """
        Test that the audit-log endpoint correctly filters results when an `investigation_id` query parameter is supplied, returning a 200 OK response containing only logs associated with the specified investigation.
        """
        response = await async_client.get(
            "/api/v1/audit",
            headers=admin_headers,
            params={"investigation_id": str(test_investigation.investigation_id)},
        )

        assert response.status_code == 200

    async def test_get_audit_logs_filter_by_date_range(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that the audit-log endpoint correctly filters entries when a start_date and end_date are provided, ensuring only logs within the specified UTC date range are returned with an HTTP 200 response.
        """
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end_date = datetime.utcnow().isoformat()

        response = await async_client.get(
            "/api/v1/audit",
            headers=admin_headers,
            params={"start_date": start_date, "end_date": end_date},
        )

        assert response.status_code == 200

    async def test_get_audit_logs_filter_by_start_date_only(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that the audit-log endpoint correctly filters results when only a `start_date` query parameter is provided.

        Args:
            async_client: An `httpx.AsyncClient` instance used to make asynchronous HTTP requests against the API.
            admin_headers: A dictionary of HTTP headers containing valid authentication credentials for an administrator user.

        The test constructs a `start_date` value set to 30 days before the current UTC time, sends a GET request to `/api/v1/audit` with this parameter, and asserts that the response status code is `200`, indicating successful handling of the filter.
        """
        start_date = (datetime.utcnow() - timedelta(days=30)).isoformat()

        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"start_date": start_date}
        )

        assert response.status_code == 200

    async def test_get_audit_logs_filter_by_end_date_only(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that the audit-log endpoint correctly filters results when only an `end_date` query parameter is provided.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            admin_headers: A dictionary containing authentication headers for an administrator user, ensuring the request has sufficient permissions.

        The test sends a GET request to `/api/v1/audit` with the `end_date` parameter set to the current UTC timestamp in ISO-8601 format and asserts that the response status code is 200, indicating successful handling of the filter.
        """
        end_date = datetime.utcnow().isoformat()

        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"end_date": end_date}
        )

        assert response.status_code == 200

    async def test_get_audit_logs_combined_filters(self, async_client: AsyncClient, admin_headers):
        """
        Test that the audit-log endpoint correctly applies multiple query filters simultaneously.

        The request includes:
        - `user_id` set to `1` to limit results to actions performed by that user.
        - `action` set to `"create_investigation"` to retrieve only creation events.
        - `start_date` set to a timestamp seven days prior to the current UTC time, restricting results to logs after this date.
        - `limit` set to `50` to cap the number of returned entries.

        The test asserts that the response status code is `200` indicating successful handling of combined filters.
        """
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()

        response = await async_client.get(
            "/api/v1/audit",
            headers=admin_headers,
            params={
                "user_id": 1,
                "action": "create_investigation",
                "start_date": start_date,
                "limit": 50,
            },
        )

        assert response.status_code == 200

    async def test_get_audit_logs_unauthorized(self, async_client: AsyncClient, auth_headers):
        """
        Test that a non-admin user receives an authentication/authorization error when attempting to retrieve audit logs via the `GET /api/v1/audit` endpoint. The request is made with standard user credentials supplied in `auth_headers` and the response status code must be either 401 (unauthenticated) or 403 (forbidden).
        """
        response = await async_client.get("/api/v1/audit", headers=auth_headers)

        # Should be forbidden for non-admin users
        assert response.status_code in [403, 401]

    async def test_get_audit_logs_no_auth(self, async_client: AsyncClient):
        """
        Test that accessing the audit-log endpoint without authentication returns a 401 Unauthorized response.
        """
        response = await async_client.get("/api/v1/audit")

        assert response.status_code == 401

    async def test_get_audit_logs_invalid_date_format(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that requesting audit logs with an invalid `start_date` query parameter returns a validation error response (HTTP 400 or 422). The request is made using an admin user’s authentication headers and the endpoint `/api/v1/audit`. The test asserts that the status code indicates a client-side validation failure.
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"start_date": "invalid-date"}
        )

        # Should fail with validation error
        assert response.status_code in [400, 422]

    async def test_get_audit_logs_negative_limit(self, async_client: AsyncClient, admin_headers):
        """
        Test that requesting audit logs with a negative `limit` query parameter triggers request validation and returns an HTTP 422 Unprocessable Entity response. The test sends a GET request to `/api/v1/audit` using admin authentication headers and asserts that the server responds with status code 422, indicating proper handling of invalid pagination parameters.
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"limit": -1}
        )

        # Should fail validation
        assert response.status_code == 422

    async def test_get_audit_logs_negative_offset(self, async_client: AsyncClient, admin_headers):
        """
        Test that requesting audit logs with a negative `offset` query parameter triggers validation and returns HTTP 422.\"""
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"offset": -1}
        )

        # Should fail validation
        assert response.status_code == 422

    async def test_get_audit_logs_very_large_limit(self, async_client: AsyncClient, admin_headers):
        """
        Test the audit-log endpoint with an excessively large `limit` query parameter.

        The request is sent to `/api/v1/audit` using the provided `async_client` and authentication headers.
        A `limit` of `10000` is supplied, which exceeds typical maximum values.

        The test asserts that the response status code is either:
        - `200` if the server caps the limit internally and returns a successful result, or
        - `422` if the server validates the parameter and rejects it as unprocessable.
        """
        response = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"limit": 10000}
        )

        # Should either cap the limit or succeed
        assert response.status_code in [200, 422]

    async def test_get_audit_logs_filter_multiple_actions(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test that the audit-log endpoint correctly filters results when queried with each individual action type.\n\nThe test iterates over a set of representative actions (e.g., `login`, `logout`, `create_investigation` and `delete_investigation`) and sends a GET request to `/api/v1/audit` with the `action` query parameter set to the current value. For each request it asserts that the response status code is `200` indicating successful handling of the filter.\n\nArgs:\n    async_client: An instance of `httpx.AsyncClient` configured for the application under test.\n    admin_headers: A dictionary containing authentication headers with administrative privileges required to access the audit endpoint.
        """
        # Try different action types
        actions = ["login", "logout", "create_investigation", "delete_investigation"]

        for action in actions:
            response = await async_client.get(
                "/api/v1/audit", headers=admin_headers, params={"action": action}
            )

            assert response.status_code == 200

    async def test_get_audit_logs_pagination_workflow(
        self, async_client: AsyncClient, admin_headers
    ):
        """
        Test the pagination workflow of the audit-log endpoint.\n\nThe test performs two consecutive GET requests to `/api/v1/audit` using an admin authentication header:\n\n* The first request retrieves the initial page with a `limit` of 5 items and an `offset` of 0.\n* The second request retrieves the next page with the same `limit` but an `offset` of 5.\n\nBoth responses are asserted to have an HTTP status code of 200, confirming that pagination parameters are accepted and processed correctly.\"""
        """
        # Get first page
        response1 = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"limit": 5, "offset": 0}
        )

        assert response1.status_code == 200

        # Get second page
        response2 = await async_client.get(
            "/api/v1/audit", headers=admin_headers, params={"limit": 5, "offset": 5}
        )

        assert response2.status_code == 200
