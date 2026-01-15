"""
Unit tests for ToolResult model.
"""

import pytest
from uuid import uuid4

from app.models.tool_result import ToolResult


@pytest.mark.unit
class TestToolResultModel:
    """Test ToolResult model structure."""

    def test_tool_result_creation(self):
        """
        Test that a :class:`ToolResult` instance can be created with the expected attributes and default values.

        The test constructs a `ToolResult` using explicit values for `result_id`, `job_id`,
        `investigation_id`, `tool_name` and `payload`. It then asserts that each attribute
        matches the supplied value and that `embedding_id` defaults to `None` when not
        provided. This verifies the model’s basic initialization behavior.
        """
        investigation_id = uuid4()
        payload = {"events": [{"id": 1, "type": "login"}], "count": 1}

        result = ToolResult(
            result_id=1,
            job_id=10,
            investigation_id=investigation_id,
            tool_name="search_events",
            payload=payload,
        )

        assert result.result_id == 1
        assert result.job_id == 10
        assert result.investigation_id == investigation_id
        assert result.tool_name == "search_events"
        assert result.payload == payload
        assert result.embedding_id is None

    def test_tool_result_with_embedding(self):
        """
        Test that a ToolResult instance correctly stores and retrieves its associated embedding identifier. The test creates a ToolResult with a specific embedding_id value and asserts that the attribute matches the provided identifier. This verifies proper handling of the embedding relationship within the model.
        """
        result = ToolResult(
            result_id=1,
            job_id=10,
            investigation_id=uuid4(),
            tool_name="search_events",
            payload={},
            embedding_id=123,
        )

        assert result.embedding_id == 123

    def test_tool_result_different_tools(self):
        """
        Test that ToolResult instances correctly store and expose the tool_name and payload fields for various supported tools.

        Parameters
        ----------
        self : object
            The test case instance.

        The test iterates over a collection of tool identifiers paired with example payload dictionaries, creates a ToolResult for each combination, and asserts that the resulting object's `tool_name` attribute matches the supplied name and that its `payload` attribute equals the provided dictionary. This ensures that different tool types are handled uniformly by the model.
        """
        tools = [
            ("search_events", {"events": [], "count": 0}),
            ("aggregate", {"groups": [], "total": 0}),
            ("query_timeline", {"entries": [], "total": 0}),
            ("hybrid_search", {"results": [], "scores": []}),
            ("execute_sql", {"rows": [], "columns": []}),
        ]

        for i, (tool_name, payload) in enumerate(tools):
            result = ToolResult(
                result_id=i + 1,
                job_id=10,
                investigation_id=uuid4(),
                tool_name=tool_name,
                payload=payload,
            )
            assert result.tool_name == tool_name
            assert result.payload == payload

    def test_tool_result_empty_payload(self):
        """
        Test that creating a ToolResult with an empty payload stores an empty dictionary as its payload attribute.
        """
        result = ToolResult(
            result_id=1, job_id=10, investigation_id=uuid4(), tool_name="test_tool", payload={}
        )

        assert result.payload == {}

    def test_tool_result_complex_payload(self):
        """
        Test the ToolResult model's handling of a complex nested payload structure.

        This test constructs a payload containing multiple layers of dictionaries and lists:
        - An `events` list with event objects that include metadata.
        - An `aggregations` dictionary summarizing counts by user and type.
        - A `summary` dictionary providing total counts, unique user count, and a time range.

        A `ToolResult` instance is created with the payload and typical identifier fields. The test then asserts that:
        - The nested `user` field within the first event equals `"admin"`.
        - The aggregation count for `admin` under `by_user` equals `5`.
        - The overall total in the summary equals `8`.

        These assertions verify that the model correctly stores and provides access to deeply nested JSON-compatible data.
        """
        payload = {
            "events": [
                {
                    "id": 1,
                    "type": "login",
                    "user": "admin",
                    "timestamp": "2024-01-01T10:00:00Z",
                    "metadata": {"ip": "192.168.1.1", "session_id": "abc123"},
                }
            ],
            "aggregations": {
                "by_user": {"admin": 5, "user1": 3},
                "by_type": {"login": 6, "logout": 2},
            },
            "summary": {
                "total": 8,
                "unique_users": 2,
                "time_range": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T23:59:59Z"},
            },
        }

        result = ToolResult(
            result_id=1,
            job_id=10,
            investigation_id=uuid4(),
            tool_name="advanced_search",
            payload=payload,
        )

        assert result.payload["events"][0]["user"] == "admin"
        assert result.payload["aggregations"]["by_user"]["admin"] == 5
        assert result.payload["summary"]["total"] == 8

    def test_tool_result_tablename(self):
        """
        Test that the `ToolResult` model defines its database table name correctly by asserting `ToolResult.__tablename__` equals `"tool_results"`.
        """
        assert ToolResult.__tablename__ == "tool_results"

    def test_tool_result_has_required_columns(self):
        """
        Test that the ToolResult model defines all required columns: result_id, job_id, investigation_id, tool_name, payload, embedding_id, and created_at.
        """
        assert hasattr(ToolResult, "result_id")
        assert hasattr(ToolResult, "job_id")
        assert hasattr(ToolResult, "investigation_id")
        assert hasattr(ToolResult, "tool_name")
        assert hasattr(ToolResult, "payload")
        assert hasattr(ToolResult, "embedding_id")
        assert hasattr(ToolResult, "created_at")


@pytest.mark.unit
class TestToolResultEdgeCases:
    """Test edge cases for ToolResult model."""

    def test_tool_result_with_unicode_tool_name(self):
        """
        Test that a `ToolResult` instance correctly handles a Unicode string for the `tool_name` attribute, ensuring the value is stored unchanged and contains the expected Unicode characters.
        """
        result = ToolResult(
            result_id=1, job_id=10, investigation_id=uuid4(), tool_name="検索_ツール", payload={}
        )

        assert "検索" in result.tool_name

    def test_tool_result_with_unicode_payload(self):
        """
        Test that a `ToolResult` instance correctly stores and preserves Unicode characters in its payload.

        The test creates a payload containing Japanese and Chinese user names and messages with check-mark and cross symbols. It then constructs a `ToolResult` with this payload and asserts that the Unicode strings are present in the stored data, verifying proper handling of non-ASCII text.
        """
        payload = {
            "events": [
                {"user": "ユーザー1", "message": "ログイン成功 ✓"},
                {"user": "用户2", "message": "登录失败 ✗"},
            ]
        }

        result = ToolResult(
            result_id=1, job_id=10, investigation_id=uuid4(), tool_name="search", payload=payload
        )

        assert "ユーザー1" in result.payload["events"][0]["user"]
        assert "✓" in result.payload["events"][0]["message"]

    def test_tool_result_with_large_payload(self):
        """
        Test that a `ToolResult` instance can store and retrieve a very large payload without truncation or errors; constructs a payload containing 10,000 event entries, creates the model with this payload, and asserts that the stored payload retains all events.
        """
        payload = {"events": [{"id": i, "data": f"Event {i}"} for i in range(10000)]}

        result = ToolResult(
            result_id=1,
            job_id=10,
            investigation_id=uuid4(),
            tool_name="bulk_search",
            payload=payload,
        )

        assert len(result.payload["events"]) == 10000

    def test_tool_result_with_null_values(self):
        """
        Test that a ToolResult instance correctly stores payloads containing null values.

        This test creates a payload where some fields are set to `None` (e.g., the `user` field in the first event and the top-level `summary`). It then constructs a `ToolResult` with this payload and asserts that the stored `payload` retains the `None` values in the expected locations.
        """
        payload = {
            "events": [
                {"id": 1, "user": None, "data": "test"},
                {"id": 2, "user": "admin", "data": None},
            ],
            "summary": None,
        }

        result = ToolResult(
            result_id=1, job_id=10, investigation_id=uuid4(), tool_name="search", payload=payload
        )

        assert result.payload["events"][0]["user"] is None
        assert result.payload["summary"] is None

    def test_tool_result_with_boolean_values(self):
        """
        Test that a :class:`ToolResult` correctly stores and preserves boolean values in its payload.

        The payload includes top-level boolean fields `success` and `has_errors` as well as nested boolean flags within an `events` list. The test constructs a `ToolResult` instance with this payload and asserts that the stored payload retains the exact boolean values, ensuring no type coercion or data loss occurs for both top-level and nested boolean entries.
        """
        payload = {
            "success": True,
            "has_errors": False,
            "events": [{"id": 1, "is_suspicious": True}, {"id": 2, "is_suspicious": False}],
        }

        result = ToolResult(
            result_id=1, job_id=10, investigation_id=uuid4(), tool_name="analyze", payload=payload
        )

        assert result.payload["success"] is True
        assert result.payload["has_errors"] is False

    def test_tool_result_with_array_payload(self):
        """
        Test that a `ToolResult` instance correctly stores an array payload at the root level, preserving its type and element count.
        """
        payload = [
            {"id": 1, "type": "event"},
            {"id": 2, "type": "finding"},
            {"id": 3, "type": "note"},
        ]

        result = ToolResult(
            result_id=1,
            job_id=10,
            investigation_id=uuid4(),
            tool_name="list_items",
            payload=payload,
        )

        assert isinstance(result.payload, list)
        assert len(result.payload) == 3

    def test_tool_result_with_special_chars_in_payload(self):
        """
        Test that a `ToolResult` instance correctly stores and retrieves payload values containing special characters such as quotation marks, backslashes, regular-expression syntax, and SQL statements.

        The test constructs a payload dictionary with:
        - A command string that includes escaped double quotes.
        - A Windows file path containing backslashes.
        - A regular-expression pattern.
        - An SQL query string with single quotes and semicolons.

        It then creates a `ToolResult` using the sample payload and asserts that the stored payload preserves the exact special characters for the `command` and `path` keys. This verifies that the model does not alter or truncate strings containing characters that often require escaping.
        """
        payload = {
            "command": 'cmd.exe /c "echo test"',
            "path": "C:\\Windows\\System32\\",
            "regex": "^[a-zA-Z0-9]+$",
            "query": "SELECT * FROM users WHERE name = 'admin';",
        }

        result = ToolResult(
            result_id=1, job_id=10, investigation_id=uuid4(), tool_name="execute", payload=payload
        )

        assert result.payload["command"] == 'cmd.exe /c "echo test"'
        assert result.payload["path"] == "C:\\Windows\\System32\\"

    def test_tool_result_with_nested_arrays(self):
        """
        Test that a `ToolResult` instance correctly stores and retrieves a payload containing deeply nested arrays.

        The payload includes a top-level `"results"` list, each element of which contains a `"group"` identifier and an `"items"` list. Each item holds an `"id"` and a `"tags"` list with multiple string values. The test constructs a `ToolResult` with this payload and asserts that the nested `"tags"` array for the first item in the first result group matches the expected list `["admin", "suspicious"]`. This verifies proper handling of complex, multi-level array structures within the `payload` field.
        """
        payload = {
            "results": [
                {
                    "group": "users",
                    "items": [
                        {"id": 1, "tags": ["admin", "suspicious"]},
                        {"id": 2, "tags": ["user", "normal"]},
                    ],
                },
                {
                    "group": "events",
                    "items": [
                        {"id": 3, "tags": ["login", "success"]},
                        {"id": 4, "tags": ["logout", "timeout"]},
                    ],
                },
            ]
        }

        result = ToolResult(
            result_id=1,
            job_id=10,
            investigation_id=uuid4(),
            tool_name="group_search",
            payload=payload,
        )

        assert result.payload["results"][0]["items"][0]["tags"] == ["admin", "suspicious"]

    def test_tool_result_with_numeric_values(self):
        """
        Test that a `ToolResult` instance correctly stores and retrieves numeric values of various types in its payload.\n\nThe payload includes an integer, a floating-point number, a negative integer, zero, a large integer, and a value expressed in scientific notation. After creating the `ToolResult` with this payload, the test asserts that:\n- The integer value is stored unchanged.\n- The float and scientific notation values are retrieved with approximate equality using `pytest.approx` to account for floating-point representation.\n\nThis ensures that numeric data types are preserved accurately within the model's JSON payload handling.
        """
        payload = {
            "integer": 42,
            "float": 3.14159,
            "negative": -100,
            "zero": 0,
            "large": 9999999999999,
            "scientific": 1.23e-10,
        }

        result = ToolResult(
            result_id=1, job_id=10, investigation_id=uuid4(), tool_name="calculate", payload=payload
        )

        assert result.payload["integer"] == 42
        assert result.payload["float"] == pytest.approx(3.14159)
        assert result.payload["scientific"] == pytest.approx(1.23e-10)
