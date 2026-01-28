"""
Unit tests for worker context manager.
Tests phase-specific context loading for the assistant agent.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.mark.unit
class TestLoadPhase1Context:
    """Test load_phase1_context function."""

    async def test_load_phase1_context_basic(self):
        """
        Test that load_phase1_context returns a string containing event types and JSONB fields.
        """
        from worker.agents.context_manager import load_execution_phase_context

        db = AsyncMock()
        investigation_id = str(uuid4())

        # Mock event types query
        event_types_result = MagicMock()
        event_types_result.fetchall.return_value = [
            ("process_creation",),
            ("network_connection",),
            ("file_modification",),
        ]

        # Mock JSONB fields query (or field dictionary)
        db.execute.return_value = event_types_result

        # Mock LLM client for field dictionary
        mock_llm_client = MagicMock()

        with patch(
            "worker.agents.field_dictionary_finalizer.get_cached_field_dictionary_markdown",
            return_value="\n### Field Dictionary\n- `process.exe`: Process executable\n- `network.destination`: Network destination\n",
        ):
            context = await load_execution_phase_context(
                db=db,
                investigation_id=investigation_id,
                llm_client=mock_llm_client,
                use_field_dictionary=True,
                llm_max_context=32768,
            )

        assert isinstance(context, str)
        assert len(context) > 0
        assert "Event Types" in context or "event" in context.lower()

    async def test_load_phase1_context_no_field_dictionary(self):
        """
        Test that load_phase1_context works without field dictionary.
        """
        from worker.agents.context_manager import load_execution_phase_context

        db = AsyncMock()
        investigation_id = str(uuid4())

        # Mock event types
        event_types_result = MagicMock()
        event_types_result.fetchall.return_value = [("process_creation",)]

        db.execute.return_value = event_types_result

        # Mock get_available_jsonb_fields
        with patch(
            "worker.tools.event_tools.get_available_jsonb_fields",
            return_value=["process.exe", "process.pid"],
        ):
            context = await load_execution_phase_context(
                db=db,
                investigation_id=investigation_id,
                llm_client=None,
                use_field_dictionary=False,
                llm_max_context=32768,
            )

        assert isinstance(context, str)
        assert len(context) > 0

    async def test_load_phase1_context_empty_investigation(self):
        """
        Test that load_phase1_context handles investigations with no events.
        """
        from worker.agents.context_manager import load_execution_phase_context

        db = AsyncMock()
        investigation_id = str(uuid4())

        # Mock empty results
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []

        db.execute.return_value = empty_result

        # Mock get_available_jsonb_fields
        with patch(
            "worker.tools.event_tools.get_available_jsonb_fields",
            return_value=[],
        ):
            context = await load_execution_phase_context(
                db=db,
                investigation_id=investigation_id,
                llm_client=None,
                use_field_dictionary=False,
                llm_max_context=32768,
            )

        # Should still return a string (even if minimal)
        assert isinstance(context, str)


@pytest.mark.unit
class TestLoadPhase2Context:
    """Test load_phase2_context function."""

    async def test_load_phase2_context_basic(self):
        """
        Test that load_phase2_context returns a string containing timeline entries.
        """
        from worker.agents.context_manager import load_analysis_phase_context

        db = AsyncMock()
        investigation_id = str(uuid4())

        # Mock timeline entries query - needs 6 values: entry_id, title, description, entry_type, tags, timestamp
        timeline_result = MagicMock()
        timeline_result.fetchall.return_value = [
            (1, "Malware Execution", "Suspicious process started", "security", ["malware"], "2024-01-01 10:00:00"),
            (2, "Network Connection", "Outbound connection to C2", "network", ["c2"], "2024-01-01 10:05:00"),
        ]

        db.execute.return_value = timeline_result

        context = await load_analysis_phase_context(
            db=db,
            investigation_id=investigation_id,
        )

        assert isinstance(context, str)
        assert len(context) > 0
        assert "Timeline" in context or "timeline" in context.lower()
        assert "Malware Execution" in context
        assert "Network Connection" in context

    async def test_load_phase2_context_no_timeline(self):
        """
        Test that load_phase2_context handles investigations with no timeline entries.
        """
        from worker.agents.context_manager import load_analysis_phase_context

        db = AsyncMock()
        investigation_id = str(uuid4())

        # Mock empty timeline
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []

        db.execute.return_value = empty_result

        context = await load_analysis_phase_context(
            db=db,
            investigation_id=investigation_id,
        )

        # Should still return a string
        assert isinstance(context, str)
        # Should indicate no timeline entries
        assert "no timeline" in context.lower() or "empty" in context.lower()

    async def test_load_phase2_context_many_entries(self):
        """
        Test that load_phase2_context handles many timeline entries efficiently.
        """
        from worker.agents.context_manager import load_analysis_phase_context

        db = AsyncMock()
        investigation_id = str(uuid4())

        # Create 100 mock timeline entries - needs 6 values: entry_id, title, description, entry_type, tags, timestamp
        timeline_entries = [
            (i, f"Event {i}", f"Description {i}", "finding", ["tag"], f"2024-01-01 10:{i:02d}:00")
            for i in range(100)
        ]

        timeline_result = MagicMock()
        timeline_result.fetchall.return_value = timeline_entries

        db.execute.return_value = timeline_result

        context = await load_analysis_phase_context(
            db=db,
            investigation_id=investigation_id,
        )

        assert isinstance(context, str)
        assert len(context) > 0
        # Should include at least some of the entries
        assert "Event" in context
