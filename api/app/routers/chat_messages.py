import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ..core.database import get_db
from ..models.chat_history import ChatMessage
from ..models.tool_execution import ToolExecution
from ..crud import chat_history as crud
from ..crud import tool_execution as tool_crud
from ..crud import investigation as inv_crud
from .chat import manager  # Import WebSocket manager for notifications

logger = logging.getLogger(__name__)

router = APIRouter()


class MessageCreate(BaseModel):
    """Request model for creating a new message."""

    role: str = Field(..., description="Message role: user, assistant, system, tool")
    message_type: str = Field(
        ..., description="Message type: question, agent_message, tool_execution, summary, error"
    )
    content: Optional[str] = Field(
        None, description="Message content (optional for tool_execution)"
    )
    parent_message_id: Optional[int] = Field(None, description="Parent message ID for threading")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )
    include_in_llm_context: bool = Field(True, description="Include in LLM context")
    visible_in_ui: bool = Field(True, description="Show in UI")


class MessageUpdate(BaseModel):
    """Request model for updating a message."""

    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    deleted_at: Optional[str] = None  # ISO timestamp for soft delete


class ToolExecutionCreate(BaseModel):
    """Request model for creating a tool execution."""

    tool_name: str
    display_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    execution_number: Optional[int] = None
    max_tools: Optional[int] = None


class ToolExecutionUpdate(BaseModel):
    """Request model for updating a tool execution."""

    result: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    status: Optional[str] = None  # executing, completed, failed


class ToolExecutionResponse(BaseModel):
    """Response model for a tool execution."""

    execution_id: int
    chat_message_id: int
    tool_name: str
    display_name: Optional[str]
    arguments: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    result_summary: Optional[str]
    status: str
    execution_number: Optional[int]
    max_tools: Optional[int]
    started_at: str
    finished_at: Optional[str]

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Response model for a single message."""

    message_id: int
    investigation_id: str
    role: str
    message_type: Optional[str]
    content: Optional[str]
    parent_message_id: Optional[int]
    metadata: Dict[str, Any]
    tool_executions: Optional[List[ToolExecutionResponse]] = None
    deleted_at: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


@router.get("/messages/{investigation_id}", response_model=Dict[str, Any])
async def get_messages(
    investigation_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    include_tool_executions: bool = Query(
        True, description="Include tool executions for each message"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all messages for an investigation.

    This endpoint is the single source of truth for chat state. The UI fetches data from here on load and after receiving WebSocket notifications.

    Args:
        investigation_id (str): Investigation UUID as a string.
        limit (int, optional): Maximum number of messages to return. Must be between 1 and 1000 inclusive. Defaults to 100.
        offset (int, optional): Number of messages to skip for pagination. Must be non-negative. Defaults to 0.
        include_tool_executions (bool, optional): Whether to include tool execution details for each message. Defaults to True.
        db (AsyncSession): Database session provided by the `get_db` dependency.

    Raises:
        HTTPException: If `investigation_id` is not a valid UUID (status code 400).

    Returns:
        dict: A dictionary containing:
            - "messages" (list[dict]): List of message dictionaries in chronological order. Each dictionary includes keys such as `message_id`, `investigation_id`, `role`, `message_type`, `content`, `parent_message_id`, `metadata`, `deleted_at`, `created_at` and, when `include_tool_executions` is True, a `tool_executions` list with execution details.
            - "total" (int): Number of messages returned in the current response.
            - "parsing_locked" (bool): Indicates whether the investigation's parsing lock is active.
    """
    try:
        inv_uuid = UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid investigation ID format")

    # Get investigation to check parsing lock status
    investigation = await inv_crud.get_investigation(db, inv_uuid)
    parsing_locked = investigation.parsing_locked if investigation else False

    messages = await crud.get_investigation_messages(
        db=db,
        investigation_id=inv_uuid,
        limit=limit,
        offset=offset,
        visible_in_ui_only=True,  # Only return UI-visible messages
        include_deleted=False,  # Exclude soft-deleted messages
    )

    # Build response with tool executions
    result_messages = []
    for msg in messages:
        msg_dict = {
            "message_id": msg.message_id,
            "investigation_id": str(msg.investigation_id),
            "role": msg.role,
            "message_type": msg.message_type,
            "content": msg.content,
            "parent_message_id": msg.parent_message_id,
            "metadata": msg.message_metadata or {},
            "deleted_at": msg.deleted_at.isoformat() if msg.deleted_at else None,
            "created_at": msg.created_at.isoformat(),
        }

        # Include tool executions if requested
        if include_tool_executions:
            tool_execs = await tool_crud.get_message_tool_executions(db, msg.message_id)
            msg_dict["tool_executions"] = [
                {
                    "execution_id": te.execution_id,
                    "chat_message_id": te.chat_message_id,
                    "tool_name": te.tool_name,
                    "display_name": te.display_name,
                    "arguments": te.arguments,
                    "result": te.result,
                    "result_summary": te.result_summary,
                    "status": te.status,
                    "execution_number": te.execution_number,
                    "max_tools": te.max_tools,
                    "started_at": te.started_at.isoformat() if te.started_at else None,
                    "finished_at": te.finished_at.isoformat() if te.finished_at else None,
                }
                for te in tool_execs
            ]

        result_messages.append(msg_dict)

    return {
        "messages": result_messages,
        "total": len(result_messages),
        "parsing_locked": parsing_locked,
    }


@router.get("/messages/single/{message_id}")
async def get_message(
    message_id: int,
    include_tool_executions: bool = Query(True, description="Include tool executions"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single chat message by its identifier, optionally including any associated tool executions.

    Parameters
    ----------
    message_id: int
        The unique identifier of the message to retrieve.
    include_tool_executions: bool, optional
        Flag indicating whether to fetch and embed tool execution details in the response. Defaults to `True` via a FastAPI query parameter.
    db: AsyncSession
        An asynchronous SQLAlchemy session provided by dependency injection.

    Returns
    -------
    dict
        A dictionary containing the message fields:
            - `message_id` (int)
            - `investigation_id` (str)
            - `role` (str)
            - `message_type` (str)
            - `content` (str)
            - `parent_message_id` (int | None)
            - `metadata` (dict)
            - `deleted_at` (str | None) ISO-8601 timestamp
            - `created_at` (str) ISO-8601 timestamp
        If `include_tool_executions` is true, the dictionary also includes a `tool_executions` key holding a list of tool execution dictionaries with their respective fields.

    Raises
    ------
    HTTPException
        Raised with status code 404 when no message matching `message_id` exists.
    """
    message = await crud.get_message_by_id(db, message_id)

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    result = {
        "message_id": message.message_id,
        "investigation_id": str(message.investigation_id),
        "role": message.role,
        "message_type": message.message_type,
        "content": message.content,
        "parent_message_id": message.parent_message_id,
        "metadata": message.message_metadata or {},
        "deleted_at": message.deleted_at.isoformat() if message.deleted_at else None,
        "created_at": message.created_at.isoformat(),
    }

    if include_tool_executions:
        tool_execs = await tool_crud.get_message_tool_executions(db, message_id)
        result["tool_executions"] = [
            {
                "execution_id": te.execution_id,
                "chat_message_id": te.chat_message_id,
                "tool_name": te.tool_name,
                "display_name": te.display_name,
                "arguments": te.arguments,
                "result": te.result,
                "result_summary": te.result_summary,
                "status": te.status,
                "execution_number": te.execution_number,
                "max_tools": te.max_tools,
                "started_at": te.started_at.isoformat() if te.started_at else None,
                "finished_at": te.finished_at.isoformat() if te.finished_at else None,
            }
            for te in tool_execs
        ]

    return result


@router.post("/messages/{investigation_id}", response_model=MessageResponse)
async def create_message(
    investigation_id: str,
    message: MessageCreate,
    user_id: int = 1,  # TODO: Get from JWT token
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new chat message for a given investigation and broadcast a notification to connected WebSocket clients.

    The function validates the provided investigation identifier, persists the message using the CRUD layer, and then sends a lightweight `message_created` event containing the new message's ID to all listeners subscribed to the investigation channel.  It returns a :class:`MessageResponse` model representing the stored message.

    Args:
        investigation_id (str): The UUID string identifying the investigation to which the message belongs.
        message (MessageCreate): Pydantic model containing the message payload, including role, content, metadata, and optional flags.
        user_id (int, optional): Identifier of the user creating the message.  Defaults to `1`; in production this should be extracted from the JWT token.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session provided by FastAPI's dependency injection.

    Returns:
        MessageResponse: A response model populated with the newly created message's details, including IDs, timestamps, and any metadata.

    Raises:
        HTTPException: If `investigation_id` cannot be parsed as a valid UUID (status code 400).
    """
    try:
        inv_uuid = UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid investigation ID format")

    # Create message in database
    msg = await crud.create_message(
        db=db,
        investigation_id=inv_uuid,
        user_id=user_id,
        role=message.role,
        content=message.content,
        metadata=message.metadata,
        include_in_llm_context=message.include_in_llm_context,
        visible_in_ui=message.visible_in_ui,
        message_type=message.message_type,
        parent_message_id=message.parent_message_id,
    )

    # Broadcast simple notification to WebSocket clients
    await manager.broadcast(
        investigation_id,
        {
            "type": "message_created",
            "message_id": msg.message_id,
        },
    )

    return MessageResponse(
        message_id=msg.message_id,
        investigation_id=str(msg.investigation_id),
        role=msg.role,
        message_type=msg.message_type,
        content=msg.content,
        parent_message_id=msg.parent_message_id,
        metadata=msg.message_metadata or {},
        created_at=msg.created_at.isoformat(),
    )


@router.patch("/messages/{message_id}")
async def update_message(
    message_id: int,
    update: MessageUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing chat message, handling both regular updates and soft-deletion.

    Args:
        message_id (int): Identifier of the message to be updated.
        update (MessageUpdate): Data containing the new content, optional metadata, or a `deleted_at` timestamp for soft deletion.
        db (AsyncSession, optional): Database session dependency provided by FastAPI. Defaults to the result of `Depends(get_db)`.

    Raises:
        HTTPException: If no message with the given `message_id` exists (HTTP 404).

    Returns:
        dict: A dictionary representation of the updated message containing:
            - `message_id` (int): The message identifier.
            - `investigation_id` (str): Identifier of the associated investigation.
            - `role` (str): Role of the sender (e.g., user, assistant).
            - `message_type` (str): Type of the message.
            - `content` (str | None): Updated textual content, if any.
            - `parent_message_id` (int | None): Identifier of the parent message, if applicable.
            - `metadata` (dict): Message metadata; empty dict if none.
            - `deleted_at` (str | None): ISO-formatted deletion timestamp for soft-deleted messages, otherwise `None`.
            - `created_at` (str): ISO-formatted creation timestamp.
    """
    # Handle soft delete
    if update.deleted_at:
        msg = await crud.soft_delete_message(db, message_id)
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        # Broadcast deletion notification
        await manager.broadcast(
            str(msg.investigation_id),
            {
                "type": "message_deleted",
                "message_id": msg.message_id,
            },
        )
    else:
        # Regular update
        msg = await crud.update_message(
            db=db,
            message_id=message_id,
            content=update.content,
            metadata=update.metadata,
        )

        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        # Broadcast update notification
        await manager.broadcast(
            str(msg.investigation_id),
            {
                "type": "message_updated",
                "message_id": msg.message_id,
            },
        )

    return {
        "message_id": msg.message_id,
        "investigation_id": str(msg.investigation_id),
        "role": msg.role,
        "message_type": msg.message_type,
        "content": msg.content,
        "parent_message_id": msg.parent_message_id,
        "metadata": msg.message_metadata or {},
        "deleted_at": msg.deleted_at.isoformat() if msg.deleted_at else None,
        "created_at": msg.created_at.isoformat(),
    }


@router.post("/investigation-state/{investigation_id}")
async def update_investigation_state(
    investigation_id: str,
    state: str = Body(..., embed=True),
):
    """
    Broadcasts an investigation state change to all connected clients.

    Args:
        investigation_id (str): The UUID of the investigation whose state is being updated.
        state (str): The new state for the investigation. Must be one of "idle", "running",
            "completed", or "failed". Provided via a request body with `embed=True`.

    Raises:
        HTTPException: If `state` is not one of the allowed values, a 400 error is raised
            indicating an invalid state.

    Returns:
        dict: A dictionary containing a single key `"status"` set to `"ok"` confirming
            that the broadcast was successfully initiated.
    """
    if state not in ["idle", "running", "completed", "failed"]:
        raise HTTPException(status_code=400, detail="Invalid state")

    await manager.broadcast(
        investigation_id,
        {
            "type": "investigation_state_changed",
            "state": state,
        },
    )

    return {"status": "ok"}


@router.post("/messages/{message_id}/tool-executions")
async def create_tool_execution(
    message_id: int,
    tool_exec: ToolExecutionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new tool execution associated with a specific chat message.

    This endpoint is invoked by an agent when it begins executing a tool call. It validates that the parent message exists, persists the tool execution record, broadcasts a notification to any connected WebSocket clients, and returns a dictionary representation of the created execution.

    Args:
        message_id (int): The identifier of the parent chat message.
        tool_exec (ToolExecutionCreate): A Pydantic model containing the details required to create the tool execution, such as `tool_name`, `display_name`, `arguments`, `execution_number` and `max_tools`.
        db (AsyncSession, optional): The asynchronous SQLAlchemy session provided by FastAPI's dependency injection. Defaults to the result of `get_db`.

    Raises:
        HTTPException: If no message with the given `message_id` exists, a 404 error is raised.

    Returns:
        dict: A dictionary containing the newly created tool execution fields:
            - `execution_id` (int): Unique identifier of the execution.
            - `chat_message_id` (int): Identifier of the parent chat message.
            - `tool_name` (str): Name of the tool being executed.
            - `display_name` (str): Human-readable name of the tool.
            - `arguments` (dict): Arguments supplied to the tool.
            - `status` (str): Current status of the execution.
            - `execution_number` (int): Sequential number of this execution for the message.
            - `max_tools` (int): Maximum allowed concurrent tools for the investigation.
            - `started_at` (str | None): ISO-8601 timestamp when execution started, or `None` if unavailable.
    """
    # Verify message exists
    message = await crud.get_message_by_id(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    execution = await tool_crud.create_tool_execution(
        db=db,
        chat_message_id=message_id,
        tool_name=tool_exec.tool_name,
        display_name=tool_exec.display_name,
        arguments=tool_exec.arguments,
        execution_number=tool_exec.execution_number,
        max_tools=tool_exec.max_tools,
    )

    # Broadcast notification
    await manager.broadcast(
        str(message.investigation_id),
        {
            "type": "tool_executing",
            "execution_id": execution.execution_id,
            "message_id": message_id,
            "tool_name": execution.tool_name,
            "display_name": execution.display_name,
        },
    )

    return {
        "execution_id": execution.execution_id,
        "chat_message_id": execution.chat_message_id,
        "tool_name": execution.tool_name,
        "display_name": execution.display_name,
        "arguments": execution.arguments,
        "status": execution.status,
        "execution_number": execution.execution_number,
        "max_tools": execution.max_tools,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
    }


@router.patch("/tool-executions/{execution_id}")
async def update_tool_execution(
    execution_id: int,
    update: ToolExecutionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a tool execution with its result data and broadcast the outcome.

    This endpoint is invoked by an agent when a previously started tool finishes execution. It persists the provided result information, validates that the execution exists, and notifies all connected clients subscribed to the investigation associated with the parent chat message.

    Args:
        execution_id (int): Identifier of the tool execution to update.
        update (ToolExecutionUpdate): Data containing the result, a summary of the result, and the new status.
        db (AsyncSession, optional): Database session dependency injected by FastAPI. Defaults to Depends(get_db).

    Returns:
        dict: A dictionary representation of the updated tool execution, including identifiers, tool metadata, arguments, result data, timestamps, and status.

    Raises:
        HTTPException: If no tool execution with the given `execution_id` exists (HTTP 404).
    """
    execution = await tool_crud.update_tool_execution(
        db=db,
        execution_id=execution_id,
        result=update.result,
        result_summary=update.result_summary,
        status=update.status,
    )

    if not execution:
        raise HTTPException(status_code=404, detail="Tool execution not found")

    # Get parent message for investigation ID
    message = await crud.get_message_by_id(db, execution.chat_message_id)
    if message:
        # Broadcast notification
        await manager.broadcast(
            str(message.investigation_id),
            {
                "type": "tool_result",
                "execution_id": execution.execution_id,
                "message_id": execution.chat_message_id,
                "tool_name": execution.tool_name,
                "status": execution.status,
                "result_summary": execution.result_summary,
            },
        )

    return {
        "execution_id": execution.execution_id,
        "chat_message_id": execution.chat_message_id,
        "tool_name": execution.tool_name,
        "display_name": execution.display_name,
        "arguments": execution.arguments,
        "result": execution.result,
        "result_summary": execution.result_summary,
        "status": execution.status,
        "execution_number": execution.execution_number,
        "max_tools": execution.max_tools,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
    }


@router.get("/messages/{message_id}/tool-executions")
async def get_message_tool_executions(
    message_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all tool execution records associated with a specific chat message.

    Args:
        message_id (int): Identifier of the parent chat message whose tool executions are to be fetched.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session injected via FastAPI's Depends; defaults to the session provided by `get_db`.

    Returns:
        dict: A dictionary containing a single key `"tool_executions"`, which maps to a list of dictionaries. Each inner dictionary represents a tool execution with the following fields:
            - execution_id (int): Unique identifier of the tool execution.
            - chat_message_id (int): Identifier of the chat message this execution belongs to.
            - tool_name (str): Internal name of the tool that was executed.
            - display_name (str): Human-readable name for the tool.
            - arguments (dict): Arguments supplied to the tool at invocation time.
            - result (Any): Full result returned by the tool.
            - result_summary (str | None): Concise summary of the result, if available.
            - status (str): Current execution status (e.g., `"pending"`, `"running"`, `"completed"`, `"failed"`).
            - execution_number (int): Sequential number indicating the order of executions for the message.
            - max_tools (int | None): Maximum number of tools allowed for this execution context, if applicable.
            - started_at (str | None): ISO-8601 timestamp marking when the execution began, or `None` if not started.
            - finished_at (str | None): ISO-8601 timestamp marking when the execution completed, or `None` if not finished.

    Raises:
        HTTPException: Propagated from the underlying CRUD operation if the database query fails.
    """
    executions = await tool_crud.get_message_tool_executions(db, message_id)

    return {
        "tool_executions": [
            {
                "execution_id": te.execution_id,
                "chat_message_id": te.chat_message_id,
                "tool_name": te.tool_name,
                "display_name": te.display_name,
                "arguments": te.arguments,
                "result": te.result,
                "result_summary": te.result_summary,
                "status": te.status,
                "execution_number": te.execution_number,
                "max_tools": te.max_tools,
                "started_at": te.started_at.isoformat() if te.started_at else None,
                "finished_at": te.finished_at.isoformat() if te.finished_at else None,
            }
            for te in executions
        ]
    }


__all__ = ["router"]
