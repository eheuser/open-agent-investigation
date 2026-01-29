# api/tests/unit/routers/test_investigations.py
import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.models import User, Investigation


@pytest.mark.asyncio
async def test_create_investigation(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating a new investigation."""
    payload = {"title": "Test Investigation"}
    
    response = await async_client.post(
        "/api/v1/investigations/",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Investigation"
    assert "investigation_id" in data
    assert "owner_user_id" in data


@pytest.mark.asyncio
async def test_list_investigations(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test listing investigations."""
    response = await async_client.get(
        "/api/v1/investigations/",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Find our test investigation
    found = any(inv["investigation_id"] == str(test_investigation.investigation_id) for inv in data)
    assert found


@pytest.mark.asyncio
async def test_get_investigation(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test getting a specific investigation."""
    response = await async_client.get(
        f"/api/v1/investigations/{test_investigation.investigation_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["investigation_id"] == str(test_investigation.investigation_id)
    assert data["title"] == test_investigation.title


@pytest.mark.asyncio
async def test_get_investigation_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test getting non-existent investigation."""
    fake_uuid = uuid4()
    response = await async_client.get(
        f"/api/v1/investigations/{fake_uuid}",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_investigation_access_control(
    async_client: AsyncClient,
    test_investigation: Investigation,
    db_session,
):
    """Test that investigation has proper ownership."""
    # Verify the investigation belongs to test_user
    from app.models import Investigation as InvModel
    from sqlalchemy import select
    
    result = await db_session.execute(
        select(InvModel).where(InvModel.investigation_id == test_investigation.investigation_id)
    )
    inv = result.scalar_one()
    
    # Verify it has an owner
    assert inv.owner_user_id is not None
    # Verify owner matches test_investigation
    assert inv.owner_user_id == test_investigation.owner_user_id


@pytest.mark.asyncio
async def test_update_investigation(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test updating investigation title."""
    payload = {"title": "Updated Title"}
    
    response = await async_client.patch(
        f"/api/v1/investigations/{test_investigation.investigation_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["investigation_id"] == str(test_investigation.investigation_id)


@pytest.mark.asyncio
async def test_update_investigation_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test updating non-existent investigation."""
    fake_uuid = uuid4()
    payload = {"title": "Updated"}
    
    response = await async_client.patch(
        f"/api/v1/investigations/{fake_uuid}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_investigation(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test deleting an investigation."""
    response = await async_client.delete(
        f"/api/v1/investigations/{test_investigation.investigation_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_investigation_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test deleting non-existent investigation."""
    fake_uuid = uuid4()
    
    response = await async_client.delete(
        f"/api/v1/investigations/{fake_uuid}",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_investigation_unauthorized(
    async_client: AsyncClient
):
    """Test that creating investigation requires authentication."""
    payload = {"title": "Test"}
    
    response = await async_client.post(
        "/api/v1/investigations/",
        json=payload
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_investigations_unauthorized(
    async_client: AsyncClient
):
    """Test that listing investigations requires authentication."""
    response = await async_client.get("/api/v1/investigations/")
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_investigation_with_long_title(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating investigation with a long title."""
    long_title = "A" * 200
    payload = {"title": long_title}
    
    response = await async_client.post(
        "/api/v1/investigations/",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == long_title


@pytest.mark.asyncio
async def test_update_investigation_short_title(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test updating investigation with a short title."""
    payload = {"title": "A"}
    
    response = await async_client.patch(
        f"/api/v1/investigations/{test_investigation.investigation_id}",
        json=payload,
        headers=auth_headers
    )
    
    # Should succeed - short titles are allowed
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "A"


@pytest.mark.asyncio
async def test_list_investigations_multiple(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test listing multiple investigations."""
    from app.crud.investigation import create_investigation
    
    # Create additional investigations
    inv1 = await create_investigation(db_session, title="Investigation 1", owner_user_id=test_user.user_id)
    inv2 = await create_investigation(db_session, title="Investigation 2", owner_user_id=test_user.user_id)
    
    response = await async_client.get(
        "/api/v1/investigations/",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    
    titles = {inv["title"] for inv in data}
    assert "Investigation 1" in titles
    assert "Investigation 2" in titles
