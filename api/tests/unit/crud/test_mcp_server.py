import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from app.crud.mcp_server import (
    create_mcp,
    get_mcp_by_id,
    get_mcp_by_name,
    list_mcp_servers,
    update_mcp,
    delete_mcp,
)
from app.models.mcp_server import MCPServer


@pytest.mark.unit
class TestCreateMCP:
    """Test create_mcp function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and configures a mock asynchronous database session for use in tests.

        Returns
        -------
        AsyncMock
            A mock object representing the database session with its `add` method replaced by a `MagicMock` and both `commit` and `refresh` methods set as `AsyncMock` instances, allowing asynchronous calls to be awaited in test scenarios.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_mcp_minimal(self, mock_db):
        """
        Test the `create_mcp` coroutine with only the required fields supplied.

        The test sets up minimal valid input values (name, base URL, allowed agents list, and owner user ID) and calls :func:`create_mcp` using a mocked asynchronous database session. It then verifies that:

        * The database session's `add`, `commit` and `refresh` methods are each invoked exactly once.
        * The object passed to `add` is an instance of :class:`MCPServer`.
        * All fields on the created `MCPServer` instance match the supplied arguments, including a `None` value for `auth_token`.

        Parameters
        ----------
        self: object
            Reference to the test case instance (unused in the body).
        mock_db: unittest.mock.AsyncMock
            A mocked asynchronous database session providing `add`, `commit` and `refresh` methods.
        """
        name = "Test MCP"
        base_url = "http://localhost:8080"
        allowed_agents = ["agent1", "agent2"]
        owner_user_id = 1

        result = await create_mcp(
            db=mock_db,
            name=name,
            base_url=base_url,
            auth_token=None,
            allowed_agents=allowed_agents,
            owner_user_id=owner_user_id,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify MCP server object
        added_server = mock_db.add.call_args[0][0]
        assert isinstance(added_server, MCPServer)
        assert added_server.name == name
        assert added_server.base_url == base_url
        assert added_server.auth_token is None
        assert added_server.allowed_agents == allowed_agents
        assert added_server.owner_user_id == owner_user_id

    async def test_create_mcp_with_auth_token(self, mock_db):
        """
        Test creating an MCP server with an authentication token.

        This asynchronous unit test verifies that the `create_mcp` coroutine correctly stores the provided `auth_token` when a new MCP server is created. It uses a mocked database session (`mock_db`) to intercept the ORM `add` call and asserts that the resulting server instance contains the expected token.

        Args:
            self: The test case instance.
            mock_db: A mock object representing the database session, with `add` and other ORM methods patched.

        The test does not return a value; it raises an assertion error if the `auth_token` is not correctly persisted.
        """
        name = "Secure MCP"
        base_url = "https://mcp.example.com"
        auth_token = "bearer-token-12345"
        allowed_agents = ["agent1"]
        owner_user_id = 1

        result = await create_mcp(
            db=mock_db,
            name=name,
            base_url=base_url,
            auth_token=auth_token,
            allowed_agents=allowed_agents,
            owner_user_id=owner_user_id,
        )

        added_server = mock_db.add.call_args[0][0]
        assert added_server.auth_token == auth_token

    async def test_create_mcp_with_empty_allowed_agents(self, mock_db):
        """
        Test that creating an MCP server with an empty `allowed_agents` list stores the server correctly.

        The test invokes :func:`create_mcp` with:
        - `name` set to `"Open MCP"`,
        - `base_url` pointing to `http://localhost:8080`,
        - no authentication token,
        - an empty `allowed_agents` sequence,
        - `owner_user_id` equal to `1`.

        It then verifies that the server instance added to the mocked database has its `allowed_agents` attribute set to an empty list.
        """
        result = await create_mcp(
            db=mock_db,
            name="Open MCP",
            base_url="http://localhost:8080",
            auth_token=None,
            allowed_agents=[],
            owner_user_id=1,
        )

        added_server = mock_db.add.call_args[0][0]
        assert added_server.allowed_agents == []

    async def test_create_mcp_with_multiple_agents(self, mock_db):
        """
        Test that creating an MCP server with a list of allowed agents correctly stores all specified agents.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_db : unittest.mock.Mock
            A mocked database session providing `add` and other ORM methods.

        The test calls :func:`create_mcp` with a name, base URL, no authentication token, a list of four allowed agents, and an owner user ID. It then verifies that the server object added to the mock database contains exactly the provided agents, both in count and content.
        """
        allowed_agents = ["agent1", "agent2", "agent3", "agent4"]

        result = await create_mcp(
            db=mock_db,
            name="Multi-Agent MCP",
            base_url="http://localhost:8080",
            auth_token=None,
            allowed_agents=allowed_agents,
            owner_user_id=1,
        )

        added_server = mock_db.add.call_args[0][0]
        assert len(added_server.allowed_agents) == 4
        assert added_server.allowed_agents == allowed_agents


@pytest.mark.unit
class TestGetMCPByID:
    """Test get_mcp_by_id function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mocked asynchronous database session for use in tests.

        Returns:
            AsyncMock: A mock object simulating an async database session with all coroutine methods stubbed.
        """
        db = AsyncMock()
        return db

    async def test_get_mcp_by_id_found(self, mock_db):
        """
        Test that retrieving an existing MCPServer by its identifier returns the correct object.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        The function sets up a mock result where `scalars().first()` yields an expected MCPServer instance, invokes `get_mcp_by_id` with the mock session and server ID, and asserts that the returned value matches the expected server. It also verifies that the database execute method was called exactly once.
        """
        server_id = 1
        expected_server = MCPServer(
            server_id=server_id,
            name="Test MCP",
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = expected_server
        mock_db.execute.return_value = mock_result

        result = await get_mcp_by_id(mock_db, server_id)

        assert result == expected_server
        mock_db.execute.assert_called_once()

    async def test_get_mcp_by_id_not_found(self, mock_db):
        """
        Test that retrieving an MCP server by a non-existent ID returns `None` and that the database execute method is called exactly once. The mock database is configured to return no result for the query.\"""
        """
        server_id = 999

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_mcp_by_id(mock_db, server_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetMCPByName:
    """Test get_mcp_by_name function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns an asynchronous mock database session object suitable for use in tests. The returned AsyncMock can be configured to simulate database interactions such as queries, commits, and rollbacks. This helper isolates test cases from a real database by providing a lightweight, fully async-compatible mock.
        """
        db = AsyncMock()
        return db

    async def test_get_mcp_by_name_found(self, mock_db):
        """
        Test that `get_mcp_by_name` correctly retrieves an existing MCPServer instance when queried by its name.

        Args:
            self: The unittest.TestCase instance providing the test context.
            mock_db: A mocked asynchronous database session used to simulate the query execution.

        The test sets up a mock result so that `mock_db.execute` returns a scalar containing the expected `MCPServer` object. It then calls `get_mcp_by_name` with the mock session and verifies that:
        * The returned value matches the expected `MCPServer` instance.
        * The database `execute` method is invoked exactly once.
        """
        name = "Test MCP"
        expected_server = MCPServer(
            server_id=1,
            name=name,
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = expected_server
        mock_db.execute.return_value = mock_result

        result = await get_mcp_by_name(mock_db, name)

        assert result == expected_server
        mock_db.execute.assert_called_once()

    async def test_get_mcp_by_name_not_found(self, mock_db):
        """
        Test that `get_mcp_by_name` returns `None` when the requested MCP server does not exist in the database.

        Args:
            self: TestCase instance (unused but required by unittest framework).
            mock_db: A mocked asynchronous database session whose `execute` method is configured to return an empty result set.

        The test sets up a `MagicMock` to simulate a query that yields no rows, calls `get_mcp_by_name` with a non-existent name, and asserts that the function returns `None`. It also verifies that the database `execute` method was invoked exactly once.
        """
        name = "Nonexistent MCP"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_mcp_by_name(mock_db, name)

        assert result is None
        mock_db.execute.assert_called_once()

    async def test_get_mcp_by_name_case_sensitive(self, mock_db):
        """
        Test that retrieving an MCP by name is case-sensitive.

        Args:
            self: TestCase instance.
            mock_db: MagicMock representing a database session; its `execute` method is mocked to return no matching records.

        The test sets up `mock_db` so that a query for the name `"test mcp"` returns `None`, even though an MCP with the capitalised name `"Test MCP"` exists. It then calls :func:`get_mcp_by_name` with the lower-case name and asserts that `mock_db.execute` was invoked exactly once, confirming that the lookup does not perform case-insensitive matching.
        """
        # This tests the current behavior - names are case-sensitive
        name = "Test MCP"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        # Looking for different case should not find it
        result = await get_mcp_by_name(mock_db, "test mcp")

        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestListMCPServers:
    """Test list_mcp_servers function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session for use in tests.

        Args:
            self: Instance of the test case class; not used directly.

        Returns:
            AsyncMock: A mock object that mimics an async database session, allowing coroutine methods to be awaited without performing real I/O.
        """
        db = AsyncMock()
        return db

    async def test_list_mcp_servers_as_admin(self, mock_db):
        """
        Test that an admin user can retrieve the full list of MCPServer records.

        The test sets up two MCPServer instances and configures a mock database session to return them when executing a query. It then calls `list_mcp_servers` with `user_id=1` and `is_admin=True` and asserts that:

        * The returned collection contains exactly two items.
        * The returned collection matches the list of servers defined in the test.
        * The database session's `execute` method was invoked exactly once.

        Parameters
        ----------
        self: object
            The test case instance (unused within the function body).
        mock_db: MagicMock
            A mocked asynchronous database session whose `execute` method is patched to return a predetermined result set.
        """
        servers = [
            MCPServer(
                server_id=1,
                name="MCP 1",
                base_url="http://localhost:8080",
                allowed_agents=["agent1"],
                owner_user_id=1,
            ),
            MCPServer(
                server_id=2,
                name="MCP 2",
                base_url="http://localhost:8081",
                allowed_agents=["agent2"],
                owner_user_id=2,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = servers
        mock_db.execute.return_value = mock_result

        result = await list_mcp_servers(mock_db, user_id=1, is_admin=True)

        assert len(result) == 2
        assert result == servers
        mock_db.execute.assert_called_once()

    async def test_list_mcp_servers_as_regular_user(self, mock_db):
        """
        Test that a regular user receives only MCP servers they own when listing servers.

        Parameters:
            self: The test case instance.
            mock_db: A MagicMock representing the asynchronous database session used by `list_mcp_servers`.

        The test sets up a mock query result containing a single `MCPServer` owned by the user with ID 1, configures the mock database to return this result, and then calls `list_mcp_servers` with `user_id=1` and `is_admin=False`. It asserts that:
        * Exactly one server is returned.
        * The returned server's `owner_user_id` matches the requesting user's ID.
        * The database execute method was invoked exactly once.
        """
        user_id = 1
        user_servers = [
            MCPServer(
                server_id=1,
                name="User MCP",
                base_url="http://localhost:8080",
                allowed_agents=["agent1"],
                owner_user_id=user_id,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = user_servers
        mock_db.execute.return_value = mock_result

        result = await list_mcp_servers(mock_db, user_id=user_id, is_admin=False)

        assert len(result) == 1
        assert result[0].owner_user_id == user_id
        mock_db.execute.assert_called_once()

    async def test_list_mcp_servers_empty(self, mock_db):
        """
        Test that listing MCP servers returns an empty list when the database contains no server records, ensuring the function correctly handles the case of zero results and that the database execute method is invoked exactly once.
        """
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await list_mcp_servers(mock_db, user_id=1, is_admin=False)

        assert result == []
        mock_db.execute.assert_called_once()

    async def test_list_mcp_servers_no_user_id_as_admin(self, mock_db):
        """
        Test that an admin user can list all MCP servers when no specific user_id is provided.

        The test sets up a mock database session returning a single MCPServer instance and verifies that `list_mcp_servers` returns a list containing that server. It also asserts that the database execute method was called exactly once.
        """
        servers = [
            MCPServer(
                server_id=1,
                name="MCP 1",
                base_url="http://localhost:8080",
                allowed_agents=["agent1"],
                owner_user_id=1,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = servers
        mock_db.execute.return_value = mock_result

        result = await list_mcp_servers(mock_db, user_id=None, is_admin=True)

        assert len(result) == 1
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestUpdateMCP:
    """Test update_mcp function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mock asynchronous database session for use in tests.

        Returns:
            AsyncMock: A mock database session with async `commit` and `refresh` methods.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_update_mcp_single_field(self, mock_db):
        """
        Test that updating a single field of an MCPServer instance works correctly.

        The test creates a mock MCPServer object with initial values, patches the `get_mcp_by_id` function to return this object, and calls `update_mcp` with a new `name` value. It then verifies that:

        - The `name` attribute of the original `existing_server` instance has been updated to the provided value.
        - The database session's `commit` method was called exactly once.
        - The database session's `refresh` method was called exactly once.

        Parameters
        ----------
        self : object
            The test case instance (typically a subclass of `unittest.TestCase` or similar).
        mock_db : unittest.mock.Mock
            A mocked SQLAlchemy session providing `commit` and `refresh` methods used by the CRUD operation.
        """
        server_id = 1
        existing_server = MCPServer(
            server_id=server_id,
            name="Old Name",
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=existing_server):
            result = await update_mcp(
                db=mock_db,
                server_id=server_id,
                name="New Name",
            )

        assert existing_server.name == "New Name"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_update_mcp_multiple_fields(self, mock_db):
        """
        Test updating multiple fields of an MCPServer instance.

        This test verifies that calling :func:`update_mcp` with several optional parameters correctly modifies the corresponding attributes on the retrieved
        :class:`MCPServer` object.

        The test performs the following steps:
        - Creates a mock `MCPServer` instance with initial values.
        - Patches `app.crud.mcp_server.get_mcp_by_id` to return the mock instance when queried by `server_id`.
        - Calls :func:`update_mcp` with new values for `name`, `base_url` and `auth_token`.
        - Asserts that the mock server's `name`, `base_url` and `auth_token` attributes have been updated to the supplied values.
        """
        server_id = 1
        existing_server = MCPServer(
            server_id=server_id,
            name="Old Name",
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=existing_server):
            result = await update_mcp(
                db=mock_db,
                server_id=server_id,
                name="New Name",
                base_url="https://new-url.com",
                auth_token="new-token",
            )

        assert existing_server.name == "New Name"
        assert existing_server.base_url == "https://new-url.com"
        assert existing_server.auth_token == "new-token"

    async def test_update_mcp_not_found(self, mock_db):
        """
        Test that updating an MCP server that does not exist returns `None` and does not commit any changes to the database.

        Args:
            self: The test case instance.
            mock_db: A mocked SQLAlchemy session injected by the test fixture.

        The test patches `app.crud.mcp_server.get_mcp_by_id` to return `None`, simulating a missing MCP server with the given `server_id`. It then calls :func:`update_mcp` and asserts that the result is `None` and that `mock_db.commit` was never invoked.
        """
        server_id = 999

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=None):
            result = await update_mcp(
                db=mock_db,
                server_id=server_id,
                name="New Name",
            )

        assert result is None
        mock_db.commit.assert_not_called()

    async def test_update_mcp_ignores_none_values(self, mock_db):
        """
        Test that passing `None` for optional update parameters does not modify the corresponding fields of an existing :class:`MCPServer` instance.

        The test creates a mock `MCPServer` object with predefined attributes and patches
        :func:`app.crud.mcp_server.get_mcp_by_id` to return this object. It then calls
        :func:`update_mcp` with `name=None` (which should be ignored) and a new
        `base_url` value. After awaiting the coroutine, the test asserts that:

        * The `name` attribute remains unchanged ("Original Name").
        * The `base_url` attribute is updated to the provided non-`None` value
          ("https://new-url.com").

        Parameters
        ----------
        self: object
            Instance of the test case class (provided by the testing framework).
        mock_db: MagicMock
            Mocked database session injected by the fixture. Used as the `db`
            argument for :func:`update_mcp`.
        """
        server_id = 1
        existing_server = MCPServer(
            server_id=server_id,
            name="Original Name",
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=existing_server):
            result = await update_mcp(
                db=mock_db,
                server_id=server_id,
                name=None,  # Should not update
                base_url="https://new-url.com",  # Should update
            )

        assert existing_server.name == "Original Name"  # Unchanged
        assert existing_server.base_url == "https://new-url.com"  # Changed

    async def test_update_mcp_allowed_agents(self, mock_db):
        """
        Test that updating an MCPServer's `allowed_agents` field correctly replaces the existing list with a new set of agents using the `update_mcp` CRUD operation. The test creates a mock server instance, patches the retrieval function to return it, invokes `update_mcp` with a new agent list, and asserts that the server object's `allowed_agents` attribute matches the provided list.
        """
        server_id = 1
        existing_server = MCPServer(
            server_id=server_id,
            name="Test MCP",
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        new_agents = ["agent1", "agent2", "agent3"]

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=existing_server):
            result = await update_mcp(
                db=mock_db,
                server_id=server_id,
                allowed_agents=new_agents,
            )

        assert existing_server.allowed_agents == new_agents


@pytest.mark.unit
class TestDeleteMCP:
    """Test delete_mcp function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return an asynchronous mock database session with stubbed `delete` and `commit` methods.

        The returned object mimics an async SQLAlchemy session, allowing test code to await `delete` and `commit` calls without performing any real database operations. This facilitates isolated unit testing of CRUD functions that interact with a database session.
        """
        db = AsyncMock()
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_delete_mcp_success(self, mock_db):
        """
        Test that deleting an existing MCP server succeeds.\n\nThe test creates a mock MCPServer instance with a specific `server_id` and patches the `get_mcp_by_id` CRUD helper to return this instance. It then calls `delete_mcp` with a mocked database session and verifies that:\n\n- The function returns `True` indicating successful deletion.\n- The session's `delete` method is called exactly once with the retrieved server object.\n- The session's `commit` method is invoked exactly once to persist the change.
        """
        server_id = 1
        existing_server = MCPServer(
            server_id=server_id,
            name="Test MCP",
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=existing_server):
            result = await delete_mcp(mock_db, server_id)

        assert result is True
        mock_db.delete.assert_called_once_with(existing_server)
        mock_db.commit.assert_called_once()

    async def test_delete_mcp_not_found(self, mock_db):
        """
        Test that attempting to delete an MCP server that does not exist returns `False` and does not invoke any database deletion or commit operations. The test patches `app.crud.mcp_server.get_mcp_by_id` to simulate a missing record, calls `delete_mcp` with a mock session and a non-existent `server_id`, then asserts the result is `False` and verifies that `mock_db.delete` and `mock_db.commit` were never called.
        """
        server_id = 999

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=None):
            result = await delete_mcp(mock_db, server_id)

        assert result is False
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_called()


@pytest.mark.unit
class TestMCPServerCRUDEdgeCases:
    """Test edge cases for MCP server CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mock asynchronous database session suitable for testing.

        The returned object mimics the essential methods of an async SQLAlchemy session:
        - `add` is a regular `MagicMock` used to record added instances.
        - `commit` and `refresh` are `AsyncMock` objects that can be awaited in coroutine code.

        Returns
        -------
        AsyncMock
            A mock session with `add`, `commit` and `refresh` attributes configured for asynchronous use.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    async def test_create_mcp_with_unicode_name(self, mock_db):
        """
        Test that creating an MCP server with a Unicode name correctly stores the provided name in the database model. The test invokes `create_mcp` with a non-ASCII string for `name`, then verifies that the object passed to `mock_db.add` has its `name` attribute set to the same Unicode value. This ensures that the creation logic preserves Unicode characters without alteration.
        """
        name = "МCP Сервер 🚀"

        result = await create_mcp(
            db=mock_db,
            name=name,
            base_url="http://localhost:8080",
            auth_token=None,
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        added_server = mock_db.add.call_args[0][0]
        assert added_server.name == name

    async def test_create_mcp_with_special_chars_in_url(self, mock_db):
        """
        Test creating an MCP server when the provided base URL contains special characters such as query parameters.\n\nThe test constructs a sample URL with query strings, invokes `create_mcp` using a mocked database session, and verifies that the resulting MCP instance stored in the mock has its `base_url` attribute unchanged (i.e., exactly equal to the input string). This ensures that URLs with characters like `?`, `=`, and `&` are handled correctly during creation.\n\nArgs:\n    self: The test case instance (unused directly).\n    mock_db: A fixture providing a mocked database session with `add` and `commit` methods patched.\n\nThe function does not return a value; assertions validate the behavior.
        """
        base_url = "http://localhost:8080/api/v1/mcp?key=value&token=abc123"

        result = await create_mcp(
            db=mock_db,
            name="Test MCP",
            base_url=base_url,
            auth_token=None,
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        added_server = mock_db.add.call_args[0][0]
        assert added_server.base_url == base_url

    async def test_create_mcp_with_very_long_auth_token(self, mock_db):
        """
        Test that creating an MCP server with an exceptionally long authentication token succeeds and stores the full token.

        Args:
            self: TestCase instance.
            mock_db: Mocked database session injected via fixture.

        The test constructs a token consisting of the prefix `"bearer-"` followed by 1,000 `"x"` characters, calls :func:`create_mcp` with typical parameters, and then verifies that the `auth_token` attribute of the added server instance matches the long token. This ensures that the creation logic does not truncate or reject overly long tokens.
        """
        auth_token = "bearer-" + ("x" * 1000)

        result = await create_mcp(
            db=mock_db,
            name="Test MCP",
            base_url="http://localhost:8080",
            auth_token=auth_token,
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        added_server = mock_db.add.call_args[0][0]
        assert added_server.auth_token == auth_token

    async def test_create_mcp_with_many_allowed_agents(self, mock_db):
        """
        Test that creating an MCP server with a large list of allowed agents correctly stores all entries.

        Parameters:
            self: Test case instance (unused in the logic but required by the unittest method signature).
            mock_db: A mocked database session object whose `add` method is inspected to verify the created server.

        The test constructs a list of 100 agent identifiers, invokes `create_mcp` with these agents and other mandatory fields, then checks that the resulting server instance added to the mock session contains exactly 100 allowed agents. No explicit return value; assertions validate behavior.
        """
        allowed_agents = [f"agent{i}" for i in range(100)]

        result = await create_mcp(
            db=mock_db,
            name="Test MCP",
            base_url="http://localhost:8080",
            auth_token=None,
            allowed_agents=allowed_agents,
            owner_user_id=1,
        )

        added_server = mock_db.add.call_args[0][0]
        assert len(added_server.allowed_agents) == 100

    async def test_create_mcp_with_duplicate_agent_names(self, mock_db):
        """
        Test that creating an MCP server with a list containing duplicate agent names preserves those duplicates in the stored record.

        The test:
        - Supplies `allowed_agents` with repeated entries.
        - Calls the asynchronous `create_mcp` CRUD function using a mocked database session.
        - Retrieves the object passed to `mock_db.add`.
        - Asserts that the `allowed_agents` attribute of the added server matches the original list, confirming that the CRUD layer does not automatically deduplicate agent names (deduplication is expected to be handled at a higher application level).
        """
        allowed_agents = ["agent1", "agent1", "agent2", "agent2"]

        result = await create_mcp(
            db=mock_db,
            name="Test MCP",
            base_url="http://localhost:8080",
            auth_token=None,
            allowed_agents=allowed_agents,
            owner_user_id=1,
        )

        added_server = mock_db.add.call_args[0][0]
        # CRUD layer doesn't deduplicate - that's application logic
        assert added_server.allowed_agents == allowed_agents

    async def test_update_mcp_with_invalid_field(self, mock_db):
        """
        Test that attempting to update an MCPServer with a field name that does not exist is safely ignored; the operation completes without raising an exception, the returned result remains non-None, and the database session's commit method is called exactly once.
        """
        server_id = 1
        existing_server = MCPServer(
            server_id=server_id,
            name="Test MCP",
            base_url="http://localhost:8080",
            allowed_agents=["agent1"],
            owner_user_id=1,
        )

        with patch("app.crud.mcp_server.get_mcp_by_id", return_value=existing_server):
            # Try to update a field that doesn't exist
            result = await update_mcp(
                db=mock_db,
                server_id=server_id,
                nonexistent_field="value",
            )

        # Should not raise error, just ignore invalid field
        assert result is not None
        mock_db.commit.assert_called_once()
