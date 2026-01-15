import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import struct

logger = logging.getLogger(__name__)


async def parse_prefetch(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    file_path: Path,
) -> int:
    """
    Parse a Windows Prefetch file and insert a corresponding execution event into the database.

    This function performs a minimal, self-contained parsing of a `*.pf` file to extract the
    executable name and the most recent execution timestamp stored in the prefetch
    structure.  The extracted information is packaged as a JSON payload and inserted
    as a single event record using an asynchronous batch insert helper.

    The implementation deliberately avoids external dependencies; for forensic-grade
    accuracy a dedicated library such as `libscca-python` or `prefetch2es` should be
    used instead.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute the
            insertion query.
        investigation_id: The UUID of the investigation to which the event belongs.
        artifact_id: Identifier of the source artifact (e.g., the file record) within
            the investigation.
        file_path: Path object pointing to the prefetch file on disk.

    Returns:
        int: The number of events successfully inserted (`1` on success, `0` if the
        file could not be parsed or lacked a valid timestamp).

    Raises:
        RuntimeError: If an unexpected error occurs during parsing or database insertion,
        wrapping the original exception for higher-level handling.
    """
    logger.info(f"Parsing prefetch file: {file_path}")

    try:
        # Basic prefetch parsing (simplified - full implementation would use prefetch2es or libscca)
        # For now, we'll do a basic parse to extract executable name and timestamps

        with open(file_path, "rb") as f:
            data = f.read()

        # Prefetch files have a specific header
        if len(data) < 84:
            logger.warning(f"Prefetch file too small: {file_path}")
            return 0

        # Extract executable name (Unicode string at offset 16)
        # This is a simplified version - full parsing would use proper library
        try:
            exe_name_offset = 16
            exe_name_bytes = data[exe_name_offset : exe_name_offset + 60]
            exe_name = exe_name_bytes.decode("utf-16-le").split("\x00")[0]
        except Exception as e:
            logger.warning(f"Failed to extract executable name: {e}")
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
            logger.warning(
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

        await _insert_event_batch(db, investigation_id, [event])

        logger.info(f"Parsed prefetch file for executable: {exe_name}")
        return 1

    except Exception as e:
        logger.error(f"Failed to parse prefetch file {file_path}: {e}", exc_info=True)
        raise RuntimeError(f"Prefetch parsing failed: {e}")


async def _insert_event_batch(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    events: list[Dict[str, Any]],
):
    """
    Batch inserts a list of event dictionaries into the unified `events` table within an asynchronous database session.

    Parameters
    ----------
    db : AsyncSession
        The active SQLAlchemy asynchronous session used to execute the insert statement.
    investigation_id : uuid.UUID
        Identifier of the investigation to which all events belong; this value is added to each event payload before insertion.
    events : list[dict[str, Any]]
        A collection of event mappings. Each mapping must contain the keys `event_ts`, `artifact_id`,
        `event_type` and `payload` (JSON-serializable). The function augments each dictionary with an
        `investigation_id` entry set to the provided `investigation_id`.

    Raises
    ------
    Exception
        Propagates any exception raised during execution of the INSERT statement after logging the error and rolling back the transaction.

    Notes
    -----
    - If `events` is empty, the function returns immediately without performing a database operation.
    - The `payload` field is cast to PostgreSQL `jsonb`; callers must ensure that the value is JSON-serializable.
    """
    if not events:
        return

    # Add investigation_id to each event
    for event in events:
        event["investigation_id"] = investigation_id

    # Use unified events table
    insert_query = text(
        """
        INSERT INTO events (investigation_id, event_ts, artifact_id, event_type, payload)
        VALUES (:investigation_id, :event_ts, :artifact_id, :event_type, CAST(:payload AS jsonb))
    """
    )

    try:
        await db.execute(insert_query, events)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to insert event batch of {len(events)} events: {e}", exc_info=True)
        await db.rollback()
        raise


__all__ = ["parse_prefetch"]
