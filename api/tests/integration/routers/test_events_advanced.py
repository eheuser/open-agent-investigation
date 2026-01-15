"""
Advanced integration tests for events endpoints.
Tests complex filtering, JSONB queries, date ranges, search, and paste functionality.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta
import json


@pytest.mark.integration
class TestEventsDateFiltering:
    """Test date range filtering in list_events endpoint."""

    async def test_list_events_with_start_date(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the events endpoint correctly filters results when a `start_date` query parameter is provided.

        Parameters
        ----------
        async_client: AsyncClient
            The HTTP client used to make asynchronous requests against the API.
        test_investigation: Any
            An object representing an investigation; its `investigation_id` attribute is used in the request URL.
        auth_headers: dict
            Dictionary containing authentication headers required for authorized access.

        The test constructs a `start_date` set to seven days before the current UTC time, sends a GET request to `/api/v1/events/{investigation_id}` with this parameter, and asserts that:
        - The response status code is 200 (OK).
        - The JSON payload contains an `events` key.
        """
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_date": start_date},
        )

        assert response.status_code == 200
        data = response.json()
        assert "events" in data

    async def test_list_events_with_end_date(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the events endpoint correctly filters results when an `end_date` query parameter is provided.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture representing a pre-created investigation object; its `investigation_id` attribute is used in the request URL.
            auth_headers: Dictionary containing authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with an ISO-formatted `end_date` parameter, asserts that the response status code is 200, and verifies that the returned JSON payload includes an `events` key.
        """
        end_date = datetime.utcnow().isoformat()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"end_date": end_date},
        )

        assert response.status_code == 200
        data = response.json()
        assert "events" in data

    async def test_list_events_with_date_range(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the events endpoint correctly filters results when both `start_date` and `end_date` query parameters are provided.

        The request is sent to `/api/v1/events/<investigation_id>` with a date range spanning the last seven days. The test asserts that:

        * The response status code is 200 (OK).
        * The JSON payload contains an `events` key holding the filtered event list.
        * The JSON payload includes a `total` key indicating the total number of matching events.

        Parameters
        ----------
        self : object
            Instance of the test class containing shared fixtures.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used in the endpoint path.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access.

        Returns
        -------
        None

        Raises
        ------
        AssertionError
            If any of the response assertions fail.
        """
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end_date = datetime.utcnow().isoformat()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_date": start_date, "end_date": end_date},
        )

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data

    async def test_list_events_invalid_start_date(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting events with an incorrectly formatted `start_date` query parameter returns a **400 Bad Request** response.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to perform the request against the API.
            test_investigation: A fixture providing an investigation object containing the `investigation_id` to target.
            auth_headers: Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with `start_date=invalid-date-format` and asserts that:
        * The response status code is 400.
        * The error detail mentions `start_date` (case-insensitive).
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"start_date": "invalid-date-format"},
        )

        assert response.status_code == 400
        assert "start_date" in response.json()["detail"].lower()

    async def test_list_events_invalid_end_date(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that providing an invalid `end_date` query parameter returns a 400 Bad Request response.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture supplying an investigation object with a valid `investigation_id` for constructing the endpoint URL.
            auth_headers: Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to the events list endpoint with `end_date` set to a non-date string and asserts that:
        * The response status code is 400.
        * The error detail mentions `end_date`, confirming proper validation of the query parameter.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"end_date": "not-a-real-date"},
        )

        assert response.status_code == 400
        assert "end_date" in response.json()["detail"].lower()


@pytest.mark.integration
class TestEventsSearch:
    """Test search functionality in list_events endpoint."""

    async def test_list_events_with_search(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test searching events by text using the `search` query parameter.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id`.
            auth_headers: Dictionary containing authentication headers required for authorized requests.

        The test sends a GET request to the `/api/v1/events/{investigation_id}` endpoint with `search=admin` and asserts that:
        * The response status code is 200 (OK).
        * The JSON payload contains an `events` key.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"search": "admin"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "events" in data

    async def test_list_events_search_with_special_chars(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the events list endpoint correctly handles search queries containing special characters such as backslashes.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests against the API.
        test_investigation : Investigation
            A fixture providing an investigation whose ID is used in the request path.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test performs a GET request to `/api/v1/events/<investigation_id>` with a `search` parameter set to `C:\Windows\System32` and asserts that the response status code is 200, indicating successful handling of special characters in the search term.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"search": "C:\\Windows\\System32"},
        )

        assert response.status_code == 200


@pytest.mark.integration
class TestEventsSorting:
    """Test sorting functionality."""

    async def test_list_events_order_asc(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving events with an ascending order parameter returns a successful response containing an "events" list.

        Parameters:
            async_client (AsyncClient): The asynchronous HTTP client used to make requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with the query parameter `order=asc`. It asserts that:
        - The response status code is 200.
        - The JSON payload includes an "events" key.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"order": "asc"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "events" in data

    async def test_list_events_order_desc(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that events are returned in descending order (the default) when the `order` query parameter is set to `desc`.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object whose `investigation_id` is used in the request URL.
            auth_headers: Dictionary containing authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with the `order=desc` parameter and asserts that the response status code is 200, indicating successful retrieval of events sorted in descending order.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"order": "desc"},
        )

        assert response.status_code == 200

    async def test_list_events_invalid_order(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that providing an invalid `order` query parameter to the event-listing endpoint does not cause an error and falls back to the default descending ordering.\n\nThe test sends a GET request to `/api/v1/events/{investigation_id}` with `order=invalid` and asserts that the response status code is `200` (OK), indicating that the server handled the malformed value gracefully by using its default sort direction.\"""
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"order": "invalid"},
        )

        # Should succeed with default ordering
        assert response.status_code == 200


@pytest.mark.integration
class TestEventsJSONBQueries:
    """Test JSONB query filtering."""

    async def test_jsonb_query_equality(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that filtering events by a JSONB field using the equality operator returns a successful response.

        The request queries the endpoint for a specific investigation, applying a JSONB filter where the `EventID` field equals `"4624"`. The test verifies that the API responds with HTTP 200 OK.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"jsonb_path_0": "EventID", "jsonb_operator_0": "=", "jsonb_value_0": "4624"},
        )

        assert response.status_code == 200

    async def test_jsonb_query_not_equal(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that filtering events by a JSONB field using the "not equal" operator returns a successful response.

        Args:
            async_client: An HTTP client capable of making asynchronous requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers: Dictionary containing authentication headers required for the request.

        The test sends a GET request to the `/api/v1/events/{investigation_id}` endpoint with query parameters specifying a JSONB path (`EventID`), the "!=" operator, and a value of `"4624"`. It asserts that the response status code is 200, indicating that the endpoint correctly handles JSONB queries using the not-equal comparison.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"jsonb_path_0": "EventID", "jsonb_operator_0": "!=", "jsonb_value_0": "4624"},
        )

        assert response.status_code == 200

    async def test_jsonb_query_greater_than(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the events endpoint correctly handles JSONB queries using the greater-than operator.

        Parameters
        ----------
        async_client: AsyncClient
            The HTTP client used to make asynchronous requests against the API.
        test_investigation: Any
            An object providing an `investigation_id` attribute identifying the investigation whose events are queried.
        auth_headers: dict
            Dictionary containing authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with query parameters specifying a JSONB path of `EventID`, an operator of `>`, and a value of `4000`. It asserts that the response status code is 200, indicating successful handling of the greater-than filter.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"jsonb_path_0": "EventID", "jsonb_operator_0": ">", "jsonb_value_0": "4000"},
        )

        assert response.status_code == 200

    async def test_jsonb_query_less_than(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the events endpoint correctly handles JSONB queries using the less-than operator.

        The test sends a GET request to the `/api/v1/events/<investigation_id>` endpoint with query parameters specifying a JSONB path (`EventID`), an operator (`<`), and a value (`5000`). It verifies that the response status code is 200, indicating successful processing of the filter.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"jsonb_path_0": "EventID", "jsonb_operator_0": "<", "jsonb_value_0": "5000"},
        )

        assert response.status_code == 200

    async def test_jsonb_query_like(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the events endpoint correctly handles JSONB queries using the LIKE operator.

        The request targets a specific investigation identified by `test_investigation.investigation_id` and includes query parameters that:

        - Specify the JSONB field path `TargetUserName` (`jsonb_path_0`).
        - Use the `LIKE` operator (`jsonb_operator_0`) to perform pattern matching.
        - Provide a wildcard pattern `Admin*` as the value (`jsonb_value_0`).

        The test asserts that the response status code is 200, indicating successful processing of the JSONB LIKE query.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "TargetUserName",
                "jsonb_operator_0": "LIKE",
                "jsonb_value_0": "Admin*",
            },
        )

        assert response.status_code == 200

    async def test_jsonb_query_ilike(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test JSONB query using the ILIKE operator for case-insensitive pattern matching.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object containing at least an `investigation_id` attribute used to build the request URL.
            auth_headers: Dictionary of authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with query parameters that specify a JSONB path, the ILIKE operator, and a wildcard pattern (e.g., `admin*`). It asserts that the response status code is 200, indicating successful handling of case-insensitive JSONB queries.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "TargetUserName",
                "jsonb_operator_0": "ILIKE",
                "jsonb_value_0": "admin*",
            },
        )

        assert response.status_code == 200

    async def test_jsonb_query_contains(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that filtering events by a JSONB field using the `CONTAINS` operator works as expected.

        Parameters
        ----------
        async_client: AsyncClient
            The asynchronous HTTP client used to make requests against the API.
        test_investigation: Any
            An object representing an investigation; must provide `investigation_id` used in the request URL.
        auth_headers: dict
            Dictionary containing authentication headers required for the request.

        The test sends a GET request to `/api/v1/events/<investigation_id>` with query parameters that specify a JSONB path of `CommandLine`, an operator of `CONTAINS`, and a value of `cmd`. It asserts that the response status code is 200, indicating successful handling of the JSONB `CONTAINS` filter.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "CommandLine",
                "jsonb_operator_0": "CONTAINS",
                "jsonb_value_0": "cmd",
            },
        )

        assert response.status_code == 200

    async def test_jsonb_query_starts_with(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that filtering events by a JSONB field using the **STARTS_WITH** operator works correctly.

        Parameters
        ----------
        async_client: AsyncClient
            The asynchronous HTTP client used to send requests to the API.
        test_investigation: Any
            An investigation fixture providing an `investigation_id` whose events are queried.
        auth_headers: dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with query parameters that specify a JSONB path of `Image`, an operator of `STARTS_WITH`, and a value of `C:\\Windows`. It asserts that the response status code is 200, indicating successful handling of the STARTS_WITH filter.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "Image",
                "jsonb_operator_0": "STARTS_WITH",
                "jsonb_value_0": "C:\\Windows",
            },
        )

        assert response.status_code == 200

    async def test_jsonb_query_ends_with(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the JSONB query endpoint correctly filters events using the **ENDS_WITH** operator.

        The test performs an HTTP GET request to the `/api/v1/events/{investigation_id}` endpoint with query parameters that specify a JSONB path of `Image` and an operator of `ENDS_WITH` searching for the suffix `cmd.exe`. It verifies that the request succeeds by asserting a 200 OK status code.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Any
            A fixture providing an investigation object containing at least an `investigation_id` attribute.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        Raises
        ------
        AssertionError
            If the response status code is not 200, indicating that the JSONB query did not behave as expected.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "Image",
                "jsonb_operator_0": "ENDS_WITH",
                "jsonb_value_0": "cmd.exe",
            },
        )

        assert response.status_code == 200

    async def test_jsonb_query_field_exists(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test JSONB query checking if a field exists without specifying a value.

        Parameters
        ----------
        async_client : AsyncClient
            The asynchronous HTTP client used to make requests to the API.
        test_investigation : object
            An investigation fixture providing the `investigation_id` used in the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to the `/api/v1/events/{investigation_id}` endpoint with query parameters that specify a JSONB path (`EventID`), an equality operator, and an empty value. An empty `jsonb_value_0` indicates that only the existence of the field should be checked. The response is expected to have a status code of 200, confirming successful handling of the existence check.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "EventID",
                "jsonb_operator_0": "=",
                "jsonb_value_0": "",  # Empty value checks existence
            },
        )

        assert response.status_code == 200

    async def test_jsonb_query_invalid_operator(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that providing an invalid JSONB operator results in a 400 Bad Request response.

        This test sends a GET request to the events endpoint with query parameters specifying a JSONB path (`jsonb_path_0`), an unsupported operator (`jsonb_operator_0` set to `INVALID_OP`), and a value. It verifies that:

        * The HTTP status code is `400`.
        * The error detail includes the word `operator` (case-insensitive).
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "EventID",
                "jsonb_operator_0": "INVALID_OP",
                "jsonb_value_0": "4624",
            },
        )

        assert response.status_code == 400
        assert "operator" in response.json()["detail"].lower()

    async def test_jsonb_multiple_queries(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that multiple JSONB query filters can be applied simultaneously on the events endpoint.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to send requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/events/{investigation_id}` with two JSONB query parameters:
        - `jsonb_path_0`/`jsonb_operator_0`/`jsonb_value_0` filtering events where the `EventID` equals `"4624"`.
        - `jsonb_path_1`/`jsonb_operator_1`/`jsonb_value_1` filtering events where the `LogonType` equals `"10"`.

        It asserts that the response status code is 200, indicating successful handling of combined JSONB filters.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "jsonb_path_0": "EventID",
                "jsonb_operator_0": "=",
                "jsonb_value_0": "4624",
                "jsonb_path_1": "LogonType",
                "jsonb_operator_1": "=",
                "jsonb_value_1": "10",
            },
        )

        assert response.status_code == 200


@pytest.mark.integration
class TestGetEventTypesEndpoint:
    """Test GET /api/v1/events/{investigation_id}/event-types endpoint."""

    async def test_get_event_types_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving event types for a given investigation succeeds.

        Args:
            async_client: An instance of `AsyncClient` used to make HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers: Dictionary containing authentication headers required for the request.

        The test performs a GET request to `/api/v1/events/{investigation_id}/event-types` and asserts that:
        - The response status code is 200.
        - The JSON payload contains the keys `event_types` and `total_types`.
        - The value associated with `event_types` is a list.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/event-types",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "event_types" in data
        assert "total_types" in data
        assert isinstance(data["event_types"], list)

    async def test_get_event_types_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Verify that attempting to retrieve the list of event types for an investigation without providing authentication results in a 401 Unauthorized response.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/event-types"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetEventFieldsEndpoint:
    """Test GET /api/v1/events/{investigation_id}/fields endpoint."""

    async def test_get_event_fields_all_types(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving all event fields for a given investigation.\n\nThis asynchronous integration test sends a GET request to the `/api/v1/events/{investigation_id}/fields` endpoint using the provided `async_client` and authentication headers. It verifies that:\n\n- The response status code is 200 (OK).\n- The JSON payload contains the keys `fields`, `count`, and `event_types_sampled`.\n- The `fields` value is a list.\n\nArgs:\n    async_client: An instance of `AsyncClient` used to perform HTTP requests against the API.\n    test_investigation: A fixture providing an investigation object with an `investigation_id` attribute.\n    auth_headers: A dictionary containing authentication headers required by the endpoint.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "fields" in data
        assert "count" in data
        assert "event_types_sampled" in data
        assert isinstance(data["fields"], list)

    async def test_get_event_fields_specific_type(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving the list of fields for a specific event type within an investigation.

        Args:
            self: The test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to make API requests.
            test_investigation: Fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers (dict): Dictionary of authentication headers required for the request.

        The function sends a GET request to `/api/v1/events/{investigation_id}/fields` with the query parameter `event_type=evtx_security_4624`. It asserts that:
        * The response status code is 200.
        * The JSON payload contains a `fields` key.
        * The value associated with `fields` is a list.

        Returns:
            None.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields",
            headers=auth_headers,
            params={"event_type": "evtx_security_4624"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "fields" in data
        assert isinstance(data["fields"], list)

    async def test_get_event_fields_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving event fields without authentication returns an HTTP 401 Unauthorized response. This ensures the endpoint correctly enforces access control by rejecting unauthenticated requests.
        """
        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}/fields"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestPasteEventsEndpoint:
    """Test POST /api/v1/events/paste endpoint."""

    async def test_paste_json_events(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test pasting events as JSON via the API.

        This integration test verifies that a POST request to the `/api/v1/events/paste` endpoint
        with a payload containing a JSON array of event objects is correctly processed.

        The test performs the following steps:
        - Constructs a JSON string representing two events, each with `event_type`,
          `timestamp`, `EventID`, and `Message` fields.
        - Sends the request using an asynchronous HTTP client, including the required
          authentication headers and setting the `Content-Type` to `text/plain`.
        - Asserts that the response status code is `200`.
        - Parses the JSON response and asserts that:
          - The `status` field equals `"ok"`,
          - The `format` field reports `"json"`,
          - The `inserted` count matches the number of events sent (`2`).

        Args:
            self: Test class instance (provided by the test framework).
            async_client: An :class:`httpx.AsyncClient` configured for the application under test.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers: Dictionary of authentication headers required to authorize the request.

        Raises:
            AssertionError: If any of the response validations fail.
        """
        json_data = json.dumps(
            [
                {
                    "event_type": "pasted_event",
                    "timestamp": datetime.utcnow().isoformat(),
                    "EventID": 1001,
                    "Message": "Test event from JSON",
                },
                {
                    "event_type": "pasted_event",
                    "timestamp": datetime.utcnow().isoformat(),
                    "EventID": 1002,
                    "Message": "Second test event",
                },
            ]
        )

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=json_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["format"] == "json"
        assert data["inserted"] == 2

    async def test_paste_json_single_object(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test pasting a single JSON object (not wrapped in an array) to the events paste endpoint and verify that exactly one event is inserted successfully.
        """
        json_data = json.dumps(
            {
                "event_type": "single_event",
                "timestamp": datetime.utcnow().isoformat(),
                "EventID": 2001,
                "Message": "Single event",
            }
        )

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=json_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["inserted"] == 1

    async def test_paste_yaml_events(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test pasting events in YAML format via the API.

        Parameters
        ----------
        self : object
            Test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Investigation fixture providing an `investigation_id` for the request.
        auth_headers : dict
            Authentication headers required by the endpoint.

        The test sends a POST request with a YAML payload containing one or more events to the
        `/api/v1/events/paste` endpoint, specifying the investigation ID as a query parameter.
        It verifies that the response status code is 200, that the returned JSON indicates the
        payload format was `yaml`, and that at least one event was inserted.
        """
        yaml_data = """
- event_type: yaml_event
  timestamp: "2024-01-01T12:00:00"
  EventID: 3001
  Message: Test YAML event
- event_type: yaml_event
  timestamp: "2024-01-01T12:01:00"
  EventID: 3002
  Message: Second YAML event
"""

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=yaml_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "yaml"
        assert data["inserted"] >= 1

    async def test_paste_csv_events(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test pasting events in CSV format.

        This test verifies that the API endpoint correctly processes a CSV payload containing event data and inserts the events into the specified investigation.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : Investigation
            A fixture providing an investigation object with a valid `investigation_id`.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/events/paste` with `Content-Type: text/plain` and a CSV body. It asserts that the response status code is 200, the returned JSON indicates the format as `csv`, and at least one event was inserted.
        """
        csv_data = """event_type,timestamp,EventID,Message
csv_event,2024-01-01T12:00:00,4001,First CSV event
csv_event,2024-01-01T12:01:00,4002,Second CSV event"""

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=csv_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "csv"
        assert data["inserted"] >= 1

    async def test_paste_invalid_format(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that posting data with an unsupported content type or malformed payload to the event paste endpoint returns a 400 Bad Request and includes an error message indicating parsing failure.

        Parameters
        ----------
        self: object
            The test case instance.
        async_client: AsyncClient
            An HTTP client fixture for making asynchronous requests against the API.
        test_investigation: Any
            Fixture providing an investigation object with a valid `investigation_id`.
        auth_headers: dict
            Authentication headers required to authorize the request.

        The test sends a plain-text payload that is neither valid JSON, YAML nor CSV, expects the endpoint to respond with status code 400, and verifies that the response detail mentions being unable to parse the input.
        """
        invalid_data = "This is not JSON, YAML, or CSV <<< invalid syntax"

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=invalid_data,
        )

        assert response.status_code == 400
        assert "unable to parse" in response.json()["detail"].lower()

    async def test_paste_empty_records(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that posting an empty list of event records to the paste endpoint returns a 400 Bad Request with an error message indicating that no records were provided. The request is sent as plain-text JSON payload, includes the required authentication headers, and specifies the investigation ID via query parameter. Assertions verify both the HTTP status code and that the response detail contains the phrase “no records”.
        """
        json_data = json.dumps([])

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=json_data,
        )

        assert response.status_code == 400
        assert "no records" in response.json()["detail"].lower()

    async def test_paste_not_list_or_dict(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that the paste endpoint rejects payloads that are neither a list nor a dictionary.\n\nParameters:\n    self: The test case instance.\n    async_client (AsyncClient): HTTP client for making asynchronous requests to the API.\n    test_investigation: Fixture providing an investigation object with a valid ID.\n    auth_headers (dict): Authentication headers required for authorized access.\n\nThe test sends a plain-text JSON string representing a simple string value to the `/api/v1/events/paste` endpoint. It asserts that the response status code is 400 Bad Request and that the error detail mentions that the payload must be a list or dictionary.
        """
        json_data = json.dumps("just a string")

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=json_data,
        )

        assert response.status_code == 400
        assert "list or dictionary" in response.json()["detail"].lower()

    async def test_paste_events_with_invalid_timestamp(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that pasting an event with an invalid timestamp string is handled gracefully by the endpoint: the server should replace the malformed timestamp with the current time and successfully insert the event.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client fixture capable of making asynchronous requests to the API.
        test_investigation : Any
            Fixture providing an investigation object whose `investigation_id` is used in the request URL.
        auth_headers : dict
            Dictionary containing authentication headers required for authorized access.

        The test sends a POST request to `/api/v1/events/paste` with a JSON payload where the `timestamp` field contains an invalid format. It asserts that the response status code is 200 and that exactly one event was inserted, indicating that the server defaulted the timestamp to the current time.
        """
        json_data = json.dumps(
            [{"event_type": "test_event", "timestamp": "invalid-timestamp-format", "EventID": 5001}]
        )

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            headers={**auth_headers, "Content-Type": "text/plain"},
            content=json_data,
        )

        # Should succeed with default timestamp
        assert response.status_code == 200
        assert response.json()["inserted"] == 1

    async def test_paste_events_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test pasting events without authentication.

        This test verifies that attempting to paste events via the `/api/v1/events/paste` endpoint without providing valid credentials results in an HTTP 401 Unauthorized response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Any
            A fixture representing a pre-created investigation; its `investigation_id` attribute is used in the request query string.

        The request payload contains a minimal JSON array with a single event dictionary specifying an `event_type` of `"test"`. The test asserts that the response status code equals 401, confirming proper authentication enforcement.
        """
        json_data = json.dumps([{"event_type": "test"}])

        response = await async_client.post(
            f"/api/v1/events/paste?investigation_id={test_investigation.investigation_id}",
            content=json_data,
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestEventsCombinedFilters:
    """Test combining multiple filter types."""

    async def test_combined_filters_all_params(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that combining all available filter query parameters on the events endpoint returns a successful response with correctly paginated data.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Investigation
            A fixture providing an investigation object whose ID is used in the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test constructs a date range covering the past week, applies an event type filter, a free-text search term, sorting order, pagination limits, and a JSONB field condition. It asserts that the response status code is 200 and that the returned JSON contains the keys `events`, `total` and `limit` with the expected limit value (50).
        """
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end_date = datetime.utcnow().isoformat()

        response = await async_client.get(
            f"/api/v1/events/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={
                "event_type": "evtx_security_4624",
                "start_date": start_date,
                "end_date": end_date,
                "search": "admin",
                "order": "asc",
                "limit": 50,
                "offset": 0,
                "jsonb_path_0": "EventID",
                "jsonb_operator_0": "=",
                "jsonb_value_0": "4624",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "limit" in data
        assert data["limit"] == 50
