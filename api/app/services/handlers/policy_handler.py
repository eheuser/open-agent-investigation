from typing import Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from ..policy_router import route_question


async def handle_policy_execution(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
    effort: str = "medium",
) -> Dict[str, Any]:
    """
    Handles a user’s complex policy-related query by delegating to the existing `policy_router` workflow.

    The function forwards the request to :func:`route_question`, which performs:
    - Selection of an appropriate policy using a language model.
    - Clarification of any ambiguous rules.
    - Queuing of a policy-driven agent job for asynchronous execution.

    Parameters
    ----------
    db: AsyncSession
        An active asynchronous database session used by `route_question` for data access and persistence.
    investigation_id: UUID
        The unique identifier of the investigation to which the query belongs.
    user_query: str
        The raw textual request submitted by the user, potentially containing multiple analysis steps or policy references.
    user_id: int
        Identifier of the requesting user; recorded for auditing and permission checks.
    effort: str, optional
        Desired level of computational effort (e.g., `"low"`, `"medium"`, `"high"`). Defaults to `"medium"`.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing either:
        - `{"job_queued": <job_id>}` when the request has been successfully scheduled for processing, or
        - `{"clarification_request": <details>}` if additional information is required before proceeding.

    Raises
    ------
    Any exception propagated from :func:`route_question`, such as database errors or validation failures.
    """
    result = await route_question(
        db=db,
        investigation_id=investigation_id,
        question=user_query,
        user_id=user_id,
        effort=effort,
    )

    return result


__all__ = ["handle_policy_execution"]
