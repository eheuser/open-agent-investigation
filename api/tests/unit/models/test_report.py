"""
Unit tests for Report model.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.models.report import Report


@pytest.mark.unit
class TestReportModel:
    """Test Report model structure."""

    def test_report_creation_minimal(self):
        """
        Test creating a Report instance with only the required fields and verifying that all attributes are set correctly, including defaulting optional fields such as `user_prompt` to `None`.
        """
        investigation_id = uuid4()

        report = Report(
            report_id=1,
            investigation_id=investigation_id,
            user_id=1,
            title="Investigation Report",
            markdown_content="# Report Content",
            artifacts_count=5,
            timeline_entries_count=10,
            event_types_count=3,
        )

        assert report.report_id == 1
        assert report.investigation_id == investigation_id
        assert report.user_id == 1
        assert report.title == "Investigation Report"
        assert report.markdown_content == "# Report Content"
        assert report.artifacts_count == 5
        assert report.timeline_entries_count == 10
        assert report.event_types_count == 3
        assert report.user_prompt is None

    def test_report_creation_with_user_prompt(self):
        """
        Test that a Report instance correctly stores the provided user_prompt value when instantiated with all required fields. The test creates a Report object with a specific user_prompt string and asserts that the attribute matches the expected prompt.
        """
        investigation_id = uuid4()

        report = Report(
            report_id=1,
            investigation_id=investigation_id,
            user_id=1,
            title="Custom Report",
            markdown_content="# Content",
            user_prompt="Focus on lateral movement",
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert report.user_prompt == "Focus on lateral movement"

    def test_report_with_long_markdown(self):
        """
        Test that a Report instance correctly stores and handles very long markdown content, ensuring the markdown_content length exceeds 10,000 characters.
        """
        long_markdown = "# Report\n\n" + ("## Section\n\nContent\n\n" * 1000)

        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Large Report",
            markdown_content=long_markdown,
            artifacts_count=100,
            timeline_entries_count=500,
            event_types_count=20,
        )

        assert len(report.markdown_content) > 10000

    def test_report_with_zero_counts(self):
        """
        Test that a Report instance correctly stores zero values for artifacts_count, timeline_entries_count, and event_types_count, ensuring these fields can handle and return a count of zero without errors.
        """
        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Empty Report",
            markdown_content="# No data yet",
            artifacts_count=0,
            timeline_entries_count=0,
            event_types_count=0,
        )

        assert report.artifacts_count == 0
        assert report.timeline_entries_count == 0
        assert report.event_types_count == 0

    def test_report_tablename(self):
        """
        Test that the Report model's __tablename__ attribute is set to the expected table name "reports".
        """
        assert Report.__tablename__ == "reports"

    def test_report_has_required_columns(self):
        """
        Test that the Report model defines all mandatory attributes.

        Ensures the Report class includes each required column: `report_id`, `investigation_id`, `user_id`, `title`, `markdown_content`, `user_prompt`, `artifacts_count`, `timeline_entries_count`, `event_types_count`, and `generated_at`. This verification helps catch schema regressions early in the test suite.
        """
        assert hasattr(Report, "report_id")
        assert hasattr(Report, "investigation_id")
        assert hasattr(Report, "user_id")
        assert hasattr(Report, "title")
        assert hasattr(Report, "markdown_content")
        assert hasattr(Report, "user_prompt")
        assert hasattr(Report, "artifacts_count")
        assert hasattr(Report, "timeline_entries_count")
        assert hasattr(Report, "event_types_count")
        assert hasattr(Report, "generated_at")


@pytest.mark.unit
class TestReportEdgeCases:
    """Test edge cases for Report model."""

    def test_report_with_unicode_title(self):
        """
        Test that a Report instance correctly stores and preserves Unicode characters in its title, including Japanese text, an emoji, and Cyrillic script. verifies the title contains each expected substring.
        """
        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="調査レポート 🔍 Отчет",
            markdown_content="# Content",
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert "調査レポート" in report.title
        assert "🔍" in report.title
        assert "Отчет" in report.title

    def test_report_with_unicode_markdown(self):
        """
        Test that a Report instance correctly stores and preserves Unicode characters within its markdown_content field.

        This test creates a markdown string containing Japanese text, emojis, and typical markdown headings. It then instantiates a Report with this content and verifies that the stored markdown_content includes specific Unicode substrings ("調査報告書" and "🚫"), ensuring proper handling of non-ASCII characters.
        """
        markdown = """# 調査報告書

## 概要
この調査では、不審なアクティビティを検出しました。

## 発見事項
1. 認証失敗: 42回 🚫
2. 横方向移動: 検出 ⚠️
3. データ流出: なし ✓

## 推奨事項
- パスワードポリシーの強化
- ログ監視の改善"""

        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Japanese Report",
            markdown_content=markdown,
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert "調査報告書" in report.markdown_content
        assert "🚫" in report.markdown_content

    def test_report_with_code_blocks(self):
        """
        Test that a Report instance correctly retains markdown containing fenced code blocks for SQL and Python, ensuring the original markdown_content includes the expected language identifiers.
        """
        markdown = """# Report

## SQL Query Used
```sql
SELECT * FROM events 
WHERE event_type = 'login' 
AND timestamp > '2024-01-01';
```

## Python Analysis
```python
import pandas as pd
df = pd.read_csv('events.csv')
print(df.describe())
```"""

        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Technical Report",
            markdown_content=markdown,
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert "```sql" in report.markdown_content
        assert "```python" in report.markdown_content

    def test_report_with_tables(self):
        """
        Test that a Report instance correctly stores and preserves markdown tables within its content, ensuring the table header line appears in the `markdown_content` attribute.
        """
        markdown = """# Report

## Event Summary

| Event Type | Count | Severity |
|------------|-------|----------|
| Login      | 42    | Low      |
| Failed Auth| 15    | High     |
| File Access| 8     | Medium   |"""

        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Report with Tables",
            markdown_content=markdown,
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert "| Event Type | Count | Severity |" in report.markdown_content

    def test_report_with_special_chars_in_content(self):
        """
        Test that a Report instance correctly stores markdown content containing various special characters.

        The test creates a multi-line markdown string with backslashes, code fences, regular expression syntax, and URL query parameters, then instantiates a Report using this markdown. It verifies that the raw file path (`C:\Windows\System32\cmd.exe`) and the regular expression pattern (`^[a-zA-Z0-9]+$`) are present unchanged in the `markdown_content` attribute of the created Report object.
        """
        markdown = """# Report

File paths: C:\\Windows\\System32\\cmd.exe

Commands: `powershell.exe -enc <base64>`

Regex: ^[a-zA-Z0-9]+$

URLs: https://example.com/api?key=value&token=abc123"""

        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Report",
            markdown_content=markdown,
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert "C:\\Windows\\System32\\cmd.exe" in report.markdown_content
        assert "^[a-zA-Z0-9]+$" in report.markdown_content

    def test_report_with_very_large_counts(self):
        """
        Test that a Report instance correctly stores and returns very large integer counts for artifacts, timeline entries, and event types. This ensures the model handles high numeric values without overflow or truncation.
        """
        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Large Investigation",
            markdown_content="# Report",
            artifacts_count=999999,
            timeline_entries_count=999999,
            event_types_count=999999,
        )

        assert report.artifacts_count == 999999
        assert report.timeline_entries_count == 999999
        assert report.event_types_count == 999999

    def test_report_with_html_in_markdown(self):
        """
        Test that a Report instance correctly stores markdown content containing embedded HTML tags, including a warning div and an HTML table, and that these raw HTML snippets are preserved unchanged in the `markdown_content` attribute.
        """
        markdown = """# Report

<div class="warning">
<strong>Warning:</strong> Suspicious activity detected!
</div>

<table>
<tr><th>Event</th><th>Count</th></tr>
<tr><td>Login</td><td>42</td></tr>
</table>"""

        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="HTML Report",
            markdown_content=markdown,
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert "<strong>Warning:</strong>" in report.markdown_content
        assert "<table>" in report.markdown_content

    def test_report_with_very_long_title(self):
        """
        Test that a Report instance correctly handles an exceptionally long title by verifying the stored title's length matches the 1000-character input.
        """
        long_title = "A" * 1000

        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title=long_title,
            markdown_content="# Content",
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert len(report.title) == 1000

    def test_report_with_unicode_user_prompt(self):
        """
        Test that a Report instance correctly stores and returns Unicode characters in the user_prompt field, ensuring both Japanese text and emoji are preserved.
        """
        report = Report(
            report_id=1,
            investigation_id=uuid4(),
            user_id=1,
            title="Report",
            markdown_content="# Content",
            user_prompt="重点: 横方向移動パターン 🎯",
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        assert "横方向移動" in report.user_prompt
        assert "🎯" in report.user_prompt

    def test_repr_format(self):
        """
        Test that the `Report` model’s `__repr__` method produces a string containing the class name and key attribute values.

        The test creates a `Report` instance with known field values, calls `repr` on it, and asserts that the resulting representation includes:

        * The word `Report` indicating the class name.
        * The identifier `id=42` confirming the `report_id` is represented.
        * The title `title='Test Report'` showing the `title` attribute.

        This ensures the `__repr__` output follows the expected formatting conventions for debugging and logging.
        """
        inv_id = uuid4()
        report = Report(
            report_id=42,
            investigation_id=inv_id,
            user_id=1,
            title="Test Report",
            markdown_content="# Content",
            artifacts_count=5,
            timeline_entries_count=10,
            event_types_count=3,
        )

        repr_str = repr(report)

        assert "Report" in repr_str
        assert "id=42" in repr_str
        assert "title='Test Report'" in repr_str
