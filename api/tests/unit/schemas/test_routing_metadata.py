"""
Unit tests for routing metadata schemas.
Tests the routing feedback metadata structures.
"""

import pytest
from app.schemas.routing_metadata import (
    HandlerMetadata,
    AgentHandlerMetadata,
    RAGHandlerMetadata,
    TimelineHandlerMetadata,
    GeneralChatHandlerMetadata,
    RoutingDecision,
    create_routing_metadata,
)


@pytest.mark.unit
class TestHandlerMetadata:
    """Test base HandlerMetadata class."""

    def test_handler_metadata_creation(self):
        """Test creating base HandlerMetadata."""
        metadata = HandlerMetadata(
            handler_type="test",
            handler_display_name="Test Handler"
        )

        assert metadata.handler_type == "test"
        assert metadata.handler_display_name == "Test Handler"
        assert metadata.confidence is None
        assert metadata.processing_time_ms is None

    def test_handler_metadata_with_optional_fields(self):
        """Test HandlerMetadata with optional fields."""
        metadata = HandlerMetadata(
            handler_type="test",
            handler_display_name="Test Handler",
            confidence=0.95,
            processing_time_ms=150
        )

        assert metadata.confidence == 0.95
        assert metadata.processing_time_ms == 150


@pytest.mark.unit
class TestAgentHandlerMetadata:
    """Test AgentHandlerMetadata class."""

    def test_agent_metadata_defaults(self):
        """Test AgentHandlerMetadata with default values."""
        metadata = AgentHandlerMetadata()

        assert metadata.handler_type == "agent"
        assert metadata.handler_display_name == "AI Agent Investigation"
        assert metadata.effort_level == "medium"
        assert metadata.max_turns == 10
        assert metadata.playbook_name is None
        assert metadata.job_id is None

    def test_agent_metadata_with_playbook(self):
        """Test AgentHandlerMetadata with playbook information."""
        metadata = AgentHandlerMetadata(
            playbook_name="lateral_movement",
            playbook_display_name="Lateral Movement Detection",
            playbook_description="Investigation strategies for lateral movement",
            effort_level="high",
            max_turns=9,
            job_id=123
        )

        assert metadata.playbook_name == "lateral_movement"
        assert metadata.playbook_display_name == "Lateral Movement Detection"
        assert metadata.playbook_description == "Investigation strategies for lateral movement"
        assert metadata.effort_level == "high"
        assert metadata.max_turns == 9
        assert metadata.job_id == 123

    def test_agent_metadata_serialization(self):
        """Test that AgentHandlerMetadata serializes correctly."""
        metadata = AgentHandlerMetadata(
            playbook_name="credential_access",
            playbook_display_name="Credential Access Detection",
            effort_level="medium",
            max_turns=6
        )

        data = metadata.model_dump()

        assert data["handler_type"] == "agent"
        assert data["playbook_name"] == "credential_access"
        assert data["effort_level"] == "medium"
        assert data["max_turns"] == 6


@pytest.mark.unit
class TestRAGHandlerMetadata:
    """Test RAGHandlerMetadata class."""

    def test_rag_metadata_defaults(self):
        """Test RAGHandlerMetadata with default values."""
        metadata = RAGHandlerMetadata()

        assert metadata.handler_type == "rag"
        assert metadata.handler_display_name == "Augmented Chat (RAG)"
        assert metadata.sources_retrieved == 0
        assert metadata.expansion_terms == 0
        assert metadata.embedding_provider is None

    def test_rag_metadata_with_values(self):
        """Test RAGHandlerMetadata with actual values."""
        metadata = RAGHandlerMetadata(
            sources_retrieved=50,
            expansion_terms=7,
            embedding_provider="openai",
            total_candidates=80
        )

        assert metadata.sources_retrieved == 50
        assert metadata.expansion_terms == 7
        assert metadata.embedding_provider == "openai"
        assert metadata.total_candidates == 80

    def test_rag_metadata_serialization(self):
        """Test that RAGHandlerMetadata serializes correctly."""
        metadata = RAGHandlerMetadata(
            sources_retrieved=25,
            expansion_terms=5,
            embedding_provider="cohere"
        )

        data = metadata.model_dump()

        assert data["handler_type"] == "rag"
        assert data["sources_retrieved"] == 25
        assert data["expansion_terms"] == 5
        assert data["embedding_provider"] == "cohere"


@pytest.mark.unit
class TestTimelineHandlerMetadata:
    """Test TimelineHandlerMetadata class."""

    def test_timeline_metadata_defaults(self):
        """Test TimelineHandlerMetadata with default values."""
        metadata = TimelineHandlerMetadata()

        assert metadata.handler_type == "timeline"
        assert metadata.handler_display_name == "Timeline Operations"
        assert metadata.operation_type is None
        assert metadata.entries_affected == 0
        assert metadata.filters_applied is None

    def test_timeline_metadata_with_values(self):
        """Test TimelineHandlerMetadata with actual values."""
        metadata = TimelineHandlerMetadata(
            operation_type="query/add",
            entries_affected=5,
            filters_applied=["entry_type=event", "tags=suspicious"]
        )

        assert metadata.operation_type == "query/add"
        assert metadata.entries_affected == 5
        assert metadata.filters_applied == ["entry_type=event", "tags=suspicious"]

    def test_timeline_metadata_serialization(self):
        """Test that TimelineHandlerMetadata serializes correctly."""
        metadata = TimelineHandlerMetadata(
            operation_type="delete",
            entries_affected=3
        )

        data = metadata.model_dump()

        assert data["handler_type"] == "timeline"
        assert data["operation_type"] == "delete"
        assert data["entries_affected"] == 3


@pytest.mark.unit
class TestGeneralChatHandlerMetadata:
    """Test GeneralChatHandlerMetadata class."""

    def test_general_chat_metadata_defaults(self):
        """Test GeneralChatHandlerMetadata with default values."""
        metadata = GeneralChatHandlerMetadata()

        assert metadata.handler_type == "general_chat"
        assert metadata.handler_display_name == "General Chat"
        assert metadata.context_sources is None
        assert metadata.query_type is None

    def test_general_chat_metadata_with_values(self):
        """Test GeneralChatHandlerMetadata with actual values."""
        metadata = GeneralChatHandlerMetadata(
            context_sources=["investigation", "timeline", "artifacts"],
            query_type="metadata"
        )

        assert metadata.context_sources == ["investigation", "timeline", "artifacts"]
        assert metadata.query_type == "metadata"

    def test_general_chat_metadata_serialization(self):
        """Test that GeneralChatHandlerMetadata serializes correctly."""
        metadata = GeneralChatHandlerMetadata(
            query_type="summary",
            context_sources=["investigation"]
        )

        data = metadata.model_dump()

        assert data["handler_type"] == "general_chat"
        assert data["query_type"] == "summary"
        assert data["context_sources"] == ["investigation"]


@pytest.mark.unit
class TestRoutingDecision:
    """Test RoutingDecision class."""

    def test_routing_decision_with_agent_metadata(self):
        """Test RoutingDecision with agent handler metadata."""
        agent_metadata = AgentHandlerMetadata(
            playbook_name="lateral_movement",
            playbook_display_name="Lateral Movement Detection",
            effort_level="medium",
            max_turns=6
        )

        decision = RoutingDecision(
            intent_type="execute_agent_policy",
            router_mode="auto",
            handler_metadata=agent_metadata,
            query_expanded=True,
            original_query="Find lateral movement",
            expanded_query="Find lateral movement evidence in network logons"
        )

        assert decision.intent_type == "execute_agent_policy"
        assert decision.router_mode == "auto"
        assert decision.query_expanded is True
        assert decision.handler_metadata.handler_type == "agent"

    def test_routing_decision_serialization(self):
        """Test that RoutingDecision serializes correctly."""
        # Test with create_routing_metadata which returns plain dict (used in actual code)
        metadata = create_routing_metadata(
            intent_type="augmented_chat",
            router_mode="augmented",
            handler_type="rag",
            sources_retrieved=30,
            expansion_terms=5
        )

        assert metadata["intent_type"] == "augmented_chat"
        assert metadata["router_mode"] == "augmented"
        # Check that handler metadata is included
        assert "handler_metadata" in metadata
        assert metadata["handler_metadata"]["handler_type"] == "rag"
        assert metadata["handler_metadata"]["handler_display_name"] == "Augmented Chat (RAG)"
        assert metadata["handler_metadata"]["sources_retrieved"] == 30
        assert metadata["handler_metadata"]["expansion_terms"] == 5


@pytest.mark.unit
class TestCreateRoutingMetadata:
    """Test create_routing_metadata factory function."""

    def test_create_agent_metadata(self):
        """Test creating agent routing metadata."""
        metadata = create_routing_metadata(
            intent_type="execute_agent_policy",
            router_mode="auto",
            handler_type="agent",
            confidence=0.9,
            playbook_name="lateral_movement",
            playbook_display_name="Lateral Movement Detection",
            effort_level="medium",
            max_turns=6,
            job_id=123
        )

        assert metadata["intent_type"] == "execute_agent_policy"
        assert metadata["router_mode"] == "auto"
        assert metadata["handler_metadata"]["handler_type"] == "agent"
        assert metadata["handler_metadata"]["handler_display_name"] == "AI Agent Investigation"
        assert metadata["handler_metadata"]["playbook_name"] == "lateral_movement"
        assert metadata["handler_metadata"]["playbook_display_name"] == "Lateral Movement Detection"
        assert metadata["handler_metadata"]["effort_level"] == "medium"
        assert metadata["handler_metadata"]["max_turns"] == 6
        assert metadata["handler_metadata"]["job_id"] == 123

    def test_create_rag_metadata(self):
        """Test creating RAG routing metadata."""
        metadata = create_routing_metadata(
            intent_type="augmented_chat",
            router_mode="augmented",
            handler_type="rag",
            confidence=0.85,
            sources_retrieved=50,
            expansion_terms=7,
            embedding_provider="openai",
            total_candidates=80
        )

        assert metadata["intent_type"] == "augmented_chat"
        assert metadata["router_mode"] == "augmented"
        assert metadata["handler_metadata"]["handler_type"] == "rag"
        assert metadata["handler_metadata"]["handler_display_name"] == "Augmented Chat (RAG)"
        assert metadata["handler_metadata"]["sources_retrieved"] == 50
        assert metadata["handler_metadata"]["expansion_terms"] == 7
        assert metadata["handler_metadata"]["embedding_provider"] == "openai"
        assert metadata["handler_metadata"]["total_candidates"] == 80

    def test_create_timeline_metadata(self):
        """Test creating timeline routing metadata."""
        metadata = create_routing_metadata(
            intent_type="timeline_query",
            router_mode="timeline",
            handler_type="timeline",
            operation_type="query",
            entries_affected=5,
            filters_applied=["entry_type=event"]
        )

        assert metadata["intent_type"] == "timeline_query"
        assert metadata["router_mode"] == "timeline"
        assert metadata["handler_metadata"]["handler_type"] == "timeline"
        assert metadata["handler_metadata"]["handler_display_name"] == "Timeline Operations"
        assert metadata["handler_metadata"]["operation_type"] == "query"
        assert metadata["handler_metadata"]["entries_affected"] == 5
        assert metadata["handler_metadata"]["filters_applied"] == ["entry_type=event"]

    def test_create_general_chat_metadata(self):
        """Test creating general chat routing metadata."""
        metadata = create_routing_metadata(
            intent_type="general_chat",
            router_mode="auto",
            handler_type="general_chat",
            query_type="metadata",
            context_sources=["investigation", "timeline"]
        )

        assert metadata["intent_type"] == "general_chat"
        assert metadata["router_mode"] == "auto"
        assert metadata["handler_metadata"]["handler_type"] == "general_chat"
        assert metadata["handler_metadata"]["handler_display_name"] == "General Chat"
        assert metadata["handler_metadata"]["query_type"] == "metadata"
        assert metadata["handler_metadata"]["context_sources"] == ["investigation", "timeline"]

    def test_create_metadata_without_optional_fields(self):
        """Test creating routing metadata with minimal fields."""
        metadata = create_routing_metadata(
            intent_type="general_chat",
            router_mode="auto",
            handler_type="general_chat"
        )

        assert metadata["intent_type"] == "general_chat"
        assert metadata["router_mode"] == "auto"
        assert metadata["handler_metadata"]["handler_type"] == "general_chat"
        assert metadata["query_expanded"] is False
