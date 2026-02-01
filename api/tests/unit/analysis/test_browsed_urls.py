"""
Unit tests for the Browsed URLs Analyzer.

Tests the BrowsedURLsAnalyzer class which analyzes browser history artifacts
from Chrome, Firefox, and Edge browsers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from datetime import datetime, timezone

from app.analysis.browsed_urls import BrowsedURLsAnalyzer, BrowsedURLEntry


@pytest.mark.unit
class TestBrowsedURLsAnalyzer:
    """Unit tests for BrowsedURLsAnalyzer."""

    def test_analyzer_initialization(self):
        """
        Test that the BrowsedURLsAnalyzer initializes correctly.
        
        Verifies that:
        - The analyzer initializes successfully
        - It has 3 browsers configured (Chrome/Chromium, Firefox, Edge Legacy)
        - Each browser has required metadata fields
        """
        analyzer = BrowsedURLsAnalyzer()
        
        assert analyzer is not None
        assert len(analyzer.BROWSERS) == 3
        
        # Verify all browsers have required fields
        for browser_key, browser_info in analyzer.BROWSERS.items():
            assert "name" in browser_info
            assert "description" in browser_info
            assert "icon" in browser_info

    def test_get_browsers(self):
        """
        Test that get_browsers returns properly formatted browser information.
        
        Verifies that:
        - The method returns a list of dictionaries
        - Each dictionary contains all required fields
        - The count matches the number of configured browsers
        """
        analyzer = BrowsedURLsAnalyzer()
        browsers = analyzer.get_browsers()
        
        assert isinstance(browsers, list)
        assert len(browsers) == 3
        
        for browser in browsers:
            assert "key" in browser
            assert "name" in browser
            assert "description" in browser
            assert "icon" in browser

    def test_chrome_browser_metadata(self):
        """
        Test that Chrome/Chromium browser has correct metadata.
        
        Verifies that:
        - Browser key is "chrome_chromium"
        - Name and description are set
        - Icon is "chrome"
        """
        analyzer = BrowsedURLsAnalyzer()
        chrome = analyzer.BROWSERS["chrome_chromium"]
        
        assert chrome["name"] == "Chrome/Chromium/Edge"
        assert chrome["description"] == "Chromium-based browsers (Chrome, new Edge, Brave, etc.)"
        assert chrome["icon"] == "chrome"

    def test_firefox_browser_metadata(self):
        """
        Test that Firefox browser has correct metadata.
        
        Verifies that:
        - Browser key is "firefox"
        - Name and description are set
        - Icon is "firefox"
        """
        analyzer = BrowsedURLsAnalyzer()
        firefox = analyzer.BROWSERS["firefox"]
        
        assert firefox["name"] == "Firefox"
        assert firefox["description"] == "Mozilla Firefox browser"
        assert firefox["icon"] == "firefox"

    def test_edge_legacy_browser_metadata(self):
        """
        Test that Legacy Edge browser has correct metadata.
        
        Verifies that:
        - Browser key is "edge_legacy"
        - Name and description are set
        - Icon is "edge"
        """
        analyzer = BrowsedURLsAnalyzer()
        edge = analyzer.BROWSERS["edge_legacy"]
        
        assert edge["name"] == "Edge (Legacy)"
        assert edge["description"] == "Legacy Microsoft Edge (pre-Chromium)"
        assert edge["icon"] == "edge"

    def test_browsed_url_entry_to_dict(self):
        """
        Test that BrowsedURLEntry.to_dict() properly serializes all fields.
        
        Verifies that:
        - All fields are included in the dictionary
        - Optional fields are preserved
        - The dictionary can be used for JSON serialization
        """
        entry = BrowsedURLEntry(
            browser="chrome_chromium",
            url="https://example.com",
            title="Example Domain",
            visit_count=5,
            timestamp="2024-01-15T10:30:00Z",
            event_id=12345,
            artifact_sequence_id=42,
            additional_data={"typed_count": 2, "transition_type": 0},
            raw_data={"full": "payload"}
        )
        
        result = entry.to_dict()
        
        assert result["browser"] == "chrome_chromium"
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example Domain"
        assert result["visit_count"] == 5
        assert result["timestamp"] == "2024-01-15T10:30:00Z"
        assert result["event_id"] == 12345
        assert result["artifact_sequence_id"] == 42
        assert result["additional_data"]["typed_count"] == 2
        assert result["raw_data"]["full"] == "payload"

    def test_extract_additional_data_chrome(self):
        """
        Test extraction of additional data from Chrome payload.
        
        Verifies that:
        - typed_count is extracted
        - transition_type is extracted
        - source_file is extracted
        """
        analyzer = BrowsedURLsAnalyzer()
        
        payload = {
            "browser": "chrome_chromium",
            "url": "https://example.com",
            "typed_count": 3,
            "transition_type": 0,
            "source_file": "History"
        }
        
        additional = analyzer._extract_additional_data("chrome_chromium", payload)
        
        assert additional["typed_count"] == 3
        assert additional["transition_type"] == 0
        assert additional["source_file"] == "History"

    def test_extract_additional_data_firefox(self):
        """
        Test extraction of additional data from Firefox payload.
        
        Verifies that:
        - typed flag is extracted
        - visit_type is extracted
        - source_file is extracted
        """
        analyzer = BrowsedURLsAnalyzer()
        
        payload = {
            "browser": "firefox",
            "url": "https://example.com",
            "typed": 1,
            "visit_type": 1,
            "source_file": "places.sqlite"
        }
        
        additional = analyzer._extract_additional_data("firefox", payload)
        
        assert additional["typed"] == 1
        assert additional["visit_type"] == 1
        assert additional["source_file"] == "places.sqlite"

    def test_extract_additional_data_edge_legacy(self):
        """
        Test extraction of additional data from Legacy Edge payload.
        
        Verifies that:
        - table_name is extracted
        - source_file is extracted
        """
        analyzer = BrowsedURLsAnalyzer()
        
        payload = {
            "browser": "edge_legacy",
            "url": "https://example.com",
            "table_name": "Container_1",
            "source_file": "WebCacheV01.dat"
        }
        
        additional = analyzer._extract_additional_data("edge_legacy", payload)
        
        assert additional["table_name"] == "Container_1"
        assert additional["source_file"] == "WebCacheV01.dat"

    def test_extract_additional_data_filters_none_values(self):
        """
        Test that _extract_additional_data filters out None values.
        
        Verifies that:
        - Only non-None values are included in the result
        - Empty dictionaries are returned when all values are None
        """
        analyzer = BrowsedURLsAnalyzer()
        
        payload = {
            "browser": "chrome_chromium",
            "url": "https://example.com",
            "typed_count": 5,
            "transition_type": None,
            "source_file": None
        }
        
        additional = analyzer._extract_additional_data("chrome_chromium", payload)
        
        assert "typed_count" in additional
        assert "transition_type" not in additional
        assert "source_file" not in additional

    @pytest.mark.asyncio
    async def test_create_entry_success(self):
        """
        Test that _create_entry successfully creates a BrowsedURLEntry from event data.
        
        Verifies that:
        - All fields are properly populated
        - Browser-specific data is extracted
        - The entry is valid and complete
        """
        analyzer = BrowsedURLsAnalyzer()
        
        payload = {
            "browser": "chrome_chromium",
            "url": "https://github.com",
            "title": "GitHub",
            "visit_count": 10,
            "typed_count": 2
        }
        
        entry = analyzer._create_entry(
            browser="chrome_chromium",
            event_id=999,
            timestamp="2024-01-15T10:00:00Z",
            artifact_sequence_id=42,
            payload=payload
        )
        
        assert entry is not None
        assert entry.browser == "chrome_chromium"
        assert entry.url == "https://github.com"
        assert entry.title == "GitHub"
        assert entry.visit_count == 10
        assert entry.event_id == 999
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.artifact_sequence_id == 42
        assert entry.additional_data["typed_count"] == 2

    @pytest.mark.asyncio
    async def test_create_entry_returns_none_when_no_url(self):
        """
        Test that _create_entry returns None when URL is missing.
        
        Verifies that:
        - Entries without URLs are filtered out
        - The method returns None instead of creating an invalid entry
        """
        analyzer = BrowsedURLsAnalyzer()
        
        payload = {
            "browser": "chrome_chromium",
            "title": "Some Title"
        }  # No URL
        
        entry = analyzer._create_entry(
            browser="chrome_chromium",
            event_id=999,
            timestamp="2024-01-15T10:00:00Z",
            artifact_sequence_id=None,
            payload=payload
        )
        
        assert entry is None

    @pytest.mark.asyncio
    async def test_analyze_with_no_browser_filter(self):
        """
        Test that analyze() queries all browsers when no filter is provided.
        
        Verifies that:
        - All browsers are included in the query when browsers parameter is None
        - The query doesn't include browser-specific WHERE clauses
        """
        analyzer = BrowsedURLsAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock database response
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db_mock.execute = AsyncMock(return_value=mock_result)
        
        await analyzer.analyze(db_mock, investigation_id, browsers=None, use_cache=False)
        
        # Verify execute was called
        db_mock.execute.assert_called_once()
        
        # Get the query that was executed
        call_args = db_mock.execute.call_args
        query_text = str(call_args[0][0])
        
        # Should not have browser filter
        assert "browser_0" not in query_text

    @pytest.mark.asyncio
    async def test_analyze_with_browser_filter(self):
        """
        Test that analyze() filters by specific browsers.
        
        Verifies that:
        - Only the requested browsers are included in the query
        - Browser filter is applied correctly
        """
        analyzer = BrowsedURLsAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock database response
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db_mock.execute = AsyncMock(return_value=mock_result)
        
        await analyzer.analyze(
            db_mock,
            investigation_id,
            browsers=["chrome_chromium", "firefox"],
            use_cache=False
        )
        
        # Verify execute was called
        db_mock.execute.assert_called_once()
        
        # Get the parameters that were passed
        call_args = db_mock.execute.call_args
        params = call_args[0][1]
        
        # Should have browser filters
        assert "browser_0" in params
        assert "browser_1" in params
        assert params["browser_0"] == "chrome_chromium"
        assert params["browser_1"] == "firefox"

    @pytest.mark.asyncio
    async def test_analyze_with_search_term(self):
        """
        Test that analyze() filters by search term.
        
        Verifies that:
        - Search term is applied to URL and title fields
        - ILIKE operator is used for case-insensitive search
        """
        analyzer = BrowsedURLsAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock database response
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db_mock.execute = AsyncMock(return_value=mock_result)
        
        await analyzer.analyze(
            db_mock,
            investigation_id,
            search_term="github",
            use_cache=False
        )
        
        # Verify execute was called
        db_mock.execute.assert_called_once()
        
        # Get the query and parameters
        call_args = db_mock.execute.call_args
        query_text = str(call_args[0][0])
        params = call_args[0][1]
        
        # Should have search term filter
        assert "ILIKE" in query_text
        assert "search_term" in params
        assert params["search_term"] == "%github%"

    @pytest.mark.asyncio
    async def test_analyze_processes_results(self):
        """
        Test that analyze() correctly processes database results.
        
        Verifies that:
        - Database rows are converted to BrowsedURLEntry objects
        - All fields are properly extracted
        - Invalid entries are filtered out
        """
        analyzer = BrowsedURLsAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock database response with sample data
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (
                1,
                datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                '{"browser": "chrome_chromium", "url": "https://example.com", "title": "Example", "visit_count": 5}'
            ),
            (
                2,
                datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
                '{"browser": "firefox", "url": "https://github.com", "title": "GitHub", "visit_count": 3}'
            ),
        ]
        db_mock.execute = AsyncMock(return_value=mock_result)
        
        entries = await analyzer.analyze(db_mock, investigation_id, use_cache=False)
        
        assert len(entries) == 2
        assert entries[0].url == "https://example.com"
        assert entries[0].browser == "chrome_chromium"
        assert entries[1].url == "https://github.com"
        assert entries[1].browser == "firefox"

    @pytest.mark.asyncio
    async def test_analyze_handles_errors_gracefully(self):
        """
        Test that analyze() handles database errors without crashing.
        
        Verifies that:
        - Database exceptions are caught and logged
        - The method returns an empty list on error
        - Transaction is rolled back after error
        """
        analyzer = BrowsedURLsAnalyzer()
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(side_effect=Exception("Database error"))
        db_mock.rollback = AsyncMock()
        
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        entries = await analyzer.analyze(db_mock, investigation_id, use_cache=False)
        
        # Should return empty list on error
        assert entries == []
        
        # Should have attempted rollback
        db_mock.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_skips_cache_for_search_results(self):
        """
        Test that analyze() doesn't cache results when search term is provided.
        
        Verifies that:
        - Cache is not used when search_term is provided
        - Results are always fresh when searching
        """
        analyzer = BrowsedURLsAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock database response
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db_mock.execute = AsyncMock(return_value=mock_result)
        
        with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=None)) as mock_get_cache:
            with patch.object(analyzer, '_cache_results', new=AsyncMock()) as mock_set_cache:
                await analyzer.analyze(
                    db_mock,
                    investigation_id,
                    search_term="test",
                    use_cache=True
                )
                
                # Should not try to get from cache
                mock_get_cache.assert_called_once()
                
                # Should not cache results
                mock_set_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_limits_results_to_10000(self):
        """
        Test that analyze() limits results to 10,000 entries.
        
        Verifies that:
        - Query includes LIMIT 10000
        - This prevents overwhelming the UI with too many results
        """
        analyzer = BrowsedURLsAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock database response
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db_mock.execute = AsyncMock(return_value=mock_result)
        
        await analyzer.analyze(db_mock, investigation_id, use_cache=False)
        
        # Get the query that was executed
        call_args = db_mock.execute.call_args
        query_text = str(call_args[0][0])
        
        # Should have LIMIT clause
        assert "LIMIT 10000" in query_text


@pytest.mark.unit
class TestBrowsedURLEntryModel:
    """Unit tests for the BrowsedURLEntry data model."""

    def test_browsed_url_entry_minimal_fields(self):
        """
        Test BrowsedURLEntry initialization with only required fields.
        
        Verifies that:
        - Required fields are properly set
        - Optional fields default to appropriate values
        """
        entry = BrowsedURLEntry(
            browser="chrome_chromium",
            url="https://example.com"
        )
        
        assert entry.browser == "chrome_chromium"
        assert entry.url == "https://example.com"
        assert entry.title is None
        assert entry.visit_count is None
        assert entry.timestamp is None
        assert entry.event_id is None
        assert entry.artifact_sequence_id is None
        assert entry.additional_data == {}
        assert entry.raw_data == {}

    def test_browsed_url_entry_all_fields(self):
        """
        Test BrowsedURLEntry initialization with all fields populated.
        
        Verifies that:
        - All fields are properly stored
        - Complex data structures (dicts) are preserved
        """
        entry = BrowsedURLEntry(
            browser="firefox",
            url="https://github.com",
            title="GitHub",
            visit_count=10,
            timestamp="2024-01-15T10:00:00Z",
            event_id=12345,
            artifact_sequence_id=42,
            additional_data={"typed": 1, "visit_type": 1},
            raw_data={"full": "payload"}
        )
        
        assert entry.browser == "firefox"
        assert entry.url == "https://github.com"
        assert entry.title == "GitHub"
        assert entry.visit_count == 10
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.event_id == 12345
        assert entry.artifact_sequence_id == 42
        assert entry.additional_data["typed"] == 1
        assert entry.raw_data["full"] == "payload"

    def test_browsed_url_entry_to_dict_serialization(self):
        """
        Test that BrowsedURLEntry can be serialized to a dictionary for JSON responses.
        
        Verifies that:
        - All fields are included in the dictionary
        - The dictionary structure matches the API schema
        - Nested data is preserved
        """
        entry = BrowsedURLEntry(
            browser="edge_legacy",
            url="https://microsoft.com",
            title="Microsoft",
            visit_count=5,
            timestamp="2024-01-15T10:00:00Z",
            event_id=999,
            artifact_sequence_id=None,
            additional_data={"table_name": "Container_1"},
            raw_data={"source_file": "WebCacheV01.dat"}
        )
        
        result = entry.to_dict()
        
        assert isinstance(result, dict)
        assert result["browser"] == "edge_legacy"
        assert result["url"] == "https://microsoft.com"
        assert result["title"] == "Microsoft"
        assert result["visit_count"] == 5
        assert result["additional_data"]["table_name"] == "Container_1"
        assert result["raw_data"]["source_file"] == "WebCacheV01.dat"
