from typing import List, Dict, Any, Optional
from pathlib import Path
from uuid import UUID
import json
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message
from app.core.database import async_session_factory

logger = get_logger(__name__)

ANALYSIS_VERSION = "1.0"  # Increment when query logic changes to invalidate cache


class UserActivityEntry:
    """Represents a single user activity entry."""

    def __init__(
        self,
        category: str,
        description: str,
        timestamp_meaning: str,
        activity_description: str,
        timestamp: Optional[str] = None,
        event_id: Optional[int] = None,
        artifact_sequence_id: Optional[int] = None,
        user_context: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ):
        self.category = category
        self.description = description
        self.timestamp_meaning = timestamp_meaning
        self.activity_description = activity_description
        self.timestamp = timestamp
        self.event_id = event_id
        self.artifact_sequence_id = artifact_sequence_id
        self.user_context = user_context
        self.additional_data = additional_data or {}
        self.raw_data = raw_data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category,
            "description": self.description,
            "timestamp_meaning": self.timestamp_meaning,
            "activity_description": self.activity_description,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "artifact_sequence_id": self.artifact_sequence_id,
            "user_context": self.user_context,
            "additional_data": self.additional_data,
            "raw_data": self.raw_data,
        }


class UserActivityAnalyzer:
    """Analyzes Windows user activity artifacts."""

    # Category metadata with descriptions and timestamp meanings
    CATEGORIES = {
        "shellbags": {
            "name": "ShellBags",
            "description": "Windows Explorer folder browsing history - Tracks which folders users have opened and their view preferences",
            "timestamp_meaning": "Last time folder was accessed via Windows Explorer",
            "event_type": "registry_shellbags_ntuser",
        },
        "recentdocs": {
            "name": "RecentDocs",
            "description": "Recently opened documents - Tracks files opened via Windows Explorer or File Open dialogs",
            "timestamp_meaning": "Last time document was opened",
            "event_type": "registry_recentdocs",
        },
        "opensavemru": {
            "name": "OpenSaveMRU",
            "description": "Open/Save dialog history - Tracks files and folders accessed via application Open/Save dialogs",
            "timestamp_meaning": "Last time file/folder was selected in Open/Save dialog",
            "event_type": "registry_opensavemru",
        },
        "lastvisitedmru": {
            "name": "LastVisitedMRU",
            "description": "Last Visited locations - Tracks which applications opened which files and from which directories",
            "timestamp_meaning": "Last time application opened a file from specific location",
            "event_type": "registry_lastvisitedmru",
        },
        "typedpaths": {
            "name": "TypedPaths",
            "description": "Manually typed paths in Windows Explorer address bar",
            "timestamp_meaning": "Registry key last modified time",
            "event_type": "registry_typedpaths",
        },
        "runmru": {
            "name": "RunMRU",
            "description": "Run dialog history - Commands executed via Win+R Run dialog",
            "timestamp_meaning": "Last time command was executed via Run dialog",
            "event_type": "registry_runmru",
        },
        "wordwheelquery": {
            "name": "WordWheelQuery",
            "description": "Windows Search queries - Search terms entered in Windows Search/Cortana",
            "timestamp_meaning": "Last time search term was used",
            "event_type": "registry_wordwheelquery",
        },
    }

    def __init__(self):
        logger.debug(f"Initialized UserActivityAnalyzer with {len(self.CATEGORIES)} categories")

    async def analyze(
        self,
        db: AsyncSession,
        investigation_id: UUID,
        categories: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[UserActivityEntry]:
        """Analyze user activity artifacts."""
        # Check cache first
        if use_cache:
            cached = await self._get_cached_results(investigation_id, categories)
            if cached:
                logger.debug(f"Returning {len(cached)} cached user activity entries (fast path)")
                return cached

        entries: List[UserActivityEntry] = []

        # Determine which categories to analyze
        if categories:
            categories_to_analyze = {k: v for k, v in self.CATEGORIES.items() if k in categories}
        else:
            categories_to_analyze = self.CATEGORIES

        logger.debug(
            f"Analyzing {len(categories_to_analyze)} user activity categories for investigation {investigation_id}"
        )

        # Log what event types we're looking for
        event_types_to_query = [info["event_type"] for info in categories_to_analyze.values()]
        logger.debug(f"Looking for event types: {event_types_to_query}")

        # Analyze each category
        for category_key, category_info in categories_to_analyze.items():
            logger.debug(f"Analyzing category: {category_info['name']}")

            category_entries = await self._query_category(
                db=db,
                investigation_id=investigation_id,
                category_key=category_key,
                category_info=category_info,
            )
            entries.extend(category_entries)

        logger.debug(f"Total user activity entries found: {len(entries)}")

        # Cache results
        if use_cache and len(entries) > 0:
            await self._cache_results(investigation_id, categories, entries)

        return entries

    async def _query_category(
        self,
        db: AsyncSession,
        investigation_id: UUID,
        category_key: str,
        category_info: Dict[str, Any],
    ) -> List[UserActivityEntry]:
        """Query events for a specific user activity category."""
        entries: List[UserActivityEntry] = []
        event_type = category_info["event_type"]

        try:
            query = """
                SELECT event_id, event_ts, payload
                FROM events
                WHERE investigation_id = :investigation_id
                  AND event_type = :event_type
                ORDER BY event_ts DESC
                LIMIT 50000
            """

            params = {
                "investigation_id": str(investigation_id),
                "event_type": event_type,
            }

            result = await db.execute(text(query), params)
            rows = result.fetchall()

            logger.debug(f"Category '{category_info['name']}' (event_type='{event_type}') returned {len(rows)} events")

            # Process results
            for row in rows:
                event_id, event_ts, payload = row[0], row[1], row[2]

                # Extract artifact_sequence_id from payload if it exists
                artifact_sequence_id = payload.get("artifact_sequence_id")

                entry = self._create_entry(
                    category_key=category_key,
                    category_info=category_info,
                    event_id=event_id,
                    timestamp=event_ts.isoformat() if event_ts else None,
                    artifact_sequence_id=artifact_sequence_id,
                    payload=payload,
                )

                if entry:
                    entries.append(entry)

        except Exception as e:
            logger.error(
                f"Failed to query category '{sanitize_log_message(category_info['name'])}': {sanitize_log_message(str(e))}",
                exc_info=True
            )
            # Rollback the transaction to prevent poisoning subsequent queries
            try:
                await db.rollback()
            except Exception as rollback_error:
                logger.warning(f"Failed to rollback transaction: {sanitize_log_message(str(rollback_error))}")

        return entries

    def _create_entry(
        self,
        category_key: str,
        category_info: Dict[str, Any],
        event_id: int,
        timestamp: Optional[str],
        artifact_sequence_id: Optional[int],
        payload: Dict[str, Any],
    ) -> Optional[UserActivityEntry]:
        """Create UserActivityEntry from event data."""
        try:
            # Extract activity description based on category
            activity_description = self._extract_activity_description(category_key, payload)
            if not activity_description:
                return None

            # Extract user context if available
            user_context = self._extract_user_context(category_key, payload)

            # Extract additional category-specific data
            additional_data = self._extract_additional_data(category_key, payload)

            return UserActivityEntry(
                category=category_info["name"],
                description=category_info["description"],
                timestamp_meaning=category_info["timestamp_meaning"],
                activity_description=activity_description,
                timestamp=timestamp,
                event_id=event_id,
                artifact_sequence_id=artifact_sequence_id,
                user_context=user_context,
                additional_data=additional_data,
                raw_data=payload,
            )

        except Exception as e:
            logger.warning(
                f"Failed to create UserActivityEntry for category '{sanitize_log_message(category_key)}': {sanitize_log_message(str(e))}"
            )
            return None

    def _extract_activity_description(self, category_key: str, payload: Dict[str, Any]) -> Optional[str]:
        """Extract activity description from payload based on category."""
        # Category-specific extraction
        if category_key == "shellbags":
            # ShellBags: folder path is the main activity
            path = payload.get("path") or payload.get("shell_bag_path") or payload.get("value_name")
            if path and isinstance(path, str) and len(path) > 0:
                return f"Browsed folder: {path}"

        elif category_key == "recentdocs":
            # RecentDocs: document name/path from parsed binary data
            # value_data contains parsed strings from PIDL structure
            doc = payload.get("value_data")
            if doc and isinstance(doc, str) and len(doc) > 0:
                # Filter out hex-only values (check if it looks like hex)
                if all(c in '0123456789abcdefABCDEF|. ' for c in doc):
                    # Looks like hex or mojibake - skip
                    return None
                return f"Opened document: {doc}"
            return None

        elif category_key == "opensavemru":
            # OpenSaveMRU: file/folder selected in dialog from parsed binary data
            item = payload.get("value_data")
            if item and isinstance(item, str) and len(item) > 0:
                # Filter out hex-only values
                if all(c in '0123456789abcdefABCDEF|. ' for c in item):
                    return None
                return f"Selected in Open/Save dialog: {item}"
            return None

        elif category_key == "lastvisitedmru":
            # LastVisitedMRU: application + file location from parsed binary data
            data = payload.get("value_data", "")
            if data and isinstance(data, str):
                # Filter out hex-only values
                if all(c in '0123456789abcdefABCDEF|. ' for c in data):
                    return None
                # Parsed data might contain multiple strings separated by |
                parts = data.split(' | ')
                if len(parts) >= 2:
                    return f"{parts[0]} opened file from: {parts[1]}"
                else:
                    return f"Opened file from: {data}"
            return None

        elif category_key == "typedpaths":
            # TypedPaths: manually typed path (usually plain text)
            path = payload.get("value_data")
            if path and isinstance(path, str) and len(path) > 0:
                return f"Typed path: {path}"

        elif category_key == "runmru":
            # RunMRU: command executed via Run dialog (usually plain text)
            command = payload.get("value_data")
            if command and isinstance(command, str) and len(command) > 0:
                # RunMRU format is often: command\1 where \1 is a separator
                # Clean it up for display
                clean_command = command.split('\\1')[0].strip()
                if clean_command:
                    return f"Executed via Run dialog: {clean_command}"

        elif category_key == "wordwheelquery":
            # WordWheelQuery: search term (usually plain text)
            query = payload.get("value_data")
            if query and isinstance(query, str) and len(query) > 0:
                return f"Searched for: {query}"

        # Fallback: try common field names
        fallback_fields = [
            "description",
            "activity",
            "path",
            "file_path",
            "value_data",
            "value_name",
        ]

        for field in fallback_fields:
            value = payload.get(field)
            if value and isinstance(value, str) and len(value) > 0:
                return value

        return None

    def _extract_user_context(self, category_key: str, payload: Dict[str, Any]) -> Optional[str]:
        """Extract user context (username, SID) from payload."""
        # Try to extract username or SID
        user_fields = ["username", "user", "user_name", "sid", "user_sid"]

        for field in user_fields:
            value = payload.get(field)
            if value and isinstance(value, str) and len(value) > 0:
                return value

        # For NTUSER.DAT artifacts, try to extract from key path
        key_path = payload.get("key_path", "")
        if "\\Users\\" in key_path:
            # Extract username from path like: HKEY_USERS\S-1-5-21-...\Software\...
            # or from file path like: C:\Users\jsmith\NTUSER.DAT
            parts = key_path.split("\\")
            for i, part in enumerate(parts):
                if part == "Users" and i + 1 < len(parts):
                    return parts[i + 1]

        return None

    def _extract_additional_data(self, category_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract category-specific additional data."""
        additional = {}

        if category_key == "shellbags":
            additional["shell_type"] = payload.get("shell_type")
            additional["slot"] = payload.get("slot")
            additional["mru_order"] = payload.get("mru_order")

        elif category_key == "recentdocs":
            additional["extension"] = payload.get("extension")
            additional["mru_position"] = payload.get("value_name")  # MRU position is the value name
            additional["raw_hex"] = payload.get("value_data_hex")  # Raw binary data for reference

        elif category_key == "opensavemru":
            additional["application"] = payload.get("application")
            additional["file_extension"] = payload.get("extension")
            additional["mru_position"] = payload.get("value_name")
            additional["raw_hex"] = payload.get("value_data_hex")

        elif category_key == "lastvisitedmru":
            additional["application"] = payload.get("application")
            additional["executable"] = payload.get("executable")
            additional["mru_position"] = payload.get("value_name")
            additional["raw_hex"] = payload.get("value_data_hex")

        elif category_key == "runmru":
            additional["mru_position"] = payload.get("value_name")

        elif category_key == "wordwheelquery":
            additional["mru_position"] = payload.get("value_name")

        # Common fields for all categories
        additional["key_path"] = payload.get("key_path")
        additional["last_modified"] = payload.get("last_modified")

        # Remove None values
        return {k: v for k, v in additional.items() if v is not None}

    def get_categories(self) -> List[Dict[str, Any]]:
        """Get list of available user activity categories."""
        categories = []
        for key, info in self.CATEGORIES.items():
            categories.append(
                {
                    "key": key,
                    "name": info["name"],
                    "description": info["description"],
                    "timestamp_meaning": info["timestamp_meaning"],
                }
            )
        return categories

    async def _get_cached_results(
        self, investigation_id: UUID, categories: Optional[List[str]]
    ) -> Optional[List[UserActivityEntry]]:
        """Retrieve cached results if available and valid."""
        try:
            async with async_session_factory() as db:
                # Build parameters for cache key
                params_dict = {"categories": sorted(categories) if categories else None}
                params_json = json.dumps(params_dict, sort_keys=True)

                query = """
                    SELECT results, created_at, event_count_when_cached
                    FROM analysis_results
                    WHERE investigation_id = :investigation_id
                      AND analysis_type = 'user_activity'
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

                logger.debug(
                    f"Found cached user activity results from {created_at} ({len(results_json)} entries, event count: {cached_event_count})"
                )

                # Convert JSON back to UserActivityEntry objects
                entries = []
                for entry_dict in results_json:
                    entries.append(UserActivityEntry(**entry_dict))

                return entries

        except Exception as e:
            logger.warning(f"Failed to retrieve cached results: {sanitize_log_message(str(e))}")
            return None

    async def _cache_results(
        self, investigation_id: UUID, categories: Optional[List[str]], entries: List[UserActivityEntry]
    ) -> None:
        """Cache analysis results permanently."""
        try:
            async with async_session_factory() as cache_db:
                # Build parameters for cache key
                params_dict = {"categories": sorted(categories) if categories else None}
                params_json = json.dumps(params_dict, sort_keys=True)

                # Convert entries to JSON
                results_json = json.dumps([entry.to_dict() for entry in entries])

                # Extract categories from entries
                categories_analyzed = list(set(entry.category for entry in entries))

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
                        :investigation_id, 'user_activity', :version, CAST(:parameters AS jsonb),
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
                        "categories_analyzed": categories_analyzed,
                        "event_count_when_cached": current_event_count,
                    },
                )
                await cache_db.commit()

                logger.debug(
                    f"Cached {len(entries)} user activity entries permanently (event count: {current_event_count})"
                )

        except Exception as e:
            logger.error(f"Failed to cache results: {sanitize_log_message(str(e))}", exc_info=True)
            # Don't fail the analysis if caching fails


__all__ = ["UserActivityAnalyzer", "UserActivityEntry"]
