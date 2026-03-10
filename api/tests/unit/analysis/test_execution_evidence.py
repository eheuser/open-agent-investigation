import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.analysis.execution_evidence import ExecutionEvidenceAnalyzer, ExecutionEntry


@pytest.mark.unit
class TestExecutionEvidenceAnalyzer:
    """Unit tests for ExecutionEvidenceAnalyzer."""

    def test_analyzer_initialization(self):
        """
        Test that the ExecutionEvidenceAnalyzer initializes with the correct number of categories.
        
        Verifies that:
        - The analyzer initializes successfully
        - It has 8 categories configured (Prefetch, ShimCache, AmCache, UserAssist, PCA, BAM/DAM, Jump Lists, LNK Files)
        - Each category has required metadata fields
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        assert analyzer is not None
        assert len(analyzer.CATEGORIES) == 8
        
        # Verify all categories have required fields
        for category_key, category_info in analyzer.CATEGORIES.items():
            assert "name" in category_info
            assert "description" in category_info
            assert "timestamp_meaning" in category_info
            assert "proves_execution" in category_info
            assert "proves_presence" in category_info
            assert "event_type" in category_info

    def test_get_categories(self):
        """
        Test that get_categories returns properly formatted category information.
        
        Verifies that:
        - The method returns a list of dictionaries
        - Each dictionary contains all required fields
        - The count matches the number of configured categories
        """
        analyzer = ExecutionEvidenceAnalyzer()
        categories = analyzer.get_categories()
        
        assert isinstance(categories, list)
        assert len(categories) == 8
        
        for category in categories:
            assert "key" in category
            assert "name" in category
            assert "description" in category
            assert "timestamp_meaning" in category
            assert "proves_execution" in category
            assert "proves_presence" in category

    def test_prefetch_category_metadata(self):
        """
        Test that Prefetch category has correct metadata.
        
        Verifies that:
        - Prefetch proves execution (True)
        - Prefetch proves presence (True)
        - Event type is "prefetch_execution"
        - Timestamp meaning is documented
        """
        analyzer = ExecutionEvidenceAnalyzer()
        prefetch = analyzer.CATEGORIES["prefetch"]
        
        assert prefetch["name"] == "Prefetch"
        assert prefetch["proves_execution"] is True
        assert prefetch["proves_presence"] is True
        assert prefetch["event_type"] == "prefetch_execution"
        assert "execution time" in prefetch["timestamp_meaning"].lower()

    def test_shimcache_category_metadata(self):
        """
        Test that ShimCache category has correct metadata.
        
        Verifies that:
        - ShimCache proves execution (True)
        - ShimCache proves presence (True)
        - Event type is "registry_shimcache"
        """
        analyzer = ExecutionEvidenceAnalyzer()
        shimcache = analyzer.CATEGORIES["shimcache"]
        
        assert shimcache["name"] == "ShimCache (AppCompatCache)"
        assert shimcache["proves_execution"] is True
        assert shimcache["proves_presence"] is True
        assert shimcache["event_type"] == "registry_shimcache"

    def test_lnk_files_category_metadata(self):
        """
        Test that LNK Files category has correct metadata.
        
        Verifies that:
        - LNK Files do NOT prove execution (False)
        - LNK Files prove presence (True)
        - Event type is "lnk_file"
        """
        analyzer = ExecutionEvidenceAnalyzer()
        lnk = analyzer.CATEGORIES["lnk_files"]
        
        assert lnk["name"] == "LNK Files (Shortcuts)"
        assert lnk["proves_execution"] is False
        assert lnk["proves_presence"] is True
        assert lnk["event_type"] == "lnk_file"

    def test_execution_entry_to_dict(self):
        """
        Test that ExecutionEntry.to_dict() properly serializes all fields.
        
        Verifies that:
        - All fields are included in the dictionary
        - Optional fields are preserved
        - The dictionary can be used for JSON serialization
        """
        entry = ExecutionEntry(
            category="Prefetch",
            description="Test description",
            timestamp_meaning="Last execution time",
            executable_path="C:\\Windows\\System32\\notepad.exe",
            timestamp="2024-01-15T10:30:00Z",
            event_id=12345,
            artifact_sequence_id=42,
            proves_execution=True,
            proves_presence=True,
            additional_data={"run_count": 5, "hash": "ABC123"},
            raw_data={"full": "payload"}
        )
        
        result = entry.to_dict()
        
        assert result["category"] == "Prefetch"
        assert result["description"] == "Test description"
        assert result["timestamp_meaning"] == "Last execution time"
        assert result["executable_path"] == "C:\\Windows\\System32\\notepad.exe"
        assert result["timestamp"] == "2024-01-15T10:30:00Z"
        assert result["event_id"] == 12345
        assert result["artifact_sequence_id"] == 42
        assert result["proves_execution"] is True
        assert result["proves_presence"] is True
        assert result["additional_data"]["run_count"] == 5
        assert result["raw_data"]["full"] == "payload"

    def test_extract_executable_path_prefetch(self):
        """
        Test executable path extraction from Prefetch payload.
        
        Verifies that:
        - The method extracts path from "executable_name" field
        - Falls back to "file_path" if "executable_name" is not present
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        # Test with executable_name
        payload1 = {"executable_name": "NOTEPAD.EXE"}
        path1 = analyzer._extract_executable_path("prefetch", payload1)
        assert path1 == "NOTEPAD.EXE"
        
        # Test with file_path fallback
        payload2 = {"file_path": "C:\\Windows\\Prefetch\\NOTEPAD.EXE-ABC123.pf"}
        path2 = analyzer._extract_executable_path("prefetch", payload2)
        assert path2 == "C:\\Windows\\Prefetch\\NOTEPAD.EXE-ABC123.pf"

    def test_extract_executable_path_amcache(self):
        """
        Test executable path extraction from AmCache payload.
        
        Verifies that:
        - The method extracts path from "name" field
        - Falls back to "lower_case_long_path" if "name" is not present
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        # Test with name field
        payload1 = {"name": "c:\\windows\\system32\\notepad.exe"}
        path1 = analyzer._extract_executable_path("amcache", payload1)
        assert path1 == "c:\\windows\\system32\\notepad.exe"
        
        # Test with lower_case_long_path fallback
        payload2 = {"lower_case_long_path": "c:\\program files\\app\\app.exe"}
        path2 = analyzer._extract_executable_path("amcache", payload2)
        assert path2 == "c:\\program files\\app\\app.exe"

    def test_extract_executable_path_lnk(self):
        """
        Test executable path extraction from LNK file payload.
        
        Verifies that:
        - The method extracts path from "link_info.local_base_path" field
        - Falls back to "data.relative_path" if "link_info.local_base_path" is not present
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        # Test with link_info.local_base_path
        payload1 = {"link_info.local_base_path": "C:\\Program Files\\App\\app.exe"}
        path1 = analyzer._extract_executable_path("lnk_files", payload1)
        assert path1 == "C:\\Program Files\\App\\app.exe"
        
        # Test with data.relative_path fallback
        payload2 = {"data.relative_path": "..\\..\\Desktop\\shortcut.lnk"}
        path2 = analyzer._extract_executable_path("lnk_files", payload2)
        assert path2 == "..\\..\\Desktop\\shortcut.lnk"

    def test_extract_executable_path_returns_none_when_missing(self):
        """
        Test that _extract_executable_path returns None when no path fields are present.
        
        Verifies that:
        - The method returns None for empty payloads
        - The method returns None when all path fields are missing
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        # Empty payload
        assert analyzer._extract_executable_path("prefetch", {}) is None
        
        # Payload with unrelated fields
        assert analyzer._extract_executable_path("prefetch", {"unrelated": "data"}) is None

    def test_extract_additional_data_prefetch(self):
        """
        Test extraction of additional data from Prefetch payload.
        
        Verifies that:
        - file_size is extracted
        - last_execution_time is extracted
        - original_path is extracted
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "file_size": 12345,
            "last_execution_time": "2024-01-15T10:00:00Z",
            "original_path": "C:\\Windows\\Prefetch\\NOTEPAD.EXE-ABC123.pf"
        }
        
        additional = analyzer._extract_additional_data("prefetch", payload)
        
        assert additional["file_size"] == 12345
        assert additional["last_execution_time"] == "2024-01-15T10:00:00Z"
        assert additional["original_path"] == "C:\\Windows\\Prefetch\\NOTEPAD.EXE-ABC123.pf"

    def test_extract_additional_data_amcache(self):
        """
        Test extraction of additional data from AmCache payload.
        
        Verifies that:
        - sha1 is extracted
        - file_size is extracted
        - publisher is extracted
        - version is extracted
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "sha1": "abc123def456",
            "size": 1024000,
            "publisher": "Microsoft Corporation",
            "version": "10.0.19041.1"
        }
        
        additional = analyzer._extract_additional_data("amcache", payload)
        
        assert additional["sha1"] == "abc123def456"
        assert additional["file_size"] == 1024000
        assert additional["publisher"] == "Microsoft Corporation"
        assert additional["version"] == "10.0.19041.1"

    def test_extract_additional_data_lnk(self):
        """
        Test extraction of additional data from LNK file payload.
        
        Verifies that:
        - File timestamps are extracted from header fields
        - Working directory is extracted from data fields
        - Drive information is extracted from link_info fields
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "header.file_size": 4096,
            "header.creation_time": "2024-01-01T00:00:00Z",
            "header.accessed_time": "2024-01-15T10:00:00Z",
            "header.modified_time": "2024-01-10T15:30:00Z",
            "data.working_directory": "C:\\Users\\test\\Documents",
            "data.relative_path": "..\\..\\Desktop\\file.txt",
            "link_info.location_info.drive_type": "FIXED",
            "link_info.location_info.drive_serial_number": "12345678"
        }
        
        additional = analyzer._extract_additional_data("lnk_files", payload)
        
        assert additional["file_size"] == 4096
        assert additional["creation_time"] == "2024-01-01T00:00:00Z"
        assert additional["accessed_time"] == "2024-01-15T10:00:00Z"
        assert additional["modified_time"] == "2024-01-10T15:30:00Z"
        assert additional["working_directory"] == "C:\\Users\\test\\Documents"
        assert additional["relative_path"] == "..\\..\\Desktop\\file.txt"
        assert additional["drive_type"] == "FIXED"
        assert additional["drive_serial"] == "12345678"

    def test_extract_additional_data_filters_none_values(self):
        """
        Test that _extract_additional_data filters out None values.
        
        Verifies that:
        - Only non-None values are included in the result
        - Empty dictionaries are returned when all values are None
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "file_size": 12345,
            "last_execution_time": None,
            "original_path": None
        }
        
        additional = analyzer._extract_additional_data("prefetch", payload)
        
        assert "file_size" in additional
        assert "last_execution_time" not in additional
        assert "original_path" not in additional

    @pytest.mark.asyncio
    async def test_analyze_with_no_categories_analyzes_all(self):
        """
        Test that analyze() queries all categories when no specific categories are provided.
        
        Verifies that:
        - All 8 categories are analyzed when categories parameter is None
        - The method calls _query_category for each category
        """
        analyzer = ExecutionEvidenceAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with patch.object(analyzer, '_query_category', new=AsyncMock(return_value=[])) as mock_query:
            with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=None)):
                with patch.object(analyzer, '_cache_results', new=AsyncMock()):
                    await analyzer.analyze(db_mock, investigation_id, categories=None, use_cache=False)
                    
                    # Should call _query_category 8 times (once per category)
                    assert mock_query.call_count == 8

    @pytest.mark.asyncio
    async def test_analyze_with_specific_categories(self):
        """
        Test that analyze() only queries specified categories.
        
        Verifies that:
        - Only the requested categories are analyzed
        - Other categories are skipped
        """
        analyzer = ExecutionEvidenceAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with patch.object(analyzer, '_query_category', new=AsyncMock(return_value=[])) as mock_query:
            with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=None)):
                with patch.object(analyzer, '_cache_results', new=AsyncMock()):
                    await analyzer.analyze(
                        db_mock, 
                        investigation_id, 
                        categories=["prefetch"], 
                        use_cache=False
                    )
                    
                    # Should call _query_category 1 time (only for prefetch)
                    assert mock_query.call_count == 1

    @pytest.mark.asyncio
    async def test_analyze_returns_cached_results_when_available(self):
        """
        Test that analyze() returns cached results when use_cache=True and cache exists.
        
        Verifies that:
        - Cached results are returned without querying the database
        - _query_category is not called when cache is available
        """
        analyzer = ExecutionEvidenceAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        cached_entry = ExecutionEntry(
            category="Prefetch",
            description="Cached entry",
            timestamp_meaning="Test",
            executable_path="cached.exe",
            proves_execution=True,
            proves_presence=True
        )
        
        with patch.object(analyzer, '_query_category', new=AsyncMock(return_value=[])) as mock_query:
            with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=[cached_entry])):
                results = await analyzer.analyze(db_mock, investigation_id, use_cache=True)
                
                # Should return cached results
                assert len(results) == 1
                assert results[0].executable_path == "cached.exe"
                
                # Should NOT call _query_category
                mock_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_entry_success(self):
        """
        Test that _create_entry successfully creates an ExecutionEntry from event data.
        
        Verifies that:
        - All fields are properly populated
        - Category-specific data is extracted
        - The entry is valid and complete
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        category_info = analyzer.CATEGORIES["prefetch"]
        payload = {
            "executable_name": "NOTEPAD.EXE",
            "file_size": 12345,
            "last_execution_time": "2024-01-15T10:00:00Z"
        }
        
        entry = analyzer._create_entry(
            category_key="prefetch",
            category_info=category_info,
            event_id=999,
            timestamp="2024-01-15T10:00:00Z",
            artifact_sequence_id=42,
            payload=payload
        )
        
        assert entry is not None
        assert entry.category == "Prefetch"
        assert entry.executable_path == "NOTEPAD.EXE"
        assert entry.event_id == 999
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.artifact_sequence_id == 42
        assert entry.proves_execution is True
        assert entry.proves_presence is True
        assert entry.additional_data["file_size"] == 12345

    @pytest.mark.asyncio
    async def test_create_entry_returns_none_when_no_executable_path(self):
        """
        Test that _create_entry returns None when executable path cannot be extracted.
        
        Verifies that:
        - Entries without executable paths are filtered out
        - The method returns None instead of creating an invalid entry
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        category_info = analyzer.CATEGORIES["prefetch"]
        payload = {"unrelated": "data"}  # No executable path
        
        entry = analyzer._create_entry(
            category_key="prefetch",
            category_info=category_info,
            event_id=999,
            timestamp="2024-01-15T10:00:00Z",
            artifact_sequence_id=None,
            payload=payload
        )
        
        assert entry is None

    @pytest.mark.asyncio
    async def test_query_category_handles_errors_gracefully(self):
        """
        Test that _query_category handles database errors without crashing.
        
        Verifies that:
        - Database exceptions are caught and logged
        - The method returns an empty list on error
        - Transaction is rolled back after error
        """
        analyzer = ExecutionEvidenceAnalyzer()
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock(side_effect=Exception("Database error"))
        db_mock.rollback = AsyncMock()
        
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        category_info = analyzer.CATEGORIES["prefetch"]
        
        entries = await analyzer._query_category(
            db=db_mock,
            investigation_id=investigation_id,
            category_key="prefetch",
            category_info=category_info
        )
        
        # Should return empty list on error
        assert entries == []
        
        # Should have attempted rollback
        db_mock.rollback.assert_called_once()


@pytest.mark.unit
class TestExecutionEntryModel:
    """Unit tests for the ExecutionEntry data model."""

    def test_execution_entry_minimal_fields(self):
        """
        Test ExecutionEntry initialization with only required fields.
        
        Verifies that:
        - Required fields are properly set
        - Optional fields default to appropriate values
        """
        entry = ExecutionEntry(
            category="Test Category",
            description="Test description",
            timestamp_meaning="Test timestamp meaning",
            executable_path="test.exe",
            proves_execution=True,
            proves_presence=False
        )
        
        assert entry.category == "Test Category"
        assert entry.description == "Test description"
        assert entry.timestamp_meaning == "Test timestamp meaning"
        assert entry.executable_path == "test.exe"
        assert entry.proves_execution is True
        assert entry.proves_presence is False
        assert entry.timestamp is None
        assert entry.event_id is None
        assert entry.artifact_sequence_id is None
        assert entry.additional_data == {}
        assert entry.raw_data == {}

    def test_execution_entry_all_fields(self):
        """
        Test ExecutionEntry initialization with all fields populated.
        
        Verifies that:
        - All fields are properly stored
        - Complex data structures (dicts) are preserved
        """
        entry = ExecutionEntry(
            category="Prefetch",
            description="Windows Prefetch",
            timestamp_meaning="Last execution time",
            executable_path="C:\\Windows\\notepad.exe",
            timestamp="2024-01-15T10:00:00Z",
            event_id=12345,
            artifact_sequence_id=42,
            proves_execution=True,
            proves_presence=True,
            additional_data={"run_count": 5},
            raw_data={"full": "payload"}
        )
        
        assert entry.timestamp == "2024-01-15T10:00:00Z"
        assert entry.event_id == 12345
        assert entry.artifact_sequence_id == 42
        assert entry.additional_data["run_count"] == 5
        assert entry.raw_data["full"] == "payload"

    def test_execution_entry_to_dict_serialization(self):
        """
        Test that ExecutionEntry can be serialized to a dictionary for JSON responses.
        
        Verifies that:
        - All fields are included in the dictionary
        - The dictionary structure matches the API schema
        - Nested data is preserved
        """
        entry = ExecutionEntry(
            category="SRUM Database",
            description="System Resource Usage Monitor",
            timestamp_meaning="Resource usage time",
            executable_path="\\Device\\HarddiskVolume2\\Windows\\System32\\svchost.exe",
            timestamp="2024-01-15T10:00:00Z",
            event_id=999,
            artifact_sequence_id=None,
            proves_execution=True,
            proves_presence=False,
            additional_data={"bytes_sent": 1024, "bytes_received": 2048},
            raw_data={"table_name": "NetworkUsage"}
        )
        
        result = entry.to_dict()
        
        assert isinstance(result, dict)
        assert result["category"] == "SRUM Database"
        assert result["executable_path"] == "\\Device\\HarddiskVolume2\\Windows\\System32\\svchost.exe"
        assert result["proves_execution"] is True
        assert result["proves_presence"] is False
        assert result["additional_data"]["bytes_sent"] == 1024
        assert result["raw_data"]["table_name"] == "NetworkUsage"
