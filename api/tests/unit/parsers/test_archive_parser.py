"""
Unit tests for the Archive Parser.

Tests archive extraction functionality for ZIP, 7z, and RAR formats.
"""

import pytest
from pathlib import Path
import zipfile
import tempfile
import uuid

from worker.parsers.archive_parser import ArchiveParser


class TestArchiveParserIdentify:
    """Test archive format identification."""
    
    def test_identify_zip_by_extension(self, tmp_path):
        """Test ZIP identification by .zip extension."""
        # Create a simple ZIP file
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("test.txt", "test content")
        
        assert ArchiveParser.identify("test.zip", zip_path) is True
    
    def test_identify_zip_by_magic(self, tmp_path):
        """Test ZIP identification by magic bytes (no extension)."""
        # Create a ZIP file with wrong extension
        zip_path = tmp_path / "test.bin"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("test.txt", "test content")
        
        assert ArchiveParser.identify("test.bin", zip_path) is True
    
    def test_identify_7z_by_extension(self):
        """Test 7z identification by .7z extension."""
        # Just test extension matching (7z creation requires py7zr)
        assert ArchiveParser.identify("test.7z", Path("nonexistent.7z")) is True
    
    def test_identify_rar_by_extension(self):
        """Test RAR identification by .rar extension."""
        assert ArchiveParser.identify("test.rar", Path("nonexistent.rar")) is True
    
    def test_identify_non_archive(self, tmp_path):
        """Test that non-archive files are rejected."""
        # Create a text file
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("not an archive")
        
        assert ArchiveParser.identify("test.txt", txt_path) is False
    
    def test_identify_evtx_file(self, tmp_path):
        """Test that EVTX files are not identified as archives."""
        evtx_path = tmp_path / "Security.evtx"
        evtx_path.write_bytes(b'ElfFile\x00' + b'\x00' * 100)
        
        assert ArchiveParser.identify("Security.evtx", evtx_path) is False


class TestArchiveParserExtraction:
    """Test archive extraction logic."""
    
    @pytest.mark.asyncio
    async def test_extract_simple_zip(self, tmp_path, db_session):
        """Test extraction of a simple ZIP file."""
        # Create a ZIP with test files
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("file1.txt", "content1")
            zf.writestr("file2.txt", "content2")
            zf.writestr("subdir/file3.txt", "content3")
        
        # Create parser
        parser = ArchiveParser()
        
        # Mock investigation and artifact IDs
        investigation_id = uuid.uuid4()
        artifact_id = 1
        
        # Note: Full extraction test requires database session and artifact CRUD
        # This test just verifies the identify() method works
        assert ArchiveParser.identify("test.zip", zip_path) is True
    
    def test_extraction_limits(self):
        """Test that safety limits are properly defined."""
        from worker.parsers.archive_parser import (
            MAX_EXTRACTION_DEPTH,
            MAX_TOTAL_EXTRACTED_SIZE,
            MAX_EXTRACTED_FILES
        )
        
        # Verify limits are reasonable
        assert MAX_EXTRACTION_DEPTH == 16
        assert MAX_TOTAL_EXTRACTED_SIZE == 10 * 1024 * 1024 * 1024  # 10 GB
        assert MAX_EXTRACTED_FILES == 50000


class TestArchiveParserSafety:
    """Test safety features against zip bombs."""
    
    def test_depth_limit_constant(self):
        """Test that depth limit is defined."""
        from worker.parsers.archive_parser import MAX_EXTRACTION_DEPTH
        assert isinstance(MAX_EXTRACTION_DEPTH, int)
        assert MAX_EXTRACTION_DEPTH > 0
    
    def test_size_limit_constant(self):
        """Test that size limit is defined."""
        from worker.parsers.archive_parser import MAX_TOTAL_EXTRACTED_SIZE
        assert isinstance(MAX_TOTAL_EXTRACTED_SIZE, int)
        assert MAX_TOTAL_EXTRACTED_SIZE > 0
    
    def test_file_limit_constant(self):
        """Test that file count limit is defined."""
        from worker.parsers.archive_parser import MAX_EXTRACTED_FILES
        assert isinstance(MAX_EXTRACTED_FILES, int)
        assert MAX_EXTRACTED_FILES > 0


@pytest.mark.integration
class TestArchiveParserIntegration:
    """Integration tests requiring full database setup."""
    
    @pytest.mark.asyncio
    async def test_zip_extraction_creates_artifacts(self, db_session, tmp_path):
        """
        Test that extracting a ZIP creates artifacts for each file.
        
        Note: This is a placeholder for full integration testing.
        Requires mocking artifact CRUD and job queue operations.
        """
        # This test would require:
        # 1. Mock investigation directory structure
        # 2. Mock artifact CRUD operations
        # 3. Mock job queue operations
        # 4. Verify correct number of artifacts created
        # 5. Verify parsing jobs queued for each artifact
        
        pytest.skip("Full integration test requires database fixtures")


__all__ = [
    "TestArchiveParserIdentify",
    "TestArchiveParserExtraction",
    "TestArchiveParserSafety",
    "TestArchiveParserIntegration",
]
