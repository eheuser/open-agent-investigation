from pathlib import Path
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import uuid

from app.models.artifact import Artifact
from app.models.filter_config import FilterConfig
from app.core.config import settings
from app.services.rag.filter_engine import FilterEngine
from app.services.embedding_batcher import queue_events_for_embedding
from app.utils.log_setup import get_logger
import json

# Import all parser classes
from .archive_parser import ArchiveParser
from .evtx_parser import EvtxParser
from .registry_parser import RegistryParser
from .prefetch_parser import PrefetchParser
from .lnk_parser import LnkParser
from .mft_parser import MftParser
from .jumplist_parser import JumplistParser
from .browser_history_parser import BrowserHistoryParser
from .windows_artifacts_parser import WindowsArtifactsParser
from .file_metadata_parser import FileMetadataParser

logger = get_logger(__name__)

# Registry of all available parsers
# Order matters - more specific parsers should come first
# ArchiveParser MUST come first to extract archives before other parsers
# FileMetadataParser MUST come last as the catch-all fallback
PARSERS = [
    ArchiveParser,  # Process archives first to extract contained files
    EvtxParser,
    RegistryParser,
    PrefetchParser,
    LnkParser,
    MftParser,
    JumplistParser,
    BrowserHistoryParser,
    WindowsArtifactsParser,
    FileMetadataParser,  # Catch-all parser - MUST be last
]


async def parse_artifact(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    user_id: int = 1,
) -> int:
    """
    Parse an artifact and store its events in the database.

    This coroutine retrieves the specified artifact file, automatically identifies
    the appropriate parser using each parser's identify() method, parses the artifact,
    and optionally processes events to create timeline entries with embeddings.

    Args:
        db: An asynchronous SQLAlchemy session used for all database operations.
        investigation_id: The UUID of the investigation that owns the artifact.
        artifact_id: The primary-key identifier of the artifact to be parsed.
        user_id: Identifier of the user whose embedding configuration should be used
            when processing interesting events (default is `1` - the admin user).

    Returns:
        int: The number of event records successfully inserted into the database.

    Raises:
        ValueError: If no artifact with the given `artifact_id` exists.
        RuntimeError: If the artifact file cannot be found on disk or if no parser
            can handle the file type.
        RuntimeError: If parsing fails for any reason.

    Notes:
        * The dispatcher automatically identifies the correct parser by calling each
          parser's identify() class method in order until one returns True.
        * No manual classification is required - parsers use magic bytes and file
          patterns for identification.
        * After successful parsing, the function attempts to create timeline entries via
          process_interesting_events(). Failures in this optional step are logged but
          do not abort the overall operation.
    """
    # Get artifact
    result = await db.execute(select(Artifact).where(Artifact.artifact_id == artifact_id))
    artifact = result.scalars().first()

    if not artifact:
        raise ValueError(f"Artifact {artifact_id} not found")

    # Get file path
    inv_dir = Path(settings.investigations_base_path) / str(investigation_id) / "raw_files"
    file_path = inv_dir / f"{artifact_id}_{artifact.filename}"

    if not file_path.exists():
        raise RuntimeError(f"Artifact file not found: {file_path}")

    logger.debug(
        f"Identifying parser for artifact {artifact_id} ({artifact.filename})"
    )

    # Try each parser's identify() method
    selected_parser = None
    for parser_class in PARSERS:
        try:
            if parser_class.identify(artifact.filename, file_path):
                selected_parser = parser_class()
                logger.debug(
                    f"Selected {parser_class.__name__} for artifact {artifact_id} ({artifact.filename})"
                )
                break
        except Exception as e:
            logger.debug(
                f"{parser_class.__name__}.identify() failed for {artifact.filename}: {e}"
            )
            continue

    if not selected_parser:
        raise RuntimeError(
            f"No parser available for artifact {artifact_id} ({artifact.filename}). "
            f"File type not recognized."
        )

    # Parse the artifact using the selected parser
    # If parsing fails, fall back to FileMetadataParser
    try:
        events_inserted = await selected_parser.parse(db, investigation_id, artifact_id, file_path)
    except Exception as e:
        # Only fall back to FileMetadataParser if the selected parser was NOT already FileMetadataParser
        if not isinstance(selected_parser, FileMetadataParser):
            logger.debug(
                f"{selected_parser.__class__.__name__} failed to parse artifact {artifact_id} "
                f"({artifact.filename}): {e}. Falling back to FileMetadataParser."
            )
            try:
                # Use FileMetadataParser as fallback
                fallback_parser = FileMetadataParser()
                events_inserted = await fallback_parser.parse(db, investigation_id, artifact_id, file_path)
                logger.debug(
                    f"FileMetadataParser successfully processed artifact {artifact_id} as fallback "
                    f"({events_inserted} events inserted)"
                )
            except Exception as fallback_error:
                logger.error(
                    f"FileMetadataParser fallback also failed for artifact {artifact_id}: {fallback_error}"
                )
                raise RuntimeError(
                    f"Both {selected_parser.__class__.__name__} and FileMetadataParser failed to parse "
                    f"artifact {artifact_id} ({artifact.filename})"
                )
        else:
            # FileMetadataParser itself failed - re-raise the error
            logger.error(f"FileMetadataParser failed for artifact {artifact_id}: {e}")
            raise

    # After parsing, queue interesting events for background embedding
    if events_inserted > 0:
        try:
            # Get filter configuration
            filter_config_result = await db.execute(
                select(FilterConfig)
                .where(FilterConfig.investigation_id == investigation_id)
                .order_by(FilterConfig.updated_at.desc())
            )
            filter_config_obj = filter_config_result.scalars().first()
            
            if filter_config_obj:
                # Extract content and ensure it's a dict with string keys
                content = getattr(filter_config_obj, "content", None)
                if content and isinstance(content, dict):
                    filter_config: Dict[str, Any] = dict(content)
                else:
                    filter_config = FilterEngine.DEFAULT_CONFIG
            else:
                filter_config = FilterEngine.DEFAULT_CONFIG
            
            filter_engine = FilterEngine(filter_config)
            
            # Fetch all events from this artifact that don't have embeddings yet
            result = await db.execute(
                text(
                    """
                    SELECT e.event_id, e.event_type, e.payload
                    FROM events e
                    LEFT JOIN embeddings emb ON emb.owner_type = 'tool' AND emb.owner_id = e.event_id
                    WHERE e.artifact_id = :artifact_id
                    AND e.investigation_id = :investigation_id
                    AND emb.id IS NULL
                    ORDER BY e.event_ts, e.event_id
                """
                ),
                {
                    "artifact_id": artifact_id,
                    "investigation_id": str(investigation_id),
                },
            )
            
            events = result.fetchall()
            
            # Filter for interesting events
            interesting_event_ids: list[int] = []
            for row in events:
                event_id = int(row[0])
                event_type = str(row[1])
                payload_json = row[2]
                try:
                    payload = (
                        json.loads(payload_json) if isinstance(payload_json, str) else payload_json
                    )
                    is_interesting = False
                    
                    if event_type.startswith("evtx_"):
                        is_interesting, _ = filter_engine.is_interesting_evtx(payload)
                    elif event_type.startswith("mft_"):
                        path = payload.get("path", payload.get("file_path", ""))
                        extension = payload.get("extension", "")
                        is_interesting = filter_engine.is_interesting_mft(path, extension)
                    elif event_type in ( "registry_key", "registry_value" ):
                        key_path = payload.get("key_path", payload.get("path", ""))
                        is_interesting = filter_engine.is_interesting_registry(key_path)
                    elif event_type.startswith("prefetch_"):
                        executable = payload.get("executable", payload.get("name", ""))
                        is_interesting = filter_engine.is_interesting_prefetch(executable)
                    elif event_type.startswith("lnk_"):
                        target = payload.get("target_path", payload.get("target", ""))
                        is_interesting = filter_engine.is_interesting_lnk(target)
                    elif event_type in (
                        "cryptnet_cache",
                        "pca_execution",
                        "scheduled_task",
                        "srum_data",
                        "windows_search",
                        "notification",
                        "browser_history",
                        "registry_amcache",
                        "registry_userassist",
                        "registry_bam",
                        "registry_shellbags_ntuser",
                        "registry_shimcache"

                    ):
                        is_interesting = True
                        
                    if is_interesting:
                        interesting_event_ids.append(event_id)
                except Exception as e:
                    logger.debug(f"Failed to filter event {event_id}: {e}")
                    continue
            
            # Queue events for background batching (thread-safe, works across processes)
            if interesting_event_ids:
                queue_events_for_embedding(
                    investigation_id=investigation_id,
                    user_id=user_id,
                    event_ids=interesting_event_ids,
                )
                logger.debug(
                    f"Queued {len(interesting_event_ids):,} events for embedding "
                    f"(artifact {artifact_id}, investigation {investigation_id})"
                )
        except Exception as e:
            logger.warning(f"Event queueing failed for artifact {artifact_id}: {e}")
            # Don't rollback - parsing succeeded, queueing is optional

    return events_inserted


__all__ = ["parse_artifact"]
