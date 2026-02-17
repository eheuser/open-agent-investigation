from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.engine import CursorResult

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message
from .utils import safe_json_dumps

logger = get_logger(__name__)


async def invalidate_analysis_cache(db: AsyncSession, investigation_id: uuid.UUID):
    """
    Invalidate all cached analysis results for an investigation.
    
    This should be called whenever new events are inserted to ensure
    that analysis modules re-run and pick up the new data.
    
    Args:
        db: Async database session
        investigation_id: UUID of the investigation
    """
    try:
        delete_query = text(
            """
            DELETE FROM analysis_results
            WHERE investigation_id = :investigation_id
            """
        )
        
        cursor_result: CursorResult = await db.execute(delete_query, {"investigation_id": str(investigation_id)})  # type: ignore
        rows_deleted = cursor_result.rowcount or 0
        
        if rows_deleted > 0:
            logger.debug(f"Invalidated {rows_deleted} cached analysis results for investigation {investigation_id}")
        else:
            logger.debug(f"No cached analysis results to invalidate for investigation {investigation_id}")
        
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to invalidate analysis cache for investigation {sanitize_log_message(str(investigation_id))}: {sanitize_log_message(str(e))}")
        await db.rollback()


class BaseParser(ABC):
    """
    Abstract base class for all artifact parsers.
    
    All parsers must implement:
    - identify() class method to determine if a file can be parsed
    - _parse_impl() method to perform the actual parsing
    
    The base class provides:
    - Common database insertion logic
    - Error handling and logging
    - Batch insertion utilities
    """
    
    @classmethod
    @abstractmethod
    def identify(cls, filename: str, file_path: Path) -> bool:
        """
        Determine if this parser can handle the given file.
        
        Args:
            filename: Original filename of the artifact
            file_path: Path to the artifact file on disk
            
        Returns:
            True if this parser can handle the file, False otherwise
        """
        pass
    
    @abstractmethod
    async def _parse_impl(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Parse the artifact and return the number of events inserted.
        
        This method should extract data from the artifact and call
        _insert_event_batch() to store events in the database.
        
        Args:
            db: Async database session
            investigation_id: UUID of the investigation
            artifact_id: ID of the artifact being parsed
            file_path: Path to the artifact file
            
        Returns:
            Number of events inserted into the database
            
        Raises:
            RuntimeError: If parsing fails
        """
        pass
    
    async def parse(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        artifact_id: int,
        file_path: Path,
    ) -> int:
        """
        Parse an artifact file and insert events into the database.
        
        This is the main entry point called by the dispatcher. It wraps
        the parser-specific _parse_impl() with common error handling.
        
        Args:
            db: Async database session
            investigation_id: UUID of the investigation
            artifact_id: ID of the artifact being parsed
            file_path: Path to the artifact file
            
        Returns:
            Number of events inserted into the database
            
        Raises:
            RuntimeError: If parsing fails
        """
        parser_name = self.__class__.__name__
        logger.debug(f"Parsing artifact {artifact_id} with {parser_name}: {sanitize_log_message(str(file_path))}")
        
        try:
            events_inserted = await self._parse_impl(db, investigation_id, artifact_id, file_path)
            logger.debug(f"{parser_name} inserted {events_inserted} events from {sanitize_log_message(str(file_path))}")
            return events_inserted
        except Exception as e:
            logger.info(f"{parser_name} failed to parse {sanitize_log_message(str(file_path))}: {sanitize_log_message(str(e))}")
            logger.debug(f"{parser_name} failed to parse {sanitize_log_message(str(file_path))}: {sanitize_log_message(str(e))}", exc_info=True)
            raise RuntimeError(f"{parser_name} parsing failed: {sanitize_log_message(str(e))}")
    
    async def _insert_event_batch(
        self,
        db: AsyncSession,
        investigation_id: uuid.UUID,
        events: List[Dict[str, Any]],
    ):
        """
        Insert a batch of events into the unified events table.
        
        This is a common utility method used by all parsers to insert events.
        Each event dictionary must contain: event_ts, artifact_id, event_type, payload.
        
        The payload is sanitized to remove null bytes and other characters that
        PostgreSQL JSONB cannot handle.
        
        Args:
            db: Async database session
            investigation_id: UUID of the investigation
            events: List of event dictionaries to insert
            
        Raises:
            Exception: If database insertion fails
        """
        if not events:
            return
        
        # Add investigation_id and sanitize payload for each event
        for event in events:
            event["investigation_id"] = investigation_id
            
            # Sanitize payload to remove null bytes and invalid Unicode
            # This prevents PostgreSQL JSONB errors
            if "payload" in event and isinstance(event["payload"], str):
                try:
                    # Parse JSON, sanitize, and re-serialize
                    payload_obj = json.loads(event["payload"])
                    event["payload"] = safe_json_dumps(payload_obj)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(f"Failed to sanitize payload, using as-is: {sanitize_log_message(str(e))}")
        
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
            
            # Invalidate analysis cache since new events were added
            await invalidate_analysis_cache(db, investigation_id)
            
        except Exception as e:
            logger.error(f"Failed to insert event batch of {len(events):,} events: {sanitize_log_message(str(e))}", exc_info=True)
            await db.rollback()
            raise


__all__ = ["BaseParser"]
