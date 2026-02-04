from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
import struct

from .base_parser import BaseParser

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

        # Extract executable name (Unicode string at offset 16)
        # This is a simplified version - full parsing would use proper library
        try:
            exe_name_offset = 16
            exe_name_bytes = data[exe_name_offset : exe_name_offset + 60]
            exe_name = exe_name_bytes.decode("utf-16-le").split("\x00")[0]
        except Exception as e:
            logger.debug(f"Failed to extract executable name: {e}")
            exe_name = file_path.stem

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
