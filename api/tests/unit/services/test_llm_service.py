import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from app.services.llm_service import (
    LLMConfig,
    LLMService,
    EmbeddingService,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    CHARS_PER_TOKEN,
)


@pytest.mark.unit
class TestLLMConfig:
    """Test LLMConfig class."""

    def test_init_with_defaults(self):
        """
        Test that initializing LLMConfig without optional arguments sets all fields to their default values, including a None API key, the standard maximum context length, the library's default temperature, and unset sampling parameters (top_p, top_k, min_p).
        """
        config = LLMConfig(
            api_endpoint="https://api.example.com/v1/chat/completions", model_name="gpt-4"
        )

        assert config.api_endpoint == "https://api.example.com/v1/chat/completions"
        assert config.model_name == "gpt-4"
        assert config.api_key is None
        assert config.max_context_length == 8192
        assert config.temperature == DEFAULT_TEMPERATURE
        assert config.top_p is None
        assert config.top_k is None
        assert config.min_p is None

    def test_init_with_custom_values(self):
        """
        Test that LLMConfig correctly assigns custom initialization parameters, verifying that each attribute (api_key, max_context_length, temperature, top_p, top_k, min_p, and timeout) matches the values provided during construction.
        """
        config = LLMConfig(
            api_endpoint="https://api.example.com",
            model_name="llama-2",
            api_key="test-key",
            max_context_length=4096,
            temperature=0.5,
            top_p=0.9,
            top_k=50,
            min_p=0.05,
            timeout=600,
        )

        assert config.api_key == "test-key"
        assert config.max_context_length == 4096
        assert config.temperature == 0.5
        assert config.top_p == 0.9
        assert config.top_k == 50
        assert config.min_p == 0.05
        assert config.timeout == 600

    def test_from_db_config(self):
        """
        Test that :meth:`LLMConfig.from_db_config` correctly creates an `LLMConfig` instance from a database configuration object by mapping all relevant fields and converting numeric `Decimal` values to native Python types.
        """
        # Mock database config object
        db_config = MagicMock()
        db_config.api_endpoint = "https://api.example.com"
        db_config.model_name = "gpt-4"
        db_config.api_key = "test-key"
        db_config.max_context_length = Decimal("8192")
        db_config.temperature = Decimal("0.7")
        db_config.top_p = Decimal("0.9")
        db_config.top_k = Decimal("50")
        db_config.min_p = Decimal("0.05")
        db_config.timeout = Decimal("300")

        config = LLMConfig.from_db_config(db_config)

        assert config.api_endpoint == "https://api.example.com"
        assert config.model_name == "gpt-4"
        assert config.api_key == "test-key"
        assert config.max_context_length == 8192
        assert config.temperature == 0.7
        assert config.top_p == 0.9
        assert config.top_k == 50
        assert config.min_p == 0.05
        assert config.timeout == 300

    def test_from_db_config_with_none_values(self):
        """
        Test that `LLMConfig.from_db_config` correctly substitutes default values when the database configuration provides `None` for optional settings, while preserving explicit `None` where appropriate. The test creates a mock DB config with only `api_endpoint` and `model_name` set, leaves all other attributes as `None`, invokes the factory method, and asserts that:

        - `api_key` remains `None`.
        - `max_context_length` falls back to the default of 8192.
        - `temperature` falls back to `DEFAULT_TEMPERATURE`.
        - `top_p`, `top_k`, and `min_p` remain `None`.
        """
        db_config = MagicMock()
        db_config.api_endpoint = "https://api.example.com"
        db_config.model_name = "gpt-4"
        db_config.api_key = None
        db_config.max_context_length = None
        db_config.temperature = None
        db_config.top_p = None
        db_config.top_k = None
        db_config.min_p = None
        db_config.timeout = None

        config = LLMConfig.from_db_config(db_config)

        assert config.api_key is None
        assert config.max_context_length == 8192  # Default
        assert config.temperature == DEFAULT_TEMPERATURE  # Default
        assert config.top_p is None
        assert config.top_k is None
        assert config.min_p is None


@pytest.mark.unit
class TestLLMService:
    """Test LLMService class."""

    def test_init(self):
        """
        Test that initializing an LLMService instance correctly assigns the provided configuration and sets default retry settings (max_retries = 3, retry_backoff_base = 2).
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        assert service.config == config
        assert service.max_retries == 3
        assert service.retry_backoff_base == 2

    def test_estimate_tokens(self):
        """
        Test that the token estimation logic correctly calculates the number of tokens for a given input string based on the configured characters-per-token ratio. The test creates an LLMService instance with a minimal configuration, supplies a known length string, invokes `estimate_tokens` and asserts that the returned token count matches the expected value derived from `CHARS_PER_TOKEN`.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        # Test with known text
        text = "a" * 100  # 100 characters
        tokens = service.estimate_tokens(text)

        assert tokens == 100 // CHARS_PER_TOKEN  # Should be 25

    def test_estimate_messages_tokens(self):
        """
        Test that the LLMService correctly estimates the token count for a list of chat messages.

        The test creates an `LLMConfig` with a dummy endpoint and model name, instantiates an `LLMService`, and defines a small set of messages representing a typical system-user-assistant exchange. It then calls `estimate_messages_tokens` on the service and asserts that the returned token count is greater than zero, confirming that the estimation logic produces a positive integer for non-empty input.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        tokens = service.estimate_messages_tokens(messages)

        # Should be > 0
        assert tokens > 0

    def test_enforce_context_limit_no_trimming_needed(self):
        """
        Test that LLMService.enforce_context_limit returns the original message list unchanged and reports zero tokens removed when the total token count is already below the specified maximum limit. This verifies that no trimming occurs for messages fitting within the allowed context size.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]

        trimmed, tokens_removed = service.enforce_context_limit(messages, max_tokens=10000)

        assert trimmed == messages
        assert tokens_removed == 0

    def test_enforce_context_limit_with_trimming(self):
        """
        Test that LLMService.enforce_context_limit correctly trims messages when the token count exceeds the specified maximum, preserving the initial system message and returning both the trimmed list of messages and the number of tokens removed. The test constructs a series of user and assistant messages sufficient to surpass the limit, invokes the method with max_tokens=50, and asserts that the resulting message list is shorter than the original, that some tokens were removed, and that the first message remains the system role.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        # Create many messages to exceed limit
        messages = [{"role": "system", "content": "System message"}]
        for i in range(20):
            messages.append({"role": "user", "content": "x" * 100})
            messages.append({"role": "assistant", "content": "y" * 100})

        trimmed, tokens_removed = service.enforce_context_limit(messages, max_tokens=50)

        # Should have trimmed some messages
        assert len(trimmed) < len(messages)
        assert tokens_removed > 0
        # System message should be preserved
        assert trimmed[0]["role"] == "system"

    def test_enforce_context_limit_preserves_recent(self):
        """
        Test that the `enforce_context_limit` method preserves the specified number of most recent messages when trimming the conversation context.

        This test creates an `LLMConfig` and an `LLMService`, defines a list of mixed system, user, and assistant messages, and invokes `service.enforce_context_limit` with a token limit and a request to preserve the last three messages. It asserts that the trimmed result still ends with the original last three messages, confirming that recent context is retained despite any truncation performed to meet the token budget.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "old message"},
            {"role": "assistant", "content": "old response"},
            {"role": "user", "content": "recent 1"},
            {"role": "assistant", "content": "recent 2"},
            {"role": "user", "content": "recent 3"},
        ]

        trimmed, _ = service.enforce_context_limit(messages, max_tokens=50, preserve_recent=3)

        # Last 3 messages should be preserved
        assert trimmed[-3:] == messages[-3:]


@pytest.mark.unit
class TestLLMServiceAsync:
    """Test async methods of LLMService."""

    async def test_from_user_config_success(self):
        """
        Test that LLMService can be instantiated from a user's configuration.\n\nThe test creates an asynchronous mock database object and defines a sample user ID. It then constructs a mocked configuration object with typical LLM settings such as endpoint, model name, API key, context length, temperature, and timeout values. By patching the `get_active_llm_config` function to return this mock configuration, the test invokes `LLMService.from_user_config` asynchronously.\n\nAssertions verify that:\n- The returned service instance is not `None`.\n- The service's internal configuration correctly reflects the mocked model name (\"gpt-4\").\n\nThis ensures that the `from_user_config` class method correctly retrieves user-specific settings and creates a functional `LLMService` object.
        """
        db = AsyncMock()
        user_id = 1

        # Mock database config
        mock_config = MagicMock()
        mock_config.api_endpoint = "https://api.example.com"
        mock_config.model_name = "gpt-4"
        mock_config.api_key = "test-key"
        mock_config.max_context_length = 8192
        mock_config.temperature = 0.7
        mock_config.top_p = None
        mock_config.top_k = None
        mock_config.min_p = None
        mock_config.timeout = 300

        with patch("app.services.llm_service.get_active_llm_config", return_value=mock_config):
            service = await LLMService.from_user_config(db, user_id)

            assert service is not None
            assert service.config.model_name == "gpt-4"

    async def test_from_user_config_no_config(self):
        """
        Test that LLMService.from_user_config returns None when there is no active configuration for the given user. The test mocks the database dependency and patches get_active_llm_config to return None, then asserts that the service creation yields a falsy result.
        """
        db = AsyncMock()
        user_id = 1

        with patch("app.services.llm_service.get_active_llm_config", return_value=None):
            service = await LLMService.from_user_config(db, user_id)

            assert service is None

    async def test_extract_text_response_openai_format(self):
        """
        Test extracting plain text from an OpenAI-style response.

        This test creates a minimal `LLMConfig` and `LLMService` instance, supplies a mock
        response dictionary that mimics the structure returned by OpenAI's chat completions API,
        and verifies that :meth:`LLMService.extract_text_response` correctly navigates to the
        `content` field of the first choice.

        The test asserts that the extracted text matches the expected string.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        response = {
            "choices": [{"message": {"role": "assistant", "content": "Hello, how can I help?"}}]
        }

        text = await service.extract_text_response(response)

        assert text == "Hello, how can I help?"

    async def test_extract_text_response_text_field(self):
        """
        Test that the LLMService correctly extracts the generated text from a response dictionary when the text is provided in the `text` field of the first choice.\n\nThe test creates a minimal configuration and service instance, supplies a mock API response containing a `choices` list with a single entry whose `text` key holds the expected output, invokes :meth:`LLMService.extract_text_response`, and asserts that the returned string matches the original text.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        response = {"choices": [{"text": "Response text"}]}

        text = await service.extract_text_response(response)

        assert text == "Response text"

    async def test_extract_text_response_not_found(self):
        """
        Test that extracting a text response returns `None` when the response dictionary does not contain any recognized fields for text extraction. The test constructs an :class:`LLMConfig` and :class:`LLMService`, provides a response with an unknown key, invokes :meth:`LLMService.extract_text_response`, and asserts that the result is `None`.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        response = {"unknown_field": "data"}

        text = await service.extract_text_response(response)

        assert text is None


@pytest.mark.unit
class TestEmbeddingService:
    """Test EmbeddingService class."""

    def test_init(self):
        """
        Test that EmbeddingService initializes correctly with given provider, API URL, API key, and model name, and that its attributes match the supplied values.
        """
        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="test-key",
            model_name="text-embedding-ada-002",
        )

        assert service.provider == "openai"
        assert service.api_url == "https://api.openai.com/v1/embeddings"
        assert service.api_key == "test-key"
        assert service.model_name == "text-embedding-ada-002"

    def test_get_embedding_dimension_openai(self):
        """
        Test that the embedding dimension returned by `EmbeddingService` for the OpenAI provider matches the expected size (1536) for the `text-embedding-ada-002` model.
        """
        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            model_name="text-embedding-ada-002",
        )

        dim = service.get_embedding_dimension()
        assert dim == 1536

    def test_get_embedding_dimension_cohere(self):
        """
        Test that the EmbeddingService correctly returns the embedding dimension for the Cohere provider using the specified model. The service is instantiated with provider "cohere", API URL, and model name "embed-english-v3.0". The test asserts that the returned dimension equals 1024.
        """
        service = EmbeddingService(
            provider="cohere",
            api_url="https://api.cohere.ai/v1/embed",
            model_name="embed-english-v3.0",
        )

        dim = service.get_embedding_dimension()
        assert dim == 1024

    def test_get_embedding_dimension_ollama(self):
        """
        Test that the `EmbeddingService` correctly reports the embedding dimension when configured for the Ollama provider using the `nomic-embed-text` model (expected dimension: 384).
        """
        service = EmbeddingService(
            provider="ollama",
            api_url="http://localhost:11434/api/embeddings",
            model_name="nomic-embed-text",
        )

        dim = service.get_embedding_dimension()
        assert dim == 384

    async def test_embed_empty_list(self):
        """
        Test that embedding an empty list returns an empty result without errors. Initializes an EmbeddingService with OpenAI provider and URL, calls embed with an empty list, and asserts the returned value is an empty list.
        """
        service = EmbeddingService(
            provider="openai", api_url="https://api.openai.com/v1/embeddings"
        )

        result = await service.embed([])

        assert result == []


@pytest.mark.unit
class TestLLMServiceCallLLM:
    """Test LLMService.call_llm method."""

    @pytest.mark.asyncio
    async def test_call_llm_success(self):
        """
        Test that LLMService correctly performs an API call when the remote endpoint returns a successful 200 response, parses the JSON payload, and extracts the assistant's message content. The test constructs a minimal LLMConfig, patches aiohttp.ClientSession to return a mocked HTTP response with status 200 and a predefined JSON structure, then asserts that the service processes the response without errors.
        """
        config = LLMConfig(api_endpoint="https://api.example.com", model_name="gpt-4")
        service = LLMService(config)

        mock_response = {
            "choices": [{"message": {"role": "assistant", "content": "Test response"}}]
        }

        with patch("aiohttp.ClientSession") as MockSession:
            mock_session = MagicMock()
            mock_post = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status = 200
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            
            mock_post.__aenter__.return_value = mock_response_obj
            mock_session.post.return_value = mock_post
            MockSession.return_value.__aenter__.return_value = mock_session
            MockSession.return_value.__aexit__.return_value = AsyncMock()

            messages = [{"role": "user", "content": "Hello"}]
            result = await service.call_llm(messages)

            assert result == mock_response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
