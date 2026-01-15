"""
Integration tests for chat messages router.
Tests message CRUD operations, tool executions, and WebSocket notifications.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime


@pytest.mark.integration
class TestChatMessagesRouter:
    """Test chat message endpoints."""

    async def test_create_message_success(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test creating a new chat message successfully.

        This integration test sends a POST request to the `/api/v1/chat/messages/{investigation_id}` endpoint with a well-formed payload representing a user question. It verifies that:

        * The response status code is 200 (OK).
        * The returned JSON contains the same `role`, `message_type` and `content` values as submitted.
        * The `investigation_id` in the response matches the ID of the provided `test_investigation` fixture.
        * The payload includes automatically generated fields such as `message_id` and `created_at`.

        Args:
            async_client: An `httpx.AsyncClient` instance configured for testing the API.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id`.
            auth_headers: Authentication headers required to authorize the request.
        """
        response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "user",
                "message_type": "question",
                "content": "What happened on this system?",
                "metadata": {"intent": "general_inquiry"},
                "include_in_llm_context": True,
                "visible_in_ui": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "user"
        assert data["message_type"] == "question"
        assert data["content"] == "What happened on this system?"
        assert data["investigation_id"] == str(test_investigation.investigation_id)
        assert "message_id" in data
        assert "created_at" in data

    async def test_create_message_assistant_response(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test creating an assistant message via the chat messages API.

        Args:
            async_client: An httpx.AsyncClient instance used to send requests to the API.
            test_investigation: Fixture providing an investigation object with an `investigation_id` attribute.
            auth_headers: Dictionary containing authentication headers required by the endpoint.

        The test sends a POST request to create an assistant message with specific fields (role, message_type, content, metadata, include_in_llm_context, visible_in_ui) and asserts that:
        * The response status code is 200.
        * The returned JSON contains the expected role and message_type.
        * The content includes the phrase "suspicious activity".
        """
        response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "assistant",
                "message_type": "agent_message",
                "content": "Based on the timeline, I found suspicious activity.",
                "metadata": {"confidence": 0.85},
                "include_in_llm_context": True,
                "visible_in_ui": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "assistant"
        assert data["message_type"] == "agent_message"
        assert "suspicious activity" in data["content"]

    async def test_create_message_invalid_investigation(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that creating a chat message with an improperly formatted investigation identifier results in a 400 Bad Request response and includes an error detail indicating the invalid ID format. The request is sent to the `/api/v1/chat/messages/invalid-uuid` endpoint with a sample payload, using provided authentication headers. Assertions verify both the HTTP status code and the presence of the expected validation message in the JSON response.
        """
        response = await async_client.post(
            "/api/v1/chat/messages/invalid-uuid",
            json={
                "role": "user",
                "message_type": "question",
                "content": "Test message",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid investigation ID format" in response.json()["detail"]

    async def test_create_message_with_parent(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test creating a threaded chat message that references an existing parent message.

        Args:
            self: Test case instance.
            async_client (AsyncClient): HTTP client for making asynchronous API requests.
            test_investigation: Fixture providing an investigation context with a valid `investigation_id`.
            auth_headers (dict): Authorization headers required for the request.

        The test performs the following steps:
        1. Sends a POST request to create a parent message of type `question` under the given investigation.
        2. Extracts the `message_id` of the created parent message from the response.
        3. Sends a second POST request to create a child message of type `agent_message`, including the `parent_message_id` obtained in step 2.
        4. Asserts that the response status code is `200` and that the returned payload contains the correct `parent_message_id` linking the child to its parent.
        """
        # Create parent message
        parent_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "user",
                "message_type": "question",
                "content": "Parent message",
            },
            headers=auth_headers,
        )
        parent_id = parent_response.json()["message_id"]

        # Create child message
        response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "assistant",
                "message_type": "agent_message",
                "content": "Child message",
                "parent_message_id": parent_id,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parent_message_id"] == parent_id

    async def test_get_messages_empty(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that retrieving messages for an investigation with no stored chat entries returns a successful response containing an empty message list, a total count of zero, and includes the `parsing_locked` flag in the payload.

        Parameters
        ----------
        self : object
            Test case instance.
        async_client : AsyncClient
            HTTP client fixture used to perform asynchronous requests against the API.
        test_investigation : Any
            Fixture providing an investigation object with a valid `investigation_id` but no associated messages.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        Raises
        ------
        AssertionError
            If the response status code is not 200, if the `messages` list is not empty, if the `total` count is not zero, or if the `parsing_locked` key is missing from the JSON payload.
        """
        response = await async_client.get(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["messages"] == []
        assert data["total"] == 0
        assert "parsing_locked" in data

    async def test_get_messages_with_data(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that retrieving chat messages for an investigation returns the correct data set.

        The test performs the following steps:
        1. Creates three chat messages associated with `test_investigation.investigation_id` using a POST request.
           - The role alternates between `user` and `assistant`.
           - All messages have `message_type` set to `question`.
        2. Retrieves the list of messages for the same investigation via a GET request.
        3. Asserts that:
           - The HTTP response status code is 200 (OK).
           - Exactly three messages are returned.
           - The `total` field reflects the correct count (3).
           - Messages are ordered chronologically, i.e., the first message's content is `Message 1` and the last is `Message 3`.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for the application under test.
            test_investigation: A fixture providing an investigation object with a valid `investigation_id`.
            auth_headers: Authentication headers required by the API endpoints.
        """
        # Create multiple messages
        for i in range(3):
            await async_client.post(
                f"/api/v1/chat/messages/{test_investigation.investigation_id}",
                json={
                    "role": "user" if i % 2 == 0 else "assistant",
                    "message_type": "question",
                    "content": f"Message {i + 1}",
                },
                headers=auth_headers,
            )

        # Get messages
        response = await async_client.get(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 3
        assert data["total"] == 3
        # Check chronological order
        assert data["messages"][0]["content"] == "Message 1"
        assert data["messages"][2]["content"] == "Message 3"

    async def test_get_messages_pagination(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test pagination of chat messages for a given investigation.

        Parameters
        ----------
        self : object
            Test class instance.
        async_client : AsyncClient
            HTTP client used to make asynchronous requests against the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Dictionary containing authentication headers required for the requests.

        The test creates five user messages associated with the specified investigation, then retrieves them in two pages using `limit` and `offset` query parameters. It asserts that each page returns a 200 status code, contains the expected number of messages, and that the message contents are ordered correctly (Message 1-2 on the first page, Message 3-4 on the second).
        """
        # Create 5 messages
        for i in range(5):
            await async_client.post(
                f"/api/v1/chat/messages/{test_investigation.investigation_id}",
                json={
                    "role": "user",
                    "message_type": "question",
                    "content": f"Message {i + 1}",
                },
                headers=auth_headers,
            )

        # Get first page (limit 2)
        response = await async_client.get(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}?limit=2&offset=0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["content"] == "Message 1"

        # Get second page
        response = await async_client.get(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}?limit=2&offset=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["content"] == "Message 3"

    async def test_get_messages_invalid_investigation(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that retrieving chat messages with an invalid investigation identifier returns a 400 Bad Request response.

        Parameters
        ----------
        self : object
            Test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to make requests against the API.
        auth_headers : dict
            Dictionary containing authentication headers required for authorized access.
        """
        response = await async_client.get(
            "/api/v1/chat/messages/invalid-uuid",
            headers=auth_headers,
        )

        assert response.status_code == 400

    async def test_get_single_message_success(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test retrieving a single chat message by its identifier and verifying the response.

        This integration test performs the following actions:

        1. **Create a new message** associated with a given investigation using a POST request to
           `/api/v1/chat/messages/{investigation_id}`. The payload includes:
           - `role`: set to `"user"`
           - `message_type`: set to `"question"`
           - `content`: the string `"Test message"`
        2. Extract the generated `message_id` from the creation response.
        3. **Retrieve the created message** with a GET request to
           `/api/v1/chat/messages/single/{message_id}`.
        4. Assert that:
           - The HTTP status code is `200` (OK).
           - The returned JSON contains the same `message_id` as created.
           - The `content` field matches the original message text (`"Test message"`).

        Parameters
        ----------
        self : object
            Instance of the test class containing shared fixtures and configuration.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests against the API under test.
        test_investigation : Any
            Fixture providing an investigation context, exposing `investigation_id` used in the endpoint URL.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access to the API.

        Raises
        ------
        AssertionError
            If any of the assertions about status code, message ID, or content fail.
        """
        # Create message
        create_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "user",
                "message_type": "question",
                "content": "Test message",
            },
            headers=auth_headers,
        )
        message_id = create_response.json()["message_id"]

        # Get message
        response = await async_client.get(
            f"/api/v1/chat/messages/single/{message_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message_id"] == message_id
        assert data["content"] == "Test message"

    async def test_get_single_message_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that retrieving a message with an ID that does not exist returns a 404 Not Found response. The request is sent to the `/api/v1/chat/messages/single/<id>` endpoint using an authenticated client, and the test asserts that the HTTP status code of the response equals 404.
        """
        response = await async_client.get(
            "/api/v1/chat/messages/single/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_message_content(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test updating the content of an existing chat message.\n\nThe test performs the following actions:\n1. Creates a new message for the given investigation using a POST request to `/api/v1/chat/messages/{investigation_id}` with role `user` and type `question`.\n2. Extracts the generated `message_id` from the creation response.\n3. Sends a PATCH request to `/api/v1/chat/messages/{message_id}` with a new `content` value.\n4. Asserts that the patch operation returns HTTP 200 and that the response payload reflects the updated content.\"""
        """
        # Create message
        create_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "user",
                "message_type": "question",
                "content": "Original content",
            },
            headers=auth_headers,
        )
        message_id = create_response.json()["message_id"]

        # Update message
        response = await async_client.patch(
            f"/api/v1/chat/messages/{message_id}",
            json={
                "content": "Updated content",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated content"

    async def test_update_message_metadata(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test updating the metadata of an existing chat message.

        This integration test verifies that:
        - A new message can be created for a given investigation.
        - The message's `metadata` field can be updated via a PATCH request.
        - The API responds with HTTP 200 and includes the newly added metadata key.

        Args:
            self: Test class instance.
            async_client (AsyncClient): Asynchronous HTTP client used to make requests against the API.
            test_investigation: Fixture providing an investigation object with an `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized API access.
        """
        # Create message
        create_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "user",
                "message_type": "question",
                "content": "Test",
                "metadata": {"key1": "value1"},
            },
            headers=auth_headers,
        )
        message_id = create_response.json()["message_id"]

        # Update metadata
        response = await async_client.patch(
            f"/api/v1/chat/messages/{message_id}",
            json={
                "metadata": {"key1": "value1", "key2": "value2"},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["key2"] == "value2"

    async def test_soft_delete_message(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that a chat message can be soft-deleted via the PATCH endpoint.

        The test performs the following steps:
        1. Creates a new user-role question message for the given investigation.
        2. Sends a PATCH request to set the `deleted_at` timestamp on the created message.
        3. Asserts that the response status code is 200 (OK).
        4. Verifies that the returned payload contains a non-null `deleted_at` field, confirming the soft delete was applied.
        """
        # Create message
        create_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "user",
                "message_type": "question",
                "content": "To be deleted",
            },
            headers=auth_headers,
        )
        message_id = create_response.json()["message_id"]

        # Soft delete
        response = await async_client.patch(
            f"/api/v1/chat/messages/{message_id}",
            json={
                "deleted_at": datetime.utcnow().isoformat(),
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_at"] is not None

    async def test_update_message_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that updating a message with an ID that does not exist returns HTTP 404. The request patches `/api/v1/chat/messages/999999` with new content and uses the provided authentication headers; the response status code is asserted to be 404.
        """
        response = await async_client.patch(
            "/api/v1/chat/messages/999999",
            json={"content": "Updated"},
            headers=auth_headers,
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestToolExecutions:
    """Test tool execution endpoints."""

    async def test_create_tool_execution(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test creating a tool execution for a chat message.

        This integration test verifies that:
        * A parent chat message of type `tool_execution` can be created.
        * A subsequent POST to the `/tool-executions` endpoint creates a new tool execution linked to the parent message.
        * The response contains the expected fields and values, including:
          - `tool_name` matching the request payload.
          - `display_name` matching the request payload.
          - `status` set to `executing`.
          - `execution_number` reflecting the supplied number.
          - An `execution_id` generated by the server.

        Args:
            self: Test class instance (provided by the test framework).
            async_client (AsyncClient): Asynchronous HTTP client used to issue requests against the API.
            test_investigation: Fixture providing an investigation context with a valid `investigation_id`.
            auth_headers (dict): Authentication headers required for authorized API access.

        Raises:
            AssertionError: If any of the response status code checks or field validations fail.
        """
        # Create parent message
        msg_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "assistant",
                "message_type": "tool_execution",
                "content": None,
            },
            headers=auth_headers,
        )
        message_id = msg_response.json()["message_id"]

        # Create tool execution
        response = await async_client.post(
            f"/api/v1/chat/messages/{message_id}/tool-executions",
            json={
                "tool_name": "search_timeline",
                "display_name": "Search Timeline",
                "arguments": {"query": "suspicious activity"},
                "execution_number": 1,
                "max_tools": 5,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tool_name"] == "search_timeline"
        assert data["display_name"] == "Search Timeline"
        assert data["status"] == "executing"
        assert data["execution_number"] == 1
        assert "execution_id" in data

    async def test_create_tool_execution_message_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that creating a tool execution for a non-existent chat message returns a 404 response.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client used to send requests to the API.
            auth_headers: Authentication headers required for authorized access.
        """
        response = await async_client.post(
            "/api/v1/chat/messages/999999/tool-executions",
            json={
                "tool_name": "test_tool",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_tool_execution(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test updating a tool execution by first creating a chat message of type `tool_execution`, adding a tool execution to that message, and then patching the execution with result data.\n\nThe test performs the following steps:\n\n1. Sends a **POST** request to create a new assistant message for the given investigation.\n2. Extracts the generated `message_id` from the response.\n3. Sends a **POST** request to create a tool execution linked to the newly created message, specifying the tool name and arguments.\n4. Retrieves the `execution_id` of the created tool execution.\n5. Sends a **PATCH** request to update the tool execution with a result payload, a summary string, and a status of `completed`.\n6. Asserts that the response has HTTP status 200 and validates that the returned JSON contains the expected `status`, `result_summary`, and a `finished_at` timestamp field.\n\nParameters\n----------\nself: object\n    The test case instance (provided by the testing framework).\nasync_client: AsyncClient\n    An asynchronous HTTP client fixture used to make API requests.\ntest_investigation: Any\n    Fixture providing an investigation context, exposing `investigation_id`.\nauth_headers: dict\n    Authentication headers required for authorized API access.\n\nRaises\n------\nAssertionError\n    If any of the response validations fail (status code, fields, or values).\n\nReturns\n-------\nNone\n    The function asserts internally and does not return a value.
        """
        # Create message and tool execution
        msg_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "assistant",
                "message_type": "tool_execution",
            },
            headers=auth_headers,
        )
        message_id = msg_response.json()["message_id"]

        tool_response = await async_client.post(
            f"/api/v1/chat/messages/{message_id}/tool-executions",
            json={
                "tool_name": "search_timeline",
                "arguments": {"query": "test"},
            },
            headers=auth_headers,
        )
        execution_id = tool_response.json()["execution_id"]

        # Update with results
        response = await async_client.patch(
            f"/api/v1/chat/tool-executions/{execution_id}",
            json={
                "result": {"events": [{"id": 1, "description": "Event 1"}]},
                "result_summary": "Found 1 event",
                "status": "completed",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result_summary"] == "Found 1 event"
        assert "finished_at" in data

    async def test_update_tool_execution_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that updating a tool execution with an ID that does not exist returns a 404 response.

        Args:
            self: Test case instance.
            async_client (AsyncClient): HTTP client used to send asynchronous requests to the API.
            auth_headers (dict): Authentication headers required for authorized access.

        The test sends a PATCH request to update the status of a non-existent tool execution (ID 999999) and asserts that the response status code is 404, indicating that the resource was not found.
        """
        response = await async_client.patch(
            "/api/v1/chat/tool-executions/999999",
            json={
                "status": "completed",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_message_tool_executions(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test retrieving all tool execution records associated with a specific chat message.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client used to interact with the API endpoints.
            test_investigation: Fixture providing an investigation object containing the `investigation_id` required for constructing request URLs.
            auth_headers (dict): Authentication headers to be included in each request.

        The test performs the following steps:
        1. Creates a new chat message of type `tool_execution` within the given investigation.
        2. Posts three distinct tool execution entries linked to the created message, varying the `tool_name`, `execution_number`, and `max_tools` fields.
        3. Sends a GET request to retrieve all tool executions for that message.

        Asserts:
        - The response status code is 200 (OK).
        - Exactly three tool execution objects are returned.
        - The first returned execution has a `tool_name` equal to `"tool_0"`.

        No value is returned; the function raises an assertion error if any of the conditions fail.
        """
        # Create message
        msg_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "assistant",
                "message_type": "tool_execution",
            },
            headers=auth_headers,
        )
        message_id = msg_response.json()["message_id"]

        # Create multiple tool executions
        for i in range(3):
            await async_client.post(
                f"/api/v1/chat/messages/{message_id}/tool-executions",
                json={
                    "tool_name": f"tool_{i}",
                    "execution_number": i + 1,
                    "max_tools": 3,
                },
                headers=auth_headers,
            )

        # Get all executions
        response = await async_client.get(
            f"/api/v1/chat/messages/{message_id}/tool-executions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tool_executions"]) == 3
        assert data["tool_executions"][0]["tool_name"] == "tool_0"

    async def test_get_messages_with_tool_executions(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that retrieving messages for an investigation can include associated tool execution details.

        The test performs the following steps:
        1. Creates a new assistant-type message with `message_type` set to `tool_execution` for the given investigation.
        2. Posts a tool execution linked to the created message, specifying a `tool_name` and `display_name`.
        3. Requests the list of messages for the investigation using the query parameter `include_tool_executions=true`.
        4. Verifies that the response has a 200 status code.
        5. Asserts that exactly one message is returned.
        6. Confirms that the returned message contains exactly one tool execution entry.
        7. Checks that the `tool_name` of the included tool execution matches the expected value (`search_timeline`).
        """
        # Create message
        msg_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "assistant",
                "message_type": "tool_execution",
            },
            headers=auth_headers,
        )
        message_id = msg_response.json()["message_id"]

        # Create tool execution
        await async_client.post(
            f"/api/v1/chat/messages/{message_id}/tool-executions",
            json={
                "tool_name": "search_timeline",
                "display_name": "Search Timeline",
            },
            headers=auth_headers,
        )

        # Get messages with tool executions
        response = await async_client.get(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}?include_tool_executions=true",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1
        assert len(data["messages"][0]["tool_executions"]) == 1
        assert data["messages"][0]["tool_executions"][0]["tool_name"] == "search_timeline"

    async def test_get_messages_without_tool_executions(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that retrieving messages for an investigation with the query parameter `include_tool_executions=false` omits any associated tool execution data.\n\nThe test performs the following steps:\n1. Creates a new chat message of type `tool_execution` for the given `test_investigation`.\n2. Posts a tool execution linked to the newly created message.\n3. Sends a GET request to fetch all messages for the investigation while explicitly requesting that tool executions not be included.\n4. Asserts that the response is successful (HTTP 200) and verifies that the `tool_executions` field of the returned message is either `None` or an empty list, confirming that tool execution details are correctly excluded when requested.\n\nParameters\n----------\nself : object\n    The test case instance.\nasync_client : AsyncClient\n    An asynchronous HTTP client fixture used to make API calls against the application.\ntest_investigation : Any\n    Fixture providing a pre-created investigation object with an `investigation_id` attribute.\nauth_headers : dict\n    Dictionary of authentication headers required for authorized API access.\"""
        """
        # Create message
        msg_response = await async_client.post(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}",
            json={
                "role": "assistant",
                "message_type": "tool_execution",
            },
            headers=auth_headers,
        )
        message_id = msg_response.json()["message_id"]

        # Create tool execution
        await async_client.post(
            f"/api/v1/chat/messages/{message_id}/tool-executions",
            json={"tool_name": "test_tool"},
            headers=auth_headers,
        )

        # Get messages without tool executions
        response = await async_client.get(
            f"/api/v1/chat/messages/{test_investigation.investigation_id}?include_tool_executions=false",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Tool executions should still be None/empty when not included
        assert (
            data["messages"][0].get("tool_executions") is None
            or data["messages"][0].get("tool_executions") == []
        )


@pytest.mark.integration
class TestInvestigationState:
    """Test investigation state broadcast endpoint."""

    async def test_update_investigation_state_running(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that updating an investigation's state to "running" triggers a successful broadcast via the API.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the application.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Dictionary containing authentication headers required for the request.

        The function sends a POST request to the `/api/v1/chat/investigation-state/{investigation_id}` endpoint with a JSON payload setting the state to `running`. It asserts that the response status code is 200 and that the returned JSON contains a `status` field equal to `"ok"`.
        """
        response = await async_client.post(
            f"/api/v1/chat/investigation-state/{test_investigation.investigation_id}",
            json={"state": "running"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_update_investigation_state_completed(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that updating an investigation's state to `completed` via the chat API triggers a successful broadcast.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client fixture used to send requests to the application.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Authentication headers required for authorized API access.

        Raises
        ------
        AssertionError
            If the response status code is not 200, indicating that the state update was not accepted.
        """
        response = await async_client.post(
            f"/api/v1/chat/investigation-state/{test_investigation.investigation_id}",
            json={"state": "completed"},
            headers=auth_headers,
        )

        assert response.status_code == 200

    async def test_update_investigation_state_invalid(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that broadcasting an invalid investigation state via the chat API returns a 400 error with an appropriate detail message.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object containing the `investigation_id` used in the request URL.
        auth_headers : dict
            Dictionary of authentication headers required for authorized access to the endpoint.

        The test posts a payload with an invalid `state` value and asserts that the response status code is 400 and that the error detail contains the phrase "Invalid state".
        """
        response = await async_client.post(
            f"/api/v1/chat/investigation-state/{test_investigation.investigation_id}",
            json={"state": "invalid_state"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid state" in response.json()["detail"]
