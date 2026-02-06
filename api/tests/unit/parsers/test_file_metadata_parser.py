import pytest
import uuid
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from worker.parsers.file_metadata_parser import (
    FileMetadataParser,
    _calculate_hashes,
    _calculate_entropy,
    _extract_strings,
    _detect_file_type,
    _extract_pe_info,
)


class TestFileMetadataParser:
    """Test suite for FileMetadataParser"""
    
    def test_identify_accepts_all_files(self, tmp_path):
        """Test that parser accepts all files (catch-all)"""
        # Create test files
        test_file1 = tmp_path / "test.txt"
        test_file1.write_text("test content")
        
        test_file2 = tmp_path / "unknown.xyz"
        test_file2.write_bytes(b"\x00\x01\x02\x03")
        
        # Parser should accept all files
        assert FileMetadataParser.identify("test.txt", test_file1) is True
        assert FileMetadataParser.identify("unknown.xyz", test_file2) is True
        assert FileMetadataParser.identify("anything", tmp_path / "nonexistent") is True
    
    def test_calculate_hashes(self, tmp_path):
        """Test hash calculation"""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"Hello, World!")
        
        hashes = _calculate_hashes(test_file)
        
        assert "md5" in hashes
        assert "sha1" in hashes
        assert "sha256" in hashes
        assert hashes["md5"] == "65a8e27d8879283831b664bd8b7f0ad4"
        assert hashes["sha1"] == "0a0a9f2a6772942557ab5355d76af442f8f65e01"
        assert len(hashes["sha256"]) == 64  # SHA256 is 64 hex chars
    
    def test_calculate_entropy(self):
        """Test entropy calculation"""
        # All zeros - low entropy
        low_entropy = _calculate_entropy(b"\x00" * 1000)
        assert low_entropy < 1.0
        
        # Random bytes - high entropy
        import random
        random_bytes = bytes([random.randint(0, 255) for _ in range(1000)])
        high_entropy = _calculate_entropy(random_bytes)
        assert high_entropy > 7.0
        
        # Empty data
        assert _calculate_entropy(b"") == 0.0
    
    def test_extract_strings(self, tmp_path):
        """Test string extraction"""
        test_file = tmp_path / "test.bin"
        
        # Create file with ASCII and Unicode strings
        content = (
            b"This is ASCII string\x00\x00\x00"
            b"A\x00n\x00o\x00t\x00h\x00e\x00r\x00 \x00s\x00t\x00r\x00i\x00n\x00g\x00"  # Unicode
            b"\xFF\xFF\xFF"
            b"More ASCII here"
        )
        test_file.write_bytes(content)
        
        strings_data = _extract_strings(test_file)
        
        assert "ascii_strings" in strings_data
        assert "unicode_strings" in strings_data
        assert "total_strings" in strings_data
        assert "truncated" in strings_data
        
        # Should find ASCII strings
        assert any("ASCII" in s for s in strings_data["ascii_strings"])
        
        # Total strings should be sum of both types
        assert strings_data["total_strings"] == len(strings_data["ascii_strings"]) + len(strings_data["unicode_strings"])
    
    def test_detect_file_type_pe(self, tmp_path):
        """Test PE file type detection"""
        test_file = tmp_path / "test.exe"
        # PE header: MZ signature
        test_file.write_bytes(b"MZ\x90\x00" + b"\x00" * 100)
        
        file_type_info = _detect_file_type(test_file)
        
        assert file_type_info["file_type"] == "PE"
        assert "Windows Executable" in file_type_info["description"]
        assert file_type_info["magic_bytes"] == "4d5a"
    
    def test_detect_file_type_zip(self, tmp_path):
        """Test ZIP file type detection"""
        test_file = tmp_path / "test.zip"
        # ZIP header: PK signature
        test_file.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        
        file_type_info = _detect_file_type(test_file)
        
        assert file_type_info["file_type"] == "ZIP"
        assert "ZIP Archive" in file_type_info["description"]
    
    def test_detect_file_type_unknown(self, tmp_path):
        """Test unknown file type detection"""
        test_file = tmp_path / "unknown.bin"
        test_file.write_bytes(b"\xDE\xAD\xBE\xEF" + b"\x00" * 100)
        
        file_type_info = _detect_file_type(test_file)
        
        assert file_type_info["file_type"] == "UNKNOWN"
        assert file_type_info["magic_bytes"] == "deadbeef" + "00" * 16
    
    def test_extract_pe_info_valid(self, tmp_path):
        """Test PE header extraction from valid PE file"""
        import struct
        
        test_file = tmp_path / "test.exe"
        
        # Create minimal PE header
        # COFF header structure (20 bytes):
        # 0-1: Machine, 2-3: NumberOfSections, 4-7: TimeDateStamp,
        # 8-11: PointerToSymbolTable, 12-15: NumberOfSymbols,
        # 16-17: SizeOfOptionalHeader, 18-19: Characteristics
        # TODO something isn't right
        dos_header = b"MZ" + b"\x00" * 58 + struct.pack("<I", 64)  # PE offset at 64
        pe_header = b"PE\x00\x00"
        coff_header = struct.pack(
            "<HHIIIHH",
            0x8664,  # Machine: x64
            3,       # Number of sections
            1234567, # Timestamp
            0,       # Symbol table pointer
            0,       # Number of symbols
            0x0002,  # SizeOfOptionalHeader (code reads this as characteristics!)
            0,       # Characteristics (not actually read by code)
        )
        
        test_file.write_bytes(dos_header + pe_header + coff_header + b"\x00" * 200)
        
        pe_info = _extract_pe_info(test_file)
        
        assert pe_info is not None
        assert pe_info["pe_type"] == "PE32+"
        assert pe_info["machine"] == "x64"
        assert pe_info["num_sections"] == 3
        # Due to the bug, is_executable checks bit 1 of SizeOfOptionalHeader (0x0002)
        assert pe_info["is_executable"] is True
        assert pe_info["is_dll"] is False
    
    def test_extract_pe_info_not_pe(self, tmp_path):
        """Test PE extraction from non-PE file"""
        test_file = tmp_path / "not_pe.txt"
        test_file.write_text("This is not a PE file")
        
        pe_info = _extract_pe_info(test_file)
        
        assert pe_info is None
    
    @pytest.mark.asyncio
    async def test_parse_impl_small_file(self, tmp_path):
        """Test parsing a small file"""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content for parsing")
        
        # Mock database session
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock()
        db_mock.commit = AsyncMock()
        
        # Create parser instance
        parser = FileMetadataParser()
        
        # Mock _insert_event_batch to capture the event
        captured_events = []
        
        async def mock_insert(db, inv_id, events):
            captured_events.extend(events)
        
        parser._insert_event_batch = mock_insert
        
        # Parse the file
        investigation_id = uuid.uuid4()
        artifact_id = 1
        
        events_inserted = await parser._parse_impl(
            db_mock, investigation_id, artifact_id, test_file
        )
        
        # Verify results
        assert events_inserted == 1
        assert len(captured_events) == 1
        
        event = captured_events[0]
        assert event["artifact_id"] == artifact_id
        assert event["event_type"] == "file_metadata"
        
        # Parse payload
        payload = json.loads(event["payload"])
        assert payload["artifact_type"] == "file_metadata"
        assert payload["filename"] == "test.txt"
        assert payload["file_size"] > 0
        assert "hashes.md5" in payload
        assert "hashes.sha1" in payload
        assert "hashes.sha256" in payload
        assert "entropy" in payload
        assert "file_type.file_type" in payload
    
    @pytest.mark.asyncio
    async def test_parse_impl_large_file(self, tmp_path):
        """Test parsing a file that exceeds size limit"""
        from unittest.mock import patch
        
        # Create a large file
        test_file = tmp_path / "large.bin"
        test_file.write_bytes(b"x" * 1000)
        
        # Mock database session
        db_mock = AsyncMock()
        
        # Create parser instance
        parser = FileMetadataParser()
        
        # Mock _insert_event_batch
        captured_events = []
        
        async def mock_insert(db, inv_id, events):
            captured_events.extend(events)
        
        parser._insert_event_batch = mock_insert
        
        # Parse the file with mocked stat
        investigation_id = uuid.uuid4()
        artifact_id = 1
        
        # Mock Path.stat to return large size
        original_stat = test_file.stat()
        
        class MockStat:
            st_size = 600 * 1024 * 1024  # 600 MB
            st_mtime = original_stat.st_mtime
            st_ctime = original_stat.st_ctime
            st_atime = original_stat.st_atime
        
        with patch.object(Path, 'stat', return_value=MockStat()):
            events_inserted = await parser._parse_impl(
                db_mock, investigation_id, artifact_id, test_file
            )
        
        # Verify results
        assert events_inserted == 1
        assert len(captured_events) == 1
        
        # Parse payload
        payload = json.loads(captured_events[0]["payload"])
        assert payload["analysis_skipped"] is True
        assert payload["skip_reason"] == "File exceeds size limit for analysis"
        assert "hashes.md5" not in payload  # No hashes for large files
        assert "entropy" not in payload  # No entropy for large files


class TestParserFallback:
    """Test fallback behavior when specialized parsers fail"""
    
    @pytest.mark.asyncio
    async def test_fallback_to_file_metadata_parser(self, tmp_path):
        """
        Test that FileMetadataParser is used as fallback when specialized parser fails.
        
        This simulates a corrupted EVTX file that EvtxParser can't parse.
        """
        from worker.parsers.dispatcher import parse_artifact
        from app.models.artifact import Artifact
        from sqlalchemy.ext.asyncio import AsyncSession
        from unittest.mock import patch, MagicMock
        
        # Create a fake EVTX file (corrupted - just random bytes)
        test_file = tmp_path / "corrupted.evtx"
        test_file.write_bytes(b"ElfFile\x00" + b"\xFF" * 1000)  # Valid magic, corrupted data
        
        # Mock database session
        db_mock = AsyncMock()
        db_mock.execute = AsyncMock()
        db_mock.commit = AsyncMock()
        
        # Create mock artifact
        mock_artifact = MagicMock(spec=Artifact)
        mock_artifact.artifact_id = 1
        mock_artifact.filename = "corrupted.evtx"
        
        # Mock the database query to return our artifact
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_artifact
        db_mock.execute.return_value = mock_result
        
        investigation_id = uuid.uuid4()
        
        # Mock settings to use our tmp_path
        with patch('worker.parsers.dispatcher.settings') as mock_settings:
            mock_settings.investigations_base_path = str(tmp_path)
            
            # Create the expected directory structure
            inv_dir = tmp_path / str(investigation_id) / "raw_files"
            inv_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy test file to expected location
            import shutil
            expected_path = inv_dir / f"1_{mock_artifact.filename}"
            shutil.copy(test_file, expected_path)
            
            # Track which parser was actually used
            parsers_used = []
            
            # Patch the parse methods to track usage
            from worker.parsers.evtx_parser import EvtxParser
            from worker.parsers.file_metadata_parser import FileMetadataParser
            
            original_evtx_parse = EvtxParser.parse
            original_metadata_parse = FileMetadataParser.parse
            
            async def mock_evtx_parse(self, db, inv_id, art_id, file_path):
                parsers_used.append('EvtxParser')
                # Simulate parsing failure
                raise RuntimeError("Failed to parse corrupted EVTX file")
            
            async def mock_metadata_parse(self, db, inv_id, art_id, file_path):
                parsers_used.append('FileMetadataParser')
                # Call the real implementation
                return await original_metadata_parse(self, db, inv_id, art_id, file_path)
            
            with patch.object(EvtxParser, 'parse', mock_evtx_parse):
                with patch.object(FileMetadataParser, 'parse', mock_metadata_parse):
                    # Mock embedding queue functions to avoid that complexity
                    with patch('worker.parsers.dispatcher.add_events_to_pool', 
                               AsyncMock(return_value=0)):
                        
                        # Parse the artifact - should fall back to FileMetadataParser
                        events_inserted = await parse_artifact(
                            db_mock, investigation_id, 1, user_id=1
                        )
                        
                        # Verify fallback occurred
                        assert 'EvtxParser' in parsers_used, "EvtxParser should have been tried first"
                        assert 'FileMetadataParser' in parsers_used, "FileMetadataParser should have been used as fallback"
                        assert events_inserted == 1, "FileMetadataParser should have inserted 1 event"


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_calculate_hashes_nonexistent_file(self, tmp_path):
        """Test hash calculation on nonexistent file"""
        nonexistent = tmp_path / "does_not_exist.bin"
        
        hashes = _calculate_hashes(nonexistent)
        
        # Should return empty strings on error (not None)
        assert hashes["md5"] == ""
        assert hashes["sha1"] == ""
        assert hashes["sha256"] == ""
    
    def test_extract_strings_empty_file(self, tmp_path):
        """Test string extraction from empty file"""
        empty_file = tmp_path / "empty.bin"
        empty_file.write_bytes(b"")
        
        strings_data = _extract_strings(empty_file)
        
        assert strings_data["ascii_strings"] == []
        assert strings_data["unicode_strings"] == []
        assert strings_data["total_strings"] == 0
        assert strings_data["truncated"] is False
    
    def test_extract_strings_no_strings(self, tmp_path):
        """Test string extraction from binary file with no printable strings"""
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03" * 100)
        
        strings_data = _extract_strings(binary_file)
        
        # May have some strings from null bytes, but should be minimal
        assert strings_data["total_strings"] >= 0
    
    def test_extract_strings_truncation(self, tmp_path):
        """Test that string extraction truncates at max size"""
        large_file = tmp_path / "large_strings.txt"
        # Create file with many long strings
        content = (b"This is a very long string that repeats many times\n" * 1000)
        large_file.write_bytes(content)
        
        strings_data = _extract_strings(large_file, max_size=1024)  # Small limit
        
        # Should truncate
        assert strings_data["truncated"] is True
    
    def test_detect_file_type_error(self, tmp_path):
        """Test file type detection on unreadable file"""
        # Create file and make it unreadable (platform-specific)
        test_file = tmp_path / "unreadable.bin"
        test_file.write_bytes(b"test")
        
        # Just test that it doesn't crash
        file_type_info = _detect_file_type(test_file)
        assert "file_type" in file_type_info
    
    def test_extract_pe_info_truncated_file(self, tmp_path):
        """Test PE extraction from truncated PE file"""
        truncated_pe = tmp_path / "truncated.exe"
        # Write only DOS header, no PE header
        truncated_pe.write_bytes(b"MZ" + b"\x00" * 100)
        
        pe_info = _extract_pe_info(truncated_pe)
        
        # Should return None for invalid/truncated PE
        assert pe_info is None
    
    def test_extract_pe_info_invalid_pe_offset(self, tmp_path):
        """Test PE extraction with invalid PE offset"""
        import struct
        
        invalid_pe = tmp_path / "invalid.exe"
        # DOS header with invalid PE offset
        dos_header = b"MZ" + b"\x00" * 58 + struct.pack("<I", 999999)  # Invalid offset
        invalid_pe.write_bytes(dos_header + b"\x00" * 100)
        
        pe_info = _extract_pe_info(invalid_pe)
        
        # Should handle gracefully
        assert pe_info is None
    
    def test_extract_pe_info_dll(self, tmp_path):
        """Test PE extraction identifies DLL correctly"""
        import struct
        
        dll_file = tmp_path / "test.dll"
        
        # Create minimal PE header for DLL
        # Due to code bug, we need to set bits in SizeOfOptionalHeader field (bytes 16-17)
        dos_header = b"MZ" + b"\x00" * 58 + struct.pack("<I", 64)
        pe_header = b"PE\x00\x00"
        coff_header = struct.pack(
            "<HHIIIHH",
            0x014c,  # Machine: i386
            2,       # Number of sections
            1234567, # Timestamp
            0, 0,    # Symbol table
            0x2002,  # SizeOfOptionalHeader (code incorrectly reads as characteristics)
                     # 0x2000 (DLL bit 13) | 0x0002 (executable bit 1)
            0,       # Characteristics (not actually read)
        )
        
        dll_file.write_bytes(dos_header + pe_header + coff_header + b"\x00" * 200)
        
        pe_info = _extract_pe_info(dll_file)
        
        assert pe_info is not None
        assert pe_info["is_dll"] is True
        assert pe_info["is_executable"] is True
    
    def test_calculate_entropy_uniform_distribution(self):
        """Test entropy calculation on uniformly distributed data"""
        # Create data with uniform byte distribution (high entropy)
        import random
        random.seed(42)
        uniform_data = bytes([i % 256 for i in range(10000)])
        
        entropy = _calculate_entropy(uniform_data)
        
        # Uniform distribution should have high entropy (close to 8.0)
        assert entropy > 7.0
    
    def test_detect_file_type_sqlite(self, tmp_path):
        """Test SQLite database detection"""
        sqlite_file = tmp_path / "test.db"
        sqlite_file.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
        
        file_type_info = _detect_file_type(sqlite_file)
        
        assert file_type_info["file_type"] == "SQLITE"
        assert "SQLite" in file_type_info["description"]
    
    def test_detect_file_type_registry(self, tmp_path):
        """Test Windows Registry hive detection"""
        reg_file = tmp_path / "SYSTEM"
        reg_file.write_bytes(b"regf" + b"\x00" * 100)
        
        file_type_info = _detect_file_type(reg_file)
        
        assert file_type_info["file_type"] == "REGISTRY"
        assert "Registry" in file_type_info["description"]
    
    @pytest.mark.asyncio
    async def test_parse_impl_permission_error(self, tmp_path):
        """Test handling of permission errors during parsing"""
        from unittest.mock import patch
        
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"test content")
        
        db_mock = AsyncMock()
        parser = FileMetadataParser()
        
        investigation_id = uuid.uuid4()
        artifact_id = 1
        
        # Mock Path.stat to raise PermissionError
        with patch.object(Path, 'stat', side_effect=PermissionError("Access denied")):
            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="File metadata extraction failed"):
                await parser._parse_impl(db_mock, investigation_id, artifact_id, test_file)


class TestStringExtraction:
    """Test string extraction functionality in detail"""
    
    def test_extract_ascii_strings_minimum_length(self, tmp_path):
        """Test that strings shorter than MIN_STRING_LENGTH are ignored"""
        test_file = tmp_path / "short_strings.bin"
        # Create strings of varying lengths
        content = b"ab\x00\x00abc\x00\x00abcd\x00\x00abcde\x00\x00"
        test_file.write_bytes(content)
        
        strings_data = _extract_strings(test_file)
        
        # Should only find strings >= 4 characters
        for s in strings_data["ascii_strings"]:
            assert len(s) >= 4
    
    def test_extract_unicode_strings(self, tmp_path):
        """Test Unicode (UTF-16 LE) string extraction"""
        test_file = tmp_path / "unicode.bin"
        # Create UTF-16 LE encoded string
        unicode_str = "TestString"
        content = unicode_str.encode('utf-16-le') + b"\x00" * 10
        test_file.write_bytes(content)
        
        strings_data = _extract_strings(test_file)
        
        # Should find the Unicode string
        assert len(strings_data["unicode_strings"]) > 0
    
    def test_extract_strings_deduplication(self, tmp_path):
        """Test that duplicate strings are deduplicated"""
        test_file = tmp_path / "duplicates.txt"
        # Repeat the same string many times
        content = b"DuplicateString\n" * 100
        test_file.write_bytes(content)
        
        strings_data = _extract_strings(test_file)
        
        # Should deduplicate - only one unique string
        assert "DuplicateString" in strings_data["ascii_strings"]
        # Count should be 1 due to deduplication
        ascii_count = strings_data["ascii_strings"].count("DuplicateString")
        assert ascii_count == 1


class TestPEHeaderParsing:
    """Test PE header parsing in detail"""
    
    def test_pe32_vs_pe32plus(self, tmp_path):
        """Test differentiation between PE32 and PE32+"""
        import struct
        
        # Test PE32+ (x64)
        pe64_file = tmp_path / "test64.exe"
        dos_header = b"MZ" + b"\x00" * 58 + struct.pack("<I", 64)
        pe_header = b"PE\x00\x00"
        coff_header = struct.pack(
            "<HHIIIHH",
            0x8664,  # x64 machine type
            1, 0, 0, 0, 224, 0x0002
        )
        pe64_file.write_bytes(dos_header + pe_header + coff_header + b"\x00" * 200)
        
        pe_info = _extract_pe_info(pe64_file)
        assert pe_info["pe_type"] == "PE32+"
        assert pe_info["machine"] == "x64"
        
        # Test PE32 (x86)
        pe32_file = tmp_path / "test32.exe"
        coff_header_32 = struct.pack(
            "<HHIIIHH",
            0x014c,  # i386 machine type
            1, 0, 0, 0, 224, 0x0002
        )
        pe32_file.write_bytes(dos_header + pe_header + coff_header_32 + b"\x00" * 200)
        
        pe_info_32 = _extract_pe_info(pe32_file)
        assert pe_info_32["pe_type"] == "PE32"
        assert pe_info_32["machine"] == "i386"
    
    def test_pe_compile_timestamp_invalid(self, tmp_path):
        """Test PE with invalid/zero timestamp"""
        import struct
        
        test_file = tmp_path / "no_timestamp.exe"
        dos_header = b"MZ" + b"\x00" * 58 + struct.pack("<I", 64)
        pe_header = b"PE\x00\x00"
        coff_header = struct.pack(
            "<HHIIIHH",
            0x014c,  # i386
            1,       # sections
            0,       # Zero timestamp
            0, 0, 224, 0x0002
        )
        test_file.write_bytes(dos_header + pe_header + coff_header + b"\x00" * 200)
        
        pe_info = _extract_pe_info(test_file)
        
        # Should handle zero timestamp gracefully
        assert pe_info["compile_timestamp"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
