"""
Embedding queue service for background embedding generation.

This module provides functions to queue events for embedding and check
the embedding status of an investigation.
"""

from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..models.job_embedding import EmbeddingJob
from ..models.job_parsing import JobStatus
from ..utils.log_setup import get_logger

logger = get_logger(__name__)

# Batch size for embedding jobs (events per job)
# Larger batches reduce job overhead and enable better concurrency
EMBEDDING_BATCH_SIZE = 1000  # Up from 50 for better throughput


async def queue_events_for_embedding(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    event_ids: List[int],
) -> int:
    """
    Queue events for background embedding generation.

    Events are batched into jobs of EMBEDDING_BATCH_SIZE events each.
    Uses adaptive batching: creates larger jobs when there's queue backpressure
    to enable better concurrency and throughput.

    Args:
        db: Database session
        investigation_id: Investigation UUID
        user_id: User ID (for LLM config lookup)
        event_ids: List of event IDs to embed

    Returns:
        Number of jobs created
    """
    if not event_ids:
        return 0

    # Check current queue depth to determine batch size
    result = await db.execute(
        select(func.count(EmbeddingJob.job_id)).where(
            and_(
                EmbeddingJob.investigation_id == investigation_id,
                EmbeddingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            )
        )
    )
    pending_count = result.scalar() or 0

    # Adaptive batching: use larger batches when queue is deep
    # This allows workers to process more events concurrently
    if pending_count > 10:
        # Heavy backpressure: create fewer, larger jobs
        batch_size = EMBEDDING_BATCH_SIZE * 2  # 2000 events per job
    elif pending_count > 5:
        # Moderate backpressure: use larger batches
        batch_size = int(EMBEDDING_BATCH_SIZE * 1.5)  # 1500 events per job
    else:
        # Light load: use standard batch size
        batch_size = EMBEDDING_BATCH_SIZE  # 1000 events per job

    # Create jobs in batches
    jobs_created = 0
    for i in range(0, len(event_ids), batch_size):
        batch = event_ids[i : i + batch_size]

        job = EmbeddingJob(
            investigation_id=investigation_id,
            user_id=user_id,
            event_ids=batch,
            status=JobStatus.PENDING,
        )
        db.add(job)
        jobs_created += 1

    await db.commit()

    logger.debug(
        f"Queued {len(event_ids):,} events for embedding in {jobs_created} jobs "
        f"(batch_size={batch_size}, queue_depth={pending_count}, investigation {investigation_id})"
    )

    return jobs_created


async def get_embedding_status(
    db: AsyncSession,
    investigation_id: UUID,
) -> dict:
    """
    Get embedding queue status for an investigation.

    Args:
        db: Database session
        investigation_id: Investigation UUID

    Returns:
        Dictionary with:
            - pending_jobs: Number of pending jobs
            - running_jobs: Number of running jobs
            - completed_jobs: Number of completed jobs
            - total_jobs: Total jobs (pending + running + completed)
            - events_pending: Events in pending/running jobs
            - events_completed: Events successfully processed
            - events_total: Total events across all jobs
            - progress_percent: Completion percentage (0-100)
            - is_complete: True if no pending/running jobs
    """
    # Count all jobs by status
    result = await db.execute(
        select(
            EmbeddingJob.status,
            func.count(EmbeddingJob.job_id).label("job_count"),
            func.sum(func.array_length(EmbeddingJob.event_ids, 1)).label("event_count"),
            func.sum(EmbeddingJob.events_processed).label("events_processed"),
        )
        .where(EmbeddingJob.investigation_id == investigation_id)
        .group_by(EmbeddingJob.status)
    )

    rows = result.all()

    pending_jobs = 0
    running_jobs = 0
    completed_jobs = 0
    events_pending = 0
    events_processing = 0  # Events in running jobs being actively processed
    events_completed = 0
    events_total = 0

    for row in rows:
        job_count = int(row.job_count)
        event_count = int(row.event_count or 0)
        processed_count = int(row.events_processed or 0)

        if row.status == JobStatus.PENDING:
            pending_jobs = job_count
            events_pending += event_count
            events_total += event_count
        elif row.status == JobStatus.RUNNING:
            running_jobs = job_count
            # For running jobs: processed events go to completed, unprocessed to processing
            events_processing += (event_count - processed_count)
            events_completed += processed_count
            events_total += event_count
        elif row.status == JobStatus.COMPLETED:
            completed_jobs = job_count
            events_completed += processed_count
            events_total += event_count

    # Calculate progress percentage
    if events_total > 0:
        progress_percent = int((events_completed / events_total) * 100)
    else:
        progress_percent = 100  # No jobs means complete

    return {
        "pending_jobs": pending_jobs,
        "running_jobs": running_jobs,
        "completed_jobs": completed_jobs,
        "total_jobs": pending_jobs + running_jobs + completed_jobs,
        "events_pending": events_pending,
        "events_processing": events_processing,  # Events currently being embedded
        "events_completed": events_completed,
        "events_total": events_total,
        "progress_percent": progress_percent,
        "is_complete": (pending_jobs == 0 and running_jobs == 0),
    }


__all__ = [
    "queue_events_for_embedding",
    "get_embedding_status",
    "EMBEDDING_BATCH_SIZE",
]
