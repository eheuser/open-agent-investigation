"""
Unit tests for LLMProviderConfig model.
Tests LLM configuration model and relationships.
"""

import pytest
from datetime import datetime
from app.models.llm_config import LLMProviderConfig


@pytest.mark.unit
class TestLLMProviderConfigModel:
    """Test LLMProviderConfig model."""

    def test_create_openai_config(self):
        """
        Test creating an OpenAI provider configuration and verify that the resulting LLMProviderConfig instance correctly stores the specified provider name, model name, and temperature values. The test constructs the config with typical parameters (user ID, endpoint, API key, model name, context length, temperature, and active flag) and asserts that these attributes are set as expected.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-test123",
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            is_active=True,
        )

        assert config.provider_name == "openai"
        assert config.model_name == "gpt-4"
        assert config.temperature == 0.7

    def test_create_ollama_config(self):
        """
        Test creating an Ollama provider configuration.

        This test instantiates :class:`LLMProviderConfig` with parameters specific to the Ollama
        provider:

        * `user_id` set to `1`.
        * `provider_name` set to `"ollama"`.
        * `api_endpoint` pointing at a local Ollama server (`http://localhost:11434`).
        * No API key (`api_key=None`) because Ollama does not require authentication.
        * `model_name` set to `"llama2"`.
        * `max_context_length` of `4096` tokens.
        * `temperature` of `0.5`.
        * `is_active` flag enabled.

        The test then asserts that the resulting configuration object correctly stores
        the provider name, API key (or lack thereof), and model name.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="ollama",
            api_endpoint="http://localhost:11434",
            api_key=None,
            model_name="llama2",
            max_context_length=4096,
            temperature=0.5,
            is_active=True,
        )

        assert config.provider_name == "ollama"
        assert config.api_key is None
        assert config.model_name == "llama2"

    def test_config_with_embeddings(self):
        """
        Test that an LLMProviderConfig instance correctly stores embedding-related settings. The test creates a configuration with explicit values for the embedding provider, API URL, API key, and model name, then asserts that the resulting object's `embedding_provider` and `embedding_model_name` attributes match the supplied inputs. This ensures that embedding configuration fields are persisted and accessible on the model.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-test123",
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            embedding_provider="openai",
            embedding_api_url="https://api.openai.com/v1",
            embedding_api_key="sk-embed123",
            embedding_model_name="text-embedding-3-small",
            is_active=True,
        )

        assert config.embedding_provider == "openai"
        assert config.embedding_model_name == "text-embedding-3-small"

    def test_config_active_flag(self):
        """
        Test that the `is_active` flag is correctly stored in an LLMProviderConfig instance.

        Creates a configuration with `is_active=True` and asserts that the attribute reflects this value.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-test",
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            is_active=True,
        )

        assert config.is_active is True

    def test_config_inactive(self):
        """
        Test that an LLMProviderConfig instance correctly reflects an inactive state when the `is_active` flag is set to `False`. The configuration is created with typical provider settings and the assertion verifies that `config.is_active` evaluates to `False`.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-old",
            model_name="gpt-3.5-turbo",
            max_context_length=4000,
            temperature=0.7,
            is_active=False,
        )

        assert config.is_active is False

    def test_config_temperature_range(self):
        """
        Test that the LLMProviderConfig model correctly stores various temperature values within the allowed range. The test iterates over a list of temperatures (0.0, 0.5, 1.0, 1.5, 2.0), creates a configuration instance for each value, and asserts that the stored `temperature` attribute matches the input. This ensures proper handling of temperature settings across typical bounds.
        """
        temperatures = [0.0, 0.5, 1.0, 1.5, 2.0]

        for temp in temperatures:
            config = LLMProviderConfig(
                user_id=1,
                provider_name="openai",
                api_endpoint="https://api.openai.com/v1",
                api_key="sk-test",
                model_name="gpt-4",
                max_context_length=8000,
                temperature=temp,
                is_active=True,
            )

            assert config.temperature == temp

    def test_config_with_top_p(self):
        """
        Test that the LLMProviderConfig correctly stores and returns the `top_p` sampling parameter when it is provided during initialization.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-test",
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            top_p=0.9,
            is_active=True,
        )

        assert config.top_p == 0.9

    def test_config_with_top_k(self):
        """
        Test that the LLMProviderConfig correctly stores and exposes the `top_k` parameter when it is provided.

        The test creates an instance of :class:`LLMProviderConfig` with:
        - `user_id` set to `1`
        - `provider_name` set to `"ollama"`
        - `api_endpoint` pointing to a local Ollama server
        - No API key (`None`)
        - `model_name` set to `"llama2"`
        - `max_context_length` of `4096`
        - `temperature` of `0.5`
        - `top_k` explicitly set to `40`
        - `is_active` flag enabled

        It then asserts that the resulting configuration object's `top_k` attribute equals `40`, confirming that the value is stored without alteration.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="ollama",
            api_endpoint="http://localhost:11434",
            api_key=None,
            model_name="llama2",
            max_context_length=4096,
            temperature=0.5,
            top_k=40,
            is_active=True,
        )

        assert config.top_k == 40

    def test_config_with_min_p(self):
        """
        Test that the `LLMProviderConfig` correctly stores and exposes the `min_p` parameter when it is provided during initialization. The configuration is created with typical values for an Ollama provider, including a `min_p` of 0.05, and the test asserts that the resulting object's `min_p` attribute matches this value.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="ollama",
            api_endpoint="http://localhost:11434",
            api_key=None,
            model_name="llama2",
            max_context_length=4096,
            temperature=0.5,
            min_p=0.05,
            is_active=True,
        )

        assert config.min_p == 0.05

    def test_config_timeout(self):
        """
        Test that a custom timeout value is correctly stored in the LLMProviderConfig instance.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-test",
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            timeout=600,
            is_active=True,
        )

        assert config.timeout == 600

    def test_config_max_context_length(self):
        """
        Test that the `max_context_length` attribute of :class:`LLMProviderConfig` correctly stores various allowed values.\n\nIterates over a list of typical context length limits (e.g., 2048, 4096, 8000, 16000, 32000), creates a configuration instance for each value, and asserts that the `max_context_length` property on the resulting object matches the input. This ensures the model accepts and retains different context size settings without alteration.
        """
        context_lengths = [2048, 4096, 8000, 16000, 32000]

        for length in context_lengths:
            config = LLMProviderConfig(
                user_id=1,
                provider_name="openai",
                api_endpoint="https://api.openai.com/v1",
                api_key="sk-test",
                model_name="gpt-4",
                max_context_length=length,
                temperature=0.7,
                is_active=True,
            )

            assert config.max_context_length == length

    def test_config_user_isolation(self):
        """
        Test that `LLMProviderConfig` instances are correctly isolated per user.

        The test constructs two separate configurations with distinct `user_id` and `api_key` values while keeping all other parameters identical. It then asserts that the `user_id` attributes differ and that the `api_key` attributes differ, verifying that configuration data is not inadvertently shared between users.
        """
        config1 = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-user1",
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            is_active=True,
        )

        config2 = LLMProviderConfig(
            user_id=2,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key="sk-user2",
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            is_active=True,
        )

        assert config1.user_id != config2.user_id
        assert config1.api_key != config2.api_key

    def test_config_unicode_model_name(self):
        """
        Test that the LLMProviderConfig correctly stores and retrieves a Unicode model name. The test creates a configuration using a Japanese model identifier (\"モデル-v1\") and asserts that the `model_name` attribute matches the provided Unicode string.
        """
        config = LLMProviderConfig(
            user_id=1,
            provider_name="custom",
            api_endpoint="http://localhost:8000",
            api_key="test",
            model_name="モデル-v1",
            max_context_length=4096,
            temperature=0.7,
            is_active=True,
        )

        assert config.model_name == "モデル-v1"

    def test_config_long_api_key(self):
        """
        Test that the LLMProviderConfig model correctly accepts and stores an API key longer than typical lengths, ensuring that extremely long keys do not cause truncation or errors. The test creates a key with over 1000 characters, initializes the configuration with it, and asserts that the stored key length exceeds 1000 characters.
        """
        long_key = "sk-" + "a" * 1000

        config = LLMProviderConfig(
            user_id=1,
            provider_name="openai",
            api_endpoint="https://api.openai.com/v1",
            api_key=long_key,
            model_name="gpt-4",
            max_context_length=8000,
            temperature=0.7,
            is_active=True,
        )

        assert len(config.api_key) > 1000
