# api/app/routers/playbooks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List
import uuid

from app.core.database import get_db
from app.deps import get_current_user
from app.models import User, Playbook, Investigation, InvestigationPlaybook
from app.schemas.playbook import (
    PlaybookCreate,
    PlaybookUpdate,
    PlaybookResponse,
    BasePlaybookResponse,
    PlaybookListResponse,
    InvestigationPlaybookCreate,
    InvestigationPlaybookResponse,
)
from worker.agents.playbooks import get_playbook_registry

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])


@router.get("/list", response_model=PlaybookListResponse)
async def list_all_playbooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all playbooks (base + user-created).
    
    Base playbooks are loaded from YAML files (immutable).
    User playbooks are stored in the database (mutable).
    """
    # Get base playbooks from YAML files
    registry = get_playbook_registry()
    base_playbooks = [
        BasePlaybookResponse(
            name=pb.name,
            description=pb.description,
            playbook=pb.playbook,
            is_base=True,
        )
        for pb in registry.playbooks
    ]
    
    # Get user playbooks from database
    result = await db.execute(
        select(Playbook).where(Playbook.user_id == current_user.user_id)
    )
    user_playbooks_db = result.scalars().all()
    
    user_playbooks = [
        PlaybookResponse.model_validate({
            **pb.__dict__,
            'is_base': False
        })
        for pb in user_playbooks_db
    ]
    
    return PlaybookListResponse(
        base_playbooks=base_playbooks,
        user_playbooks=user_playbooks,
        total=len(base_playbooks) + len(user_playbooks),
    )


@router.get("/user", response_model=List[PlaybookResponse])
async def list_user_playbooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all user-created playbooks."""
    result = await db.execute(
        select(Playbook).where(Playbook.user_id == current_user.user_id)
    )
    playbooks = result.scalars().all()
    
    return [
        PlaybookResponse.model_validate({
            **pb.__dict__,
            'is_base': False
        })
        for pb in playbooks
    ]


@router.get("/base", response_model=List[BasePlaybookResponse])
async def list_base_playbooks():
    """Get all base (YAML) playbooks."""
    registry = get_playbook_registry()
    
    return [
        BasePlaybookResponse(
            name=pb.name,
            description=pb.description,
            playbook=pb.playbook,
            is_base=True,
        )
        for pb in registry.playbooks
    ]


@router.post("/create", response_model=PlaybookResponse, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    data: PlaybookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new user playbook."""
    # Check if name already exists for this user
    result = await db.execute(
        select(Playbook).where(
            and_(
                Playbook.user_id == current_user.user_id,
                Playbook.name == data.name,
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Playbook with name '{data.name}' already exists",
        )
    
    # Create new playbook
    playbook = Playbook(
        user_id=current_user.user_id,
        name=data.name,
        description=data.description,
        playbook=data.playbook,
        is_enabled=data.is_enabled,
    )
    
    db.add(playbook)
    await db.commit()
    await db.refresh(playbook)
    
    return PlaybookResponse.model_validate({
        **playbook.__dict__,
        'is_base': False
    })


@router.put("/{playbook_id}", response_model=PlaybookResponse)
async def update_playbook(
    playbook_id: int,
    data: PlaybookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing user playbook."""
    # Get playbook
    result = await db.execute(
        select(Playbook).where(
            and_(
                Playbook.playbook_id == playbook_id,
                Playbook.user_id == current_user.user_id,
            )
        )
    )
    playbook = result.scalar_one_or_none()
    
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )
    
    # Update fields
    if data.name is not None:
        # Check for name conflict
        result = await db.execute(
            select(Playbook).where(
                and_(
                    Playbook.user_id == current_user.user_id,
                    Playbook.name == data.name,
                    Playbook.playbook_id != playbook_id,
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Playbook with name '{data.name}' already exists",
            )
        
        playbook.name = data.name  # type: ignore
    
    if data.description is not None:
        playbook.description = data.description  # type: ignore
    
    if data.playbook is not None:
        playbook.playbook = data.playbook  # type: ignore
    
    if data.is_enabled is not None:
        playbook.is_enabled = data.is_enabled  # type: ignore
    
    await db.commit()
    await db.refresh(playbook)
    
    return PlaybookResponse.model_validate({
        **playbook.__dict__,
        'is_base': False
    })


@router.delete("/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a user playbook."""
    # Get playbook
    result = await db.execute(
        select(Playbook).where(
            and_(
                Playbook.playbook_id == playbook_id,
                Playbook.user_id == current_user.user_id,
            )
        )
    )
    playbook = result.scalar_one_or_none()
    
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )
    
    await db.delete(playbook)
    await db.commit()


@router.post("/clone/{source_name}", response_model=PlaybookResponse, status_code=status.HTTP_201_CREATED)
async def clone_playbook(
    source_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clone a base playbook to user playbooks.
    
    Creates a mutable copy of an immutable base playbook.
    """
    # Get base playbook from YAML registry
    registry = get_playbook_registry()
    base_playbook = registry.get_playbook_by_name(source_name)
    
    if not base_playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Base playbook '{source_name}' not found",
        )
    
    # Generate unique name for clone
    clone_name = f"{source_name}_copy"
    counter = 1
    
    while True:
        result = await db.execute(
            select(Playbook).where(
                and_(
                    Playbook.user_id == current_user.user_id,
                    Playbook.name == clone_name,
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            break
        
        counter += 1
        clone_name = f"{source_name}_copy_{counter}"
    
    # Create cloned playbook
    playbook = Playbook(
        user_id=current_user.user_id,
        name=clone_name,
        description=base_playbook.description,
        playbook=base_playbook.playbook,
        is_enabled=True,
    )
    
    db.add(playbook)
    await db.commit()
    await db.refresh(playbook)
    
    return PlaybookResponse.model_validate({
        **playbook.__dict__,
        'is_base': False
    })


@router.get("/investigation/{investigation_id}", response_model=List[InvestigationPlaybookResponse])
async def get_investigation_playbooks(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all playbooks enabled for an investigation.
    
    Returns both base playbooks (always enabled) and user playbooks (if enabled).
    """
    # Verify investigation exists and user has access
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid investigation ID format",
        )
    
    result = await db.execute(
        select(Investigation).where(Investigation.investigation_id == inv_uuid)
    )
    investigation = result.scalar_one_or_none()
    
    if not investigation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found",
        )
    
    # Get enabled user playbooks for this investigation
    result = await db.execute(
        select(InvestigationPlaybook)
        .where(InvestigationPlaybook.investigation_id == inv_uuid)
        .join(Playbook)
    )
    investigation_playbooks = result.scalars().all()
    
    # Convert to response format
    responses = []
    for ip in investigation_playbooks:
        playbook = await db.get(Playbook, ip.playbook_id)
        if playbook:
            responses.append(
                InvestigationPlaybookResponse(
                    id=ip.id,  # type: ignore
                    investigation_id=str(ip.investigation_id),
                    playbook_id=ip.playbook_id,  # type: ignore
                    is_enabled=ip.is_enabled,  # type: ignore
                    enabled_at=ip.enabled_at,  # type: ignore
                    playbook=PlaybookResponse.model_validate({
                        **playbook.__dict__,
                        'is_base': False
                    }),
                )
            )
    
    return responses


@router.post("/investigation/{investigation_id}/enable", status_code=status.HTTP_201_CREATED)
async def enable_playbook_for_investigation(
    investigation_id: str,
    data: InvestigationPlaybookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enable a user playbook for an investigation."""
    # Verify investigation exists
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid investigation ID format",
        )
    
    result = await db.execute(
        select(Investigation).where(Investigation.investigation_id == inv_uuid)
    )
    investigation = result.scalar_one_or_none()
    
    if not investigation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found",
        )
    
    # Verify playbook exists and belongs to user
    result = await db.execute(
        select(Playbook).where(
            and_(
                Playbook.playbook_id == data.playbook_id,
                Playbook.user_id == current_user.user_id,
            )
        )
    )
    playbook = result.scalar_one_or_none()
    
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )
    
    # Check if already enabled
    result = await db.execute(
        select(InvestigationPlaybook).where(
            and_(
                InvestigationPlaybook.investigation_id == inv_uuid,
                InvestigationPlaybook.playbook_id == data.playbook_id,
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Update is_enabled
        existing.is_enabled = data.is_enabled  # type: ignore
        await db.commit()
        return {"message": "Playbook status updated"}
    
    # Create new relationship
    investigation_playbook = InvestigationPlaybook(
        investigation_id=inv_uuid,
        playbook_id=data.playbook_id,
        is_enabled=data.is_enabled,
    )
    
    db.add(investigation_playbook)
    await db.commit()
    
    return {"message": "Playbook enabled for investigation"}


@router.delete("/investigation/{investigation_id}/disable/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_playbook_for_investigation(
    investigation_id: str,
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disable a user playbook for an investigation."""
    # Verify investigation exists
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid investigation ID format",
        )
    
    # Get relationship
    result = await db.execute(
        select(InvestigationPlaybook).where(
            and_(
                InvestigationPlaybook.investigation_id == inv_uuid,
                InvestigationPlaybook.playbook_id == playbook_id,
            )
        )
    )
    investigation_playbook = result.scalar_one_or_none()
    
    if not investigation_playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not enabled for this investigation",
        )
    
    # Set to disabled (don't delete, preserve history)
    investigation_playbook.is_enabled = False  # type: ignore
    await db.commit()
