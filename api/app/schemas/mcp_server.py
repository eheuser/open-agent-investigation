from pydantic import BaseModel, Field, ConfigDict, HttpUrl
from datetime import datetime
from typing import Optional, List


class MCPServerCreate(BaseModel):
    """Schema for creating a new MCP server."""
    name: str = Field(..., min_length=1, max_length=100)
    base_url: str = Field(..., description="HTTP endpoint of the MCP server")
    auth_token: Optional[str] = None
    allowed_agents: List[str] = Field(default_factory=list)


class MCPServerUpdate(BaseModel):
    """Schema for updating MCP server (partial updates)."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    base_url: Optional[str] = None
    auth_token: Optional[str] = None
    allowed_agents: Optional[List[str]] = None


class MCPServerRead(BaseModel):
    """Schema for reading MCP server data (response)."""
    server_id: int
    name: str
    base_url: str
    auth_token: Optional[str] = None
    allowed_agents: List[str]
    owner_user_id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


__all__ = ["MCPServerCreate", "MCPServerUpdate", "MCPServerRead"]
