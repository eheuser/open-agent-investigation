from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, List

from ..deps import get_db, get_current_user
from ..models.user import User
from ..services.policy_router import route_question
from ..services.chat_router import route_chat_message, handle_clarification_response
from ..services.chat_persistence import (
    persist_user_message,
    persist_assistant_message,
    persist_system_message,
)
from ..crud.investigation import check_investigation_access

from ..utils.log_setup import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/policy/route")
async def route_policy(
    payload: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Route a policy-related question through the chat router with intent classification and persist relevant messages.

    Parameters
    ----------
    payload: Dict[str, Any]
        The request body parsed by FastAPI. Must contain `investigation_id` (a UUID string) and `question` (the user’s query). Optional keys include `effort` to control processing intensity.
    db: AsyncSession
        An asynchronous SQLAlchemy session injected via dependency injection. Used for all database operations such as access checks and message persistence.
    user: User
        The authenticated user object provided by the `get_current_user` dependency. Permissions are verified against the investigation.

    Returns
    -------
    Dict[str, Any]
        A JSON-serialisable response describing the outcome of the routing operation. Possible structures:

        * `{"type": "intent_classified", "intent": str, "confidence": float}`
        * `{"type": "events_inserted", "count": int, "message": str}`
        * `{"type": "mutation_preview", "mutation_id": str, "changes": dict}`
        * `{"type": "answer_chunk", "content": str, "is_final": bool}`
        * `{"type": "job_queued", "job_id": int, ...}`
        * `{"type": "clarification_request", "missing_rules": list, ...}`
        * `{"type": "error", "message": str}`

        If multiple responses are generated they are wrapped in a `multi_response` envelope:
        `{"type": "multi_response", "responses": [...], "refresh_graph": bool (optional)}`. A single response is returned directly, optionally augmented with `"refresh_graph": True` when the underlying graph was mutated.

    Raises
    ------
    HTTPException
        * 400 - if `investigation_id` or `question` are missing from the payload.
        * 403 - if the user lacks access to the specified investigation (raised by `check_investigation_access`).
        * 500 - for unexpected errors occurring inside the chat router, with details included in the response body.

    Side Effects
    ------------
    * Persists the user's original question as a user message linked to the investigation.
    * Streams responses from `route_chat_message` and aggregates answer chunks; the full assistant reply is persisted once complete, together with detected intent metadata.
    * Persists system-level messages for job queuing events or errors, excluding them from LLM context when appropriate.
    * May trigger graph refresh hints based on `graph_mutated` or `graph_updated` response types.
    """
    investigation_id_str = payload.get("investigation_id")
    question = payload.get("question")
    effort = payload.get("effort", "medium")  # Default to medium effort

    if not all([investigation_id_str, question]):
        raise HTTPException(status_code=400, detail="investigation_id and question are required")

    # Type assertions after validation
    investigation_id = UUID(str(investigation_id_str))
    question_str = str(question)

    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Persist user message to chat history
    await persist_user_message(
        db=db,
        investigation_id=investigation_id,
        user_id=user.user_id,
        content=question_str,
    )

    # Use new chat router with intent classification
    responses: List[Dict[str, Any]] = []
    assistant_content_chunks: List[str] = []
    intent_type = None

    try:
        async for response in route_chat_message(
            db=db,
            investigation_id=investigation_id,
            user_query=question_str,
            user_id=user.user_id,
            effort=effort,
        ):
            logger.debug(f"Chat router response: {response}")
            responses.append(response)

            # Track intent classification
            if response.get("type") == "intent_classified":
                intent_type = response.get("intent")

            # Collect answer chunks for persistence
            if response.get("type") == "answer_chunk":
                assistant_content_chunks.append(response.get("content", ""))
    except Exception as e:
        logger.error(f"Error in chat router: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat router error: {str(e)}")

    logger.debug(f"Total responses collected: {len(responses):,}")

    # Persist assistant response if we got answer chunks
    if assistant_content_chunks:
        full_response = "".join(assistant_content_chunks)
        await persist_assistant_message(
            db=db,
            investigation_id=investigation_id,
            user_id=user.user_id,
            content=full_response,
            metadata={"intent": intent_type},
            include_in_llm_context=True,
        )

    # Persist system messages for job queued, errors, etc.
    for response in responses:
        if response.get("type") == "job_queued":
            await persist_system_message(
                db=db,
                investigation_id=investigation_id,
                user_id=user.user_id,
                content=f"Job queued: {response.get('message')}",
                metadata={
                    "type": "job_queued",
                    "job_id": response.get("job_id"),
                    "policy_id": response.get("policy_id"),
                },
                include_in_llm_context=False,
            )
        elif response.get("type") == "error":
            await persist_system_message(
                db=db,
                investigation_id=investigation_id,
                user_id=user.user_id,
                content=f"Error: {response.get('message')}",
                metadata={
                    "type": "error",
                    "details": response.get("details"),
                },
                include_in_llm_context=False,
            )

    # Check if graph was mutated to add refresh signal
    graph_mutated = any(r.get("type") == "graph_mutated" for r in responses)
    graph_updated_signal = any(r.get("type") == "graph_updated" for r in responses)

    # For REST compatibility, return all responses as an array
    # The UI can process them sequentially
    if len(responses) == 0:
        return {"type": "error", "message": "No response from chat router"}
    elif len(responses) == 1:
        result = responses[0]
        # Add refresh hint if graph was mutated
        if graph_mutated or graph_updated_signal:
            result["refresh_graph"] = True
        return result
    else:
        result = {"type": "multi_response", "responses": responses}
        # Add refresh hint if graph was mutated
        if graph_mutated or graph_updated_signal:
            result["refresh_graph"] = True
        return result


@router.post("/policy/clarify")
async def provide_clarification(
    payload: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Provide clarification values for missing policy rules.

    Parameters
    ----------
    payload: dict[str, Any]
        The request body containing:
            - `investigation_id` (str or UUID): Identifier of the investigation.
            - `policy_id` (str): Name or identifier of the policy.
            - `question` (str): The original user question that requires clarification.
            - `rule_values` (dict[str, Any], optional): Mapping of rule names to their provided values.

    db: AsyncSession
        Asynchronous SQLAlchemy session injected by FastAPI's dependency system.

    user: User
        The authenticated user object injected by the `get_current_user` dependency.

    Returns
    -------
    dict
        A dictionary returned by :func:`handle_clarification_response`.  On success it contains the clarification result; on error it includes `type` set to `"error"` and a `message` field.

    Raises
    ------
    HTTPException
        * **400 Bad Request** - If required fields are missing, if access validation fails, or if the clarification handler returns an error.
        * **500 Internal Server Error** - For unexpected exceptions during processing.
    """
    investigation_id_str = payload.get("investigation_id")
    policy_id = payload.get("policy_id")
    question = payload.get("question")
    rule_values = payload.get("rule_values", {})

    if not all([investigation_id_str, policy_id, question]):
        raise HTTPException(
            status_code=400, detail="investigation_id, policy_id and question are required"
        )

    # Type assertions after validation
    investigation_id = UUID(str(investigation_id_str))
    question_str = str(question)
    policy_id_str = str(policy_id)

    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Use new chat router's clarification handler
    try:
        result = await handle_clarification_response(
            db=db,
            investigation_id=investigation_id,
            policy_id=policy_id_str,
            rule_values=rule_values,
            original_question=question_str,
            user_id=user.user_id,
        )

        # Check if result contains an error
        if result.get("type") == "error":
            error_msg = result.get("message", "Unknown error")
            logger.error(
                f"Clarification failed for investigation {investigation_id}, "
                f"policy {policy_id_str}: {error_msg}"
            )
            raise HTTPException(status_code=400, detail=error_msg)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in provide_clarification for investigation {investigation_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your clarification. Please try again.",
        )


# DEPRECATED: Graph mutations endpoint removed
# Graph mutations are no longer supported - use timeline entries instead
