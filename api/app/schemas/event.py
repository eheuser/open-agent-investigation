from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any, Dict, List


class EventRead(BaseModel):
    """Schema for reading event data."""
    event_id: int
    event_ts: datetime
    artifact_id: Optional[int] = None
    event_type: str
    payload: Dict[str, Any]
    created_at: datetime


class EventListResponse(BaseModel):
    """Schema for paginated event list."""
    events: List[Dict[str, Any]]
    count: int
    total: Optional[int] = None


class EventPasteRequest(BaseModel):
    """Schema for pasting raw event data."""
    investigation_id: str
    payload: str = Field(..., description="Raw CSV/JSON/YAML event data")
    format_hint: Optional[str] = Field(None, description="Optional format hint: json, yaml, csv")


class EventPasteResponse(BaseModel):
    """Schema for paste operation response."""
    status: str
    inserted: int
    message: Optional[str] = None


__all__ = [
    "EventRead",
    "EventListResponse",
    "EventPasteRequest",
    "EventPasteResponse",
]
