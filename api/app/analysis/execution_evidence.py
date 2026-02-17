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
        "srum": {
            "name": "SRUM Database",
            "description": "System Resource Usage Monitor - Tracks application resource usage, network activity, and execution metrics",
            "timestamp_meaning": "Time when application was actively using resources",
            "proves_execution": True,
            "proves_presence": False,
            "event_type": "srum_data",
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
        # Category-specific extraction (check first for best accuracy)
        if category_key == "srum":
            # SRUM stores executable in data.IdBlob field (flattened)
            path = payload.get("data.IdBlob") or payload.get("app_id") or payload.get("application")
            if path and isinstance(path, str) and len(path) > 0:
                return path
        elif category_key == "shimcache":
            return payload.get("path") or payload.get("file_path")
        elif category_key == "amcache":
            return payload.get("file_path") or payload.get("full_path")
        elif category_key == "prefetch":
            return payload.get("executable_name") or payload.get("file_path")
        elif category_key == "userassist":
            return payload.get("value_name") or payload.get("program_name")
        elif category_key == "bam_dam":
            return payload.get("image_path") or payload.get("executable_path")
        elif category_key == "jump_lists":
            return payload.get("target_path") or payload.get("file_path")
        elif category_key == "lnk_files":
            return payload.get("target_path") or payload.get("local_path")
        elif category_key == "syscache":
            return payload.get("file_path") or payload.get("path")
        elif category_key == "shimdb":
            return payload.get("database_path") or payload.get("shim_name")

        # Common field names for executable paths (fallback)
        path_fields = [
            "path",
            "file_path",
            "executable_path",
            "image_path",
            "application_path",
            "target_path",
            "program_name",
            "app_id",
        ]

        for field in path_fields:
            value = payload.get(field)
            if value and isinstance(value, str) and len(value) > 0:
                return value

        return None

    def _extract_additional_data(self, category_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract category-specific additional data."""
        additional = {}

        if category_key == "shimcache":
            additional["file_size"] = payload.get("file_size")
            additional["insertion_flags"] = payload.get("insertion_flags")
            additional["shim_flags"] = payload.get("shim_flags")

        elif category_key == "amcache":
            additional["sha1"] = payload.get("sha1")
            additional["file_size"] = payload.get("file_size")
            additional["publisher"] = payload.get("publisher")
            additional["version"] = payload.get("version")
            additional["binary_type"] = payload.get("binary_type")

        elif category_key == "prefetch":
            additional["run_count"] = payload.get("run_count")
            additional["file_size"] = payload.get("file_size")
            additional["hash"] = payload.get("hash")
            # Prefetch can have multiple execution times
            exec_times = payload.get("execution_times", [])
            if exec_times:
                additional["execution_times"] = exec_times
                additional["last_run_time"] = exec_times[0] if len(exec_times) > 0 else None
                additional["previous_run_times"] = exec_times[1:] if len(exec_times) > 1 else []

        elif category_key == "srum":
            additional["bytes_sent"] = payload.get("bytes_sent")
            additional["bytes_received"] = payload.get("bytes_received")
            additional["network_interface"] = payload.get("interface_luid")
            additional["user_sid"] = payload.get("user_sid")

        elif category_key == "userassist":
            additional["run_count"] = payload.get("run_count")
            additional["focus_count"] = payload.get("focus_count")
            additional["focus_time"] = payload.get("focus_time")

        elif category_key == "bam_dam":
            additional["user_sid"] = payload.get("user_sid")
            additional["source"] = payload.get("source")  # BAM or DAM

        elif category_key == "jump_lists":
            additional["app_id"] = payload.get("app_id")
            additional["file_size"] = payload.get("file_size")
            additional["file_attributes"] = payload.get("file_attributes")
            additional["creation_time"] = payload.get("creation_time")
            additional["access_time"] = payload.get("access_time")
            additional["write_time"] = payload.get("write_time")

        elif category_key == "lnk_files":
            additional["file_size"] = payload.get("file_size")
            additional["file_attributes"] = payload.get("file_attributes")
            additional["creation_time"] = payload.get("creation_time")
            additional["access_time"] = payload.get("access_time")
            additional["write_time"] = payload.get("write_time")
            additional["working_directory"] = payload.get("working_directory")
            additional["command_line_args"] = payload.get("command_line_arguments")
            additional["drive_type"] = payload.get("drive_type")
            additional["volume_serial"] = payload.get("volume_serial_number")

        elif category_key == "syscache":
            additional["file_size"] = payload.get("file_size")
            additional["sha1"] = payload.get("sha1")

        elif category_key == "shimdb":
            additional["database_guid"] = payload.get("database_guid")
            additional["database_type"] = payload.get("database_type")
            additional["shim_name"] = payload.get("shim_name")
            additional["command_line"] = payload.get("command_line")

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
                    SELECT results, created_at
                    FROM analysis_results
                    WHERE investigation_id = :investigation_id
                      AND analysis_type = 'execution_evidence'
                      AND analysis_version = :version
                      AND parameters = CAST(:parameters AS jsonb)
                      AND (expires_at IS NULL OR expires_at > NOW())
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
                if row:
                    results_json = row[0]
                    created_at = row[1]
                    logger.debug(f"Found cached execution evidence results from {created_at}")

                    # Convert JSON back to ExecutionEntry objects
                    entries = []
                    for entry_dict in results_json:
                        entries.append(ExecutionEntry(**entry_dict))

                    return entries

                return None

        except Exception as e:
            logger.warning(f"Failed to retrieve cached results: {sanitize_log_message(str(e))}")
            return None

    async def _cache_results(
        self, investigation_id: UUID, categories: Optional[List[str]], entries: List[ExecutionEntry]
    ) -> None:
        """Cache analysis results."""
        try:
            async with async_session_factory() as cache_db:
                # Build parameters for cache key
                params_dict = {"categories": sorted(categories) if categories else None}
                params_json = json.dumps(params_dict, sort_keys=True)

                # Convert entries to JSON
                results_json = json.dumps([entry.to_dict() for entry in entries])

                # Extract categories from entries
                categories_analyzed = list(set(entry.category for entry in entries))

                # Set expiration (cache for 12 hour)
                expires_at = datetime.utcnow() + timedelta(hours=12)

                # Insert or update cache
                query = """
                    INSERT INTO analysis_results (
                        investigation_id, analysis_type, analysis_version, parameters,
                        results, entry_count, categories_analyzed, expires_at
                    )
                    VALUES (
                        :investigation_id, 'execution_evidence', :version, CAST(:parameters AS jsonb),
                        CAST(:results AS jsonb), :entry_count, :categories_analyzed, :expires_at
                    )
                    ON CONFLICT (investigation_id, analysis_type, parameters)
                    DO UPDATE SET
                        analysis_version = EXCLUDED.analysis_version,
                        results = EXCLUDED.results,
                        entry_count = EXCLUDED.entry_count,
                        categories_analyzed = EXCLUDED.categories_analyzed,
                        created_at = NOW(),
                        expires_at = EXCLUDED.expires_at
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
                        "expires_at": expires_at,
                    },
                )
                await cache_db.commit()

                logger.debug(f"Cached {len(entries)} execution evidence entries (expires in 12 hours)")

        except Exception as e:
            logger.error(f"Failed to cache results: {sanitize_log_message(str(e))}", exc_info=True)
            # Don't fail the analysis if caching fails


__all__ = ["ExecutionEvidenceAnalyzer", "ExecutionEntry"]
