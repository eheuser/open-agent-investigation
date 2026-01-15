from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID

from ..deps import get_db, get_current_user
from ..models.user import User
from ..services.rag.embedding_service import (
    generate_embedding_for_timeline_entry,
    generate_embedding_for_chat_message,
)
from ..crud.llm_config import get_active_llm_config

router = APIRouter()


@router.post("/generate/investigation/{investigation_id}")
async def generate_embeddings_for_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate embeddings for all timeline entries and chat messages within a specified investigation.

    This operation backfills missing embeddings after an embedding provider has been configured. It validates the investigation identifier, ensures the current user has an active LLM configuration with an embedding provider, then iterates over un-embedded timeline entries and chat messages, creating embeddings for each and counting successes.

    Args:
        investigation_id (str): The UUID string of the investigation to process.
        db (AsyncSession, optional): An asynchronous SQLAlchemy session provided via dependency injection. Defaults to Depends(get_db).
        current_user (User, optional): The authenticated user obtained from the request context. Defaults to Depends(get_current_user).

    Raises:
        HTTPException: If `investigation_id` is not a valid UUID.
        HTTPException: If the user does not have an active LLM configuration with an embedding provider configured.

    Returns:
        dict: A summary of the embedding operation containing:
            - "investigation_id" (str): The processed investigation identifier.
            - "timeline_entries_embedded" (int): Number of timeline entries for which embeddings were created.
            - "chat_messages_embedded" (int): Number of chat messages for which embeddings were created.
            - "total_embeddings_created" (int): Combined count of all embeddings generated.
    """
    try:
        inv_uuid = UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid investigation ID format")

    # Check if user has embedding configuration
    llm_config = await get_active_llm_config(db, current_user.user_id)
    if not llm_config or not getattr(llm_config, "embedding_provider", None):
        raise HTTPException(
            status_code=400,
            detail="No embedding provider configured. Please configure embedding settings in LLM configuration.",
        )

    timeline_count = 0
    chat_count = 0

    # Generate embeddings for timeline entries
    result = await db.execute(
        text(
            """
            SELECT entry_id, title, description
            FROM timeline_entries
            WHERE investigation_id = :inv_id
            AND embedding_id IS NULL
            ORDER BY created_at ASC
        """
        ),
        {"inv_id": str(inv_uuid)},
    )

    timeline_rows = result.fetchall()

    for entry_id, title, description in timeline_rows:
        embedding_id = await generate_embedding_for_timeline_entry(
            db=db,
            entry_id=entry_id,
            title=title,
            description=description,
            user_id=current_user.user_id,
        )
        if embedding_id:
            timeline_count += 1

    # Generate embeddings for chat messages
    result = await db.execute(
        text(
            """
            SELECT message_id, content
            FROM chat_messages
            WHERE investigation_id = :inv_id
            AND embedding_id IS NULL
            AND content IS NOT NULL
            AND LENGTH(content) > 10
            AND role IN ('user', 'assistant')
            ORDER BY created_at ASC
        """
        ),
        {"inv_id": str(inv_uuid)},
    )

    chat_rows = result.fetchall()

    for message_id, content in chat_rows:
        embedding_id = await generate_embedding_for_chat_message(
            db=db,
            message_id=message_id,
            content=content,
            user_id=current_user.user_id,
        )
        if embedding_id:
            chat_count += 1

    return {
        "investigation_id": investigation_id,
        "timeline_entries_embedded": timeline_count,
        "chat_messages_embedded": chat_count,
        "total_embeddings_created": timeline_count + chat_count,
    }


@router.get("/stats/investigation/{investigation_id}")
async def get_embedding_stats(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get embedding statistics for a specific investigation.

    Args:
        investigation_id (str): The UUID of the investigation whose embeddings are being queried.
        db (AsyncSession, optional): An asynchronous SQLAlchemy session provided by FastAPI's dependency injection. Defaults to Depends(get_db).
        current_user (User, optional): The authenticated user making the request, injected via FastAPI dependencies. Defaults to Depends(get_current_user).

    Returns:
        dict: A dictionary containing:
            - `investigation_id` (str): Echo of the supplied investigation identifier.
            - `embeddings_by_type` (dict[str, int]): Counts of embeddings grouped by their owner type (e.g., "chat", "timeline", "note", "tool").
            - `total_embeddings` (int): Sum of all embedding counts across types.
            - `timeline_entries_without_embeddings` (int): Number of timeline entries in the investigation that lack an associated embedding.
            - `chat_messages_without_embeddings` (int): Number of chat messages meeting content criteria that do not have an associated embedding.

    Raises:
        HTTPException: If `investigation_id` cannot be parsed as a valid UUID, resulting in a 400 Bad Request response.
    """
    try:
        inv_uuid = UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid investigation ID format")

    # Count embeddings by type
    result = await db.execute(
        text(
            """
            SELECT 
                e.owner_type,
                COUNT(*) as count
            FROM embeddings e
            WHERE EXISTS (
                SELECT 1 FROM (
                    SELECT investigation_id FROM chat_messages WHERE message_id = e.owner_id AND owner_type = 'chat'
                    UNION ALL
                    SELECT investigation_id FROM timeline_entries WHERE entry_id = e.owner_id AND owner_type = 'timeline'
                    UNION ALL
                    SELECT investigation_id FROM investigation_notes WHERE note_id = e.owner_id AND owner_type = 'note'
                    UNION ALL
                    SELECT investigation_id FROM tool_results WHERE result_id = e.owner_id AND owner_type = 'tool'
                ) AS owners
                WHERE owners.investigation_id = :inv_id
            )
            GROUP BY e.owner_type
        """
        ),
        {"inv_id": str(inv_uuid)},
    )

    stats_rows = result.fetchall()
    stats_by_type = {row[0]: row[1] for row in stats_rows}

    # Count items without embeddings
    timeline_without = await db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM timeline_entries
            WHERE investigation_id = :inv_id
            AND embedding_id IS NULL
        """
        ),
        {"inv_id": str(inv_uuid)},
    )

    chat_without = await db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM chat_messages
            WHERE investigation_id = :inv_id
            AND embedding_id IS NULL
            AND content IS NOT NULL
            AND LENGTH(content) > 10
            AND role IN ('user', 'assistant')
        """
        ),
        {"inv_id": str(inv_uuid)},
    )

    return {
        "investigation_id": investigation_id,
        "embeddings_by_type": stats_by_type,
        "total_embeddings": sum(stats_by_type.values()),
        "timeline_entries_without_embeddings": timeline_without.scalar() or 0,
        "chat_messages_without_embeddings": chat_without.scalar() or 0,
    }


__all__ = ["router"]
