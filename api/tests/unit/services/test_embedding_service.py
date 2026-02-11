import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.llm_service import EmbeddingService


@pytest.mark.unit
class TestEmbeddingService:
    """Test EmbeddingService initialization and basic functionality."""

    def test_embedding_service_init(self):
        """Test EmbeddingService initialization with all parameters."""
        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-test123",
            model_name="text-embedding-3-small",
            embedding_max_context_length=8192,
            reranker_model_name="text-embedding-3-large",
            reranker_max_context_length=8192,
            allow_concurrent_calls=True,
            timeout=120,
        )

        assert service.provider == "openai"
        assert service.model_name == "text-embedding-3-small"
        assert service.reranker_model_name == "text-embedding-3-large"
        assert service.embedding_max_context_length == 8192
        assert service.reranker_max_context_length == 8192
        assert service.allow_concurrent_calls is True

    def test_embedding_service_defaults(self):
        """Test that EmbeddingService applies correct defaults."""
        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
        )

        assert service.model_name == "text-embedding-ada-002"
        assert service.embedding_max_context_length == 8192
        assert service.reranker_max_context_length == 8192
        assert service.allow_concurrent_calls is False
        # Reranker should default to embedding model
        assert service.reranker_model_name == "text-embedding-ada-002"

    def test_token_estimation(self):
        """Test token estimation logic (1 token ≈ 4 characters)."""
        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
        )

        # Test various text lengths
        assert service._estimate_tokens("test") == 1  # 4 chars = 1 token
        assert service._estimate_tokens("a" * 100) == 25  # 100 chars = 25 tokens
        assert service._estimate_tokens("a" * 8192) == 2048  # 8192 chars = 2048 tokens

    def test_get_embedding_dimension(self):
        """Test embedding dimension detection for different providers."""
        # OpenAI
        service_openai = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            model_name="text-embedding-3-small",
        )
        assert service_openai.get_embedding_dimension() == 1536

        # Cohere
        service_cohere = EmbeddingService(
            provider="cohere",
            api_url="https://api.cohere.ai/v1/embed",
        )
        assert service_cohere.get_embedding_dimension() == 1024

        # Ollama
        service_ollama = EmbeddingService(
            provider="ollama",
            api_url="http://localhost:11434/api/embeddings",
        )
        assert service_ollama.get_embedding_dimension() == 384


@pytest.mark.unit
@pytest.mark.asyncio
class TestEmbeddingServiceAsync:
    """Test async embedding methods."""

    async def test_embed_empty_list(self):
        """Test that embedding empty list returns empty list."""
        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
        )

        result = await service.embed([])
        assert result == []

    @patch('aiohttp.ClientSession')
    async def test_embed_single_text(self, mock_session_class):
        """Test embedding a single text."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "data": [
                {"embedding": [0.1, 0.2, 0.3]}
            ]
        })

        # Create proper async context manager mock
        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session_ctx

        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-test123",
        )

        result = await service.embed(["test text"])

        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]

    @patch('aiohttp.ClientSession')
    async def test_embed_concurrent_calls(self, mock_session_class):
        """Test that concurrent embedding is triggered for large batches."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "data": [{"embedding": [0.1] * 1536} for _ in range(50)]
        })

        # Create proper async context manager mock
        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session_ctx

        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-test123",
            allow_concurrent_calls=True,
        )

        # Create 100 texts to trigger concurrent processing (threshold is 50)
        texts = [f"text {i}" for i in range(100)]
        result = await service.embed(texts)

        # Should return 100 embeddings
        assert len(result) == 100

    @patch('aiohttp.ClientSession')
    async def test_rerank_basic(self, mock_session_class):
        """Test basic reranking functionality."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "results": [
                {"index": 1, "score": 0.9},
                {"index": 0, "score": 0.7},
            ]
        })

        # Create proper async context manager mock
        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session_ctx

        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-test123",
            reranker_model_name="text-embedding-3-large",
        )

        result = await service.rerank(
            query="test query",
            documents=["doc 1", "doc 2"],
            top_k=2
        )

        assert len(result) == 2
        assert result[0]["index"] == 1
        assert result[0]["score"] == 0.9

    @patch('aiohttp.ClientSession')
    async def test_rerank_empty_documents(self, mock_session_class):
        """Test that reranking empty list returns empty list."""
        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
        )

        result = await service.rerank(query="test", documents=[])
        assert result == []

    @patch('aiohttp.ClientSession')
    async def test_rerank_concurrent_calls(self, mock_session_class):
        """Test that concurrent reranking is triggered for large document sets."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "results": [{"index": i, "score": 0.5} for i in range(100)]
        })

        # Create proper async context manager mock
        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session_ctx

        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-test123",
            reranker_model_name="text-embedding-3-large",
            allow_concurrent_calls=True,
        )

        # Create 150 documents to trigger concurrent processing (threshold is 100)
        documents = [f"document {i}" for i in range(150)]
        result = await service.rerank(query="test query", documents=documents, top_k=50)

        # Should return top 50 after reranking
        assert len(result) <= 50

    @patch('aiohttp.ClientSession')
    async def test_embed_with_retry(self, mock_session_class):
        """Test that embedding retries on failure."""
        # First call fails, second succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status = 500
        mock_response_fail.text = AsyncMock(return_value="Server error")

        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json = AsyncMock(return_value={
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        })

        # Create proper async context manager mocks
        mock_post_ctx_fail = AsyncMock()
        mock_post_ctx_fail.__aenter__ = AsyncMock(return_value=mock_response_fail)
        mock_post_ctx_fail.__aexit__ = AsyncMock(return_value=None)

        mock_post_ctx_success = AsyncMock()
        mock_post_ctx_success.__aenter__ = AsyncMock(return_value=mock_response_success)
        mock_post_ctx_success.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=[mock_post_ctx_fail, mock_post_ctx_success])

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session_ctx

        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-test123",
            max_retries=2,
        )

        result = await service.embed(["test"])

        # Should succeed on second attempt
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]


@pytest.mark.unit
class TestEmbeddingServiceTokenWarnings:
    """Test token limit warning logic."""

    @patch('app.services.llm_service.logger')
    @patch('aiohttp.ClientSession')
    async def test_embed_token_limit_warning(self, mock_session_class, mock_logger):
        """Test that warning is logged when text exceeds token limit."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "data": [{"embedding": [0.1] * 1536}]
        })

        # Create proper async context manager mock
        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session_ctx

        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            embedding_max_context_length=100,  # Very low limit
        )

        # Text with ~500 tokens (2000 chars)
        long_text = "a" * 2000
        await service.embed([long_text])

        # Should have logged a warning
        mock_logger.info.assert_called()
        warning_call = mock_logger.info.call_args[0][0]
        assert "exceeds embedding model token limit" in warning_call

    @patch('app.services.llm_service.logger')
    @patch('aiohttp.ClientSession')
    async def test_rerank_token_limit_warning(self, mock_session_class, mock_logger):
        """Test that warning is logged when reranking query/documents exceed token limit."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "results": [{"index": 0, "score": 0.9}]
        })

        # Create proper async context manager mock
        mock_post_ctx = AsyncMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session_ctx

        service = EmbeddingService(
            provider="openai",
            api_url="https://api.openai.com/v1/embeddings",
            reranker_model_name="text-embedding-3-large",
            reranker_max_context_length=100,  # Very low limit
        )

        # Long query and document
        long_query = "a" * 5000  # ~500 tokens
        long_doc = "b" * 5000    # ~500 tokens
        
        await service.rerank(query=long_query, documents=[long_doc])

        # Should have logged warnings for both query and document
        assert mock_logger.info.call_count >= 2
