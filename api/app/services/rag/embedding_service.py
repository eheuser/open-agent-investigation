import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import numpy as np

from .embedding import Embedder
from ...crud.llm_config import get_active_llm_config

logger = logging.getLogger(__name__)


async def generate_embeddings_for_events(
    db: AsyncSession,
    investigation_id: UUID,
    event_ids: List[int],
    user_id: int,
) -> int:
    """
    Generate vector embeddings for timeline entries associated with the given event IDs and store them in the database.

    Parameters
    ----------
    db : AsyncSession
        An asynchronous SQLAlchemy session used to query and modify the database.
    investigation_id : UUID
        The identifier of the investigation that owns the events.
    event_ids : List[int]
        A list of primary-key identifiers for the events whose timeline entries should be embedded. Empty lists are ignored.
    user_id : int
        Identifier of the user whose active LLM configuration provides the embedding provider, API endpoint, key and model name.

    Returns
    -------
    int
        The number of embeddings that were successfully created and linked to timeline entries.

    Notes
    -----
    * If no event IDs are supplied, if the user lacks an active LLM configuration, or if the configuration does not specify an embedding provider or API URL, the function returns `0` without performing any work.
    * Only timeline entries that belong to the specified investigation, are linked to one of the provided events, and do not already have an `embedding_id` are processed.
    * Embeddings are generated in batches (default size 100) using the configured `Embedder` implementation. Each embedding is inserted into the `embeddings` table and the corresponding timeline entry is updated with the new `embedding_id`.
    * The function commits after each batch; on any exception it rolls back the transaction, logs the error, and returns `0`.
    """
    if not event_ids:
        return 0

    # Get user's LLM configuration
    llm_config = await get_active_llm_config(db, user_id)
    if not llm_config:
        logger.warning(f"No active LLM config for user {user_id}, skipping embeddings")
        return 0

    # Check if embeddings are configured
    embedding_provider = getattr(llm_config, "embedding_provider", None)
    if not embedding_provider:
        logger.info(f"No embedding provider configured for user {user_id}, skipping embeddings")
        return 0

    # Extract embedding config
    embedding_api_url = str(getattr(llm_config, "embedding_api_url", ""))
    embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
    embedding_api_key = str(embedding_api_key_val) if embedding_api_key_val else None
    embedding_model_name = str(
        getattr(llm_config, "embedding_model_name", "text-embedding-ada-002")
    )

    if not embedding_api_url:
        logger.warning(f"No embedding API URL configured, skipping embeddings")
        return 0

    try:
        # Initialize embedder
        embedder = Embedder(
            provider=embedding_provider,
            api_url=embedding_api_url,
            api_key=embedding_api_key,
            model_name=embedding_model_name,
        )

        # Fetch events and create timeline entries if they don't exist
        # Note: We embed timeline entries, not raw events
        result = await db.execute(
            text(
                """
                SELECT te.entry_id, te.title, COALESCE(te.description, '')
                FROM timeline_entries te
                WHERE te.event_id = ANY(:event_ids)
                AND te.investigation_id = :inv_id
                AND te.embedding_id IS NULL
            """
            ),
            {"event_ids": event_ids, "inv_id": str(investigation_id)},
        )
        rows = result.fetchall()

        if not rows:
            logger.info("All events already have embeddings")
            return 0

        # Prepare texts for embedding
        texts = []
        entry_ids = []
        for entry_id, title, description in rows:
            # Create a readable text representation
            text_content = f"{title}\n{description}"
            texts.append(text_content)
            entry_ids.append(entry_id)

        logger.info(f"Generating embeddings for {len(texts)} events")

        # Generate embeddings in batches
        batch_size = 100  # Adjust based on API limits
        created_count = 0

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_entry_ids = entry_ids[i : i + batch_size]

            # Generate embeddings
            embeddings = await embedder.embed(batch_texts)

            # Insert embeddings
            for entry_id, embedding_vec in zip(batch_entry_ids, embeddings):
                # Convert numpy array to list, then to PostgreSQL vector format string
                vec_list = embedding_vec.tolist()
                vec_str = "[" + ",".join(map(str, vec_list)) + "]"

                result = await db.execute(
                    text(
                        """
                        INSERT INTO embeddings (owner_type, owner_id, model_name, vector)
                        VALUES ('timeline', :entry_id, :model_name, CAST(:vec_str AS vector))
                        RETURNING id
                    """
                    ),
                    {
                        "entry_id": entry_id,
                        "model_name": embedding_model_name,
                        "vec_str": vec_str,
                    },
                )
                row = result.fetchone()
                if row:
                    embedding_id = row[0]
                    # Update timeline entry with embedding_id
                    await db.execute(
                        text(
                            "UPDATE timeline_entries SET embedding_id = :emb_id WHERE entry_id = :entry_id"
                        ),
                        {"emb_id": embedding_id, "entry_id": entry_id},
                    )
                    created_count += 1

            await db.commit()
            logger.info(f"Created {len(batch_entry_ids)} embeddings (batch {i//batch_size + 1})")

        logger.info(f"Successfully created {created_count} embeddings for timeline entries")
        return created_count

    except Exception as e:
        logger.error(f"Error generating embeddings for events: {e}", exc_info=True)
        await db.rollback()
        return 0


async def generate_embedding_for_chat_message(
    db: AsyncSession,
    message_id: int,
    content: str,
    user_id: int,
) -> Optional[int]:
    """
    Generate and store an embedding for a chat message.

    This function validates the provided message content, retrieves the active LLM configuration for the given user, and uses the configured embedding provider to compute a vector representation of the message text. The resulting embedding is inserted into the `embeddings` table and linked back to the original chat message record.

    Args:
        db: An asynchronous SQLAlchemy session used for all database interactions.
        message_id: Primary key of the chat message that should receive an embedding.
        content: Raw textual content of the chat message. Must be at least 10 non-whitespace characters.
        user_id: Identifier of the user whose LLM configuration determines which embedder to use.

    Returns:
        The integer primary key of the newly created embedding record, or `None` if no embedding was generated (e.g., due to invalid content, missing configuration, or an error during processing).

    Raises:
        No exceptions are propagated; any errors are logged and result in a `None` return after rolling back the transaction.
    """
    if not content or len(content.strip()) < 10:
        return None

    # Get user's LLM configuration
    llm_config = await get_active_llm_config(db, user_id)
    if not llm_config:
        return None

    # Check if embeddings are configured
    embedding_provider = getattr(llm_config, "embedding_provider", None)
    if not embedding_provider:
        return None

    # Extract embedding config
    embedding_api_url_val = getattr(llm_config, "embedding_api_url", None)
    if not embedding_api_url_val:
        return None
    embedding_api_url = str(embedding_api_url_val)

    embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
    embedding_api_key = str(embedding_api_key_val) if embedding_api_key_val else None

    embedding_model_name_val = getattr(llm_config, "embedding_model_name", None)
    embedding_model_name = (
        str(embedding_model_name_val) if embedding_model_name_val else "text-embedding-ada-002"
    )

    try:
        # Initialize embedder
        embedder = Embedder(
            provider=embedding_provider,
            api_url=embedding_api_url,
            api_key=embedding_api_key,
            model_name=embedding_model_name,
        )

        # Generate embedding
        embeddings = await embedder.embed([content])

        if len(embeddings) == 0:
            return None

        # Insert embedding
        # Convert numpy array to list, then to PostgreSQL vector format string
        vec_list = embeddings[0].tolist()
        vec_str = "[" + ",".join(map(str, vec_list)) + "]"

        result = await db.execute(
            text(
                """
                INSERT INTO embeddings (owner_type, owner_id, model_name, vector)
                VALUES ('chat', :message_id, :model_name, CAST(:vec_str AS vector))
                ON CONFLICT DO NOTHING
                RETURNING id
            """
            ),
            {
                "message_id": message_id,
                "model_name": embedding_model_name,
                "vec_str": vec_str,
            },
        )

        row = result.fetchone()
        embedding_id = row[0] if row else None

        # Update chat message with embedding_id
        if embedding_id:
            await db.execute(
                text("UPDATE chat_messages SET embedding_id = :emb_id WHERE message_id = :msg_id"),
                {"emb_id": embedding_id, "msg_id": message_id},
            )

        await db.commit()
        logger.info(f"Created embedding {embedding_id} for chat message {message_id}")
        return embedding_id

    except Exception as e:
        logger.error(f"Error generating embedding for chat message: {e}", exc_info=True)
        await db.rollback()
        return None


async def generate_embedding_for_timeline_entry(
    db: AsyncSession,
    entry_id: int,
    title: str,
    description: Optional[str],
    user_id: int,
) -> Optional[int]:
    """
    Generate and store an embedding for a timeline entry.

    This coroutine creates a text representation of a timeline entry by concatenating its title and optional description,
    obtains the active LLM configuration for the specified user, and uses the configured embedding provider to compute
    a vector embedding. The resulting vector is inserted into the `embeddings` table and linked back to the timeline
    entry via its `embedding_id` column.

    Parameters
    ----------
    db : AsyncSession
        An asynchronous SQLAlchemy session used for all database interactions.
    entry_id : int
        Primary key of the timeline entry that will receive the embedding.
    title : str
        The title of the timeline entry; part of the content to be embedded.
    description : Optional[str]
        Additional description text for the entry. If `None` or empty, only the title is used.
    user_id : int
        Identifier of the user whose active LLM configuration determines which embedding service and model are used.

    Returns
    -------
    Optional[int]
        The primary key of the newly created embedding record if the operation succeeds; otherwise `None` when
        the content is too short, no suitable LLM/embedding configuration exists, or an error occurs.

    Raises
    ------
    No exceptions are propagated.  All errors are caught, logged, and result in a return value of `None` with the
    database transaction rolled back.
    """
    # Combine title and description
    content = f"{title}\n{description or ''}"

    if len(content.strip()) < 10:
        return None

    # Get user's LLM configuration
    llm_config = await get_active_llm_config(db, user_id)
    if not llm_config:
        return None

    # Check if embeddings are configured
    embedding_provider = getattr(llm_config, "embedding_provider", None)
    if not embedding_provider:
        return None

    # Extract embedding config
    embedding_api_url_val = getattr(llm_config, "embedding_api_url", None)
    if not embedding_api_url_val:
        return None
    embedding_api_url = str(embedding_api_url_val)

    embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
    embedding_api_key = str(embedding_api_key_val) if embedding_api_key_val else None

    embedding_model_name_val = getattr(llm_config, "embedding_model_name", None)
    embedding_model_name = (
        str(embedding_model_name_val) if embedding_model_name_val else "text-embedding-ada-002"
    )

    try:
        # Initialize embedder
        embedder = Embedder(
            provider=embedding_provider,
            api_url=embedding_api_url,
            api_key=embedding_api_key,
            model_name=embedding_model_name,
        )

        # Generate embedding
        embeddings = await embedder.embed([content])

        if len(embeddings) == 0:
            return None

        # Insert embedding
        # Convert numpy array to list, then to PostgreSQL vector format string
        vec_list = embeddings[0].tolist()
        vec_str = "[" + ",".join(map(str, vec_list)) + "]"

        result = await db.execute(
            text(
                """
                INSERT INTO embeddings (owner_type, owner_id, model_name, vector)
                VALUES ('timeline', :entry_id, :model_name, CAST(:vec_str AS vector))
                ON CONFLICT DO NOTHING
                RETURNING id
            """
            ),
            {
                "entry_id": entry_id,
                "model_name": embedding_model_name,
                "vec_str": vec_str,
            },
        )

        row = result.fetchone()
        embedding_id = row[0] if row else None

        # Update timeline entry with embedding_id
        if embedding_id:
            await db.execute(
                text(
                    "UPDATE timeline_entries SET embedding_id = :emb_id WHERE entry_id = :entry_id"
                ),
                {"emb_id": embedding_id, "entry_id": entry_id},
            )

        await db.commit()
        logger.info(f"Created embedding {embedding_id} for timeline entry {entry_id}")
        return embedding_id

    except Exception as e:
        logger.error(f"Error generating embedding for timeline entry: {e}", exc_info=True)
        await db.rollback()
        return None


__all__ = [
    "generate_embeddings_for_events",
    "generate_embedding_for_chat_message",
    "generate_embedding_for_timeline_entry",
]
