import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core import LLMClient, ToolExecutor, tool_registry
from ..models import AssistantMessage, ToolResult
from ..tools.csv_formatter import events_to_csv
from .context_manager import estimate_tokens, prune_chat_log, load_investigation_context
from .tool_categories import filter_tools_for_phase, is_analysis_tool
from .memory_summarizer import generate_chat_summary, load_chat_summary, trim_messages_from_middle
from .prompts import (
    get_system_prompt,
    get_tool_execution_prompt,
    get_analysis_prompt,
    get_completion_enforcement_prompt,
)

logger = logging.getLogger(__name__)

# Constants
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # Exponential backoff: 2s, 4s, 8s
MAX_TOOLS_PER_PHASE = 5
MAX_CHAT_LOG_TOKENS = 65535  # Token budget for chat log


def _compact_serialize(data: Any) -> str:
    """
    Compactly serializes *data* to a JSON string optimized for LLM context usage.

    Parameters
    ----------
    data: Any
        The Python object to be serialized. Objects that are not natively JSON-serializable will be converted to their `str` representation via the `default=str` hook.

    Returns
    -------
    str
        A JSON-encoded string with no unnecessary whitespace (compact separators) and Unicode characters preserved (`ensure_ascii=False`).
    """
    return json.dumps(data, default=str, separators=(",", ":"), ensure_ascii=False)


def _strip_cot_tags(text: str) -> str:
    """
    Strip Chain-of-Thought (CoT) sections from a string.

    This function removes any substrings enclosed by `<cot>` and `</cot>` tags,
    including the tags themselves. It first checks that the number of opening and
    closing tags matches; if they differ, a warning is logged but processing
    continues. After removing all matched tag blocks, any stray `<cot>` or
    `</cot>` markers are also stripped. Consecutive blank lines are collapsed to at
    most two, and leading/trailing whitespace is trimmed.

    Args:
        text: The input string that may contain one or more `<cot>...</cot>`
            sections.

    Returns:
        A new string with all CoT sections removed and excess whitespace cleaned.
    """
    import re

    # Pattern to match <cot>...</cot> (non-greedy, case-insensitive)
    pattern = r"<cot>.*?</cot>"

    # Check for mismatched tags
    open_count = text.count("<cot>")
    close_count = text.count("</cot>")

    if open_count != close_count:
        logger.warning(
            f"Mismatched CoT tags detected: {open_count} <cot> vs {close_count} </cot>. "
            f"Removing all CoT tags anyway."
        )

    # Remove all <cot>...</cot> sections
    cleaned = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # Also remove any orphaned tags
    cleaned = re.sub(r"</?cot>", "", cleaned, flags=re.IGNORECASE)

    # Clean up excessive whitespace
    cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)  # Max 2 consecutive newlines
    cleaned = cleaned.strip()

    return cleaned


class AssistantAgentV2:
    """
    Two-phase forensic analysis agent.

    Features:
    - Separate tool execution and analysis phases
    - Automatic chat log pruning to manage context
    - Real-time streaming of progress
    - Cancellation support
    """

    def __init__(
        self,
        db: AsyncSession,
        investigation_id: str,
        job_id: int,
        question: str,
        llm_endpoint: str,
        llm_model: str,
        llm_api_key: Optional[str] = None,
        llm_max_context: int = 32768,
        llm_temperature: float = 0.1,
        llm_top_p: Optional[float] = None,
        llm_top_k: Optional[int] = None,
        llm_min_p: Optional[float] = None,
        llm_timeout: int = 300,
        max_iterations: int = 10,
        user_id: Optional[int] = None,
    ):
        """
        Initialises the asynchronous investigation agent.

        Parameters
        ----------
        db: AsyncSession
            Database session used by the tool executor for persisting and retrieving investigation data.
        investigation_id: str
            Unique identifier of the investigation this agent will operate on.
        job_id: int
            Identifier of the background job associated with the investigation run.
        question: str
            The primary user question or problem statement that guides the investigation.
        llm_endpoint: str
            URL or network location of the large-language-model (LLM) service.
        llm_model: str
            Name or identifier of the LLM model to be used for generating prompts and analysing results.
        llm_api_key: Optional[str], default=None
            Authentication token for the LLM service, if required.
        llm_max_context: int, default=32768
            Maximum number of tokens the LLM can accept in a single request. Used to size the internal context buffer.
        llm_temperature: float, default=0.1
            Sampling temperature controlling randomness of LLM output (lower = more deterministic).
        llm_top_p: Optional[float], default=None
            Nucleus sampling probability threshold; if set, limits token selection to the smallest set whose cumulative probability exceeds this value.
        llm_top_k: Optional[int], default=None
            Limits token selection to the top-k most likely tokens at each step when provided.
        llm_min_p: Optional[float], default=None
            Minimum token probability; tokens with lower probability are filtered out before sampling.
        llm_timeout: int, default=300
            Maximum time in seconds to wait for an LLM response before raising a timeout error.
        max_iterations: int, default=10
            Upper bound on the number of iterative reasoning turns the agent may perform before stopping automatically.
        user_id: Optional[int], default=None
            Identifier of the user who initiated the investigation; propagated to tool execution for audit purposes.

        Notes
        -----
        The constructor configures several internal components:

        * An :class:`LLMClient` instance is created using the supplied endpoint, model and optional API key.
        * A :class:`ToolExecutor` is instantiated with a shared statistics dictionary that tracks events analysed, tools called, timeline entries created and tags applied.
        * Agent state variables such as `iteration` counters, turn-extension tracking, cancellation flag and total tool execution count are initialised.
        * Context management parameters are derived from the LLM’s maximum context size; the agent will trigger a compaction step once the accumulated token usage exceeds 80 % of this limit.

        The initialization logs an informational message containing key configuration values for debugging and observability.
        """
        self.db = db
        self.investigation_id = investigation_id
        self.job_id = job_id
        self.question = question

        # LLM client
        self.llm_client = LLMClient(
            endpoint=llm_endpoint,
            model=llm_model,
            api_key=llm_api_key,
        )
        self.llm_max_context = llm_max_context
        self.llm_temperature = llm_temperature
        self.llm_top_p = llm_top_p
        self.llm_top_k = llm_top_k
        self.llm_min_p = llm_min_p
        self.llm_timeout = llm_timeout

        # Tool executor
        self.stats = {
            "events_analyzed": 0,
            "tools_called": {},
            "timeline_entries_created": 0,
            "tags_applied": set(),
        }
        self.user_id = user_id
        self.tool_executor = ToolExecutor(db, investigation_id, self.stats, user_id=user_id)

        # Agent state
        self.iteration = 0
        self.max_iterations = max_iterations
        self.initial_max_iterations = max_iterations  # Track original limit
        self.turn_extensions_granted = 0  # Track number of extensions
        self.hard_ceiling = 30  # Hard limit on total turns (safety)
        self.cancelled = False
        self.total_tools_executed = 0

        # Context management
        self.compaction_threshold = int(llm_max_context * 0.8)  # Compact at 80% of max context

        logger.info(
            f"AssistantAgentV2 initialized: investigation={investigation_id}, "
            f"max_iterations={max_iterations}, max_context={llm_max_context}, "
            f"compaction_threshold={self.compaction_threshold}"
        )

    async def check_cancel_signal(self) -> bool:
        """
        Check whether the current job has been cancelled by querying the database.

        This coroutine queries the `jobs_agents` table for the `stop_requested` flag associated with
        the instance's `job_id`. If the flag is present and set to `'true'`, the method sets the
        instance attribute `cancelled` to `True`, logs an informational message, and returns `True`.

        If the flag is not set or no row is found, the method simply returns `False`. Any exception raised
        while accessing the database is caught; a warning is logged and `False` is returned.

        Returns:
            bool: `True` if a cancellation request was detected, otherwise `False`.
        """
        try:
            from sqlalchemy import text

            result = await self.db.execute(
                text(
                    """
                    SELECT metadata->>'stop_requested' as stop_requested
                    FROM jobs_agents
                    WHERE job_id = :job_id
                """
                ),
                {"job_id": self.job_id},
            )
            row = result.fetchone()

            if row and row[0] == "true":
                self.cancelled = True
                logger.info(f"Job {self.job_id} cancelled by user")
                return True

            return False
        except Exception as e:
            logger.warning(f"Failed to check cancel signal: {e}")
            return False

    async def _call_llm_with_retry(
        self,
        chat_log: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
        max_retries: int = MAX_RETRIES,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Call the language model with streaming support and retry logic, yielding incremental status updates.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            The sequence of messages forming the conversation context to send to the LLM.
        tools: List[Dict[str, Any]]
            Definitions of tool specifications that may be invoked by the model.
        tool_choice: str, optional
            Selection mode for tool usage (default `"auto"`). Passed directly to the LLM client.
        max_retries: int, optional
            Maximum number of retry attempts on failure (default `MAX_RETRIES`).

        Yields
        ------
        dict
            A series of status dictionaries consumed by the UI:

            * `{"type": "agent_cancelled", "message": ...}` - emitted when a user-initiated cancellation is detected.
            * `{"type": "llm_retry", "message": ..., "retry_count": int}` - emitted before each retry attempt, indicating back-off delay.
            * `{"type": "llm_error", "error": str}` - emitted after the final failed attempt.
            * `{"type": "llm_response", "message": AssistantMessage | None, "success": bool, "error": str (optional)}` - emitted once with the final assistant message on success or with `None` and error details on failure.

        Returns
        -------
        Never returns directly; the function terminates after yielding a final `"llm_response"` entry.

        Raises
        ------
        asyncio.CancelledError
            Propagated when the operation is cancelled by the user. The cancellation event is also reported via a yielded `agent_cancelled` message before re-raising.
        """
        last_error = None

        for retry_count in range(max_retries):
            try:
                # Calculate and log input tokens
                from .context_manager import estimate_tokens

                input_tokens = sum(
                    estimate_tokens(json.dumps(msg, default=str)) for msg in chat_log
                )
                logger.info(f"LLM call: {len(chat_log)} messages, ~{input_tokens} input tokens")

                # Stream LLM response
                stream = self.llm_client.stream_chat(
                    messages=chat_log,
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=self.llm_temperature,
                    max_tokens=min(16_384, self.llm_max_context // 4),
                    top_p=self.llm_top_p,
                    top_k=self.llm_top_k,
                    min_p=self.llm_min_p,
                    timeout=self.llm_timeout,
                )

                # Accumulate streaming response
                accumulated_content = ""
                accumulated_tool_calls = []
                chunk_count = 0

                async for chunk in stream:
                    # Check for cancellation every 10 chunks (balance responsiveness vs performance)
                    chunk_count += 1
                    if chunk_count % 10 == 0:
                        if await self.check_cancel_signal():
                            logger.info("LLM streaming cancelled by user")
                            yield {
                                "type": "agent_cancelled",
                                "message": "Investigation stopped by user",
                            }
                            raise asyncio.CancelledError()

                    if "choices" not in chunk or len(chunk["choices"]) == 0:
                        continue

                    delta = chunk["choices"][0].get("delta", {})

                    # Handle content
                    if "content" in delta and delta["content"]:
                        content_chunk = delta["content"]
                        accumulated_content += content_chunk

                        # Don't stream content in Phase 1 - agent should only make tool calls
                        # Content will be shown in Phase 2 (analysis) after CoT stripping
                        # This prevents showing reasoning steps or malformed output

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
                                    accumulated_tool_calls[idx]["function"]["name"] += func_delta[
                                        "name"
                                    ]
                                if "arguments" in func_delta:
                                    accumulated_tool_calls[idx]["function"][
                                        "arguments"
                                    ] += func_delta["arguments"]

                # Build AssistantMessage
                from ..models import ToolCall

                # Strip CoT tags from accumulated content
                cleaned_content = None
                if accumulated_content:
                    cleaned_content = _strip_cot_tags(accumulated_content)
                    if not cleaned_content:  # If content was only CoT, set to None
                        cleaned_content = None

                msg_dict = {
                    "role": "assistant",
                    "content": cleaned_content,
                }

                if accumulated_tool_calls:
                    parsed_tool_calls = []
                    for tc in accumulated_tool_calls:
                        parsed_tool_calls.append(
                            ToolCall(id=tc.get("id"), type="function", function=tc["function"])
                        )
                    msg_dict["tool_calls"] = parsed_tool_calls

                assistant_msg = AssistantMessage(**msg_dict)

                # Calculate and log response tokens
                response_tokens = estimate_tokens(accumulated_content) if accumulated_content else 0
                # Add tokens for tool calls (rough estimate)
                if accumulated_tool_calls:
                    for tc in accumulated_tool_calls:
                        response_tokens += estimate_tokens(json.dumps(tc, default=str))

                logger.info(
                    f"LLM response: ~{response_tokens} output tokens, "
                    f"{len(accumulated_tool_calls)} tool calls, "
                    f"{len(accumulated_content)} chars content"
                )

                # Success - return via final yield
                yield {"type": "llm_response", "message": assistant_msg, "success": True}
                return

            except asyncio.CancelledError:
                logger.info("LLM call cancelled by user")
                yield {"type": "agent_cancelled", "message": "Investigation stopped by user"}
                raise

            except Exception as e:
                last_error = e
                logger.error(
                    f"LLM call failed (attempt {retry_count + 1}/{max_retries}): {type(e).__name__}: {e}",
                    exc_info=True,
                )

                if retry_count < max_retries - 1:
                    wait_time = RETRY_BACKOFF_BASE ** (retry_count + 1)
                    yield {
                        "type": "llm_retry",
                        "message": f"LLM error, retrying in {wait_time}s...",
                        "retry_count": retry_count + 1,
                    }
                    await asyncio.sleep(wait_time)
                else:
                    # Max retries exceeded
                    yield {
                        "type": "llm_error",
                        "error": f"LLM failed after {max_retries} attempts: {str(last_error)}",
                    }
                    yield {
                        "type": "llm_response",
                        "message": None,
                        "success": False,
                        "error": str(last_error),
                    }
                    return

    async def _execute_tool_with_retry(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tool_call_id: str,
        max_retries: int = MAX_RETRIES,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a single tool with built-in retry handling and stream progress updates.

        Parameters
        ----------
        self : object
            The agent instance containing iteration state, configuration, and the `tool_executor` used to run tools.
        tool_name : str
            Identifier of the tool to invoke (e.g., `search_events_by_type` or `register_timeline_entry`).
        arguments : Dict[str, Any]
            Mapping of argument names to values that will be passed to the tool.  May include a `description` key used for UI display.
        tool_call_id : str
            Unique identifier for this particular tool call; propagated in all emitted events so the caller can correlate responses.
        max_retries : int, optional
            Maximum number of retry attempts before giving up.  Defaults to the module-level constant `MAX_RETRIES`.

        Yields
        ------
        Dict[str, Any]
            A sequence of event dictionaries that drive the UI and internal logic:

            * `type: "tool_executing"` - emitted once at the start with metadata about the tool, its arguments, the current turn number and the overall iteration limit.
            * `type: "tool_retry"` - emitted when a call fails but retries remain; includes a human-readable message and the current retry count.
            * `type: "tool_result"` - emitted on success or final failure.  Contains the serialized `ToolResult` (status, result payload, error message), a concise `result_summary` for display, a boolean `success` flag, and UI-friendly fields such as `display_name`.
            * `type: "_internal_tool_result"` - emitted immediately after the public `tool_result` event; carries the actual `ToolResult` object for downstream processing.

        Returns
        -------
        None
            The coroutine finishes after yielding either a successful result or an error result; the concrete `ToolResult` is provided via the internal `_internal_tool_result` yield rather than as a return value.

        Raises
        ------
        asyncio.CancelledError
            Propagated unchanged if the surrounding task is cancelled by the user.  No retry or cleanup is performed in this case.
        """
        # Notify UI
        yield {
            "type": "tool_executing",
            "tool": tool_name,
            "arguments": arguments,
            "turn_number": self.iteration,
            "max_turns": self.max_iterations,
        }

        last_error = None

        for retry_count in range(max_retries):
            try:
                result = await self.tool_executor.execute(tool_name, arguments)

                # Success - convert ToolResult to dict for JSON serialization
                result_dict = {
                    "status": result.status,
                    "result": result.result,
                    "error_msg": result.error_msg,
                }

                # Build result summary for UI
                result_summary = ""
                display_name = arguments.get("description", tool_name)

                # Only show event counts for query tools
                is_query_tool = tool_name in [
                    "search_events_by_type",
                    "query_jsonb_field",
                    "aggregate_jsonb_field",
                    "search_events_by_timerange",
                    "search_events_by_content",
                    "get_event_by_id",
                ]

                if result.status == "ok" and result.result:
                    if is_query_tool:
                        count = result.result.get("count", 0)
                        if count > 0:
                            result_summary = f"Found {count} events"
                        else:
                            result_summary = "No matching events found"
                    elif tool_name == "register_timeline_entry":
                        result_summary = "Registered to timeline"
                    elif tool_name == "complete_investigation":
                        result_summary = "Investigation completed"
                    else:
                        result_summary = "Success"
                elif result.status == "error":
                    result_summary = f"Error: {result.error_msg}"

                yield {
                    "type": "tool_result",
                    "tool": tool_name,
                    "display_name": display_name,
                    "result": result_dict,
                    "result_summary": result_summary,
                    "success": result.status == "ok",
                    "tool_call_id": tool_call_id,
                }
                # Return the actual ToolResult object (not the dict)
                yield {
                    "type": "_internal_tool_result",
                    "tool_result_obj": result,
                }
                return

            except asyncio.CancelledError:
                logger.info(f"Tool {tool_name} cancelled by user")
                raise

            except Exception as e:
                last_error = e
                logger.error(
                    f"Tool {tool_name} failed (attempt {retry_count + 1}/{max_retries}): {e}",
                    exc_info=True,
                )

                if retry_count < max_retries - 1:
                    wait_time = RETRY_BACKOFF_BASE ** (retry_count + 1)
                    yield {
                        "type": "tool_retry",
                        "tool": tool_name,
                        "message": f"Tool error, retrying in {wait_time}s...",
                        "retry_count": retry_count + 1,
                    }
                    await asyncio.sleep(wait_time)
                else:
                    # Max retries exceeded - return error result
                    error_result = ToolResult(
                        status="error", error_msg=str(last_error), result=None
                    )
                    result_dict = {
                        "status": "error",
                        "result": None,
                        "error_msg": str(last_error),
                    }
                    display_name = arguments.get("description", tool_name)
                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "display_name": display_name,
                        "result": result_dict,
                        "result_summary": f"Error: {str(last_error)}",
                        "success": False,
                        "tool_call_id": tool_call_id,
                    }
                    # Return the actual ToolResult object
                    yield {
                        "type": "_internal_tool_result",
                        "tool_result_obj": error_result,
                    }
                    return

    async def _compact_chat_log(
        self,
        chat_log: List[Dict[str, Any]],
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Compact the chat log by summarizing earlier messages and preserving recent context.

        This asynchronous generator processes a list of chat messages and yields progress updates
        while producing a compacted version of the conversation suitable for continued LLM
        interaction.

        The compaction strategy is:

        1. Attempt to retrieve an existing summary for the current investigation/iteration from
           the database.
        2. If no cached summary exists, generate a new one using the configured language model and
           store it in the database.
        3. If summary generation fails, fall back to trimming messages from the middle of the log
           to stay within a token budget (default 4 000 tokens).

        The function always retains the system prompt, the original user question, and the last five
        messages; all intervening messages are replaced by a single system message containing the
        LLM-generated summary and progress statistics.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            The full conversation history in chronological order. Each entry must contain at
            least `role` and `content` keys as expected by the LLM client.

        Yields
        ------
        dict
            A progress event with `type` set to `"context_compacted"` describing how many
            messages were removed, how many tokens were saved, and a short human-readable message.
        dict
            The final compacted chat log wrapped in an event where `type` is
            `"_compacted_chat_log"` and `chat_log` contains the new list of messages.

        Notes
        -----
        * If the original log contains seven or fewer messages, no compaction occurs; the function
          yields a single `"_compacted_chat_log"` event with the unmodified log.
        * Token estimates are obtained via :func:`estimate_tokens`; these values are logged for
          diagnostic purposes but not returned to the caller.
        * Summary metadata may include `event_ids`, `tools_executed`, token counts, and a
          compression ratio, which are incorporated into the generated system message.
        """
        # Extract messages to compact (everything except system, user question, and last 5)
        if len(chat_log) <= 7:
            # Not enough messages to compact
            yield {
                "type": "_compacted_chat_log",
                "chat_log": chat_log,
            }
            return

        messages_to_compact = chat_log[2:-5]
        start_idx = 2
        end_idx = len(chat_log) - 5

        # Try to load existing summary from database
        summary_text, summary_metadata = await load_chat_summary(
            db=self.db,
            investigation_id=self.investigation_id,
            job_id=self.job_id,
            iteration_number=self.iteration,
        )

        if summary_text:
            # Use cached summary
            logger.info(f"Using cached summary from database (iteration {self.iteration})")

            event_ids_found = set(summary_metadata.get("event_ids", []))
            tools_executed_list = summary_metadata.get("tools_executed", [])
            original_tokens = summary_metadata.get("original_tokens", 0)
            summary_tokens = summary_metadata.get("summary_tokens", 0)
            tokens_saved = original_tokens - summary_tokens
        else:
            # Generate new summary with LLM
            logger.info(f"Generating new summary for iteration {self.iteration}")

            try:
                summary_text, summary_metadata = await generate_chat_summary(
                    db=self.db,
                    investigation_id=self.investigation_id,
                    job_id=self.job_id,
                    iteration_number=self.iteration,
                    messages_to_summarize=messages_to_compact,
                    start_idx=start_idx,
                    end_idx=end_idx,
                    llm_client=self.llm_client,
                )

                event_ids_found = set(summary_metadata.get("event_ids", []))
                tools_executed_list = summary_metadata.get("tools_executed", [])
                original_tokens = summary_metadata.get("original_tokens", 0)
                summary_tokens = summary_metadata.get("summary_tokens", 0)
                tokens_saved = original_tokens - summary_tokens

            except Exception as e:
                logger.error(f"Summary generation failed: {e}", exc_info=True)

                # Fallback: trim from middle
                logger.warning("Falling back to middle-trimming strategy")

                trimmed_log = trim_messages_from_middle(chat_log, max_tokens=4000)

                yield {
                    "type": "context_compacted",
                    "message": f"Chat log trimmed from middle (LLM summary failed): {len(chat_log)} → {len(trimmed_log)} messages",
                    "messages_removed": len(chat_log) - len(trimmed_log),
                    "tokens_saved": 0,
                }

                yield {
                    "type": "_compacted_chat_log",
                    "chat_log": trimmed_log,
                }
                return

        # Build compaction summary using LLM-generated summary
        event_ids_found = set()  # Will be populated from summary
        transcript_parts = []

        # The summary_text already contains the transcript, just use it directly
        # Extract event IDs from summary metadata
        event_ids_found = set(summary_metadata.get("event_ids", []))

        # Use LLM-generated summary with additional context
        summary = f"{summary_text}\n\n**Progress Stats**:\n"
        summary += f"- Messages Compacted: {len(messages_to_compact)}\n"
        summary += f"- Total Tools Executed: {self.total_tools_executed}\n"
        summary += (
            f"- Timeline Entries Created: {self.stats.get('timeline_entries_created', 0)}\n\n"
        )
        summary += "*Note: This is an LLM-generated summary. Event IDs above can be used to register events to the timeline.*\n"

        # Rebuild chat log with summary
        compacted_log = [
            chat_log[0],  # System prompt
            chat_log[1],  # User question
            {
                "role": "system",
                "content": (
                    "## Investigation History (Compacted)\n\n"
                    "**Note**: Your conversation history was compacted to manage context length. "
                    "The summary below preserves critical information including event IDs, findings, "
                    "and patterns discovered. Use this information to continue your investigation "
                    "and register relevant events to the timeline.\n\n" + summary
                ),
            },
        ] + chat_log[
            -5:
        ]  # Last 5 messages

        # Tokens already calculated from summary generation
        original_tokens_full = sum(
            estimate_tokens(json.dumps(msg, default=str)) for msg in chat_log
        )
        new_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in compacted_log)

        logger.info(
            f"Compacted chat log: {len(chat_log)} -> {len(compacted_log)} messages, "
            f"{original_tokens_full} -> {new_tokens} tokens (saved {original_tokens_full - new_tokens} tokens, "
            f"{((original_tokens_full - new_tokens)/original_tokens_full)*100:.1f}% reduction)"
        )

        yield {
            "type": "context_compacted",
            "message": f"Investigation history compacted using LLM summary (saved {original_tokens_full - new_tokens} tokens, {summary_metadata.get('compression_ratio', 0)*100:.1f}% compression)",
            "messages_removed": len(chat_log) - len(compacted_log),
            "tokens_saved": original_tokens_full - new_tokens,
        }

        yield {
            "type": "_compacted_chat_log",
            "chat_log": compacted_log,
        }

    async def execute_tool_phase(
        self, chat_log: List[Dict[str, Any]]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute Phase 1 of the agent’s workflow - tool execution.

        This coroutine iterates through the following steps while streaming progress updates
        as dictionaries via an async iterator:

        1. **Context size check** - Calculates the token count of `chat_log` and logs the
           percentage of the LLM’s maximum context window. If the token count exceeds
           :attr:`self.compaction_threshold`, the method invokes :meth:`_compact_chat_log`
           to reduce the log size, yielding any intermediate progress messages.

        2. **Tool selection** - Retrieves all registered tools from `tool_registry` and
           filters them for the *tool_execution* phase using :func:`filter_tools_for_phase`.
           After a configurable number of iterations (default 4), the special
           `complete_investigation` tool is added to the allowed set.

        3. **LLM call** - Calls the language model via :meth:`_call_llm_with_retry` with
           `tool_choice="required"` so that only tool calls are returned. Progress from
           this step is yielded directly; on failure a `phase_error` message is emitted
           and execution stops.

        4. **Tool call processing** - If the LLM response contains `tool_calls`:

           * Enforces :data:`MAX_TOOLS_PER_PHASE` by truncating excess calls.
           * Deduplicates calls that have identical tool names and argument sets,
             emitting a `tool_limit_enforced` message for any removed duplicates.
           * Validates each call against the Phase 1 allow-list; disallowed tools are
             skipped with a `tool_rejected` entry.
           * Executes each permitted tool via :meth:`_execute_tool_with_retry`,
             streaming intermediate progress and collecting results.

        5. **Special tool handling** - Recognises two control tools:

           * `request_additional_turns` - If approved, extends `self.max_iterations`
             within the hard ceiling, updates counters, and yields a
             `turn_extension_granted` message.
           * `complete_investigation` - Marks the investigation as finished,
             captures the provided summary, and records it for downstream phases.

        6. **Completion** - After all tool calls are processed (or none were returned),
           yields a final dictionary with type `phase_complete` containing:

           * The original LLM assistant message.
           * A list of executed tool results (each with call id, name, arguments,
             and the :class:`ToolResult` object).
           * Flags indicating whether the investigation was completed in this phase
             and the accompanying summary.

        Parameters
        ----------
        self: Agent
            Instance of the asynchronous agent managing iteration state.
        chat_log: List[Dict[str, Any]]
            The current conversation history to be sent to the LLM. Each entry is a
            serialisable message dict compatible with OpenAI chat format.

        Yields
        -----
        Dict[str, Any]
            Progress dictionaries whose `type` key indicates the nature of the update,
            e.g.:

            * `_compacted_chat_log` - intermediate compaction result.
            * `llm_response` - raw LLM reply (internal handling).
            * `phase_error` - fatal error in this phase.
            * `tool_limit_enforced` - when tool count or duplicates are trimmed.
            * `tool_rejected` - disallowed tool call encountered.
            * `turn_extension_granted` - successful request for extra turns.
            * `_internal_tool_result` - internal message containing a :class:`ToolResult`.
            * `phase_complete` - final payload with all outcomes.

        Returns
        -------
        None
            The coroutine yields all information; it does not return a value.
        """
        logger.info(f"[Iteration {self.iteration}] Phase 1: Tool Execution")

        # Check context length and compact if needed
        current_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in chat_log)
        context_pct = (current_tokens / self.llm_max_context) * 100

        logger.info(
            f"[Iteration {self.iteration}] Current context: {current_tokens} tokens "
            f"({context_pct:.1f}% of {self.llm_max_context} max)"
        )

        if current_tokens > self.compaction_threshold:
            logger.warning(
                f"[Iteration {self.iteration}] Context exceeds threshold "
                f"({current_tokens} > {self.compaction_threshold}), invoking compaction..."
            )

            compacted_log = None
            async for progress in self._compact_chat_log(chat_log):
                if progress.get("type") == "_compacted_chat_log":
                    compacted_log = progress.get("chat_log")
                else:
                    yield progress  # Stream progress to UI

            if compacted_log:
                chat_log = compacted_log
            else:
                logger.warning("Compaction failed, using original chat log")

        # Get Phase 1 tools (data query tools + complete_investigation after iteration 3)
        all_tools = tool_registry.get_openai_format()
        logger.info(f"Total tools registered: {len(all_tools)}")
        logger.info(f"All tool names: {[t.get('function', {}).get('name') for t in all_tools]}")
        phase1_tools = filter_tools_for_phase(all_tools, "tool_execution")
        logger.info(
            f"Phase 1 filtered tools: {[t.get('function', {}).get('name') for t in phase1_tools]}"
        )

        # Allow complete_investigation in Phase 1 after iteration 3
        MIN_ITERATIONS_BEFORE_COMPLETION = 4
        if self.iteration >= MIN_ITERATIONS_BEFORE_COMPLETION:
            # Add complete_investigation to Phase 1 tools
            complete_tool = [
                t
                for t in all_tools
                if t.get("function", {}).get("name") == "complete_investigation"
            ]
            if complete_tool:
                phase1_tools.extend(complete_tool)
                logger.info(
                    f"Iteration {self.iteration}/{MIN_ITERATIONS_BEFORE_COMPLETION}: "
                    f"complete_investigation tool ENABLED in Phase 1"
                )

        logger.info(
            f"Phase 1 tools available: {len(phase1_tools)} (data query tools + control tools)"
        )

        # Verify we're only sending data query tools
        tool_names = [t.get("function", {}).get("name") for t in phase1_tools]
        logger.debug(f"Phase 1 tools: {tool_names}")

        # Call LLM to get tool executions
        # Use tool_choice="required" to force tool calls only (no text output)
        assistant_msg = None
        async for progress in self._call_llm_with_retry(
            chat_log=chat_log, tools=phase1_tools, tool_choice="required"
        ):
            if progress.get("type") == "llm_response":
                assistant_msg = progress.get("message")
                if not progress.get("success"):
                    # LLM call failed
                    yield {
                        "type": "phase_error",
                        "phase": "tool_execution",
                        "error": progress.get("error", "LLM call failed"),
                    }
                    return
            else:
                yield progress  # Stream progress to UI

        if not assistant_msg:
            yield {
                "type": "phase_error",
                "phase": "tool_execution",
                "error": "No LLM response received",
            }
            return

        # Execute tools
        tool_results = []
        investigation_completed_in_phase1 = False
        completion_summary_phase1 = None

        if assistant_msg.tool_calls:
            # Enforce tool limit
            total_tool_calls = len(assistant_msg.tool_calls)
            if total_tool_calls > MAX_TOOLS_PER_PHASE:
                logger.warning(
                    f"Agent attempted {total_tool_calls} tool calls, limiting to {MAX_TOOLS_PER_PHASE}"
                )
                yield {
                    "type": "tool_limit_enforced",
                    "message": f"Tool limit enforced: {total_tool_calls} requested, executing {MAX_TOOLS_PER_PHASE}",
                    "requested": total_tool_calls,
                    "executed": MAX_TOOLS_PER_PHASE,
                }

            # Filter out Phase 2 tools that shouldn't be in Phase 1
            # Phase 1 should ONLY have data query tools
            tool_calls_to_execute = list(assistant_msg.tool_calls[:MAX_TOOLS_PER_PHASE])

            # Deduplicate tool calls - track tool name + args combinations
            seen_tool_signatures = set()
            deduplicated_calls = []
            duplicate_count = 0

            for tc in tool_calls_to_execute:
                tool_name = tc.function.get("name", "")
                try:
                    args_str = tc.function.get("arguments", "{}")
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    # Create signature from tool name + sorted args (exclude description for dedup)
                    args_for_sig = {k: v for k, v in args.items() if k != "description"}
                    signature = f"{tool_name}:{json.dumps(args_for_sig, sort_keys=True)}"

                    if signature in seen_tool_signatures:
                        duplicate_count += 1
                        logger.warning(
                            f"Duplicate tool call detected: {tool_name} with same arguments"
                        )
                    else:
                        seen_tool_signatures.add(signature)
                        deduplicated_calls.append(tc)
                except Exception as e:
                    logger.error(f"Failed to deduplicate tool call: {e}")
                    deduplicated_calls.append(tc)  # Include it anyway

            if duplicate_count > 0:
                yield {
                    "type": "tool_limit_enforced",
                    "message": f"Removed {duplicate_count} duplicate tool calls (same tool + arguments)",
                    "requested": len(tool_calls_to_execute),
                    "executed": len(deduplicated_calls),
                }

            # All tools are already filtered to Phase 1 tools only by filter_tools_for_phase
            # Validate and execute deduplicated calls
            for tool_call in deduplicated_calls:
                # Check cancellation
                if await self.check_cancel_signal():
                    yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                    self.cancelled = True
                    return

                tool_name = tool_call.function.get("name", "")

                # CRITICAL: Validate that the tool is allowed in Phase 1
                # Reject any analysis tools that the LLM might hallucinate
                allowed_tool_names = [t.get("function", {}).get("name") for t in phase1_tools]
                if tool_name not in allowed_tool_names:
                    logger.warning(
                        f"Agent attempted to call '{tool_name}' in Phase 1, but it's not allowed. "
                        f"Allowed tools: {allowed_tool_names}. Skipping this tool call."
                    )
                    yield {
                        "type": "tool_rejected",
                        "tool": tool_name,
                        "reason": f"Tool '{tool_name}' is not available in Phase 1 (tool execution phase)",
                        "allowed_tools": allowed_tool_names,
                    }
                    continue

                # Parse arguments
                try:
                    args_str = tool_call.function.get("arguments", "{}")
                    arguments = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool arguments: {e}")
                    arguments = {}

                # Execute tool
                tool_result = None
                async for progress in self._execute_tool_with_retry(
                    tool_name=tool_name,
                    arguments=arguments,
                    tool_call_id=tool_call.id or f"call_{len(tool_results) + 1}",
                ):
                    if progress.get("type") == "_internal_tool_result":
                        # Internal message with actual ToolResult object
                        tool_result = progress.get("tool_result_obj")
                    elif progress.get("type") != "_internal_tool_result":
                        # Stream to UI (skip internal messages)
                        yield progress

                if tool_result:
                    tool_results.append(
                        {
                            "tool_call_id": tool_call.id or f"call_{len(tool_results)}",
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "result": tool_result,
                        }
                    )
                    self.total_tools_executed += 1

                    # Check if this was request_additional_turns
                    if tool_name == "request_additional_turns" and tool_result.status == "ok":
                        result_data = tool_result.result
                        if result_data.get("status") == "approved":
                            turns_requested = result_data.get("turns_requested", 3)
                            justification = result_data.get("justification", "")

                            # Check if we're under the hard ceiling
                            new_max = self.max_iterations + turns_requested
                            if new_max <= self.hard_ceiling:
                                self.max_iterations = new_max
                                self.turn_extensions_granted += 1
                                logger.info(
                                    f"Turn extension granted: +{turns_requested} turns. "
                                    f"New max: {self.max_iterations}/{self.hard_ceiling}. "
                                    f"Justification: {justification[:100]}..."
                                )

                                # Notify UI
                                yield {
                                    "type": "turn_extension_granted",
                                    "turns_requested": turns_requested,
                                    "new_max_turns": self.max_iterations,
                                    "hard_ceiling": self.hard_ceiling,
                                    "justification": justification,
                                    "extensions_granted": self.turn_extensions_granted,
                                }
                            else:
                                logger.warning(
                                    f"Turn extension DENIED: Would exceed hard ceiling. "
                                    f"Requested: {new_max}, Ceiling: {self.hard_ceiling}"
                                )
                                # Update tool result to reflect denial
                                tool_result.result["status"] = "denied"
                                tool_result.result["message"] = (
                                    f"Request denied: Would exceed hard ceiling of {self.hard_ceiling} turns. "
                                    f"Current limit: {self.max_iterations}, Requested: {turns_requested}"
                                )

                    # Check if this was complete_investigation
                    if tool_name == "complete_investigation" and tool_result.status == "ok":
                        investigation_completed_in_phase1 = True
                        completion_summary_phase1 = tool_result.result.get(
                            "summary", "Investigation completed"
                        )
                        logger.info(
                            f"Investigation completed in Phase 1 with summary: {completion_summary_phase1[:100]}..."
                        )

        # Return results
        yield {
            "type": "phase_complete",
            "phase": "tool_execution",
            "assistant_message": assistant_msg,
            "tool_results": tool_results,
            "investigation_completed": investigation_completed_in_phase1,
            "completion_summary": completion_summary_phase1,
        }

    async def execute_analysis_phase(
        self, chat_log: List[Dict[str, Any]], tool_results_summary: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute Phase 2 (Result Analysis) of an investigation.

        Iteratively calls the LLM with only analysis-phase tools, processes its response,
        deduplicates and validates any requested tool calls, executes those tools while
        handling cancellation signals, and yields progress updates throughout the
        process.  The final yielded dictionary contains a summary of the analysis and
        indicates whether the investigation was completed.

        Parameters
        ----------
        self : object
            The agent instance containing iteration state, configuration, and helper
            methods.
        chat_log : List[Dict[str, Any]]
            Ordered list of prior messages forming the conversation context to be sent
            to the LLM.  Each entry follows the OpenAI chat format (role/content).
        tool_results_summary : str
            Human-readable summary of results from previous tool executions; included in
            the analysis prompt.

        Yields
        ------
        dict
            Progress updates emitted during execution.  The `type` key determines the
            meaning of each item, for example:

            - `"llm_response"` - raw LLM response (internal use).
            - `"phase_error"` - an error occurred in this phase; includes `error`
              message.
            - `"tool_limit_enforced"` - duplicate or disallowed tool calls were
              removed; provides `requested` and `executed` counts.
            - `"tool_rejected"` - a tool call was not permitted in the analysis phase;
              includes `tool` name, `reason`, and list of `allowed_tools`.
            - `"timeline_updated"` - a timeline entry was successfully registered;
              reports number of entries added.
            - `"agent_cancelled"` - cancellation signal received; investigation stops.
            - `"phase_complete"` - final result of the analysis phase; contains
              `analysis_summary`, `investigation_completed` (bool), and optional
              `completion_summary`.

        Returns
        -------
        None
            The function is an asynchronous generator; it does not return a value but
            yields dictionaries as described above.
        """
        logger.info(f"[Iteration {self.iteration}] Phase 2: Result Analysis")

        # Get ONLY Phase 2 tools (analysis tools)
        all_tools = tool_registry.get_openai_format()
        phase2_tools = filter_tools_for_phase(all_tools, "analysis")

        # CRITICAL: Remove complete_investigation from available tools until iteration 4+
        # This forces the agent to gather more data before completing
        MIN_ITERATIONS_BEFORE_COMPLETION = 4
        if self.iteration < MIN_ITERATIONS_BEFORE_COMPLETION:
            phase2_tools = [
                tool
                for tool in phase2_tools
                if tool.get("function", {}).get("name") != "complete_investigation"
            ]
            logger.info(
                f"Iteration {self.iteration}/{MIN_ITERATIONS_BEFORE_COMPLETION}: "
                f"complete_investigation tool DISABLED (need {MIN_ITERATIONS_BEFORE_COMPLETION - self.iteration} more iterations)"
            )

        logger.info(f"Phase 2 tools available: {len(phase2_tools)} (analysis tools only)")

        # Verify we're only sending analysis tools
        tool_names = [t.get("function", {}).get("name") for t in phase2_tools]
        logger.info(f"Phase 2 tools: {tool_names}")

        # Call LLM to get analysis
        assistant_msg = None
        async for progress in self._call_llm_with_retry(
            chat_log=chat_log, tools=phase2_tools, tool_choice="auto"
        ):
            if progress.get("type") == "llm_response":
                assistant_msg = progress.get("message")
                if not progress.get("success"):
                    yield {
                        "type": "phase_error",
                        "phase": "analysis",
                        "error": progress.get("error", "LLM call failed"),
                    }
                    return
            else:
                yield progress

        if not assistant_msg:
            yield {"type": "phase_error", "phase": "analysis", "error": "No LLM response received"}
            return

        # Execute any analysis tools (register_timeline_entry, complete_investigation)
        investigation_completed = False
        completion_summary = None

        if assistant_msg.tool_calls:
            # Deduplicate tool calls in analysis phase
            seen_tool_signatures = set()
            deduplicated_calls = []
            duplicate_count = 0

            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.get("name", "")
                try:
                    args_str = tc.function.get("arguments", "{}")
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    # Create signature from tool name + sorted args
                    signature = f"{tool_name}:{json.dumps(args, sort_keys=True)}"

                    if signature in seen_tool_signatures:
                        duplicate_count += 1
                        logger.warning(f"Duplicate tool call in analysis phase: {tool_name}")
                    else:
                        seen_tool_signatures.add(signature)
                        deduplicated_calls.append(tc)
                except Exception as e:
                    logger.error(f"Failed to deduplicate analysis tool call: {e}")
                    deduplicated_calls.append(tc)

            if duplicate_count > 0:
                yield {
                    "type": "tool_limit_enforced",
                    "message": f"Removed {duplicate_count} duplicate tool calls in analysis phase",
                    "requested": len(assistant_msg.tool_calls),
                    "executed": len(deduplicated_calls),
                }

            # All tools are already filtered to Phase 2 tools only by filter_tools_for_phase
            # Check if complete_investigation is in the tool calls
            # If so, move it to the end and ensure only one is executed
            tool_calls_to_execute = deduplicated_calls
            complete_calls = [
                tc
                for tc in tool_calls_to_execute
                if tc.function.get("name") == "complete_investigation"
            ]
            other_calls = [
                tc
                for tc in tool_calls_to_execute
                if tc.function.get("name") != "complete_investigation"
            ]

            if complete_calls:
                if len(complete_calls) > 1:
                    logger.warning(
                        f"Agent called complete_investigation {len(complete_calls)} times in analysis phase, will only execute once"
                    )
                    yield {
                        "type": "tool_limit_enforced",
                        "message": f"complete_investigation called {len(complete_calls)} times - will only execute once at the end",
                        "requested": len(complete_calls),
                        "executed": 1,
                    }

                # Execute other tools first, then complete_investigation last
                logger.info(
                    f"Reordering analysis tools: executing {len(other_calls)} tools first, then complete_investigation last"
                )
                tool_calls_to_execute = other_calls + [
                    complete_calls[0]
                ]  # Only first complete_investigation

            for tool_call in tool_calls_to_execute:
                # Check cancellation before each tool in analysis phase
                if await self.check_cancel_signal():
                    yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                    self.cancelled = True
                    return

                tool_name = tool_call.function.get("name", "")

                # CRITICAL: Validate that the tool is allowed in Phase 2
                # Reject any data query tools that the LLM might hallucinate
                allowed_tool_names = [t.get("function", {}).get("name") for t in phase2_tools]
                if tool_name not in allowed_tool_names:
                    logger.warning(
                        f"Agent attempted to call '{tool_name}' in Phase 2, but it's not allowed. "
                        f"Allowed tools: {allowed_tool_names}. Skipping this tool call."
                    )
                    yield {
                        "type": "tool_rejected",
                        "tool": tool_name,
                        "reason": f"Tool '{tool_name}' is not available in Phase 2 (analysis phase)",
                        "allowed_tools": allowed_tool_names,
                    }
                    continue

                # Parse arguments
                try:
                    args_str = tool_call.function.get("arguments", "{}")
                    arguments = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    arguments = {}

                # Execute tool
                tool_result = None
                async for progress in self._execute_tool_with_retry(
                    tool_name=tool_name,
                    arguments=arguments,
                    tool_call_id=tool_call.id or f"analysis_call_{tool_name}",
                ):
                    if progress.get("type") == "_internal_tool_result":
                        # Internal message with actual ToolResult object
                        tool_result = progress.get("tool_result_obj")
                    elif progress.get("type") != "_internal_tool_result":
                        # Stream to UI (skip internal messages)
                        yield progress

                # Check if timeline entry was added
                if (
                    tool_name == "register_timeline_entry"
                    and tool_result
                    and tool_result.status == "ok"
                ):
                    # Notify UI to refresh timeline
                    yield {
                        "type": "timeline_updated",
                        "entries_added": 1,
                        "total_entries": self.stats.get("timeline_entries_created", 0),
                    }

                # Check if investigation completed
                if (
                    tool_name == "complete_investigation"
                    and tool_result
                    and tool_result.status == "ok"
                ):
                    investigation_completed = True
                    completion_summary = tool_result.result.get(
                        "summary", "Investigation completed"
                    )

        # Extract analysis summary from assistant's content (already stripped of CoT tags)
        analysis_summary = assistant_msg.content or "Analysis complete."

        # DON'T send agent_thinking here - it will be shown AFTER tool execution completes
        # This prevents showing explanatory text between tool calls
        # The analysis summary will be added to chat_log for LLM context only

        # Return results
        yield {
            "type": "phase_complete",
            "phase": "analysis",
            "analysis_summary": analysis_summary,
            "investigation_completed": investigation_completed,
            "completion_summary": completion_summary,
        }

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Run the assistant agent loop, yielding incremental progress events.

        This coroutine orchestrates the full investigation lifecycle using a two-phase architecture:
        1. **Tool Execution Phase** - prompts the LLM to select and run data-query tools, collects their results, and records any tool output in the chat log.
        2. **Analysis Phase** - asks the LLM to analyse the aggregated tool results, decide whether the investigation is complete, and optionally produce a final summary.

        The method:
        - Loads the investigation context (including field dictionary) from the database.
        - Emits an `agent_started` event containing the original question.
        - Builds the initial system-prompt + user message chat log.
        - Enters a loop that continues until the agent is cancelled, the maximum number of iterations is reached, or the investigation finishes successfully.
          - Handles cancellation signals each iteration.
          - Retries an entire iteration up to two times when **all** tools fail.
          - Prunes or compacts the chat log when token usage exceeds `self.compaction_threshold`.
          - Emits `iteration_complete` and `turn_complete` events after each successful turn.
        - When either phase signals that the investigation is complete, yields an `agent_completed` event with a summary and statistics, then returns.
        - If the maximum iteration count is hit without completion, forces termination by yielding an `agent_completed` event marked as incomplete.
        - Catches `asyncio.CancelledError` to emit an `agent_cancelled` event before re-raising.
        - Catches any other exception, logs it, and yields an `agent_error` event describing the failure.

        Yielded dictionaries have a mandatory `type` key indicating the event kind (e.g., `agent_started`, `phase_complete`, `iteration_complete`, `turn_complete`, `agent_completed`, `agent_cancelled`, `agent_error`) and additional fields specific to each event such as `summary`, `stats`, `message` or progress details.

        Parameters
        ----------
        None (the method operates on the instance attributes of the agent, including `self.question`, `self.db`, `self.llm_client`, `self.max_iterations` and others).

        Yields
        ------
        AsyncIterator[Dict[str, Any]]
            Progress events as described above. The iterator yields intermediate UI-friendly messages during tool execution, analysis, compaction, retries, cancellation, and final completion.

        Raises
        ------
        asyncio.CancelledError
            Propagated after emitting an `agent_cancelled` event when the coroutine is externally cancelled.
        Exception
            Any unexpected exception is caught, logged, and results in an `agent_error` event being yielded; the exception is not re-raised.
        """
        try:
            logger.info(f"AssistantAgentV2 starting: {self.question}")

            # Load investigation context with field dictionary
            context = await load_investigation_context(
                db=self.db,
                investigation_id=self.investigation_id,
                llm_client=self.llm_client,
                use_field_dictionary=True,
                llm_max_context=self.llm_max_context,
            )

            # Yield start message
            yield {
                "type": "agent_started",
                "agent": "assistant_agent_v2",
                "question": self.question,
            }

            # Build initial chat log
            system_prompt = get_system_prompt(context)
            chat_log = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self.question},
            ]

            # Main iteration loop
            while not self.cancelled and self.iteration < self.max_iterations:
                self.iteration += 1
                iteration_retry_count = 0
                max_iteration_retries = 2  # Retry failed iterations up to 2 times

                logger.info(f"=== Iteration {self.iteration}/{self.max_iterations} ===")

                # Check cancellation
                if await self.check_cancel_signal():
                    yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                    break

                # Iteration retry loop (for when all tools fail)
                iteration_successful = False

                while not iteration_successful and iteration_retry_count <= max_iteration_retries:
                    if iteration_retry_count > 0:
                        logger.warning(
                            f"Retrying iteration {self.iteration} (attempt {iteration_retry_count + 1}/{max_iteration_retries + 1}) "
                            f"due to all tools failing"
                        )
                        # Remove the failed tool execution prompt and results from chat log
                        # Keep only messages up to the last assistant analysis
                        chat_log = prune_chat_log(
                            chat_log, max_tokens=MAX_CHAT_LOG_TOKENS, preserve_recent=5
                        )

                    # === PHASE 1: Tool Execution ===
                    tool_execution_prompt = get_tool_execution_prompt(self.question, self.iteration)
                    chat_log.append({"role": "user", "content": tool_execution_prompt})

                    tool_results = None
                    assistant_msg_phase1 = None
                    investigation_completed_phase1 = False
                    completion_summary_phase1 = None

                    async for progress in self.execute_tool_phase(chat_log):
                        if progress.get("type") == "phase_complete":
                            assistant_msg_phase1 = progress.get("assistant_message")
                            tool_results = progress.get("tool_results", [])
                            investigation_completed_phase1 = progress.get(
                                "investigation_completed", False
                            )
                            completion_summary_phase1 = progress.get("completion_summary")
                        elif progress.get("type") == "phase_error":
                            # Phase 1 failed
                            yield progress
                            return
                        else:
                            yield progress  # Stream to UI

                    if tool_results is None:
                        logger.error("Phase 1 returned no tool results")
                        yield {"type": "agent_error", "error": "Tool execution phase failed"}
                        return

                    # Check if ALL tools failed
                    all_tools_failed = False
                    if tool_results is not None and len(tool_results) > 0:
                        all_tools_failed = all(
                            tr["result"].status == "error" for tr in tool_results
                        )
                    elif tool_results is None or len(tool_results) == 0:
                        # No tools executed at all - treat as failure
                        all_tools_failed = True

                    if all_tools_failed and iteration_retry_count < max_iteration_retries:
                        # All tools failed - retry this iteration without showing to UI
                        logger.warning(
                            f"All {len(tool_results) if tool_results else 0} tools failed in iteration {self.iteration}. "
                            f"Retrying iteration (attempt {iteration_retry_count + 1}/{max_iteration_retries + 1})..."
                        )
                        iteration_retry_count += 1

                        # Remove the failed prompt from chat log before retrying
                        if chat_log and chat_log[-1].get("role") == "user":
                            chat_log.pop()

                        # Continue to retry loop
                        continue

                    # If we get here, either some tools succeeded OR we've exhausted retries
                    if all_tools_failed and iteration_retry_count >= max_iteration_retries:
                        logger.error(
                            f"All tools failed in iteration {self.iteration} after {max_iteration_retries + 1} attempts. "
                            f"Continuing with errors visible to user."
                        )

                    # Add assistant message and tool results to chat log (if any tools were called)
                    if (
                        tool_results is not None
                        and assistant_msg_phase1
                        and assistant_msg_phase1.tool_calls
                    ):
                        # Add assistant's tool calls to chat log (strip any content - Phase 1 should be silent)
                        phase1_msg = assistant_msg_phase1.model_dump(exclude_none=True)
                        # Remove content field - Phase 1 should only have tool calls
                        phase1_msg.pop("content", None)
                        chat_log.append(phase1_msg)

                        # Add tool results to chat log (CSV format for agent efficiency)
                        for tr in tool_results:
                            if tr["result"].status == "ok" and tr["result"].result:
                                # Check if result contains events list
                                events = tr["result"].result.get("events", [])
                                if events and isinstance(events, list) and len(events) > 0:
                                    # Convert events to CSV for token efficiency
                                    csv_data = events_to_csv(events)
                                    count = tr["result"].result.get("count", len(events))

                                    # Format as CSV with metadata
                                    content = f"Found {count} events:\n\n{csv_data}"
                                else:
                                    # No events, just serialize the result
                                    content = _compact_serialize(tr["result"].result)
                            else:
                                # Error result
                                content = _compact_serialize({"error": tr["result"].error_msg})

                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": tr["tool_call_id"],
                                "name": tr["tool_name"],
                                "content": content,
                            }
                            chat_log.append(tool_msg)

                    # Build tool results summary for Phase 2
                    tool_results_summary = self._build_tool_results_summary(
                        tool_results if tool_results is not None else []
                    )

                    # Check if investigation was completed in Phase 1
                    if investigation_completed_phase1:
                        logger.info(
                            "Investigation completed in Phase 1. Running Phase 2 for final analysis, then exiting."
                        )

                    # === PHASE 2: Result Analysis ===
                    analysis_prompt = get_analysis_prompt(
                        self.question, self.iteration, tool_results_summary
                    )
                    chat_log.append({"role": "user", "content": analysis_prompt})

                    analysis_summary = None
                    investigation_completed = False
                    completion_summary = None  # Initialize here to avoid UnboundLocalError

                    async for progress in self.execute_analysis_phase(
                        chat_log, tool_results_summary
                    ):
                        if progress.get("type") == "phase_complete":
                            analysis_summary = progress.get("analysis_summary")
                            investigation_completed = progress.get("investigation_completed", False)
                            completion_summary = progress.get("completion_summary")  # May be None

                            # Check if investigation was completed in either phase
                            if investigation_completed or investigation_completed_phase1:
                                final_summary = (
                                    completion_summary
                                    or completion_summary_phase1
                                    or "Investigation completed"
                                )
                                logger.info(
                                    f"Investigation completed! Yielding final results and exiting. Summary: {final_summary[:100]}..."
                                )
                                yield {
                                    "type": "agent_completed",
                                    "summary": final_summary,
                                    "stats": {
                                        "turns_executed": self.iteration,
                                        "tool_executions": self.total_tools_executed,
                                        "events_analyzed": self.stats.get("events_analyzed", 0),
                                        "timeline_entries_created": self.stats.get(
                                            "timeline_entries_created", 0
                                        ),
                                        "tools_called": dict(self.stats.get("tools_called", {})),
                                    },
                                }
                                return
                            else:
                                logger.info(
                                    f"Investigation NOT completed. investigation_completed={investigation_completed}"
                                )
                        elif progress.get("type") == "phase_error":
                            yield progress
                            return
                        else:
                            yield progress

                    logger.info("Finished processing analysis phase results.")

                    # Add analysis summary to chat log
                    logger.info(
                        f"Adding analysis summary to chat log: {len(analysis_summary) if analysis_summary else 0} chars"
                    )
                    if analysis_summary:
                        chat_log.append({"role": "assistant", "content": analysis_summary})

                    # Check context and compact if needed (before next iteration)
                    current_tokens = sum(
                        estimate_tokens(json.dumps(msg, default=str)) for msg in chat_log
                    )
                    if current_tokens > self.compaction_threshold:
                        logger.info(
                            f"Chat log exceeds threshold ({current_tokens} > {self.compaction_threshold}), "
                            f"compacting before next iteration..."
                        )

                        compacted_log = None
                        async for progress in self._compact_chat_log(chat_log):
                            if progress.get("type") == "_compacted_chat_log":
                                compacted_log = progress.get("chat_log")
                            else:
                                yield progress  # Stream progress to UI

                        if compacted_log:
                            chat_log = compacted_log
                        else:
                            logger.warning("Compaction failed, using prune_chat_log as fallback")
                            chat_log = prune_chat_log(chat_log, max_tokens=MAX_CHAT_LOG_TOKENS)
                    else:
                        # Standard pruning to remove obvious duplicates/noise
                        chat_log = prune_chat_log(chat_log, max_tokens=MAX_CHAT_LOG_TOKENS)

                    # Yield iteration complete (also send as turn_complete for UI compatibility)
                    yield {
                        "type": "iteration_complete",
                        "iteration": self.iteration,
                        "tools_executed": len(tool_results) if tool_results is not None else 0,
                        "total_tools": self.total_tools_executed,
                    }
                    yield {
                        "type": "turn_complete",
                        "turn_number": self.iteration,
                        "tools_executed": len(tool_results) if tool_results is not None else 0,
                        "total_tools": self.total_tools_executed,
                    }

                    # Break out of iteration retry loop
                    iteration_successful = True
                    break

            # Check if we should continue to next iteration
            logger.info(f"Iteration {self.iteration} complete. Continuing to next iteration...")

            # End of main iteration loop - continue to next iteration

            # Max iterations reached without completion
            # Ensure we send a completion event before exiting
            logger.info(
                f"Agent exiting run loop. Cancelled: {self.cancelled}, Iteration: {self.iteration}/{self.max_iterations}"
            )

            if not self.cancelled:
                # Force completion with a summary
                logger.warning(
                    "Agent reached max iterations without calling complete_investigation. Forcing completion."
                )
                yield {
                    "type": "agent_completed",
                    "summary": f"Investigation reached maximum iterations ({self.max_iterations}) without explicit completion. "
                    f"Executed {self.total_tools_executed} tools and created {self.stats.get('timeline_entries_created', 0)} timeline entries.",
                    "stats": {
                        "turns_executed": self.iteration,
                        "tool_executions": self.total_tools_executed,
                        "events_analyzed": self.stats.get("events_analyzed", 0),
                        "timeline_entries_created": self.stats.get("timeline_entries_created", 0),
                        "tools_called": dict(self.stats.get("tools_called", {})),
                    },
                    "incomplete": True,
                }

        except asyncio.CancelledError:
            logger.info("AssistantAgentV2 cancelled")
            yield {
                "type": "agent_cancelled",
                "message": "Investigation stopped by user",
                "summary": "Investigation stopped by user",
                "stats": {
                    "turns_executed": self.iteration,
                    "tool_executions": self.total_tools_executed,
                    "events_analyzed": self.stats.get("events_analyzed", 0),
                    "timeline_entries_created": self.stats.get("timeline_entries_created", 0),
                    "tools_called": dict(self.stats.get("tools_called", {})),
                },
            }
            raise

        except Exception as e:
            logger.error(f"Unexpected error in AssistantAgentV2: {e}", exc_info=True)
            yield {
                "type": "agent_error",
                "error": f"Unexpected error: {type(e).__name__}: {str(e)}",
            }

    def _build_tool_results_summary(self, tool_results: List[Dict[str, Any]]) -> str:
        """
        Builds a concise, human-readable summary of the results returned by executed tools.

        Parameters
        ----------
        tool_results: List[Dict[str, Any]]
            A list where each element is a dictionary representing the outcome of a single tool execution.
            Expected keys in each dict are:
                * `"tool_name"` - The name of the tool that was run (str).
                * `"result"` - An object exposing attributes `status`, `result` and `error_msg`.
                  `status` is `"ok"` for successful executions; otherwise it indicates failure.
                  When `status` is `"ok"`, `result` may contain pagination metadata:
                      - `count` (int): Number of events found on the current page.
                      - `total_count` (int, optional): Total number of matching events across all pages.
                      - `current_page` (int, optional): Index of the current page.
                      - `total_pages` (int, optional): Total number of pages available.
                      - `has_more` (bool, optional): Whether additional data remains to be fetched.

        Returns
        -------
        str
            A markdown-formatted string that lists each tool with either a brief success description,
            including pagination details when applicable, or an error message if the tool failed.
            The summary always begins with the heading "**Tool Execution Results**:" followed by one line per
            tool. If more data is available for a successful query, a warning icon and hint are appended.
        """
        summary_parts = ["**Tool Execution Results**:\n\n"]

        for tr in tool_results:
            tool_name = tr["tool_name"]
            result = tr["result"]

            if result.status == "ok":
                # Summarize successful result with pagination info
                if result.result:
                    count = result.result.get("count", 0)
                    total_count = result.result.get("total_count")
                    current_page = result.result.get("current_page")
                    total_pages = result.result.get("total_pages")
                    has_more = result.result.get("has_more", False)

                    summary = f"- **{tool_name}**: Found {count} events"

                    # Add pagination info if available
                    if total_count is not None and total_count > count:
                        summary += f" (page {current_page}/{total_pages}, {total_count} total)"
                        if has_more:
                            summary += " ⚠️ MORE DATA AVAILABLE - use offset to explore"

                    summary_parts.append(summary + "\n")
                else:
                    summary_parts.append(f"- **{tool_name}**: No result\n")
            else:
                # Show error
                summary_parts.append(f"- **{tool_name}**: Error - {result.error_msg}\n")

        return "".join(summary_parts)


__all__ = ["AssistantAgentV2"]
