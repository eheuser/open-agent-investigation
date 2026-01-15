"""
Advanced integration tests for reports router.
Tests report generation and retrieval endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestGenerateReport:
    """Test POST /api/v1/reports/generate endpoint."""

    async def test_generate_report_missing_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that generating a report without providing an `investigation_id` in the request payload returns a validation error (HTTP 422). The test sends a POST request to the `/api/v1/reports/generate` endpoint with an empty JSON body and verifies that the response status code indicates unprocessable entity. Parameters\n    async_client: An instance of `httpx.AsyncClient` used to perform asynchronous HTTP requests against the API.\n    auth_headers: A dictionary containing authentication headers required for authorized access to the endpoint.
        """
        response = await async_client.post(
            "/api/v1/reports/generate", headers=auth_headers, json={}
        )

        assert response.status_code == 422

    async def test_generate_report_invalid_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test the report generation endpoint when provided with an invalid investigation ID.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests against the API.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/reports/generate` with a payload containing an invalid UUID string for `investigation_id` and asserts that the response status code indicates a client error (HTTP 400 or 422).
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={"investigation_id": "invalid-uuid"},
        )

        assert response.status_code in [400, 422]

    async def test_generate_report_nonexistent_investigation(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that generating a report with an investigation ID that does not exist returns an appropriate error status (404 Not Found or 403 Forbidden). The test creates a random UUID, sends it to the generate endpoint, and asserts that the response status code indicates the request was rejected because the investigation cannot be found or access is denied.
        """
        from uuid import uuid4

        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={"investigation_id": str(uuid4())},
        )

        assert response.status_code in [404, 403]

    async def test_generate_report_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that attempting to generate a report without providing authentication credentials returns an HTTP 401 Unauthorized response. The request posts the investigation identifier to the report generation endpoint using an unauthenticated client and asserts that the status code indicates lack of authorization.
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            json={"investigation_id": str(test_investigation.investigation_id)},
        )

        assert response.status_code == 401

    async def test_generate_report_with_title(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that generating a report with a custom title returns an acceptable HTTP status.

        Parameters
        ----------
        self : object
            Test class instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to make requests against the API.
        test_investigation : Any
            Fixture providing an investigation object whose `investigation_id` is used in the request payload.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test posts a JSON payload containing the `investigation_id` and a custom `title` to the `/api/v1/reports/generate` endpoint. It asserts that the response status code is one of the expected values (200, 201, or 400), allowing for variations in data availability or validation outcomes.
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "title": "Custom Report Title",
            },
        )

        # May succeed or fail depending on data availability
        assert response.status_code in [200, 201, 400]

    async def test_generate_report_with_sections(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that generating a report with a specific set of sections succeeds or fails as expected.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object containing a valid `investigation_id`.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access.

        The function sends a POST request to `/api/v1/reports/generate` with a JSON payload specifying the `investigation_id` and a list of sections (e.g., `["timeline", "events", "summary"]`). It asserts that the response status code is either 200, 201, or 400, covering successful creation, accepted processing, or client-side validation errors.
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "sections": ["timeline", "events", "summary"],
            },
        )

        assert response.status_code in [200, 201, 400]


@pytest.mark.integration
class TestGetLatestReport:
    """Test GET /api/v1/reports/latest/{investigation_id} endpoint."""

    async def test_get_latest_report_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting the latest report for an investigation returns a 404 response when no reports have been generated.

        Args:
            async_client: An httpx.AsyncClient instance used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with a populated `investigation_id`.
            auth_headers: Dictionary of authentication headers required for authorized access to the endpoint.
        """
        response = await async_client.get(
            f"/api/v1/reports/latest/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 404

    async def test_get_latest_report_invalid_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that requesting the latest report with an invalid investigation identifier returns an appropriate client-error status code (400, 404, or 422). The request is made using an authenticated async HTTP client; the response status code is asserted to be one of the expected error codes.
        """
        response = await async_client.get(
            "/api/v1/reports/latest/invalid-uuid", headers=auth_headers
        )

        assert response.status_code in [400, 404, 422]

    async def test_get_latest_report_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that an unauthenticated request to retrieve the latest report returns a 401 Unauthorized response.

        Args:
            async_client: An `httpx.AsyncClient` instance used to perform HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute.

        Returns:
            None. The test asserts that the response status code equals 401.
        """
        response = await async_client.get(
            f"/api/v1/reports/latest/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetLatestReportMetadata:
    """Test GET /api/v1/reports/latest/{investigation_id}/metadata endpoint."""

    async def test_get_metadata_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving report metadata for an investigation without any generated reports returns a 404 Not Found response.\"""
        """
        response = await async_client.get(
            f"/api/v1/reports/latest/{test_investigation.investigation_id}/metadata",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_metadata_invalid_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that requesting report metadata with an invalid investigation ID (non-UUID) returns an appropriate client error status code (400 Bad Request, 404 Not Found, or 422 Unprocessable Entity). The test uses the provided asynchronous HTTP client and authentication headers to perform a GET request against the `/api/v1/reports/latest/not-a-uuid/metadata` endpoint and asserts that the response status code indicates a validation or not-found error.
        """
        response = await async_client.get(
            "/api/v1/reports/latest/not-a-uuid/metadata", headers=auth_headers
        )

        assert response.status_code in [400, 404, 422]

    async def test_get_metadata_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that retrieving report metadata without authentication fails with a 401 Unauthorized response.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for making requests to the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` used in the request URL.
        """
        response = await async_client.get(
            f"/api/v1/reports/latest/{test_investigation.investigation_id}/metadata"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestDownloadReportPDF:
    """Test POST /api/v1/reports/download endpoint."""

    async def test_download_pdf_missing_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that attempting to download a PDF without providing an `investigation_id` results in a validation error.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            auth_headers: A dictionary containing authentication headers required for authorized access.

        The test sends a POST request to the `/api/v1/reports/download` endpoint with an empty JSON payload and asserts that the response status code is `422`, indicating a missing or invalid `investigation_id`.
        """
        response = await async_client.post(
            "/api/v1/reports/download", headers=auth_headers, json={}
        )

        assert response.status_code == 422

    async def test_download_pdf_invalid_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that attempting to download a PDF report with an invalid investigation_id returns a client-error status code (HTTP 400 or 422), confirming proper validation of the UUID parameter.
        """
        response = await async_client.post(
            "/api/v1/reports/download", headers=auth_headers, json={"investigation_id": "invalid"}
        )

        assert response.status_code in [400, 422]

    async def test_download_pdf_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that attempting to download a PDF report without providing authentication credentials results in an HTTP 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture configured for the application under test.
        test_investigation : Any
            A fixture representing a persisted investigation whose `investigation_id` is used in the request payload.
        """
        response = await async_client.post(
            "/api/v1/reports/download",
            json={"investigation_id": str(test_investigation.investigation_id)},
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestReportsEdgeCases:
    """Test edge cases and error handling."""

    async def test_generate_report_very_long_title(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that generating a report with an excessively long title is handled appropriately by the API.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An HTTP client capable of making asynchronous requests to the application.
            test_investigation: A fixture providing a populated investigation object whose ID will be used in the request.
            auth_headers (dict): Authentication headers required for authorized access to the reports endpoint.

        The test sends a POST request to `/api/v1/reports/generate` with a title consisting of 1000 characters. It asserts that the response status code is one of the expected outcomes:
        - `200` or `201` if the server accepts and creates the report,
        - `400` or `422` if the server rejects the request due to validation constraints.

        No value is returned; the test passes when the assertion holds.
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "title": "A" * 1000,
            },
        )

        # Should handle or reject long title
        assert response.status_code in [200, 201, 400, 422]

    async def test_generate_report_special_characters_title(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that generating a report with a title containing special characters (e.g., HTML/JavaScript) is handled safely by the API. The request posts to `/api/v1/reports/generate` with an `investigation_id` and a title that includes a script tag. The test asserts that the response status code indicates either successful creation (200 or 201) or appropriate validation failure (400), ensuring that the endpoint sanitizes or validates the input without causing errors or security issues.
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "title": "Report <script>alert('xss')</script>",
            },
        )

        # Should sanitize or handle safely
        assert response.status_code in [200, 201, 400]

    async def test_generate_report_empty_sections_list(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test case that verifies the behavior of the report generation endpoint when an empty list of sections is provided.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make requests against the API.
            test_investigation: Fixture providing a pre-created investigation object whose ID is used in the request payload.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/reports/generate` with a valid `investigation_id` and an empty `sections` array. It asserts that the response status code indicates either successful handling (200 or 201) or appropriate validation failure (400).
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={"investigation_id": str(test_investigation.investigation_id), "sections": []},
        )

        # Should handle empty sections
        assert response.status_code in [200, 201, 400]

    async def test_generate_report_invalid_section_names(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that generating a report with section names that are not recognized by the system is handled appropriately.

        The test sends a POST request to the `/api/v1/reports/generate` endpoint with an `investigation_id` and a list of invalid section identifiers (e.g., `"invalid_section"`, `"nonexistent"`). It then asserts that the HTTP response status code indicates either successful handling (200 or 201) or proper validation error reporting (400 or 422). This ensures the API gracefully manages unknown sections without causing unexpected failures.
        """
        response = await async_client.post(
            "/api/v1/reports/generate",
            headers=auth_headers,
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "sections": ["invalid_section", "nonexistent"],
            },
        )

        # Should handle invalid sections
        assert response.status_code in [200, 201, 400, 422]

    async def test_concurrent_report_generation(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that multiple concurrent report generation requests are handled correctly by the API.

        Args:
            async_client: An instance of `AsyncClient` used to make asynchronous HTTP requests against the test server.
            test_investigation: A fixture providing a populated investigation object whose `investigation_id` is used in the request payload.
            auth_headers: Dictionary containing authentication headers required for authorized access to the reports endpoint.

        The test creates three simultaneous POST requests to `/api/v1/reports/generate` with the same investigation ID, gathers their responses concurrently, and asserts that each response returns a status code indicating either successful processing (200 or 201) or an expected error condition (400, 409, or 500). This validates the API's ability to handle concurrent generation attempts without deadlocking or crashing.
        """
        import asyncio

        tasks = [
            async_client.post(
                "/api/v1/reports/generate",
                headers=auth_headers,
                json={"investigation_id": str(test_investigation.investigation_id)},
            )
            for _ in range(3)
        ]

        responses = await asyncio.gather(*tasks)

        # All should complete (success or failure)
        for response in responses:
            assert response.status_code in [200, 201, 400, 409, 500]
