# api/app/schemas/playbook.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PlaybookBase(BaseModel):
    """Base playbook schema."""
    name: str = Field(..., min_length=1, max_length=200, description="Playbook name (e.g., 'lateral_movement')")
    description: str = Field(..., min_length=1, max_length=1000, description="Brief description of investigation strategy")
    playbook: str = Field(..., min_length=1, description="Markdown playbook content with investigation steps")


class PlaybookCreate(PlaybookBase):
    """Schema for creating a new user playbook."""
    is_enabled: bool = Field(default=True, description="Whether playbook is enabled by default")


class PlaybookUpdate(BaseModel):
    """Schema for updating an existing user playbook."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=1000)
    playbook: Optional[str] = Field(None, min_length=1)
    is_enabled: Optional[bool] = None


class PlaybookResponse(PlaybookBase):
    """Schema for playbook responses."""
    playbook_id: int
    user_id: int
    is_enabled: bool
    is_base: bool = Field(default=False, description="True for immutable YAML playbooks")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class BasePlaybookResponse(BaseModel):
    """Schema for base (YAML) playbook responses."""
    name: str
    description: str
    playbook: str
    is_base: bool = Field(default=True, description="Always true for YAML playbooks")


class InvestigationPlaybookCreate(BaseModel):
    """Schema for enabling a playbook for an investigation."""
    playbook_id: int
    is_enabled: bool = Field(default=True)


class InvestigationPlaybookResponse(BaseModel):
    """Schema for investigation-playbook relationship."""
    id: int
    investigation_id: str
    playbook_id: int
    is_enabled: bool
    enabled_at: datetime
    playbook: PlaybookResponse
    
    class Config:
        from_attributes = True


class PlaybookListResponse(BaseModel):
    """Combined list of base and user playbooks."""
    base_playbooks: List[BasePlaybookResponse]
    user_playbooks: List[PlaybookResponse]
    total: int
