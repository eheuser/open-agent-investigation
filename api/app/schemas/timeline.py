from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class EntryType(str, Enum):
    """Timeline entry types."""
    EVENT = "event"
    FINDING = "finding"
    NOTE = "note"
    OBSERVATION = "observation"


class TimelineEntryCreate(BaseModel):
    """Schema for creating a timeline entry."""
    event_id: Optional[int] = Field(None, description="Reference to source event (if applicable)")
    timestamp: datetime = Field(..., description="When this evidence occurred")
    entry_type: EntryType = Field(..., description="Type of timeline entry")
    title: str = Field(..., min_length=1, max_length=500, description="Brief title for the entry")
    description: Optional[str] = Field(None, description="Detailed description")
    data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional structured data")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")
    is_visible: bool = Field(True, description="Whether entry is visible in timeline")


class TimelineEntryUpdate(BaseModel):
    """Schema for updating a timeline entry (partial update)."""
    timestamp: Optional[datetime] = None
    entry_type: Optional[EntryType] = None
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    is_visible: Optional[bool] = None


class TimelineEntryRead(BaseModel):
    """Schema for reading a timeline entry."""
    entry_id: int
    investigation_id: str
    event_id: Optional[int]
    timestamp: datetime
    entry_type: str
    title: str
    description: Optional[str]
    data: Dict[str, Any]
    tags: List[str]
    created_by_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    is_visible: bool
    notes: Optional[List['TimelineNoteRead']] = Field(default_factory=list, description="User notes on this entry")

    class Config:
        from_attributes = True


class TimelineNoteCreate(BaseModel):
    """Schema for creating a note on a timeline entry."""
    note_text: str = Field(..., min_length=1, description="Note content")


class TimelineNoteUpdate(BaseModel):
    """Schema for updating a note."""
    note_text: str = Field(..., min_length=1, description="Updated note content")


class TimelineNoteRead(BaseModel):
    """Schema for reading a timeline note."""
    note_id: int
    entry_id: int
    user_id: int
    note_text: str
    created_at: datetime
    updated_at: datetime
    username: Optional[str] = Field(None, description="Username who created the note")

    class Config:
        from_attributes = True


class TimelineResponse(BaseModel):
    """Complete timeline response with all entries."""
    entries: List[TimelineEntryRead]
    total: int
    limit: int
    offset: int


class TimelineStatsResponse(BaseModel):
    """Timeline statistics."""
    total_entries: int
    entries_by_type: Dict[str, int]
    date_range: Dict[str, Optional[datetime]]
    tags: List[str]
    total_notes: int


# Update forward references
TimelineEntryRead.model_rebuild()
