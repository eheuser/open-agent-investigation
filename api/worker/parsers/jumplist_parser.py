from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import uuid
import json
import struct

from sqlalchemy.ext.asyncio import AsyncSession
import olefile
import LnkParse3

from .base_parser import BaseParser
from .utils import flatten_dict
from app.utils.log_setup import get_logger

logger = get_logger(__name__)


def _sanitize_lnk_data(data: Any) -> Any:
    """
    Sanitize LNK data to make it JSON-serializable.
    Converts datetime objects to ISO format strings.
    """
    if isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, dict):
        return {k: _sanitize_lnk_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_lnk_data(item) for item in data]
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    else:
        # Convert unknown types to string
        return str(data)


class JumplistParser(BaseParser):
    """
    Parser for Windows Jump List files.
    
    Supports both Automatic Destinations (.automaticDestinations-ms) and
    Custom Destinations (.customDestinations-ms) formats.
    """
    
    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Identify Jump List files by extension.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            True if file is a Jump List file
        """
        filename_lower = filename.lower()
        return (filename_lower.endswith('.automaticdestinations-ms') or
                filename_lower.endswith('.customdestinations-ms'))
    
    async def _parse_impl(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Parse Jump List file and extract recently accessed file entries.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID
            file_path: Path to Jump List file
            
        Returns:
            Number of events inserted
        """
        filename_lower = file_path.name.lower()
        events = []
        
        if filename_lower.endswith(".automaticdestinations-ms"):
            events = await self._parse_automatic_destinations(file_path)
        elif filename_lower.endswith(".customdestinations-ms"):
            events = await self._parse_custom_destinations(file_path)
        else:
            logger.debug(f"Unknown jump list format: {file_path.name}")
            return 0
        
        if not events:
            logger.debug(f"No valid entries found in jump list: {file_path}")
            return 0
        
        # Prepare events for insertion
        db_events = []
        for event_data in events:
            event = {
                "event_ts": event_data["timestamp"],
                "artifact_id": artifact_id,
                "event_type": "jumplist_entry",
                "payload": json.dumps(event_data["payload"]),
            }
            db_events.append(event)
        
        await self._insert_event_batch(db, investigation_id, db_events)
        
        logger.debug(f"Parsed {len(db_events)} entries from jump list: {file_path.name}")
        return len(db_events)
    
    async def _parse_automatic_destinations(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Parse Automatic Destinations jump list file using olefile.
        
        These are OLE compound files containing multiple streams, each representing
        a recently accessed file (LNK data embedded in OLE streams).
        """
        events = []
        
        try:
            # Extract AppID from filename (format: {AppID}.automaticDestinations-ms)
            app_id = file_path.stem
            
            # Open OLE file
            ole = olefile.OleFileIO(str(file_path))
            
            # List all streams in the OLE file
            stream_list = ole.listdir()
            
            for stream_path in stream_list:
                # Skip DestList stream (metadata stream)
                stream_name = '/'.join(stream_path)
                if stream_name == 'DestList':
                    continue
                
                try:
                    # Read stream data
                    stream_data = ole.openstream(stream_path).read()
                    
                    # Each stream contains LNK file data
                    # Try to parse as LNK
                    if len(stream_data) > 76:  # Minimum LNK size
                        try:
                            # Parse LNK data from stream
                            import io
                            lnk_stream = io.BytesIO(stream_data)
                            lnk = LnkParse3.lnk_file(lnk_stream)
                            lnk_data = lnk.get_json()
                            
                            # Extract timestamp
                            event_ts = None
                            if isinstance(lnk_data, dict) and "header" in lnk_data:
                                header = lnk_data["header"]
                                for ts_field in ["write_time", "access_time", "creation_time"]:
                                    if ts_field in header and header[ts_field]:
                                        try:
                                            if isinstance(header[ts_field], (int, float)):
                                                event_ts = datetime.fromtimestamp(header[ts_field])
                                                break
                                        except:
                                            pass
                            
                            if not event_ts:
                                event_ts = datetime.fromtimestamp(file_path.stat().st_mtime)
                            
                            # Extract target path
                            target_path = "unknown"
                            if isinstance(lnk_data, dict):
                                if "link_info" in lnk_data and isinstance(lnk_data["link_info"], dict):
                                    target_path = lnk_data["link_info"].get("local_base_path", "unknown")
                                elif "string_data" in lnk_data and isinstance(lnk_data["string_data"], dict):
                                    target_path = lnk_data["string_data"].get("relative_path", "unknown")
                            
                            # Sanitize lnk_data to make it JSON-serializable
                            sanitized_lnk_data = _sanitize_lnk_data(lnk_data) if isinstance(lnk_data, dict) else {}
                            
                            payload = flatten_dict({
                                "jumplist_type": "automatic_destinations",
                                "app_id": app_id,
                                "stream_name": stream_name,
                                "target_path": target_path,
                                "lnk_data": sanitized_lnk_data,
                                "file_path": str(file_path.name)
                            })
                            
                            events.append({
                                "timestamp": event_ts,
                                "payload": payload
                            })
                        
                        except Exception as lnk_error:
                            logger.debug(f"Could not parse LNK from stream {stream_name}: {lnk_error}")
                
                except Exception as stream_error:
                    logger.debug(f"Error reading stream {stream_name}: {stream_error}")
            
            ole.close()
        
        except Exception as e:
            logger.debug(f"Error parsing automatic destinations: {e}")
        
        return events
    
    async def _parse_custom_destinations(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Parse Custom Destinations jump list file.
        
        These files contain a header followed by one or more LNK file entries.
        """
        events = []
        
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            
            # Extract AppID from filename
            app_id = file_path.stem
            
            if len(data) < 32:
                logger.debug(f"File too small to be valid custom destinations: {file_path.name}")
                return events
            
            offset = 0
            entry_num = 0
            
            while offset < len(data) - 76:  # 76 = minimum LNK size
                # Look for LNK signature (0x0000004C)
                if offset + 4 <= len(data):
                    sig = struct.unpack('<I', data[offset:offset+4])[0]
                    
                    if sig == 0x0000004C:  # LNK header signature
                        entry_num += 1
                        
                        try:
                            if offset + 76 <= len(data):
                                # Parse LNK data
                                import io
                                lnk_stream = io.BytesIO(data[offset:])
                                lnk = LnkParse3.lnk_file(lnk_stream)
                                lnk_data = lnk.get_json()
                                
                                # Extract timestamp
                                event_ts = None
                                if isinstance(lnk_data, dict) and "header" in lnk_data:
                                    header = lnk_data["header"]
                                    for ts_field in ["write_time", "access_time", "creation_time"]:
                                        if ts_field in header and header[ts_field]:
                                            try:
                                                if isinstance(header[ts_field], (int, float)):
                                                    event_ts = datetime.fromtimestamp(header[ts_field])
                                                    break
                                            except:
                                                pass
                                
                                if not event_ts:
                                    event_ts = datetime.fromtimestamp(file_path.stat().st_mtime)
                                
                                # Extract target path
                                target_path = "unknown"
                                if isinstance(lnk_data, dict):
                                    if "link_info" in lnk_data and isinstance(lnk_data["link_info"], dict):
                                        target_path = lnk_data["link_info"].get("local_base_path", "unknown")
                                    elif "string_data" in lnk_data and isinstance(lnk_data["string_data"], dict):
                                        target_path = lnk_data["string_data"].get("relative_path", "unknown")
                                
                                # Sanitize lnk_data to make it JSON-serializable
                                sanitized_lnk_data = _sanitize_lnk_data(lnk_data) if isinstance(lnk_data, dict) else {}
                                
                                payload = flatten_dict({
                                    "jumplist_type": "custom_destinations",
                                    "app_id": app_id,
                                    "entry_number": entry_num,
                                    "offset": offset,
                                    "target_path": target_path,
                                    "lnk_data": sanitized_lnk_data,
                                    "file_path": str(file_path.name)
                                })
                                
                                events.append({
                                    "timestamp": event_ts,
                                    "payload": payload
                                })
                                
                                # Move past this LNK entry
                                offset += 512
                            else:
                                offset += 1
                        
                        except Exception as lnk_error:
                            logger.debug(f"Could not parse LNK at offset {offset}: {lnk_error}")
                            offset += 1
                    else:
                        offset += 1
                else:
                    break
        
        except Exception as e:
            logger.debug(f"Error parsing custom destinations: {e}")
        
        return events


__all__ = ["JumplistParser"]
