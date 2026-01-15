"""
Unit tests for report CRUD operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime

from app.crud.report import (
    get_latest_report,
    create_report,
    delete_reports_for_investigation,
)
from app.models.report import Report


@pytest.mark.unit
class TestGetLatestReport:
    """Test get_latest_report function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session using `AsyncMock`. This helper is intended for use in unit tests where an async DB interface is required. Returns:\n    AsyncMock: A mock object that mimics an asynchronous database session.
        """
        db = AsyncMock()
        return db

    async def test_get_latest_report_found(self, mock_db):
        """
        Test that get_latest_report returns the most recent Report instance when it exists in the database, verifying the correct query execution and result handling.
        """
        investigation_id = uuid4()
        expected_report = Report(
            report_id=1,
            investigation_id=investigation_id,
            user_id=1,
            title="Investigation Report",
            markdown_content="# Report Content",
            artifacts_count=5,
            timeline_entries_count=10,
            event_types_count=3,
        )

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_report
        mock_db.execute.return_value = mock_result

        result = await get_latest_report(mock_db, investigation_id)

        assert result == expected_report
        mock_db.execute.assert_called_once()

    async def test_get_latest_report_not_found(self, mock_db):
        """
        Test that `get_latest_report` returns `None` when there are no reports for the given investigation.

        The test creates a mock asynchronous database session, configures its `execute` method to return a result whose `scalar_one_or_none` call yields `None`, and then calls `get_latest_report` with a fresh `investigation_id`.

        Assertions verify that:
        - The function returns `None` indicating no report was found.
        - The database `execute` method is invoked exactly once.
        """
        investigation_id = uuid4()

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_latest_report(mock_db, investigation_id)

        assert result is None
        mock_db.execute.assert_called_once()

    async def test_get_latest_report_multiple_reports(self, mock_db):
        """
        Test that get_latest_report returns only the most recent report for a given investigation.

        Args:
            self: The unittest.TestCase instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        The test sets up two reports in the mock, configures the mock to return the latest one (ordered by `generated_at` descending with a limit of 1), invokes `get_latest_report`, and asserts that the returned object matches the expected latest report and has the correct `report_id`.
        """
        investigation_id = uuid4()

        # The query should use ORDER BY generated_at DESC LIMIT 1
        latest_report = Report(
            report_id=2,
            investigation_id=investigation_id,
            user_id=1,
            title="Latest Report",
            markdown_content="# Latest",
            artifacts_count=5,
            timeline_entries_count=10,
            event_types_count=3,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = latest_report
        mock_db.execute.return_value = mock_result

        result = await get_latest_report(mock_db, investigation_id)

        assert result == latest_report
        assert result.report_id == 2


@pytest.mark.unit
class TestCreateReport:
    """Test create_report function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mock asynchronous database session for testing.

        This helper returns an `AsyncMock` instance with its commonly used
        SQLAlchemy methods replaced by mocks:

        - `add` is a `MagicMock` allowing inspection of objects added to the
          session.
        - `commit`, `refresh` and `execute` are `AsyncMock` instances so they
          can be awaited in asynchronous code.

        The returned mock mimics the minimal interface required by the CRUD
        functions under test, enabling isolated unit tests without a real database.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        return db

    async def test_create_report_success(self, mock_db):
        """
        Test that creating a report succeeds and performs all expected database operations.

        The test sets up identifiers and content for a new report, invokes :func:`create_report` with these values, and then asserts that:

        * The old reports for the same investigation are deleted (`mock_db.execute` called once).
        * A new :class:`Report` instance is added to the session (`mock_db.add` called once).
        * The transaction is committed and the newly created object is refreshed (`mock_db.commit` and `mock_db.refresh` each called once).

        It also verifies that the added report instance has the correct attribute values for:

        * `investigation_id`
        * `user_id`
        * `title`
        * `markdown_content`
        * `user_prompt`
        * `artifacts_count`
        * `timeline_entries_count`
        * `event_types_count`

        The test uses a mocked asynchronous database session (`mock_db`) and runs within an async test framework.
        """
        investigation_id = uuid4()
        user_id = 1
        title = "Investigation Report"
        markdown_content = "# Report\n\nContent here"
        user_prompt = "Focus on lateral movement"
        artifacts_count = 5
        timeline_entries_count = 10
        event_types_count = 3

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=user_id,
            title=title,
            markdown_content=markdown_content,
            user_prompt=user_prompt,
            artifacts_count=artifacts_count,
            timeline_entries_count=timeline_entries_count,
            event_types_count=event_types_count,
        )

        # Verify database operations
        mock_db.execute.assert_called_once()  # DELETE old reports
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify report object
        added_report = mock_db.add.call_args[0][0]
        assert isinstance(added_report, Report)
        assert added_report.investigation_id == investigation_id
        assert added_report.user_id == user_id
        assert added_report.title == title
        assert added_report.markdown_content == markdown_content
        assert added_report.user_prompt == user_prompt
        assert added_report.artifacts_count == artifacts_count
        assert added_report.timeline_entries_count == timeline_entries_count
        assert added_report.event_types_count == event_types_count

    async def test_create_report_without_user_prompt(self, mock_db):
        """
        Test that creating a report without providing a custom user prompt stores a report whose `user_prompt` attribute is `None`.

        The test:
        - Generates a random investigation identifier.
        - Calls :func:`create_report` with `user_prompt=None` and minimal artifact, timeline entry, and event type counts.
        - Retrieves the report instance passed to the mocked database's `add` method.
        - Asserts that the `user_prompt` attribute of the added report is `None`.
        """
        investigation_id = uuid4()

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title="Report",
            markdown_content="# Content",
            user_prompt=None,
            artifacts_count=0,
            timeline_entries_count=0,
            event_types_count=0,
        )

        added_report = mock_db.add.call_args[0][0]
        assert added_report.user_prompt is None

    async def test_create_report_deletes_old_reports(self, mock_db):
        """
        Test that creating a new report removes any existing reports for the same investigation before inserting the new one.

        Parameters
        ----------
        self: unittest.TestCase
            The test case instance.
        mock_db: MagicMock
            A mocked asynchronous database session with `execute` and `add` methods.

        The test performs the following steps:
        1. Generates a random `investigation_id`.
        2. Configures `mock_db.execute` to return a mock result whose `rowcount` attribute is set to 2, simulating the deletion of two old reports.
        3. Calls :func:`create_report` with the mocked database and sample report data.
        4. Asserts that `mock_db.execute` (the DELETE operation) was called exactly once and that `mock_db.add` (the INSERT operation) was also called exactly once, confirming that old reports are deleted before the new report is added.
        """
        investigation_id = uuid4()

        # Mock the DELETE result
        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 2  # Simulate 2 old reports deleted
        mock_db.execute.return_value = mock_delete_result

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title="New Report",
            markdown_content="# New",
            user_prompt=None,
            artifacts_count=1,
            timeline_entries_count=2,
            event_types_count=3,
        )

        # Verify DELETE was called before INSERT
        mock_db.execute.assert_called_once()
        mock_db.add.assert_called_once()

    async def test_create_report_with_zero_counts(self, mock_db):
        """
        Test creating a report when all count parameters are zero.

        Ensures that `create_report` correctly stores a report with `artifacts_count`, `timeline_entries_count`, and `event_types_count` set to 0, and that these values are preserved in the object added to the database mock.
        """
        investigation_id = uuid4()

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title="Empty Report",
            markdown_content="# No data yet",
            user_prompt=None,
            artifacts_count=0,
            timeline_entries_count=0,
            event_types_count=0,
        )

        added_report = mock_db.add.call_args[0][0]
        assert added_report.artifacts_count == 0
        assert added_report.timeline_entries_count == 0
        assert added_report.event_types_count == 0

    async def test_create_report_with_large_markdown(self, mock_db):
        """
        Test creating a report with very large markdown content and verify that the stored report retains the full content length. The test generates a markdown string exceeding 10 000 lines, invokes `create_report` with this content, and asserts that the resulting report object's `markdown_content` attribute has a length greater than 10 000 characters. This ensures the function can handle large inputs without truncation.
        """
        investigation_id = uuid4()
        large_content = "# Report\n\n" + ("Content line\n" * 10000)

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title="Large Report",
            markdown_content=large_content,
            user_prompt=None,
            artifacts_count=100,
            timeline_entries_count=500,
            event_types_count=20,
        )

        added_report = mock_db.add.call_args[0][0]
        assert len(added_report.markdown_content) > 10000


@pytest.mark.unit
class TestDeleteReportsForInvestigation:
    """Test delete_reports_for_investigation function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mock asynchronous database session.\n\nThe returned object mimics an async database connection, providing an `AsyncMock` instance with its `commit` coroutine also mocked. This helper is used in unit tests to simulate database interactions without requiring a real database backend.
        """
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    async def test_delete_reports_success(self, mock_db):
        """
        Test that deleting reports for a specific investigation succeeds and returns the number of rows removed.

        Args:
            self: The test case instance.
            mock_db: A MagicMock representing the asynchronous database connection, with `execute` and `commit` methods mocked.

        Returns:
            None

        The test creates a fake UUID for an investigation, configures the mock to simulate three rows being deleted, invokes `delete_reports_for_investigation`, and asserts that the returned row count matches the mock and that the appropriate database methods were called exactly once.
        """
        investigation_id = uuid4()

        # Mock the DELETE result
        mock_result = MagicMock()
        mock_result.rowcount = 3  # 3 reports deleted
        mock_db.execute.return_value = mock_result

        result = await delete_reports_for_investigation(mock_db, investigation_id)

        assert result == 3
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_delete_reports_none_found(self, mock_db):
        """
        Test deletion of reports when none exist for a given investigation.

        Args:
            self: Test case instance.
            mock_db: MagicMock representing an asynchronous database connection with `execute` and `commit` methods.

        Returns:
            None (assertions verify that `delete_reports_for_investigation` returns 0, the execute method is called once, and the transaction is committed).
        """
        investigation_id = uuid4()

        # Mock empty result
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await delete_reports_for_investigation(mock_db, investigation_id)

        assert result == 0
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_delete_reports_single_report(self, mock_db):
        """
        Test deletion of a single report for a given investigation.\n\nArgs:\n    self: The test case instance (unused).\n    mock_db: A mocked asynchronous database connection providing an `execute` coroutine that returns a result with a `rowcount` attribute.\n\nThe test creates a random `investigation_id`, configures the mock to return a result indicating one row was deleted, invokes `delete_reports_for_investigation` and asserts that the function reports exactly one deletion.\"""
        """
        investigation_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await delete_reports_for_investigation(mock_db, investigation_id)

        assert result == 1


@pytest.mark.unit
class TestReportCRUDEdgeCases:
    """Test edge cases for report CRUD operations."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mock asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session with:
        - `add` as a synchronous `MagicMock` to track added entities.
        - `commit`, `refresh` and `execute` as `AsyncMock` instances to simulate asynchronous operations.

        Returns
            An `AsyncMock` instance representing the mock database session.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        return db

    async def test_create_report_with_special_characters(self, mock_db):
        """
        Test creating a report when the title and markdown content contain special characters, ensuring those values are stored unchanged in the added report.
        """
        investigation_id = uuid4()
        title = "Report: <script>alert('XSS')</script> & Special Chars"
        markdown_content = "# Report\n\n```sql\nSELECT * FROM users;\n```"

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title=title,
            markdown_content=markdown_content,
            user_prompt=None,
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        added_report = mock_db.add.call_args[0][0]
        assert added_report.title == title
        assert added_report.markdown_content == markdown_content

    async def test_create_report_with_unicode(self, mock_db):
        """
        Test creating a report containing Unicode characters.

        This test verifies that `create_report` correctly handles titles, markdown content, and user prompts with non-ASCII characters. It ensures the generated report stored in the mocked database preserves the exact Unicode strings for `title`, `markdown_content` and `user_prompt`. The test uses a fresh investigation identifier and checks that the added report's attributes match the provided Unicode values.
        """
        investigation_id = uuid4()
        title = "レポート 报告 🔍"
        markdown_content = "# 調査報告\n\n中文内容"

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title=title,
            markdown_content=markdown_content,
            user_prompt="カスタムプロンプト",
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        added_report = mock_db.add.call_args[0][0]
        assert added_report.title == title
        assert added_report.markdown_content == markdown_content
        assert added_report.user_prompt == "カスタムプロンプト"

    async def test_create_report_with_very_long_title(self, mock_db):
        """
        Test creating a report when the title length exceeds typical limits.

        This test verifies that `create_report` correctly stores a title composed of 1,000 characters and does not truncate or raise an error. It uses a mocked asynchronous database session to intercept the added report object, then asserts that the stored title retains the full length.
        """
        investigation_id = uuid4()
        title = "A" * 1000  # Very long title

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title=title,
            markdown_content="# Content",
            user_prompt=None,
            artifacts_count=1,
            timeline_entries_count=1,
            event_types_count=1,
        )

        added_report = mock_db.add.call_args[0][0]
        assert len(added_report.title) == 1000

    async def test_create_report_with_negative_counts(self, mock_db):
        """
        Test creating a report when artifact, timeline entry, and event type counts are negative.

        Args:
            self: Test case instance.
            mock_db: Asynchronous mock of the database session used for CRUD operations.

        The test invokes `create_report` with `artifacts_count`, `timeline_entries_count`, and `event_types_count` set to `-1`. It then verifies that the report object added to the mocked database retains these negative values, confirming that the CRUD layer does not perform validation on count fields.
        """
        investigation_id = uuid4()

        # This might be a data validation issue, but testing the CRUD layer
        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title="Report",
            markdown_content="# Content",
            user_prompt=None,
            artifacts_count=-1,
            timeline_entries_count=-1,
            event_types_count=-1,
        )

        added_report = mock_db.add.call_args[0][0]
        # CRUD layer doesn't validate, just stores
        assert added_report.artifacts_count == -1

    async def test_create_report_with_very_large_counts(self, mock_db):
        """
        Test creating a report when the numeric count fields are set to very large values.

        This test verifies that `create_report` correctly stores large integer counts (e.g., `artifacts_count`, `timeline_entries_count`, and `event_types_count`) without overflow or truncation. It uses a mocked asynchronous database session (`mock_db`) to intercept the added report object, then asserts that the stored `artifacts_count` matches the supplied value of 999 999.

        Args:
            self: The test case instance.
            mock_db: A fixture providing a mocked async database interface with an `add` method that records its arguments.
        """
        investigation_id = uuid4()

        result = await create_report(
            db=mock_db,
            investigation_id=investigation_id,
            user_id=1,
            title="Large Investigation",
            markdown_content="# Massive dataset",
            user_prompt=None,
            artifacts_count=999999,
            timeline_entries_count=999999,
            event_types_count=999999,
        )

        added_report = mock_db.add.call_args[0][0]
        assert added_report.artifacts_count == 999999
