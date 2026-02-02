import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime
import json

from app.services.handlers.timeline_handler import (
    handle_timeline_query,
    _generate_timeline_summary,
    _execute_timeline_tool,
)


@pytest.mark.unit
class TestHandleTimelineQuery:
    """Test handle_timeline_query function."""

    async def test_no_llm_config(self):
        """
        Test that the timeline query handler correctly detects the absence of an active LLM configuration and returns an appropriate error response.

        The test sets up:
        - A mocked asynchronous database connection.
        - Random `investigation_id` and a fixed `user_id`.
        - Patches `app.services.handlers.timeline_handler.get_active_llm_config` to return `None` (simulating no configured LLM).

        It then calls :func:`handle_timeline_query` with a sample user query and asserts that:
        - The returned dictionary has a `type` key equal to `"error"`.
        - The `message` field contains the phrase `"No active LLM configuration"`, indicating proper error handling.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        with patch(
            "app.services.handlers.timeline_handler.get_active_llm_config", return_value=None
        ):
            result = await handle_timeline_query(
                db=db,
                investigation_id=investigation_id,
                user_query="Show timeline entries",
                user_id=user_id,
            )

            # Verify error response
            assert result["type"] == "error"
            assert "No active LLM configuration" in result["message"]

    async def test_handles_exception(self):
        """
        Test that the timeline query handler correctly catches and reports exceptions raised while retrieving the active LLM configuration. The test mocks `get_active_llm_config` to raise a generic `Exception` (simulating a database error), invokes `handle_timeline_query` with typical parameters, and asserts that the returned payload has a type of `"error"` and includes the original exception message in its `message` field.
        """
        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        with patch(
            "app.services.handlers.timeline_handler.get_active_llm_config",
            side_effect=Exception("DB error"),
        ):
            result = await handle_timeline_query(
                db=db,
                investigation_id=investigation_id,
                user_query="Show timeline entries",
                user_id=user_id,
            )

            # Verify error response
            assert result["type"] == "error"
            assert "DB error" in result["message"]


@pytest.mark.unit
class TestGenerateTimelineSummary:
    """Test _generate_timeline_summary function."""

    def test_no_tools_used(self):
        """
        Test that `_generate_timeline_summary` returns the correct message when no tools are provided, ensuring an empty operation list yields "No timeline operations performed."
        """
        summary = _generate_timeline_summary([])
        assert summary == "No timeline operations performed."

    def test_single_query(self):
        """
        Test that a single successful timeline query tool generates a summary containing the phrase “1 query”.
        """
        tools_used = [{"name": "query_timeline_entries", "success": True}]
        summary = _generate_timeline_summary(tools_used)
        assert "1 query" in summary

    def test_multiple_queries(self):
        """
        Test that the timeline summary correctly reports multiple query operations.

        This test constructs a list of tool usage entries where the `query_timeline_entries` tool is invoked twice with successful outcomes, generates a summary via `_generate_timeline_summary`, and asserts that the resulting text includes the phrase `"2 queries"`.
        """
        tools_used = [
            {"name": "query_timeline_entries", "success": True},
            {"name": "query_timeline_entries", "success": True},
        ]
        summary = _generate_timeline_summary(tools_used)
        assert "2 queries" in summary

    def test_mixed_operations(self):
        """
        Test that the timeline summary generator correctly aggregates mixed successful operations, producing a human-readable string containing one occurrence each of query, addition, update, deletion, and statistics request.
        """
        tools_used = [
            {"name": "query_timeline_entries", "success": True},
            {"name": "add_timeline_entry", "success": True},
            {"name": "update_timeline_entry", "success": True},
            {"name": "delete_timeline_entry", "success": True},
            {"name": "get_timeline_stats", "success": True},
        ]
        summary = _generate_timeline_summary(tools_used)
        assert "1 query" in summary
        assert "1 addition" in summary
        assert "1 update" in summary
        assert "1 deletion" in summary
        assert "1 stats request" in summary

    def test_failed_operations_not_counted(self):
        """
        Test that only successful operations are reflected in the generated timeline summary.

        The test constructs a list of tool usage dictionaries where some entries have `"success": False`. It then calls `_generate_timeline_summary` with this list and asserts that the resulting summary includes counts for the successful `query_timeline_entries` operation while omitting any mention of failed operations such as additions. This verifies that failed actions are excluded from the human-readable summary output.
        """
        tools_used = [
            {"name": "query_timeline_entries", "success": True},
            {"name": "query_timeline_entries", "success": False},  # Failed
            {"name": "add_timeline_entry", "success": False},  # Failed
        ]
        summary = _generate_timeline_summary(tools_used)
        assert "1 query" in summary
        assert "addition" not in summary

    def test_all_failed_operations(self):
        """
        Test that the summary generated when every timeline operation reports failure matches the expected message.

        Parameters
        ----------
        self : object
            The test case instance providing context for assertions.

        Returns
        -------
        None

        Raises
        ------
        AssertionError
            If the generated summary does not equal "All timeline operations failed.".
        """
        tools_used = [
            {"name": "query_timeline_entries", "success": False},
            {"name": "add_timeline_entry", "success": False},
        ]
        summary = _generate_timeline_summary(tools_used)
        assert summary == "All timeline operations failed."

    def test_plural_forms(self):
        """
        Test that the summary generator correctly pluralizes operation descriptors based on the count of each tool type used. The test constructs a list of tool usage dictionaries representing two successful additions, two updates, two deletions, and two statistics requests, then calls `_generate_timeline_summary` with this list. It asserts that the resulting summary string contains the expected phrases: "2 additions", "2 updates", "2 deletions", and "2 stats requests". This verifies that the plural-form logic produces accurate human-readable summaries for multiple occurrences of each operation.
        """
        tools_used = [
            {"name": "add_timeline_entry", "success": True},
            {"name": "add_timeline_entry", "success": True},
            {"name": "update_timeline_entry", "success": True},
            {"name": "update_timeline_entry", "success": True},
            {"name": "delete_timeline_entry", "success": True},
            {"name": "delete_timeline_entry", "success": True},
            {"name": "get_timeline_stats", "success": True},
            {"name": "get_timeline_stats", "success": True},
        ]
        summary = _generate_timeline_summary(tools_used)
        assert "2 additions" in summary
        assert "2 updates" in summary
        assert "2 deletions" in summary
        assert "2 stats requests" in summary


@pytest.mark.unit
class TestExecuteTimelineTool:
    """Test _execute_timeline_tool function."""

    async def test_unknown_tool(self):
        """
        Test that the timeline tool executor correctly handles an unrecognized tool name by returning a failure response.

        Args:
            self: The test case instance.

        Returns:
            None - assertions validate that `result["success"]` is False and that the error message contains "Unknown tool".
        """
        db = AsyncMock()
        investigation_id = uuid4()

        result = await _execute_timeline_tool(
            db=db,
            investigation_id=investigation_id,
            tool_name="unknown_tool",
            arguments={},
            user_id=1,
        )

        assert result["success"] is False
        assert "Unknown tool" in result["error"]


@pytest.mark.unit
class TestToolQueryTimeline:
    """Test _tool_query_timeline function."""

    async def test_query_all_entries(self):
        """
        Test that the `_tool_query_timeline` handler correctly retrieves all timeline entries for a given investigation.

        The test sets up an asynchronous mock database connection and populates it with a single fabricated row representing a timeline entry. It then calls the private `_tool_query_timeline` function with an empty query filter and verifies that:

        * The operation reports success (`result["success"] is True`).
        * The total number of matching entries equals one.
        * Exactly one entry is returned in `result["entries"]`.
        * The returned entry contains the expected field values for `entry_id`, `title`, `entry_type`, and `tags`.

        This ensures that the query handler correctly transforms raw database rows into the public API response format.
        """
        from app.services.handlers.timeline_handler import _tool_query_timeline

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock database result
        mock_row = (
            1,  # entry_id
            None,  # event_id
            datetime(2024, 1, 1, 12, 0),  # timestamp
            "event",  # entry_type
            "Test Entry",  # title
            "Test description",  # description
            {"key": "value"},  # data
            ["tag1", "tag2"],  # tags
        )

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        db.execute.return_value = mock_result

        result = await _tool_query_timeline(db, investigation_id, {})

        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["entries"]) == 1
        entry = result["entries"][0]
        assert entry["entry_id"] == 1
        assert entry["title"] == "Test Entry"
        assert entry["entry_type"] == "event"
        assert entry["tags"] == ["tag1", "tag2"]

    async def test_query_with_filters(self):
        """
        Test querying timeline entries with various filter parameters.

        This test verifies that `_tool_query_timeline` correctly handles a request containing
        multiple filtering criteria-entry type, tags, time range, free-text search and result limit-
        when the underlying database query returns no rows.

        The function performs the following steps:

        * Imports the private handler `_tool_query_timeline` from `app.services.handlers.timeline_handler`.
        * Creates an asynchronous mock database connection (`AsyncMock`) and a random investigation UUID.
        * Configures the mock to return an empty result set for any executed query.
        * Constructs a dictionary of filter parameters:
          - `entry_type`: the type of timeline entry to retrieve (e.g., `"finding"`).
          - `tags`: list of tags that entries must contain.
          - `start_time` and `end_time`: ISO-8601 timestamps delimiting the time window.
          - `search_text`: free-text term to match against entry content.
          - `limit`: maximum number of entries to return.
        * Calls `_tool_query_timeline` with the mock database, investigation ID and filter parameters.
        * Asserts that the returned payload indicates success, reports a total count of zero,
          and contains an empty list of entries.

        No explicit arguments are passed to this test method; it relies on the test framework
        to instantiate `self` as part of a unittest.TestCase subclass. The function returns
        nothing (implicitly `None`).
        """
        from app.services.handlers.timeline_handler import _tool_query_timeline

        db = AsyncMock()
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute.return_value = mock_result

        params = {
            "entry_type": "finding",
            "tags": ["suspicious"],
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-31T23:59:59Z",
            "search_text": "malware",
            "limit": 10,
        }

        result = await _tool_query_timeline(db, investigation_id, params)

        assert result["success"] is True
        assert result["total"] == 0
        assert result["entries"] == []

    async def test_query_handles_exception(self):
        """
        Test that _tool_query_timeline correctly handles exceptions raised by the database layer.\n\nThe test creates an asynchronous mock database object whose `execute` method is configured to raise a generic `Exception` with the message \"DB error\". It then invokes `_tool_query_timeline` with this mock, a newly generated investigation UUID, and an empty parameters dictionary.\n\nAssertions verify that the returned mapping indicates failure (`success` set to `False`) and that the original exception message appears in the `error` field of the result. This ensures that database errors are gracefully captured and reported by the timeline query handler.
        """
        from app.services.handlers.timeline_handler import _tool_query_timeline

        db = AsyncMock()
        investigation_id = uuid4()

        db.execute.side_effect = Exception("DB error")

        result = await _tool_query_timeline(db, investigation_id, {})

        assert result["success"] is False
        assert "DB error" in result["error"]


@pytest.mark.unit
class TestToolAddTimelineEntry:
    """Test _tool_add_timeline_entry function."""

    async def test_add_entry_success(self):
        """
        Test that adding a timeline entry succeeds when the database insert operation returns a valid row.

        Args:
            self: The test case instance.

        Returns:
            None. The function performs assertions on the result returned by `_tool_add_timeline_entry` to verify successful insertion.

        The test sets up an asynchronous mock database, defines input parameters for a new timeline entry, and configures the mock to return a row containing the newly created entry's ID, timestamp, and title. It then calls the internal `_tool_add_timeline_entry` coroutine with these arguments and asserts that:
        - The operation reports success (`result["success"] is True`).
        - The returned entry identifier matches the mocked ID (`result["entry_id"] == 1`).
        - The title in the result corresponds to the provided title (`result["title"] == "New Entry"`).
        """
        from app.services.handlers.timeline_handler import _tool_add_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        # Mock successful insert
        mock_row = (1, datetime(2024, 1, 1, 12, 0), "New Entry")
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        db.execute.return_value = mock_result

        params = {
            "title": "New Entry",
            "entry_type": "finding",
            "description": "Test description",
            "tags": ["important"],
        }

        result = await _tool_add_timeline_entry(db, investigation_id, params, user_id)

        assert result["success"] is True
        assert result["entry_id"] == 1
        assert result["title"] == "New Entry"

    async def test_add_entry_missing_title(self):
        """
        Test adding a timeline entry when the required `title` field is missing.

        This test verifies that `_tool_add_timeline_entry` correctly identifies the absence of the mandatory
        `title` parameter in the supplied `params` dictionary and returns a failure response.

        The function:
        - Mocks an asynchronous database connection.
        - Generates a random investigation identifier and uses a static user identifier.
        - Calls the handler with parameters containing only a `description`.
        - Asserts that the result indicates failure (`success` is `False`) and that the error message
          includes the expected text about the missing `title` field.
        """
        from app.services.handlers.timeline_handler import _tool_add_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        params = {"description": "No title"}

        result = await _tool_add_timeline_entry(db, investigation_id, params, user_id)

        assert result["success"] is False
        assert "Missing required field: title" in result["error"]

    async def test_add_entry_handles_exception(self):
        """
        Test that the `_tool_add_timeline_entry` handler correctly propagates database exceptions.\n\nThe test creates an asynchronous mock of the database connection, configures its `execute` method to raise a generic `Exception` with the message \"DB error\", and then calls the private timeline-entry addition tool with a minimal set of parameters. After awaiting the coroutine, the result dictionary is inspected to ensure that:\n\n* `success` is `False`, indicating the operation failed.\n* The `error` field contains the original exception message (\"DB error\").\n\nThis verifies that the handler does not swallow exceptions and returns a structured error response suitable for downstream processing.\"""
        """
        from app.services.handlers.timeline_handler import _tool_add_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()
        user_id = 1

        db.execute.side_effect = Exception("DB error")

        params = {"title": "Test Entry"}

        result = await _tool_add_timeline_entry(db, investigation_id, params, user_id)

        assert result["success"] is False
        assert "DB error" in result["error"]


@pytest.mark.unit
class TestToolUpdateTimelineEntry:
    """Test _tool_update_timeline_entry function."""

    async def test_update_entry_success(self):
        """
        Test that updating an existing timeline entry succeeds.

        This test verifies the `_tool_update_timeline_entry` handler by mocking an asynchronous database connection and ensuring it returns a successful result with the expected entry data.

        Args:
            self: The unittest.TestCase instance providing the testing context.

        Procedure:
            1. Import the private `_tool_update_timeline_entry` function from the timeline handler.
            2. Create an `AsyncMock` to simulate the database connection.
            3. Generate a random investigation UUID using `uuid4`.
            4. Configure the mock to return a single row `(1, "Updated Entry")` when `fetchone` is called on the result of `db.execute`.
            5. Define update parameters with `entry_id`, `title`, and `tags`.
            6. Await the handler call with the mocked database, investigation ID, and parameters.
            7. Assert that the returned dictionary indicates success and contains the correct `entry_id` and `title`.

        Returns:
            None - assertions validate the behavior; any failure raises an AssertionError.
        """
        from app.services.handlers.timeline_handler import _tool_update_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock successful update
        mock_row = (1, "Updated Entry")
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        db.execute.return_value = mock_result

        params = {"entry_id": 1, "title": "Updated Entry", "tags": ["updated"]}

        result = await _tool_update_timeline_entry(db, investigation_id, params)

        assert result["success"] is True
        assert result["entry_id"] == 1
        assert result["title"] == "Updated Entry"

    async def test_update_entry_missing_id(self):
        """
        Test that updating a timeline entry without providing the required `entry_id` field fails gracefully.\n\nThe test imports the private helper `_tool_update_timeline_entry` from the timeline handler, creates a mocked asynchronous database connection, and calls the function with an `investigation_id` and a parameters dictionary that lacks `entry_id`. It then asserts that the returned payload indicates failure (`success` is `False`) and that the error message contains the expected text about the missing required field.\n\nThis verifies the handler’s validation logic for mandatory input fields before any database interaction occurs.
        """
        from app.services.handlers.timeline_handler import _tool_update_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()

        params = {"title": "No ID"}

        result = await _tool_update_timeline_entry(db, investigation_id, params)

        assert result["success"] is False
        assert "Missing required field: entry_id" in result["error"]

    async def test_update_entry_not_found(self):
        """
        Test that updating a timeline entry which does not exist returns a failure result.

        The test creates an asynchronous mock database and configures the `execute` call to return a result whose `fetchone` method yields `None`, simulating a missing row for the given `entry_id`.

        It then calls the private handler `_tool_update_timeline_entry` with:
        - `db` - the mocked async database connection,
        - `investigation_id` - a randomly generated UUID identifying the investigation,
        - `params` - a dictionary containing an `entry_id` that is not present in the database and the new `title`.

        The test asserts that:
        - The returned mapping has `success` set to `False`,
        - The `error` message contains the phrase “not found”, indicating proper handling of the missing entry case.
        """
        from app.services.handlers.timeline_handler import _tool_update_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock no rows returned
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db.execute.return_value = mock_result

        params = {"entry_id": 999, "title": "Updated"}

        result = await _tool_update_timeline_entry(db, investigation_id, params)

        assert result["success"] is False
        assert "not found" in result["error"]

    async def test_update_entry_no_fields(self):
        """
        \"""Test that updating a timeline entry with an empty update payload fails gracefully.\n\nThe test imports the internal `_tool_update_timeline_entry` handler, creates a mocked asynchronous database client, and invokes the function with only an `entry_id` provided in `params` - omitting any fields to modify. It asserts that the returned dictionary indicates failure (`success` is `False`) and that the error message contains the phrase \"No fields to update\".\n\nThis verifies that the handler correctly validates input parameters before attempting a database operation.\"""
        """
        from app.services.handlers.timeline_handler import _tool_update_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()

        params = {"entry_id": 1}  # Only ID, no fields to update

        result = await _tool_update_timeline_entry(db, investigation_id, params)

        assert result["success"] is False
        assert "No fields to update" in result["error"]


@pytest.mark.unit
class TestToolDeleteTimelineEntry:
    """Test _tool_delete_timeline_entry function."""

    async def test_delete_entry_success(self):
        """
        Test that deleting an existing timeline entry succeeds.

        The test imports the private handler `_tool_delete_timeline_entry` and uses an `AsyncMock` to simulate the database connection. It creates a fake investigation identifier with `uuid4()` and prepares two mocked query results:

        * The first mock represents the existence check for the entry; it returns a row containing the title `"Entry to Delete"`.
        * The second mock simulates the delete operation itself, returning a row indicating one affected row.

        The `db.execute` coroutine is configured to return these mocks in sequence via `side_effect`.

        A parameter dictionary with `entry_id` set to `1` is passed to the handler. After awaiting the call, the test asserts that:

        * The result reports success (`result["success"] is True`).
        * The returned `entry_id` matches the requested identifier.
        * The title in the response corresponds to the mocked entry title.

        This verifies that the delete tool correctly retrieves the entry details, performs the deletion, and returns the expected payload.
        """
        from app.services.handlers.timeline_handler import _tool_delete_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock check query (entry exists)
        check_row = ("Entry to Delete",)
        check_result = MagicMock()
        check_result.fetchone.return_value = check_row

        # Mock delete query
        delete_row = (1,)
        delete_result = MagicMock()
        delete_result.fetchone.return_value = delete_row

        db.execute.side_effect = [check_result, delete_result]

        params = {"entry_id": 1}

        result = await _tool_delete_timeline_entry(db, investigation_id, params)

        assert result["success"] is True
        assert result["entry_id"] == 1
        assert result["title"] == "Entry to Delete"

    async def test_delete_entry_missing_id(self):
        """
        Test the deletion tool when the required `entry_id` parameter is omitted.\n\nThis test verifies that `_tool_delete_timeline_entry` correctly identifies the missing mandatory field, returns a failure response, and includes an appropriate error message indicating that `entry_id` is required. The function sets up a mocked asynchronous database connection, supplies an empty parameters dictionary, invokes the deletion tool, and asserts that the result signals unsuccessful execution with the expected error detail.
        """
        from app.services.handlers.timeline_handler import _tool_delete_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()

        params = {}

        result = await _tool_delete_timeline_entry(db, investigation_id, params)

        assert result["success"] is False
        assert "Missing required field: entry_id" in result["error"]

    async def test_delete_entry_not_found(self):
        """
        Test that attempting to delete a timeline entry that does not exist results in a failure response.\n\nThe test imports the internal `_tool_delete_timeline_entry` handler, creates a mocked asynchronous database connection, and simulates a query that returns no rows for the requested `entry_id`. It then calls the handler with a non-existent entry identifier and verifies that the returned dictionary indicates `success` is `False` and contains an error message mentioning that the entry was not found. This ensures the delete tool correctly handles the \"not found\" case.
        """
        from app.services.handlers.timeline_handler import _tool_delete_timeline_entry

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock check query (entry not found)
        check_result = MagicMock()
        check_result.fetchone.return_value = None
        db.execute.return_value = check_result

        params = {"entry_id": 999}

        result = await _tool_delete_timeline_entry(db, investigation_id, params)

        assert result["success"] is False
        assert "not found" in result["error"]


@pytest.mark.unit
class TestToolGetTimelineStats:
    """Test _tool_get_timeline_stats function."""

    async def test_get_stats_success(self):
        """
        Test that the `_tool_get_timeline_stats` handler correctly aggregates timeline statistics when all database queries succeed.

        The test sets up an asynchronous mock database connection and configures it to return:

        * A total entry count of `10`.
        * Per-type counts for `event`, `finding` and `observation`.
        * An earliest and latest timestamp spanning January 2024.
        * Three distinct tag strings.

        It then invokes the private `_tool_get_timeline_stats` coroutine with the mock database and a generated investigation identifier, awaiting its result.

        Assertions verify that:

        * The operation reports success (`result["success"] is True`).
        * The total entry count matches the mocked value.
        * The per-type breakdown is correctly transformed into a dictionary.
        * Both `earliest` and `latest` timestamps are present in the `date_range` mapping.
        * Exactly three tags are returned and the expected tag `"suspicious"` is included.
        """
        from app.services.handlers.timeline_handler import _tool_get_timeline_stats

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock total count query
        total_result = MagicMock()
        total_result.scalar.return_value = 10

        # Mock entries by type query
        type_result = MagicMock()
        type_result.fetchall.return_value = [("event", 5), ("finding", 3), ("observation", 2)]

        # Mock date range query
        range_result = MagicMock()
        range_result.fetchone.return_value = (
            datetime(2024, 1, 1, 0, 0),
            datetime(2024, 1, 31, 23, 59),
        )

        # Mock tags query
        tags_result = MagicMock()
        tags_result.fetchall.return_value = [("suspicious",), ("important",), ("reviewed",)]

        db.execute.side_effect = [total_result, type_result, range_result, tags_result]

        result = await _tool_get_timeline_stats(db, investigation_id)

        assert result["success"] is True
        assert result["total_entries"] == 10
        assert result["entries_by_type"] == {"event": 5, "finding": 3, "observation": 2}
        assert result["date_range"]["earliest"] is not None
        assert result["date_range"]["latest"] is not None
        assert len(result["tags"]) == 3
        assert "suspicious" in result["tags"]

    async def test_get_stats_empty_timeline(self):
        """
        Test case for the private `_tool_get_timeline_stats` coroutine that verifies correct handling of an empty timeline.

        The test sets up a mocked asynchronous database connection (`AsyncMock`) and supplies a random `investigation_id`. It configures the mock to return:

        * A scalar result of `0` for the total entry count.
        * An empty list for the per-type entry aggregation.
        * `(None, None)` for the earliest and latest timestamps, indicating no entries.
        * An empty list for distinct tags.

        After invoking `_tool_get_timeline_stats` with the mocked database and investigation identifier, the test asserts that:

        * The operation reports success (`result["success"] is True`).
        * `total_entries` equals `0`.
        * `entries_by_type` is an empty dictionary.
        * Both `earliest` and `latest` timestamps in `date_range` are `None`.
        * The `tags` list is empty.
        """
        from app.services.handlers.timeline_handler import _tool_get_timeline_stats

        db = AsyncMock()
        investigation_id = uuid4()

        # Mock empty results
        total_result = MagicMock()
        total_result.scalar.return_value = 0

        type_result = MagicMock()
        type_result.fetchall.return_value = []

        range_result = MagicMock()
        range_result.fetchone.return_value = (None, None)

        tags_result = MagicMock()
        tags_result.fetchall.return_value = []

        db.execute.side_effect = [total_result, type_result, range_result, tags_result]

        result = await _tool_get_timeline_stats(db, investigation_id)

        assert result["success"] is True
        assert result["total_entries"] == 0
        assert result["entries_by_type"] == {}
        assert result["date_range"]["earliest"] is None
        assert result["date_range"]["latest"] is None
        assert result["tags"] == []

    async def test_get_stats_handles_exception(self):
        """
        Test that the `_tool_get_timeline_stats` helper correctly handles exceptions raised by the database layer, returning a failure response containing the error message.
        """
        from app.services.handlers.timeline_handler import _tool_get_timeline_stats

        db = AsyncMock()
        investigation_id = uuid4()

        db.execute.side_effect = Exception("DB error")

        result = await _tool_get_timeline_stats(db, investigation_id)

        assert result["success"] is False
        assert "DB error" in result["error"]
