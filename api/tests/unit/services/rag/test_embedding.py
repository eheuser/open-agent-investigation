"""
Unit tests for RAG embedding service wrapper.
Tests the Embedder wrapper class that delegates to centralized service.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag.embedding import Embedder


@pytest.mark.unit
class TestEmbedder:
    """Test Embedder wrapper class."""

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_init_openai(self, mock_service_class):
        """
        Test that initializing an :class:`Embedder` with the OpenAI provider correctly stores the supplied configuration values and creates an underlying `CentralizedEmbeddingService` instance with matching arguments. The test verifies:

        - The `provider`, `api_url`, `api_key`, and `model_name` attributes on the created `embedder` match the inputs.
        - The mocked service class is instantiated exactly once with the same keyword arguments, ensuring proper delegation to the central embedding service implementation.
        """
        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test123",
            model_name="text-embedding-ada-002",
        )

        assert embedder.provider == "openai"
        assert embedder.api_url == "https://api.openai.com/v1"
        assert embedder.api_key == "sk-test123"
        assert embedder.model_name == "text-embedding-ada-002"

        mock_service_class.assert_called_once_with(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test123",
            model_name="text-embedding-ada-002",
            embedding_max_context_length=8192,
            reranker_model_name=None,
            reranker_max_context_length=8192,
            allow_concurrent_calls=False,
            timeout=120,
        )

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_init_ollama(self, mock_service_class):
        """
        Test that initializing an Embedder with the Ollama provider correctly sets the provider attribute to "ollama" and leaves the api_key attribute as None, verifying proper handling of provider-specific configuration without requiring an API key.
        """
        embedder = Embedder(
            provider="ollama",
            api_url="http://localhost:11434",
            model_name="nomic-embed-text",
        )

        assert embedder.provider == "ollama"
        assert embedder.api_key is None

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_init_cohere(self, mock_service_class):
        """
        Test initializing an Embedder instance with the Cohere provider, verifying that the provider attribute is correctly set to "cohere" after construction.
        """
        embedder = Embedder(
            provider="cohere",
            api_url="https://api.cohere.ai/v1",
            api_key="cohere-key",
            model_name="embed-english-v3.0",
        )

        assert embedder.provider == "cohere"

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_init_case_insensitive(self, mock_service_class):
        """
        Test that the Embedder initializer normalizes the provider name to lowercase, ensuring case-insensitive handling of the `provider` argument.
        """
        embedder = Embedder(
            provider="OpenAI",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        assert embedder.provider == "openai"

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_basic(self, mock_service_class):
        """
        Test basic embedding generation.

        This test verifies that the :class:`Embedder` correctly forwards a list of texts to the underlying
        embedding service and returns the embeddings as a NumPy array with the expected shape and values.

        Parameters
        ----------
        self: object
            The test case instance (typically a subclass of `unittest.TestCase` or similar).
        mock_service_class: unittest.mock.Mock
            A patched reference to :class:`CentralizedEmbeddingService` that is replaced with a mock
            providing an asynchronous `embed` method.

        The test performs the following steps:
        1. Configures a mock embedding service whose `embed` coroutine returns a predefined 2×3 matrix.
        2. Instantiates an :class:`Embedder` configured for the "openai" provider.
        3. Calls :meth:`Embedder.embed` with two sample texts.
        4. Asserts that the result is a NumPy `ndarray` of shape `(2, 3)` and matches the mock data.
        5. Confirms that the mock service's `embed` method was invoked exactly once with the supplied
           list of texts.

        No value is returned; the function raises an assertion error if any condition fails.
        """
        mock_service = MagicMock()
        mock_service.embed = AsyncMock(
            return_value=[
                [0.1, 0.2, 0.3],
                [0.4, 0.5, 0.6],
            ]
        )
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        texts = ["Hello world", "Test text"]
        result = await embedder.embed(texts)

        assert isinstance(result, np.ndarray)
        assert result.shape == (2, 3)
        assert np.array_equal(result, np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]))
        mock_service.embed.assert_called_once_with(texts)

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_single_text(self, mock_service_class):
        """
        Test embedding of a single text input using a mocked embedding service.

        Args:
            self: The test case instance.
            mock_service_class (unittest.mock.MagicMock): Mocked class for CentralizedEmbeddingService injected by the test framework.

        The function configures a MagicMock to simulate the embed method returning a predefined 2-dimensional list, instantiates an Embedder with OpenAI provider settings, and invokes its async embed method with a single-item list. It then asserts that the resulting NumPy array has the expected shape of (1, 3).
        """
        mock_service = MagicMock()
        mock_service.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        result = await embedder.embed(["Single text"])

        assert result.shape == (1, 3)

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_empty_list(self, mock_service_class):
        """
        Test that embedding an empty list returns an empty NumPy array without invoking the underlying service.

        Parameters
        ----------
        self: object
            The test case instance.
        mock_service_class: MagicMock
            A patched reference to `CentralizedEmbeddingService` used to inject a mock service.

        Returns
        -------
        None

        Notes
        -----
        - The function creates a mock service and ensures that `Embedder.embed` returns an empty `np.ndarray` with shape `(0,)` when given an empty list.
        - It also verifies that the underlying service's `embed` method is never called for empty inputs.
        """
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        result = await embedder.embed([])

        assert isinstance(result, np.ndarray)
        assert result.shape == (0,)
        mock_service.embed.assert_not_called()

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_large_batch(self, mock_service_class):
        """
        Test embedding a large batch of texts using a mocked embedding service.

        This test verifies that the `Embedder.embed` method correctly handles a list of 100 input strings and returns an array with the expected shape (100, 1536). It sets up a mock `CentralizedEmbeddingService` that asynchronously returns pre-generated embeddings, constructs an `Embedder` instance configured for the OpenAI provider, invokes `embed` with the batch, and asserts that the resulting NumPy array has the correct dimensions.
        """
        mock_service = MagicMock()
        embeddings = [[float(i)] * 1536 for i in range(100)]
        mock_service.embed = AsyncMock(return_value=embeddings)
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        texts = [f"Text {i}" for i in range(100)]
        result = await embedder.embed(texts)

        assert result.shape == (100, 1536)

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_get_embedding_dimension(self, mock_service_class):
        """
        Test retrieving the embedding dimension from the provider.

        Sets up a mock CentralizedEmbeddingService to return a fixed dimension (1536), instantiates an `Embedder` with OpenAI configuration, calls :meth:`Embedder.get_embedding_dimension`, and asserts that the returned value matches the mocked dimension. Also verifies that the service's `get_embedding_dimension` method was invoked exactly once.
        """
        mock_service = MagicMock()
        mock_service.get_embedding_dimension.return_value = 1536
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        dim = embedder.get_embedding_dimension()

        assert dim == 1536
        mock_service.get_embedding_dimension.assert_called_once()

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_get_embedding_dimension_ollama(self, mock_service_class):
        """
        Test that the Embedder correctly retrieves the embedding dimension when configured for the Ollama provider by mocking the CentralizedEmbeddingService to return a predefined dimension value. The test verifies that `get_embedding_dimension` returns the mocked dimension (768).
        """
        mock_service = MagicMock()
        mock_service.get_embedding_dimension.return_value = 768
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="ollama",
            api_url="http://localhost:11434",
            model_name="nomic-embed-text",
        )

        dim = embedder.get_embedding_dimension()

        assert dim == 768

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_unicode_text(self, mock_service_class):
        """
        Test that the Embedder correctly handles Unicode input strings.

        Creates a mock CentralizedEmbeddingService with an asynchronous `embed` method returning a fixed embedding vector.
        Initializes an `Embedder` instance configured for the OpenAI provider.
        Calls `embed` on a list containing Japanese, Chinese, and Korean text samples.
        Asserts that the underlying service's `embed` method is invoked exactly once with the original list of Unicode texts.
        """
        mock_service = MagicMock()
        mock_service.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        texts = ["日本語のテキスト", "中文文本", "한국어 텍스트"]
        await embedder.embed(texts)

        mock_service.embed.assert_called_once_with(texts)

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_long_text(self, mock_service_class):
        """
        Test that the Embedder correctly handles embedding of an extremely long input string by verifying the returned array has the expected shape (1, 1536) when using a mocked CentralizedEmbeddingService. The test sets up a mock service that returns a fixed-size embedding vector, creates an Embedder instance configured for the OpenAI provider, generates a very long text composed of repeated words, invokes the asynchronous embed method with this text, and asserts that the resulting NumPy array matches the expected dimensions.
        """
        mock_service = MagicMock()
        mock_service.embed = AsyncMock(return_value=[[0.1] * 1536])
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        long_text = "word " * 10000  # Very long text
        result = await embedder.embed([long_text])

        assert result.shape == (1, 1536)

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_special_characters(self, mock_service_class):
        """
        Test that the Embedder correctly forwards texts containing special characters to the underlying embedding service.

        This test creates a mock CentralizedEmbeddingService with an async `embed` method returning a dummy embedding vector. An `Embedder` instance is instantiated using the "openai" provider and dummy API credentials. A list of strings featuring various special characters-including punctuation, whitespace control characters, and escaped quotes-is passed to `embed`. The test asserts that the mock service's `embed` method is called exactly once with the original list of texts, confirming that the Embedder does not alter or filter special characters before delegating the request.
        """
        mock_service = MagicMock()
        mock_service.embed = AsyncMock(return_value=[[0.1, 0.2]])
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        texts = ["Text with @#$%^&*()", "Line\nbreak\ttest", 'Quote "test"']
        await embedder.embed(texts)

        mock_service.embed.assert_called_once_with(texts)

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_embed_returns_numpy_array(self, mock_service_class):
        """
        Test that the `embed` method of :class:`Embedder` always returns a NumPy `ndarray` with a floating-point dtype.\n\nThe test patches :class:`CentralizedEmbeddingService` (via `mock_service_class`) so that its `embed` coroutine returns a deterministic list of floats. An :class:`Embedder` instance is created with dummy OpenAI credentials, and its asynchronous `embed` method is called with a single-element list.\n\nAssertions verify that:\n- The returned object's type name is `'ndarray'` (i.e., it is a NumPy array).\n- The array's `dtype` is either `np.float32` or `np.float64`, ensuring the result is a floating-point vector suitable for downstream processing.\n\nParameters\n----------\nmock_service_class : MagicMock\n    A mock of the `CentralizedEmbeddingService` class injected by the test framework. The mock's `return_value` is configured to provide an object whose `embed` coroutine yields a predefined embedding list.\n\nReturns\n-------\nNone\n    The function uses assertions for validation and does not return a value.
        """
        mock_service = MagicMock()
        mock_service.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
        )

        result = await embedder.embed(["test"])

        assert type(result).__name__ == "ndarray"
        assert result.dtype in [np.float32, np.float64]

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_backward_compatibility_attributes(self, mock_service_class):
        """
        Test that backward-compatibility attributes are preserved on an Embedder instance.

        This test creates an `Embedder` with explicit provider, API URL, API key, and model name arguments. It then verifies that the legacy attribute names (`provider`, `api_url`, `api_key`, and `model_name`) exist on the object and that their values are correctly normalized (e.g., the provider is lower-cased). The test ensures older code relying on these attributes continues to function after refactoring.
        """
        embedder = Embedder(
            provider="OpenAI",
            api_url="https://api.openai.com/v1",
            api_key="sk-test",
            model_name="text-embedding-3-small",
        )

        # These attributes should be accessible for backward compatibility
        assert hasattr(embedder, "provider")
        assert hasattr(embedder, "api_url")
        assert hasattr(embedder, "api_key")
        assert hasattr(embedder, "model_name")
        assert embedder.provider == "openai"
        assert embedder.model_name == "text-embedding-3-small"

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    async def test_rerank_delegation(self, mock_service_class):
        """
        Test that Embedder.rerank properly delegates to the centralized service.
        """
        mock_service = MagicMock()
        mock_service.rerank = AsyncMock(return_value=[
            {"index": 1, "score": 0.9},
            {"index": 0, "score": 0.7},
        ])
        mock_service_class.return_value = mock_service

        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-test",
            reranker_model_name="text-embedding-3-large",
        )

        result = await embedder.rerank(
            query="test query",
            documents=["doc 1", "doc 2"],
            top_k=2
        )

        assert len(result) == 2
        assert result[0]["score"] == 0.9
        mock_service.rerank.assert_called_once_with("test query", ["doc 1", "doc 2"], 2)

    @patch("app.services.rag.embedding.CentralizedEmbeddingService")
    def test_reranker_model_name_attribute(self, mock_service_class):
        """
        Test that Embedder stores reranker_model_name attribute.
        """
        embedder = Embedder(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            reranker_model_name="text-embedding-3-large",
        )

        assert embedder.reranker_model_name == "text-embedding-3-large"
