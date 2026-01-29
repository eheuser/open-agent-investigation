# api/tests/unit/routers/test_mcp.py
import pytest
from httpx import AsyncClient

from app.models import User, MCPServer


@pytest.mark.asyncio
async def test_create_mcp_server(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating an MCP server."""
    payload = {
        "name": "Test MCP",
        "base_url": "http://localhost:8000",
        "auth_token": "test-token",
        "allowed_agents": ["agent1", "agent2"]
    }
    
    response = await async_client.post(
        "/api/v1/mcp/",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test MCP"
    assert data["base_url"] == "http://localhost:8000"
    assert data["allowed_agents"] == ["agent1", "agent2"]
    assert "server_id" in data


@pytest.mark.asyncio
async def test_list_mcp_servers(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test listing MCP servers."""
    # Create test servers
    server1 = MCPServer(
        owner_user_id=test_user.user_id,
        name="Server 1",
        base_url="http://server1.com",
        auth_token="token1",
        allowed_agents=["agent1"]
    )
    server2 = MCPServer(
        owner_user_id=test_user.user_id,
        name="Server 2",
        base_url="http://server2.com",
        auth_token="token2",
        allowed_agents=["agent2"]
    )
    
    db_session.add_all([server1, server2])
    await db_session.commit()
    
    response = await async_client.get(
        "/api/v1/mcp/",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    names = {s["name"] for s in data}
    assert "Server 1" in names
    assert "Server 2" in names


@pytest.mark.asyncio
async def test_get_mcp_server(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test getting a specific MCP server."""
    server = MCPServer(
        owner_user_id=test_user.user_id,
        name="Test Server",
        base_url="http://test.com",
        auth_token="token",
        allowed_agents=["agent"]
    )
    
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    
    response = await async_client.get(
        f"/api/v1/mcp/{server.server_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Server"
    assert data["server_id"] == server.server_id


@pytest.mark.asyncio
async def test_get_mcp_server_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test getting non-existent MCP server."""
    response = await async_client.get(
        "/api/v1/mcp/999999",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_mcp_server_forbidden(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test that non-owner cannot access another user's server."""
    # Create another user
    other_user = User(
        username="other_mcp_user",
        password_hash="hash",
        role=0
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    # Create server owned by other_user
    server = MCPServer(
        owner_user_id=other_user.user_id,
        name="Other's Server",
        base_url="http://other.com",
        auth_token="token",
        allowed_agents=[]
    )
    
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    
    # Try to access as test_user
    response = await async_client.get(
        f"/api/v1/mcp/{server.server_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 403
    assert "denied" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_mcp_server(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test updating an MCP server."""
    server = MCPServer(
        owner_user_id=test_user.user_id,
        name="Original Name",
        base_url="http://original.com",
        auth_token="token",
        allowed_agents=["agent1"]
    )
    
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    
    payload = {
        "name": "Updated Name",
        "base_url": "http://updated.com",
        "allowed_agents": ["agent1", "agent2", "agent3"]
    }
    
    response = await async_client.patch(
        f"/api/v1/mcp/{server.server_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["base_url"] == "http://updated.com"
    assert len(data["allowed_agents"]) == 3


@pytest.mark.asyncio
async def test_update_mcp_server_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test updating non-existent server."""
    payload = {"name": "Updated"}
    
    response = await async_client.patch(
        "/api/v1/mcp/999999",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_mcp_server_forbidden(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test that non-owner cannot update another user's server."""
    other_user = User(
        username="other_update_user",
        password_hash="hash",
        role=0
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    server = MCPServer(
        owner_user_id=other_user.user_id,
        name="Other's Server",
        base_url="http://other.com",
        auth_token="token",
        allowed_agents=[]
    )
    
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    
    payload = {"name": "Hacked"}
    
    response = await async_client.patch(
        f"/api/v1/mcp/{server.server_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_mcp_server(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test deleting an MCP server."""
    server = MCPServer(
        owner_user_id=test_user.user_id,
        name="To Delete",
        base_url="http://delete.com",
        auth_token="token",
        allowed_agents=[]
    )
    
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    
    response = await async_client.delete(
        f"/api/v1/mcp/{server.server_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_mcp_server_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test deleting non-existent server."""
    response = await async_client.delete(
        "/api/v1/mcp/999999",
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_mcp_server_forbidden(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test that non-owner cannot delete another user's server."""
    other_user = User(
        username="other_delete_user",
        password_hash="hash",
        role=0
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    server = MCPServer(
        owner_user_id=other_user.user_id,
        name="Other's Server",
        base_url="http://other.com",
        auth_token="token",
        allowed_agents=[]
    )
    
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    
    response = await async_client.delete(
        f"/api/v1/mcp/{server.server_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_mcp_server_unauthorized(
    async_client: AsyncClient
):
    """Test that creating MCP server requires authentication."""
    payload = {
        "name": "Test",
        "base_url": "http://test.com",
        "auth_token": "token",
        "allowed_agents": []
    }
    
    response = await async_client.post(
        "/api/v1/mcp/",
        json=payload
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_mcp_server_partial(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test partial update of MCP server."""
    server = MCPServer(
        owner_user_id=test_user.user_id,
        name="Original",
        base_url="http://original.com",
        auth_token="token",
        allowed_agents=["agent1"]
    )
    
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    
    # Only update name
    payload = {"name": "New Name"}
    
    response = await async_client.patch(
        f"/api/v1/mcp/{server.server_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["base_url"] == "http://original.com"  # Unchanged
