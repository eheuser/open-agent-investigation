from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from mft.mft import PyMftParser

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


def _parse_timestamp(ts_value) -> datetime | None:
    """
    Parse a timestamp value into a :class:`datetime.datetime` object.

    The function accepts timestamps in several common representations and normalises them to a UTC
    :class:`datetime.datetime`. If the input is falsy or cannot be interpreted, `None` is returned.

    Parameters
    ----------
    ts_value : Any
        The timestamp to convert. Supported types are:

        * `datetime` - returned unchanged.
        * `int` or `float` - treated as a Unix epoch seconds value; `0` or `0.0` yields `None`.
        * `str` - interpreted as an ISO-8601 string; a trailing `'Z'` is converted to `+00:00`.

    Returns
    -------
    datetime.datetime | None
        A timezone-naïve UTC datetime object representing the input timestamp, or `None` if the
        value is empty, zero, or cannot be parsed.
    """
    if not ts_value:
        return None

    try:
        # Already a datetime object
        if isinstance(ts_value, datetime):
            return ts_value

        # Unix timestamp (float or int)
        if isinstance(ts_value, (float, int)):
            if ts_value == 0.0 or ts_value == 0:
                return None
            return datetime.utcfromtimestamp(ts_value)

        # ISO format string
        if isinstance(ts_value, str):
            return datetime.fromisoformat(ts_value.replace("Z", "+00:00"))

    except Exception as e:
        logger.debug(f"Failed to parse timestamp {ts_value}: {e}")
        return None

    return None


async def parse_mft(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    file_path: Path,
) -> int:
    """
    Parse an NTFS Master File Table (MFT) file and insert forensic events into the database.

    This function uses **PyMftParser** to iterate over MFT entries, extracts relevant timestamps and metadata from the StandardInformation and FileName attributes, builds a JSON payload for each valid record, and batch-inserts the events into the provided asynchronous SQLAlchemy session.  Entries that lack any usable timestamp or raise parsing errors are skipped and counted.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute INSERT statements.
        investigation_id: The UUID of the investigation to which the events belong.
        artifact_id: Identifier of the source artifact (e.g., the file representing the MFT) within the investigation.
        file_path: Path object pointing to the MFT file on disk.

    Returns:
        int: The total number of events successfully inserted into the database.

    Raises:
        RuntimeError: If a fatal error occurs while opening or processing the MFT file, the original exception is wrapped in a `RuntimeError` with an explanatory message.

    Notes:
    * The implementation processes entries in batches (default size 2000) to reduce transaction overhead.
    * Only entries that provide at least one of the following timestamps are considered valid: FileName created, StandardInformation created, FileName modified, or StandardInformation modified.
    * Timestamps are converted to ISO-8601 strings; missing values are stored as `null` in the JSON payload.
    * Errors encountered while parsing individual entries are logged and ignored, allowing processing to continue for remaining records.
    """
    logger.info(f"Parsing MFT file: {file_path}")

    try:
        events_inserted = 0
        batch_size = 2000
        event_batch = []
        record_count = 0

        # Parse MFT using PyMftParser
        parser = PyMftParser(str(file_path))

        skipped_errors = 0
        skipped_no_timestamp = 0

        for entry_or_error in parser.entries():
            # Skip errors
            if isinstance(entry_or_error, RuntimeError):
                skipped_errors += 1
                del entry_or_error
                continue

            try:
                # entry_or_error is a PyMftEntry object, not JSON
                entry = entry_or_error

                # Initialize timestamp variables
                si_m = None  # StandardInformation Modified
                si_a = None  # StandardInformation Accessed
                si_c = None  # StandardInformation Created
                si_e = None  # StandardInformation MFT Modified
                fn_m = None  # FileName Modified
                fn_a = None  # FileName Accessed
                fn_c = None  # FileName Created
                fn_e = None  # FileName MFT Modified
                fn_logical_size = None
                fn_physical_size = None
                si_owner_id = None

                # Extract attributes from entry
                # PyMftParser returns entry as dict-like or has 'attributes' property/method
                attributes: list = []
                try:
                    if hasattr(entry, "attributes"):
                        # Check if it's a method or property
                        attr = getattr(entry, "attributes")
                        if callable(attr):
                            result = attr()
                            # Ensure result is iterable
                            try:
                                attributes = list(result)  # type: ignore
                            except TypeError:
                                logger.debug(f"attributes() returned non-iterable: {type(result)}")
                        else:
                            # Try to iterate the attribute directly
                            try:
                                attributes = list(attr)  # type: ignore
                            except TypeError:
                                logger.debug(f"attributes is not iterable: {type(attr)}")
                    elif isinstance(entry, dict) and "attributes" in entry:
                        attr_val = entry["attributes"]
                        if isinstance(attr_val, list):
                            attributes = attr_val
                        else:
                            try:
                                attributes = list(attr_val)  # type: ignore
                            except TypeError:
                                logger.debug(f"dict attributes not iterable: {type(attr_val)}")
                except Exception as e:
                    logger.debug(f"Failed to extract attributes from entry: {e}")
                    # Try alternative approaches
                    if hasattr(entry, "__dict__"):
                        logger.debug(
                            f"Entry has __dict__ with keys: {list(entry.__dict__.keys())[:10]}"
                        )
                    continue

                # Skip if no attributes found
                if not attributes:
                    continue

                # Parse StandardInformation and FileName attributes
                for attribute in attributes:
                    attr_header = (
                        attribute.get("header", {})
                        if isinstance(attribute, dict)
                        else getattr(attribute, "header", {})
                    )
                    attr_data = (
                        attribute.get("data", {})
                        if isinstance(attribute, dict)
                        else getattr(attribute, "data", {})
                    )

                    type_code = (
                        attr_header.get("type_code")
                        if isinstance(attr_header, dict)
                        else getattr(attr_header, "type_code", None)
                    )

                    if type_code == "StandardInformation":
                        si_owner_id = (
                            attr_data.get("owner_id")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "owner_id", None)
                        )
                        si_m = _parse_timestamp(
                            attr_data.get("modified")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "modified", None)
                        )
                        si_a = _parse_timestamp(
                            attr_data.get("accessed")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "accessed", None)
                        )
                        si_c = _parse_timestamp(
                            attr_data.get("created")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "created", None)
                        )
                        si_e = _parse_timestamp(
                            attr_data.get("mft_modified")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "mft_modified", None)
                        )
                    elif type_code == "FileName":
                        fn_logical_size = (
                            attr_data.get("logical_size")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "logical_size", None)
                        )
                        fn_physical_size = (
                            attr_data.get("physical_size")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "physical_size", None)
                        )
                        fn_m = _parse_timestamp(
                            attr_data.get("modified")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "modified", None)
                        )
                        fn_a = _parse_timestamp(
                            attr_data.get("accessed")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "accessed", None)
                        )
                        fn_c = _parse_timestamp(
                            attr_data.get("created")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "created", None)
                        )
                        fn_e = _parse_timestamp(
                            attr_data.get("mft_modified")
                            if isinstance(attr_data, dict)
                            else getattr(attr_data, "mft_modified", None)
                        )

                # Use FileName created time as primary event timestamp (forensically valid)
                # Fall back to StandardInformation created if FileName not available
                # Skip entries without any valid timestamp
                event_ts = fn_c or si_c or fn_m or si_m
                if not event_ts:
                    skipped_no_timestamp += 1
                    continue

                # Build forensically valid payload with all MFT timestamps
                payload = {
                    "record_number": (
                        getattr(entry, "record_number", None)
                        if hasattr(entry, "record_number")
                        else entry.get("record_number")
                    ),
                    "file_name": (
                        getattr(entry, "file_name", None) or getattr(entry, "filename", None)
                        if hasattr(entry, "file_name")
                        else entry.get("file_name") or entry.get("filename")
                    ),
                    "full_path": (
                        getattr(entry, "full_path", None) or getattr(entry, "path", None)
                        if hasattr(entry, "full_path")
                        else entry.get("full_path") or entry.get("path")
                    ),
                    "is_directory": (
                        getattr(entry, "is_directory", None) or getattr(entry, "is_dir", None)
                        if hasattr(entry, "is_directory")
                        else entry.get("is_directory") or entry.get("is_dir")
                    ),
                    # StandardInformation timestamps
                    "si_modified": si_m.isoformat() if si_m else None,
                    "si_accessed": si_a.isoformat() if si_a else None,
                    "si_created": si_c.isoformat() if si_c else None,
                    "si_mft_modified": si_e.isoformat() if si_e else None,
                    "si_owner_id": si_owner_id,
                    # FileName timestamps
                    "fn_modified": fn_m.isoformat() if fn_m else None,
                    "fn_accessed": fn_a.isoformat() if fn_a else None,
                    "fn_created": fn_c.isoformat() if fn_c else None,
                    "fn_mft_modified": fn_e.isoformat() if fn_e else None,
                    "fn_logical_size": fn_logical_size,
                    "fn_physical_size": fn_physical_size,
                }

                event_batch.append(
                    {
                        "event_ts": event_ts,
                        "artifact_id": artifact_id,
                        "event_type": "mft_entry",
                        "payload": json.dumps(payload),
                    }
                )

                # Batch insert
                if len(event_batch) >= batch_size:
                    await _insert_event_batch(db, investigation_id, event_batch)
                    events_inserted += len(event_batch)
                    event_batch = []

                record_count += 1

            except Exception as e:
                logger.warning(f"Failed to parse MFT entry: {e}")
                continue

        # Insert remaining events
        if event_batch:
            await _insert_event_batch(db, investigation_id, event_batch)
            events_inserted += len(event_batch)

        logger.info(
            f"Parsed {events_inserted} MFT records (skipped {skipped_errors} errors, {skipped_no_timestamp} entries without timestamps)"
        )
        return events_inserted

    except Exception as e:
        logger.error(f"Failed to parse MFT file {file_path}: {e}", exc_info=True)
        raise RuntimeError(f"MFT parsing failed: {e}")


async def _insert_event_batch(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    events: list[Dict[str, Any]],
):
    """
    Insert a batch of forensic events into the unified `events` table.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used to execute the insert statement.
    investigation_id : uuid.UUID
        The identifier of the investigation to which all supplied events belong; this value is added to each event before insertion.
    events : list[Dict[str, Any]]
        A collection of dictionaries representing individual events. Each dictionary must contain at least the keys `event_ts`, `artifact_id`, `event_type` and `payload`. The function augments every dictionary with the provided `investigation_id`.

    Raises
    ------
    Exception
        Propagates any exception raised during execution of the INSERT statement after logging the error and rolling back the transaction.

    Notes
    -----
    * If `events` is empty, the function returns immediately without performing any database operation.
    * The `payload` field is cast to PostgreSQL `jsonb`; callers should ensure that the value is JSON-serializable.
    * On successful execution the transaction is committed; on failure it is rolled back and the original exception is re-raised.
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
        logger.error(f"Failed to insert event batch of {len(events):,} events: {e}", exc_info=True)
        await db.rollback()
        raise


__all__ = ["parse_mft"]
