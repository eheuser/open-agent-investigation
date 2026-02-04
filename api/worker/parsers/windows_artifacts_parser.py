from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import uuid
import json
import sqlite3
import struct

from sqlalchemy.ext.asyncio import AsyncSession
import pyesedb
import xml.etree.ElementTree as ET

from .base_parser import BaseParser
from .utils import flatten_dict
from app.utils.log_setup import get_logger

logger = get_logger(__name__)


def _sanitize_value(value: Any) -> Any:
    """
    Sanitize a value to remove null bytes and other problematic characters.
    
    PostgreSQL cannot handle null bytes in text/json fields, so we need to
    strip them out before insertion.
    """
    if isinstance(value, str):
        # Remove null bytes and other control characters
        return value.replace('\x00', '').replace('\u0000', '')
    elif isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    return value


class WindowsArtifactsParser(BaseParser):
    """
    Parser for various Windows forensic artifacts.
    
    Supports:
    - CryptNetUrlCache
    - PCA (Program Compatibility Assistant) files
    - Scheduled Tasks (.job files and Task Scheduler XML)
    - SRUM (System Resource Usage Monitor) database
    - Windows Search database
    - Bitmap Cache
    - Notification database (wpndatabase.db)
    """
    
    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Identify various Windows artifact files using magic bytes and structural validation.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            True if file is a recognized Windows artifact
        """
        try:
            file_size = file_path.stat().st_size
            
            # Read appropriate amount based on file size
            # CryptNetUrlCache files are typically < 100KB
            read_size = min(file_size, 32 * 1024)  # Read up to 32KB
            
            with open(file_path, 'rb') as f:
                header = f.read(read_size)
            
            if len(header) < 16:
                return False
            
            # Validate it's an ESE database, then check if it's SRUM specifically
            if file_size <= (16 * 1024 * 1024):  # Only try to open smaller ESE files
                try:
                    db = pyesedb.file()
                    db.open(str(file_path))  # Convert Path to string
                    cnt = 0
                    for table_idx in range(db.get_number_of_tables()):
                        _table = db.get_table(table_idx)
                        if _table.get_name() in (
                            "SruDbIdMapTable",
                            "{973F5D5C-1D90-4944-BE8E-24B94231A174}",
                        ):
                            cnt += 1
                    db.close()
                    if cnt == 2:
                        return True
                except Exception as e:
                    logger.debug(f"SRUM DB check failed: {e}")
                    pass
            
            # SQLite database (Notification DB) - magic: "SQLite format 3\x00"
            if header.startswith(b'SQLite format 3\x00'):
                # Verify it has a Notification table
                try:
                    conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Notification'")
                    has_notif_table = cursor.fetchone() is not None
                    conn.close()
                    if has_notif_table:
                        return True
                except Exception as e:
                    logger.debug(f"SQLite3 Browser History check failed: {e}")
                    pass
            
            # Windows .job file - magic: product version at specific offset
            if len(header) >= 20:
                # Job files have specific structure: version info at offset 0
                try:
                    product_version = struct.unpack('<H', header[0:2])[0]
                    file_version = struct.unpack('<H', header[2:4])[0]
                    # Windows job files typically have version 0x0001 and specific UUID
                    if product_version == 0x0001 and file_version == 0x0001:
                        # Check for task UUID at offset 4
                        uuid_bytes = header[4:20]
                        if len(uuid_bytes) == 16:
                            return True
                except Exception as e:
                    logger.debug(f"Windows Job check failed: {e}")
                    pass
            
            # Task Scheduler XML - check for XML with task namespace
            # This must be checked BEFORE registry parser to avoid false positives
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                # Check for Task Scheduler namespace and Task element
                # Root tag could be: {http://schemas.microsoft.com/windows/2004/02/mit/task}Task or just Task
                # Check if it has the namespace or has the expected structure
                ns = {'task': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
                
                # Check both namespaced and non-namespaced elements
                if 'Task' in (root.tag or ''):
                    # Try with namespace
                    has_task_elements = (
                        root.find('.//task:RegistrationInfo', ns) is not None or 
                        root.find('.//task:Actions', ns) is not None or
                        root.find('.//task:Triggers', ns) is not None
                    )
                    
                    # Try without namespace (some task XMLs don't use namespace)
                    if not has_task_elements:
                        has_task_elements = (
                            root.find('.//RegistrationInfo') is not None or 
                            root.find('.//Actions') is not None or
                            root.find('.//Triggers') is not None
                        )
                    
                    if has_task_elements:
                        return True
            except ET.ParseError:
                pass
            except Exception as e:
                logger.debug(f"XML parsing failed for {filename}: {e}")
                pass
            
            # CryptNetUrlCache - try to actually parse it (files typically < 100KB)
            if file_size < 100 * 1024 and len(header) >= 116:
                try:
                    # Parse header structure (matches original code exactly)
                    parsed_header = struct.unpack("<12xIQ64xQ4xI8xI", header[:116])
                    url_size = parsed_header[0]
                    # Verify we have enough data
                    if len(header) < 116 + url_size:
                        raise ValueError("Insufficient data for URL")
                    
                    # Try to decode the URL (match original logic exactly)
                    url_bytes = header[116:116+url_size]
                    url_chars = struct.unpack(f"{url_size}c", url_bytes)
                    url = b"".join(url_chars).decode("utf-16-le")[0:-1]  # Slice off last char
                    
                    # URL should be non-empty
                    if url and len(url) > 0:
                        return True
                except Exception as e:
                    logger.debug(f"CryptNetUrlCache check failed: {e}")
                    pass
            
            # Bitmap Cache (thumbcache/iconcache) - Windows cache format
            # These have "CMMM" magic at offset 0
            if header.startswith(b'CMMM'):
                return True
            
            # PCA files - binary format with specific structure
            # These are harder to identify by magic, but have characteristic patterns
            if len(header) >= 32:
                try:
                    # PCA files often start with specific byte patterns
                    # They contain serialized .NET binary formatter data
                    if header[0:1] == b'\x00' and b'\x01\x00\x00\x00' in header[:32]:
                        # Additional heuristic: check for .NET binary formatter signatures
                        if b'System.' in header or b'Microsoft.' in header:
                            return True
                except Exception as e:
                    logger.debug(f"PCA Launch Item check failed: {e}")
                    pass
            return False
            
        except Exception as e:
            logger.debug(f"Error during Windows artifact identification: {e}")
            return False
    
    async def _parse_impl(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Parse Windows artifact and extract forensic events.
        
        Attempts to parse using multiple parsers and returns results from the first successful one.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID
            file_path: Path to artifact file
            
        Returns:
            Number of events inserted
        """
        events = []
        
        parsers = (
            self._parse_notification_database,
            self._parse_srum_database,
            self._parse_windows_search,
            self._parse_scheduled_task_xml,
            self._parse_scheduled_task_job,
            self._parse_cryptnet_cache,
            self._parse_bitmap_cache,
            self._parse_pca_file,
        )

        for parser_fn in parsers:
            try:
                events = await parser_fn(file_path)
            except Exception:
                continue
            if events:
                break

        if not events:
            logger.debug(f"No valid entries found in Windows artifact: {file_path}")
            return 0
        
        # Prepare events for insertion
        db_events = []
        for event_data in events:
            event = {
                "event_ts": event_data["timestamp"],
                "artifact_id": artifact_id,
                "event_type": event_data.get("event_type", "windows_artifact"),
                "payload": json.dumps(event_data["payload"]),
            }
            db_events.append(event)
        
        await self._insert_event_batch(db, investigation_id, db_events)
        
        logger.debug(f"Parsed {len(db_events)} entries from Windows artifact: {file_path.name}")
        return len(db_events)
    
    async def _parse_cryptnet_cache(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse CryptNetUrlCache files."""
        events = []
        
        try:
            with open(file_path, "rb") as fh:
                data = fh.read()
                
                if len(data) < 116:
                    return events
                
                # Parse header
                header = struct.unpack("<12xIQ64xQ4xI8xI", data[:116])
                urlSize = header[0]
                last_download_time_raw = header[1]
                last_modification_time_raw = header[2]
                
                # Validate FILETIME values
                if not (116444736000000000 <= last_download_time_raw <= 200000000000000000):
                    return events
                
                last_download_time = round(((last_download_time_raw - 116444736000000000) // 10) / 1_000_000, 3)
                last_modification_time_header = round(((last_modification_time_raw - 116444736000000000) // 10) / 1_000_000, 3)
                
                # Validate URL size
                if not (1 <= urlSize <= 2048) or len(data) < 116 + urlSize:
                    return events
                
                # Extract URL
                url_bytes = data[116:116+urlSize]
                url = url_bytes.decode("utf-16-le", errors='ignore').rstrip('\x00')
                
                if not url:
                    return events
                
                event_ts = datetime.fromtimestamp(last_download_time, tz=timezone.utc)
                
                payload = flatten_dict({
                    "artifact_type": "cryptnet_url_cache",
                    "url": url,
                    "last_download_time": last_download_time,
                    "last_modification_time": last_modification_time_header,
                    "file_path": str(file_path.name)
                })
                
                events.append({
                    "timestamp": event_ts,
                    "event_type": "cryptnet_cache",
                    "payload": payload
                })
        
        except Exception as e:
            logger.debug(f"Not a valid CryptNetUrlCache file: {e}")
        
        return events
    
    async def _parse_pca_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Program Compatibility Assistant (PCA) files."""
        events = []
        
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            
            event_ts = datetime.fromtimestamp(file_path.stat().st_mtime)
            
            payload = flatten_dict({
                "artifact_type": "pca_launch",
                "file_name": file_path.name,
                "file_size": len(data),
                "file_path": str(file_path)
            })
            
            events.append({
                "timestamp": event_ts,
                "event_type": "pca_execution",
                "payload": payload
            })
        
        except Exception as e:
            logger.debug(f"Error parsing PCA file: {e}")
        
        return events
    
    async def _parse_scheduled_task_job(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Windows .job files (legacy scheduled tasks)."""
        events = []
        
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            
            if len(data) < 68:
                return events
            
            # Validate job file header
            product_version = struct.unpack('<H', data[0:2])[0]
            file_version = struct.unpack('<H', data[2:4])[0]
            
            if product_version != 0x0001 or file_version != 0x0001:
                return events
            
            event_ts = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            task_name = file_path.stem
            
            payload = flatten_dict({
                "artifact_type": "scheduled_task_job",
                "task_name": task_name,
                "file_size": len(data),
                "file_path": str(file_path)
            })
            
            events.append({
                "timestamp": event_ts,
                "event_type": "scheduled_task",
                "payload": payload
            })
        
        except Exception as e:
            logger.debug(f"Not a valid .job file: {e}")
        
        return events
    
    async def _parse_scheduled_task_xml(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Windows Task Scheduler XML files (modern format)."""
        events = []
        
        try:
            import xml.etree.ElementTree as ET
            
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Extract namespace (may or may not be present)
            ns = {'task': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
            
            # Validate this is a Task Scheduler XML by checking for expected structure
            # Must have Task in root tag and at least one of the expected child elements
            if 'Task' not in root.tag:
                return events
            
            # Try with namespace first, then without
            has_structure = (
                root.find('.//task:RegistrationInfo', ns) is not None or 
                root.find('.//task:Actions', ns) is not None or
                root.find('.//task:Triggers', ns) is not None
            )
            
            use_namespace = has_structure
            
            if not has_structure:
                # Try without namespace
                has_structure = (
                    root.find('.//RegistrationInfo') is not None or 
                    root.find('.//Actions') is not None or
                    root.find('.//Triggers') is not None
                )
                use_namespace = False
            
            if not has_structure:
                return events
            
            # Try to find task registration info
            if use_namespace:
                reg_info = root.find('.//task:RegistrationInfo', ns)
                date_elem = reg_info.find('task:Date', ns) if reg_info is not None else None
                author_elem = reg_info.find('task:Author', ns) if reg_info is not None else None
                desc_elem = reg_info.find('task:Description', ns) if reg_info is not None else None
                actions = root.findall('.//task:Exec', ns)
            else:
                reg_info = root.find('.//RegistrationInfo')
                date_elem = reg_info.find('Date') if reg_info is not None else None
                author_elem = reg_info.find('Author') if reg_info is not None else None
                desc_elem = reg_info.find('Description') if reg_info is not None else None
                actions = root.findall('.//Exec')
            
            # Extract actions
            action_commands = []
            for action in actions:
                if use_namespace:
                    command = action.find('task:Command', ns)
                    args = action.find('task:Arguments', ns)
                else:
                    command = action.find('Command')
                    args = action.find('Arguments')
                
                if command is not None:
                    cmd_text = command.text or ""
                    args_text = args.text if args is not None else ""
                    action_commands.append(f"{cmd_text} {args_text}".strip())
            
            # Use registration date or file modification time
            if date_elem is not None and date_elem.text:
                try:
                    event_ts = datetime.fromisoformat(date_elem.text.replace('Z', '+00:00'))
                except:
                    event_ts = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            else:
                event_ts = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            
            payload = flatten_dict({
                "artifact_type": "scheduled_task_xml",
                "task_name": file_path.stem,
                "author": author_elem.text if author_elem is not None else "",
                "description": desc_elem.text if desc_elem is not None else "",
                "actions": action_commands,
                "file_path": str(file_path)
            })
            
            events.append({
                "timestamp": event_ts,
                "event_type": "scheduled_task",
                "payload": payload
            })
        
        except Exception as e:
            logger.debug(f"Not a valid Task Scheduler XML: {e}")
        
        return events
    
    async def _parse_srum_database(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse SRUM (System Resource Usage Monitor) database using pyesedb."""
        events = []
        
        try:
            esedb_file = pyesedb.file()
            # pyesedb requires string path, not Path object
            esedb_file.open(str(file_path))
            
            # Validate this is a SRUM database by checking for characteristic tables
            table_names = [esedb_file.get_table(i).get_name() for i in range(min(esedb_file.get_number_of_tables(), 20))]
            srum_indicators = ['SruDbIdMapTable', '{D10CA2FE-6FCF-4F6D-848E-B2E99266FA89}', 
                              '{973F5D5C-1D90-4944-BE8E-24B94231A174}', '{DD6636C4-8929-4683-974E-22C046A43763}']
            
            if not any(indicator in table_names for indicator in srum_indicators):
                esedb_file.close()
                return events
            
            for table_idx in range(esedb_file.get_number_of_tables()):
                table = esedb_file.get_table(table_idx)
                table_name = table.get_name()
                
                # Skip system tables
                if table_name.startswith('MSys'):
                    continue
                
                try:
                    # Get column names
                    column_names = []
                    for col_idx in range(table.get_number_of_columns()):
                        column = table.get_column(col_idx)
                        column_names.append(column.get_name())
                    
                    # Process records (limit to prevent excessive data)
                    max_records = min(table.get_number_of_records(), 1000)
                    
                    for record_idx in range(max_records):
                        try:
                            record = table.get_record(record_idx)
                            record_data = {}
                            timestamp = None
                            
                            for col_idx, col_name in enumerate(column_names):
                                try:
                                    value = record.get_value_data(col_idx)
                                    
                                    # Handle timestamps (FILETIME format)
                                    if col_name == 'TimeStamp' and value:
                                        try:
                                            if isinstance(value, int):
                                                epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
                                                timestamp = epoch + timedelta(microseconds=value / 10)
                                            elif isinstance(value, bytes) and len(value) == 8:
                                                filetime = struct.unpack('<Q', value)[0]
                                                epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
                                                timestamp = epoch + timedelta(microseconds=filetime / 10)
                                        except:
                                            pass
                                    
                                    # Store value
                                    if value is not None:
                                        if isinstance(value, bytes):
                                            try:
                                                record_data[col_name] = value.decode('utf-16-le', errors='ignore').strip('\x00')
                                            except:
                                                record_data[col_name] = value.hex()
                                        else:
                                            record_data[col_name] = value
                                except:
                                    pass
                            
                            if not timestamp:
                                timestamp = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                            
                            if record_data:
                                # Sanitize record_data to remove null bytes
                                record_data = _sanitize_value(record_data)
                                
                                payload = flatten_dict({
                                    "artifact_type": "srum_database",
                                    "table_name": table_name,
                                    "data": record_data,
                                    "source_file": file_path.name
                                })
                                
                                events.append({
                                    "timestamp": timestamp,
                                    "event_type": "srum_data",
                                    "payload": payload
                                })
                        
                        except Exception:
                            continue
                
                except Exception as table_error:
                    logger.debug(f"Error processing SRUM table {table_name}: {table_error}")
            
            esedb_file.close()
        
        except Exception as e:
            logger.debug(f"Not a valid SRUM database: {e}")
        
        return events
    
    async def _parse_windows_search(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Windows Search database (Windows.edb) using pyesedb."""
        events = []
        
        try:
            esedb_file = pyesedb.file()
            # pyesedb requires string path, not Path object
            esedb_file.open(str(file_path))
            
            # Validate this is a Windows Search database by checking for SystemIndex tables
            table_names = [esedb_file.get_table(i).get_name() for i in range(min(esedb_file.get_number_of_tables(), 50))]
            
            if not any('SystemIndex' in name for name in table_names):
                esedb_file.close()
                return events
            
            for table_idx in range(esedb_file.get_number_of_tables()):
                table = esedb_file.get_table(table_idx)
                table_name = table.get_name()
                
                # Focus on SystemIndex tables
                if not table_name.startswith('SystemIndex'):
                    continue
                
                try:
                    # Get column names
                    column_names = []
                    for col_idx in range(table.get_number_of_columns()):
                        column = table.get_column(col_idx)
                        column_names.append(column.get_name())
                    
                    # Process records (limit to prevent excessive data)
                    max_records = min(table.get_number_of_records(), 5000)
                    
                    for record_idx in range(max_records):
                        try:
                            record = table.get_record(record_idx)
                            record_data = {}
                            timestamp = None
                            
                            for col_idx, col_name in enumerate(column_names):
                                try:
                                    value = record.get_value_data(col_idx)
                                    
                                    # Extract common search index fields
                                    if col_name in ['System_ItemUrl', 'System_ItemName', 'System_ItemPathDisplay',
                                                   'System_DateModified', 'System_DateCreated', 'System_Size',
                                                   'System_FileExtension', 'System_Kind', 'System_Author']:
                                        
                                        if value is not None:
                                            if isinstance(value, bytes):
                                                try:
                                                    record_data[col_name] = value.decode('utf-16-le', errors='ignore').strip('\x00')
                                                except:
                                                    record_data[col_name] = value.hex()
                                            else:
                                                record_data[col_name] = value
                                            
                                            # Use DateModified or DateCreated as timestamp
                                            if col_name in ['System_DateModified', 'System_DateCreated'] and not timestamp:
                                                try:
                                                    if isinstance(value, int):
                                                        epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
                                                        timestamp = epoch + timedelta(microseconds=value / 10)
                                                    elif isinstance(value, bytes) and len(value) == 8:
                                                        filetime = struct.unpack('<Q', value)[0]
                                                        epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
                                                        timestamp = epoch + timedelta(microseconds=filetime / 10)
                                                except:
                                                    pass
                                except:
                                    pass
                            
                            if not timestamp:
                                timestamp = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                            
                            if record_data:
                                # Sanitize record_data to remove null bytes
                                record_data = _sanitize_value(record_data)
                                
                                payload = flatten_dict({
                                    "artifact_type": "windows_search_database",
                                    "table_name": table_name,
                                    "data": record_data,
                                    "source_file": file_path.name
                                })
                                
                                events.append({
                                    "timestamp": timestamp,
                                    "event_type": "windows_search",
                                    "payload": payload
                                })
                        
                        except Exception:
                            continue
                
                except Exception as table_error:
                    logger.debug(f"Error processing Windows Search table {table_name}: {table_error}")
            
            esedb_file.close()
        
        except Exception as e:
            logger.debug(f"Not a valid Windows Search database: {e}")
        
        return events
    
    async def _parse_bitmap_cache(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Windows Bitmap Cache files (thumbcache_*.db, iconcache_*.db)."""
        events = []
        
        try:
            with open(file_path, "rb") as f:
                header = f.read(32)
            
            # Validate bitmap cache magic "CMMM"
            if not header.startswith(b'CMMM'):
                return events
            
            event_ts = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            
            # Determine cache type from magic or structure if possible
            cache_type = "unknown"
            if len(header) >= 8:
                # Could add more specific type detection here
                cache_type = "thumbnail_or_icon"
            
            payload = flatten_dict({
                "artifact_type": "bitmap_cache",
                "cache_type": cache_type,
                "file_name": file_path.name,
                "file_size": file_path.stat().st_size,
                "file_path": str(file_path),
                "note": "Bitmap cache contains thumbnail/icon images"
            })
            
            events.append({
                "timestamp": event_ts,
                "event_type": "bitmap_cache",
                "payload": payload
            })
        
        except Exception as e:
            logger.debug(f"Not a valid bitmap cache file: {e}")
        
        return events
    
    async def _parse_notification_database(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Windows Notification database (wpndatabase.db)."""
        events = []
        
        try:
            # Verify it's a SQLite database with Notification table
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Check for Notification table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Notification'")
            if not cursor.fetchone():
                conn.close()
                return events
            
            # Query notification table
            query = """
                SELECT 
                    Id,
                    Type,
                    Payload,
                    ExpiryTime,
                    ArrivalTime
                FROM Notification
                ORDER BY ArrivalTime DESC
                LIMIT 1000
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                notif_id, notif_type, payload_data, expiry, arrival = row
                
                # Parse arrival time (Unix timestamp in milliseconds)
                if arrival:
                    timestamp = datetime.fromtimestamp(arrival / 1000, tz=timezone.utc)
                else:
                    timestamp = datetime.now(timezone.utc)
                
                payload = flatten_dict({
                    "artifact_type": "windows_notification",
                    "notification_id": notif_id,
                    "notification_type": notif_type,
                    "payload_preview": payload_data[:200] if payload_data else "",
                    "expiry_time": expiry,
                    "source_file": file_path.name
                })
                
                events.append({
                    "timestamp": timestamp,
                    "event_type": "notification",
                    "payload": payload
                })
            
            conn.close()
        
        except Exception as e:
            logger.debug(f"Not a valid notification database: {e}")
        
        return events


__all__ = ["WindowsArtifactsParser"]
