import asyncio
from typing import List, Dict, Set
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..models.job_embedding import EmbeddingJob
from ..models.job_parsing import JobStatus
from ..utils.log_setup import get_logger

logger = get_logger(__name__)

# Pool configuration
# NOTE: Size-based and timeout-based flushing are DISABLED for deterministic behavior
# Pool is only flushed when parsing completes for an investigation
POOL_FLUSH_SIZE = 999999999  # Effectively disabled (only flush on investigation completion)
POOL_FLUSH_TIMEOUT = 999999  # Effectively disabled (only flush on investigation completion)
POOL_CHECK_INTERVAL = 60  # Check infrequently (only for cleanup of abandoned pools)


class EmbeddingPool:
    """
    In-memory pool that accumulates events before creating embedding jobs.

    Thread-safe singleton that manages event pooling across multiple parsing jobs.
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Pool structure: {(investigation_id, user_id): {event_ids: set, first_added: datetime}}
        self._pools: Dict[tuple[UUID, int], Dict] = {}
        self._pool_lock = asyncio.Lock()
        self._background_task = None
        self._initialized = True

        logger.debug("Embedding pool initialized")

    async def add_events(
        self,
        db: AsyncSession,
        investigation_id: UUID,
        user_id: int,
        event_ids: List[int],
    ) -> int:
        """
        Add events to the pool for this investigation/user.

        Will automatically flush if pool reaches POOL_FLUSH_SIZE.

        Args:
            db: Database session
            investigation_id: Investigation UUID
            user_id: User ID
            event_ids: List of event IDs to add

        Returns:
            Number of jobs created (0 if still pooling, >0 if flushed)
        """
        if not event_ids:
            return 0

        async with self._pool_lock:
            pool_key = (investigation_id, user_id)

            # Initialize pool if needed
            if pool_key not in self._pools:
                self._pools[pool_key] = {
                    "event_ids": set(),
                    "first_added": datetime.utcnow(),
                }

            pool = self._pools[pool_key]

            # Add new events
            initial_size = len(pool["event_ids"])
            pool["event_ids"].update(event_ids)
            new_size = len(pool["event_ids"])
            added_count = new_size - initial_size

            logger.debug(
                f"Added {added_count:,} events to pool (investigation {investigation_id}, "
                f"pool size: {new_size:,}/{POOL_FLUSH_SIZE})"
            )

            # Size-based flushing is disabled - only flush when investigation parsing completes
            # This ensures deterministic batching (same artifacts = same batches)
            return 0

    async def _flush_pool(
        self,
        db: AsyncSession,
        pool_key: tuple[UUID, int],
    ) -> int:
        """
        Flush a specific pool by creating embedding jobs with proper batching.

        Must be called with _pool_lock held.

        Args:
            db: Database session
            pool_key: (investigation_id, user_id) tuple

        Returns:
            Number of jobs created
        """
        if pool_key not in self._pools:
            return 0

        pool = self._pools[pool_key]
        event_ids = sorted(list(pool["event_ids"]))  # Sort for deterministic batching

        if not event_ids:
            # Clean up empty pool
            del self._pools[pool_key]
            return 0

        investigation_id, user_id = pool_key

        # Batch events into jobs of 1000 events each (deterministic batching)
        BATCH_SIZE = 1000
        jobs_created = 0

        for i in range(0, len(event_ids), BATCH_SIZE):
            batch = event_ids[i : i + BATCH_SIZE]
            
            job = EmbeddingJob(
                investigation_id=investigation_id,
                user_id=user_id,
                event_ids=batch,
                status=JobStatus.PENDING,
            )
            db.add(job)
            jobs_created += 1

        try:
            await db.commit()

            logger.debug(
                f"Flushed pool: created {jobs_created} job(s) with {len(event_ids):,} events "
                f"(investigation {investigation_id})"
            )

            # Clear the pool
            del self._pools[pool_key]

            return jobs_created

        except Exception as e:
            logger.error(f"Failed to flush pool: {e}", exc_info=True)
            await db.rollback()
            return 0

    async def flush_investigation(self, db: AsyncSession, investigation_id: UUID) -> int:
        """
        Flush all pools for a specific investigation.

        Args:
            db: Database session
            investigation_id: Investigation UUID to flush

        Returns:
            Number of jobs created
        """
        async with self._pool_lock:
            total_jobs = 0
            
            # Find all pool keys for this investigation
            keys_to_flush = [
                key for key in self._pools.keys()
                if key[0] == investigation_id
            ]

            for pool_key in keys_to_flush:
                jobs_created = await self._flush_pool(db, pool_key)
                total_jobs += jobs_created

            if total_jobs > 0:
                logger.debug(
                    f"Flushed {len(keys_to_flush)} pool(s) for investigation {investigation_id}: "
                    f"{total_jobs} job(s) created"
                )
            return total_jobs

    async def flush_all(self, db: AsyncSession) -> int:
        """
        Flush all pools (used during shutdown or manual flush).

        Args:
            db: Database session

        Returns:
            Total number of jobs created
        """
        async with self._pool_lock:
            total_jobs = 0
            pool_keys = list(self._pools.keys())

            for pool_key in pool_keys:
                jobs_created = await self._flush_pool(db, pool_key)
                total_jobs += jobs_created

            logger.debug(f"Flushed all pools: {total_jobs} jobs created")
            return total_jobs

    async def flush_stale_pools(self, db: AsyncSession) -> int:
        """
        Flush pools that have exceeded POOL_FLUSH_TIMEOUT.

        Called periodically by background task.

        Args:
            db: Database session

        Returns:
            Number of jobs created
        """
        async with self._pool_lock:
            now = datetime.utcnow()
            timeout_threshold = now - timedelta(seconds=POOL_FLUSH_TIMEOUT)

            total_jobs = 0
            stale_keys = []

            # Find stale pools
            for pool_key, pool in self._pools.items():
                if pool["first_added"] <= timeout_threshold:
                    stale_keys.append(pool_key)

            # Flush stale pools
            for pool_key in stale_keys:
                investigation_id, user_id = pool_key
                pool = self._pools[pool_key]
                age_seconds = (now - pool["first_added"]).total_seconds()

                logger.debug(
                    f"Flushing stale pool (age: {age_seconds:.1f}s, "
                    f"size: {len(pool['event_ids']):,}, investigation {investigation_id})"
                )

                jobs_created = await self._flush_pool(db, pool_key)
                total_jobs += jobs_created

            if total_jobs > 0:
                logger.debug(f"Flushed {len(stale_keys)} stale pools: {total_jobs} jobs created")

            return total_jobs

    async def start_background_flusher(self, get_db_session):
        """
        Start background task that periodically flushes stale pools.

        Args:
            get_db_session: Async function that returns a database session context manager
        """
        if self._background_task is not None:
            logger.warning("Background flusher already running")
            return

        async def background_flush_loop():
            logger.debug(
                f"Starting background pool flusher (interval: {POOL_CHECK_INTERVAL}s, "
                f"timeout: {POOL_FLUSH_TIMEOUT}s)"
            )

            while True:
                try:
                    await asyncio.sleep(POOL_CHECK_INTERVAL)

                    # Get a database session
                    async with get_db_session() as db:
                        await self.flush_stale_pools(db)

                except asyncio.CancelledError:
                    logger.debug("Background flusher cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in background flusher: {e}", exc_info=True)
                    # Continue running despite errors

        self._background_task = asyncio.create_task(background_flush_loop())
        logger.debug("Background pool flusher started")

    async def stop_background_flusher(self):
        """Stop the background flusher task."""
        if self._background_task is None:
            return

        logger.debug("Stopping background pool flusher...")
        self._background_task.cancel()

        try:
            await self._background_task
        except asyncio.CancelledError:
            pass

        self._background_task = None
        logger.debug("Background pool flusher stopped")

    def get_pool_stats(self) -> Dict:
        """
        Get statistics about current pools.

        Returns:
            Dictionary with pool statistics
        """
        total_events = sum(len(pool["event_ids"]) for pool in self._pools.values())
        pool_count = len(self._pools)

        pools_info = []
        for (investigation_id, user_id), pool in self._pools.items():
            age_seconds = (datetime.utcnow() - pool["first_added"]).total_seconds()
            pools_info.append(
                {
                    "investigation_id": str(investigation_id),
                    "user_id": user_id,
                    "event_count": len(pool["event_ids"]),
                    "age_seconds": age_seconds,
                }
            )

        return {
            "pool_count": pool_count,
            "total_events": total_events,
            "pools": pools_info,
        }


# Global singleton instance
_embedding_pool = EmbeddingPool()


async def add_events_to_pool(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    event_ids: List[int],
) -> int:
    """
    Add events to the embedding pool.

    Public API for adding events. Events will be accumulated and batched
    into jobs automatically.

    Args:
        db: Database session
        investigation_id: Investigation UUID
        user_id: User ID
        event_ids: List of event IDs to embed

    Returns:
        Number of jobs created (0 if still pooling)
    """
    return await _embedding_pool.add_events(db, investigation_id, user_id, event_ids)


async def flush_investigation_pool(db: AsyncSession, investigation_id: UUID) -> int:
    """
    Flush the embedding pool for a specific investigation.

    Args:
        db: Database session
        investigation_id: Investigation UUID

    Returns:
        Number of jobs created
    """
    return await _embedding_pool.flush_investigation(db, investigation_id)


async def flush_embedding_pool(db: AsyncSession) -> int:
    """
    Manually flush all pools.

    Args:
        db: Database session

    Returns:
        Number of jobs created
    """
    return await _embedding_pool.flush_all(db)


async def start_pool_flusher(get_db_session):
    """
    Start the background pool flusher.

    Should be called during application startup.

    Args:
        get_db_session: Async function that returns a database session context manager
    """
    await _embedding_pool.start_background_flusher(get_db_session)


async def stop_pool_flusher():
    """
    Stop the background pool flusher.

    Should be called during application shutdown.
    """
    await _embedding_pool.stop_background_flusher()


def get_pool_statistics() -> Dict:
    """Get current pool statistics."""
    return _embedding_pool.get_pool_stats()


__all__ = [
    "add_events_to_pool",
    "flush_investigation_pool",
    "flush_embedding_pool",
    "start_pool_flusher",
    "stop_pool_flusher",
    "get_pool_statistics",
    "POOL_FLUSH_SIZE",
    "POOL_FLUSH_TIMEOUT",
]
