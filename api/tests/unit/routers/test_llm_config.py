# api/tests/unit/routers/test_llm_config.py
import pytest
from httpx import AsyncClient

from app.models import User
from app.models.llm_config import LLMProviderConfig


@pytest.mark.asyncio
async def test_create_llm_config(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating an LLM configuration."""
    payload = {
        "provider_name": "openai",
        "api_endpoint": "https://api.openai.com/v1",
        "api_key": "sk-test-key",
        "model_name": "gpt-4",
        "max_context_length": 8192,
        "temperature": 0.7,
        "is_active": True
    }
    
    response = await async_client.post(
        "/api/v1/llm-config/",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["provider_name"] == "openai"
    assert data["model_name"] == "gpt-4"
    assert data["temperature"] == 0.7
    assert "config_id" in data


@pytest.mark.asyncio
async def test_list_llm_configs(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test listing LLM configurations."""
    # Create test configs
    config1 = LLMProviderConfig(
        user_id=test_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key1",
        model_name="gpt-4",
        max_context_length=8192,
        temperature=0.7,
        is_active=True
    )
    config2 = LLMProviderConfig(
        user_id=test_user.user_id,
        provider_name="anthropic",
        api_endpoint="https://api.anthropic.com",
        api_key="key2",
        model_name="claude-3",
        max_context_length=100000,
        temperature=0.5,
        is_active=False
    )
    
    db_session.add_all([config1, config2])
    await db_session.commit()
    
    response = await async_client.get(
        "/api/v1/llm-config/",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    providers = {c["provider_name"] for c in data}
    assert "openai" in providers
    assert "anthropic" in providers


@pytest.mark.asyncio
async def test_get_active_config(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test getting active LLM configuration."""
    config = LLMProviderConfig(
        user_id=test_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-4",
        max_context_length=8192,
        temperature=0.7,
        is_active=True
    )
    
    db_session.add(config)
    await db_session.commit()
    
    response = await async_client.get(
        "/api/v1/llm-config/active",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["provider_name"] == "openai"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_get_active_config_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test getting active config when none exists."""
    response = await async_client.get(
        "/api/v1/llm-config/active",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "No active" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_llm_config_by_id(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test getting specific LLM configuration."""
    config = LLMProviderConfig(
        user_id=test_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-4",
        max_context_length=8192,
        temperature=0.7,
        is_active=True
    )
    
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    
    response = await async_client.get(
        f"/api/v1/llm-config/{config.config_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["config_id"] == config.config_id
    assert data["provider_name"] == "openai"


@pytest.mark.asyncio
async def test_get_llm_config_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test getting non-existent config."""
    response = await async_client.get(
        "/api/v1/llm-config/999999",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_llm_config_forbidden(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test that non-owner cannot access another user's config."""
    other_user = User(
        username="other_llm_user",
        password_hash="hash",
        role=0
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    config = LLMProviderConfig(
        user_id=other_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-4",
        max_context_length=8192,
        temperature=0.7,
        is_active=True
    )
    
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    
    response = await async_client.get(
        f"/api/v1/llm-config/{config.config_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_llm_config(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test updating LLM configuration."""
    config = LLMProviderConfig(
        user_id=test_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-3.5",
        max_context_length=4096,
        temperature=0.7,
        is_active=False
    )
    
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    
    payload = {
        "model_name": "gpt-4",
        "max_context_length": 8192,
        "is_active": True
    }
    
    response = await async_client.patch(
        f"/api/v1/llm-config/{config.config_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["model_name"] == "gpt-4"
    assert data["max_context_length"] == 8192
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_update_llm_config_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test updating non-existent config."""
    payload = {"model_name": "gpt-4"}
    
    response = await async_client.patch(
        "/api/v1/llm-config/999999",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_llm_config_forbidden(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test that non-owner cannot update another user's config."""
    other_user = User(
        username="other_update_llm_user",
        password_hash="hash",
        role=0
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    config = LLMProviderConfig(
        user_id=other_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-4",
        max_context_length=8192,
        temperature=0.7,
        is_active=True
    )
    
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    
    payload = {"model_name": "hacked"}
    
    response = await async_client.patch(
        f"/api/v1/llm-config/{config.config_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_llm_config(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test deleting LLM configuration."""
    config = LLMProviderConfig(
        user_id=test_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-4",
        max_context_length=8192,
        temperature=0.7,
        is_active=True
    )
    
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    
    response = await async_client.delete(
        f"/api/v1/llm-config/{config.config_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_llm_config_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test deleting non-existent config."""
    response = await async_client.delete(
        "/api/v1/llm-config/999999",
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_llm_config_forbidden(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test that non-owner cannot delete another user's config."""
    other_user = User(
        username="other_delete_llm_user",
        password_hash="hash",
        role=0
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    config = LLMProviderConfig(
        user_id=other_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-4",
        max_context_length=8192,
        temperature=0.7,
        is_active=True
    )
    
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    
    response = await async_client.delete(
        f"/api/v1/llm-config/{config.config_id}",
        headers=auth_headers
    )
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_llm_config_with_embedding(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating LLM config with embedding configuration."""
    payload = {
        "provider_name": "openai",
        "api_endpoint": "https://api.openai.com/v1",
        "api_key": "sk-test-key",
        "model_name": "gpt-4",
        "max_context_length": 8192,
        "temperature": 0.7,
        "is_active": True,
        "embedding_provider": "openai",
        "embedding_api_url": "https://api.openai.com/v1/embeddings",
        "embedding_api_key": "sk-embed-key",
        "embedding_model_name": "text-embedding-ada-002"
    }
    
    response = await async_client.post(
        "/api/v1/llm-config/",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["embedding_provider"] == "openai"
    assert data["embedding_model_name"] == "text-embedding-ada-002"


@pytest.mark.asyncio
async def test_create_llm_config_with_optional_params(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test creating LLM config with optional parameters."""
    payload = {
        "provider_name": "openai",
        "api_endpoint": "https://api.openai.com/v1",
        "api_key": "sk-test-key",
        "model_name": "gpt-4",
        "max_context_length": 8192,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 50,
        "min_p": 0.1,
        "timeout": 60,
        "is_active": True
    }
    
    response = await async_client.post(
        "/api/v1/llm-config/",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["top_p"] == 0.9
    assert data["top_k"] == 50
    assert data["min_p"] == 0.1
    assert data["timeout"] == 60


@pytest.mark.asyncio
async def test_update_llm_config_partial(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test partial update of LLM config."""
    config = LLMProviderConfig(
        user_id=test_user.user_id,
        provider_name="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key="key",
        model_name="gpt-3.5",
        max_context_length=4096,
        temperature=0.7,
        is_active=False
    )
    
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    
    # Only update temperature
    payload = {"temperature": 0.9}
    
    response = await async_client.patch(
        f"/api/v1/llm-config/{config.config_id}",
        json=payload,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["temperature"] == 0.9
    assert data["model_name"] == "gpt-3.5"  # Unchanged
