"""
Unit tests for event Pydantic schemas.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from app.schemas.event import (
    EventRead,
    EventListResponse,
    EventPasteRequest,
    EventPasteResponse,
)


@pytest.mark.unit
class TestEventRead:
    """Test EventRead schema."""

    def test_event_read_minimal(self):
        """
        Test that an EventRead instance can be created with only the required fields and that all attributes are correctly assigned, verifying minimal valid input handling.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "login",
            "payload": {"username": "admin"},
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert event.event_id == 1
        assert event.event_ts == event_ts
        assert event.artifact_id is None
        assert event.event_type == "login"
        assert event.payload == {"username": "admin"}
        assert event.created_at == created_at

    def test_event_read_with_artifact(self):
        """
        Test that an EventRead instance correctly stores and exposes the provided artifact_id when initialized with valid data, ensuring the artifact identifier is accessible as an attribute on the resulting model object.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": 123,
            "event_type": "file_access",
            "payload": {"path": "/etc/passwd"},
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert event.artifact_id == 123

    def test_event_read_complex_payload(self):
        """
        Test that an :class:`EventRead` instance correctly parses and stores a complex nested payload structure.

        The test creates timestamps for `event_ts` and `created_at` using the current UTC time, then builds a dictionary representing a network event with a multi-level `payload` containing source and destination details, protocol information, byte count, and flag list. An :class:`EventRead` object is instantiated from this data.

        Assertions verify that:
        - The nested `source.ip` field in the payload equals `"192.168.1.1"`.
        - The `flags` list in the payload matches `["SYN", "ACK"]`.

        This ensures that the model handles deep JSON-like structures and preserves their contents accurately.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "network",
            "payload": {
                "source": {"ip": "192.168.1.1", "port": 443},
                "destination": {"ip": "10.0.0.1", "port": 80},
                "protocol": "TCP",
                "bytes": 1024,
                "flags": ["SYN", "ACK"],
            },
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert event.payload["source"]["ip"] == "192.168.1.1"
        assert event.payload["flags"] == ["SYN", "ACK"]

    def test_event_read_missing_required_fields(self):
        """
        Test that constructing an `EventRead` instance without providing any required fields raises a `ValidationError` and that the error details include each missing field: `event_id`, `event_ts`, `event_type`, `payload`, and `created_at`.
        """
        with pytest.raises(ValidationError) as exc_info:
            EventRead()

        errors = exc_info.value.errors()
        error_fields = {error["loc"][0] for error in errors}
        assert "event_id" in error_fields
        assert "event_ts" in error_fields
        assert "event_type" in error_fields
        assert "payload" in error_fields
        assert "created_at" in error_fields

    def test_event_read_empty_payload(self):
        """
        Test that an EventRead instance can be created with an empty payload dictionary and that the resulting object's `payload` attribute equals an empty dict. The test constructs timestamps for `event_ts` and `created_at`, assembles a data dictionary with required fields (including `artifact_id` set to `None` and an unknown `event_type`), instantiates `EventRead` using keyword arguments, and asserts that the `payload` field is preserved as an empty mapping.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "unknown",
            "payload": {},
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert event.payload == {}


@pytest.mark.unit
class TestEventListResponse:
    """Test EventListResponse schema."""

    def test_event_list_with_events(self):
        """
        Test that an EventListResponse correctly stores and reports a list of event dictionaries, verifying the length of the events collection as well as the count and total fields match the provided values.
        """
        events = [{"event_id": 1, "event_type": "login"}, {"event_id": 2, "event_type": "logout"}]

        response = EventListResponse(events=events, count=2, total=100)

        assert len(response.events) == 2
        assert response.count == 2
        assert response.total == 100

    def test_event_list_empty(self):
        """
        Test that an EventListResponse with an empty events list correctly reports zero length, and that its count attribute equals zero. This verifies handling of empty event collections in the response schema.
        """
        response = EventListResponse(events=[], count=0, total=0)

        assert len(response.events) == 0
        assert response.count == 0

    def test_event_list_without_total(self):
        """
        Test that an EventListResponse created without specifying a total returns `None` for its `total` attribute while correctly storing the provided events list and count.
        """
        response = EventListResponse(events=[{"event_id": 1}], count=1)

        assert response.total is None

    def test_event_list_large_dataset(self):
        """
        Test that the EventListResponse correctly handles a large dataset by creating 1,000 event entries, initializing the response with matching count and total values, and asserting that the number of events, the count attribute, and the total attribute are all set as expected.
        """
        events = [{"event_id": i} for i in range(1000)]

        response = EventListResponse(events=events, count=1000, total=10000)

        assert len(response.events) == 1000
        assert response.count == 1000
        assert response.total == 10000


@pytest.mark.unit
class TestEventPasteRequest:
    """Test EventPasteRequest schema."""

    def test_paste_request_json(self):
        """
        Test that an EventPasteRequest instance correctly stores and returns the provided investigation ID, JSON payload string, and format hint. Verifies attribute values match the inputs used during construction.
        """
        request = EventPasteRequest(
            investigation_id="inv-123",
            payload='[{"event": "login", "user": "admin"}]',
            format_hint="json",
        )

        assert request.investigation_id == "inv-123"
        assert request.payload == '[{"event": "login", "user": "admin"}]'
        assert request.format_hint == "json"

    def test_paste_request_csv(self):
        """
        Test that an :class:`EventPasteRequest` correctly stores CSV payload data and format hint.

        The test creates a minimal CSV string containing a header line and one record, then instantiates an `EventPasteRequest` with:
        - `investigation_id` set to `"inv-123"`,
        - `payload` set to the CSV string,
        - `format_hint` set to `"csv"`.

        It asserts that:
        1. The `format_hint` attribute of the request equals `"csv"`, confirming the format hint is preserved.
        2. The CSV header line (`"timestamp,event_type,user"`) appears within the `payload` attribute, verifying that the payload content is stored unchanged.
        """
        csv_data = "timestamp,event_type,user\n2024-01-01,login,admin"
        request = EventPasteRequest(investigation_id="inv-123", payload=csv_data, format_hint="csv")

        assert request.format_hint == "csv"
        assert "timestamp,event_type,user" in request.payload

    def test_paste_request_yaml(self):
        """
        Test that an :class:`EventPasteRequest` correctly handles a YAML payload.\n\nThe test creates a request with a sample YAML string, sets the `format_hint` to `\"yaml\"`, and verifies that the `format_hint` attribute is stored unchanged. This ensures that the model accepts YAML data without alteration or validation errors.
        """
        yaml_data = "events:\n  - type: login\n    user: admin"
        request = EventPasteRequest(
            investigation_id="inv-123", payload=yaml_data, format_hint="yaml"
        )

        assert request.format_hint == "yaml"

    def test_paste_request_no_format_hint(self):
        """
        Test that creating an EventPasteRequest without providing a format_hint results in the format_hint attribute being set to None.
        """
        request = EventPasteRequest(investigation_id="inv-123", payload='{"event": "test"}')

        assert request.format_hint is None

    def test_paste_request_missing_payload(self):
        """
        Test that creating an :class:`EventPasteRequest` without providing the required `payload` field triggers a :class:`pydantic.ValidationError`. The test uses `pytest.raises` to assert that the exception is raised when the model is instantiated with only `investigation_id`. This ensures the schema enforces mandatory payload data.
        """
        with pytest.raises(ValidationError):
            EventPasteRequest(investigation_id="inv-123")

    def test_paste_request_missing_investigation_id(self):
        """
        Test that creating an `EventPasteRequest` without providing the required `investigation_id` field raises a `ValidationError` when the request is instantiated with only a payload.
        """
        with pytest.raises(ValidationError):
            EventPasteRequest(payload='{"test": "data"}')

    def test_paste_request_very_large_payload(self):
        """
        Test paste request with a very large payload.

        Creates an `EventPasteRequest` using a payload composed of many repeated JSON fragments to exceed 100,000 characters, then asserts that the resulting payload length is greater than this threshold, verifying that the model can handle unusually large input strings without errors.
        """
        large_payload = '[{"event": "test"}]' * 10000
        request = EventPasteRequest(investigation_id="inv-123", payload=large_payload)

        assert len(request.payload) > 100000


@pytest.mark.unit
class TestEventPasteResponse:
    """Test EventPasteResponse schema."""

    def test_paste_response_success(self):
        """
        Test that an EventPasteResponse instance correctly reflects a successful paste operation by verifying its status, inserted count, and message fields match the expected values.
        """
        response = EventPasteResponse(
            status="success", inserted=100, message="Successfully inserted 100 events"
        )

        assert response.status == "success"
        assert response.inserted == 100
        assert response.message == "Successfully inserted 100 events"

    def test_paste_response_failure(self):
        """
        Test that an EventPasteResponse with an error status correctly reflects the failure details, including a status of "error", zero inserted count, and the appropriate error message.
        """
        response = EventPasteResponse(status="error", inserted=0, message="Invalid data format")

        assert response.status == "error"
        assert response.inserted == 0
        assert response.message == "Invalid data format"

    def test_paste_response_partial(self):
        """
        Test that an EventPasteResponse with status "partial" correctly reflects partial success.

        The test creates a response object with:
        - `status` set to `"partial"` indicating not all events were inserted.
        - `inserted` set to `50`, representing the number of events successfully added.
        - `message` providing a human-readable summary of the operation.

        It then asserts that:
        1. The `status` attribute matches the expected `"partial"` value.
        2. The `inserted` count is accurately stored as `50`.

        No return value; the test passes if both assertions hold without raising an exception.
        """
        response = EventPasteResponse(
            status="partial", inserted=50, message="Inserted 50 out of 100 events"
        )

        assert response.status == "partial"
        assert response.inserted == 50

    def test_paste_response_without_message(self):
        """
        Test that an :class:`EventPasteResponse` created without a `message` field correctly sets the `message` attribute to `None`. This verifies the optional nature of the `message` attribute in the response schema.
        """
        response = EventPasteResponse(status="success", inserted=10)

        assert response.message is None


@pytest.mark.unit
class TestEventSchemaEdgeCases:
    """Test edge cases for event schemas."""

    def test_event_with_unicode_payload(self):
        """
        Test that an EventRead instance correctly handles Unicode characters in its payload.

        This test creates a sample event with a timestamp and a payload containing Japanese text and an emoji.
        It verifies that the `payload["text"]` field retains the expected Unicode strings after model validation.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "message",
            "payload": {"text": "メッセージ: こんにちは 🌍", "user": "ユーザー"},
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert "こんにちは" in event.payload["text"]
        assert "🌍" in event.payload["text"]

    def test_event_with_special_chars_in_type(self):
        """
        Test that an `EventRead` model correctly preserves an `event_type` containing special characters (e.g., hyphens, underscores, and periods).

        The test creates UTC timestamps for `event_ts` and `created_at`, builds a data dictionary with `event_type` set to `"custom-event_type.v2"`, instantiates the model, and asserts that the stored `event_type` matches the original string.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "custom-event_type.v2",
            "payload": {},
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert event.event_type == "custom-event_type.v2"

    def test_event_payload_with_null_values(self):
        """
        Test that an EventRead instance correctly retains null values in its payload dictionary.

        This test creates timestamps for the event and creation time, constructs a data dictionary with `artifact_id` set to `None` and a nested `payload` containing both `None` and non-null entries. An :class:`EventRead` object is instantiated from this data, and assertions verify that:

        * The payload key `field1` remains `None`.
        * The payload key `field2` retains its string value `"value"`.

        The test ensures the schema allows nullable fields without altering or discarding them during validation.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "test",
            "payload": {"field1": None, "field2": "value", "field3": None},
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert event.payload["field1"] is None
        assert event.payload["field2"] == "value"

    def test_event_payload_with_binary_data(self):
        """
        Test that an event with a binary-like payload is correctly parsed and retains the original string representation.

        The test creates timestamps for `event_ts` and `created_at`, builds a data dictionary containing:
        - `event_id` set to `1`
        - `artifact_id` as `None`
        - `event_type` equal to `"binary"`
        - `payload` with a `data` field holding an escaped binary string (e.g., `\\x00\\x01\\x02\\xff`) and an `encoding` of `"hex"`
        - The generated timestamps

        An :class:`EventRead` instance is instantiated from this dictionary, and the assertion verifies that the `payload["data"]` attribute matches the original escaped binary string. This ensures that the model preserves binary-like data without alteration during validation and serialization.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "binary",
            "payload": {"data": "\\x00\\x01\\x02\\xff", "encoding": "hex"},
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert event.payload["data"] == "\\x00\\x01\\x02\\xff"

    def test_paste_request_with_unicode(self):
        """
        Test that a paste request correctly handles Unicode characters in its payload.

        The test creates an `EventPasteRequest` instance with a JSON-encoded string containing Japanese text and an emoji. It then asserts that both the Japanese characters (テストデータ) and the emoji (🔍) are present in the `payload` attribute, ensuring that Unicode data is preserved during request construction.
        """
        request = EventPasteRequest(
            investigation_id="inv-123", payload='{"message": "テストデータ 🔍"}', format_hint="json"
        )

        assert "テストデータ" in request.payload
        assert "🔍" in request.payload

    def test_paste_request_with_newlines(self):
        """
        Test that an :class:`EventPasteRequest` can be instantiated with a CSV payload containing newline characters, and verify that the newline characters are preserved in the `payload` attribute.
        """
        payload_with_newlines = """event_type,user
login,admin
logout,admin"""

        request = EventPasteRequest(
            investigation_id="inv-123", payload=payload_with_newlines, format_hint="csv"
        )

        assert "\n" in request.payload

    def test_event_list_with_mixed_event_structures(self):
        """
        Test that an EventListResponse correctly handles a list containing heterogeneous event dictionaries.

        The test constructs a mixed list of three events:
        - A login event with `event_id`, `event_type` and `user` fields.
        - A file access event with additional `path` and `mode` keys.
        - A minimal event containing only a boolean `simple` flag.

        It then creates an :class:`EventListResponse` instance using the mixed list, specifying both `count` and `total` as 3. The assertions verify that:
        1. The response contains exactly three events.
        2. The first event retains its `event_type` value of `"login"`.
        3. The second event includes the expected `path` entry of `"/etc/passwd"`.
        4. The third event preserves the `simple` flag set to `True`.

        This ensures that the response model accepts and accurately stores events with varying structures without data loss.
        """
        events = [
            {"event_id": 1, "event_type": "login", "user": "admin"},
            {"event_id": 2, "event_type": "file_access", "path": "/etc/passwd", "mode": "read"},
            {"event_id": 3, "simple": True},
        ]

        response = EventListResponse(events=events, count=3, total=3)

        assert len(response.events) == 3
        assert response.events[0]["event_type"] == "login"
        assert response.events[1]["path"] == "/etc/passwd"
        assert response.events[2]["simple"] is True

    def test_paste_response_with_zero_inserted(self):
        """
        Test that an EventPasteResponse with a status of "error" correctly reports zero inserted events and retains the provided error message.
        """
        response = EventPasteResponse(status="error", inserted=0, message="No valid events found")

        assert response.inserted == 0

    def test_paste_response_with_large_count(self):
        """
        Test that an EventPasteResponse correctly stores and returns a very large inserted count value, ensuring the `inserted` attribute can handle high numeric values without overflow or data loss. The test creates a response with `inserted=1000000` and asserts that this value is retained accurately.
        """
        response = EventPasteResponse(
            status="success", inserted=1000000, message="Successfully inserted 1M events"
        )

        assert response.inserted == 1000000

    def test_event_with_deeply_nested_payload(self):
        """
        Test that an EventRead instance correctly handles a payload containing multiple nested dictionary levels, ensuring the deep value can be accessed through the full hierarchy of keys.
        """
        event_ts = datetime.now(timezone.utc)
        created_at = datetime.now(timezone.utc)

        data = {
            "event_id": 1,
            "event_ts": event_ts,
            "artifact_id": None,
            "event_type": "complex",
            "payload": {
                "level1": {"level2": {"level3": {"level4": {"level5": {"data": "deep value"}}}}}
            },
            "created_at": created_at,
        }

        event = EventRead(**data)

        assert (
            event.payload["level1"]["level2"]["level3"]["level4"]["level5"]["data"] == "deep value"
        )
