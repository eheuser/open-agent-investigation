"""
Unit tests for AssistantAgent.
Tests the two-phase plan-execute workflow and state management.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
from datetime import datetime
import json

from worker.agents.assistant_agent import AssistantAgent, _deduplicate_tool_calls, _strip_cot_tags
from worker.models import ToolResult, AssistantMessage, ToolCall


@pytest.mark.unit
class TestAssistantAgentUtilities:
    """Test utility functions."""

    def test_strip_cot_tags_removes_tags(self):
        """Test that _strip_cot_tags removes chain-of-thought tags."""
        text = "Before <cot>thinking process</cot> After"
        result = _strip_cot_tags(text)
        assert result == "Before  After"

    def test_strip_cot_tags_handles_multiline(self):
        """Test that _strip_cot_tags handles multiline CoT blocks."""
        text = "Start\n<cot>\nLine 1\nLine 2\n</cot>\nEnd"
        result = _strip_cot_tags(text)
        assert "Line 1" not in result
        assert "Start" in result
        assert "End" in result

    def test_deduplicate_tool_calls_removes_duplicates(self):
        """Test that _deduplicate_tool_calls removes duplicate tool calls."""
        tool_calls = [
            ToolCall(id="1", type="function", function={"name": "test_tool", "arguments": '{"arg": "value"}'}),
            ToolCall(id="2", type="function", function={"name": "test_tool", "arguments": '{"arg": "value"}'}),
            ToolCall(id="3", type="function", function={"name": "other_tool", "arguments": '{"arg": "value"}'}),
        ]
        unique, dup_count = _deduplicate_tool_calls(tool_calls)
        assert len(unique) == 2
        assert dup_count == 1

    def test_deduplicate_tool_calls_ignores_description(self):
        """Test that _deduplicate_tool_calls ignores description field."""
        tool_calls = [
            ToolCall(id="1", type="function", function={"name": "test_tool", "arguments": '{"arg": "value", "description": "Desc 1"}'}),
            ToolCall(id="2", type="function", function={"name": "test_tool", "arguments": '{"arg": "value", "description": "Desc 2"}'}),
        ]
        unique, dup_count = _deduplicate_tool_calls(tool_calls)
        assert len(unique) == 1
        assert dup_count == 1


@pytest.mark.unit
class TestAssistantAgentInitialization:
    """Test AssistantAgent initialization."""

    def test_initialization_sets_defaults(self):
        """Test that agent initializes with correct defaults."""
        agent = AssistantAgent(
            db=MagicMock(),
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        assert agent.iteration == 0
        assert agent.max_iterations == 10
        assert agent.total_tools_executed == 0
        assert isinstance(agent.tool_execution_log, list)
        assert len(agent.tool_execution_log) == 0
        assert isinstance(agent.query_signatures, set)
        assert len(agent.query_signatures) == 0
        assert agent.cancelled is False

    def test_initialization_with_custom_iterations(self):
        """Test initialization with custom max_iterations."""
        agent = AssistantAgent(
            db=MagicMock(),
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
            max_iterations=20,
        )

        assert agent.max_iterations == 20


@pytest.mark.unit
class TestAssistantAgentCancelSignal:
    """Test cancellation functionality."""

    async def test_check_cancel_signal_not_cancelled(self):
        """Test check_cancel_signal returns False when not cancelled."""
        db = AsyncMock()
        result = MagicMock()
        result.fetchone.return_value = (None,)
        
        async def mock_execute(*args, **kwargs):
            return result
        
        db.execute = mock_execute

        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        is_cancelled = await agent.check_cancel_signal()
        assert is_cancelled is False
        assert agent.cancelled is False

    async def test_check_cancel_signal_cancelled(self):
        """Test check_cancel_signal returns True when cancelled."""
        db = AsyncMock()
        result = MagicMock()
        result.fetchone.return_value = ("true",)
        
        async def mock_execute(*args, **kwargs):
            return result
        
        db.execute = mock_execute

        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        is_cancelled = await agent.check_cancel_signal()
        assert is_cancelled is True
        assert agent.cancelled is True


@pytest.mark.unit
class TestAssistantAgentToolLogging:
    """Test tool execution logging."""

    async def test_query_tool_logged_on_success(self):
        """Test that successful query tools are logged."""
        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        agent.iteration = 1

        mock_result = ToolResult(
            status="ok",
            result={"count": 45, "events": []},
            error_msg=None,
        )
        agent.tool_executor.execute = AsyncMock(return_value=mock_result)

        tool_calls = [
            ToolCall(
                id="call_1",
                type="function",
                function={"name": "query_jsonb_field", "arguments": '{"jsonb_path": "EventData.TargetUserName", "value": "admin"}'}
            )
        ]

        events = []
        async for event in agent._execute_tools(tool_calls):
            events.append(event)

        assert len(agent.tool_execution_log) == 1
        logged = agent.tool_execution_log[0]
        assert logged["iteration"] == 1
        assert logged["tool_name"] == "query_jsonb_field"
        assert logged["status"] == "ok"
        assert logged["result_count"] == 45

    async def test_non_query_tool_not_logged(self):
        """Test that non-query tools are not logged."""
        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        agent.iteration = 1

        mock_result = ToolResult(
            status="ok",
            result={"entry_id": 1},
            error_msg=None,
        )
        agent.tool_executor.execute = AsyncMock(return_value=mock_result)

        tool_calls = [
            ToolCall(
                id="call_1",
                type="function",
                function={"name": "register_timeline_entry", "arguments": '{"description": "Test"}'}
            )
        ]

        async for event in agent._execute_tools(tool_calls):
            pass

        assert len(agent.tool_execution_log) == 0

    async def test_failed_tool_not_logged(self):
        """Test that failed tools are not logged."""
        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        agent.iteration = 1

        mock_result = ToolResult(
            status="error",
            result=None,
            error_msg="Database error",
        )
        agent.tool_executor.execute = AsyncMock(return_value=mock_result)

        tool_calls = [
            ToolCall(
                id="call_1",
                type="function",
                function={"name": "query_jsonb_field", "arguments": '{"jsonb_path": "test"}'}
            )
        ]

        async for event in agent._execute_tools(tool_calls):
            pass

        assert len(agent.tool_execution_log) == 0


@pytest.mark.unit
class TestAssistantAgentPhases:
    """Test two-phase workflow."""

    async def test_plan_tools_returns_tool_calls(self):
        """Test that _plan_tools extracts tool calls from LLM response."""
        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        mock_tool_call = ToolCall(
            id="call_1",
            type="function",
            function={"name": "query_jsonb_field", "arguments": '{"jsonb_path": "test"}'}
        )
        mock_message = AssistantMessage(role="assistant", content=None, tool_calls=[mock_tool_call])

        with patch.object(agent, '_llm_stream') as mock_stream:
            async def mock_gen():
                yield {"type": "llm_response", "message": mock_message, "success": True}
            mock_stream.return_value = mock_gen()

            events = []
            async for event in agent._plan_tools([], []):
                events.append(event)

            internal_events = [e for e in events if e["type"] == "_internal_plan_result"]
            assert len(internal_events) == 1
            assert len(internal_events[0]["tool_calls"]) == 1

    async def test_execute_tools_yields_results(self):
        """Test that _execute_tools executes and yields results."""
        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        agent.iteration = 1

        mock_result = ToolResult(status="ok", result={"count": 10, "events": []}, error_msg=None)
        agent.tool_executor.execute = AsyncMock(return_value=mock_result)

        tool_calls = [
            ToolCall(
                id="call_1",
                type="function",
                function={"name": "query_jsonb_field", "arguments": '{"jsonb_path": "test"}'}
            )
        ]

        events = []
        async for event in agent._execute_tools(tool_calls):
            events.append(event)

        tool_executing_events = [e for e in events if e["type"] == "tool_executing"]
        tool_result_events = [e for e in events if e["type"] == "tool_result"]

        assert len(tool_executing_events) == 1
        assert len(tool_result_events) == 1
        assert tool_result_events[0]["success"] is True

    async def test_analyze_results_processes_summary(self):
        """Test that _analyze_results processes tool summary."""
        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        mock_message = AssistantMessage(role="assistant", content="Analysis complete")

        with patch.object(agent, '_llm_stream') as mock_stream:
            async def mock_gen():
                yield {"type": "llm_response", "message": mock_message, "success": True}
            mock_stream.return_value = mock_gen()

            events = []
            async for event in agent._analyze_results([], [], "Tool summary"):
                events.append(event)

            analysis_events = [e for e in events if e["type"] == "analysis_complete"]
            assert len(analysis_events) == 1
            assert "Analysis complete" in analysis_events[0]["summary"]


@pytest.mark.unit
class TestAssistantAgentCompaction:
    """Test context compaction."""

    async def test_maybe_compact_skips_when_under_threshold(self):
        """Test that compaction is skipped when under threshold."""
        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
            llm_max_context=10000,
        )

        agent.compact_threshold = 5000

        chat_log = [
            {"role": "system", "content": "Short content"},
            {"role": "user", "content": "question"},
        ]

        with patch.object(agent, '_compact_chat_log') as mock_compact:
            events = []
            async for event in agent._maybe_compact(chat_log):
                events.append(event)

            assert not mock_compact.called

    def test_stats_snapshot(self):
        """Test that _stats_snapshot returns correct stats."""
        agent = AssistantAgent(
            db=MagicMock(),
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        agent.iteration = 5
        agent.total_tools_executed = 15
        agent.stats = {
            "events_analyzed": 100,
            "timeline_entries_created": 3,
            "tools_called": {"query_jsonb_field": 5},
        }

        snapshot = agent._stats_snapshot()

        assert snapshot["turns_executed"] == 5
        assert snapshot["tool_executions"] == 15
        assert snapshot["events_analyzed"] == 100
        assert snapshot["timeline_entries_created"] == 3
        assert snapshot["tools_called"]["query_jsonb_field"] == 5


@pytest.mark.unit
class TestAssistantAgentToolLimits:
    """Test tool execution limits."""

    async def test_tool_limit_enforced(self):
        """Test that MAX_TOOLS_PER_ITERATION limit is enforced."""
        from worker.agents.assistant_agent import MAX_TOOLS_PER_ITERATION

        db = AsyncMock()
        agent = AssistantAgent(
            db=db,
            investigation_id=str(uuid4()),
            job_id=1,
            question="Test question",
            llm_endpoint="http://test",
            llm_model="test-model",
        )

        many_tool_calls = [
            ToolCall(
                id=f"call_{i}",
                type="function",
                function={"name": "query_jsonb_field", "arguments": f'{{"jsonb_path": "test{i}"}}'}
            )
            for i in range(MAX_TOOLS_PER_ITERATION + 5)
        ]

        mock_message = AssistantMessage(role="assistant", content=None, tool_calls=many_tool_calls)

        with patch.object(agent, '_llm_stream') as mock_stream:
            async def mock_gen():
                yield {"type": "llm_response", "message": mock_message, "success": True}
            mock_stream.return_value = mock_gen()

            events = []
            async for event in agent._plan_tools([], []):
                events.append(event)

            limit_events = [e for e in events if e["type"] == "tool_limit_enforced"]
            internal_events = [e for e in events if e["type"] == "_internal_plan_result"]

            assert len(limit_events) >= 1
            assert len(internal_events[0]["tool_calls"]) == MAX_TOOLS_PER_ITERATION
