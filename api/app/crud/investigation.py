import uuid
from typing import Optional, List
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from ..models.investigation import Investigation
from ..models.user import User
from ..core.config import settings
from fastapi import HTTPException, status

from ..utils.log_setup import get_logger
from ..utils.security import validate_path_within_base, sanitize_log_message

logger = get_logger(__name__)


async def create_investigation(
    db: AsyncSession,
    title: str,
    owner_user_id: Optional[int] = None,
) -> Investigation:
    """
    Create a new Investigation record in the database and set up its filesystem directory.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for persisting the investigation.
    title : str
        Human-readable title of the investigation.
    owner_user_id : Optional[int], optional
        Identifier of the user who will own the investigation. If omitted, the investigation is created without an explicit owner.

    Returns
    -------
    Investigation
        The newly created Investigation instance, refreshed from the database with its generated identifier.

    Notes
    -----
    * A UUID is generated for `investigation_id` and used both as the primary key in the database and as the name of the directory under `settings.investigations_base_path`.
    * The function uses unified tables (e.g., events, timeline_entries) that include an `investigation_id` column; no per-investigation tables are created.
    * If the filesystem directory cannot be created, a warning is logged but the creation of the investigation record proceeds unchanged.
    """
    inv_id = uuid.uuid4()

    # Create investigation record
    investigation = Investigation(
        investigation_id=inv_id,
        title=title,
        owner_user_id=owner_user_id,
    )

    db.add(investigation)
    await db.flush()

    logger.info(f"Created investigation {inv_id}")

    # Create filesystem directory
    try:
        base_path = Path(settings.investigations_base_path)
        inv_dir = validate_path_within_base(Path(str(inv_id)), base_path)
        raw_files_dir = inv_dir / "raw_files"
        raw_files_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        # If filesystem creation fails, log but don't fail the investigation creation
        logger.warning(f"Could not create investigation directory: {sanitize_log_message(str(e))}")

    await db.commit()
    await db.refresh(investigation)
    return investigation


async def get_investigation(
    db: AsyncSession, investigation_id: uuid.UUID
) -> Optional[Investigation]:
    """
    Retrieve an investigation by its unique identifier.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for the query.
    investigation_id : uuid.UUID
        The UUID of the investigation to retrieve.

    Returns
    -------
    Optional[Investigation]
        The matching Investigation instance, or `None` if no record exists.
    """
    result = await db.execute(
        select(Investigation).where(Investigation.investigation_id == investigation_id)
    )
    return result.scalars().first()


async def list_investigations(
    db: AsyncSession, user_id: Optional[int] = None, is_admin: bool = False
) -> List[Investigation]:
    """
    List investigations visible to a user.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for the query.
    user_id : int or None, optional
        Identifier of the requesting user. If provided and `is_admin` is `False`,
        only investigations owned by this user are returned.
    is_admin : bool, default=False
        Flag indicating whether the caller has administrative privileges. When
        `True`, all investigations are listed regardless of ownership.

    Returns
    -------
    list[Investigation]
        A list of :class:`Investigation` objects ordered by creation date in
        descending order.
    """
    query = select(Investigation)

    # Regular users see only their own investigations
    if not is_admin and user_id is not None:
        query = query.where(Investigation.owner_user_id == user_id)

    result = await db.execute(query.order_by(Investigation.created_at.desc()))
    return list(result.scalars().all())


async def update_investigation(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    title: Optional[str] = None,
) -> Investigation:
    """
    Update an investigation's metadata in the database.

    Args:
        db: An active asynchronous SQLAlchemy session.
        investigation_id: The unique identifier of the investigation to be updated.
        title: Optional new title for the investigation; if omitted, the title remains unchanged.

    Returns:
        The refreshed `Investigation` instance reflecting any applied changes.

    Raises:
        HTTPException: If no investigation with the given `investigation_id` exists (HTTP 404).
    """
    investigation = await get_investigation(db, investigation_id)

    if not investigation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    # Update fields if provided
    if title is not None:
        investigation.title = title

    await db.commit()
    await db.refresh(investigation)

    return investigation


async def delete_investigation(
    db: AsyncSession, investigation_id: uuid.UUID, deleted_by_user_id: int
) -> None:
    """
    Delete an investigation and all associated data.

    This function removes the investigation record from the database, which cascades to related
    timeline entries, artifacts, graph nodes/edges, and event rows. After committing the
    transaction it attempts to delete the corresponding filesystem directory. Failure to
    remove the directory is logged but does not raise an exception.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used for database operations.
        investigation_id: The UUID of the investigation to be deleted.
        deleted_by_user_id: Identifier of the user performing the deletion (currently unused
            but retained for audit-trail compatibility).

    Returns:
        None

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If the database delete or commit fails. Other exceptions
        from filesystem cleanup are caught and logged, not propagated.
    """
    # Delete investigation record (cascades to timeline_entries, artifacts, etc.)
    # Note: We skip statistics collection to avoid transaction failures
    # when optional tables (events, timeline_entries) don't exist
    await db.execute(
        text("DELETE FROM investigations WHERE investigation_id = :inv_id"),
        {"inv_id": str(investigation_id)},
    )

    # Commit the deletion
    await db.commit()

    # Remove filesystem directory (best effort, don't fail if it doesn't exist)
    try:
        import shutil

        base_path = Path(settings.investigations_base_path)
        inv_dir = validate_path_within_base(Path(str(investigation_id)), base_path)
        if inv_dir.exists():
            shutil.rmtree(inv_dir)
            logger.info(f"Removed investigation directory: {inv_dir}")
    except Exception as e:
        # If filesystem cleanup fails, log but don't fail the deletion
        logger.warning(f"Could not remove investigation directory: {sanitize_log_message(str(e))}")


async def check_investigation_access(
    db: AsyncSession, investigation_id: uuid.UUID, user: User
) -> Investigation:
    """
    Check if a user has permission to access a specific investigation.

    Args:
        db: An active asynchronous SQLAlchemy session.
        investigation_id: The UUID identifying the investigation to retrieve.
        user: The User instance representing the requesting user.

    Returns:
        The Investigation object when the user is authorized to view it.

    Raises:
        HTTPException: If the investigation does not exist (404) or the user lacks permission (403).
    """
    investigation = await get_investigation(db, investigation_id)

    if not investigation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    # Admins can access all investigations
    if user.role == 1:
        return investigation

    # Regular users can only access their own investigations
    if investigation.owner_user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this investigation"
        )

    return investigation


async def set_parsing_lock(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    locked: bool,
) -> Optional[Investigation]:
    """
    Set or clear the parsing lock for a specific investigation.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous database session used for queries and commits.
    investigation_id : uuid.UUID
        The unique identifier of the investigation whose lock status is being modified.
    locked : bool
        `True` to indicate that parsing is in progress (lock the investigation),
        or `False` to clear the lock.

    Returns
    -------
    Optional[Investigation]
        The updated :class:`~models.Investigation` instance with the new
        `parsing_locked` value, or `None` if no investigation matching
        `investigation_id` exists.
    """
    investigation = await get_investigation(db, investigation_id)
    if not investigation:
        return None

    investigation.parsing_locked = locked
    await db.commit()
    await db.refresh(investigation)

    logger.info(f"Investigation {sanitize_log_message(str(investigation_id))} parsing_locked set to {locked}")
    return investigation


async def is_parsing_locked(
    db: AsyncSession,
    investigation_id: uuid.UUID,
) -> bool:
    """
    Check if parsing is locked for the specified investigation.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used to retrieve the investigation.
    investigation_id : uuid.UUID
        Unique identifier of the investigation to check.

    Returns
    -------
    bool
        `True` if the investigation exists and its `parsing_locked` flag is set,
        otherwise `False`.
    """
    investigation = await get_investigation(db, investigation_id)
    if not investigation:
        return False
    return investigation.parsing_locked


__all__ = [
    "create_investigation",
    "get_investigation",
    "list_investigations",
    "update_investigation",
    "delete_investigation",
    "check_investigation_access",
    "set_parsing_lock",
    "is_parsing_locked",
]
