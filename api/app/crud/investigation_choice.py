from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.sql import func

from ..models.investigation_choice import InvestigationChoice
from ..schemas.investigation_choice import InvestigationChoiceCreate, InvestigationChoiceUpdate


async def create_investigation_choice(
    db: AsyncSession, choice: InvestigationChoiceCreate
) -> InvestigationChoice:
    """
    Create a new `InvestigationChoice` record in the database.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used to interact with the database.
    choice : InvestigationChoiceCreate
        A Pydantic model containing the data required to create an `InvestigationChoice`.

    Returns
    -------
    InvestigationChoice
        The newly created `InvestigationChoice` instance, refreshed from the database.
    """
    db_choice = InvestigationChoice(**choice.model_dump())
    db.add(db_choice)
    await db.commit()
    await db.refresh(db_choice)
    return db_choice


async def create_investigation_choices_bulk(
    db: AsyncSession, choices: List[InvestigationChoiceCreate]
) -> List[InvestigationChoice]:
    """
    Create multiple InvestigationChoice records in bulk.

    Args:
        db (AsyncSession): An active asynchronous SQLAlchemy session.
        choices (List[InvestigationChoiceCreate]): A list of data objects representing the investigation
            choices to be created. Each object must provide fields compatible with the
            InvestigationChoice model.

    Returns:
        List[InvestigationChoice]: The list of newly persisted InvestigationChoice instances,
        refreshed from the database so that generated fields (e.g., primary keys) are populated.
    """
    db_choices = [InvestigationChoice(**choice.model_dump()) for choice in choices]
    db.add_all(db_choices)
    await db.commit()

    # Refresh all choices
    for choice in db_choices:
        await db.refresh(choice)

    return db_choices


async def get_investigation_choices_by_job(
    db: AsyncSession, job_id: int
) -> List[InvestigationChoice]:
    """
    Retrieve all investigation choices associated with a specific job.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for database access.
    job_id : int
        Identifier of the agent job whose choices are to be fetched.

    Returns
    -------
    List[InvestigationChoice]
        A list of `InvestigationChoice` objects ordered by `display_order` and then `choice_id`.
    """
    result = await db.execute(
        select(InvestigationChoice)
        .where(InvestigationChoice.job_id == job_id)
        .order_by(InvestigationChoice.display_order, InvestigationChoice.choice_id)
    )
    return list(result.scalars().all())


async def get_investigation_choices_by_investigation(
    db: AsyncSession, investigation_id: UUID, include_selected: bool = True
) -> List[InvestigationChoice]:
    """
    Get all `InvestigationChoice` records for a given investigation.

    Args:
        db: An :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute the query.
        investigation_id: The UUID of the investigation whose choices should be retrieved.
        include_selected: If `True` (default), both selected and unselected choices are returned; if `False`, only choices where `selected` is `False` are included.

    Returns:
        A list of :class:`InvestigationChoice` objects ordered by `created_at` in descending order (newest first).
    """
    query = select(InvestigationChoice).where(
        InvestigationChoice.investigation_id == investigation_id
    )

    if not include_selected:
        query = query.where(InvestigationChoice.selected == False)

    query = query.order_by(InvestigationChoice.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_investigation_choice(
    db: AsyncSession, choice_id: int
) -> Optional[InvestigationChoice]:
    """
    Retrieve an :class:`~models.InvestigationChoice` instance by its primary key.

    Args:
        db: An active `AsyncSession` used to execute the query.
        choice_id: The unique identifier of the desired investigation choice.

    Returns:
        The matching :class:`InvestigationChoice` object, or `None` if no record with the given
        `choice_id` exists.
    """
    result = await db.execute(
        select(InvestigationChoice).where(InvestigationChoice.choice_id == choice_id)
    )
    return result.scalar_one_or_none()


async def update_investigation_choice(
    db: AsyncSession, choice_id: int, choice_update: InvestigationChoiceUpdate
) -> Optional[InvestigationChoice]:
    """
    Update an InvestigationChoice record with the provided data.

    Args:
        db: An active asynchronous SQLAlchemy session.
        choice_id: The primary key of the InvestigationChoice to update.
        choice_update: A pydantic model containing the fields to modify; only fields that are set will be applied.

    Returns:
        The updated InvestigationChoice instance if a matching record was found, otherwise `None`.

    Raises:
        Any exception raised by the database layer during execution (e.g., connection errors).
    """
    # Build update dict, only including fields that were set
    update_data = choice_update.model_dump(exclude_unset=True)

    # Add timestamp if marking as selected
    if update_data.get("selected") is True:
        update_data["selected_at"] = func.now()

    result = await db.execute(
        update(InvestigationChoice)
        .where(InvestigationChoice.choice_id == choice_id)
        .values(**update_data)
        .returning(InvestigationChoice)
    )

    await db.commit()

    return result.scalar_one_or_none()


async def delete_investigation_choice(db: AsyncSession, choice_id: int) -> bool:
    """
    Delete an `InvestigationChoice` record identified by its primary key.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for database operations.
    choice_id : int
        Unique identifier of the `InvestigationChoice` to delete.

    Returns
    -------
    bool
        `True` if a matching record was found and deleted; `False` if no such record exists.
    """
    choice = await get_investigation_choice(db, choice_id)
    if not choice:
        return False

    await db.delete(choice)
    await db.commit()
    return True


__all__ = [
    "create_investigation_choice",
    "create_investigation_choices_bulk",
    "get_investigation_choices_by_job",
    "get_investigation_choices_by_investigation",
    "get_investigation_choice",
    "update_investigation_choice",
    "delete_investigation_choice",
]
