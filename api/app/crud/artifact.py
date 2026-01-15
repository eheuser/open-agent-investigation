import hashlib
from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from ..models.artifact import Artifact, ArtifactClassification
from ..core.config import settings


def sha256_bytes(data: bytes) -> bytes:
    """
    Compute the SHA-256 digest of a bytes object.

    Args:
        data (bytes): The binary data to be hashed.

    Returns:
        bytes: A 32-byte SHA-256 hash value.
    """
    return hashlib.sha256(data).digest()


async def create_artifact(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    filename: str,
    classification: ArtifactClassification,
    file_bytes: bytes,
) -> Artifact:
    """
    Create a new artifact record associated with an investigation, storing its binary data both in the database (as a BLOB) and on the filesystem.

    Args:
        db: An active asynchronous SQLAlchemy session used to persist the artifact.
        investigation_id: The UUID of the investigation to which the artifact belongs.
        filename: The original name of the uploaded file.
        classification: An `ArtifactClassification` enum value describing the type or sensitivity of the artifact.
        file_bytes: The raw binary content of the file to be stored.

    Returns:
        The newly created :class:`Artifact` instance, refreshed from the database and containing its generated identifier.

    Raises:
        OSError: If the filesystem directory cannot be created or the file cannot be written.
        sqlalchemy.exc.SQLAlchemyError: If any database operation fails.
    """
    sha = sha256_bytes(file_bytes)

    # Create artifact record
    artifact = Artifact(
        investigation_id=investigation_id,
        sha256=sha,
        filename=filename,
        classification=classification,
        blob=file_bytes,
    )

    db.add(artifact)
    await db.flush()  # Get artifact_id

    # Write to filesystem
    inv_dir = Path(settings.investigations_base_path) / str(investigation_id) / "raw_files"
    inv_dir.mkdir(parents=True, exist_ok=True)

    file_path = inv_dir / f"{artifact.artifact_id}_{filename}"
    file_path.write_bytes(file_bytes)

    await db.commit()
    await db.refresh(artifact)

    return artifact


async def get_artifact(db: AsyncSession, artifact_id: int) -> Optional[Artifact]:
    """
    Retrieve an artifact by its unique identifier.

    Args:
        db (AsyncSession): An active asynchronous SQLAlchemy session used to query the database.
        artifact_id (int): The primary key of the artifact to retrieve.

    Returns:
        Optional[Artifact]: The matching Artifact instance if found; otherwise, `None`.
    """
    result = await db.execute(select(Artifact).where(Artifact.artifact_id == artifact_id))
    return result.scalars().first()


async def list_artifacts(db: AsyncSession, investigation_id: uuid.UUID) -> list[Artifact]:
    """
    List all Artifact records associated with a given investigation.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used to execute the query.
    investigation_id : uuid.UUID
        The unique identifier of the investigation whose artifacts are to be retrieved.

    Returns
    -------
    list[Artifact]
        A list of `Artifact` objects ordered by upload timestamp in descending order.
    """
    result = await db.execute(
        select(Artifact)
        .where(Artifact.investigation_id == investigation_id)
        .order_by(Artifact.upload_ts.desc())
    )
    return list(result.scalars().all())


__all__ = [
    "sha256_bytes",
    "create_artifact",
    "get_artifact",
    "list_artifacts",
]
