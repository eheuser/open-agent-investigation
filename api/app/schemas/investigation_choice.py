from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from uuid import UUID


class InvestigationChoiceBase(BaseModel):
    """Base schema for investigation choices."""
    title: str = Field(..., description="Short title for the suggested path")
    description: str = Field(..., description="Detailed description of what this choice will investigate")
    rationale: str = Field(..., description="Why the agent suggests this path")
    suggested_query: str = Field(..., description="The question/query to execute")
    suggested_effort: str = Field(default="medium", description="Effort level (low, medium, high)")
    tool_suggestions: Optional[Dict[str, Any]] = Field(None, description="Optional tool hints")
    display_order: int = Field(default=0, description="Display order (lower = higher priority)")


class InvestigationChoiceCreate(InvestigationChoiceBase):
    """Schema for creating a new investigation choice."""
    job_id: int = Field(..., description="Parent agent job ID")
    investigation_id: UUID = Field(..., description="Investigation ID")


class InvestigationChoiceUpdate(BaseModel):
    """Schema for updating an investigation choice (selection)."""
    selected: bool = Field(..., description="Whether the choice was selected")
    selected_job_id: Optional[int] = Field(None, description="Job ID created from this choice")


class InvestigationChoice(InvestigationChoiceBase):
    """Full investigation choice schema with all fields."""
    choice_id: int
    job_id: int
    investigation_id: UUID
    selected: bool
    selected_at: Optional[datetime] = None
    selected_job_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class InvestigationChoicesResponse(BaseModel):
    """Response schema for multiple choices."""
    choices: List[InvestigationChoice] = Field(..., description="List of suggested investigation paths")
    total: int = Field(..., description="Total number of choices")
    job_id: int = Field(..., description="Parent job ID")
    investigation_id: UUID = Field(..., description="Investigation ID")


__all__ = [
    "InvestigationChoiceBase",
    "InvestigationChoiceCreate",
    "InvestigationChoiceUpdate",
    "InvestigationChoice",
    "InvestigationChoicesResponse",
]
