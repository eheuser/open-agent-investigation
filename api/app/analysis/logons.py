from typing import List, Dict, Any, Optional
from uuid import UUID
import json
from datetime import datetime, timedelta
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message
from app.core.database import async_session_factory

logger = get_logger(__name__)

ANALYSIS_VERSION = "1.0"  # Increment when query logic changes to invalidate cache


class LogonEntry:
    """Represents a single logon/logoff event found in the system."""

    def __init__(
        self,
        logon_type: str,
        event_action: str,  # "Logon", "Logoff", "Failed Logon"
        username: str,
        domain: Optional[str] = None,
        logon_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        source_host: Optional[str] = None,
        timestamp: Optional[str] = None,
        event_id: Optional[int] = None,
        event_record_id: Optional[int] = None,
        logon_process: Optional[str] = None,
        authentication_package: Optional[str] = None,
        failure_reason: Optional[str] = None,
        status_code: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ):
        self.logon_type = logon_type
        self.event_action = event_action
        self.username = username
        self.domain = domain
        self.logon_id = logon_id
        self.source_ip = source_ip
        self.source_host = source_host
        self.timestamp = timestamp
        self.event_id = event_id
        self.event_record_id = event_record_id
        self.logon_process = logon_process
        self.authentication_package = authentication_package
        self.failure_reason = failure_reason
        self.status_code = status_code
        self.raw_data = raw_data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "logon_type": self.logon_type,
            "event_action": self.event_action,
            "username": self.username,
            "domain": self.domain,
            "logon_id": self.logon_id,
            "source_ip": self.source_ip,
            "source_host": self.source_host,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "event_record_id": self.event_record_id,
            "logon_process": self.logon_process,
            "authentication_package": self.authentication_package,
            "failure_reason": self.failure_reason,
            "status_code": self.status_code,
            "raw_data": self.raw_data,
        }


class LogonsAnalyzer:
    """Analyzes Windows logon, logoff, and failed logon events."""

    # Windows Event Log Event IDs for Security logs
    EVENT_ID_MAPPING = {
        4624: "Logon",  # Successful logon
        4625: "Failed Logon",  # Failed logon
        4634: "Logoff",  # Logoff
        4647: "User Initiated Logoff",  # User-initiated logoff
        4648: "Explicit Credential Logon",  # RunAs logon
        4672: "Special Privileges Logon",  # Admin logon
    }

    # Logon type descriptions
    LOGON_TYPE_MAPPING = {
        "2": "Interactive",
        "3": "Network",
        "4": "Batch",
        "5": "Service",
        "7": "Unlock",
        "8": "NetworkCleartext",
        "9": "NewCredentials",
        "10": "RemoteInteractive",
        "11": "CachedInteractive",
    }

    def __init__(self):
        logger.debug("Initialized LogonsAnalyzer")

    async def analyze(
        self,
        db: AsyncSession,
        investigation_id: UUID,
        logon_types: Optional[List[str]] = None,
        source_ips: Optional[List[str]] = None,
        usernames: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[LogonEntry]:
        """
        Analyze logon events from Windows Event Logs and application logs.

        Args:
            db: Database session
            investigation_id: UUID of the investigation
            logon_types: Optional filter for logon types (e.g., ["Interactive", "Network"])
            source_ips: Optional filter for source IP addresses
            usernames: Optional filter for specific usernames
            use_cache: Whether to use cached results

        Returns:
            List of LogonEntry objects
        """
        # Check cache first
        if use_cache:
            logger.debug(f"Checking cache for investigation {investigation_id} with filters: logon_types={logon_types}, source_ips={source_ips}, usernames={usernames}")
            cached = await self._get_cached_results(investigation_id, logon_types, source_ips, usernames)
            if cached:
                logger.debug(f"Returning {len(cached)} cached logon entries (fast path)")
                return cached
            else:
                logger.debug("No cached results found, running fresh analysis")

        entries: List[LogonEntry] = []

        logger.debug(f"Analyzing logon events for investigation {investigation_id}")

        # Query Windows Event Log events
        event_log_entries = await self._query_event_logs(
            db=db,
            investigation_id=investigation_id,
            logon_types=logon_types,
            source_ips=source_ips,
            usernames=usernames,
        )
        entries.extend(event_log_entries)

        logger.debug(f"Total logon entries found: {len(entries)}")

        # Cache results
        if use_cache and len(entries) > 0:
            await self._cache_results(investigation_id, logon_types, source_ips, usernames, entries)

        return entries

    async def _query_event_logs(
        self,
        db: AsyncSession,
        investigation_id: UUID,
        logon_types: Optional[List[str]] = None,
        source_ips: Optional[List[str]] = None,
        usernames: Optional[List[str]] = None,
    ) -> List[LogonEntry]:
        """Query Windows Event Log events for logon/logoff events."""
        entries: List[LogonEntry] = []

        try:
            # Build event type patterns for logon-related events
            # EVTX parser creates event types like: evtx_security_4624, evtx_security_4625, etc.
            event_ids = list(self.EVENT_ID_MAPPING.keys())
            event_type_patterns = []
            for eid in event_ids:
                event_type_patterns.append(f"evtx_security_{eid}")
            
            # Build base query for event logs using event_type patterns
            placeholders = ", ".join([f":etype_{i}" for i in range(len(event_type_patterns))])
            query = f"""
                SELECT event_id, event_ts, payload
                FROM events
                WHERE investigation_id = :investigation_id
                  AND event_type IN ({placeholders})
                ORDER BY event_ts DESC
                LIMIT 10000
            """

            params: Dict[str, Any] = {
                "investigation_id": str(investigation_id),
            }

            # Add event type parameters
            for i, etype in enumerate(event_type_patterns):
                params[f"etype_{i}"] = etype

            result = await db.execute(text(query), params)
            rows = result.fetchall()

            logger.debug(f"Found {len(rows)} event log entries")

            # Process results
            for row in rows:
                event_id, event_ts, payload = row[0], row[1], row[2]

                entry = self._create_entry_from_event_log(
                    event_id=event_id,
                    timestamp=event_ts.isoformat() if event_ts else None,
                    payload=payload,
                )

                if entry:
                    # Apply filters
                    if logon_types and entry.logon_type not in logon_types:
                        continue
                    
                    # Source IP filter: skip if filter is active and entry doesn't match
                    if source_ips:
                        # If entry has no source_ip, skip it (can't match filter)
                        if not entry.source_ip:
                            continue
                        # If entry has source_ip but it's not in the filter list, skip it
                        if entry.source_ip not in source_ips:
                            continue
                    
                    # Username filter: skip if filter is active and entry doesn't match
                    if usernames:
                        # If entry has no username or it's not in the filter list, skip it
                        if not entry.username or entry.username not in usernames:
                            continue

                    entries.append(entry)

        except Exception as e:
            logger.error(f"Failed to query event logs: {sanitize_log_message(str(e))}", exc_info=True)

        return entries

    def _create_entry_from_event_log(
        self,
        event_id: int,
        timestamp: Optional[str],
        payload: Dict[str, Any],
    ) -> Optional[LogonEntry]:
        """Create LogonEntry from Windows Event Log event."""
        try:
            # Extract Event ID from payload (EVTX parser uses 'event_id' field)
            event_record_id = payload.get("event_id")
            if event_record_id is None:
                return None

            event_record_id = int(event_record_id)

            # Determine event action
            event_action = self.EVENT_ID_MAPPING.get(event_record_id, "Unknown")

            # Extract common fields from event_data namespace (flattened with dots)
            # EVTX parser creates fields like: event_data.TargetUserName, event_data.LogonType, etc.
            username = (
                payload.get("event_data.TargetUserName") 
                or payload.get("event_data.SubjectUserName") 
                or "Unknown"
            )
            domain = (
                payload.get("event_data.TargetDomainName") 
                or payload.get("event_data.SubjectDomainName")
            )
            logon_id = (
                payload.get("event_data.TargetLogonId") 
                or payload.get("event_data.SubjectLogonId")
            )

            # Extract logon type
            logon_type_code = payload.get("event_data.LogonType")
            if logon_type_code:
                logon_type = self.LOGON_TYPE_MAPPING.get(str(logon_type_code), f"Type {logon_type_code}")
            else:
                logon_type = "Unknown"

            # Extract source IP and hostname
            source_ip = self._extract_ip_address(payload)
            source_host = (
                payload.get("event_data.WorkstationName") 
                or payload.get("event_data.SourceNetworkAddress")
            )

            # Extract authentication details
            logon_process = payload.get("event_data.LogonProcessName")
            authentication_package = payload.get("event_data.AuthenticationPackageName")

            # Extract failure details (for failed logons)
            failure_reason = payload.get("event_data.FailureReason")
            status_code = (
                payload.get("event_data.Status") 
                or payload.get("event_data.SubStatus")
            )

            # Filter out system/anonymous logons unless they're failures
            if event_action != "Failed Logon":
                if username.lower() in ["system", "anonymous logon", "local service", "network service", "-"]:
                    return None

            return LogonEntry(
                logon_type=logon_type,
                event_action=event_action,
                username=username,
                domain=domain,
                logon_id=logon_id,
                source_ip=source_ip,
                source_host=source_host,
                timestamp=timestamp,
                event_id=event_id,
                event_record_id=event_record_id,
                logon_process=logon_process,
                authentication_package=authentication_package,
                failure_reason=failure_reason,
                status_code=status_code,
                raw_data=payload,
            )

        except Exception as e:
            logger.warning(f"Failed to create LogonEntry from event log: {sanitize_log_message(str(e))}")
            return None

    def _extract_ip_address(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract IP address from various event log fields."""
        # Try common field names (with event_data. prefix for flattened structure)
        ip_fields = [
            "event_data.IpAddress",
            "event_data.SourceAddress",
            "event_data.SourceNetworkAddress",
            "event_data.IpPort",  # May contain IP:Port
        ]

        for field in ip_fields:
            value = payload.get(field)
            if value and isinstance(value, str):
                # Clean up IP address
                value = value.strip()

                # Remove port if present (e.g., "192.168.1.1:3389")
                if ":" in value:
                    value = value.split(":")[0]

                # Validate IP format
                if self._is_valid_ip(value):
                    # Filter out local/loopback addresses
                    if value not in ["127.0.0.1", "::1", "-", "0.0.0.0"]:
                        return value

        return None

    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is a valid IPv4 or IPv6 address."""
        # IPv4 pattern
        ipv4_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        if re.match(ipv4_pattern, ip):
            # Validate octets are 0-255
            octets = ip.split(".")
            return all(0 <= int(octet) <= 255 for octet in octets)

        # IPv6 pattern (simplified)
        ipv6_pattern = r"^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$"
        if re.match(ipv6_pattern, ip):
            return True

        return False

    def get_filter_categories(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get available filter categories for the UI.

        Returns:
            Dictionary with three categories:
            - logon_types: List of logon type filters
            - source_ips: Placeholder for dynamic IP filters (populated from data)
            - logon_ids: Placeholder for dynamic logon ID filters (populated from data)
        """
        return {
            "logon_types": [
                {
                    "key": "Interactive",
                    "name": "Interactive",
                    "description": "Local keyboard/screen logons",
                    "icon": "user",
                },
                {
                    "key": "Network",
                    "name": "Network",
                    "description": "Network logons (file shares, etc.)",
                    "icon": "globe-alt",
                },
                {
                    "key": "RemoteInteractive",
                    "name": "Remote Interactive",
                    "description": "RDP/Terminal Services logons",
                    "icon": "computer-desktop",
                },
                {
                    "key": "Service",
                    "name": "Service",
                    "description": "Service account logons",
                    "icon": "cog",
                },
                {
                    "key": "Batch",
                    "name": "Batch",
                    "description": "Scheduled task logons",
                    "icon": "clock",
                },
                {
                    "key": "Unlock",
                    "name": "Unlock",
                    "description": "Workstation unlock events",
                    "icon": "lock-open",
                },
                {
                    "key": "NetworkCleartext",
                    "name": "Network Cleartext",
                    "description": "Network logons with cleartext credentials",
                    "icon": "shield-exclamation",
                },
                {
                    "key": "NewCredentials",
                    "name": "New Credentials",
                    "description": "RunAs with different credentials",
                    "icon": "key",
                },
                {
                    "key": "CachedInteractive",
                    "name": "Cached Interactive",
                    "description": "Logons using cached credentials",
                    "icon": "server",
                },
            ],
            "source_ips": [],  # Populated dynamically from data
            "usernames": [],  # Populated dynamically from data
        }

    async def get_dynamic_filters(
        self, db: AsyncSession, investigation_id: UUID
    ) -> Dict[str, List[str]]:
        """
        Get dynamic filter values (IPs and Logon IDs) from actual data.

        Args:
            db: Database session
            investigation_id: UUID of the investigation

        Returns:
            Dictionary with 'source_ips' and 'logon_ids' lists
        """
        try:
            # Query for unique source IPs from all possible IP fields
            # This matches the fields checked in _extract_ip_address()
            ip_query = """
                SELECT DISTINCT ip FROM (
                    SELECT payload->>'event_data.IpAddress' as ip FROM events
                    WHERE investigation_id = :investigation_id
                      AND event_type LIKE 'evtx_security_%'
                      AND payload->>'event_data.IpAddress' IS NOT NULL
                    UNION
                    SELECT payload->>'event_data.SourceAddress' as ip FROM events
                    WHERE investigation_id = :investigation_id
                      AND event_type LIKE 'evtx_security_%'
                      AND payload->>'event_data.SourceAddress' IS NOT NULL
                    UNION
                    SELECT payload->>'event_data.SourceNetworkAddress' as ip FROM events
                    WHERE investigation_id = :investigation_id
                      AND event_type LIKE 'evtx_security_%'
                      AND payload->>'event_data.SourceNetworkAddress' IS NOT NULL
                    UNION
                    SELECT SPLIT_PART(payload->>'event_data.IpPort', ':', 1) as ip FROM events
                    WHERE investigation_id = :investigation_id
                      AND event_type LIKE 'evtx_security_%'
                      AND payload->>'event_data.IpPort' IS NOT NULL
                      AND payload->>'event_data.IpPort' LIKE '%:%'
                ) AS all_ips
                WHERE ip IS NOT NULL
                  AND ip != '-'
                  AND ip != '127.0.0.1'
                  AND ip != '::1'
                  AND ip != '0.0.0.0'
                ORDER BY ip
                LIMIT 100
            """

            ip_result = await db.execute(text(ip_query), {"investigation_id": str(investigation_id)})
            source_ips = [row[0] for row in ip_result.fetchall() if row[0]]

            # Query for unique usernames
            username_query = """
                SELECT DISTINCT payload->>'event_data.TargetUserName' as username
                FROM events
                WHERE investigation_id = :investigation_id
                  AND event_type LIKE 'evtx_security_%'
                  AND payload->>'event_data.TargetUserName' IS NOT NULL
                  AND LOWER(payload->>'event_data.TargetUserName') NOT IN ('system', 'anonymous logon', 'local service', 'network service', '-')
                ORDER BY username
                LIMIT 100
            """

            username_result = await db.execute(
                text(username_query), {"investigation_id": str(investigation_id)}
            )
            usernames = [row[0] for row in username_result.fetchall() if row[0]]

            return {
                "source_ips": source_ips,
                "usernames": usernames,
            }

        except Exception as e:
            logger.error(f"Failed to get dynamic filters: {sanitize_log_message(str(e))}", exc_info=True)
            return {
                "source_ips": [],
                "usernames": [],
            }

    async def _get_cached_results(
        self,
        investigation_id: UUID,
        logon_types: Optional[List[str]],
        source_ips: Optional[List[str]],
        usernames: Optional[List[str]],
    ) -> Optional[List[LogonEntry]]:
        """Retrieve cached results if available and valid."""
        try:
            async with async_session_factory() as db:
                # Build parameters for cache key
                params_dict = {
                    "logon_types": sorted(logon_types) if logon_types else None,
                    "source_ips": sorted(source_ips) if source_ips else None,
                    "usernames": sorted(usernames) if usernames else None,
                }
                params_json = json.dumps(params_dict, sort_keys=True)

                query = """
                    SELECT results, created_at, event_count_when_cached
                    FROM analysis_results
                    WHERE investigation_id = :investigation_id
                      AND analysis_type = 'logons'
                      AND analysis_version = :version
                      AND parameters = CAST(:parameters AS jsonb)
                    ORDER BY created_at DESC
                    LIMIT 1
                """

                result = await db.execute(
                    text(query),
                    {
                        "investigation_id": str(investigation_id),
                        "version": ANALYSIS_VERSION,
                        "parameters": params_json,
                    },
                )

                row = result.fetchone()
                if not row:
                    logger.debug(f"No cache match found for params: {params_json}")
                    return None

                results_json = row[0]
                created_at = row[1]
                cached_event_count = row[2]

                # Check if event count has changed since caching
                current_count_query = text(
                    """
                        SELECT COUNT(*) as count
                        FROM events
                        WHERE investigation_id = :investigation_id
                    """
                )
                count_result = await db.execute(current_count_query, {"investigation_id": str(investigation_id)})
                current_event_count = count_result.scalar() or 0

                if cached_event_count != current_event_count:
                    logger.debug(
                        f"Cache stale: event count changed from {cached_event_count} to {current_event_count}. "
                        f"Returning None to trigger refresh."
                    )
                    return None

                logger.debug(f"Found cached logon results from {created_at} ({len(results_json)} entries, event count: {cached_event_count})")

                # Convert JSON back to LogonEntry objects
                entries = []
                for entry_dict in results_json:
                    entries.append(LogonEntry(**entry_dict))

                return entries

        except Exception as e:
            logger.warning(f"Failed to retrieve cached results: {sanitize_log_message(str(e))}")
            return None

    async def _cache_results(
        self,
        investigation_id: UUID,
        logon_types: Optional[List[str]],
        source_ips: Optional[List[str]],
        usernames: Optional[List[str]],
        entries: List[LogonEntry],
    ) -> None:
        """Cache analysis results permanently."""
        try:
            async with async_session_factory() as cache_db:
                # Build parameters for cache key
                params_dict = {
                    "logon_types": sorted(logon_types) if logon_types else None,
                    "source_ips": sorted(source_ips) if source_ips else None,
                    "usernames": sorted(usernames) if usernames else None,
                }
                params_json = json.dumps(params_dict, sort_keys=True)

                # Convert entries to JSON
                results_json = json.dumps([entry.to_dict() for entry in entries])

                # Extract unique values for metadata
                logon_types_analyzed = list(set(entry.logon_type for entry in entries))

                # Get current event count for cache invalidation tracking
                count_query = text(
                    """
                        SELECT COUNT(*) as count
                        FROM events
                        WHERE investigation_id = :investigation_id
                    """
                )
                count_result = await cache_db.execute(count_query, {"investigation_id": str(investigation_id)})
                current_event_count = count_result.scalar() or 0

                # Insert or update cache (no expiration - permanent until events change)
                query = """
                    INSERT INTO analysis_results (
                        investigation_id, analysis_type, analysis_version, parameters,
                        results, entry_count, categories_analyzed, event_count_when_cached
                    )
                    VALUES (
                        :investigation_id, 'logons', :version, CAST(:parameters AS jsonb),
                        CAST(:results AS jsonb), :entry_count, :categories_analyzed, :event_count_when_cached
                    )
                    ON CONFLICT (investigation_id, analysis_type, parameters)
                    DO UPDATE SET
                        analysis_version = EXCLUDED.analysis_version,
                        results = EXCLUDED.results,
                        entry_count = EXCLUDED.entry_count,
                        categories_analyzed = EXCLUDED.categories_analyzed,
                        event_count_when_cached = EXCLUDED.event_count_when_cached,
                        created_at = NOW()
                """

                await cache_db.execute(
                    text(query),
                    {
                        "investigation_id": str(investigation_id),
                        "version": ANALYSIS_VERSION,
                        "parameters": params_json,
                        "results": results_json,
                        "entry_count": len(entries),
                        "categories_analyzed": logon_types_analyzed,
                        "event_count_when_cached": current_event_count,
                    },
                )
                await cache_db.commit()

                logger.debug(f"Cached {len(entries)} logon entries permanently (event count: {current_event_count})")

        except Exception as e:
            logger.error(f"Failed to cache results: {sanitize_log_message(str(e))}", exc_info=True)


__all__ = ["LogonsAnalyzer", "LogonEntry"]
