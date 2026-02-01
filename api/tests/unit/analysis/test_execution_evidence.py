"""
Unit tests for the Execution Evidence Analyzer.

Tests the ExecutionEvidenceAnalyzer class which analyzes Windows execution artifacts
including Prefetch, SRUM, Jump Lists, and LNK files.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from datetime import datetime, timezone

from app.analysis.execution_evidence import ExecutionEvidenceAnalyzer, ExecutionEntry


@pytest.mark.unit
class TestExecutionEvidenceAnalyzer:
    """Unit tests for ExecutionEvidenceAnalyzer."""

    def test_analyzer_initialization(self):
        """
        Test that the ExecutionEvidenceAnalyzer initializes with the correct number of categories.
        
        Verifies that:
        - The analyzer initializes successfully
        - It has 4 categories configured (Prefetch, SRUM, Jump Lists, LNK Files)
        - Each category has required metadata fields
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        assert analyzer is not None
        assert len(analyzer.CATEGORIES) == 4
        
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
        assert len(categories) == 4
        
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

    def test_srum_category_metadata(self):
        """
        Test that SRUM category has correct metadata.
        
        Verifies that:
        - SRUM proves execution (True)
        - SRUM does NOT prove presence (False)
        - Event type is "srum_data"
        """
        analyzer = ExecutionEvidenceAnalyzer()
        srum = analyzer.CATEGORIES["srum"]
        
        assert srum["name"] == "SRUM Database"
        assert srum["proves_execution"] is True
        assert srum["proves_presence"] is False
        assert srum["event_type"] == "srum_data"

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

    def test_extract_executable_path_srum(self):
        """
        Test executable path extraction from SRUM payload.
        
        Verifies that:
        - The method extracts path from "app_id" field
        - Falls back to "application" if "app_id" is not present
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        # Test with app_id
        payload1 = {"app_id": "\\Device\\HarddiskVolume2\\Windows\\System32\\svchost.exe"}
        path1 = analyzer._extract_executable_path("srum", payload1)
        assert path1 == "\\Device\\HarddiskVolume2\\Windows\\System32\\svchost.exe"
        
        # Test with application fallback
        payload2 = {"application": "chrome.exe"}
        path2 = analyzer._extract_executable_path("srum", payload2)
        assert path2 == "chrome.exe"

    def test_extract_executable_path_lnk(self):
        """
        Test executable path extraction from LNK file payload.
        
        Verifies that:
        - The method extracts path from "target_path" field
        - Falls back to "local_path" if "target_path" is not present
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        # Test with target_path
        payload1 = {"target_path": "C:\\Program Files\\App\\app.exe"}
        path1 = analyzer._extract_executable_path("lnk_files", payload1)
        assert path1 == "C:\\Program Files\\App\\app.exe"
        
        # Test with local_path fallback
        payload2 = {"local_path": "C:\\Users\\test\\Desktop\\shortcut.lnk"}
        path2 = analyzer._extract_executable_path("lnk_files", payload2)
        assert path2 == "C:\\Users\\test\\Desktop\\shortcut.lnk"

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
        - run_count is extracted
        - file_size is extracted
        - hash is extracted
        - execution_times array is extracted and split into last_run and previous_runs
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "run_count": 42,
            "file_size": 12345,
            "hash": "ABC123DEF456",
            "execution_times": [
                "2024-01-15T10:00:00Z",
                "2024-01-14T09:00:00Z",
                "2024-01-13T08:00:00Z"
            ]
        }
        
        additional = analyzer._extract_additional_data("prefetch", payload)
        
        assert additional["run_count"] == 42
        assert additional["file_size"] == 12345
        assert additional["hash"] == "ABC123DEF456"
        assert additional["execution_times"] == payload["execution_times"]
        assert additional["last_run_time"] == "2024-01-15T10:00:00Z"
        assert len(additional["previous_run_times"]) == 2
        assert additional["previous_run_times"][0] == "2024-01-14T09:00:00Z"

    def test_extract_additional_data_srum(self):
        """
        Test extraction of additional data from SRUM payload.
        
        Verifies that:
        - bytes_sent is extracted
        - bytes_received is extracted
        - network interface is extracted
        - user_sid is extracted
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "bytes_sent": 1024000,
            "bytes_received": 2048000,
            "interface_luid": "0x123456",
            "user_sid": "S-1-5-21-123456789-123456789-123456789-1001"
        }
        
        additional = analyzer._extract_additional_data("srum", payload)
        
        assert additional["bytes_sent"] == 1024000
        assert additional["bytes_received"] == 2048000
        assert additional["network_interface"] == "0x123456"
        assert additional["user_sid"] == "S-1-5-21-123456789-123456789-123456789-1001"

    def test_extract_additional_data_lnk(self):
        """
        Test extraction of additional data from LNK file payload.
        
        Verifies that:
        - File timestamps are extracted
        - File attributes are extracted
        - Working directory is extracted
        - Command line arguments are extracted
        - Drive information is extracted
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "file_size": 4096,
            "file_attributes": 32,
            "creation_time": "2024-01-01T00:00:00Z",
            "access_time": "2024-01-15T10:00:00Z",
            "write_time": "2024-01-10T15:30:00Z",
            "working_directory": "C:\\Users\\test\\Documents",
            "command_line_arguments": "--verbose --debug",
            "drive_type": "FIXED",
            "volume_serial_number": "12345678"
        }
        
        additional = analyzer._extract_additional_data("lnk_files", payload)
        
        assert additional["file_size"] == 4096
        assert additional["file_attributes"] == 32
        assert additional["creation_time"] == "2024-01-01T00:00:00Z"
        assert additional["access_time"] == "2024-01-15T10:00:00Z"
        assert additional["write_time"] == "2024-01-10T15:30:00Z"
        assert additional["working_directory"] == "C:\\Users\\test\\Documents"
        assert additional["command_line_args"] == "--verbose --debug"
        assert additional["drive_type"] == "FIXED"
        assert additional["volume_serial"] == "12345678"

    def test_extract_additional_data_filters_none_values(self):
        """
        Test that _extract_additional_data filters out None values.
        
        Verifies that:
        - Only non-None values are included in the result
        - Empty dictionaries are returned when all values are None
        """
        analyzer = ExecutionEvidenceAnalyzer()
        
        payload = {
            "run_count": 5,
            "file_size": None,
            "hash": None
        }
        
        additional = analyzer._extract_additional_data("prefetch", payload)
        
        assert "run_count" in additional
        assert "file_size" not in additional
        assert "hash" not in additional

    @pytest.mark.asyncio
    async def test_analyze_with_no_categories_analyzes_all(self):
        """
        Test that analyze() queries all categories when no specific categories are provided.
        
        Verifies that:
        - All 4 categories are analyzed when categories parameter is None
        - The method calls _query_category for each category
        """
        analyzer = ExecutionEvidenceAnalyzer()
        db_mock = AsyncMock()
        investigation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with patch.object(analyzer, '_query_category', new=AsyncMock(return_value=[])) as mock_query:
            with patch.object(analyzer, '_get_cached_results', new=AsyncMock(return_value=None)):
                with patch.object(analyzer, '_cache_results', new=AsyncMock()):
                    await analyzer.analyze(db_mock, investigation_id, categories=None, use_cache=False)
                    
                    # Should call _query_category 4 times (once per category)
                    assert mock_query.call_count == 4

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
                        categories=["prefetch", "srum"], 
                        use_cache=False
                    )
                    
                    # Should call _query_category 2 times (only for prefetch and srum)
                    assert mock_query.call_count == 2

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
            "run_count": 10,
            "file_size": 12345,
            "hash": "ABC123"
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
        assert entry.additional_data["run_count"] == 10

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
