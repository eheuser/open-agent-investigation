import json
from typing import Any, Dict, List, Optional, Tuple

from ..utils.log_setup import get_logger
from ..utils.security import sanitize_log_message

logger = get_logger(__name__)

# Token estimation constant
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in *text* based on an average characters-per-token ratio.

    Args:
        text (str): The input string whose token count is to be estimated.

    Returns:
        int: Approximate token count calculated as `len(text) // CHARS_PER_TOKEN`.
    """
    return len(text) // CHARS_PER_TOKEN


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    Estimate the total number of tokens required for a list of chat messages.

    Args:
        messages (List[Dict[str, Any]]): A sequence of message dictionaries, where each dictionary represents a single chat entry (e.g., containing role and content fields). The function will serialize each dictionary to JSON before estimating its token count.

    Returns:
        int: The sum of the estimated token counts for all provided messages. This value approximates the number of tokens that would be consumed if the messages were sent to an LLM.
    """
    total = 0
    for msg in messages:
        msg_json = json.dumps(msg, default=str)
        total += estimate_tokens(msg_json)
    return total


class ChatContextManager:
    """Context manager for chat router (intent classification)."""

    @staticmethod
    def prepare_classification_context(
        system_prompt: str,
        user_query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        max_history_messages: int = 5,
    ) -> List[Dict[str, str]]:
        """
        Prepare a message list for intent classification by combining a system prompt with a formatted user prompt that includes recent conversation history.

        Args:
            system_prompt: The system-level instruction guiding the classifier.
            user_query: The current query from the user to be classified.
            chat_history: An optional list of prior messages, each a dict with `role` and `content` keys. If omitted or empty, a placeholder indicating no previous conversation is used.
            max_history_messages: The maximum number of most recent messages from `chat_history` to include in the context (default is 5). Only the last `max_history_messages` entries are considered.

        Returns:
            A list of two dictionaries suitable for LLM input:
                * `{"role": "system", "content": system_prompt}`
                * `{"role": "user", "content": user_prompt}`

        The `user_prompt` contains a “Conversation History” section followed by the current query and an instruction to classify it based on the provided context.
        """
        # Format chat history
        if chat_history:
            history_text = "\n".join(
                [
                    f"{msg['role'].upper()}: {msg['content']}"
                    for msg in chat_history[-max_history_messages:]
                ]
            )
        else:
            history_text = "(No previous conversation)"

        # Build user prompt with history
        user_prompt = f"""## Conversation History

{history_text}

## Current User Query

{user_query}

---

Classify the current user query based on the conversation context above."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]


class TimelineContextManager:
    """Context manager for timeline handler (multi-turn tool execution)."""

    @staticmethod
    def prepare_initial_context(
        user_query: str,
        max_tokens: int = 2000,
    ) -> List[Dict[str, str]]:
        """
        Prepare the initial message list for a timeline-based interaction with a language model.

        Args:
            user_query: The raw query supplied by the user describing the timeline request.
            max_tokens: The maximum number of tokens allowed for the entire context (default 2000). If the combined token count of the system prompt and the user query exceeds this limit, the user query will be truncated to fit within the budget.

        Returns:
            A list of message dictionaries suitable for passing to an LLM API. The first entry is a `system` message containing the timeline assistant prompt; the second entry is a `user` message with the (potentially truncated) query.
        """
        system_prompt = """You are a timeline assistant. Use the available timeline tools to answer the user's question.

IMPORTANT: When searching for timeline entries:
- Use search_text parameter for keyword searches (e.g., "powershell", "suspicious", "malware")
- Do NOT filter by entry_type unless the user specifically mentions it
- Most queries should use ONLY search_text, not entry_type

After using tools, provide a clear, concise answer based on the results."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ]

        # Enforce token limit
        current_tokens = estimate_messages_tokens(messages)
        if current_tokens > max_tokens:
            # Truncate user query if needed
            truncated_query = user_query[: max_tokens * CHARS_PER_TOKEN // 2]
            messages[1]["content"] = truncated_query
            logger.warning(
                f"Timeline query truncated: {len(user_query):,} → {len(truncated_query):,} chars"
            )

        return messages

    @staticmethod
    def add_tool_result(
        messages: List[Dict[str, Any]],
        assistant_message: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
        max_tokens: int = 8000,
    ) -> List[Dict[str, Any]]:
        """
        Add tool execution results to a chat context while respecting a token limit.

        This function appends the assistant's message and each tool result to the existing list of messages, then checks whether the total token count exceeds `max_tokens`. If the limit is exceeded, the context is trimmed to retain only the system prompt, the original user query, and the most recent five messages. The trimming operation logs the reduction in message count and tokens removed.

        Args:
            messages: A mutable list of message dictionaries representing the current conversation history.
            assistant_message: The assistant's message dictionary that includes any tool calls made during the turn.
            tool_results: A list of dictionaries, each containing a `tool_call_id` and `content` produced by executed tools.
            max_tokens: The maximum allowed token count for the combined messages (default is 8000).

        Returns:
            A new or modified list of message dictionaries that fits within the specified token budget. If trimming was necessary, the returned list contains the system prompt, the original user query, and the last five messages; otherwise, it includes all original messages plus the newly added ones.
        """
        # Add assistant message
        messages.append(assistant_message)

        # Add tool results
        for result in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": json.dumps(result["content"]),
                }
            )

        # Check token limit
        current_tokens = estimate_messages_tokens(messages)
        if current_tokens > max_tokens:
            # Keep system, user query, and recent messages
            trimmed = [
                messages[0],  # System
                messages[1],  # User query
            ] + messages[
                -5:
            ]  # Last 5 messages

            tokens_removed = current_tokens - estimate_messages_tokens(trimmed)
            logger.info(
                f"Timeline context trimmed: {len(messages):,} → {len(trimmed):,} messages, "
                f"{tokens_removed:,} tokens removed"
            )
            return trimmed

        return messages


class GeneralChatContextManager:
    """Context manager for general chat (single-turn Q&A)."""

    @staticmethod
    def prepare_context(
        investigation_context: Dict[str, Any],
        user_query: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Prepare a prompt string for a general-purpose investigation assistant chat.

        The function assembles a multi-section prompt that includes a brief system instruction, details extracted from the provided `investigation_context` (such as investigation metadata, timeline summary, artifact counts, and event statistics), and the user's question.  The resulting prompt is intended to be sent to a language model that will answer concisely based on the supplied context.

        If the assembled prompt exceeds `max_tokens` (as estimated by :func:`estimate_tokens`), the function falls back to a minimal version containing only the most essential information (title, timeline entry count, and the user question) and logs a warning.

        Args:
            investigation_context: Mapping containing optional keys `"investigation"`, `"timeline"`, `"artifacts"`, and `"events"`.  Each sub-mapping holds metadata used to populate the context sections.
            user_query: The question posed by the user that the assistant must answer.
            max_tokens: Upper bound on the number of tokens allowed for the final prompt.  Defaults to 2000.

        Returns:
            A single string representing the complete prompt, ready for consumption by a language model.
        """
        prompt_parts = [
            "You are an investigation assistant. Answer the user's question based on the context provided.",
            "",
            "# Investigation Context",
            "",
        ]

        # Investigation info
        if "investigation" in investigation_context:
            inv = investigation_context["investigation"]
            prompt_parts.append(f"**Title:** {inv.get('title', 'Untitled')}")
            if inv.get("description"):
                prompt_parts.append(f"**Description:** {inv['description']}")
            prompt_parts.append(f"**Created:** {inv.get('created_at', 'Unknown')}")
            prompt_parts.append("")

        # Timeline info
        if "timeline" in investigation_context:
            tl = investigation_context["timeline"]
            prompt_parts.append(f"**Timeline Entries:** {tl.get('total_entries', 0)}")
            if tl.get("earliest") and tl.get("latest"):
                prompt_parts.append(f"**Time Range:** {tl['earliest']} to {tl['latest']}")
            prompt_parts.append("")

        # Artifacts
        if "artifacts" in investigation_context and investigation_context["artifacts"]:
            prompt_parts.append("**Available Artifacts:**")
            for artifact_type, count in investigation_context["artifacts"].items():
                prompt_parts.append(f"  - {artifact_type}: {count} files")
            prompt_parts.append("")

        # Events
        if "events" in investigation_context and investigation_context["events"]:
            total_events = sum(investigation_context["events"].values())
            prompt_parts.append(f"**Total Events:** {total_events}")
            prompt_parts.append("**Event Types:**")
            for event_type, count in list(investigation_context["events"].items())[:10]:
                prompt_parts.append(f"  - {event_type}: {count}")
            prompt_parts.append("")

        prompt_parts.extend(
            [
                "# User Question",
                "",
                user_query,
                "",
                "Provide a helpful, concise answer based on the context above. If the question requires searching events or executing tools, suggest using the agent instead.",
            ]
        )

        prompt = "\n".join(prompt_parts)

        # Enforce token limit
        if estimate_tokens(prompt) > max_tokens:
            # Truncate context sections
            prompt_parts = [
                "You are an investigation assistant. Answer the user's question based on the context provided.",
                "",
                "# Investigation Context",
                "",
                f"**Title:** {investigation_context.get('investigation', {}).get('title', 'Unknown')}",
                f"**Timeline Entries:** {investigation_context.get('timeline', {}).get('total_entries', 0)}",
                "",
                "# User Question",
                "",
                user_query,
                "",
                "Provide a helpful, concise answer.",
            ]
            prompt = "\n".join(prompt_parts)
            logger.warning(f"General chat context truncated to fit {max_tokens} token limit")

        return prompt


class RAGContextManager:
    """Context manager for RAG handler (single-turn with retrieved context)."""

    @staticmethod
    def prepare_context(
        investigation_title: str,
        user_query: str,
        retrieved_chunks: List[Dict[str, Any]],
        max_tokens: int = 16000,
    ) -> Tuple[str, str]:
        """
        Prepare system and user prompts for retrieval-augmented generation (RAG).

        Constructs a system prompt that includes the investigation title and formatted
        retrieved context chunks, then verifies that the combined token count of the
        system prompt and the user's query does not exceed `max_tokens`. If the limit
        is exceeded, the function reduces the number of chunks (and truncates their
        text) before rebuilding the prompt.

        Parameters
        ----------
        investigation_title: str
            Title of the investigation to be referenced in the system prompt.
        user_query: str
            The question or request submitted by the user.
        retrieved_chunks: List[Dict[str, Any]]
            A list of dictionaries representing retrieved context pieces. Each dict
            should contain at least `'text'` (the chunk content) and optionally
            `'owner_type'` to identify the source type.
        max_tokens: int, optional
            Maximum allowed token count for the combined system prompt and user query.
            Defaults to 16000.

        Returns
        -------
        Tuple[str, str]
            A tuple containing:
            * `system_prompt` - The constructed system message with investigation
              details, context excerpts, and usage instructions.
            * `user_query` - The original user question (unchanged).

        Notes
        -----
        The function logs a warning when the initial prompt exceeds `max_tokens` and
        automatically halves the number of chunks, truncating each to 500 characters.
        If further reduction is needed, callers should adjust `max_tokens` or supply
        fewer/shorter chunks.
        """
        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            context_parts.append(f"[Source {i} - {chunk.get('owner_type', 'unknown')}]")
            context_parts.append(chunk.get("text", ""))
            context_parts.append("")  # Blank line

        context_text = "\n".join(context_parts)

        # Build system prompt
        system_prompt = f"""You are a forensic analysis assistant. Answer the user's question based on the retrieved context from the investigation.

Investigation: {investigation_title}

Retrieved Context:
{context_text}

Instructions:
- Answer based ONLY on the provided context
- If the context doesn't contain enough information, say so
- Cite sources by number (e.g., "According to Source 1...")
- Be concise and factual
"""

        # Check token limit
        current_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_query)

        if current_tokens > max_tokens:
            # Reduce number of chunks
            max_chunks = len(retrieved_chunks) // 2
            logger.warning(
                f"RAG context exceeds {max_tokens:,} tokens, reducing chunks: "
                f"{len(retrieved_chunks):,} → {max_chunks:,}"
            )

            # Rebuild with fewer chunks
            context_parts = []
            for i, chunk in enumerate(retrieved_chunks[:max_chunks], 1):
                context_parts.append(f"[Source {i} - {chunk.get('owner_type', 'unknown')}]")
                # Truncate chunk text
                text = chunk.get("text", "")[:500]
                context_parts.append(text)
                context_parts.append("")

            context_text = "\n".join(context_parts)

            system_prompt = f"""You are a forensic analysis assistant. Answer the user's question based on the retrieved context from the investigation.

Investigation: {investigation_title}

Retrieved Context (truncated):
{context_text}

Instructions:
- Answer based ONLY on the provided context
- If the context doesn't contain enough information, say so
- Cite sources by number (e.g., "According to Source 1...")
- Be concise and factual
"""

        return system_prompt, user_query


class AgentContextManager:
    """Context manager for agents (multi-turn investigation with summarization)."""

    @staticmethod
    def prepare_initial_context(
        system_prompt: str,
        user_question: str,
    ) -> List[Dict[str, str]]:
        """
        Prepare the initial message list for an agent interaction.

        Args:
            system_prompt (str): The system prompt defining the agent's behavior and context.
            user_question (str): The user's initial question or request.

        Returns:
            List[Dict[str, str]]: A list containing two messages-first a `system` role with the provided system prompt,
            followed by a `user` role with the user's question.
        """
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question},
        ]

    @staticmethod
    def should_compact(
        messages: List[Dict[str, Any]],
        max_context_tokens: int,
        threshold_pct: float = 0.8,
    ) -> bool:
        """
        Check whether the accumulated token count of the supplied message list exceeds a fraction of the allowed context size.

        Parameters
        ----------
        messages : List[Dict[str, Any]]
            The sequence of chat messages whose tokens are to be counted.
        max_context_tokens : int
            The hard limit on the number of tokens that may be kept in context.
        threshold_pct : float, optional
            Fraction of `max_context_tokens` at which compaction should be triggered; must be between 0.0 and 1.0. Default is 0.8.

        Returns
        -------
        bool
            `True` if the total token count of `messages` exceeds `max_context_tokens * threshold_pct`, indicating that the context should be compacted; otherwise `False`.
        """
        current_tokens = estimate_messages_tokens(messages)
        threshold = int(max_context_tokens * threshold_pct)

        return current_tokens > threshold

    @staticmethod
    def trim_from_middle(
        messages: List[Dict[str, Any]],
        max_tokens: int,
        preserve_system: bool = True,
        preserve_recent: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Trim messages from the middle of a conversation when token limits are exceeded.

        This fallback strategy removes older messages while preserving essential context:
        the system message (if present and requested) and a configurable number of the most recent
        messages. It is used when summarization or other reduction methods fail to bring the total
        token count within `max_tokens`.

        Args:
            messages: A list of message dictionaries, each containing at least a `role` key and
                content that contributes to token usage.
            max_tokens: The maximum allowed number of tokens for the resulting message list.
            preserve_system: If `True` and the first message has the role `"system"`, that
                message is always retained in the output.
            preserve_recent: The number of most recent messages to keep unchanged at the end of
                the list. These are taken from the tail of `messages`.

        Returns:
            A new list of messages trimmed to include only the preserved system message (if any)
            and the specified number of recent messages. The total token count of this list will be
            less than or equal to `max_tokens` when possible; otherwise it contains the minimal
            set defined by the preservation rules.

        Notes:
            - If the original `messages` already fit within `max_tokens`, the function returns
              the input list unchanged.
            - The function logs an informational message indicating how many messages were removed
              and the token count before and after trimming.
        """
        current_tokens = estimate_messages_tokens(messages)

        if current_tokens <= max_tokens:
            return messages

        # Keep system + recent messages
        if preserve_system and messages and messages[0].get("role") == "system":
            trimmed = [messages[0]] + messages[-preserve_recent:]
        else:
            trimmed = messages[-preserve_recent:]

        logger.info(
            f"Trimmed from middle: {len(messages):,} → {len(trimmed):,} messages, "
            f"{current_tokens} → {estimate_messages_tokens(trimmed):,} tokens"
        )

        return trimmed


__all__ = [
    "estimate_tokens",
    "estimate_messages_tokens",
    "ChatContextManager",
    "TimelineContextManager",
    "GeneralChatContextManager",
    "RAGContextManager",
    "AgentContextManager",
]
