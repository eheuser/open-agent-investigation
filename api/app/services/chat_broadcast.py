import asyncio
from typing import Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ..models.job_agent import AgentJob
from ..crud import chat_history as crud
from ..crud import tool_execution as tool_crud
from .chat_persistence import (
    persist_assistant_message,
    persist_system_message,
)
from ..utils.content_sanitizer import sanitize_llm_content

from ..utils.log_setup import get_logger

logger = get_logger(__name__)


async def handle_broadcast_message(
    db: AsyncSession,
    investigation_id: UUID,
    message: Dict[str, Any],
) -> None:
    """
    Handle broadcast messages from an agent execution and persist the appropriate information to the database.

    The function receives a raw message emitted by the worker process, determines its type, and forwards it to a dedicated handler that creates or updates chat/message records associated with the given investigation. It also ensures that user-level metadata (such as `user_id`) is resolved from the most recent `AgentJob` entry, defaulting to an administrative user when no job exists.

    The supported message types include lifecycle events (e.g., `agent_started`, `agent_completed`), loop notifications (e.g., `loop_start`, `loop_error`), tool interactions (call, result, executing), LLM streaming updates (waiting, chunk, error), agent thinking steps, user-initiated stops or cancellations, safety limits, timeline updates, and investigation incompleteness. For each type a corresponding private coroutine (prefixed with `_handle_`) is invoked; some types are logged directly or persisted as system messages.

    Parameters
    ----------
    db: AsyncSession
        An active asynchronous SQLAlchemy session used to query and persist data.
    investigation_id: UUID
        The unique identifier of the investigation to which the broadcast belongs.
    message: Dict[str, Any]
        A dictionary representing the broadcast payload. It must contain a `type` key that determines how the message is processed; additional keys are interpreted by the specific handlers.

    Returns
    -------
    None

    Side Effects
    ------------
    * Queries the database for the latest `AgentJob` linked to *investigation_id*.
    * May create, update, or delete chat/message records in the database.
    * Commits the transaction after persisting system-level messages (e.g., safety limits, LLM errors).
    * Emits debug logs for informational message types such as `turn_complete` and `timeline_updated`.

    Raises
    ------
    Any exception raised by the underlying database operations or handler coroutines will propagate to the caller.
    """
    message_type = message.get("type")

    # Get the job to retrieve user_id (needed for persistence)
    result = await db.execute(
        select(AgentJob)
        .where(AgentJob.investigation_id == investigation_id)
        .order_by(desc(AgentJob.created_at))
        .limit(1)
    )
    agent_job = result.scalar_one_or_none()

    # Default user_id to 1 if no job found
    user_id = agent_job.user_id if agent_job else 1

    # Route to appropriate handler
    if message_type == "agent_started":
        await _handle_agent_started(db, investigation_id, user_id, agent_job, message)

    elif message_type == "loop_start":
        await _handle_loop_start(db, investigation_id, agent_job, message)

    elif message_type == "tool_call":
        await _handle_tool_call(db, investigation_id, agent_job, message)

    elif message_type == "tool_result":
        await _handle_tool_result(db, investigation_id, agent_job, message)

    elif message_type == "agent_message":
        await _handle_agent_message(db, investigation_id, agent_job, message)

    elif message_type == "agent_completed":
        await _handle_agent_completed(db, investigation_id, user_id, agent_job, message)

    elif message_type == "loop_error":
        await _handle_loop_error(db, investigation_id, agent_job, message)

    elif message_type == "agent_step":
        await _handle_agent_step(db, investigation_id, agent_job, message)

    elif message_type == "tool_executing":
        await _handle_tool_executing(db, investigation_id, agent_job, message)

    elif message_type == "llm_waiting":
        await _handle_llm_waiting(db, investigation_id, agent_job, message)

    elif message_type == "llm_chunk":
        await _handle_llm_chunk(db, investigation_id, agent_job, message)

    elif message_type == "agent_thinking":
        await _handle_agent_thinking(db, investigation_id, agent_job, message)

    elif message_type == "user_stopped":
        await _handle_user_stopped(db, investigation_id, user_id, agent_job, message)

    elif message_type == "agent_cancelled":
        await _handle_agent_cancelled(db, investigation_id, user_id, agent_job, message)

    elif message_type == "agent_error":
        await _handle_agent_error(db, investigation_id, user_id, agent_job, message)

    elif message_type == "turn_error":
        await _handle_turn_error(db, investigation_id, agent_job, message)

    elif message_type == "turn_complete":
        # New AssistantAgent message - just log for now
        logger.debug(
            f"Turn {message.get('turn_number')} complete: {message.get('tools_executed')} tools executed"
        )

    elif message_type == "safety_limit_reached":
        # Safety limit reached - persist as system message
        await persist_system_message(
            db=db,
            investigation_id=investigation_id,
            user_id=user_id,
            content=message.get("message", "Safety limit reached"),
            metadata={"type": "safety_limit"},
            include_in_llm_context=False,
        )
        await db.commit()

    elif message_type == "llm_error":
        # LLM error - persist as error message
        await persist_system_message(
            db=db,
            investigation_id=investigation_id,
            user_id=user_id,
            content=f"❌ LLM Error: {message.get('error', 'Unknown error')}",
            metadata={"type": "llm_error", "error": message.get("error")},
            include_in_llm_context=False,
        )
        await db.commit()

    elif message_type == "timeline_updated":
        # Timeline was updated (auto-registration) - just pass through to WebSocket
        # No need to persist this as a message, it's a notification only
        logger.debug(f"Timeline updated: {message.get('entries_added')} entries added")

    elif message_type == "investigation_incomplete":
        await _handle_investigation_incomplete(db, investigation_id, user_id, agent_job, message)


async def _get_streaming_message(
    db: AsyncSession,
    investigation_id: UUID,
    streaming_id: str,
) -> crud.ChatMessage | None:
    """
    Fetches the most recent assistant chat message associated with a specific streaming session.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database queries.
    investigation_id : UUID
        Identifier of the investigation to which the message belongs.
    streaming_id : str
        Unique identifier of the streaming message (stored in `message_metadata["streaming_message_id"]`).

    Returns
    -------
    crud.ChatMessage | None
        The latest matching `ChatMessage` instance if one exists; otherwise `None`.

    Notes
    -----
    The query filters for messages with role `"assistant"`, matches the provided `investigation_id`,
    and selects records where the `streaming_message_id` metadata field equals `streaming_id`.
    Results are ordered by creation time descending and limited to a single record.
    """
    result = await db.execute(
        select(crud.ChatMessage)
        .where(crud.ChatMessage.investigation_id == investigation_id)
        .where(crud.ChatMessage.role == "assistant")
        .where(crud.ChatMessage.message_metadata["streaming_message_id"].astext == streaming_id)
        .order_by(desc(crud.ChatMessage.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _handle_agent_started(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `agent_started` broadcast event by locating or creating the appropriate chat message record and updating its metadata.

    The function performs the following steps:

    * Logs receipt of the event and validates that an :class:`~models.AgentJob` instance is provided.
    * Constructs a unique `streaming_id` for the job (e.g. `agent_<job_id>`).
    * If the job metadata contains a `reuse_message_id`, treats the event as a continuation of a previous run:
      * Retrieves the existing message by its ID.
      * Updates its metadata to reflect the new start, clears any incomplete flag and marks it as continuing and awaiting LLM output.
    * Otherwise attempts to locate an existing placeholder message created earlier (e.g. by a `job_queued` handler) via :func:`_get_streaming_message`.
      * If a placeholder is found but already marked as `agent_started`, the call is deduplicated and returns early.
      * If a placeholder exists, updates its metadata with the agent name and job identifier.
    * When no placeholder is present, retries once after a short pause to mitigate race conditions.
    * If still absent, creates a new assistant-type chat message with default content (`"Starting analysis..."`) and appropriate metadata, then persists it.

    Parameters
    ----------
    db: AsyncSession
        The asynchronous SQLAlchemy session used for all database operations.
    investigation_id: UUID
        Identifier of the investigation to which the message belongs.
    user_id: int
        Database identifier of the user that initiated the agent run.
    agent_job: AgentJob | None
        The job object representing the running agent; may be `None` if unavailable.
    message: dict[str, Any]
        Payload received from the broadcast source. Expected keys include `"agent"`.

    Returns
    -------
    None

    Side Effects
    ------------
    * Updates or creates a :class:`~models.ChatMessage` row in the database.
    * Commits the transaction after each successful modification.
    * Emits informational and warning logs describing the processing flow.
    """
    logger.info(f"[AGENT_STARTED] Called for job_id={agent_job.job_id if agent_job else None}")
    if not agent_job:
        logger.warning("[AGENT_STARTED] No agent_job provided, returning")
        return

    streaming_id = f"agent_{agent_job.job_id}"
    logger.info(f"[AGENT_STARTED] streaming_id={streaming_id}")

    # Check if this is a continuation job that should reuse an existing message
    reuse_message_id = None
    if agent_job.job_metadata:
        reuse_message_id = agent_job.job_metadata.get("reuse_message_id")

    if reuse_message_id:
        # This is a continuation - reuse the existing message
        logger.info(f"Continuation job detected, reusing message {reuse_message_id}")
        result = await db.execute(
            select(crud.ChatMessage).where(crud.ChatMessage.message_id == reuse_message_id)
        )
        existing_msg = result.scalar_one_or_none()

        if existing_msg:
            # Update the existing message to continue
            current_metadata = existing_msg.message_metadata or {}
            current_metadata["type"] = "agent_started"
            current_metadata["agent"] = message.get("agent")
            current_metadata["job_id"] = agent_job.job_id  # Update to new job ID
            current_metadata["streaming_message_id"] = streaming_id
            current_metadata["investigation_incomplete"] = False  # Clear incomplete flag
            current_metadata["is_continuing"] = True
            current_metadata["isWaitingForLLM"] = True

            await crud.update_message(
                db=db,
                message_id=existing_msg.message_id,
                metadata=current_metadata,
            )
            await db.commit()
            return

    # Check if there's already a placeholder message (created by job_queued handler)
    # OR if agent_started was already processed (deduplication)
    existing_msg = await _get_streaming_message(db, investigation_id, streaming_id)

    logger.info(
        f"Looking for placeholder with streaming_id={streaming_id}, found: {existing_msg is not None}"
    )
    if existing_msg:
        logger.info(
            f"Placeholder message_id={existing_msg.message_id}, type={existing_msg.message_metadata.get('type') if existing_msg.message_metadata else None}"
        )

        # Check if this is already processed (deduplication)
        if (
            existing_msg.message_metadata
            and existing_msg.message_metadata.get("type") == "agent_started"
        ):
            logger.warning(
                f"[AGENT_STARTED] DUPLICATE DETECTED - already processed for streaming_id={streaming_id}, skipping"
            )
            return

    if existing_msg:
        # Update the existing placeholder message
        logger.info(
            f"[AGENT_STARTED] Updating existing placeholder message_id={existing_msg.message_id}"
        )
        current_metadata = existing_msg.message_metadata or {}
        current_metadata["type"] = "agent_started"
        current_metadata["agent"] = message.get("agent")
        current_metadata["job_id"] = agent_job.job_id

        await crud.update_message(
            db=db,
            message_id=existing_msg.message_id,
            metadata=current_metadata,
        )
        await db.commit()
    else:
        # No placeholder - this might be a race condition
        # Wait a moment and try again before creating a duplicate
        logger.warning(
            f"[AGENT_STARTED] No placeholder found for streaming_id={streaming_id}, retrying once..."
        )
        await asyncio.sleep(0.1)  # 100ms delay
        existing_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if existing_msg:
            logger.info(
                f"[AGENT_STARTED] Found placeholder on retry: message_id={existing_msg.message_id}"
            )
            # Update it
            current_metadata = existing_msg.message_metadata or {}
            current_metadata["type"] = "agent_started"
            current_metadata["agent"] = message.get("agent")
            current_metadata["job_id"] = agent_job.job_id

            await crud.update_message(
                db=db,
                message_id=existing_msg.message_id,
                metadata=current_metadata,
            )
            await db.commit()
            return

        # Still no placeholder - create new message
        logger.warning(f"[AGENT_STARTED] Creating NEW message for streaming_id={streaming_id}")
        content = "Starting analysis..."
        msg = await persist_assistant_message(
            db=db,
            investigation_id=investigation_id,
            user_id=user_id,
            content=content,
            metadata={
                "type": "agent_started",
                "agent": message.get("agent"),
                "job_id": agent_job.job_id,
                "streaming_message_id": streaming_id,
                "event_sequence": [],
            },
            include_in_llm_context=False,
            visible_in_ui=True,
        )
        await db.commit()


async def _handle_loop_start(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a loop_start broadcast event by updating the corresponding streaming chat message.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for database operations.
    investigation_id : UUID
        Identifier of the investigation to which the message belongs.
    agent_job : AgentJob | None
        The agent job associated with the current execution; if `None` the function returns without action.
    message : dict[str, Any]
        Payload received from the broadcast containing at least the keys `loop` (current iteration number) and `max_loops` (total iterations).

    Behavior
    --------
    * If `agent_job` is falsy, the function exits early.
    * Constructs a streaming identifier based on the agent job ID.
    * Retrieves the most recent streaming message for the given investigation and identifier.
    * When such a message exists, appends an iteration indicator of the form
      `"\n\n🔄 Iteration {loop}/{max_loops}..."` to its content and persists the update via the CRUD layer.

    Returns
    -------
    None
        The function performs side-effects only; it does not return a value.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

    if last_msg:
        iter_info = f"\n\n🔄 Iteration {message.get('loop')}/{message.get('max_loops')}..."
        current_content = last_msg.content or ""
        await crud.update_message(
            db=db,
            message_id=last_msg.message_id,
            content=current_content + iter_info,
        )


async def _handle_tool_call(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a tool call broadcast event by updating the corresponding streaming chat message.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used to query and update database records.
    investigation_id : UUID
        Identifier of the investigation to which the message belongs.
    agent_job : AgentJob | None
        The agent job context; if `None` the function exits without performing any action.
    message : dict[str, Any]
        Payload containing details about the tool call. Expected keys include `"tool"`, whose value is used in the appended status text.

    Notes
    -----
    * If `agent_job` is not provided, the function returns immediately.
    * The function retrieves the latest streaming message for the given investigation and agent job using `_get_streaming_message`.
    * When a streaming message exists, it appends a line indicating the tool being called (e.g., `"\n  ↳ Calling <tool>..."`) to the current content and persists the update via `crud.update_message`.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

    if last_msg:
        tool_info = f"\n  ↳ Calling {message.get('tool')}..."
        current_content = last_msg.content or ""
        await crud.update_message(
            db=db,
            message_id=last_msg.message_id,
            content=current_content + tool_info,
        )


async def _handle_tool_result(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a tool_result broadcast message by locating the associated streaming chat message and updating the corresponding tool execution record.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used for all database operations.
    investigation_id: UUID
        Identifier of the investigation to which the agent job belongs; used to locate the streaming message.
    agent_job: AgentJob | None
        The current agent job context. If `None` the function returns immediately because there is no active job to associate the result with.
    message: Dict[str, Any]
        Parsed JSON payload representing a tool_result event. Expected keys include:

        - `tool` (str): name of the tool that produced the result.
        - `result` (dict, optional): raw result data returned by the tool.
        - `result_summary` (str, optional): human-readable summary of the result.
        - `success` (bool, optional): indicates whether the tool execution succeeded; defaults to `True`.

    Raises
    ------
    Any exception raised during database access or processing is caught internally and logged as an error; the function does not re-raise exceptions.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            tool_name = message.get("tool")
            if tool_name:
                result_summary = message.get("result_summary", "")
                tool_result = message.get("result", {})
                success = message.get("success", True)

                # Enhance result summary with auto-registration info
                if tool_result and isinstance(tool_result, dict):
                    auto_registered = tool_result.get("auto_registered", 0)
                    if auto_registered > 0:
                        if not result_summary:
                            result_summary = f"Auto-registered {auto_registered} events to timeline"
                        else:
                            result_summary = (
                                f"{result_summary} (auto-registered {auto_registered} to timeline)"
                            )

                # Find the most recent executing tool of this type
                tool_execution = await tool_crud.get_latest_executing_tool(
                    db=db,
                    chat_message_id=last_msg.message_id,
                    tool_name=tool_name,
                )

                if tool_execution:
                    # Update it with results
                    await tool_crud.update_tool_execution(
                        db=db,
                        execution_id=tool_execution.execution_id,
                        result=tool_result,
                        result_summary=result_summary,
                        status="completed" if success else "failed",
                    )

                    # Update the event_sequence entry with result summary
                    current_metadata = last_msg.message_metadata or {}
                    event_sequence = current_metadata.get("event_sequence", [])

                    # Find the event for this tool execution and update it
                    for event in event_sequence:
                        if (
                            event.get("type") == "tool_execution"
                            and event.get("execution_id") == tool_execution.execution_id
                        ):
                            event["status"] = "completed" if success else "failed"
                            event["result_summary"] = result_summary
                            event["completed_at"] = datetime.utcnow().isoformat()
                            break

                    current_metadata["event_sequence"] = event_sequence

                    await crud.update_message(
                        db=db,
                        message_id=last_msg.message_id,
                        metadata=current_metadata,
                    )
                    await db.commit()

                    logger.info(f"Updated tool execution {tool_execution.execution_id} with result")
                else:
                    logger.warning(
                        f"No executing tool found for {tool_name} on message {last_msg.message_id}"
                    )
            else:
                logger.warning("tool_result message missing 'tool' field")
        else:
            logger.debug(f"No agent message found for tool_result (streaming_id={streaming_id})")
    except Exception as e:
        logger.error(f"Failed to update tool_result: {e}", exc_info=True)


async def _handle_agent_message(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an incoming agent_message event by updating the corresponding streaming chat message in the database.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database operations.
    investigation_id : UUID
        Identifier of the investigation to which the message belongs.
    agent_job : AgentJob | None
        The job information for the agent; if `None` the function returns without action.
    message : dict[str, Any]
        Payload containing at least a `"content"` key with the text generated by the agent.

    The function retrieves the latest streaming message associated with the given `agent_job` (identified by a composite `streaming_id`). If such a message exists, it appends the new content prefixed by a thought-bubble emoji to the existing message content and persists the update via the CRUD layer. No value is returned.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

    if last_msg:
        analysis_info = f"\n\n💭 {message.get('content', '')}"
        current_content = last_msg.content or ""
        await crud.update_message(
            db=db,
            message_id=last_msg.message_id,
            content=current_content + analysis_info,
        )


async def _handle_agent_completed(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `agent_completed` broadcast event by locating the streaming chat message associated with the given agent job, clearing its waiting flag, marking it as completed, and appending any final summary and statistics to the message metadata.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for database queries and updates.
    investigation_id : UUID
        Identifier of the investigation to which the streaming message belongs.
    user_id : int
        Identifier of the user who initiated the agent job (currently unused but kept for signature compatibility).
    agent_job : AgentJob | None
        The `AgentJob` instance representing the running agent. If `None`, the function returns immediately.
    message : dict[str, Any]
        Payload received from the broadcast containing optional keys:

        * `stats` - Dictionary of execution statistics to store in metadata.
        * `summary` - Textual summary produced by the `complete_investigation` tool; added as a new event in the message's `event_sequence`.

    Raises
    ------
    Any exception raised during database access or update is caught internally, logged, and not re-raised. The function completes silently on error.
    """
    logger.info(
        f"[AGENT_COMPLETED] Handler executing for job {agent_job.job_id if agent_job else 'unknown'}"
    )
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        # Mark the working message as completed (clear waiting flag)
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            logger.info(f"[AGENT_COMPLETED] Found working message {last_msg.message_id}")

            # Clear the waiting flag on the working message
            current_metadata = last_msg.message_metadata or {}
            event_seq_len = len(current_metadata.get("event_sequence", []))
            logger.info(
                f"[AGENT_COMPLETED] Working message has {event_seq_len} events in event_sequence"
            )

            current_metadata["isWaitingForLLM"] = False
            current_metadata["agent_completed"] = True  # Mark as completed

            # Add stats to metadata for reference
            stats = message.get("stats", {})
            current_metadata["stats"] = stats

            # Add summary from complete_investigation tool call to event_sequence
            summary = message.get("summary", "")
            if summary:
                event_sequence = current_metadata.get("event_sequence", [])
                sequence_num = len(event_sequence)

                event_sequence.append(
                    {
                        "type": "thinking",
                        "sequence": sequence_num,
                        "content": f"**Investigation Complete**\n\n{summary}",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                current_metadata["event_sequence"] = event_sequence

            await crud.update_message(
                db=db,
                message_id=last_msg.message_id,
                metadata=current_metadata,
            )

            await db.commit()
            logger.info("[AGENT_COMPLETED] Marked message as completed with summary")
        else:
            logger.warning(
                f"[AGENT_COMPLETED] No agent message found (streaming_id={streaming_id})"
            )
    except Exception as e:
        logger.error(f"[AGENT_COMPLETED] Failed to mark completed: {e}", exc_info=True)


async def _handle_job_completed(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    message: Dict[str, Any],
) -> None:
    """
    Handle a job_completed broadcast event by persisting an assistant message summarizing the completed job.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database operations.
    investigation_id : UUID
        Identifier of the investigation to which the message belongs.
    user_id : int
        Identifier of the user who initiated or is associated with the job.
    message : dict[str, Any]
        Payload received from the broadcast containing at least a `summary` (optional) and `job_id`. If `summary` is missing, a default text "Analysis complete." is used.

    The function creates an assistant chat message with metadata indicating the event type ("job_completed") and the associated job identifier, marks it as visible in the UI but excludes it from LLM context, then commits the transaction. No value is returned.
    """
    await persist_assistant_message(
        db=db,
        investigation_id=investigation_id,
        user_id=user_id,
        content=message.get("summary", "Analysis complete."),
        metadata={
            "type": "job_completed",
            "job_id": message.get("job_id"),
        },
        include_in_llm_context=False,
        visible_in_ui=True,
    )
    await db.commit()


async def _handle_job_failed(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    message: Dict[str, Any],
) -> None:
    """
    Handle a job_failed broadcast event by persisting an assistant message that records the failure.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used to interact with the database.
    investigation_id : UUID
        Identifier of the investigation to which the message belongs.
    user_id : int
        Identifier of the user associated with the message.
    message : Dict[str, Any]
        Payload received from the agent containing at least an `error` field and optionally a `job_id`.

    The function creates an assistant-role chat message with content prefixed by a failure emoji, stores relevant metadata (type, job identifier, error description), marks it as visible in the UI but excludes it from LLM context, and commits the transaction. No value is returned.
    """
    await persist_assistant_message(
        db=db,
        investigation_id=investigation_id,
        user_id=user_id,
        content=f"❌ Job failed: {message.get('error', 'Unknown error')}",
        metadata={
            "type": "job_failed",
            "job_id": message.get("job_id"),
            "error": message.get("error"),
        },
        include_in_llm_context=False,
        visible_in_ui=True,
    )
    await db.commit()


async def _handle_loop_error(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a loop_error broadcast message by appending error information to the associated streaming chat message.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used for database operations.
    investigation_id: UUID
        Identifier of the investigation to which the messages belong.
    agent_job: AgentJob | None
        The agent job context; if `None` the function exits without action.
    message: Dict[str, Any]
        Dictionary containing the loop error payload. Expected keys include:

        * `loop` - the iteration number where the error occurred.
        * `error` - a string describing the error.

    Behavior
    --------
    * If `agent_job` is falsy, the function returns immediately.
    * Constructs a streaming identifier in the form `"agent_{job_id}"`.
    * Retrieves the most recent streaming message for the given investigation and identifier via `_get_streaming_message`.
    * When such a message exists, formats an error line prefixed with a warning emoji and appends it to the message's existing content using `crud.update_message`.

    Returns
    -------
    None

    Raises
    ------
    Any exceptions raised by database interactions (e.g., connection errors) are propagated to the caller.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

    if last_msg:
        error_info = f"\n  ⚠️ Error in iteration {message.get('loop')}: {message.get('error')}"
        current_content = last_msg.content or ""
        await crud.update_message(
            db=db,
            message_id=last_msg.message_id,
            content=current_content + error_info,
        )


async def _handle_agent_step(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `agent_step` broadcast event by appending its content to the existing streaming chat message.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used for database queries and updates.
    investigation_id: UUID
        Identifier of the investigation to which the agent belongs; used to locate the correct streaming message.
    agent_job: AgentJob | None
        The job representing the running agent. If `None` the function returns immediately without performing any work.
    message: Dict[str, Any]
        Payload received from the broadcast channel. Expected to contain a `content` key with the LLM-generated step text.

    Notes
    -----
    * The function constructs a streaming identifier of the form `"agent_{job_id}"` and retrieves the most recent message for that stream via :func:`_get_streaming_message`.
    * If a previous message exists, its content is sanitized using :func:`sanitize_llm_content` and appended to the stored message.
    * The database update is performed through :func:`crud.update_message`, which writes the concatenated content back to the `Message` record identified by `last_msg.message_id`.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

    if last_msg:
        step_content = sanitize_llm_content(message.get("content", ""))
        step_info = f"\n\n{step_content}"
        current_content = last_msg.content or ""
        await crud.update_message(
            db=db,
            message_id=last_msg.message_id,
            content=current_content + step_info,
        )


async def _handle_tool_executing(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a "tool_executing" broadcast message by locating the current streaming chat message and creating an explicit tool-execution record.

    The function performs the following steps:

    * If no `agent_job` is supplied the call is a no-op.
    * Retrieves the most recent streaming chat message for the given investigation using a generated `streaming_id` based on the agent job identifier.
    * Extracts tool information (name, arguments, optional description/display name) and turn metadata (turn number and maximum turns) from the incoming `message` payload.
    * Creates a new tool-execution entry via :func:`tool_crud.create_tool_execution`, linking it to the retrieved chat message.
    * Updates the chat message’s `metadata` by appending an event dictionary describing the execution, including sequence index, identifiers, status, and timestamp.
    * Persists the metadata changes with :func:`crud.update_message` and commits the transaction.

    If the required `tool` field is missing a warning is logged; if no streaming message exists a debug entry is recorded. Any unexpected exception is caught, logged with traceback, and does not propagate.

    Args:
        db: Async SQLAlchemy session used for all database interactions.
        investigation_id: Unique identifier of the investigation to which the broadcast belongs.
        agent_job: The :class:`AgentJob` instance representing the running agent; may be `None`.
        message: Dictionary containing the broadcast payload. Expected keys include
            `tool` (str), optional `arguments` (dict) with an optional `description` entry,
            `display_name` (str), `turn_number` (int), and `max_turns` (int).

    Returns:
        None

    Raises:
        No exceptions are raised; all errors are logged internally.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            tool_name = message.get("tool")
            if tool_name:
                # Use description from arguments if provided, otherwise use display_name
                arguments = message.get("arguments", {})
                description = arguments.get("description", "")
                display_name = description or message.get("display_name", tool_name)

                # Get turn information instead of tool counts
                turn_number = message.get("turn_number", 1)
                max_turns = message.get("max_turns", 10)

                # Create explicit tool execution record
                tool_execution = await tool_crud.create_tool_execution(
                    db=db,
                    chat_message_id=last_msg.message_id,
                    tool_name=tool_name,
                    display_name=display_name,
                    arguments=arguments,
                    execution_number=turn_number,  # Use turn number
                    max_tools=max_turns,  # Use max turns
                )

                # Add to event sequence
                current_metadata = last_msg.message_metadata or {}
                event_sequence = current_metadata.get("event_sequence", [])
                sequence_num = len(event_sequence)

                event_sequence.append(
                    {
                        "type": "tool_execution",
                        "sequence": sequence_num,
                        "execution_id": tool_execution.execution_id,
                        "tool_name": tool_name,
                        "display_name": display_name,
                        "execution_number": turn_number,  # Use turn number
                        "max_tools": max_turns,  # Use max turns
                        "status": "executing",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                current_metadata["event_sequence"] = event_sequence

                await crud.update_message(
                    db=db,
                    message_id=last_msg.message_id,
                    metadata=current_metadata,
                )
                await db.commit()

                logger.info(
                    f"Created tool execution {tool_execution.execution_id} for message {last_msg.message_id} (sequence {sequence_num})"
                )
            else:
                logger.warning("tool_executing message missing 'tool' field")
        else:
            logger.debug(f"No agent message found for tool_executing (streaming_id={streaming_id})")
    except Exception as e:
        logger.error(f"Failed to create tool_executing: {e}", exc_info=True)


async def _handle_llm_waiting(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `llm_waiting` broadcast message by marking the associated streaming chat
    message as waiting for a language-model response.

    The function looks up the most recent streaming message for the given investigation and
    agent job (identified by `streaming_id = f"agent_{agent_job.job_id}"`). If such a message
    exists, its `message_metadata` dictionary is updated with the key `isWaitingForLLM`
    set to `True` and persisted via the CRUD layer.  When no prior streaming message is
    found, a debug log entry is emitted. Any exception raised during processing is caught
    and logged as an error.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used for database queries and updates.
    investigation_id: UUID
        Identifier of the investigation to which the broadcast belongs.
    agent_job: AgentJob | None
        The agent job that generated the `llm_waiting` event; if `None` the function returns
        immediately without performing any action.
    message: Dict[str, Any]
        The raw broadcast payload (currently unused but retained for signature consistency).

    Returns
    -------
    None

    Raises
    ------
    All exceptions are caught internally; errors are logged but not re-raised.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            # Set isWaitingForLLM flag in metadata
            current_metadata = last_msg.message_metadata or {}
            current_metadata["isWaitingForLLM"] = True

            await crud.update_message(
                db=db,
                message_id=last_msg.message_id,
                metadata=current_metadata,
            )
        else:
            logger.debug(f"No agent message found for llm_waiting (streaming_id={streaming_id})")
    except Exception as e:
        logger.error(f"Failed to update llm_waiting: {e}", exc_info=True)


async def _handle_llm_chunk(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a streaming LLM chunk message by appending its content to the current agent-side chat message.

    Args:
        db: An asynchronous SQLAlchemy session used for database operations.
        investigation_id: The UUID of the investigation to which the message belongs.
        agent_job: The AgentJob instance representing the running job; if `None` the function returns immediately.
        message: A dictionary containing the incoming LLM chunk, expected to have a `'content'` key with the text fragment.

    The function retrieves (or creates) the streaming message associated with the given `agent_job` using its `job_id` as part of the `streaming_id`. If a previous message exists, it sanitises the new content, clears the `isWaitingForLLM` flag in the stored metadata, and updates the database record by concatenating the new chunk to the existing content. Errors during processing are logged but not re-raised.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            chunk_content = sanitize_llm_content(message.get("content", ""))
            current_content = last_msg.content or ""

            # Clear the waiting flag when tokens arrive
            current_metadata = last_msg.message_metadata or {}
            current_metadata["isWaitingForLLM"] = False

            await crud.update_message(
                db=db,
                message_id=last_msg.message_id,
                content=current_content + chunk_content,
                metadata=current_metadata,
            )
        else:
            logger.debug(f"No agent message found for llm_chunk (streaming_id={streaming_id})")
    except Exception as e:
        logger.error(f"Failed to update llm_chunk: {e}", exc_info=True)


async def _handle_agent_thinking(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `agent_thinking` broadcast message by updating the corresponding streaming chat record.

    The function retrieves (or creates) the streaming message associated with the given
    `investigation_id` and agent job, sanitises the incoming LLM content, and appends it
    to the stored message if it is new.  It also records a structured event entry in the
    message metadata under `event_sequence` to preserve ordering and timestamps.

    If no `AgentJob` instance is supplied the function returns immediately.
    When no existing streaming message is found the situation is logged and nothing
    is persisted.  Any exception raised during processing is caught, logged with a
    stack trace, and does not propagate further.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used for all database
            reads and writes.
        investigation_id: The UUID of the investigation to which the message belongs.
        agent_job: The :class:`AgentJob` instance representing the running agent; may be
            `None` in which case the function exits early.
        message: A mapping containing at least a `'content'` key with the raw LLM output.

    Returns:
        None

    Raises:
        No exceptions are raised; all errors are logged internally.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            thinking_content = sanitize_llm_content(message.get("content", ""))
            current_content = last_msg.content or ""

            # Skip if this looks like a complete_investigation summary (will be in agent_completed)
            if "Summary of" in thinking_content and "Investigation" in thinking_content:
                logger.debug("Skipping agent_thinking that looks like completion summary")
            # Check if this exact content is already in the message (prevent duplicates)
            elif thinking_content and thinking_content not in current_content:
                # Add to event sequence
                current_metadata = last_msg.message_metadata or {}
                event_sequence = current_metadata.get("event_sequence", [])
                sequence_num = len(event_sequence)

                event_sequence.append(
                    {
                        "type": "thinking",
                        "sequence": sequence_num,
                        "content": thinking_content,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                current_metadata["event_sequence"] = event_sequence

                # Still append to content for backwards compatibility
                await crud.update_message(
                    db=db,
                    message_id=last_msg.message_id,
                    content=current_content + "\n\n" + thinking_content,
                    metadata=current_metadata,
                )
                await db.commit()
        else:
            logger.debug(f"No agent message found for agent_thinking (streaming_id={streaming_id})")
    except Exception as e:
        logger.error(f"Failed to update agent_thinking: {e}", exc_info=True)


async def _handle_user_stopped(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a user-initiated stop event for an investigation.

    This coroutine updates the state of any active streaming assistant message associated with the given
    agent job to indicate that it is no longer waiting for a LLM response, and then persists a
    user-visible “stopped” message in the database.

    Args:
        db: An asynchronous SQLAlchemy session used for all database operations.
        investigation_id: The UUID of the investigation whose execution was stopped.
        user_id: The identifier of the user who issued the stop command.
        agent_job: The AgentJob instance representing the running agent, or `None` if no job is
            associated with the current stream.
        message: A dictionary containing broadcast data for the stop event; expected to include a
            `turn` key indicating the turn number at which the stop occurred.

    Raises:
        Any exception raised by the underlying CRUD operations or database commit will propagate
        to the caller.
    """
    if agent_job:
        streaming_id = f"agent_{agent_job.job_id}"
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            # Clear the waiting flag
            current_metadata = last_msg.message_metadata or {}
            current_metadata["isWaitingForLLM"] = False

            await crud.update_message(
                db=db,
                message_id=last_msg.message_id,
                metadata=current_metadata,
            )
            await db.commit()

    # Persist stop message
    await persist_assistant_message(
        db=db,
        investigation_id=investigation_id,
        user_id=user_id,
        content=f"⏸️ Investigation stopped by user at turn {message.get('turn')}",
        metadata={
            "type": "user_stopped",
            "turn": message.get("turn"),
        },
        include_in_llm_context=False,
        visible_in_ui=True,
    )
    await db.commit()


async def _handle_agent_cancelled(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `agent_cancelled` broadcast event by updating the corresponding streaming chat message in the database.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used for database operations.
    investigation_id : UUID
        Identifier of the investigation to which the agent belongs.
    user_id : int
        Identifier of the user who initiated the agent job.
    agent_job : AgentJob | None
        The agent job instance associated with the broadcast; if `None` the function returns early.
    message : dict[str, Any]
        Payload received from the broadcast containing optional keys:

        * `stats` - a dictionary of statistics to store in the message metadata.
        * `summary` - a textual summary describing why the agent was cancelled.

    Returns
    -------
    None

    Side Effects
    ------------
    * Retrieves the latest streaming message for the given investigation and agent job.
    * Clears the `isWaitingForLLM` flag and sets `agent_cancelled` to `True` in the message metadata.
    * Merges any provided `stats` into the metadata.
    * If a `summary` is present, appends it to both the message content and the `event_sequence` list in the metadata, recording a new “thinking” event with a timestamp.
    * Persists all changes to the database and commits the transaction.

    Raises
    ------
    Any exception raised during database access or update is caught internally; an error is logged but not re-raised.
    """
    logger.info(
        f"[AGENT_CANCELLED] Handler executing for job {agent_job.job_id if agent_job else 'unknown'}"
    )
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            logger.info(f"[AGENT_CANCELLED] Found working message {last_msg.message_id}")

            # Clear the waiting flag
            current_metadata = last_msg.message_metadata or {}
            current_metadata["isWaitingForLLM"] = False
            current_metadata["agent_cancelled"] = True

            # Add stats to metadata
            stats = message.get("stats", {})
            current_metadata["stats"] = stats

            # Add summary to event_sequence
            summary = message.get("summary", "")
            if summary:
                event_sequence = current_metadata.get("event_sequence", [])
                sequence_num = len(event_sequence)

                event_sequence.append(
                    {
                        "type": "thinking",
                        "sequence": sequence_num,
                        "content": f"\n\n{summary}",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                current_metadata["event_sequence"] = event_sequence

                # Also append to content
                current_content = last_msg.content or ""
                await crud.update_message(
                    db=db,
                    message_id=last_msg.message_id,
                    content=current_content + f"\n\n{summary}",
                    metadata=current_metadata,
                )
            else:
                await crud.update_message(
                    db=db,
                    message_id=last_msg.message_id,
                    metadata=current_metadata,
                )

            await db.commit()
            logger.info("[AGENT_CANCELLED] Marked message as cancelled with summary")
        else:
            logger.warning(
                f"[AGENT_CANCELLED] No agent message found (streaming_id={streaming_id})"
            )
    except Exception as e:
        logger.error(f"[AGENT_CANCELLED] Failed to mark cancelled: {e}", exc_info=True)


async def _handle_agent_error(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `agent_error` broadcast message by updating the corresponding streaming chat record.

    The function looks up the most recent streaming message for the given investigation and agent job. If a message is found, it clears the `isWaitingForLLM` flag, marks the message as having encountered an error, stores any provided statistics, and optionally appends a summary to both the message content and its `event_sequence` metadata. All changes are persisted with a database commit.

    Args:
        db: An asynchronous SQLAlchemy session used for all database operations.
        investigation_id: The UUID of the investigation to which the streaming message belongs.
        user_id: Identifier of the user who initiated the agent job (currently unused but retained for signature consistency).
        agent_job: The :class:`AgentJob` instance representing the running job; if `None` the function returns immediately.
        message: A dictionary containing the error payload. Expected keys include:
            - `stats` (optional): Mapping of statistical data to store under `metadata['stats']`.
            - `summary` (optional): Textual summary of the error to append to the message content and event sequence.

    Raises:
        Any exception raised during database access or update is caught internally; the function logs the error but does not re-raise.
    """
    logger.info(
        f"[AGENT_ERROR] Handler executing for job {agent_job.job_id if agent_job else 'unknown'}"
    )
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            logger.info(f"[AGENT_ERROR] Found working message {last_msg.message_id}")

            # Clear the waiting flag
            current_metadata = last_msg.message_metadata or {}
            current_metadata["isWaitingForLLM"] = False
            current_metadata["agent_error"] = True

            # Add stats to metadata
            stats = message.get("stats", {})
            current_metadata["stats"] = stats

            # Add summary to event_sequence
            summary = message.get("summary", "")
            if summary:
                event_sequence = current_metadata.get("event_sequence", [])
                sequence_num = len(event_sequence)

                event_sequence.append(
                    {
                        "type": "thinking",
                        "sequence": sequence_num,
                        "content": f"\n\n{summary}",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                current_metadata["event_sequence"] = event_sequence

                # Also append to content
                current_content = last_msg.content or ""
                await crud.update_message(
                    db=db,
                    message_id=last_msg.message_id,
                    content=current_content + f"\n\n{summary}",
                    metadata=current_metadata,
                )
            else:
                await crud.update_message(
                    db=db,
                    message_id=last_msg.message_id,
                    metadata=current_metadata,
                )

            await db.commit()
            logger.info("[AGENT_ERROR] Marked message as error with summary")
        else:
            logger.warning(f"[AGENT_ERROR] No agent message found (streaming_id={streaming_id})")
    except Exception as e:
        logger.error(f"[AGENT_ERROR] Failed to mark error: {e}", exc_info=True)


async def _handle_turn_error(
    db: AsyncSession,
    investigation_id: UUID,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle a turn_error broadcast event by appending error information to the associated streaming chat message.

    Args:
        db (AsyncSession): Asynchronous SQLAlchemy session used for database operations.
        investigation_id (UUID): Identifier of the investigation to which the message belongs.
        agent_job (AgentJob | None): The agent job context; if `None` the function exits without action.
        message (Dict[str, Any]): Payload containing error details, expected keys include:
            - `turn`: The turn number where the error occurred.
            - `error`: A string describing the error.

    The function retrieves the latest streaming message for the given agent job and investigation. If a message is found, it appends a formatted error line (including the turn number and error description) to the existing content and updates the record in the database. No value is returned.
    """
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

    if last_msg:
        error_info = f"\n  ⚠️ Error in turn {message.get('turn')}: {message.get('error')}"
        current_content = last_msg.content or ""
        await crud.update_message(
            db=db,
            message_id=last_msg.message_id,
            content=current_content + error_info,
        )


async def _handle_investigation_incomplete(
    db: AsyncSession,
    investigation_id: UUID,
    user_id: int,
    agent_job: AgentJob | None,
    message: Dict[str, Any],
) -> None:
    """
    Handle an `investigation_incomplete` broadcast event by updating the associated streaming chat message.

    The function retrieves the active streaming message for the given investigation and agent job, clears its waiting flag, marks it as incomplete, disables continuation, records any provided statistics, summary, and investigation choices in the message metadata, persists the changes to the database, and logs the operation. If no active message is found or an error occurs, appropriate warnings or errors are logged.

    Args:
        db: An `AsyncSession` used for all database interactions.
        investigation_id: The UUID of the investigation to which the message belongs.
        user_id: Identifier of the user who initiated the agent job (currently unused but retained for signature compatibility).
        agent_job: The `AgentJob` instance representing the running agent; if `None`, the function returns immediately.
        message: A dictionary containing payload data from the broadcast, expected keys include:
            * `stats` - optional dict of statistical information to store in metadata.
            * `summary` - optional string summarizing the investigation step; added to the event sequence.
            * `choices` - optional list of possible next actions or investigations; stored under `investigation_choices` in metadata.

    Returns:
        None

    Raises:
        Any exception raised during database access or message updating is caught internally; the function logs the error with stack trace but does not re-raise.
    """
    logger.info(
        f"[INVESTIGATION_INCOMPLETE] Handler executing for job {agent_job.job_id if agent_job else 'unknown'}"
    )
    if not agent_job:
        return

    streaming_id = f"agent_{agent_job.job_id}"
    try:
        # Mark the working message as completed (clear waiting flag)
        last_msg = await _get_streaming_message(db, investigation_id, streaming_id)

        if last_msg:
            logger.info(f"[INVESTIGATION_INCOMPLETE] Found working message {last_msg.message_id}")

            # Clear the waiting flag on the working message
            current_metadata = last_msg.message_metadata or {}
            current_metadata["isWaitingForLLM"] = False
            current_metadata["investigation_incomplete"] = True
            current_metadata["can_continue"] = False  # Disable old continue button

            # Add stats to metadata for reference
            stats = message.get("stats", {})
            current_metadata["stats"] = stats

            # Add summary to event_sequence
            summary = message.get("summary", "")
            if summary:
                event_sequence = current_metadata.get("event_sequence", [])
                sequence_num = len(event_sequence)

                event_sequence.append(
                    {
                        "type": "thinking",
                        "sequence": sequence_num,
                        "content": summary,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                current_metadata["event_sequence"] = event_sequence

            # Store investigation choices in metadata if provided
            choices = message.get("choices", [])
            if choices:
                logger.info(
                    f"[INVESTIGATION_INCOMPLETE] Storing {len(choices)} investigation choices in metadata"
                )
                current_metadata["investigation_choices"] = choices

            await crud.update_message(
                db=db,
                message_id=last_msg.message_id,
                metadata=current_metadata,
            )

            await db.commit()
            logger.info(
                "[INVESTIGATION_INCOMPLETE] Marked message as incomplete with investigation choices"
            )
        else:
            logger.warning(
                f"[INVESTIGATION_INCOMPLETE] No agent message found (streaming_id={streaming_id})"
            )
    except Exception as e:
        logger.error(f"[INVESTIGATION_INCOMPLETE] Failed to mark incomplete: {e}", exc_info=True)
