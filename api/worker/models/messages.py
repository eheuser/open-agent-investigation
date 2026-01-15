from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class MessageBase(BaseModel):
    """Base message model."""
    
    model_config = ConfigDict(extra="forbid")
    
    role: str
    content: Optional[str] = None


class SystemMessage(BaseModel):
    """System message with instructions."""
    
    model_config = ConfigDict(extra="forbid")
    
    role: Literal["system"] = "system"
    content: str = Field(..., description="System message content")


class UserMessage(BaseModel):
    """User message with question."""
    
    model_config = ConfigDict(extra="forbid")
    
    role: Literal["user"] = "user"
    content: str = Field(..., description="User message content")


class ToolCall(BaseModel):
    """Tool call from LLM."""
    
    model_config = ConfigDict(extra="forbid")
    
    id: Optional[str] = None
    type: Literal["function"] = "function"
    function: Dict[str, Any] = Field(
        default_factory=dict,
        description="Function name and arguments"
    )


class AssistantMessage(MessageBase):
    """Assistant message with optional tool calls."""
    
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class ToolMessage(BaseModel):
    """Tool execution result message."""
    
    model_config = ConfigDict(extra="forbid")
    
    role: Literal["tool"] = "tool"
    tool_call_id: str
    name: str
    content: str = Field(..., description="Tool result content")


class ToolResult(BaseModel):
    """Result from tool execution."""
    
    model_config = ConfigDict(extra="forbid")
    
    status: Literal["ok", "error"]
    result: Any = None
    error_msg: Optional[str] = None
