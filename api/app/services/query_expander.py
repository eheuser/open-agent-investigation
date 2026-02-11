from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..crud.chat_history import get_investigation_messages
from .llm_service import LLMService

from ..utils.log_setup import get_logger

logger = get_logger(__name__)


EXPANSION_PROMPT_TEMPLATE = """You are a query expansion assistant. Your job is to take short, curt user queries and expand them into verbose, detailed instructions that include full context from the ongoing investigation.

## CONTEXT AVAILABLE

### Recent Chat History (User/Assistant Conversation)
{chat_history}

### Timeline Context (Evidence Documented)
{graph_summary}

### Investigation Metadata (Available Data)
{investigation_metadata}

## USER'S CURRENT QUERY
{user_query}

## YOUR TASK
Expand the user's query into a detailed, verbose instruction that:
1. **PRESERVES THE USER'S EXACT INTENT** - Don't change what they're asking for
2. **ADDS CONTEXT FROM CHAT HISTORY** - If this is a follow-up question, include what they were previously discussing
3. **REFERENCES SPECIFIC ENTITIES** - Replace pronouns ("this", "that", "it") with specific entities from the conversation
4. **STAYS FOCUSED** - Only include context that's directly relevant to the current query
5. **KEEPS IT CONCISE** - The expanded query should be 2-5 sentences maximum

**CRITICAL RULES**:
- If the query is already detailed (>50 words), return it EXACTLY as-is
- If the query is a NEW topic (not a follow-up), return it as-is with minimal expansion
- Only expand if the query is ambiguous or uses pronouns that need clarification
- DO NOT change the user's requested action or scope
- DO NOT add new requirements that the user didn't ask for
- Use specific names, IDs, timestamps, or values from the chat history when replacing pronouns

**EXAMPLES**:
- User: "show me more" → "Show me more [specific topic from previous message]"
- User: "what about those files?" → "What about the [specific files mentioned in previous exchange]?"
- User: "find similar events" → "Find events similar to [specific event type from previous discussion]"
- User: "search for authentication failures" → Return as-is (already specific)

Respond with ONLY the expanded query, no explanation or preamble.
"""


async def expand_query(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
) -> str:
    """
    Expand a short user query by adding relevant contextual information.

    If the supplied query already contains sufficient detail (more than 30 words) or matches a known simple command, the function returns the original query unchanged. Otherwise it gathers recent chat history, a summary of the timeline state, and investigation metadata, builds an expansion prompt, and invokes the configured LLM for the user to produce a richer query.

    Args:
        db: An active asynchronous SQLAlchemy session used to fetch context data.
        investigation_id: The UUID identifying the current investigation whose context should be included.
        user_query: The original query string supplied by the user.
        user_id: Identifier of the user, used to locate their LLM configuration.

    Returns:
        A string containing the expanded query with added context, or the original `user_query` if no expansion was performed or an error occurred.
    """
    # Skip expansion for already-detailed queries
    word_count = len(user_query.split())
    if word_count > 30:  # Lowered threshold - if they wrote 30+ words, it's detailed enough
        logger.info(f"Query already detailed ({word_count} words), skipping expansion")
        return user_query

    # Skip expansion for very simple commands that don't need context
    simple_commands = [
        "help",
        "status",
        "summary",
        "stats",
        "clear",
        "reset",
        "show graph",
        "show events",
        "list nodes",
        "list edges",
    ]
    if user_query.lower().strip() in simple_commands:
        logger.info(f"Simple command detected, skipping expansion: {user_query}")
        return user_query

    logger.info(f"Expanding query ({word_count} words): {user_query[:100]}...")

    try:
        # Gather context components
        chat_history = await _get_chat_context(db, investigation_id)
        graph_summary = await _get_graph_context(db, investigation_id)
        investigation_metadata = await _get_investigation_context(db, investigation_id)

        # Build expansion prompt
        prompt = EXPANSION_PROMPT_TEMPLATE.format(
            chat_history=chat_history,
            graph_summary=graph_summary,
            investigation_metadata=investigation_metadata,
            user_query=user_query,
        )

        # Call LLM to expand query
        llm_service = await LLMService.from_user_config(db, user_id)

        if not llm_service:
            # No LLM config - return original query
            logger.warning(f"No LLM config for user {user_id}, returning original query")
            return user_query

        # Call LLM via centralized service
        # Use None for max_tokens and temperature to respect user's DB configuration
        data = await llm_service.call_llm(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=None,  # Use user's configured default
            temperature=None,  # Use user's configured temperature
            enforce_context_limit=False,
        )

        # Extract response
        response_text = await llm_service.extract_text_response(data)

        if not response_text:
            logger.warning(f"Empty LLM response, returning original query")
            return user_query

        expanded_query = response_text.strip()

        # Sanity check: don't return absurdly long expansions
        if len(expanded_query) > len(user_query) * 100:
            logger.warning(f"Expansion too long ({len(expanded_query):,} chars), using original")
            return user_query

        logger.info(f"Query expanded: {user_query[:50]}... -> {expanded_query[:100]}...")
        return expanded_query

    except Exception as e:
        logger.error(f"Query expansion failed: {e}", exc_info=True)
        return user_query


async def _get_chat_context(db: AsyncSession, investigation_id: UUID) -> str:
    """
    Retrieve and format recent chat history for a given investigation.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used to query messages.
    investigation_id : UUID
        Identifier of the investigation whose chat history is being fetched.

    Returns
    -------
    str
        A string containing up to the last 10 user-assistant exchanges, each prefixed with the capitalized role (e.g., `User: ...`). Messages longer than 300 characters are truncated with an ellipsis. If no relevant messages exist or an error occurs, a short notice such as `"No previous chat history."` or `"Chat history unavailable."` is returned.

    Notes
    -----
    - The function queries up to 20 recent messages but only includes those with roles `user` or `assistant` in the output.
    - Tool and system messages are omitted from the formatted context.
    """
    try:
        # Get last 20 messages to capture more context
        messages = await get_investigation_messages(
            db,
            investigation_id,
            limit=20,
            visible_in_ui_only=True,
        )

        if not messages:
            return "No previous chat history."

        # Format as conversation, focusing on user/assistant exchanges
        lines = []
        for msg in messages[-20:]:  # Last 20 messages for better context
            role = msg.role.capitalize()
            content = msg.content or ""

            # Skip tool messages and system messages in context
            if msg.role in ["tool", "system"]:
                continue

            # Truncate very long messages but keep more context than before
            if len(content) > 300:
                content = content[:297] + "..."

            lines.append(f"{role}: {content}")

        if not lines:
            return "No previous chat history."

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to get chat context: {e}")
        return "Chat history unavailable."


async def _get_graph_context(db: AsyncSession, investigation_id: UUID) -> str:
    """
    Fetches recent timeline entries for a given investigation and formats them as a human-readable context string.

    Args:
        db: An active `AsyncSession` used to execute the query against the database.
        investigation_id: The UUID of the investigation whose timeline entries should be retrieved.

    Returns:
        A formatted string containing:
            * The total number of recent visible entries (up to 15).
            * A breakdown of entry types and their counts.
            * A bullet list of the five most recent entries with timestamps, titles, and tags.
            * An ellipsis line if more than five entries were retrieved.

    If no entries are found, a short message indicating an empty timeline is returned.
    If any exception occurs while querying or processing the data, a warning is logged and the string `"Timeline context unavailable."` is returned.
    """
    try:
        # Get timeline entries (limit to most recent 15 for context)
        timeline_result = await db.execute(
            text(
                """
                SELECT entry_id, entry_type, title, description, tags, timestamp
                FROM timeline_entries
                WHERE investigation_id = :investigation_id
                AND is_visible = true
                ORDER BY timestamp DESC
                LIMIT 15
            """
            ),
            {"investigation_id": str(investigation_id)},
        )
        entries = timeline_result.fetchall()

        if not entries:
            return "No timeline entries yet. User may be starting fresh."

        # Count by type
        type_counts = {}
        for _, entry_type, _, _, _, _ in entries:
            type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

        lines = [f"**Timeline Entries**: {len(entries):,} entries documented"]
        lines.append(f"**Types**: {', '.join(f'{k}={v}' for k, v in type_counts.items())}")

        # Add most recent entries (these are what user might be referencing)
        lines.append("\nMost Recent Timeline Entries (user may be referencing these):")
        for entry_id, entry_type, title, description, tags, timestamp in entries[
            :5
        ]:  # Show top 5 only
            tags_str = f" [{', '.join(tags)}]" if tags else ""
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "unknown"
            lines.append(f"  - [{time_str}] {title}{tags_str}")

        if len(entries) > 5:
            lines.append(f"  ...and {len(entries) - 5:,} more entries")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to get graph context: {e}")
        return "Timeline context unavailable."


async def _get_investigation_context(db: AsyncSession, investigation_id: UUID) -> str:
    """
    Retrieve and format metadata about a specific investigation.

    Parameters
    ----------
    db: AsyncSession
        An asynchronous SQLAlchemy session used to execute queries against the database.
    investigation_id: UUID
        The unique identifier of the investigation whose context should be gathered.

    Returns
    -------
    str
        A human-readable summary containing:
        * The number of distinct event types (up to ten most frequent).
        * The total count of events across those types.
        * A bullet list of the top five event types with their respective counts, and an optional line summarising any additional types.
        * The earliest and latest timestamps of events in ISO-8601 format, if available.

    If no events are found for the investigation, the function returns the string
    ```
    No events in this investigation yet.
    ```
    If an unexpected error occurs while querying the database, a warning is logged and the function returns
    ```
    Investigation metadata unavailable.
    ```
    """
    try:
        # Get event type counts
        event_result = await db.execute(
            text(
                """
                SELECT event_type, COUNT(*) as count
                FROM events
                WHERE investigation_id = :investigation_id
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 10
            """
            ),
            {"investigation_id": str(investigation_id)},
        )
        event_counts = event_result.fetchall()

        # Get time range
        time_result = await db.execute(
            text(
                """
                SELECT MIN(event_ts) as earliest, MAX(event_ts) as latest
                FROM events
                WHERE investigation_id = :investigation_id
            """
            ),
            {"investigation_id": str(investigation_id)},
        )
        time_row = time_result.fetchone()

        if not event_counts:
            return "No events in this investigation yet."

        lines = [f"**Total Event Types**: {len(event_counts):,}"]

        # Add event type summary
        total_events = sum(count for _, count in event_counts)
        lines.append(f"**Total Events**: {total_events}")

        lines.append("\nEvent Types:")
        for event_type, count in event_counts[:5]:  # Top 5
            lines.append(f"  - {event_type}: {count}")

        if len(event_counts) > 5:
            remaining = sum(count for _, count in event_counts[5:])
            lines.append(f"  - ...and {len(event_counts) - 5:,} more types ({remaining} events)")

        # Add time range
        if time_row and time_row[0] and time_row[1]:
            earliest = time_row[0]
            latest = time_row[1]
            lines.append(f"\n**Time Range**: {earliest.isoformat()} to {latest.isoformat()}")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to get investigation context: {e}")
        return "Investigation metadata unavailable."


__all__ = ["expand_query"]
