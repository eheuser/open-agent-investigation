from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import update, select, or_
from datetime import datetime

from .core.config import settings
from .core.database import get_db, init_db
from .models.job_parsing import ParsingJob, JobStatus
from .models.job_agent import AgentJob
from .models.job_embedding import EmbeddingJob
from .routers import (
    auth,
    investigations,
    artifacts,
    mcp,
    events,
    agents,
    tags,
    audit,
    llm_config,
    chat,
    chat_messages,
    timeline,
    jobs,
    embeddings,
    investigation_choices,
    reports,
    logs,
    playbooks,
    analysis,
    system,
)
from .utils.log_setup import get_logger
from .services.log_streaming import setup_log_streaming
from .services.embedding_pool import start_pool_flusher, stop_pool_flusher, flush_embedding_pool

logger = get_logger(__name__)

# Create FastAPI instance
app = FastAPI(
    title="Open Agent Investigation API", version="0.1.0", docs_url="/docs", redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(investigations.router, prefix="/api/v1/investigations", tags=["investigations"])
app.include_router(artifacts.router, prefix="/api/v1/artifacts", tags=["artifacts"])
app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
app.include_router(mcp.router, prefix="/api/v1/mcp", tags=["mcp"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(tags.router, prefix="/api/v1/tags", tags=["tags"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(llm_config.router, prefix="/api/v1/llm-config", tags=["llm-config"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(chat_messages.router, prefix="/api/v1/chat", tags=["chat-messages"])
app.include_router(timeline.router, tags=["timeline"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(embeddings.router)  # Prefix already defined in router
app.include_router(investigation_choices.router, tags=["investigation-choices"])
app.include_router(reports.router, tags=["reports"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["logs"])
app.include_router(playbooks.router, tags=["playbooks"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["analysis"])
app.include_router(system.router, prefix="/api/v1", tags=["system"])


@app.get("/health")
async def health(db=Depends(get_db)):
    """
    Health check endpoint that verifies database connectivity.

    Args:
        db: Database session dependency injected by FastAPI (default: Depends(get_db)). Used to execute a simple query to test the connection.

    Returns:
        dict: A JSON-serializable dictionary containing:
            - "status": `"ok"` if the database query succeeds, otherwise `"error"`.
            - "database": `"connected"` when the query is successful, `"disconnected"` on failure.
            - "error": (optional) String representation of the exception raised when the connection test fails. This key is omitted on success.

    Raises:
        None explicitly; any exception during the database check is caught and reported in the returned dictionary.
    """
    try:
        # Test database connection
        await db.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": "disconnected", "error": str(e)}


@app.get("/metrics")
async def metrics():
    """
    Fetch Prometheus metrics if the feature is enabled.\n\nReturns:\n    fastapi.Response: A response containing the latest Prometheus metrics when `settings.prometheus_enabled` is True.\n    dict: A JSON object with an `error` key indicating that metrics collection is disabled when the setting is False.
    """
    if settings.prometheus_enabled:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    return {"error": "Metrics disabled"}


@app.on_event("startup")
async def startup_event():
    """
    Initialize resources and log configuration details when the FastAPI application starts.

    This coroutine is registered as a startup event handler. It performs the following actions:

    * Logs the start of the Open Agent Investigation API.
    * Displays the database host extracted from `settings.database_url` (or indicates that it is configured without a host).
    * Indicates whether a JWT secret has been provided.
    * Notes that tables are created externally via `bootstrap.sql` rather than by SQLAlchemy.
    * Cancels any running or pending jobs from previous service instances.
    * Confirms that the chat router is enabled.
    * Signals that the API is ready to accept requests.

    No return value. Raises any exception propagated from logging or settings access.
    """
    # Initialize log streaming before any other logging
    setup_log_streaming()

    logger.info("Starting Open Agent Investigation API...")
    logger.info(
        f"Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'configured'}"
    )
    logger.info(f"JWT Secret: {'configured' if settings.jwt_secret else 'missing'}")
    # Note: Tables are created by bootstrap.sql, not by SQLAlchemy

    # Clean up any running/pending jobs from previous service instances
    await cleanup_stale_jobs()

    # Start the embedding pool background flusher
    # Wrap get_db generator in a context manager for the pool flusher
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def get_db_session():
        async for db in get_db():
            yield db
            break

    await start_pool_flusher(get_db_session)
    logger.info("Embedding pool flusher started")

    logger.info("Chat router enabled")
    logger.info("Log streaming enabled")
    logger.info("API ready")


async def cleanup_stale_jobs():
    """
    Cancel or mark as failed any jobs that are in PENDING or RUNNING state.

    This function is called on application startup to handle jobs that may have been
    left in an incomplete state due to service crashes or restarts. It:

    * Marks all RUNNING jobs as FAILED with an appropriate error message
    * Marks all PENDING jobs as FAILED with an appropriate error message
    * Sets the finished_at timestamp to the current time
    * Logs the number of jobs cleaned up for both parsing and agent jobs

    This prevents jobs from hanging indefinitely and cluttering the job queue.

    Returns:
        None

    Raises:
        May raise database exceptions if the update operations fail.
    """
    try:
        # Get a database session
        async for db in get_db():
            try:
                # Clean up parsing jobs
                parsing_result = await db.execute(
                    select(ParsingJob).where(
                        or_(
                            ParsingJob.status == JobStatus.RUNNING,
                            ParsingJob.status == JobStatus.PENDING,
                        )
                    )
                )
                stale_parsing_jobs = parsing_result.scalars().all()

                if stale_parsing_jobs:
                    await db.execute(
                        update(ParsingJob)
                        .where(
                            or_(
                                ParsingJob.status == JobStatus.RUNNING,
                                ParsingJob.status == JobStatus.PENDING,
                            )
                        )
                        .values(
                            status=JobStatus.FAILED,
                            finished_at=datetime.utcnow(),
                            error_message="Job cancelled due to service restart",
                        )
                    )
                    logger.info(f"Cleaned up {len(stale_parsing_jobs)} stale parsing job(s)")

                # Clean up agent jobs
                agent_result = await db.execute(
                    select(AgentJob).where(
                        or_(
                            AgentJob.status == JobStatus.RUNNING,
                            AgentJob.status == JobStatus.PENDING,
                        )
                    )
                )
                stale_agent_jobs = agent_result.scalars().all()

                if stale_agent_jobs:
                    await db.execute(
                        update(AgentJob)
                        .where(
                            or_(
                                AgentJob.status == JobStatus.RUNNING,
                                AgentJob.status == JobStatus.PENDING,
                            )
                        )
                        .values(
                            status=JobStatus.FAILED,
                            finished_at=datetime.utcnow(),
                            error_message="Job cancelled due to service restart",
                        )
                    )
                    logger.info(f"Cleaned up {len(stale_agent_jobs)} stale agent job(s)")

                # Clean up embedding jobs
                embedding_result = await db.execute(
                    select(EmbeddingJob).where(
                        or_(
                            EmbeddingJob.status == JobStatus.RUNNING,
                            EmbeddingJob.status == JobStatus.PENDING,
                        )
                    )
                )
                stale_embedding_jobs = embedding_result.scalars().all()

                if stale_embedding_jobs:
                    await db.execute(
                        update(EmbeddingJob)
                        .where(
                            or_(
                                EmbeddingJob.status == JobStatus.RUNNING,
                                EmbeddingJob.status == JobStatus.PENDING,
                            )
                        )
                        .values(
                            status=JobStatus.FAILED,
                            finished_at=datetime.utcnow(),
                            error_message="Job cancelled due to service restart",
                        )
                    )
                    logger.info(f"Cleaned up {len(stale_embedding_jobs)} stale embedding job(s)")

                # Commit the changes
                await db.commit()

                if not stale_parsing_jobs and not stale_agent_jobs and not stale_embedding_jobs:
                    logger.info("No stale jobs found")

            finally:
                await db.close()
            break  # Exit after first iteration

    except Exception as e:
        logger.error(f"Error cleaning up stale jobs: {e}")
        # Don't raise - we don't want to prevent startup


@app.on_event("shutdown")
async def shutdown_event():
    """
    Performs cleanup actions when the FastAPI application is shutting down. Logs a shutdown message and can be extended to close resources such as database connections or background tasks. Returns nothing.
    """
    logger.info("Shutting down Open Agent Investigation API...")

    # Flush any remaining pooled events
    try:
        async for db in get_db():
            try:
                jobs_created = await flush_embedding_pool(db)
                if jobs_created > 0:
                    logger.info(f"Flushed {jobs_created} embedding jobs on shutdown")
            finally:
                await db.close()
            break
    except Exception as e:
        logger.error(f"Error flushing embedding pool on shutdown: {e}")

    # Stop the background flusher
    await stop_pool_flusher()
    logger.info("Embedding pool flusher stopped")
