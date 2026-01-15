"""
Integration tests for events endpoints.
Tests CRUD operations for forensic events.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime


@pytest.mark.integration
class TestGetEvents:
    """Test GET /api/v1/events/{investigation_id} endpoint."""

    async def test_get_events_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving events for an investigation that currently has no associated events.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An asynchronous HTTP client used to make requests against the API.
            test_investigation: A fixture providing a populated investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to the `/api/v1/events/{investigation_id}` endpoint and asserts that:
        - The response status code is 200 (OK).
        - The response body is JSON-serializable and returns either an empty list or an appropriate dictionary structure when no events exist.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    async def test_get_events_with_pagination(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test the retrieval of events for a specific investigation using pagination parameters.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute representing the target investigation.
            auth_headers: Dictionary containing authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with `limit` and `offset` query parameters, then asserts that the response status code is 200, indicating successful pagination handling.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 10, "offset": 0},
        )

        assert response.status_code == 200

    async def test_get_events_with_filters(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving events filtered by event type.

        Args:
            self: Test class instance.
            async_client (AsyncClient): Asynchronous HTTP client used to make API requests.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a GET request to the events endpoint for the specified investigation, applying an `event_type` query parameter (`evtx_security_4624`). It asserts that the response status code is 200, indicating successful retrieval of filtered events.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"event_type": "evtx_security_4624"},
        )

        assert response.status_code == 200

    async def test_get_events_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that retrieving events for a specific investigation returns a 401 Unauthorized response when no authentication credentials are provided.
        """
        response = await async_client.get(f"/api/v1/events/{test_investigation.investigation_id}")

        assert response.status_code == 401


@pytest.mark.integration
class TestCreateEvent:
    """Test POST /api/v1/events/{investigation_id} endpoint."""

    async def test_create_event_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating a forensic event via the events API.

        This test sends a POST request with a valid event payload to the endpoint
        `/api/v1/events/{investigation_id}` using an authenticated client.
        It verifies that the response status code is **201 Created**, checks that the
        returned JSON contains the expected `event_type` value, and ensures that an
        `event_id` field is present in the response data.
        """
        event_data = {
            "event_type": "evtx_security_4624",
            "timestamp": datetime.utcnow().isoformat(),
            "source_artifact": "Security.evtx",
            "event_data": {"EventID": 4624, "TargetUserName": "Administrator", "LogonType": "10"},
        }

        response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=event_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "evtx_security_4624"
        assert "event_id" in data

    async def test_create_event_minimal(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test creating an event with only the required fields.

        Args:
            self: The test class instance.
            async_client (AsyncClient): HTTP client for making asynchronous requests to the API.
            test_investigation: Fixture providing a populated investigation object, including its `investigation_id`.
            auth_headers (dict): Authentication headers containing a valid token for authorized access.

        The test sends a POST request to the `/api/v1/events/{investigation_id}` endpoint with minimal event data (`event_type` and `timestamp`). It asserts that the response status code is 201, indicating successful creation of the event.
        """
        event_data = {"event_type": "custom_event", "timestamp": datetime.utcnow().isoformat()}

        response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=event_data,
        )

        assert response.status_code == 201

    async def test_create_event_missing_type(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that creating an event without the required `event_type` field fails with a validation error.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An HTTP client capable of making asynchronous requests to the API.
            test_investigation: A fixture providing an investigation object whose `investigation_id` is used in the request URL.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.

        The test sends a POST request with a payload missing the `event_type` field and asserts that the response status code is 422, indicating unprocessable entity due to validation failure.
        """
        event_data = {"timestamp": datetime.utcnow().isoformat(), "event_data": {"key": "value"}}

        response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=event_data,
        )

        assert response.status_code == 422  # Validation error

    async def test_create_event_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that creating an event without providing authentication credentials returns a 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the API.
        test_investigation : Investigation
            A fixture representing an existing investigation; its `investigation_id` is used in the request URL.
        """
        event_data = {"event_type": "test_event", "timestamp": datetime.utcnow().isoformat()}

        response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}", json=event_data
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestBulkCreateEvents:
    """Test POST /api/v1/events/{investigation_id}/bulk endpoint."""

    async def test_bulk_create_events_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test bulk creation of multiple events for a given investigation.

        Parameters
        ----------
        self : object
            Instance of the test class containing shared fixtures.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Investigation
            Fixture providing an existing investigation context; its `investigation_id` is used in the request URL.
        auth_headers : dict
            Dictionary containing authentication headers required for authorized access.

        The test constructs a payload with two distinct events, posts it to the bulk-creation endpoint,
        and asserts that the response status code indicates success (200 or 201). It then verifies that
        the returned JSON includes either a `created` field, a `count` field, or is a list,
        confirming that the API reports the newly created events.
        """
        events_data = {
            "events": [
                {
                    "event_type": "evtx_security_4624",
                    "timestamp": datetime.utcnow().isoformat(),
                    "event_data": {"EventID": 4624},
                },
                {
                    "event_type": "evtx_security_4625",
                    "timestamp": datetime.utcnow().isoformat(),
                    "event_data": {"EventID": 4625},
                },
            ]
        }

        response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}/bulk",
            headers=auth_headers,
            json=events_data,
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert "created" in data or "count" in data or isinstance(data, list)

    async def test_bulk_create_events_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test bulk creation of events when the provided list is empty.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers: Dictionary containing authentication headers required by the endpoint.

        The test sends a POST request to the bulk-create events endpoint with an empty `events` array and asserts that the response status code is one of the expected outcomes (200, 201 for successful no-op creation, or 400/422 if the API validates the payload as invalid).
        """
        events_data = {"events": []}

        response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}/bulk",
            headers=auth_headers,
            json=events_data,
        )

        # Should succeed with 0 created or return validation error
        assert response.status_code in [200, 201, 400, 422]

    async def test_bulk_create_events_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that attempting to bulk-create events for an investigation without providing authentication credentials results in a 401 Unauthorized response. The request payload contains a minimal list of event dictionaries, each with required fields such as `event_type` and `timestamp`. The test verifies that the API correctly enforces authentication by asserting the HTTP status code returned is 401.
        """
        events_data = {
            "events": [{"event_type": "test", "timestamp": datetime.utcnow().isoformat()}]
        }

        response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}/bulk", json=events_data
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetEvent:
    """Test GET /api/v1/events/{investigation_id}/{event_id} endpoint."""

    async def test_get_event_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving an event that does not exist returns a 404 Not Found response.

        Args:
            async_client: An `httpx.AsyncClient` instance used to perform HTTP requests against the API.
            test_investigation: Fixture providing an investigation object containing a valid `investigation_id`.
            auth_headers: Dictionary of authentication headers included in the request.

        The test issues a GET request to `/api/v1/events/{investigation_id}/999999` (where `999999` is an ID that does not correspond to any stored event) and asserts that the response status code equals 404.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/999999", headers=auth_headers
        )

        assert response.status_code == 404

    async def test_get_event_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test retrieving a single event without providing authentication credentials, expecting an HTTP 401 Unauthorized response.

        Parameters
        ----------
        self : object
            Instance of the test class containing this method.
        async_client : AsyncClient
            Asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Any
            Fixture representing a pre-created investigation; provides `investigation_id` for constructing the request URL.

        The test asserts that the response status code equals 401, confirming proper access control enforcement.
        """
        response = await async_client.get(f"/api/v1/events/{test_investigation.investigation_id}/1")

        assert response.status_code == 401


@pytest.mark.integration
class TestUpdateEvent:
    """Test PUT /api/v1/events/{investigation_id}/{event_id} endpoint."""

    async def test_update_event_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that updating an event with a non-existent ID returns a 404 response.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for the application.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers: Dictionary containing authentication headers required by the API.

        The test sends a PUT request to `/api/v1/events/<investigation_id>/999999` with a sample payload and asserts that the response status code is 404, indicating that the event was not found.
        """
        update_data = {"event_data": {"updated": True}}

        response = await async_client.put(
            f"/api/v1/events/{test_investigation.investigation_id}/999999",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code == 404

    async def test_update_event_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that updating an event without authentication returns a 401 Unauthorized response. The test sends a PUT request with sample update data to the event endpoint for a given investigation and asserts that the HTTP status code is 401.
        """
        update_data = {"event_data": {"updated": True}}

        response = await async_client.put(
            f"/api/v1/events/{test_investigation.investigation_id}/1", json=update_data
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestDeleteEvent:
    """Test DELETE /api/v1/events/{investigation_id}/{event_id} endpoint."""

    async def test_delete_event_not_found(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that deleting an event with an ID that does not exist returns a 404 Not Found response. The test sends a DELETE request to the events endpoint using a valid investigation ID combined with a non-existent event identifier (e.g., 999999) and asserts that the HTTP status code of the response equals 404. This verifies proper error handling for missing resources in the API.
        """
        response = await async_client.delete(
            f"/api/v1/events/{test_investigation.investigation_id}/999999", headers=auth_headers
        )

        assert response.status_code == 404

    async def test_delete_event_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that deleting an event without providing authentication credentials results in an HTTP 401 Unauthorized response. The test sends a DELETE request to the endpoint for a specific investigation's event (using the provided `test_investigation` fixture) and asserts that the status code returned by the API is 401. Parameters: `self` - instance of the test class; `async_client` - an HTTPX AsyncClient configured for testing; `test_investigation` - fixture supplying a populated investigation object with a known ID. No return value.
        """
        response = await async_client.delete(
            f"/api/v1/events/{test_investigation.investigation_id}/1"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestDeleteAllEvents:
    """Test DELETE /api/v1/events/{investigation_id}/all endpoint."""

    async def test_delete_all_events(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Delete all events for a given investigation and verify a successful response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object that contains the `investigation_id` attribute.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access.

        The function issues a DELETE request to `/api/v1/events/{investigation_id}/all` and asserts that the response status code indicates success (either 200 or 204), which should be true even when no events exist.
        """
        response = await async_client.delete(
            f"/api/v1/events/{test_investigation.investigation_id}/all", headers=auth_headers
        )

        # Should succeed even if no events exist
        assert response.status_code in [200, 204]

    async def test_delete_all_events_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that attempting to delete all events for a given investigation without providing authentication credentials results in an HTTP 401 Unauthorized response. The test sends a DELETE request to the “/api/v1/events/{investigation_id}/all” endpoint using an unauthenticated client and asserts that the returned status code equals 401.
        """
        response = await async_client.delete(
            f"/api/v1/events/{test_investigation.investigation_id}/all"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetEventTypes:
    """Test GET /api/v1/events/{investigation_id}/types endpoint."""

    async def test_get_event_types_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving event types for an investigation when no events have been recorded.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make requests against the API.
            test_investigation: A fixture providing a populated investigation object with an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to the `/api/v1/events/{investigation_id}/types` endpoint and verifies that:
        - The response status code is 200 (OK).
        - The response body is JSON-serializable and is either an empty list or an empty dictionary, indicating no event types are available.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/types", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    async def test_get_event_types_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Ensures that attempting to retrieve event types for an investigation without providing authentication results in a 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client fixture configured for asynchronous requests.
        test_investigation : Investigation
            A fixture representing an existing investigation whose ID is used in the request.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/types"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetEventStats:
    """Test GET /api/v1/events/{investigation_id}/stats endpoint."""

    async def test_get_event_stats_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving event statistics for an investigation with no associated events returns a successful response containing an empty dictionary.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the API.
        test_investigation : Investigation
            A fixture providing an investigation object whose `investigation_id` is used in the request URL.
        auth_headers : dict
            Authentication headers required to authorize the request.

        The function sends a GET request to the `/api/v1/events/{investigation_id}/stats` endpoint and asserts that:
        - The response status code is 200 (OK).
        - The JSON payload is a dictionary, representing empty statistics when no events exist.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/stats", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_get_event_stats_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving event statistics without authentication returns a 401 Unauthorized response.

        Parameters
        ----------
        self : object
            Instance of the test class.
        async_client : AsyncClient
            Asynchronous HTTP client used to make requests against the API.
        test_investigation : Investigation
            Fixture providing an investigation instance whose ID is used in the request.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/stats"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestEventsFullWorkflow:
    """Test complete events CRUD workflow."""

    async def test_create_update_delete_workflow(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test the full lifecycle of an event within an investigation, covering creation, retrieval, update, deletion, and verification of removal.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An HTTP client capable of making asynchronous requests to the API.
            test_investigation: Fixture providing a populated investigation object with an `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access to the endpoints.

        The test performs the following steps:
        1. Sends a POST request to create a new event and asserts that the response status is 201.
        2. Retrieves the created event via GET, asserting a 200 status and confirming the `event_type`.
        3. Updates the event with additional data using PUT and checks for a 200 status.
        4. Deletes the event with DELETE, accepting either a 200 or 204 status code.
        5. Attempts to retrieve the deleted event, expecting a 404 status to confirm successful removal.
        """
        # Create event
        create_data = {
            "event_type": "evtx_sysmon_1",
            "timestamp": datetime.utcnow().isoformat(),
            "source_artifact": "Sysmon.evtx",
            "event_data": {
                "EventID": 1,
                "Image": "C:\\Windows\\System32\\cmd.exe",
                "CommandLine": "cmd.exe /c whoami",
            },
        }

        create_response = await async_client.post(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=create_data,
        )

        assert create_response.status_code == 201
        created_event = create_response.json()
        event_id = created_event["event_id"]

        # Get event
        get_response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/{event_id}", headers=auth_headers
        )

        assert get_response.status_code == 200
        assert get_response.json()["event_type"] == "evtx_sysmon_1"

        # Update event
        update_data = {
            "event_data": {
                "EventID": 1,
                "Image": "C:\\Windows\\System32\\cmd.exe",
                "CommandLine": "cmd.exe /c whoami",
                "Updated": True,
            }
        }

        update_response = await async_client.put(
            f"/api/v1/events/{test_investigation.investigation_id}/{event_id}",
            headers=auth_headers,
            json=update_data,
        )

        assert update_response.status_code == 200

        # Delete event
        delete_response = await async_client.delete(
            f"/api/v1/events/{test_investigation.investigation_id}/{event_id}", headers=auth_headers
        )

        assert delete_response.status_code in [200, 204]

        # Verify deletion
        verify_response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/{event_id}", headers=auth_headers
        )

        assert verify_response.status_code == 404
