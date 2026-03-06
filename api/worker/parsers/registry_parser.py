import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import uuid
import json
import calendar

from sqlalchemy.ext.asyncio import AsyncSession
from regipy.registry import RegistryHive
from regipy.exceptions import RegistryParsingException
from regipy.plugins.system.shimcache import ShimCachePlugin
from regipy.plugins.system.bam import BAMPlugin
from regipy.plugins.amcache.amcache import AmCachePlugin
from regipy.plugins.ntuser.user_assist import UserAssistPlugin
from regipy.plugins.ntuser.shellbags_ntuser import ShellBagNtuserPlugin
from notatin import PyNotatinParser
import pyfwsi

from .base_parser import BaseParser
from .utils import flatten_dict, safe_json_dumps, sanitize_for_jsonb

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)

# Suppress verbose regipy logging
logging.getLogger("regipy").setLevel(logging.CRITICAL)
logging.getLogger("regipy.utils").setLevel(logging.CRITICAL)
logging.getLogger("regipy.registry").setLevel(logging.CRITICAL)
logging.getLogger("regipy.plugins").setLevel(logging.CRITICAL)
logging.getLogger("regipy.plugins.system.bam").setLevel(logging.CRITICAL)
logging.getLogger("regipy.plugins.amcache.amcache").setLevel(logging.CRITICAL)
logging.getLogger("regipy.plugins.ntuser.shellbags_ntuser").setLevel(logging.CRITICAL)


class RegistryParser(BaseParser):
    """
    Parser for Windows Registry hive files.
    
    Extracts registry keys, values, and runs specialized plugins for
    forensic artifacts like UserAssist, BAM, AmCache, ShellBags, and ShimCache.
    """
    
    @classmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Identify Windows Registry hive files.
        
        Args:
            filename: Original filename
            file_path: Path to the file
            
        Returns:
            True if file is a Registry hive
        """
        # First, check magic bytes - this is the most reliable method
        # Registry hives start with "regf" signature
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(4)
                if magic == b'regf':
                    return True
        except Exception:
            pass
        
        # Extract just the filename without path
        base_filename = Path(filename).name.lower()
        
        # Exact matches for common registry hives
        exact_names = [
            'ntuser.dat', 'usrclass.dat', 'system', 'software', 
            'sam', 'security', 'default', 'amcache.hve'
        ]
        
        # Check for exact match
        if base_filename in exact_names:
            # Double-check with magic bytes to avoid false positives
            try:
                with open(file_path, 'rb') as f:
                    magic = f.read(4)
                    return magic == b'regf'
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
        Parse a Windows Registry hive file and extract forensic events.

        The function performs three main steps:

        1. Load the hive using RegistryHive and run any applicable regipy plugins to obtain specialized
           artifact events. Plugin events are inserted immediately so they remain separate from generic
           key/value events.
        2. Walk every registry key with PyNotatinParser, extract each value's name, type and data,
           convert the information into a JSON payload, and batch-insert registry_value events.
        3. Keep statistics about processed keys/values, skipped entries, and the total number of events
           inserted.

        Args:
            db: Database session
            investigation_id: Investigation UUID
            artifact_id: Artifact ID
            file_path: Path to Registry hive file

        Returns:
            Number of events inserted
        """
        events_inserted = 0
        batch_size = 2000
        event_batch = []

        try:
            reg = RegistryHive(str(file_path))

            # Try to extract specialized forensic artifacts using plugins
            logger.debug(f"Attempting to extract plugin events from {file_path.name}")
            plugin_events = await self._extract_plugin_events(reg, file_path, artifact_id)
            plugin_event_count = len(plugin_events)

            # Insert plugin events immediately to keep them separate
            if plugin_events:
                await self._insert_event_batch(db, investigation_id, plugin_events)
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
                                f"Skipping registry key {sanitize_log_message(current_path)} without valid timestamp: {sanitize_log_message(str(e))}"
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
                                    "payload": safe_json_dumps(payload),
                                }
                            )

                            # Batch insert
                            if len(event_batch) >= batch_size:
                                await self._insert_event_batch(db, investigation_id, event_batch)
                                events_inserted += len(event_batch)
                                event_batch = []

                        except Exception as e:
                            logger.debug(f"Failed to parse registry value: {sanitize_log_message(str(e))}")
                            continue

                except Exception as e:
                    logger.debug(f"Failed to process registry key: {sanitize_log_message(str(e))}")
                    continue

            # Insert remaining events
            if event_batch:
                await self._insert_event_batch(db, investigation_id, event_batch)
                events_inserted += len(event_batch)

            logger.debug(
                f"Registry parsing complete: {events_inserted} total events ({plugin_event_count} plugin events, {events_inserted - plugin_event_count} registry values)"
            )
            logger.debug(f"Processed {key_count} keys and {value_count} values")
            logger.debug(
                f"Skipped {skipped_invalid_ts} keys with invalid timestamps, {skipped_exceptions} keys with timestamp exceptions"
            )
            return events_inserted

        except RegistryParsingException as e:
            #logger.error(f"Failed to parse registry hive {file_path}: {e}")
            logger.debug(f"Failed to parse registry hive {sanitize_log_message(str(file_path))}: {sanitize_log_message(str(e))}", exc_info=True)
            raise RuntimeError(f"Registry parsing failed: {sanitize_log_message(str(e))}")
        except Exception as e:
            #logger.error(f"Unexpected error parsing registry hive {file_path}: {e}")
            logger.debug(f"Unexpected error parsing registry hive {sanitize_log_message(str(file_path))}: {sanitize_log_message(str(e))}", exc_info=True)
            raise RuntimeError(f"Registry parsing failed: {sanitize_log_message(str(e))}")

    async def _extract_plugin_events(
        self,
        reg: RegistryHive,
        file_path: Path,
        artifact_id: int,
    ) -> list[Dict[str, Any]]:
        """
        Extracts forensic events from a Windows Registry hive using a set of regipy plugins.

        Args:
            reg: An instantiated RegistryHive representing the opened registry file.
            file_path: The filesystem path to the hive file being processed.
            artifact_id: Integer identifier of the source artifact record in the database.

        Returns:
            A list of event dictionaries ready for database insertion.
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
        
        # Extract custom MRU artifacts (not available as regipy plugins)
        logger.debug(f"Starting MRU artifact extraction from {file_path.name}")
        mru_events = await self._extract_mru_artifacts(reg, file_path, artifact_id)
        if mru_events:
            all_events.extend(mru_events)
            logger.debug(f"MRU extraction: Found {len(mru_events)} events")
        else:
            logger.debug(f"MRU extraction: No MRU artifacts found in {file_path.name}")

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
                        data_sample = json.dumps(plugin_data, default=str)[:1024]
                        logger.debug(f"Plugin {plugin_name} data sample: {data_sample}")
                    else:
                        logger.debug(f"Plugin {plugin_name} data: {str(plugin_data)[:1024]}")

                    # Parse plugin output
                    plugin_events = self._parse_plugin_data(plugin_data, plugin_name, artifact_id)
                    if plugin_events:
                        all_events.extend(plugin_events)
                        logger.debug(
                            f"Plugin {plugin_name} SUCCESS: Extracted {len(plugin_events)} events (event_type: registry_{plugin_name})"
                        )
                    else:
                        logger.warning(
                            f"Plugin {plugin_name} FAILED: Returned data but no events were parsed. Data type: {type(plugin_data)}"
                        )
                else:
                    logger.debug(f"Plugin {plugin_name} SKIPPED: No data found (hive doesn't contain this artifact type)")

            except ModuleNotFoundError as e:
                # Missing optional dependency (e.g., pyfwsi for shellbags)
                logger.warning(f"Plugin {plugin_name} FAILED: Missing dependency - {e}")
                continue
            except (KeyError, AttributeError) as e:
                # Plugin not applicable to this hive type (expected)
                logger.debug(
                    f"Plugin {plugin_name} SKIPPED: Not applicable to this hive ({type(e).__name__}: {sanitize_log_message(str(e))})"
                )
                continue
            except ValueError as e:
                # Value errors might indicate parsing issues
                logger.warning(f"Plugin {plugin_name} FAILED: ValueError - {sanitize_log_message(str(e))}")
                continue
            except Exception as e:
                # Unexpected error - log but continue
                logger.error(
                    f"Plugin {plugin_name} FAILED: {type(e).__name__} - {sanitize_log_message(str(e))}", exc_info=True
                )
                continue

        return all_events

    def _parse_plugin_data(
        self,
        plugin_data: Any,
        plugin_name: str,
        artifact_id: int,
    ) -> list[Dict[str, Any]]:
        """
        Parse raw plugin output into a list of normalized event dictionaries.

        Args:
            plugin_data: The raw output from a regipy plugin.
            plugin_name: The name of the plugin that produced the data.
            artifact_id: Integer identifier linking events to their source artifact.

        Returns:
            A list of event dictionaries ready for database insertion.
        """
        events = []

        try:
            # Parse JSON string if needed
            if isinstance(plugin_data, str):
                try:
                    plugin_data = json.loads(plugin_data)
                except json.JSONDecodeError:
                    logger.debug(
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
                logger.debug(f"Plugin {plugin_name} returned unexpected type: {type(plugin_data)}")
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
                    "last_mod_date",  # ShimCache uses this field
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
                
                # Sanitize payload to handle encoding issues
                payload = sanitize_for_jsonb(payload)

                events.append(
                    {
                        "event_ts": event_ts,
                        "artifact_id": artifact_id,
                        "event_type": f"registry_{plugin_name}",
                        "payload": safe_json_dumps(payload),
                    }
                )

        except Exception as e:
            logger.error(f"Failed to parse {sanitize_log_message(plugin_name)} plugin data: {sanitize_log_message(str(e))}", exc_info=True)

        logger.debug(f"Plugin {plugin_name} parsed {len(events)} events")
        return events

    def _parse_mru_binary_data(self, data: bytes, artifact_name: str) -> tuple[str, bool]:
        """
        Parse binary MRU data (Shell Item/PIDL structures) to extract file paths.
        
        Uses pyfwsi (Windows Forensic Shell Item parser) for proper PIDL parsing.
        Falls back to heuristic string extraction for simple cases.
        
        Args:
            data: Raw binary data from registry value
            artifact_name: Name of the artifact (for context-specific parsing)
            
        Returns:
            Tuple of (parsed_string, is_valid)
            - parsed_string: Human-readable path/string or empty if parsing failed
            - is_valid: True if we extracted readable data, False otherwise
        """
        if not data or len(data) == 0:
            return ("", False)
        
        # Try pyfwsi for proper PIDL/Shell Item parsing
        try:
            # Parse the Shell Item list structure
            item_list = pyfwsi.item_list()
            item_list.copy_from_byte_stream(data)
            
            # Extract paths from all items in the list
            paths = []
            num_items = item_list.get_number_of_items()
            
            for i in range(num_items):
                try:
                    item = item_list.get_item(i)
                    
                    # Try to get the name from the item
                    # Different item types have different name attributes
                    item_name = None
                    
                    # File entry items
                    if hasattr(item, 'get_name'):
                        try:
                            item_name = item.get_name()
                        except:
                            pass
                    
                    # Some items have long_name
                    if not item_name and hasattr(item, 'get_long_name'):
                        try:
                            item_name = item.get_long_name()
                        except:
                            pass
                    
                    # Network location items
                    if not item_name and hasattr(item, 'get_location'):
                        try:
                            item_name = item.get_location()
                        except:
                            pass
                    
                    # Validate the component before adding it
                    if item_name and self._is_valid_path_component(item_name):
                        paths.append(item_name)
                    elif item_name:
                        logger.debug(f"Rejected invalid path component: {item_name[:50]}")
                        
                except Exception:
                    continue
            
            if paths:
                # Build path from components
                full_path = '\\'.join(paths)
                
                # Validate that this looks like a real Windows path
                # Filter out mojibake and garbage data
                if self._is_valid_windows_path(full_path):
                    logger.debug(f"pyfwsi extracted valid path: {full_path}")
                    return (full_path, True)
                else:
                    logger.debug(f"pyfwsi extracted invalid path (mojibake): {full_path[:100]}")
                    # Fall through to try other parsing methods
                
        except Exception as e:
            # Shell Item parsing failed - try fallback methods
            logger.debug(f"pyfwsi parsing failed for {artifact_name}: {sanitize_log_message(str(e))}")
        
        # Fallback: Try simple UTF-16-LE decoding for string-based MRU values
        # (RunMRU, TypedPaths, WordWheelQuery typically use plain strings)
        try:
            decoded = data.decode('utf-16-le', errors='ignore').rstrip('\x00')
            if decoded and len(decoded) >= 1:
                # Check if mostly printable (allow control chars like \1 in RunMRU)
                printable_count = sum(1 for c in decoded if c.isprintable() or c in '\r\n\t')
                if printable_count / len(decoded) >= 0.5:  # At least 50% printable
                    return (decoded, True)
        except (ValueError, UnicodeDecodeError):
            pass
        
        # Fallback: Scan for embedded UTF-16-LE strings in binary data
        # This handles cases where PIDL structures contain file paths
        extracted_strings = []
        i = 0
        
        while i < len(data) - 8:  # Need at least 8 bytes for meaningful string
            # Look for UTF-16-LE pattern: printable ASCII, null, printable ASCII, null...
            if (data[i] >= 0x20 and data[i] <= 0x7E and
                i + 1 < len(data) and data[i + 1] == 0):
                
                string_start = i
                string_end = i
                
                # Continue while pattern holds
                while string_end < len(data) - 1:
                    if string_end + 1 < len(data) and data[string_end] == 0 and data[string_end + 1] == 0:
                        break  # Double null = end of string
                    string_end += 2
                    if string_end >= len(data):
                        break
                
                # Extract if long enough (at least 3 UTF-16-LE chars = 6 bytes)
                if string_end - string_start >= 6:
                    try:
                        string_bytes = data[string_start:string_end]
                        string = string_bytes.decode('utf-16-le', errors='ignore').rstrip('\x00')
                        
                        # Strict validation: ASCII-only, no mojibake
                        if string and len(string) >= 2:
                            # Check if ALL characters are ASCII (no Unicode)
                            is_ascii = all(ord(c) <= 0x7F for c in string)
                            if is_ascii:
                                # Check if mostly printable
                                printable = sum(1 for c in string if c.isprintable())
                                if printable / len(string) >= 0.8:
                                    extracted_strings.append(string)
                    except:
                        pass
                
                i = string_end + 2
            else:
                i += 1
        
        # Return extracted strings if found and valid
        if extracted_strings:
            seen = set()
            unique = []
            for s in extracted_strings:
                # Additional validation: must look like a filename or path
                if self._is_valid_path_component(s) or '\\' in s or '/' in s or '.' in s:
                    s_lower = s.lower()
                    if s_lower not in seen and len(s) >= 2:
                        seen.add(s_lower)
                        unique.append(s)
            
            if unique:
                result = ' | '.join(unique)
                logger.debug(f"Extracted valid strings from binary: {result[:100]}")
                return (result, True)
        
        # No readable data found
        return ("", False)
    
    def _is_valid_windows_path(self, path: str) -> bool:
        """
        Validate that a string looks like a valid Windows file path.
        Filters out mojibake and garbage data from PIDL parsing.
        
        Args:
            path: String to validate
            
        Returns:
            True if path looks valid, False otherwise
        """
        if not path or len(path) < 2:
            return False
        
        # Check if path contains mostly ASCII printable characters
        # Allow some extended ASCII (0x80-0xFF) for international filenames
        ascii_printable = sum(1 for c in path if ord(c) >= 0x20 and ord(c) <= 0x7E)
        extended_ascii = sum(1 for c in path if ord(c) >= 0x80 and ord(c) <= 0xFF)
        total_valid = ascii_printable + extended_ascii
        
        # At least 90% of characters should be valid ASCII/extended ASCII
        if total_valid / len(path) < 0.9:
            return False
        
        # Check for common Windows path patterns
        path_lower = path.lower()
        
        # Valid patterns:
        # - Drive letter: C:\, D:\, etc.
        # - UNC path: \\server\share
        # - Relative path with backslashes
        # - Contains common path separators
        has_drive_letter = len(path) >= 3 and path[1] == ':' and path[2] == '\\'
        has_unc_prefix = path.startswith('\\\\')
        has_backslash = '\\' in path
        has_forward_slash = '/' in path
        
        # Must have at least one path separator or be a drive letter path
        if not (has_drive_letter or has_unc_prefix or has_backslash or has_forward_slash):
            return False
        
        # Reject paths with too many non-ASCII characters (likely mojibake)
        # Chinese/Japanese/Korean characters indicate corrupted data
        non_ascii_chars = sum(1 for c in path if ord(c) > 0xFF)
        if non_ascii_chars > 0:
            return False
        
        # Check for common Windows path components
        common_dirs = ['windows', 'program files', 'users', 'appdata', 'documents', 
                       'downloads', 'desktop', 'temp', 'system32', 'programdata']
        has_common_dir = any(d in path_lower for d in common_dirs)
        
        # Check for file extensions
        common_extensions = ['.exe', '.dll', '.txt', '.doc', '.pdf', '.jpg', '.png', 
                            '.zip', '.rar', '.mp3', '.mp4', '.avi', '.lnk', '.url']
        has_extension = any(ext in path_lower for ext in common_extensions)
        
        # If it has a drive letter or UNC prefix, it's likely valid
        if has_drive_letter or has_unc_prefix:
            return True
        
        # If it has common directories or extensions, it's likely valid
        if has_common_dir or has_extension:
            return True
        
        # If it's short and has path separators, it might be valid
        if len(path) <= 100 and (has_backslash or has_forward_slash):
            return True
        
        # Otherwise, reject it as likely garbage
        return False
    
    def _is_valid_path_component(self, component: str) -> bool:
        """
        Validate that a path component (filename or directory name) is valid.
        Rejects mojibake and non-ASCII garbage.
        
        Args:
            component: Path component to validate
            
        Returns:
            True if component looks valid, False otherwise
        """
        if not component or len(component) == 0:
            return False
        
        # Reject any component with non-ASCII characters (Unicode > 0x7F)
        # This catches Chinese/Japanese/Korean mojibake
        for char in component:
            if ord(char) > 0x7F:
                return False
        
        # Check if component contains only valid Windows filename characters
        # Valid: A-Z, a-z, 0-9, space, dash, underscore, period, parentheses, etc.
        # Invalid: control characters, pipes, asterisks, etc.
        invalid_chars = '<>:"|?*\x00-\x1F'
        for char in component:
            if char in invalid_chars:
                return False
        
        # Must contain at least one alphanumeric character
        has_alnum = any(c.isalnum() for c in component)
        if not has_alnum:
            return False
        
        return True
    
    def _extract_valid_path_fragments(self, text: str, min_length: int = 5) -> str:
        """
        Extract contiguous ASCII sequences that look like valid file paths or names.
        Used to clean up mojibake by extracting just the valid parts.
        
        Args:
            text: Text potentially containing mojibake
            min_length: Minimum length for a valid fragment
            
        Returns:
            Cleaned text with only valid path fragments, or empty string if none found
        """
        fragments = []
        current_fragment = []
        
        for char in text:
            # Only keep ASCII printable characters that are valid in Windows paths
            if ord(char) <= 0x7F and (char.isalnum() or char in r' .-_()[]{}~!@#$%^&\/'):
                current_fragment.append(char)
            else:
                # Non-ASCII or invalid char - end current fragment
                if len(current_fragment) >= min_length:
                    fragment_str = ''.join(current_fragment).strip()
                    # Additional validation: must look like a filename or path component
                    if self._looks_like_path_fragment(fragment_str):
                        fragments.append(fragment_str)
                current_fragment = []
        
        # Don't forget the last fragment
        if len(current_fragment) >= min_length:
            fragment_str = ''.join(current_fragment).strip()
            if self._looks_like_path_fragment(fragment_str):
                fragments.append(fragment_str)
        
        # Join fragments with separator
        if fragments:
            return ' | '.join(fragments)
        return ""
    
    def _looks_like_path_fragment(self, fragment: str) -> bool:
        """
        Check if a fragment looks like a valid path component or filename.
        
        Args:
            fragment: String fragment to check
            
        Returns:
            True if fragment looks valid, False otherwise
        """
        if not fragment or len(fragment) < 3:
            return False
        
        # Must contain at least one alphanumeric character
        if not any(c.isalnum() for c in fragment):
            return False
        
        # Check for common path indicators
        has_extension = '.' in fragment and not fragment.startswith('.') and not fragment.endswith('.')
        has_path_sep = '\\' in fragment or '/' in fragment
        has_drive = len(fragment) >= 3 and fragment[1] == ':'
        
        # Check for common filename patterns
        common_extensions = ['.exe', '.dll', '.txt', '.doc', '.pdf', '.jpg', '.png', 
                            '.zip', '.rar', '.lnk', '.url', '.ini', '.log', '.dat',
                            '.docx', '.xlsx', '.pptx', '.html', '.xml', '.json']
        has_common_ext = any(fragment.lower().endswith(ext) for ext in common_extensions)
        
        # Check for common directory names
        common_dirs = ['windows', 'program', 'files', 'users', 'appdata', 'documents',
                       'downloads', 'desktop', 'temp', 'system', 'local', 'roaming']
        has_common_dir = any(d in fragment.lower() for d in common_dirs)
        
        # Accept if it has any of these characteristics
        if has_extension or has_path_sep or has_drive or has_common_ext or has_common_dir:
            return True
        
        # Also accept if it's a reasonable length and mostly alphanumeric
        if 3 <= len(fragment) <= 100:
            alnum_count = sum(1 for c in fragment if c.isalnum())
            if alnum_count / len(fragment) >= 0.5:
                return True
        
        return False

    async def _extract_mru_artifacts(
        self,
        reg: RegistryHive,
        file_path: Path,
        artifact_id: int,
    ) -> list[Dict[str, Any]]:
        """
        Extract MRU (Most Recently Used) artifacts from registry hive.
        
        Extracts:
        - RecentDocs
        - OpenSaveMRU (OpenSavePidlMRU)
        - LastVisitedMRU (LastVisitedPidlMRU)
        - TypedPaths
        - RunMRU
        - WordWheelQuery
        
        Uses flexible path matching to handle different hive structures and Windows versions.
        Parses binary PIDL structures to extract human-readable file/folder names.
        
        Args:
            reg: Registry hive object
            file_path: Path to hive file
            artifact_id: Artifact ID
            
        Returns:
            List of event dictionaries
        """
        events = []
        
        # MRU registry path patterns to search for (case-insensitive partial matching)
        # Using path patterns that match the actual registry structure
        # Paths are normalized to lowercase for matching
        mru_patterns = [
            # RecentDocs - recently opened documents
            {
                "path_suffix": "explorer\\recentdocs",
                "event_type": "registry_recentdocs",
                "artifact_name": "RecentDocs",
            },
            # OpenSaveMRU - files/folders in Open/Save dialogs
            {
                "path_suffix": "comdlg32\\opensavepidlmru",
                "event_type": "registry_opensavemru",
                "artifact_name": "OpenSaveMRU",
            },
            # LastVisitedMRU - applications and files opened together
            {
                "path_suffix": "comdlg32\\lastvisitedpidlmru",
                "event_type": "registry_lastvisitedmru",
                "artifact_name": "LastVisitedMRU",
            },
            # TypedPaths - manually typed paths in Explorer address bar
            {
                "path_suffix": "explorer\\typedpaths",
                "event_type": "registry_typedpaths",
                "artifact_name": "TypedPaths",
            },
            # RunMRU - commands executed via Win+R Run dialog
            {
                "path_suffix": "explorer\\runmru",
                "event_type": "registry_runmru",
                "artifact_name": "RunMRU",
            },
            # WordWheelQuery - Windows Search queries
            {
                "path_suffix": "explorer\\wordwheelquery",
                "event_type": "registry_wordwheelquery",
                "artifact_name": "WordWheelQuery",
            },
        ]
        
        # Walk all keys in the hive and match against patterns
        try:
            reg_object = PyNotatinParser(str(file_path))  # type: ignore
            
            # Track which patterns we've found and sample paths
            patterns_found = {pattern["artifact_name"]: 0 for pattern in mru_patterns}
            sample_paths = {pattern["artifact_name"]: None for pattern in mru_patterns}
            
            # Match keys against MRU patterns
            for key in reg_object.reg_keys():
                try:
                    key_path = key.path
                    key_path_lower = key_path.lower()
                    
                    # Try to match against each pattern
                    for mru_config in mru_patterns:
                        path_suffix = mru_config["path_suffix"]
                        
                        # Check if this key matches the pattern
                        # The path_suffix is the ending part (e.g., "explorer\recentdocs")
                        # We need to match it anywhere in the path, accounting for:
                        # 1. Exact suffix match: path ends with the pattern
                        # 2. Subkey match: path contains pattern followed by backslash (e.g., RecentDocs\.txt)
                        
                        # Find the pattern in the path
                        pattern_index = key_path_lower.find(path_suffix)
                        
                        if pattern_index == -1:
                            # Pattern not found at all
                            continue
                        
                        # Check if this is a valid match:
                        # Either the pattern is at the end, or followed by a backslash (subkey)
                        pattern_end = pattern_index + len(path_suffix)
                        matches = (
                            pattern_end == len(key_path_lower) or  # Exact end match
                            (pattern_end < len(key_path_lower) and key_path_lower[pattern_end] == '\\')  # Subkey match
                        )
                        
                        if not matches:
                            continue
                        
                        # Track first match for this pattern
                        if patterns_found[mru_config["artifact_name"]] == 0:
                            sample_paths[mru_config["artifact_name"]] = key_path
                        
                        # Get key timestamp
                        try:
                            ts_dt = key.last_key_written_date_and_time
                            key_ts = round(float(calendar.timegm(ts_dt.timetuple())), 3)
                            if key_ts <= 0:
                                continue
                            key_timestamp = datetime.fromtimestamp(key_ts)
                        except (AttributeError, TypeError, ValueError):
                            # Skip keys without valid timestamps
                            continue
                        
                        # Extract values from the matching key
                        for value in key.values():
                            try:
                                value_name = value.pretty_name if value.pretty_name else "(Default)"
                                
                                # Skip MRUList, MRUListEx, and other metadata entries
                                if value_name.lower() in ["mrulist", "mrulistex", "mrulistex2", "nodecount", "nodeslots"]:
                                    continue
                                
                                # Convert value content to string
                                content = value.content
                                value_str = None
                                raw_hex = None
                                is_valid = True
                                
                                if isinstance(content, bytes):
                                    # Binary data - parse based on artifact type
                                    # RecentDocs, OpenSaveMRU, LastVisitedMRU use Shell Item (PIDL) structures
                                    # RunMRU, TypedPaths, WordWheelQuery typically use plain UTF-16-LE strings
                                    
                                    artifact_type = mru_config["artifact_name"].lower()
                                    
                                    # Determine parsing strategy based on artifact type
                                    artifact_type = mru_config["artifact_name"].lower()
                                    
                                    # PIDL-based artifacts: RecentDocs, OpenSaveMRU, LastVisitedMRU
                                    # These store Shell Item (PIDL) binary structures that require pyfwsi
                                    if artifact_type in ["recentdocs", "opensavemru", "lastvisitedmru"]:
                                        value_str, is_valid = self._parse_mru_binary_data(content, mru_config["artifact_name"])
                                        raw_hex = content.hex()
                                        
                                        if not is_valid or not value_str:
                                            logger.debug(
                                                f"Skipping {mru_config['artifact_name']} entry '{value_name}': "
                                                f"Shell Item parsing failed"
                                            )
                                            continue
                                    
                                    # String-based artifacts: RunMRU, TypedPaths, WordWheelQuery
                                    # These typically store plain UTF-16-LE strings
                                    else:
                                        try:
                                            decoded = content.decode('utf-16-le', errors='ignore').rstrip('\x00')
                                            if decoded and len(decoded) >= 1:
                                                # Allow control characters (e.g., \1 in RunMRU indicates position)
                                                printable_count = sum(1 for c in decoded if c.isprintable() or c in '\r\n\t')
                                                if printable_count / len(decoded) >= 0.5:
                                                    value_str = decoded
                                                    raw_hex = content.hex()
                                                    is_valid = True
                                                else:
                                                    raise ValueError("Not enough printable characters")
                                            else:
                                                raise ValueError("Empty string")
                                        except (ValueError, UnicodeDecodeError):
                                            # UTF-16 decoding failed, try fallback parsing
                                            value_str, is_valid = self._parse_mru_binary_data(content, mru_config["artifact_name"])
                                            raw_hex = content.hex()
                                            
                                            if not is_valid or not value_str:
                                                logger.debug(
                                                    f"Skipping {mru_config['artifact_name']} entry '{value_name}': "
                                                    f"could not decode binary data"
                                                )
                                                continue
                                        
                                elif isinstance(content, (str, int, float)):
                                    # Already a string - use as-is
                                    value_str = str(content)
                                elif isinstance(content, list):
                                    value_str = ", ".join(str(v) for v in content).strip(", ")
                                else:
                                    value_str = str(content)
                                
                                # Final validation - ensure we have meaningful data
                                # Be lenient - even single characters can be forensically valuable
                                if not value_str or len(value_str.strip()) == 0:
                                    logger.debug(
                                        f"Skipping {mru_config['artifact_name']} entry '{value_name}': "
                                        f"value is empty"
                                    )
                                    continue
                                
                                # If value contains non-ASCII characters, try to extract valid ASCII fragments
                                if any(ord(c) > 0x7F for c in value_str):
                                    logger.debug(
                                        f"{mru_config['artifact_name']} entry '{value_name}' contains non-ASCII, "
                                        f"attempting to extract valid path fragments"
                                    )
                                    # Extract contiguous ASCII sequences that look like paths
                                    cleaned = self._extract_valid_path_fragments(value_str)
                                    if cleaned:
                                        value_str = cleaned
                                        logger.debug(f"Extracted valid fragments: {value_str}")
                                    else:
                                        logger.debug(
                                            f"Skipping {mru_config['artifact_name']} entry '{value_name}': "
                                            f"no valid path fragments found in: {value_str[:50]}"
                                        )
                                        continue
                                
                                # Create payload
                                payload = {
                                    "artifact_name": mru_config["artifact_name"],
                                    "key_path": key_path,
                                    "value_name": value_name,
                                    "value_data": value_str,
                                    "last_modified": key_timestamp.isoformat(),
                                }
                                
                                # Only include hex if it exists (binary data)
                                if raw_hex:
                                    payload["value_data_hex"] = raw_hex
                                
                                # Flatten and sanitize
                                payload = flatten_dict(payload)
                                payload = sanitize_for_jsonb(payload)
                                
                                events.append({
                                    "event_ts": key_timestamp,
                                    "artifact_id": artifact_id,
                                    "event_type": mru_config["event_type"],
                                    "payload": safe_json_dumps(payload),
                                })
                                
                                # Track successful extraction
                                patterns_found[mru_config["artifact_name"]] += 1
                                
                            except Exception as e:
                                logger.debug(f"Failed to parse MRU value: {sanitize_log_message(str(e))}")
                                continue
                        
                        # Break after processing this pattern to avoid double-counting
                        break
                                
                except Exception as e:
                    logger.debug(f"Failed to process key for MRU pattern: {sanitize_log_message(str(e))}")
                    continue
                        
        except Exception as e:
            logger.debug(f"Failed to extract MRU artifacts: {sanitize_log_message(str(e))}", exc_info=True)
        
        # Log summary of what was found
        if events:
            logger.debug(f"MRU extraction complete: {len(events)} total events from {len([c for c in patterns_found.values() if c > 0])} artifact types")
            for artifact_name, count in patterns_found.items():
                if count > 0:
                    logger.debug(f"  - {artifact_name}: {count} events (sample path: {sample_paths[artifact_name]})")
        else:
            logger.debug(f"MRU extraction complete: No MRU artifacts found")
            logger.debug(f"Searched for: {', '.join([p['artifact_name'] for p in mru_patterns])}")
        
        return events


__all__ = ["RegistryParser"]
