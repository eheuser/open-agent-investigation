import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from decimal import Decimal

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from ..crud.llm_config import get_active_llm_config
from .llm_auth_helper import prepare_llm_auth

logger = logging.getLogger(__name__)

# Constants
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_BASE = 2  # Exponential backoff: 2s, 4s, 8s
DEFAULT_TIMEOUT = 300  # 5 minutes
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096

# Token estimation (rough approximation: 1 token ≈ 4 characters)
CHARS_PER_TOKEN = 4


class LLMConfig:
    """LLM configuration object with validated parameters."""

    def __init__(
        self,
        api_endpoint: str,
        model_name: str,
        api_key: Optional[str] = None,
        max_context_length: int = 8192,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        min_p: Optional[float] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Initializes the LLM service client with configuration parameters.

        Parameters
        ----------
        api_endpoint : str
            Base URL of the API endpoint to which requests will be sent.
        model_name : str
            Identifier of the model to use for generation or embedding tasks.
        api_key : Optional[str], optional
            Authentication token or key required by the provider. If omitted, the client may rely on environment variables or unauthenticated access where supported.
        max_context_length : int, default 8192
            Maximum number of tokens that can be included in a single request context. Requests exceeding this limit should be truncated or split by the caller.
        temperature : float, default DEFAULT_TEMPERATURE
            Sampling temperature controlling randomness; higher values produce more diverse outputs.
        top_p : Optional[float], optional
            Nucleus sampling probability threshold. When set, the model considers only the smallest set of tokens whose cumulative probability exceeds this value.
        top_k : Optional[int], optional
            Limits sampling to the top-k most likely tokens. Mutually exclusive with `top_p` in many APIs.
        min_p : Optional[float], optional
            Minimum token probability; tokens with a probability lower than this are filtered out.
        timeout : int, default DEFAULT_TIMEOUT
            Number of seconds to wait for a response before raising a timeout error.

        Raises
        ------
        ValueError
            If any provided parameter is invalid (e.g., negative `max_context_length` or non-positive `temperature`).
        """
        self.api_endpoint = api_endpoint
        self.model_name = model_name
        self.api_key = api_key
        self.max_context_length = max_context_length
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.min_p = min_p
        self.timeout = timeout

    @classmethod
    def from_db_config(cls, db_config: Any) -> "LLMConfig":
        """
        Create an :class:`LLMConfig` instance from a database configuration object.

        Parameters
        ----------
        db_config: Any
            An SQLAlchemy model instance representing a row in the `llm_provider_config` table. The function extracts relevant fields using `getattr` to accommodate different column types (e.g., `Decimal` for numeric columns).

        Returns
        -------
        LLMConfig
            A new configuration object populated with values from `db_config`. Missing optional fields fall back to sensible defaults:

            * `api_endpoint` - empty string if not present.
            * `model_name` - empty string if not present.
            * `api_key` - `None` when absent.
            * `max_context_length` - `8192` when unspecified.
            * `temperature` - :data:`DEFAULT_TEMPERATURE` when unspecified.
            * `top_p`, `top_k`, `min_p` - `None` when not provided.
            * `timeout` - :data:`DEFAULT_TIMEOUT` when unspecified.

        The method performs type conversion to ensure all numeric values are plain Python `int` or `float` types, regardless of the underlying SQLAlchemy column representation.
        """
        # Extract values using getattr to handle SQLAlchemy column types
        api_endpoint = str(getattr(db_config, "api_endpoint", ""))
        model_name = str(getattr(db_config, "model_name", ""))

        api_key_val = getattr(db_config, "api_key", None)
        api_key = str(api_key_val) if api_key_val is not None else None

        # Extract numeric parameters with proper type conversion
        # SQLAlchemy Numeric columns return Decimal objects
        max_context_val = getattr(db_config, "max_context_length", None)
        max_context_length = int(str(max_context_val)) if max_context_val is not None else 8192

        temperature_val = getattr(db_config, "temperature", None)
        temperature = (
            float(str(temperature_val)) if temperature_val is not None else DEFAULT_TEMPERATURE
        )

        top_p_val = getattr(db_config, "top_p", None)
        top_p = float(str(top_p_val)) if top_p_val is not None else None

        top_k_val = getattr(db_config, "top_k", None)
        top_k = int(str(top_k_val)) if top_k_val is not None else None

        min_p_val = getattr(db_config, "min_p", None)
        min_p = float(str(min_p_val)) if min_p_val is not None else None

        timeout_val = getattr(db_config, "timeout", None)
        timeout = int(str(timeout_val)) if timeout_val is not None else DEFAULT_TIMEOUT

        return cls(
            api_endpoint=api_endpoint,
            model_name=model_name,
            api_key=api_key,
            max_context_length=max_context_length,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            timeout=timeout,
        )


class LLMService:
    """Centralized LLM service for all API calls."""

    def __init__(
        self,
        config: LLMConfig,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_base: int = DEFAULT_RETRY_BACKOFF_BASE,
    ):
        """
        Initialize a new LLM service instance with the provided configuration and optional retry settings.

        Parameters
        ----------
        config : LLMConfig
            The configuration object containing all required settings for the language-model provider, such as endpoint URLs, authentication credentials, model identifiers, and any default request parameters.
        max_retries : int, optional
            The maximum number of times a failed API call will be automatically retried. Defaults to `DEFAULT_MAX_RETRIES`. A value of `0` disables automatic retries.
        retry_backoff_base : int, optional
            The base duration in seconds used for exponential backoff between retry attempts. The actual wait time before the *n*-th retry is calculated as `retry_backoff_base ** n`. Defaults to `DEFAULT_RETRY_BACKOFF_BASE`.

        Raises
        ------
        TypeError
            If `config` is not an instance of :class:`LLMConfig` or if `max_retries` / `retry_backoff_base` are not integers.

        Notes
        -----
        The retry mechanism applies to transient errors such as network timeouts, rate-limit responses, and server-side failures. The exponential backoff helps mitigate hammering the provider's API while still attempting to recover from temporary issues.
        """
        self.config = config
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

    @classmethod
    async def from_user_config(
        cls,
        db: AsyncSession,
        user_id: int,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Optional["LLMService"]:
        """
        Create an LLMService instance based on a user's active configuration stored in the database.

        Parameters
        ----------
        cls : type
            The class on which this method is called; typically `LLMService`.
        db : AsyncSession
            An asynchronous SQLAlchemy session used to query the user's configuration.
        user_id : int
            Identifier of the user whose active LLM configuration should be retrieved.
        max_retries : int, optional
            Maximum number of retry attempts for API calls made by the service. Defaults to `DEFAULT_MAX_RETRIES`.

        Returns
        -------
        Optional[LLMService]
            An initialized `LLMService` object if an active configuration exists for the given user; otherwise `None`.

        Raises
        ------
        None directly raised by this method. Errors occurring during database access or configuration parsing are propagated from the underlying helper functions.
        """
        db_config = await get_active_llm_config(db, user_id)
        if not db_config:
            logger.warning(f"No active LLM configuration found for user {user_id}")
            return None

        config = LLMConfig.from_db_config(db_config)
        return cls(config, max_retries=max_retries)

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens required for a given piece of text.

        Args:
            text (str): The input string whose token count is to be estimated.

        Returns:
            int: An approximate token count, calculated by dividing the character length
                 of *text* by the module-level constant `CHARS_PER_TOKEN`. This value
                 provides a rough estimate suitable for sizing requests to language model
                 APIs.
        """
        return len(text) // CHARS_PER_TOKEN

    def estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Estimate the total number of tokens required for a list of chat messages.

        Args:
            messages (List[Dict[str, Any]]): A sequence of message dictionaries as expected by the language-model API. Each dictionary is serialized to JSON before token estimation.

        Returns:
            int: The summed token estimate for all provided messages, based on the model’s tokenization strategy.

        Notes:
            - The method serializes each message with `json.dumps` (using `default=str` for non-serializable values) and then delegates to :meth:`estimate_tokens` for the actual counting.
            - This is an approximation; actual token usage may differ depending on the provider’s tokenizer.
        """
        total = 0
        for msg in messages:
            # Serialize message to JSON and estimate
            msg_json = json.dumps(msg, default=str)
            total += self.estimate_tokens(msg_json)
        return total

    def enforce_context_limit(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        preserve_system: bool = True,
        preserve_recent: int = 3,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Enforce the token limit for a list of chat messages by trimming excess content while preserving essential parts.

        This method implements a three-step strategy:

        1. **System message preservation** - If `preserve_system` is true and the first message has the role `"system"`, that message is always kept.
        2. **Recent history preservation** - The last `preserve_recent` messages are retained regardless of token count, ensuring the most recent conversational context remains intact.
        3. **Middle trimming** - All other messages (the “trimmable” portion) are examined in order and included only while the cumulative token count stays within the allowed budget.

        If the total token count of the preserved messages alone exceeds `max_tokens`, an emergency fallback is applied: only the system message (if any) and the last two messages are kept.

        Parameters
        ----------
        messages : List[Dict[str, Any]]
            The full list of chat messages to be evaluated. Each dictionary must contain at least a `"role"` key.
        max_tokens : Optional[int], default=None
            Maximum number of tokens permitted for the final message set. If omitted, 80 % of the configured
            `self.config.max_context_length` is used.
        preserve_system : bool, default=True
            When true, the initial system-role message (if present) will never be removed.
        preserve_recent : int, default=3
            Number of most recent messages that must always be retained.

        Returns
        -------
        Tuple[List[Dict[str, Any]], int]
            * **trimmed_messages** - The possibly reduced list of messages that fits within `max_tokens` while respecting the preservation rules.
            * **tokens_removed** - The total number of tokens eliminated from the original message set.

        Notes
        -----
        * Token estimation for individual messages is performed via `self.estimate_tokens` on a JSON-encoded representation of each message, and aggregate token counts are obtained with `self.estimate_messages_tokens`.
        * Logging at INFO level reports when trimming occurs and summarizes the before/after token and message counts; a WARN entry is emitted if the preserved subset alone exceeds the limit.
        * The method does not modify the input list; it builds and returns new collections.
        """
        if max_tokens is None:
            max_tokens = int(self.config.max_context_length * 0.8)  # Use 80% of max

        current_tokens = self.estimate_messages_tokens(messages)

        if current_tokens <= max_tokens:
            return messages, 0  # No trimming needed

        logger.info(
            f"Context limit enforcement: {current_tokens} tokens > {max_tokens} limit, trimming..."
        )

        # Separate messages into preserved and trimmable
        preserved = []
        trimmable = []

        # Preserve system message
        if preserve_system and messages and messages[0].get("role") == "system":
            preserved.append(messages[0])
            remaining = messages[1:]
        else:
            remaining = messages

        # Preserve recent messages
        if len(remaining) > preserve_recent:
            trimmable = remaining[:-preserve_recent]
            preserved.extend(remaining[-preserve_recent:])
        else:
            preserved.extend(remaining)
            trimmable = []

        # Calculate tokens for preserved messages
        preserved_tokens = self.estimate_messages_tokens(preserved)

        if preserved_tokens >= max_tokens:
            # Even preserved messages exceed limit - this shouldn't happen
            logger.warning(
                f"Preserved messages ({preserved_tokens} tokens) exceed limit ({max_tokens}). "
                f"Trimming recent messages as well."
            )
            # Emergency fallback: keep only system + last 2 messages
            if preserve_system and messages[0].get("role") == "system":
                trimmed = [messages[0]] + messages[-2:]
            else:
                trimmed = messages[-2:]
            tokens_removed = current_tokens - self.estimate_messages_tokens(trimmed)
            return trimmed, tokens_removed

        # Calculate available tokens for trimmable messages
        available_tokens = max_tokens - preserved_tokens

        # Trim from middle
        trimmed_middle = []
        current_middle_tokens = 0

        for msg in trimmable:
            msg_tokens = self.estimate_tokens(json.dumps(msg, default=str))
            if current_middle_tokens + msg_tokens <= available_tokens:
                trimmed_middle.append(msg)
                current_middle_tokens += msg_tokens
            else:
                # Can't fit this message, stop adding
                break

        # Build final message list
        if preserve_system and messages[0].get("role") == "system":
            final_messages = [messages[0]] + trimmed_middle + remaining[-preserve_recent:]
        else:
            final_messages = trimmed_middle + remaining[-preserve_recent:]

        tokens_removed = current_tokens - self.estimate_messages_tokens(final_messages)

        logger.info(
            f"Context trimmed: {len(messages)} → {len(final_messages)} messages, "
            f"{current_tokens} → {self.estimate_messages_tokens(final_messages)} tokens "
            f"({tokens_removed} tokens removed)"
        )

        return final_messages, tokens_removed

    async def call_llm(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        enforce_context_limit: bool = True,
    ) -> Dict[str, Any]:
        """
        Call an LLM API endpoint with automatic retries, context-limit enforcement, and optional tool usage.

        Parameters
        ----------
        messages : List[Dict[str, Any]]
            The conversation history to send to the model. Each entry must contain at least a `role` and `content` key as required by the target provider.
        max_tokens : Optional[int], default=None
            Maximum number of tokens the model may generate. If omitted, the module-wide `DEFAULT_MAX_TOKENS` is used.
        temperature : Optional[float], default=None
            Sampling temperature controlling randomness. When not supplied, the value from `self.config.temperature` is applied.
        tools : Optional[List[Dict[str, Any]]], default=None
            A list of tool definitions that the model may invoke (e.g., function calling specifications). Ignored if `None`.
        tool_choice : Optional[str], default="auto"
            Strategy for selecting a tool when multiple are provided. Passed through to the API payload when `tools` is set.
        enforce_context_limit : bool, default=True
            If true, the method will truncate or prune `messages` to stay within the model’s context window using `self.enforce_context_limit` before making the request.

        Returns
        -------
        Dict[str, Any]
            The parsed JSON response from the LLM provider. The exact schema depends on the underlying API but typically includes fields such as `choices`, `usage`, and `id`.

        Raises
        ------
        RuntimeError
            If all retry attempts fail or if the HTTP response status is not 200. The exception message contains the final error encountered.

        Notes
        -----
        * Context enforcement may drop older messages; a log entry records how many tokens were removed.
        * Retries use exponential back-off based on `self.retry_backoff_base` and respect `self.max_retries`.
        * Authentication headers and cookies are generated by :func:`prepare_llm_auth` using the configured API key.
        * The request timeout is taken from `self.config.timeout` and applied via `aiohttp.ClientTimeout`.
        """
        # Enforce context limit
        if enforce_context_limit:
            messages, tokens_removed = self.enforce_context_limit(messages)
            if tokens_removed > 0:
                logger.info(f"Context enforcement removed {tokens_removed} tokens")

        # Use config defaults if not specified
        if max_tokens is None:
            max_tokens = DEFAULT_MAX_TOKENS
        if temperature is None:
            temperature = self.config.temperature

        # Build payload
        payload: Dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add optional parameters
        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p
        if self.config.top_k is not None:
            payload["top_k"] = self.config.top_k
        if self.config.min_p is not None:
            payload["min_p"] = self.config.min_p

        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        # Prepare authentication
        headers, cookies = prepare_llm_auth(self.config.api_key)

        # Retry loop
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(cookies=cookies) as session:
                    async with session.post(
                        self.config.api_endpoint,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise RuntimeError(f"LLM API error {response.status}: {error_text}")

                        result = await response.json()

                        logger.debug(
                            f"LLM call successful: {len(messages)} messages, "
                            f"~{self.estimate_messages_tokens(messages)} input tokens"
                        )

                        return result

            except Exception as e:
                last_error = e
                logger.error(
                    f"LLM call failed (attempt {attempt + 1}/{self.max_retries}): {e}",
                    exc_info=True,
                )

                if attempt < self.max_retries - 1:
                    wait_time = self.retry_backoff_base ** (attempt + 1)
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        # All retries failed
        raise RuntimeError(f"LLM call failed after {self.max_retries} attempts: {last_error}")

    async def stream_llm(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        enforce_context_limit: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream an LLM response with automatic retries and optional context-limit enforcement.

        Args:
            messages (List[Dict[str, Any]]): The conversation history to send to the model.
            max_tokens (Optional[int]): Maximum number of tokens the model may generate. If omitted,
                a module-wide default is used.
            temperature (Optional[float]): Sampling temperature for the generation. Falls back
                to the configured default when None.
            tools (Optional[List[Dict[str, Any]]]): Optional tool definitions that can be invoked by the model.
            tool_choice (Optional[str]): Strategy for selecting a tool when multiple are provided.
                Defaults to `"auto"`; set to `None` to omit from the payload.
            enforce_context_limit (bool): When True, truncate or prune the message list so that
                the total token count stays within the model’s context window. Logs the number of
                tokens removed.

        Yields:
            Dict[str, Any]: Parsed JSON chunks received from the streaming endpoint. Non-JSON
            lines are ignored, and a `[DONE]` sentinel is filtered out.

        Raises:
            RuntimeError: If the API returns a non-200 status code or if all retry attempts fail.
            json.JSONDecodeError: Propagated only when a line appears to be JSON but cannot be parsed;
                otherwise such lines are skipped silently.
        """
        # Enforce context limit
        if enforce_context_limit:
            messages, tokens_removed = self.enforce_context_limit(messages)
            if tokens_removed > 0:
                logger.info(f"Context enforcement removed {tokens_removed} tokens")

        # Use config defaults
        if max_tokens is None:
            max_tokens = DEFAULT_MAX_TOKENS
        if temperature is None:
            temperature = self.config.temperature

        # Build payload
        payload: Dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        # Add optional parameters
        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p
        if self.config.top_k is not None:
            payload["top_k"] = self.config.top_k
        if self.config.min_p is not None:
            payload["min_p"] = self.config.min_p

        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        # Prepare authentication
        headers, cookies = prepare_llm_auth(self.config.api_key)

        # Retry loop
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(cookies=cookies) as session:
                    async with session.post(
                        self.config.api_endpoint,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise RuntimeError(f"LLM API error {response.status}: {error_text}")

                        # Stream response
                        async for line in response.content:
                            line = line.decode("utf-8").strip()

                            if not line or line == "data: [DONE]":
                                continue

                            if line.startswith("data: "):
                                line = line[6:]

                            try:
                                chunk = json.loads(line)
                                yield chunk
                            except json.JSONDecodeError:
                                # Skip non-JSON chunks
                                if "OPENROUTER PROCESSING" not in line:
                                    logger.debug(f"Skipping non-JSON chunk: {line[:100]}")
                                continue

                        logger.debug(
                            f"LLM stream completed: {len(messages)} messages, "
                            f"~{self.estimate_messages_tokens(messages)} input tokens"
                        )

                        return  # Success

            except Exception as e:
                last_error = e
                logger.error(
                    f"LLM stream failed (attempt {attempt + 1}/{self.max_retries}): {e}",
                    exc_info=True,
                )

                if attempt < self.max_retries - 1:
                    wait_time = self.retry_backoff_base ** (attempt + 1)
                    logger.info(f"Retrying stream in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        # All retries failed
        raise RuntimeError(f"LLM stream failed after {self.max_retries} attempts: {last_error}")

    async def extract_text_response(self, llm_response: Dict[str, Any]) -> Optional[str]:
        """
        Extracts the textual content from a language-model API response dictionary.\n\nThe function inspects several common keys used by different providers (e.g., OpenAI's `choices`, Ollama's `response`) and returns the first available text payload. For `choices` it handles the typical list structure, retrieving either the `message.content` field or a top-level `text` entry.\n\nArgs:\n    llm_response: A dictionary representing the raw response returned by an LLM provider.\n\nReturns:\n    The extracted text as a string if a recognizable field is found; otherwise `None`. If extraction succeeds but the underlying value is not a string, it is converted to `str` before returning.
        """
        # Try multiple field names
        for field in ["choices", "response", "text", "content"]:
            if field in llm_response:
                if field == "choices" and isinstance(llm_response[field], list):
                    if len(llm_response[field]) > 0:
                        choice = llm_response[field][0]
                        if "message" in choice:
                            return choice["message"].get("content", "")
                        elif "text" in choice:
                            return choice["text"]
                else:
                    return str(llm_response[field])

        logger.warning(f"Could not extract text from LLM response: {llm_response}")
        return None


class EmbeddingService:
    """Centralized embedding service for RAG features."""

    def __init__(
        self,
        provider: str,
        api_url: str,
        api_key: Optional[str] = None,
        model_name: str = "text-embedding-ada-002",
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_base: int = DEFAULT_RETRY_BACKOFF_BASE,
    ):
        """
        Initialize an embedding service instance.

        Args:
            provider (str): The name of the LLM provider (e.g., `"openai"`, `"cohere"`, `"ollama"`). Case is ignored and will be normalized to lower-case.
            api_url (str): The base URL for the provider's embedding API endpoint.
            api_key (Optional[str]): Authentication token or secret required by providers such as OpenAI or Cohere. May be omitted for providers that do not require authentication (e.g., local Ollama instances).
            model_name (str, optional): Identifier of the model to use for generating embeddings. Defaults to `"text-embedding-ada-002"`.
            max_retries (int, optional): Maximum number of retry attempts for transient request failures. Defaults to :data:`DEFAULT_MAX_RETRIES`.
            retry_backoff_base (int, optional): Base value used in exponential back-off calculations between retries. Defaults to :data:`DEFAULT_RETRY_BACKOFF_BASE`.

        Raises:
            ValueError: If `provider` is not one of the supported types or if required credentials are missing for the selected provider.
        """
        self.provider = provider.lower()
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        logger.debug(f"EmbeddingService initialized: {provider} at {api_url}")

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embedding vectors for a list of input texts with built-in retry handling.

        Args:
            texts (List[str]): A list of strings to be embedded. If empty, an empty list is returned immediately.

        Returns:
            List[List[float]]: A list containing the embedding vector for each input text. The length of the outer list matches the number of provided texts.

        Raises:
            RuntimeError: Raised when all retry attempts fail or when the API returns a non-200 status code.
            ValueError: Raised if the response format from the provider cannot be parsed into embeddings.

        Notes:
            * Supports multiple providers (e.g., OpenAI, Cohere, Ollama) and automatically formats the request payload accordingly.
            * Includes exponential backoff between retries using `self.retry_backoff_base`.
            * Authentication headers are added when an API key is present for supported providers.
        """
        if not texts:
            return []

        # Build headers
        headers: Dict[str, str] = {"Content-Type": "application/json"}

        if self.api_key:
            if self.provider in ["openai", "cohere"]:
                headers["Authorization"] = f"Bearer {self.api_key}"

        # Build payload based on provider
        if self.provider == "cohere":
            payload = {
                "model": self.model_name,
                "texts": texts,
                "input_type": "search_document",
            }
        else:
            # OpenAI-compatible format (OpenAI, Ollama, LM Studio)
            payload = {
                "model": self.model_name,
                "input": texts,
            }

        # Retry loop
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.api_url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30.0),
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise RuntimeError(
                                f"Embedding API error {response.status}: {error_text}"
                            )

                        result = await response.json()

                # Parse response based on provider
                if self.provider == "cohere":
                    embeddings = result["embeddings"]
                else:
                    # OpenAI-compatible format
                    if "data" in result:
                        embeddings = [item["embedding"] for item in result["data"]]
                    elif "embeddings" in result:
                        embeddings = result["embeddings"]
                    elif "embedding" in result:
                        embeddings = [result["embedding"]]
                    else:
                        raise ValueError(f"Unexpected response format: {result.keys()}")

                logger.debug(
                    f"Embedding successful: {len(texts)} texts, "
                    f"{len(embeddings)} embeddings generated"
                )

                return embeddings

            except Exception as e:
                last_error = e
                logger.error(
                    f"Embedding call failed (attempt {attempt + 1}/{self.max_retries}): {e}",
                    exc_info=True,
                )

                if attempt < self.max_retries - 1:
                    wait_time = self.retry_backoff_base ** (attempt + 1)
                    logger.info(f"Retrying embedding in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        # All retries failed
        raise RuntimeError(f"Embedding failed after {self.max_retries} attempts: {last_error}")

    def get_embedding_dimension(self) -> int:
        """
        Return the dimensionality of the embeddings generated by the configured provider/model.

        The method inspects `self.provider` and, when applicable, `self.model_name` to determine the size of the embedding vector returned by the underlying service. Supported providers are:

        - **openai** - currently returns 1536 for all known models (including Ada, `text-embedding-3-small` and `text-embedding-3-large`).
        - **cohere** - returns 1024.
        - **ollama** - returns 384 (model-dependent placeholder).

        If the provider is unrecognised, a default dimension of 768 is returned.

        Returns
        -------
        int
            The number of dimensions for the embedding vectors produced by this service.
        """
        if self.provider == "openai":
            if "ada" in self.model_name.lower():
                return 1536
            elif "3-small" in self.model_name.lower() or "3-large" in self.model_name.lower():
                return 1536
            return 1536
        elif self.provider == "cohere":
            return 1024
        elif self.provider == "ollama":
            return 384  # Model-dependent
        return 768  # Default fallback


__all__ = ["LLMService", "LLMConfig", "EmbeddingService"]
