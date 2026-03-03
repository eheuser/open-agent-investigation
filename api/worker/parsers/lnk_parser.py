from pathlib import Path
from datetime import datetime, date
from typing import Any
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
import LnkParse3

from .base_parser import BaseParser
from .utils import flatten_dict

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class LnkParser(BaseParser):
    """
    Parser for Windows LNK shortcut files.
    """
    
    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Identify LNK files by extension and magic bytes.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            True if file is a LNK file
        """
        if filename.lower().endswith('.lnk'):
            try:
                with open(file_path, 'rb') as f:
                    magic = f.read(4)
                    return magic == b'\x4c\x00\x00\x00'
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
        Parse LNK file and extract metadata.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID
            file_path: Path to LNK file
            
        Returns:
            Number of events inserted
        """
        with open(file_path, "rb") as f:
            lnk = LnkParse3.lnk_file(f)
            data = lnk.get_json()

        # Convert datetime objects to timestamps
        data = _walk_data(data)
        
        # Sanitize data to handle encoding issues from LNK parser
        from .utils import sanitize_for_jsonb
        data = sanitize_for_jsonb(data)

        # Extract timestamp for event (try various fields)
        # Forensically valid: use timestamps from the LNK file, not current time
        event_ts = None

        # Try to extract a meaningful timestamp from the data
        if isinstance(data, dict):
            # Check header timestamps
            if "header" in data and isinstance(data["header"], dict):
                header = data["header"]
                for ts_field in ["write_time", "access_time", "creation_time"]:
                    if ts_field in header and header[ts_field]:
                        try:
                            if isinstance(header[ts_field], (int, float)):
                                event_ts = datetime.fromtimestamp(header[ts_field])
                                break
                        except:
                            pass

        # Skip LNK files without valid timestamp (forensically invalid)
        if event_ts is None:
            logger.debug(f"Skipping LNK file {file_path} without valid timestamp")
            return 0

        # Use the full parsed data as payload and flatten it
        payload = data if isinstance(data, dict) else {"raw_data": data}
        payload = flatten_dict(payload)

        # Add extracted timestamp to payload for reference
        payload["extracted_timestamp"] = event_ts.isoformat()

        event = {
            "event_ts": event_ts,
            "artifact_id": artifact_id,
            "event_type": "lnk_file",
            "payload": json.dumps(payload),
        }

        # Extract target path for logging
        target_path = "unknown"
        if isinstance(payload, dict):
            if "link_info" in payload and isinstance(payload["link_info"], dict):
                target_path = payload["link_info"].get("local_base_path", "unknown")
            elif "string_data" in payload and isinstance(payload["string_data"], dict):
                target_path = payload["string_data"].get("relative_path", "unknown")

        await self._insert_event_batch(db, investigation_id, [event])

        logger.debug(f"Parsed LNK file: {target_path}")
        return 1


def _walk_data(o: Any) -> Any:
    """
    Recursively traverse a nested data structure and replace any `datetime` or `date` instances with their POSIX timestamps.

    Parameters
    ----------
    o : Any
        The object to process. Supported types are:
        * `dict` - each value is recursively processed.
        * `list` - each element is recursively processed.
        * `datetime` or `date` - converted to a float timestamp via `.timestamp()`.
        * any other primitive type - returned unchanged.

    Returns
    -------
    Any
        A new data structure mirroring the input where all datetime-like objects have been replaced by their corresponding timestamps. The original input is not mutated.
    """
    if isinstance(o, dict):
        return {k: _walk_data(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk_data(i) for i in o]
    if isinstance(o, (datetime, date)):
        return o.timestamp()  # type: ignore
    return o


__all__ = ["LnkParser"]
