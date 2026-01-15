"""
Unit tests for InvestigationChoice model.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.models.investigation_choice import InvestigationChoice


@pytest.mark.unit
class TestInvestigationChoiceModel:
    """Test InvestigationChoice model structure."""

    def test_choice_creation_minimal(self):
        """
        Test creating an InvestigationChoice instance with only the required fields, verifying that all provided attributes are set correctly and that optional attributes (display_order and selected) remain unset (None), reflecting database defaults.
        """
        investigation_id = uuid4()

        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=investigation_id,
            title="Investigate failed logins",
            description="Analyze authentication failures",
            rationale="Multiple failed attempts detected",
            suggested_query="Find failed login attempts",
            suggested_effort="medium",
        )

        assert choice.choice_id == 1
        assert choice.job_id == 10
        assert choice.investigation_id == investigation_id
        assert choice.title == "Investigate failed logins"
        assert choice.description == "Analyze authentication failures"
        assert choice.rationale == "Multiple failed attempts detected"
        assert choice.suggested_query == "Find failed login attempts"
        assert choice.suggested_effort == "medium"
        assert choice.display_order is None  # Set by database default
        assert choice.selected is None  # Set by database default

    def test_choice_creation_full(self):
        """
        Test creating an InvestigationChoice with all fields populated.

        This test verifies that the model correctly stores each provided argument:
        - Initializes identifiers (choice_id, job_id, investigation_id) and timestamps (created_at, selected_at).
        - Sets textual attributes (title, description, rationale, suggested_query, suggested_effort).
        - Accepts a complex dictionary for tool_suggestions.
        - Handles display order, selection flag, and the ID of the selecting job.

        The assertions confirm that:
        * The `tool_suggestions` attribute matches the input dictionary.
        * The `display_order` is stored as the given integer.
        * The `selected` boolean reflects the provided value.
        * The `selected_at` timestamp equals the supplied datetime.
        * The `selected_job_id` matches the specified identifier.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)
        selected_at = datetime.now(timezone.utc)

        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=investigation_id,
            title="Investigate lateral movement",
            description="Analyze lateral movement patterns",
            rationale="Suspicious network activity detected",
            suggested_query="Find lateral movement indicators",
            suggested_effort="high",
            tool_suggestions={"tools": ["search_events", "aggregate"]},
            display_order=1,
            selected=True,
            selected_at=selected_at,
            selected_job_id=20,
            created_at=created_at,
        )

        assert choice.tool_suggestions == {"tools": ["search_events", "aggregate"]}
        assert choice.display_order == 1
        assert choice.selected is True
        assert choice.selected_at == selected_at
        assert choice.selected_job_id == 20

    def test_choice_effort_levels(self):
        """
        Test that InvestigationChoice correctly stores and returns various suggested effort levels.

        Iterates over a list of effort strings ("low", "medium", "high"), creates an InvestigationChoice instance for each level, and asserts that the `suggested_effort` attribute of the created object matches the input value. This ensures the model accepts and preserves different effort level values without alteration.
        """
        effort_levels = ["low", "medium", "high"]

        for i, effort in enumerate(effort_levels):
            choice = InvestigationChoice(
                choice_id=i + 1,
                job_id=10,
                investigation_id=uuid4(),
                title=f"Choice {i}",
                description="Description",
                rationale="Rationale",
                suggested_query="Query",
                suggested_effort=effort,
            )
            assert choice.suggested_effort == effort

    def test_choice_display_order(self):
        """
        Test that the InvestigationChoice model correctly assigns the provided display_order value.

        Iterates over a range of integers, creates an InvestigationChoice instance with each integer as the display_order, and asserts that the instance's display_order attribute matches the input value. This verifies that the model stores and returns the display order without alteration.
        """
        for i in range(10):
            choice = InvestigationChoice(
                choice_id=i + 1,
                job_id=10,
                investigation_id=uuid4(),
                title=f"Choice {i}",
                description="Description",
                rationale="Rationale",
                suggested_query="Query",
                suggested_effort="medium",
                display_order=i,
            )
            assert choice.display_order == i

    def test_choice_repr(self):
        """
        Test that the string representation of an `InvestigationChoice` instance includes the class name and key attribute values.

        The test creates an `InvestigationChoice` with a representative set of fields, obtains its `repr` output, and asserts that the resulting string contains:

        - The class identifier `InvestigationChoice`
        - The `choice_id` value
        - The `title` value formatted as a quoted string
        - The `selected` flag

        These checks verify that `__repr__` provides a useful, informative representation for debugging and logging purposes.
        """
        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Test Choice",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
            suggested_effort="medium",
            selected=False,
            display_order=0,
        )

        repr_str = repr(choice)
        assert "InvestigationChoice" in repr_str
        assert "choice_id=1" in repr_str
        assert "title='Test Choice'" in repr_str
        assert "selected=False" in repr_str

    def test_choice_tablename(self):
        """
        Ensures that the SQLAlchemy model `InvestigationChoice` defines its table name correctly by asserting that the class attribute `__tablename__` matches the expected string `"investigation_choices"`.
        """
        assert InvestigationChoice.__tablename__ == "investigation_choices"

    def test_choice_has_required_columns(self):
        """
        Test that the InvestigationChoice model defines all required attributes.

        This test verifies the presence of each mandatory column on the InvestigationChoice class, ensuring that fields such as `choice_id`, `job_id`, `investigation_id`, `title`, `description`, `rationale`, `suggested_query`, `suggested_effort`, `tool_suggestions`, `display_order`, `selected`, `selected_at`, `selected_job_id` and `created_at` exist as attributes.
        """
        assert hasattr(InvestigationChoice, "choice_id")
        assert hasattr(InvestigationChoice, "job_id")
        assert hasattr(InvestigationChoice, "investigation_id")
        assert hasattr(InvestigationChoice, "title")
        assert hasattr(InvestigationChoice, "description")
        assert hasattr(InvestigationChoice, "rationale")
        assert hasattr(InvestigationChoice, "suggested_query")
        assert hasattr(InvestigationChoice, "suggested_effort")
        assert hasattr(InvestigationChoice, "tool_suggestions")
        assert hasattr(InvestigationChoice, "display_order")
        assert hasattr(InvestigationChoice, "selected")
        assert hasattr(InvestigationChoice, "selected_at")
        assert hasattr(InvestigationChoice, "selected_job_id")
        assert hasattr(InvestigationChoice, "created_at")


@pytest.mark.unit
class TestInvestigationChoiceEdgeCases:
    """Test edge cases for InvestigationChoice model."""

    def test_choice_with_unicode_title(self):
        """
        Test that an `InvestigationChoice` instance correctly stores a Unicode title containing non-ASCII characters and emojis, ensuring the characters are retained and accessible via the `title` attribute.
        """
        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="調査選択: 横方向移動を分析 🔍",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
            suggested_effort="medium",
        )

        assert "調査選択" in choice.title
        assert "🔍" in choice.title

    def test_choice_with_unicode_description(self):
        """
        Test that an InvestigationChoice instance correctly stores and returns a Unicode description.

        The test creates an InvestigationChoice with a Japanese description containing Unicode characters.
        It verifies that the `description` attribute of the created object includes the expected
        Unicode substring, ensuring proper handling of non-ASCII text in the model.
        """
        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Choice",
            description="詳細な説明: ネットワークトラフィックを分析します",
            rationale="Rationale",
            suggested_query="Query",
            suggested_effort="medium",
        )

        assert "詳細な説明" in choice.description

    def test_choice_with_very_long_query(self):
        """
        Test that an InvestigationChoice instance can be created with an extremely long suggested_query string and that the length of the stored query exceeds 10,000 characters, verifying proper handling of very large text inputs.
        """
        long_query = "Search for " + ("suspicious activity " * 1000)

        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Choice",
            description="Description",
            rationale="Rationale",
            suggested_query=long_query,
            suggested_effort="medium",
        )

        assert len(choice.suggested_query) > 10000

    def test_choice_with_complex_tool_suggestions(self):
        """
        Test that an InvestigationChoice correctly stores and provides access to complex tool suggestion data structures.

        This test constructs a dictionary containing primary and optional tools, associated parameters, and a specific ordering. It creates an InvestigationChoice instance with this dictionary passed as the `tool_suggestions` argument and then verifies that:
        - The `primary_tools` list is stored unchanged.
        - Nested parameter values (e.g., the limit for `search_events`) are correctly preserved and accessible via attribute lookup.
        """
        tool_suggestions = {
            "primary_tools": ["search_events", "aggregate"],
            "optional_tools": ["hybrid_search", "execute_sql"],
            "parameters": {"search_events": {"limit": 100}, "aggregate": {"field": "event_type"}},
            "order": ["search_events", "aggregate", "hybrid_search"],
        }

        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Choice",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
            suggested_effort="medium",
            tool_suggestions=tool_suggestions,
        )

        assert choice.tool_suggestions["primary_tools"] == ["search_events", "aggregate"]
        assert choice.tool_suggestions["parameters"]["search_events"]["limit"] == 100

    def test_choice_with_negative_display_order(self):
        """
        Test that an InvestigationChoice instance correctly retains a negative display_order value when initialized.
        """
        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Choice",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
            suggested_effort="medium",
            display_order=-1,
        )

        assert choice.display_order == -1

    def test_choice_with_special_chars_in_query(self):
        """
        Test that an InvestigationChoice instance correctly stores and preserves a suggested query containing special characters such as SQL keywords, parentheses, comparison operators, and wildcard patterns. The test constructs a multi-line query string with WHERE, AND, OR, LIKE clauses, creates an InvestigationChoice with this query, and asserts that the stored `suggested_query` includes the expected substrings "WHERE" and "LIKE". This verifies proper handling of complex query strings during initialization.
        """
        query = """Find events WHERE user = 'admin' AND (type = 'login' OR type = 'logout')
AND timestamp > '2024-01-01' AND ip_address LIKE '192.168.%'"""

        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Choice",
            description="Description",
            rationale="Rationale",
            suggested_query=query,
            suggested_effort="medium",
        )

        assert "WHERE" in choice.suggested_query
        assert "LIKE" in choice.suggested_query

    def test_choice_selection_tracking(self):
        """
        Test the tracking behavior of selection-related fields on an InvestigationChoice instance, verifying initial default values (selected=False, selected_at=None, selected_job_id=None) and confirming that updates to these attributes correctly reflect a chosen state, timestamp, and associated job identifier.
        """
        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Choice",
            description="Description",
            rationale="Rationale",
            suggested_query="Query",
            suggested_effort="medium",
            selected=False,
            display_order=0,
        )

        # Before selection
        assert choice.selected is False
        assert choice.selected_at is None
        assert choice.selected_job_id is None

        # After selection
        choice.selected = True
        choice.selected_at = datetime.now(timezone.utc)
        choice.selected_job_id = 20

        assert choice.selected is True
        assert choice.selected_at is not None
        assert choice.selected_job_id == 20

    def test_choice_with_markdown_in_description(self):
        """
        Test that an InvestigationChoice correctly stores and preserves markdown formatting in its description field.

        The test creates a multi-line string containing bold headings, bullet points, and italicized text using standard markdown syntax. An InvestigationChoice instance is instantiated with this description along with required fields (choice_id, job_id, investigation_id, title, rationale, suggested_query, suggested_effort). The assertions verify that the raw markdown markers for bold (**...**) and italics (*...*) are present unchanged in the choice.description attribute, confirming that the model does not alter or strip markdown content.
        """
        description = """**Detailed Analysis Required**

This choice will:
- Search for authentication events
- Identify brute force patterns
- Analyze source IPs
- Build timeline of attempts

*Estimated time: 5-10 minutes*"""

        choice = InvestigationChoice(
            choice_id=1,
            job_id=10,
            investigation_id=uuid4(),
            title="Choice",
            description=description,
            rationale="Rationale",
            suggested_query="Query",
            suggested_effort="medium",
        )

        assert "**Detailed Analysis Required**" in choice.description
        assert "*Estimated time: 5-10 minutes*" in choice.description
