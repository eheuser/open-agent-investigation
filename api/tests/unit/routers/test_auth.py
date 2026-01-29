# api/tests/unit/routers/test_auth.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.auth import hash_password


@pytest.mark.asyncio
async def test_login_success(
    async_client: AsyncClient,
    test_user: User,
    db_session: AsyncSession
):
    """Test successful login."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "testuser"
    assert data["role"] == 0


@pytest.mark.asyncio
async def test_login_nonexistent_user(
    async_client: AsyncClient
):
    """Test login with non-existent username (triggers timing attack prevention)."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent", "password": "anypassword"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "Incorrect username or password" in data["detail"]
    assert "WWW-Authenticate" in response.headers


@pytest.mark.asyncio
async def test_login_wrong_password(
    async_client: AsyncClient,
    test_user: User
):
    """Test login with wrong password."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "wrongpassword"}
    )
    
    assert response.status_code == 401
    data = response.json()
    assert "Incorrect username or password" in data["detail"]
    assert "WWW-Authenticate" in response.headers


@pytest.mark.asyncio
async def test_register_success(
    async_client: AsyncClient
):
    """Test successful user registration."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"username": "newuser", "password": "newpass123"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["username"] == "newuser"
    assert data["role"] == 0  # Regular user


@pytest.mark.asyncio
async def test_register_duplicate_username(
    async_client: AsyncClient,
    test_user: User
):
    """Test registration with existing username."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "anypassword"}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "already registered" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_me(
    async_client: AsyncClient,
    auth_headers: dict,
    test_user: User
):
    """Test getting current user info."""
    response = await async_client.get(
        "/api/v1/auth/me",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.user_id
    assert data["username"] == "testuser"
    assert data["role"] == 0


@pytest.mark.asyncio
async def test_get_me_unauthorized(
    async_client: AsyncClient
):
    """Test getting current user without authentication."""
    response = await async_client.get("/api/v1/auth/me")
    
    assert response.status_code == 401
