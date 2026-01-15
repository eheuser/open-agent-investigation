from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.mcp_server import MCPServer


async def create_mcp(
    db: AsyncSession,
    name: str,
    base_url: str,
    auth_token: Optional[str],
    allowed_agents: List[str],
    owner_user_id: int,
) -> MCPServer:
    """
    Create a new MCPServer record in the database.

    Args:
        db (AsyncSession): Asynchronous SQLAlchemy session used for DB operations.
        name (str): Human-readable name for the MCP server.
        base_url (str): Base HTTP URL of the MCP endpoint.
        auth_token (Optional[str]): Optional bearer token required for authentication with the server.
        allowed_agents (List[str]): List of agent identifiers permitted to use this server.
        owner_user_id (int): Identifier of the user who owns the server definition.

    Returns:
        MCPServer: The newly created and persisted MCPServer instance.
    """
    server = MCPServer(
        name=name,
        base_url=base_url,
        auth_token=auth_token,
        allowed_agents=allowed_agents,
        owner_user_id=owner_user_id,
    )

    db.add(server)
    await db.commit()
    await db.refresh(server)

    return server


async def get_mcp_by_id(db: AsyncSession, server_id: int) -> Optional[MCPServer]:
    """
    Retrieve an MCPServer record by its unique identifier.

    Args:
        db (AsyncSession): The asynchronous database session used for the query.
        server_id (int): The primary key of the MCPServer to retrieve.

    Returns:
        Optional[MCPServer]: The matching MCPServer instance if found; otherwise, `None`.
    """
    result = await db.execute(select(MCPServer).where(MCPServer.server_id == server_id))
    return result.scalars().first()


async def get_mcp_by_name(db: AsyncSession, name: str) -> Optional[MCPServer]:
    """
    Retrieve an MCPServer instance matching the given name.

    Args:
        db (AsyncSession): The asynchronous database session used for the query.
        name (str): The unique name of the MCP server to retrieve.

    Returns:
        Optional[MCPServer]: The MCPServer object if a record with the specified name exists; otherwise, `None`.
    """
    result = await db.execute(select(MCPServer).where(MCPServer.name == name))
    return result.scalars().first()


async def list_mcp_servers(
    db: AsyncSession, user_id: Optional[int] = None, is_admin: bool = False
) -> List[MCPServer]:
    """
    List MCPServer records visible to a user.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous database session used to execute the query.
    user_id : int or None, optional
        Identifier of the requesting user. If provided and `is_admin` is `False`,
        only servers owned by this user are returned. Defaults to `None`.
    is_admin : bool, optional
        Flag indicating whether the caller has administrative privileges. When
        `True`, all MCPServer records are listed regardless of ownership.
        Defaults to `False`.

    Returns
    -------
    list[MCPServer]
        A list of :class:`MCPServer` objects ordered by their name. The list is
        filtered according to the user's visibility rules described above.
    """
    query = select(MCPServer)

    # Regular users see only their own servers
    if not is_admin and user_id is not None:
        query = query.where(MCPServer.owner_user_id == user_id)

    result = await db.execute(query.order_by(MCPServer.name))
    return list(result.scalars().all())


async def update_mcp(db: AsyncSession, server_id: int, **kwargs) -> Optional[MCPServer]:
    """
    Update an MCPServer record with the provided field values.

    Args:
        db (AsyncSession): An asynchronous SQLAlchemy session used for database operations.
        server_id (int): The unique identifier of the MCPServer to update.
        **kwargs: Arbitrary keyword arguments where each key corresponds to a mutable attribute
            of `MCPServer` and its value is the new data to set. Attributes that do not exist
            on the model or have a value of `None` are ignored.

    Returns:
        Optional[MCPServer]: The updated `MCPServer` instance if it exists; otherwise `None`.
    """
    server = await get_mcp_by_id(db, server_id)
    if not server:
        return None

    for key, value in kwargs.items():
        if hasattr(server, key) and value is not None:
            setattr(server, key, value)

    await db.commit()
    await db.refresh(server)

    return server


async def delete_mcp(db: AsyncSession, server_id: int) -> bool:
    """
    Delete an MCP server record from the database.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database operations.
    server_id : int
        The unique identifier of the MCP server to be deleted.

    Returns
    -------
    bool
        `True` if a server with the given `server_id` was found and successfully removed;
        `False` if no matching server existed.
    """
    server = await get_mcp_by_id(db, server_id)
    if not server:
        return False

    await db.delete(server)
    await db.commit()

    return True


__all__ = [
    "create_mcp",
    "get_mcp_by_id",
    "get_mcp_by_name",
    "list_mcp_servers",
    "update_mcp",
    "delete_mcp",
]
