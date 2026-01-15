from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
import uuid

from ..models.job_parsing import ParsingJob, JobStatus as ParseStatus
from ..models.job_agent import AgentJob, JobStatus as AgentStatus


async def enqueue_parsing_job(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
) -> ParsingJob:
    """
    Create and enqueue a new parsing job for the specified artifact.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to interact with the database.
    investigation_id : uuid.UUID
        Unique identifier of the investigation to which the job belongs.
    artifact_id : int
        Identifier of the artifact that should be parsed.

    Returns
    -------
    ParsingJob
        The newly created `ParsingJob` instance, persisted in the database and refreshed with its generated primary key and default values.
    """
    job = ParsingJob(
        investigation_id=investigation_id,
        artifact_id=artifact_id,
        status=ParseStatus.PENDING,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job


async def enqueue_agent_job(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    user_id: int,
    policy_id: str,
    rule_values: dict,
    seed_instructions: str,
) -> AgentJob:
    """
    Create a new `AgentJob` record and add it to the database queue.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used for persisting the job.
    investigation_id : uuid.UUID
        The unique identifier of the investigation to which the job belongs.
    user_id : int
        Identifier of the user that requested the creation of the job.
    policy_id : str
        Name of the policy YAML file associated with the job.
    rule_values : dict
        A dictionary containing resolved rule values, typically serialized as JSON.
    seed_instructions : str
        The rendered prompt or initial instructions that will be supplied to the agent.

    Returns
    -------
    AgentJob
        The newly created `AgentJob` instance, refreshed from the database so that all generated fields (e.g., primary key) are populated.
    """
    job = AgentJob(
        investigation_id=investigation_id,
        user_id=user_id,
        policy_id=policy_id,
        rule_values=rule_values,
        seed_instructions=seed_instructions,
        status=ParseStatus.PENDING,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job


async def get_parsing_job(db: AsyncSession, job_id: int) -> Optional[ParsingJob]:
    """
    Retrieve a parsing job from the database by its identifier.

    Args:
        db: An active asynchronous SQLAlchemy session.
        job_id: The unique identifier of the parsing job to retrieve.

    Returns:
        The :class:`ParsingJob` instance matching `job_id` if it exists; otherwise, `None`.
    """
    result = await db.execute(select(ParsingJob).where(ParsingJob.job_id == job_id))
    return result.scalars().first()


async def get_agent_job(db: AsyncSession, job_id: int) -> Optional[AgentJob]:
    """
    Retrieve an :class:`~models.AgentJob` instance by its primary key.\n\nParameters\n----------\ndb: AsyncSession\n    An active asynchronous SQLAlchemy session used for the query.\njob_id: int\n    The unique identifier of the agent job to retrieve.\n\nReturns\n-------\nOptional[AgentJob]\n    The matching :class:`~models.AgentJob` object if it exists; otherwise `None`.
    """
    result = await db.execute(select(AgentJob).where(AgentJob.job_id == job_id))
    return result.scalars().first()


async def set_parsing_job_status(
    db: AsyncSession, job_id: int, new_status: ParseStatus, error_msg: Optional[str] = None
) -> bool:
    """
    Update the status of a parsing job in the database.

    Args:
        db (AsyncSession): An active asynchronous SQLAlchemy session used to execute the update.
        job_id (int): The unique identifier of the parsing job whose status should be changed.
        new_status (ParseStatus): The new status to assign to the job. Supported values include
            `ParseStatus.RUNNING`, `ParseStatus.COMPLETED`, and `ParseStatus.FAILED`.
        error_msg (Optional[str], optional): An optional error message describing why the job failed.
            This value is stored only when provided.

    Returns:
        bool: `True` if a row was found and updated; `False` if no parsing job with the
        specified `job_id` exists.
    """
    values: Dict[str, Any] = {"status": new_status}

    if new_status == ParseStatus.RUNNING:
        values["started_at"] = datetime.now(timezone.utc)
    elif new_status in (ParseStatus.COMPLETED, ParseStatus.FAILED):
        values["finished_at"] = datetime.now(timezone.utc)

    if error_msg:
        values["error_message"] = error_msg

    result = await db.execute(
        update(ParsingJob).where(ParsingJob.job_id == job_id).values(**values)
    )

    await db.commit()
    return result.rowcount > 0


async def set_agent_job_status(
    db: AsyncSession, job_id: int, new_status: AgentStatus, error_msg: Optional[str] = None
) -> bool:
    """
    Update the status of an agent job in the database.

    Args:
        db (AsyncSession): An active asynchronous SQLAlchemy session used to execute the update.
        job_id (int): The unique identifier of the agent job whose status should be modified.
        new_status (AgentStatus): The new status to assign to the job. Supported statuses affect timestamp handling:
            - `AgentStatus.RUNNING` sets `started_at` to the current UTC time.
            - `AgentStatus.COMPLETED` or `AgentStatus.FAILED` set `finished_at` to the current UTC time.
        error_msg (Optional[str], optional): An optional error message to store when the job fails. Defaults to `None`.

    Returns:
        bool: `True` if a row was found and updated; `False` if no job with the given `job_id` exists.
    """
    values: Dict[str, Any] = {"status": new_status}

    if new_status == AgentStatus.RUNNING:
        values["started_at"] = datetime.now(timezone.utc)
    elif new_status in (AgentStatus.COMPLETED, AgentStatus.FAILED):
        values["finished_at"] = datetime.now(timezone.utc)

    if error_msg:
        values["error_message"] = error_msg

    result = await db.execute(update(AgentJob).where(AgentJob.job_id == job_id).values(**values))

    await db.commit()
    return result.rowcount > 0


__all__ = [
    "enqueue_parsing_job",
    "enqueue_agent_job",
    "get_parsing_job",
    "get_agent_job",
    "set_parsing_job_status",
    "set_agent_job_status",
]
