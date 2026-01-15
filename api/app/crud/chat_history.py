from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func
from ..models.chat_history import ChatMessage
from ..models.tool_execution import ToolExecution


async def create_message(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    role: str,
    content: Optional[str] = None,
    name: Optional[str] = None,
    tool_calls: Optional[Dict[str, Any]] = None,
    tool_call_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    include_in_llm_context: bool = True,
    visible_in_ui: bool = True,
    message_type: Optional[str] = None,
    parent_message_id: Optional[int] = None,
) -> ChatMessage:
    """
    Create and persist a new chat message record.

    Args:
        db: An active asynchronous SQLAlchemy session used for database operations.
        investigation_id: The UUID of the investigation to which the message belongs.
        user_id: Identifier of the user who sent or received the message.
        role: OpenAI role designation (e.g., `system`, `user`, `assistant`, `tool`).
        content: Textual content of the message; may be omitted when the message represents a tool call.
        name: Optional name associated with the message (used for tool calls or system messages).
        tool_calls: Optional dictionary describing tool calls included in the message.
        tool_call_id: Identifier linking this message to a specific tool call, if applicable.
        metadata: Additional arbitrary metadata such as intent, confidence scores, job identifiers, etc.
        include_in_llm_context: Flag indicating whether the message should be incorporated into subsequent LLM prompts.
        visible_in_ui: Flag indicating whether the message should be displayed in the chat user interface.
        message_type: Optional categorisation of the message (e.g., `question`, `agent_message`, `tool_execution`, `summary`, `error`).
        parent_message_id: Identifier of a parent message to support threading or hierarchical relationships.

    Returns:
        The newly created :class:`ChatMessage` instance, refreshed from the database.
    """
    message = ChatMessage(
        investigation_id=investigation_id,
        user_id=user_id,
        role=role,
        content=content,
        name=name,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        message_metadata=metadata or {},
        include_in_llm_context=include_in_llm_context,
        visible_in_ui=visible_in_ui,
        message_type=message_type,
        parent_message_id=parent_message_id,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_investigation_messages(
    db: AsyncSession,
    investigation_id: UUID,
    limit: Optional[int] = None,
    offset: int = 0,
    include_in_llm_only: bool = False,
    visible_in_ui_only: bool = False,
    include_deleted: bool = False,
) -> List[ChatMessage]:
    """
    Retrieve chat messages for a given investigation with optional filtering and pagination.

    Parameters
    ----------
    db : AsyncSession
        Active asynchronous database session used to execute the query.
    investigation_id : UUID
        Identifier of the investigation whose messages are being fetched.
    limit : Optional[int], default=None
        Maximum number of messages to return. If `None` all matching messages are retrieved.
    offset : int, default=0
        Number of messages to skip before returning results; useful for pagination.
    include_in_llm_only : bool, default=False
        When `True`, only messages marked with `include_in_llm_context=True` are returned.
    visible_in_ui_only : bool, default=False
        When `True`, restrict the result set to messages where `visible_in_ui=True`.
    include_deleted : bool, default=False
        If `False` (default), soft-deleted messages (where `deleted_at` is not null) are excluded from the results.

    Returns
    -------
    List[ChatMessage]
        A list of :class:`ChatMessage` objects ordered by their insertion order (ascending `message_id`). The list respects the supplied filters, limit, and offset.
    """
    query = select(ChatMessage).where(ChatMessage.investigation_id == investigation_id)

    # Filter out soft-deleted messages unless explicitly requested
    if not include_deleted:
        query = query.where(ChatMessage.deleted_at.is_(None))

    if include_in_llm_only:
        query = query.where(ChatMessage.include_in_llm_context == True)

    if visible_in_ui_only:
        query = query.where(ChatMessage.visible_in_ui == True)

    # Order by message_id instead of created_at to maintain insertion order
    query = query.order_by(ChatMessage.message_id.asc())

    if limit is not None:
        query = query.limit(limit)

    if offset > 0:
        query = query.offset(offset)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_llm_context(
    db: AsyncSession,
    investigation_id: UUID,
    max_messages: Optional[int] = None,
) -> List[dict]:
    """
    Builds a list of chat messages formatted for OpenAI's API to serve as context for an LLM.

    Only messages that are marked with `include_in_llm_context=True` and are not soft-deleted are included. The function returns the most recent messages up to `max_messages` (if provided), preserving their chronological order from oldest to newest.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used for database queries.
        investigation_id: The UUID of the investigation whose chat history should be queried.
        max_messages: Optional maximum number of messages to return. If `None` all qualifying messages are included; otherwise the most recent `max_messages` records are returned.

    Returns:
        A list of dictionaries, each representing a message in OpenAI's chat format (e.g., `{\"role\": \"user\", \"content\": \"...\"}`). The list is ordered from oldest to newest to maintain conversational context.
    """
    messages = await get_investigation_messages(
        db,
        investigation_id,
        limit=max_messages,
        include_in_llm_only=True,
        include_deleted=False,  # Never include deleted messages in LLM context
    )

    return [msg.to_openai_format() for msg in messages]


async def get_message_by_id(
    db: AsyncSession,
    message_id: int,
) -> Optional[ChatMessage]:
    """
    Retrieve a single chat message identified by its primary key.

    Args:
        db (AsyncSession): An active asynchronous SQLAlchemy session used for the query.
        message_id (int): The unique identifier of the message to retrieve.

    Returns:
        Optional[ChatMessage]: The `ChatMessage` instance matching `message_id` if it exists,
        otherwise `None`.

    Raises:
        None. This function returns `None` when no matching record is found rather than raising an exception.
    """
    result = await db.execute(select(ChatMessage).where(ChatMessage.message_id == message_id))
    return result.scalar_one_or_none()


async def update_message(
    db: AsyncSession,
    message_id: int,
    content: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    include_in_llm_context: Optional[bool] = None,
    visible_in_ui: Optional[bool] = None,
) -> Optional[ChatMessage]:
    """
    Update an existing chat message in the database.

    Args:
        db: An active asynchronous SQLAlchemy session used for the operation.
        message_id: The primary key of the `ChatMessage` to be updated.
        content: Optional new textual content for the message. If `None`, the
            existing content is left unchanged.
        metadata: Optional dictionary containing additional metadata. When provided,
            it is deep-copied and merged with the current `message_metadata` field;
            SQLAlchemy is explicitly flagged as modified to ensure persistence.
        include_in_llm_context: Optional boolean indicating whether the message should be
            included in prompts sent to language models. If `None`, the flag remains
            unchanged.
        visible_in_ui: Optional boolean controlling the visibility of the message in the
            user interface. If `None`, the existing visibility setting is retained.

    Returns:
        The updated `ChatMessage` instance if a record with `message_id` exists;
        otherwise, `None` is returned.
    """
    message = await get_message_by_id(db, message_id)
    if not message:
        return None

    if content is not None:
        message.content = content

    if metadata is not None:
        # Create a deep copy to ensure SQLAlchemy detects the change
        import copy
        from sqlalchemy.orm import attributes

        message.message_metadata = copy.deepcopy(metadata)
        # Flag the column as modified so SQLAlchemy knows to update it
        attributes.flag_modified(message, "message_metadata")

    if include_in_llm_context is not None:
        message.include_in_llm_context = include_in_llm_context

    if visible_in_ui is not None:
        message.visible_in_ui = visible_in_ui

    await db.commit()
    await db.refresh(message)
    return message


async def soft_delete_message(
    db: AsyncSession,
    message_id: int,
) -> Optional[ChatMessage]:
    """
    Soft-delete a chat message by marking it as removed.

    This function retrieves the :class:`ChatMessage` with the given `message_id` and,
    if found, sets its `deleted_at` timestamp to the current time and disables
    its inclusion in LLM context. The changes are committed to the database and the
    updated instance is refreshed before being returned.

    Args:
        db: An active :class:`AsyncSession` used for database operations.
        message_id: The primary key of the chat message to be soft-deleted.

    Returns:
        The updated :class:`ChatMessage` instance if it exists, otherwise `None`.
    """
    message = await get_message_by_id(db, message_id)
    if not message:
        return None

    message.deleted_at = func.now()
    message.include_in_llm_context = False  # Remove from LLM context
    await db.commit()
    await db.refresh(message)
    return message


async def hard_delete_message(
    db: AsyncSession,
    message_id: int,
) -> bool:
    """
    Hard-delete a chat message from the database.

    Permanently removes the `ChatMessage` record identified by `message_id`.  This operation cannot be undone; use :func:`soft_delete_message` for a reversible delete.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute the query.
        message_id: The primary-key identifier of the message to remove.

    Returns:
        bool: `True` if a row was deleted, `False` if no matching message was found.
    """
    result = await db.execute(delete(ChatMessage).where(ChatMessage.message_id == message_id))
    await db.commit()
    return result.rowcount > 0


# Alias for backwards compatibility
delete_message = soft_delete_message


async def delete_investigation_messages(
    db: AsyncSession,
    investigation_id: UUID,
) -> int:
    """
    Delete all chat messages associated with a given investigation.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database operations.
    investigation_id : UUID
        The unique identifier of the investigation whose messages are to be removed.

    Returns
    -------
    int
        The number of message records that were deleted.
    """
    result = await db.execute(
        delete(ChatMessage).where(ChatMessage.investigation_id == investigation_id)
    )
    await db.commit()
    return result.rowcount


async def get_message_count(
    db: AsyncSession,
    investigation_id: UUID,
    include_in_llm_only: bool = False,
    include_deleted: bool = False,
) -> int:
    """
    Count chat messages for a given investigation.

    Args:
        db: An asynchronous SQLAlchemy session used to execute the query.
        investigation_id: The UUID of the investigation whose messages are being counted.
        include_in_llm_only: When True, only messages marked with `include_in_llm_context=True` are included in the count.
        include_deleted: When True, soft-deleted messages (where `deleted_at` is not null) are also counted; otherwise they are excluded.

    Returns:
        The total number of messages matching the specified criteria as an integer.
    """
    query = select(func.count(ChatMessage.message_id)).where(
        ChatMessage.investigation_id == investigation_id
    )

    if not include_deleted:
        query = query.where(ChatMessage.deleted_at.is_(None))

    if include_in_llm_only:
        query = query.where(ChatMessage.include_in_llm_context == True)

    result = await db.execute(query)
    return result.scalar_one()


async def get_message_with_tool_executions(
    db: AsyncSession,
    message_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a chat message together with all tool executions that belong to it.

    Args:
        db: An active asynchronous SQLAlchemy session used for database queries.
        message_id: The primary key identifier of the chat message to retrieve.

    Returns:
        A dictionary containing two keys:
            - `message`: The ORM instance representing the requested chat message, or `None` if no such record exists.
            - `tool_executions`: A list of dictionaries, each derived from a `ToolExecution` instance associated with the message, ordered chronologically by their start time.

        If the specified message does not exist, `None` is returned instead of a dictionary.
    """
    message = await get_message_by_id(db, message_id)
    if not message:
        return None

    # Get tool executions for this message
    result = await db.execute(
        select(ToolExecution)
        .where(ToolExecution.chat_message_id == message_id)
        .order_by(ToolExecution.started_at.asc())
    )
    tool_executions = list(result.scalars().all())

    return {
        "message": message,
        "tool_executions": [te.to_dict() for te in tool_executions],
    }


__all__ = [
    "create_message",
    "get_investigation_messages",
    "get_llm_context",
    "get_message_by_id",
    "update_message",
    "soft_delete_message",
    "hard_delete_message",
    "delete_message",
    "delete_investigation_messages",
    "get_message_count",
    "get_message_with_tool_executions",
    "ChatMessage",
    "ToolExecution",
]
