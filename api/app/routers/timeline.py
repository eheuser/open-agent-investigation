from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, func
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import json

from ..core.database import get_db
from ..deps import get_current_user
from ..models.user import User
from ..services.websocket_manager import manager as websocket_manager
from ..schemas.timeline import (
    TimelineEntryCreate,
    TimelineEntryRead,
    TimelineEntryUpdate,
    TimelineNoteCreate,
    TimelineNoteRead,
    TimelineNoteUpdate,
    TimelineResponse,
    TimelineStatsResponse,
    EntryType,
)

router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])


@router.get("/{investigation_id}", response_model=TimelineResponse)
async def get_timeline(
    investigation_id: UUID,
    entry_type: Optional[EntryType] = Query(None, description="Filter by entry type"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    start_time: Optional[datetime] = Query(None, description="Filter by start timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter by end timestamp"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    include_hidden: bool = Query(False, description="Include hidden entries"),
    limit: int = Query(100, le=1000, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Fetch timeline entries for a given investigation with optional filtering, pagination, and visibility control.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation whose timeline entries are being retrieved.
    entry_type: EntryType | None, optional
        Filter results to only include entries of the specified type. Defaults to `None` (no type filter).
    event_type: str | None, optional
        When provided, joins the `events` table and filters entries associated with events of this type. Defaults to `None`.
    tags: list[str] | None, optional
        Filter entries that contain any of the supplied tags. Uses PostgreSQL array overlap operator (&&). Defaults to `None`.
    start_time: datetime | None, optional
        Include only entries whose timestamp is greater than or equal to this value. Defaults to `None`.
    end_time: datetime | None, optional
        Include only entries whose timestamp is less than or equal to this value. Defaults to `None`.
    search: str | None, optional
        Case-insensitive substring search applied to both the title and description fields. Defaults to `None`.
    include_hidden: bool, optional
        When `False`, restrict results to entries where `is_visible` is true. Defaults to `False`.
    limit: int, optional
        Maximum number of entries to return (capped at 1000). Defaults to `100`.
    offset: int, optional
        Number of entries to skip for pagination. Must be non-negative. Defaults to `0`.
    db: AsyncSession
        Database session injected by FastAPI's dependency system.
    user: User
        Current authenticated user injected by FastAPI's dependency system.

    Returns
    -------
    TimelineResponse
        An object containing:
            * `entries` - a list of :class:`TimelineEntryRead` objects matching the query,
            * `total` - total number of entries that satisfy the filters (ignoring pagination),
            * `limit` - the limit value used for this request,
            * `offset` - the offset value used for this request.

    Notes
    -----
    * The query orders results by timestamp in descending order (newest first).
    * When `event_type` is supplied, the function joins the `events` table and prefixes column references with the appropriate alias.
    * Tag filtering relies on PostgreSQL's array overlap operator; ensure the underlying column type supports this operation.
    """
    # Build query - join with events if filtering by event_type
    if event_type:
        query_parts = [
            "SELECT te.entry_id, te.investigation_id, te.event_id, te.timestamp, te.entry_type, te.title, te.description,",
            "te.data, te.tags, te.created_by_user_id, te.created_at, te.updated_at, te.is_visible",
            "FROM timeline_entries te",
            "JOIN events e ON te.event_id = e.event_id",
            "WHERE te.investigation_id = :investigation_id",
        ]
    else:
        query_parts = [
            "SELECT entry_id, investigation_id, event_id, timestamp, entry_type, title, description,",
            "data, tags, created_by_user_id, created_at, updated_at, is_visible",
            "FROM timeline_entries",
            "WHERE investigation_id = :investigation_id",
        ]
    params: Dict[str, Any] = {"investigation_id": str(investigation_id)}

    # Filter by visibility
    if not include_hidden:
        query_parts.append("AND is_visible = true")

    # Filter by entry type
    if entry_type:
        if event_type:
            query_parts.append("AND te.entry_type = :entry_type")
        else:
            query_parts.append("AND entry_type = :entry_type")
        params["entry_type"] = entry_type.value

    # Filter by event type
    if event_type:
        query_parts.append("AND e.event_type = :event_type")
        params["event_type"] = event_type

    # Filter by tags
    if tags:
        if event_type:
            query_parts.append("AND te.tags && :tags")
        else:
            query_parts.append("AND tags && :tags")
        params["tags"] = tags

    # Filter by time range
    if start_time:
        if event_type:
            query_parts.append("AND te.timestamp >= :start_time")
        else:
            query_parts.append("AND timestamp >= :start_time")
        params["start_time"] = start_time

    if end_time:
        if event_type:
            query_parts.append("AND te.timestamp <= :end_time")
        else:
            query_parts.append("AND timestamp <= :end_time")
        params["end_time"] = end_time

    # Search filter
    if search:
        if event_type:
            query_parts.append("AND (te.title ILIKE :search OR te.description ILIKE :search)")
        else:
            query_parts.append("AND (title ILIKE :search OR description ILIKE :search)")
        params["search"] = f"%{search}%"

    # Order and pagination
    if event_type:
        query_parts.append("ORDER BY te.timestamp DESC")
    else:
        query_parts.append("ORDER BY timestamp DESC")
    query_parts.append("LIMIT :limit OFFSET :offset")
    params["limit"] = limit
    params["offset"] = offset

    query = text(" ".join(query_parts))

    result = await db.execute(query, params)
    rows = result.fetchall()

    # Build entry objects
    entries = []
    for row in rows:
        entry = TimelineEntryRead(
            entry_id=row[0],
            investigation_id=str(row[1]),
            event_id=row[2],
            timestamp=row[3],
            entry_type=row[4],
            title=row[5],
            description=row[6],
            data=row[7] or {},
            tags=row[8] or [],
            created_by_user_id=row[9],
            created_at=row[10],
            updated_at=row[11],
            is_visible=row[12],
            notes=[],
        )
        entries.append(entry)

    # Get total count WITH ALL THE SAME FILTERS
    if event_type:
        count_query_parts = [
            "SELECT COUNT(*) FROM timeline_entries te",
            "JOIN events e ON te.event_id = e.event_id",
            "WHERE te.investigation_id = :investigation_id",
        ]
    else:
        count_query_parts = [
            "SELECT COUNT(*) FROM timeline_entries",
            "WHERE investigation_id = :investigation_id",
        ]
    count_params: Dict[str, Any] = {"investigation_id": str(investigation_id)}

    # Apply ALL the same filters as the main query
    if not include_hidden:
        if event_type:
            count_query_parts.append("AND te.is_visible = true")
        else:
            count_query_parts.append("AND is_visible = true")

    if entry_type:
        if event_type:
            count_query_parts.append("AND te.entry_type = :entry_type")
        else:
            count_query_parts.append("AND entry_type = :entry_type")
        count_params["entry_type"] = entry_type.value

    if event_type:
        count_query_parts.append("AND e.event_type = :event_type")
        count_params["event_type"] = event_type

    if tags:
        if event_type:
            count_query_parts.append("AND te.tags && :tags")
        else:
            count_query_parts.append("AND tags && :tags")
        count_params["tags"] = tags

    if start_time:
        if event_type:
            count_query_parts.append("AND te.timestamp >= :start_time")
        else:
            count_query_parts.append("AND timestamp >= :start_time")
        count_params["start_time"] = start_time

    if end_time:
        if event_type:
            count_query_parts.append("AND te.timestamp <= :end_time")
        else:
            count_query_parts.append("AND timestamp <= :end_time")
        count_params["end_time"] = end_time

    if search:
        if event_type:
            count_query_parts.append("AND (te.title ILIKE :search OR te.description ILIKE :search)")
        else:
            count_query_parts.append("AND (title ILIKE :search OR description ILIKE :search)")
        count_params["search"] = f"%{search}%"

    count_query = text(" ".join(count_query_parts))
    count_result = await db.execute(count_query, count_params)
    total = count_result.scalar() or 0

    return TimelineResponse(entries=entries, total=total, limit=limit, offset=offset)


@router.get("/{investigation_id}/entries/{entry_id}", response_model=TimelineEntryRead)
async def get_timeline_entry(
    investigation_id: UUID,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retrieve a single timeline entry and its associated notes for a given investigation.

    Args:
        investigation_id (UUID): Identifier of the investigation containing the entry.
        entry_id (int): Unique identifier of the timeline entry to retrieve.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session provided by dependency injection. Defaults to Depends(get_db).
        user (User, optional): The currently authenticated user obtained via dependency injection. Defaults to Depends(get_current_user).

    Returns:
        TimelineEntryRead: A pydantic model representing the timeline entry, including its metadata and a list of TimelineNoteRead objects for each associated note.

    Raises:
        HTTPException: If no timeline entry matching the provided `investigation_id` and `entry_id` exists (status code 404).
    """
    # Fetch entry
    entry_query = text(
        """
        SELECT entry_id, investigation_id, event_id, timestamp, entry_type, title, description,
               data, tags, created_by_user_id, created_at, updated_at, is_visible
        FROM timeline_entries
        WHERE investigation_id = :investigation_id AND entry_id = :entry_id
    """
    )

    result = await db.execute(
        entry_query, {"investigation_id": str(investigation_id), "entry_id": entry_id}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Timeline entry not found")

    # Fetch notes for this entry
    notes_query = text(
        """
        SELECT n.note_id, n.entry_id, n.user_id, n.note_text, n.created_at, n.updated_at, u.username
        FROM timeline_notes n
        LEFT JOIN users u ON n.user_id = u.user_id
        WHERE n.entry_id = :entry_id
        ORDER BY n.created_at ASC
    """
    )

    notes_result = await db.execute(notes_query, {"entry_id": entry_id})
    notes_rows = notes_result.fetchall()

    notes = [
        TimelineNoteRead(
            note_id=n[0],
            entry_id=n[1],
            user_id=n[2],
            note_text=n[3],
            created_at=n[4],
            updated_at=n[5],
            username=n[6],
        )
        for n in notes_rows
    ]

    return TimelineEntryRead(
        entry_id=row[0],
        investigation_id=str(row[1]),
        event_id=row[2],
        timestamp=row[3],
        entry_type=row[4],
        title=row[5],
        description=row[6],
        data=row[7] or {},
        tags=row[8] or [],
        created_by_user_id=row[9],
        created_at=row[10],
        updated_at=row[11],
        is_visible=row[12],
        notes=notes,
    )


@router.post("/{investigation_id}/entries", response_model=TimelineEntryRead)
async def create_timeline_entry(
    investigation_id: UUID,
    entry: TimelineEntryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Create a new timeline entry for a given investigation.

    Parameters
    ----------
    investigation_id: UUID
        The unique identifier of the investigation to which the entry will belong.
    entry: TimelineEntryCreate
        Pydantic model containing the data required to create the entry, including optional `event_id`,
        timestamp, type, title, description, arbitrary JSON `data`, tags and visibility flag.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session injected by FastAPI's dependency system. Used for all database
        interactions within the function.
    user: User, optional
        The currently authenticated user injected by FastAPI's dependency system. The user's ID is stored
        as `created_by_user_id` on the new entry.

    Returns
    -------
    TimelineEntryRead
        A read-only representation of the newly created timeline entry, populated with all fields
        returned from the database and an empty list for associated notes.

    Raises
    ------
    HTTPException
        * 404 - if the specified investigation does not exist.
        * 400 - if `entry.event_id` is provided but the referenced event either does not exist or does not belong to the investigation.
        * 409 - if the supplied `event_id` is already linked to another timeline entry within the same investigation.
        * 500 - if the INSERT statement succeeds but no row is returned, indicating an unexpected failure.

    Side Effects
    ------------
    * Commits the transaction to persist the new entry.
    * Broadcasts a WebSocket message of type `timeline_entry_added` to all clients subscribed to the investigation's channel.
    """
    # Verify investigation exists
    inv_check = text("SELECT investigation_id FROM investigations WHERE investigation_id = :id")
    inv_result = await db.execute(inv_check, {"id": str(investigation_id)})
    if not inv_result.fetchone():
        raise HTTPException(status_code=404, detail="Investigation not found")

    # If event_id is provided, verify it exists and belongs to this investigation
    if entry.event_id:
        event_check = text(
            """
            SELECT event_id FROM events
            WHERE event_id = :event_id AND investigation_id = :investigation_id
        """
        )
        event_result = await db.execute(
            event_check, {"event_id": entry.event_id, "investigation_id": str(investigation_id)}
        )
        if not event_result.fetchone():
            raise HTTPException(
                status_code=400, detail="Event not found or does not belong to this investigation"
            )

        # Check if this event is already on the timeline (unique constraint)
        existing_check = text(
            """
            SELECT entry_id, title FROM timeline_entries
            WHERE investigation_id = :investigation_id AND event_id = :event_id
        """
        )
        existing_result = await db.execute(
            existing_check, {"investigation_id": str(investigation_id), "event_id": entry.event_id}
        )
        existing_row = existing_result.fetchone()
        if existing_row:
            raise HTTPException(
                status_code=409,
                detail=f"Event {entry.event_id} is already on the timeline (entry {existing_row[0]}: '{existing_row[1]}')",
            )

    query = text(
        """
        INSERT INTO timeline_entries
        (investigation_id, event_id, timestamp, entry_type, title, description, data, tags, created_by_user_id, is_visible)
        VALUES (:investigation_id, :event_id, :timestamp, :entry_type, :title, :description,
                CAST(:data AS jsonb), :tags, :user_id, :is_visible)
        RETURNING entry_id, investigation_id, event_id, timestamp, entry_type, title, description,
                  data, tags, created_by_user_id, created_at, updated_at, is_visible
    """
    )

    result = await db.execute(
        query,
        {
            "investigation_id": str(investigation_id),
            "event_id": entry.event_id,
            "timestamp": entry.timestamp,
            "entry_type": entry.entry_type.value,
            "title": entry.title,
            "description": entry.description,
            "data": json.dumps(entry.data),
            "tags": entry.tags,
            "user_id": user.user_id,
            "is_visible": entry.is_visible,
        },
    )
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create timeline entry")

    # Broadcast WebSocket message about timeline entry added
    await websocket_manager.broadcast(
        str(investigation_id),
        {
            "type": "timeline_entry_added",
            "investigation_id": str(investigation_id),
            "entry_id": row[0],
        },
    )

    return TimelineEntryRead(
        entry_id=row[0],
        investigation_id=str(row[1]),
        event_id=row[2],
        timestamp=row[3],
        entry_type=row[4],
        title=row[5],
        description=row[6],
        data=row[7] or {},
        tags=row[8] or [],
        created_by_user_id=row[9],
        created_at=row[10],
        updated_at=row[11],
        is_visible=row[12],
        notes=[],
    )


@router.patch("/{investigation_id}/entries/{entry_id}", response_model=TimelineEntryRead)
async def update_timeline_entry(
    investigation_id: UUID,
    entry_id: int,
    entry_update: TimelineEntryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Update a timeline entry with partial data.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation containing the entry.
    entry_id: int
        Primary key of the timeline entry to update.
    entry_update: TimelineEntryUpdate
        Pydantic model containing the fields to modify. Only non-None attributes are applied.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session provided by FastAPI dependency injection.
    user: User, optional
        Authenticated user performing the operation, injected via dependency.

    Returns
    -------
    TimelineEntryRead
        The updated timeline entry representation, including all fields and an empty notes list.

    Raises
    ------
    HTTPException
        * 400 - No fields were supplied for update.
        * 404 - The specified timeline entry does not exist.
    """
    # Build dynamic update query
    update_parts = []
    params: Dict[str, Any] = {"investigation_id": str(investigation_id), "entry_id": entry_id}

    if entry_update.timestamp is not None:
        update_parts.append("timestamp = :timestamp")
        params["timestamp"] = entry_update.timestamp

    if entry_update.entry_type is not None:
        update_parts.append("entry_type = :entry_type")
        params["entry_type"] = entry_update.entry_type.value

    if entry_update.title is not None:
        update_parts.append("title = :title")
        params["title"] = entry_update.title

    if entry_update.description is not None:
        update_parts.append("description = :description")
        params["description"] = entry_update.description

    if entry_update.data is not None:
        update_parts.append("data = CAST(:data AS jsonb)")
        params["data"] = json.dumps(entry_update.data)

    if entry_update.tags is not None:
        update_parts.append("tags = :tags")
        params["tags"] = entry_update.tags

    if entry_update.is_visible is not None:
        update_parts.append("is_visible = :is_visible")
        params["is_visible"] = entry_update.is_visible

    if not update_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    query = text(
        f"""
        UPDATE timeline_entries
        SET {', '.join(update_parts)}, updated_at = NOW()
        WHERE investigation_id = :investigation_id AND entry_id = :entry_id
        RETURNING entry_id, investigation_id, event_id, timestamp, entry_type, title, description,
                  data, tags, created_by_user_id, created_at, updated_at, is_visible
    """
    )

    result = await db.execute(query, params)
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Timeline entry not found")

    return TimelineEntryRead(
        entry_id=row[0],
        investigation_id=str(row[1]),
        event_id=row[2],
        timestamp=row[3],
        entry_type=row[4],
        title=row[5],
        description=row[6],
        data=row[7] or {},
        tags=row[8] or [],
        created_by_user_id=row[9],
        created_at=row[10],
        updated_at=row[11],
        is_visible=row[12],
        notes=[],
    )


@router.delete("/{investigation_id}/entries/{entry_id}")
async def delete_timeline_entry(
    investigation_id: UUID,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete a timeline entry and cascade deletion to its associated notes.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation containing the timeline entry.
    entry_id: int
        Unique identifier of the timeline entry to be removed.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session injected via FastAPI dependency. Defaults to the result of `get_db`.
    user: User, optional
        The authenticated user performing the operation, provided by `get_current_user`.

    Returns
    -------
    dict
        A JSON-serializable dictionary with keys `status` (always `"ok"`) and `message` describing the deleted entry.

    Raises
    ------
    HTTPException
        If no timeline entry matches the supplied `investigation_id` and `entry_id`, a 404 error is raised.
    """
    query = text(
        """
        DELETE FROM timeline_entries
        WHERE investigation_id = :investigation_id AND entry_id = :entry_id
        RETURNING entry_id
    """
    )

    result = await db.execute(
        query, {"investigation_id": str(investigation_id), "entry_id": entry_id}
    )
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Timeline entry not found")

    # Broadcast WebSocket message about timeline entry removed
    await websocket_manager.broadcast(
        str(investigation_id),
        {
            "type": "timeline_entry_removed",
            "investigation_id": str(investigation_id),
            "entry_id": entry_id,
        },
    )

    return {"status": "ok", "message": f"Timeline entry {entry_id} deleted"}


@router.post("/{investigation_id}/entries/{entry_id}/notes", response_model=TimelineNoteRead)
async def create_note(
    investigation_id: UUID,
    entry_id: int,
    note: TimelineNoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Add a note to a specific timeline entry within an investigation.

    Args:
        investigation_id (UUID): Identifier of the investigation to which the timeline entry belongs.
        entry_id (int): Primary key of the timeline entry that will receive the new note.
        note (TimelineNoteCreate): Pydantic model containing the text of the note to be created.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session provided by FastAPI dependency injection. Defaults to Depends(get_db).
        user (User, optional): The authenticated user making the request, injected via dependency. Defaults to Depends(get_current_user).

    Returns:
        TimelineNoteRead: A read-only representation of the newly created note, including its identifiers, timestamps, and the username of the author.

    Raises:
        HTTPException:
            - 404 if the specified timeline entry does not exist or does not belong to the given investigation.
            - 500 if the database insertion fails for an unexpected reason.
    """
    # Verify entry exists and belongs to investigation
    entry_check = text(
        """
        SELECT entry_id FROM timeline_entries
        WHERE entry_id = :entry_id AND investigation_id = :investigation_id
    """
    )
    entry_result = await db.execute(
        entry_check, {"entry_id": entry_id, "investigation_id": str(investigation_id)}
    )
    if not entry_result.fetchone():
        raise HTTPException(status_code=404, detail="Timeline entry not found")

    query = text(
        """
        INSERT INTO timeline_notes (entry_id, user_id, note_text)
        VALUES (:entry_id, :user_id, :note_text)
        RETURNING note_id, entry_id, user_id, note_text, created_at, updated_at
    """
    )

    result = await db.execute(
        query, {"entry_id": entry_id, "user_id": user.user_id, "note_text": note.note_text}
    )
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create note")

    return TimelineNoteRead(
        note_id=row[0],
        entry_id=row[1],
        user_id=row[2],
        note_text=row[3],
        created_at=row[4],
        updated_at=row[5],
        username=user.username,
    )


@router.get("/{investigation_id}/entries/{entry_id}/notes", response_model=List[TimelineNoteRead])
async def get_notes(
    investigation_id: UUID,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get all notes associated with a specific timeline entry within an investigation.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation to which the timeline entry belongs.
    entry_id: int
        Unique identifier of the timeline entry whose notes are being retrieved.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session injected via FastAPI dependency. Used for executing database queries.
    user: User, optional
        The currently authenticated user injected via FastAPI dependency.

    Returns
    -------
    list[TimelineNoteRead]
        A list of `TimelineNoteRead` objects, each representing a note linked to the specified entry. The notes are ordered chronologically by their creation timestamp.

    Raises
    ------
    HTTPException
        If no timeline entry matching `entry_id` and `investigation_id` exists, a 404 error is raised indicating that the timeline entry was not found.
    """
    # Verify entry exists
    entry_check = text(
        """
        SELECT entry_id FROM timeline_entries
        WHERE entry_id = :entry_id AND investigation_id = :investigation_id
    """
    )
    entry_result = await db.execute(
        entry_check, {"entry_id": entry_id, "investigation_id": str(investigation_id)}
    )
    if not entry_result.fetchone():
        raise HTTPException(status_code=404, detail="Timeline entry not found")

    query = text(
        """
        SELECT n.note_id, n.entry_id, n.user_id, n.note_text, n.created_at, n.updated_at, u.username
        FROM timeline_notes n
        LEFT JOIN users u ON n.user_id = u.user_id
        WHERE n.entry_id = :entry_id
        ORDER BY n.created_at ASC
    """
    )

    result = await db.execute(query, {"entry_id": entry_id})
    rows = result.fetchall()

    return [
        TimelineNoteRead(
            note_id=row[0],
            entry_id=row[1],
            user_id=row[2],
            note_text=row[3],
            created_at=row[4],
            updated_at=row[5],
            username=row[6],
        )
        for row in rows
    ]


@router.patch("/{investigation_id}/notes/{note_id}", response_model=TimelineNoteRead)
async def update_note(
    investigation_id: UUID,
    note_id: int,
    note_update: TimelineNoteUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Update a timeline note belonging to an investigation.

    Args:
        investigation_id (UUID): Identifier of the investigation containing the note.
        note_id (int): Primary key of the note to be updated.
        note_update (TimelineNoteUpdate): Pydantic model with the new `note_text` value.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session injected by FastAPI's dependency system. Defaults to Depends(get_db).
        user (User, optional): Authenticated user object provided by the `get_current_user` dependency.

    Raises:
        HTTPException:
            - 404 if no note matching `note_id` exists within the specified investigation.
            - 403 if the authenticated user is not an admin (role != 1) and does not own the note.
            - 500 if the update operation fails to return a record.

    Returns:
        TimelineNoteRead: A read-only representation of the updated note, including `note_id`, `entry_id`, `user_id`, `note_text`, timestamps, and the author's username (or `None` if not found).
    """
    # Check if note exists and belongs to user (or user is admin)
    check_query = text(
        """
        SELECT n.note_id, n.user_id, te.investigation_id
        FROM timeline_notes n
        JOIN timeline_entries te ON n.entry_id = te.entry_id
        WHERE n.note_id = :note_id AND te.investigation_id = :investigation_id
    """
    )

    check_result = await db.execute(
        check_query, {"note_id": note_id, "investigation_id": str(investigation_id)}
    )
    check_row = check_result.fetchone()

    if not check_row:
        raise HTTPException(status_code=404, detail="Note not found")

    # Verify ownership (unless admin)
    if user.role != 1 and check_row[1] != user.user_id:
        raise HTTPException(status_code=403, detail="You can only edit your own notes")

    query = text(
        """
        UPDATE timeline_notes
        SET note_text = :note_text, updated_at = NOW()
        WHERE note_id = :note_id
        RETURNING note_id, entry_id, user_id, note_text, created_at, updated_at
    """
    )

    result = await db.execute(query, {"note_id": note_id, "note_text": note_update.note_text})
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to update note")

    # Get username
    user_query = text("SELECT username FROM users WHERE user_id = :user_id")
    user_result = await db.execute(user_query, {"user_id": row[2]})
    username_row = user_result.fetchone()

    return TimelineNoteRead(
        note_id=row[0],
        entry_id=row[1],
        user_id=row[2],
        note_text=row[3],
        created_at=row[4],
        updated_at=row[5],
        username=username_row[0] if username_row else None,
    )


@router.delete("/{investigation_id}/notes/{note_id}")
async def delete_note(
    investigation_id: UUID,
    note_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete a note from an investigation.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation containing the note.
    note_id: int
        Primary key of the note to be deleted.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session provided by FastAPI dependency injection.
    user: User, optional
        The authenticated user performing the operation, injected via dependency.

    Returns
    -------
    dict
        A JSON-serializable dictionary with keys `status` (always `"ok"`) and `message` confirming deletion, e.g. `{"status": "ok", "message": "Note 42 deleted"}`.

    Raises
    ------
    HTTPException
        * 404 - If the note does not exist within the specified investigation.
        * 403 - If the user is not an admin (role != 1) and does not own the note.
        * 500 - If the deletion query does not return a row, indicating a failure to delete.
    """
    # Check if note exists and belongs to user (or user is admin)
    check_query = text(
        """
        SELECT n.note_id, n.user_id, te.investigation_id
        FROM timeline_notes n
        JOIN timeline_entries te ON n.entry_id = te.entry_id
        WHERE n.note_id = :note_id AND te.investigation_id = :investigation_id
    """
    )

    check_result = await db.execute(
        check_query, {"note_id": note_id, "investigation_id": str(investigation_id)}
    )
    check_row = check_result.fetchone()

    if not check_row:
        raise HTTPException(status_code=404, detail="Note not found")

    # Verify ownership (unless admin)
    if user.role != 1 and check_row[1] != user.user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own notes")

    query = text("DELETE FROM timeline_notes WHERE note_id = :note_id RETURNING note_id")
    result = await db.execute(query, {"note_id": note_id})
    await db.commit()

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to delete note")

    return {"status": "ok", "message": f"Note {note_id} deleted"}


@router.get("/{investigation_id}/event-types")
async def get_timeline_event_types(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Fetches a summary of distinct event types associated with timeline entries for a given investigation.

    Args:
        investigation_id (UUID): Identifier of the investigation whose timeline entry events are being queried.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session provided by FastAPI dependency injection.
        user (User, optional): The currently authenticated user, injected via dependency.

    Returns:
        dict: A dictionary containing:
            - "event_types" (list[dict]): List of dictionaries each with:
                * "event_type" (str): The unique event type name.
                * "count" (int): Number of timeline entries that reference this event type.
              Ordered by descending count and then alphabetically by event type.
            - "total_types" (int): Total number of distinct event types found.
    """
    query = text(
        """
        SELECT DISTINCT e.event_type, COUNT(*) as count
        FROM timeline_entries te
        JOIN events e ON te.event_id = e.event_id
        WHERE te.investigation_id = :investigation_id
        GROUP BY e.event_type
        ORDER BY count DESC, e.event_type ASC
    """
    )

    result = await db.execute(query, {"investigation_id": str(investigation_id)})

    rows = result.fetchall()

    event_types = [{"event_type": row[0], "count": row[1]} for row in rows]

    return {"event_types": event_types, "total_types": len(event_types)}


@router.get("/{investigation_id}/fields")
async def get_timeline_fields(
    investigation_id: UUID,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get a sorted list of unique JSONB field names present in timeline entry data for a given investigation.

    The function retrieves a sample of timeline entries - either 10 entries per event type (if no filter)
    or 10 entries for a specific event type - and extracts the keys from their `data` column.
    It returns those keys alphabetically, together with metadata about the operation.

    Args:
        investigation_id (UUID): Identifier of the investigation whose timeline entries are queried.
        event_type (str, optional): If provided, limits the sample to 10 entries linked to events of this type;
            otherwise samples 10 entries per distinct event type.
        db (AsyncSession): Asynchronous SQLAlchemy session injected by FastAPI's dependency system.
        user (User): The current authenticated user, also injected via dependency.

    Returns:
        dict: A mapping with three entries:
            `fields` (list[str]): Alphabetically sorted list of unique data field names found in the sampled entries.
            `count` (int): Number of distinct fields returned.
            `entries_sampled` (int): Number of timeline entry rows examined to derive the field set.

    Raises:
        HTTPException: Propagated from `check_investigation_access` if the user lacks permission to view the investigation.
    """
    # Build query based on whether event_type filter is provided
    if event_type:
        # Get sample of 10 timeline entries for specific event type
        query = """
            SELECT te.entry_id, te.data
            FROM timeline_entries te
            JOIN events e ON te.event_id = e.event_id
            WHERE te.investigation_id = :investigation_id
              AND e.event_type = :event_type
              AND te.is_visible = true
            ORDER BY te.timestamp DESC
            LIMIT 10
        """
        params = {"investigation_id": str(investigation_id), "event_type": event_type}
    else:
        # Get 10 timeline entries per event_type using window function
        # This efficiently samples multiple entries per type
        query = """
            SELECT entry_id, data
            FROM (
                SELECT
                    te.entry_id,
                    te.data,
                    ROW_NUMBER() OVER (PARTITION BY e.event_type ORDER BY te.timestamp DESC) as rn
                FROM timeline_entries te
                JOIN events e ON te.event_id = e.event_id
                WHERE te.investigation_id = :investigation_id
                  AND te.is_visible = true
            ) AS ranked
            WHERE rn <= 10
        """
        params = {"investigation_id": str(investigation_id)}

    result = await db.execute(text(query), params)

    rows = result.fetchall()

    # Extract all unique field names from data JSONB and linked event payloads
    field_set = set()

    for row in rows:
        data = row[1]  # data is the second column

        if isinstance(data, dict):
            # Data is already a dict (JSONB)
            field_set.update(data.keys())
            
            # Also extract nested payload fields if they exist
            if 'payload' in data and isinstance(data['payload'], dict):
                field_set.update(data['payload'].keys())
        elif isinstance(data, str):
            # Data might be a JSON string
            try:
                data_dict = json.loads(data)
                if isinstance(data_dict, dict):
                    field_set.update(data_dict.keys())
                    
                    # Also extract nested payload fields
                    if 'payload' in data_dict and isinstance(data_dict['payload'], dict):
                        field_set.update(data_dict['payload'].keys())
            except (json.JSONDecodeError, TypeError):
                pass
    
    # If we didn't find many fields from timeline entry data, also sample from linked events
    # This is useful when timeline entries have minimal data but link to rich event payloads
    if len(field_set) < 10:
        # Get sample of linked event payloads
        if event_type:
            event_query = """
                SELECT e.payload
                FROM timeline_entries te
                JOIN events e ON te.event_id = e.event_id
                WHERE te.investigation_id = :investigation_id
                  AND e.event_type = :event_type
                  AND te.is_visible = true
                ORDER BY te.timestamp DESC
                LIMIT 10
            """
            event_params = {"investigation_id": str(investigation_id), "event_type": event_type}
        else:
            event_query = """
                SELECT e.payload
                FROM (
                    SELECT
                        te.event_id,
                        ROW_NUMBER() OVER (PARTITION BY e.event_type ORDER BY te.timestamp DESC) as rn
                    FROM timeline_entries te
                    JOIN events e ON te.event_id = e.event_id
                    WHERE te.investigation_id = :investigation_id
                      AND te.is_visible = true
                ) AS ranked
                JOIN events e ON ranked.event_id = e.event_id
                WHERE ranked.rn <= 10
            """
            event_params = {"investigation_id": str(investigation_id)}
        
        event_result = await db.execute(text(event_query), event_params)
        event_rows = event_result.fetchall()
        
        for event_row in event_rows:
            payload = event_row[0]
            if isinstance(payload, dict):
                field_set.update(payload.keys())
            elif isinstance(payload, str):
                try:
                    payload_dict = json.loads(payload)
                    if isinstance(payload_dict, dict):
                        field_set.update(payload_dict.keys())
                except (json.JSONDecodeError, TypeError):
                    pass

    # Return sorted list of field names
    fields = sorted(list(field_set))

    return {"fields": fields, "count": len(fields), "entries_sampled": len(rows)}


@router.get("/{investigation_id}/stats", response_model=TimelineStatsResponse)
async def get_timeline_stats(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retrieve statistical information for timeline entries belonging to a specific investigation.

    Parameters
    ----------
    investigation_id: UUID
        Unique identifier of the investigation whose timeline data is being queried.
    db: AsyncSession, optional
        Asynchronous SQLAlchemy session injected by FastAPI's dependency system; used to execute raw SQL queries.
    user: User, optional
        The currently authenticated user provided by the `get_current_user` dependency. Access control checks are assumed to be performed elsewhere.

    Returns
    -------
    TimelineStatsResponse
        An object containing aggregated timeline metrics:
            * total_entries (int): Count of visible timeline entries for the investigation.
            * entries_by_type (dict[str, int]): Mapping of each entry type to its occurrence count.
            * date_range (dict): `{"earliest": datetime | None, "latest": datetime | None}` indicating the span of timestamps across all visible entries.
            * tags (list[str]): List of unique tags collected from the `tags` array column of visible entries.
            * total_notes (int): Count of notes associated with entries in the investigation.

    Raises
    ------
    Any database-related exceptions propagated by SQLAlchemy during query execution.
    """
    # Total entries
    total_query = text(
        """
        SELECT COUNT(*) FROM timeline_entries
        WHERE investigation_id = :investigation_id AND is_visible = true
    """
    )
    total_result = await db.execute(total_query, {"investigation_id": str(investigation_id)})
    total_entries = total_result.scalar() or 0

    # Entries by type
    type_query = text(
        """
        SELECT entry_type, COUNT(*) as count
        FROM timeline_entries
        WHERE investigation_id = :investigation_id AND is_visible = true
        GROUP BY entry_type
    """
    )
    type_result = await db.execute(type_query, {"investigation_id": str(investigation_id)})
    entries_by_type = {row[0]: row[1] for row in type_result.fetchall()}

    # Date range
    range_query = text(
        """
        SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest
        FROM timeline_entries
        WHERE investigation_id = :investigation_id AND is_visible = true
    """
    )
    range_result = await db.execute(range_query, {"investigation_id": str(investigation_id)})
    range_row = range_result.fetchone()
    date_range = {
        "earliest": range_row[0] if range_row else None,
        "latest": range_row[1] if range_row else None,
    }

    # Unique tags
    tags_query = text(
        """
        SELECT DISTINCT unnest(tags) as tag
        FROM timeline_entries
        WHERE investigation_id = :investigation_id AND is_visible = true
    """
    )
    tags_result = await db.execute(tags_query, {"investigation_id": str(investigation_id)})
    tags = [row[0] for row in tags_result.fetchall()]

    # Total notes
    notes_query = text(
        """
        SELECT COUNT(*)
        FROM timeline_notes n
        JOIN timeline_entries te ON n.entry_id = te.entry_id
        WHERE te.investigation_id = :investigation_id
    """
    )
    notes_result = await db.execute(notes_query, {"investigation_id": str(investigation_id)})
    total_notes = notes_result.scalar() or 0

    return TimelineStatsResponse(
        total_entries=total_entries,
        entries_by_type=entries_by_type,
        date_range=date_range,
        tags=tags,
        total_notes=total_notes,
    )
