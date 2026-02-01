from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import uuid
import json
import sqlite3

from sqlalchemy.ext.asyncio import AsyncSession
import pyesedb

from .base_parser import BaseParser
from .utils import flatten_dict
from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class BrowserHistoryParser(BaseParser):
    """
    Parser for browser history databases.
    
    Supports Chrome, Edge (Chromium and Legacy), and Firefox history databases.
    """
    
    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Identify browser history files.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            True if file is a browser history database
        """
        filename_lower = filename.lower()
        
        # Chrome/Edge Chromium: History (SQLite)
        if filename_lower == 'history' or 'history' in filename_lower:
            try:
                # Check if it's a SQLite database
                with open(file_path, 'rb') as f:
                    header = f.read(16)
                    if header.startswith(b'SQLite format 3'):
                        return True
            except Exception:
                pass
        
        # Firefox: places.sqlite
        if 'places.sqlite' in filename_lower:
            return True
        
        # Legacy Edge: WebCacheV*.dat (ESE database)
        if 'webcache' in filename_lower and filename_lower.endswith('.dat'):
            try:
                # Try to open as ESE database
                esedb_file = pyesedb.file()
                esedb_file.open(str(file_path))
                esedb_file.close()
                return True
            except Exception:
                pass
        
        return False
    
    async def _parse_impl(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Parse browser history database and extract browsing events.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID
            file_path: Path to browser history file
            
        Returns:
            Number of events inserted
        """
        filename_lower = file_path.name.lower()
        events = []
        
        # Determine browser type from filename
        if "history" in filename_lower and not filename_lower.endswith(".dat"):
            # Chrome or Chromium-based Edge
            events = await self._parse_chromium_history(file_path)
        elif "places.sqlite" in filename_lower:
            # Firefox
            events = await self._parse_firefox_history(file_path)
        elif "webcache" in filename_lower and filename_lower.endswith(".dat"):
            # Legacy Edge ESE database
            events = await self._parse_legacy_edge_history(file_path)
        else:
            logger.warning(f"Unknown browser history format: {file_path.name}")
            return 0
        
        if not events:
            logger.warning(f"No valid entries found in browser history: {file_path}")
            return 0
        
        # Prepare events for insertion
        db_events = []
        for event_data in events:
            event = {
                "event_ts": event_data["timestamp"],
                "artifact_id": artifact_id,
                "event_type": "browser_history",
                "payload": json.dumps(event_data["payload"]),
            }
            db_events.append(event)
        
        await self._insert_event_batch(db, investigation_id, db_events)
        
        logger.info(f"Parsed {len(db_events)} browser history entries from: {file_path.name}")
        return len(db_events)
    
    async def _parse_chromium_history(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Chrome/Chromium-based browser history."""
        events = []
        
        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Query urls and visits tables
            query = """
                SELECT 
                    urls.url,
                    urls.title,
                    visits.visit_time,
                    visits.transition,
                    urls.visit_count,
                    urls.typed_count,
                    urls.last_visit_time
                FROM urls
                LEFT JOIN visits ON urls.id = visits.url
                ORDER BY visits.visit_time DESC
                LIMIT 10000
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                url, title, visit_time, transition, visit_count, typed_count, last_visit = row
                
                # Chrome stores timestamps as microseconds since 1601-01-01
                if visit_time:
                    # Convert Chrome timestamp to Unix timestamp
                    chrome_epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
                    timestamp = chrome_epoch + timedelta(microseconds=visit_time)
                else:
                    timestamp = datetime.now(timezone.utc)
                
                payload = flatten_dict({
                    "browser": "chrome_chromium",
                    "url": url or "",
                    "title": title or "",
                    "visit_count": visit_count or 0,
                    "typed_count": typed_count or 0,
                    "transition_type": transition,
                    "source_file": file_path.name
                })
                
                events.append({
                    "timestamp": timestamp,
                    "payload": payload
                })
            
            conn.close()
        
        except Exception as e:
            logger.warning(f"Error parsing Chromium history: {e}")
        
        return events
    
    async def _parse_firefox_history(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse Firefox browser history from places.sqlite."""
        events = []
        
        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Query moz_places and moz_historyvisits tables
            query = """
                SELECT 
                    moz_places.url,
                    moz_places.title,
                    moz_historyvisits.visit_date,
                    moz_places.visit_count,
                    moz_places.typed,
                    moz_historyvisits.visit_type
                FROM moz_places
                LEFT JOIN moz_historyvisits ON moz_places.id = moz_historyvisits.place_id
                ORDER BY moz_historyvisits.visit_date DESC
                LIMIT 10000
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                url, title, visit_date, visit_count, typed, visit_type = row
                
                # Firefox stores timestamps as microseconds since Unix epoch
                if visit_date:
                    timestamp = datetime.fromtimestamp(visit_date / 1000000, tz=timezone.utc)
                else:
                    timestamp = datetime.now(timezone.utc)
                
                payload = flatten_dict({
                    "browser": "firefox",
                    "url": url or "",
                    "title": title or "",
                    "visit_count": visit_count or 0,
                    "typed": typed or 0,
                    "visit_type": visit_type,
                    "source_file": file_path.name
                })
                
                events.append({
                    "timestamp": timestamp,
                    "payload": payload
                })
            
            conn.close()
        
        except Exception as e:
            logger.warning(f"Error parsing Firefox history: {e}")
        
        return events
    
    async def _parse_legacy_edge_history(self, file_path: Path) -> List[Dict[str, Any]]:
        """Parse legacy Edge browser history from WebCacheV*.dat ESE database."""
        events = []
        
        try:
            # Open ESE database
            esedb_file = pyesedb.file()
            esedb_file.open(str(file_path))
            
            # Legacy Edge WebCache contains multiple containers
            for table_idx in range(esedb_file.get_number_of_tables()):
                table = esedb_file.get_table(table_idx)
                table_name = table.get_name()
                
                # Look for History container tables
                if "container" in table_name.lower():
                    try:
                        # Iterate through records
                        for record_idx in range(table.get_number_of_records()):
                            try:
                                record = table.get_record(record_idx)
                                
                                # Extract URL and access time
                                url = None
                                access_time = None
                                
                                # Try to extract URL (usually in early columns)
                                for col_idx in range(min(record.get_number_of_values(), 20)):
                                    try:
                                        value = record.get_value_data(col_idx)
                                        if value and isinstance(value, bytes):
                                            try:
                                                decoded = value.decode('utf-16-le', errors='ignore').strip('\x00')
                                                if decoded.startswith('http://') or decoded.startswith('https://'):
                                                    url = decoded
                                                    break
                                            except:
                                                pass
                                    except:
                                        pass
                                
                                # Try to extract timestamp
                                for col_idx in range(min(record.get_number_of_values(), 20)):
                                    try:
                                        value_type = record.get_column_type(col_idx)
                                        if value_type in [8, 15]:  # Date/time types
                                            value = record.get_value_data_as_integer(col_idx)
                                            if value and value > 0:
                                                # Convert FILETIME to datetime
                                                epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
                                                access_time = epoch + timedelta(microseconds=value / 10)
                                                break
                                    except:
                                        pass
                                
                                if url:
                                    if not access_time:
                                        access_time = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                                    
                                    payload = flatten_dict({
                                        "browser": "edge_legacy",
                                        "url": url,
                                        "table_name": table_name,
                                        "source_file": file_path.name
                                    })
                                    
                                    events.append({
                                        "timestamp": access_time,
                                        "payload": payload
                                    })
                            
                            except Exception:
                                continue
                    
                    except Exception as table_error:
                        logger.debug(f"Error processing table {table_name}: {table_error}")
            
            esedb_file.close()
        
        except Exception as e:
            logger.warning(f"Error parsing legacy Edge history: {e}")
        
        return events


__all__ = ["BrowserHistoryParser"]
