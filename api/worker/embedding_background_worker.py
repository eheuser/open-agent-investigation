"""
Dedicated background worker for embedding generation.

This worker runs independently from the main worker pool and continuously
processes embedding jobs without being blocked by parsing or agent jobs.

Supports multiple worker processes for higher throughput.
Number of workers controlled by NUM_EMBEDDING_WORKERS environment variable.
"""

import asyncio
import uuid as uuid_pkg
import signal
import multiprocessing as mp
import time
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, and_, text

from app.models.job_embedding import EmbeddingJob
from app.models.job_parsing import JobStatus
from app.core.config import settings
from worker.embedding_worker import claim_embedding_job, process_embedding_job

from app.utils.log_setup import get_logger
from app.utils.http_log_handler import setup_worker_logging

logger = get_logger(__name__)

# Number of embedding worker processes (configurable)
NUM_EMBEDDING_WORKERS = settings.num_embedding_workers or 1

# Create database engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=2,  # Small pool for background worker
    max_overflow=0,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def recover_stale_embedding_jobs(db: AsyncSession):
    """
    Recover stale embedding jobs that have been running for too long.
    
    Args:
        db: Database session
    """
    stale_threshold = datetime.utcnow() - timedelta(minutes=30)

    result = await db.execute(
        update(EmbeddingJob)
        .where(
            and_(
                EmbeddingJob.status == JobStatus.RUNNING,
                EmbeddingJob.started_at < stale_threshold,
            )
        )
        .values(
            status=JobStatus.PENDING,
            worker_id=None,
            started_at=None,
            error_message="Job was stale (worker likely crashed), resetting to pending",
        )
    )

    count = result.rowcount
    await db.commit()

    if count > 0:
        logger.warning(f"Recovered {count} stale embedding job(s)")
    else:
        logger.debug("No stale embedding jobs found")


async def embedding_worker_loop(worker_id: uuid_pkg.UUID, worker_index: int):
    """
    Main loop for the dedicated embedding background worker.
    
    Continuously processes embedding jobs without being blocked by
    parsing or agent jobs.
    
    Args:
        worker_id: Unique worker ID
        worker_index: Worker index (for logging)
    """
    logger.info(f"Embedding worker {worker_index} starting (ID: {worker_id})")

    last_stale_check = datetime.utcnow()
    stale_check_interval_minutes = 5

    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Try to claim an embedding job
                embedding_job = await claim_embedding_job(db, worker_id)

                if embedding_job:
                    # Process embedding job
                    try:
                        await process_embedding_job(db, embedding_job)
                    except asyncio.CancelledError:
                        logger.info("Embedding job cancelled")
                        # Mark job as failed
                        embedding_job.status = JobStatus.FAILED
                        embedding_job.finished_at = datetime.utcnow()
                        embedding_job.error_message = "Job cancelled"
                        await db.commit()
                    except Exception as e:
                        logger.error(f"Embedding job processing failed: {e}", exc_info=True)
                        # Error handling is done inside process_embedding_job
                    continue

                # No jobs available, wait before polling again
                await asyncio.sleep(2.0)  # Poll less frequently than main workers

                # Periodically check for stale jobs
                now = datetime.utcnow()
                if (now - last_stale_check).total_seconds() > (stale_check_interval_minutes * 60):
                    logger.debug("Running periodic stale job check...")
                    await recover_stale_embedding_jobs(db)
                    last_stale_check = now

        except Exception as e:
            logger.error(f"Embedding worker loop error: {e}", exc_info=True)
            await asyncio.sleep(5.0)  # Wait longer on error


async def cleanup_embedding_jobs(worker_id: uuid_pkg.UUID):
    """
    Clean up any embedding jobs claimed by this worker on shutdown.
    
    Args:
        worker_id: Worker UUID to clean up
    """
    logger.info(f"Cleaning up embedding jobs claimed by worker {worker_id}...")

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(EmbeddingJob)
                .where(
                    and_(
                        EmbeddingJob.status == JobStatus.RUNNING,
                        EmbeddingJob.worker_id == worker_id,
                    )
                )
                .values(
                    status=JobStatus.PENDING,
                    worker_id=None,
                    started_at=None,
                    error_message="Embedding worker shutdown, job reset to pending",
                )
            )

            count = result.rowcount
            await db.commit()

            if count > 0:
                logger.info(f"Reset {count} embedding job(s) claimed by worker {worker_id}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)


def embedding_worker_process(worker_id: uuid_pkg.UUID, worker_index: int):
    """
    Embedding worker process entry point.
    
    Args:
        worker_id: Unique worker ID
        worker_index: Worker index (for logging)
    """
    # Set process name
    mp.current_process().name = f"EmbeddingWorker-{worker_index}"
    
    # Configure HTTP logging
    setup_worker_logging(
        api_host=settings.api_host,
        api_port=settings.api_port,
        process_name=f"EmbeddingWorker-{worker_index}"
    )

    logger.info(f"Embedding worker {worker_index} starting (ID: {worker_id})")

    # Create new event loop for this process
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run the worker loop
    try:
        loop.run_until_complete(embedding_worker_loop(worker_id, worker_index))
    except KeyboardInterrupt:
        logger.info(f"Embedding worker {worker_index} interrupted")
    finally:
        # Cleanup
        loop.run_until_complete(cleanup_embedding_jobs(worker_id))
        loop.close()
        logger.info(f"Embedding worker {worker_index} stopped")


def main():
    """
    Entry point for the dedicated embedding background worker manager.
    
    Spawns multiple embedding worker processes for parallel embedding generation.
    Number of workers controlled by NUM_EMBEDDING_WORKERS environment variable.
    """
    logger.info(f"Starting {NUM_EMBEDDING_WORKERS} embedding background worker(s)...")

    # Create worker processes
    workers = []
    worker_ids = []

    for i in range(NUM_EMBEDDING_WORKERS):
        worker_id = uuid_pkg.uuid4()
        worker_ids.append(worker_id)

        p = mp.Process(
            target=embedding_worker_process,
            args=(worker_id, i),
            name=f"EmbeddingWorker-{i}"
        )
        p.start()
        workers.append(p)
        logger.info(f"Started embedding worker {i} (PID {p.pid})")

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down embedding workers...")
        
        # Wait for workers to finish
        for i, p in enumerate(workers):
            p.join(timeout=10)
            if p.is_alive():
                logger.warning(f"Embedding worker {i} did not stop gracefully, terminating...")
                p.terminate()
                p.join(timeout=5)
                if p.is_alive():
                    logger.error(f"Embedding worker {i} did not terminate, killing...")
                    p.kill()
        
        # Cleanup jobs
        for worker_id in worker_ids:
            asyncio.run(cleanup_embedding_jobs(worker_id))
        
        # Dispose engine
        asyncio.run(engine.dispose())
        
        logger.info("All embedding workers stopped")
        exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Monitor workers and restart if they crash
    try:
        while True:
            for i, p in enumerate(workers):
                if not p.is_alive():
                    logger.warning(f"Embedding worker {i} crashed, restarting...")

                    # Cleanup old worker's jobs
                    asyncio.run(cleanup_embedding_jobs(worker_ids[i]))

                    # Create new worker
                    worker_id = uuid_pkg.uuid4()
                    worker_ids[i] = worker_id

                    new_worker = mp.Process(
                        target=embedding_worker_process,
                        args=(worker_id, i),
                        name=f"EmbeddingWorker-{i}",
                    )
                    new_worker.start()
                    workers[i] = new_worker
                    logger.info(f"Restarted embedding worker {i} (PID {new_worker.pid})")

            # Sleep before next check
            time.sleep(5)

    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    # Required for multiprocessing on Windows
    mp.set_start_method("spawn", force=True)
    main()
