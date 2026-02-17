"""
Embedding batcher service that intelligently batches events into embedding jobs.

This service runs as a separate process and:
1. Receives events from parsers via multiprocessing.Queue
2. Batches events into groups of 500 (or smaller if queue drains)
3. Creates embedding jobs when batch is full or after 3-second timeout
4. Runs continuously in parallel with parsing

This ensures consistent batching regardless of parsing concurrency.
"""

import multiprocessing as mp
import time
from typing import List, Dict, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import asyncio

from ..models.job_embedding import EmbeddingJob
from ..models.job_parsing import JobStatus
from ..core.config import settings
from ..utils.log_setup import get_logger
from ..utils.security import sanitize_log_message

logger = get_logger(__name__)

# Batch configuration
BATCH_SIZE = 500  # Events per embedding job
BATCH_TIMEOUT = 3.0  # Seconds to wait before flushing partial batch

# Global queue for cross-process communication
_event_queue = None
_batcher_process = None
_stop_event = None


def initialize_event_queue():
    """Initialize the global event queue using Manager for true cross-process sharing."""
    global _event_queue
    manager = mp.Manager()
    _event_queue = manager.Queue()
    logger.info("Embedding event queue initialized (Manager.Queue)")
    return _event_queue


def get_event_queue():
    """Get the global event queue."""
    return _event_queue


def set_event_queue(queue):
    """Set the event queue (called by child processes)."""
    global _event_queue
    _event_queue = queue


async def batch_loop_async(stop_event):
    """
    Async batching loop that creates embedding jobs from queued events.
    
    Args:
        stop_event: Multiprocessing event to signal stop
    """
    logger.info(f"Batching loop started (batch_size={BATCH_SIZE}, timeout={BATCH_TIMEOUT}s)")
    
    global _event_queue
    if _event_queue is None:
        logger.error("Event queue not initialized")
        return

    # Create database engine for this process
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        while not stop_event.is_set():
            try:
                # Collect events for a batch
                batch = []
                batch_start = time.time()

                # Pull events until batch is full or timeout expires
                while len(batch) < BATCH_SIZE:
                    remaining_time = BATCH_TIMEOUT - (time.time() - batch_start)
                    
                    if remaining_time <= 0:
                        break  # Timeout expired
                    
                    try:
                        # Non-blocking get with timeout
                        event_tuple = _event_queue.get(timeout=min(remaining_time, 0.1))
                        batch.append(event_tuple)
                    except:
                        # Check stop event
                        if stop_event.is_set():
                            break
                        continue

                # If we have events, create jobs
                if batch:
                    # Group events by (investigation_id, user_id)
                    groups = {}
                    
                    for investigation_id, user_id, event_id in batch:
                        key = (investigation_id, user_id)
                        if key not in groups:
                            groups[key] = []
                        groups[key].append(event_id)
                    
                    # Create embedding jobs for each group
                    async with session_maker() as db:
                        try:
                            jobs_created = 0
                            
                            for (investigation_id, user_id), event_ids in groups.items():
                                # Sort event IDs for deterministic batching
                                event_ids = sorted(event_ids)
                                
                                job = EmbeddingJob(
                                    investigation_id=investigation_id,
                                    user_id=user_id,
                                    event_ids=event_ids,
                                    status=JobStatus.PENDING,
                                )
                                db.add(job)
                                jobs_created += 1
                            
                            await db.commit()
                            
                            logger.debug(
                                f"Created {jobs_created} embedding job(s) with "
                                f"{sum(len(ids) for ids in groups.values()):,} events"
                            )
                            
                        except Exception as e:
                            logger.error(f"Failed to create embedding jobs: {sanitize_log_message(str(e))}", exc_info=True)
                            try:
                                await db.rollback()
                            except:
                                pass
                else:
                    # Queue is empty, sleep before next iteration
                    await asyncio.sleep(3.0)

            except Exception as e:
                logger.error(f"Error in batching loop: {sanitize_log_message(str(e))}", exc_info=True)
                await asyncio.sleep(5.0)  # Back off on error

    finally:
        await engine.dispose()
        logger.info("Batching loop stopped")


def batch_loop_sync(stop_event):
    """Synchronous wrapper for async batch loop."""
    asyncio.run(batch_loop_async(stop_event))


def start_batcher_process(event_queue, stop_event):
    """
    Start the batching process (runs as separate process).
    
    Args:
        event_queue: The multiprocessing queue to receive events from
        stop_event: Multiprocessing event to signal stop
    """
    mp.current_process().name = "EmbeddingBatcher"
    
    # Set the event queue for this process
    set_event_queue(event_queue)
    
    # Configure HTTP logging to send logs to API server
    from ..utils.http_log_handler import setup_worker_logging
    setup_worker_logging(
        api_host=settings.api_host,
        api_port=settings.api_port,
        process_name="EmbeddingBatcher"
    )
    
    logger.info("Embedding batcher process starting...")
    batch_loop_sync(stop_event)


def start_embedding_batcher():
    """Start the embedding batcher as a separate process."""
    global _event_queue, _batcher_process, _stop_event
    
    if _batcher_process is not None and _batcher_process.is_alive():
        logger.warning("Batcher process already running")
        return
    
    # Queue should already be initialized by main process
    if _event_queue is None:
        logger.error("Event queue not initialized - call initialize_event_queue() first")
        return
    
    # Create stop event
    _stop_event = mp.Event()
    
    # Start batcher process (pass queue as argument)
    _batcher_process = mp.Process(
        target=start_batcher_process,
        args=(_event_queue, _stop_event),
        name="EmbeddingBatcher",
        daemon=True
    )
    _batcher_process.start()
    
    logger.info(f"Embedding batcher process started (PID {_batcher_process.pid})")


def stop_embedding_batcher():
    """Stop the embedding batcher process."""
    global _batcher_process, _stop_event
    
    if _batcher_process is None:
        return
    
    logger.info("Stopping embedding batcher process...")
    
    if _stop_event:
        _stop_event.set()
    
    # Wait for process to finish (with timeout)
    _batcher_process.join(timeout=10)
    
    if _batcher_process.is_alive():
        logger.warning("Batcher process did not stop gracefully, terminating...")
        _batcher_process.terminate()
        _batcher_process.join(timeout=5)
        
        if _batcher_process.is_alive():
            logger.error("Batcher process did not terminate, killing...")
            _batcher_process.kill()
    
    logger.info("Embedding batcher process stopped")


def queue_events_for_embedding(
    investigation_id: UUID,
    user_id: int,
    event_ids: List[int],
):
    """
    Queue events for embedding.
    
    Events are added to a multiprocessing queue and batched by a background process.
    
    Args:
        investigation_id: Investigation UUID
        user_id: User ID (for LLM config lookup)
        event_ids: List of event IDs to embed
    """
    global _event_queue
    if _event_queue is None:
        logger.warning("Event queue not initialized, events will not be queued")
        return
    
    for event_id in event_ids:
        _event_queue.put((investigation_id, user_id, event_id))
    
    logger.debug(
        f"Queued {len(event_ids):,} events for batching "
        f"(investigation {investigation_id})"
    )


def get_queue_size() -> int:
    """Get current queue size."""
    global _event_queue
    if _event_queue is None:
        return 0
    try:
        return _event_queue.qsize()
    except:
        return 0


__all__ = [
    "initialize_event_queue",
    "get_event_queue",
    "set_event_queue",
    "start_embedding_batcher",
    "stop_embedding_batcher",
    "queue_events_for_embedding",
    "get_queue_size",
]
