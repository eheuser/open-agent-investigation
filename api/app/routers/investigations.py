from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Dict, Any
import uuid

from ..deps import get_db, get_current_user
from ..models.user import User
from ..schemas.investigation import InvestigationCreate, InvestigationRead, InvestigationUpdate
from ..crud import investigation as crud

router = APIRouter()


@router.post("/", response_model=InvestigationRead, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    payload: InvestigationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Create a new investigation record and associated resources.

    This function performs several actions:
    - Inserts an :class:`Investigation` entry into the database with the given title and owner.
    - Generates per-investigation tables for events, graph nodes, and graph edges.
    - Creates a filesystem directory to store raw files related to the investigation.

    Parameters
    ----------
    payload: InvestigationCreate
        The data required to create the investigation, including its title.
    db: AsyncSession
        An asynchronous SQLAlchemy session provided by dependency injection.
    user: User
        The currently authenticated user, injected via dependency injection; used as the owner of the new investigation.

    Returns
    -------
    Investigation
        The newly created investigation instance returned from the CRUD layer.
    """
    inv = await crud.create_investigation(db, title=payload.title, owner_user_id=user.user_id)
    return inv


@router.get("/", response_model=List[InvestigationRead])
async def list_investigations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List investigations visible to the current user.

    Regular users see only their own investigations; admins see all investigations.

    Args:
        db (AsyncSession): Database session dependency.
        user (User): The currently authenticated user.

    Returns:
        List[Investigation]: A list of investigation objects accessible to the user.
    """
    invs = await crud.list_investigations(db, user_id=user.user_id, is_admin=user.is_admin())
    return invs


@router.get("/{inv_id}", response_model=InvestigationRead)
async def get_investigation(
    inv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retrieve a specific investigation by its UUID.

    Args:
        inv_id: The UUID of the investigation to retrieve.
        db: An asynchronous SQLAlchemy session provided via dependency injection.
        user: The currently authenticated user obtained from the request context.

    Returns:
        The investigation instance matching `inv_id`.

    Raises:
        HTTPException: If no investigation with the given ID exists (404 Not Found) or if the requesting user lacks permission to access it (403 Forbidden).
    """
    inv = await crud.get_investigation(db, inv_id)

    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    # Check permissions
    if not user.is_admin() and inv.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return inv


@router.patch("/{inv_id}", response_model=InvestigationRead)
async def update_investigation(
    inv_id: uuid.UUID,
    payload: InvestigationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Update an investigation's metadata.

    Parameters
    ----------
    inv_id: uuid.UUID
        The unique identifier of the investigation to update.
    payload: InvestigationUpdate
        An object containing the fields to be updated (e.g., `title`).
    db: AsyncSession, optional
        Database session dependency injected by FastAPI. Defaults to the result of `get_db`.
    user: User, optional
        The currently authenticated user provided by `get_current_user`.

    Returns
    -------
    Investigation
        The updated investigation instance.

    Raises
    ------
    HTTPException
        - 404 NOT FOUND if no investigation with `inv_id` exists.
        - 403 FORBIDDEN if the requesting user is neither an admin nor the owner of the investigation.
    """
    inv = await crud.get_investigation(db, inv_id)

    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    # Check permissions
    if not user.is_admin() and inv.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    updated_inv = await crud.update_investigation(db, inv_id, title=payload.title)

    return updated_inv


@router.delete("/{inv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investigation(
    inv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete an investigation and all associated data.

    This operation removes the investigation record along with its related resources:
    - Per-investigation database tables
    - Filesystem directory containing investigation files
    - Artifact records linked to the investigation
    - Corresponding entry in the deletion log

    Args:
        inv_id (uuid.UUID): The unique identifier of the investigation to delete.
        db (AsyncSession, optional): Database session dependency injected by FastAPI. Defaults to Depends(get_db).
        user (User, optional): The currently authenticated user, provided via dependency injection. Defaults to Depends(get_current_user).

    Raises:
        HTTPException: If the investigation does not exist (404 Not Found) or if the user lacks permission to delete it (403 Forbidden).
    """
    inv = await crud.get_investigation(db, inv_id)

    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    # Check permissions
    if not user.is_admin() and inv.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await crud.delete_investigation(db, inv_id, user.user_id)


@router.get("/{inv_id}/field-dictionary/status")
async def get_field_dictionary_status(
    inv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get the status of field dictionary generation for an investigation.

    Returns counts of total fields discovered and how many still need LLM descriptions.
    This helps track progress of the background field dictionary generation task.

    Args:
        inv_id: The UUID of the investigation.
        db: Database session dependency.
        user: The currently authenticated user.

    Returns:
        Dict containing:
        - total_fields: Total number of fields discovered
        - pending_fields: Number of fields without LLM descriptions
        - completed_fields: Number of fields with descriptions
        - event_types: Number of distinct event types
        - is_complete: Boolean indicating if all fields have descriptions

    Raises:
        HTTPException: If investigation not found (404) or access denied (403).
    """
    inv = await crud.get_investigation(db, inv_id)

    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    # Check permissions
    if not user.is_admin() and inv.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Count total fields
    total_result = await db.execute(
        text(
            """
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT event_type) as event_types
            FROM field_dictionary
            WHERE investigation_id = :investigation_id
        """
        ),
        {"investigation_id": str(inv_id)},
    )
    total_row = total_result.fetchone()
    total_fields = total_row[0] if total_row else 0
    event_types = total_row[1] if total_row else 0

    # Count pending fields (NULL description)
    pending_result = await db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM field_dictionary
            WHERE investigation_id = :investigation_id
              AND description IS NULL
        """
        ),
        {"investigation_id": str(inv_id)},
    )
    pending_fields = pending_result.scalar() or 0

    completed_fields = total_fields - pending_fields

    return {
        "total_fields": total_fields,
        "pending_fields": pending_fields,
        "completed_fields": completed_fields,
        "event_types": event_types,
        "is_complete": pending_fields == 0 and total_fields > 0,
    }


__all__ = ["router"]
