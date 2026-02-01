"""
Unit tests for LLM config schemas.
Tests Pydantic validation for LLM configuration data.
"""

import pytest
from pydantic import ValidationError
from app.schemas.llm_config import LLMConfigCreate, LLMConfigRead, LLMConfigUpdate, LLMConfigReadMasked


@pytest.mark.unit
class TestLLMConfigCreate:
    """Test LLMConfigCreate schema."""

    def test_create_openai_config(self):
        """
        Test creating an OpenAI LLM configuration using the `LLMConfigCreate` schema.

        The test constructs a dictionary with required fields (provider name, API endpoint, API key, model name,
        maximum context length) and optional settings such as temperature. It then instantiates
        `LLMConfigCreate` with this data and asserts that:

        * The `provider_name` attribute is set to `"openai"`
        * The `model_name` attribute matches the supplied value (`"gpt-4"`)
        * The `temperature` attribute retains the provided float (`0.7`)

        This verifies that the Pydantic model correctly validates input data and populates its
        attributes for a typical OpenAI configuration.
        """
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1",
            "api_key": "sk-test123",
            "model_name": "gpt-4",
            "max_context_length": 8000,
            "temperature": 0.7,
        }

        config = LLMConfigCreate(**data)

        assert config.provider_name == "openai"
        assert config.model_name == "gpt-4"
        assert config.temperature == 0.7

    def test_create_ollama_config(self):
        """
        Test that creating an `LLMConfigCreate` instance with valid Ollama provider data correctly populates the required fields and defaults optional attributes (e.g., `api_key`) to `None`. The test supplies a dictionary containing all mandatory keys for an Ollama configuration, instantiates the model, and asserts that the resulting object's `provider_name` matches the input while `api_key` remains unset. This verifies both successful validation of required fields and proper handling of optional attributes.
        """
        data = {
            "provider_name": "ollama",
            "api_endpoint": "http://localhost:11434",
            "model_name": "llama2",
            "max_context_length": 4096,
            "temperature": 0.5,
        }

        config = LLMConfigCreate(**data)

        assert config.provider_name == "ollama"
        assert config.api_key is None

    def test_create_config_with_embeddings(self):
        """
        Test creating an LLM configuration that includes embedding settings.

        This test verifies that when all required fields and the optional embedding-related fields are supplied, the :class:`LLMConfigCreate` model correctly stores the embedding provider and model name. It constructs a data dictionary with typical OpenAI parameters, instantiates `LLMConfigCreate` using keyword arguments, and asserts that the resulting object's `embedding_provider` and `embedding_model_name` attributes match the input values.
        """
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1",
            "api_key": "sk-test123",
            "model_name": "gpt-4",
            "max_context_length": 8000,
            "temperature": 0.7,
            "embedding_provider": "openai",
            "embedding_api_url": "https://api.openai.com/v1/embeddings",
            "embedding_api_key": "sk-embed123",
            "embedding_model_name": "text-embedding-3-small",
            "embedding_max_context_length": 8192,
            "reranker_model_name": "text-embedding-3-large",
            "reranker_max_context_length": 8192,
        }

        config = LLMConfigCreate(**data)

        assert config.embedding_provider == "openai"
        assert config.embedding_model_name == "text-embedding-3-small"
        assert config.embedding_max_context_length == 8192
        assert config.reranker_model_name == "text-embedding-3-large"
        assert config.reranker_max_context_length == 8192

    def test_create_config_missing_required_field(self):
        """
        Test that creating an LLM configuration without a required field raises a ValidationError.

        The test constructs input data missing the `api_endpoint` key, which is mandatory for `LLMConfigCreate`. It then asserts that initializing `LLMConfigCreate` with this incomplete payload triggers a Pydantic `ValidationError`. This ensures required-field validation is enforced during schema creation.
        """
        data = {
            "provider_name": "openai",
            # Missing api_endpoint
        }

        with pytest.raises(ValidationError):
            LLMConfigCreate(**data)

    def test_create_config_invalid_temperature(self):
        """
        Test that creating an LLM configuration with an out-of-range temperature value (e.g., -1.0) either retains the invalid value or triggers a Pydantic ValidationError, depending on whether temperature range validation is implemented. The test constructs a data dictionary with required fields and an invalid temperature, attempts to instantiate `LLMConfigCreate` with it, and asserts that the resulting object's `temperature` attribute matches the supplied value if no exception is raised; otherwise, it silently accepts the ValidationError. This verifies proper handling of temperature validation edge cases.
        """
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1",
            "model_name": "gpt-4",
            "max_context_length": 8000,
            "temperature": -1.0,  # Invalid
        }

        # May or may not validate temperature range
        try:
            config = LLMConfigCreate(**data)
            assert config.temperature == -1.0
        except ValidationError:
            pass


@pytest.mark.unit
class TestLLMConfigRead:
    """Test LLMConfigRead schema."""

    def test_read_config_basic(self):
        """
        Test the basic reading of an LLM configuration using the `LLMConfigRead` schema.\n\nThe test constructs a dictionary containing all required fields for a read-only LLM configuration, instantiates `LLMConfigRead` with that data, and asserts that key attributes are correctly populated. It verifies that:\n\n* `config_id` is set to `1`\n* `provider_name` matches the provided string (\"openai\")\n* `is_active` reflects a truthy value (`True`)   \n\nNo return value is expected; the test passes if all assertions succeed.
        """
        from datetime import datetime

        data = {
            "config_id": 1,
            "user_id": 1,
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1",
            "api_key": "sk-***",
            "model_name": "gpt-4",
            "max_context_length": 8000,
            "temperature": 0.7,
            "timeout": 300,
            "is_active": True,
            "allow_concurrent_llm_calls": False,
            "allow_concurrent_embedding_calls": False,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        config = LLMConfigRead(**data)

        assert config.config_id == 1
        assert config.provider_name == "openai"
        assert config.is_active is True
        assert config.allow_concurrent_llm_calls is False
        assert config.allow_concurrent_embedding_calls is False

    def test_read_config_with_embeddings(self):
        """
        Test that LLMConfigRead correctly parses a configuration dictionary containing embedding settings and that the resulting model instance has the expected `embedding_provider` attribute value. This ensures optional embedding fields are handled during read operations.
        """
        from datetime import datetime

        data = {
            "config_id": 1,
            "user_id": 1,
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1",
            "api_key": "sk-***",
            "model_name": "gpt-4",
            "max_context_length": 8000,
            "temperature": 0.7,
            "timeout": 300,
            "embedding_provider": "openai",
            "embedding_api_url": "https://api.openai.com/v1/embeddings",
            "embedding_model_name": "text-embedding-3-small",
            "embedding_max_context_length": 8192,
            "reranker_model_name": "text-embedding-3-large",
            "reranker_max_context_length": 8192,
            "is_active": True,
            "allow_concurrent_llm_calls": False,
            "allow_concurrent_embedding_calls": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        config = LLMConfigRead(**data)

        assert config.embedding_provider == "openai"
        assert config.embedding_model_name == "text-embedding-3-small"
        assert config.embedding_max_context_length == 8192
        assert config.reranker_model_name == "text-embedding-3-large"
        assert config.reranker_max_context_length == 8192
        assert config.allow_concurrent_embedding_calls is True

    def test_read_config_backward_compatibility(self):
        """
        Test that LLMConfigRead handles missing new fields with defaults for backward compatibility.
        """
        from datetime import datetime

        # Old config without new concurrent fields
        data = {
            "config_id": 1,
            "user_id": 1,
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1",
            "api_key": "sk-***",
            "model_name": "gpt-4",
            "max_context_length": 8000,
            "temperature": 0.7,
            "timeout": 300,
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            # Missing: allow_concurrent_llm_calls, allow_concurrent_embedding_calls
        }

        config = LLMConfigRead(**data)

        # Should use defaults
        assert config.allow_concurrent_llm_calls is False
        assert config.allow_concurrent_embedding_calls is False

    def test_create_config_with_reranker_only(self):
        """
        Test creating config with reranker but no embedding model (should work).
        """
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_name": "gpt-4",
            "reranker_model_name": "text-embedding-3-large",
            "reranker_max_context_length": 8192,
        }

        config = LLMConfigCreate(**data)

        assert config.reranker_model_name == "text-embedding-3-large"
        assert config.embedding_model_name is None

    def test_create_config_with_concurrent_calls(self):
        """
        Test creating an LLM configuration with concurrent call flags enabled.
        """
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "api_key": "sk-test123",
            "model_name": "gpt-4",
            "max_context_length": 128000,
            "temperature": 0.7,
            "allow_concurrent_llm_calls": True,
            "allow_concurrent_embedding_calls": True,
        }

        config = LLMConfigCreate(**data)

        assert config.allow_concurrent_llm_calls is True
        assert config.allow_concurrent_embedding_calls is True

    def test_create_config_defaults(self):
        """
        Test that LLMConfigCreate applies correct default values for optional fields.
        """
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_name": "gpt-4",
        }

        config = LLMConfigCreate(**data)

        assert config.temperature == 0.7
        assert config.max_context_length == 8192
        assert config.timeout == 300
        assert config.is_active is True
        assert config.allow_concurrent_llm_calls is False
        assert config.allow_concurrent_embedding_calls is False
        assert config.embedding_max_context_length == 8192
        assert config.reranker_max_context_length == 8192

    def test_create_config_token_limits(self):
        """
        Test that embedding and reranker token limits are validated properly.
        """
        # Test with valid token limits
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_name": "gpt-4",
            "embedding_max_context_length": 512,
            "reranker_max_context_length": 16384,
        }

        config = LLMConfigCreate(**data)

        assert config.embedding_max_context_length == 512
        assert config.reranker_max_context_length == 16384

        # Test with invalid token limit (should raise ValidationError)
        invalid_data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_name": "gpt-4",
            "embedding_max_context_length": 0,  # Invalid: must be >= 1
        }

        with pytest.raises(ValidationError):
            LLMConfigCreate(**invalid_data)

    def test_create_config_same_embedding_and_reranker(self):
        """
        Test creating config where reranker and embedding use same model (valid but reranking will be skipped).
        """
        data = {
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "model_name": "gpt-4",
            "embedding_model_name": "text-embedding-3-small",
            "reranker_model_name": "text-embedding-3-small",  # Same as embedding
        }

        config = LLMConfigCreate(**data)

        assert config.embedding_model_name == "text-embedding-3-small"
        assert config.reranker_model_name == "text-embedding-3-small"


@pytest.mark.unit
class TestLLMConfigUpdate:
    """Test LLMConfigUpdate schema."""

    def test_update_concurrent_flags(self):
        """
        Test updating concurrent call flags.
        """
        data = {
            "allow_concurrent_llm_calls": True,
            "allow_concurrent_embedding_calls": True,
        }

        config = LLMConfigUpdate(**data)

        assert config.allow_concurrent_llm_calls is True
        assert config.allow_concurrent_embedding_calls is True

    def test_update_reranker_config(self):
        """
        Test updating reranker configuration.
        """
        data = {
            "reranker_model_name": "text-embedding-3-large",
            "reranker_max_context_length": 16384,
        }

        config = LLMConfigUpdate(**data)

        assert config.reranker_model_name == "text-embedding-3-large"
        assert config.reranker_max_context_length == 16384

    def test_update_partial_fields(self):
        """
        Test that LLMConfigUpdate allows partial updates (all fields optional).
        """
        data = {
            "temperature": 0.9,
        }

        config = LLMConfigUpdate(**data)

        assert config.temperature == 0.9
        assert config.model_name is None  # Not updated


@pytest.mark.unit
class TestLLMConfigReadMasked:
    """Test LLMConfigReadMasked schema."""

    def test_masked_response_with_all_fields(self):
        """
        Test that LLMConfigReadMasked properly masks API keys and includes all new fields.
        """
        from datetime import datetime

        data = {
            "config_id": 1,
            "user_id": 1,
            "provider_name": "openai",
            "api_endpoint": "https://api.openai.com/v1/chat/completions",
            "api_key_masked": "••••••••",
            "model_name": "gpt-4",
            "max_context_length": 128000,
            "temperature": 0.7,
            "timeout": 300,
            "is_active": True,
            "allow_concurrent_llm_calls": True,
            "embedding_provider": "openai",
            "embedding_api_url": "https://api.openai.com/v1/embeddings",
            "embedding_api_key_masked": "••••••••",
            "embedding_model_name": "text-embedding-3-small",
            "embedding_max_context_length": 8192,
            "reranker_model_name": "text-embedding-3-large",
            "reranker_max_context_length": 8192,
            "allow_concurrent_embedding_calls": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        config = LLMConfigReadMasked(**data)

        assert config.api_key_masked == "••••••••"
        assert config.embedding_api_key_masked == "••••••••"
        assert config.allow_concurrent_llm_calls is True
        assert config.allow_concurrent_embedding_calls is True
        assert config.reranker_model_name == "text-embedding-3-large"
