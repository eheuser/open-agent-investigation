from typing import List, Optional
import numpy as np

from ..llm_service import EmbeddingService as CentralizedEmbeddingService

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class Embedder:
    """
    Embedding service wrapper that uses centralized EmbeddingService.

    This class maintains backward compatibility while delegating to the
    centralized service for actual API calls.

    Providers:
        - openai: OpenAI embeddings API
        - cohere: Cohere embeddings API
        - ollama: Ollama embeddings API
    """

    def __init__(
        self,
        provider: str,
        api_url: str,
        api_key: Optional[str] = None,
        model_name: str = "text-embedding-ada-002",
        timeout: int = 120,
    ):
        """
        Initialize a backward-compatible embedder that forwards requests to a centralized embedding service.

        Parameters
        ----------
        provider : str
            The name of the provider to use. Accepted values are `'openai'`, `'cohere'` and `'ollama'` (case-insensitive).
        api_url : str
            The base URL of the provider's API endpoint. This argument is required for all providers.
        api_key : Optional[str], default=None
            Authentication token for the provider. Required when `provider` is `'openai'` or `'cohere'`; ignored for Ollama which may run locally without a key.
        model_name : str, default='text-embedding-ada-002'
            Identifier of the model to request embeddings from. The default corresponds to OpenAI's Ada embedding model but can be overridden for other providers.
        timeout : int, default=120
            Request timeout in seconds. Defaults to 120 seconds (2 minutes) which is suitable for batch embedding operations.

        Notes
        -----
        The constructor creates an instance of :class:`CentralizedEmbeddingService` with the supplied arguments and stores it on `self._service`. For compatibility with legacy code, the original initialization parameters are also saved as public attributes (`provider`, `api_url`, `api_key`, `model_name`). A debug log entry is emitted indicating which provider and endpoint are being used.
        """
        # Create centralized embedding service
        self._service = CentralizedEmbeddingService(
            provider=provider,
            api_url=api_url,
            api_key=api_key,
            model_name=model_name,
            timeout=timeout,
        )

        # Keep these for backward compatibility
        self.provider = provider.lower()
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name

        logger.debug(f"Using centralized embedding service: {provider} at {api_url}")

    async def embed(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a sequence of texts using the configured centralized service.

        Parameters
        ----------
        texts : List[str]
            A list containing the text strings to be embedded. The list may be empty; in that case an empty NumPy array is returned.

        Returns
        -------
        numpy.ndarray
            A two-dimensional NumPy array where each row corresponds to the embedding of the respective input text. The shape is `(len(texts), embedding_dim)`; if `texts` is empty, an array with shape `(0,)` is returned.
        """
        if not texts:
            return np.array([])

        # Use centralized service
        embeddings = await self._service.embed(texts)
        return np.array(embeddings)

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embeddings produced by this embedder.

        Returns:
            int: The size of each embedding vector returned by the underlying service.
        """
        return self._service.get_embedding_dimension()


__all__ = ["Embedder"]
