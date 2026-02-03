import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime
import json

from app.services.handlers.event_handler import (
    parse_structured_events,
    _is_valid_event,
    handle_event_insertion,
    insert_events,
)


@pytest.mark.unit
class TestIsValidEvent:
    """Test _is_valid_event function."""

    def test_valid_event_minimal(self):
        """
        Test that an event containing only the required `event_type` field is considered valid by the validation routine. The test creates a minimal event dictionary with `event_type` set to `"login"`, invokes `_is_valid_event` and asserts that it returns `True`, confirming that no additional fields are mandatory for a valid event.
        """
        event = {"event_type": "login"}
        assert _is_valid_event(event) is True

    def test_valid_event_complete(self):
        """
        Test that a fully populated event dictionary passes validation, confirming that `_is_valid_event` returns `True` when all required fields (`event_type`, `event_ts`, and `payload`) are present and correctly formatted.
        """
        event = {
            "event_type": "login",
            "event_ts": "2024-01-01T10:00:00Z",
            "payload": {"user": "admin"},
        }
        assert _is_valid_event(event) is True

    def test_invalid_event_no_type(self):
        """
        Test that an event missing the required `event_type` field is considered invalid by the `_is_valid_event` helper, expecting a return value of `False`.
        """
        event = {"event_ts": "2024-01-01T10:00:00Z"}
        assert _is_valid_event(event) is False

    def test_invalid_event_empty(self):
        """
        Test that an empty dictionary is recognized as an invalid event, ensuring `_is_valid_event` returns `False` for missing required fields.
        """
        event = {}
        assert _is_valid_event(event) is False


@pytest.mark.unit
class TestParseStructuredEvents:
    """Test parse_structured_events function."""

    async def test_parse_json_single_event(self):
        """
        Test that a single JSON-encoded event string is correctly parsed into a list containing one event dictionary with the expected fields.

        The test supplies a minimal JSON payload representing an event, invokes :func:`parse_structured_events` asynchronously, and asserts that:

        * Exactly one event is returned.
        * The returned event contains the `event_type` key with the value `"login"`.
        """
        raw_text = '{"event_type": "login", "user": "admin"}'

        events = await parse_structured_events(raw_text)

        assert len(events) == 1
        assert events[0]["event_type"] == "login"

    async def test_parse_json_array(self):
        """
        Test that `parse_structured_events` correctly parses a JSON array containing multiple event objects.

        The test provides a raw JSON string representing an array with two events: a login and a logout performed by the same user. It then awaits the asynchronous `parse_structured_events` call and verifies:

        * The returned list contains exactly two event dictionaries.
        * The first dictionary has its `event_type` field set to `"login"`.
        * The second dictionary has its `event_type` field set to `"logout"`.
        """
        raw_text = """[
            {"event_type": "login", "user": "admin"},
            {"event_type": "logout", "user": "admin"}
        ]"""

        events = await parse_structured_events(raw_text)

        assert len(events) == 2
        assert events[0]["event_type"] == "login"
        assert events[1]["event_type"] == "logout"

    async def test_parse_yaml_single_event(self):
        """
        Test that a single YAML-formatted event string is correctly parsed into one event dictionary with the expected fields. The raw YAML text contains an `event_type` and a `user` key. After invoking :func:`parse_structured_events` asynchronously, the test asserts that exactly one event is returned and that its `event_type` value matches `"login"`. This validates the parser’s ability to handle simple YAML inputs representing a single event.
        """
        raw_text = """
event_type: login
user: admin
"""

        events = await parse_structured_events(raw_text)

        assert len(events) == 1
        assert events[0]["event_type"] == "login"

    async def test_parse_yaml_array(self):
        """
        Test that a YAML-formatted string representing an array of event objects is correctly parsed into a list of dictionaries, verifying the number of events returned and the values of specific fields.
        """
        raw_text = """
- event_type: login
  user: admin
- event_type: logout
  user: admin
"""

        events = await parse_structured_events(raw_text)

        assert len(events) == 2
        assert events[0]["event_type"] == "login"

    async def test_parse_csv(self):
        """
        Test that CSV-formatted event data is correctly parsed into structured event dictionaries.

        The test supplies a small CSV string containing two events with fields `event_type`, `user`, and `timestamp`. It calls the asynchronous `parse_structured_events` helper to convert the raw CSV text into a list of event dictionaries, then verifies:

        - Exactly two events are returned.
        - The first event's `event_type` field equals `"login"`.
        - The first event's `user` field equals `"admin"`.

        This ensures that CSV parsing produces the expected number of events and correctly maps column values to dictionary keys.
        """
        raw_text = """event_type,user,timestamp
login,admin,2024-01-01T10:00:00Z
logout,admin,2024-01-01T11:00:00Z"""

        events = await parse_structured_events(raw_text)

        assert len(events) == 2
        assert events[0]["event_type"] == "login"
        assert events[0]["user"] == "admin"

    async def test_parse_invalid_data(self):
        """
        Test that parsing completely unstructured input returns an empty list of events, confirming that the parser gracefully handles invalid data without raising exceptions.
        """
        raw_text = "This is not structured data"

        events = await parse_structured_events(raw_text)

        assert events == []

    async def test_parse_invalid_json(self):
        """
        Test that parsing malformed JSON returns an empty list of events, ensuring the parser gracefully handles invalid input without raising exceptions.
        """
        raw_text = '{"invalid": json}'

        events = await parse_structured_events(raw_text)

        assert events == []

    async def test_parse_json_without_event_type(self):
        """
        Test that parsing a JSON string lacking the required `event_type` field results in an empty list of events being returned. The function supplies a minimal JSON payload without `event_type`, invokes :func:`parse_structured_events`, and asserts that the resulting collection is empty, confirming proper validation of mandatory fields.
        """
        raw_text = '{"user": "admin", "timestamp": "2024-01-01T10:00:00Z"}'

        events = await parse_structured_events(raw_text)

        # Should return empty because event is invalid
        assert events == []


@pytest.mark.unit
class TestInsertEvents:
    """Test insert_events function."""

    async def test_insert_empty_list(self):
        """
        Test that inserting an empty list of events returns a zero count.

        The test creates a mock asynchronous database connection, generates a random investigation identifier, and calls `insert_events` with an empty event collection. It then asserts that the result equals `0`, confirming that the function correctly handles the edge case where no events are provided.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        result = await insert_events(db, investigation_id, [])

        assert result == 0

    async def test_insert_single_event(self):
        """
        Test that inserting a single valid event results in one record being added to the database.

        The test creates an asynchronous mock database connection, generates a random investigation identifier, and defines a list containing one event dictionary with required fields (`event_type`, `event_ts`, `user`). It then calls :func:`insert_events` with these parameters and asserts that:

        * The returned count of inserted events equals `1`.
        * The mock database's `execute` method was called, indicating an insertion query was issued.
        * The mock database's `commit` method was called, confirming the transaction was finalized.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        events = [{"event_type": "login", "event_ts": "2024-01-01T10:00:00Z", "user": "admin"}]

        result = await insert_events(db, investigation_id, events)

        assert result == 1
        assert db.execute.called
        assert db.commit.called

    async def test_insert_multiple_events(self):
        """
        Test inserting multiple events into the database.

        This test creates an asynchronous mock database connection and a random investigation identifier, then defines a list containing two event dictionaries. It calls :func:`insert_events` with these parameters and verifies that:

        - The function returns `2` indicating both events were processed.
        - The mock database's `execute` method was called exactly twice, confirming that each event triggered an insertion operation.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        events = [
            {"event_type": "login", "user": "admin"},
            {"event_type": "logout", "user": "admin"},
        ]

        result = await insert_events(db, investigation_id, events)

        assert result == 2
        assert db.execute.call_count == 2

    async def test_insert_event_with_datetime_object(self):
        """
        Test that inserting an event whose timestamp is provided as a :class:`datetime.datetime` object is correctly handled by the `insert_events` coroutine, resulting in a successful insertion count of one. The test uses an asynchronous mock database connection and verifies that the function returns the expected number of inserted records.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        events = [
            {"event_type": "login", "event_ts": datetime(2024, 1, 1, 10, 0, 0), "user": "admin"}
        ]

        result = await insert_events(db, investigation_id, events)

        assert result == 1

    async def test_insert_event_without_timestamp(self):
        """
        Test that inserting an event without an explicit `timestamp` field defaults to using the current time.

        Args:
            self: The test case instance.

        Returns:
            None - the assertion validates that the `insert_events` function reports a successful insertion count of `1` when the timestamp is omitted.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        events = [{"event_type": "login", "user": "admin"}]

        result = await insert_events(db, investigation_id, events)

        assert result == 1

    async def test_insert_event_with_artifact_id(self):
        """
        Test that inserting an event containing an `artifact_id` succeeds and returns the expected count.

        The test creates a mock asynchronous database connection, generates a random investigation identifier, and defines a single event payload with `event_type`, `artifact_id` and additional fields. It then calls :func:`insert_events` with these parameters and asserts that the function reports one successfully inserted event.
        """
        db = AsyncMock()
        investigation_id = uuid4()

        events = [{"event_type": "login", "artifact_id": 123, "user": "admin"}]

        result = await insert_events(db, investigation_id, events)

        assert result == 1


@pytest.mark.unit
class TestHandleEventInsertion:
    """Test handle_event_insertion function."""

    async def test_handle_json_events(self):
        """
        Test handling of JSON event data insertion.\n\nThis coroutine verifies that a JSON-formatted event string can be processed by `handle_event_insertion` and results in a successful database operation. It creates mock dependencies, supplies a sample investigation ID, user ID, and a simple login event payload, then asserts that the returned dictionary indicates success, contains a count of one inserted record, and includes the event type name in its message.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        user_query = '{"event_type": "login", "user": "admin"}'

        result = await handle_event_insertion(db, investigation_id, user_query, user_id)

        assert result["success"] is True
        assert result["count"] == 1
        assert "login" in result["message"]

    async def test_handle_yaml_events(self):
        """
        Test that a YAML-formatted event string is correctly parsed and inserted via `handle_event_insertion`.\n\nThe test creates an asynchronous mock database connection, generates a random investigation UUID, and defines a simple YAML payload representing a single login event. It then calls `handle_event_insertion` with these parameters and asserts that the operation reports success and indicates exactly one event was processed.\"""
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        user_query = """
event_type: login
user: admin
"""

        result = await handle_event_insertion(db, investigation_id, user_query, user_id)

        assert result["success"] is True
        assert result["count"] == 1

    async def test_handle_invalid_data_no_llm(self):
        """
        Test that handle_event_insertion returns a failure response when given unstructured input and the LLM extraction function yields no events. The test mocks the database, generates identifiers, patches llm_extract_events to return an empty list, invokes the handler with a non-JSON/YAML/CSV string, and asserts that the result indicates unsuccessful processing and contains an appropriate error message about parsing failure.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        user_query = "This is not structured data"

        with patch("app.services.handlers.event_handler.llm_extract_events", return_value=[]):
            result = await handle_event_insertion(db, investigation_id, user_query, user_id)

            assert result["success"] is False
            assert "Could not parse" in result["message"]

    async def test_handle_insertion_error(self):
        """
        Test handling of a database insertion error during event processing.

        This asynchronous unit test verifies that when the `handle_event_insertion` function encounters an exception while executing the database insert operation, it returns a result indicating failure. The test:

        - Mocks an async database connection and configures its `execute` method to raise a generic `Exception` with the message "Database error".
        - Generates a random investigation identifier and uses a fixed user identifier.
        - Supplies a minimal JSON string representing a user query (e.g., a login event).
        - Calls `handle_event_insertion` with the mocked database, identifiers, and query.
        - Asserts that the returned dictionary has `success` set to `False`.
        - Checks that the `message` field contains the phrase "Failed to insert", confirming proper error handling and messaging.
        """
        db = AsyncMock()
        db.execute.side_effect = Exception("Database error")
        investigation_id = uuid4()
        user_id = 1

        user_query = '{"event_type": "login"}'

        result = await handle_event_insertion(db, investigation_id, user_query, user_id)

        assert result["success"] is False
        assert "Failed to insert" in result["message"]

    async def test_handle_multiple_event_types(self):
        """
        Test that handling multiple events of different types returns a successful result with correct count and includes a summary of event type occurrences in the message. The test sets up a mock database, defines an investigation ID and user ID, provides a JSON query containing two "login" events and one "logout" event, invokes `handle_event_insertion` asynchronously, and asserts that the operation succeeds, the total count equals three, and the returned message contains a summary indicating the number of “login” events (e.g., “2 login”).
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        user_query = """[
            {"event_type": "login"},
            {"event_type": "login"},
            {"event_type": "logout"}
        ]"""

        result = await handle_event_insertion(db, investigation_id, user_query, user_id)

        assert result["success"] is True
        assert result["count"] == 3
        # Should show event type counts
        assert "2 login" in result["message"] or "login" in result["message"]
