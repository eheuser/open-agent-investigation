"""
Embedding worker for background embedding generation.

This module provides functions to claim and process embedding jobs from the queue.
Optimized for high-throughput concurrent embedding generation.
"""

import uuid as uuid_pkg
from datetime import datetime
from typing import Optional
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.job_embedding import EmbeddingJob
from app.models.job_parsing import JobStatus
from app.crud.llm_config import get_active_llm_config
from app.services.rag.event_processor import _batch_create_embeddings
from app.utils.log_setup import get_logger
import json

logger = get_logger(__name__)

# Concurrency settings for embedding generation
MAX_CONCURRENT_BATCHES = 8  # Number of simultaneous API calls
EMBEDDING_BATCH_SIZE = 200  # Events per API call (within a job)


async def claim_embedding_job(db: AsyncSession, worker_id: uuid_pkg.UUID) -> Optional[EmbeddingJob]:
    """
    Atomically claim a pending embedding job for execution.
    
    Args:
        db: Database session
        worker_id: Worker UUID
        
    Returns:
        Claimed EmbeddingJob or None if no jobs available
    """
    # Find first pending job
    result = await db.execute(
        select(EmbeddingJob)
        .where(EmbeddingJob.status == JobStatus.PENDING)
        .order_by(EmbeddingJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)  # Skip locked rows for concurrency
    )

    job = result.scalars().first()

    if not job:
        return None

    # Claim it
    job.status = JobStatus.RUNNING
    job.worker_id = worker_id
    job.started_at = datetime.utcnow()

    await db.commit()
    await db.refresh(job)

    logger.debug(f"Claimed embedding job {job.job_id} ({len(job.event_ids)} events)")

    return job


async def process_embedding_job(db: AsyncSession, job: EmbeddingJob):
    """
    Process a single embedding job by generating embeddings for the batched events.
    
    Uses concurrent batch processing to maximize throughput:
    - Splits job into multiple batches of EMBEDDING_BATCH_SIZE events
    - Processes up to MAX_CONCURRENT_BATCHES batches simultaneously
    - Each batch makes a single API call to the embedding provider
    
    Args:
        db: Database session
        job: EmbeddingJob to process
    """
    # Extract job attributes early to avoid lazy loading issues after rollback
    job_id = job.job_id
    investigation_id = job.investigation_id
    user_id = job.user_id
    event_ids = job.event_ids

    try:
        logger.debug(f"Processing embedding job {job_id} ({len(event_ids):,} events)")

        # Get user's LLM config
        llm_config = await get_active_llm_config(db, user_id)
        if not llm_config:
            raise ValueError(f"No active LLM config for user {user_id}")

        # Check if embeddings are configured
        embedding_provider = getattr(llm_config, "embedding_provider", None)
        if not embedding_provider:
            logger.warning(f"No embedding provider configured for user {user_id}, skipping job")
            # Mark as completed (nothing to do)
            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.utcnow()
            job.events_processed = 0
            await db.commit()
            return

        # Fetch events to embed
        result = await db.execute(
            text(
                """
                SELECT e.event_id, e.event_type, e.payload
                FROM events e
                LEFT JOIN embeddings emb ON emb.owner_type = 'tool' AND emb.owner_id = e.event_id
                WHERE e.event_id = ANY(:event_ids)
                AND emb.id IS NULL
                ORDER BY e.event_ts
            """
            ),
            {"event_ids": event_ids},
        )

        events = result.fetchall()

        if not events:
            logger.info(f"No events to embed for job {job_id} (already embedded)")
            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.utcnow()
            job.events_processed = 0
            await db.commit()
            return

        # Prepare interesting_events list for batch embedding
        interesting_events: list[tuple[int, str, dict]] = []
        for row in events:
            event_id = int(row[0])
            event_type = str(row[1])
            payload_json = row[2]
            try:
                payload = (
                    json.loads(payload_json) if isinstance(payload_json, str) else payload_json
                )
                interesting_events.append((event_id, event_type, payload))
            except Exception as e:
                logger.debug(f"Failed to parse event {event_id}: {e}")
                continue

        # Check if concurrent embedding calls are enabled
        allow_concurrent = getattr(llm_config, "allow_concurrent_embedding_calls", False)
        
        if allow_concurrent:
            # Use concurrent processing for high-throughput
            logger.debug(f"Using concurrent embedding generation (max {MAX_CONCURRENT_BATCHES} batches)")
            created_count = await _batch_create_embeddings_concurrent(
                db, interesting_events, user_id, llm_config, job_id=job_id
            )
        else:
            # Use sequential processing (original behavior)
            logger.debug("Using sequential embedding generation (concurrent calls disabled)")
            created_count = await _batch_create_embeddings(
                db, interesting_events, user_id, llm_config
            )

        # Mark job as completed
        await db.execute(
            text(
                """
                UPDATE jobs_embedding 
                SET status = 'completed', 
                    finished_at = NOW(), 
                    events_processed = :count,
                    error_message = NULL
                WHERE job_id = :job_id
            """
            ),
            {"job_id": job_id, "count": created_count},
        )
        await db.commit()

        logger.debug(
            f"Embedding job {job_id} completed ({created_count:,}/{len(event_ids):,} embeddings created)"
        )

    except Exception as e:
        logger.error(f"Embedding job {job_id} failed: {e}", exc_info=True)

        # Rollback any failed transaction
        try:
            await db.rollback()
        except:
            pass

        # Mark job as failed
        try:
            await db.execute(
                text(
                    """
                    UPDATE jobs_embedding 
                    SET status = 'failed', 
                        finished_at = NOW(), 
                        error_message = :error_msg
                    WHERE job_id = :job_id
                """
                ),
                {"job_id": job_id, "error_msg": str(e)[:1000]},
            )
            await db.commit()
        except Exception as update_error:
            logger.error(f"Failed to update job status: {update_error}")


async def _batch_create_embeddings_concurrent(
    db: AsyncSession,
    interesting_events: list[tuple[int, str, dict]],
    user_id: int,
    llm_config,
    job_id: Optional[int] = None,
) -> int:
    """
    Create embeddings for events with concurrent batch processing.
    
    Splits events into batches and processes multiple batches concurrently
    to maximize API throughput. Uses a semaphore to limit concurrency.
    Each batch gets its own database session to avoid asyncpg conflicts.
    Updates job progress incrementally as batches complete.
    
    Args:
        db: Database session (used to get session factory)
        interesting_events: List of (event_id, event_type, payload) tuples
        user_id: User ID (unused but kept for compatibility)
        llm_config: LLM configuration object
        job_id: Optional job ID for progress tracking
        
    Returns:
        Total number of embeddings created
    """
    from app.services.rag.event_processor import _format_event_for_timeline
    from app.services.rag.embedding import Embedder
    from app.core.database import async_session_factory

    if not interesting_events:
        return 0

    # Extract embedding config
    embedding_provider = getattr(llm_config, "embedding_provider", None)
    if not embedding_provider:
        return 0

    embedding_api_url_val = getattr(llm_config, "embedding_api_url", None)
    if not embedding_api_url_val:
        return 0

    embedding_api_url = str(embedding_api_url_val)
    embedding_api_key_val = getattr(llm_config, "embedding_api_key", None)
    embedding_api_key = str(embedding_api_key_val) if embedding_api_key_val else None
    embedding_model_name_val = getattr(llm_config, "embedding_model_name", None)
    embedding_model_name = (
        str(embedding_model_name_val) if embedding_model_name_val else "nomic-embed-text"
    )

    # Initialize embedder
    embedder = Embedder(
        provider=embedding_provider,
        api_url=embedding_api_url,
        api_key=embedding_api_key,
        model_name=embedding_model_name,
    )

    # Semaphore to limit concurrent batches
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    created_count = 0

    async def process_batch(batch_events: list[tuple[int, str, dict]], batch_num: int) -> int:
        """Process a single batch of events concurrently with its own DB session."""
        async with semaphore:
            # Create a new database session for this batch
            async with async_session_factory() as batch_db:
                # Build text representations
                texts = []
                event_ids = []
                for event_id, event_type, payload in batch_events:
                    title, description = _format_event_for_timeline(event_type, payload)
                    text_content = f"{title}\n{description}"
                    if len(text_content.strip()) >= 10:
                        texts.append(text_content)
                        event_ids.append(event_id)

                if not texts:
                    return 0

                try:
                    # Generate embeddings for the batch
                    logger.debug(
                        f"Generating embeddings for batch {batch_num} ({len(texts):,} events)"
                    )
                    embeddings = await embedder.embed(texts)

                    # Bulk insert embeddings
                    insert_params = []
                    for event_id, embedding_vec in zip(event_ids, embeddings):
                        vec_list = embedding_vec.tolist()
                        vec_str = "[" + ",".join(map(str, vec_list)) + "]"
                        insert_params.append({
                            "event_id": event_id,
                            "model_name": embedding_model_name,
                            "vec_str": vec_str,
                        })

                    # Execute bulk insert using this batch's dedicated session
                    await batch_db.execute(
                        text(
                            """
                            INSERT INTO embeddings (owner_type, owner_id, model_name, vector)
                            VALUES ('tool', :event_id, :model_name, CAST(:vec_str AS vector))
                            ON CONFLICT DO NOTHING
                        """
                        ),
                        insert_params,
                    )
                    await batch_db.commit()
                    
                    batch_created = len(insert_params)
                    logger.debug(f"Batch {batch_num} completed: {batch_created:,} embeddings created")
                    
                    # Update job progress incrementally if job_id provided
                    if job_id is not None:
                        try:
                            await batch_db.execute(
                                text(
                                    """
                                    UPDATE jobs_embedding 
                                    SET events_processed = events_processed + :count
                                    WHERE job_id = :job_id
                                """
                                ),
                                {"job_id": job_id, "count": batch_created},
                            )
                            await batch_db.commit()
                        except Exception as update_error:
                            logger.warning(f"Failed to update job progress: {update_error}")
                            # Don't fail the batch if progress update fails
                    
                    return batch_created

                except Exception as e:
                    logger.error(f"Batch {batch_num} failed: {e}")
                    try:
                        await batch_db.rollback()
                    except:
                        pass
                    return 0

    # Split into batches and process concurrently
    tasks = []
    for i in range(0, len(interesting_events), EMBEDDING_BATCH_SIZE):
        batch = interesting_events[i:i + EMBEDDING_BATCH_SIZE]
        batch_num = i // EMBEDDING_BATCH_SIZE + 1
        tasks.append(process_batch(batch, batch_num))

    # Wait for all batches to complete
    if tasks:
        logger.debug(
            f"Processing {len(tasks)} batches with up to {MAX_CONCURRENT_BATCHES} concurrent connections"
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)
    else:
        results = []

    # Sum up successful creations
    for result in results:
        if isinstance(result, int):
            created_count += result
        else:
            logger.error(f"Batch processing raised exception: {result}")

    return created_count


__all__ = [
    "claim_embedding_job",
    "process_embedding_job",
    "_batch_create_embeddings_concurrent",
    "MAX_CONCURRENT_BATCHES",
    "EMBEDDING_BATCH_SIZE",
]
