import pytest
from datetime import datetime
from app.models.tool_execution import ToolExecution


@pytest.mark.unit
class TestToolExecutionModel:
    """Test ToolExecution model."""

    def test_create_tool_execution(self):
        """
        Test the creation of a ToolExecution instance with specific fields and verify that its attributes (tool_name, display_name, and status) are set correctly.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="search_timeline",
            display_name="Search Timeline",
            arguments={"query": "suspicious activity"},
            status="executing",
        )

        assert execution.tool_name == "search_timeline"
        assert execution.display_name == "Search Timeline"
        assert execution.status == "executing"

    def test_execution_default_status(self):
        """
        Test that a newly created ToolExecution instance correctly sets its status attribute to the explicitly provided default value "executing".
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="test_tool",
            status="executing",
        )

        assert execution.status == "executing"

    def test_execution_with_arguments(self):
        """
        Test execution with complex arguments.

        This test verifies that a :class:`ToolExecution` instance correctly stores and provides access to nested argument structures. It creates an execution with a dictionary containing a query string, nested filters (including a date range and a list of severity levels), and a limit value. The assertions confirm that the `severity` list and the `limit` integer are preserved accurately within the `arguments` attribute.
        """
        arguments = {
            "query": "test",
            "filters": {
                "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                "severity": ["high", "critical"],
            },
            "limit": 100,
        }

        execution = ToolExecution(
            chat_message_id=1,
            tool_name="search_events",
            arguments=arguments,
        )

        assert execution.arguments["filters"]["severity"] == ["high", "critical"]
        assert execution.arguments["limit"] == 100

    def test_execution_with_result(self):
        """
        Test that a ToolExecution instance correctly stores and exposes result data, including nested structures, total count, event list length, and the associated result summary when initialized with explicit result information.
        """
        result = {
            "events": [
                {"id": 1, "description": "Event 1"},
                {"id": 2, "description": "Event 2"},
            ],
            "total": 2,
        }

        execution = ToolExecution(
            chat_message_id=1,
            tool_name="search_timeline",
            result=result,
            result_summary="Found 2 events",
            status="completed",
        )

        assert execution.result["total"] == 2
        assert len(execution.result["events"]) == 2
        assert execution.result_summary == "Found 2 events"

    def test_execution_completed_status(self):
        """
        Test that a ToolExecution instance initialized with a completed status correctly reflects the status and records a non-null finished timestamp. This verifies that the model stores the provided status value and that the `finished_at` attribute is set when supplied.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="test_tool",
            status="completed",
            finished_at=datetime.utcnow(),
        )

        assert execution.status == "completed"
        assert execution.finished_at is not None

    def test_execution_failed_status(self):
        """
        Test that a ToolExecution instance correctly records a failed status and includes error information in its result dictionary. The test creates a ToolExecution with status set to "failed" and a result containing an error message, then asserts that the status attribute equals "failed" and that the result dictionary contains the key "error".
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="test_tool",
            status="failed",
            result={"error": "Tool execution failed"},
        )

        assert execution.status == "failed"
        assert "error" in execution.result

    def test_execution_with_progress(self):
        """
        Test that a ToolExecution instance correctly stores and reports progress-related attributes. The test creates a ToolExecution with specific `execution_number` and `max_tools` values, then asserts that these fields are set to the expected integers, confirming proper handling of progress tracking metadata.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="bulk_operation",
            execution_number=3,
            max_tools=10,
        )

        assert execution.execution_number == 3
        assert execution.max_tools == 10

    def test_execution_minimal(self):
        """
        Test that creating a ToolExecution instance with only the required fields sets optional attributes to their default `None` values and correctly stores the provided `tool_name`. The test verifies that `chat_message_id` is accepted, `tool_name` is retained, and that `display_name`, `arguments`, and `result` are all `None` when not supplied.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="minimal_tool",
        )

        assert execution.tool_name == "minimal_tool"
        assert execution.display_name is None
        assert execution.arguments is None
        assert execution.result is None

    def test_execution_display_name(self):
        """
        Test that a ToolExecution instance correctly stores and returns a custom display_name value when provided during initialization.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="search_timeline",
            display_name="🔍 Search Timeline",
        )

        assert execution.display_name == "🔍 Search Timeline"

    def test_execution_unicode_tool_name(self):
        """
        Test that a ToolExecution instance correctly stores and returns a tool name containing Unicode characters.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="検索_timeline",
        )

        assert execution.tool_name == "検索_timeline"

    def test_execution_large_result(self):
        """
        Test that a ToolExecution instance can store and retrieve a large result payload.

        This test creates a dictionary containing 1 000 event entries and passes it as the `result` argument when constructing a :class:`ToolExecution`. It then asserts that the stored `result` retains all events, confirming that the model correctly handles large data structures without truncation or loss.
        """
        large_result = {"events": [{"id": i, "data": f"Event {i}"} for i in range(1000)]}

        execution = ToolExecution(
            chat_message_id=1,
            tool_name="bulk_search",
            result=large_result,
        )

        assert len(execution.result["events"]) == 1000

    def test_execution_null_arguments(self):
        """
        Test that a ToolExecution instance can be created with `arguments` set to `None` and that the attribute is stored unchanged. The test constructs a `ToolExecution` using minimal required fields, explicitly passing `arguments=None`, and then asserts that the resulting object's `arguments` attribute is `None`. This verifies that the model correctly handles null argument values without raising errors or converting them to another type.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="test_tool",
            arguments=None,
        )

        assert execution.arguments is None

    def test_execution_empty_result(self):
        """
        Test that a ToolExecution instance correctly records an empty result dictionary.

        The test creates a ToolExecution object with `chat_message_id` set to 1, `tool_name` set to `"test_tool"`, an empty dictionary for `result`, and a status of `"completed"`. It then asserts that the `result` attribute of the created instance is exactly the empty dictionary provided. This verifies that the model does not alter or replace empty result payloads during initialization.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="test_tool",
            result={},
            status="completed",
        )

        assert execution.result == {}

    def test_to_dict_method(self):
        """
        Test converting a `ToolExecution` instance to a dictionary.\n\nCreates a `ToolExecution` object with predefined attributes (including `chat_message_id`, `tool_name`, `display_name`, `arguments` and `status`) and calls its :meth:`to_dict` method. The test then verifies that the resulting dictionary contains the expected `tool_name` and `status` values, ensuring that the serialization correctly reflects these fields.
        """
        execution = ToolExecution(
            chat_message_id=1,
            tool_name="search_timeline",
            display_name="Search Timeline",
            arguments={"query": "test"},
            status="completed",
        )

        result_dict = execution.to_dict()

        assert result_dict["tool_name"] == "search_timeline"
        assert result_dict["status"] == "completed"

    def test_repr_format(self):
        """
        Test that the `__repr__` method of :class:`ToolExecution` returns a string containing the class name and key attribute values. The test creates an instance with a known `execution_id`, `chat_message_id`, `tool_name` and `status` and asserts that the resulting representation includes `"ToolExecution"`, `id=42`, `tool='search_events'`, `status='completed'` and `message_id=1`.
        """
        execution = ToolExecution(
            execution_id=42, chat_message_id=1, tool_name="search_events", status="completed"
        )

        repr_str = repr(execution)

        assert "ToolExecution" in repr_str
        assert "id=42" in repr_str
        assert "tool='search_events'" in repr_str
        assert "status='completed'" in repr_str
        assert "message_id=1" in repr_str
