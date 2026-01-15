"""
Unit tests for timeline Pydantic schemas.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.timeline import (
    EntryType,
    TimelineEntryCreate,
    TimelineEntryUpdate,
    TimelineEntryRead,
    TimelineNoteCreate,
    TimelineNoteUpdate,
    TimelineNoteRead,
    TimelineResponse,
    TimelineStatsResponse,
)


@pytest.mark.unit
class TestEntryType:
    """Test EntryType enum."""

    def test_entry_type_values(self):
        """
        Test that each member of the EntryType enumeration matches its expected string value, ensuring all defined entry types are correctly set.
        """
        assert EntryType.EVENT == "event"
        assert EntryType.FINDING == "finding"
        assert EntryType.NOTE == "note"
        assert EntryType.OBSERVATION == "observation"

    def test_entry_type_from_string(self):
        """
        Test that converting string literals to :class:`EntryType` enum members yields the correct enum values for each supported entry type. The assertions verify that the `EntryType` constructor correctly maps the strings "event", "finding", "note", and "observation" to their respective enum constants `ENTRY_TYPE.EVENT`, `ENTRY_TYPE.FINDING`, `ENTRY_TYPE.NOTE`, and `ENTRY_TYPE.OBSERVATION`.
        """
        assert EntryType("event") == EntryType.EVENT
        assert EntryType("finding") == EntryType.FINDING
        assert EntryType("note") == EntryType.NOTE
        assert EntryType("observation") == EntryType.OBSERVATION


@pytest.mark.unit
class TestTimelineEntryCreate:
    """Test TimelineEntryCreate schema."""

    def test_create_minimal(self):
        """
        Test creating a minimal timeline entry using the `TimelineEntryCreate` schema.

        The test builds a payload containing only the required fields:

        * `timestamp` - current UTC datetime
        * `entry_type` - string `"event"`
        * `title` - a simple title

        It then instantiates `TimelineEntryCreate` with this data and asserts that:

        * The `timestamp` field is preserved.
        * The `entry_type` enum resolves to :class:`EntryType.EVENT`.
        * The `title` matches the input.
        * Optional fields `event_id` and `description` default to `None`.
        * `data` defaults to an empty dictionary.
        * `tags` defaults to an empty list.
        * `is_visible` defaults to `True`.
        """
        data = {
            "timestamp": datetime.now(timezone.utc),
            "entry_type": "event",
            "title": "Test Entry",
        }

        entry = TimelineEntryCreate(**data)

        assert entry.timestamp == data["timestamp"]
        assert entry.entry_type == EntryType.EVENT
        assert entry.title == "Test Entry"
        assert entry.event_id is None
        assert entry.description is None
        assert entry.data == {}
        assert entry.tags == []
        assert entry.is_visible is True

    def test_create_full(self):
        """
        Test creating a full timeline entry using all available fields.\n\nThe test constructs a `TimelineEntryCreate` instance with a complete set of data, including:\n\n* `event_id` - integer identifier of the related event\n* `timestamp` - aware `datetime` object representing when the entry occurred\n* `entry_type` - string that should be coerced to :class:`EntryType.FINDING`\n* `title` - short descriptive title\n* `description` - longer explanatory text\n* `data` - arbitrary dictionary payload with additional details\n* `tags` - list of tag strings for categorisation\n* `is_visible` - boolean flag indicating visibility status\n\nAfter instantiation, the test asserts that each attribute on the resulting model matches the input values and that the `entry_type` string is correctly converted to the corresponding :class:`EntryType` enum member. This verifies both field validation and default handling for a fully populated timeline entry.
        """
        timestamp = datetime.now(timezone.utc)
        data = {
            "event_id": 123,
            "timestamp": timestamp,
            "entry_type": "finding",
            "title": "Suspicious Activity",
            "description": "Detected unusual login pattern",
            "data": {"ip": "192.168.1.1", "count": 5},
            "tags": ["suspicious", "authentication"],
            "is_visible": True,
        }

        entry = TimelineEntryCreate(**data)

        assert entry.event_id == 123
        assert entry.timestamp == timestamp
        assert entry.entry_type == EntryType.FINDING
        assert entry.title == "Suspicious Activity"
        assert entry.description == "Detected unusual login pattern"
        assert entry.data == {"ip": "192.168.1.1", "count": 5}
        assert entry.tags == ["suspicious", "authentication"]
        assert entry.is_visible is True

    def test_create_missing_required_fields(self):
        """
        Test that constructing a TimelineEntryCreate without providing any required fields raises a ValidationError, and verify that the error locations include the missing 'timestamp', 'entry_type', and 'title' fields.
        """
        with pytest.raises(ValidationError) as exc_info:
            TimelineEntryCreate()

        errors = exc_info.value.errors()
        error_fields = {error["loc"][0] for error in errors}
        assert "timestamp" in error_fields
        assert "entry_type" in error_fields
        assert "title" in error_fields

    def test_create_invalid_entry_type(self):
        """
        Test that creating a TimelineEntryCreate with an unsupported entry_type raises a ValidationError.

        **Steps**
        1. Attempt to instantiate `TimelineEntryCreate` using:
           - `timestamp`: current UTC datetime
           - `entry_type`: a string value not defined in the allowed enum (`"invalid_type"`).
           - `title`: a placeholder title.
        2. Assert that a `ValidationError` is raised by wrapping the call in `pytest.raises`.
        """
        with pytest.raises(ValidationError):
            TimelineEntryCreate(
                timestamp=datetime.now(timezone.utc), entry_type="invalid_type", title="Test"
            )

    def test_create_title_too_short(self):
        """
        Test that creating a TimelineEntryCreate with an empty title triggers a Pydantic ValidationError, ensuring the title field enforces minimum length constraints.
        """
        with pytest.raises(ValidationError):
            TimelineEntryCreate(timestamp=datetime.now(timezone.utc), entry_type="event", title="")

    def test_create_title_too_long(self):
        """
        Test that creating a TimelineEntryCreate with a title longer than the allowed maximum length raises a ValidationError. The title is set to 501 characters, exceeding the defined limit of 500 characters. This verifies that the model enforces its length constraint during validation.
        """
        with pytest.raises(ValidationError):
            TimelineEntryCreate(
                timestamp=datetime.now(timezone.utc),
                entry_type="event",
                title="A" * 501,  # Max is 500
            )

    def test_create_title_max_length(self):
        """
        Test that creating a TimelineEntryCreate with a title exactly at the maximum allowed length (500 characters) succeeds and preserves the full title length.
        """
        entry = TimelineEntryCreate(
            timestamp=datetime.now(timezone.utc), entry_type="event", title="A" * 500
        )
        assert len(entry.title) == 500

    def test_create_with_complex_data(self):
        """
        Test creating a timeline entry using complex nested data structures.

        This test verifies that the `TimelineEntryCreate` model correctly parses and retains
        deeply nested dictionaries, lists, and boolean values provided in the `data`
        field. It constructs an input payload containing:

        * A UTC timestamp.
        * An `entry_type` of `"finding"`.
        * A descriptive title.
        * A `data` dictionary with:
          * A multi-level nested mapping (`nested.level1.level2`) holding a list of strings.
          * An `array` key containing a simple integer list.
          * A `boolean` key set to `True`.

        The test asserts that after model instantiation:

        * The nested list under `data["nested"]["level1"]["level2"]` matches the original
          `["item1", "item2"]`.
        * The `array` field is preserved as `[1, 2, 3]`.
        * The boolean flag remains `True`.

        Ensures that complex payloads are handled without data loss or type errors.
        """
        data = {
            "timestamp": datetime.now(timezone.utc),
            "entry_type": "finding",
            "title": "Complex Data",
            "data": {
                "nested": {"level1": {"level2": ["item1", "item2"]}},
                "array": [1, 2, 3],
                "boolean": True,
            },
        }

        entry = TimelineEntryCreate(**data)
        assert entry.data["nested"]["level1"]["level2"] == ["item1", "item2"]
        assert entry.data["array"] == [1, 2, 3]
        assert entry.data["boolean"] is True


@pytest.mark.unit
class TestTimelineEntryUpdate:
    """Test TimelineEntryUpdate schema."""

    def test_update_all_fields(self):
        """
        Test that updating all fields of a :class:`TimelineEntryUpdate` model correctly assigns the provided values, including timestamp, entry type conversion, title, description, data payload, tags list, and visibility flag. This ensures full-field updates behave as expected.
        """
        timestamp = datetime.now(timezone.utc)
        data = {
            "timestamp": timestamp,
            "entry_type": "observation",
            "title": "Updated Title",
            "description": "Updated description",
            "data": {"key": "value"},
            "tags": ["tag1", "tag2"],
            "is_visible": False,
        }

        update = TimelineEntryUpdate(**data)

        assert update.timestamp == timestamp
        assert update.entry_type == EntryType.OBSERVATION
        assert update.title == "Updated Title"
        assert update.description == "Updated description"
        assert update.data == {"key": "value"}
        assert update.tags == ["tag1", "tag2"]
        assert update.is_visible is False

    def test_update_partial(self):
        """
        Validate that a partial update of a timeline entry correctly sets the supplied field and leaves all other optional fields unset.

        The test creates a `TimelineEntryUpdate` instance with only the `title` argument provided. It then asserts:

        - The `title` attribute matches the given value.
        - All other attributes (`timestamp`, `entry_type`, and `description`) remain `None`, confirming that omitted optional fields are not populated by default.
        """
        update = TimelineEntryUpdate(title="New Title")

        assert update.title == "New Title"
        assert update.timestamp is None
        assert update.entry_type is None
        assert update.description is None

    def test_update_empty(self):
        """
        Test updating a timeline entry with no fields set, ensuring all optional attributes remain None.
        """
        update = TimelineEntryUpdate()

        assert update.timestamp is None
        assert update.entry_type is None
        assert update.title is None

    def test_update_title_validation(self):
        """
        Test that title validation is enforced when updating a timeline entry, ensuring that empty titles and overly long titles raise ValidationError.
        """
        with pytest.raises(ValidationError):
            TimelineEntryUpdate(title="")  # Too short

        with pytest.raises(ValidationError):
            TimelineEntryUpdate(title="A" * 501)  # Too long


@pytest.mark.unit
class TestTimelineEntryRead:
    """Test TimelineEntryRead schema."""

    def test_read_full(self):
        """
        Test that a fully populated :class:`TimelineEntryRead` model correctly assigns all provided fields, including identifiers, timestamps, metadata, and an empty notes list.
        """
        now = datetime.now(timezone.utc)
        investigation_id = str(uuid4())

        data = {
            "entry_id": 1,
            "investigation_id": investigation_id,
            "event_id": 123,
            "timestamp": now,
            "entry_type": "event",
            "title": "Test Entry",
            "description": "Description",
            "data": {"key": "value"},
            "tags": ["tag1"],
            "created_by_user_id": 1,
            "created_at": now,
            "updated_at": now,
            "is_visible": True,
            "notes": [],
        }

        entry = TimelineEntryRead(**data)

        assert entry.entry_id == 1
        assert entry.investigation_id == investigation_id
        assert entry.event_id == 123
        assert entry.title == "Test Entry"
        assert entry.notes == []

    def test_read_with_notes(self):
        """
        Test that a :class:`~app.models.timeline.TimelineEntryRead` instance correctly parses and exposes note data.

        The test constructs a timeline entry payload containing a single note, instantiates the model with `TimelineEntryRead(**data)`, and verifies:

        * The `notes` collection on the resulting object contains exactly one element.
        * The note’s `note_text` field matches the supplied value (`"Note 1"`).
        * The note’s `username` field is correctly populated (`"analyst1"```).
        """
        now = datetime.now(timezone.utc)

        data = {
            "entry_id": 1,
            "investigation_id": str(uuid4()),
            "event_id": None,
            "timestamp": now,
            "entry_type": "finding",
            "title": "Entry with Notes",
            "description": None,
            "data": {},
            "tags": [],
            "created_by_user_id": 1,
            "created_at": now,
            "updated_at": now,
            "is_visible": True,
            "notes": [
                {
                    "note_id": 1,
                    "entry_id": 1,
                    "user_id": 1,
                    "note_text": "Note 1",
                    "created_at": now,
                    "updated_at": now,
                    "username": "analyst1",
                }
            ],
        }

        entry = TimelineEntryRead(**data)

        assert len(entry.notes) == 1
        assert entry.notes[0].note_text == "Note 1"
        assert entry.notes[0].username == "analyst1"


@pytest.mark.unit
class TestTimelineNoteCreate:
    """Test TimelineNoteCreate schema."""

    def test_create_note(self):
        """
        Test that a TimelineNoteCreate instance correctly stores the provided note text.
        """
        note = TimelineNoteCreate(note_text="This is a note")

        assert note.note_text == "This is a note"

    def test_create_note_empty(self):
        """
        Test that creating a TimelineNoteCreate with an empty note_text raises a ValidationError, ensuring the model enforces non-empty content.
        """
        with pytest.raises(ValidationError):
            TimelineNoteCreate(note_text="")

    def test_create_note_long_text(self):
        """
        Test creating a note with an extremely long text string, verifying that the `TimelineNoteCreate` model accepts the input without truncation and that the stored `note_text` retains the expected length of 10,000 characters.
        """
        long_text = "A" * 10000
        note = TimelineNoteCreate(note_text=long_text)

        assert len(note.note_text) == 10000


@pytest.mark.unit
class TestTimelineNoteUpdate:
    """Test TimelineNoteUpdate schema."""

    def test_update_note(self):
        """
        Test that a :class:`TimelineNoteUpdate` instance correctly stores the provided `note_text` value when updated.
        """
        update = TimelineNoteUpdate(note_text="Updated note")

        assert update.note_text == "Updated note"

    def test_update_note_empty(self):
        """
        Test that providing an empty `note_text` when updating a timeline note raises a :class:`pydantic.ValidationError`.
        """
        with pytest.raises(ValidationError):
            TimelineNoteUpdate(note_text="")


@pytest.mark.unit
class TestTimelineNoteRead:
    """Test TimelineNoteRead schema."""

    def test_read_note(self):
        """
        Test that a TimelineNoteRead instance correctly parses and exposes all expected fields when instantiated with valid data, ensuring attribute values match the input dictionary.
        """
        now = datetime.now(timezone.utc)

        data = {
            "note_id": 1,
            "entry_id": 1,
            "user_id": 1,
            "note_text": "Test note",
            "created_at": now,
            "updated_at": now,
            "username": "analyst1",
        }

        note = TimelineNoteRead(**data)

        assert note.note_id == 1
        assert note.entry_id == 1
        assert note.user_id == 1
        assert note.note_text == "Test note"
        assert note.username == "analyst1"

    def test_read_note_without_username(self):
        """
        Test that a TimelineNoteRead instance correctly sets the `username` attribute to `None` when the input data does not include a username field. The test creates a note with required fields, instantiates the model, and asserts that `note.username` is `None`.
        """
        now = datetime.now(timezone.utc)

        data = {
            "note_id": 1,
            "entry_id": 1,
            "user_id": 1,
            "note_text": "Test note",
            "created_at": now,
            "updated_at": now,
        }

        note = TimelineNoteRead(**data)

        assert note.username is None


@pytest.mark.unit
class TestTimelineResponse:
    """Test TimelineResponse schema."""

    def test_timeline_response(self):
        """
        Test that a TimelineResponse correctly serializes a list containing a single timeline entry and preserves pagination metadata.

        Creates a mock timeline entry with realistic field values, constructs a TimelineResponse using this entry list, and asserts that:
        - The response contains exactly one entry.
        - The total count matches the number of entries.
        - The pagination limit and offset are set to the provided values.
        """
        now = datetime.now(timezone.utc)
        investigation_id = str(uuid4())

        entries = [
            {
                "entry_id": 1,
                "investigation_id": investigation_id,
                "event_id": None,
                "timestamp": now,
                "entry_type": "event",
                "title": "Entry 1",
                "description": None,
                "data": {},
                "tags": [],
                "created_by_user_id": 1,
                "created_at": now,
                "updated_at": now,
                "is_visible": True,
                "notes": [],
            }
        ]

        response = TimelineResponse(entries=entries, total=1, limit=10, offset=0)

        assert len(response.entries) == 1
        assert response.total == 1
        assert response.limit == 10
        assert response.offset == 0

    def test_timeline_response_empty(self):
        """
        Test that a TimelineResponse with an empty entries list correctly reports zero entries and a total count of zero. This verifies handling of empty result sets and ensures default pagination fields are set as expected.
        """
        response = TimelineResponse(entries=[], total=0, limit=10, offset=0)

        assert len(response.entries) == 0
        assert response.total == 0


@pytest.mark.unit
class TestTimelineStatsResponse:
    """Test TimelineStatsResponse schema."""

    def test_stats_response(self):
        """
        Test that a :class:`TimelineStatsResponse` instance correctly stores and exposes its fields.

        The test creates a `TimelineStatsResponse` with specific values for total entries, entry counts by type, date range, tags, and total notes, then asserts that each attribute matches the expected value. This verifies proper model initialization, field assignment, and data integrity.
        """
        now = datetime.now(timezone.utc)

        stats = TimelineStatsResponse(
            total_entries=10,
            entries_by_type={"event": 5, "finding": 3, "note": 2},
            date_range={"start": now, "end": now},
            tags=["suspicious", "authentication", "network"],
            total_notes=15,
        )

        assert stats.total_entries == 10
        assert stats.entries_by_type["event"] == 5
        assert stats.date_range["start"] == now
        assert len(stats.tags) == 3
        assert stats.total_notes == 15

    def test_stats_response_empty_date_range(self):
        """
        Test that a `TimelineStatsResponse` instance correctly represents an empty statistics payload when no date range is provided, ensuring that `total_entries` is zero, the `date_range` dictionary contains `None` for both start and end keys, and other collection fields are initialized as empty.
        """
        stats = TimelineStatsResponse(
            total_entries=0,
            entries_by_type={},
            date_range={"start": None, "end": None},
            tags=[],
            total_notes=0,
        )

        assert stats.total_entries == 0
        assert stats.date_range["start"] is None
        assert stats.date_range["end"] is None


@pytest.mark.unit
class TestTimelineSchemaEdgeCases:
    """Test edge cases for timeline schemas."""

    def test_entry_with_unicode_title(self):
        """
        Test that a `TimelineEntryCreate` instance correctly stores and preserves Unicode characters in its `title` attribute, verifying that both Japanese text and emoji are retained as expected.
        """
        entry = TimelineEntryCreate(
            timestamp=datetime.now(timezone.utc),
            entry_type="event",
            title="タイムライン エントリー 🔍",
        )

        assert "タイムライン" in entry.title
        assert "🔍" in entry.title

    def test_entry_with_unicode_description(self):
        """
        Test that creating a :class:`TimelineEntryCreate` with Unicode characters in the `description` field preserves those characters, ensuring they are stored and accessible correctly.
        """
        entry = TimelineEntryCreate(
            timestamp=datetime.now(timezone.utc),
            entry_type="event",
            title="Test",
            description="説明 Description 描述",
        )

        assert "説明" in entry.description

    def test_entry_with_special_chars_in_data(self):
        """
        Test that a TimelineEntryCreate instance correctly stores and preserves special characters within its data dictionary, ensuring strings containing escaped quotes, backslashes, and regular expression patterns remain unchanged after model initialization.
        """
        entry = TimelineEntryCreate(
            timestamp=datetime.now(timezone.utc),
            entry_type="event",
            title="Test",
            data={
                "command": 'cmd.exe /c "echo test"',
                "path": "C:\\Users\\Admin\\file.txt",
                "regex": "^[a-z]+$",
            },
        )

        assert entry.data["command"] == 'cmd.exe /c "echo test"'
        assert entry.data["path"] == "C:\\Users\\Admin\\file.txt"

    def test_entry_with_empty_tags_list(self):
        """
        Test that creating a `TimelineEntryCreate` instance with an explicitly empty list for `tags` preserves the empty list without defaulting or raising errors. The entry is instantiated with required fields and `tags=[]`, then the assertion verifies that `entry.tags` equals an empty list.
        """
        entry = TimelineEntryCreate(
            timestamp=datetime.now(timezone.utc), entry_type="event", title="Test", tags=[]
        )

        assert entry.tags == []

    def test_entry_with_duplicate_tags(self):
        """
        Test that creating a TimelineEntryCreate with duplicate tags preserves all provided tag values without automatic deduplication; verifies the length of the tags list remains equal to the number of input entries.
        """
        entry = TimelineEntryCreate(
            timestamp=datetime.now(timezone.utc),
            entry_type="event",
            title="Test",
            tags=["tag1", "tag2", "tag1"],
        )

        # Schema doesn't deduplicate - that's application logic
        assert len(entry.tags) == 3

    def test_note_with_very_long_text(self):
        """
        Test that creating a `TimelineNoteCreate` instance with an extremely long `note_text` correctly stores the full string without truncation, verifying that the length of `note_text` matches the expected 100 000 characters.
        """
        long_text = "A" * 100000
        note = TimelineNoteCreate(note_text=long_text)

        assert len(note.note_text) == 100000

    def test_stats_with_many_tags(self):
        """
        Test that the `TimelineStatsResponse` correctly stores a large number of tags.

        This test creates a list containing 100 distinct tag strings, constructs a
        `TimelineStatsResponse` instance with those tags, and asserts that the
        `tags` attribute on the resulting object contains exactly 100 entries.
        """
        tags = [f"tag{i}" for i in range(100)]
        stats = TimelineStatsResponse(
            total_entries=100,
            entries_by_type={"event": 100},
            date_range={"start": None, "end": None},
            tags=tags,
            total_notes=0,
        )

        assert len(stats.tags) == 100
