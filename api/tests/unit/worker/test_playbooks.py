"""
Unit tests for investigation playbooks.
Tests playbook loading, selection, and strategy generation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import yaml

from worker.agents.playbooks import (
    Playbook,
    PlaybookRegistry,
    get_playbook_registry,
    select_playbook_for_query,
)
from worker.agents.investigation_playbooks import (
    get_playbook_for_query,
    get_investigation_strategy_prompt,
)
from worker.models import AssistantMessage


@pytest.mark.unit
class TestPlaybook:
    """Test Playbook class."""

    def test_playbook_initialization(self):
        """Test Playbook object creation."""
        playbook = Playbook(
            name="test_playbook",
            description="Test playbook description",
            playbook="# Test Playbook Content"
        )

        assert playbook.name == "test_playbook"
        assert playbook.description == "Test playbook description"
        assert playbook.playbook == "# Test Playbook Content"

    def test_playbook_repr(self):
        """Test Playbook string representation."""
        playbook = Playbook(
            name="lateral_movement",
            description="Lateral movement investigation",
            playbook="Content"
        )

        assert repr(playbook) == "Playbook(name=lateral_movement)"


@pytest.mark.unit
class TestPlaybookRegistry:
    """Test PlaybookRegistry class."""

    def test_registry_loads_playbooks(self):
        """Test that registry loads playbooks from directory."""
        registry = get_playbook_registry()

        assert len(registry.playbooks) > 0
        playbook_names = [pb.name for pb in registry.playbooks]
        assert "lateral_movement" in playbook_names

    def test_get_all_descriptions(self):
        """Test that get_all_descriptions formats playbooks."""
        registry = get_playbook_registry()
        descriptions = registry.get_all_descriptions()

        assert "Available Investigation Playbooks:" in descriptions
        assert "lateral_movement" in descriptions.lower()

    def test_get_playbook_by_name(self):
        """Test retrieving specific playbook by name."""
        registry = get_playbook_registry()
        playbook = registry.get_playbook_by_name("lateral_movement")

        assert playbook is not None
        assert playbook.name == "lateral_movement"
        assert "Lateral Movement" in playbook.description or "lateral movement" in playbook.description

    def test_get_playbook_by_name_not_found(self):
        """Test that get_playbook_by_name returns None for unknown playbook."""
        registry = get_playbook_registry()
        playbook = registry.get_playbook_by_name("nonexistent_playbook")

        assert playbook is None

    def test_reload_playbooks(self):
        """Test that reload_playbooks reloads from disk."""
        registry = get_playbook_registry()
        initial_count = len(registry.playbooks)

        registry.reload_playbooks()

        assert len(registry.playbooks) == initial_count


@pytest.mark.unit
class TestPlaybookRegistryCustom:
    """Test PlaybookRegistry with custom playbooks."""

    def test_load_custom_playbook(self):
        """Test loading a custom playbook from temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            playbook_path = Path(tmpdir) / "custom_playbook.yaml"
            playbook_data = {
                "name": "custom_test",
                "description": "Custom test playbook",
                "playbook": "# Custom Playbook\nTest content"
            }

            with open(playbook_path, 'w') as f:
                yaml.dump(playbook_data, f)

            registry = PlaybookRegistry()
            registry.playbooks = []
            registry._playbooks_dir = Path(tmpdir)
            registry._load_playbooks()

            assert len(registry.playbooks) == 1
            assert registry.playbooks[0].name == "custom_test"

    def test_invalid_playbook_skipped(self):
        """Test that invalid playbooks are skipped during loading."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "invalid.yaml"
            with open(invalid_path, 'w') as f:
                f.write("invalid: yaml: content:")

            registry = PlaybookRegistry()
            registry.playbooks = []
            registry._playbooks_dir = Path(tmpdir)
            registry._load_playbooks()

            assert len(registry.playbooks) == 0


@pytest.mark.unit
class TestSelectPlaybookForQuery:
    """Test LLM-based playbook selection."""

    async def test_select_playbook_returns_match(self):
        """Test that select_playbook_for_query returns matching playbook."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(
            role="assistant",
            content="lateral_movement"
        )

        async def mock_stream():
            yield {"choices": [{"delta": {"content": "lateral_movement"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        playbook = await select_playbook_for_query(
            user_question="Investigate lateral movement in the network",
            llm_client=mock_llm_client
        )

        assert playbook is not None
        assert playbook.name == "lateral_movement"

    async def test_select_playbook_returns_none(self):
        """Test that select_playbook_for_query returns None when LLM says 'none'."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(
            role="assistant",
            content="none"
        )

        async def mock_stream():
            yield {"choices": [{"delta": {"content": "none"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        playbook = await select_playbook_for_query(
            user_question="What is the weather today?",
            llm_client=mock_llm_client
        )

        assert playbook is None

    async def test_select_playbook_handles_unknown_name(self):
        """Test that select_playbook_for_query handles unknown playbook names."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(
            role="assistant",
            content="unknown_playbook_name"
        )

        async def mock_stream():
            yield {"choices": [{"delta": {"content": "unknown_playbook_name"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        playbook = await select_playbook_for_query(
            user_question="Test question",
            llm_client=mock_llm_client
        )

        assert playbook is None

    async def test_select_playbook_handles_error(self):
        """Test that select_playbook_for_query handles LLM errors gracefully."""
        mock_llm_client = MagicMock()
        mock_llm_client.stream_chat.side_effect = Exception("LLM error")

        playbook = await select_playbook_for_query(
            user_question="Test question",
            llm_client=mock_llm_client
        )

        assert playbook is None


@pytest.mark.unit
class TestGetPlaybookForQuery:
    """Test get_playbook_for_query wrapper function."""

    async def test_get_playbook_for_query_returns_playbook_text(self):
        """Test that get_playbook_for_query returns playbook text."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(
            role="assistant",
            content="lateral_movement"
        )

        async def mock_stream():
            yield {"choices": [{"delta": {"content": "lateral_movement"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        playbook_text = await get_playbook_for_query(
            user_question="Investigate lateral movement",
            llm_client=mock_llm_client
        )

        assert playbook_text is not None
        assert isinstance(playbook_text, str)
        assert len(playbook_text) > 0

    async def test_get_playbook_for_query_returns_none(self):
        """Test that get_playbook_for_query returns None when no match."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(
            role="assistant",
            content="none"
        )

        async def mock_stream():
            yield {"choices": [{"delta": {"content": "none"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        playbook_text = await get_playbook_for_query(
            user_question="Random question",
            llm_client=mock_llm_client
        )

        assert playbook_text is None


@pytest.mark.unit
class TestGetInvestigationStrategyPrompt:
    """Test investigation strategy prompt generation."""

    async def test_strategy_prompt_includes_playbook(self):
        """Test that strategy prompt includes playbook content when matched."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(
            role="assistant",
            content="lateral_movement"
        )

        async def mock_stream():
            yield {"choices": [{"delta": {"content": "lateral_movement"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        strategy = await get_investigation_strategy_prompt(
            user_question="Investigate lateral movement",
            iteration=1,
            max_iterations=10,
            tool_execution_log=[],
            llm_client=mock_llm_client
        )

        assert "YOUR PROGRESS" in strategy
        assert "Iteration: 1/10" in strategy
        assert "LATERAL MOVEMENT" in strategy.upper()

    async def test_strategy_prompt_without_playbook(self):
        """Test that strategy prompt provides generic guidance without playbook."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(
            role="assistant",
            content="none"
        )

        async def mock_stream():
            yield {"choices": [{"delta": {"content": "none"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        strategy = await get_investigation_strategy_prompt(
            user_question="Generic question",
            iteration=1,
            max_iterations=10,
            tool_execution_log=[],
            llm_client=mock_llm_client
        )

        assert "INVESTIGATION STRATEGY" in strategy
        assert "systematic approach" in strategy.lower()

    async def test_strategy_prompt_early_iteration_with_playbook(self):
        """Test strategy prompt for early iterations includes discovery phase."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(role="assistant", content="lateral_movement")
        
        async def mock_stream():
            yield {"choices": [{"delta": {"content": "lateral_movement"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        strategy = await get_investigation_strategy_prompt(
            user_question="Test",
            iteration=1,
            max_iterations=10,
            tool_execution_log=[],
            llm_client=mock_llm_client
        )

        assert "CURRENT PHASE" in strategy
        assert "Discovery" in strategy

    async def test_strategy_prompt_mid_iteration_with_playbook(self):
        """Test strategy prompt for mid iterations includes analysis phase."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(role="assistant", content="lateral_movement")
        
        async def mock_stream():
            yield {"choices": [{"delta": {"content": "lateral_movement"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        strategy = await get_investigation_strategy_prompt(
            user_question="Test",
            iteration=3,
            max_iterations=10,
            tool_execution_log=[],
            llm_client=mock_llm_client
        )

        assert "CURRENT PHASE" in strategy
        assert "Analysis" in strategy

    async def test_strategy_prompt_late_iteration_with_playbook(self):
        """Test strategy prompt for late iterations includes validation phase."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(role="assistant", content="lateral_movement")
        
        async def mock_stream():
            yield {"choices": [{"delta": {"content": "lateral_movement"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        strategy = await get_investigation_strategy_prompt(
            user_question="Test",
            iteration=7,
            max_iterations=10,
            tool_execution_log=[],
            llm_client=mock_llm_client
        )

        assert "CURRENT PHASE" in strategy
        assert "Validation" in strategy or "Completion" in strategy

    async def test_strategy_prompt_includes_tool_history(self):
        """Test that strategy prompt includes tool execution history."""
        mock_llm_client = MagicMock()

        mock_message = AssistantMessage(role="assistant", content="lateral_movement")
        
        async def mock_stream():
            yield {"choices": [{"delta": {"content": "lateral_movement"}}]}

        async def mock_parse(stream):
            return mock_message

        mock_llm_client.stream_chat.return_value = mock_stream()
        mock_llm_client.parse_stream_to_message = mock_parse

        tool_log = [
            {
                "tool_name": "query_jsonb_field",
                "arguments": {"jsonb_path": "EventData.TargetUserName", "value": "admin"},
                "iteration": 1,
            },
            {
                "tool_name": "aggregate_jsonb_field",
                "arguments": {"jsonb_path": "EventData.LogonType"},
                "iteration": 1,
            }
        ]

        strategy = await get_investigation_strategy_prompt(
            user_question="Test",
            iteration=2,
            max_iterations=10,
            tool_execution_log=tool_log,
            llm_client=mock_llm_client
        )

        assert "ALREADY CHECKED" in strategy
        assert "query_jsonb_field" in strategy
        assert "aggregate_jsonb_field" in strategy
        assert "Don't repeat" in strategy or "don't repeat" in strategy.lower()
