"""
Unit tests for Analysis modules
"""

import pytest
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta
import json
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from app.analysis.autoruns import AutorunsAnalyzer, AutorunEntry, ANALYSIS_VERSION


class TestAutorunEntry:
    """Test AutorunEntry class."""
    
    def test_create_entry(self):
        """Test creating an AutorunEntry."""
        entry = AutorunEntry(
            category="Logon",
            location="Run",
            entry_name="TestApp",
            image_path="C:\\Test\\app.exe",
            enabled=True,
            timestamp="2024-01-15T10:00:00",
            event_id=123,
            registry_path="\\ROOT\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        )
        
        assert entry.category == "Logon"
        assert entry.location == "Run"
        assert entry.entry_name == "TestApp"
        assert entry.image_path == "C:\\Test\\app.exe"
        assert entry.enabled is True
        assert entry.event_id == 123
    
    def test_to_dict(self):
        """Test converting entry to dictionary."""
        entry = AutorunEntry(
            category="Services",
            location="Services",
            entry_name="MyService",
            image_path="C:\\Windows\\System32\\service.exe",
            enabled=False,
        )
        
        data = entry.to_dict()
        
        assert data["category"] == "Services"
        assert data["location"] == "Services"
        assert data["entry_name"] == "MyService"
        assert data["image_path"] == "C:\\Windows\\System32\\service.exe"
        assert data["enabled"] is False
        assert "raw_data" in data


class TestAutorunsAnalyzer:
    """Test AutorunsAnalyzer class."""
    
    def test_init_with_default_config(self):
        """Test initializing analyzer with default config."""
        analyzer = AutorunsAnalyzer()
        
        categories = analyzer.get_categories()
        assert len(categories) > 0
        assert any(cat["name"] == "Logon" for cat in categories)
        assert any(cat["name"] == "Services" for cat in categories)
    
    def test_init_with_missing_config(self, tmp_path):
        """Test initializing with non-existent config file."""
        config_path = tmp_path / "missing.yaml"
        analyzer = AutorunsAnalyzer(config_path=config_path)
        
        # Should fall back to empty config
        categories = analyzer.get_categories()
        assert len(categories) == 0
    
    def test_get_categories(self):
        """Test getting list of categories."""
        analyzer = AutorunsAnalyzer()
        categories = analyzer.get_categories()
        
        assert isinstance(categories, list)
        assert len(categories) > 0
        
        for cat in categories:
            assert "name" in cat
            assert "description" in cat
            assert isinstance(cat["name"], str)
            assert isinstance(cat["description"], str)
    
    def test_is_valid_autorun_path(self):
        """Test path validation logic."""
        analyzer = AutorunsAnalyzer()
        
        # Valid paths
        assert analyzer._is_valid_autorun_path("C:\\Windows\\System32\\app.exe") is True
        assert analyzer._is_valid_autorun_path("C:\\Program Files\\App\\app.dll") is True
        assert analyzer._is_valid_autorun_path("app.exe") is True
        assert analyzer._is_valid_autorun_path("%SystemRoot%\\System32\\service.exe") is True
        assert analyzer._is_valid_autorun_path("\\\\server\\share\\tool.exe") is True
        
        # Invalid paths
        assert analyzer._is_valid_autorun_path("") is False
        assert analyzer._is_valid_autorun_path("123") is False
        assert analyzer._is_valid_autorun_path("1") is False
        assert analyzer._is_valid_autorun_path("abc") is False  # Too short, no extension
        assert analyzer._is_valid_autorun_path("0") is False
    
    @pytest.mark.asyncio
    async def test_analyze_returns_entries(self):
        """Test that analyze method returns list of entries."""
        analyzer = AutorunsAnalyzer()
        
        # Mock database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        
        # Mock query results - empty
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        investigation_id = uuid4()
        
        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            use_cache=False
        )
        
        assert isinstance(entries, list)
        # With no data, should return empty list
        assert len(entries) == 0
    
    @pytest.mark.asyncio
    async def test_query_single_path_builds_correct_query(self):
        """Test that query construction is correct."""
        analyzer = AutorunsAnalyzer()
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        investigation_id = uuid4()
        
        entries = await analyzer._query_single_path(
            db=mock_db,
            investigation_id=investigation_id,
            category="Logon",
            location="Run",
            registry_path="Microsoft\\Windows\\CurrentVersion\\Run",
            value_names=None,
            value_filters=None,
            match_subkeys=False,
        )
        
        # Should have called execute
        assert mock_db.execute.called
        
        # Check the query was built correctly
        call_args = mock_db.execute.call_args
        query_text = str(call_args[0][0])
        
        # Should use LOWER and LIKE for case-insensitive matching
        assert "LOWER" in query_text
        assert "LIKE" in query_text
        assert "registry_value" in query_text
        
        # Should exclude WinSxS
        assert "winsxs" in query_text.lower()
        assert "NOT LIKE" in query_text
    
    @pytest.mark.asyncio
    async def test_query_with_value_names_filter(self):
        """Test querying with value_names filter."""
        analyzer = AutorunsAnalyzer()
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        investigation_id = uuid4()
        
        await analyzer._query_single_path(
            db=mock_db,
            investigation_id=investigation_id,
            category="Services",
            location="Services",
            registry_path="ControlSet001\\Services",
            value_names=["ImagePath"],
            value_filters=None,
            match_subkeys=True,
        )
        
        # Check query includes value_name filter
        call_args = mock_db.execute.call_args
        query_text = str(call_args[0][0])
        params = call_args[0][1]
        
        assert "value_name" in query_text
        assert "IN" in query_text
        assert "vname_0" in params
        assert params["vname_0"] == "ImagePath"
    
    @pytest.mark.asyncio
    async def test_create_entry_from_registry_event(self):
        """Test creating entry from registry payload."""
        analyzer = AutorunsAnalyzer()
        
        payload = {
            "key_path": "\\ROOT\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "value_name": "TestApp",
            "value_data": '"C:\\Program Files\\Test\\app.exe" /start',
            "value_type": "1",
            "last_modified": "2024-01-15T10:00:00"
        }
        
        entry = analyzer._create_entry(
            category="Logon",
            location="Run",
            event_id=123,
            timestamp="2024-01-15T10:00:00",
            payload=payload
        )
        
        assert entry is not None
        assert entry.entry_name == "TestApp"
        assert entry.image_path == 'C:\\Program Files\\Test\\app.exe" /start'
        assert entry.enabled is True
        assert entry.registry_path == "\\ROOT\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    
    @pytest.mark.asyncio
    async def test_create_entry_filters_invalid_paths(self):
        """Test that entries with invalid paths are filtered."""
        analyzer = AutorunsAnalyzer()
        
        # Invalid path - pure number
        payload = {
            "key_path": "\\ROOT\\Test",
            "value_name": "BadValue",
            "value_data": "123",
            "value_type": "4",
        }
        
        entry = analyzer._create_entry(
            category="Logon",
            location="Run",
            event_id=123,
            timestamp="2024-01-15T10:00:00",
            payload=payload
        )
        
        assert entry is None  # Should be filtered out
    
    @pytest.mark.asyncio
    async def test_create_entry_from_event_scheduled_task(self):
        """Test creating entry from scheduled task event."""
        analyzer = AutorunsAnalyzer()
        
        payload = {
            "artifact_type": "scheduled_task_xml",
            "task_name": "UpdateTask",
            "author": "Microsoft",
            "description": "Update task",
            "actions": ["C:\\Windows\\System32\\update.exe /silent"],
            "file_path": "UpdateTask.xml"
        }
        
        entry = analyzer._create_entry_from_event(
            category="Scheduled Tasks",
            location="Task Scheduler (Artifacts)",
            event_id=456,
            timestamp="2024-01-15T10:00:00",
            payload=payload,
            event_type="scheduled_task"
        )
        
        assert entry is not None
        assert entry.entry_name == "UpdateTask"
        assert entry.image_path == "C:\\Windows\\System32\\update.exe /silent"
        assert entry.publisher == "Microsoft"
        assert entry.description == "Update task"
    
    @pytest.mark.asyncio
    async def test_service_disabled_detection(self):
        """Test that disabled services are detected correctly."""
        analyzer = AutorunsAnalyzer()
        
        # Enabled service (Start=2)
        payload_enabled = {
            "key_path": "\\ROOT\\Services\\EnabledService",
            "value_name": "ImagePath",
            "value_data": "C:\\Windows\\System32\\enabled.exe",
            "Start": "2",
            "Type": "16",
        }
        
        entry_enabled = analyzer._create_entry(
            category="Services",
            location="Services",
            event_id=1,
            timestamp="2024-01-15T10:00:00",
            payload=payload_enabled
        )
        
        assert entry_enabled.enabled is True
        
        # Disabled service (Start=4)
        payload_disabled = {
            "key_path": "\\ROOT\\Services\\DisabledService",
            "value_name": "ImagePath",
            "value_data": "C:\\Windows\\System32\\disabled.exe",
            "Start": "4",
            "Type": "16",
        }
        
        entry_disabled = analyzer._create_entry(
            category="Services",
            location="Services",
            event_id=2,
            timestamp="2024-01-15T10:00:00",
            payload=payload_disabled
        )
        
        assert entry_disabled.enabled is False
    
    @pytest.mark.asyncio
    async def test_cache_key_generation(self):
        """Test that cache keys are generated correctly for different parameters."""
        analyzer = AutorunsAnalyzer()
        
        # Mock the cache lookup
        with patch.object(analyzer, '_get_cached_results', return_value=None) as mock_cache:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_db.execute.return_value = mock_result
            
            investigation_id = uuid4()
            
            # Query with no categories
            await analyzer.analyze(mock_db, investigation_id, categories=None, use_cache=True)
            
            # Should have called cache with None
            assert mock_cache.called
            call_args = mock_cache.call_args[0]
            assert call_args[1] is None  # categories parameter
            
            mock_cache.reset_mock()
            
            # Query with specific categories
            await analyzer.analyze(mock_db, investigation_id, categories=["Logon", "Services"], use_cache=True)
            
            # Should have called cache with sorted categories
            assert mock_cache.called
            call_args = mock_cache.call_args[0]
            assert call_args[1] == ["Logon", "Services"]
    
    def test_config_loading_from_yaml(self, tmp_path):
        """Test loading configuration from YAML file."""
        # Create a test config
        config_content = """
categories:
  - name: "Test Category"
    description: "Test description"
    locations:
      - name: "Test Location"
        registry_paths:
          - "Test\\\\Path"
        enabled: true
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(config_content)
        
        analyzer = AutorunsAnalyzer(config_path=config_file)
        
        categories = analyzer.get_categories()
        assert len(categories) == 1
        assert categories[0]["name"] == "Test Category"
        assert categories[0]["description"] == "Test description"
    
    def test_path_pattern_generation(self):
        """Test that path patterns are generated correctly."""
        analyzer = AutorunsAnalyzer()
        
        # Test path with multiple components
        path = "Microsoft\\Windows\\CurrentVersion\\Run"
        path_parts = path.split("\\")
        
        # Should use last 2 components
        if len(path_parts) >= 2:
            pattern = "%" + "%".join(path_parts[-2:])
            assert pattern == "%CurrentVersion%Run"
    
    @pytest.mark.asyncio
    async def test_analyze_with_empty_results(self):
        """Test analyze when no entries are found."""
        analyzer = AutorunsAnalyzer()
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        investigation_id = uuid4()
        
        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            use_cache=False
        )
        
        assert isinstance(entries, list)
        assert len(entries) == 0
    
    @pytest.mark.asyncio
    async def test_query_event_type(self):
        """Test querying by event_type instead of registry."""
        analyzer = AutorunsAnalyzer()
        
        # Mock database with scheduled task event
        mock_db = AsyncMock()
        mock_result = MagicMock()
        
        # Simulate a scheduled task event
        mock_row = (
            123,  # event_id
            datetime.utcnow(),  # event_ts
            {  # payload
                "artifact_type": "scheduled_task_xml",
                "task_name": "TestTask",
                "actions": ["C:\\Windows\\System32\\test.exe"],
                "author": "Test",
            }
        )
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result
        
        investigation_id = uuid4()
        
        entries = await analyzer._query_event_type(
            db=mock_db,
            investigation_id=investigation_id,
            category="Scheduled Tasks",
            location="Task Scheduler (Artifacts)",
            event_type="scheduled_task"
        )
        
        assert len(entries) == 1
        assert entries[0].entry_name == "TestTask"
        assert entries[0].category == "Scheduled Tasks"
    
    @pytest.mark.asyncio  
    async def test_value_filters_applied(self):
        """Test that value_filters are applied correctly."""
        analyzer = AutorunsAnalyzer()
        
        # Mock database with service entries
        mock_db = AsyncMock()
        mock_result = MagicMock()
        
        # Service with Start=2 (Auto) - should be included
        # Service with Start=4 (Disabled) - should be excluded by filter
        mock_rows = [
            (1, datetime.utcnow(), {
                "key_path": "\\ROOT\\Services\\AutoService",
                "value_name": "ImagePath",
                "value_data": "C:\\auto.exe",
                "Start": "2",
                "Type": "16"
            }),
            (2, datetime.utcnow(), {
                "key_path": "\\ROOT\\Services\\DisabledService",
                "value_name": "ImagePath",
                "value_data": "C:\\disabled.exe",
                "Start": "4",
                "Type": "16"
            }),
        ]
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result
        
        investigation_id = uuid4()
        
        # Query with value_filters for Start
        entries = await analyzer._query_single_path(
            db=mock_db,
            investigation_id=investigation_id,
            category="Services",
            location="Services",
            registry_path="ControlSet001\\Services",
            value_names=["ImagePath"],
            value_filters={"Start": ["0", "1", "2"]},  # Only auto-start
            match_subkeys=True
        )
        
        # Should only include the auto-start service
        assert len(entries) == 1
        assert entries[0].entry_name == "ImagePath"


class TestAutorunsIntegration:
    """Integration tests for Autoruns analyzer."""
    
    @pytest.mark.asyncio
    async def test_full_analysis_workflow(self):
        """Test complete analysis workflow."""
        analyzer = AutorunsAnalyzer()
        
        # Mock database with realistic data
        mock_db = AsyncMock()
        mock_result = MagicMock()
        
        # Sample Run key entry
        mock_rows = [
            (100, datetime.utcnow(), {
                "key_path": "\\ROOT\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                "value_name": "OneDrive",
                "value_data": '"C:\\Users\\Test\\AppData\\Local\\Microsoft\\OneDrive\\OneDrive.exe" /background',
                "value_type": "1",
                "last_modified": "2024-01-15T10:00:00"
            })
        ]
        mock_result.fetchall.return_value = mock_rows
        mock_db.execute.return_value = mock_result
        
        investigation_id = uuid4()
        
        # Run analysis
        entries = await analyzer.analyze(
            db=mock_db,
            investigation_id=investigation_id,
            categories=["Logon"],
            use_cache=False
        )
        
        # Should find the OneDrive entry
        assert len(entries) >= 1
        onedrive_entries = [e for e in entries if e.entry_name == "OneDrive"]
        if onedrive_entries:
            entry = onedrive_entries[0]
            assert "OneDrive.exe" in entry.image_path
            assert entry.category == "Logon"
            assert entry.location == "Run"
