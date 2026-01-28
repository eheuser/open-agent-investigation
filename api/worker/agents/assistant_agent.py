import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core import LLMClient, ToolExecutor, tool_registry
from ..models import AssistantMessage, ToolResult
from ..tools.csv_formatter import events_to_csv
from .context_manager import estimate_tokens, prune_chat_log, load_investigation_context, load_execution_phase_context, load_analysis_phase_context
from .tool_categories import filter_tools_for_phase
from .memory_summarizer import generate_chat_summary, load_chat_summary, trim_messages_from_middle
from .prompts import (
    get_system_prompt,
    get_tool_execution_prompt,
    get_analysis_prompt,
)

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


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


class AssistantAgent:
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
        * Context management parameters are derived from the LLM's maximum context size; the agent will trigger a compaction step once the accumulated token usage exceeds 80 % of this limit.

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
            max_context_length=llm_max_context,
            temperature=llm_temperature,
            top_p=llm_top_p,
            top_k=llm_top_k,
            min_p=llm_min_p,
            timeout=llm_timeout,
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
            f"AssistantAgent initialized: investigation={investigation_id}, "
            f"max_iterations={max_iterations}, max_context={llm_max_context} (type: {type(llm_max_context).__name__}), "
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
                logger.info(f"LLM call: {len(chat_log):,} messages, ~{input_tokens:,} input tokens")

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
                    f"LLM response: ~{response_tokens:,} output tokens, "
                    f"{len(accumulated_tool_calls):,} tool calls, "
                    f"{len(accumulated_content):,} chars content"
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

    def _get_execution_phase_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools available for Phase 1 (tool execution phase).

        Retrieves data query tools from the registry and optionally includes
        the `complete_investigation` tool after a minimum number of iterations.

        Returns
        -------
        List[Dict[str, Any]]
            List of tool definitions in OpenAI format, filtered for Phase 1.
        """
        MIN_ITERATIONS_BEFORE_COMPLETION = 4
        all_tools = tool_registry.get_openai_format()
        execution_phase_tools = filter_tools_for_phase(all_tools, "tool_execution")

        # Allow complete_investigation after minimum iterations
        if self.iteration >= MIN_ITERATIONS_BEFORE_COMPLETION:
            complete_tool = [
                t
                for t in all_tools
                if t.get("function", {}).get("name") == "complete_investigation"
            ]
            if complete_tool:
                execution_phase_tools.extend(complete_tool)
                logger.info(
                    f"Iteration {self.iteration}/{MIN_ITERATIONS_BEFORE_COMPLETION}: "
                    f"complete_investigation tool ENABLED in Phase 1"
                )

        return execution_phase_tools

    def _get_analysis_phase_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools available for Phase 2 (analysis phase).

        Retrieves analysis tools from the registry and optionally excludes
        the `complete_investigation` tool before a minimum number of iterations.

        Returns
        -------
        List[Dict[str, Any]]
            List of tool definitions in OpenAI format, filtered for Phase 2.
        """
        MIN_ITERATIONS_BEFORE_COMPLETION = 4
        all_tools = tool_registry.get_openai_format()
        analysis_phase_tools = filter_tools_for_phase(all_tools, "analysis")

        # Remove complete_investigation until minimum iterations
        if self.iteration < MIN_ITERATIONS_BEFORE_COMPLETION:
            analysis_phase_tools = [
                tool
                for tool in analysis_phase_tools
                if tool.get("function", {}).get("name") != "complete_investigation"
            ]
            logger.info(
                f"Iteration {self.iteration}/{MIN_ITERATIONS_BEFORE_COMPLETION}: "
                f"complete_investigation tool DISABLED (need {MIN_ITERATIONS_BEFORE_COMPLETION - self.iteration} more iterations)"
            )

        return analysis_phase_tools

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
                    "message": f"Chat log trimmed from middle (LLM summary failed): {len(chat_log):,} → {len(trimmed_log):,} messages",
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
        summary += f"- Messages Compacted: {len(messages_to_compact):,}\n"
        summary += f"- Total Tools Executed: {self.total_tools_executed:,}\n"
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
            f"Compacted chat log: {len(chat_log):,} -> {len(compacted_log):,} messages, "
            f"{original_tokens_full} -> {new_tokens:,} tokens (saved {original_tokens_full - new_tokens:,} tokens, "
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

    def _get_stats(self) -> Dict[str, Any]:
        """
        Get current investigation statistics.

        Returns
        -------
        Dict[str, Any]
            Statistics dictionary with turns executed, tool executions, events analyzed,
            timeline entries created, and tools called.
        """
        return {
            "turns_executed": self.iteration,
            "tool_executions": self.total_tools_executed,
            "events_analyzed": self.stats.get("events_analyzed", 0),
            "timeline_entries_created": self.stats.get("timeline_entries_created", 0),
            "tools_called": dict(self.stats.get("tools_called", {})),
        }

    async def execute_tool_phase(
        self, chat_log: List[Dict[str, Any]], execution_phase_tools: List[Dict[str, Any]]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute Phase 1 (tool execution) of the investigation workflow.

        Prompts the LLM to select and execute data query tools, enforces limits,
        deduplicates calls, and handles special control tools.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Current conversation history in OpenAI chat format.
        execution_phase_tools: List[Dict[str, Any]]
            Tool definitions available for Phase 1, pre-filtered for this phase.

        Yields
        ------
        Dict[str, Any]
            Progress events including:
            - `context_compacted`: Chat log compaction result
            - `llm_response`: LLM response (internal)
            - `phase_error`: Fatal error in this phase
            - `tool_limit_enforced`: Tool count/duplicate limit applied
            - `turn_extension_granted`: Additional turns granted
            - `_internal_tool_result`: Tool execution result (internal)
            - `phase_complete`: Final phase result with tool outputs
        """
        logger.info(f"[Iteration {self.iteration}] Phase 1: Tool Execution")
        logger.info(
            f"Phase 1 tools available: {len(execution_phase_tools):,} - "
            f"{[t.get('function', {}).get('name') for t in execution_phase_tools]}"
        )

        # Call LLM to get tool executions
        # Use tool_choice="required" to force tool calls only (no text output)
        assistant_msg = None
        async for progress in self._call_llm_with_retry(
            chat_log=chat_log, tools=execution_phase_tools, tool_choice="required"
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
        investigation_completed_in_execution_phase = False
        completion_summary_execution_phase = None

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
                    tool_call_id=tool_call.id or f"call_{len(tool_results) + 1:,}",
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
                            "tool_call_id": tool_call.id or f"call_{len(tool_results):,}",
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
                        investigation_completed_in_execution_phase = True
                        completion_summary_execution_phase = tool_result.result.get(
                            "summary", "Investigation completed"
                        )
                        logger.info(
                            f"Investigation completed in Phase 1 with summary: {completion_summary_execution_phase[:100]}..."
                        )

        # Return results
        yield {
            "type": "phase_complete",
            "phase": "tool_execution",
            "assistant_message": assistant_msg,
            "tool_results": tool_results,
            "investigation_completed": investigation_completed_in_execution_phase,
            "completion_summary": completion_summary_execution_phase,
        }

    async def execute_analysis_phase(
        self, chat_log: List[Dict[str, Any]], analysis_phase_tools: List[Dict[str, Any]], tool_results_summary: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute Phase 2 (analysis) of the investigation workflow.

        Calls the LLM with analysis tools to interpret tool execution results,
        register timeline entries, and optionally complete the investigation.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Current conversation history in OpenAI chat format.
        analysis_phase_tools: List[Dict[str, Any]]
            Tool definitions available for Phase 2, pre-filtered for this phase.
        tool_results_summary: str
            Human-readable summary of Phase 1 tool execution results.

        Yields
        ------
        Dict[str, Any]
            Progress events including:
            - `llm_response`: LLM response (internal)
            - `phase_error`: Fatal error in this phase
            - `tool_limit_enforced`: Duplicate tool calls removed
            - `timeline_updated`: Timeline entry registered
            - `agent_cancelled`: Cancellation signal received
            - `phase_complete`: Final analysis result with completion status
        """
        logger.info(f"[Iteration {self.iteration}] Phase 2: Result Analysis")
        logger.info(
            f"Phase 2 tools available: {len(analysis_phase_tools):,} - "
            f"{[t.get('function', {}).get('name') for t in analysis_phase_tools]}"
        )

        # Call LLM to get analysis
        assistant_msg = None
        async for progress in self._call_llm_with_retry(
            chat_log=chat_log, tools=analysis_phase_tools, tool_choice="auto"
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
                        f"Agent called complete_investigation {len(complete_calls):,} times in analysis phase, will only execute once"
                    )
                    yield {
                        "type": "tool_limit_enforced",
                        "message": f"complete_investigation called {len(complete_calls):,} times - will only execute once at the end",
                        "requested": len(complete_calls),
                        "executed": 1,
                    }

                # Execute other tools first, then complete_investigation last
                logger.info(
                    f"Reordering analysis tools: executing {len(other_calls):,} tools first, then complete_investigation last"
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

    async def _run_execution_phase(
        self, chat_log: List[Dict[str, Any]], execution_phase_tools: List[Dict[str, Any]]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Run Phase 1 (tool execution) and return results.

        Loads Phase 1 context (event types, JSONB fields) and executes tools.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Current conversation history.
        execution_phase_tools: List[Dict[str, Any]]
            Pre-filtered tools for Phase 1.

        Yields
        ------
        Dict[str, Any]
            Progress events and final phase_complete event.
        """
        # Load Phase 1 context (event types and JSONB fields)
        execution_phase_context = await load_execution_phase_context(
            db=self.db,
            investigation_id=self.investigation_id,
            llm_client=self.llm_client,
            use_field_dictionary=True,
            llm_max_context=self.llm_max_context,
        )

        # Build Phase 1 prompt with context
        tool_execution_prompt = get_tool_execution_prompt(self.question, self.iteration)
        full_prompt = f"{execution_phase_context}\n{tool_execution_prompt}"
        chat_log.append({"role": "user", "content": full_prompt})

        async for progress in self.execute_tool_phase(chat_log, execution_phase_tools):
            yield progress

    async def _run_analysis_phase(
        self, chat_log: List[Dict[str, Any]], analysis_phase_tools: List[Dict[str, Any]], tool_results_summary: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Run Phase 2 (analysis) and return results.

        Loads Phase 2 context (timeline entries) and performs analysis.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Current conversation history.
        analysis_phase_tools: List[Dict[str, Any]]
            Pre-filtered tools for Phase 2.
        tool_results_summary: str
            Summary of Phase 1 results.

        Yields
        ------
        Dict[str, Any]
            Progress events and final phase_complete event.
        """
        # Load Phase 2 context (timeline entries)
        analysis_phase_context = await load_analysis_phase_context(
            db=self.db,
            investigation_id=self.investigation_id,
        )

        # Build Phase 2 prompt with context
        analysis_prompt = get_analysis_prompt(self.question, self.iteration, tool_results_summary)
        full_prompt = f"{analysis_phase_context}\n{analysis_prompt}"
        chat_log.append({"role": "user", "content": full_prompt})

        async for progress in self.execute_analysis_phase(chat_log, analysis_phase_tools, tool_results_summary):
            yield progress

    def _add_tool_results_to_chat(
        self, chat_log: List[Dict[str, Any]], assistant_msg: Optional[AssistantMessage], tool_results: Optional[List[Dict[str, Any]]]
    ) -> None:
        """
        Add Phase 1 tool results to chat log in CSV format.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Chat log to modify in-place.
        assistant_msg: Optional[AssistantMessage]
            Assistant message containing tool calls, or None.
        tool_results: Optional[List[Dict[str, Any]]]
            Tool execution results to add, or None.
        """
        if not tool_results or not assistant_msg or not assistant_msg.tool_calls:
            return

        # Add assistant's tool calls (strip content - Phase 1 is silent)
        execution_phase_msg = assistant_msg.model_dump(exclude_none=True)
        execution_phase_msg.pop("content", None)
        chat_log.append(execution_phase_msg)

        # Add tool results (CSV format for efficiency)
        for tr in tool_results:
            if tr["result"].status == "ok" and tr["result"].result:
                events = tr["result"].result.get("events", [])
                if events and isinstance(events, list) and len(events) > 0:
                    csv_data = events_to_csv(events)
                    count = tr["result"].result.get("count", len(events))
                    content = f"Found {count} events:\n\n{csv_data}"
                else:
                    content = _compact_serialize(tr["result"].result)
            else:
                content = _compact_serialize({"error": tr["result"].error_msg})

            chat_log.append({
                "role": "tool",
                "tool_call_id": tr["tool_call_id"],
                "name": tr["tool_name"],
                "content": content,
            })

    async def _batch_generate_embeddings(self) -> None:
        """
        Batch generate embeddings for timeline entries created in this iteration.

        More efficient than generating embeddings serially during registration.
        Called at the end of each iteration.
        """
        try:
            from ..tools.timeline_tools import batch_generate_embeddings

            count = await batch_generate_embeddings(
                db=self.db,
                investigation_id=self.investigation_id,
                user_id=self.user_id or 1,
            )
            if count > 0:
                logger.info(f"Batch generated {count} embeddings for timeline entries")
        except Exception as e:
            logger.warning(f"Failed to batch generate embeddings: {e}")

    async def _compact_chat_if_needed(self, chat_log: List[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
        """
        Compact or prune chat log if it exceeds threshold.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Chat log to check and potentially compact.

        Yields
        ------
        Dict[str, Any]
            Progress events from compaction process.
        """
        current_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in chat_log)
        
        if current_tokens > self.compaction_threshold:
            logger.info(
                f"Chat log exceeds threshold ({current_tokens} > {self.compaction_threshold}), "
                f"compacting..."
            )
            compacted_log = None
            async for progress in self._compact_chat_log(chat_log):
                if progress.get("type") == "_compacted_chat_log":
                    compacted_log = progress.get("chat_log")
                else:
                    yield progress

            if compacted_log:
                chat_log[:] = compacted_log
            else:
                logger.warning("Compaction failed, using prune_chat_log")
                chat_log[:] = prune_chat_log(chat_log, max_tokens=MAX_CHAT_LOG_TOKENS)
        else:
            chat_log[:] = prune_chat_log(chat_log, max_tokens=MAX_CHAT_LOG_TOKENS)

    def _check_investigation_complete(
        self, 
        investigation_completed: bool,
        investigation_completed_execution_phase: bool,
        completion_summary: Optional[str],
        completion_summary_execution_phase: Optional[str]
    ) -> Optional[str]:
        """
        Check if investigation completed and return final summary.

        Parameters
        ----------
        investigation_completed: bool
            Whether Phase 2 completed the investigation.
        investigation_completed_execution_phase: bool
            Whether Phase 1 completed the investigation.
        completion_summary: Optional[str]
            Summary from Phase 2.
        completion_summary_execution_phase: Optional[str]
            Summary from Phase 1.

        Returns
        -------
        Optional[str]
            Final summary if completed, None otherwise.
        """
        if investigation_completed or investigation_completed_execution_phase:
            return completion_summary or completion_summary_execution_phase or "Investigation completed"
        return None

    async def _execute_iteration(
        self, chat_log: List[Dict[str, Any]]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a single investigation iteration (both phases).

        Runs Phase 1 (tool execution) followed by Phase 2 (analysis), handling
        retries when all tools fail, and updating the chat log with results.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Current conversation history, modified in-place.

        Yields
        ------
        Dict[str, Any]
            Progress events from both phases, plus:
            - `iteration_complete`: Iteration finished successfully
            - `turn_complete`: Turn finished (UI compatibility)
            - `agent_completed`: Investigation completed (triggers return)
        """
        max_iteration_retries = 2
        iteration_retry_count = 0

        while iteration_retry_count <= max_iteration_retries:
            if iteration_retry_count > 0:
                logger.warning(
                    f"Retrying iteration {self.iteration} "
                    f"(attempt {iteration_retry_count + 1}/{max_iteration_retries + 1}) "
                    f"due to all tools failing"
                )
                chat_log[:] = prune_chat_log(chat_log, max_tokens=MAX_CHAT_LOG_TOKENS, preserve_recent=5)

            # === PHASE 1: Tool Execution ===
            execution_phase_tools = self._get_execution_phase_tools()
            tool_results = None
            assistant_msg_execution_phase = None
            investigation_completed_execution_phase = False
            completion_summary_execution_phase = None

            async for progress in self._run_execution_phase(chat_log, execution_phase_tools):
                if progress.get("type") == "phase_complete":
                    assistant_msg_execution_phase = progress.get("assistant_message")
                    tool_results = progress.get("tool_results", [])
                    investigation_completed_execution_phase = progress.get("investigation_completed", False)
                    completion_summary_execution_phase = progress.get("completion_summary")
                elif progress.get("type") == "phase_error":
                    yield progress
                    return
                else:
                    yield progress

            if tool_results is None:
                logger.error("Phase 1 returned no tool results")
                yield {"type": "agent_error", "error": "Tool execution phase failed"}
                return

            # Check if all tools failed - retry if needed
            all_tools_failed = not tool_results or all(tr["result"].status == "error" for tr in tool_results)
            if all_tools_failed and iteration_retry_count < max_iteration_retries:
                logger.warning(f"All {len(tool_results) if tool_results else 0:,} tools failed. Retrying...")
                iteration_retry_count += 1
                if chat_log and chat_log[-1].get("role") == "user":
                    chat_log.pop()
                continue

            if all_tools_failed:
                logger.error(f"All tools failed after {max_iteration_retries + 1} attempts. Continuing with errors.")

            # Add tool results to chat log
            self._add_tool_results_to_chat(chat_log, assistant_msg_execution_phase, tool_results)

            # Build summary for Phase 2
            tool_results_summary = self._build_tool_results_summary(tool_results if tool_results else [])

            if investigation_completed_execution_phase:
                logger.info("Investigation completed in Phase 1. Running Phase 2 for final analysis.")

            # === PHASE 2: Result Analysis ===
            analysis_phase_tools = self._get_analysis_phase_tools()
            analysis_summary = None
            investigation_completed = False
            completion_summary = None

            async for progress in self._run_analysis_phase(chat_log, analysis_phase_tools, tool_results_summary):
                if progress.get("type") == "phase_complete":
                    analysis_summary = progress.get("analysis_summary")
                    investigation_completed = progress.get("investigation_completed", False)
                    completion_summary = progress.get("completion_summary")

                    # Check if investigation completed
                    final_summary = self._check_investigation_complete(
                        investigation_completed, investigation_completed_execution_phase,
                        completion_summary, completion_summary_execution_phase
                    )
                    if final_summary:
                        logger.info(f"Investigation completed! Summary: {final_summary[:100]}...")
                        yield {
                            "type": "agent_completed",
                            "summary": final_summary,
                            "stats": self._get_stats(),
                        }
                        return
                elif progress.get("type") == "phase_error":
                    yield progress
                    return
                else:
                    yield progress

            # Add analysis summary to chat log
            if analysis_summary:
                chat_log.append({"role": "assistant", "content": analysis_summary})

            # Batch generate embeddings for any new timeline entries
            await self._batch_generate_embeddings()

            # Compact chat log if needed
            async for progress in self._compact_chat_if_needed(chat_log):
                yield progress

            # Yield iteration complete
            yield {
                "type": "iteration_complete",
                "iteration": self.iteration,
                "tools_executed": len(tool_results) if tool_results else 0,
                "total_tools": self.total_tools_executed,
            }
            yield {
                "type": "turn_complete",
                "turn_number": self.iteration,
                "tools_executed": len(tool_results) if tool_results else 0,
                "total_tools": self.total_tools_executed,
            }

            return

    def _remove_tool_messages_from_chat(self, chat_log: List[Dict[str, Any]]) -> None:
        """
        Remove tool-related messages from chat log to prevent unbounded growth.

        Removes:
        - Assistant messages with tool_calls
        - Tool result messages (role="tool")

        Preserves:
        - System messages
        - User messages
        - Assistant messages with content only (analysis summaries)

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Chat log to modify in-place.
        """
        messages_to_keep = []
        removed_count = 0

        for msg in chat_log:
            role = msg.get("role")
            
            # Keep system and user messages
            if role in ["system", "user"]:
                messages_to_keep.append(msg)
            # Keep assistant messages that only have content (analysis summaries)
            elif role == "assistant" and "tool_calls" not in msg:
                messages_to_keep.append(msg)
            # Remove tool result messages and assistant messages with tool_calls
            elif role == "tool" or (role == "assistant" and "tool_calls" in msg):
                removed_count += 1
            else:
                # Keep anything else (shouldn't happen, but be safe)
                messages_to_keep.append(msg)

        if removed_count > 0:
            logger.info(f"Removed {removed_count} tool-related messages from chat log")
            chat_log[:] = messages_to_keep

    async def _refresh_timeline_context_if_needed(
        self, chat_log: List[Dict[str, Any]], previous_timeline_count: int
    ) -> int:
        """
        Refresh timeline context in system prompt if timeline entries changed.

        Parameters
        ----------
        chat_log: List[Dict[str, Any]]
            Chat log to potentially update.
        previous_timeline_count: int
            Number of timeline entries from previous iteration.

        Returns
        -------
        int
            Current number of timeline entries.
        """
        current_timeline_count = self.stats.get("timeline_entries_created", 0)

        # Only refresh if timeline changed
        if current_timeline_count != previous_timeline_count:
            logger.info(
                f"Timeline changed: {previous_timeline_count} -> {current_timeline_count} entries. "
                f"Refreshing context..."
            )

            # Reload full investigation context with updated timeline
            context = await load_investigation_context(
                db=self.db,
                investigation_id=self.investigation_id,
                llm_client=self.llm_client,
                use_field_dictionary=True,
                llm_max_context=self.llm_max_context,
            )

            # Update system prompt (first message in chat log)
            system_prompt = get_system_prompt(context)
            if chat_log and chat_log[0].get("role") == "system":
                chat_log[0]["content"] = system_prompt
                logger.info("Updated system prompt with refreshed timeline context")

        return current_timeline_count

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Run the assistant agent investigation loop.

        Orchestrates the full investigation lifecycle using a two-phase architecture:
        1. **Tool Execution Phase** - LLM selects and executes data query tools
        2. **Analysis Phase** - LLM analyzes results and updates timeline

        Yields
        ------
        AsyncIterator[Dict[str, Any]]
            Progress events including:
            - `agent_started`: Investigation started
            - `phase_complete`: Phase finished
            - `iteration_complete`: Iteration finished
            - `turn_complete`: Turn finished (UI compatibility)
            - `agent_completed`: Investigation completed or max iterations reached
            - `agent_cancelled`: User cancelled investigation
            - `agent_error`: Unexpected error occurred

        Raises
        ------
        asyncio.CancelledError
            Propagated after emitting `agent_cancelled` event.
        """
        try:
            logger.info("AssistantAgent starting")
            logger.debug(f"AssistantAgent starting: {self.question}")

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
                "agent": "assistant_agent",
                "question": self.question,
            }

            # Build initial chat log
            system_prompt = get_system_prompt(context)
            chat_log = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self.question},
            ]

            # Track timeline count for refresh detection
            timeline_count = 0

            # Main iteration loop
            while not self.cancelled and self.iteration < self.max_iterations:
                self.iteration += 1
                logger.info(f"=== Iteration {self.iteration}/{self.max_iterations} ===")

                # Check cancellation
                if await self.check_cancel_signal():
                    yield {"type": "agent_cancelled", "message": "Investigation stopped"}
                    break

                # Remove tool calls and results from previous iteration
                self._remove_tool_messages_from_chat(chat_log)

                # Refresh timeline context if timeline entries changed
                timeline_count = await self._refresh_timeline_context_if_needed(
                    chat_log, timeline_count
                )

                # Execute iteration (both phases)
                async for progress in self._execute_iteration(chat_log):
                    yield progress
                    # If investigation completed, _execute_iteration already yielded agent_completed
                    if progress.get("type") == "agent_completed":
                        return
                    if progress.get("type") == "agent_error":
                        return

            # Max iterations reached without completion
            if not self.cancelled:
                logger.warning(
                    "Agent reached max iterations without completing. Forcing completion."
                )
                yield {
                    "type": "agent_completed",
                    "summary": (
                        f"Investigation reached maximum iterations ({self.max_iterations}) "
                        f"without explicit completion. Executed {self.total_tools_executed} tools "
                        f"and created {self.stats.get('timeline_entries_created', 0)} timeline entries."
                    ),
                    "stats": self._get_stats(),
                    "incomplete": True,
                }

        except asyncio.CancelledError:
            logger.info("AssistantAgent cancelled")
            yield {
                "type": "agent_cancelled",
                "message": "Investigation stopped by user",
                "summary": "Investigation stopped by user",
                "stats": self._get_stats(),
            }
            raise

        except Exception as e:
            logger.error(f"Unexpected error in AssistantAgent: {e}", exc_info=True)
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


__all__ = ["AssistantAgent"]
