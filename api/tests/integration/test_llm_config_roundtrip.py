import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestLLMConfigRoundTrip:
    """Test complete round-trip of LLM configuration fields."""

    async def test_all_fields_create_retrieve_roundtrip(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that ALL fields in the schema are properly saved and retrieved.
        This is a critical test to catch missing field mappings in routers/CRUD.
        """
        # Comprehensive payload with ALL possible fields
        payload = {
            # Core LLM fields
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "api_key": "sk-test-key-12345",
            "model_name": "gpt-4-turbo",
            "max_context_length": 128000,
            "temperature": 0.8,
            "top_p": 0.95,
            "top_k": 50,
            "min_p": 0.05,
            "timeout": 600,
            "is_active": True,
            "allow_concurrent_llm_calls": True,
            # Embedding fields
            "embedding_provider": "openai",
            "embedding_api_url": "https://api.openai.com/v1/embeddings",
            "embedding_api_key": "sk-embed-key-67890",
            "embedding_model_name": "text-embedding-3-small",
            "embedding_max_context_length": 8192,
            # Reranker fields
            "reranker_model_name": "text-embedding-3-large",
            "reranker_max_context_length": 16384,
            "allow_concurrent_embedding_calls": True,
        }

        # Step 1: Create configuration
        create_response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )
        assert create_response.status_code == 201, f"Create failed: {create_response.text}"
        created_data = create_response.json()
        config_id = created_data["config_id"]

        # Step 2: Verify creation response contains all fields
        assert created_data["provider_name"] == "openai"
        assert created_data["model_name"] == "gpt-4-turbo"
        assert created_data["max_context_length"] == 128000
        assert created_data["temperature"] == 0.8
        assert created_data["top_p"] == 0.95
        assert created_data["top_k"] == 50
        assert created_data["min_p"] == 0.05
        assert created_data["timeout"] == 600
        assert created_data["is_active"] is True
        assert created_data["allow_concurrent_llm_calls"] is True
        assert created_data["embedding_provider"] == "openai"
        assert created_data["embedding_api_url"] == "https://api.openai.com/v1/embeddings"
        assert created_data["embedding_model_name"] == "text-embedding-3-small"
        assert created_data["embedding_max_context_length"] == 8192
        assert created_data["reranker_model_name"] == "text-embedding-3-large"
        assert created_data["reranker_max_context_length"] == 16384
        assert created_data["allow_concurrent_embedding_calls"] is True

        # Step 3: Retrieve by ID and verify all fields
        get_response = await async_client.get(
            f"/api/v1/llm-config/{config_id}", headers=auth_headers
        )
        assert get_response.status_code == 200
        retrieved_data = get_response.json()

        # Verify all fields match
        assert retrieved_data["config_id"] == config_id
        assert retrieved_data["provider_name"] == "openai"
        assert retrieved_data["model_name"] == "gpt-4-turbo"
        assert retrieved_data["max_context_length"] == 128000
        assert retrieved_data["temperature"] == 0.8
        assert retrieved_data["top_p"] == 0.95
        assert retrieved_data["top_k"] == 50
        assert retrieved_data["min_p"] == 0.05
        assert retrieved_data["timeout"] == 600
        assert retrieved_data["is_active"] is True
        assert retrieved_data["allow_concurrent_llm_calls"] is True
        assert retrieved_data["embedding_provider"] == "openai"
        assert retrieved_data["embedding_api_url"] == "https://api.openai.com/v1/embeddings"
        assert retrieved_data["embedding_model_name"] == "text-embedding-3-small"
        assert retrieved_data["embedding_max_context_length"] == 8192
        assert retrieved_data["reranker_model_name"] == "text-embedding-3-large"
        assert retrieved_data["reranker_max_context_length"] == 16384
        assert retrieved_data["allow_concurrent_embedding_calls"] is True

        # Step 4: List configs and verify fields are present
        list_response = await async_client.get("/api/v1/llm-config/", headers=auth_headers)
        assert list_response.status_code == 200
        configs_list = list_response.json()
        
        # Find our config in the list
        our_config = next((c for c in configs_list if c["config_id"] == config_id), None)
        assert our_config is not None, "Created config not found in list"
        
        # Verify fields in list response
        assert our_config["allow_concurrent_llm_calls"] is True
        assert our_config["reranker_model_name"] == "text-embedding-3-large"
        assert our_config["allow_concurrent_embedding_calls"] is True

        # Step 5: Get active config and verify fields
        active_response = await async_client.get(
            "/api/v1/llm-config/active", headers=auth_headers
        )
        assert active_response.status_code == 200
        active_data = active_response.json()
        
        assert active_data["allow_concurrent_llm_calls"] is True
        assert active_data["embedding_max_context_length"] == 8192
        assert active_data["reranker_model_name"] == "text-embedding-3-large"
        assert active_data["reranker_max_context_length"] == 16384
        assert active_data["allow_concurrent_embedding_calls"] is True

    async def test_update_roundtrip_all_new_fields(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that updating new fields persists changes and returns updated values.
        """
        # Create minimal config
        create_payload = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_name": "gpt-4",
            "max_context_length": 8192,
            "temperature": 0.7,
        }
        
        create_response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=create_payload
        )
        config_id = create_response.json()["config_id"]

        # Update with all new fields
        update_payload = {
            "allow_concurrent_llm_calls": True,
            "embedding_provider": "openai",
            "embedding_api_url": "https://api.openai.com/v1/embeddings",
            "embedding_model_name": "text-embedding-3-small",
            "embedding_max_context_length": 8192,
            "reranker_model_name": "text-embedding-3-large",
            "reranker_max_context_length": 16384,
            "allow_concurrent_embedding_calls": True,
        }

        update_response = await async_client.patch(
            f"/api/v1/llm-config/{config_id}", headers=auth_headers, json=update_payload
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()

        # Verify update response contains all fields
        assert updated_data["allow_concurrent_llm_calls"] is True
        assert updated_data["embedding_max_context_length"] == 8192
        assert updated_data["reranker_model_name"] == "text-embedding-3-large"
        assert updated_data["reranker_max_context_length"] == 16384
        assert updated_data["allow_concurrent_embedding_calls"] is True

        # Re-fetch and verify persistence
        get_response = await async_client.get(
            f"/api/v1/llm-config/{config_id}", headers=auth_headers
        )
        assert get_response.status_code == 200
        refetched_data = get_response.json()

        # Verify fields persisted to database
        assert refetched_data["allow_concurrent_llm_calls"] is True
        assert refetched_data["embedding_max_context_length"] == 8192
        assert refetched_data["reranker_model_name"] == "text-embedding-3-large"
        assert refetched_data["reranker_max_context_length"] == 16384
        assert refetched_data["allow_concurrent_embedding_calls"] is True

    async def test_default_values_for_new_fields(
        self, async_client: AsyncClient, auth_headers
    ):
        """
        Test that new fields have correct defaults when not provided in create request.
        """
        payload = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_name": "gpt-4",
            # Don't provide new fields - should use defaults
        }

        response = await async_client.post(
            "/api/v1/llm-config/", headers=auth_headers, json=payload
        )
        assert response.status_code == 201
        data = response.json()

        # Verify defaults
        assert data["allow_concurrent_llm_calls"] is False
        assert data["allow_concurrent_embedding_calls"] is False
        assert data["embedding_max_context_length"] == 8192
        assert data["reranker_max_context_length"] == 8192

    async def test_backward_compatibility_old_configs(
        self, async_client: AsyncClient, auth_headers, db_session
    ):
        """
        Test that old configs without new fields can still be retrieved.
        This simulates configs created before the new fields were added.
        """
        from app.models.llm_config import LLMProviderConfig
        from app.models.user import User
        
        # Get the test user
        result = await db_session.execute(
            "SELECT user_id FROM users WHERE username = 'testuser' LIMIT 1"
        )
        user_row = result.fetchone()
        if not user_row:
            # Create test user if doesn't exist
            from sqlalchemy import text
            await db_session.execute(
                text("INSERT INTO users (username, password_hash, role) VALUES ('testuser', 'hash', 0)")
            )
            await db_session.commit()
            result = await db_session.execute(
                "SELECT user_id FROM users WHERE username = 'testuser' LIMIT 1"
            )
            user_row = result.fetchone()
        
        user_id = user_row[0]

        # Create config directly in DB without new fields (simulate old config)
        from sqlalchemy import text
        await db_session.execute(
            text("""
                INSERT INTO llm_provider_config 
                (user_id, provider_name, api_endpoint, model_name, max_context_length, temperature, timeout, is_active)
                VALUES (:user_id, 'openai', 'https://api.openai.com/v1', 'gpt-4', 8192, 0.7, 300, true)
            """),
            {"user_id": user_id}
        )
        await db_session.commit()

        # Retrieve via API
        response = await async_client.get("/api/v1/llm-config/", headers=auth_headers)
        assert response.status_code == 200
        configs = response.json()
        
        # Should have at least one config
        assert len(configs) > 0
        
        # Find the old config
        old_config = next((c for c in configs if c["provider_name"] == "openai"), None)
        assert old_config is not None
        
        # New fields should have defaults
        assert old_config["allow_concurrent_llm_calls"] is False
        assert old_config["allow_concurrent_embedding_calls"] is False
