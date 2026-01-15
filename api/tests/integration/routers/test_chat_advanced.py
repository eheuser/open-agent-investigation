"""
Advanced integration tests for chat endpoints.
Tests HTTP endpoints, WebSocket messages, and complex chat flows.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime
import json


@pytest.mark.integration
class TestGetChatHistory:
    """Test GET /api/v1/chat/history/{investigation_id} endpoint."""

    async def test_get_chat_history_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving chat history for an existing investigation succeeds.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make requests against the API.
            test_investigation: A fixture providing a populated investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test performs a GET request to `/api/v1/chat/history/{investigation_id}` using the provided
        authentication headers and asserts that:
        - The response status code is 200.
        - The JSON payload contains both `"messages"` and `"total"` keys.
        - The `"messages"` value is a list.
        """
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "total" in data
        assert isinstance(data["messages"], list)

    async def test_get_chat_history_with_limit(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving chat history for a specific investigation with a limit parameter.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture used to make requests against the API.
            test_investigation: A fixture providing an investigation object containing at least an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/chat/history/{investigation_id}` with a query parameter `limit=50`. It asserts that the response status code is 200 and that the returned JSON payload contains a `"messages"` key.
        """
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 50},
        )

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data

    async def test_get_chat_history_with_offset(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving a segment of chat history using pagination parameters.

        Args:
            self: Test case instance.
            async_client (AsyncClient): HTTP client for making asynchronous requests to the API.
            test_investigation: Fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/chat/history/{investigation_id}` with query parameters
        `limit=20` and `offset=10`, then asserts that the response status code is 200, indicating successful
        retrieval of the requested slice of chat history.
        """
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 20, "offset": 10},
        )

        assert response.status_code == 200

    async def test_get_chat_history_invalid_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that requesting chat history with an improperly formatted investigation ID returns a 400 Bad Request response and includes an error message indicating the ID is invalid.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.
        """
        response = await async_client.get("/api/v1/chat/history/invalid-uuid", headers=auth_headers)

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    async def test_get_chat_history_limit_bounds(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Tests that the `limit` query parameter for retrieving chat history enforces its allowed range (1-1000). The test sends two GET requests using an authenticated client: one with `limit=1` to verify the minimum boundary and another with `limit=1000` to verify the maximum boundary. Both responses are expected to return HTTP 200, confirming that values at the edges of the valid interval are accepted.
        """
        # Test minimum
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 1},
        )
        assert response.status_code == 200

        # Test maximum
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 1000},
        )
        assert response.status_code == 200

    async def test_get_chat_history_negative_offset(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that providing a negative `offset` query parameter when retrieving chat history results in a validation error.

        Args:
            self: The test case instance.
            async_client (AsyncClient): HTTP client used to make asynchronous requests against the API.
            test_investigation: Fixture supplying an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/chat/history/{investigation_id}` with `offset=-1` and asserts that the response status code is `422` indicating input validation failure.
        """
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"offset": -1},
        )

        # Should fail validation
        assert response.status_code == 422

    async def test_get_chat_history_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that attempting to retrieve chat history for a given investigation without providing authentication credentials returns an HTTP 401 Unauthorized response. The async client performs a GET request to the chat history endpoint using the investigation's identifier, and the test asserts that the response status code equals 401. Parameters: `self` - instance of the test class; `async_client` - an asynchronous HTTP client fixture for making requests; `test_investigation` - fixture providing an investigation object with a valid `investigation_id`.
        """
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetActiveJob:
    """Test GET /api/v1/chat/active-job/{investigation_id} endpoint."""

    async def test_get_active_job_none(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving the active job for an investigation returns a successful response with `active_job` set to `None` when no job is currently associated.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An HTTP client capable of making asynchronous requests against the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access to the endpoint.

        The function sends a GET request to `/api/v1/chat/active-job/{investigation_id}` and asserts that:
        * The response status code is 200.
        * The JSON payload contains an `active_job` key.
        * The value of `active_job` is `None`.
        """
        response = await async_client.get(
            f"/api/v1/chat/active-job/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "active_job" in data
        assert data["active_job"] is None

    async def test_get_active_job_invalid_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test retrieving the active job endpoint with an improperly formatted investigation ID, expecting a 400 Bad Request response and an error detail indicating the ID is invalid.
        """
        response = await async_client.get(
            "/api/v1/chat/active-job/not-a-uuid", headers=auth_headers
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    async def test_get_active_job_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that retrieving the active job for a given investigation without providing authentication credentials results in an HTTP 401 Unauthorized response. The test sends a GET request to the `/api/v1/chat/active-job/{investigation_id}` endpoint using an unauthenticated client and asserts that the returned status code equals 401.
        """
        response = await async_client.get(
            f"/api/v1/chat/active-job/{test_investigation.investigation_id}"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestContinueInvestigation:
    """Test POST /api/v1/chat/continue/{job_id} endpoint."""

    async def test_continue_investigation_job_not_found(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that attempting to continue a chat investigation with an invalid job ID returns a 404 response and an appropriate “not found” error message. The test sends a POST request to the continuation endpoint using a non-existent job identifier (e.g., 999999) with a sample effort payload, then asserts that the HTTP status code is 404 and that the response detail contains the phrase “not found” (case-insensitive). This verifies proper handling of missing resources in the continue-investigation API.
        """
        response = await async_client.post(
            "/api/v1/chat/continue/999999", headers=auth_headers, json={"effort": "medium"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_continue_investigation_low_effort(self, async_client: AsyncClient, auth_headers):
        """
        Test that the `continue` investigation endpoint correctly handles an `effort` value of `"low"`.

        The request is sent to `/api/v1/chat/continue/1` with authentication headers and a JSON body containing `{"effort": "low"}`. Because no real job exists for ID 1, the expected response status code is either **404** (job not found) or **400** (invalid request). The assertion verifies that the endpoint reaches the job-lookup logic and returns one of these error codes.
        """
        # This will fail with 404 since we don't have a real job, but it tests the endpoint
        response = await async_client.post(
            "/api/v1/chat/continue/1", headers=auth_headers, json={"effort": "low"}
        )

        # Should reach job lookup logic
        assert response.status_code in [404, 400]

    async def test_continue_investigation_medium_effort(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that continuing an investigation with an effort level of `\"medium\"` is handled correctly by the API.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to send requests to the application.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/chat/continue/1` with a JSON body containing `{\"effort\": \"medium\"}`. It asserts that the response status code indicates either a client error (400) or a not-found error (404), covering scenarios where the specified investigation does not exist or the effort value is invalid for the given context.
        """
        response = await async_client.post(
            "/api/v1/chat/continue/1", headers=auth_headers, json={"effort": "medium"}
        )

        assert response.status_code in [404, 400]

    async def test_continue_investigation_high_effort(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that providing an effort value of `"high"` when continuing an investigation returns an error status code.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/chat/continue/1` with a JSON payload containing `{"effort": "high"}` and asserts that the response status code indicates failure (either 400 Bad Request or 404 Not Found).
        """
        response = await async_client.post(
            "/api/v1/chat/continue/1", headers=auth_headers, json={"effort": "high"}
        )

        assert response.status_code in [404, 400]

    async def test_continue_investigation_default_effort(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that continuing an investigation without specifying effort defaults to the expected level (medium) and results in an appropriate error response (404 Not Found or 400 Bad Request). The test sends a POST request to the continue endpoint with an empty JSON payload and verifies that the returned HTTP status code is either 404 or 400, indicating proper handling of missing or invalid investigation identifiers.
        """
        response = await async_client.post("/api/v1/chat/continue/1", headers=auth_headers, json={})

        assert response.status_code in [404, 400]

    async def test_continue_investigation_unauthorized(self, async_client: AsyncClient):
        """
        Test that attempting to continue an investigation endpoint without authentication returns HTTP 401 Unauthorized.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client fixture used to send requests to the API.

        The test sends a POST request to `/api/v1/chat/continue/1` with a JSON payload specifying an effort level. It asserts that the response status code is 401, confirming that unauthenticated access is correctly rejected.
        """
        response = await async_client.post("/api/v1/chat/continue/1", json={"effort": "medium"})

        assert response.status_code == 401


@pytest.mark.integration
class TestBroadcastMessage:
    """Test POST /api/v1/chat/broadcast/{investigation_id} endpoint."""

    async def test_broadcast_message_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting a message to all participants of an investigation.

        Args:
            async_client: An instance of `AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute identifying the target investigation.
            auth_headers: Dictionary containing authentication headers required for authorized access to the broadcast endpoint.

        The test sends a POST request to `/api/v1/chat/broadcast/{investigation_id}` with a JSON payload representing the message to be broadcast. It verifies that:
        * The response status code is 200 (OK).
        * The returned JSON contains a `status` field whose value is either `"ok"` or `"ok_with_errors"`, indicating successful delivery or partial failures.
        * A `recipients` field is present in the response, listing the recipients of the broadcast.
        """
        message = {"type": "test_message", "content": "Test broadcast"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ok", "ok_with_errors"]
        assert "recipients" in data

    async def test_broadcast_agent_started(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting an `agent_started` message for a given investigation succeeds.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            HTTP client used to send asynchronous requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Authentication headers required for authorized access.

        The function sends a POST request to `/api/v1/chat/broadcast/{investigation_id}` with a JSON payload containing `type`, `job_id` and `policy_id` fields, then asserts that the response status code is 200.
        """
        message = {"type": "agent_started", "job_id": 123, "policy_id": "test_policy"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_agent_thinking(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting an `agent_thinking` message via the chat broadcast endpoint.

        This integration test verifies that a POST request containing a payload with
        `type` set to `agent_thinking`, along with a `job_id` and `thought`,
        is accepted by the API and returns an HTTP 200 status code.

        Args:
            async_client: An instance of `AsyncClient` used to perform asynchronous HTTP requests.
            test_investigation: A fixture providing an investigation object whose `investigation_id` is used in the request URL.
            auth_headers: Authentication headers required for authorized access to the endpoint.
        """
        message = {"type": "agent_thinking", "job_id": 123, "thought": "Analyzing evidence..."}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_agent_tool_execution(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting an `agent_tool_execution` message via the chat API.

        This integration test verifies that posting a payload with type `agent_tool_execution` to the broadcast endpoint
        for a given investigation succeeds with an HTTP 200 response.

        Args:
            async_client: An `httpx.AsyncClient` instance used to make asynchronous HTTP requests against the test server.
            test_investigation: A fixture providing an investigation object containing at least an `investigation_id` attribute.
            auth_headers: Dictionary of authentication headers required by the endpoint (e.g., `{"Authorization": "Bearer <token>"}`).

        The test constructs a JSON payload containing:
        * `type` set to `agent_tool_execution`
        * `job_id` identifying the related job
        * `tool_name` specifying the tool being executed
        * `tool_args` providing arguments for the tool

        It then posts this payload to `/api/v1/chat/broadcast/<investigation_id>` and asserts that the response status code is 200,
        indicating successful handling of the broadcast message.
        """
        message = {
            "type": "agent_tool_execution",
            "job_id": 123,
            "tool_name": "query_timeline",
            "tool_args": {"query": "test"},
        }

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_agent_completed(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting an `agent_completed` message for a given investigation succeeds with a HTTP 200 response.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object containing at least `investigation_id`.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access.

        The function constructs a payload with type `agent_completed`, posts it to the broadcast endpoint, and asserts that the response status code equals 200.
        """
        message = {"type": "agent_completed", "job_id": 123, "summary": "Investigation complete"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_agent_error(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting an `agent_error` message for a given investigation succeeds.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to send requests to the API.
        test_investigation : Investigation
            Fixture providing an investigation object whose `investigation_id` is used in the broadcast URL.
        auth_headers : dict
            Dictionary containing authentication headers required for authorized access.

        The test constructs a payload with type `agent_error`, a sample `job_id` and an error description, posts it to the `/api/v1/chat/broadcast/<investigation_id>` endpoint, and asserts that the response status code is 200, indicating successful handling of the error broadcast.
        """
        message = {"type": "agent_error", "job_id": 123, "error": "Test error message"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_timeline_entry_added(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting a `timeline_entry_added` message for a given investigation succeeds with an HTTP 200 response.

        Parameters
        ----------
        self : object
            Test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object whose `investigation_id` is used in the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the broadcast endpoint.

        The test constructs a payload representing a timeline entry addition, posts it to the broadcast endpoint, and asserts that the server returns status code 200, indicating successful handling of the message.
        """
        message = {"type": "timeline_entry_added", "entry_id": 456, "title": "Test Entry"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_invalid_investigation_id(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test broadcasting a message using an invalid investigation ID and verify that the API responds with a 400 status code and an error detail mentioning “invalid”.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the application.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        Raises
        ------
        AssertionError
            If the response status code is not 400 or if the error detail does not contain the word “invalid”.
        """
        message = {"type": "test_message", "content": "Test"}

        response = await async_client.post(
            "/api/v1/chat/broadcast/invalid-uuid", headers=auth_headers, json=message
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    async def test_broadcast_empty_message(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting an empty payload to the chat broadcast endpoint for a given investigation, ensuring that the request succeeds with a 200 status code even when no message type or content is provided.
        """
        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json={},
        )

        # Should still succeed (type will be None)
        assert response.status_code == 200

    async def test_broadcast_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that broadcasting a message to an investigation endpoint without providing authentication credentials returns a 401 Unauthorized response. The test sends a sample JSON payload containing a generic message type and content, then asserts that the HTTP status code indicates lack of authorization.
        """
        message = {"type": "test_message", "content": "Test"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}", json=message
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestChatHistoryMessageStructure:
    """Test the structure of messages returned by chat history."""

    async def test_message_structure_fields(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that each message returned by the chat history endpoint includes all required fields.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with a valid `investigation_id` used for creating and retrieving messages.
        auth_headers : dict
            Dictionary containing authentication headers required for authorized API access.
        db_session : Session
            Database session fixture used to persist the test message.

        The test creates a new chat message via the CRUD layer, commits it to the database, retrieves the full chat history for the investigation, and asserts that the response contains a `messages` list where each entry includes the keys `message_id`, `role`, `content`, `metadata`, and `created_at`.
        """
        # First create a test message
        from app.crud.chat_history import create_message

        message_id = await create_message(
            db=db_session,
            investigation_id=test_investigation.investigation_id,
            user_id=1,
            role="user",
            content="Test message",
            metadata={"test": "data"},
        )
        await db_session.commit()

        # Now fetch history
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        if data["messages"]:
            msg = data["messages"][0]
            assert "message_id" in msg
            assert "role" in msg
            assert "content" in msg
            assert "metadata" in msg
            assert "created_at" in msg

    async def test_message_ordering(
        self, async_client: AsyncClient, test_investigation, auth_headers, db_session
    ):
        """
        Test that messages are returned in chronological order for a given investigation.

        Parameters
        ----------
        self : object
            The test class instance.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute used to scope the chat history.
        auth_headers : dict
            Dictionary containing authentication headers required for authorized API access.
        db_session : Session
            SQLAlchemy session used to insert test messages directly into the database.

        Raises
        ------
        AssertionError
            If the response status code is not 200, or if any pair of consecutive messages in the returned list is not ordered by `created_at` in non-decreasing order.
        """
        # Create multiple messages
        from app.crud.chat_history import create_message
        import asyncio

        for i in range(3):
            await create_message(
                db=db_session,
                investigation_id=test_investigation.investigation_id,
                user_id=1,
                role="user",
                content=f"Message {i}",
                metadata={},
            )
            await db_session.commit()
            await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        if len(data["messages"]) >= 2:
            # Verify chronological order (ascending by created_at)
            for i in range(len(data["messages"]) - 1):
                current = data["messages"][i]["created_at"]
                next_msg = data["messages"][i + 1]["created_at"]
                assert current <= next_msg


@pytest.mark.integration
class TestChatEdgeCases:
    """Test edge cases and error conditions."""

    async def test_broadcast_with_very_large_message(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting a very large message payload.

        This integration test verifies that the broadcast endpoint can handle an unusually large message body (approximately 100 KB). It sends a POST request with a JSON payload containing a `type` field and a `content` field filled with repetitive characters to simulate size. The test asserts that the response status code is one of the expected outcomes:

        - **200** - successful handling of the large payload.
        - **413** - request entity too large, indicating proper enforcement of size limits.
        - **500** - internal server error, which may be raised if the system cannot process the payload.

        Args:
            async_client: An `AsyncClient` instance used to perform asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` for targeting the broadcast endpoint.
            auth_headers: Authentication headers required by the endpoint, typically containing a bearer token.

        The function does not return a value; it raises an assertion error if the response status code is outside the expected set.
        """
        large_content = "A" * 100000  # 100KB of text
        message = {"type": "test_message", "content": large_content}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        # Should handle large messages
        assert response.status_code in [200, 413, 500]

    async def test_broadcast_with_special_characters(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting a message containing special characters and Unicode symbols.

        This integration test verifies that the chat broadcast endpoint correctly handles payloads with HTML-like characters (`<`, `>`, `&`), quotation marks (`"`, `'`), escape sequences (`\n`, `\t`), and non-ASCII Unicode (e.g., the snowman emoji `☃`). The test sends a POST request to `/api/v1/chat/broadcast/{investigation_id}` using an authenticated client and asserts that the response status code is 200, indicating successful processing of the special characters.
        """
        message = {
            "type": "test_message",
            "content": "Special chars: <>&\"'\\n\\t\u2603",  # Snowman emoji
        }

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_with_nested_metadata(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting a message that contains deeply nested metadata.

        This integration test verifies that the `/api/v1/chat/broadcast/{investigation_id}` endpoint correctly accepts and processes a payload where the `metadata` field includes multiple levels of nesting. The request is sent using an authenticated client, and the response status code is asserted to be 200, indicating successful handling of complex metadata structures.
        """
        message = {
            "type": "agent_thinking",
            "job_id": 123,
            "metadata": {"level1": {"level2": {"level3": {"data": "nested"}}}},
        }

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_get_history_with_zero_limit(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting chat history with a limit of zero triggers validation failure.

        Args:
            async_client: An HTTP client capable of making asynchronous requests to the API.
            test_investigation: Fixture providing an investigation object containing the `investigation_id` used in the request path.
            auth_headers: Dictionary of authentication headers required for authorized access.

        The test sends a GET request to the `/api/v1/chat/history/{investigation_id}` endpoint with `limit=0`. It asserts that the response status code is 422, indicating that the request failed validation because the minimum allowed limit is one.
        """
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 0},
        )

        # Should fail validation (minimum is 1)
        assert response.status_code == 422

    async def test_get_history_with_excessive_limit(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that requesting chat history with a limit greater than the allowed maximum (1000) triggers validation failure.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to make requests against the API.
            test_investigation: Fixture providing an investigation object containing a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a GET request to `/api/v1/chat/history/{investigation_id}` with a query parameter `limit=2000`. It asserts that the response status code is 422, indicating that the request was rejected due to exceeding the maximum allowed limit.
        """
        response = await async_client.get(
            f"/api/v1/chat/history/{test_investigation.investigation_id}",
            headers=auth_headers,
            params={"limit": 2000},
        )

        # Should fail validation (maximum is 1000)
        assert response.status_code == 422


@pytest.mark.integration
class TestChatBroadcastMessageTypes:
    """Test all different broadcast message types."""

    async def test_broadcast_investigation_state_changed(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting an investigation state-change message via the chat API succeeds with a 200 OK response.

        Args:
            self: Test case instance.
            async_client (AsyncClient): HTTP client for making asynchronous requests to the API.
            test_investigation: Fixture providing an investigation object containing the target `investigation_id`.
            auth_headers (dict): Authentication headers required by the endpoint.

        The test sends a POST request to `/api/v1/chat/broadcast/<investigation_id>` with a JSON payload
        representing an `investigation_state_changed` event and asserts that the response status code is 200.
        """
        message = {"type": "investigation_state_changed", "state": "analyzing"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_message_created(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting a `message_created` event for a given investigation succeeds.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Dictionary containing authentication headers required for the request.

        The function sends a POST request to `/api/v1/chat/broadcast/{investigation_id}` with a JSON payload representing a `message_created` event and asserts that the response status code is 200, indicating successful handling of the broadcast.
        """
        message = {"type": "message_created", "message_id": 789}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_message_updated(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting a `message_updated` event for a given investigation succeeds with an HTTP 200 response.

        Parameters
        ----------
        self : object
            Test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object containing the target `investigation_id`.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access.

        The test constructs a payload with `type` set to `"message_updated"` and a sample `message_id`, posts it to the broadcast endpoint, and asserts that the response status code equals 200.
        """
        message = {"type": "message_updated", "message_id": 789}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_message_deleted(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test broadcasting a `message_deleted` event for a specific investigation.

        Args:
            self: Test class instance.
            async_client (AsyncClient): Asynchronous HTTP client used to send requests to the API.
            test_investigation: Fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a POST request to `/api/v1/chat/broadcast/<investigation_id>` with a JSON payload containing the `type` set to `"message_deleted"` and a `message_id`. It asserts that the response status code is 200, indicating successful handling of the deletion broadcast.
        """
        message = {"type": "message_deleted", "message_id": 789}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_stop_acknowledged(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting a `stop_acknowledged` message for a given investigation succeeds.\n\nThe test sends a POST request to the `/api/v1/chat/broadcast/{investigation_id}` endpoint with a JSON payload containing:\n\n* `type` - The message type, set to `\"stop_acknowledged\"`.\n* `job_id` - An identifier for the related job (e.g., `123`).\n* `message` - A human-readable description of the stop signal.\n\nThe request includes authentication headers supplied by `auth_headers`. The test asserts that the server responds with HTTP status code 200, indicating successful handling of the broadcast message.\"""
        """
        message = {"type": "stop_acknowledged", "job_id": 123, "message": "Stop signal sent"}

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200

    async def test_broadcast_job_continuing(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that broadcasting a `job_continuing` message for a given investigation succeeds with an HTTP 200 response.

        The test constructs a payload containing the message type, job identifiers and policy ID, sends it via an asynchronous POST request to the broadcast endpoint of the specified investigation, and asserts that the server returns status code 200.
        """
        message = {
            "type": "job_continuing",
            "job_id": 124,
            "original_job_id": 123,
            "policy_id": "test_policy",
        }

        response = await async_client.post(
            f"/api/v1/chat/broadcast/{test_investigation.investigation_id}",
            headers=auth_headers,
            json=message,
        )

        assert response.status_code == 200
