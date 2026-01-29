from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.log_setup import get_logger
from .field_dictionary_finalizer import get_cached_field_dictionary_markdown

logger = get_logger(__name__)


async def generate_field_dictionary(
    db: AsyncSession,
    investigation_id: str,
    llm_client,
    max_fields_per_type: int = 30,
    llm_max_context: int = 32768,
) -> str:
    """
    Generate field dictionary using cached markdown.

    This function now uses pre-generated cached markdown from the field_dictionary table
    instead of regenerating it every call. Field descriptions are populated by the
    post-parsing finalizer (field_dictionary_finalizer.py).

    Args:
        db: An active `AsyncSession` used for all database queries.
        investigation_id: The UUID of the investigation whose events are being inspected.
        llm_client: LLM client (unused in optimized path, kept for compatibility).
        max_fields_per_type: Maximum number of fields to display per event type (default 30).
        llm_max_context: The maximum token context size (unused in optimized path).

    Returns:
        A markdown string containing a "Field Dictionary" section with cached descriptions.
    """
    try:
        # Use optimized cached markdown retrieval
        cached_dict = await get_cached_field_dictionary_markdown(
            db=db,
            investigation_id=investigation_id,
            max_fields_per_type=max_fields_per_type,
        )

        logger.debug(
            f"Retrieved cached field dictionary for investigation {investigation_id}: "
            f"{len(cached_dict):,} chars"
        )

        return cached_dict

    except Exception as e:
        logger.error(f"Failed to retrieve cached field dictionary: {e}", exc_info=True)
        return "**Error retrieving field dictionary**\n"


__all__ = [
    "generate_field_dictionary",
]
