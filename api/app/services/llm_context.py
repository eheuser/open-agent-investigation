import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from ..crud import chat_history as crud
from ..crud.llm_config import get_active_llm_config

logger = logging.getLogger(__name__)

# Token budget configuration
MAX_CONTEXT_PERCENT = 0.85  # Use at most 85% of model's max context
DEFAULT_MAX_TOKENS = 8192
CHARS_PER_TOKEN_ESTIMATE = 4  # Conservative estimate for token counting


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a given string using a simple character-based heuristic.

    This lightweight implementation divides the length of the input text by a constant
    (`CHARS_PER_TOKEN_ESTIMATE`) to approximate token usage. It is intended for quick,
    non-critical calculations; for production scenarios where precise token counts are
    required, consider integrating a dedicated tokenizer such as *tiktoken*.

    Args:
        text: The string whose tokens are to be estimated.

    Returns:
        An integer representing the estimated number of tokens in `text`. Returns 0
        when `text` is empty or falsy.
    """
    if not text:
        return 0
    return len(text) // CHARS_PER_TOKEN_ESTIMATE


def message_to_openai_format(msg: Any) -> Dict[str, Any]:
    """
    Convert a ChatMessage-like object into the dictionary format expected by OpenAI's chat API.

    Args:
        msg: An object representing a chat message. It must have at least a `role` attribute and may optionally provide `content`, `name`, `tool_calls`, and `tool_call_id` attributes.

    Returns:
        dict: A dictionary containing the `role` key and any of the optional keys (`content`, `name`, `tool_calls`, `tool_call_id`) that were present on the input object. The resulting structure conforms to OpenAI's message schema.
    """
    result: Dict[str, Any] = {"role": msg.role}

    if msg.content is not None:
        result["content"] = msg.content

    if msg.name is not None:
        result["name"] = msg.name

    if msg.tool_calls is not None:
        result["tool_calls"] = msg.tool_calls

    if msg.tool_call_id is not None:
        result["tool_call_id"] = msg.tool_call_id

    return result


async def build_context(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    system_prompt: str,
    mode: str = "general",
    additional_context: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build a token-aware conversation context for an LLM.

    Constructs a list of messages in the OpenAI chat format that fits within a configurable
    portion of the model’s maximum context length. The function retrieves the user’s active
    LLM configuration to determine the overall token limit, reserves a percentage of that
    limit as a budget, and then sequentially adds:

    * The primary system prompt.
    * Optional additional context (e.g., timeline entries) if it fits within the remaining
      budget.
    * Recent investigation messages from the database, ordered from oldest to newest,
      stopping when adding another message would exceed the token budget.

    The resulting list can be passed directly to an OpenAI chat completion request.

    Parameters
    ----------
    db: AsyncSession
        An active asynchronous SQLAlchemy session used for all database queries.
    investigation_id: UUID
        The identifier of the investigation whose messages should be included in the context.
    user_id: int
        Identifier of the user; used to look up the user's LLM configuration (max token limit).
    system_prompt: str
        The main system-level prompt that primes the model's behavior.
    mode: str, optional
        A string indicating the context mode (e.g., `"general"`, `"timeline"`,
        `"event"`, or `"agent_seed"`). Currently only influences logging; future
        extensions may adjust token budgeting based on mode. Defaults to `"general"`.
    additional_context: str | None, optional
        Extra system-level content to prepend after the primary system prompt (for example,
        a timeline summary). It is included only if it does not cause the token budget to be
        exceeded.

    Returns
    -------
    list[dict[str, Any]]
        A list of message dictionaries compatible with OpenAI’s chat API. Each dictionary
        contains `"role"` (`"system"`, `"user"`, or `"assistant"`) and `"content"`
        keys. The list respects the calculated token budget.

    Raises
    ------
    RuntimeError
        If the user’s LLM configuration cannot be retrieved and a default token limit is not
        defined.
    Any exception raised by the underlying database calls (e.g., connection errors) will
    propagate to the caller.
    """
    # Get user's LLM config for max token limit
    llm_config = await get_active_llm_config(db, user_id)

    # Extract max_context_length safely
    # SQLAlchemy returns actual int values at runtime, not Column objects
    if llm_config is not None:
        # Use getattr to get the actual value and satisfy type checker
        context_length = getattr(llm_config, "max_context_length", None)
        max_tokens = int(context_length) if context_length else DEFAULT_MAX_TOKENS
    else:
        max_tokens = DEFAULT_MAX_TOKENS

    # Calculate token budget
    token_budget = int(max_tokens * MAX_CONTEXT_PERCENT)

    # Start with system prompt
    context: List[Dict[str, Any]] = []
    tokens_used = 0

    # Add system prompt
    system_tokens = estimate_tokens(system_prompt)
    context.append({"role": "system", "content": system_prompt})
    tokens_used += system_tokens

    # Add additional context if provided (e.g., timeline entries for timeline mode)
    if additional_context:
        additional_tokens = estimate_tokens(additional_context)
        if tokens_used + additional_tokens < token_budget:
            context.append({"role": "system", "content": additional_context})
            tokens_used += additional_tokens

    # Get messages from database (most recent first for truncation)
    messages = await crud.get_investigation_messages(
        db=db,
        investigation_id=investigation_id,
        include_in_llm_only=True,
        include_deleted=False,
    )

    # Build context from messages (newest to oldest, then reverse)
    message_context: List[Dict[str, Any]] = []
    for msg in reversed(messages):
        openai_msg = message_to_openai_format(msg)
        msg_tokens = estimate_tokens(openai_msg.get("content") or "")

        if tokens_used + msg_tokens > token_budget:
            logger.debug(f"Token budget exceeded, stopping at {len(message_context)} messages")
            break

        message_context.insert(0, openai_msg)
        tokens_used += msg_tokens

    # Combine: system prompt(s) + messages
    context.extend(message_context)

    logger.info(
        f"Built context for {investigation_id}: "
        f"{len(context)} messages, ~{tokens_used} tokens "
        f"(budget: {token_budget}, mode: {mode})"
    )

    return context


async def build_general_context(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
) -> List[Dict[str, Any]]:
    """
    Builds a conversation context for general-purpose chats without any specialized system prompt.

    Args:
        db: An asynchronous SQLAlchemy session used to query stored messages.
        investigation_id: The unique identifier of the investigation whose message history should be included.
        user_id: Identifier of the user requesting the context; used to filter messages authored by this user.

    Returns:
        A list of dictionaries representing messages formatted for OpenAI’s chat completion API. Each dictionary contains a `role` key (e.g., `"system"`, `"user"`, `"assistant"`) and a `content` key with the corresponding text.

    The function constructs a generic system prompt that describes the assistant as a helpful forensic investigation aide, then delegates to :func:`build_context` with the `mode` set to `\"general\"` to assemble the final message list while respecting token budget constraints.
    """
    system_prompt = """You are a helpful forensic investigation assistant. 
You help analysts understand digital forensic evidence and answer questions about investigations.
Be concise, accurate, and focus on actionable insights."""

    return await build_context(
        db=db,
        investigation_id=investigation_id,
        user_id=user_id,
        system_prompt=system_prompt,
        mode="general",
    )


async def build_timeline_context(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    timeline_entries: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build a conversation context for timeline-related queries.

    This function assembles a list of messages formatted for the OpenAI API that includes a
    timeline-aware system prompt and, optionally, pre-formatted timeline entries.  The
    resulting context can be passed directly to a language model call to answer questions
    about an investigation’s chronological events.

    Args:
        db: An asynchronous SQLAlchemy session used to retrieve additional data needed for
            the context.
        investigation_id: The UUID of the investigation whose timeline is being queried.
        user_id: Identifier of the user requesting the context.
        timeline_entries: Optional pre-formatted string containing timeline entries that should
            be injected into the context as additional information.

    Returns:
        A list of dictionaries, each representing a message in the OpenAI chat format
        (e.g., `{'role': 'system', 'content': ...}`).  The list includes the system prompt,
        any provided timeline entries, and other relevant messages constructed by the
        underlying `build_context` helper.
    """
    system_prompt = """You are a forensic timeline analyst. 
You help investigators understand the sequence of events in an investigation.
Focus on temporal relationships, patterns, and anomalies in the timeline.
When discussing events, always reference their timestamps."""

    return await build_context(
        db=db,
        investigation_id=investigation_id,
        user_id=user_id,
        system_prompt=system_prompt,
        mode="timeline",
        additional_context=timeline_entries,
    )


async def build_agent_seed_context(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    agent_instructions: str,
) -> List[Dict[str, Any]]:
    """
    Builds a conversation context for generating an agent’s initial investigation plan.

    This function assembles a list of messages formatted for OpenAI chat completion calls. It creates a system prompt that defines the role of an autonomous forensic investigation agent, incorporates any agent-specific instructions, and then delegates to `build_context` with the mode set to `"agent_seed"`.

    Args:
        db: An asynchronous SQLAlchemy session used to retrieve relevant data from the database.
        investigation_id: The UUID identifying the investigation for which the context is being built.
        user_id: The identifier of the user requesting the context.
        agent_instructions: A string containing additional instructions that tailor the agent’s behavior.

    Returns:
        A list of dictionaries, each representing a message in OpenAI's chat format (e.g., `{'role': 'system', 'content': ...}`). This list can be passed directly to an OpenAI chat completion request.
    """
    system_prompt = f"""You are an autonomous forensic investigation agent.
Your task is to investigate digital forensic evidence and build a timeline of findings.

{agent_instructions}

Use the available tools to search events, analyze patterns, and register your findings.
Always explain your reasoning before taking actions."""

    return await build_context(
        db=db,
        investigation_id=investigation_id,
        user_id=user_id,
        system_prompt=system_prompt,
        mode="agent_seed",
    )


__all__ = [
    "build_context",
    "build_general_context",
    "build_timeline_context",
    "build_agent_seed_context",
    "estimate_tokens",
    "MAX_CONTEXT_PERCENT",
    "DEFAULT_MAX_TOKENS",
]
