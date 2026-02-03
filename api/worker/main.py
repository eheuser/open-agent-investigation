import asyncio
import logging
import time
import uuid as uuid_pkg
import multiprocessing as mp
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, cast
import aiohttp

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, and_, text

from app.models.job_parsing import ParsingJob, JobStatus
from app.models.job_agent import AgentJob
from app.models.llm_config import LLMProviderConfig
from app.models.investigation import Investigation
from app.core.config import settings
from app.crud import investigation as inv_crud
from app.crud.investigation_choice import create_investigation_choices_bulk
from app.schemas.investigation_choice import InvestigationChoiceCreate
from worker.parsers import parse_artifact
from worker.agents.assistant_agent import AssistantAgent
from worker.core.llm_client import LLMClient
from worker.agents.field_dictionary_finalizer import finalize_field_dictionary

from app.utils.log_setup import get_logger
from app.utils.http_log_handler import setup_worker_logging

logger = get_logger(__name__)

MAIN_WORKER_ID = uuid_pkg.uuid4()

NUM_WORKERS = min(mp.cpu_count(), 4)


async def generate_field_dictionary_background(investigation_id: uuid_pkg.UUID):
    """
    Generate a field-dictionary for an investigation in the background.

    This coroutine is invoked after parsing has finished for a given
    investigation. It retrieves the investigation’s owner, obtains the
    owner’s active LLM provider configuration, creates an `LLMClient`,
    and calls :func:`worker.agents.field_dictionary_finalizer.finalize_field_dictionary`
    to generate LLM descriptions for pending fields discovered during parsing.
    A rough count of processed fields is logged and a WebSocket notification
    is sent to inform connected clients that the dictionary is ready.

    Args:
        investigation_id: The UUID of the investigation whose field dictionary
            should be generated.

    Returns:
        `None`.  All results are persisted to the database and communicated via
        logging and WebSocket messages.

    Raises:
        Any exception raised during execution is caught internally; the error
        details are logged with stack trace information, but the coroutine does
        not propagate the exception to callers.
    """
    try:
        logger.info(
            f"Starting background field dictionary generation for investigation {investigation_id}"
        )

        async with AsyncSessionLocal() as db:
            # Get investigation owner to fetch their LLM config
            result = await db.execute(
                select(Investigation).where(Investigation.investigation_id == investigation_id)
            )
            investigation = result.scalar_one_or_none()

            if not investigation:
                logger.warning(
                    f"Investigation {investigation_id} not found, skipping field dictionary generation"
                )
                return

            user_id = getattr(investigation, "owner_user_id", None)
            if not user_id:
                logger.warning(
                    f"Investigation {investigation_id} has no owner, skipping field dictionary generation"
                )
                return

            # Get user's active LLM config
            result = await db.execute(
                select(LLMProviderConfig)
                .where(LLMProviderConfig.user_id == user_id)
                .where(LLMProviderConfig.is_active == True)
            )
            llm_config = result.scalar_one_or_none()

            if not llm_config:
                logger.warning(
                    f"No active LLM config for user {user_id}, skipping field dictionary generation. "
                    f"Dictionary will be generated on first agent run."
                )
                return

            # Create LLM client
            llm_endpoint = cast(str, llm_config.api_endpoint)
            llm_model = cast(str, llm_config.model_name)
            api_key_raw = llm_config.api_key
            llm_api_key = cast(str, api_key_raw) if api_key_raw is not None else None
            llm_max_context = cast(int, llm_config.max_context_length)

            llm_client = LLMClient(
                endpoint=llm_endpoint,
                model=llm_model,
                api_key=llm_api_key,
            )

            # OPTIMIZED: Use new finalizer that only processes pending fields
            logger.info(
                f"Finalizing field dictionary for investigation {investigation_id} using {llm_model}..."
            )

            stats = await finalize_field_dictionary(
                db=db,
                investigation_id=str(investigation_id),
                llm_client=llm_client,
                max_output_tokens=min(16_384, int(llm_max_context * 0.75)),
            )

            fields_processed = stats.get("fields_processed", 0)
            event_types = stats.get("event_types_processed", 0)

            logger.info(
                f"Field dictionary finalization complete for investigation {investigation_id}. "
                f"Processed {fields_processed:,} fields across {event_types:,} event types."
            )

            # Notify WebSocket clients that field dictionary is ready
            await notify_websocket_clients(
                investigation_id=investigation_id,
                message={
                    "type": "field_dictionary_ready",
                    "investigation_id": str(investigation_id),
                    "field_count": fields_processed,
                    "event_types": event_types,
                },
            )

    except Exception as e:
        logger.error(
            f"Background field dictionary generation failed for investigation {investigation_id}: {e}",
            exc_info=True,
        )
        # Don't fail - this is a background optimization task
        # Field dictionary will be generated on first agent run if this fails


# Database engine for main process
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def check_and_clear_parsing_lock(db: AsyncSession, investigation_id: uuid_pkg.UUID):
    """
    Check for remaining parsing jobs associated with an investigation and, if none are found, release the investigation's parsing lock while notifying clients and initiating background field-dictionary generation.

    Args:
        db: An active asynchronous SQLAlchemy session used to query `ParsingJob` records.
        investigation_id: The UUID of the investigation whose parsing jobs are being inspected.

    Raises:
        Any exception raised by the database queries or CRUD operations will propagate to the caller.
    """
    # Count pending or running parsing jobs for this investigation
    result = await db.execute(
        select(ParsingJob)
        .where(ParsingJob.investigation_id == investigation_id)
        .where(ParsingJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
    )
    remaining_jobs = result.scalars().all()

    if len(remaining_jobs) == 0:
        # No more parsing jobs, clear the lock
        await inv_crud.set_parsing_lock(db, investigation_id, locked=False)
        logger.info(f"Cleared parsing lock for investigation {investigation_id}")

        # Notify WebSocket clients that parsing is complete
        await notify_websocket_clients(
            investigation_id=investigation_id,
            message={
                "type": "parsing_complete",
                "investigation_id": str(investigation_id),
            },
        )

        # Trigger field dictionary generation in background
        # This will pre-populate the field_dictionary table for faster agent startup
        asyncio.create_task(generate_field_dictionary_background(investigation_id))
    else:
        logger.debug(
            f"Investigation {investigation_id} still has {len(remaining_jobs):,} parsing job(s) pending/running"
        )


async def claim_parsing_job(db: AsyncSession, worker_id: uuid_pkg.UUID) -> Optional[ParsingJob]:
    """
    Atomically claim a pending parsing job for execution by the specified worker.

    This function queries the database for the earliest `ParsingJob` in the `PENDING` state,
    acquires a row-level lock that skips already locked rows to allow safe concurrent
    workers, and updates the job's status to `RUNNING` while recording the claiming
    worker's identifier and start timestamp. The changes are committed atomically and
    the refreshed ORM instance is returned.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used for all database
            interactions within this operation.
        worker_id: The unique identifier of the worker attempting to claim a job; stored
            on the job record as `worker_id` when claimed.

    Returns:
        The claimed :class:`ParsingJob` instance with its status set to `RUNNING` and
        associated metadata updated, or `None` if no pending jobs are available at the
        time of the query.
    """
    # Find first pending job
    result = await db.execute(
        select(ParsingJob)
        .where(ParsingJob.status == JobStatus.PENDING)
        .order_by(ParsingJob.created_at)
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

    logger.debug(f"Claimed parsing job {job.job_id} for artifact {job.artifact_id}")

    return job


async def claim_agent_job(db: AsyncSession, worker_id: uuid_pkg.UUID) -> Optional[AgentJob]:
    """
    Atomically claims a pending :class:`AgentJob` from the database for the specified worker.

    The function queries for the earliest job with status `PENDING` using a
    SELECT … FOR UPDATE query with `skip_locked=True` to avoid blocking on jobs
    that are already being processed by other workers. If such a job is found,
    its status is updated to `RUNNING`, the `worker_id` and `started_at`
    fields are populated, and the changes are committed atomically. The refreshed
    instance is then returned; if no pending jobs exist, `None` is returned.

    Args:
        db: An active :class:`AsyncSession` used to execute the query and commit
            the transaction.
        worker_id: The UUID of the worker that will claim the job.

    Returns:
        The claimed :class:`AgentJob` instance with updated status and timestamps,
        or `None` if no pending jobs are available.
    """
    # Find first pending job
    result = await db.execute(
        select(AgentJob)
        .where(AgentJob.status == JobStatus.PENDING)
        .order_by(AgentJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
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

    logger.info(f"Claimed agent job {job.job_id} for policy {job.policy_id}")

    return job


async def notify_websocket_clients(
    investigation_id: uuid_pkg.UUID,
    message: dict,
    max_retries: int = 3,
):
    """
    Send a notification to all WebSocket clients connected to the specified investigation.

    This helper performs a best-effort broadcast of a JSON message to the API server’s websocket endpoint.
    If the API server is unavailable or returns an error, the function will retry up to `max_retries`
    times using exponential backoff and then exit silently. No exception is propagated to the caller;
    the function logs warnings for diagnostic purposes.

    Args:
        investigation_id: The UUID of the investigation whose clients should receive the message.
        message: A dictionary representing the payload to broadcast (e.g., `{'type': 'update', ...}`).
        max_retries: Maximum number of retry attempts before giving up. Defaults to 3.

    Returns:
        None. The function logs success or failure but does not return a value.

    Raises:
        No exceptions are raised; all errors are caught and logged internally.
    """
    # Get API base URL from settings
    api_host = settings.api_host
    api_port = settings.api_port
    url = f"http://{api_host}:{api_port}/api/v1/chat/broadcast/{investigation_id}"

    for attempt in range(max_retries):
        try:
            logger.debug(
                f"Broadcasting message to {url}: {message.get('type')} (attempt {attempt + 1}/{max_retries})"
            )

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=message, timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        logger.warning(
                            f"Failed to notify WebSocket clients: {response.status} - {response_text}"
                        )
                        # Don't retry on 4xx errors (client errors)
                        if 400 <= response.status < 500:
                            return
                    else:
                        result = await response.json()
                        logger.debug(
                            f"Broadcast successful: {result.get('recipients', 0)} recipients"
                        )
                        return  # Success, exit

        except aiohttp.ClientConnectorError as e:
            # Connection refused - API might not be ready yet
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                logger.debug(f"API server not reachable, retrying in {wait_time}s... ({e})")
                await asyncio.sleep(wait_time)
            else:
                logger.warning(
                    f"Could not notify WebSocket clients after {max_retries} attempts: {e}. "
                    "This is normal if the API server is not running or still starting up."
                )

        except asyncio.TimeoutError:
            logger.warning(f"Timeout broadcasting message (attempt {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                logger.warning("Giving up on WebSocket notification after timeout")

        except Exception as e:
            logger.warning(
                f"Unexpected error notifying WebSocket clients (attempt {attempt + 1}/{max_retries}): {e}"
            )
            if attempt == max_retries - 1:
                logger.debug("Full error details:", exc_info=True)


async def process_parsing_job(db: AsyncSession, job: ParsingJob):
    """
    Process a single parsing job, handling artifact parsing, database updates, notifications, and lock cleanup.

    Args:
        db (AsyncSession): An asynchronous SQLAlchemy session used for all database interactions.
        job (ParsingJob): The parsing job instance containing identifiers for the job, artifact,
            and investigation.

    The function performs the following steps:
    * Extracts identifiers from the job early to avoid lazy-loading issues after a potential
      rollback.
    * Retrieves the associated Investigation record to determine the owner user identifier;
      defaults to the admin user (ID 1) when unavailable.
    * Calls `parse_artifact` to parse the artifact and insert resulting events into the
      database, capturing the number of inserted events.
    * Updates the job status to `completed` with a timestamp using raw SQL and commits the
      transaction.
    * Logs successful completion and, if any events were inserted, sends a silent WebSocket
      notification to connected clients.
    * Checks for remaining pending or running parsing jobs for the same investigation and,
      when none are found, clears the investigation-wide parsing lock.

    Error handling:
    * On any exception, logs the error, attempts to roll back the current transaction, and
      updates the job status to `failed` with an abbreviated error message.
    * After a failure it also attempts to clear the parsing lock for the investigation,
      logging any secondary errors that occur during this cleanup.

    Raises:
        None directly; all exceptions are caught internally and result in job-status updates
        and appropriate log entries.
    """
    # Extract job attributes early to avoid lazy loading issues after rollback
    job_id = job.job_id
    artifact_id = job.artifact_id
    investigation_id = job.investigation_id

    try:
        logger.debug(f"Processing job {job_id} for artifact {artifact_id}")

        # Get investigation to find user_id
        result = await db.execute(
            select(Investigation).where(Investigation.investigation_id == investigation_id)
        )
        investigation = result.scalar_one_or_none()
        # Extract owner_user_id using getattr to satisfy type checker
        user_id = getattr(investigation, "owner_user_id", None) if investigation else None
        user_id = user_id if user_id is not None else 1  # Default to admin if not found

        # Parse the artifact
        events_inserted = await parse_artifact(
            db=db,
            investigation_id=investigation_id,
            artifact_id=artifact_id,
            user_id=user_id,
        )

        # Mark job as completed using raw SQL to avoid session issues
        await db.execute(
            text(
                """
                UPDATE jobs_parsing 
                SET status = 'completed', 
                    finished_at = NOW(), 
                    error_message = NULL
                WHERE job_id = :job_id
            """
            ),
            {"job_id": job_id},
        )
        await db.commit()

        logger.debug(f"Job {job_id} completed successfully. " f"Inserted {events_inserted} events.")

        # Notify WebSocket clients that new events were inserted (silent refresh)
        if events_inserted > 0:
            await notify_websocket_clients(
                investigation_id=investigation_id,
                message={
                    "type": "events_inserted",
                    "count": events_inserted,
                    "artifact_id": artifact_id,
                    "job_id": job_id,
                    "silent": True,  # Don't show as chat message
                },
            )

        # Check if there are any more pending/running parsing jobs for this investigation
        # If not, clear the parsing lock
        await check_and_clear_parsing_lock(db, investigation_id)

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")

        # Rollback any failed transaction
        try:
            await db.rollback()
        except:
            pass

        # Use raw SQL to update job status to avoid ORM session issues
        try:
            await db.execute(
                text(
                    """
                    UPDATE jobs_parsing 
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

        # Check if we should clear the parsing lock even on failure
        try:
            await check_and_clear_parsing_lock(db, investigation_id)
        except Exception as lock_error:
            logger.error(f"Failed to clear parsing lock: {lock_error}")


async def process_agent_job(
    db: AsyncSession, job: AgentJob, control_queue: Optional[mp.Queue] = None
):
    """
    Process an agent job by retrieving the user's active LLM configuration, initializing an AssistantAgent with parameters derived from the job and configuration, streaming progress updates to WebSocket clients, handling errors, marking the job's final status in the database, and optionally generating continuation choices when the investigation is incomplete.

    Args:
        db: An asynchronous SQLAlchemy session used for all database queries and commits.
        job: The AgentJob instance containing all metadata required to run the agent (user ID, policy ID, seed instructions, effort level, etc.).
        control_queue: Optional multiprocessing queue that can receive external control messages such as stop signals; currently unused within the function but kept for future extensibility.

    Returns:
        None. The function performs its work via side effects: updating the job record in the database, sending real-time notifications through WebSocket clients, and creating InvestigationChoice records when needed.

    Raises:
        ValueError: If no active LLM configuration is found for the job's user.
        Exception: Any unexpected error during processing results in the job being marked as failed and a `job_failed` message being sent to connected clients.
    """
    # Extract job attributes early to avoid lazy loading issues after rollback
    job_id = job.job_id
    investigation_id = job.investigation_id
    user_id = job.user_id
    policy_id = job.policy_id
    seed_instructions = job.seed_instructions
    rule_values = job.rule_values
    job_metadata = job.job_metadata
    
    try:
        logger.info(f"Processing agent job {job_id} with policy {policy_id}")

        # Extract effort level from rule_values
        effort = rule_values.get("effort", "medium")

        # Retrieve LLM configuration for the user (REQUIRED - no fallbacks)
        result = await db.execute(
            select(LLMProviderConfig)
            .where(LLMProviderConfig.user_id == user_id)
            .where(LLMProviderConfig.is_active == True)
        )
        llm_config = result.scalar_one_or_none()

        if not llm_config:
            raise ValueError(
                f"No active LLM configuration found for user {user_id}. "
                f"Please create an LLM configuration via POST /api/v1/llm-config/ before running agent jobs."
            )

        # Extract values from ORM object
        llm_endpoint = cast(str, llm_config.api_endpoint)
        llm_model = cast(str, llm_config.model_name)
        api_key_raw = llm_config.api_key
        llm_api_key = cast(str, api_key_raw) if api_key_raw is not None else None
        llm_max_context = cast(int, llm_config.max_context_length)
        llm_temperature = float(cast(float, llm_config.temperature))
        
        llm_top_p = float(cast(float, llm_config.top_p)) if llm_config.top_p is not None else None
        llm_top_k = cast(int, llm_config.top_k) if llm_config.top_k is not None else None
        llm_min_p = float(cast(float, llm_config.min_p)) if llm_config.min_p is not None else None
        llm_timeout = cast(int, llm_config.timeout)

        # Note: llm_api_key can be None (for cookie-based auth) or a string (for Bearer token or cookie string)
        # The prepare_llm_auth helper in EventAgent will handle both cases appropriately

        logger.info(
            f"Using LLM config: {llm_config.provider_name} / {llm_model} "
            f"(context={llm_max_context}, temp={llm_temperature})"
        )

        # Use AssistantAgent - responsive agent with bounded turns
        # Map effort to max turns (updated for choice-based continuation)
        effort_to_turns = {
            "low": 3,
            "medium": 6,
            "high": 9,
        }
        max_turns = effort_to_turns.get(effort, 6)

        # Check if this is a continuation job
        if job_metadata and job_metadata.get("continued_from"):
            additional_turns = job_metadata.get("additional_turns", 6)
            max_turns = additional_turns
            logger.info(
                f"Continuation job: adding {additional_turns} turns "
                f"(continued from job {job_metadata['continued_from']})"
            )

        agent = AssistantAgent(
            db=db,
            investigation_id=str(investigation_id),
            job_id=job_id,
            question=seed_instructions,
            llm_endpoint=llm_endpoint,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            llm_max_context=llm_max_context,
            llm_temperature=llm_temperature,
            llm_top_p=llm_top_p,
            llm_top_k=llm_top_k,
            llm_min_p=llm_min_p,
            llm_timeout=llm_timeout,
            max_iterations=max_turns,
            user_id=user_id,
        )

        # Run agent and stream progress updates
        summary_parts = []
        agent_error = None
        investigation_incomplete = False
        agent_stats = {}

        async for update in agent.run():
            # Send progress updates via WebSocket
            await notify_websocket_clients(investigation_id=investigation_id, message=update)

            # Track if agent encountered an error
            if update.get("type") == "agent_error":
                agent_error = update
                logger.error(f"Agent job {job_id} encountered error: {update.get('error')}")

            # Collect summary if final message
            if update.get("type") == "agent_completed":
                summary_parts.append(update["summary"])
                investigation_incomplete = update.get("incomplete", False)
                agent_stats = update.get("stats", {})

        # Check if agent had an error
        if agent_error:
            # Mark job as failed
            job.status = JobStatus.FAILED
            job.finished_at = datetime.utcnow()
            job.error_message = agent_error.get("error", "Unknown agent error")[:1000]

            await db.commit()

            logger.error(f"Agent job {job_id} failed: {job.error_message}")

            # Note: agent_error message was already sent by the agent during run()
            # No need to send job_failed - it would create a duplicate message
        else:
            # Mark job as completed
            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.utcnow()
            job.error_message = None

            await db.commit()

            logger.info(f"Agent job {job_id} completed successfully")

            # Check if investigation was incomplete and generate continuation choices
            if investigation_incomplete:
                logger.info(
                    f"Investigation incomplete - generating continuation choices for job {job_id}"
                )

                try:
                    # Generate 3 continuation choices with different effort levels
                    turns_executed = agent_stats.get("turns_executed", 0)
                    tools_executed = agent_stats.get("tool_executions", 0)
                    timeline_entries = agent_stats.get("timeline_entries_created", 0)

                    choices_to_create = [
                        InvestigationChoiceCreate(
                            investigation_id=investigation_id,
                            job_id=job_id,
                            title="Quick follow-up (3 more turns)",
                            description=f"Continue investigating with 3 additional turns. So far: {turns_executed} turns, {tools_executed} tools, {timeline_entries} timeline entries.",
                            rationale=f"The investigation reached the maximum of {turns_executed} turns without completion. A quick follow-up can explore additional leads or verify findings.",
                            suggested_query=seed_instructions,
                            suggested_effort="low",
                            tool_suggestions={
                                "continued_from": job_id,
                                "additional_turns": 3,
                                "original_turns": turns_executed,
                                "original_tools": tools_executed,
                            },
                            display_order=1,
                        ),
                        InvestigationChoiceCreate(
                            investigation_id=investigation_id,
                            job_id=job_id,
                            title="Standard follow-up (6 more turns)",
                            description=f"Continue investigating with 6 additional turns. So far: {turns_executed} turns, {tools_executed} tools, {timeline_entries} timeline entries.",
                            rationale=f"The investigation reached the maximum of {turns_executed} turns without completion. A standard follow-up provides balanced depth for thorough analysis.",
                            suggested_query=seed_instructions,
                            suggested_effort="medium",
                            tool_suggestions={
                                "continued_from": job_id,
                                "additional_turns": 6,
                                "original_turns": turns_executed,
                                "original_tools": tools_executed,
                            },
                            display_order=2,
                        ),
                        InvestigationChoiceCreate(
                            investigation_id=investigation_id,
                            job_id=job_id,
                            title="Thorough follow-up (9 more turns)",
                            description=f"Continue investigating with 9 additional turns. So far: {turns_executed} turns, {tools_executed} tools, {timeline_entries} timeline entries.",
                            rationale=f"The investigation reached the maximum of {turns_executed} turns without completion. A thorough follow-up enables comprehensive analysis of complex patterns.",
                            suggested_query=seed_instructions,
                            suggested_effort="high",
                            tool_suggestions={
                                "continued_from": job_id,
                                "additional_turns": 9,
                                "original_turns": turns_executed,
                                "original_tools": tools_executed,
                            },
                            display_order=3,
                        ),
                    ]

                    # Create choices in database
                    created_choices = await create_investigation_choices_bulk(db, choices_to_create)

                    logger.info(
                        f"Created {len(created_choices):,} continuation choices for job {job_id} "
                        f"(investigation {investigation_id})"
                    )

                    # Notify UI that choices are available
                    await notify_websocket_clients(
                        investigation_id=investigation_id,
                        message={
                            "type": "investigation_choices_available",
                            "job_id": job_id,
                            "count": len(created_choices),
                            "choices": [
                                {
                                    "choice_id": choice.choice_id,
                                    "title": choice.title,
                                    "description": choice.description,
                                    "rationale": choice.rationale,
                                    "suggested_effort": choice.suggested_effort,
                                }
                                for choice in created_choices
                            ],
                        },
                    )

                except Exception as choice_error:
                    logger.error(
                        f"Failed to create investigation choices for job {job_id}: {choice_error}",
                        exc_info=True,
                    )
                    # Don't fail the job if choice creation fails

            # Note: agent_completed message was already sent by the agent during run()
            # No need to send job_completed - it would create a duplicate message

    except Exception as e:
        logger.error(f"Agent job {job_id} failed: {e}", exc_info=True)

        # Mark job as failed
        job.status = JobStatus.FAILED
        job.finished_at = datetime.utcnow()
        job.error_message = str(e)[:1000]

        await db.commit()

        # Notify of failure
        await notify_websocket_clients(
            investigation_id=investigation_id,
            message={
                "type": "job_failed",
                "job_id": job_id,
                "error": str(e)[:500],
            },
        )


async def recover_stale_jobs(db: AsyncSession):
    """
    Recover and reset jobs that have been marked as running but are considered stale.

    The function scans both parsing and agent job tables for entries whose status is `JobStatus.RUNNING` and whose `started_at` timestamp is older than 30 minutes from the current UTC time. Such jobs are assumed to be abandoned due to worker crashes, container restarts, or forced termination. For each stale job the status is set back to `JobStatus.PENDING`, the associated `worker_id` and `started_at` fields are cleared, and an explanatory `error_message` is recorded.

    After updating the database, the function commits the transaction and logs a summary of the recovery operation: a warning if any jobs were reset, otherwise an informational message indicating that no stale jobs were found.

    Args:
        db: An active asynchronous SQLAlchemy session (AsyncSession) used to execute update statements and commit changes.

    Returns:
        None

    Raises:
        Any exception raised by the database layer will propagate to the caller.
    """
    stale_threshold = datetime.utcnow() - timedelta(minutes=30)

    # Reset stale parsing jobs
    parsing_result = await db.execute(
        update(ParsingJob)
        .where(
            and_(ParsingJob.status == JobStatus.RUNNING, ParsingJob.started_at < stale_threshold)
        )
        .values(
            status=JobStatus.PENDING,
            worker_id=None,
            started_at=None,
            error_message="Job was stale (worker likely crashed), resetting to pending",
        )
    )

    parsing_count = parsing_result.rowcount

    # Reset stale agent jobs
    agent_result = await db.execute(
        update(AgentJob)
        .where(and_(AgentJob.status == JobStatus.RUNNING, AgentJob.started_at < stale_threshold))
        .values(
            status=JobStatus.PENDING,
            worker_id=None,
            started_at=None,
            error_message="Job was stale (worker likely crashed), resetting to pending",
        )
    )

    agent_count = agent_result.rowcount

    await db.commit()

    if parsing_count > 0 or agent_count > 0:
        logger.warning(
            f"Recovered {parsing_count} parsing job(s) and {agent_count} agent job(s) "
            f"that were stale (running > 30 minutes)"
        )
    else:
        logger.debug("No stale jobs found")


def worker_process(worker_id: uuid_pkg.UUID, control_queue: mp.Queue, worker_index: int):
    """
    Worker process entry point that runs in its own subprocess.

    This function sets up process-specific logging, creates an asyncio event loop, and establishes a dedicated async database engine and session factory for the worker. It then enters an asynchronous loop that continuously:

    * Checks `control_queue` for a `"stop"` message to terminate gracefully.
    * Attempts to claim an **agent** job (higher priority) using :func:`claim_agent_job`. If a job is claimed, it is processed with :func:`process_agent_job`; cancellation marks the job as failed and records an error message.
    * If no agent job is available, attempts to claim a **parsing** job via :func:`claim_parsing_job` and processes it with :func:`process_parsing_job`, handling cancellation similarly.
    * Sleeps briefly when no jobs are found before polling again.
    * Periodically (every `stale_check_interval_minutes`) runs :func:`recover_stale_jobs` to reset jobs that have become stale.

    On termination, the function disposes of the database engine and logs shutdown information. It also handles unexpected exceptions by logging them and backing off before retrying, and it respects `KeyboardInterrupt` for manual interruption.

    Args:
        worker_id (uuid_pkg.UUID): Unique identifier for this worker instance.
        control_queue (mp.Queue): Multiprocessing queue used to receive control commands such as a stop signal.
        worker_index (int): Zero-based index of the worker, used for naming and logging.

    Raises:
        None directly; internal errors are caught and logged. Unexpected exceptions propagate only to the outer async loop where they are handled before the process exits.
    """
    # Set process name for logging
    mp.current_process().name = f"Worker-{worker_index}"

    # Configure HTTP logging to send logs to API server
    setup_worker_logging(
        api_host=settings.api_host,
        api_port=settings.api_port,
        process_name=f"Worker-{worker_index}"
    )

    # Configure logging for this process
    logger.info(f"Worker process {worker_index} starting with ID {worker_id}")

    # Create new event loop for this process
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Create database engine for this process
    worker_engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )

    WorkerSessionLocal = async_sessionmaker(
        worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Track when we last checked for stale jobs
    last_stale_check = datetime.utcnow()
    stale_check_interval_minutes = 5

    async def async_worker_loop():
        """
        Async worker loop that continuously polls for jobs, processes them, and handles shutdown and maintenance tasks.

        The loop performs the following actions:
        * Checks a control queue for a `stop` message; if received, exits gracefully.
        * Opens an asynchronous database session using :class:`WorkerSessionLocal`.
        * Attempts to claim an agent job (higher priority) via :func:`claim_agent_job`.
          - If a job is claimed, it is processed with :func:`process_agent_job`.
          - Handles `asyncio.CancelledError` by marking the job as failed and committing the change.
        * If no agent job is available, attempts to claim a parsing job via :func:`claim_parsing_job`.
          - Processes the job with :func:`process_parsing_job` and similarly handles cancellation.
        * When no jobs are found, sleeps briefly before the next poll.
        * Periodically (every `stale_check_interval_minutes`) runs :func:`recover_stale_jobs` to reclaim stale jobs.
        * Logs any unexpected exception, waits longer, and continues looping.

        Upon exiting the loop, disposes of the global `worker_engine` and logs shutdown.

        Parameters
        ----------
        None - all required state is captured from surrounding scope (e.g., `worker_index`, `control_queue`, `worker_id`, `last_stale_check`, `stale_check_interval_minutes`).

        Returns
        -------
        None. The coroutine runs indefinitely until a stop signal is received or an unhandled exception terminates the process.

        Raises
        ------
        All exceptions are caught internally; unexpected errors are logged and cause a brief back-off before retrying. Cancellation of individual jobs is handled explicitly, marking those jobs as failed.
        """
        logger.info(f"Worker {worker_index} ready to process jobs")

        while True:
            try:
                # Check for stop signal (non-blocking)
                try:
                    msg = control_queue.get_nowait()
                    if msg == "stop":
                        logger.info(f"Worker {worker_index} received stop signal")
                        break
                except:
                    pass  # Queue empty, continue

                async with WorkerSessionLocal() as db:
                    # Try to claim an agent job first (higher priority)
                    agent_job = await claim_agent_job(db, worker_id)

                    if agent_job:
                        # Process agent job
                        try:
                            await process_agent_job(db, agent_job, control_queue)
                        except asyncio.CancelledError:
                            logger.info(f"Worker {worker_index} agent job cancelled")
                            # Mark job as failed
                            agent_job.status = JobStatus.FAILED
                            agent_job.finished_at = datetime.utcnow()
                            agent_job.error_message = "Job cancelled by user"
                            await db.commit()
                        continue

                    # Try to claim a parsing job
                    parsing_job = await claim_parsing_job(db, worker_id)

                    if parsing_job:
                        # Process parsing job
                        try:
                            await process_parsing_job(db, parsing_job)
                        except asyncio.CancelledError:
                            logger.info(f"Worker {worker_index} parsing job cancelled")
                            # Mark job as failed
                            parsing_job.status = JobStatus.FAILED
                            parsing_job.finished_at = datetime.utcnow()
                            parsing_job.error_message = "Job cancelled by user"
                            await db.commit()
                        continue

                    # No jobs available, wait before polling again
                    await asyncio.sleep(1.0)

                    # Periodically check for stale jobs (every 5 minutes)
                    nonlocal last_stale_check
                    now = datetime.utcnow()
                    if (now - last_stale_check).total_seconds() > (
                        stale_check_interval_minutes * 60
                    ):
                        logger.debug(f"Worker {worker_index} running periodic stale job check...")
                        await recover_stale_jobs(db)
                        last_stale_check = now

            except Exception as e:
                logger.error(f"Worker {worker_index} loop error: {e}", exc_info=True)
                await asyncio.sleep(5.0)  # Wait longer on error

        # Cleanup
        await worker_engine.dispose()
        logger.info(f"Worker {worker_index} stopped")

    try:
        # Run the async worker loop
        loop.run_until_complete(async_worker_loop())
    except KeyboardInterrupt:
        logger.info(f"Worker {worker_index} interrupted")
    finally:
        loop.close()


async def cleanup_worker_jobs(worker_id: uuid_pkg.UUID):
    """
    Clean up any jobs that were claimed by the specified worker and left in a running state.

    This function queries both `ParsingJob` and `AgentJob` tables for entries whose
    status is :class:`~app.models.JobStatus.RUNNING` and whose `worker_id` matches the
    provided identifier. For each matching job it resets the status to
    :class:`~app.models.JobStatus.PENDING`, clears the `worker_id` and `started_at`
    fields, and records an `error_message` indicating that the worker shut down.

    The function logs the number of parsing and agent jobs that were reset and commits
    the changes to the database. Any exception raised during the operation is caught,
    logged with a stack trace, and does not propagate further.
    """
    logger.info(f"Cleaning up jobs claimed by worker {worker_id}...")

    try:
        async with AsyncSessionLocal() as db:
            # Reset parsing jobs claimed by this worker
            parsing_result = await db.execute(
                update(ParsingJob)
                .where(
                    and_(ParsingJob.status == JobStatus.RUNNING, ParsingJob.worker_id == worker_id)
                )
                .values(
                    status=JobStatus.PENDING,
                    worker_id=None,
                    started_at=None,
                    error_message="Worker shutdown, job reset to pending",
                )
            )

            parsing_count = parsing_result.rowcount

            # Reset agent jobs claimed by this worker
            agent_result = await db.execute(
                update(AgentJob)
                .where(and_(AgentJob.status == JobStatus.RUNNING, AgentJob.worker_id == worker_id))
                .values(
                    status=JobStatus.PENDING,
                    worker_id=None,
                    started_at=None,
                    error_message="Worker shutdown, job reset to pending",
                )
            )

            agent_count = agent_result.rowcount

            await db.commit()

            if parsing_count > 0 or agent_count > 0:
                logger.info(
                    f"Reset {parsing_count} parsing job(s) and {agent_count} agent job(s) "
                    f"claimed by worker {worker_id}"
                )
    except Exception as e:
        logger.error(f"Error during cleanup for worker {worker_id}: {e}", exc_info=True)


async def monitor_stop_signals(control_queues: dict):
    """
    Monitor the database for stop-request flags on running jobs and forward stop commands to the corresponding worker control queues.

    Parameters
    ----------
    control_queues : dict
        Mapping of job identifiers (as stored in `jobs_agents.job_id`) to asyncio-compatible queue objects used to send control messages to active workers. The function will place a `"stop"` message onto the appropriate queue when a stop request is detected and subsequently remove that entry from the mapping.

    Behavior
    --------
    * Periodically (once per second) opens an asynchronous database session and queries the `jobs_agents` table for rows where `status` equals `'running'` and the JSON `metadata` field contains `"stop_requested": true`.
    * For each matching `job_id`/`worker_id` pair, if a corresponding queue exists in `control_queues`, a `"stop"` message is enqueued and the entry is deleted from `control_queues` to prevent duplicate signals.
    * Errors encountered during database access or processing are logged at error level; after an exception the loop sleeps for five seconds before retrying, ensuring resilience against transient failures.

    Returns
    -------
    None

    Raises
    ------
    The coroutine handles all exceptions internally; it never propagates them outward. Any unexpected errors are logged and cause a temporary back-off before the next iteration.
    """
    logger.info("Stop signal monitor starting...")

    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Find jobs with stop_requested flag
                result = await db.execute(
                    text(
                        """
                        SELECT job_id, worker_id
                        FROM jobs_agents
                        WHERE status = 'running'
                        AND metadata->>'stop_requested' = 'true'
                    """
                    )
                )

                jobs_to_stop = result.fetchall()

                for job_id, worker_id in jobs_to_stop:
                    if job_id in control_queues:
                        logger.info(f"Sending stop signal for job {job_id}")
                        control_queues[job_id].put("stop")
                        # Remove from tracking
                        del control_queues[job_id]

            await asyncio.sleep(1.0)  # Check every second

        except Exception as e:
            logger.error(f"Stop signal monitor error: {e}", exc_info=True)
            await asyncio.sleep(5.0)


def main():
    """
    Entry point that orchestrates the lifecycle of multiple worker processes.

    The function performs the following steps:

    1. Logs the start of the manager and recovers any stale jobs left in the database from previous runs.
    2. Creates a dedicated control queue for each worker process to receive runtime commands (e.g., stop signals).
    3. Spawns `NUM_WORKERS` separate processes, assigning each a unique UUID, its own control queue, and an index identifier.  Each child executes :func:`worker_process`.
    4. Registers signal handlers for `SIGINT` and `SIGTERM` that:
       - Log receipt of the shutdown request.
       - Broadcast a `"stop"` command to all workers via their queues.
       - Wait up to ten seconds for each worker to exit gracefully, escalating to termination or forced kill if necessary.
       - Run :func:`cleanup_worker_jobs` for every worker UUID to release any remaining job locks.
       - Dispose of the global database engine.
       - Log completion and exit the program.

    5. Enters a monitoring loop that periodically (every five seconds):
       - Checks each worker’s aliveness.
       - If a worker has crashed, logs the event, cleans up its jobs, generates a new UUID, restarts the process, and updates internal bookkeeping structures.

    The loop runs indefinitely until a shutdown signal is received or a `KeyboardInterrupt` occurs, in which case the same graceful-shutdown routine is invoked.
    """
    logger.info(f"Worker manager starting with {NUM_WORKERS} worker processes...")

    # Recover stale jobs on startup
    async def recover():
        """
        Recover any stale jobs in the database.

        This coroutine opens an asynchronous session with the configured database engine and invokes
        `recover_stale_jobs` to detect jobs that were claimed but not completed (e.g., due to worker crashes or timeouts) and resets them so they can be reassigned.

        The function does not take any parameters and returns `None`. It should be called during application startup or shutdown to ensure the job queue remains consistent.
        """
        async with AsyncSessionLocal() as db:
            await recover_stale_jobs(db)

    asyncio.run(recover())

    # Create control queues for each worker
    control_queues = [mp.Queue() for _ in range(NUM_WORKERS)]

    # Create worker processes
    workers = []
    worker_ids = []

    for i in range(NUM_WORKERS):
        worker_id = uuid_pkg.uuid4()
        worker_ids.append(worker_id)

        p = mp.Process(
            target=worker_process, args=(worker_id, control_queues[i], i), name=f"Worker-{i}"
        )
        p.start()
        workers.append(p)
        logger.info(f"Started worker process {i} (PID {p.pid})")

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        """
        Signal handler invoked on termination signals to gracefully shut down all worker processes.

        Parameters
        ----------
        signum : int
            The signal number received (e.g., `signal.SIGINT` or `signal.SIGTERM`).
        frame : types.FrameType
            The current stack frame (unused, required by the `signal` module).

        The function performs the following steps:

        1. Logs receipt of the signal.
        2. Sends a `"stop"` command to each control queue associated with a worker,
           prompting workers to cease accepting new jobs.
        3. Waits up to 10 seconds for each worker process to exit cleanly via `join`.
           - If a worker remains alive after the timeout, it is terminated and joined
             again for up to 5 seconds.
           - If the worker still does not exit, it is force-killed.
        4. Executes asynchronous cleanup of any jobs that were claimed by each worker,
           ensuring database state consistency.
        5. Disposes of the global SQLAlchemy engine asynchronously to close all connections.
        6. Logs completion and exits the interpreter with status `0`.

        Raises
        ------
        No exceptions are propagated; errors during shutdown are logged at appropriate
        severity levels.
        """
        logger.info(f"Received signal {signum}, shutting down workers...")

        # Send stop signal to all workers
        for q in control_queues:
            q.put("stop")

        # Wait for workers to finish (with timeout)
        for i, p in enumerate(workers):
            p.join(timeout=10)
            if p.is_alive():
                logger.warning(f"Worker {i} did not stop gracefully, terminating...")
                p.terminate()
                p.join(timeout=5)
                if p.is_alive():
                    logger.error(f"Worker {i} did not terminate, killing...")
                    p.kill()

        # Cleanup jobs
        for worker_id in worker_ids:
            asyncio.run(cleanup_worker_jobs(worker_id))

        # Dispose engine
        asyncio.run(engine.dispose())

        logger.info("All workers stopped")
        exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Monitor workers and restart if they crash
    try:
        while True:
            for i, p in enumerate(workers):
                if not p.is_alive():
                    logger.warning(f"Worker {i} crashed, restarting...")

                    # Cleanup old worker's jobs
                    asyncio.run(cleanup_worker_jobs(worker_ids[i]))

                    # Create new worker
                    worker_id = uuid_pkg.uuid4()
                    worker_ids[i] = worker_id

                    new_worker = mp.Process(
                        target=worker_process,
                        args=(worker_id, control_queues[i], i),
                        name=f"Worker-{i}",
                    )
                    new_worker.start()
                    workers[i] = new_worker
                    logger.info(f"Restarted worker {i} (PID {new_worker.pid})")

            # Sleep before next check
            time.sleep(5)

    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    # Required for multiprocessing on Windows
    mp.set_start_method("spawn", force=True)
    main()
