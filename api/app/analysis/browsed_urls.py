"""
Browsed URLs Analyzer

Analyzes browser history artifacts to identify URLs visited across different browsers.
Supports Chrome, Firefox, Edge (Chromium and Legacy).
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


@dataclass
class BrowsedURLEntry:
    """Represents a single browsed URL entry."""
    
    browser: str  # Browser name (chrome_chromium, firefox, edge_legacy)
    url: str
    title: Optional[str] = None
    visit_count: Optional[int] = None
    timestamp: Optional[str] = None
    event_id: Optional[int] = None
    artifact_sequence_id: Optional[int] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary for JSON serialization."""
        return {
            "browser": self.browser,
            "url": self.url,
            "title": self.title,
            "visit_count": self.visit_count,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "artifact_sequence_id": self.artifact_sequence_id,
            "additional_data": self.additional_data,
            "raw_data": self.raw_data,
        }


class BrowsedURLsAnalyzer:
    """
    Analyzer for browsed URLs from various browsers.
    
    This analyzer queries browser_history events and extracts URL visit information
    from Chrome, Firefox, and Edge browsers.
    """
    
    # Browser metadata
    BROWSERS = {
        "chrome_chromium": {
            "name": "Chrome/Chromium/Edge",
            "description": "Chromium-based browsers (Chrome, new Edge, Brave, etc.)",
            "icon": "chrome",
        },
        "firefox": {
            "name": "Firefox",
            "description": "Mozilla Firefox browser",
            "icon": "firefox",
        },
        "edge_legacy": {
            "name": "Edge (Legacy)",
            "description": "Legacy Microsoft Edge (pre-Chromium)",
            "icon": "edge",
        },
    }
    
    ANALYSIS_VERSION = "1.0"
    
    def __init__(self):
        """Initialize the BrowsedURLsAnalyzer."""
        pass
    
    def get_browsers(self) -> List[Dict[str, Any]]:
        """
        Get list of supported browsers with metadata.
        
        Returns:
            List of browser dictionaries with key, name, description, icon
        """
        browsers = []
        for browser_key, browser_info in self.BROWSERS.items():
            browsers.append({
                "key": browser_key,
                "name": browser_info["name"],
                "description": browser_info["description"],
                "icon": browser_info["icon"],
            })
        return browsers
    
    async def analyze(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        browsers: Optional[List[str]] = None,
        search_term: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[BrowsedURLEntry]:
        """
        Analyze browsed URLs for an investigation.
        
        Args:
            db: Database session
            investigation_id: Investigation UUID
            browsers: Optional list of browser keys to filter by
            search_term: Optional search term to filter URLs/titles
            use_cache: Whether to use cached results
            
        Returns:
            List of BrowsedURLEntry objects
        """
        # Check cache if enabled
        if use_cache:
            cached = await self._get_cached_results(investigation_id, browsers, search_term)
            if cached is not None:
                logger.info(f"Returning cached browsed URLs results for investigation {investigation_id}")
                return cached
        
        logger.info(f"Analyzing browsed URLs for investigation {investigation_id}")
        
        # Build query
        query_parts = []
        query_parts.append("SELECT event_id, event_ts, payload FROM events")
        query_parts.append("WHERE investigation_id = :investigation_id")
        query_parts.append("AND event_type = 'browser_history'")
        
        params: Dict[str, Any] = {"investigation_id": str(investigation_id)}
        
        # Add browser filter if specified
        if browsers:
            browser_conditions = []
            for idx, browser in enumerate(browsers):
                param_name = f"browser_{idx}"
                browser_conditions.append(f"payload->>'browser' = :{param_name}")
                params[param_name] = browser
            
            query_parts.append(f"AND ({' OR '.join(browser_conditions)})")
        
        # Add search filter if specified
        if search_term:
            query_parts.append(
                "AND (payload->>'url' ILIKE :search_term OR payload->>'title' ILIKE :search_term)"
            )
            params["search_term"] = f"%{search_term}%"
        
        query_parts.append("ORDER BY event_ts DESC")
        query_parts.append("LIMIT 10000")
        
        query = text(" ".join(query_parts))
        
        # Execute query
        entries = []
        try:
            result = await db.execute(query, params)
            rows = result.fetchall()
            
            logger.info(f"Found {len(rows)} browser history events")
            
            for row in rows:
                event_id = row[0]
                event_ts = row[1]
                payload_str = row[2]
                
                try:
                    payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse payload for event {event_id}")
                    continue
                
                # Extract data
                browser = payload.get("browser", "unknown")
                url = payload.get("url")
                
                if not url:
                    continue
                
                # Extract artifact_sequence_id from payload
                artifact_sequence_id = payload.get("artifact_sequence_id")
                
                # Create entry
                entry = self._create_entry(
                    browser=browser,
                    event_id=event_id,
                    timestamp=event_ts.isoformat() if event_ts else None,
                    artifact_sequence_id=artifact_sequence_id,
                    payload=payload,
                )
                
                if entry:
                    entries.append(entry)
        
        except Exception as e:
            logger.error(f"Failed to query browser history: {e}", exc_info=True)
            try:
                await db.rollback()
            except Exception as rollback_error:
                logger.warning(f"Failed to rollback transaction: {rollback_error}")
        
        logger.info(f"Analyzed {len(entries)} browsed URL entries")
        
        # Cache results if enabled
        if use_cache and not search_term:  # Don't cache search results
            await self._cache_results(investigation_id, browsers, entries)
        
        return entries
    
    def _create_entry(
        self,
        browser: str,
        event_id: int,
        timestamp: Optional[str],
        artifact_sequence_id: Optional[int],
        payload: Dict[str, Any],
    ) -> Optional[BrowsedURLEntry]:
        """
        Create a BrowsedURLEntry from event data.
        
        Args:
            browser: Browser identifier
            event_id: Event ID
            timestamp: Event timestamp
            artifact_sequence_id: Artifact sequence ID
            payload: Event payload
            
        Returns:
            BrowsedURLEntry or None if data is invalid
        """
        url = payload.get("url")
        if not url:
            return None
        
        title = payload.get("title")
        visit_count = payload.get("visit_count")
        
        # Extract additional data based on browser
        additional_data = self._extract_additional_data(browser, payload)
        
        return BrowsedURLEntry(
            browser=browser,
            url=url,
            title=title,
            visit_count=visit_count,
            timestamp=timestamp,
            event_id=event_id,
            artifact_sequence_id=artifact_sequence_id,
            additional_data=additional_data,
            raw_data=payload,
        )
    
    def _extract_additional_data(self, browser: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract browser-specific additional data.
        
        Args:
            browser: Browser identifier
            payload: Event payload
            
        Returns:
            Dictionary of additional data
        """
        additional = {}
        
        if browser == "chrome_chromium":
            # Chrome/Chromium-specific fields
            if payload.get("typed_count") is not None:
                additional["typed_count"] = payload["typed_count"]
            if payload.get("transition_type") is not None:
                additional["transition_type"] = payload["transition_type"]
            if payload.get("source_file"):
                additional["source_file"] = payload["source_file"]
        
        elif browser == "firefox":
            # Firefox-specific fields
            if payload.get("typed") is not None:
                additional["typed"] = payload["typed"]
            if payload.get("visit_type") is not None:
                additional["visit_type"] = payload["visit_type"]
            if payload.get("source_file"):
                additional["source_file"] = payload["source_file"]
        
        elif browser == "edge_legacy":
            # Legacy Edge-specific fields
            if payload.get("table_name"):
                additional["table_name"] = payload["table_name"]
            if payload.get("source_file"):
                additional["source_file"] = payload["source_file"]
        
        # Filter out None values
        return {k: v for k, v in additional.items() if v is not None}
    
    async def _get_cached_results(
        self,
        investigation_id: uuid.UUID,
        browsers: Optional[List[str]],
        search_term: Optional[str],
    ) -> Optional[List[BrowsedURLEntry]]:
        """
        Retrieve cached analysis results.
        
        Args:
            investigation_id: Investigation UUID
            browsers: Browser filter
            search_term: Search term filter
            
        Returns:
            List of cached entries or None if cache miss
        """
        # Don't cache search results
        if search_term:
            return None
        
        # TODO: Implement caching logic
        # For now, return None to always run fresh analysis
        return None
    
    async def _cache_results(
        self,
        investigation_id: uuid.UUID,
        browsers: Optional[List[str]],
        entries: List[BrowsedURLEntry],
    ) -> None:
        """
        Cache analysis results.
        
        Args:
            investigation_id: Investigation UUID
            browsers: Browser filter
            entries: Entries to cache
        """
        # TODO: Implement caching logic
        # For now, skip caching
        pass


__all__ = ["BrowsedURLsAnalyzer", "BrowsedURLEntry"]
