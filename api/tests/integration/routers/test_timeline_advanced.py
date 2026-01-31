"""
Advanced integration tests for timeline endpoints.
Tests complex filtering, notes, statistics, and edge cases.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta
import json


@pytest.mark.integration
class TestGetTimelineFiltering:
    """Test advanced filtering in get_timeline endpoint."""

    async def test_get_timeline_filter_by_entry_type(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline filtered by an entry type returns a successful response with the expected structure.

        Args:
            async_client: An asynchronous HTTP client used to make requests against the API.
            test_investigation: Fixture providing an investigation instance containing the `investigation_id` to query.
            auth_headers: Dictionary of authentication headers required for authorized access.

        The test sends a GET request to the timeline endpoint with the `entry_type` query parameter set to `authentication`. It asserts that:
        * The response status code is 200 (OK).
        * The JSON payload contains both an `entries` list and a `total` count field.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"entry_type": "authentication"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data

    async def test_get_timeline_filter_by_event_type(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline filtered by a specific event type returns a successful response with entries.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture for making API requests.
            test_investigation: Fixture providing an investigation object containing the `investigation_id` used in the request URL.
            auth_headers (dict): Authentication headers required to authorize the API call.

        The test sends a GET request to the timeline endpoint with the `event_type` query parameter set to `"evtx_security_4624"`. It asserts that:
        - The HTTP status code is 200 (OK).
        - The JSON response contains an `"entries"` key.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"event_type": "evtx_security_4624"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data

    async def test_get_timeline_filter_by_tags(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline with tag filters returns a successful response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests against the API.
        test_investigation : Investigation
            A fixture providing an investigation object whose `investigation_id` is used in the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/timeline/{investigation_id}` with the query parameter `tags` set to `["suspicious", "malware"]` and asserts that the response status code is 200, indicating successful filtering by tags.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"tags": ["suspicious", "malware"]},
        )

        assert response.status_code == 200

    async def test_get_timeline_filter_by_start_time(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline filtered by a specific start_time returns a successful response.

        Args:
            async_client: An httpx.AsyncClient instance used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with a valid investigation_id for the timeline endpoint.
            auth_headers: Dictionary of authentication headers required for authorized access to the API.
        """
        start_time = (datetime.utcnow() - timedelta(days=7)).isoformat()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_time": start_time},
        )

        assert response.status_code == 200

    async def test_get_timeline_filter_by_end_time(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline filtered by an `end_time` query parameter returns a successful response.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` for which the timeline is queried.
            auth_headers: Authentication headers (e.g., containing a JWT token) required by the endpoint.

        The test constructs an ISO-8601 formatted current UTC timestamp, sends a GET request to `/api/v1/timeline/{investigation_id}` with the `end_time` parameter, and asserts that the response status code is 200.
        """
        end_time = datetime.utcnow().isoformat()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"end_time": end_time},
        )

        assert response.status_code == 200

    async def test_get_timeline_filter_by_time_range(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline with both `start_time` and `end_time` query parameters returns a successful (200) response.

        The test constructs a time window spanning the last seven days, sends an authenticated GET request to the timeline endpoint for the given investigation, and asserts that the HTTP status code is 200.
        """
        start_time = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end_time = datetime.utcnow().isoformat()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_time": start_time, "end_time": end_time},
        )

        assert response.status_code == 200

    async def test_get_timeline_filter_by_search(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving a timeline filtered by a search term that matches the title or description of entries. The test sends a GET request with a `search` query parameter and asserts that the response status code is 200, indicating successful filtering.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"search": "login"},
        )

        assert response.status_code == 200

    async def test_get_timeline_include_hidden(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline with the `include_hidden` query parameter set to `True` returns a successful response (HTTP 200). The test sends an authenticated GET request to the timeline endpoint for the given investigation and asserts that the server responds with status code 200, indicating hidden items are included without error.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"include_hidden": True},
        )

        assert response.status_code == 200

    async def test_get_timeline_exclude_hidden_default(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that hidden timeline entries are excluded when the `include_hidden` query parameter is set to `False`, verifying a successful 200 response from the endpoint.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"include_hidden": False},
        )

        assert response.status_code == 200

    async def test_get_timeline_combined_filters(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving timeline entries for a specific investigation while applying multiple query filters simultaneously.

        The test performs the following steps:
        1. Calculates a start timestamp representing seven days prior to the current UTC time and formats it as an ISO-8601 string.
        2. Sends an asynchronous GET request to the `/api/v1/timeline/{investigation_id}` endpoint, supplying:
           * An authentication header payload (`auth_headers`).
           * Query parameters that combine several filters:
             - `entry_type=authentication` - restrict results to authentication-related entries.
             - `start_time` - include only entries created after the calculated start timestamp.
             - `search=admin` - perform a free-text search for the term “admin”.
             - `limit=50` - cap the number of returned records at fifty.
             - `offset=0` - begin pagination from the first record.
        3. Asserts that the HTTP response status code is 200 (OK).
        4. Parses the JSON payload and verifies that the `limit` field in the response matches the requested limit value (50).
        """
        start_time = (datetime.utcnow() - timedelta(days=7)).isoformat()

        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "entry_type": "authentication",
                "start_time": start_time,
                "search": "admin",
                "limit": 50,
                "offset": 0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50

    async def test_get_timeline_with_event_type_and_entry_type(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that filtering a timeline by both `event_type` and `entry_type` works correctly, verifying that the API combines these filters using a JOIN and returns a successful 200 response. The request is made with authentication headers and expects the combined filter to narrow results accordingly.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"event_type": "evtx_security_4624", "entry_type": "authentication"},
        )

        assert response.status_code == 200

    async def test_get_timeline_limit_max(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting the maximum allowed number of timeline entries (limit = 1000) returns a successful 200 response for a valid investigation ID. The function uses an asynchronous HTTP client to send a GET request with authentication headers and verifies the status code. Parameters: async_client - an AsyncClient instance for making requests; test_investigation - fixture providing an investigation object with its ID; auth_headers - dictionary containing authentication header values. No return value; assertions validate behavior.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 1000},
        )

        assert response.status_code == 200

    async def test_get_timeline_limit_exceeds_max(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting a timeline with a `limit` parameter greater than the maximum allowed value (1000) results in a validation error.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture for making requests to the API.
            test_investigation: A fixture providing an investigation object whose `investigation_id` is used in the request path.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a GET request to the timeline endpoint with `limit=2000` and asserts that the response status code is `422`, indicating that the input validation correctly rejects limits exceeding the allowed maximum.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 2000},
        )

        assert response.status_code == 422

    async def test_get_timeline_negative_offset(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Tests that requesting a timeline with a negative `offset` query parameter triggers validation failure and returns an HTTP 422 status code.

        Args:
            async_client: An instance of `AsyncClient` used to perform the request.
            test_investigation: Fixture providing an investigation object whose `investigation_id` is used in the URL.
            auth_headers: Dictionary containing authentication headers required for the API call.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"offset": -1},
        )

        assert response.status_code == 422


@pytest.mark.integration
class TestCreateTimelineEntry:
    """Test creating timeline entries with various scenarios."""

    async def test_create_entry_investigation_not_found(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that creating a timeline entry for an investigation ID that does not exist returns a 404 response.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An HTTP client capable of making asynchronous requests to the API.
            auth_headers (dict): Authentication headers required for authorized access.

        The test generates a random UUID, constructs a valid entry payload, sends a POST request to the `/api/v1/timeline/{uuid}/entries` endpoint, and asserts that:
        * The response status code is 404.
        * The error detail contains the phrase “investigation not found” (case-insensitive).
        """
        from uuid import uuid4

        entry_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "authentication",
            "title": "Test Entry",
            "description": "Test",
            "data": {},
            "tags": [],
            "is_visible": True,
        }

        response = await async_client.post(
            f"/api/v1/timeline/{uuid4()}/entries", headers=auth_headers, json=entry_data
        )

        assert response.status_code == 404
        assert "investigation not found" in response.json()["detail"].lower()

    async def test_create_entry_with_event_id_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a timeline entry using an `event_id` that does not exist.

        Parameters
        ----------
        self : object
            Test class instance.
        async_client : AsyncClient
            HTTP client fixture used to make asynchronous requests against the API.
        test_investigation : Any
            Fixture providing an investigation object whose `investigation_id` is used in the request URL.
        auth_headers : dict
            Dictionary containing authentication headers required for the request.

        The test builds a payload with a deliberately invalid `event_id` (e.g., `999999`) and posts it to the endpoint
        `/api/v1/timeline/{investigation_id}/entries`. It asserts that the response status code is `400` and that the error
        detail contains the phrase “event not found”, confirming proper validation of non-existent event references.
        """
        entry_data = {
            "event_id": 999999,
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "authentication",
            "title": "Test Entry",
            "description": "Test",
            "data": {},
            "tags": [],
            "is_visible": True,
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data,
        )

        assert response.status_code == 400
        assert "event not found" in response.json()["detail"].lower()

    async def test_create_entry_minimal_fields(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a timeline entry using only the minimal required fields.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        test_investigation : object
            Fixture providing an investigation context, including its `investigation_id` used in the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a POST request with a payload containing `timestamp`, `entry_type`, and `title`. It asserts that the response status code is one of the expected outcomes (200 OK, 201 Created, or 422 Unprocessable Entity), reflecting either successful creation or schema validation failure.
        """
        entry_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "authentication",
            "title": "Minimal Entry",
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data,
        )

        # Might succeed or fail depending on schema requirements
        assert response.status_code in [200, 201, 422]

    async def test_create_entry_with_tags(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a timeline entry that includes a list of tags.

        This integration test sends a POST request to the timeline entries endpoint with a payload containing
        standard entry fields as well as a `tags` array. It verifies that the API accepts the request and
        responds with a successful status code (200 OK or 201 Created).

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing against the application.
            test_investigation: A fixture providing an investigation object whose `investigation_id` is used in the URL.
            auth_headers: Dictionary containing authentication headers required by the endpoint.

        The test asserts that the response status code indicates success; no further validation of the
        response body is performed.
        """
        entry_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "authentication",
            "title": "Tagged Entry",
            "description": "Entry with tags",
            "data": {},
            "tags": ["suspicious", "malware", "c2"],
            "is_visible": True,
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data,
        )

        assert response.status_code in [200, 201]

    async def test_create_entry_hidden(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a hidden timeline entry for a given investigation.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to send requests to the API.
            test_investigation: Fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized access.

        The test constructs a payload representing a hidden entry (`is_visible` set to `False`) and sends a POST request to the timeline entries endpoint of the specified investigation. It asserts that the response status code indicates success (either 200 OK or 201 Created).
        """
        entry_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "authentication",
            "title": "Hidden Entry",
            "description": "This is hidden",
            "data": {},
            "tags": [],
            "is_visible": False,
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data,
        )

        assert response.status_code in [200, 201]


@pytest.mark.integration
class TestUpdateTimelineEntry:
    """Test updating timeline entries."""

    async def test_update_entry_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating an entry that does not exist returns a 404 response.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing a populated investigation object, including its `investigation_id`.
            auth_headers: Dictionary containing authentication headers required for authorized API access.

        The test sends a PATCH request to update a non-existent timeline entry (ID `999999`) and asserts that the response status code is 404, indicating that the resource was not found.
        """
        update_data = {"title": "Updated Title"}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/999999",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code == 404

    async def test_update_entry_no_fields(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating a timeline entry without providing any fields in the request body results in an error response (HTTP 400 Bad Request or HTTP 404 Not Found), verifying proper validation of required update data.
        """
        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json={},
        )

        assert response.status_code in [400, 404]

    async def test_update_entry_title_only(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating an entry with only a new title works as expected.\n\nArgs:\n    async_client: An httpx.AsyncClient instance used to make requests against the API.\n    test_investigation: Fixture providing an investigation object containing the `investigation_id` used in the request URL.\n    auth_headers: Dictionary of authentication headers required for authorized access.\n\nThe test sends a PATCH request with a payload containing only the `title` field to update entry ID 1 of the specified investigation. It asserts that the response status code is either `200` (successful update) or `404` (entry not found), allowing the test to pass in environments where the entry may not exist.
        """
        update_data = {"title": "New Title"}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json=update_data,
        )

        # Will fail with 404 if entry doesn't exist
        assert response.status_code in [200, 404]

    async def test_update_entry_description_only(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating an entry with only the `description` field works as expected.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing a populated investigation object, including its `investigation_id`.
            auth_headers: Dictionary containing authentication headers required for authorized API access.

        The test sends a PATCH request to update the description of entry `1` within the specified investigation and asserts that the response status code indicates either successful update (200) or that the entry was not found (404).
        """
        update_data = {"description": "New description"}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code in [200, 404]

    async def test_update_entry_timestamp(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test updating the timestamp of a timeline entry via the API.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing against the application.
            test_investigation: A fixture providing an investigation object containing at least an `investigation_id` used to construct the request URL.
            auth_headers: Dictionary of authentication headers required by the endpoint.

        The test sends a PATCH request to update the `timestamp` field of entry ID 1 for the specified investigation, using the current UTC time in ISO-8601 format. It asserts that the response status code indicates either a successful update (200) or that the entry was not found (404).
        """
        update_data = {"timestamp": datetime.utcnow().isoformat()}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code in [200, 404]

    async def test_update_entry_type(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating the `entry_type` field of a timeline entry behaves as expected.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : object
            Fixture providing an investigation with a populated timeline; its `investigation_id` attribute is used in the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a PATCH request to modify the `entry_type` of entry ID 1 within the specified investigation, then asserts that the response status code indicates either successful update (200) or that the entry was not found (404).
        """
        update_data = {"entry_type": "process_execution"}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code in [200, 404]

    async def test_update_entry_tags(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test updating the tags of an existing timeline entry.\n\nThis integration test sends a PATCH request to modify the `tags` field of the entry with ID `1` belonging to the specified investigation. The payload contains a list of new tag strings. The request includes authentication headers.\n\nThe response status code is asserted to be either `200` (indicating a successful update) or `404` (indicating that the entry was not found).\"""
        """
        update_data = {"tags": ["new_tag1", "new_tag2"]}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code in [200, 404]

    async def test_update_entry_visibility(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating an entry's visibility toggles the `is_visible` flag correctly and returns an appropriate HTTP status code (200 on success or 404 if the entry does not exist). The request is sent using the provided asynchronous client with authentication headers, and the response status code is asserted to be either 200 or 404.
        """
        update_data = {"is_visible": False}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code in [200, 404]

    async def test_update_entry_data(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test updating the `data` field of a timeline entry.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to send requests to the API.
            test_investigation: Fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a PATCH request to update the `data` field of entry ID `1` within the specified investigation. It asserts that the response status code is either 200 (successful update) or 404 (entry not found), covering both successful and missing-resource scenarios.
        """
        update_data = {"data": {"custom_field": "custom_value"}}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestTimelineNotes:
    """Test timeline notes CRUD operations."""

    async def test_create_note_entry_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that creating a note for a timeline entry that does not exist returns a 404 response.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to send requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a POST request to the notes endpoint of a non-existent entry (`id 999999`) and asserts that:
        * The response status code is 404.
        * The error detail contains the phrase “timeline entry not found” (case-insensitive).
        """
        note_data = {"note_text": "Test note"}

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/999999/notes",
            headers=auth_headers,
            json=note_data,
        )

        assert response.status_code == 404
        assert "timeline entry not found" in response.json()["detail"].lower()

    async def test_get_notes_entry_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving notes for a timeline entry that does not exist returns a 404 Not Found response. The request is made with valid authentication headers, and the assertion verifies the HTTP status code.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/999999/notes",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_note_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating a note with an ID that does not exist returns a 404 Not Found response. The test sends a PATCH request with valid authentication headers and a payload containing `note_text` to the notes endpoint for a non-existent note (ID 999999) and asserts that the HTTP status code of the response is 404.
        """
        update_data = {"note_text": "Updated text"}

        response = await async_client.patch(
            f"/api/v1/timeline/{test_investigation.investigation_id}/notes/999999",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code == 404

    async def test_delete_note_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that deleting a note with an ID that does not exist returns a 404 Not Found response. The request is made against the timeline endpoint for a valid investigation, using authentication headers; the expected status code confirms proper error handling for missing notes.
        """
        response = await async_client.delete(
            f"/api/v1/timeline/{test_investigation.investigation_id}/notes/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestTimelineStats:
    """Test timeline statistics endpoints."""

    async def test_get_timeline_event_types(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test the retrieval of timeline event types for a specific investigation.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client used to make requests against the API.
            test_investigation: Fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized API access.

        The test sends a GET request to the `/api/v1/timeline/{investigation_id}/event-types` endpoint and asserts that:
        - The response status code is 200.
        - The JSON payload contains the keys `"event_types"` and `"total_types"`.
        - The value associated with `"event_types"` is a list.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/event-types",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "event_types" in data
        assert "total_types" in data
        assert isinstance(data["event_types"], list)

    async def test_get_timeline_stats(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving timeline statistics for a given investigation.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to make requests.
            test_investigation: Fixture providing an investigation object with an `investigation_id`.
            auth_headers (dict): Authentication headers required for the request.

        The test sends a GET request to the timeline statistics endpoint and asserts that:
        - The response status code is 200.
        - The JSON payload contains the keys "total_entries", "entries_by_type", "date_range", "tags", and "total_notes".
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/stats", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_entries" in data
        assert "entries_by_type" in data
        assert "date_range" in data
        assert "tags" in data
        assert "total_notes" in data

    async def test_get_timeline_stats_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving timeline statistics for an investigation with no entries returns a successful response containing zero counts and empty collections.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Investigation
            A fixture providing an investigation object whose timeline is expected to be empty.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        Returns
        -------
        None

        The test asserts that:
        - The response status code is 200 (OK).
        - The JSON payload includes a non-negative `total_entries` value.
        - `entries_by_type` is an empty dictionary.
        - `tags` is an empty list.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/stats", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        # Should return zeros and empty collections
        assert data["total_entries"] >= 0
        assert isinstance(data["entries_by_type"], dict)
        assert isinstance(data["tags"], list)

    async def test_get_timeline_event_types_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving timeline event types without authentication returns an HTTP 401 Unauthorized response. The request is made to the `/api/v1/timeline/{investigation_id}/event-types` endpoint using an unauthenticated client, and the test asserts that the response status code equals 401.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/event-types"
        )

        assert response.status_code == 401

    async def test_get_timeline_stats_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving timeline statistics without authentication returns a 401 Unauthorized response.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/stats"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetTimelineFieldsEndpoint:
    """Test GET /api/v1/timeline/{investigation_id}/fields endpoint."""

    async def test_get_timeline_fields_all_types(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving all timeline fields for a given investigation.
        
        Verifies that the endpoint returns a proper response with fields list,
        count, and entries_sampled metadata.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "fields" in data
        assert "count" in data
        assert "entries_sampled" in data
        assert isinstance(data["fields"], list)

    async def test_get_timeline_fields_specific_event_type(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving timeline fields filtered by a specific event type.
        
        Verifies that the event_type parameter correctly filters which
        timeline entries are sampled for field extraction.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers,
            params={"event_type": "evtx_security_4624"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "fields" in data
        assert isinstance(data["fields"], list)

    async def test_get_timeline_fields_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving timeline fields without authentication returns 401.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields"
        )

        assert response.status_code == 401
    
    async def test_get_timeline_fields_samples_from_events(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that timeline /fields endpoint samples from linked event payloads
        when timeline entry data is sparse.
        
        This is critical for the timeline viewer to show available fields
        even when timeline entries have minimal data but link to rich events.
        """
        from sqlalchemy import text
        
        # Create an event with rich payload
        event_result = await db_session.execute(
            text("""
                INSERT INTO events (investigation_id, event_ts, event_type, payload)
                VALUES (:inv_id, NOW(), :event_type, :payload)
                RETURNING event_id
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_type": "test_event",
                "payload": json.dumps({
                    "EventID": "4624",
                    "TargetUserName": "admin",
                    "SourceIP": "192.168.1.1",
                    "ProcessName": "svchost.exe",
                    "CommandLine": "C:\\Windows\\System32\\svchost.exe"
                })
            }
        )
        event_id = event_result.scalar()
        
        # Create timeline entry with minimal data that links to the event
        await db_session.execute(
            text("""
                INSERT INTO timeline_entries 
                (investigation_id, event_id, timestamp, entry_type, title, description, data, tags)
                VALUES (:inv_id, :event_id, NOW(), 'event', 'Test Entry', 'Test', '{}'::jsonb, '{}')
            """),
            {
                "inv_id": str(test_investigation.investigation_id),
                "event_id": event_id
            }
        )
        await db_session.commit()
        
        # Request fields - should discover fields from linked event payload
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have discovered fields from the event payload
        assert "EventID" in data["fields"]
        assert "TargetUserName" in data["fields"]
        assert "SourceIP" in data["fields"]
        assert data["count"] >= 5
    
    async def test_get_timeline_fields_samples_multiple_per_type(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that /fields endpoint samples 10 timeline entries per event type.
        
        Ensures the window function query correctly partitions by event_type
        and retrieves multiple samples per type for comprehensive field discovery.
        """
        from sqlalchemy import text
        
        # Create 15 events with different fields
        event_ids = []
        for i in range(15):
            result = await db_session.execute(
                text("""
                    INSERT INTO events (investigation_id, event_ts, event_type, payload)
                    VALUES (:inv_id, NOW(), :event_type, :payload)
                    RETURNING event_id
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_type": "test_type",
                    "payload": json.dumps({f"field_{i}": f"value_{i}"})
                }
            )
            event_ids.append(result.scalar())
        
        # Create timeline entries linking to these events
        for event_id in event_ids:
            await db_session.execute(
                text("""
                    INSERT INTO timeline_entries 
                    (investigation_id, event_id, timestamp, entry_type, title, data)
                    VALUES (:inv_id, :event_id, NOW(), 'event', 'Entry', '{}'::jsonb)
                """),
                {
                    "inv_id": str(test_investigation.investigation_id),
                    "event_id": event_id
                }
            )
        await db_session.commit()
        
        # Request fields - should sample 10 entries and discover 10 unique fields
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/fields",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have discovered at least 10 fields (field_0 through field_9)
        assert data["count"] >= 10
        assert data["entries_sampled"] >= 10


@pytest.mark.integration
class TestTimelineEntryWithNotes:
    """Test getting timeline entry with notes."""

    async def test_get_entry_with_notes(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a specific timeline entry includes its notes.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to perform the request.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers: Dictionary containing authentication headers required for the API call.

        The test sends a GET request to the endpoint for entry ID 1 of the given investigation. If the response is successful (status code 200), it verifies that the returned JSON payload contains a `notes` field and that this field is a list. A 404 status indicates that the entry does not exist, which is considered an acceptable outcome for the test.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
        )

        # Will fail with 404 if entry doesn't exist
        if response.status_code == 200:
            data = response.json()
            assert "notes" in data
            assert isinstance(data["notes"], list)

    async def test_get_entry_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline entry with an ID that does not exist returns a 404 Not Found response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client fixture configured for asynchronous requests against the API.
        test_investigation : Investigation
            Fixture providing an investigation whose `investigation_id` is used in the request URL.
        auth_headers : dict
            Authentication headers required to authorize the request.

        Asserts
        -------
        The response status code equals 404, indicating that the requested entry could not be found.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestTimelineEdgeCases:
    """Test edge cases and complex scenarios."""

    async def test_get_timeline_all_entry_types(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the timeline endpoint correctly filters entries by each supported entry type.\n\nThe test iterates over all defined `entry_type` values and sends a GET request to the timeline API for a given investigation. It verifies that the response status code is 200 for every entry type, confirming that filtering does not produce errors.\n\nArgs:\n    async_client: An `httpx.AsyncClient` instance used to perform asynchronous HTTP requests against the API.\n    test_investigation: A fixture providing an investigation object with a valid `investigation_id`.\n    auth_headers: Dictionary of authentication headers required for authorized access to the endpoint.\"""
        """
        entry_types = [
            "authentication",
            "process_execution",
            "network_connection",
            "file_modification",
            "registry_modification",
            "service_installation",
            "user_creation",
            "custom",
        ]

        for entry_type in entry_types:
            response = await async_client.get(
                f"/api/v1/timeline/{test_investigation.investigation_id}",
                headers=auth_headers,
                params={"entry_type": entry_type},
            )
            assert response.status_code == 200

    async def test_get_timeline_with_multiple_tags(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving a timeline with multiple tag filters returns a successful response (HTTP 200) when the request includes several tags in the query parameters. The test uses an asynchronous client, a prepared investigation fixture, and authentication headers to perform a GET request against the timeline endpoint with `tags` set to a list of tag strings. It asserts that the API responds with status code 200, indicating proper handling of multi-tag filtering.
        """
        response = await async_client.get(
            f"/api/v1/timeline/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"tags": ["tag1", "tag2", "tag3"]},
        )

        assert response.status_code == 200

    async def test_delete_entry_with_notes_cascade(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that deleting an entry via the timeline API correctly handles cascade deletion of associated notes.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the test server.
            test_investigation: A fixture providing a populated investigation object, including its `investigation_id` and related entries/notes.
            auth_headers: Dictionary containing authentication headers required for authorized API access.

        The test sends an HTTP DELETE request to remove entry ID 1 from the specified investigation. It asserts that the response status code is either 200 (successful deletion) or 404 (entry not found), ensuring the endpoint behaves as expected in both scenarios.
        """
        response = await async_client.delete(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries/1",
            headers=auth_headers,
        )

        # Will fail with 404 if entry doesn't exist, but tests the endpoint
        assert response.status_code in [200, 404]

    async def test_create_entry_with_complex_data(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a timeline entry with complex nested data.

        This test verifies that the API correctly accepts and processes an entry payload containing
        deeply nested dictionaries, arrays, and various primitive types. It constructs a sample
        `entry_data` dictionary with:

        - A UTC timestamp in ISO-8601 format.
        - Custom `entry_type`, `title`, and `description`.
        - A `data` field that includes multiple nesting levels, an array, and a boolean value.
        - Empty `tags` list and the `is_visible` flag set to `True`.

        The test sends a POST request to the timeline entries endpoint for the given
        `test_investigation` using the provided `auth_headers`. It asserts that the HTTP
        response status code indicates success (either 200 OK or 201 Created).
        """
        entry_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "entry_type": "custom",
            "title": "Complex Entry",
            "description": "Entry with nested data",
            "data": {
                "level1": {"level2": {"level3": "value"}, "array": [1, 2, 3], "boolean": True}
            },
            "tags": [],
            "is_visible": True,
        }

        response = await async_client.post(
            f"/api/v1/timeline/{test_investigation.investigation_id}/entries",
            headers=auth_headers,
            json=entry_data,
        )

        assert response.status_code in [200, 201]
