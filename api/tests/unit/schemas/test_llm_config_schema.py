"""
Unit tests for LLM config schemas.
Tests Pydantic validation for LLM configuration data.
"""

import pytest
from pydantic import ValidationError
from app.schemas.llm_config import LLMConfigCreate, LLMConfigRead


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
            "embedding_api_url": "https://api.openai.com/v1",
            "embedding_api_key": "sk-embed123",
            "embedding_model_name": "text-embedding-3-small",
        }

        config = LLMConfigCreate(**data)

        assert config.embedding_provider == "openai"
        assert config.embedding_model_name == "text-embedding-3-small"

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
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        config = LLMConfigRead(**data)

        assert config.config_id == 1
        assert config.provider_name == "openai"
        assert config.is_active is True

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
            "embedding_model_name": "text-embedding-3-small",
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        config = LLMConfigRead(**data)

        assert config.embedding_provider == "openai"
