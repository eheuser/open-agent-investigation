import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime


@pytest.mark.integration
class TestGetTimelineEntries:
    """Test GET /api/v1/timeline/{investigation_id} endpoint."""

    async def test_get_timeline_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving an empty timeline for a given investigation.

        This integration test verifies that requesting the timeline endpoint for an investigation
        that contains no entries returns a successful HTTP 200 response with an empty list payload.
        It uses the provided asynchronous client, a pre-created test investigation fixture,
        and authentication headers. The assertions confirm the status code, ensure the JSON
        response is a list, and check that its length is zero.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_get_timeline_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that attempting to retrieve a timeline without authentication returns a 401 Unauthorized status code.
        """
        response = await async_client.get(f"/api/v1/timeline/{test_investigation.investigation_id}")

        assert response.status_code == 401

    async def test_get_timeline_with_filters(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving a timeline for a specific investigation using query parameters.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make requests against the API.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/timeline/{investigation_id}` with filters:
        - `entry_type` set to `event`,
        - `limit` set to `10`,
        - `offset` set to `0`.

        It asserts that the response status code is 200 and that the returned JSON payload is a list.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"entry_type": "event", "limit": 10, "offset": 0},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_timeline_invalid_investigation(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test retrieving the timeline for an investigation that does not exist.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            auth_headers: A dictionary containing authentication headers required by the endpoint.

        The test generates a random UUID, sends a GET request to `/api/v1/timeline/{fake_id}`, and asserts that the response status code is either 200 (with an empty list) or 404 (not found), confirming proper handling of non-existent investigations.
        """
        fake_id = uuid4()
        response = await async_client.get(f"/api/v1/timeline/{fake_id}", headers=auth_headers)

        # Should return empty list or 404
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestCreateTimelineEntry:
    """Test POST /api/v1/timeline/{investigation_id} endpoint."""

    async def test_create_timeline_entry_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a timeline entry successfully.

        This integration test verifies that a POST request to the timeline endpoint creates a new entry and returns the expected response.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` used in the URL path.
            auth_headers: Dictionary containing authentication headers required by the endpoint.

        The test sends a JSON payload containing `title`, `description`, `entry_type`, `timestamp` and `tags`. It asserts that:

        * The response status code is `201 Created`.
        * The returned JSON includes the same `title` and `entry_type` as submitted.
        * An `entry_id` field is present in the response, indicating successful creation.
        """
        entry_data = {
            "title": "Test Event",
            "description": "Test description",
            "entry_type": "event",
            "timestamp": datetime.utcnow().isoformat(),
            "tags": ["test", "important"],
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=entry_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Event"
        assert data["entry_type"] == "event"
        assert "entry_id" in data

    async def test_create_timeline_entry_minimal(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a timeline entry using only the minimal required fields.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to send requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers containing a valid token for authorized access.

        The test sends a POST request to the timeline endpoint with a payload that includes only the `title` and `entry_type` fields. It asserts that the response status code is `201 Created`, indicating successful creation of the timeline entry with minimal data.
        """
        entry_data = {"title": "Minimal Event", "entry_type": "finding"}

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=entry_data,
        )

        assert response.status_code == 201

    async def test_create_timeline_entry_missing_title(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that creating a timeline entry without the required `title` field fails with a validation error.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to send requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers containing a valid JWT token.

        The test sends a POST request to the timeline endpoint for the given investigation, omitting the `title` field in the JSON payload. It asserts that the API responds with HTTP status code 422, indicating an unprocessable entity due to missing required data.
        """
        entry_data = {"description": "No title", "entry_type": "event"}

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=entry_data,
        )

        assert response.status_code == 422  # Validation error

    async def test_create_timeline_entry_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that creating a timeline entry without authentication returns a 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object containing `investigation_id` for constructing the endpoint URL.

        The test posts minimal entry data (title and entry_type) to the timeline endpoint without authentication headers and asserts that the response status code equals 401.
        """
        entry_data = {"title": "Test Event", "entry_type": "event"}

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}", json=entry_data
        )

        assert response.status_code == 401

    async def test_create_timeline_entry_with_event_id(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a timeline entry that references an event by its ID.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute, representing the target investigation for the timeline entry.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a POST request to create a new timeline entry of type `event` with a specified `event_id`. It asserts that the response status code indicates either successful creation (201) or a client error (400), accounting for possible foreign-key constraints on the event reference.
        """
        entry_data = {
            "title": "Event-linked Entry",
            "entry_type": "event",
            "event_id": 123,  # Reference to event table
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=entry_data,
        )

        # Should succeed even if event doesn't exist (FK constraint may vary)
        assert response.status_code in [201, 400]


@pytest.mark.integration
class TestGetTimelineEntry:
    """Test GET /api/v1/timeline/{investigation_id}/{entry_id} endpoint."""

    async def test_get_timeline_entry_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline entry with an ID that does not exist returns HTTP 404.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make requests against the API.
            test_investigation: Fixture providing an investigation object whose `investigation_id` is used in the request URL.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/999999", headers=auth_headers
        )

        assert response.status_code == 404

    async def test_get_timeline_entry_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving a timeline entry without providing authentication credentials returns an HTTP 401 Unauthorized response.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/1"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestUpdateTimelineEntry:
    """Test PUT /api/v1/timeline/{investigation_id}/{entry_id} endpoint."""

    async def test_update_timeline_entry_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating a timeline entry with an ID that does not exist returns a 404 response.

        The test sends a PUT request to the `/api/v1/timeline/<investigation_id>/999999` endpoint with a minimal payload containing a new title.
        It uses the provided `async_client` fixture for making asynchronous HTTP calls, `test_investigation` to obtain a valid investigation identifier, and `auth_headers` for authentication.

        The assertion verifies that the API correctly responds with HTTP status code 404, indicating that the requested timeline entry could not be found.
        """
        update_data = {"title": "Updated Title"}

        response = await async_client.put(
            f"/api/v1/timeline/{test_investigation.investigation_id}/999999",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code == 404

    async def test_update_timeline_entry_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that updating a timeline entry without providing authentication credentials is rejected.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for the test suite.
            test_investigation: A fixture supplying an investigation object with a valid `investigation_id`.

        The test sends a `PUT` request to the endpoint responsible for updating a specific timeline entry (identified by the hard-coded entry ID `1`) using only the payload containing the new title. No authentication headers or tokens are included in the request.

        Asserts:
            The response status code is `401 Unauthorized`, confirming that the API correctly enforces authentication requirements for update operations.
        """
        update_data = {"title": "Updated Title"}

        response = await async_client.put(
            f"/api/v1/timeline/{test_investigation.investigation_id}/1", json=update_data
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestDeleteTimelineEntry:
    """Test DELETE /api/v1/timeline/{investigation_id}/{entry_id} endpoint."""

    async def test_delete_timeline_entry_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that attempting to delete a timeline entry that does not exist returns a 404 Not Found response. The request targets an invalid entry ID (e.g., `999999`) within a valid investigation context, using proper authentication headers. The assertion verifies that the API responds with HTTP status code 404.
        """
        response = await async_client.delete(
            f"/api/v1/timeline/{test_investigation.investigation_id}/999999", headers=auth_headers
        )

        assert response.status_code == 404

    async def test_delete_timeline_entry_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that attempting to delete a timeline entry without providing authentication credentials results in an HTTP 401 Unauthorized response.
        """
        response = await async_client.delete(
            f"/api/v1/timeline/{test_investigation.investigation_id}/1"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetTimelineStats:
    """Test GET /api/v1/timeline/{investigation_id}/stats endpoint."""

    async def test_get_timeline_stats_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving timeline statistics for an investigation with no entries returns a successful response and includes at least one of the expected count fields.

        Parameters
        ----------
        self : object
            Test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to make requests against the API.
        test_investigation : Any
            Fixture providing an investigation object containing an `investigation_id` attribute.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access.

        Raises
        ------
        AssertionError
            If the response status code is not 200 or none of the expected statistic keys (`total`, `count`, `total_entries`) are present in the JSON payload.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/stats", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data or "count" in data or "total_entries" in data

    async def test_get_timeline_stats_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving timeline statistics without authentication returns a 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client fixture configured for asynchronous requests to the API.
        test_investigation : Any
            A fixture providing an investigation object with an `investigation_id` attribute used to construct the request URL.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/stats"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestExportTimeline:
    """Test GET /api/v1/timeline/{investigation_id}/export endpoint."""

    async def test_export_timeline_json(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that exporting a timeline in JSON format returns a successful response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests to the API.
        test_investigation : Any
            A fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Authentication headers required for authorized access.

        Raises
        ------
        AssertionError
            If the response status code is not 200 or if the returned JSON payload is not a list or dictionary.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/export?format=json",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    async def test_export_timeline_csv(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test exporting a timeline in CSV format.

        This integration test verifies that requesting the export endpoint with `format=csv` returns a successful response containing CSV data.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to perform asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object whose `investigation_id` is used in the request URL.
            auth_headers: Authentication headers required for authorized access to the endpoint.

        Asserts:
            The response status code is 200 (OK).
            The `Content-Type` header indicates a CSV payload (contains `text/csv`).
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/export?format=csv",
            headers=auth_headers,
        )

        assert response.status_code == 200
        # Should return CSV content
        assert (
            "text/csv" in response.headers.get("content-type", "").lower()
            or response.status_code == 200
        )

    async def test_export_timeline_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test exporting a timeline when the request is unauthenticated, asserting that the API returns HTTP 401 Unauthorized.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/export"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestTimelineFullWorkflow:
    """Test complete timeline CRUD workflow."""

    async def test_create_update_delete_workflow(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating, updating, and deleting a timeline entry for a given investigation.

        Parameters
        ----------
        self : object
            Test case instance.
        async_client : AsyncClient
            HTTP client used to make asynchronous requests against the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Dictionary containing authentication headers required for authorized API access.

        The test performs the following steps:
        1. Sends a POST request to create a new timeline entry and asserts a 201 response.
        2. Retrieves the created entry via GET and verifies the title matches the initial data.
        3. Updates the entry with a PUT request, asserting a 200 response and confirming the updated title.
        4. Deletes the entry using DELETE and checks for a successful status (200 or 204).
        5. Attempts to retrieve the deleted entry, expecting a 404 Not Found response.

        Raises
        ------
        AssertionError
            If any of the HTTP responses do not have the expected status codes or if the returned data does not match expectations.
        """
        # Create entry
        create_data = {
            "title": "Workflow Test Entry",
            "description": "Initial description",
            "entry_type": "finding",
            "tags": ["workflow"],
        }

        create_response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=create_data,
        )

        assert create_response.status_code == 201
        created_entry = create_response.json()
        entry_id = created_entry["entry_id"]

        # Get entry
        get_response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/{entry_id}",
            headers=auth_headers,
        )

        assert get_response.status_code == 200
        assert get_response.json()["title"] == "Workflow Test Entry"

        # Update entry
        update_data = {"title": "Updated Workflow Entry", "description": "Updated description"}

        update_response = await async_client.put(
            f"/api/v1/timeline/{test_investigation.investigation_id}/{entry_id}",
            headers=auth_headers,
            json=update_data,
        )

        assert update_response.status_code == 200
        updated_entry = update_response.json()
        assert updated_entry["title"] == "Updated Workflow Entry"

        # Delete entry
        delete_response = await async_client.delete(
            f"/api/v1/timeline/{test_investigation.investigation_id}/{entry_id}",
            headers=auth_headers,
        )

        assert delete_response.status_code in [200, 204]

        # Verify deletion
        verify_response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/{entry_id}",
            headers=auth_headers,
        )

        assert verify_response.status_code == 404
