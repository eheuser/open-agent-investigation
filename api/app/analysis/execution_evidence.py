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


class ExecutionEntry:
    """Represents a single execution evidence entry."""

    def __init__(
        self,
        category: str,
        description: str,
        timestamp_meaning: str,
        executable_path: str,
        timestamp: Optional[str] = None,
        event_id: Optional[int] = None,
        artifact_sequence_id: Optional[int] = None,
        proves_execution: bool = False,
        proves_presence: bool = False,
        additional_data: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ):
        self.category = category
        self.description = description
        self.timestamp_meaning = timestamp_meaning
        self.executable_path = executable_path
        self.timestamp = timestamp
        self.event_id = event_id
        self.artifact_sequence_id = artifact_sequence_id
        self.proves_execution = proves_execution
        self.proves_presence = proves_presence
        self.additional_data = additional_data or {}
        self.raw_data = raw_data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category,
            "description": self.description,
            "timestamp_meaning": self.timestamp_meaning,
            "executable_path": self.executable_path,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "artifact_sequence_id": self.artifact_sequence_id,
            "proves_execution": self.proves_execution,
            "proves_presence": self.proves_presence,
            "additional_data": self.additional_data,
            "raw_data": self.raw_data,
        }


class ExecutionEvidenceAnalyzer:
    """Analyzes Windows execution evidence artifacts."""

    # Category metadata with descriptions and timestamp meanings
    CATEGORIES = {
        "prefetch": {
            "name": "Prefetch",
            "description": "Windows Prefetch files - Created when executables run, used to optimize application loading",
            "timestamp_meaning": "Last execution time (up to 8 execution times stored in Windows 10+)",
            "proves_execution": True,
            "proves_presence": True,
            "event_type": "prefetch_execution",
        },
        "shimcache": {
            "name": "ShimCache (AppCompatCache)",
            "description": "Application Compatibility Cache - Tracks executables run on the system for compatibility purposes",
            "timestamp_meaning": "Last modification time of the executable file",
            "proves_execution": True,
            "proves_presence": True,
            "event_type": "registry_shimcache",
        },
        "amcache": {
            "name": "AmCache",
            "description": "AmCache.hve registry hive - Records application execution, installation, and file metadata",
            "timestamp_meaning": "First execution time or file modification time",
            "proves_execution": True,
            "proves_presence": True,
            "event_type": "registry_amcache",
        },
        "userassist": {
            "name": "UserAssist",
            "description": "UserAssist registry keys - Tracks GUI-based program execution via Windows Explorer",
            "timestamp_meaning": "Last execution time",
            "proves_execution": True,
            "proves_presence": True,
            "event_type": "registry_userassist",
        },
        "pca_execution": {
            "name": "Program Compatibility Assistant",
            "description": "PCA launch events - Created when programs are executed and compatibility issues are detected",
            "timestamp_meaning": "Program execution time",
            "proves_execution": True,
            "proves_presence": True,
            "event_type": "pca_execution",
        },
        "bam_dam": {
            "name": "BAM/DAM",
            "description": "Background Activity Moderator / Desktop Activity Moderator - Windows 10+ execution tracking",
            "timestamp_meaning": "Last execution time",
            "proves_execution": True,
            "proves_presence": True,
            "event_type": "registry_bam",
        },
        "jump_lists": {
            "name": "Jump Lists",
            "description": "Recent items and tasks for applications accessed via taskbar or Start menu",
            "timestamp_meaning": "Time when file or application was accessed by the user",
            "proves_execution": True,
            "proves_presence": True,
            "event_type": "jumplist_entry",
        },
        "lnk_files": {
            "name": "LNK Files (Shortcuts)",
            "description": "Windows shortcut files containing target file metadata and access timestamps",
            "timestamp_meaning": "Target file access/modification time and LNK creation time",
            "proves_execution": False,
            "proves_presence": True,
            "event_type": "lnk_file",
        },
    }

    def __init__(self):
        logger.debug(f"Initialized ExecutionEvidenceAnalyzer with {len(self.CATEGORIES)} categories")

    async def analyze(
        self,
        db: AsyncSession,
        investigation_id: UUID,
        categories: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[ExecutionEntry]:
        """Analyze execution evidence artifacts."""
        # Check cache first
        if use_cache:
            cached = await self._get_cached_results(investigation_id, categories)
            if cached:
                logger.debug(f"Returning {len(cached)} cached execution evidence entries (fast path)")
                return cached

        entries: List[ExecutionEntry] = []

        # Determine which categories to analyze
        if categories:
            categories_to_analyze = {k: v for k, v in self.CATEGORIES.items() if k in categories}
        else:
            categories_to_analyze = self.CATEGORIES

        logger.debug(
            f"Analyzing {len(categories_to_analyze)} execution evidence categories for investigation {investigation_id}"
        )
        
        # Log what event types we're looking for
        event_types_to_query = [info["event_type"] for info in categories_to_analyze.values()]
        logger.debug(f"Looking for event types: {event_types_to_query}")
        
        # Debug: Check what event types actually exist
        try:
            debug_query = text(
                """
                SELECT event_type, COUNT(*) as count
                FROM events
                WHERE investigation_id = :investigation_id
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 20
                """
            )
            debug_result = await db.execute(debug_query, {"investigation_id": str(investigation_id)})
            debug_rows = debug_result.fetchall()
            
            if debug_rows:
                logger.debug(f"Investigation has {len(debug_rows)} event types:")
                for row in debug_rows:
                    logger.debug(f"  - {row[0]}: {row[1]} events")
            else:
                logger.warning(f"Investigation {sanitize_log_message(str(investigation_id))} has NO events at all!")
        except Exception as e:
            logger.warning(f"Failed to query event types for debugging: {sanitize_log_message(str(e))}")

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

        logger.debug(f"Total execution evidence entries found: {len(entries)}")

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
    ) -> List[ExecutionEntry]:
        """Query events for a specific execution evidence category."""
        entries: List[ExecutionEntry] = []
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

            # Process results based on category type
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
            logger.error(f"Failed to query category '{sanitize_log_message(category_info['name'])}': {sanitize_log_message(str(e))}", exc_info=True)
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
    ) -> Optional[ExecutionEntry]:
        """Create ExecutionEntry from event data."""
        try:
            # Extract executable path based on category
            executable_path = self._extract_executable_path(category_key, payload)
            if not executable_path:
                return None

            # Extract additional category-specific data
            additional_data = self._extract_additional_data(category_key, payload)

            return ExecutionEntry(
                category=category_info["name"],
                description=category_info["description"],
                timestamp_meaning=category_info["timestamp_meaning"],
                executable_path=executable_path,
                timestamp=timestamp,
                event_id=event_id,
                artifact_sequence_id=artifact_sequence_id,
                proves_execution=category_info["proves_execution"],
                proves_presence=category_info["proves_presence"],
                additional_data=additional_data,
                raw_data=payload,
            )

        except Exception as e:
            logger.warning(f"Failed to create ExecutionEntry for category '{sanitize_log_message(category_key)}': {sanitize_log_message(str(e))}")
            return None

    def _extract_executable_path(self, category_key: str, payload: Dict[str, Any]) -> Optional[str]:
        """Extract executable path from payload based on category."""
        # Category-specific extraction based on actual field structures from diagnostic output
        if category_key == "prefetch":
            # Prefetch: executable_name, file_path, original_path
            return payload.get("executable_name") or payload.get("file_path")
        elif category_key == "shimcache":
            # ShimCache: path field (from regipy plugin)
            return payload.get("path") or payload.get("file_path")
        elif category_key == "amcache":
            # AmCache: name field is primary, lower_case_long_path is secondary
            return payload.get("name") or payload.get("lower_case_long_path")
        elif category_key == "userassist":
            # UserAssist: name field
            return payload.get("name")
        elif category_key == "pca_execution":
            # PCA: executable_path, executable_name, file_name
            return payload.get("executable_path") or payload.get("executable_name") or payload.get("file_name")
        elif category_key == "bam_dam":
            # BAM/DAM: executable field
            return payload.get("executable")
        elif category_key == "jump_lists":
            # JumpLists: target_path, file_path
            return payload.get("target_path") or payload.get("file_path")
        elif category_key == "lnk_files":
            # LNK files: complex nested structure
            # Check link_info.local_base_path, data.relative_path
            local_base = payload.get("link_info.local_base_path")
            if local_base:
                return local_base
            return payload.get("data.relative_path") or payload.get("target_path")

        # Generic fallback for unknown categories
        path_fields = [
            "path",
            "file_path",
            "executable_path",
            "image_path",
            "name",
        ]

        for field in path_fields:
            value = payload.get(field)
            if value and isinstance(value, str) and len(value) > 0:
                return value

        return None

    def _extract_additional_data(self, category_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract category-specific additional data based on actual field structures."""
        additional = {}

        if category_key == "prefetch":
            # Prefetch fields: executable_name, file_path, file_size, last_execution_time, original_path
            additional["file_size"] = payload.get("file_size")
            additional["last_execution_time"] = payload.get("last_execution_time")
            additional["original_path"] = payload.get("original_path")

        elif category_key == "shimcache":
            # ShimCache fields: path, timestamp, plugin
            additional["plugin"] = payload.get("plugin")

        elif category_key == "amcache":
            # AmCache fields: name, sha1, size, version, publisher, usn, link_date, product_name, language, binary_type, etc.
            additional["sha1"] = payload.get("sha1")
            additional["file_size"] = payload.get("size")
            additional["publisher"] = payload.get("publisher")
            additional["version"] = payload.get("version")
            additional["binary_type"] = payload.get("binary_type")
            additional["usn"] = payload.get("usn")
            additional["link_date"] = payload.get("link_date")
            additional["product_name"] = payload.get("product_name")
            additional["language"] = payload.get("language")
            additional["file_id"] = payload.get("file_id")
            additional["program_id"] = payload.get("program_id")
            additional["original_file_name"] = payload.get("original_file_name")

        elif category_key == "userassist":
            # UserAssist fields: name, run_counter, focus_count, total_focus_time_ms, session_id, timestamp
            additional["run_counter"] = payload.get("run_counter")
            additional["focus_count"] = payload.get("focus_count")
            additional["total_focus_time_ms"] = payload.get("total_focus_time_ms")
            additional["session_id"] = payload.get("session_id")

        elif category_key == "pca_execution":
            # PCA fields: file_name, file_path, file_size, artifact_type, executable_name, executable_path
            additional["file_size"] = payload.get("file_size")
            additional["file_name"] = payload.get("file_name")
            additional["artifact_type"] = payload.get("artifact_type")

        elif category_key == "bam_dam":
            # BAM/DAM fields: executable, sid, timestamp, sequence_number, version, key_path, plugin
            additional["sid"] = payload.get("sid")
            additional["sequence_number"] = payload.get("sequence_number")
            additional["version"] = payload.get("version")
            additional["key_path"] = payload.get("key_path")
            additional["plugin"] = payload.get("plugin")

        elif category_key == "jump_lists":
            # JumpList fields: app_id, file_path, stream_name, target_path, jumplist_type, lnk_data.*
            additional["app_id"] = payload.get("app_id")
            additional["stream_name"] = payload.get("stream_name")
            additional["jumplist_type"] = payload.get("jumplist_type")
            # LNK header data
            additional["file_size"] = payload.get("lnk_data.header.file_size")
            additional["creation_time"] = payload.get("lnk_data.header.creation_time")
            additional["accessed_time"] = payload.get("lnk_data.header.accessed_time")
            additional["modified_time"] = payload.get("lnk_data.header.modified_time")

        elif category_key == "lnk_files":
            # LNK fields: header.*, link_info.*, data.*, target.items, extra.*
            additional["file_size"] = payload.get("header.file_size")
            additional["creation_time"] = payload.get("header.creation_time")
            additional["accessed_time"] = payload.get("header.accessed_time")
            additional["modified_time"] = payload.get("header.modified_time")
            additional["working_directory"] = payload.get("data.working_directory")
            additional["relative_path"] = payload.get("data.relative_path")
            additional["drive_type"] = payload.get("link_info.location_info.drive_type")
            additional["drive_serial"] = payload.get("link_info.location_info.drive_serial_number")
            additional["volume_label"] = payload.get("link_info.location_info.volume_label")
            additional["machine_id"] = payload.get("extra.DISTRIBUTED_LINK_TRACKER_BLOCK.machine_identifier")

        # Remove None values
        return {k: v for k, v in additional.items() if v is not None}

    def get_categories(self) -> List[Dict[str, Any]]:
        """Get list of available execution evidence categories."""
        categories = []
        for key, info in self.CATEGORIES.items():
            categories.append(
                {
                    "key": key,
                    "name": info["name"],
                    "description": info["description"],
                    "timestamp_meaning": info["timestamp_meaning"],
                    "proves_execution": info["proves_execution"],
                    "proves_presence": info["proves_presence"],
                }
            )
        return categories

    async def _get_cached_results(
        self, investigation_id: UUID, categories: Optional[List[str]]
    ) -> Optional[List[ExecutionEntry]]:
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
                      AND analysis_type = 'execution_evidence'
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

                logger.debug(f"Found cached execution evidence results from {created_at} ({len(results_json)} entries, event count: {cached_event_count})")

                # Convert JSON back to ExecutionEntry objects
                entries = []
                for entry_dict in results_json:
                    entries.append(ExecutionEntry(**entry_dict))

                return entries

        except Exception as e:
            logger.warning(f"Failed to retrieve cached results: {sanitize_log_message(str(e))}")
            return None

    async def _cache_results(
        self, investigation_id: UUID, categories: Optional[List[str]], entries: List[ExecutionEntry]
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
                        :investigation_id, 'execution_evidence', :version, CAST(:parameters AS jsonb),
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

                logger.debug(f"Cached {len(entries)} execution evidence entries permanently (event count: {current_event_count})")

        except Exception as e:
            logger.error(f"Failed to cache results: {sanitize_log_message(str(e))}", exc_info=True)
            # Don't fail the analysis if caching fails


__all__ = ["ExecutionEvidenceAnalyzer", "ExecutionEntry"]
