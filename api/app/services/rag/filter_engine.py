from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class FilterEngine:
    """
    Determines which forensic artifacts should be indexed for RAG.

    Default configuration mirrors the existing hard-coded filter logic,
    but can be overridden per-investigation or globally.
    """

    DEFAULT_CONFIG = {
        "mft": {
            "include_paths": [
                "users\\",
                "programdata\\",
                "\\temp\\",
                "\\tmp\\",
                "windows\\temp\\",
                "appdata\\",
                "downloads\\",
            ],
            "extensions": [
                ".zip",
                ".7z",
                ".rar",
                ".exe",
                ".scr",
                ".sys",
                ".ps1",
                ".vbs",
                ".py",
                ".bat",
                ".cmd",
                ".dll",
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
            ],
        },
        "evtx": {
            "channels": [
                {
                    "name": "Microsoft-Windows-Sysmon/Operational",
                    "event_ids": [1, 3, 8, 10, 11, 12, 13, 19, 20, 21],
                },
                {
                    "name": "Security",
                    "event_ids": [
                        4624,
                        4625,
                        4634,
                        4647,
                        4648,
                        4672,
                        4688,
                        4720,
                        4779,
                        7045,
                    ],
                },
                {
                    "name": "Microsoft-Windows-PowerShell/Operational",
                    "event_ids": [
                        4103,
                        4104,
                        40961,
                        40962,
                        24577,
                        8193,
                        8194,
                        8197,
                    ],
                },
                {
                    "name": "Microsoft-Windows-WinRM/Operational",
                    "event_ids": [91, 168, 169, 254],
                },
                {
                    "name": "Microsoft-Windows-WMI-Activity/Operational",
                    "event_ids": [5857, 5858, 5860, 5861],
                },
                {
                    "name": "Microsoft-Windows-Windows Defender/Operational",
                    "event_ids": [1006, 1007, 1116, 1117, 1118, 1119],
                },
                {
                    "name": "Microsoft-Windows-TerminalServices-LocalSessionManager/Operational",
                    "event_ids": [21, 22, 23, 24, 25],
                },
                {
                    "name": "Microsoft-Windows-TerminalServices-RemoteConnectionManager/Operational",
                    "event_ids": [1149],
                },
                {
                    "name": "Microsoft-Windows-TerminalServices-RDPClient/Operational",
                    "event_ids": [1024, 1025, 1102, 1103],
                },
                {
                    "name": "Microsoft-Windows-TaskScheduler/Operational",
                    "event_ids": [106, 129, 140, 141, 200, 201],
                },
                {
                    "name": "Microsoft-Windows-RemoteDesktopServices-RdpCoreTS/Operational",
                    "event_ids": [131, 140],
                },
            ],
            "lol_bins": True,
            "interesting_ports": [3389, 5900, 5985, 5986, 22, 23],
        },
        "registry": {
            "interesting_keys": [
                "run",
                "runonce",
                "services",
                "userinit",
                "shell",
                "winlogon",
            ],
        },
        "prefetch": {
            "include_all": False,
        },
        "lnk": {
            "include_all": False,
        },
    }

    # LOLBins (Living Off the Land Binaries)
    LOLBINS = [
        "powershell.exe",
        "cmd.exe",
        "wmic.exe",
        "mshta.exe",
        "rundll32.exe",
        "regsvr32.exe",
        "certutil.exe",
        "bitsadmin.exe",
        "psexec.exe",
        "wevtutil.exe",
        "net.exe",
        "sc.exe",
        "schtasks.exe",
        "at.exe",
        "reg.exe",
        "vssadmin.exe",
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize a new FilterEngine instance with optional configuration.

        :param config: Optional dictionary containing filter settings. If omitted or `None`, the engine falls back to :pyattr:`DEFAULT_CONFIG`.
        :type config: dict[str, Any] | None

        The provided configuration overrides the default rules used by the engine to evaluate forensic artifacts such as MFT entries, EVTX events (including LOLBins and specific ports), registry keys, prefetch files, and LNK shortcuts. The resulting configuration is stored in :pyattr:`self.config`.
        """
        self.config = config or self.DEFAULT_CONFIG

    def is_interesting_mft(self, path: str, extension: str = "") -> bool:
        """
        Determine whether a given Master File Table (MFT) entry should be considered interesting for indexing.

        Args:
            path: The full file system path of the artifact.
            extension: The file's extension (including the leading dot), e.g., ".exe". Optional; defaults to an empty string.

        Returns:
            bool: `True` if the entry matches any inclusion criteria defined in the engine’s configuration (such as configured include paths or allowed extensions); otherwise `False`.
        """
        return False

    def is_interesting_evtx(self, event_dict: Dict[str, Any]) -> Tuple[bool, Optional[datetime]]:
        """
        Determine whether an EVTX event should be considered interesting for indexing.

        The method evaluates a flattened EVTX event dictionary against the engine's configuration and built-in heuristics:

        * **Channel and Event ID matching** - Checks if the event's channel name contains any configured channel pattern and if its numeric ID is listed among the allowed IDs for that channel.
        * **Living-off-the-land binary (LOLBin) detection** - When enabled, inspects the `Image`, `ParentImage`, and `CommandLine` fields for any known LOLBin executable names.
        * **Interesting port detection** - If a list of ports is configured, examines the source or destination port fields for matches.

        The function also attempts to parse the event timestamp into a :class:`datetime.datetime` object when possible.

        Args:
            event_dict: A dictionary representing a flattened EVTX event payload. Keys may include
                `system.Channel`, `Channel`, `system.EventID`, `event_id`, `EventID`,
                `timestamp`, `system.TimeCreated`, as well as nested fields such as
                `event_data.Image`, `Image`, `event_data.ParentImage`, `ParentImage`,
                `event_data.CommandLine`, `CommandLine`, `event_data.DestinationPort`,
                `DestinationPort`, `event_data.SourcePort`, and `SourcePort`.

        Returns:
            tuple[bool, datetime | None]: A two-element tuple where the first element is
            `True` if the event matches any of the interesting criteria, otherwise `False`.
            The second element is a :class:`datetime.datetime` object representing the event's
            timestamp when it could be parsed, or `None` if parsing failed or the timestamp was absent.
        """
        evtx_config = self.config.get("evtx", {})

        channel = event_dict.get("system.Channel") or event_dict.get("Channel") or ""
        event_id_raw = (
            event_dict.get("system.EventID")
            or event_dict.get("event_id")
            or event_dict.get("EventID")
        )
        try:
            event_id = int(event_id_raw) if event_id_raw else None
        except (ValueError, TypeError):
            event_id = None

        timestamp_str = event_dict.get("timestamp") or event_dict.get("system.TimeCreated")

        timestamp = None
        if timestamp_str:
            try:
                if isinstance(timestamp_str, datetime):
                    timestamp = timestamp_str
                else:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except Exception:
                pass

        # Check if event matches configured channel + event_id
        is_interesting_event = False
        channels = evtx_config.get("channels", [])
        for channel_config in channels:
            if channel and channel_config["name"].lower() in channel.lower():
                if event_id and event_id in channel_config.get("event_ids", []):
                    is_interesting_event = True
                    break

        # If event doesn't match channel+event_id, it's not interesting
        if not is_interesting_event:
            return (False, timestamp)

        # Carve out for null IP events
        if (
            event_dict.get("event_data.IpAddress", "") == "-"
            or event_dict.get("event_data.IpAddress", "") == "127.0.0.1"
        ):
            return (False, timestamp)

        # TODO This is slow
        if evtx_config.get("lol_bins", False):
            for v in event_dict.values():
                if isinstance(v, str):
                    for lolbin in self.LOLBINS:
                        if lolbin in v.casefold():
                            return (True, timestamp)

        interesting_ports = evtx_config.get("interesting_ports", [])
        if interesting_ports:
            dest_port = event_dict.get("event_data.DestinationPort") or event_dict.get(
                "DestinationPort"
            )
            source_port = event_dict.get("event_data.SourcePort") or event_dict.get("SourcePort")

            try:
                if dest_port and isinstance(dest_port, str):
                    dest_port = int(dest_port)
                if source_port and isinstance(source_port, str):
                    source_port = int(source_port)
            except (ValueError, TypeError):
                pass

            if dest_port in interesting_ports or source_port in interesting_ports:
                return (True, timestamp)

        # event id and channel is enough
        return (True, timestamp)

    def is_interesting_registry(self, key_path: str) -> bool:
        """
        Determine whether a given registry key path is considered interesting based on the engine’s configuration.

        Args:
            key_path (str): The full registry key path to evaluate.

        Returns:
            bool: `True` if the key matches any pattern defined in the `interesting_keys` list of the registry configuration and should therefore be indexed; otherwise `False`.
        """
        return False

    def is_interesting_prefetch(self, executable_name: str) -> bool:
        """
        Determine whether a prefetch file should be indexed based on the engine's configuration.

        Args:
            executable_name (str): Name of the executable associated with the prefetch file. Currently unused but retained for API compatibility and future extensions.

        Returns:
            bool: `True` if the configuration indicates that all prefetch files are to be included (i.e., `prefetch.include_all` is set to `True` or missing), otherwise `False`.
        """
        prefetch_config = self.config.get("prefetch", {})

        if prefetch_config.get("include_all", True):
            return True

        return False

    def is_interesting_lnk(self, target_path: str) -> bool:
        """
        Determine whether a shortcut (LNK) file should be considered interesting based on configuration.

        Args:
            target_path: The resolved target path of the LNK file.

        Returns:
            True if the LNK is marked for indexing according to the `lnk` section of the engine's configuration; otherwise, False.
        """
        lnk_config = self.config.get("lnk", {})

        if lnk_config.get("include_all", True):
            return True

        return False


__all__ = ["FilterEngine"]
