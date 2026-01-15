import logging
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text

from ..core.database import get_db
from ..auth import verify_jwt_token
from ..services.chat_router import (
    route_chat_message,
    handle_clarification_response,
)
from ..services.chat_persistence import (
    persist_user_message,
    persist_assistant_message,
    persist_system_message,
)
from ..services.websocket_manager import manager
from ..services.chat_broadcast import handle_broadcast_message
from ..crud import investigation as inv_crud
from ..models.chat_history import ChatMessage
from ..models.job_agent import AgentJob
from ..models.job_parsing import JobStatus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/{investigation_id}")
async def chat_websocket(
    websocket: WebSocket,
    investigation_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    \"""WebSocket endpoint handling real-time chat interactions for a specific investigation.

    This coroutine establishes a WebSocket connection authenticated via JWT,
    validates the investigation identifier, and then enters a message loop
    processing client-sent events such as questions, clarification responses,
    agent stop requests, and keep-alive pings.  Server-side messages are sent
    through the shared `manager` to inform the client about connection status,
    classification results, answer chunks, job queueing, clarification prompts,
    errors, and pong replies.

    The function performs the following steps:

    1. Verify the JWT token supplied as a query parameter; close the connection
       with code 1008 on failure.
    2. Validate that `investigation_id` is a proper UUID; close the connection
       with code 1003 if the format is invalid.
    3. Register the WebSocket with the global `manager` and send an initial
       `connected` message.
    4. Continuously receive JSON payloads from the client, dispatching them to
       helper functions based on the `type` field:
       * `question` - forward the user question for processing.
       * `clarification_response` - handle a previously requested clarification.
       * `confirm_mutation` - (deprecated) inform the client that graph mutations
         are no longer supported.
       * `stop_agent` - request termination of an ongoing background job.
       * `ping` - reply with a `pong` message.
       * any other type - respond with an `error` indicating an unknown message.

    On normal disconnection (`WebSocketDisconnect`) the socket is removed from
    the manager and a log entry is written.  Unexpected exceptions are logged,
    an `error` payload is sent to the client if possible, and the connection
    is cleaned up.

    Args:
        websocket: The FastAPI `WebSocket` instance representing the client
            connection.
        investigation_id: String identifier of the investigation; must be a valid
            UUID.
        token: JWT authentication token supplied as a query parameter.
        db: Asynchronous SQLAlchemy session injected via dependency injection.

    Returns:
        None

    Raises:
        WebSocketDisconnect: Propagated when the client disconnects cleanly.
        Exception: Any unexpected error is caught, logged, and results in an
            `error` message sent to the client before cleanup.\"""
    """
    # Verify JWT token
    try:
        payload = verify_jwt_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token")
            return
        user_id = int(user_id)
    except Exception as e:
        await websocket.close(code=1008, reason=f"Authentication failed: {str(e)}")
        return

    # Validate investigation_id format
    try:
        inv_uuid = UUID(investigation_id)
    except ValueError:
        await websocket.close(code=1003, reason="Invalid investigation ID format")
        return

    # Connect
    await manager.connect(investigation_id, websocket)

    # Send welcome message
    await manager.send_message(
        websocket,
        {
            "type": "connected",
            "investigation_id": investigation_id,
            "message": "Connected to investigation chat",
        },
    )

    # State tracking for multi-turn conversations
    pending_clarification: Optional[Dict[str, Any]] = None
    original_question: Optional[str] = None

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "question":
                await _handle_question(websocket, db, inv_uuid, user_id, investigation_id, data)
                original_question = data.get("text", "").strip()

            elif message_type == "clarification_response":
                result = await _handle_clarification_response(
                    websocket, db, inv_uuid, user_id, data, pending_clarification
                )
                if result:
                    pending_clarification = None

            elif message_type == "confirm_mutation":
                # DEPRECATED: Graph mutations are no longer supported
                await manager.send_message(
                    websocket,
                    {
                        "type": "error",
                        "message": "Graph mutations are deprecated. Use timeline entries instead.",
                    },
                )

            elif message_type == "stop_agent":
                await _handle_stop_agent(websocket, db, investigation_id, data)

            elif message_type == "ping":
                await manager.send_message(websocket, {"type": "pong"})

            else:
                await manager.send_message(
                    websocket, {"type": "error", "message": f"Unknown message type: {message_type}"}
                )

    except WebSocketDisconnect:
        manager.disconnect(investigation_id, websocket)
        logger.info(f"Client disconnected from investigation {investigation_id}")

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await manager.send_message(
                websocket, {"type": "error", "message": f"Internal error: {str(e)}"}
            )
        except:
            pass
        manager.disconnect(investigation_id, websocket)


async def _handle_question(
    websocket: WebSocket,
    db: AsyncSession,
    inv_uuid: UUID,
    user_id: int,
    investigation_id: str,
    data: Dict[str, Any],
) -> None:
    """
    Handle an incoming user question over a WebSocket connection.

    This coroutine validates the request, checks investigation parsing locks, retrieves recent chat history for context, persists the user's message, and broadcasts it to all connected clients. It then creates and broadcasts a temporary “thinking” assistant message to provide immediate UI feedback while routing the query through the appropriate backend (LLM, RAG, or agent job).

    The function streams routing responses back to the client, updates intent classification, tracks whether an external agent job was queued, collects answer chunks, and processes special response types via `_handle_routing_response`. After routing completes, if the response is a non-agent answer, it finalizes the thinking message with the assembled content, enriches its metadata (including intent, RAG event sequences, and tool execution IDs), persists any RAG tool executions, and broadcasts updates to all clients. Finally, it signals that the investigation state has returned to idle.

    Args:
        websocket: The active WebSocket connection for sending direct messages back to the requester.
        db: Asynchronous SQLAlchemy session used for database queries and mutations.
        inv_uuid: Unique identifier of the investigation associated with the chat.
        user_id: Identifier of the user who submitted the question.
        investigation_id: String identifier used for broadcasting messages to all participants in the investigation.
        data: Dictionary containing the incoming payload, expected keys include:
            - `text` (str): The user's query text.
            - `effort` (str, optional): Desired processing effort level; defaults to `"medium"`.
            - `router_mode` (str, optional): Routing mode for the message; defaults to `"auto"`.

    Returns:
        None

    Raises:
        None directly; error conditions are communicated to the client via WebSocket messages with type `"error"`.
    """
    user_query = data.get("text", "").strip()
    effort = data.get("effort", "medium")
    router_mode = data.get("router_mode", "auto")

    if not user_query:
        await manager.send_message(websocket, {"type": "error", "message": "Empty query received"})
        return

    # Check if investigation is locked for parsing
    is_locked = await inv_crud.is_parsing_locked(db, inv_uuid)
    if is_locked:
        await manager.send_message(
            websocket,
            {
                "type": "error",
                "message": "Investigation is locked while artifacts are being parsed. Please wait for parsing to complete.",
                "error_code": "PARSING_LOCKED",
            },
        )
        return

    # Fetch recent chat history for context
    # This will be passed to route_chat_message for intent classification
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.investigation_id == inv_uuid)
        .where(ChatMessage.include_in_llm_context == True)
        .where(ChatMessage.deleted_at.is_(None))
        .order_by(desc(ChatMessage.created_at))
        .limit(10)
    )
    messages = list(result.scalars().all())
    messages.reverse()  # Chronological order

    chat_history = [{"role": msg.role, "content": msg.content or ""} for msg in messages]

    # Persist user message
    user_message_id = await persist_user_message(
        db=db,
        investigation_id=inv_uuid,
        user_id=user_id,
        content=user_query,
    )
    await db.commit()

    # Broadcast user message to all connected clients
    await manager.broadcast(
        investigation_id,
        {
            "type": "user_message",
            "message_id": user_message_id,
            "content": user_query,
            "user_id": user_id,
        },
    )

    # IMMEDIATELY create a "thinking" assistant message BEFORE LLM processing
    # This provides instant feedback to the user while the LLM is processing
    # Note: We use a temporary streaming_id that will be updated when job_queued arrives
    thinking_message_id = await persist_assistant_message(
        db=db,
        investigation_id=inv_uuid,
        user_id=user_id,
        content="",  # Empty content - will show typing indicator
        metadata={
            "type": "agent_thinking_initial",
            "streaming_message_id": f"thinking_{user_message_id}",
            "isWaitingForLLM": True,
            "event_sequence": [],
        },
        include_in_llm_context=False,
        visible_in_ui=True,
    )
    await db.commit()

    # Broadcast the thinking message immediately
    await manager.broadcast(
        investigation_id,
        {
            "type": "message_created",
            "message_id": thinking_message_id,
        },
    )

    # Route the message and collect assistant responses
    assistant_response_chunks = []
    assistant_response_metadata = {}
    intent_type = None
    is_agent_job = False

    async for response in route_chat_message(
        db=db,
        investigation_id=inv_uuid,
        user_query=user_query,
        user_id=user_id,
        effort=effort,
        router_mode=router_mode,
        chat_history=chat_history,  # Pass chat history for context-aware classification
    ):
        # Track intent classification
        if response.get("type") == "intent_classified":
            intent_type = response.get("intent")

        # Track if this is an agent job (will be handled by worker)
        if response.get("type") == "job_queued":
            is_agent_job = True

        # Collect answer chunks and metadata for persistence
        if response.get("type") == "answer_chunk":
            assistant_response_chunks.append(response.get("content", ""))
            # Capture metadata from the response (includes event_sequence for RAG)
            if response.get("metadata"):
                assistant_response_metadata.update(response.get("metadata", {}))

        # Handle special message types and create DB messages
        await _handle_routing_response(
            db, inv_uuid, user_id, response, investigation_id, thinking_message_id
        )

        # Send to client
        await manager.send_message(websocket, response)

    # After routing complete, handle non-agent responses
    if assistant_response_chunks and not is_agent_job:
        # For timeline/general chat/RAG responses, update the thinking message with the final answer
        full_response = "".join(assistant_response_chunks)

        if thinking_message_id:
            from ..crud.chat_history import update_message
            from ..services.handlers.rag_handler import persist_rag_tool_executions

            # Build metadata with event_sequence from RAG (if present)
            final_metadata = {
                "intent": intent_type,
                "type": "answer",
                "isWaitingForLLM": False,
            }
            # Merge in any metadata from the response (event_sequence, stats, etc.)
            final_metadata.update(assistant_response_metadata)

            await update_message(
                db=db,
                message_id=thinking_message_id,
                content=full_response,
                metadata=final_metadata,
            )
            await db.commit()

            # If this was a RAG query, persist tool executions now that we have the message_id
            if final_metadata.get("handler") == "rag" and final_metadata.get("event_sequence"):
                logger.info(f"Persisting RAG tool executions for message {thinking_message_id}")
                execution_ids = await persist_rag_tool_executions(
                    db=db,
                    message_id=thinking_message_id,
                    event_sequence=final_metadata["event_sequence"],
                    expanded_terms=assistant_response_metadata.get("expanded_terms", []),
                    chunks_data=assistant_response_metadata.get("chunks_data", []),
                )
                await db.commit()

                # Update event_sequence with execution_ids so UI can load the tool executions
                if execution_ids:
                    event_sequence = final_metadata.get("event_sequence", [])
                    execution_idx = 0

                    for event in event_sequence:
                        if event.get("type") == "tool_execution" and execution_idx < len(
                            execution_ids
                        ):
                            event["execution_id"] = execution_ids[execution_idx]
                            execution_idx += 1

                    # Update the message metadata with execution_ids
                    await update_message(
                        db=db,
                        message_id=thinking_message_id,
                        metadata=final_metadata,
                    )
                    await db.commit()
                    logger.info(f"Updated event_sequence with {len(execution_ids)} execution_ids")

            # Broadcast message update
            await manager.broadcast(
                investigation_id,
                {
                    "type": "message_updated",
                    "message_id": thinking_message_id,
                },
            )

            # IMPORTANT: Tell UI to unlock (remove stop button)
            await manager.broadcast(
                investigation_id, {"type": "investigation_state_changed", "state": "idle"}
            )
        else:
            # Fallback: create new message
            await persist_assistant_message(
                db=db,
                investigation_id=inv_uuid,
                user_id=user_id,
                content=full_response,
                metadata={"intent": intent_type},
                include_in_llm_context=True,
            )
            await db.commit()

            # Tell UI to unlock
            await manager.broadcast(
                investigation_id, {"type": "investigation_state_changed", "state": "idle"}
            )


async def _handle_routing_response(
    db: AsyncSession,
    inv_uuid: UUID,
    user_id: int,
    response: Dict[str, Any],
    investigation_id: str,
    thinking_message_id: Optional[int] = None,
) -> None:
    """
    Handle special routing response types emitted by the assistant worker.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used for database operations.
    inv_uuid: UUID
        Unique identifier of the investigation to which the messages belong.
    user_id: int
        Identifier of the user who initiated the request.
    response: dict[str, Any]
        Dictionary containing the routing response. Expected keys include `type` and additional fields specific to each type (e.g., `policy_id`, `job_id`, `message`).
    investigation_id: str
        String identifier used for broadcasting events to connected WebSocket clients.
    thinking_message_id: int | None, optional
        Identifier of the temporary “thinking” message that represents a pending assistant response. If provided, it will be updated or deleted according to the response type; otherwise fallback messages are created.

    Raises
    ------
    Any exception raised by the underlying CRUD functions, database commit operations, or the broadcast manager will propagate to the caller. The function does not catch exceptions internally.
    """
    response_type = response.get("type")

    if response_type == "clarification_request":
        await persist_system_message(
            db=db,
            investigation_id=inv_uuid,
            user_id=user_id,
            content=f"Clarification requested for policy: {response.get('policy_id')}",
            metadata={
                "type": "clarification_request",
                "policy_id": response.get("policy_id"),
            },
            include_in_llm_context=False,
        )

        # Delete the thinking message since we're asking for clarification
        if thinking_message_id:
            from ..crud.chat_history import delete_message

            await delete_message(db, thinking_message_id)
            await db.commit()
            await manager.broadcast(
                investigation_id,
                {
                    "type": "message_deleted",
                    "message_id": thinking_message_id,
                },
            )

    elif response_type == "job_queued":
        # Update the existing thinking message with job_id instead of creating a new one
        logger.info(
            f"job_queued handler: thinking_message_id={thinking_message_id}, job_id={response.get('job_id')}"
        )
        if thinking_message_id:
            from ..crud.chat_history import update_message

            # IMPORTANT: Update streaming_message_id to match what the worker will look for
            # This prevents duplicate messages when worker broadcasts agent_started
            logger.info(
                f"Updating existing thinking message {thinking_message_id} with streaming_id=agent_{response.get('job_id')}"
            )
            await update_message(
                db=db,
                message_id=thinking_message_id,
                metadata={
                    "type": "agent_starting",
                    "job_id": response.get("job_id"),
                    "policy_id": response.get("policy_id"),
                    "streaming_message_id": f"agent_{response.get('job_id')}",  # Worker will look for this
                    "isWaitingForLLM": True,
                    "event_sequence": [],
                },
            )
            await db.commit()

            # Broadcast message update
            await manager.broadcast(
                investigation_id,
                {
                    "type": "message_updated",
                    "message_id": thinking_message_id,
                },
            )
        else:
            # Fallback: create a new message if thinking_message_id wasn't provided
            logger.warning(
                f"thinking_message_id is None, creating fallback message for job_id={response.get('job_id')}"
            )
            message_id = await persist_assistant_message(
                db=db,
                investigation_id=inv_uuid,
                user_id=user_id,
                content="",  # Empty content - will show typing indicator
                metadata={
                    "type": "agent_starting",
                    "job_id": response.get("job_id"),
                    "policy_id": response.get("policy_id"),
                    "streaming_message_id": f"agent_{response.get('job_id')}",
                    "isWaitingForLLM": True,
                    "event_sequence": [],
                },
                include_in_llm_context=False,
                visible_in_ui=True,
            )
            await db.commit()

            # Broadcast message_created
            await manager.broadcast(
                investigation_id,
                {
                    "type": "message_created",
                    "message_id": message_id,
                },
            )

    elif response_type == "error":
        # Update thinking message with error instead of deleting
        if thinking_message_id:
            from ..crud.chat_history import update_message

            await update_message(
                db=db,
                message_id=thinking_message_id,
                content=f"❌ Error: {response.get('message')}",
                metadata={
                    "type": "error",
                    "details": response.get("details"),
                    "isWaitingForLLM": False,
                },
            )
            await db.commit()
            await manager.broadcast(
                investigation_id,
                {
                    "type": "message_updated",
                    "message_id": thinking_message_id,
                },
            )
        else:
            # Fallback: create error message
            await persist_system_message(
                db=db,
                investigation_id=inv_uuid,
                user_id=user_id,
                content=f"Error: {response.get('message')}",
                metadata={
                    "type": "error",
                    "details": response.get("details"),
                },
                include_in_llm_context=False,
            )
            await db.commit()


async def _handle_clarification_response(
    websocket: WebSocket,
    db: AsyncSession,
    inv_uuid: UUID,
    user_id: int,
    data: Dict[str, Any],
    pending_clarification: Optional[Dict[str, Any]],
) -> bool:
    """
    Handle a clarification response from a WebSocket client.

    Parameters
    ----------
    websocket: WebSocket
        The active WebSocket connection used to send messages back to the client.
    db: AsyncSession
        Asynchronous SQLAlchemy session for persisting messages and related data.
    inv_uuid: UUID
        Unique identifier of the investigation to which the clarification belongs.
    user_id: int
        Identifier of the user who submitted the clarification response.
    data: Dict[str, Any]
        Payload received from the client. Expected keys include `policy_id` (str) and optionally `rule_values` (dict) containing configuration values for the policy.
    pending_clarification: Optional[Dict[str, Any]]
        The stored clarification request awaiting a response. Must contain at least an `original_question` key; if `None`, the function aborts with an error message.

    Returns
    -------
    bool
        `True` if the clarification was processed and appropriate messages were persisted and sent; `False` if validation failed or no pending clarification existed.

    Raises
    ------
    No exceptions are raised directly; validation errors are communicated to the client via WebSocket messages.
    """
    if not pending_clarification:
        await manager.send_message(
            websocket, {"type": "error", "message": "No pending clarification request"}
        )
        return False

    policy_id = data.get("policy_id")
    if not policy_id or not isinstance(policy_id, str):
        await manager.send_message(
            websocket,
            {"type": "error", "message": "Missing or invalid policy_id in clarification response"},
        )
        return False

    rule_values = data.get("rule_values", {})

    # Persist user's clarification response
    clarification_summary = f"Provided configuration for {policy_id}: {', '.join(f'{k}={v}' for k, v in rule_values.items())}"
    await persist_system_message(
        db=db,
        investigation_id=inv_uuid,
        user_id=user_id,
        content=clarification_summary,
        metadata={
            "type": "clarification_provided",
            "policy_id": policy_id,
            "rule_values": rule_values,
        },
        include_in_llm_context=False,
    )

    # Process clarification
    result = await handle_clarification_response(
        db=db,
        investigation_id=inv_uuid,
        policy_id=policy_id,
        rule_values=rule_values,
        original_question=pending_clarification["original_question"],
        user_id=user_id,
    )

    # Send result to client
    await manager.send_message(websocket, result)

    # Persist the result if it's a job_queued response
    if result.get("type") == "job_queued":
        job_message = f"✓ Analysis job created (Job #{result.get('job_id')})\n\nPolicy: {result.get('policy_title')}\nEstimated Duration: {result.get('estimated_duration')}\n\nThe agent is now processing your request."
        await persist_assistant_message(
            db=db,
            investigation_id=inv_uuid,
            user_id=user_id,
            content=job_message,
            metadata={
                "type": "job_queued",
                "job_id": result.get("job_id"),
                "policy_id": result.get("policy_id"),
            },
            include_in_llm_context=False,
        )

    return True


async def _handle_stop_agent(
    websocket: WebSocket,
    db: AsyncSession,
    investigation_id: str,
    data: Dict[str, Any],
) -> None:
    """
    Handle a request from a client to stop an agent associated with a specific job.

    Parameters
    ----------
    websocket: WebSocket
        The active WebSocket connection through which responses and error messages are sent back to the requesting client.
    db: AsyncSession
        An asynchronous SQLAlchemy session used to execute the update that marks the job as having a stop request in its metadata.
    investigation_id: str
        Identifier of the investigation context; used to broadcast state changes to all participants subscribed to this investigation.
    data: Dict[str, Any]
        Payload received from the client. Must contain a `job_id` key identifying the job whose agent should be stopped.

    Behavior
    --------
    * If `job_id` is missing from `data`, an error message is sent over the WebSocket and the function returns early.
    * Otherwise, the function updates the `jobs_agents` table, setting the `stop_requested` flag to true in the JSONB `metadata` column for the specified job.
    * The database transaction is committed after the update.
    * An informational log entry records that a stop signal was set.
    * Acknowledgement of the stop request is broadcast to all clients connected to the investigation, including the `job_id` and a descriptive message.
    * Finally, an `investigation_state_changed` event with state `idle` is broadcast to inform participants that the investigation has returned to an idle state.

    Returns
    -------
    None

    Raises
    ------
    Any exception raised by database operations or WebSocket communication will propagate to the caller.
    """
    job_id = data.get("job_id")

    if not job_id:
        await manager.send_message(
            websocket, {"type": "error", "message": "No job_id provided for stop request"}
        )
        return

    # Set stop signal in job metadata
    await db.execute(
        text(
            """
            UPDATE jobs_agents
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'),
                '{stop_requested}',
                'true'
            )
            WHERE job_id = :job_id
        """
        ),
        {"job_id": job_id},
    )
    await db.commit()

    logger.info(f"Stop signal set for job {job_id}")

    # Acknowledge the stop request and broadcast to all clients
    await manager.broadcast(
        investigation_id,
        {"type": "stop_acknowledged", "job_id": job_id, "message": "Stop signal sent to agent"},
    )

    # Send investigation state change
    await manager.broadcast(
        investigation_id, {"type": "investigation_state_changed", "state": "idle"}
    )


@router.get("/history/{investigation_id}")
async def get_chat_history(
    investigation_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve paginated chat history for a given investigation.

    Args:
        investigation_id (str): UUID string identifying the investigation whose messages are requested.
        limit (int, optional): Maximum number of messages to return. Must be between 1 and 1000 inclusive; defaults to 100.
        offset (int, optional): Number of most recent messages to skip before returning results; must be non-negative, default is 0.
        db (AsyncSession): Asynchronous SQLAlchemy session provided by the `get_db` dependency.

    Returns:
        dict: A dictionary containing two keys:
            - "messages": List of dictionaries, each representing a chat message with the following fields:
                * "message_id" (UUID): Unique identifier of the message.
                * "role" (str): Role of the sender (e.g., user, assistant).
                * "content" (str): Text content of the message.
                * "metadata" (dict): Arbitrary metadata associated with the message.
                * "created_at" (str): ISO-8601 timestamp of when the message was created.
            - "total" (int): Number of messages included in the returned list.

    Raises:
        HTTPException: If `investigation_id` cannot be parsed as a valid UUID, a 400 Bad Request error is raised.
    """
    try:
        inv_uuid = UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid investigation ID format")

    query = (
        select(ChatMessage)
        .where(ChatMessage.investigation_id == inv_uuid)
        .order_by(ChatMessage.created_at.asc())
    )

    if limit:
        query = query.limit(limit)
    if offset > 0:
        query = query.offset(offset)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    # Convert to JSON-serializable format
    return {
        "messages": [
            {
                "message_id": msg.message_id,
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.message_metadata,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ],
        "total": len(messages),
    }


@router.get("/active-job/{investigation_id}")
async def get_active_job(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Check for an active agent job associated with a given investigation.

    This endpoint is used by the UI to determine whether it should reconnect to an in-progress
    job after a page refresh. It queries the database for the most recent `AgentJob` that
    has a status of `RUNNING` for the specified investigation and returns a summary of
    that job if one exists.

    Args:
        investigation_id (str): The UUID string identifying the investigation.
        db (AsyncSession, optional): An asynchronous SQLAlchemy session provided by FastAPI
            dependency injection. Defaults to the result of :func:`get_db`.

    Raises:
        HTTPException: If `investigation_id` is not a valid UUID (status code 400).

    Returns:
        dict: A dictionary with a single key `"active_job"`.
            * If an active job is found, its value is a nested dictionary containing:

              - `job_id` (str): Identifier of the job.
              - `policy_id` (str | None): Associated policy identifier.
              - `status` (str): Current status value (e.g., `"RUNNING"`).
              - `started_at` (str | None): ISO-8601 timestamp when the job started.
              - `metadata` (dict): Additional metadata for the job, empty if none.

            * If no active job exists, the value is `None`.
    """
    try:
        inv_uuid = UUID(investigation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid investigation ID format")

    # Find the most recent running job for this investigation
    result = await db.execute(
        select(AgentJob)
        .where(AgentJob.investigation_id == inv_uuid)
        .where(AgentJob.status == JobStatus.RUNNING)
        .order_by(desc(AgentJob.started_at))
        .limit(1)
    )

    active_job = result.scalar_one_or_none()

    if not active_job:
        return {"active_job": None}

    return {
        "active_job": {
            "job_id": active_job.job_id,
            "policy_id": active_job.policy_id,
            "status": active_job.status.value,
            "started_at": active_job.started_at.isoformat() if active_job.started_at else None,
            "metadata": active_job.job_metadata or {},
        }
    }


@router.post("/continue/{job_id}")
async def continue_investigation(
    job_id: int,
    effort: str = Body("medium", embed=True),
    db: AsyncSession = Depends(get_db),
):
    """
    Continue an incomplete investigation by creating a new job with additional turns.

    The function retrieves the original job identified by `job_id` and verifies that it exists and is not currently running. Based on the requested `effort` level (low, medium, or high), it calculates the number of extra turns to allocate. It then creates a new `AgentJob` record copying the parameters of the original job while updating its metadata to reference the continuation.

    If an incomplete assistant message associated with the original job is found, the function updates that message’s metadata to mark it as no longer incomplete, flags it as part of a continuation, and adds a “thinking” indicator. The updated message is persisted via `update_message` and broadcast to connected WebSocket clients so UI components can hide any banner indicating incompleteness.

    Finally, the function broadcasts a `job_continuing` event containing identifiers for the new job (and optionally the related message) to all listeners of the investigation’s channel, then returns a dictionary summarising the newly queued continuation job.

    Args:
        job_id: Identifier of the original job to continue.
        effort: Desired effort level for the continuation; determines how many additional turns are added. Defaults to `"medium"` and is read from the request body.
        db: Asynchronous SQLAlchemy session injected by FastAPI's dependency system.

    Returns:
        A mapping with keys `job_id`, `investigation_id`, `additional_turns` and `status` indicating that the new job has been queued.

    Raises:
        HTTPException 404: If no job matching `job_id` exists.
        HTTPException 400: If the original job is still running and cannot be continued.
    """
    # Get the original job
    result = await db.execute(select(AgentJob).where(AgentJob.job_id == job_id))
    original_job = result.scalar_one_or_none()

    if not original_job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify job is completed (not running)
    if original_job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Job is still running")

    # Determine additional turns based on effort
    effort_to_turns = {
        "low": 5,
        "medium": 10,
        "high": 15,
    }
    additional_turns = effort_to_turns.get(effort, 10)

    # Find the existing incomplete message for this job
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.investigation_id == original_job.investigation_id)
        .where(ChatMessage.role == "assistant")
        .where(ChatMessage.message_metadata["job_id"].astext == str(job_id))
        .order_by(desc(ChatMessage.created_at))
        .limit(1)
    )
    existing_message = result.scalar_one_or_none()

    # Create a new job with same parameters but increased turn limit
    new_job = AgentJob(
        investigation_id=original_job.investigation_id,
        user_id=original_job.user_id,
        policy_id=original_job.policy_id,
        rule_values=original_job.rule_values,
        seed_instructions=original_job.seed_instructions,
        status=JobStatus.PENDING,
        job_metadata={
            "continued_from": job_id,
            "additional_turns": additional_turns,
            "original_effort": original_job.rule_values.get("effort", "medium"),
            "continuation_effort": effort,
            "reuse_message_id": existing_message.message_id if existing_message else None,
        },
    )

    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    logger.info(
        f"Created continuation job {new_job.job_id} from job {job_id} with {additional_turns} additional turns"
    )

    # If we have an existing message, update it to remove the incomplete flag and add continuation metadata
    if existing_message:
        current_metadata = existing_message.message_metadata or {}
        current_metadata["investigation_incomplete"] = False
        current_metadata["is_continuing"] = True
        current_metadata["continuation_job_id"] = new_job.job_id
        current_metadata["isWaitingForLLM"] = True  # Show thinking indicator again

        # Use ORM update instead of raw SQL to avoid parameter binding issues
        from ..crud.chat_history import update_message

        await update_message(
            db=db,
            message_id=existing_message.message_id,
            metadata=current_metadata,
        )
        await db.commit()

        # Broadcast message update to hide the continuation banner
        await manager.broadcast(
            str(original_job.investigation_id),
            {
                "type": "message_updated",
                "message_id": existing_message.message_id,
            },
        )

    # Broadcast job_queued message to WebSocket clients (but don't create a new message)
    await manager.broadcast(
        str(original_job.investigation_id),
        {
            "type": "job_continuing",
            "job_id": new_job.job_id,
            "original_job_id": job_id,
            "policy_id": new_job.policy_id,
            "message_id": existing_message.message_id if existing_message else None,
        },
    )

    return {
        "job_id": new_job.job_id,
        "investigation_id": str(new_job.investigation_id),
        "additional_turns": additional_turns,
        "status": "queued",
    }


@router.post("/broadcast/{investigation_id}")
async def broadcast_message(
    investigation_id: str,
    message: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Broadcast a message to all WebSocket clients of an investigation and persist it.

    This endpoint receives a notification from background workers, validates the
    investigation identifier, stores the message in the database, and forwards the
    payload to every active WebSocket connection associated with the given
    `investigation_id`.

    Args:
        investigation_id: The UUID string identifying the investigation for which
            the broadcast is intended.
        message: A dictionary containing the message payload.  It must include a
            `type` key that describes the kind of notification being sent.
        db: An asynchronous SQLAlchemy session provided by dependency injection,
            used to persist the broadcast message.

    Returns:
        dict: A JSON-serialisable mapping with keys:
            - `status` (str): `"ok"` when persistence and broadcasting succeed,
              or `"ok_with_errors"` if persistence fails but broadcasting still
              succeeds.
            - `recipients` (int): The number of WebSocket clients that received the
              broadcast.
            - `error` (str, optional): Human-readable description of any error that
              occurred during persistence.

    Raises:
        HTTPException: With status code 400 if `investigation_id` is not a valid
        UUID, or with status code 500 for unexpected errors when both persistence
        and broadcasting fail.
    """
    message_type = message.get("type")
    logger.info(f"[BROADCAST] type={message_type}, inv={investigation_id[:8]}")

    try:
        # Validate investigation_id format
        try:
            inv_uuid = UUID(investigation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid investigation ID format")

        # Handle the broadcast message (persist to DB)
        await handle_broadcast_message(db, inv_uuid, message)

        # Broadcast to WebSocket clients
        recipients = manager.get_connection_count(investigation_id)
        logger.info(
            f"Broadcasting {message_type} to {recipients} clients for investigation {investigation_id}"
        )
        await manager.broadcast(investigation_id, message)

        return {"status": "ok", "recipients": recipients}

    except Exception as e:
        logger.error(f"Broadcast failed: {e}", exc_info=True)
        # Still try to broadcast even if persistence failed
        try:
            recipients = manager.get_connection_count(investigation_id)
            await manager.broadcast(investigation_id, message)
            return {"status": "ok_with_errors", "recipients": recipients, "error": str(e)}
        except:
            raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
