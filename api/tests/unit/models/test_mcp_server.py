import pytest
from datetime import datetime
from app.models.mcp_server import MCPServer


@pytest.mark.unit
class TestMCPServerModel:
    """Test MCPServer model."""

    def test_create_mcp_server(self):
        """
        Test that an :class:`MCPServer` instance can be created with the required fields and that its attributes are correctly assigned.

        The test constructs a server with a name, base URL, authentication token, and owner user ID, then asserts that each attribute matches the provided value. This verifies basic object initialization and attribute storage.
        """
        server = MCPServer(
            name="Test MCP Server",
            base_url="http://localhost:8080",
            auth_token="test-token-123",
            owner_user_id=1,
        )

        assert server.name == "Test MCP Server"
        assert server.base_url == "http://localhost:8080"
        assert server.auth_token == "test-token-123"

    def test_server_without_auth_token(self):
        """
        Test that an MCPServer instance can be created without providing an authentication token and that the `auth_token` attribute is set to `None` after initialization.
        """
        server = MCPServer(
            name="Public Server",
            base_url="http://localhost:8080",
            auth_token=None,
            owner_user_id=1,
        )

        assert server.auth_token is None

    def test_server_with_allowed_agents(self):
        """
        Test that an MCPServer instance correctly stores and reports its allowed agents list.

        Creates a server with three permitted agent identifiers and verifies:
        - The `allowed_agents` attribute contains exactly three entries.
        - A known identifier (`"agent1"`) is present in the collection.
        """
        server = MCPServer(
            name="Test Server",
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
            allowed_agents=["agent1", "agent2", "agent3"],
        )

        assert len(server.allowed_agents) == 3
        assert "agent1" in server.allowed_agents

    def test_server_empty_allowed_agents(self):
        """
        Test that creating an MCPServer instance with an empty list for `allowed_agents` correctly stores an empty list, ensuring the attribute is initialized without errors and matches the provided value.
        """
        server = MCPServer(
            name="Test Server",
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
            allowed_agents=[],
        )

        assert server.allowed_agents == []

    def test_server_unicode_name(self):
        """
        Test that an MCPServer instance correctly stores and returns a Unicode string for its name attribute. The server is created with a Japanese name ("サーバー名") and the test asserts that the `name` property matches the provided Unicode value.
        """
        server = MCPServer(
            name="サーバー名",
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
        )

        assert server.name == "サーバー名"

    def test_server_long_name(self):
        """
        Test that creating an :class:`MCPServer` with an excessively long `name` value stores the full string without truncation, ensuring the `name` attribute can exceed typical length limits (e.g., longer than 500 characters). The test constructs a repetitive long name, instantiates the server, and asserts that the stored name length meets the expected threshold.
        """
        long_name = "Server " * 100

        server = MCPServer(
            name=long_name,
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
        )

        assert len(server.name) > 500

    def test_server_https_url(self):
        """
        Test that an MCPServer instance correctly stores and reports an HTTPS base URL.

        The server is created with a name, a base_url using the "https://" scheme, an authentication token, and an owner user ID.
        The test asserts that the `base_url` attribute of the resulting object starts with the expected "https://" prefix, confirming proper handling of secure URLs.
        """
        server = MCPServer(
            name="Secure Server",
            base_url="https://api.example.com",
            auth_token="token",
            owner_user_id=1,
        )

        assert server.base_url.startswith("https://")

    def test_server_localhost_url(self):
        """
        Test that creating an :class:`MCPServer` with a localhost base URL stores the URL correctly and includes the substring `"localhost"` in the `base_url` attribute.
        """
        server = MCPServer(
            name="Local Server",
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
        )

        assert "localhost" in server.base_url

    def test_server_ip_address_url(self):
        """
        Test that an MCPServer instance correctly stores and reports a base URL containing an IP address.

        Creates an `MCPServer` with:
        - `name` set to `"IP Server"`
        - `base_url` using the HTTP scheme and a numeric IP (e.g., `http://192.168.1.100:8080`)
        - `auth_token` set to `"token"`
        - `owner_user_id` set to `1`

        The test asserts that the string representation of the server's `base_url` includes the expected IP address component (`"192.168.1.100"`), confirming that the model does not alter or reject URLs that use raw IP addresses.
        """
        server = MCPServer(
            name="IP Server",
            base_url="http://192.168.1.100:8080",
            auth_token="token",
            owner_user_id=1,
        )

        assert "192.168.1.100" in server.base_url

    def test_server_with_path(self):
        """
        Test that an MCPServer instance correctly retains and exposes a base URL containing a path segment, verifying that the specified path (e.g., "/api/v1") is present in the server's `base_url` attribute after initialization.
        """
        server = MCPServer(
            name="Path Server",
            base_url="http://localhost:8080/api/v1",
            auth_token="token",
            owner_user_id=1,
        )

        assert "/api/v1" in server.base_url

    def test_server_owner_isolation(self):
        """
        Test that each MCPServer instance correctly stores its associated owner_user_id, ensuring that servers created with different owners have distinct owner identifiers.
        """
        server1 = MCPServer(
            name="User 1 Server",
            base_url="http://localhost:8080",
            auth_token="token1",
            owner_user_id=1,
        )

        server2 = MCPServer(
            name="User 2 Server",
            base_url="http://localhost:8081",
            auth_token="token2",
            owner_user_id=2,
        )

        assert server1.owner_user_id != server2.owner_user_id

    def test_server_long_auth_token(self):
        """
        Test that creating an MCPServer with an exceptionally long authentication token stores the full token correctly, ensuring the `auth_token` attribute length exceeds 1000 characters.
        """
        long_token = "token-" + "a" * 1000

        server = MCPServer(
            name="Test Server",
            base_url="http://localhost:8080",
            auth_token=long_token,
            owner_user_id=1,
        )

        assert len(server.auth_token) > 1000

    def test_server_special_chars_in_name(self):
        """
        Test that a server name containing special characters such as parentheses and brackets is stored correctly.

        The test creates an `MCPServer` instance with a name that includes
        `(Production)` and `[v1.0]`. It then asserts that both substrings are
        present in the `name` attribute, confirming that special characters are
        preserved during initialization.
        """
        server = MCPServer(
            name="Test Server (Production) [v1.0]",
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
        )

        assert "(Production)" in server.name
        assert "[v1.0]" in server.name

    def test_server_allowed_agents_unicode(self):
        """
        Test that the `allowed_agents` attribute correctly stores and retrieves agent names containing Unicode characters.

        The test creates an `MCPServer` instance with a list of allowed agents that includes Japanese strings (`"エージェント1"` and `"代理2"`). It then asserts that the Unicode name `"エージェント1"` is present in the server's `allowed_agents` collection, verifying proper handling of non-ASCII characters.
        """
        server = MCPServer(
            name="Test Server",
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
            allowed_agents=["エージェント1", "代理2"],
        )

        assert "エージェント1" in server.allowed_agents

    def test_repr_format(self):
        """
        Test that the `__repr__` method of :class:`MCPServer` produces a string containing the class name and key attribute values.

        The test creates an instance with known attributes (ID, name, base URL, auth token, owner ID) and then checks that the resulting representation includes:

        * The literal `"MCPServer"`
        * The identifier `id=42`
        * The name field formatted as `name='Test Server'`
        * The URL field formatted as `url='http://localhost:8080'`

        These assertions confirm that `__repr__` follows the expected formatting convention.
        """
        server = MCPServer(
            server_id=42,
            name="Test Server",
            base_url="http://localhost:8080",
            auth_token="token",
            owner_user_id=1,
        )

        repr_str = repr(server)

        assert "MCPServer" in repr_str
        assert "id=42" in repr_str
        assert "name='Test Server'" in repr_str
        assert "url='http://localhost:8080'" in repr_str
