from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from ..models.tool_execution import ToolExecution


async def create_tool_execution(
    db: AsyncSession,
    chat_message_id: int,
    tool_name: str,
    display_name: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
    execution_number: Optional[int] = None,
    max_tools: Optional[int] = None,
) -> ToolExecution:
    """
    Create and persist a new tool execution record in the database.

    This function constructs a :class:`ToolExecution` instance with the provided
    metadata, adds it to the given asynchronous SQLAlchemy session, commits the
    transaction, refreshes the instance to load any generated defaults (e.g., primary
    key), and returns the resulting object.

    Args:
        db: An active :class:`AsyncSession` used for database operations.
        chat_message_id: The identifier of the parent chat message that triggered the tool execution.
        tool_name: The internal name of the tool being executed.
        display_name: Optional human-readable name for the tool; defaults to `tool_name` when omitted.
        arguments: Optional dictionary of arguments supplied to the tool; defaults to an empty dict.
        execution_number: Optional sequential number indicating this execution's order within a larger agent run.
        max_tools: Optional limit on the total number of tools that may be executed in the current context.

    Returns:
        The newly created and persisted :class:`ToolExecution` instance, with all fields populated
        (including any database-generated values).
    """
    execution = ToolExecution(
        chat_message_id=chat_message_id,
        tool_name=tool_name,
        display_name=display_name or tool_name,
        arguments=arguments or {},
        status="executing",
        execution_number=execution_number,
        max_tools=max_tools,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def update_tool_execution(
    db: AsyncSession,
    execution_id: int,
    result: Optional[Dict[str, Any]] = None,
    result_summary: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[ToolExecution]:
    """
    Update an existing tool execution record with optional result data, summary, and status.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database operations.
    execution_id : int
        Identifier of the tool execution to be updated.
    result : dict[str, Any] | None, optional
        Structured result data produced by the tool. If `None` is passed, the existing result remains unchanged.
    result_summary : str | None, optional
        A human-readable summary of the tool's outcome. If omitted, the current summary is left untouched.
    status : str | None, optional
        New execution status (e.g., `"completed"`, `"failed"`, or other custom states). When set to `"completed"` or `"failed"`, the `finished_at` timestamp is automatically updated to the current time.

    Returns
    -------
    ToolExecution | None
        The refreshed `ToolExecution` instance reflecting the applied changes, or `None` if no record with the given `execution_id` exists.
    """
    execution = await get_tool_execution(db, execution_id)
    if not execution:
        return None

    if result is not None:
        execution.result = result
    if result_summary is not None:
        execution.result_summary = result_summary
    if status is not None:
        execution.status = status
        if status in ("completed", "failed"):
            execution.finished_at = func.now()

    await db.commit()
    await db.refresh(execution)
    return execution


async def complete_tool_execution(
    db: AsyncSession,
    execution_id: int,
    result: Optional[Dict[str, Any]] = None,
    result_summary: Optional[str] = None,
    success: bool = True,
) -> Optional[ToolExecution]:
    """
    Mark a tool execution as completed and update its stored data.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used for database operations.
    execution_id : int
        The unique identifier of the tool execution record to be marked as complete.
    result : dict[str, Any] or None, optional
        A dictionary containing the raw result data produced by the tool. If `None` is provided,
        the existing result (if any) remains unchanged.
    result_summary : str or None, optional
        A human-readable summary of the execution outcome. Supplying `None` leaves the current
        summary untouched.
    success : bool, default True
        Indicates whether the tool finished successfully. When `True`, the status is set to
        `"completed"`, otherwise it is set to `"failed"`.

    Returns
    -------
    ToolExecution or None
        The updated :class:`~models.ToolExecution` instance if a matching record was found;
        otherwise `None` is returned.

    Notes
    -----
    This function is a thin wrapper around :func:`update_tool_execution`; it forwards all arguments
    and determines the appropriate `status` value based on the `success` flag.
    """
    return await update_tool_execution(
        db=db,
        execution_id=execution_id,
        result=result,
        result_summary=result_summary,
        status="completed" if success else "failed",
    )


async def get_tool_execution(
    db: AsyncSession,
    execution_id: int,
) -> Optional[ToolExecution]:
    """
    Fetch a single :class:`~models.ToolExecution` record by its primary key.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for the query.
    execution_id : int
        Identifier of the tool execution to retrieve.

    Returns
    -------
    Optional[ToolExecution]
        The matching `ToolExecution` instance, or `None` if no such record exists.
    """
    result = await db.execute(
        select(ToolExecution).where(ToolExecution.execution_id == execution_id)
    )
    return result.scalar_one_or_none()


async def get_message_tool_executions(
    db: AsyncSession,
    chat_message_id: int,
) -> List[ToolExecution]:
    """
    Retrieve all tool execution records associated with a specific chat message.\n\nArgs:\n    db (AsyncSession): The asynchronous SQLAlchemy session used for database access.\n    chat_message_id (int): Identifier of the parent chat message whose tool executions are to be fetched.\n\nReturns:\n    List[ToolExecution]: A list of `ToolExecution` objects ordered by their `started_at` timestamp in ascending order.
    """
    result = await db.execute(
        select(ToolExecution)
        .where(ToolExecution.chat_message_id == chat_message_id)
        .order_by(ToolExecution.started_at.asc())
    )
    return list(result.scalars().all())


async def get_latest_executing_tool(
    db: AsyncSession,
    chat_message_id: int,
    tool_name: str,
) -> Optional[ToolExecution]:
    """
    Retrieve the most recent tool execution that is currently in the "executing" state for a given chat message and tool name.

    Args:
        db: An active asynchronous SQLAlchemy session used to query the database.
        chat_message_id: The identifier of the parent chat message whose tool executions are being inspected.
        tool_name: The specific name of the tool to filter executions by.

    Returns:
        A :class:`ToolExecution` instance representing the latest executing record that matches the criteria, or `None` if no such execution exists.
    """
    result = await db.execute(
        select(ToolExecution)
        .where(ToolExecution.chat_message_id == chat_message_id)
        .where(ToolExecution.tool_name == tool_name)
        .where(ToolExecution.status == "executing")
        .order_by(ToolExecution.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


__all__ = [
    "create_tool_execution",
    "update_tool_execution",
    "complete_tool_execution",
    "get_tool_execution",
    "get_message_tool_executions",
    "get_latest_executing_tool",
]
