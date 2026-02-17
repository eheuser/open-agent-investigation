import json
import logging
import re
import sys
import tiktoken
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import yaml

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Add parent directories to path to import from api.app
worker_dir = Path(__file__).parent.parent
api_dir = worker_dir.parent
if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

from app.services.llm_service import LLMService, LLMConfig

# Import the new function for getting available fields
try:
    from ..tools.event_tools import get_available_jsonb_fields
except ImportError:
    # Fallback if import fails (shouldn't happen in normal operation)
    async def get_available_jsonb_fields(db, investigation_id, event_type=None):
        """
        Retrieve a list of JSONB field names that are available for a given investigation.

        Parameters
        ----------
        db : object
            Database connection or session used to query the investigation data.
        investigation_id : int or str
            Identifier of the investigation whose JSONB fields should be inspected.
        event_type : str, optional
            Specific event type to filter the JSONB fields. If omitted, fields for all event types are returned.

        Returns
        -------
        list[str]
            A list containing the names of JSONB fields that can be queried for the specified investigation (and optionally filtered by event type). The list may be empty if no matching fields are found.
        """
        return []


from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)

# Token counter (using tiktoken for OpenAI-compatible models)
try:
    encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4/3.5 encoding
except Exception:
    encoding = None
    logger.warning("tiktoken not available, using character-based estimation")


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens that would be produced by encoding the given text.

    Args:
        text (str): The input string whose token count is to be estimated.

    Returns:
        int: An approximate token count. If a tokenizer encoding is available, the exact length of the encoded
             representation is returned; otherwise a rough estimate based on an average of four characters per token is provided.
    """
    if encoding:
        return len(encoding.encode(text))
    else:
        # Rough estimate: ~4 chars per token
        return len(text) // 4


class BaseAgent:
    """
    Base class for investigation agents.

    Provides common functionality:
    - LLM interaction
    - Tool call parsing (both function calling and text-based)
    - Memory management
    - Status updates
    """

    def __init__(
        self,
        db: AsyncSession,
        investigation_id: str,
        job_id: int,
        question: str,
        effort: str = "medium",
        llm_endpoint: Optional[str] = None,
        llm_model: str = "gpt-4",
        llm_api_key: Optional[str] = None,
        llm_max_context: int = 32768,
        llm_temperature: float = 0.1,
        agent_yaml_path: Optional[Path] = None,
    ):
        """
        Initialize a BaseAgent instance that coordinates LLM interactions, tool usage, and investigative workflow state.

        Args:
            db: An asynchronous SQLAlchemy session used for persisting investigation data.
            investigation_id: The UUID string identifying the current investigation.
            job_id: Integer identifier for this agent execution within the investigation.
            question: The original user query that drives the investigation.
            effort: Desired effort level - `low`, `medium` or `high` - influencing loop limits and resource usage. Defaults to `"medium"`.
            llm_endpoint: Optional custom endpoint URL for the LLM API. If omitted, defaults to OpenAI’s chat completions endpoint.
            llm_model: Name of the language model to use (e.g., `"gpt-4"`). Defaults to `"gpt-4"`.
            llm_api_key: Optional API key for authenticating with the LLM provider.
            llm_max_context: Maximum number of tokens the model can accept in a single request. Defaults to `32768`.
            llm_temperature: Sampling temperature controlling response randomness. Defaults to `0.1`.
            agent_yaml_path: Optional path to a YAML file defining additional agent configuration such as effort-level loop limits.

        Attributes set by the initializer:
            db: The provided database session.
            investigation_id, job_id, question, effort: Stored input parameters for later reference.
            _llm_service: An `LLMService` instance configured with the supplied endpoint, model, API key, context length, and temperature.
            llm_endpoint, llm_model, llm_api_key, llm_temperature, max_context_tokens: Backward-compatible copies of LLM configuration values.
            compaction_threshold: Token count at which conversation history will be compacted (half of `llm_max_context` capped at 16 384 tokens).
            agent_def: Parsed contents of the YAML definition file if one was supplied and exists; otherwise `None`.
            max_loops: Maximum number of reasoning loops permitted, derived from the agent definition’s `effort_levels` mapping or defaulting to six.
            stats: Dictionary tracking execution metrics such as loops executed, events analyzed, nodes/edges created, findings, tags applied, and tool call counts.
            should_exit, exit_reason: Flags used to terminate the agent early; initially `False` with no reason.
            last_status_update: Timestamp of the most recent status broadcast, initialized to the current UTC time.
            _disable_function_calling: Boolean indicating whether function calling is disabled for the LLM; defaults to `False`.
            _available_fields: Cached list of JSONB fields available in the database; populated lazily on first use.
        """
        self.db = db
        self.investigation_id = investigation_id
        self.job_id = job_id
        self.question = question
        self.effort = effort
        # Create centralized LLM service
        config = LLMConfig(
            api_endpoint=llm_endpoint or "https://api.openai.com/v1/chat/completions",
            model_name=llm_model,
            api_key=llm_api_key,
            max_context_length=llm_max_context,
            temperature=llm_temperature,
        )
        self._llm_service = LLMService(config)

        # Keep these for backward compatibility
        self.llm_endpoint = llm_endpoint or "https://api.openai.com/v1/chat/completions"
        self.llm_model = llm_model
        self.llm_api_key = llm_api_key
        self.llm_temperature = llm_temperature
        self.max_context_tokens = llm_max_context
        self.compaction_threshold = min(int(llm_max_context * 0.5), 16_384)

        # Load agent definition if provided
        self.agent_def = None
        if agent_yaml_path and agent_yaml_path.exists():
            with open(agent_yaml_path) as f:
                self.agent_def = yaml.safe_load(f)

        # Effort levels
        if self.agent_def:
            effort_levels = self.agent_def.get("effort_levels", {})
            self.max_loops = effort_levels.get(effort, effort_levels.get("medium", 10))
        else:
            self.max_loops = 6

        # Statistics
        self.stats = {
            "loops_executed": 0,
            "events_analyzed": 0,
            "nodes_created": 0,
            "edges_created": 0,
            "findings": [],
            "tags_applied": set(),
            "tools_called": {},
        }

        # Early exit flag
        self.should_exit = False
        self.exit_reason = None

        # Last status update time
        self.last_status_update = datetime.utcnow()

        # Track if function calling is supported
        self._disable_function_calling = False

        # Available JSONB fields (populated on first use)
        self._available_fields: Optional[List[str]] = None

        logger.info(
            f"{self.__class__.__name__} initialized with model={llm_model}, "
            f"max_context={llm_max_context}, temperature={llm_temperature}, "
            f"compaction_threshold={self.compaction_threshold}"
        )

    async def get_available_fields(self) -> List[str]:
        """
        Retrieve and cache the list of JSONB field names defined for the current investigation.

        The method queries the database only on the first call; subsequent calls return the cached
        result stored in `self._available_fields`.  If an error occurs while fetching the data,
        the exception is logged and an empty list is returned, ensuring that callers always receive
        a list.

        Returns:
            List[str]: A list containing the names of all available JSONB fields for the investigation.

        Notes:
            - The result is cached per instance to avoid redundant database queries.
            - Errors during retrieval are caught, logged, and result in an empty list rather than
              propagating the exception.
        """
        if self._available_fields is None:
            try:
                self._available_fields = await get_available_jsonb_fields(
                    self.db, self.investigation_id
                )
                logger.info(
                    f"Loaded {len(self._available_fields):,} available JSONB fields "
                    f"for investigation {self.investigation_id}"
                )
            except Exception as e:
                logger.error(f"Failed to load available fields: {sanitize_log_message(str(e))}", exc_info=True)
                self._available_fields = []

        return self._available_fields

    async def update_job_status(self, status_message: str):
        """
        Updates the job's status message in the database, ensuring that updates occur at most once every 30 seconds.

        Args:
            status_message (str): The new status text to store for the job. Only the first 1000 characters are persisted.

        Raises:
            None explicitly; any exception raised during the database operation is caught and logged as a warning, preventing propagation.
        """
        now = datetime.utcnow()
        elapsed = (now - self.last_status_update).total_seconds()

        if elapsed >= 30:
            try:
                await self.db.execute(
                    text(
                        """
                        UPDATE jobs_agents 
                        SET error_message = :status
                        WHERE job_id = :job_id
                    """
                    ),
                    {"job_id": self.job_id, "status": status_message[:1000]},
                )
                await self.db.commit()
                self.last_status_update = now
                logger.info(f"Job {self.job_id} status: {status_message}")
            except Exception as e:
                logger.warning(f"Failed to update job status: {sanitize_log_message(str(e))}")

    async def call_llm(
        self, messages: List[Dict[str, Any]], stream: bool = False
    ) -> Union[Dict[str, Any], Any]:
        """
        Call the language model with the provided message history and handle tool integration, token accounting, and error management.

        Args:
            messages (List[Dict[str, Any]]): A list of message dictionaries representing the conversation history to be sent to the LLM.
            stream (bool, optional): If True, request a streaming response. Streaming is not currently supported by the centralized service for BaseAgent; attempting to use it raises NotImplementedError. Defaults to False.

        Returns:
            Union[Dict[str, Any], Any]: The assistant message extracted from the LLM's response. When function calling is successful, this includes tool call information; otherwise it contains a plain text reply.

        Raises:
            RuntimeError: Propagated if an unexpected runtime error occurs during the LLM request.
            Exception: Raised when the token count exceeds the maximum context size or other unrecoverable errors are encountered. The exception message provides details about the token limit breach and suggests compacting memory before retrying.
            NotImplementedError: Raised when streaming mode is requested, as it is not yet supported by the centralized service for this agent.
        """
        # Calculate and log token count
        current_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in messages)

        # Log detailed breakdown
        logger.info(
            f"Sending to LLM: {current_tokens:,} tokens "
            f"({len(messages):,} messages, {current_tokens/self.max_context_tokens*100:.1f}% of max context)"
        )

        # Log per-message breakdown if in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            for i, msg in enumerate(messages):
                msg_tokens = estimate_tokens(json.dumps(msg, default=str))
                role = msg.get("role", "unknown")
                logger.debug(f"  Message {i} ({role}): {msg_tokens} tokens")

        if current_tokens > self.compaction_threshold:
            logger.warning(
                f"WARNING: Context approaching limit ({current_tokens}/{self.max_context_tokens} tokens), "
                "caller should compact before LLM call"
            )

        # Build tool definitions for function calling
        tools = self._build_tool_definitions()

        # Check if we should use function calling or text-based tool calls
        use_function_calling = not self._disable_function_calling

        # Prepare tools for centralized service
        tools_param = tools if (use_function_calling and tools) else None

        try:
            if stream:
                # Streaming not yet supported by centralized service for base_agent
                # Fall back to direct implementation for now
                logger.warning("Streaming mode not yet centralized, using legacy implementation")
                # Return a placeholder - this path is rarely used
                raise NotImplementedError("Streaming not yet centralized for base_agent")
            else:
                # Use centralized service for non-streaming calls
                try:
                    result = await self._llm_service.call_llm(
                        messages=messages,
                        max_tokens=min(4096, self.max_context_tokens // 4),
                        temperature=self.llm_temperature,
                        tools=tools_param,
                        tool_choice="auto" if tools_param else None,
                        enforce_context_limit=False,  # We manage context ourselves
                    )

                    # Extract assistant message
                    assistant_message = result["choices"][0]["message"]

                    # Log token usage if available
                    if "usage" in result:
                        usage = result["usage"]
                        logger.info(
                            f"LLM response: {usage.get('completion_tokens', 0)} tokens generated, "
                            f"{usage.get('total_tokens', 0)} total tokens used"
                        )

                    return assistant_message

                except RuntimeError as e:
                    error_str = str(e)

                    # Check if error is due to unsupported 'tools' parameter
                    if "tools" in error_str.lower() or "function" in error_str.lower():
                        logger.warning(
                            f"LLM doesn't support function calling, falling back to text-based tool calls. "
                            f"Error: {error_str[:200]}"
                        )
                        # Disable function calling for future calls
                        self._disable_function_calling = True

                        # Retry without tools
                        messages = self._inject_tool_descriptions_to_messages(messages)

                        result = await self._llm_service.call_llm(
                            messages=messages,
                            max_tokens=min(4096, self.max_context_tokens // 4),
                            temperature=self.llm_temperature,
                            tools=None,
                            enforce_context_limit=False,
                        )

                        assistant_message = result["choices"][0]["message"]
                        return assistant_message
                    else:
                        raise

        except Exception as e:
            error_str = str(e)

            # Check for context length errors
            if "context" in error_str.lower() or "token" in error_str.lower():
                logger.error(
                    f"Context length error detected. Current tokens: {current_tokens}, "
                    f"Max: {self.max_context_tokens}."
                )
                raise Exception(
                    f"Context length exceeded ({current_tokens}/{self.max_context_tokens} tokens). "
                    "Caller should compact memory and retry."
                )

            logger.error(f"LLM call failed: {sanitize_log_message(str(e))}", exc_info=True)
            raise

    def _build_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Build a list of OpenAI function-calling tool definitions from the agent's configuration.

        The method inspects `self.agent_def` for a `"tools"` entry. For each tool it extracts the name, description, and optional parameter specifications, then converts those into the JSON schema format required by OpenAI’s function calling API.

        Parameters
        ----------
        None (uses instance attributes).

        Returns
        -------
        list of dict
            A list where each element is a dictionary representing a tool definition with the keys:

            * `"type"` - always set to `"function"`.
            * `"function"` - a nested mapping containing:
                - `"name"` - the tool's name.
                - `"description"` - the tool's description.
                - `"parameters"` - a JSON-schema object describing the function’s arguments, including:
                    - `"type"` - always `"object"`.
                    - `"properties"` - a mapping of parameter names to their type and description.
                    - `"required"` - a list of required parameter names (parameters whose description does not contain the word “optional”).

        The conversion handles simple type strings (e.g., `string`, `integer`, `object`) and maps `"array of strings"` to an array schema with string items. If `self.agent_def` is missing or lacks a `"tools"` key, an empty list is returned.
        """
        if not self.agent_def or "tools" not in self.agent_def:
            return []

        tools_def = []

        for tool in self.agent_def["tools"]:
            tool_name = tool["name"]
            tool_desc = tool["description"]
            params = tool.get("parameters", {})

            # Convert to OpenAI function schema
            properties = {}
            required = []

            for param_name, param_desc in params.items():
                # Parse "name: type (description)" format
                parts = param_desc.split(" (", 1)
                param_type = parts[0].split(": ")[1] if ": " in parts[0] else "string"

                # Map types
                type_map = {
                    "string": "string",
                    "integer": "integer",
                    "object": "object",
                    "array of strings": "array",
                }

                json_type = type_map.get(param_type, "string")

                properties[param_name] = {
                    "type": json_type,
                    "description": parts[1].rstrip(")") if len(parts) > 1 else param_desc,
                }

                if json_type == "array":
                    properties[param_name]["items"] = {"type": "string"}

                # Mark as required if no "optional" in description
                if "optional" not in param_desc.lower():
                    required.append(param_name)

            tools_def.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool_desc,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                }
            )

        return tools_def

    def _inject_tool_descriptions_to_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Injects descriptions of available tools into the system message when the underlying LLM does not support native function calling.

        Args:
            messages: A list of message dictionaries representing the conversation history. Each dictionary must contain at least a "role" key (e.g., "system", "user", "assistant") and a "content" key with the textual payload.

        Returns:
            A new list of message dictionaries where the original list is left unmodified. If the first message has the role "system" and the agent definition includes tool specifications, the system content is appended with a formatted markdown section that enumerates each tool's name, description, and parameters.

        Notes:
            * The method checks `self.agent_def` for a "tools" entry; if absent or empty, the original messages are returned unchanged.
            * Tool parameter information is rendered as a bullet-point list under a "Parameters:" heading.
            * Logging at INFO level records when tool descriptions are injected.
        """
        if not self.agent_def or "tools" not in self.agent_def:
            return messages

        tool_descriptions = ["\n\n## Available Tools\n"]
        tool_descriptions.append(
            'To use a tool, output: Tool: <tool_name>\n{"param": "value", ...}\n\n'
        )

        for tool in self.agent_def["tools"]:
            tool_descriptions.append(f"### {tool['name']}\n")
            tool_descriptions.append(f"{tool['description']}\n\n")

            if "parameters" in tool and tool["parameters"]:
                tool_descriptions.append("Parameters:\n")
                for param_name, param_desc in tool["parameters"].items():
                    tool_descriptions.append(f"- {param_name}: {param_desc}\n")
                tool_descriptions.append("\n")

        tool_text = "".join(tool_descriptions)

        # Create a copy of messages to avoid mutating the original
        messages_copy = messages.copy()

        # Update system message
        if len(messages_copy) > 0 and messages_copy[0]["role"] == "system":
            messages_copy[0] = messages_copy[0].copy()
            messages_copy[0]["content"] += tool_text
            logger.info("Injected tool descriptions into system prompt for text-based tool calling")

        return messages_copy

    def parse_tool_calls_from_text(self, content: str) -> List[tuple[str, Dict[str, Any]]]:
        """
        Parse tool calls from plain-text LLM responses for agents that lack native function-calling support.

        The method scans the supplied `content` string for several known patterns that represent
        tool invocations and extracts a list of tuples containing the tool name and its argument
        dictionary.

        Supported patterns include:

        * `:functions.<tool_name>` followed by `<constraint>:json:<message>{...}`
        * A block starting with `Tool: <tool_name>` on one line and a JSON object on the next
          line.
        * Direct function-call syntax such as `<tool_name>({ ... })`.

        Only tools declared in `self.agent_def["tools"]` are considered valid; any matches for
        unknown tool names are ignored.

        If the input is `None` or empty, an empty list is returned. Errors while decoding JSON
        for a detected tool are logged and that particular entry is skipped.

        Args:
            content: The raw text output from the LLM (may be `None` or an empty string).

        Returns:
            A list of `(tool_name, arguments)` tuples where `tool_name` is a string matching one
            of the agent's registered tools and `arguments` is a dictionary parsed from the JSON
            payload associated with that tool. The list may be empty if no valid tool calls are
            found.
        """
        # Handle None or empty content
        if content is None or not content:
            return []

        if not self.agent_def or "tools" not in self.agent_def:
            return []

        tool_calls = []
        known_tools = [tool["name"] for tool in self.agent_def["tools"]]

        # Pattern 1: <|start|>assistant|>|commentary|>:functions.tool_name
        # Followed by <constraint>:json:<message>{...}
        pattern1 = r":functions\.(\w+)"
        json_pattern = r"<constraint>:json:<message>(\{[^}]+\})"

        tool_matches = re.findall(pattern1, content)
        json_matches = re.findall(json_pattern, content)

        if tool_matches and json_matches:
            for tool_name, json_str in zip(tool_matches, json_matches):
                if tool_name in known_tools:
                    try:
                        arguments = json.loads(json_str)
                        tool_calls.append((tool_name, arguments))
                        logger.info(f"Parsed tool call from text: {tool_name}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON for {tool_name}: {sanitize_log_message(str(e))}")

        # Pattern 2: Simple JSON blocks with tool name
        # Tool: register_graph_node
        # {"label": "...", ...}
        pattern2 = r"Tool:\s*(\w+)\s*\n\s*(\{[^}]+\})"
        matches2 = re.findall(pattern2, content, re.DOTALL)

        for tool_name, json_str in matches2:
            if tool_name in known_tools:
                try:
                    arguments = json.loads(json_str)
                    tool_calls.append((tool_name, arguments))
                    logger.info(f"Parsed tool call from text (pattern 2): {tool_name}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for {tool_name}: {sanitize_log_message(str(e))}")

        # Pattern 3: Function call syntax
        # register_graph_node({"label": "...", ...})
        pattern3 = r"(\w+)\(\s*(\{[^}]+\})\s*\)"
        matches3 = re.findall(pattern3, content)

        for tool_name, json_str in matches3:
            if tool_name in known_tools:
                try:
                    arguments = json.loads(json_str)
                    tool_calls.append((tool_name, arguments))
                    logger.info(f"Parsed tool call from text (pattern 3): {tool_name}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for {tool_name}: {sanitize_log_message(str(e))}")

        return tool_calls

    def build_loop_summary(
        self,
        loop_num: int,
        tools_executed: List[tuple[str, Dict[str, Any], Dict[str, Any]]],
        events_seen: List[Dict[str, Any]],
    ) -> str:
        """
        Builds a concise textual summary of the activities performed during a single processing loop.

        Parameters
        ----------
        loop_num : int
            The sequential number of the current loop.
        tools_executed : list[tuple[str, dict[str, Any], dict[str, Any]]]
            A collection of tuples describing each tool invocation in the loop. Each tuple contains:
                * `tool_name` - the identifier of the tool that was run,
                * `arguments` - a dictionary of arguments passed to the tool,
                * `result` - the dictionary returned by the tool, which may include identifiers for created nodes or edges and counts of discovered events.
        events_seen : list[dict[str, Any]]
            A list of event dictionaries that were examined in this loop. Each dictionary may contain an `event_type` key among other metadata.

        Returns
        -------
        str
            A formatted multi-section summary string that includes:
                * Loop header,
                * Number and breakdown of tools executed,
                * Highlights of recently created nodes, edges, and any events found,
                * Count and top types of events analyzed,
                * Cumulative statistics drawn from `self.stats` (total events analyzed, nodes created, edges created).
        """
        summary_parts = [f"\n## Loop {loop_num} Summary\n"]

        if tools_executed:
            summary_parts.append(f"**Tools executed**: {len(tools_executed):,}\n")

            # Group by tool type
            tool_counts = {}
            for tool_name, _, _ in tools_executed:
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

            for tool_name, count in tool_counts.items():
                summary_parts.append(f"  - {tool_name}: {count}x\n")

            # Highlight important results
            nodes_created = []
            edges_created = []
            events_found = 0

            for tool_name, args, result in tools_executed:
                if "node_id" in result:
                    nodes_created.append(
                        f"Node {result['node_id']}: {result.get('label', 'unknown')}"
                    )
                elif "edge_id" in result:
                    edges_created.append(
                        f"Edge {result['edge_id']}: {result.get('relationship', 'unknown')}"
                    )
                elif "count" in result and result["count"] > 0:
                    events_found += result["count"]

            if nodes_created:
                summary_parts.append("\n**Nodes created**:\n")
                for node_desc in nodes_created[-5:]:  # Show last 5
                    summary_parts.append(f"  - {node_desc}\n")

            if edges_created:
                summary_parts.append("\n**Edges created**:\n")
                for edge_desc in edges_created[-5:]:  # Show last 5
                    summary_parts.append(f"  - {edge_desc}\n")

            if events_found > 0:
                summary_parts.append(f"\n**Events found**: {events_found:,}\n")

        if events_seen:
            summary_parts.append(f"\n**Events analyzed**: {len(events_seen):,}\n")

            # Summarize event types
            event_types = {}
            for event in events_seen:
                event_type = event.get("event_type", "unknown")
                event_types[event_type] = event_types.get(event_type, 0) + 1

            for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True)[
                :5
            ]:
                summary_parts.append(f"  - {event_type}: {count}\n")

        summary_parts.append(
            f"\n**Cumulative stats**: {self.stats['events_analyzed']} events, "
            f"{self.stats['nodes_created']} nodes, "
            f"{self.stats['edges_created']} edges\n"
        )

        return "".join(summary_parts)

    async def _compact_conversation_with_llm(
        self,
        messages_to_compact: List[Dict[str, Any]],
        user_query: str,
    ) -> str:
        """
        Use an LLM to intelligently compact a list of conversation messages into a concise markdown summary relevant to a specific user query.

        Args:
            messages_to_compact (List[Dict[str, Any]]): A sequence of message dictionaries representing the dialogue history to be summarized. Each dictionary should contain at least a `role` key (e.g., "user", "assistant", "tool", or "system") and a `content` key with the textual payload. Tool call messages may also include a `tool_calls` field.
            user_query (str): The original question posed by the user, used to focus the summary on relevant information.

        Returns:
            str: A markdown-formatted summary that preserves technical details while reducing token count. The summary is crafted for downstream consumption by the agent rather than end-user presentation.

        Raises:
            Exception: Any exception raised during the LLM call or processing is caught internally; the function falls back to a deterministic summarization routine and returns its result instead of propagating the error.
        """
        # Build conversation transcript for summarization
        transcript_parts = []

        for msg in messages_to_compact:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                transcript_parts.append(f"## Question\n{content}\n")
            elif role == "assistant":
                # Check if this is a tool call or text response
                if "tool_calls" in msg:
                    tool_names = [tc["function"]["name"] for tc in msg.get("tool_calls", [])]
                    transcript_parts.append(
                        f"## Agent Action\nCalled tools: {', '.join(tool_names)}\n"
                    )
                elif content:
                    transcript_parts.append(f"## Agent Analysis\n{content}\n")
            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                # Truncate large tool results
                if len(content) > 2000:
                    content = content[:2000] + "\n... (truncated)"
                transcript_parts.append(f"## Tool Result: {tool_name}\n{content}\n")
            elif role == "system" and "Loop" in content:
                # This is a loop summary
                transcript_parts.append(f"{content}\n")

        transcript = "\n".join(transcript_parts)

        # Build compaction prompt
        compaction_prompt = f"""# Instructions and Task:
- Your **role** is to assume the role of a senior forensic analyst.
- Your **task** is to examine the evidence collected along with the Investigation Goals directed by your supervising Agent.
- You will summarize and compact the discoveries while still keeping the technical details intact and accurate.
- The summary should only contain content relevant to the query `{user_query}`, evidence that doesn't align with this category should be disregarded.

This is your memory compaction routine. Summarize the questions you've asked and the answers you received so that the investigation's momentum and relevance are preserved.

**Output Format**
Markdown formatted paragraphs (**no** leading/trailing ticks ```, or titles) and lists that are technical, clear and easily understandable by an Agent.
You are not speaking to a user, you are generating clear, technically correct data for later use by yourself.
Summarize each Question and Answer (while still retaining accurate technical detail) so that you may continue conducting a coherent investigation.
This step is critical, losing control of your investigation due to omission is a very real danger, so be verbose in your summaries.

**Investigation Transcript to Summarize:**

{transcript}

**Your Summary:**"""

        # Call LLM for compaction (use higher temperature for more natural summarization)
        compaction_messages = [
            {
                "role": "system",
                "content": "You are a forensic analyst assistant that creates detailed, technical investigation summaries.",
            },
            {"role": "user", "content": compaction_prompt},
        ]

        try:
            logger.info("Calling LLM to compact conversation history...")

            # Use centralized service for compaction
            result = await self._llm_service.call_llm(
                messages=compaction_messages,
                max_tokens=16_384,
                temperature=self.llm_temperature,
                enforce_context_limit=False,  # Compaction messages are already minimal
            )

            # Extract summary
            summary = result["choices"][0]["message"].get("content", "")

            if not summary:
                logger.warning("Empty summary from LLM, using fallback")
                return self._fallback_compaction(messages_to_compact)

            summary_tokens = estimate_tokens(summary)
            original_tokens = sum(
                estimate_tokens(json.dumps(msg, default=str)) for msg in messages_to_compact
            )

            logger.info(
                f"Compacted {len(messages_to_compact):,} messages "
                f"from {original_tokens:,} to {summary_tokens:,} tokens "
                f"(saved {original_tokens - summary_tokens:,} tokens, {(1 - summary_tokens/original_tokens)*100:.1f}% reduction)"
            )

            return summary

        except Exception as e:
            logger.error(f"Failed to compact with LLM: {sanitize_log_message(str(e))}", exc_info=True)
            return self._fallback_compaction(messages_to_compact)

    def _fallback_compaction(self, messages: List[Dict[str, Any]]) -> str:
        """
        Compact and summarize investigation messages when LLM summarization fails.

        Parameters
        ----------
        messages : List[Dict[str, Any]]
            A list of message dictionaries representing the conversation history to be compacted.

        Returns
        -------
        str
            A plain-text summary containing key statistics (loops executed, events analyzed, graph nodes/edges created) and, if applicable, a short list of the most frequently used tools. The summary also includes a note indicating that detailed history was omitted to conserve context space.
        """
        summary_parts = [
            "## Investigation Progress (Compacted)\n",
            f"**Loops executed**: {self.stats['loops_executed']}\n",
            f"**Events analyzed**: {self.stats['events_analyzed']}\n",
            f"**Graph nodes created**: {self.stats['nodes_created']}\n",
            f"**Graph edges created**: {self.stats['edges_created']}\n",
        ]

        if self.stats["tools_called"]:
            summary_parts.append("\n**Tools used**:\n")
            for tool, count in sorted(
                self.stats["tools_called"].items(), key=lambda x: x[1], reverse=True
            )[:5]:
                summary_parts.append(f"- {tool}: {count}x\n")

        summary_parts.append(
            "\n*Note: Detailed investigation history was compacted to save context space.*\n"
        )

        return "".join(summary_parts)

    async def rebuild_messages_with_summary(
        self,
        system_message: Dict[str, Any],
        user_question: Dict[str, Any],
        loop_summaries: List[str],
        recent_exchanges: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Rebuilds the message list for an LLM request by incorporating system prompts, the original user question, loop summaries, and recent exchanges, while ensuring the total token count stays within the configured compaction threshold.

        If the assembled messages exceed the threshold, the method invokes an LLM-based compaction routine to generate a concise summary that preserves investigation context. The generated summary replaces the detailed loop summaries and recent exchanges, and the internal collections are cleared accordingly.

        Args:
            system_message (Dict[str, Any]): The immutable system prompt that should always appear at the start of the conversation.
            user_question (Dict[str, Any]): The original user query message; its content may be used as a fallback when extracting the question for compaction.
            loop_summaries (List[str]): A list of textual summaries from previous investigation loops. This list is mutated in-place-cleared if LLM compaction occurs.
            recent_exchanges (List[Dict[str, Any]]): The most recent message exchanges that provide immediate context. Also cleared in-place when a compacted summary replaces them.

        Returns:
            List[Dict[str, Any]]: A reordered list of messages ready to be sent to the language model, containing the system prompt, either the original loop summaries and recent exchanges or a single LLM-generated summary, followed by any remaining context needed for the next step.
        """
        # Build initial messages
        messages = [system_message, user_question]

        # Add consolidated summary of all loops
        if loop_summaries:
            consolidated_summary = "\n".join(
                [
                    "[Previous investigation loops summary]",
                    *loop_summaries,
                    f"\nTotal loops completed: {len(loop_summaries):,}",
                    f"Continue investigation with remaining loops.",
                ]
            )

            messages.append({"role": "system", "content": consolidated_summary})

        # Add recent exchanges for context
        messages.extend(recent_exchanges)

        # Check total token count
        total_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in messages)

        # Log initial context composition
        logger.debug(
            f"rebuild_messages_with_summary: {total_tokens} tokens "
            f"(system+question + {len(loop_summaries):,} summaries + {len(recent_exchanges):,} exchanges)"
        )

        # If over compaction threshold, use LLM to intelligently compact
        if total_tokens > self.compaction_threshold:
            logger.warning(
                f"WARNING: Context too large ({total_tokens} tokens > {self.compaction_threshold} threshold), "
                f"invoking LLM-based compaction"
            )

            # Collect all messages except system prompt for compaction
            messages_to_compact = []

            # Add user question
            messages_to_compact.append(user_question)

            # Add loop summaries as system messages
            for summary in loop_summaries:
                messages_to_compact.append({"role": "system", "content": summary})

            # Add recent exchanges
            messages_to_compact.extend(recent_exchanges)

            # Extract user query from user_question
            user_query = user_question.get("content", self.question)

            # Get LLM-generated summary
            compacted_summary = await self._compact_conversation_with_llm(
                messages_to_compact, user_query
            )

            # Clear loop summaries and exchanges (they're now in the compacted summary)
            loop_summaries.clear()
            recent_exchanges.clear()

            # Rebuild messages with compacted summary
            messages = [
                system_message,
                {
                    "role": "system",
                    "content": f"## Investigation Progress Summary\n\n{compacted_summary}\n\n**Continue your investigation.**",
                },
            ]

            # Check new token count
            new_total_tokens = sum(
                estimate_tokens(json.dumps(msg, default=str)) for msg in messages
            )
            logger.info(
                f"After LLM compaction: {new_total_tokens} tokens "
                f"(saved {total_tokens - new_total_tokens} tokens, {(1 - new_total_tokens/total_tokens)*100:.1f}% reduction)"
            )

        return messages


__all__ = ["BaseAgent", "estimate_tokens"]
