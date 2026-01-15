import logging
from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.models.artifact import Artifact, ArtifactClassification
from app.core.config import settings
from app.services.rag.event_processor import process_interesting_events

# Optional parser imports - may not be available in test environments
try:
    from .evtx_parser import parse_evtx

    EVTX_AVAILABLE = True
except ImportError:
    EVTX_AVAILABLE = False
    parse_evtx = None

try:
    from .registry_parser import parse_registry

    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False
    parse_registry = None

try:
    from .prefetch_parser import parse_prefetch

    PREFETCH_AVAILABLE = True
except ImportError:
    PREFETCH_AVAILABLE = False
    parse_prefetch = None

try:
    from .lnk_parser import parse_lnk

    LNK_AVAILABLE = True
except ImportError:
    LNK_AVAILABLE = False
    parse_lnk = None

try:
    from .mft_parser import parse_mft

    MFT_AVAILABLE = True
except ImportError:
    MFT_AVAILABLE = False
    parse_mft = None

logger = logging.getLogger(__name__)


async def parse_artifact(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    artifact_id: int,
    user_id: int = 1,
) -> int:
    """
    Parse an artifact and store its events in the database.

    This coroutine retrieves the specified artifact file, selects a parser based on the
    artifact’s classification and filename extension, inserts any generated events,
    and optionally processes those events to create timeline entries with embeddings.

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
        RuntimeError: If the artifact file cannot be found on disk or if a required
            parser library (e.g., EVTX, Registry, Prefetch, LNK, MFT) is not available.
        RuntimeError: If parsing fails for any other reason not covered by the optional
            event-processing step.

    Notes:
        * Supported classifications and their parsers are:
          - `LOG_FILE` - currently only Windows Event Log files (`.evtx`).
          - `SYSTEM_HIVE` - Windows Registry hive files.
          - `BINARY` - Prefetch files (`.pf`) and shortcut files (`.lnk`).
          - `ARCHIVE` - Master File Table dumps (`$MFT` or `.mft`).

        * If a parser for the artifact’s type is unavailable, a `RuntimeError` is raised.
        * After successful parsing, the function attempts to create timeline entries via
          :func:`process_interesting_events`. Failures in this optional step are logged,
          cause a session rollback, but do not abort the overall operation.
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

    logger.info(
        f"Parsing artifact {artifact_id} ({artifact.filename}) "
        f"with classification {artifact.classification}"
    )

    # Route to appropriate parser
    classification = ArtifactClassification(artifact.classification)
    events_inserted = 0

    if classification == ArtifactClassification.LOG_FILE:
        # Check file extension for specific log types
        ext = artifact.filename.lower()

        if ext.endswith(".evtx"):
            if not EVTX_AVAILABLE:
                raise RuntimeError("EVTX parser not available (evtx library not installed)")
            events_inserted = await parse_evtx(db, investigation_id, artifact_id, file_path)
        else:
            logger.warning(f"Unsupported log file type: {artifact.filename}")
            return 0

    elif classification == ArtifactClassification.SYSTEM_HIVE:
        # Registry hive
        if not REGISTRY_AVAILABLE:
            raise RuntimeError("Registry parser not available (regipy library not installed)")
        events_inserted = await parse_registry(db, investigation_id, artifact_id, file_path)

    elif classification == ArtifactClassification.BINARY:
        # Check for specific binary types
        ext = artifact.filename.lower()

        if ext.endswith(".pf"):
            if not PREFETCH_AVAILABLE:
                raise RuntimeError("Prefetch parser not available (prefetch library not installed)")
            events_inserted = await parse_prefetch(db, investigation_id, artifact_id, file_path)
        elif ext.endswith(".lnk"):
            if not LNK_AVAILABLE:
                raise RuntimeError("LNK parser not available (lnk library not installed)")
            events_inserted = await parse_lnk(db, investigation_id, artifact_id, file_path)
        else:
            # Generic binary - no parsing for now
            logger.info(f"No parser for binary file: {artifact.filename}")
            return 0

    elif classification == ArtifactClassification.ARCHIVE:
        # MFT or other archive formats
        ext = artifact.filename.lower()

        if "$mft" in ext or ext.endswith(".mft"):
            if not MFT_AVAILABLE:
                raise RuntimeError("MFT parser not available (mft library not installed)")
            events_inserted = await parse_mft(db, investigation_id, artifact_id, file_path)
        else:
            logger.info(f"No parser for archive file: {artifact.filename}")
            return 0

    else:
        logger.info(f"No parser for classification: {classification}")
        return 0

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
