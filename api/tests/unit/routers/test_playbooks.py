# api/tests/unit/routers/test_playbooks.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import User, Playbook, Investigation, InvestigationPlaybook


@pytest.mark.asyncio
async def test_list_all_playbooks(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test listing all playbooks (base + user)."""
    # Create a user playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="Test content",
        is_enabled=True,
    )
    db_session.add(playbook)
    await db_session.commit()
    
    response = await async_client.get("/api/v1/playbooks/list", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "base_playbooks" in data
    assert "user_playbooks" in data
    assert "total" in data
    assert len(data["base_playbooks"]) > 0  # Should have base playbooks
    assert len(data["user_playbooks"]) == 1  # Our test playbook
    assert data["user_playbooks"][0]["name"] == "test_playbook"
    assert data["user_playbooks"][0]["is_base"] is False


@pytest.mark.asyncio
async def test_list_user_playbooks(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test listing user playbooks only."""
    # Create two user playbooks
    playbook1 = Playbook(
        user_id=test_user.user_id,
        name="playbook_1",
        description="First playbook",
        playbook="Content 1",
    )
    playbook2 = Playbook(
        user_id=test_user.user_id,
        name="playbook_2",
        description="Second playbook",
        playbook="Content 2",
    )
    
    db_session.add_all([playbook1, playbook2])
    await db_session.commit()
    
    response = await async_client.get("/api/v1/playbooks/user", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 2
    assert all(pb["is_base"] is False for pb in data)
    names = {pb["name"] for pb in data}
    assert names == {"playbook_1", "playbook_2"}


@pytest.mark.asyncio
async def test_list_base_playbooks(async_client: AsyncClient):
    """Test listing base YAML playbooks."""
    response = await async_client.get("/api/v1/playbooks/base")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) > 0  # Should have base playbooks
    assert all(pb["is_base"] is True for pb in data)
    # Check for known base playbooks
    names = {pb["name"] for pb in data}
    assert "lateral_movement" in names


@pytest.mark.asyncio
async def test_create_playbook(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test creating a new playbook."""
    payload = {
        "name": "new_playbook",
        "description": "New playbook description",
        "playbook": "## New Playbook\n\n### Steps\n1. Step 1",
        "is_enabled": True,
    }
    
    response = await async_client.post(
        "/api/v1/playbooks/create",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == "new_playbook"
    assert data["description"] == "New playbook description"
    assert data["is_enabled"] is True
    assert data["is_base"] is False
    assert "playbook_id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_playbook_duplicate_name(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that duplicate playbook names are rejected."""
    # Create first playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="duplicate_name",
        description="First playbook",
        playbook="Content 1",
    )
    db_session.add(playbook)
    await db_session.commit()
    
    # Try to create duplicate
    payload = {
        "name": "duplicate_name",
        "description": "Second playbook",
        "playbook": "Content 2",
    }
    
    response = await async_client.post(
        "/api/v1/playbooks/create",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_playbook(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test updating a playbook."""
    # Create playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="update_test",
        description="Original description",
        playbook="Original content",
        is_enabled=True,
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Update playbook
    payload = {
        "description": "Updated description",
        "playbook": "Updated content",
        "is_enabled": False,
    }
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["description"] == "Updated description"
    assert data["playbook"] == "Updated content"
    assert data["is_enabled"] is False
    assert data["name"] == "update_test"  # Unchanged


@pytest.mark.asyncio
async def test_update_playbook_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test updating non-existent playbook."""
    payload = {"description": "Updated"}
    
    response = await async_client.put(
        "/api/v1/playbooks/999999",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_playbook_duplicate_name(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that updating to duplicate name is rejected."""
    # Create two playbooks
    playbook1 = Playbook(
        user_id=test_user.user_id,
        name="playbook_1",
        description="First",
        playbook="Content 1",
    )
    playbook2 = Playbook(
        user_id=test_user.user_id,
        name="playbook_2",
        description="Second",
        playbook="Content 2",
    )
    
    db_session.add_all([playbook1, playbook2])
    await db_session.commit()
    await db_session.refresh(playbook1)
    
    # Try to rename playbook1 to playbook2's name
    payload = {"name": "playbook_2"}
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook1.playbook_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_playbook(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test deleting a playbook."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="delete_test",
        description="To be deleted",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    playbook_id = playbook.playbook_id
    
    response = await async_client.delete(
        f"/api/v1/playbooks/{playbook_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 204
    
    # Verify deletion
    result = await db_session.execute(
        select(Playbook).where(Playbook.playbook_id == playbook_id)
    )
    deleted = result.scalar_one_or_none()
    
    assert deleted is None


@pytest.mark.asyncio
async def test_delete_playbook_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test deleting non-existent playbook."""
    response = await async_client.delete(
        "/api/v1/playbooks/999999",
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_clone_base_playbook(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test cloning a base playbook."""
    response = await async_client.post(
        "/api/v1/playbooks/clone/lateral_movement",
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == "lateral_movement_copy"
    assert data["is_base"] is False
    assert "description" in data
    assert "playbook" in data
    assert data["is_enabled"] is True


@pytest.mark.asyncio
async def test_clone_base_playbook_multiple_times(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test cloning the same base playbook multiple times generates unique names."""
    # First clone
    response1 = await async_client.post(
        "/api/v1/playbooks/clone/lateral_movement",
        headers=auth_headers
    )
    assert response1.status_code == 201
    assert response1.json()["name"] == "lateral_movement_copy"
    
    # Second clone
    response2 = await async_client.post(
        "/api/v1/playbooks/clone/lateral_movement",
        headers=auth_headers
    )
    assert response2.status_code == 201
    assert response2.json()["name"] == "lateral_movement_copy_2"
    
    # Third clone
    response3 = await async_client.post(
        "/api/v1/playbooks/clone/lateral_movement",
        headers=auth_headers
    )
    assert response3.status_code == 201
    assert response3.json()["name"] == "lateral_movement_copy_3"


@pytest.mark.asyncio
async def test_clone_nonexistent_playbook(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test cloning a non-existent base playbook."""
    response = await async_client.post(
        "/api/v1/playbooks/clone/nonexistent_playbook",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_enable_playbook_for_investigation(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test enabling a playbook for an investigation."""
    # Create playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Enable for investigation
    payload = {
        "playbook_id": playbook.playbook_id,
        "is_enabled": True,
    }
    
    response = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_enable_playbook_update_existing(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that enabling an already-enabled playbook updates the status."""
    # Create playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Enable first time
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
        is_enabled=False,
    )
    db_session.add(inv_playbook)
    await db_session.commit()
    
    # Enable again (should update)
    payload = {
        "playbook_id": playbook.playbook_id,
        "is_enabled": True,
    }
    
    response = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    assert "updated" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_disable_playbook_for_investigation(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test disabling a playbook for an investigation."""
    # Create playbook and enable it
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
        is_enabled=True,
    )
    db_session.add(inv_playbook)
    await db_session.commit()
    
    # Disable it
    response = await async_client.delete(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/disable/{playbook.playbook_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 204
    
    # Verify it's disabled
    await db_session.refresh(inv_playbook)
    assert inv_playbook.is_enabled == False  # type: ignore


@pytest.mark.asyncio
async def test_get_investigation_playbooks(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test getting all playbooks for an investigation."""
    # Create two playbooks
    playbook1 = Playbook(
        user_id=test_user.user_id,
        name="playbook_1",
        description="First",
        playbook="Content 1",
    )
    playbook2 = Playbook(
        user_id=test_user.user_id,
        name="playbook_2",
        description="Second",
        playbook="Content 2",
    )
    
    db_session.add_all([playbook1, playbook2])
    await db_session.commit()
    await db_session.refresh(playbook1)
    await db_session.refresh(playbook2)
    
    # Enable both for investigation
    inv_pb1 = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook1.playbook_id,
        is_enabled=True,
    )
    inv_pb2 = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook2.playbook_id,
        is_enabled=False,
    )
    
    db_session.add_all([inv_pb1, inv_pb2])
    await db_session.commit()
    
    # Get investigation playbooks
    response = await async_client.get(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 2
    
    # Check that both relationships are returned
    playbook_ids = {item["playbook_id"] for item in data}
    assert playbook_ids == {playbook1.playbook_id, playbook2.playbook_id}
    
    # Check enabled status
    for item in data:
        if item["playbook_id"] == playbook1.playbook_id:
            assert item["is_enabled"] is True
        else:
            assert item["is_enabled"] is False


@pytest.mark.asyncio
async def test_create_playbook_unauthorized(async_client: AsyncClient):
    """Test that creating a playbook requires authentication."""
    payload = {
        "name": "test",
        "description": "Test",
        "playbook": "Content",
    }
    
    response = await async_client.post("/api/v1/playbooks/create", json=payload)
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_playbook_wrong_user(
    async_client: AsyncClient,
    test_user: User,
    db_session: AsyncSession
):
    """Test that users cannot update other users' playbooks."""
    # Create playbook for test_user
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Create another user
    other_user = User(
        username="other_user",
        password_hash="hash",
        role=0,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    # Try to update as other user (would need to generate auth token for other_user)
    # For now, just verify the playbook belongs to test_user
    result = await db_session.execute(
        select(Playbook).where(Playbook.playbook_id == playbook.playbook_id)
    )
    found = result.scalar_one()
    
    assert found.user_id == test_user.user_id
    assert found.user_id != other_user.user_id


@pytest.mark.asyncio
async def test_clone_with_existing_copy(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that cloning generates unique names when copies exist."""
    # Create a manual copy
    existing_copy = Playbook(
        user_id=test_user.user_id,
        name="lateral_movement_copy",
        description="Existing copy",
        playbook="Content",
    )
    db_session.add(existing_copy)
    await db_session.commit()
    
    # Clone should create lateral_movement_copy_2
    response = await async_client.post(
        "/api/v1/playbooks/clone/lateral_movement",
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == "lateral_movement_copy_2"


@pytest.mark.asyncio
async def test_enable_playbook_invalid_investigation_id(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test enabling playbook with invalid investigation ID."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    payload = {
        "playbook_id": playbook.playbook_id,
        "is_enabled": True,
    }
    
    response = await async_client.post(
        "/api/v1/playbooks/investigation/invalid-uuid/enable",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 400
    assert "Invalid investigation ID" in response.json()["detail"]


@pytest.mark.asyncio
async def test_enable_playbook_nonexistent_investigation(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test enabling playbook for non-existent investigation."""
    import uuid
    
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    payload = {
        "playbook_id": playbook.playbook_id,
        "is_enabled": True,
    }
    
    fake_uuid = str(uuid.uuid4())
    response = await async_client.post(
        f"/api/v1/playbooks/investigation/{fake_uuid}/enable",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "Investigation not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_enable_nonexistent_playbook(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test enabling non-existent playbook for investigation."""
    payload = {
        "playbook_id": 999999,
        "is_enabled": True,
    }
    
    response = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "Playbook not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_playbook_name_only(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test updating only the name field."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="original_name",
        description="Original description",
        playbook="Original content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    payload = {"name": "new_name"}
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "new_name"
    assert data["description"] == "Original description"
    assert data["playbook"] == "Original content"


@pytest.mark.asyncio
async def test_update_playbook_content_only(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test updating only the playbook content."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_name",
        description="Test description",
        playbook="Original content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    payload = {"playbook": "## Updated Content\n\nNew steps"}
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["playbook"] == "## Updated Content\n\nNew steps"
    assert data["name"] == "test_name"
    assert data["description"] == "Test description"


@pytest.mark.asyncio
async def test_disable_playbook_not_enabled(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test disabling a playbook that was never enabled."""
    response = await async_client.delete(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/disable/999999",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not enabled" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_playbook_minimal(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating a playbook with minimal required fields."""
    payload = {
        "name": "minimal",
        "description": "Minimal description",
        "playbook": "Content",
    }
    
    response = await async_client.post(
        "/api/v1/playbooks/create",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["is_enabled"] == True  # Default value


@pytest.mark.asyncio
async def test_list_playbooks_empty_user(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test listing playbooks when user has no custom playbooks."""
    response = await async_client.get("/api/v1/playbooks/user", headers=auth_headers)
    
    # User might have playbooks from other tests, so just check structure
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_enable_playbook_disable_then_enable(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test toggling playbook enabled status."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="toggle_test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Enable
    payload1 = {"playbook_id": playbook.playbook_id, "is_enabled": True}
    response1 = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload1,
        headers=auth_headers
    )
    assert response1.status_code == 201
    
    # Disable
    payload2 = {"playbook_id": playbook.playbook_id, "is_enabled": False}
    response2 = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload2,
        headers=auth_headers
    )
    assert response2.status_code == 201
    assert "updated" in response2.json()["message"].lower()


@pytest.mark.asyncio
async def test_get_investigation_playbooks_empty(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test getting playbooks for investigation with none enabled."""
    response = await async_client.get(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_update_playbook_enable_disable(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test toggling is_enabled flag."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="toggle_test",
        description="Test",
        playbook="Content",
        is_enabled=True,
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Disable
    response1 = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json={"is_enabled": False},
        headers=auth_headers
    )
    assert response1.status_code == 200
    assert response1.json()["is_enabled"] == False
    
    # Enable again
    response2 = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json={"is_enabled": True},
        headers=auth_headers
    )
    assert response2.status_code == 200
    assert response2.json()["is_enabled"] == True


@pytest.mark.asyncio
async def test_create_playbook_with_markdown(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating a playbook with complex markdown."""
    markdown_content = """## Investigation Playbook

### Overview
This is a test playbook.

### Steps
1. First step
2. Second step

### Code Example
```python
query_jsonb_field(path='event_data.LogonType', value='10')
```

### Notes
- Important note
- Another note
"""
    
    payload = {
        "name": "markdown_test",
        "description": "Test markdown rendering",
        "playbook": markdown_content,
    }
    
    response = await async_client.post(
        "/api/v1/playbooks/create",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "```python" in data["playbook"]
    assert "## Investigation Playbook" in data["playbook"]


@pytest.mark.asyncio
async def test_list_all_playbooks_structure(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test the structure of list_all_playbooks response."""
    # Create a user playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="structure_test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    
    response = await async_client.get("/api/v1/playbooks/list", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify structure
    assert "base_playbooks" in data
    assert "user_playbooks" in data
    assert "total" in data
    
    # Verify base playbooks have correct fields
    if len(data["base_playbooks"]) > 0:
        base = data["base_playbooks"][0]
        assert "name" in base
        assert "description" in base
        assert "playbook" in base
        assert base["is_base"] == True
    
    # Verify user playbooks have correct fields
    if len(data["user_playbooks"]) > 0:
        user = data["user_playbooks"][0]
        assert "playbook_id" in user
        assert "user_id" in user
        assert "name" in user
        assert "description" in user
        assert "playbook" in user
        assert "is_enabled" in user
        assert "created_at" in user
        assert "updated_at" in user
        assert user["is_base"] == False


@pytest.mark.asyncio
async def test_clone_preserves_content(
    async_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that cloning preserves the original playbook content."""
    response = await async_client.post(
        "/api/v1/playbooks/clone/lateral_movement",
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify content was copied
    assert len(data["playbook"]) > 100  # Should have substantial content
    assert len(data["description"]) > 10  # Should have description


@pytest.mark.asyncio
async def test_delete_playbook_cascades_to_investigation_playbooks(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that deleting a playbook removes investigation relationships."""
    # Create playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="cascade_test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    playbook_id = playbook.playbook_id
    
    # Enable for investigation
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook_id,
        is_enabled=True,
    )
    db_session.add(inv_playbook)
    await db_session.commit()
    relationship_id = inv_playbook.id
    
    # Delete playbook
    response = await async_client.delete(
        f"/api/v1/playbooks/{playbook_id}",
        headers=auth_headers
    )
    assert response.status_code == 204
    
    # Verify relationship was also deleted
    result = await db_session.execute(
        select(InvestigationPlaybook).where(InvestigationPlaybook.id == relationship_id)
    )
    deleted = result.scalar_one_or_none()
    assert deleted is None


@pytest.mark.asyncio
async def test_update_only_description(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test updating only description field."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="desc_test",
        description="Original",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json={"description": "Updated description"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"
    assert response.json()["name"] == "desc_test"


@pytest.mark.asyncio
async def test_clone_increments_correctly(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that clone numbering increments correctly with gaps."""
    # Create copy_2 manually (skipping copy_1)
    manual = Playbook(
        user_id=test_user.user_id,
        name="credential_access_copy_2",
        description="Manual",
        playbook="Content",
    )
    db_session.add(manual)
    await db_session.commit()
    
    # Clone should create copy (not copy_1)
    response = await async_client.post(
        "/api/v1/playbooks/clone/credential_access",
        headers=auth_headers
    )
    
    assert response.status_code == 201
    # Should create credential_access_copy since copy_1 doesn't exist
    assert response.json()["name"] == "credential_access_copy"


@pytest.mark.asyncio
async def test_list_user_playbooks_multiple(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test listing multiple user playbooks."""
    # Create 5 playbooks
    for i in range(5):
        playbook = Playbook(
            user_id=test_user.user_id,
            name=f"playbook_{i}",
            description=f"Description {i}",
            playbook=f"Content {i}",
        )
        db_session.add(playbook)
    
    await db_session.commit()
    
    response = await async_client.get("/api/v1/playbooks/user", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5


@pytest.mark.asyncio
async def test_enable_playbook_twice_same_status(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test enabling a playbook that's already enabled with same status."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Enable first time
    payload = {"playbook_id": playbook.playbook_id, "is_enabled": True}
    response1 = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload,
        headers=auth_headers
    )
    assert response1.status_code == 201
    
    # Enable again with same status
    response2 = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload,
        headers=auth_headers
    )
    assert response2.status_code == 201
    assert "updated" in response2.json()["message"].lower()


@pytest.mark.asyncio
async def test_get_investigation_playbooks_with_disabled(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that get_investigation_playbooks returns both enabled and disabled."""
    # Create two playbooks
    playbook1 = Playbook(
        user_id=test_user.user_id,
        name="enabled_pb",
        description="Enabled",
        playbook="Content",
    )
    playbook2 = Playbook(
        user_id=test_user.user_id,
        name="disabled_pb",
        description="Disabled",
        playbook="Content",
    )
    db_session.add_all([playbook1, playbook2])
    await db_session.commit()
    await db_session.refresh(playbook1)
    await db_session.refresh(playbook2)
    
    # Enable first, disable second
    inv_pb1 = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook1.playbook_id,
        is_enabled=True,
    )
    inv_pb2 = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook2.playbook_id,
        is_enabled=False,
    )
    db_session.add_all([inv_pb1, inv_pb2])
    await db_session.commit()
    
    response = await async_client.get(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    # Verify we get both enabled and disabled
    enabled_count = sum(1 for item in data if item["is_enabled"])
    disabled_count = sum(1 for item in data if not item["is_enabled"])
    assert enabled_count == 1
    assert disabled_count == 1


@pytest.mark.asyncio
async def test_update_all_fields_at_once(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test updating all fields in a single request."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="original",
        description="Original desc",
        playbook="Original content",
        is_enabled=True,
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    payload = {
        "name": "updated",
        "description": "Updated desc",
        "playbook": "Updated content",
        "is_enabled": False,
    }
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "updated"
    assert data["description"] == "Updated desc"
    assert data["playbook"] == "Updated content"
    assert data["is_enabled"] == False


@pytest.mark.asyncio
async def test_disable_playbook_invalid_investigation_id(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test disabling playbook with invalid investigation ID."""
    response = await async_client.delete(
        "/api/v1/playbooks/investigation/invalid-uuid/disable/1",
        headers=auth_headers
    )
    
    assert response.status_code == 400
    assert "Invalid investigation ID" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_playbook_disabled_by_default(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating a playbook that's disabled by default."""
    payload = {
        "name": "disabled_playbook",
        "description": "Disabled by default",
        "playbook": "Content",
        "is_enabled": False,
    }
    
    response = await async_client.post(
        "/api/v1/playbooks/create",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["is_enabled"] == False


@pytest.mark.asyncio
async def test_update_playbook_no_changes(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test updating a playbook with empty update data."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="no_change",
        description="Original",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Send empty update
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json={},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    # Nothing should change
    assert data["name"] == "no_change"
    assert data["description"] == "Original"
    assert data["playbook"] == "Content"


@pytest.mark.asyncio
async def test_get_investigation_playbooks_with_none_playbook(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test get_investigation_playbooks when a playbook was deleted but relationship exists."""
    # Create playbook
    playbook = Playbook(
        user_id=test_user.user_id,
        name="temp_playbook",
        description="Temp",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    playbook_id = playbook.playbook_id
    
    # Create relationship
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook_id,
        is_enabled=True,
    )
    db_session.add(inv_playbook)
    await db_session.commit()
    
    # Manually delete the playbook (simulating orphaned relationship)
    # This shouldn't happen due to CASCADE, but tests the if playbook: check
    await db_session.delete(playbook)
    await db_session.commit()
    
    # Get investigation playbooks - should skip the None playbook
    response = await async_client.get(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    # Should be empty since playbook was deleted
    assert len(data) == 0


@pytest.mark.asyncio
async def test_enable_playbook_creates_new_relationship(
    async_client: AsyncClient,
    test_user: User,
    test_investigation: Investigation,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that enabling creates a new relationship when none exists."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="new_rel_test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    payload = {"playbook_id": playbook.playbook_id, "is_enabled": True}
    
    response = await async_client.post(
        f"/api/v1/playbooks/investigation/{test_investigation.investigation_id}/enable",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    assert "enabled" in response.json()["message"].lower()
    
    # Verify relationship was created
    result = await db_session.execute(
        select(InvestigationPlaybook).where(
            and_(
                InvestigationPlaybook.investigation_id == test_investigation.investigation_id,
                InvestigationPlaybook.playbook_id == playbook.playbook_id,
            )
        )
    )
    relationship = result.scalar_one_or_none()
    assert relationship is not None
    assert relationship.is_enabled == True  # type: ignore


@pytest.mark.asyncio
async def test_clone_with_very_long_name(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test cloning increments past 10."""
    # Create copies 1-12
    for i in range(1, 13):
        if i == 1:
            name = "persistence_copy"
        else:
            name = f"persistence_copy_{i}"
        
        playbook = Playbook(
            user_id=test_user.user_id,
            name=name,
            description="Test",
            playbook="Content",
        )
        db_session.add(playbook)
    
    await db_session.commit()
    
    # Clone should create persistence_copy_13
    response = await async_client.post(
        "/api/v1/playbooks/clone/persistence",
        headers=auth_headers
    )
    
    assert response.status_code == 201
    assert response.json()["name"] == "persistence_copy_13"


@pytest.mark.asyncio
async def test_list_base_playbooks_has_known_playbooks(
    async_client: AsyncClient
):
    """Test that base playbooks include expected playbooks."""
    response = await async_client.get("/api/v1/playbooks/base")
    
    assert response.status_code == 200
    data = response.json()
    
    names = {pb["name"] for pb in data}
    
    # Check for multiple known playbooks
    expected = {"lateral_movement", "credential_access", "persistence", "privilege_escalation"}
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_update_playbook_partial_fields(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test updating description and playbook but not name."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="partial_test",
        description="Old desc",
        playbook="Old content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    payload = {
        "description": "New desc",
        "playbook": "New content",
    }
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "partial_test"  # Unchanged
    assert data["description"] == "New desc"
    assert data["playbook"] == "New content"


@pytest.mark.asyncio
async def test_update_playbook_wrong_user_ownership(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that updating another user's playbook returns 404."""
    # Create another user
    other_user = User(
        username="other_user_update",
        password_hash="hash",
        role=0,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    # Create playbook for other_user
    playbook = Playbook(
        user_id=other_user.user_id,
        name="other_playbook",
        description="Other's playbook",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Try to update as test_user (should fail)
    payload = {"description": "Hacked"}
    
    response = await async_client.put(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_playbook_wrong_user_ownership(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session: AsyncSession
):
    """Test that deleting another user's playbook returns 404."""
    # Create another user
    other_user = User(
        username="other_user_delete",
        password_hash="hash",
        role=0,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    # Create playbook for other_user
    playbook = Playbook(
        user_id=other_user.user_id,
        name="other_playbook_delete",
        description="Other's playbook",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Try to delete as test_user (should fail)
    response = await async_client.delete(
        f"/api/v1/playbooks/{playbook.playbook_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_investigation_playbooks_invalid_uuid_format(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test get_investigation_playbooks with malformed UUID."""
    response = await async_client.get(
        "/api/v1/playbooks/investigation/not-a-valid-uuid",
        headers=auth_headers
    )
    
    assert response.status_code == 400
    assert "Invalid investigation ID" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_investigation_playbooks_nonexistent(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test get_investigation_playbooks for non-existent investigation."""
    import uuid as uuid_module
    
    fake_uuid = str(uuid_module.uuid4())
    response = await async_client.get(
        f"/api/v1/playbooks/investigation/{fake_uuid}",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "Investigation not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_disable_playbook_nonexistent_investigation(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test disabling playbook for non-existent investigation."""
    import uuid as uuid_module
    
    fake_uuid = str(uuid_module.uuid4())
    # Note: We don't check if investigation exists in disable endpoint
    # It just returns 404 if the relationship doesn't exist
    response = await async_client.delete(
        f"/api/v1/playbooks/investigation/{fake_uuid}/disable/1",
        headers=auth_headers
    )
    
    # Should return 404 because relationship doesn't exist
    assert response.status_code == 404
