from typing import Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ...crud.llm_config import get_active_llm_config
from ..llm_service import LLMService

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


async def handle_general_chat(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
) -> Dict[str, Any]:
    """
    Answer general questions about an investigation by gathering relevant metadata, constructing a context-rich prompt, and querying the configured LLM.

    The function logs the incoming query, retrieves the active LLM configuration for the requesting user, assembles investigation-specific context (metadata, timeline entries, artifacts, event statistics), builds a prompt that combines this context with the user's question, and obtains a concise answer from the LLM. It returns a dictionary containing either the answer or error information.

    Args:
        db: An asynchronous SQLAlchemy session used for all database interactions.
        investigation_id: The UUID identifying the investigation whose context should be retrieved.
        user_query: The natural-language question posed by the user.
        user_id: The identifier of the user making the request, used to fetch their active LLM configuration.

    Returns:
        A dictionary with one of the following structures:
            {
                "type": "general_chat_answer",
                "success": True,
                "message": "<LLM-generated answer>"
            }
        or
            {
                "type": "error",
                "message": "<description of the failure>"
            }

    Raises:
        No exceptions are propagated; any error is caught, logged, and returned in the error dictionary.
    """
    logger.info(f"[GENERAL_CHAT] Processing: {user_query[:100]}")

    try:
        # Get LLM config
        llm_config = await get_active_llm_config(db, user_id)
        if not llm_config:
            return {
                "type": "error",
                "message": "No active LLM configuration found.",
            }

        # Gather investigation context
        context = await _gather_investigation_context(db, investigation_id)

        # Build prompt with context
        prompt = _build_context_prompt(context, user_query)

        # Get LLM response
        answer = await _get_llm_response(llm_config, prompt)

        if answer.get("type") == "error":
            return answer

        # Determine query type from context
        query_type = "metadata"
        if "timeline" in user_query.lower():
            query_type = "timeline_summary"
        elif "artifact" in user_query.lower():
            query_type = "artifact_summary"
        elif "event" in user_query.lower():
            query_type = "event_summary"

        return {
            "type": "general_chat_answer",
            "success": True,
            "message": answer.get("content", ""),
            "routing_metadata": {
                "handler_type": "general_chat",
                "handler_display_name": "General Chat",
                "query_type": query_type,
                "context_sources": list(context.keys()),
            },
        }

    except Exception as e:
        logger.error(f"[GENERAL_CHAT] Critical error: {e}", exc_info=True)
        # Ensure transaction is clean
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"[GENERAL_CHAT] Rollback failed: {rollback_error}")

        return {
            "type": "error",
            "message": f"General chat error: {str(e)}",
        }


async def _gather_investigation_context(
    db: AsyncSession,
    investigation_id: UUID,
) -> Dict[str, Any]:
    """
    Gathers comprehensive context for a given investigation from the database.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to execute queries.
    investigation_id : UUID
        Unique identifier of the investigation whose context is being retrieved.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing:
        * `investigation` - metadata with title, description, creation and update timestamps (ISO-8601 strings) if available.
        * `timeline` - statistics about visible timeline entries: total count, earliest and latest timestamps (ISO-8601 strings).
        * `artifacts` - mapping of artifact types to their respective counts.
        * `events` - mapping of event types to their respective counts (limited to the first 20 types).

    Notes
    -----
    * All datetime values are converted to ISO-8601 formatted strings or `None` when absent.
    * If no rows are found for a particular query, the corresponding key may be omitted or contain empty/default values.
    """
    context = {}

    # Investigation metadata
    inv_query = text(
        """
        SELECT title, description, created_at, updated_at
        FROM investigations
        WHERE investigation_id = :id
    """
    )
    inv_result = await db.execute(inv_query, {"id": str(investigation_id)})
    inv_row = inv_result.fetchone()

    if inv_row:
        context["investigation"] = {
            "title": inv_row[0],
            "description": inv_row[1],
            "created_at": inv_row[2].isoformat() if inv_row[2] else None,
            "updated_at": inv_row[3].isoformat() if inv_row[3] else None,
        }

    # Timeline stats
    timeline_query = text(
        """
        SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM timeline_entries
        WHERE investigation_id = :id AND is_visible = true
    """
    )
    timeline_result = await db.execute(timeline_query, {"id": str(investigation_id)})
    timeline_row = timeline_result.fetchone()

    if timeline_row:
        context["timeline"] = {
            "total_entries": timeline_row[0] or 0,
            "earliest": timeline_row[1].isoformat() if timeline_row[1] else None,
            "latest": timeline_row[2].isoformat() if timeline_row[2] else None,
        }

    # Artifact stats
    artifact_query = text(
        """
        SELECT artifact_type, COUNT(*)
        FROM artifacts
        WHERE investigation_id = :id
        GROUP BY artifact_type
    """
    )
    artifact_result = await db.execute(artifact_query, {"id": str(investigation_id)})
    artifacts = {row[0]: row[1] for row in artifact_result.fetchall()}
    context["artifacts"] = artifacts

    # Event stats
    event_query = text(
        """
        SELECT event_type, COUNT(*)
        FROM events
        WHERE investigation_id = :id
        GROUP BY event_type
        LIMIT 20
    """
    )
    event_result = await db.execute(event_query, {"id": str(investigation_id)})
    events = {row[0]: row[1] for row in event_result.fetchall()}
    context["events"] = events

    return context


def _build_context_prompt(context: Dict[str, Any], user_query: str) -> str:
    """
    Builds a prompt string that combines investigation metadata with the user's question for LLM processing.

    Parameters
    ----------
    context: Dict[str, Any]
        A dictionary containing optional keys:
        - `investigation` - mapping with `title`, `description`, and `created_at`.
        - `timeline` - mapping with `total_entries`, `earliest` and `latest` timestamps.
        - `artifacts` - mapping of artifact type names to file counts.
        - `events` - mapping of event type names to occurrence counts.

    user_query: str
        The question posed by the user that should be answered using the supplied context.

    Returns
    -------
    str
        A single string containing a formatted prompt. The prompt includes:
        * An introductory instruction for the LLM.
        * A "# Investigation Context" section populated with any available metadata.
        * A "# User Question" section followed by the original query.
        * Guidance for the model to provide a concise answer or suggest using an agent when appropriate.

    Notes
    -----
    The function gracefully skips sections that are missing from `context` and limits the displayed event types to the first ten entries. The resulting prompt is ready to be sent to a language model for inference.
    """
    prompt_parts = [
        "You are an investigation assistant. Answer the user's question based on the context provided.",
        "",
        "# Investigation Context",
        "",
    ]

    # Investigation info
    if "investigation" in context:
        inv = context["investigation"]
        prompt_parts.append(f"**Title:** {inv.get('title', 'Untitled')}")
        if inv.get("description"):
            prompt_parts.append(f"**Description:** {inv['description']}")
        prompt_parts.append(f"**Created:** {inv.get('created_at', 'Unknown')}")
        prompt_parts.append("")

    # Timeline info
    if "timeline" in context:
        tl = context["timeline"]
        prompt_parts.append(f"**Timeline Entries:** {tl.get('total_entries', 0)}")
        if tl.get("earliest") and tl.get("latest"):
            prompt_parts.append(f"**Time Range:** {tl['earliest']} to {tl['latest']}")
        prompt_parts.append("")

    # Artifacts
    if "artifacts" in context and context["artifacts"]:
        prompt_parts.append("**Available Artifacts:**")
        for artifact_type, count in context["artifacts"].items():
            prompt_parts.append(f"  - {artifact_type}: {count} files")
        prompt_parts.append("")

    # Events
    if "events" in context and context["events"]:
        total_events = sum(context["events"].values())
        prompt_parts.append(f"**Total Events:** {total_events}")
        prompt_parts.append("**Event Types:**")
        for event_type, count in list(context["events"].items())[:10]:
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

    return "\n".join(prompt_parts)


async def _get_llm_response(llm_config, prompt: str) -> Dict[str, Any]:
    """
    Fetches a response from the configured language model for a given prompt.

    Args:
        llm_config (dict or similar): Configuration data used to instantiate an LLMConfig object, typically retrieved from the database.
        prompt (str): The user-supplied text that will be sent to the LLM as a single “user” message.

    Returns:
        dict: A dictionary describing the outcome of the request.
            - On success, returns `{"type": "success", "content": <response_text>}` where
              `<response_text>` is the trimmed string produced by the model.
            - On failure or if the model returns an empty response, returns
              `{"type": "error", "message": <error_message>}` describing what went wrong.

    Raises:
        No exceptions are propagated; all errors are caught and reported in the returned dictionary.
    """
    try:
        # Create LLM service from config
        from ..llm_service import LLMConfig

        config = LLMConfig.from_db_config(llm_config)
        llm_service = LLMService(config)

        # Call LLM with simple user message
        # Use None for max_tokens and temperature to respect user's DB configuration
        data = await llm_service.call_llm(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=None,  # Use user's configured default
            temperature=None,  # Use user's configured temperature
            enforce_context_limit=False,  # Single message, no need to enforce
        )

        # Extract response text
        response_text = await llm_service.extract_text_response(data)

        if not response_text:
            return {
                "type": "error",
                "message": "LLM returned empty response",
            }

        return {
            "type": "success",
            "content": str(response_text).strip(),
        }

    except Exception as e:
        logger.error(f"LLM request failed: {e}", exc_info=True)
        return {
            "type": "error",
            "message": f"Error getting LLM response: {str(e)}",
        }


__all__ = ["handle_general_chat"]
