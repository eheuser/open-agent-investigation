import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

# Add parent directories to path to import from api.app
worker_dir = Path(__file__).parent.parent
api_dir = worker_dir.parent
if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

from app.services.llm_service import LLMService, LLMConfig

from ..models import AssistantMessage, ToolCall

logger = logging.getLogger(__name__)

DEBUG = False


class LLMClient:
    """LLM client with streaming and cancellation.

    This wraps the centralized LLMService and adds cancellation support.
    """

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: Optional[str] = None,
        max_context_length: int = 32768,
        temperature: float = 0.1,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        min_p: Optional[float] = None,
        timeout: int = 300,
    ):
        # Create centralized LLM service
        """
        Initialize a client wrapper for a centralized LLM service.

        Parameters
        ----------
        endpoint : str
            Base URL of the remote LLM API.
        model : str
            Identifier of the model to use (e.g., "gpt-4o-mini").
        api_key : Optional[str], default=None
            Authentication token or secret required by the service. If omitted, the underlying
            `LLMService` may fall back to environment variables or other credential sources.
        max_context_length : int, default=32768
            Maximum number of tokens that can be sent in a single request. This value is passed
            to the service configuration and may affect truncation behaviour.
        temperature : float, default=0.1
            Sampling temperature for stochastic generation; lower values produce more deterministic
            output, higher values increase randomness.
        top_p : Optional[float], default=None
            Nucleus sampling probability cutoff. When set, the model will consider only the smallest
            set of tokens whose cumulative probability exceeds this value.
        top_k : Optional[int], default=None
            Limits token selection to the top *k* most likely tokens at each step. Mutually exclusive
            with `top_p` in many back-ends.
        min_p : Optional[float], default=None
            Minimum probability threshold; tokens with a probability lower than this value are filtered
            out before sampling.
        timeout : int, default=300
            Maximum number of seconds to wait for a response from the remote service before raising
            a timeout error.

        Attributes
        ----------
        _service : LLMService
            Internal instance that handles communication with the centralized LLM endpoint using the
            provided configuration.
        endpoint : str
            Stored copy of the API endpoint for backward compatibility.
        model : str
            Stored model identifier for backward compatibility.
        api_key : Optional[str]
            Stored API key (may be `None`) for backward compatibility.
        _cancel_event : asyncio.Event
            Event used to signal cancellation of ongoing streaming requests.
        """
        config = LLMConfig(
            api_endpoint=endpoint,
            model_name=model,
            api_key=api_key,
            max_context_length=max_context_length,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            timeout=timeout,
        )
        self._service = LLMService(config)

        # Keep these for backward compatibility
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self._cancel_event = asyncio.Event()

    def cancel(self) -> None:
        """
        Signal that the client operation should be cancelled.

        This method sets an internal cancellation flag, causing any coroutine currently awaiting a streaming response from the LLM service to raise :class:`asyncio.CancelledError`. It also logs an informational message indicating that a cancellation request has been made.
        """
        self._cancel_event.set()
        logger.info("LLM client cancellation requested")

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto",
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        min_p: Optional[float] = None,
        timeout: int = 300,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream chat completions from the centralized LLM service.

        This coroutine sends the provided conversation history to the remote model and yields each
        streaming chunk as soon as it is received.  The method updates the underlying service's
        configuration with any parameters that differ from the current defaults, then forwards the
        request to `self._service.stream_llm`.  Cancellation can be triggered externally via the
        instance's `_cancel_event`; a cancellation raises :class:`asyncio.CancelledError` after
        the current chunk is processed.

        Parameters
        ----------
        messages: List[Dict[str, Any]]
            The conversation history in the format expected by the LLM service.
        tools: Optional[List[Dict[str, Any]]], optional
            A list of tool specifications that the model may invoke.  If `None` no tools are
            provided.
        tool_choice: Optional[str], default "auto"
            Strategy for selecting a tool when multiple are available (e.g., `"auto"`,
            `"none"`, or a specific tool name).
        temperature: float, default 0.1
            Sampling temperature that controls randomness; lower values make output more deterministic.
        max_tokens: Optional[int], optional
            Maximum number of tokens the model is allowed to generate for this request.
        top_p: Optional[float], optional
            Nucleus sampling probability (0.0-1.0).  When set, the model considers only the smallest
            set of tokens whose cumulative probability exceeds this value.
        top_k: Optional[int], optional
            Top-k sampling limit; the model restricts its choice to the `k` most probable tokens.
        min_p: Optional[float], optional
            Minimum token probability threshold (0.0-1.0).  Tokens with a probability lower than this
            are excluded from consideration.
        timeout: int, default 300
            Request timeout in seconds for the underlying HTTP call.

        Yields
        ------
        Dict[str, Any]
            Individual streaming chunks returned by the LLM service.  The exact schema depends on
            the provider but typically includes `role`, `content` and optional tool-call data.

        Raises
        ------
        asyncio.CancelledError
            Propagated when the operation is cancelled via the instance's cancellation event.
        RuntimeError
            Raised if the remote LLM API returns an error response.  The exception message contains
            details from the service.
        """
        if DEBUG is True:
            print(json.dumps(messages, indent=2))

        # Update service config for this call if parameters differ
        if temperature != self._service.config.temperature:
            self._service.config.temperature = temperature
        if top_p is not None:
            self._service.config.top_p = top_p
        if top_k is not None:
            self._service.config.top_k = top_k
        if min_p is not None:
            self._service.config.min_p = min_p
        if timeout != self._service.config.timeout:
            self._service.config.timeout = timeout

        # Use centralized streaming service with cancellation checks
        chunk_count = 0
        try:
            async for chunk in self._service.stream_llm(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
                tool_choice=tool_choice,
                enforce_context_limit=True,
            ):
                # Check cancellation every chunk for immediate response
                if self._cancel_event.is_set():
                    logger.info("LLM stream cancelled")
                    raise asyncio.CancelledError("User cancelled LLM request")

                chunk_count += 1
                yield chunk

            logger.debug(f"Streamed {chunk_count} chunks from LLM")

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled after {chunk_count} chunks")
            raise

    async def parse_stream_to_message(
        self,
        stream: AsyncIterator[Dict[str, Any]],
        on_chunk: Optional[Any] = None,  # Callable[[str], Awaitable[None]]
    ) -> AssistantMessage:
        """
        Parse an asynchronous stream of LLM response chunks into a single :class:`AssistantMessage` instance.

        The function iterates over the provided `stream` (an async iterator yielding dictionaries
        representing partial responses from the language model).  It concatenates any textual
        content found in each chunk and aggregates incremental tool-call information until the
        stream is exhausted.  An optional `on_chunk` callback can be supplied to receive each
        piece of content as it arrives.

        If a cancellation event (`self._cancel_event`) is set during iteration, the function logs
        the interruption and raises :class:`asyncio.CancelledError` to abort processing.

        Parameters
        ----------
        stream: AsyncIterator[Dict[str, Any]]
            An asynchronous iterator yielding response chunks from the LLM service.  Each chunk
            is expected to contain a `choices` list with at least one element; the first choice's
            `delta` dictionary may include `content` and/or `tool_calls` entries.
        on_chunk: Optional[Callable[[str], Awaitable[None]]]
            An optional coroutine function that will be awaited for every non-empty content chunk
            extracted from the stream.  The callback receives the raw text fragment as its sole
            argument.

        Returns
        -------
        AssistantMessage
            A fully constructed assistant message with `role` set to `"assistant"`, combined
            `content` (or `None` if no textual content was received), and, when applicable,
            a list of parsed :class:`ToolCall` objects representing any function calls generated by
            the model.

        Raises
        ------
        asyncio.CancelledError
            Propagated when `self._cancel_event` is set during stream processing, indicating that
            the user cancelled the request.
        Exception
            Any unexpected exception raised while parsing tool-call structures is logged but does not
            interrupt message construction; malformed tool calls are omitted from the final result.
        """
        accumulated_content = ""
        accumulated_tool_calls = []

        async for chunk in stream:
            # Check cancellation
            if self._cancel_event.is_set():
                logger.info("Stream parsing cancelled")
                raise asyncio.CancelledError("User cancelled LLM request")

            if "choices" not in chunk or len(chunk["choices"]) == 0:
                continue

            delta = chunk["choices"][0].get("delta", {})

            # Handle content
            if "content" in delta and delta["content"]:
                content_chunk = delta["content"]
                accumulated_content += content_chunk

                if on_chunk:
                    await on_chunk(content_chunk)

            # Handle tool calls
            if "tool_calls" in delta:
                for tool_call_delta in delta["tool_calls"]:
                    idx = tool_call_delta.get("index", 0)

                    # Ensure we have enough slots
                    while len(accumulated_tool_calls) <= idx:
                        accumulated_tool_calls.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        )

                    if "id" in tool_call_delta:
                        accumulated_tool_calls[idx]["id"] = tool_call_delta["id"]

                    if "function" in tool_call_delta:
                        func_delta = tool_call_delta["function"]
                        if "name" in func_delta:
                            accumulated_tool_calls[idx]["function"]["name"] += func_delta["name"]
                        if "arguments" in func_delta:
                            accumulated_tool_calls[idx]["function"]["arguments"] += func_delta[
                                "arguments"
                            ]

        # Build AssistantMessage
        msg_dict = {
            "role": "assistant",
            "content": accumulated_content if accumulated_content else None,
        }

        if accumulated_tool_calls:
            # Parse tool calls
            parsed_tool_calls = []
            for tc in accumulated_tool_calls:
                try:
                    parsed_tool_calls.append(
                        ToolCall(id=tc.get("id"), type="function", function=tc["function"])
                    )
                except Exception as e:
                    logger.error(f"Failed to parse tool call: {e}")

            if parsed_tool_calls:
                msg_dict["tool_calls"] = parsed_tool_calls

        return AssistantMessage(**msg_dict)
