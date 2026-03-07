from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from uuid import UUID

from ..deps import get_db, get_current_user
from ..models.user import User
from ..models.job_parsing import ParsingJob, JobStatus
from ..models.job_agent import AgentJob
from ..crud.investigation import check_investigation_access

router = APIRouter()


@router.get("/parsing/{job_id}")
async def get_parsing_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retrieve detailed status information for a specific parsing job.

    Args:
        job_id: Identifier of the parsing job to query.
        db: Asynchronous SQLAlchemy session injected via FastAPI dependency injection.
        user: The currently authenticated user provided by the `get_current_user` dependency.

    Raises:
        HTTPException: If no job with the given `job_id` exists (404 Not Found).
        HTTPException: Propagated from `check_investigation_access` when the user lacks permission to view the associated investigation.

    Returns:
        dict: A mapping containing comprehensive job details:
            - `job_id` (int): The job identifier.
            - `investigation_id` (str): UUID of the related investigation.
            - `artifact_id` (int | None): Identifier of the artifact being processed, if applicable.
            - `status` (str): Current status value from :class:`JobStatus`.
            - `worker_id` (str | None): UUID of the worker handling the job, or `None` if not assigned.
            - `created_at` (str | None): ISO-8601 timestamp when the job was created.
            - `started_at` (str | None): ISO-8601 timestamp when processing began.
            - `finished_at` (str | None): ISO-8601 timestamp when processing completed.
            - `error_message` (str | None): Error details if the job failed.
            - `event_count` (int | None): Number of events generated for the artifact when the job has finished successfully; `None` if not applicable.
    """
    # Fetch job
    result = await db.execute(select(ParsingJob).where(ParsingJob.job_id == job_id))
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Check access to investigation
    await check_investigation_access(db, job.investigation_id, user)

    # Count events if completed
    event_count = None
    if job.status == JobStatus.COMPLETED:
        from sqlalchemy import text

        try:
            count_query = text(
                """
                SELECT COUNT(*) FROM events 
                WHERE investigation_id = :investigation_id 
                AND artifact_id = :artifact_id
            """
            )
            count_result = await db.execute(
                count_query,
                {"investigation_id": str(job.investigation_id), "artifact_id": job.artifact_id},
            )
            event_count = count_result.scalar()
        except Exception:
            event_count = 0

    return {
        "job_id": job.job_id,
        "investigation_id": str(job.investigation_id),
        "artifact_id": job.artifact_id,
        "status": job.status.value,
        "worker_id": str(job.worker_id) if job.worker_id else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": job.error_message,
        "event_count": event_count,
    }


@router.get("/parsing/investigation/{investigation_id}")
async def list_parsing_jobs(
    investigation_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List all parsing jobs for a given investigation with pagination.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation whose parsing jobs should be listed.
    limit: int, optional (default=100)
        Maximum number of jobs to return. Must be a positive integer.
    offset: int, optional (default=0)
        Number of jobs to skip before starting to collect the result set. Used for pagination.
    db: AsyncSession, injected by FastAPI Depends(get_db)
        Asynchronous SQLAlchemy session used to query the database.
    user: User, injected by FastAPI Depends(get_current_user)
        The currently authenticated user; access to the investigation is verified.

    Returns
    -------
    dict
        A dictionary containing:
            - `jobs` (list[dict]): List of job summaries, each with keys `job_id`, `artifact_id`,
              `status`, `created_at`, `started_at`, `finished_at`, and `error_message`.
            - `total` (int): Total number of parsing jobs for the investigation.
            - `limit` (int): The limit value used in the query.
            - `offset` (int): The offset value used in the query.

    Raises
    ------
    HTTPException
        If the user does not have access to the specified investigation.
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Fetch jobs
    result = await db.execute(
        select(ParsingJob)
        .where(ParsingJob.investigation_id == investigation_id)
        .order_by(ParsingJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    jobs = result.scalars().all()

    # Get total count
    from sqlalchemy import func

    count_result = await db.execute(
        select(func.count(ParsingJob.job_id)).where(ParsingJob.investigation_id == investigation_id)
    )
    total = count_result.scalar()

    return {
        "jobs": [
            {
                "job_id": job.job_id,
                "artifact_id": job.artifact_id,
                "status": job.status.value,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "error_message": job.error_message,
            }
            for job in jobs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/agent/{job_id}")
async def get_agent_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retrieve detailed status information for a specific agent job.

    Args:
        job_id: Identifier of the agent job to query.
        db: Asynchronous SQLAlchemy session injected via FastAPI dependency.
        user: Currently authenticated user injected via FastAPI dependency.

    Returns:
        A dictionary containing comprehensive job details, including identifiers,
        policy and rule information, timestamps, status, any error message, and,
        when the job has completed, the count of timeline entries created for the
        associated investigation. Timestamp fields are ISO-8601 strings or `None`
        if unavailable; `worker_id` is returned as a string when present.

    Raises:
        HTTPException: If no job with the given `job_id` exists (404 Not Found).
        Any exception raised by `check_investigation_access` if the user lacks
        permission to view the investigation linked to the job.
    """
    # Fetch job
    result = await db.execute(select(AgentJob).where(AgentJob.job_id == job_id))
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Check access to investigation
    await check_investigation_access(db, job.investigation_id, user)

    # Count timeline entries created if completed
    timeline_entries_created = None
    if job.status == JobStatus.COMPLETED:
        from sqlalchemy import text

        try:
            # Count timeline entries
            timeline_query = text(
                """
                SELECT COUNT(*) FROM timeline_entries 
                WHERE investigation_id = :investigation_id
            """
            )
            timeline_result = await db.execute(
                timeline_query, {"investigation_id": str(job.investigation_id)}
            )
            timeline_entries_created = timeline_result.scalar()
        except Exception:
            timeline_entries_created = 0

    return {
        "job_id": job.job_id,
        "investigation_id": str(job.investigation_id),
        "user_id": job.user_id,
        "policy_id": job.policy_id,
        "rule_values": job.rule_values,
        "status": job.status.value,
        "worker_id": str(job.worker_id) if job.worker_id else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": job.error_message,
        "timeline_entries_created": timeline_entries_created,
    }


@router.get("/agent/investigation/{investigation_id}")
async def list_agent_jobs(
    investigation_id: UUID,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List all agent jobs for a given investigation with pagination support.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation whose agent jobs should be retrieved.
    limit: int, optional
        Maximum number of jobs to return. Defaults to `100`.
    offset: int, optional
        Number of jobs to skip before starting to collect the result set. Defaults to `0`.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session injected by FastAPI's dependency system.
    user: User, optional
        The currently authenticated user, injected by FastAPI's dependency system.

    Returns
    -------
    dict
        A dictionary containing:

        - `jobs` (list[dict]): List of job summaries. Each summary includes:
            * `job_id` (UUID): Unique identifier of the job.
            * `user_id` (UUID): Identifier of the user who created the job.
            * `policy_id` (UUID | None): Associated policy identifier, if any.
            * `status` (str): Current status of the job (e.g., `"pending"`, `"running"`, `"completed"`, `"failed"`).
            * `created_at` (str | None): ISO-8601 timestamp when the job was created.
            * `started_at` (str | None): ISO-8601 timestamp when the job started execution.
            * `finished_at` (str | None): ISO-8601 timestamp when the job finished execution.
            * `error_message` (str | None): Error details if the job failed.
        - `total` (int): Total number of agent jobs for the investigation.
        - `limit` (int): The limit value used in the query.
        - `offset` (int): The offset value used in the query.

    Raises
    ------
    HTTPException
        If the authenticated user does not have access to the specified investigation.
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Fetch jobs
    result = await db.execute(
        select(AgentJob)
        .where(AgentJob.investigation_id == investigation_id)
        .order_by(AgentJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    jobs = result.scalars().all()

    # Get total count
    from sqlalchemy import func

    count_result = await db.execute(
        select(func.count(AgentJob.job_id)).where(AgentJob.investigation_id == investigation_id)
    )
    total = count_result.scalar()

    return {
        "jobs": [
            {
                "job_id": job.job_id,
                "user_id": job.user_id,
                "policy_id": job.policy_id,
                "status": job.status.value,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "error_message": job.error_message,
            }
            for job in jobs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/agent/{job_id}/stop")
async def stop_agent_job(
    job_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Stop an agent job either gracefully or forcefully.

    Args:
        job_id (int): Identifier of the agent job to stop.
        force (bool, optional): When `True` the job is marked as failed immediately; when `False` a graceful stop request is sent to the worker. Defaults to `False`.
        db (AsyncSession): Database session provided by FastAPI dependency injection.
        user (User): The currently authenticated user, injected via dependency.

    Returns:
        dict: A JSON-serialisable dictionary containing:
            - `status` (str): Either `"force_stopped"` when `force=True` or `"stop_requested"` for a graceful stop.
            - `job_id` (int): The identifier of the job that was targeted.
            - `message` (str): Human-readable description of the outcome.

    Raises:
        HTTPException: If the job does not exist (404) or is not in a running state (400).
        HTTPException: Propagated from :func:`check_investigation_access` when the user lacks permission to access the investigation associated with the job.

    Notes:
        * A graceful stop updates the `metadata` column of the `jobs_agents` table, setting `stop_requested` to `true`. The worker process will finish its current turn and then terminate.
        * If the worker does not acknowledge the stop request within 30 seconds, a background task automatically marks the job as failed.
        * A forced stop directly updates the job status to :class:`JobStatus.FAILED`, records the current timestamp in `finished_at` and stores an error message indicating that the job was forcefully stopped by the user.
    """
    # Fetch job
    result = await db.execute(select(AgentJob).where(AgentJob.job_id == job_id))
    job = result.scalars().first()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Check access to investigation
    await check_investigation_access(db, job.investigation_id, user)

    # Check if job is running
    if job.status != JobStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not running (status: {job.status.value})",
        )

    if force:
        # Forcefully mark job as failed
        await db.execute(
            update(AgentJob)
            .where(AgentJob.job_id == job_id)
            .values(
                status=JobStatus.FAILED,
                finished_at=text("NOW()"),
                error_message="Job forcefully stopped by user",
            )
        )
        await db.commit()

        return {
            "status": "force_stopped",
            "job_id": job_id,
            "message": "Job forcefully stopped. Worker process will detect and terminate.",
        }
    else:
        # Set stop signal in metadata (graceful stop)
        await db.execute(
            text(
                """
                UPDATE jobs_agents
                SET metadata = jsonb_set(
                    COALESCE(metadata, '{}'),
                    '{stop_requested}',
                    'true'
                )
                WHERE job_id = :job_id
            """
            ),
            {"job_id": job_id},
        )
        await db.commit()

        # Schedule force-stop after 30 seconds if job is still running
        import asyncio
        from datetime import datetime, timedelta

        async def force_stop_after_timeout():
            """
            Force-stop a running agent job if it does not acknowledge a graceful stop request within 30 seconds.\n\nThe coroutine sleeps for thirty seconds, then re-queries the database for the job identified by `job_id`. If the job is still in the `RUNNING` state after this interval, its status is updated to `FAILED`, the completion timestamp is set to the current UTC time, and an error message indicating a forced termination is recorded.\n\nThis function does not return any value. It may raise database-related exceptions if the underlying SQLAlchemy operations fail.
            """
            await asyncio.sleep(30)

            # Re-fetch job to check if it's still running
            async with db.begin():
                result = await db.execute(select(AgentJob).where(AgentJob.job_id == job_id))
                job_check = result.scalars().first()

                if job_check and job_check.status == JobStatus.RUNNING:
                    # Job is still running after 30 seconds - force stop
                    await db.execute(
                        update(AgentJob)
                        .where(AgentJob.job_id == job_id)
                        .values(
                            status=JobStatus.FAILED,
                            finished_at=datetime.utcnow(),
                            error_message="Job did not respond to stop signal within 30 seconds (force stopped)",
                        )
                    )
                    await db.commit()

        # Start background task (fire and forget)
        asyncio.create_task(force_stop_after_timeout())

        return {
            "status": "stop_requested",
            "job_id": job_id,
            "message": "Stop signal sent to agent. It will finish its current turn and stop. If it doesn't respond within 30 seconds, it will be force-stopped.",
        }