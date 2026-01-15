from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional


class InvestigationCreate(BaseModel):
    """Schema for creating a new investigation."""
    title: str = Field(..., min_length=1, max_length=200)


class InvestigationRead(BaseModel):
    """Schema for reading investigation data (response)."""
    investigation_id: UUID
    title: str
    owner_user_id: Optional[int] = None
    parsing_locked: bool = False
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class InvestigationUpdate(BaseModel):
    """Schema for updating investigation metadata."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)


__all__ = ["InvestigationCreate", "InvestigationRead", "InvestigationUpdate"]
