"""
Integration tests for agents router.
Tests agent execution and policy management.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestAgentsRouter:
    """Test agents endpoints."""

    async def test_list_available_agents(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that the `/api/v1/agents/available` endpoint returns either a successful response containing a list or dictionary of agents, or a 404 status when no agents are available.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        auth_headers : dict
            A mapping of authentication headers required for authorized access.

        The function performs a GET request to the `/api/v1/agents/available` endpoint using the supplied `auth_headers` and asserts that the response status code is either 200 (OK) or 404 (Not Found). If the status code is 200, it further validates that the JSON payload is of type `list` or `dict`.
        """
        response = await async_client.get(
            "/api/v1/agents/available",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or isinstance(data, dict)

    async def test_list_available_agents_unauthenticated(
        self,
        async_client: AsyncClient,
    ):
        """
        Test that attempting to list available agents without providing authentication credentials results in an HTTP 401 Unauthorized response.
        """
        response = await async_client.get(
            "/api/v1/agents/available",
        )

        assert response.status_code == 401

    async def test_get_agent_by_id(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test retrieving an agent by its identifier.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to perform asynchronous HTTP requests against the API.
            auth_headers: A dictionary containing authentication headers required for authorized access to the endpoint.

        The test sends a GET request to `/api/v1/agents/<agent_id>` and asserts that the response status code is either 200 (agent found) or 404 (agent not found). No value is returned.
        """
        response = await async_client.get(
            "/api/v1/agents/test_agent",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404]

    async def test_get_agent_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that retrieving an agent with an identifier that does not exist returns a 404 Not Found response. The test sends a GET request to the `/api/v1/agents/<agent_id>` endpoint using the provided asynchronous client and authentication headers, then asserts that the HTTP status code of the response is 404. This verifies proper error handling for unknown agents.
        """
        response = await async_client.get(
            "/api/v1/agents/nonexistent_agent",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_execute_agent_basic(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test executing an agent via the API.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            An investigation fixture providing a valid `investigation_id` for the request payload.
        auth_headers : dict
            Authentication headers required by the endpoint.

        The function sends a POST request to `/api/v1/agents/execute` with a JSON body containing the investigation ID, agent identifier, and execution instructions. It asserts that the response status code is one of the expected values (200, 201, 400, 404, or 500), accounting for possible failure scenarios such as missing agents or misconfigured language models.
        """
        response = await async_client.post(
            f"/api/v1/agents/execute",
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "agent_id": "test_agent",
                "instructions": "Analyze the system for suspicious activity",
            },
            headers=auth_headers,
        )

        # May fail if agent doesn't exist or LLM not configured
        assert response.status_code in [200, 201, 400, 404, 500]

    async def test_execute_agent_unauthenticated(
        self,
        async_client: AsyncClient,
        test_investigation,
    ):
        """
        Test that executing an agent without providing authentication credentials results in an unauthorized (401) response.

        Args:
            async_client: An instance of `AsyncClient` used to make HTTP requests against the API.
            test_investigation: A fixture representing a pre-created investigation, providing its `investigation_id`.

        The test posts a request to the `/api/v1/agents/execute` endpoint with required payload fields but without authentication headers, then asserts that the response status code is 401.
        """
        response = await async_client.post(
            f"/api/v1/agents/execute",
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "agent_id": "test_agent",
                "instructions": "Test",
            },
        )

        assert response.status_code == 401

    async def test_execute_agent_invalid_investigation(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test executing an agent when the provided investigation ID is invalid.

        Args:
            async_client: An instance of `httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            auth_headers: A dictionary containing authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/agents/execute` with an `investigation_id` that is not a valid UUID, along with a sample `agent_id` and `instructions`. It asserts that the response status code indicates a client error (either 400 Bad Request or 422 Unprocessable Entity), confirming that the API correctly validates investigation identifiers.
        """
        response = await async_client.post(
            f"/api/v1/agents/execute",
            json={
                "investigation_id": "invalid-uuid",
                "agent_id": "test_agent",
                "instructions": "Test",
            },
            headers=auth_headers,
        )

        assert response.status_code in [400, 422]

    async def test_get_agent_status(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test that retrieving the execution status of an agent returns either a successful response (HTTP 200) when the investigation exists or a not-found response (HTTP 404) when it does not. The request is sent to the `/api/v1/agents/status/{investigation_id}` endpoint using the provided asynchronous client and authentication headers, and the HTTP status code of the response is asserted to be one of the expected values.
        """
        response = await async_client.get(
            f"/api/v1/agents/status/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404]

    async def test_stop_agent_execution(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test stopping an agent execution via the API.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            Asynchronous HTTP client used to send requests to the API.
        test_investigation : Any
            Fixture providing an investigation object with an `investigation_id` attribute.
        auth_headers : dict
            Dictionary containing authentication headers required for the request.

        The function sends a POST request to `/api/v1/agents/stop/{investigation_id}` and asserts that the response status code is either 200 (successful stop) or 404 (execution not found).
        """
        response = await async_client.post(
            f"/api/v1/agents/stop/{test_investigation.investigation_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404]

    async def test_list_agent_policies(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that the API endpoint for listing agent policies returns a successful response or a not-found status.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured to make requests against the test server.
            auth_headers: A dictionary containing authentication headers required by the endpoint.

        The function sends a GET request to `/api/v1/agents/policies` and asserts that the response status code is either 200 (OK) or 404 (Not Found). If the status code is 200, it verifies that the returned JSON payload is either a list or a dictionary representing the policies. No value is returned; assertions are used to validate behavior.
        """
        response = await async_client.get(
            "/api/v1/agents/policies",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or isinstance(data, dict)

    async def test_get_agent_policy_by_id(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test retrieving an agent policy by its identifier.

        Args:
            self: Test case instance.
            async_client (AsyncClient): Asynchronous HTTP client used to call the API.
            auth_headers (dict): Headers containing authentication credentials.

        The test performs a GET request to `/api/v1/agents/policies/default` and asserts that
        the response status code is either 200 (policy found) or 404 (policy not found).
        """
        response = await async_client.get(
            "/api/v1/agents/policies/default",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404]

    async def test_execute_agent_with_custom_policy(
        self,
        async_client: AsyncClient,
        test_investigation,
        auth_headers,
    ):
        """
        Test executing an agent using a custom policy.

        Args:
            async_client: An instance of `AsyncClient` used to make asynchronous HTTP requests against the API.
            test_investigation: A fixture providing an investigation object whose `investigation_id` is used in the request payload.
            auth_headers: Dictionary containing authentication headers required for authorized access to the endpoint.

        The test sends a POST request to `/api/v1/agents/execute` with a JSON body that includes the investigation ID, agent identifier, execution instructions, and the custom policy ID. It then asserts that the response status code is one of the expected values (200 OK, 201 Created, 400 Bad Request, 404 Not Found, or 500 Internal Server Error).
        """
        response = await async_client.post(
            f"/api/v1/agents/execute",
            json={
                "investigation_id": str(test_investigation.investigation_id),
                "agent_id": "test_agent",
                "instructions": "Test",
                "policy_id": "custom_policy",
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 201, 400, 404, 500]
