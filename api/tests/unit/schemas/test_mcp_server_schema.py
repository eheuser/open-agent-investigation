"""
Unit tests for MCP server schemas.
Tests Pydantic validation for MCP server data.
"""

import pytest
from pydantic import ValidationError
from app.schemas.mcp_server import MCPServerCreate, MCPServerRead, MCPServerUpdate


@pytest.mark.unit
class TestMCPServerCreate:
    """Test MCPServerCreate schema."""

    def test_create_valid_server(self):
        """
        Test that creating an :class:`MCPServerCreate` instance with all required fields and optional `auth_token` succeeds and correctly assigns the provided values.
        """
        data = {
            "name": "Test MCP Server",
            "base_url": "http://localhost:8080",
            "auth_token": "test-token-123",
        }

        server = MCPServerCreate(**data)

        assert server.name == "Test MCP Server"
        assert server.base_url == "http://localhost:8080"
        assert server.auth_token == "test-token-123"

    def test_create_server_without_auth(self):
        """
        Test that creating an MCP server schema without providing an authentication token succeeds, verifying that the required fields are correctly set and the optional `auth_token` attribute defaults to `None`.
        """
        data = {
            "name": "Public Server",
            "base_url": "http://localhost:8080",
        }

        server = MCPServerCreate(**data)

        assert server.name == "Public Server"
        assert server.auth_token is None

    def test_create_server_with_allowed_agents(self):
        """
        Test that creating an MCPServerCreate schema instance with an explicit list of allowed agents correctly stores the provided agents.

        The test constructs input data containing:
        - `name`: The server's display name.
        - `base_url`: The base URL where the server is reachable.
        - `allowed_agents`: A list of agent identifiers that are permitted to interact with the server.

        It then instantiates :class:`MCPServerCreate` using the supplied data and asserts that the resulting object's `allowed_agents` attribute contains exactly two entries, confirming that the schema accepts and preserves the optional `allowed_agents` field without modification.
        """
        data = {
            "name": "Test Server",
            "base_url": "http://localhost:8080",
            "allowed_agents": ["agent1", "agent2"],
        }

        server = MCPServerCreate(**data)

        assert len(server.allowed_agents) == 2

    def test_create_server_missing_name(self):
        """
        Test that creating an MCPServerCreate schema without the required `name` field raises a `ValidationError`. The input data includes only optional fields (e.g., `base_url`), and the test asserts that validation fails as expected.
        """
        data = {
            "base_url": "http://localhost:8080",
        }

        with pytest.raises(ValidationError):
            MCPServerCreate(**data)

    def test_create_server_missing_url(self):
        """
        Test that creating an MCPServerCreate schema without the required `url` field raises a `ValidationError`. The input data includes only the optional `name` attribute; attempting to instantiate the schema should trigger validation failure due to the missing mandatory URL.
        """
        data = {
            "name": "Test Server",
        }

        with pytest.raises(ValidationError):
            MCPServerCreate(**data)


@pytest.mark.unit
class TestMCPServerRead:
    """Test MCPServerRead schema."""

    def test_read_server_basic(self):
        """
        Test that the MCPServerRead schema correctly parses a full set of server attributes, ensuring required fields are populated and optional fields (such as auth_token and allowed_agents) are accepted without error. The test constructs a data dictionary with typical values, instantiates an MCPServerRead object, and asserts that key attributes (server_id and name) match the input.
        """
        from datetime import datetime

        data = {
            "server_id": 1,
            "name": "Test Server",
            "base_url": "http://localhost:8080",
            "auth_token": "token",
            "owner_user_id": 1,
            "allowed_agents": [],
            "created_at": datetime.now(),
        }

        server = MCPServerRead(**data)

        assert server.server_id == 1
        assert server.name == "Test Server"

    def test_read_server_with_allowed_agents(self):
        """
        Test that MCPServerRead correctly includes allowed agents in the deserialized model. The test constructs a data dictionary with an `allowed_agents` list, creates a `MCPServerRead` instance using keyword arguments, and asserts that a known agent (\"agent1\") is present in the resulting `allowed_agents` attribute. This verifies that the Pydantic schema properly handles optional list fields during read operations.
        """
        from datetime import datetime

        data = {
            "server_id": 1,
            "name": "Test Server",
            "base_url": "http://localhost:8080",
            "auth_token": "token",
            "owner_user_id": 1,
            "allowed_agents": ["agent1", "agent2"],
            "created_at": datetime.now(),
        }

        server = MCPServerRead(**data)

        assert "agent1" in server.allowed_agents


@pytest.mark.unit
class TestMCPServerUpdate:
    """Test MCPServerUpdate schema."""

    def test_update_name(self):
        """
        Test that updating only the `name` field of an :class:`MCPServerUpdate` instance correctly assigns the new value without affecting other attributes. The test creates a minimal payload containing a new name, instantiates the update schema, and asserts that the `name` attribute matches the provided value.
        """
        data = {
            "name": "Updated Name",
        }

        update = MCPServerUpdate(**data)

        assert update.name == "Updated Name"

    def test_update_url(self):
        """
        Test that updating only the server's base URL using the MCPServerUpdate schema correctly assigns the new value without affecting other fields.
        """
        data = {
            "base_url": "http://new-url:9000",
        }

        update = MCPServerUpdate(**data)

        assert update.base_url == "http://new-url:9000"

    def test_update_auth_token(self):
        """
        Test that updating an MCPServer record with a new authentication token correctly assigns the provided value to the `auth_token` attribute of the :class:`MCPServerUpdate` schema instance. This ensures that partial updates containing only the optional `auth_token` field are validated and applied without errors.
        """
        data = {
            "auth_token": "new-token",
        }

        update = MCPServerUpdate(**data)

        assert update.auth_token == "new-token"

    def test_update_empty(self):
        """
        Test that updating an MCP server with an empty payload creates a model instance where all optional fields are set to `None` without raising validation errors. This ensures the update schema permits partial updates and correctly defaults missing attributes.
        """
        data = {}

        update = MCPServerUpdate(**data)

        assert update.name is None
        assert update.base_url is None
