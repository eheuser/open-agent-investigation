from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional, Any, Dict


class JobRead(BaseModel):
    """Schema for reading job data (both parsing and agent jobs)."""
    job_id: int
    investigation_id: UUID
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class ParsingJobRead(JobRead):
    """Schema for reading parsing job data."""
    artifact_id: int


class AgentJobRead(JobRead):
    """Schema for reading agent job data."""
    policy_id: str
    rule_values: Dict[str, Any]
    seed_instructions: str


class JobStatusUpdate(BaseModel):
    """Schema for updating job status (internal use)."""
    status: str = Field(..., pattern="^(pending|running|completed|failed)$")
    error_message: Optional[str] = None


__all__ = [
    "JobRead",
    "ParsingJobRead",
    "AgentJobRead",
    "JobStatusUpdate",
]
