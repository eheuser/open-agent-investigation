from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import List

from ..deps import get_db, get_current_user
from ..models.user import User
from ..crud.investigation import check_investigation_access

router = APIRouter()


@router.post("/nodes/{investigation_id}/{node_id}")
async def add_node_tags(
    investigation_id: UUID,
    node_id: int,
    tags: List[str] = [],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Add tags to a graph node. This endpoint is deprecated and always returns an HTTP 410 Gone error.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation containing the node.
    node_id: int
        Unique identifier of the node within the investigation.
    tags: List[str], optional
        List of tag strings to add to the node. Defaults to an empty list.
    db: AsyncSession, optional
        Database session dependency injected by FastAPI.
    user: User, optional
        The authenticated user performing the operation.

    Raises
    ------
    HTTPException
        Always raised with status_code 410 and a detail message indicating that graph nodes are deprecated in favor of timeline entry tags.
    """
    raise HTTPException(
        status_code=410, detail="Graph nodes are deprecated. Use /api/v1/timeline tags instead."
    )


@router.delete("/nodes/{investigation_id}/{node_id}")
async def remove_node_tags(
    investigation_id: UUID,
    node_id: int,
    tags: List[str] = [],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Remove one or more tags from a specific graph node.

    This endpoint is deprecated and always responds with HTTP 410 Gone.  Clients should use the timeline entry tagging API (`/api/v1/timeline`) instead.

    Args:
        investigation_id (UUID): Identifier of the investigation containing the node.
        node_id (int): Unique identifier of the node from which tags should be removed.
        tags (List[str], optional): List of tag strings to remove.  An empty list is treated as a no-op but still triggers the deprecation response. Defaults to an empty list.
        db (AsyncSession, optional): Database session provided by FastAPI dependency injection. Defaults to `Depends(get_db)`.
        user (User, optional): The authenticated user performing the operation, supplied via dependency injection. Defaults to `Depends(get_current_user)`.

    Raises:
        HTTPException: Always raised with status code 410 and a detail message indicating that graph node tagging is deprecated in favor of timeline entry tags.
    """
    raise HTTPException(
        status_code=410, detail="Graph nodes are deprecated. Use /api/v1/timeline tags instead."
    )


@router.post("/edges/{investigation_id}/{edge_id}")
async def add_edge_tags(
    investigation_id: UUID,
    edge_id: int,
    tags: List[str] = [],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Add tags to a graph edge (DEPRECATED).

    Args:
        investigation_id: Identifier of the investigation.
        edge_id: Unique identifier of the edge within the investigation.
        tags: List of tag strings to associate with the edge. Defaults to an empty list.
        db: Asynchronous database session, injected via dependency injection.
        user: Current authenticated user, injected via dependency injection.

    Raises:
        HTTPException: Always raised with status code 410 and a detail message indicating that graph edges are deprecated and directing users to use the timeline tags endpoint instead.
    """
    raise HTTPException(
        status_code=410, detail="Graph edges are deprecated. Use /api/v1/timeline tags instead."
    )


@router.delete("/edges/{investigation_id}/{edge_id}")
async def remove_edge_tags(
    investigation_id: UUID,
    edge_id: int,
    tags: List[str] = [],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Remove tags from a graph edge (DEPRECATED).

    Args:
        investigation_id: Unique identifier of the investigation.
        edge_id: Identifier of the edge from which to remove tags.
        tags: List of tag strings to be removed; defaults to an empty list.
        db: Asynchronous database session, injected via dependency injection.
        user: Current authenticated user, injected via dependency injection.

    Raises:
        HTTPException: Always raised with status code 410 and a detail message indicating that graph edge tagging is deprecated in favor of timeline entry tags.
    """
    raise HTTPException(
        status_code=410, detail="Graph edges are deprecated. Use /api/v1/timeline tags instead."
    )
