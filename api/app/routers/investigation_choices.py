from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..deps import get_current_user
from ..models.user import User
from ..models.investigation_choice import InvestigationChoice as InvestigationChoiceModel
from ..crud import investigation_choice as crud
from ..schemas.investigation_choice import (
    InvestigationChoice,
    InvestigationChoicesResponse,
)

from ..utils.log_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/investigations", tags=["investigation_choices"])


@router.get("/{investigation_id}/choices", response_model=InvestigationChoicesResponse)
async def get_investigation_choices(
    investigation_id: UUID,
    include_selected: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve all investigation choices for a given investigation.

    Args:
        investigation_id (UUID): The unique identifier of the investigation whose choices are being requested.
        include_selected (bool, optional): If `True` (default), include choices that have already been selected; if `False`, exclude them.
        db (AsyncSession, optional): An asynchronous SQLAlchemy session provided by FastAPI's dependency injection.
        current_user (User, optional): The authenticated user making the request, injected via FastAPI dependencies.

    Returns:
        InvestigationChoicesResponse: A response object containing:
            - `choices`: A list of :class:`InvestigationChoice` Pydantic models representing each choice.
            - `total`: The total number of choices returned.
            - `job_id`: The job identifier associated with the first choice, or `0` if no choices exist.
            - `investigation_id`: Echoes the supplied investigation UUID.
    """
    choice_models: List[InvestigationChoiceModel] = (
        await crud.get_investigation_choices_by_investigation(
            db=db,
            investigation_id=investigation_id,
            include_selected=include_selected,
        )
    )

    # Convert SQLAlchemy models to Pydantic schemas
    choice_schemas = [InvestigationChoice.model_validate(c) for c in choice_models]

    # Get job_id from first choice if available
    first_job_id = choice_models[0].job_id if choice_models else 0

    return InvestigationChoicesResponse(
        choices=choice_schemas,
        total=len(choice_schemas),
        job_id=first_job_id,
        investigation_id=investigation_id,
    )


@router.post("/{investigation_id}/choices/{choice_id}/select")
async def select_investigation_choice(
    investigation_id: UUID,
    choice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Select an investigation choice and create a corresponding agent job.

    This endpoint validates the requested choice, ensures it belongs to the specified
    investigation and has not been selected before, then enqueues a new agent job
    using the suggestion stored in the choice. The choice is marked as selected and
    linked to the newly created job.

    Args:
        investigation_id (UUID): Identifier of the investigation to which the choice belongs.
        choice_id (int): Primary key of the `InvestigationChoiceModel` to be selected.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session injected by FastAPI's dependency system.
        current_user (User, optional): The authenticated user performing the operation,
            provided via dependency injection.

    Raises:
        HTTPException: If the choice does not exist (404), does not belong to the given
            investigation (400), or has already been selected (400).

    Returns:
        dict: A dictionary containing:
            - `success` (bool): Always `True` when the operation completes.
            - `job_id` (UUID): Identifier of the newly created agent job.
            - `choice_id` (int): The identifier of the choice that was selected.
            - `suggested_query` (str): The query text suggested by the choice.
            - `message` (str): Human-readable confirmation message including the choice title.
    """
    # Get the choice
    selected_choice: Optional[InvestigationChoiceModel] = await crud.get_investigation_choice(
        db=db, choice_id=choice_id
    )

    if selected_choice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Choice {choice_id} not found"
        )

    # Type narrowing - we know selected_choice is not None here
    assert selected_choice is not None

    if str(selected_choice.investigation_id) != str(investigation_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choice does not belong to this investigation",
        )

    if bool(selected_choice.selected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Choice has already been selected"
        )

    # Create a new agent job with the suggested query
    from ..crud.job import enqueue_agent_job

    # Extract values from SQLAlchemy model (these are actual Python values, not Column objects)
    effort: str = (
        selected_choice.suggested_effort
        if selected_choice.suggested_effort is not None
        else "medium"
    )
    suggested_query: str = selected_choice.suggested_query
    choice_title: str = selected_choice.title

    new_job = await enqueue_agent_job(
        db=db,
        investigation_id=investigation_id,
        user_id=current_user.user_id,
        policy_id="event_search",  # Default policy
        rule_values={"effort": effort},
        seed_instructions=suggested_query,
    )

    # Mark the choice as selected
    from ..schemas.investigation_choice import InvestigationChoiceUpdate

    await crud.update_investigation_choice(
        db=db,
        choice_id=choice_id,
        choice_update=InvestigationChoiceUpdate(
            selected=True,
            selected_job_id=new_job.job_id,
        ),
    )

    await db.commit()

    logger.info(
        f"User {current_user.user_id} selected choice {choice_id} "
        f"('{choice_title}'), created job {new_job.job_id}"
    )

    return {
        "success": True,
        "job_id": new_job.job_id,
        "choice_id": choice_id,
        "suggested_query": suggested_query,
        "message": f"Started investigation: {choice_title}",
    }


__all__ = ["router"]
