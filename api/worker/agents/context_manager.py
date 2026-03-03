import json
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message
from ..tools.event_tools import get_enhanced_jsonb_fields

logger = get_logger(__name__)


# Token estimation
try:
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4/3.5 encoding
except Exception:
    encoding = None
    logger.warning("tiktoken not available, using character-based estimation")


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens that would be generated from *text*.

    Parameters
    ----------
    text : str
        The input string whose token count is to be estimated.

    Returns
    -------
    int
        An approximate token count. If a tokenizer encoding is available, the exact token
        count based on `encoding.encode` is returned; otherwise a fallback heuristic of one
        token per four characters is used.
    """
    if encoding:
        return len(encoding.encode(text))
    else:
        # Rough estimate: ~4 chars per token
        return len(text) // 4


def prune_chat_log(
    chat_log: List[Dict[str, Any]], max_tokens: int = 65535, preserve_recent: int = 10
) -> List[Dict[str, Any]]:
    """
    Prune a chat log so that its total token count does not exceed a specified budget.

    The function keeps essential context while discarding older assistant messages when necessary. The preservation strategy is:

    * Always retain the system prompt (the first message in the list).
    * Always retain the original user question (the second message).
    * Always retain the most recent *preserve_recent* messages, regardless of role.
    * Remove the oldest assistant messages first until the token budget is satisfied.

    Parameters
    ----------
    chat_log: List[Dict[str, Any]]
        A chronological list of chat messages where each entry follows the OpenAI API format (e.g., `{'role': 'user', 'content': ...}`).
    max_tokens: int, optional
        The maximum number of tokens allowed for the entire log. Defaults to 65 535.
    preserve_recent: int, optional
        The number of most recent messages that must be kept intact. Defaults to 10.

    Returns
    -------
    List[Dict[str, Any]]
        A pruned version of *chat_log* that respects the token limit while preserving critical context. If the log is already within budget or cannot be reduced without losing required messages, the original list is returned unchanged.
    """
    # Calculate current token count
    current_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in chat_log)

    if current_tokens <= max_tokens:
        return chat_log  # No pruning needed

    logger.info(f"Chat log exceeds {max_tokens} tokens ({current_tokens}), pruning...")

    # Preserve system, user question, and recent messages
    if len(chat_log) <= preserve_recent + 2:
        # Can't prune further without losing critical context
        logger.warning(f"Chat log at minimum size ({len(chat_log):,} messages), cannot prune further")
        return chat_log

    # Build pruned log: system + user question + recent messages
    pruned_log = [
        chat_log[0],  # System prompt
        chat_log[1],  # User question
    ] + chat_log[
        -preserve_recent:
    ]  # Recent messages

    # Calculate new token count
    new_tokens = sum(estimate_tokens(json.dumps(msg, default=str)) for msg in pruned_log)
    messages_removed = len(chat_log) - len(pruned_log)
    tokens_saved = current_tokens - new_tokens

    logger.info(
        f"Pruned chat log: {len(chat_log):,} -> {len(pruned_log):,} messages, "
        f"{current_tokens:,} -> {new_tokens:,} tokens (saved {tokens_saved:,} tokens, "
        f"{(tokens_saved/current_tokens)*100:.1f}% reduction)"
    )

    return pruned_log


async def load_investigation_context(
    db: AsyncSession,
    investigation_id: str,
    max_retries: int = 3,
    llm_client=None,
    llm_max_context: int = 32768,
) -> str:
    """
    Load investigation context including event type counts, available JSONB fields, and recent timeline entries.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used to execute database queries.
    investigation_id: str
        Identifier of the investigation whose context should be assembled.
    max_retries: int, optional
        Maximum number of retry attempts for database queries (default is 3). Currently unused but kept for API compatibility.
    llm_client: Any, optional
        Optional language-model client (unused, kept for compatibility).
    llm_max_context: int, default 32768
        Maximum token budget (unused, kept for compatibility).

    Returns
    -------
    str
        A formatted markdown string containing:
        * a summary of event type counts,
        * a concise list of available JSONB fields,
        * a snapshot of recent timeline entries,
        * and helpful usage notes for downstream agents.

    Raises
    ------
    Exception
        Any exception raised during database access is caught internally; the function logs the error and inserts an error message into the returned context string instead of propagating it.
    """
    context_parts = ["\n\n## INVESTIGATION CONTEXT\n"]

    # Get event type counts
    try:
        result = await db.execute(
            text(
                """
                SELECT event_type, COUNT(*) as count
                FROM events
                WHERE investigation_id = :investigation_id
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 20
            """
            ),
            {"investigation_id": investigation_id},
        )

        event_counts = result.fetchall()

        if event_counts:
            context_parts.append("\n### Available Data\n")
            total_events = sum(row[1] for row in event_counts)
            context_parts.append(f"**Total Events**: {total_events}\n\n")

            for event_type, count in event_counts:
                context_parts.append(f"- `{event_type}`: {count}\n")
        else:
            context_parts.append("\n### Available Data\n")
            context_parts.append("No events found. Upload artifacts first.\n")
    except Exception as e:
        logger.error(f"Failed to load event counts: {sanitize_log_message(str(e))}", exc_info=True)
        context_parts.append("\n### Available Data\n")
        context_parts.append(f"Error loading data: {type(e).__name__}: {e}\n")

    # Get enhanced JSONB fields with metadata
    try:
        enhanced_fields = await get_enhanced_jsonb_fields(
            db=db,
            investigation_id=investigation_id,
            sample_size=10,
            llm_max_context=llm_max_context,
        )

        if enhanced_fields["field_metadata"]:
            budget_info = enhanced_fields["budget_info"]
            context_parts.append("\n### Available JSONB Fields\n")
            context_parts.append(
                f"**Showing**: {budget_info['showing_fields']}/{budget_info['total_fields']} fields "
                f"(budget: {budget_info['field_budget']} for {budget_info['llm_max_context']:,} token context)\n\n"
            )

            # Group fields by prefix for better organization
            field_groups = enhanced_fields["field_groups"]
            
            for group_name in sorted(field_groups.keys()):
                fields = field_groups[group_name]
                
                if group_name == "top_level":
                    context_parts.append("**Top-level fields**:\n")
                else:
                    context_parts.append(f"**{group_name}** (nested fields):\n")
                
                for field_info in fields:
                    path = field_info["path"]
                    freq = field_info["frequency_pct"]
                    samples = field_info["samples"]
                    
                    # Format sample values
                    if samples:
                        sample_str = ", ".join(f'"{s}"' for s in samples[:3])
                        context_parts.append(
                            f"- `{path}` ({freq:.0f}% of events) - Examples: {sample_str}\n"
                        )
                    else:
                        context_parts.append(f"- `{path}` ({freq:.0f}% of events)\n")
                
                context_parts.append("\n")
            
            context_parts.append(
                "**USAGE**: Use exact paths with `query_jsonb_field(jsonb_path=\"...\", ...)` or `aggregate_jsonb_field(...)`\n"
            )
            context_parts.append(
                "**TIP**: Use `discover_jsonb_fields(event_type=\"...\")` to explore fields in specific event types\n"
            )
    except Exception as e:
        logger.error(f"Failed to load enhanced fields: {sanitize_log_message(str(e))}", exc_info=True)

    # Get existing timeline entries (limited to most recent 10 by UTC timestamp)
    try:
        # First get total count
        count_result = await db.execute(
            text(
                """
                SELECT COUNT(*) as total
                FROM timeline_entries
                WHERE investigation_id = :investigation_id
            """
            ),
            {"investigation_id": investigation_id},
        )
        total_count = int(count_result.scalar() or 0)

        # Get most recent 10 entries by UTC timestamp
        result = await db.execute(
            text(
                """
                SELECT entry_id, title, description, entry_type, tags, timestamp
                FROM timeline_entries
                WHERE investigation_id = :investigation_id
                ORDER BY timestamp DESC
                LIMIT 10
            """
            ),
            {"investigation_id": investigation_id},
        )

        timeline_entries = result.fetchall()

        if timeline_entries:
            context_parts.append("\n### Existing Timeline Evidence\n")
            context_parts.append(f"**Total Timeline Entries**: {total_count:,}\n")
            if total_count > 10:
                context_parts.append(f"**Showing Most Recent**: 10 of {total_count:,}\n\n")
            else:
                context_parts.append("\n")

            for entry_id, title, description, entry_type, tags, timestamp in timeline_entries:
                context_parts.append(f"- **Entry {entry_id}**: {title}")
                if description:
                    desc_preview = (
                        description[:100] + "..." if len(description) > 100 else description
                    )
                    context_parts.append(f" - {desc_preview}")
                if tags:
                    context_parts.append(f" [Tags: {', '.join(tags)}]")
                context_parts.append("\n")

            context_parts.append(
                "\n**IMPORTANT**: Don't re-register events already on the timeline!\n"
            )
        else:
            context_parts.append("\n### Existing Timeline Evidence\n")
            context_parts.append("**No timeline entries yet** - Register important findings!\n")
    except Exception as e:
        logger.error(f"Failed to load timeline entries: {sanitize_log_message(str(e))}", exc_info=True)

    context_parts.append("\n---\n")

    return "".join(context_parts)


async def load_execution_phase_context(
    db: AsyncSession,
    investigation_id: str,
    llm_client=None,
    llm_max_context: int = 32768,
) -> str:
    """
    Load context needed for Phase 1 (Tool Execution).

    Phase 1 needs:
    - Event type counts (to know what data exists)
    - Available JSONB fields (to query specific fields)
    - No timeline entries needed (Phase 1 doesn't register to timeline)

    Parameters
    ----------
    db: AsyncSession
        Database session.
    investigation_id: str
        Investigation identifier.
    llm_client: Any, optional
        LLM client (unused, kept for compatibility).
    llm_max_context: int, default 32768
        Maximum token budget (unused, kept for compatibility).

    Returns
    -------
    str
        Formatted markdown context for Phase 1.
    """
    context_parts = ["\n\n## PHASE 1 CONTEXT - AVAILABLE DATA\n"]

    # Get event type counts
    try:
        result = await db.execute(
            text(
                """
                SELECT event_type, COUNT(*) as count
                FROM events
                WHERE investigation_id = :investigation_id
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 20
            """
            ),
            {"investigation_id": investigation_id},
        )

        event_counts = result.fetchall()

        if event_counts:
            context_parts.append("\n### Event Types\n")
            total_events = sum(row[1] for row in event_counts)
            context_parts.append(f"**Total Events**: {total_events}\n\n")

            for event_type, count in event_counts:
                context_parts.append(f"- `{event_type}`: {count}\n")
        else:
            context_parts.append("\n### Event Types\n")
            context_parts.append("No events found. Upload artifacts first.\n")
    except Exception as e:
        logger.error(f"Failed to load event counts: {sanitize_log_message(str(e))}", exc_info=True)
        context_parts.append("\n### Event Types\n")
        context_parts.append(f"Error loading data: {type(e).__name__}: {e}\n")

    # Get enhanced JSONB fields with metadata
    try:
        enhanced_fields = await get_enhanced_jsonb_fields(
            db=db,
            investigation_id=investigation_id,
            sample_size=10,
            llm_max_context=llm_max_context,
        )

        if enhanced_fields["field_metadata"]:
            budget_info = enhanced_fields["budget_info"]
            context_parts.append("\n### Available JSONB Fields\n")
            context_parts.append(
                f"**Showing**: {budget_info['showing_fields']}/{budget_info['total_fields']} fields "
                f"(budget: {budget_info['field_budget']} for {budget_info['llm_max_context']:,} token context)\n\n"
            )
            
            # Group fields by prefix for better organization
            field_groups = enhanced_fields["field_groups"]
            
            for group_name in sorted(field_groups.keys()):
                fields = field_groups[group_name]
                
                if group_name == "top_level":
                    context_parts.append("**Top-level fields**:\n")
                else:
                    context_parts.append(f"**{group_name}** (nested fields):\n")
                
                for field_info in fields:
                    path = field_info["path"]
                    freq = field_info["frequency_pct"]
                    samples = field_info["samples"]
                    
                    # Format sample values
                    if samples:
                        sample_str = ", ".join(f'"{s}"' for s in samples[:3])
                        context_parts.append(
                            f"- `{path}` ({freq:.0f}% of events) - Examples: {sample_str}\n"
                        )
                    else:
                        context_parts.append(f"- `{path}` ({freq:.0f}% of events)\n")
                
                context_parts.append("\n")
            
            context_parts.append(
                "**USAGE**: Use exact paths with `query_jsonb_field(jsonb_path=\"...\", ...)` or `aggregate_jsonb_field(...)`\n"
            )
            context_parts.append(
                "**TIP**: Use `discover_jsonb_fields(event_type=\"...\")` to explore fields in specific event types\n"
            )
    except Exception as e:
        logger.error(f"Failed to load enhanced fields: {sanitize_log_message(str(e))}", exc_info=True)

    context_parts.append("\n---\n")
    return "".join(context_parts)


async def load_analysis_phase_context(
    db: AsyncSession,
    investigation_id: str,
) -> str:
    """
    Load context needed for Phase 2 (Analysis).

    Phase 2 needs:
    - Existing timeline entries (to avoid duplicates when registering)
    - Tool results are passed separately, not part of context

    Parameters
    ----------
    db: AsyncSession
        Database session.
    investigation_id: str
        Investigation identifier.

    Returns
    -------
    str
        Formatted markdown context for Phase 2.
    """
    context_parts = ["\n\n## PHASE 2 CONTEXT - TIMELINE STATUS\n"]

    # Get existing timeline entries (limited to most recent 10 by UTC timestamp)
    try:
        # First get total count
        count_result = await db.execute(
            text(
                """
                SELECT COUNT(*) as total
                FROM timeline_entries
                WHERE investigation_id = :investigation_id
            """
            ),
            {"investigation_id": investigation_id},
        )
        total_count = int(count_result.scalar() or 0)

        # Get most recent 10 entries by UTC timestamp
        result = await db.execute(
            text(
                """
                SELECT entry_id, title, description, entry_type, tags, timestamp
                FROM timeline_entries
                WHERE investigation_id = :investigation_id
                ORDER BY timestamp DESC
                LIMIT 10
            """
            ),
            {"investigation_id": investigation_id},
        )

        timeline_entries = result.fetchall()

        if timeline_entries:
            context_parts.append("\n### Existing Timeline Evidence\n")
            context_parts.append(f"**Total Timeline Entries**: {total_count:,}\n")
            if total_count > 10:
                context_parts.append(f"**Showing Most Recent**: 10 of {total_count:,}\n\n")
            else:
                context_parts.append("\n")

            for entry_id, title, description, entry_type, tags, timestamp in timeline_entries:
                context_parts.append(f"- **Entry {entry_id}**: {title}")
                if description:
                    desc_preview = (
                        description[:100] + "..." if len(description) > 100 else description
                    )
                    context_parts.append(f" - {desc_preview}")
                if tags:
                    context_parts.append(f" [Tags: {', '.join(tags)}]")
                context_parts.append("\n")

            context_parts.append(
                "\n**IMPORTANT**: Don't re-register events already on the timeline!\n"
            )
        else:
            context_parts.append("\n### Existing Timeline Evidence\n")
            context_parts.append("**No timeline entries yet** - Register important findings!\n")
    except Exception as e:
        logger.error(f"Failed to load timeline entries: {sanitize_log_message(str(e))}", exc_info=True)

    context_parts.append("\n---\n")
    return "".join(context_parts)


__all__ = [
    "estimate_tokens",
    "prune_chat_log",
    "load_investigation_context",
    "load_execution_phase_context",
    "load_analysis_phase_context",
]
