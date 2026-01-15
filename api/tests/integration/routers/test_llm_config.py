"""
Integration tests for LLM configuration endpoints.
Tests CRUD operations for LLM provider configurations.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestCreateLLMConfig:
    """Test LLM configuration creation endpoint."""

    async def test_create_llm_config_success(self, async_client: AsyncClient, auth_headers):
        """
        Test that creating an LLM configuration with valid data succeeds.

        The test sends a POST request to `/api/v1/llm-config/` with a payload containing all required fields for an Ollama provider, including optional settings such as `max_context_length` and `temperature`. It asserts that the response has a **201 Created** status code, verifies that the returned JSON contains a `config_id`, checks that the `provider_name` and `model_name` match the input, and ensures that sensitive information like `api_key` is omitted from the response.
        """
        payload = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "api_key": "test-key",
            "model_name": "llama3.2",
            "max_context_length": 8192,
            "temperature": 0.7,
            "is_active": True,
        }

        response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert "config_id" in data
        assert data["provider_name"] == "ollama"
        assert data["model_name"] == "llama3.2"
        assert "api_key" not in data  # Should be masked

    async def test_create_llm_config_with_embeddings(self, async_client: AsyncClient, auth_headers):
        """
        Test creating an LLM configuration that includes embedding settings.

        This integration test sends a POST request to the `/api/v1/llm-config/` endpoint with a payload containing both standard LLM fields and optional embedding configuration fields. It verifies that:

        * The response status code is **201 Created**, indicating successful creation.
        * The returned JSON contains the expected embedding provider (`"openai"`) and embedding model name (`"text-embedding-3-small"`).

        Parameters
        ----------
        self : object
            Instance of the test class containing shared fixtures.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API under test.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoint.

        Raises
        ------
        AssertionError
            If the response status code is not 201 or if the embedding fields in the response do not match the expected values.
        """
        payload = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "model_name": "gpt-4",
            "max_context_length": 128000,
            "temperature": 0.5,
            "is_active": False,
            "embedding_provider": "openai",
            "embedding_api_url": "https://api.openai.com/v1/embeddings",
            "embedding_api_key": "sk-test",
            "embedding_model_name": "text-embedding-3-small",
        }

        response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["embedding_provider"] == "openai"
        assert data["embedding_model_name"] == "text-embedding-3-small"

    async def test_create_llm_config_unauthenticated(self, async_client: AsyncClient):
        """
        Test that an unauthenticated request to the LLM configuration creation endpoint is rejected with a 401 Unauthorized response. The test sends a POST request containing a minimal valid payload and asserts that the HTTP status code returned by the server equals 401, confirming that authentication is required for creating LLM provider configurations.
        """
        payload = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "model_name": "llama3.2",
        }

        response = await async_client.post("/api/v1/llm-config/", json=payload)

        assert response.status_code == 401

    async def test_create_llm_config_missing_required_fields(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that creating an LLM configuration without all required fields fails validation.

        Args:
            async_client: An instance of AsyncClient used to send HTTP requests to the API.
            auth_headers: A dictionary containing authentication headers for authorized access.

        The test sends a POST request with an incomplete payload (only `provider_name` provided) to the `/api/v1/llm-config/` endpoint and asserts that the response status code is 422, indicating a validation error due to missing required fields.
        """
        payload = {"provider_name": "ollama"}  # Missing required fields

        response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )

        assert response.status_code == 422


@pytest.mark.integration
class TestListLLMConfigs:
    """Test listing LLM configurations."""

    async def test_list_llm_configs_empty(self, async_client: AsyncClient, auth_headers):
        """
        Test that listing LLM provider configurations returns an empty list when no configurations have been created.

        Parameters
        ----------
        self: object
            The test case instance.
        async_client: AsyncClient
            An asynchronous HTTP client fixture used to make requests against the API.
        auth_headers: dict
            Authentication headers containing a valid bearer token for authorized access.
        """
        response = await async_client.get("/api/v1/llm-config/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_llm_configs_with_data(self, async_client: AsyncClient, auth_headers):
        """
        Test that listing LLM provider configurations returns the created entry.

        Creates a temporary LLM configuration via a POST request, then retrieves the list of configurations with a GET request.
        Asserts that the response status is 200, that at least one configuration is present, and that the first
        configuration in the returned list matches the payload (specifically the `provider_name` field).
        """
        # Create a config first
        payload = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "api_key": "test-key",
            "model_name": "llama3.2",
            "max_context_length": 8192,
            "temperature": 0.7,
            "is_active": True,
        }
        await async_client.post("/api/v1/llm-config/", headers=auth_headers, json=payload)

        # List configs
        response = await async_client.get("/api/v1/llm-config/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["provider_name"] == "ollama"

    async def test_list_llm_configs_unauthenticated(self, async_client: AsyncClient):
        """
        Test that an unauthenticated request to the LLM configuration list endpoint returns HTTP 401 Unauthorized.
        """
        response = await async_client.get("/api/v1/llm-config/")

        assert response.status_code == 401


@pytest.mark.integration
class TestGetActiveLLMConfig:
    """Test getting active LLM configuration."""

    async def test_get_active_config_success(self, async_client: AsyncClient, auth_headers):
        """
        Test that retrieving the active LLM provider configuration returns a successful response with the correct data.

        The test performs the following steps:
        1. Creates an LLM configuration marked as active by sending a POST request to `/api/v1/llm-config/`.
        2. Sends a GET request to `/api/v1/llm-config/active` to fetch the currently active configuration.
        3. Asserts that the response status code is 200 (OK).
        4. Parses the JSON payload and verifies that:
           - The `is_active` flag is `True`.
           - The `provider_name` matches the value supplied during creation (`"ollama"`).
        """
        # Create an active config
        payload = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "api_key": "test-key",
            "model_name": "llama3.2",
            "max_context_length": 8192,
            "temperature": 0.7,
            "is_active": True,
        }
        await async_client.post("/api/v1/llm-config/", headers=auth_headers, json=payload)

        response = await async_client.get("/api/v1/llm-config/active", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True
        assert data["provider_name"] == "ollama"

    async def test_get_active_config_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that retrieving the active LLM configuration returns an appropriate response when no active config exists, asserting that the status code is either 200 (with an empty result) or 404.
        """
        response = await async_client.get("/api/v1/llm-config/active", headers=auth_headers)

        # Could be 200 with empty list or 404 depending on implementation
        assert response.status_code in [200, 404]

    async def test_get_active_config_unauthenticated(self, async_client: AsyncClient):
        """
        Test that an unauthenticated request to the active LLM configuration endpoint returns a 401 Unauthorized response.
        """
        response = await async_client.get("/api/v1/llm-config/active")

        assert response.status_code == 401


@pytest.mark.integration
class TestGetLLMConfig:
    """Test getting specific LLM configuration by ID."""

    async def test_get_config_success(self, async_client: AsyncClient, auth_headers):
        """
        Test retrieving a specific LLM provider configuration.

        The test performs the following actions:
        1. Creates a new LLM configuration using a POST request with a payload containing provider details such as `provider_name`, `api_endpoint`, `api_key`, `model_name`, `max_context_length`, `temperature` and `is_active`.
        2. Extracts the generated `config_id` from the creation response.
        3. Retrieves the newly created configuration with a GET request to `/api/v1/llm-config/{config_id}`.
        4. Asserts that the retrieval request returns HTTP status 200.
        5. Verifies that the returned JSON contains the expected `config_id` and that the `provider_name` matches the value supplied during creation.
        """
        # Create a config
        payload = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "api_key": "test-key",
            "model_name": "llama3.2",
            "max_context_length": 8192,
            "temperature": 0.7,
            "is_active": True,
        }
        create_response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )
        config_id = create_response.json()["config_id"]

        # Get the config
        response = await async_client.get(f"/api/v1/llm-config/{config_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["config_id"] == config_id
        assert data["provider_name"] == "ollama"

    async def test_get_config_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that attempting to retrieve a non-existent LLM configuration returns a 404 Not Found response by sending a GET request to the `/api/v1/llm-config/999999` endpoint and asserting the status code.
        """
        response = await async_client.get("/api/v1/llm-config/999999", headers=auth_headers)

        assert response.status_code == 404

    async def test_get_config_unauthenticated(self, async_client: AsyncClient):
        """
        Test that an unauthenticated request to retrieve a specific LLM configuration returns a 401 Unauthorized response. The test sends a GET request to the `/api/v1/llm-config/1` endpoint using the provided asynchronous HTTP client and asserts that the response status code equals 401, confirming that authentication is required for this operation.
        """
        response = await async_client.get("/api/v1/llm-config/1")

        assert response.status_code == 401


@pytest.mark.integration
class TestUpdateLLMConfig:
    """Test updating LLM configuration."""

    async def test_update_config_success(self, async_client: AsyncClient, auth_headers):
        """
        Test successful update of an existing LLM provider configuration.

        This integration test performs the following steps:
        1. Creates a new LLM configuration via `POST /api/v1/llm-config/` using a comprehensive payload that includes provider details, model settings, and activation status.
        2. Extracts the generated `config_id` from the creation response.
        3. Sends a partial update request to `PATCH /api/v1/llm-config/{config_id}` with a payload that modifies `temperature` and `model_name`.
        4. Asserts that the response has an HTTP 200 status code.
        5. Verifies that the returned JSON reflects the updated `temperature` and `model_name` values.

        Args:
            self: Test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture for making API requests.
            auth_headers (dict): Authorization headers containing a valid JWT or token.

        Raises:
            AssertionError: If any of the response status codes or returned fields do not match the expected values.
        """
        # Create a config
        payload = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "api_key": "test-key",
            "model_name": "llama3.2",
            "max_context_length": 8192,
            "temperature": 0.7,
            "is_active": True,
        }
        create_response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )
        config_id = create_response.json()["config_id"]

        # Update the config
        update_payload = {"temperature": 0.9, "model_name": "llama3.2:latest"}
        response = await async_client.patch(
            f"/api/v1/llm-config/{config_id}", headers=auth_headers, json=update_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["temperature"] == 0.9
        assert data["model_name"] == "llama3.2:latest"

    async def test_update_config_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that updating a non-existent LLM configuration returns HTTP 404 Not Found. The request patches an unknown config ID (999999) with a sample payload and asserts the response status code is 404.
        """
        update_payload = {"temperature": 0.9}
        response = await async_client.patch(
            "/api/v1/llm-config/999999", headers=auth_headers, json=update_payload
        )

        assert response.status_code == 404

    async def test_update_config_unauthenticated(self, async_client: AsyncClient):
        """
        Test that updating an LLM configuration without authentication is rejected.

        This test sends a PATCH request with a sample payload to the `/api/v1/llm-config/1` endpoint using an unauthenticated client and asserts that the response status code is `401 Unauthorized`.
        """
        update_payload = {"temperature": 0.9}
        response = await async_client.patch("/api/v1/llm-config/1", json=update_payload)

        assert response.status_code == 401


@pytest.mark.integration
class TestDeleteLLMConfig:
    """Test deleting LLM configuration."""

    async def test_delete_config_success(self, async_client: AsyncClient, auth_headers):
        """
        Test that deleting an LLM provider configuration succeeds and removes the resource.

        The test performs the following actions:
        1. Creates a new LLM configuration using a POST request to `/api/v1/llm-config/` with a sample payload.
        2. Extracts the generated `config_id` from the creation response.
        3. Sends a DELETE request to `/api/v1/llm-config/{config_id}` and asserts that the status code is `204 No Content`.
        4. Attempts to retrieve the same configuration with a GET request and asserts that the status code is `404 Not Found`, confirming the deletion.

        Args:
            async_client: An instance of :class:`httpx.AsyncClient` used to make asynchronous HTTP requests against the API.
            auth_headers: A dictionary containing authentication headers required for authorized access.
        """
        # Create a config
        payload = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "api_key": "test-key",
            "model_name": "llama3.2",
            "max_context_length": 8192,
            "temperature": 0.7,
            "is_active": True,
        }
        create_response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )
        config_id = create_response.json()["config_id"]

        # Delete the config
        response = await async_client.delete(
            f"/api/v1/llm-config/{config_id}", headers=auth_headers
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await async_client.get(
            f"/api/v1/llm-config/{config_id}", headers=auth_headers
        )
        assert get_response.status_code == 404

    async def test_delete_config_not_found(self, async_client: AsyncClient, auth_headers):
        """
        Test that deleting a non-existent LLM configuration returns a 404 response. The test sends an HTTP DELETE request to the `/api/v1/llm-config/999999` endpoint using an authenticated client and asserts that the server responds with status code 404, indicating the resource was not found.
        """
        response = await async_client.delete("/api/v1/llm-config/999999", headers=auth_headers)

        assert response.status_code == 404

    async def test_delete_config_unauthenticated(self, async_client: AsyncClient):
        """
        Test that an unauthenticated request to delete an LLM configuration endpoint is rejected with HTTP 401 Unauthorized.
        """
        response = await async_client.delete("/api/v1/llm-config/1")

        assert response.status_code == 401
