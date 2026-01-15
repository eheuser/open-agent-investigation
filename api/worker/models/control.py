from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict


class TurnComplete(BaseModel):
    """Sent after each turn (max 5 tools)."""
    
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["turn_complete"] = "turn_complete"
    assistant_message: Dict[str, Any]
    tool_results: List[Dict[str, Any]] = []
    tools_executed: int = 0
    turn_number: int


class CancelMessage(BaseModel):
    """Cancel a running job."""
    
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["cancel"] = "cancel"
    job_id: int


class JobMessage(BaseModel):
    """Generic job message for queue."""
    
    model_config = ConfigDict(extra="allow")
    
    job_type: Literal["agent", "parsing"]
    job_id: int
    payload: Dict[str, Any]
