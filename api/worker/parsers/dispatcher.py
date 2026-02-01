from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.models.artifact import Artifact
from app.core.config import settings
from app.services.rag.event_processor import process_interesting_events
from app.utils.log_setup import get_logger

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
                logger.info(
                    f"Selected {parser_class.__name__} for artifact {artifact_id} ({artifact.filename})"
                )
                break
        except Exception as e:
            logger.warning(
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
            logger.warning(
                f"{selected_parser.__class__.__name__} failed to parse artifact {artifact_id} "
                f"({artifact.filename}): {e}. Falling back to FileMetadataParser."
            )
            try:
                # Use FileMetadataParser as fallback
                fallback_parser = FileMetadataParser()
                events_inserted = await fallback_parser.parse(db, investigation_id, artifact_id, file_path)
                logger.info(
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

    # After parsing, process interesting events to create timeline entries with embeddings
    if events_inserted > 0:
        try:
            timeline_entries_created = await process_interesting_events(
                db, investigation_id, artifact_id, user_id
            )
            if timeline_entries_created > 0:
                logger.info(
                    f"Created {timeline_entries_created} timeline entries from artifact {artifact_id}"
                )
        except Exception as e:
            logger.warning(f"Event processing failed for artifact {artifact_id}: {e}")
            # Rollback to clean up the session state
            try:
                await db.rollback()
            except:
                pass
            # Don't re-raise - parsing succeeded, event processing is optional

    return events_inserted


__all__ = ["parse_artifact"]
