import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import uuid
import json
import calendar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from regipy.registry import RegistryHive
from regipy.exceptions import RegistryParsingException
from regipy.plugins.system.shimcache import ShimCachePlugin
from regipy.plugins.system.bam import BAMPlugin
from regipy.plugins.amcache.amcache import AmCachePlugin
from regipy.plugins.ntuser.user_assist import UserAssistPlugin
from regipy.plugins.ntuser.shellbags_ntuser import ShellBagNtuserPlugin
from notatin import PyNotatinParser

from .utils import flatten_dict

from app.utils.log_setup import get_logger

logger = get_logger(__name__)

# Suppress verbose regipy logging (but allow WARNING and above)
logging.getLogger("regipy").setLevel(logging.WARNING)
logging.getLogger("regipy.utils").setLevel(logging.WARNING)
logging.getLogger("regipy.registry").setLevel(logging.WARNING)
logging.getLogger("regipy.plugins").setLevel(logging.WARNING)
logging.getLogger("regipy.plugins.system.bam").setLevel(logging.WARNING)
logging.getLogger("regipy.plugins.amcache.amcache").setLevel(logging.WARNING)
logging.getLogger("regipy.plugins.ntuser.shellbags_ntuser").setLevel(logging.WARNING)


async def parse_registry(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    file_path: Path,
) -> int:
    """
    Parse a Windows Registry hive file, extract forensic events, and insert them into the database.

    The function performs three main steps:

    1. Load the hive using :class:`RegistryHive` and run any applicable regipy plugins to obtain specialized
       artifact events.  Plugin events are inserted immediately so they remain separate from generic
       key/value events.
    2. Walk every registry key with :class:`PyNotatinParser`, extract each value’s name, type and data,
       convert the information into a JSON payload, and batch-insert `registry_value` events.
    3. Keep statistics about processed keys/values, skipped entries, and the total number of events
       inserted.

    The insertion is performed in asynchronous batches (default size 2000) to minimise database round-trips.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used for inserting events.
        investigation_id: The UUID identifying the current investigation; it is stored with each event.
        artifact_id: Integer identifier of the source artifact (the registry file) that generated the
            events.
        file_path: Path to the Windows Registry hive on disk.

    Returns:
        int: The total number of events successfully inserted into the database, including both plugin
        and generic registry value events.

    Raises:
        RuntimeError: If the hive cannot be parsed due to a :class:`RegistryParsingException` or any other
        unexpected error.  The original exception is logged with traceback information before being
        re-raised as `RuntimeError`.
    """
    logger.info(f"Parsing registry hive: {file_path}")

    events_inserted = 0
    batch_size = 2000
    event_batch = []

    try:
        reg = RegistryHive(str(file_path))

        # Try to extract specialized forensic artifacts using plugins
        logger.debug(f"Attempting to extract plugin events from {file_path.name}")
        plugin_events = await _extract_plugin_events(reg, file_path, artifact_id)
        plugin_event_count = len(plugin_events)

        # Insert plugin events immediately to keep them separate
        if plugin_events:
            await _insert_event_batch(db, investigation_id, plugin_events)
            events_inserted += plugin_event_count
            logger.debug(f"Inserted {plugin_event_count} plugin events from registry hive")

        # Walk the registry tree (reg_keys() already iterates all keys)
        reg_object = PyNotatinParser(str(file_path))  # type: ignore

        key_count = 0
        value_count = 0
        skipped_invalid_ts = 0
        skipped_exceptions = 0
        for key in reg_object.reg_keys():
            key_count += 1
            try:
                # Build key path
                current_path = key.path

                # Get key timestamp
                try:
                    ts_dt = key.last_key_written_date_and_time
                    key_ts = round(float(calendar.timegm(ts_dt.timetuple())), 3)
                    if key_ts <= 0:
                        # Skip keys with invalid timestamps
                        skipped_invalid_ts += 1
                        continue
                    event_ts = datetime.fromtimestamp(key_ts)
                    last_modified_str = event_ts.isoformat()
                except (AttributeError, TypeError, ValueError) as e:
                    # If timestamp extraction fails, skip this key (forensically invalid)
                    skipped_exceptions += 1
                    logger.debug(
                        f"Skipping registry key {current_path} without valid timestamp: {e}"
                    )
                    continue

                # Process values
                for value in key.values():
                    value_count += 1
                    try:
                        # Get value name and content
                        name = value.pretty_name if value.pretty_name else "(Default)"

                        # Convert value content to string
                        content = value.content
                        if isinstance(content, (str, int, float)):
                            vcontent = str(content)
                        elif isinstance(content, list):
                            vcontent = ", ".join(str(v) for v in content).strip(", ")
                        elif isinstance(content, bytes):
                            vcontent = content.hex()
                        else:
                            vcontent = str(content)

                        # Get data type from pynotatin
                        vtype = (
                            str(value.raw_data_type)
                            if hasattr(value, "raw_data_type")
                            else "unknown"
                        )

                        payload = {
                            "key_path": current_path,
                            "value_name": name,
                            "value_type": vtype,
                            "value_data": vcontent,
                            "last_modified": last_modified_str,
                        }

                        event_batch.append(
                            {
                                "event_ts": event_ts,
                                "artifact_id": artifact_id,
                                "event_type": "registry_value",
                                "payload": json.dumps(payload),
                            }
                        )

                        # Batch insert
                        if len(event_batch) >= batch_size:
                            await _insert_event_batch(db, investigation_id, event_batch)
                            events_inserted += len(event_batch)
                            event_batch = []

                    except Exception as e:
                        logger.warning(f"Failed to parse registry value: {e}")
                        continue

            except Exception as e:
                logger.warning(f"Failed to process registry key: {e}")
                continue

        # Insert remaining events
        if event_batch:
            await _insert_event_batch(db, investigation_id, event_batch)
            events_inserted += len(event_batch)

        logger.info(
            f"Registry parsing complete: {events_inserted} total events ({plugin_event_count} plugin events, {events_inserted - plugin_event_count} registry values)"
        )
        logger.debug(f"Processed {key_count} keys and {value_count} values")
        logger.debug(
            f"Skipped {skipped_invalid_ts} keys with invalid timestamps, {skipped_exceptions} keys with timestamp exceptions"
        )
        return events_inserted

    except RegistryParsingException as e:
        logger.error(f"Failed to parse registry hive {file_path}: {e}", exc_info=True)
        raise RuntimeError(f"Registry parsing failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error parsing registry hive {file_path}: {e}", exc_info=True)
        raise RuntimeError(f"Registry parsing failed: {e}")


async def _extract_plugin_events(
    reg: RegistryHive,
    file_path: Path,
    artifact_id: int,
) -> list[Dict[str, Any]]:
    """
    Extracts forensic events from a Windows Registry hive using a set of regipy plugins.

    The function iterates over a predefined list of plugin classes that target common artifact types (e.g., UserAssist, BAM, AmCache, ShellBag, ShimCache). For each plugin it:

    * Instantiates the plugin with the provided `RegistryHive` object and requests JSON-compatible output.
    * Executes the plugin via its `run` method.
    * Retrieves the parsed entries from the plugin’s `entries` attribute (if present).
    * Logs diagnostic information about the raw data, including a truncated JSON sample when possible.
    * Passes the raw plugin output to `_parse_plugin_data` together with the plugin name and the originating artifact identifier.
      The helper converts the plugin-specific structures into a list of normalized event dictionaries.
    * Accumulates any successfully parsed events in a master list.

    The function is defensive: it catches and logs a variety of expected failure modes (missing optional dependencies, plugins not applicable to the current hive, value errors, or any other unexpected exception) and then proceeds with the next plugin rather than aborting.

    Args:
        reg: An instantiated `RegistryHive` representing the opened registry file.
        file_path: The filesystem path to the hive file being processed.  It is used only for logging/contextual purposes; the function does not read from it directly.
        artifact_id: Integer identifier of the source artifact record in the database, attached to each generated event.

    Returns:
        A list of dictionaries, where each dictionary conforms to the internal event schema (including keys such as `timestamp`, `event_type` set to `registry_<plugin_name>`, and any plugin-specific fields).  The list may be empty if no plugins produced parsable events.
    """
    all_events = []

    # Define plugins to try based on common hive types
    plugins = [
        (UserAssistPlugin, "userassist"),
        (BAMPlugin, "bam"),
        (AmCachePlugin, "amcache"),
        (ShellBagNtuserPlugin, "shellbags_ntuser"),
        (ShimCachePlugin, "shimcache"),
    ]

    for plugin_class, plugin_name in plugins:
        try:
            logger.debug(f"Attempting to run {plugin_name} plugin")
            plugin = plugin_class(reg, as_json=True)

            # Run the plugin (populates internal entries attribute)
            plugin.run()

            # Get the entries from the plugin object
            plugin_data = None
            if hasattr(plugin, "entries"):
                plugin_data = plugin.entries
                logger.debug(
                    f"Plugin {plugin_name} has {len(plugin_data) if plugin_data else 0} entries"
                )
            else:
                logger.debug(f"Plugin {plugin_name} has no 'entries' attribute")

            if plugin_data and len(plugin_data) > 0:
                # Log raw plugin output for debugging
                logger.debug(f"Plugin {plugin_name} returned data type: {type(plugin_data)}")
                if isinstance(plugin_data, (dict, list)):
                    data_sample = json.dumps(plugin_data, default=str)[:500]
                    logger.debug(f"Plugin {plugin_name} data sample: {data_sample}")
                else:
                    logger.debug(f"Plugin {plugin_name} data: {str(plugin_data)[:500]}")

                # Parse plugin output
                plugin_events = _parse_plugin_data(plugin_data, plugin_name, artifact_id)
                if plugin_events:
                    all_events.extend(plugin_events)
                    logger.info(
                        f"{plugin_name}: extracted {len(plugin_events)} events (event_type: registry_{plugin_name})"
                    )
                else:
                    logger.debug(
                        f"Plugin {plugin_name} returned data but no events were parsed. Data type: {type(plugin_data)}"
                    )
            else:
                logger.debug(f"Plugin {plugin_name} returned no data (None or empty)")

        except ModuleNotFoundError as e:
            # Missing optional dependency (e.g., pyfwsi for shellbags)
            logger.debug(f"Plugin {plugin_name} requires additional dependencies: {e}")
            continue
        except (KeyError, AttributeError) as e:
            # Plugin not applicable to this hive type (expected)
            logger.debug(
                f"Plugin {plugin_name} not applicable to this hive: {type(e).__name__}: {e}"
            )
            continue
        except ValueError as e:
            # Value errors might indicate parsing issues
            logger.debug(f"Plugin {plugin_name} encountered ValueError: {e}")
            continue
        except Exception as e:
            # Unexpected error - log but continue
            logger.debug(
                f"Plugin {plugin_name} failed unexpectedly ({type(e).__name__}): {e}", exc_info=True
            )
            continue

    return all_events


def _parse_plugin_data(
    plugin_data: Any,
    plugin_name: str,
    artifact_id: int,
) -> list[Dict[str, Any]]:
    """
    Parse raw plugin output into a list of normalized event dictionaries.

    This helper converts the heterogeneous data structures returned by regipy plugins
    into a uniform representation suitable for bulk insertion into the events table.
    It accepts JSON strings, dictionaries, or lists and extracts a timestamp from each
    record using a set of common field names.  Entries without a parsable timestamp are
    ignored because they cannot be reliably correlated in a forensic timeline.

    The resulting event dictionaries contain:
    * `event_ts` - a :class:`datetime.datetime` object representing the event time.
    * `artifact_id` - the integer identifier of the source artifact.
    * `event_type` - a string prefixed with `registry_` followed by the plugin name.
    * `payload` - a JSON-encoded string of the flattened original entry, enriched with
      the plugin name.

    If an unexpected data type is encountered or parsing fails, a warning is logged and
    the function returns an empty list.  Any other exception is caught, logged as an error,
    and results in an empty list being returned.

    Args:
        plugin_data: The raw output from a regipy plugin. May be a JSON-encoded string,
            a dictionary, or a list of dictionaries.
        plugin_name: The name of the plugin that produced `plugin_data`; used for
            logging and to build the `event_type` field.
        artifact_id: Integer identifier linking the generated events to their originating
            forensic artifact.

    Returns:
        A list of dictionaries, each representing a single event ready for database insertion.
        If no valid entries are found or an error occurs, the list will be empty.
    """
    events = []

    try:
        # Parse JSON string if needed
        if isinstance(plugin_data, str):
            try:
                plugin_data = json.loads(plugin_data)
            except json.JSONDecodeError:
                logger.warning(
                    f"Plugin {plugin_name} returned non-JSON string: {plugin_data[:200]}"
                )
                return events

        # Handle different plugin output formats
        entries = []
        if isinstance(plugin_data, dict):
            # Check for common wrapper keys
            if "entries" in plugin_data:
                entries = plugin_data["entries"]
            elif "results" in plugin_data:
                entries = plugin_data["results"]
            elif "items" in plugin_data:
                entries = plugin_data["items"]
            else:
                # Treat the dict itself as a single entry
                entries = [plugin_data]
        elif isinstance(plugin_data, list):
            entries = plugin_data
        else:
            logger.warning(f"Plugin {plugin_name} returned unexpected type: {type(plugin_data)}")
            return events

        if not entries:
            logger.debug(f"Plugin {plugin_name} returned empty entries list")
            return events

        logger.debug(f"Plugin {plugin_name} processing {len(entries)} entries")

        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                logger.debug(f"Plugin {plugin_name} entry {idx} is not a dict: {type(entry)}")
                continue

            # Extract timestamp (try multiple common field names)
            event_ts = None
            ts_fields = [
                "timestamp",
                "last_execution",
                "last_write",
                "modified_time",
                "last_modified",
                "execution_time",
                "last_execution_time",
                "last_run",
                "run_time",
                "write_time",
            ]

            for ts_field in ts_fields:
                if ts_field in entry:
                    try:
                        ts_value = entry[ts_field]
                        if isinstance(ts_value, str):
                            # Handle ISO format with or without timezone
                            ts_value = ts_value.replace("Z", "+00:00")
                            event_ts = datetime.fromisoformat(ts_value)
                        elif isinstance(ts_value, datetime):
                            event_ts = ts_value
                        elif isinstance(ts_value, (int, float)):
                            # Handle both seconds and milliseconds
                            if ts_value > 1e12:  # Likely milliseconds
                                event_ts = datetime.fromtimestamp(ts_value / 1000.0)
                            else:
                                event_ts = datetime.fromtimestamp(ts_value)

                        if event_ts:
                            break
                    except (ValueError, TypeError, AttributeError, OSError) as e:
                        continue

            if not event_ts:
                # Skip events without valid timestamp (forensically invalid)
                logger.debug(f"Skipping {plugin_name} plugin entry without valid timestamp")
                continue

            # Create event payload
            payload = {"plugin": plugin_name, **entry}

            # Flatten the payload to enable better JSONB queries
            payload = flatten_dict(payload)

            events.append(
                {
                    "event_ts": event_ts,
                    "artifact_id": artifact_id,
                    "event_type": f"registry_{plugin_name}",
                    "payload": json.dumps(payload, default=str),
                }
            )

    except Exception as e:
        logger.error(f"Failed to parse {plugin_name} plugin data: {e}", exc_info=True)

    logger.debug(f"Plugin {plugin_name} parsed {len(events)} events")
    return events


async def _insert_event_batch(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    events: list[Dict[str, Any]],
):
    """
    Insert a batch of event records into the unified `events` table.

    This coroutine adds the provided `investigation_id` to each event dictionary,
    then performs a bulk insert using a raw SQL statement that casts the `payload`
    field to JSONB for efficient storage.  The operation is committed on success
    or rolled back and re-raised on failure.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute
            the insert and manage the transaction.
        investigation_id: The UUID of the investigation to which all events belong;
            this value is injected into each event dictionary under the key
            `investigation_id`.
        events: A list of dictionaries, each representing a single event with at
            least the keys `event_ts`, `artifact_id`, `event_type` and
            `payload`.  The function mutates these dictionaries by adding the
            `investigation_id`.

    Returns:
        None.

    Raises:
        Exception: Propagates any exception raised during execution after logging
        an error message, rolling back the transaction, and re-raising the original
        exception.
    """
    if not events:
        return

    # Add investigation_id to each event
    for event in events:
        event["investigation_id"] = investigation_id

    try:
        # Use core insert for better performance with JSONB casting
        insert_query = text(
            """
            INSERT INTO events (investigation_id, event_ts, artifact_id, event_type, payload)
            VALUES (:investigation_id, :event_ts, :artifact_id, :event_type, CAST(:payload AS jsonb))
        """
        )
        await db.execute(insert_query, events)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to insert event batch of {len(events)} events: {e}", exc_info=True)
        logger.error(f"First event sample: {events[0] if events else 'N/A'}")
        await db.rollback()
        raise


__all__ = ["parse_registry"]
