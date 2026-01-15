from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..deps import get_db, get_current_user, require_admin
from ..models.user import User
from ..schemas.mcp_server import MCPServerCreate, MCPServerRead, MCPServerUpdate
from ..crud import mcp_server as crud

router = APIRouter()


@router.post("/", response_model=MCPServerRead, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    payload: MCPServerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Create a new MCP server definition in the database.

    Parameters
    ----------
    payload: MCPServerCreate
        The data required to create the MCP server, including name, base URL,
        authentication token, and allowed agents.
    db: AsyncSession, optional
        An asynchronous SQLAlchemy session provided by dependency injection.
    user: User, optional
        The currently authenticated user, injected via dependency injection; the
        user's ID will be set as the owner of the new server.

    Returns
    -------
    MCPServer
        The newly created MCP server record with its generated identifier and
        ownership information.
    """
    srv = await crud.create_mcp(
        db,
        name=payload.name,
        base_url=payload.base_url,
        auth_token=payload.auth_token,
        allowed_agents=payload.allowed_agents,
        owner_user_id=user.user_id,
    )
    return srv


@router.get("/", response_model=List[MCPServerRead])
async def list_mcp_servers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List MCP servers visible to the current user.

    Regular users see only their own servers; administrators see all servers.

    Args:
        db (AsyncSession): The asynchronous database session.
        user (User): The currently authenticated user.

    Returns:
        List[Server]: A list of MCP server records that the user is permitted to view.
    """
    servers = await crud.list_mcp_servers(db, user_id=user.user_id, is_admin=user.is_admin())
    return servers


@router.get("/{server_id}", response_model=MCPServerRead)
async def get_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retrieve an MCP server by its identifier.

    Parameters
    ----------
    server_id: int
        The unique identifier of the MCP server to retrieve.
    db: AsyncSession, optional
        An asynchronous SQLAlchemy session provided via dependency injection.
    user: User, optional
        The currently authenticated user obtained from the request context.

    Returns
    -------
    MCPServer
        The requested MCP server object if it exists and the caller has permission to view it.

    Raises
    ------
    HTTPException
        * 404 NOT FOUND - when no MCP server with `server_id` exists.
        * 403 FORBIDDEN - when the authenticated user is neither an admin nor the owner of the server.
    """
    server = await crud.get_mcp_by_id(db, server_id)

    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    # Check permissions
    if not user.is_admin() and server.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return server


@router.patch("/{server_id}", response_model=MCPServerRead)
async def update_mcp_server(
    server_id: int,
    payload: MCPServerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Update an MCP server's configuration.

    Args:
        server_id (int): The unique identifier of the MCP server to update.
        payload (MCPServerUpdate): A Pydantic model containing the fields to be updated; only provided fields are applied.
        db (AsyncSession, optional): The asynchronous database session injected by FastAPI dependency injection.
        user (User, optional): The currently authenticated user injected by FastAPI dependency injection.

    Returns:
        MCPServer: The updated MCP server instance reflecting the applied changes.

    Raises:
        HTTPException: If no server with `server_id` exists (HTTP 404) or if the requesting user is neither the owner nor an administrator (HTTP 403).
    """
    server = await crud.get_mcp_by_id(db, server_id)

    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    # Check permissions (owner or admin can update)
    if not user.is_admin() and server.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    updated = await crud.update_mcp(db, server_id, **payload.model_dump(exclude_unset=True))

    return updated


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete an MCP server record from the database.

    Args:
        server_id (int): The unique identifier of the MCP server to delete.
        db (AsyncSession): An asynchronous SQLAlchemy session provided by dependency injection.
        user (User): The currently authenticated user, injected via dependency.

    Raises:
        HTTPException: If no server with the given `server_id` exists (404 Not Found).
        HTTPException: If the requesting user is neither an admin nor the owner of the server (403 Forbidden).
    """
    server = await crud.get_mcp_by_id(db, server_id)

    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    # Check permissions (owner or admin can delete)
    if not user.is_admin() and server.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await crud.delete_mcp(db, server_id)


__all__ = ["router"]
