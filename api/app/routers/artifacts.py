from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid
import io

from ..deps import get_db, get_current_user
from ..models.user import User
from ..models.artifact import ArtifactClassification
from ..schemas.artifact import ArtifactMetadata, ArtifactUploadResponse
from ..crud import artifact as crud
from ..crud import investigation as inv_crud
from ..crud import job as job_crud
from .chat import manager  # Import WebSocket manager for notifications

router = APIRouter()


@router.post("/", response_model=ArtifactUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_artifact(
    investigation_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Upload an artifact file to a specific investigation.

    The function validates the provided investigation identifier, checks user permissions,
    reads the uploaded file content, stores the artifact both in the database and on the 
    filesystem, creates a parsing job for the new artifact, locks the investigation while 
    parsing is pending, and notifies connected WebSocket clients that parsing has started.
    
    The artifact type is automatically identified by the parser system using magic bytes
    and file patterns - no manual classification is required.

    Args:
        investigation_id (str): UUID string of the parent investigation.
        file (UploadFile): The uploaded file object.
        db (AsyncSession): Asynchronous database session, injected via dependency.
        user (User): Currently authenticated user, injected via dependency.

    Returns:
        ArtifactUploadResponse: Response model containing the created artifact metadata,
        its identifier, the associated parsing job identifier, and a success message.

    Raises:
        HTTPException: If the investigation ID format is invalid (400),
            the investigation does not exist (404),
            the user lacks access rights (403), or
            the uploaded file is empty (400).
    """
    # Parse UUID
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid investigation ID format"
        )

    # Verify investigation exists and user has access
    inv = await inv_crud.get_investigation(db, inv_uuid)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    if not user.is_admin() and inv.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Read file content
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file not allowed"
        )

    # Create artifact with UNKNOWN classification (will be auto-detected by parser)
    artifact = await crud.create_artifact(
        db,
        investigation_id=inv_uuid,
        filename=file.filename or "unnamed",
        classification=ArtifactClassification.UNKNOWN,
        file_bytes=content,
    )

    # Create parsing job for this artifact
    job = await job_crud.enqueue_parsing_job(
        db,
        investigation_id=inv_uuid,
        artifact_id=artifact.artifact_id,
    )

    # Set parsing lock on investigation (blocks new user questions)
    await inv_crud.set_parsing_lock(db, inv_uuid, locked=True)

    # Notify WebSocket clients that parsing has started
    await manager.broadcast(
        investigation_id,
        {
            "type": "parsing_started",
            "investigation_id": investigation_id,
            "artifact_id": artifact.artifact_id,
            "job_id": job.job_id,
        },
    )

    return ArtifactUploadResponse(
        artifact=artifact,
        artifact_id=artifact.artifact_id,
        job_id=job.job_id,
        message="Uploaded successfully and queued for parsing",
    )


@router.get("/{artifact_id}", response_class=StreamingResponse)
async def download_artifact(
    artifact_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Download an artifact file as a streaming response.

    Parameters
    ----------
    artifact_id: int
        The unique identifier of the artifact to download.
    db: AsyncSession
        Database session dependency injected by FastAPI.
    user: User
        The currently authenticated user, provided via dependency injection.

    Returns
    -------
    StreamingResponse
        A streaming HTTP response containing the artifact's binary data,
        with appropriate `Content-Disposition` and `Content-Length` headers
        to prompt a file download.

    Raises
    ------
    HTTPException
        - 404 Not Found if the specified artifact does not exist.
        - 404 Not Found if the parent investigation cannot be found.
        - 403 Forbidden if the requesting user is neither an administrator nor the owner of the investigation.
    """
    artifact = await crud.get_artifact(db, artifact_id)

    if not artifact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    # Verify access to parent investigation
    inv = await inv_crud.get_investigation(db, artifact.investigation_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Parent investigation not found"
        )

    if not user.is_admin() and inv.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Stream the file
    def file_iterator():
        """
        Iterates over the binary content of an artifact.

        Yields:
            bytes: Chunks of the artifact's blob data for streaming or processing.
        """
        yield artifact.blob

    return StreamingResponse(
        file_iterator(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Content-Length": str(len(artifact.blob)),
        },
    )


@router.get("/investigation/{investigation_id}", response_model=List[ArtifactMetadata])
async def list_artifacts(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List all artifacts associated with a given investigation.

    Args:
        investigation_id (str): The UUID of the investigation whose artifacts are being requested.
        db (AsyncSession): Asynchronous database session provided by FastAPI's dependency injection.
        user (User): The currently authenticated user, injected via dependency.

    Returns:
        List[dict]: A list containing metadata dictionaries for each artifact belonging to the investigation.

    Raises:
        HTTPException:
            - 400 Bad Request if `investigation_id` is not a valid UUID string.
            - 404 Not Found if no investigation with the given ID exists.
            - 403 Forbidden if the requesting user is neither an admin nor the owner of the investigation.
    """
    try:
        inv_uuid = uuid.UUID(investigation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid investigation ID format"
        )

    # Verify access
    inv = await inv_crud.get_investigation(db, inv_uuid)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found")

    if not user.is_admin() and inv.owner_user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    artifacts = await crud.list_artifacts(db, inv_uuid)
    return artifacts


__all__ = ["router"]
