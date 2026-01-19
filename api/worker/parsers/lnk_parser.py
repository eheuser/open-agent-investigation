from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import LnkParse3

from .utils import flatten_dict

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


async def parse_lnk(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    file_path: Path,
) -> int:
    """
    Parse a Windows LNK (shortcut) file, extract its metadata, and insert a single forensic event record into the database.

    Args:
        db: An active `AsyncSession` used to execute the INSERT operation.
        investigation_id: The UUID of the investigation that owns the new event.
        artifact_id: Identifier of the source artifact from which the LNK file originated.
        file_path: Path object pointing to the `.lnk` file on disk.

    Returns:
        int: The number of events successfully inserted (always 0 or 1). A return value
        of `0` indicates that the file was skipped because it lacked a valid forensic
        timestamp; `1` means an event was created and stored.

    Raises:
        RuntimeError: If any unexpected error occurs while reading, parsing, or inserting
        the LNK data. The original exception is included in the message for debugging.

    Notes:
        * The function uses :pymod:`LnkParse3` to read the binary file and obtain a JSON-serialisable
          representation of its contents.
        * All datetime objects found in the parsed structure are converted to Unix timestamps by
          `_walk_data` before further processing.
        * A forensic timestamp is selected from the LNK header fields (`write_time`, `access_time`,
          or `creation_time`) in that order. If none of these fields contain a valid numeric value,
          the file is considered forensically invalid and no event is created.
        * The parsed data dictionary is flattened with :func:`flatten_dict` so that nested keys become
          top-level entries, simplifying storage and querying.
        * An `extracted_timestamp` field (ISO-8601 string) is added to the payload for reference,
          alongside the original timestamp stored in the `event_ts` column of the event record.
    """
    logger.info(f"Parsing LNK file: {file_path}")

    try:
        with open(file_path, "rb") as f:
            lnk = LnkParse3.lnk_file(f)
            data = lnk.get_json()

        # Convert datetime objects to timestamps
        data = _walk_data(data)

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
            logger.warning(f"Skipping LNK file {file_path} without valid timestamp")
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

        await _insert_event_batch(db, investigation_id, [event])

        logger.info(f"Parsed LNK file: {target_path}")
        return 1

    except Exception as e:
        logger.error(f"Failed to parse LNK file {file_path}: {e}", exc_info=True)
        raise RuntimeError(f"LNK parsing failed: {e}")


async def _insert_event_batch(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    events: list[Dict[str, Any]],
):
    """
    Insert a batch of forensic events into the unified `events` table.

    This coroutine adds the provided `investigation_id` to each event dictionary,
    constructs an INSERT statement using SQLAlchemy's :func:`text` construct, and
    executes it asynchronously via the given database session.  If the insertion
    fails, the transaction is rolled back and the original exception is re-raised
    after logging an error.

    Parameters
    ----------
    db: AsyncSession
        An active asynchronous SQLAlchemy session used to execute the INSERT query.
    investigation_id: uuid.UUID
        The identifier of the investigation to which all events belong.  This value
        will be added to each event dictionary under the key `investigation_id`.
    events: list[Dict[str, Any]]
        A list of dictionaries representing individual events.  Each dictionary must
        contain the keys `event_ts`, `artifact_id`, `event_type`, and
        `payload`; the function will augment each with `investigation_id`.

    Raises
    ------
    Exception
        Propagates any exception raised during query execution after logging an
        error message and rolling back the transaction.
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


__all__ = ["parse_lnk"]
