# api/tests/unit/routers/test_investigation_choices.py
import pytest
from httpx import AsyncClient

from app.models import User, Investigation, InvestigationChoice
from app.models.job_agent import AgentJob, JobStatus


@pytest.mark.asyncio
async def test_get_investigation_choices_empty(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test getting choices when none exist."""
    response = await async_client.get(
        f"/api/v1/investigations/{test_investigation.investigation_id}/choices",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["choices"] == []
    assert data["total"] == 0
    assert data["job_id"] == 0
    assert data["investigation_id"] == str(test_investigation.investigation_id)


@pytest.mark.asyncio
async def test_get_investigation_choices_with_data(
    async_client: AsyncClient,
    test_investigation: Investigation,
    test_user: User,
    auth_headers: dict,
    db_session
):
    """Test getting choices with existing data."""
    # Create a job first
    job = AgentJob(
        investigation_id=test_investigation.investigation_id,
        user_id=test_user.user_id,
        status=JobStatus.COMPLETED,
        policy_id="test_policy",
        seed_instructions="test"
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    
    # Create test choices
    choice1 = InvestigationChoice(
        investigation_id=test_investigation.investigation_id,
        job_id=job.job_id,
        title="Test Choice 1",
        description="Description 1",
        rationale="Rationale 1",
        suggested_query="query 1",
        suggested_effort="low",
        selected=False
    )
    choice2 = InvestigationChoice(
        investigation_id=test_investigation.investigation_id,
        job_id=job.job_id,
        title="Test Choice 2",
        description="Description 2",
        rationale="Rationale 2",
        suggested_query="query 2",
        suggested_effort="medium",
        selected=True
    )
    
    db_session.add_all([choice1, choice2])
    await db_session.commit()
    
    # Get all choices (including selected)
    response = await async_client.get(
        f"/api/v1/investigations/{test_investigation.investigation_id}/choices?include_selected=true",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["job_id"] == job.job_id


@pytest.mark.asyncio
async def test_select_nonexistent_choice(
    async_client: AsyncClient,
    test_investigation: Investigation,
    auth_headers: dict
):
    """Test selecting a choice that doesn't exist."""
    response = await async_client.post(
        f"/api/v1/investigations/{test_investigation.investigation_id}/choices/999999/select",
        headers=auth_headers
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
