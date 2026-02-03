import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestMCPRouter:
    """Test MCP server endpoints."""

    async def test_create_mcp_server_success(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test creating a new MCP server via the API.

        This integration test sends a POST request to `/api/v1/mcp/` with a JSON payload
        containing the required fields for an MCP server (name, base_url,
        auth_token, and allowed_agents).  The request includes authentication headers
        provided by the fixture `auth_headers`.

        The test asserts that:

        * The response status code is **201 Created**.
        * The returned JSON contains the same `name`, `base_url` and
          `allowed_agents` values as sent in the request.
        * The response includes a generated `server_id` field.
        * The response includes an `owner_user_id` field indicating the user who
          created the server.

        Parameters
        ----------
        self : object
            The test class instance (provided by the test framework).
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        auth_headers : dict
            A dictionary containing authentication headers required for the request.
        """
        response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Test MCP Server",
                "base_url": "http://localhost:8080",
                "auth_token": "test-token-123",
                "allowed_agents": ["agent1", "agent2"],
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test MCP Server"
        assert data["base_url"] == "http://localhost:8080"
        assert data["allowed_agents"] == ["agent1", "agent2"]
        assert "server_id" in data
        assert "owner_user_id" in data

    async def test_create_mcp_server_minimal(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test creating an MCP server using only the required fields.

        Parameters:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client fixture for making API requests.
            auth_headers (dict): Authentication headers to include in the request, typically containing a valid JWT or token.

        The test sends a POST request to the `/api/v1/mcp/` endpoint with a minimal payload consisting of `name` and `base_url`. It asserts that:
        * The response status code is 201 (Created).
        * The returned JSON contains the same `name` as provided.
        * The `auth_token` field is `None`.
        * The `allowed_agents` field is either an empty list or `None`, indicating no agent restrictions were set.
        """
        response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Minimal Server",
                "base_url": "http://localhost:9000",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Server"
        assert data["auth_token"] is None
        assert data["allowed_agents"] == [] or data["allowed_agents"] is None

    async def test_create_mcp_server_unauthenticated(
        self,
        async_client: AsyncClient,
    ):
        """
        Test that creating an MCP server endpoint rejects unauthenticated requests by returning HTTP 401 Unauthorized. The test sends a POST request to `/api/v1/mcp/` with minimal valid JSON payload (`name` and `base_url`) using the provided `async_client` fixture, then asserts that the response status code equals 401. This ensures that authentication is required for server creation.
        """
        response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Test Server",
                "base_url": "http://localhost:8080",
            },
        )

        assert response.status_code == 401

    async def test_list_mcp_servers_empty(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that listing MCP servers returns an empty list when no servers have been created.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An asynchronous HTTP client used to make requests against the API.
        auth_headers : dict
            Authentication headers to include in the request, representing a logged-in user.

        Raises
        ------
        AssertionError
            If the response status code is not 200 or if the returned JSON payload is not an empty list.
        """
        response = await async_client.get(
            "/api/v1/mcp/",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_mcp_servers_with_data(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that listing MCP servers returns all created entries for an authenticated user.

        Args:
            self: Test case instance.
            async_client (AsyncClient): HTTP client for making asynchronous requests to the API.
            auth_headers (dict): Authentication headers containing a valid token for the test user.

        The test creates three MCP server records via POST requests, then retrieves the list of servers with a GET request. It asserts that:
        - The response status code is 200.
        - Exactly three server objects are returned.
        - The first server's name matches "Server 1".
        """
        # Create multiple servers
        for i in range(3):
            await async_client.post(
                "/api/v1/mcp/",
                json={
                    "name": f"Server {i + 1}",
                    "base_url": f"http://localhost:{8080 + i}",
                },
                headers=auth_headers,
            )

        # List servers
        response = await async_client.get(
            "/api/v1/mcp/",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["name"] == "Server 1"

    async def test_list_mcp_servers_user_isolation(
        self,
        async_client: AsyncClient,
        auth_headers,
        admin_token,
        test_user,
    ):
        """
        Test that regular users only see their own MCP servers.

        This integration test verifies user isolation in the server listing endpoint:

        * Creates an MCP server using a regular user's authentication headers.
        * Creates another MCP server using an admin token.
        * Retrieves the list of MCP servers with the regular user's credentials.
        * Asserts that the response is successful (HTTP 200) and contains exactly one entry,
          which must be the server created by the regular user.

        Args:
            async_client: An instance of `httpx.AsyncClient` configured for the test application.
            auth_headers: Authentication headers containing a bearer token for a non-admin user.
            admin_token: Bearer token with administrative privileges.
            test_user: Fixture representing the regular user (unused directly but ensures user context).
        """
        # Create server as regular user
        await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "User Server",
                "base_url": "http://localhost:8080",
            },
            headers=auth_headers,
        )

        # Create server as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Admin Server",
                "base_url": "http://localhost:8081",
            },
            headers=admin_headers,
        )

        # Regular user should only see their server
        response = await async_client.get(
            "/api/v1/mcp/",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "User Server"

    async def test_list_mcp_servers_admin_sees_all(
        self,
        async_client: AsyncClient,
        auth_headers,
        admin_token,
    ):
        """
        Test that an admin user can list all MCP servers regardless of ownership.

        This integration test performs the following steps:
        1. Creates a server using regular-user credentials.
        2. Creates another server using admin credentials.
        3. Retrieves the list of servers with admin authentication.
        4. Asserts that the response status is 200 and that both created servers are present in the returned collection.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client configured for asynchronous requests against the API under test.
        auth_headers : dict
            Authorization headers containing a bearer token for a regular user.
        admin_token : str
            JWT token representing an admin user; used to build `admin_headers`.
        """
        # Create server as regular user
        await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "User Server",
                "base_url": "http://localhost:8080",
            },
            headers=auth_headers,
        )

        # Create server as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Admin Server",
                "base_url": "http://localhost:8081",
            },
            headers=admin_headers,
        )

        # Admin should see both servers
        response = await async_client.get(
            "/api/v1/mcp/",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_mcp_server_success(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test retrieving a specific MCP server.

        Creates an MCP server using the provided authentication headers, then fetches that server by its ID and verifies a successful response. The test asserts that:
        - The HTTP status code is 200.
        - The returned JSON contains the expected `server_id`, `name`, and `auth_token` matching the created server.
        """
        # Create server
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Test Server",
                "base_url": "http://localhost:8080",
                "auth_token": "secret-token",
            },
            headers=auth_headers,
        )
        server_id = create_response.json()["server_id"]

        # Get server
        response = await async_client.get(
            f"/api/v1/mcp/{server_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["server_id"] == server_id
        assert data["name"] == "Test Server"
        assert data["auth_token"] == "secret-token"

    async def test_get_mcp_server_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that retrieving an MCP server with an ID that does not exist returns a 404 response and includes a “not found” message in the error detail. The test sends a GET request to `/api/v1/mcp/999999` using the provided authentication headers, then asserts that the status code is 404 and that the response body’s `detail` field contains the phrase “not found”.
        """
        response = await async_client.get(
            "/api/v1/mcp/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_mcp_server_access_denied(
        self,
        async_client: AsyncClient,
        auth_headers,
        admin_token,
    ):
        """
        Test that a regular user cannot retrieve an MCP server created by another user (admin), expecting a 403 Forbidden response with an "Access denied" detail message. The test creates a server using admin credentials, then attempts to GET the server endpoint with non-admin authentication headers and asserts the correct error status and message.
        """
        # Create server as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Admin Server",
                "base_url": "http://localhost:8080",
            },
            headers=admin_headers,
        )
        server_id = create_response.json()["server_id"]

        # Try to access as regular user
        response = await async_client.get(
            f"/api/v1/mcp/{server_id}",
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    async def test_update_mcp_server_success(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test updating an MCP server via the API.

        The test performs the following actions:
        1. Creates a new MCP server using a POST request to `/api/v1/mcp/` with a
           `name` of `"Original Name"` and a `base_url` of `http://localhost:8080`.
        2. Extracts the `server_id` from the creation response.
        3. Sends a PATCH request to `/api/v1/mcp/{server_id}` updating both the
           `name` to `"Updated Name"` and the `base_url` to `http://localhost:9000`.
        4. Asserts that the response status code is `200` (OK).
        5. Verifies that the returned JSON payload reflects the updated values for
           `name` and `base_url`.

        Parameters
        ----------
        self : object
            The test case instance.
        async_client : AsyncClient
            An HTTP client capable of making asynchronous requests to the API.
        auth_headers : dict
            Authentication headers required for authorized access to the endpoints.
        """
        # Create server
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Original Name",
                "base_url": "http://localhost:8080",
            },
            headers=auth_headers,
        )
        server_id = create_response.json()["server_id"]

        # Update server
        response = await async_client.patch(
            f"/api/v1/mcp/{server_id}",
            json={
                "name": "Updated Name",
                "base_url": "http://localhost:9000",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["base_url"] == "http://localhost:9000"

    async def test_update_mcp_server_partial(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that partially updating an MCP server via the PATCH endpoint correctly modifies only the supplied fields while leaving unspecified fields unchanged.

        The test performs the following actions:
        1. Creates a new MCP server with a specific name, base URL, and authentication token.
        2. Sends a PATCH request containing only a new `name` value for the created server.
        3. Asserts that the response status code is 200 (OK).
        4. Verifies that the returned JSON reflects the updated name while preserving the original `base_url` and `auth_token` values.
        """
        # Create server
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Original Name",
                "base_url": "http://localhost:8080",
                "auth_token": "original-token",
            },
            headers=auth_headers,
        )
        server_id = create_response.json()["server_id"]

        # Update only name
        response = await async_client.patch(
            f"/api/v1/mcp/{server_id}",
            json={
                "name": "New Name",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["base_url"] == "http://localhost:8080"  # Unchanged
        assert data["auth_token"] == "original-token"  # Unchanged

    async def test_update_mcp_server_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that updating an MCP server with an ID that does not exist returns a 404 response.

        The test sends a PATCH request to `/api/v1/mcp/999999` (an ID presumed absent) with a JSON payload containing a new name and the appropriate authentication headers. It then asserts that the HTTP status code of the response is `404`, confirming that the API correctly reports “Not Found” for non-existent resources.
        """
        response = await async_client.patch(
            "/api/v1/mcp/999999",
            json={"name": "Updated"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_mcp_server_access_denied(
        self,
        async_client: AsyncClient,
        auth_headers,
        admin_token,
    ):
        """
        Test that a regular user cannot update an MCP server owned by another user.

        Args:
            self: The test case instance.
            async_client (AsyncClient): An asynchronous HTTP client used to send requests to the API.
            auth_headers (dict): Authorization headers for a non-admin user, typically containing a bearer token.
            admin_token (str): Bearer token with administrative privileges used to create the server.

        The test performs the following steps:
        1. Creates an MCP server using admin credentials.
        2. Attempts to patch (update) that server using regular user credentials.
        3. Asserts that the response status code is 403, indicating that the operation is forbidden for users lacking ownership or appropriate permissions.
        """
        # Create server as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Admin Server",
                "base_url": "http://localhost:8080",
            },
            headers=admin_headers,
        )
        server_id = create_response.json()["server_id"]

        # Try to update as regular user
        response = await async_client.patch(
            f"/api/v1/mcp/{server_id}",
            json={"name": "Hacked"},
            headers=auth_headers,
        )

        assert response.status_code == 403

    async def test_update_mcp_server_admin_can_update_any(
        self,
        async_client: AsyncClient,
        auth_headers,
        admin_token,
    ):
        """
        Test that an admin user can update any MCP server regardless of ownership.

        This integration test performs the following steps:
        1. Creates a new MCP server using regular user credentials provided via `auth_headers`.
        2. Extracts the `server_id` from the creation response.
        3. Sends a PATCH request to update the server's name, authenticating with an admin token supplied in `admin_token`.
        4. Asserts that the response status code is 200 (OK) and that the returned JSON reflects the updated name.

        Args:
            self: The test class instance.
            async_client: An `httpx.AsyncClient` configured for making asynchronous HTTP requests to the API.
            auth_headers: A dictionary containing authentication headers for a regular user, typically `{"Authorization": "Bearer <user_token>"}`.
            admin_token: A JWT token string with administrative privileges used to construct the admin authorization header.

        Raises:
            AssertionError: If the response status code is not 200 or if the server name in the response does not match the expected updated value.
        """
        # Create server as regular user
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "User Server",
                "base_url": "http://localhost:8080",
            },
            headers=auth_headers,
        )
        server_id = create_response.json()["server_id"]

        # Update as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        response = await async_client.patch(
            f"/api/v1/mcp/{server_id}",
            json={"name": "Admin Updated"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Admin Updated"

    async def test_delete_mcp_server_success(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that an authenticated user can successfully delete an MCP server and that subsequent retrieval attempts return a 404 Not Found.

        The test performs the following actions:
        1. Creates a new MCP server using a POST request to `/api/v1/mcp/` with a minimal payload.
        2. Extracts the generated `server_id` from the creation response.
        3. Sends a DELETE request to `/api/v1/mcp/{server_id}` and asserts that the response status code is 204 (No Content), indicating successful deletion.
        4. Attempts to retrieve the deleted server with a GET request to the same endpoint and asserts that the response status code is 404, confirming that the server no longer exists.
        """
        # Create server
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "To Delete",
                "base_url": "http://localhost:8080",
            },
            headers=auth_headers,
        )
        server_id = create_response.json()["server_id"]

        # Delete server
        response = await async_client.delete(
            f"/api/v1/mcp/{server_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = await async_client.get(
            f"/api/v1/mcp/{server_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    async def test_delete_mcp_server_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """
        Test that attempting to delete an MCP server with an ID that does not exist returns a 404 Not Found response, confirming proper error handling for missing resources.
        """
        response = await async_client.delete(
            "/api/v1/mcp/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_mcp_server_access_denied(
        self,
        async_client: AsyncClient,
        auth_headers,
        admin_token,
    ):
        """
        Test that a regular user cannot delete an MCP server created by another user (admin), ensuring the API returns HTTP 403 Forbidden when attempting unauthorized deletion. The test creates a server using admin credentials, then attempts to delete it with standard user authentication headers and asserts that the response status code is 403.
        """
        # Create server as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "Admin Server",
                "base_url": "http://localhost:8080",
            },
            headers=admin_headers,
        )
        server_id = create_response.json()["server_id"]

        # Try to delete as regular user
        response = await async_client.delete(
            f"/api/v1/mcp/{server_id}",
            headers=auth_headers,
        )

        assert response.status_code == 403

    async def test_delete_mcp_server_admin_can_delete_any(
        self,
        async_client: AsyncClient,
        auth_headers,
        admin_token,
    ):
        """
        Test that an admin user can delete any MCP server regardless of the creator.

        Args:
            self: The test class instance.
            async_client (AsyncClient): An asynchronous HTTP client for making API requests.
            auth_headers (dict): Authorization headers containing a regular user's token, used to create a server.
            admin_token (str): Bearer token with administrative privileges, used to perform the delete operation.

        The test creates an MCP server using a regular user's credentials, then attempts to delete that server using an admin's credentials. It asserts that the deletion request returns HTTP status code 204 (No Content), indicating successful removal of the server.
        """
        # Create server as regular user
        create_response = await async_client.post(
            "/api/v1/mcp/",
            json={
                "name": "User Server",
                "base_url": "http://localhost:8080",
            },
            headers=auth_headers,
        )
        server_id = create_response.json()["server_id"]

        # Delete as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        response = await async_client.delete(
            f"/api/v1/mcp/{server_id}",
            headers=admin_headers,
        )

        assert response.status_code == 204
