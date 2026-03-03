from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
import struct

from .base_parser import BaseParser
from .utils import sanitize_for_jsonb

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class PrefetchParser(BaseParser):
    """
    Parser for Windows Prefetch files.
    """

    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Identify Prefetch files by extension and magic bytes.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            True if file is a Prefetch file
        """
        if filename.lower().endswith('.pf'):
            try:
                with open(file_path, 'rb') as f:
                    magic = f.read(4)
                    # Prefetch files have MAM\x04 (Win10+) or SCCA (Win7/8) signature
                    return magic in [b'MAM\x04', b'SCCA']
            except Exception:
                return False
        return False
    
    async def _parse_impl(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Parse Prefetch file and extract execution metadata.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID
            file_path: Path to Prefetch file
            
        Returns:
            Number of events inserted
        """
        with open(file_path, "rb") as f:
            data = f.read()

        if len(data) < 84:
            logger.debug(f"Prefetch file too small: {file_path}")
            return 0

        # Extract executable name from prefetch file
        # Prefetch format varies by Windows version:
        # - SCCA (Win7/8): Uncompressed, executable name at offset 16
        # - MAM (Win10+): Compressed, need to decompress first
        
        magic = data[:4]
        exe_name = None
        
        try:
            if magic == b'SCCA':
                # Uncompressed format (Windows 7/8)
                # Executable name is at offset 16, UTF-16-LE encoded, max 60 bytes
                exe_name_offset = 16
                exe_name_bytes = data[exe_name_offset : exe_name_offset + 60]
                
                # Decode UTF-16-LE
                exe_name = exe_name_bytes.decode("utf-16-le", errors='ignore')
                
                # Split on null terminator
                if '\x00' in exe_name:
                    exe_name = exe_name.split('\x00')[0]
                    
            elif magic == b'MAM\x04':
                # Compressed format (Windows 10+)
                # The file is compressed, so we can't easily extract the name
                # Use the filename instead (prefetch files are named after the executable)
                exe_name = None
            else:
                # Unknown format
                exe_name = None
            
            # Clean up the extracted name
            if exe_name:
                # Remove null bytes and strip whitespace
                exe_name = exe_name.replace('\x00', '').strip()
                
                # Validate that it's actually text (not binary garbage)
                # Check if at least 50% of characters are printable ASCII/Latin
                if exe_name:
                    printable_count = sum(1 for c in exe_name if c.isprintable() and ord(c) < 256)
                    if len(exe_name) > 0 and printable_count / len(exe_name) < 0.5:
                        # Likely binary garbage, not a real name
                        logger.debug(f"Extracted name appears to be binary garbage: {exe_name[:20]}")
                        exe_name = None
                    else:
                        # Keep only printable characters
                        exe_name = ''.join(char for char in exe_name if char.isprintable())
            
            # Fall back to filename if extraction failed
            if not exe_name:
                # Prefetch files are named: EXECUTABLE-HASH.pf
                # Extract just the executable name part
                filename_parts = file_path.stem.split('-')
                if len(filename_parts) > 1:
                    # Remove the hash suffix
                    exe_name = '-'.join(filename_parts[:-1]) + '.exe'
                else:
                    exe_name = file_path.stem + '.exe'
                    
        except Exception as e:
            logger.debug(f"Failed to extract executable name: {e}")
            # Fall back to filename
            filename_parts = file_path.stem.split('-')
            if len(filename_parts) > 1:
                exe_name = '-'.join(filename_parts[:-1]) + '.exe'
            else:
                exe_name = file_path.stem + '.exe'

        # Extract last execution time from prefetch file
        # Prefetch files store FILETIME timestamps (64-bit value representing
        # 100-nanosecond intervals since January 1, 1601)
        # Location varies by Windows version:
        # - Windows XP/Vista/7: offset 0x78 (120)
        # - Windows 8+: offset 0x80 (128) for first execution time
        event_ts = None

        # Try Windows 8+ format first (offset 0x80)
        try:
            if len(data) >= 136:  # 0x80 + 8 bytes
                filetime_bytes = data[0x80:0x88]
                filetime = struct.unpack("<Q", filetime_bytes)[0]
                if filetime > 0:
                    # Convert FILETIME to Unix timestamp
                    # FILETIME epoch is 1601-01-01, Unix epoch is 1970-01-01
                    # Difference: 11644473600 seconds
                    unix_timestamp = (filetime / 10000000.0) - 11644473600
                    if unix_timestamp > 0:  # Sanity check
                        event_ts = datetime.utcfromtimestamp(unix_timestamp)
        except Exception as e:
            logger.debug(f"Failed to extract timestamp from Windows 8+ format: {e}")

        # Try Windows XP/Vista/7 format (offset 0x78) if above failed
        if event_ts is None:
            try:
                if len(data) >= 128:  # 0x78 + 8 bytes
                    filetime_bytes = data[0x78:0x80]
                    filetime = struct.unpack("<Q", filetime_bytes)[0]
                    if filetime > 0:
                        unix_timestamp = (filetime / 10000000.0) - 11644473600
                        if unix_timestamp > 0:
                            event_ts = datetime.utcfromtimestamp(unix_timestamp)
            except Exception as e:
                logger.debug(f"Failed to extract timestamp from Windows XP/Vista/7 format: {e}")

        # If we couldn't extract timestamp from prefetch structure, skip this file
        # (forensically invalid to use filesystem metadata)
        if event_ts is None:
            logger.debug(
                f"Could not extract execution timestamp from prefetch file {file_path} - skipping"
            )
            return 0

        # Create event
        payload = {
            "executable_name": exe_name,
            "file_size": len(data),
            "file_path": str(file_path.name),
            "last_execution_time": event_ts.isoformat(),
        }
        
        # Sanitize payload to handle any remaining encoding issues
        payload = sanitize_for_jsonb(payload)

        event = {
            "event_ts": event_ts,
            "artifact_id": artifact_id,
            "event_type": "prefetch_execution",
            "payload": json.dumps(payload),
        }

        await self._insert_event_batch(db, investigation_id, [event])

        logger.debug(f"Parsed prefetch file for executable: {exe_name}")
        return 1


__all__ = ["PrefetchParser"]
