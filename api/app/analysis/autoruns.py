from typing import List, Dict, Any, Optional
from pathlib import Path
from uuid import UUID
import yaml
import json
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.log_setup import get_logger
from app.core.database import async_session_factory

logger = get_logger(__name__)

ANALYSIS_VERSION = "1.0"  # Increment when query logic changes to invalidate cache


class AutorunEntry:
    """Represents a single autorun entry found in the system."""

    def __init__(
        self,
        category: str,
        location: str,
        entry_name: str,
        image_path: str,
        enabled: bool,
        timestamp: Optional[str] = None,
        event_id: Optional[int] = None,
        registry_path: Optional[str] = None,
        publisher: Optional[str] = None,
        description: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ):
        self.category = category
        self.location = location
        self.entry_name = entry_name
        self.image_path = image_path
        self.enabled = enabled
        self.timestamp = timestamp
        self.event_id = event_id
        self.registry_path = registry_path
        self.publisher = publisher
        self.description = description
        self.raw_data = raw_data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category,
            "location": self.location,
            "entry_name": self.entry_name,
            "image_path": self.image_path,
            "enabled": self.enabled,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "registry_path": self.registry_path,
            "publisher": self.publisher,
            "description": self.description,
            "raw_data": self.raw_data,
        }


class AutorunsAnalyzer:
    """Analyzes Windows autostart persistence mechanisms."""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config" / "autoruns_config.yaml"
        
        self.config = self._load_config(config_path)
        logger.debug(f"Loaded Autoruns config with {len(self.config.get('categories', []))} categories")

    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        try:
            if not config_path.exists():
                logger.warning(f"Config file not found: {config_path}")
                return {"categories": []}

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config or "categories" not in config:
                logger.warning(f"Invalid config file: {config_path}")
                return {"categories": []}

            return config

        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}", exc_info=True)
            return {"categories": []}

    async def analyze(
        self, db: AsyncSession, investigation_id: UUID, categories: Optional[List[str]] = None, use_cache: bool = True
    ) -> List[AutorunEntry]:
        """Analyze autostart persistence mechanisms."""
        # Check cache first (uses separate session to avoid transaction issues)
        if use_cache:
            cached = await self._get_cached_results(investigation_id, categories)
            if cached:
                logger.info(f"✓ Returning {len(cached)} cached autoruns entries (fast path)")
                return cached
        
        entries: List[AutorunEntry] = []

        # Get categories to analyze
        all_categories = self.config.get("categories", [])
        if categories:
            categories_to_analyze = [c for c in all_categories if c["name"] in categories]
        else:
            categories_to_analyze = all_categories

        logger.info(
            f"Analyzing {len(categories_to_analyze)} categories for investigation {investigation_id}"
        )

        # Analyze each category
        for category in categories_to_analyze:
            category_name = category["name"]
            logger.debug(f"Analyzing category: {category_name}")

            for location in category.get("locations", []):
                if not location.get("enabled", True):
                    continue

                location_name = location["name"]
                registry_paths = location.get("registry_paths", [])
                value_names = location.get("value_names")
                value_filters = location.get("value_filters", {})

                # Query each registry path separately
                for registry_path in registry_paths:
                    path_entries = await self._query_single_path(
                        db=db,
                        investigation_id=investigation_id,
                        category=category_name,
                        location=location_name,
                        registry_path=registry_path,
                        value_names=value_names,
                        value_filters=value_filters,
                    )
                    entries.extend(path_entries)

        logger.info(f"Total autoruns entries found: {len(entries)}")
        
        # Cache results (uses separate session to avoid transaction pollution)
        if use_cache and len(entries) > 0:
            await self._cache_results(investigation_id, categories, entries)
        
        return entries

    async def _query_single_path(
        self,
        db: AsyncSession,
        investigation_id: UUID,
        category: str,
        location: str,
        registry_path: str,
        value_names: Optional[List[str]] = None,
        value_filters: Optional[Dict[str, List[str]]] = None,
    ) -> List[AutorunEntry]:
        """Query a single registry path."""
        entries: List[AutorunEntry] = []
        
        # Normalize path
        normalized_path = registry_path.strip("\\\\")
        
        # Build query that matches path endings and excludes temp/backup locations
        # Use LIKE instead of ILIKE to avoid backslash escaping issues
        query = """
            SELECT event_id, event_ts, payload
            FROM events
            WHERE investigation_id = :investigation_id
              AND event_type = 'registry_value'
              AND (
                  -- Match paths ending with our target path (case-insensitive via LOWER)
                  LOWER(payload->>'key_path') LIKE LOWER(:path_exact)
                  -- Match paths where our target is a parent key
                  OR LOWER(payload->>'key_path') LIKE LOWER(:path_subkeys)
              )
              -- Exclude side-by-side (SXS) assemblies and other temp locations
              AND LOWER(payload->>'key_path') NOT LIKE '%winsxs%'
              AND LOWER(payload->>'key_path') NOT LIKE '%sxs%'
              AND LOWER(payload->>'key_path') NOT LIKE '%backup%'
        """
        
        # Add value name filter if specified
        if value_names:
            placeholders = ", ".join([f":vname_{i}" for i in range(len(value_names))])
            query += f" AND payload->>'value_name' IN ({placeholders})"
        
        query += " ORDER BY event_ts DESC LIMIT 10000"
        
        # Build parameters - match end of path
        # Use % wildcards between path components to avoid backslash escaping issues
        # E.g., "Microsoft\Windows\CurrentVersion\Run" -> "%CurrentVersion%Run"
        path_parts = normalized_path.split("\\")
        if len(path_parts) >= 2:
            # Use last 2 components with % wildcards between them
            pattern_exact = "%" + "%".join(path_parts[-2:])
            pattern_subkeys = "%" + "%".join(path_parts[-2:]) + "%"
        else:
            pattern_exact = "%" + normalized_path
            pattern_subkeys = "%" + normalized_path + "%"
        
        params: Dict[str, Any] = {
            "investigation_id": str(investigation_id),
            # Match paths with our target components
            "path_exact": pattern_exact,
            "path_subkeys": pattern_subkeys,
        }
        
        logger.info(f"Original path: {registry_path}")
        logger.info(f"Normalized path: {normalized_path}")
        logger.info(f"Escaped patterns: exact={params['path_exact']}, subkeys={params['path_subkeys']}")
        
        if value_names:
            for i, vname in enumerate(value_names):
                params[f"vname_{i}"] = vname
        
        # Execute
        try:
            logger.info(f"Querying normalized path: {normalized_path}")
            logger.info(f"Pattern will match: {params['path_exact']} or {params['path_subkeys']}")
            
            # Test query first
            test_query = f"SELECT COUNT(*) FROM events WHERE investigation_id = :investigation_id AND event_type = 'registry_value' AND LOWER(payload->>'key_path') LIKE LOWER(:path_exact)"
            test_result = await db.execute(text(test_query), {"investigation_id": params["investigation_id"], "path_exact": params["path_exact"]})
            test_count = test_result.scalar()
            logger.info(f"Test query for exact path returned: {test_count} events")
            
            result = await db.execute(text(query), params)
            rows = result.fetchall()
            
            logger.info(f"Path '{normalized_path}' returned {len(rows)} events (after all filters)")
            
            # Process results
            for row in rows:
                event_id, event_ts, payload = row[0], row[1], row[2]
                
                # Apply value filters
                if value_filters:
                    skip = False
                    for filter_name, allowed_values in value_filters.items():
                        actual_value = payload.get(filter_name)
                        if actual_value is not None and str(actual_value) not in allowed_values:
                            skip = True
                            break
                    if skip:
                        continue
                
                # Create entry
                entry = self._create_entry(
                    category=category,
                    location=location,
                    event_id=event_id,
                    timestamp=event_ts.isoformat() if event_ts else None,
                    payload=payload,
                )
                
                if entry:
                    entries.append(entry)
        
        except Exception as e:
            logger.error(f"Failed to query path '{normalized_path}': {e}", exc_info=True)
        
        return entries

    def _create_entry(
        self,
        category: str,
        location: str,
        event_id: int,
        timestamp: Optional[str],
        payload: Dict[str, Any],
    ) -> Optional[AutorunEntry]:
        """Create AutorunEntry from registry event."""
        try:
            key_path = payload.get("key_path", "")
            value_name = payload.get("value_name", "(Default)")
            value_data = payload.get("value_data", "")
            
            # Extract image path - preserve full command line
            image_path = str(value_data).strip('"').strip("'")
            # Don't split on spaces - keep the full command line with arguments
            
            # Filter out non-executable entries
            # Skip if value_data doesn't look like a file path or command
            if not self._is_valid_autorun_path(image_path):
                return None
            
            # Determine enabled status
            enabled = True
            if category in ["Services", "Drivers"]:
                start_value = payload.get("Start")
                if start_value is not None:
                    enabled = str(start_value) in ["0", "1", "2"]
            
            return AutorunEntry(
                category=category,
                location=location,
                entry_name=value_name,
                image_path=image_path,
                enabled=enabled,
                timestamp=timestamp,
                event_id=event_id,
                registry_path=key_path,
                raw_data=payload,
            )
        
        except Exception as e:
            logger.warning(f"Failed to create AutorunEntry: {e}")
            return None
    
    def _is_valid_autorun_path(self, path: str) -> bool:
        """Check if path looks like a valid executable/DLL path."""
        if not path or len(path) < 3:
            return False
        
        path_lower = path.lower()
        
        # Must contain path separators or be a filename
        has_path_separator = "\\" in path or "/" in path or ":" in path
        
        # Common executable extensions
        executable_extensions = [".exe", ".dll", ".sys", ".bat", ".cmd", ".vbs", ".ps1", ".msi"]
        has_executable_ext = any(path_lower.endswith(ext) for ext in executable_extensions)
        
        # Skip pure numeric values (like "0", "1", "2")
        if path.isdigit():
            return False
        
        # Skip very short values that are likely config data
        if len(path) < 5 and not has_executable_ext:
            return False
        
        # Must have either path separator OR executable extension
        return has_path_separator or has_executable_ext

    def get_categories(self) -> List[Dict[str, str]]:
        """Get list of available analysis categories."""
        categories = []
        for cat in self.config.get("categories", []):
            categories.append({"name": cat["name"], "description": cat.get("description", "")})
        return categories
    
    async def _get_cached_results(
        self, investigation_id: UUID, categories: Optional[List[str]]
    ) -> Optional[List[AutorunEntry]]:
        """Retrieve cached results if available and valid (uses separate session)."""
        try:
            # Use a fresh session for cache lookup
            async with async_session_factory() as db:
                # Build parameters for cache key
                params_dict = {
                    "categories": sorted(categories) if categories else None
                }
                params_json = json.dumps(params_dict, sort_keys=True)
                
                query = """
                    SELECT results, created_at
                    FROM analysis_results
                    WHERE investigation_id = :investigation_id
                      AND analysis_type = 'autoruns'
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
                    }
                )
                
                row = result.fetchone()
                if row:
                    results_json = row[0]
                    created_at = row[1]
                    logger.info(f"Found cached autoruns results from {created_at}")
                    
                    # Convert JSON back to AutorunEntry objects
                    entries = []
                    for entry_dict in results_json:
                        entries.append(AutorunEntry(**entry_dict))
                    
                    return entries
                
                return None
            
        except Exception as e:
            logger.warning(f"Failed to retrieve cached results: {e}")
            return None
    
    async def _cache_results(
        self, investigation_id: UUID, categories: Optional[List[str]], entries: List[AutorunEntry]
    ) -> None:
        """Cache analysis results (uses separate session to avoid transaction pollution)."""
        try:
            # Use a completely separate session for caching
            async with async_session_factory() as cache_db:
                # Build parameters for cache key
                params_dict = {
                    "categories": sorted(categories) if categories else None
                }
                params_json = json.dumps(params_dict, sort_keys=True)
                
                # Convert entries to JSON
                results_json = json.dumps([entry.to_dict() for entry in entries])
                
                # Extract categories from entries
                categories_analyzed = list(set(entry.category for entry in entries))
                
                # Set expiration (cache for 1 hour)
                expires_at = datetime.utcnow() + timedelta(hours=1)
                
                # Insert or update cache
                query = """
                    INSERT INTO analysis_results (
                        investigation_id, analysis_type, analysis_version, parameters,
                        results, entry_count, categories_analyzed, expires_at
                    )
                    VALUES (
                        :investigation_id, 'autoruns', :version, CAST(:parameters AS jsonb),
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
                    }
                )
                await cache_db.commit()
                
                logger.info(f"Cached {len(entries)} autoruns entries (expires in 1 hour)")
                
        except Exception as e:
            logger.error(f"Failed to cache results: {e}", exc_info=True)
            # Don't fail the analysis if caching fails - just log the error


__all__ = ["AutorunsAnalyzer", "AutorunEntry"]
