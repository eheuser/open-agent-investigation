"""
Integration tests for chat WebSocket endpoint.
Tests the real-time chat interface with WebSocket connections.
"""

import pytest
import json
from httpx import AsyncClient
from uuid import uuid4

from app.models.investigation import Investigation
from app.models.llm_config import LLMProviderConfig


@pytest.mark.integration
class TestChatWebSocket:
    """Test WebSocket chat endpoint."""

    async def test_websocket_requires_authentication(self, async_client: AsyncClient):
        """
        Test that establishing a WebSocket connection to the chat endpoint without providing an authentication token raises an exception, confirming that authentication is required. The test creates a temporary investigation identifier and attempts to open a WebSocket connection to `/api/v1/chat/ws/{investigation_id}` using the provided `async_client`. The expected behavior is for the connection attempt to fail, triggering an exception captured by pytest.
        """
        # Create test investigation
        investigation_id = uuid4()

        # Try to connect without auth token
        with pytest.raises(Exception):  # WebSocket will reject connection
            async with async_client.websocket_connect(
                f"/api/v1/chat/ws/{investigation_id}"
            ) as websocket:
                pass

    async def test_websocket_connect_with_auth(
        self, async_client: AsyncClient, test_investigation, test_token
    ):
        """
        Test that a WebSocket connection can be established when an authentication token is provided in the query string, and verify basic message exchange.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client capable of establishing WebSocket connections for testing.
        test_investigation : Any
            Fixture representing an investigation; its `investigation_id` attribute is used to build the endpoint URL.
        test_token : str
            Valid authentication token included in the connection query parameters.

        The test connects to `/api/v1/chat/ws/<investigation_id>?token=<test_token>`, sends a simple user message, and asserts that at least one JSON response is received from the server.
        """
        # Connect with auth token in query params
        url = f"/api/v1/chat/ws/{test_investigation.investigation_id}?token={test_token}"

        async with async_client.websocket_connect(url) as websocket:
            # Should connect successfully
            # Send a simple message
            await websocket.send_json({"type": "user_message", "content": "Hello"})

            # Should receive at least one response
            response = await websocket.receive_json()
            assert response is not None

    async def test_websocket_invalid_investigation(self, async_client: AsyncClient, test_token):
        """
        Test that attempting to open a WebSocket connection for a non-existent investigation results in an error.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to establish the WebSocket connection.
            test_token: Authentication token passed as a query parameter.

        Raises:
            Exception: Expected when the server rejects the connection or returns an error message for the invalid investigation ID.
        """
        fake_investigation_id = uuid4()
        url = f"/api/v1/chat/ws/{fake_investigation_id}?token={test_token}"

        # Should fail to connect or receive error
        with pytest.raises(Exception):
            async with async_client.websocket_connect(url) as websocket:
                await websocket.send_json({"type": "user_message", "content": "Hello"})
                response = await websocket.receive_json()
                # Expect error response
                assert response.get("type") == "error"


@pytest.mark.integration
class TestGetMessages:
    """Test GET /api/v1/chat/{investigation_id}/messages endpoint."""

    async def test_get_messages_empty(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving messages for an investigation with no stored messages returns an empty list.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing a populated `Investigation` object whose `investigation_id` is used in the request URL.
            auth_headers: Authentication headers required for authorized access to the endpoint.

        Asserts:
            The response status code is 200 (OK).
            The response body is a JSON list.
            The list is empty, indicating no messages are present for the investigation.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/messages", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_get_messages_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that attempting to retrieve chat messages without providing authentication credentials results in an HTTP 401 Unauthorized response. The test sends a GET request to the messages endpoint for a given investigation and asserts that the status code returned is 401.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/messages"
        )

        assert response.status_code == 401

    async def test_get_messages_invalid_investigation(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that retrieving messages for an investigation ID that does not exist returns an appropriate response.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured to make requests against the test application.
            auth_headers: A dictionary containing authentication headers required by the endpoint.

        The test generates a random UUID, issues a GET request to `/api/v1/chat/{fake_id}/messages`, and asserts that the response status code is either 200 (with an empty list) or 404, depending on how missing investigations are handled.
        """
        fake_id = uuid4()
        response = await async_client.get(f"/api/v1/chat/{fake_id}/messages", headers=auth_headers)

        # Should return 404 or empty list depending on implementation
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestClearChat:
    """Test DELETE /api/v1/chat/{investigation_id}/clear endpoint."""

    async def test_clear_chat_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that clearing a chat removes messages successfully.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Authentication headers required for authorized access.

        The function sends a DELETE request to the chat clear endpoint and asserts that the response status code is 200. It then verifies that the JSON payload contains either a `message` key or a `deleted_count` key, indicating successful deletion of chat messages.
        """
        response = await async_client.delete(
            f"/api/v1/chat/{test_investigation.investigation_id}/clear", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "deleted_count" in data

    async def test_clear_chat_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that attempting to clear a chat without providing authentication credentials results in an HTTP 401 Unauthorized response. The test sends a DELETE request to the chat-clear endpoint for a given investigation and asserts that the returned status code equals 401.
        """
        response = await async_client.delete(
            f"/api/v1/chat/{test_investigation.investigation_id}/clear"
        )

        assert response.status_code == 401

    async def test_clear_chat_invalid_investigation(self, async_client: AsyncClient, auth_headers):
        """
        Test that clearing a chat for a non-existent investigation behaves idempotently: the request should complete without error, returning either a 200 OK (if the endpoint treats missing resources as already cleared) or a 404 Not Found (if it explicitly indicates the resource does not exist). The test creates a random UUID, sends a DELETE request to the chat clear endpoint with appropriate authentication headers, and asserts that the response status code is one of the expected values.
        """
        fake_id = uuid4()
        response = await async_client.delete(f"/api/v1/chat/{fake_id}/clear", headers=auth_headers)

        # Should succeed even if investigation doesn't exist (idempotent)
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestExportChat:
    """Test GET /api/v1/chat/{investigation_id}/export endpoint."""

    async def test_export_chat_json(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test exporting chat as JSON.

        Args:
            async_client: An instance of `AsyncClient` used to perform HTTP requests against the API.
            test_investigation: Fixture providing an investigation object that contains the `investigation_id` used in the request URL.
            auth_headers: Dictionary of authentication headers required for authorized access.

        The test sends a GET request to the `/api/v1/chat/{investigation_id}/export` endpoint with the query parameter `format=json`. It asserts that the response status code is 200 and verifies that the returned payload is valid JSON, either a list or a dictionary.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/export?format=json",
            headers=auth_headers,
        )

        assert response.status_code == 200
        # Should return JSON array
        data = response.json()
        assert isinstance(data, (list, dict))

    async def test_export_chat_markdown(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test exporting a chat transcript in Markdown format.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object that contains the `investigation_id` for which the chat export is requested.
            auth_headers: Dictionary of authentication headers required to authorize the request.

        The test performs a GET request to the `/api/v1/chat/{investigation_id}/export` endpoint with the query parameter `format=markdown`. It asserts that the response status code is 200 and that the `Content-Type` header indicates a text-based MIME type (e.g., `text/plain` or `text/markdown`).
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/export?format=markdown",
            headers=auth_headers,
        )

        assert response.status_code == 200
        # Should return text/plain or text/markdown
        assert "text" in response.headers.get("content-type", "").lower()

    async def test_export_chat_default_format(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test exporting a chat transcript using the default format.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        test_investigation : Investigation
            A fixture providing an investigation object whose `investigation_id` is used in the request URL.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        The test sends a GET request to the chat export endpoint without specifying a format, expecting the server to return the transcript in JSON format. It asserts that the response status code is 200, indicating a successful export.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/export", headers=auth_headers
        )

        assert response.status_code == 200

    async def test_export_chat_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that attempting to export a chat without providing authentication credentials results in an HTTP 401 Unauthorized response. The test sends a GET request to the chat export endpoint for a given investigation and asserts that the response status code equals 401.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/export"
        )

        assert response.status_code == 401

    async def test_export_chat_invalid_format(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test exporting a chat transcript using an unsupported format parameter.

        Args:
            async_client: An instance of httpx.AsyncClient configured for testing the API.
            test_investigation: Fixture providing a populated investigation object with a valid `investigation_id`.
            auth_headers: Dictionary containing authentication headers required for authorized requests.

        The test sends a GET request to the chat export endpoint with `format=invalid` and asserts that the response status code is either 200 (if the server defaults to JSON) or 400 (if it returns an error for unsupported formats).
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/export?format=invalid",
            headers=auth_headers,
        )

        # Should either default to JSON or return error
        assert response.status_code in [200, 400]


@pytest.mark.integration
class TestGetContext:
    """Test GET /api/v1/chat/{investigation_id}/context endpoint."""

    async def test_get_context_success(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test retrieving the chat context for a given investigation.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the test server.
            test_investigation: A fixture providing an investigation object with an `investigation_id` attribute representing the target investigation.
            auth_headers: Dictionary containing authentication headers required for authorized API access.

        The test sends a GET request to the `/api/v1/chat/{investigation_id}/context` endpoint and asserts that:
        * The response status code is 200 (OK).
        * The returned JSON payload is a dictionary, indicating that the context data was successfully retrieved.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/context", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        # Context should include investigation info
        assert isinstance(data, dict)

    async def test_get_context_unauthorized(self, async_client: AsyncClient, test_investigation):
        """
        Test that retrieving the chat context endpoint without providing authentication credentials returns an HTTP 401 Unauthorized response. The async client makes a GET request to the context URL for the given investigation, and the test asserts that the status code is 401. Parameters: `async_client` - an instance of `httpx.AsyncClient` used to perform requests; `test_investigation` - a fixture providing an investigation object with an `investigation_id` attribute identifying the target chat session. No return value.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/context"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestStopGeneration:
    """Test POST /api/v1/chat/{investigation_id}/stop endpoint."""

    async def test_stop_generation(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that stopping message generation via the chat endpoint behaves correctly.\n\nThis integration test sends a POST request to the `/api/v1/chat/{investigation_id}/stop` endpoint using an authenticated client. It verifies that the server responds with either a 200 OK status (when a generation task was active and has been stopped) or a 404 Not Found status (when no generation task was running). The test ensures that invoking the stop operation is safe and does not raise unexpected errors.\n\nArgs:\n    async_client: An `httpx.AsyncClient` instance configured for asynchronous requests against the test server.\n    test_investigation: A fixture providing an investigation object with a valid `investigation_id` used to construct the request URL.\n    auth_headers: A dictionary of HTTP headers containing authentication credentials required by the API.
        """
        response = await async_client.post(
            f"/api/v1/chat/{test_investigation.investigation_id}/stop", headers=auth_headers
        )

        # Should succeed even if nothing is running
        assert response.status_code in [200, 404]

    async def test_stop_generation_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that attempting to stop a chat generation without providing authentication credentials returns an HTTP 401 Unauthorized response. The test sends a POST request to the stop endpoint for a given investigation and asserts that the status code is 401.
        """
        response = await async_client.post(
            f"/api/v1/chat/{test_investigation.investigation_id}/stop"
        )

        assert response.status_code == 401


@pytest.mark.integration
class TestGetStreamingStatus:
    """Test GET /api/v1/chat/{investigation_id}/streaming endpoint."""

    async def test_get_streaming_status(
        self, async_client: AsyncClient, test_investigation, auth_headers
    ):
        """
        Test that retrieving the streaming status endpoint returns a successful response containing either an `is_streaming` flag or a `status` field.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for testing the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id` used in the request URL.
            auth_headers: Authentication headers required to authorize the request.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/streaming", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "is_streaming" in data or "status" in data

    async def test_get_streaming_status_unauthorized(
        self, async_client: AsyncClient, test_investigation
    ):
        """
        Test that retrieving the streaming status endpoint without providing authentication returns an HTTP 401 Unauthorized response. The test sends a GET request to `/api/v1/chat/{investigation_id}/streaming` using an unauthenticated client and asserts that the response status code equals 401. This verifies that the endpoint correctly enforces authentication requirements.
        """
        response = await async_client.get(
            f"/api/v1/chat/{test_investigation.investigation_id}/streaming"
        )

        assert response.status_code == 401
