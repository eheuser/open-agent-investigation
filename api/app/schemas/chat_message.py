from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from enum import Enum
from uuid import UUID
from datetime import datetime


class IntentType(str, Enum):
    """Classification of user query intent."""

    INSERT_EVENTS = "insert_events"
    QUERY_KG = "query_knowledge_graph"
    MUTATE_KG = "mutate_knowledge_graph"
    EXECUTE_POLICY = "execute_agent_policy"
    GENERAL_CHAT = "general_chat"
    TIMELINE_QUERY = "timeline_query"
    RAG_QUERY = "rag_query"  # RAG-based query with vector search


class MessageType(str, Enum):
    """Types of chat messages."""

    QUESTION = "question"  # User question
    ASSISTANT_ANSWER = "assistant_answer"  # General chat response
    TIMELINE_QUERY = "timeline_query"  # Timeline-specific query response
    AGENT_CHAT = "agent_chat"  # Full agent loop with tools
    TOOL_EXECUTION = "tool_execution"  # Individual tool execution (child of agent_chat)
    SUMMARY = "summary"  # Investigation summary
    ERROR = "error"  # Error message
    SYSTEM = "system"  # Internal system message (not shown in UI)


class AgentEffort(str, Enum):
    """Agent effort levels controlling max iterations."""

    LOW = "low"  # 5 iterations
    MEDIUM = "medium"  # 15 iterations
    HIGH = "high"  # 30 iterations

    @property
    def max_iterations(self) -> int:
        """
        Return the maximum number of iterations allowed for the current difficulty level.

        The method looks up the integer value associated with the instance's `value` attribute in a predefined mapping:
        - `"low"` → 5
        - `"medium"` → 15
        - `"high"` → 30

        Returns:
            int: The maximum iteration count corresponding to the object's difficulty setting.
        """
        return {"low": 5, "medium": 15, "high": 30}[self.value]


class RouterMode(str, Enum):
    """Router mode for query routing."""

    AUTO = "auto"  # Automatic intent classification (default)
    AGENT = "agent"  # Force agent-only execution
    RAG = "rag"  # Force RAG-only execution


class QuestionMessage(BaseModel):
    """User asks a question."""

    type: Literal["question"] = "question"
    text: str = Field(..., description="User's natural language query")
    effort: Optional[str] = Field("medium", description="Agent effort level: low, medium, high")
    router_mode: Optional[str] = Field("auto", description="Router mode: auto, agent, rag")


class ClarificationResponseMessage(BaseModel):
    """User provides clarification for policy rules."""

    type: Literal["clarification_response"] = "clarification_response"
    policy_id: str
    rule_values: Dict[str, Any]


class ConfirmMutationMessage(BaseModel):
    """User confirms or rejects a graph mutation preview."""

    type: Literal["confirm_mutation"] = "confirm_mutation"
    mutation_id: str
    confirmed: bool


class IntentClassifiedMessage(BaseModel):
    """Intent classification result."""

    type: Literal["intent_classified"] = "intent_classified"
    intent: IntentType
    confidence: float = 1.0


class AnswerChunkMessage(BaseModel):
    """Streaming answer chunk (for KG queries)."""

    type: Literal["answer_chunk"] = "answer_chunk"
    content: str
    chunk_id: int = 0
    is_final: bool = False


class EventsInsertedMessage(BaseModel):
    """Confirmation of event insertion."""

    type: Literal["events_inserted"] = "events_inserted"
    count: int
    message: str


class MutationPreviewMessage(BaseModel):
    """Preview of proposed graph mutations."""

    type: Literal["mutation_preview"] = "mutation_preview"
    mutation_id: str
    changes: Dict[str, Any]
    requires_confirmation: bool = True


class GraphMutatedMessage(BaseModel):
    """Confirmation of graph mutation."""

    type: Literal["graph_mutated"] = "graph_mutated"
    changes: Dict[str, Any]
    message: str


class JobQueuedMessage(BaseModel):
    """Agent job queued for processing."""

    type: Literal["job_queued"] = "job_queued"
    job_id: int
    policy_id: str
    policy_title: Optional[str] = None
    estimated_duration: Optional[str] = None
    message: str


class ClarificationRequestMessage(BaseModel):
    """Request for missing policy rule values."""

    type: Literal["clarification_request"] = "clarification_request"
    policy_id: str
    policy_title: str
    missing_rules: List[Dict[str, Any]]
    message: str


class ErrorMessage(BaseModel):
    """Error notification."""

    type: Literal["error"] = "error"
    message: str
    details: Optional[str] = None


class ProgressUpdateMessage(BaseModel):
    """Job progress update."""

    type: Literal["progress_update"] = "progress_update"
    job_id: int
    progress: float  # 0.0 to 1.0
    message: str


class GraphUpdateMessage(BaseModel):
    """Knowledge graph update notification."""

    type: Literal["graph_update"] = "graph_update"
    investigation_id: str
    nodes_added: int = 0
    edges_added: int = 0
    nodes_updated: int = 0


class ClassificationResult(BaseModel):
    """Internal model for intent classification."""

    intent: IntentType
    confidence: float = 1.0
    reasoning: str = ""


class ChatMessageCreate(BaseModel):
    """Schema for creating a chat message."""

    role: str = Field(..., description="OpenAI role: system, user, assistant, tool")
    message_type: Optional[str] = Field(
        None, description="Message type: question, assistant_answer, agent_chat, etc."
    )
    content: Optional[str] = Field(None, description="Message content")
    name: Optional[str] = Field(None, description="Optional name for function/tool messages")
    tool_calls: Optional[Dict[str, Any]] = Field(None, description="Tool calls array")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID for tool responses")
    parent_message_id: Optional[int] = Field(None, description="Parent message ID for threading")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )
    include_in_llm_context: bool = Field(True, description="Whether to include in LLM calls")
    visible_in_ui: bool = Field(True, description="Whether to show in UI")


class ChatMessageResponse(BaseModel):
    """Schema for chat message response."""

    message_id: int
    investigation_id: UUID
    user_id: int
    role: str
    message_type: Optional[str]
    content: Optional[str]
    name: Optional[str]
    tool_calls: Optional[Dict[str, Any]]
    tool_call_id: Optional[str]
    parent_message_id: Optional[int]
    metadata: Optional[Dict[str, Any]]  # Use 'metadata' not 'message_metadata' for API
    tool_executions: Optional[List[Dict[str, Any]]] = None  # Joined tool executions
    include_in_llm_context: bool
    visible_in_ui: bool
    deleted_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """Schema for chat history list response."""

    messages: List[ChatMessageResponse]
    total_count: int
    llm_context_count: int


class ToolExecutionCreate(BaseModel):
    """Schema for creating a tool execution."""

    chat_message_id: int
    tool_name: str
    display_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    execution_number: Optional[int] = None
    max_tools: Optional[int] = None


class ToolExecutionUpdate(BaseModel):
    """Schema for updating a tool execution."""

    result: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    status: Optional[str] = None  # executing, completed, failed


class ToolExecutionResponse(BaseModel):
    """Schema for tool execution response."""

    execution_id: int
    chat_message_id: int
    tool_name: str
    display_name: Optional[str]
    arguments: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    result_summary: Optional[str]
    status: str
    execution_number: Optional[int]
    max_tools: Optional[int]
    started_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class OpenAIMessage(BaseModel):
    """OpenAI message format for LLM context."""

    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[Dict[str, Any]] = None
    tool_call_id: Optional[str] = None


__all__ = [
    "IntentType",
    "MessageType",
    "AgentEffort",
    "RouterMode",
    "QuestionMessage",
    "ClarificationResponseMessage",
    "ConfirmMutationMessage",
    "IntentClassifiedMessage",
    "AnswerChunkMessage",
    "EventsInsertedMessage",
    "MutationPreviewMessage",
    "GraphMutatedMessage",
    "JobQueuedMessage",
    "ClarificationRequestMessage",
    "ErrorMessage",
    "ProgressUpdateMessage",
    "GraphUpdateMessage",
    "ClassificationResult",
    "ChatMessageCreate",
    "ChatMessageResponse",
    "ChatHistoryResponse",
    "OpenAIMessage",
    "ToolExecutionCreate",
    "ToolExecutionUpdate",
    "ToolExecutionResponse",
]
