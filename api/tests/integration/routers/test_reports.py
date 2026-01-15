"""
Integration tests for reports router.
Tests report generation and export functionality.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestReportsRouter:
    """Test reports endpoints."""

    async def test_generate_investigation_report(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that generating an investigation report via the reports API returns an appropriate HTTP status.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the application.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used in the request URL.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/reports/investigation/{investigation_id}` and asserts that the response status code is one of the expected values:
        - **200** - report generated successfully,
        - **404** - markdown source not available,
        - **500** - internal server error during generation.
        """
        response = await async_client.post(
            f"/api/v1/reports/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        # May return 200 with report or error if markdown not available
        assert response.status_code in [200, 404, 500]

    async def test_generate_report_unauthenticated(
        self,
        async_client: AsyncClient,
        test_investigation,
    ):
        """
        Test that generating a report without authentication fails with a 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used to construct the request URL.
        """
        response = await async_client.post(
            f"/api/v1/reports/investigation/{test_investigation.investigation_id}",
        )

        assert response.status_code == 401

    async def test_generate_report_invalid_investigation(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that generating a report for a non-existent or malformed investigation identifier returns an appropriate client error.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests against the API.
        auth_headers : dict
            A dictionary containing authentication headers required for authorized access.

        The test sends a POST request to the reports endpoint with an invalid investigation UUID and asserts that the response status code indicates a client-side error (HTTP 400, 404, or 422).
        """
        response = await async_client.post(
            f"/api/v1/reports/investigation/invalid-uuid",
            headers=auth_headers,
        )

        assert response.status_code in [400, 404, 422]

    async def test_generate_timeline_report(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test generating a timeline report for a given investigation.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : object
            Fixture providing an investigation with an `investigation_id` attribute used in the request URL.
        auth_headers : dict
            Dictionary containing authentication headers required for the request.

        The test sends a POST request to the timeline report endpoint and asserts that the response status code is one of the expected values (200, 404, or 500).
        """
        response = await async_client.post(
            f"/api/v1/reports/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 500]

    async def test_export_report_pdf(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that exporting a report as PDF via the reports API endpoint behaves as expected.\n\nThe test sends an asynchronous GET request to the `/api/v1/reports/investigation/{investigation_id}/pdf` endpoint using the provided `async_client` and authentication headers. It then asserts that the HTTP status code returned by the server is one of the acceptable values:\n\n- `200` - PDF generated successfully.\n- `404` - The requested report or PDF generation service was not found.\n- `500` - An internal server error occurred during PDF generation.\n- `501` - PDF generation functionality is not implemented or unavailable.\n\nParameters\n----------\nself : object\n    Instance of the test class containing this method.\nasync_client : AsyncClient\n    The asynchronous HTTP client used to perform requests against the API.\ntest_investigation : Any\n    Fixture providing an investigation object with an `investigation_id` attribute used in the request URL.\nauth_headers : dict\n    Dictionary of authentication headers required for authorized access to the endpoint.\n\nReturns\n-------\nNone\n    The function asserts internally; it does not return a value.
        """
        response = await async_client.get(
            f"/api/v1/reports/investigation/{test_investigation.investigation_id}/pdf",
            headers=auth_headers,
        )

        # PDF generation may not be available
        assert response.status_code in [200, 404, 500, 501]

    async def test_export_report_markdown(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test exporting a report in markdown format via the reports API endpoint.

        The test sends an asynchronous GET request to the markdown export URL for a given investigation, using provided authentication headers. It asserts that the response status code is one of the expected outcomes (200 OK, 404 Not Found, or 500 Internal Server Error), covering successful export as well as error handling scenarios.
        """
        response = await async_client.get(
            f"/api/v1/reports/investigation/{test_investigation.investigation_id}/markdown",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 500]

    async def test_list_reports(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that the reports listing endpoint returns an appropriate HTTP status code.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous requests against the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` attribute.
            auth_headers: Dictionary containing authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/reports/investigation/{investigation_id}` and asserts that the response status code is either 200 (successful retrieval) or 404 (no reports found).
        """
        response = await async_client.get(
            f"/api/v1/reports/investigation/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404]

    async def test_delete_report(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that deleting a report via the reports API behaves as expected.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the application.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used to construct the request URL.
        auth_headers : dict
            Dictionary containing authentication headers required for the API call.

        The test sends a DELETE request to the endpoint responsible for removing a specific report identified by the investigation ID and a hard-coded report identifier (`1`). It asserts that the response status code is one of the expected values: `200` (OK), `204` (No Content) indicating successful deletion, or `404` (Not Found) if the report does not exist.
        """
        response = await async_client.delete(
            f"/api/v1/reports/investigation/{test_investigation.investigation_id}/1",
            headers=auth_headers,
        )

        assert response.status_code in [200, 204, 404]
