from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional

from ..deps import get_db, require_admin
from ..models.user import User

router = APIRouter()


@router.get("/")
async def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    action_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """
    List audit log entries for administrators.

    Args:
        limit (int): Maximum number of log entries to return. Defaults to 100.
        offset (int): Number of entries to skip before starting to collect the result set. Defaults to 0.
        action_type (Optional[str]): If provided, filters logs to only those with the specified action type.
        db (AsyncSession): Database session injected by FastAPI's dependency system.
        user (User): The currently authenticated admin user, injected via `require_admin`.

    Returns:
        dict: A dictionary containing pagination metadata and log entries with the following keys:
            - `entries` (list[dict]): List of audit log records as dictionaries.
            - `count` (int): Number of entries returned in this response.
            - `total` (int): Total number of matching audit log records in the database.
            - `limit` (int): The limit value used for pagination.
            - `offset` (int): The offset value used for pagination.

    Raises:
        HTTPException: If the requesting user is not an administrator (handled by `require_admin`).
    """
    query = """
        SELECT 
            log_id,
            timestamp,
            user_id,
            action_type,
            investigation_id,
            details
        FROM audit_log
    """

    params: dict = {"limit": limit, "offset": offset}

    if action_type:
        query += " WHERE action_type = :action_type"
        params["action_type"] = action_type

    query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"

    result = await db.execute(text(query), params)
    rows = [dict(r._mapping) for r in result.fetchall()]

    # Get total count
    count_query = "SELECT COUNT(*) FROM audit_log"
    if action_type:
        count_query += " WHERE action_type = :action_type"
    count_result = await db.execute(
        text(count_query), {"action_type": action_type} if action_type else {}
    )
    total = count_result.scalar()

    return {"entries": rows, "count": len(rows), "total": total, "limit": limit, "offset": offset}


@router.get("/deletions")
async def list_deletion_logs(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """
    List investigation deletion logs with pagination (admin only).

    Args:
        limit (int): Maximum number of log entries to return. Defaults to 100.
        offset (int): Number of log entries to skip before starting to collect the result set. Defaults to 0.
        db (AsyncSession): Asynchronous SQLAlchemy session injected by FastAPI's dependency system.
        user (User): Authenticated admin user injected by FastAPI's dependency system; required for authorization.

    Returns:
        dict: A dictionary containing pagination metadata and log entries:
            - deletions (list[dict]): List of deletion log records, each with keys `deletion_id`, `investigation_id`, `deleted_at`,
              `deleted_by_user_id`, `investigation_title`, `artifact_count` and `total_size_bytes`.
            - count (int): Number of records returned in the current response (may be less than `limit`).
            - total (int): Total number of deletion log entries available in the database.
            - limit (int): The `limit` value used for this request.
            - offset (int): The `offset` value used for this request.
    """
    query = """
        SELECT 
            deletion_id,
            investigation_id,
            deleted_at,
            deleted_by_user_id,
            investigation_title,
            artifact_count,
            total_size_bytes
        FROM deletion_log
        ORDER BY deleted_at DESC
        LIMIT :limit OFFSET :offset
    """

    result = await db.execute(text(query), {"limit": limit, "offset": offset})
    rows = [dict(r._mapping) for r in result.fetchall()]

    # Get total count
    count_result = await db.execute(text("SELECT COUNT(*) FROM deletion_log"))
    total = count_result.scalar()

    return {"deletions": rows, "count": len(rows), "total": total, "limit": limit, "offset": offset}
