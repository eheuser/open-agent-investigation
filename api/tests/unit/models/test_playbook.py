# api/tests/unit/models/test_playbook.py
import pytest
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Playbook, InvestigationPlaybook, User, Investigation


@pytest.mark.asyncio
async def test_create_playbook(db_session: AsyncSession, test_user: User):
    """Test creating a new playbook."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test playbook description",
        playbook="## Test Playbook\n\n### Steps\n1. Step 1\n2. Step 2",
        is_enabled=True,
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    assert playbook.playbook_id is not None
    assert playbook.user_id == test_user.user_id
    assert playbook.name == "test_playbook"
    assert playbook.description == "Test playbook description"
    assert playbook.is_enabled == True  # type: ignore
    assert playbook.created_at is not None
    assert playbook.updated_at is not None


@pytest.mark.asyncio
async def test_playbook_name_not_empty_constraint(db_session: AsyncSession, test_user: User):
    """Test that playbook name cannot be empty."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="",
        description="Test description",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    
    with pytest.raises(Exception):  # Should raise constraint violation
        await db_session.commit()
    
    await db_session.rollback()


@pytest.mark.asyncio
async def test_playbook_description_not_empty_constraint(db_session: AsyncSession, test_user: User):
    """Test that playbook description cannot be empty."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    
    with pytest.raises(Exception):  # Should raise constraint violation
        await db_session.commit()
    
    await db_session.rollback()


@pytest.mark.asyncio
async def test_playbook_content_not_empty_constraint(db_session: AsyncSession, test_user: User):
    """Test that playbook content cannot be empty."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="",
    )
    
    db_session.add(playbook)
    
    with pytest.raises(Exception):  # Should raise constraint violation
        await db_session.commit()
    
    await db_session.rollback()


@pytest.mark.asyncio
async def test_playbook_cascade_delete_on_user(db_session: AsyncSession, test_user: User):
    """Test that playbooks are deleted when user is deleted."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    await db_session.commit()
    playbook_id = playbook.playbook_id
    
    # Delete user
    await db_session.delete(test_user)
    await db_session.commit()
    
    # Verify playbook was deleted
    result = await db_session.execute(
        select(Playbook).where(Playbook.playbook_id == playbook_id)
    )
    deleted_playbook = result.scalar_one_or_none()
    
    assert deleted_playbook is None


@pytest.mark.asyncio
async def test_update_playbook(db_session: AsyncSession, test_user: User):
    """Test updating a playbook."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Original description",
        playbook="Original content",
        is_enabled=True,
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    original_created_at = playbook.created_at
    
    # Update playbook
    playbook.description = "Updated description"  # type: ignore
    playbook.is_enabled = False  # type: ignore
    
    await db_session.commit()
    await db_session.refresh(playbook)
    
    assert playbook.description == "Updated description"
    assert playbook.is_enabled == False  # type: ignore
    assert playbook.created_at == original_created_at
    assert playbook.updated_at > original_created_at


@pytest.mark.asyncio
async def test_create_investigation_playbook(
    db_session: AsyncSession, 
    test_user: User, 
    test_investigation: Investigation
):
    """Test creating an investigation-playbook relationship."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Create relationship
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
        is_enabled=True,
    )
    
    db_session.add(inv_playbook)
    await db_session.commit()
    await db_session.refresh(inv_playbook)
    
    assert inv_playbook.id is not None
    assert inv_playbook.investigation_id == test_investigation.investigation_id
    assert inv_playbook.playbook_id == playbook.playbook_id
    assert inv_playbook.is_enabled == True  # type: ignore
    assert inv_playbook.enabled_at is not None


@pytest.mark.asyncio
async def test_investigation_playbook_unique_constraint(
    db_session: AsyncSession,
    test_user: User,
    test_investigation: Investigation
):
    """Test that the same playbook cannot be added twice to an investigation."""
    from sqlalchemy.exc import IntegrityError
    
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Create first relationship
    inv_playbook1 = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
        is_enabled=True,
    )
    
    db_session.add(inv_playbook1)
    await db_session.commit()
    
    # Try to create duplicate
    inv_playbook2 = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
        is_enabled=True,
    )
    
    db_session.add(inv_playbook2)
    
    with pytest.raises(IntegrityError):
        await db_session.commit()
    
    await db_session.rollback()


@pytest.mark.asyncio
async def test_investigation_playbook_cascade_delete_on_investigation(
    db_session: AsyncSession,
    test_user: User,
    test_investigation: Investigation
):
    """Test that investigation-playbook relationships are deleted when investigation is deleted."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Create relationship
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
        is_enabled=True,
    )
    
    db_session.add(inv_playbook)
    await db_session.commit()
    relationship_id = inv_playbook.id
    
    # Delete investigation
    await db_session.delete(test_investigation)
    await db_session.commit()
    
    # Verify relationship was deleted
    result = await db_session.execute(
        select(InvestigationPlaybook).where(InvestigationPlaybook.id == relationship_id)
    )
    deleted_relationship = result.scalar_one_or_none()
    
    assert deleted_relationship is None


@pytest.mark.asyncio
async def test_investigation_playbook_cascade_delete_on_playbook(
    db_session: AsyncSession,
    test_user: User,
    test_investigation: Investigation
):
    """Test that investigation-playbook relationships are deleted when playbook is deleted."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Create relationship
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
        is_enabled=True,
    )
    
    db_session.add(inv_playbook)
    await db_session.commit()
    relationship_id = inv_playbook.id
    
    # Delete playbook
    await db_session.delete(playbook)
    await db_session.commit()
    
    # Verify relationship was deleted
    result = await db_session.execute(
        select(InvestigationPlaybook).where(InvestigationPlaybook.id == relationship_id)
    )
    deleted_relationship = result.scalar_one_or_none()
    
    assert deleted_relationship is None


@pytest.mark.asyncio
async def test_playbook_relationships(db_session: AsyncSession, test_user: User):
    """Test playbook relationships with user."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test_playbook",
        description="Test description",
        playbook="Test content",
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    # Verify relationship
    result = await db_session.execute(
        select(User).where(User.user_id == test_user.user_id)
    )
    user = result.scalar_one()
    
    assert user is not None
    # Note: Accessing relationships requires proper session handling
    # This test verifies the foreign key constraint works
    assert playbook.user_id == user.user_id


@pytest.mark.asyncio
async def test_playbook_default_values(db_session: AsyncSession, test_user: User):
    """Test that playbook has correct default values."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test",
        description="Test",
        playbook="Content",
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    assert playbook.is_enabled == True  # type: ignore
    assert playbook.created_at is not None
    assert playbook.updated_at is not None


@pytest.mark.asyncio
async def test_multiple_playbooks_same_user(db_session: AsyncSession, test_user: User):
    """Test that a user can have multiple playbooks."""
    playbook1 = Playbook(
        user_id=test_user.user_id,
        name="playbook_1",
        description="First",
        playbook="Content 1",
    )
    playbook2 = Playbook(
        user_id=test_user.user_id,
        name="playbook_2",
        description="Second",
        playbook="Content 2",
    )
    
    db_session.add_all([playbook1, playbook2])
    await db_session.commit()
    
    # Query all playbooks for user
    result = await db_session.execute(
        select(Playbook).where(Playbook.user_id == test_user.user_id)
    )
    playbooks = result.scalars().all()
    
    assert len(playbooks) == 2
    names = {pb.name for pb in playbooks}
    assert names == {"playbook_1", "playbook_2"}


@pytest.mark.asyncio
async def test_investigation_playbook_default_enabled(db_session: AsyncSession, test_user: User, test_investigation: Investigation):
    """Test that investigation playbook is enabled by default."""
    playbook = Playbook(
        user_id=test_user.user_id,
        name="test",
        description="Test",
        playbook="Content",
    )
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    inv_playbook = InvestigationPlaybook(
        investigation_id=test_investigation.investigation_id,
        playbook_id=playbook.playbook_id,
    )
    
    db_session.add(inv_playbook)
    await db_session.commit()
    await db_session.refresh(inv_playbook)
    
    assert inv_playbook.is_enabled == True  # type: ignore


@pytest.mark.asyncio
async def test_playbook_long_content(db_session: AsyncSession, test_user: User):
    """Test creating a playbook with long content."""
    long_content = "## Playbook\n\n" + ("Step\n" * 1000)
    
    playbook = Playbook(
        user_id=test_user.user_id,
        name="long_playbook",
        description="Playbook with long content",
        playbook=long_content,
    )
    
    db_session.add(playbook)
    await db_session.commit()
    await db_session.refresh(playbook)
    
    assert len(playbook.playbook) > 5000
    assert playbook.playbook == long_content
