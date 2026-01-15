"""
Unit tests for InvestigationNote model.
"""

import pytest
from uuid import uuid4

from app.models.investigation_note import InvestigationNote


@pytest.mark.unit
class TestInvestigationNoteModel:
    """Test InvestigationNote model structure."""

    def test_note_creation(self):
        """
        Test creating an InvestigationNote instance.

        This test verifies that an InvestigationNote can be instantiated with explicit values for `note_id`, `investigation_id`, `user_id` and `content`. It asserts that each attribute is set correctly on the resulting object and confirms that the optional `embedding_id` field defaults to `None` when not provided.
        """
        investigation_id = uuid4()

        note = InvestigationNote(
            note_id=1,
            investigation_id=investigation_id,
            user_id=1,
            content="This is a note about the investigation",
        )

        assert note.note_id == 1
        assert note.investigation_id == investigation_id
        assert note.user_id == 1
        assert note.content == "This is a note about the investigation"
        assert note.embedding_id is None

    def test_note_with_embedding(self):
        """
        Test that an InvestigationNote correctly stores and returns its associated embedding identifier when initialized with an embedding_id value. The note is created with sample identifiers and content, then the assertion verifies that the embedding_id attribute equals the provided integer (123). This ensures the model retains the embedding reference as expected.
        """
        note = InvestigationNote(
            note_id=1,
            investigation_id=uuid4(),
            user_id=1,
            content="Note with embedding",
            embedding_id=123,
        )

        assert note.embedding_id == 123

    def test_note_with_long_content(self):
        """
        Test note with very long content.

        Creates an InvestigationNote instance using a string of 10,000 characters as the content and verifies that the `content` attribute length matches the expected size. This ensures the model can handle extremely large text fields without truncation or errors.
        """
        long_content = "A" * 10000

        note = InvestigationNote(
            note_id=1, investigation_id=uuid4(), user_id=1, content=long_content
        )

        assert len(note.content) == 10000

    def test_note_with_markdown_content(self):
        """
        Test that an InvestigationNote correctly stores and preserves Markdown-formatted content.

        The test creates a multiline string containing various Markdown elements (headings, lists, inline code) and initializes an `InvestigationNote` with it. It then asserts that specific Markdown fragments (the "## Findings" heading and the inline code "`admin`") are present in the note's `content` attribute, verifying that the model retains the original formatting without alteration.
        """
        markdown_content = """# Investigation Notes

## Findings
- Suspicious login from 192.168.1.1
- Multiple failed authentication attempts
- User account: `admin`

## Next Steps
1. Analyze network traffic
2. Review user activity logs
3. Check for lateral movement"""

        note = InvestigationNote(
            note_id=1, investigation_id=uuid4(), user_id=1, content=markdown_content
        )

        assert "## Findings" in note.content
        assert "`admin`" in note.content

    def test_note_tablename(self):
        """
        Test that the InvestigationNote model’s table name (__tablename__) is set to “investigation_notes”.
        """
        assert InvestigationNote.__tablename__ == "investigation_notes"

    def test_note_has_required_columns(self):
        """
        Ensures that the `InvestigationNote` model defines every mandatory attribute: `note_id`, `investigation_id`, `user_id`, `content`, `embedding_id`, `created_at` and `updated_at`.
        """
        assert hasattr(InvestigationNote, "note_id")
        assert hasattr(InvestigationNote, "investigation_id")
        assert hasattr(InvestigationNote, "user_id")
        assert hasattr(InvestigationNote, "content")
        assert hasattr(InvestigationNote, "embedding_id")
        assert hasattr(InvestigationNote, "created_at")
        assert hasattr(InvestigationNote, "updated_at")


@pytest.mark.unit
class TestInvestigationNoteEdgeCases:
    """Test edge cases for InvestigationNote model."""

    def test_note_with_unicode_content(self):
        """
        Test that an InvestigationNote correctly stores Unicode characters in its content field, ensuring Japanese text and emoji symbols are preserved without alteration.
        """
        content = """調査メモ

発見事項:
- 不審なログイン 🔍
- 複数の認証失敗 ⚠️

次のステップ:
1. ネットワークトラフィックを分析
2. ユーザーアクティビティログを確認"""

        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content=content)

        assert "調査メモ" in note.content
        assert "🔍" in note.content
        assert "⚠️" in note.content

    def test_note_with_code_blocks(self):
        """
        Test that an `InvestigationNote` instance preserves fenced code block sections within its `content` field. The test creates a note containing Python and SQL code blocks delimited by triple backticks, then verifies that the raw markdown markers (```python and ```sql) are present in the stored content. This ensures that multiline strings with embedded code snippets are handled without alteration.
        """
        content = """Investigation findings:

```python
# Suspicious script found
import os
os.system("rm -rf /")
```

```sql
SELECT * FROM users WHERE password = '123456';
```"""

        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content=content)

        assert "```python" in note.content
        assert "```sql" in note.content

    def test_note_with_special_characters(self):
        """
        Test that an InvestigationNote correctly stores content containing various special characters, including punctuation, backslashes, regular expression patterns, and URLs, and that these substrings are present in the note's content attribute.
        """
        content = """Special chars: !@#$%^&*()_+-=[]{}|;:'",.<>?/~`

Paths: C:\\Windows\\System32\\cmd.exe
Regex: ^[a-zA-Z0-9]+$
URL: https://example.com/api?key=value&token=abc123"""

        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content=content)

        assert "C:\\Windows\\System32\\cmd.exe" in note.content
        assert "^[a-zA-Z0-9]+$" in note.content

    def test_note_with_html_content(self):
        """
        Test that an InvestigationNote correctly stores HTML-like content, ensuring that tags such as <strong> and <script> are preserved in the note's content attribute.
        """
        content = """<strong>Important Finding</strong>

<script>alert('XSS')</script>

<a href="http://malicious.com">Click here</a>"""

        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content=content)

        assert "<strong>" in note.content
        assert "<script>" in note.content

    def test_note_with_newlines_and_tabs(self):
        """
        Test that an InvestigationNote correctly stores content containing newline (`\n`, `\r\n`) and tab (`\t`) characters, verifying those whitespace characters are present in the stored `content` attribute.
        """
        content = "Line 1\nLine 2\r\nLine 3\tTabbed\t\tDouble tab"

        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content=content)

        assert "\n" in note.content
        assert "\t" in note.content

    def test_note_with_empty_content(self):
        """
        Test that creating an `InvestigationNote` with an empty string for `content` correctly initializes the instance and preserves the empty value.\n\nThe test constructs a note using `note_id`, a generated `investigation_id` via `uuid4()`, `user_id` and an empty `content`. It then asserts that the `content` attribute of the resulting object is exactly an empty string. No return value is expected.
        """
        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content="")

        assert note.content == ""

    def test_note_with_json_content(self):
        """
        Test that an InvestigationNote can be created with JSON-formatted text as its content.

        The test constructs a multi-line string containing valid JSON data, instantiates an `InvestigationNote` with this content, and then asserts that key substrings from the JSON (the "findings" field name and one of the tags) are present in the stored `note.content` attribute. This verifies that the model accepts arbitrary text-including JSON-and stores it unchanged.
        """
        content = """{
  "findings": [
    {
      "type": "authentication_failure",
      "count": 42,
      "source_ip": "192.168.1.100"
    }
  ],
  "severity": "high",
  "tags": ["brute_force", "suspicious"]
}"""

        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content=content)

        assert '"findings"' in note.content
        assert '"brute_force"' in note.content

    def test_note_with_multiline_strings(self):
        """
        Test creation of an InvestigationNote using a multiline string as content.

        Ensures that when a note is instantiated with a string containing multiple paragraphs, blank lines, and indented blocks, the `content` attribute preserves the exact formatting, including newline characters and indentation. This validates proper handling of complex multiline text inputs.
        """
        content = """First paragraph with multiple
lines of text that wrap around.

Second paragraph after blank line.

    Indented paragraph
    with multiple lines."""

        note = InvestigationNote(note_id=1, investigation_id=uuid4(), user_id=1, content=content)

        assert content == note.content
