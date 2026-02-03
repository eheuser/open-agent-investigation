import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from app.services.report_generator import (
    _parse_narrative_sections,
    _build_markdown_report,
)


@pytest.mark.unit
class TestParseNarrativeSections:
    """Test _parse_narrative_sections function."""

    def test_parse_all_sections(self):
        """
        Test that the narrative parser correctly extracts all defined sections from a complete markdown document.

        The test provides a sample content string containing an executive summary, key findings, and recommendations, each marked with a level-2 heading (e.g., `## Executive Summary`). It then calls :func:`_parse_narrative_sections` to obtain a dictionary of parsed sections.

        Assertions verify that:
        - The resulting dictionary includes the expected keys (`executive_summary`, `findings`, and `recommendations`).
        - Each key contains the appropriate excerpt from the original content, confirming that multiline text and list items are captured accurately.
        """
        content = """
## Executive Summary

This is the executive summary.
It has multiple lines.

## Key Findings

- Finding 1
- Finding 2

## Recommendations

- Recommendation 1
- Recommendation 2
"""

        sections = _parse_narrative_sections(content)

        assert "executive_summary" in sections
        assert "This is the executive summary" in sections["executive_summary"]
        assert "Finding 1" in sections["findings"]
        assert "Recommendation 1" in sections["recommendations"]

    def test_parse_with_single_hash_headers(self):
        """
        Test that `_parse_narrative_sections` correctly extracts content from a narrative string containing single-hash (`#`) headings for the standard sections (Executive Summary, Findings, Recommendations). The test supplies a multiline markdown-style `content` variable with each heading followed by its respective paragraph text, invokes the parser, and asserts that the returned dictionary contains the expected substrings under the keys `"executive_summary"`, `"findings"`, and `"recommendations"`. This ensures proper handling of simple single-level headers.
        """
        content = """
# Executive Summary

Summary text here.

# Findings

Finding text here.

# Recommendations

Recommendation text here.
"""

        sections = _parse_narrative_sections(content)

        assert "Summary text here" in sections["executive_summary"]
        assert "Finding text here" in sections["findings"]
        assert "Recommendation text here" in sections["recommendations"]

    def test_parse_with_missing_sections(self):
        """
        Test that _parse_narrative_sections correctly handles content where only the Executive Summary section is present, ensuring missing sections (findings and recommendations) are returned as empty strings while the provided summary is captured.
        """
        content = """
## Executive Summary

Only summary provided.
"""

        sections = _parse_narrative_sections(content)

        assert "Only summary provided" in sections["executive_summary"]
        assert sections["findings"] == ""
        assert sections["recommendations"] == ""

    def test_parse_empty_content(self):
        """
        Test that parsing an empty narrative string returns empty sections for executive summary, findings, and recommendations. The function verifies that `_parse_narrative_sections` handles a lack of content without raising errors and produces dictionary entries with empty strings for each expected key.
        """
        content = ""

        sections = _parse_narrative_sections(content)

        assert sections["executive_summary"] == ""
        assert sections["findings"] == ""
        assert sections["recommendations"] == ""

    def test_parse_case_insensitive(self):
        """
        Test that the narrative parser treats section headers case-insensitively, correctly extracting the executive summary and findings regardless of header capitalisation. The function supplies a markdown string with mixed-case headings, invokes `_parse_narrative_sections` and asserts that the expected text appears in the corresponding dictionary entries for `executive_summary` and `findings`.
        """
        content = """
## EXECUTIVE SUMMARY

Summary in caps.

## key findings

Findings in lowercase.
"""

        sections = _parse_narrative_sections(content)

        assert "Summary in caps" in sections["executive_summary"]
        assert "Findings in lowercase" in sections["findings"]


@pytest.mark.unit
class TestBuildMarkdownReport:
    """Test _build_markdown_report function."""

    def test_build_complete_report(self):
        """
        Test case that verifies the full Markdown report generation workflow using realistic input data.

        The test constructs a complete set of inputs required by `_build_markdown_report`:

        * **investigation_title** - a short title for the investigation.
        * **investigation_created** - a `datetime` instance representing when the investigation was created.
        * **artifacts** - a list containing a single artifact dictionary with keys `filename`, `classification`, `size_bytes` and `sha256`. The hash is 64 characters long to emulate a real SHA-256 value.
        * **timeline_entries** - a list with one timeline entry that includes a timestamp, type, title, description and a list of tags.
        * **event_counts** - a mapping of event identifiers to occurrence counts, exercising the report’s event-type summary section.
        * **narrative** - a dictionary supplying executive-summary, findings and recommendations text.

        The function under test is called with these arguments and the resulting string is examined for the presence of expected Markdown headings and content fragments:

        * The top-level title `# Investigation Report: Test Investigation`.
        * Section headings `## 1. Executive Summary`, `## 2. Investigation Scope & Artifacts`,
          `## 3. Timeline Narrative`, `## 4. Findings & ATT&CK Mapping` and
          `## 5. Recommendations`.
        * The artifact filename `test.evtx` appears in the scope section.
        * The timeline entry title `Suspicious Login` is included.
        * Narrative text for executive summary, findings and recommendations matches the supplied values.

        The assertions confirm that the generated report contains all required sections and correctly incorporates the provided data.
        """
        investigation_title = "Test Investigation"
        investigation_created = datetime(2024, 1, 1, 10, 0, 0)

        artifacts = [
            {
                "filename": "test.evtx",
                "classification": "evtx",
                "size_bytes": 1024 * 1024,  # 1 MB
                "sha256": "abcd1234" * 8,  # 64 chars
            }
        ]

        timeline_entries = [
            {
                "timestamp": datetime(2024, 1, 1, 12, 0, 0),
                "type": "event",
                "title": "Suspicious Login",
                "description": "Login from unusual IP",
                "tags": ["suspicious", "login"],
            }
        ]

        event_counts = {"evtx_security_4624": 100, "evtx_sysmon_1": 50}

        narrative = {
            "executive_summary": "Test summary",
            "findings": "Test findings",
            "recommendations": "Test recommendations",
        }

        report = _build_markdown_report(
            investigation_title=investigation_title,
            investigation_created=investigation_created,
            artifacts=artifacts,
            timeline_entries=timeline_entries,
            event_counts=event_counts,
            narrative=narrative,
        )

        # Verify report structure
        assert "# Investigation Report: Test Investigation" in report
        assert "## 1. Executive Summary" in report
        assert "Test summary" in report
        assert "## 2. Investigation Scope & Artifacts" in report
        assert "test.evtx" in report
        assert "## 3. Timeline Narrative" in report
        assert "Suspicious Login" in report
        assert "## 4. Findings & ATT&CK Mapping" in report
        assert "Test findings" in report
        assert "## 5. Recommendations" in report
        assert "Test recommendations" in report

    def test_build_report_with_no_artifacts(self):
        """
        Test that building a markdown report with no artifacts and no timeline entries produces a correctly formatted header and zero counts.

        The test invokes `_build_markdown_report` with:
        - An investigation title of `"Empty Investigation"`
        - A creation timestamp of `datetime(2024, 1, 1, 10, 0, 0)`
        - Empty lists for `artifacts` and `timeline_entries`
        - An empty dictionary for `event_counts`
        - A minimal narrative containing an executive summary, findings, and recommendations

        It then asserts that the generated report includes:
        - The investigation title in a level-1 heading
        - The artifact count displayed as `0`
        - The timeline entry count displayed as `0`
        """
        report = _build_markdown_report(
            investigation_title="Empty Investigation",
            investigation_created=datetime(2024, 1, 1, 10, 0, 0),
            artifacts=[],
            timeline_entries=[],
            event_counts={},
            narrative={
                "executive_summary": "Summary",
                "findings": "None",
                "recommendations": "None",
            },
        )

        assert "# Investigation Report: Empty Investigation" in report
        assert "**Artifacts Analyzed**: 0" in report
        assert "**Timeline Entries**: 0" in report

    def test_build_report_with_no_timeline(self):
        """
        Test that the markdown report generator correctly handles cases where no timeline entries are provided, ensuring the output contains the placeholder "*No timeline entries recorded.*" and includes the supplied narrative sections.
        """
        report = _build_markdown_report(
            investigation_title="No Timeline",
            investigation_created=datetime(2024, 1, 1, 10, 0, 0),
            artifacts=[],
            timeline_entries=[],
            event_counts={},
            narrative={
                "executive_summary": "Summary",
                "findings": "None",
                "recommendations": "None",
            },
        )

        assert "*No timeline entries recorded.*" in report

    def test_build_report_formats_timestamps(self):
        """
        Test that timestamps within timeline entries are correctly formatted in the generated markdown report.

        Creates a single timeline entry with a known datetime value, invokes the internal `_build_markdown_report` helper using a fixed investigation title and creation time, and asserts that the expected timestamp string (`YYYY-MM-DD HH:MM:SS`) appears in the resulting markdown output. This ensures the report generator formats timestamps consistently for readability.
        """
        timeline_entries = [
            {
                "timestamp": datetime(2024, 1, 15, 14, 30, 45),
                "type": "event",
                "title": "Test Event",
                "description": None,
                "tags": [],
            }
        ]

        report = _build_markdown_report(
            investigation_title="Timestamp Test",
            investigation_created=datetime(2024, 1, 1, 10, 0, 0),
            artifacts=[],
            timeline_entries=timeline_entries,
            event_counts={},
            narrative={"executive_summary": "", "findings": "", "recommendations": ""},
        )

        assert "2024-01-15 14:30:45" in report

    def test_build_report_handles_none_timestamp(self):
        """
        Test that the markdown report builder correctly handles timeline entries with a `None` timestamp by inserting the placeholder text `"Unknown Time"`, ensuring that events lacking explicit timestamps are still represented in the generated output.
        """
        timeline_entries = [
            {
                "timestamp": None,
                "type": "event",
                "title": "No Timestamp Event",
                "description": None,
                "tags": [],
            }
        ]

        report = _build_markdown_report(
            investigation_title="None Timestamp Test",
            investigation_created=datetime(2024, 1, 1, 10, 0, 0),
            artifacts=[],
            timeline_entries=timeline_entries,
            event_counts={},
            narrative={"executive_summary": "", "findings": "", "recommendations": ""},
        )

        assert "Unknown Time" in report

    def test_build_report_includes_tags(self):
        """
        Test that the markdown report generated by `_build_markdown_report` includes a formatted list of tags for timeline entries.

        The test creates a single timeline entry with a `tags` field containing two strings (`"critical"` and `"malware"`). It then calls `_build_markdown_report` with minimal required arguments, including empty narrative sections and no artifacts. After the report is built, the test asserts that the string `"**Tags**: critical, malware"` appears in the resulting markdown output, confirming that tag information is correctly rendered in the report.
        """
        timeline_entries = [
            {
                "timestamp": datetime(2024, 1, 1, 12, 0, 0),
                "type": "event",
                "title": "Tagged Event",
                "description": "Description",
                "tags": ["critical", "malware"],
            }
        ]

        report = _build_markdown_report(
            investigation_title="Tags Test",
            investigation_created=datetime(2024, 1, 1, 10, 0, 0),
            artifacts=[],
            timeline_entries=timeline_entries,
            event_counts={},
            narrative={"executive_summary": "", "findings": "", "recommendations": ""},
        )

        assert "**Tags**: critical, malware" in report

    def test_build_report_truncates_sha256(self):
        """
        Test that the Markdown report builder truncates SHA256 hash values when rendering the artifact table.

        Creates a single artifact with a full 64-character SHA256 hash, builds a report using `_build_markdown_report`, and asserts that the resulting Markdown contains only the first sixteen characters of the hash followed by an ellipsis (`aaaaaaaaaaaaaaaa...`). This verifies that long hash strings are shortened for readability in generated reports.
        """
        artifacts = [
            {
                "filename": "test.bin",
                "classification": "binary",
                "size_bytes": 2048,
                "sha256": "a" * 64,  # Full 64-char hash
            }
        ]

        report = _build_markdown_report(
            investigation_title="SHA256 Test",
            investigation_created=datetime(2024, 1, 1, 10, 0, 0),
            artifacts=artifacts,
            timeline_entries=[],
            event_counts={},
            narrative={"executive_summary": "", "findings": "", "recommendations": ""},
        )

        # Should show first 16 chars + "..."
        assert "aaaaaaaaaaaaaaaa..." in report

    def test_build_report_limits_event_types(self):
        """
        Test that the markdown report limits the event-type table to a maximum of fifteen rows.

        The test creates a dictionary with thirty distinct event types (`type_0` through `type_29`) and passes it to the private helper `_build_markdown_report` along with minimal required metadata. After generating the report, the function extracts all lines that begin with a table row marker for an event type (i.e., lines starting with `| `type_`). It then asserts that exactly fifteen such rows are present, confirming that the implementation correctly truncates the event-type section to the configured limit.
        """
        event_counts = {f"type_{i}": i for i in range(30)}  # 30 event types

        report = _build_markdown_report(
            investigation_title="Event Types Test",
            investigation_created=datetime(2024, 1, 1, 10, 0, 0),
            artifacts=[],
            timeline_entries=[],
            event_counts=event_counts,
            narrative={"executive_summary": "", "findings": "", "recommendations": ""},
        )

        # Count table rows (should be 15 + header)
        event_table_lines = [line for line in report.split("\n") if line.startswith("| `type_")]
        assert len(event_table_lines) == 15


@pytest.mark.unit
class TestGenerateInvestigationReport:
    """Test generate_investigation_report function."""

    async def test_investigation_not_found(self):
        """
        Test that the report generator correctly handles the case where the requested investigation does not exist in the database.\n\nThe function mocks an asynchronous database connection and configures the `fetchone` call to return `None`, simulating a missing investigation record. It then invokes :func:`app.services.report_generator.generate_investigation_report` with the mocked DB, a random UUID for the investigation ID, and a sample user ID.\n\nThe test asserts that the returned report dictionary contains an `\"error\"` key and that its value matches the expected error message `\"Investigation not found\"`. This verifies that the service returns a clear, user-friendly error response when the investigation cannot be located.
        """
        from app.services.report_generator import generate_investigation_report

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        # Mock empty result
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        db.execute.return_value = result_mock

        report = await generate_investigation_report(db, investigation_id, user_id)

        assert "error" in report
        assert report["error"] == "Investigation not found"

    async def test_generate_report_without_llm(self):
        """
        Test that the investigation report generator produces a valid markdown output when no LLM client is provided and the database contains an investigation with no associated artifacts, timeline entries, or events.

        The test sets up an asynchronous mock database (`db`) and configures its `execute` method to return:
        - An investigation record containing a title, creation timestamp, and owner ID.
        - Empty result sets for artifacts, timeline entries, and events.

        It then calls `generate_investigation_report` with the mocked database, a random investigation UUID, a user identifier, and `llm_client=None`.

        Assertions verify that:
        - The returned dictionary includes a `markdown` key.
        - The markdown content contains the investigation title.
        - The counts for artifacts and timeline entries are both zero.
        """
        from app.services.report_generator import generate_investigation_report

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        # Mock investigation data
        inv_result = MagicMock()
        inv_result.fetchone.return_value = ("Test Investigation", datetime(2024, 1, 1), 1)

        # Mock empty artifacts, timeline, events
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []

        db.execute.side_effect = [inv_result, empty_result, empty_result, empty_result]

        report = await generate_investigation_report(db, investigation_id, user_id, llm_client=None)

        assert "markdown" in report
        assert "Test Investigation" in report["markdown"]
        assert report["artifacts_count"] == 0
        assert report["timeline_entries_count"] == 0
