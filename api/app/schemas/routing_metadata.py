from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class HandlerMetadata(BaseModel):
    """Base metadata for all chat handlers."""
    
    handler_type: str = Field(..., description="Type of handler (agent, rag, timeline, general_chat)")
    handler_display_name: str = Field(..., description="Human-readable handler name")
    confidence: Optional[float] = Field(None, description="Routing confidence score (0.0-1.0)")
    processing_time_ms: Optional[int] = Field(None, description="Handler processing time in milliseconds")


class AgentHandlerMetadata(HandlerMetadata):
    """Metadata for agent handler routing."""
    
    handler_type: str = "agent"
    handler_display_name: str = "AI Agent Investigation"
    processing_time_ms: Optional[int] = None
    
    playbook_name: Optional[str] = Field(default=None, description="Selected playbook identifier")
    playbook_display_name: Optional[str] = Field(default=None, description="Playbook friendly name")
    playbook_description: Optional[str] = Field(default=None, description="Playbook description")
    effort_level: str = Field(default="medium", description="Investigation effort level (low/medium/high)")
    max_turns: int = Field(default=10, description="Maximum turns allocated")
    job_id: Optional[int] = Field(default=None, description="Background job ID")


class RAGHandlerMetadata(HandlerMetadata):
    """Metadata for RAG (Augmented Chat) handler routing."""
    
    handler_type: str = "rag"
    handler_display_name: str = "Augmented Chat (RAG)"
    processing_time_ms: Optional[int] = None
    
    sources_retrieved: int = Field(default=0, description="Number of contextual sources retrieved")
    expansion_terms: int = Field(default=0, description="Number of query expansion terms generated")
    embedding_provider: Optional[str] = Field(default=None, description="Embedding provider used (openai/cohere/ollama)")
    total_candidates: Optional[int] = Field(default=None, description="Total candidates before deduplication")


class TimelineHandlerMetadata(HandlerMetadata):
    """Metadata for timeline handler routing."""
    
    handler_type: str = "timeline"
    handler_display_name: str = "Timeline Operations"
    processing_time_ms: Optional[int] = None
    
    operation_type: Optional[str] = Field(default=None, description="Timeline operation (query/add/update/delete)")
    entries_affected: int = Field(default=0, description="Number of timeline entries affected")
    filters_applied: Optional[List[str]] = Field(default=None, description="Filters applied to query")


class GeneralChatHandlerMetadata(HandlerMetadata):
    """Metadata for general chat handler routing."""
    
    handler_type: str = "general_chat"
    handler_display_name: str = "General Chat"
    processing_time_ms: Optional[int] = None
    
    context_sources: Optional[List[str]] = Field(default=None, description="Context sources used (investigation metadata, etc.)")
    query_type: Optional[str] = Field(default=None, description="Type of general query (metadata/summary/help)")


class RoutingDecision(BaseModel):
    """Complete routing decision with handler metadata."""
    
    intent_type: str = Field(..., description="Classified intent type")
    router_mode: str = Field("auto", description="Router mode used (auto/agent/timeline/augmented)")
    handler_metadata: HandlerMetadata = Field(..., description="Handler-specific metadata")
    query_expanded: bool = Field(False, description="Whether query was expanded")
    original_query: Optional[str] = Field(None, description="Original user query")
    expanded_query: Optional[str] = Field(None, description="Expanded query (if applicable)")


def create_routing_metadata(
    intent_type: str,
    router_mode: str,
    handler_type: str,
    confidence: Optional[float] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Factory function to create routing metadata based on handler type.
    
    Args:
        intent_type: The classified intent type
        router_mode: Router mode used (auto/agent/timeline/augmented)
        handler_type: Type of handler (agent/rag/timeline/general_chat)
        confidence: Routing confidence score
        **kwargs: Handler-specific metadata fields
    
    Returns:
        Dictionary with routing metadata
    """
    # Build handler metadata dict directly to avoid Pydantic serialization issues
    handler_metadata_dict = {
        "handler_type": handler_type,
        "confidence": confidence,
        "processing_time_ms": kwargs.get("processing_time_ms"),
    }
    
    if handler_type == "agent":
        handler_metadata_dict.update({
            "handler_display_name": "AI Agent Investigation",
            "playbook_name": kwargs.get("playbook_name"),
            "playbook_display_name": kwargs.get("playbook_display_name"),
            "playbook_description": kwargs.get("playbook_description"),
            "effort_level": kwargs.get("effort_level", "medium"),
            "max_turns": kwargs.get("max_turns", 10),
            "job_id": kwargs.get("job_id"),
        })
    elif handler_type == "rag":
        handler_metadata_dict.update({
            "handler_display_name": "Augmented Chat (RAG)",
            "sources_retrieved": kwargs.get("sources_retrieved", 0),
            "expansion_terms": kwargs.get("expansion_terms", 0),
            "embedding_provider": kwargs.get("embedding_provider"),
            "total_candidates": kwargs.get("total_candidates"),
        })
    elif handler_type == "timeline":
        handler_metadata_dict.update({
            "handler_display_name": "Timeline Operations",
            "operation_type": kwargs.get("operation_type"),
            "entries_affected": kwargs.get("entries_affected", 0),
            "filters_applied": kwargs.get("filters_applied"),
        })
    else:  # general_chat
        handler_metadata_dict.update({
            "handler_display_name": "General Chat",
            "context_sources": kwargs.get("context_sources"),
            "query_type": kwargs.get("query_type"),
        })
    
    # Return as plain dict
    return {
        "intent_type": intent_type,
        "router_mode": router_mode,
        "handler_metadata": handler_metadata_dict,
        "query_expanded": kwargs.get("query_expanded", False),
        "original_query": kwargs.get("original_query"),
        "expanded_query": kwargs.get("expanded_query"),
    }


__all__ = [
    "HandlerMetadata",
    "AgentHandlerMetadata",
    "RAGHandlerMetadata",
    "TimelineHandlerMetadata",
    "GeneralChatHandlerMetadata",
    "RoutingDecision",
    "create_routing_metadata",
]
