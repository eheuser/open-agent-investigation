import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from evtx import PyEvtxParser  # type: ignore

from .utils import flatten_dict

logger = logging.getLogger(__name__)


def _normalize_channel_name(channel: str) -> str:
    """
    Normalize a Windows Event Log channel name to a short identifier.

    Args:
        channel: The full channel name as found in an EVTX record (e.g., `"Microsoft-Windows-Sysmon/Operational"`).

    Returns:
        A normalized, lowercase short name representing the channel (e.g., `"sysmon"`). If the channel is not recognized, a best-effort identifier is derived by stripping common prefixes/suffixes and converting to snake_case; if this process yields an empty string, `"unknown"` is returned.
    """
    # Map of common Windows Event Log channels to short names
    channel_map = {
        # Core Windows Logs
        "Security": "security",
        "System": "system",
        "Application": "application",
        "Setup": "setup",
        # Sysmon
        "Microsoft-Windows-Sysmon/Operational": "sysmon",
        # PowerShell
        "Microsoft-Windows-PowerShell/Operational": "powershell",
        "Windows PowerShell": "powershell",
        "Microsoft-Windows-PowerShell/Admin": "powershell_admin",
        "Microsoft-Windows-PowerShell-DesiredStateConfiguration-FileDownloadManager/Operational": "powershell_dsc",
        # Windows Defender
        "Microsoft-Windows-Windows Defender/Operational": "defender",
        "Microsoft-Windows-Windows Defender/WHC": "defender_whc",
        # Task Scheduler
        "Microsoft-Windows-TaskScheduler/Operational": "taskscheduler",
        # Terminal Services / RDP
        "Microsoft-Windows-TerminalServices-LocalSessionManager/Operational": "rdp_local",
        "Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational": "rdp_remote",
        "Microsoft-Windows-RemoteDesktopServices-RdpCoreTS/Operational": "rdp_core",
        # WMI
        "Microsoft-Windows-WMI-Activity/Operational": "wmi",
        # Windows Firewall
        "Microsoft-Windows-Windows Firewall With Advanced Security/Firewall": "firewall",
        # DNS
        "DNS Server": "dns",
        "Microsoft-Windows-DNS-Client/Operational": "dns_client",
        # NTLM
        "Microsoft-Windows-NTLM/Operational": "ntlm",
        # Kerberos
        "Microsoft-Windows-Security-Kerberos/Operational": "kerberos",
        # SMB
        "Microsoft-Windows-SmbClient/Security": "smb_client",
        "Microsoft-Windows-SMBServer/Security": "smb_server",
        "Microsoft-Windows-SMBClient/Operational": "smb_client_ops",
        "Microsoft-Windows-SMBServer/Operational": "smb_server_ops",
        # Bits Client
        "Microsoft-Windows-Bits-Client/Operational": "bits",
        # AppLocker
        "Microsoft-Windows-AppLocker/EXE and DLL": "applocker_exe",
        "Microsoft-Windows-AppLocker/MSI and Script": "applocker_script",
        "Microsoft-Windows-AppLocker/Packaged app-Deployment": "applocker_appx",
        "Microsoft-Windows-AppLocker/Packaged app-Execution": "applocker_appx_exec",
        # Code Integrity
        "Microsoft-Windows-CodeIntegrity/Operational": "codeintegrity",
        # Windows Update
        "Microsoft-Windows-WindowsUpdateClient/Operational": "windowsupdate",
        # User Account Management
        "Microsoft-Windows-User Profile Service/Operational": "userprofile",
        # Print Service
        "Microsoft-Windows-PrintService/Operational": "printservice",
        "Microsoft-Windows-PrintService/Admin": "printservice_admin",
        # DHCP
        "Microsoft-Windows-Dhcp-Client/Operational": "dhcp_client",
        "Microsoft-Windows-DHCP-Server/Operational": "dhcp_server",
        # Driver Framework
        "Microsoft-Windows-DriverFrameworks-UserMode/Operational": "driver_usermode",
        # Kernel
        "Microsoft-Windows-Kernel-PnP/Configuration": "kernel_pnp",
        "Microsoft-Windows-Kernel-Boot/Operational": "kernel_boot",
        # LSA/Authentication
        "Microsoft-Windows-LSA/Operational": "lsa",
        # NTFS
        "Microsoft-Windows-Ntfs/Operational": "ntfs",
        # Storage/Disk
        "Microsoft-Windows-Storage-Storport/Operational": "storage",
        "Microsoft-Windows-Partition/Diagnostic": "partition",
        # Diagnosis/Troubleshooting
        "Microsoft-Windows-Diagnosis-Scripted/Operational": "diagnosis",
        # Application Experience
        "Microsoft-Windows-Application-Experience/Program-Inventory": "appexperience_inventory",
        "Microsoft-Windows-Application-Experience/Program-Telemetry": "appexperience_telemetry",
        # WinRM/WinRS
        "Microsoft-Windows-WinRM/Operational": "winrm",
        "Microsoft-Windows-Windows Remote Management/Operational": "winrm",
        # Hyper-V
        "Microsoft-Windows-Hyper-V-Worker": "hyperv_worker",
        "Microsoft-Windows-Hyper-V-VMMS-Admin": "hyperv_vmms",
        # WLAN
        "Microsoft-Windows-WLAN-AutoConfig/Operational": "wlan",
        # VPN
        "Microsoft-Windows-NetworkProfile/Operational": "network_profile",
        # Service Control Manager
        "System": "system",  # SCM events are in System log
    }

    # Check exact match first
    if channel in channel_map:
        return channel_map[channel]

    # Try case-insensitive match
    channel_lower = channel.lower()
    for key, value in channel_map.items():
        if key.lower() == channel_lower:
            return value

    # Fallback: extract meaningful part from channel name
    # Remove common prefixes and suffixes
    normalized = channel.lower()
    normalized = normalized.replace("microsoft-windows-", "")
    normalized = normalized.replace("/operational", "")
    normalized = normalized.replace("/admin", "")
    normalized = normalized.replace("/analytic", "")
    normalized = normalized.replace("/debug", "")
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("-", "_")
    normalized = normalized.replace("/", "_")

    # Remove duplicate underscores and strip
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    normalized = normalized.strip("_")

    return normalized if normalized else "unknown"


def _extract_channel(data: Dict[str, Any]) -> Optional[str]:
    """
    Extracts the channel name from a parsed EVTX event dictionary.

    Args:
        data: A dictionary representing the parsed EVTX event structure.

    Returns:
        The channel name as a string if present; otherwise, `None`.
    """
    try:
        return data["Event"]["System"]["Channel"]
    except (KeyError, TypeError):
        return None


def _extract_event_id(data: Dict[str, Any]) -> Optional[int]:
    """
    Extracts the event identifier from a parsed EVTX data structure.

    Args:
        data (Dict[str, Any]): The dictionary representing a single EVTX record as produced by the parser. It must contain an `"Event"` key with a nested `"System"` mapping that includes an `"EventID"` entry.

    Returns:
        Optional[int]: The numeric event ID if it can be located and converted to an integer; otherwise `None` when the field is missing, malformed, or any error occurs during extraction.
    """
    try:
        event_id_field = data["Event"]["System"]["EventID"]

        if isinstance(event_id_field, (int, str)):
            return int(event_id_field)
        elif isinstance(event_id_field, dict):
            # Handle {"#text": "4624"} format
            return int(event_id_field["#text"])
    except Exception as e:
        logger.warning(f"Failed to extract event ID: {e}")
        return None


def _extract_timestamp(record: Dict[str, Any], data: Dict[str, Any]) -> datetime | None:
    """
    Extracts a datetime object from an EVTX record.

    Args:
        record: A dictionary representing the raw EVTX record; may contain a `timestamp` or `EventTime` key.
        data:   The parsed event payload as a nested dictionary, typically containing `Event → System → TimeCreated → #attributes → SystemTime`.

    Returns:
        A :class:`datetime.datetime` instance if a valid timestamp string is found and successfully parsed, otherwise `None`. The function attempts to parse ISO-8601 strings with optional microseconds (e.g., `2023-03-24T12:38:23.153533Z`) and fallback formats such as `2023-03-24 12:38:23.153569 UTC`. If parsing fails, a warning is logged and `None` is returned.
    """
    # Try multiple timestamp sources in order of preference
    ts_str = None

    # 1. Try SystemTime from TimeCreated (most reliable)
    try:
        ts_str = data["Event"]["System"]["TimeCreated"]["#attributes"]["SystemTime"]
    except (KeyError, TypeError):
        pass

    # 2. Try timestamp field from record
    if not ts_str and "timestamp" in record:
        ts_str = record["timestamp"]

    # 3. Try EventTime field from record
    if not ts_str and "EventTime" in record:
        ts_str = record["EventTime"]

    if ts_str:
        try:
            # Remove 'Z' suffix and parse as ISO format
            # Handle formats like: "2023-03-24T12:38:23.153533Z"
            ts_clean = ts_str.replace("Z", "").replace("z", "")

            # Try with microseconds
            try:
                return datetime.strptime(ts_clean, "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                # Try without microseconds
                return datetime.strptime(ts_clean, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            # Try parsing '2023-03-24 12:38:23.153569 UTC' format
            try:
                ts_str_clean = ts_str.replace(" UTC", "").replace(" utc", "")
                return datetime.strptime(ts_str_clean, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                try:
                    return datetime.strptime(ts_str_clean, "%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.warning(f"Failed to parse timestamp '{ts_str}': {e}")

    # No valid timestamp found - this is a critical error for forensic validity
    # Return None to allow caller to skip invalid events
    logger.warning(f"No valid timestamp found in EVTX record - event will be skipped")
    return None


def _build_event_type(channel: Optional[str], event_id: int) -> str:
    """
    Build a standardized event type identifier.

    Parameters
    ----------
    channel : Optional[str]
        The name of the Windows Event Log channel associated with the event.
    event_id : int
        The numeric identifier of the event within the channel.

    Returns
    -------
    str
        A string in the form `"evtx_<normalized_channel>_<event_id>"` when a channel is provided, or `"evtx_<event_id>"` when the channel is `None`. The channel name is normalized by :func:`_normalize_channel_name`.
    """
    if channel:
        normalized_channel = _normalize_channel_name(channel)
        return f"evtx_{normalized_channel}_{event_id}"
    else:
        # Fallback if channel is not available
        return f"evtx_{event_id}"


def _flatten_event_data(event_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Flatten EventData fields by collapsing single-key dictionaries into their scalar values.

    Args:
        event_data (Optional[Dict[str, Any]]):
            The raw EventData dictionary obtained from a parsed EVTX record. May be `None` or contain nested dictionaries where each has only one key (e.g., `{"#text": "value"}`).

    Returns:
        Dict[str, Any]:
            A new dictionary with the same top-level keys as *event_data*. For entries whose value is a single-key dict, the function replaces the dict with its sole value; all other values are copied unchanged. If *event_data* is `None`, an empty dictionary is returned.

    Notes:
        This helper normalizes the structure of EventData payloads so that downstream processing can treat fields uniformly without needing to handle the special single-key dict case.
    """
    if event_data is None:
        return {}

    flattened = {}
    for key, value in event_data.items():
        if isinstance(value, dict) and len(value) == 1:
            # Flatten single-key dicts like {"#text": "value"}
            flattened[key] = value.get(list(value.keys())[0], None)
        else:
            flattened[key] = value

    return flattened


async def parse_evtx(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    file_path: Path,
) -> int:
    """
    Parse a Windows EVTX file and insert its events into the database.

    This function reads the specified EVTX file using :class:`PyEvtxParser`, extracts relevant
    information from each record (event ID, channel, timestamp, and payload data), normalises
    the payload structure, builds a canonical event type string, and inserts the events in
    batches.  It returns the total number of events successfully inserted.

    Args:
        db: An active :class:`AsyncSession` used for database operations.
        investigation_id: The UUID identifying the current investigation; this value is stored
            with each inserted event to maintain provenance.
        artifact_id: The integer identifier of the source artifact (e.g., the file record) from
            which the EVTX data originates.
        file_path: A :class:`pathlib.Path` pointing to the EVTX file to be processed.

    Returns:
        int: The number of events that were inserted into the database.

    Raises:
        RuntimeError: If the EVTX file cannot be opened or parsed, or if an unexpected error
            occurs during processing.  The original exception is included in the message and
            logged with full traceback.
    """
    logger.info(f"Parsing EVTX file: {file_path}")

    events_inserted = 0
    batch_size = 1000
    event_batch = []

    try:
        parser = PyEvtxParser(str(file_path))

        for record in parser.records_json():
            try:
                # Check if we have data field
                if "data" not in record:
                    logger.warning("EVTX record missing 'data' field")
                    continue

                # Parse the JSON data
                data = json.loads(record["data"])

                # Extract event ID and channel
                event_id = _extract_event_id(data)
                if event_id is None:
                    logger.warning(f"Could not extract event ID from record")
                    continue

                channel = _extract_channel(data)

                # Extract timestamp
                event_ts = _extract_timestamp(record, data)

                # Skip events without valid timestamp (forensically invalid)
                if event_ts is None:
                    logger.warning(f"Skipping EVTX event {event_id} without valid timestamp")
                    continue

                # Get original timestamp string for payload
                try:
                    ts_str = data["Event"]["System"]["TimeCreated"]["#attributes"]["SystemTime"]
                except (KeyError, TypeError):
                    ts_str = (
                        record.get("timestamp") or record.get("EventTime") or event_ts.isoformat()
                    )

                # Get EventData and flatten it
                event_data = data["Event"].get("EventData", {})
                event_data = _flatten_event_data(event_data)

                # Add SystemTime if not present
                if "SystemTime" not in event_data and "UtcTime" not in event_data:
                    event_data["SystemTime"] = ts_str

                # Build comprehensive payload with nested structure
                payload = {
                    "event_id": event_id,
                    "timestamp": ts_str,
                    "system": data["Event"].get("System", {}),
                    "event_data": event_data,
                    "user_data": data["Event"].get("UserData", {}),
                    "record_id": record.get("event_record_id"),
                }

                # Flatten the payload (creates dotted keys like "system.Task", "event_data.LogonType")
                # Do NOT promote event_data to root - keep the namespace clear
                payload = flatten_dict(payload)

                # Build event type from channel and event ID
                event_type = _build_event_type(channel, event_id)

                event_batch.append(
                    {
                        "event_ts": event_ts,
                        "artifact_id": artifact_id,
                        "event_type": event_type,
                        "payload": json.dumps(payload),
                    }
                )

                # Batch insert
                if len(event_batch) >= batch_size:
                    await _insert_event_batch(db, investigation_id, event_batch)
                    events_inserted += len(event_batch)
                    event_batch = []

            except Exception as e:
                logger.warning(f"Failed to parse EVTX record: {e}")
                continue

        # Insert remaining events
        if event_batch:
            await _insert_event_batch(db, investigation_id, event_batch)
            events_inserted += len(event_batch)

        logger.info(f"Parsed {events_inserted} events from EVTX file")
        return events_inserted

    except Exception as e:
        logger.error(f"Failed to parse EVTX file {file_path}: {e}", exc_info=True)
        raise RuntimeError(f"EVTX parsing failed: {e}")


async def _insert_event_batch(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    events: list[Dict[str, Any]],
):
    """
    Insert a batch of parsed events into the unified `events` table.

    This coroutine enriches each event dictionary with the provided
    `investigation_id` and then executes a single bulk INSERT statement.
    If the `events` collection is empty the function returns immediately
    without performing any database work.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used to execute the query
        and commit the transaction.
    investigation_id : uuid.UUID
        The identifier of the investigation to which all events belong.  It is
        added to each event record under the `investigation_id` column.
    events : list[dict[str, Any]]
        A list of dictionaries representing individual events.  Each dictionary
        must contain the keys `event_ts`, `artifact_id`, `event_type` and
        `payload`; the function will augment it with `investigation_id`.

    Raises
    ------
    Exception
        Propagates any exception raised during execution of the INSERT query.
        The database transaction is rolled back and the error is logged before
        being re-raised.

    Notes
    -----
    The SQL statement casts the `payload` field to `jsonb` to store it as a
    JSON document in PostgreSQL.  Because the operation is performed with an
    asynchronous session, callers should await this coroutine within an async
    context.
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


__all__ = [
    "parse_evtx",
    "_extract_event_id",
    "_extract_channel",
    "_extract_timestamp",
    "_flatten_event_data",
    "_normalize_channel_name",
    "_build_event_type",
]
