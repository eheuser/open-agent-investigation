# api/tests/unit/routers/test_tags.py
import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.models import User, Investigation


@pytest.mark.asyncio
async def test_add_node_tags_deprecated(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test that add_node_tags returns 410 (deprecated)."""
    response = await async_client.post(
        f"/api/v1/tags/nodes/{test_investigation.investigation_id}/1",
        json=["tag1", "tag2"],
        headers=auth_headers
    )
    
    assert response.status_code == 410
    assert "deprecated" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_node_tags_deprecated(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test that remove_node_tags returns 410 (deprecated)."""
    response = await async_client.delete(
        f"/api/v1/tags/nodes/{test_investigation.investigation_id}/1",
        headers=auth_headers
    )
    
    assert response.status_code == 410
    assert "deprecated" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_add_edge_tags_deprecated(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test that add_edge_tags returns 410 (deprecated)."""
    response = await async_client.post(
        f"/api/v1/tags/edges/{test_investigation.investigation_id}/1",
        json=["tag1", "tag2"],
        headers=auth_headers
    )
    
    assert response.status_code == 410
    assert "deprecated" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_edge_tags_deprecated(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test that remove_edge_tags returns 410 (deprecated)."""
    response = await async_client.delete(
        f"/api/v1/tags/edges/{test_investigation.investigation_id}/1",
        headers=auth_headers
    )
    
    assert response.status_code == 410
    assert "deprecated" in response.json()["detail"].lower()
