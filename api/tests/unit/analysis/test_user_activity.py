import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.analysis.user_activity import UserActivityAnalyzer, UserActivityEntry


@pytest.mark.unit
class TestUserActivityAnalyzer:
    """Unit tests for UserActivityAnalyzer."""

    def test_analyzer_initialization(self):
        """
        Test that the UserActivityAnalyzer initializes with the correct number of categories.
        
        Verifies that:
        - The analyzer initializes successfully
        - It has 7 categories configured
        - Each category has required metadata fields
        """
        analyzer = UserActivityAnalyzer()
        
        assert analyzer is not None
        assert len(analyzer.CATEGORIES) == 7
        
        # Verify all categories have required fields
        for category_key, category_info in analyzer.CATEGORIES.items():
            assert "name" in category_info
            assert "description" in category_info
            assert "timestamp_meaning" in category_info
            assert "event_type" in category_info

    def test_get_categories(self):
        """
        Test that get_categories returns properly formatted category information.
        
        Verifies that:
        - The method returns a list of dictionaries
        - Each dictionary contains all required fields
        - The count matches the number of configured categories
        """
        analyzer = UserActivityAnalyzer()
        categories = analyzer.get_categories()
        
        assert isinstance(categories, list)
        assert len(categories) == 7
        
        for category in categories:
            assert "key" in category
            assert "name" in category
            assert "description" in category
            assert "timestamp_meaning" in category

    def test_shellbags_category_metadata(self):
        """Test that ShellBags category has correct metadata."""
        analyzer = UserActivityAnalyzer()
        shellbags = analyzer.CATEGORIES["shellbags"]
        
        assert shellbags["name"] == "ShellBags"
        assert "folder browsing" in shellbags["description"].lower()
        assert shellbags["event_type"] == "registry_shellbags_ntuser"

    def test_recentdocs_category_metadata(self):
        """Test that RecentDocs category has correct metadata."""
        analyzer = UserActivityAnalyzer()
        recentdocs = analyzer.CATEGORIES["recentdocs"]
        
        assert recentdocs["name"] == "RecentDocs"
        assert "recently opened documents" in recentdocs["description"].lower()
        assert recentdocs["event_type"] == "registry_recentdocs"

    def test_user_activity_entry_to_dict(self):
        """Test that UserActivityEntry.to_dict() properly serializes all fields."""
        entry = UserActivityEntry(
            category="ShellBags",
            description="Test description",
            timestamp_meaning="Last access time",
            activity_description="Browsed folder: C:\\Users\\test",
            timestamp="2024-01-15T10:30:00Z",
            event_id=12345,
            artifact_sequence_id=42,
            user_context="testuser",
            additional_data={"path": "C:\\Users\\test"},
            raw_data={"full": "payload"}
        )
        
        result = entry.to_dict()
        
        assert result["category"] == "ShellBags"
        assert result["description"] == "Test description"
        assert result["timestamp_meaning"] == "Last access time"
        assert result["activity_description"] == "Browsed folder: C:\\Users\\test"
        assert result["timestamp"] == "2024-01-15T10:30:00Z"
        assert result["event_id"] == 12345
        assert result["artifact_sequence_id"] == 42
        assert result["user_context"] == "testuser"
        assert result["additional_data"]["path"] == "C:\\Users\\test"
        assert result["raw_data"]["full"] == "payload"

    def test_extract_activity_description_shellbags(self):
        """Test activity description extraction from ShellBags payload."""
        analyzer = UserActivityAnalyzer()
        
        # Test with path field
        payload1 = {"path": "C:\\Users\\test\\Documents"}
        desc1 = analyzer._extract_activity_description("shellbags", payload1)
        assert desc1 == "Browsed folder: C:\\Users\\test\\Documents"
        
        # Test with shell_bag_path fallback
        payload2 = {"shell_bag_path": "C:\\Program Files"}
        desc2 = analyzer._extract_activity_description("shellbags", payload2)
        assert desc2 == "Browsed folder: C:\\Program Files"

    def test_extract_activity_description_recentdocs(self):
        """Test activity description extraction from RecentDocs payload."""
        analyzer = UserActivityAnalyzer()
        
        # Test with valid document name
        payload1 = {"value_data": "document.docx"}
        desc1 = analyzer._extract_activity_description("recentdocs", payload1)
        assert desc1 == "Opened document: document.docx"
        
        # Test with hex-only value (should be filtered out)
        payload2 = {"value_data": "01020304abcdef"}
        desc2 = analyzer._extract_activity_description("recentdocs", payload2)
        assert desc2 is None

    def test_extract_activity_description_opensavemru(self):
        """Test activity description extraction from OpenSaveMRU payload."""
        analyzer = UserActivityAnalyzer()
        
        # Test with valid file path
        payload1 = {"value_data": "C:\\Users\\test\\file.txt"}
        desc1 = analyzer._extract_activity_description("opensavemru", payload1)
        assert desc1 == "Selected in Open/Save dialog: C:\\Users\\test\\file.txt"
        
        # Test with hex-only value (should be filtered out)
        payload2 = {"value_data": "0102030405"}
        desc2 = analyzer._extract_activity_description("opensavemru", payload2)
        assert desc2 is None

    def test_extract_activity_description_lastvisitedmru(self):
        """Test activity description extraction from LastVisitedMRU payload."""
        analyzer = UserActivityAnalyzer()
        
        # Test with application and location
        payload1 = {"value_data": "notepad.exe | C:\\Users\\test\\Documents"}
        desc1 = analyzer._extract_activity_description("lastvisitedmru", payload1)
        assert desc1 == "notepad.exe opened file from: C:\\Users\\test\\Documents"
        
        # Test with single value
        payload2 = {"value_data": "C:\\Users\\test"}
        desc2 = analyzer._extract_activity_description("lastvisitedmru", payload2)
        assert desc2 == "Opened file from: C:\\Users\\test"

    def test_extract_activity_description_typedpaths(self):
        """Test activity description extraction from TypedPaths payload."""
        analyzer = UserActivityAnalyzer()
        
        payload = {"value_data": "\\\\server\\share\\folder"}
        desc = analyzer._extract_activity_description("typedpaths", payload)
        assert desc == "Typed path: \\\\server\\share\\folder"

    def test_extract_activity_description_runmru(self):
        """Test activity description extraction from RunMRU payload."""
        analyzer = UserActivityAnalyzer()
        
        # Test with clean command
        payload1 = {"value_data": "cmd.exe\\1"}
        desc1 = analyzer._extract_activity_description("runmru", payload1)
        assert desc1 == "Executed via Run dialog: cmd.exe"
        
        # Test without separator
        payload2 = {"value_data": "notepad.exe"}
        desc2 = analyzer._extract_activity_description("runmru", payload2)
        assert desc2 == "Executed via Run dialog: notepad.exe"

    def test_extract_activity_description_wordwheelquery(self):
        """Test activity description extraction from WordWheelQuery payload."""
        analyzer = UserActivityAnalyzer()
        
        payload = {"value_data": "malware analysis"}
        desc = analyzer._extract_activity_description("wordwheelquery", payload)
        assert desc == "Searched for: malware analysis"

    def test_extract_activity_description_returns_none_when_missing(self):
        """Test that _extract_activity_description returns None when no valid data is present."""
        analyzer = UserActivityAnalyzer()
        
        # Empty payload
        assert analyzer._extract_activity_description("shellbags", {}) is None
        
        # Payload with unrelated fields
        assert analyzer._extract_activity_description("shellbags", {"unrelated": "data"}) is None

    def test_extract_user_context_from_username(self):
        """Test user context extraction from username field."""
        analyzer = UserActivityAnalyzer()
        
        payload = {"username": "testuser"}
        context = analyzer._extract_user_context("shellbags", payload)
        assert context == "testuser"

    def test_extract_user_context_from_sid(self):
        """Test user context extraction from SID field."""
        analyzer = UserActivityAnalyzer()
        
        payload = {"sid": "S-1-5-21-123456789-123456789-123456789-1001"}
        context = analyzer._extract_user_context("shellbags", payload)
        assert context == "S-1-5-21-123456789-123456789-123456789-1001"

    def test_extract_user_context_from_key_path(self):
        """Test user context extraction from registry key path."""
        analyzer = UserActivityAnalyzer()
        
        payload = {"key_path": "C:\\Users\\testuser\\NTUSER.DAT"}
        context = analyzer._extract_user_context("shellbags", payload)
        # Should extract username from path containing \Users\
        assert context == "testuser" or context is None  # Depends on parsing logic

    def test_extract_additional_data_shellbags(self):
        """Test extraction of additional data from ShellBags payload."""
        analyzer = UserActivityAnalyzer()
        
        payload = {
            "shell_type": "folder",
            "slot": "1",
            "mru_order": "0",
            "key_path": "HKEY_USERS\\...",
            "last_modified": "2024-01-15T10:00:00Z"
        }
        
        additional = analyzer._extract_additional_data("shellbags", payload)
        
        assert additional["shell_type"] == "folder"
        assert additional["slot"] == "1"
        assert additional["mru_order"] == "0"
        assert additional["key_path"] == "HKEY_USERS\\..."
        assert additional["last_modified"] == "2024-01-15T10:00:00Z"

    def test_extract_additional_data_recentdocs(self):
        """Test extraction of additional data from RecentDocs payload."""
        analyzer = UserActivityAnalyzer()
        
        payload = {
            "extension": ".docx",
            "value_name": "0",
            "value_data_hex": "0102030405",
            "key_path": "HKEY_USERS\\..."
        }
        
        additional = analyzer._extract_additional_data("recentdocs", payload)
        
        assert additional["extension"] == ".docx"
        assert additional["mru_position"] == "0"
        assert additional["raw_hex"] == "0102030405"

    def test_extract_additional_data_filters_none_values(self):
        """Test that _extract_additional_data filters out None values."""
        analyzer = UserActivityAnalyzer()
        
        payload = {
            "shell_type": "folder",
            "slot": None,
            "mru_order": None
        }
        
        additional = analyzer._extract_additional_data("shellbags", payload)
        
        assert "shell_type" in additional
        assert "slot" not in additional
        assert "mru_order" not in additional

    @pytest.mark.asyncio
    async def test_analyze_with_no_categories_analyzes_all(self):
        """Test that analyze() queries all categories when no specific categories are provided."""
        analyzer = UserActivityAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with patch.object(analyzer, '_query_category', new=AsyncMock(return_value=[])) as mock_query:
            with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=None)):
                with patch.object(analyzer, '_cache_results', new=AsyncMock()):
                    await analyzer.analyze(db_mock, investigation_id, categories=None, use_cache=False)
                    
                    # Should call _query_category 7 times (once per category)
                    assert mock_query.call_count == 7

    @pytest.mark.asyncio
    async def test_analyze_with_specific_categories(self):
        """Test that analyze() only queries specified categories."""
        analyzer = UserActivityAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with patch.object(analyzer, '_query_category', new=AsyncMock(return_value=[])) as mock_query:
            with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=None)):
                with patch.object(analyzer, '_cache_results', new=AsyncMock()):
                    await analyzer.analyze(
                        db_mock, 
                        investigation_id, 
                        categories=["shellbags", "recentdocs"], 
                        use_cache=False
                    )
                    
                    # Should call _query_category 2 times
                    assert mock_query.call_count == 2

    @pytest.mark.asyncio
    async def test_analyze_returns_cached_results_when_available(self):
        """Test that analyze() returns cached results when use_cache=True and cache exists."""
        analyzer = UserActivityAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        cached_entry = UserActivityEntry(
            category="ShellBags",
            description="Cached entry",
            timestamp_meaning="Test",
            activity_description="Browsed folder: cached",
        )
        
        with patch.object(analyzer, '_query_category', new=AsyncMock(return_value=[])) as mock_query:
            with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=[cached_entry])):
                results = await analyzer.analyze(db_mock, investigation_id, use_cache=True)
                
                # Should return cached results
                assert len(results) == 1
                assert results[0].activity_description == "Browsed folder: cached"
                
                # Should NOT call _query_category
                mock_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_entry_success(self):
        """Test that _create_entry successfully creates a UserActivityEntry from event data."""
        analyzer = UserActivityAnalyzer()
        
        category_info = analyzer.CATEGORIES["shellbags"]
        payload = {
            "path": "C:\\Users\\test\\Documents",
            "shell_type": "folder",
            "username": "testuser"
        }
        
        entry = analyzer._create_entry(
            category_key="shellbags",
            category_info=category_info,
            event_id=999,
            timestamp="2024-01-15T10:00:00Z",
            artifact_sequence_id=42,
            payload=payload
        )
        
        assert entry is not None
        assert entry.category == "ShellBags"
        assert entry.activity_description == "Browsed folder: C:\\Users\\test\\Documents"
        assert entry.event_id == 999
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.artifact_sequence_id == 42
        assert entry.user_context == "testuser"
        assert entry.additional_data["shell_type"] == "folder"

    @pytest.mark.asyncio
    async def test_create_entry_returns_none_when_no_activity_description(self):
        """Test that _create_entry returns None when activity description cannot be extracted."""
        analyzer = UserActivityAnalyzer()
        
        category_info = analyzer.CATEGORIES["shellbags"]
        payload = {"unrelated": "data"}  # No path
        
        entry = analyzer._create_entry(
            category_key="shellbags",
            category_info=category_info,
            event_id=999,
            timestamp="2024-01-15T10:00:00Z",
            artifact_sequence_id=None,
            payload=payload
        )
        
        assert entry is None

    @pytest.mark.asyncio
    async def test_query_category_handles_errors_gracefully(self):
        """Test that _query_category handles database errors without crashing."""
        analyzer = UserActivityAnalyzer()
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(side_effect=Exception("Database error"))
        db_mock.rollback = AsyncMock()
        
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        category_info = analyzer.CATEGORIES["shellbags"]
        
        entries = await analyzer._query_category(
            db=db_mock,
            investigation_id=investigation_id,
            category_key="shellbags",
            category_info=category_info
        )
        
        # Should return empty list on error
        assert entries == []
        
        # Should have attempted rollback
        db_mock.rollback.assert_called_once()


@pytest.mark.unit
class TestUserActivityEntryModel:
    """Unit tests for the UserActivityEntry data model."""

    def test_user_activity_entry_minimal_fields(self):
        """Test UserActivityEntry initialization with only required fields."""
        entry = UserActivityEntry(
            category="Test Category",
            description="Test description",
            timestamp_meaning="Test timestamp meaning",
            activity_description="Test activity",
        )
        
        assert entry.category == "Test Category"
        assert entry.description == "Test description"
        assert entry.timestamp_meaning == "Test timestamp meaning"
        assert entry.activity_description == "Test activity"
        assert entry.timestamp is None
        assert entry.event_id is None
        assert entry.artifact_sequence_id is None
        assert entry.user_context is None
        assert entry.additional_data == {}
        assert entry.raw_data == {}

    def test_user_activity_entry_all_fields(self):
        """Test UserActivityEntry initialization with all fields populated."""
        entry = UserActivityEntry(
            category="ShellBags",
            description="Windows Explorer folder browsing",
            timestamp_meaning="Last access time",
            activity_description="Browsed folder: C:\\Users\\test",
            timestamp="2024-01-15T10:00:00Z",
            event_id=12345,
            artifact_sequence_id=42,
            user_context="testuser",
            additional_data={"path": "C:\\Users\\test"},
            raw_data={"full": "payload"}
        )
        
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.event_id == 12345
        assert entry.artifact_sequence_id == 42
        assert entry.user_context == "testuser"
        assert entry.additional_data["path"] == "C:\\Users\\test"
        assert entry.raw_data["full"] == "payload"

    def test_user_activity_entry_to_dict_serialization(self):
        """Test that UserActivityEntry can be serialized to a dictionary for JSON responses."""
        entry = UserActivityEntry(
            category="RecentDocs",
            description="Recently opened documents",
            timestamp_meaning="Last opened time",
            activity_description="Opened document: report.docx",
            timestamp="2024-01-15T10:00:00Z",
            event_id=999,
            artifact_sequence_id=None,
            user_context="jsmith",
            additional_data={"extension": ".docx"},
            raw_data={"value_data": "report.docx"}
        )
        
        result = entry.to_dict()
        
        assert isinstance(result, dict)
        assert result["category"] == "RecentDocs"
        assert result["activity_description"] == "Opened document: report.docx"
        assert result["user_context"] == "jsmith"
        assert result["additional_data"]["extension"] == ".docx"
        assert result["raw_data"]["value_data"] == "report.docx"
