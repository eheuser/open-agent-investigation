# api/tests/unit/schemas/test_artifact.py
import pytest
from datetime import datetime
from uuid import uuid4

from app.schemas.artifact import ArtifactMetadata, ArtifactUploadResponse, ArtifactListResponse


def test_artifact_metadata_with_hex_sha256():
    """Test ArtifactMetadata with SHA-256 as hex string."""
    data = {
        "artifact_id": 1,
        "investigation_id": uuid4(),
        "sha256": "a" * 64,  # Hex string
        "filename": "test.txt",
        "classification": 0,
        "upload_ts": datetime.now(),
    }
    
    artifact = ArtifactMetadata(**data)
    
    assert artifact.sha256 == "a" * 64
    assert artifact.filename == "test.txt"


def test_artifact_metadata_with_bytes_sha256():
    """Test ArtifactMetadata converts bytes SHA-256 to hex."""
    sha256_bytes = bytes.fromhex("a" * 64)
    
    data = {
        "artifact_id": 1,
        "investigation_id": uuid4(),
        "sha256": sha256_bytes,
        "filename": "test.txt",
        "classification": 0,
        "upload_ts": datetime.now(),
    }
    
    artifact = ArtifactMetadata(**data)
    
    assert artifact.sha256 == "a" * 64
    assert isinstance(artifact.sha256, str)


def test_artifact_metadata_with_bytearray_sha256():
    """Test ArtifactMetadata converts bytearray SHA-256 to hex."""
    sha256_bytes = bytearray.fromhex("b" * 64)
    
    data = {
        "artifact_id": 2,
        "investigation_id": uuid4(),
        "sha256": sha256_bytes,
        "filename": "test2.txt",
        "classification": 1,
        "upload_ts": datetime.now(),
    }
    
    artifact = ArtifactMetadata(**data)
    
    assert artifact.sha256 == "b" * 64
    assert isinstance(artifact.sha256, str)


def test_artifact_metadata_with_memoryview_sha256():
    """Test ArtifactMetadata converts memoryview SHA-256 to hex."""
    sha256_bytes = memoryview(bytes.fromhex("c" * 64))
    
    data = {
        "artifact_id": 3,
        "investigation_id": uuid4(),
        "sha256": sha256_bytes,
        "filename": "test3.txt",
        "classification": 2,
        "upload_ts": datetime.now(),
    }
    
    artifact = ArtifactMetadata(**data)
    
    assert artifact.sha256 == "c" * 64
    assert isinstance(artifact.sha256, str)


def test_artifact_metadata_from_object_with_bytes():
    """Test ArtifactMetadata with object having bytes sha256 attribute."""
    
    class MockArtifact:
        def __init__(self):
            self.artifact_id = 4
            self.investigation_id = uuid4()
            self.sha256 = bytes.fromhex("d" * 64)
            self.filename = "mock.txt"
            self.classification = 0
            self.upload_ts = datetime.now()
    
    mock_obj = MockArtifact()
    artifact = ArtifactMetadata.model_validate(mock_obj)
    
    assert artifact.sha256 == "d" * 64
    assert isinstance(artifact.sha256, str)


def test_artifact_upload_response():
    """Test ArtifactUploadResponse schema."""
    metadata = ArtifactMetadata(
        artifact_id=1,
        investigation_id=uuid4(),
        sha256="a" * 64,
        filename="test.txt",
        classification=0,
        upload_ts=datetime.now(),
    )
    
    response = ArtifactUploadResponse(
        artifact=metadata,
        artifact_id=1,
        job_id=100,
    )
    
    assert response.artifact_id == 1
    assert response.job_id == 100
    assert response.message == "Uploaded successfully"
    assert response.artifact == metadata


def test_artifact_upload_response_custom_message():
    """Test ArtifactUploadResponse with custom message."""
    metadata = ArtifactMetadata(
        artifact_id=1,
        investigation_id=uuid4(),
        sha256="a" * 64,
        filename="test.txt",
        classification=0,
        upload_ts=datetime.now(),
    )
    
    response = ArtifactUploadResponse(
        artifact=metadata,
        artifact_id=1,
        job_id=100,
        message="Custom upload message",
    )
    
    assert response.message == "Custom upload message"


def test_artifact_list_response():
    """Test ArtifactListResponse schema."""
    artifacts = [
        ArtifactMetadata(
            artifact_id=i,
            investigation_id=uuid4(),
            sha256=str(i) * 64,
            filename=f"test{i}.txt",
            classification=0,
            upload_ts=datetime.now(),
        )
        for i in range(1, 4)
    ]
    
    response = ArtifactListResponse(
        artifacts=artifacts,
        total=3,
    )
    
    assert len(response.artifacts) == 3
    assert response.total == 3
    assert all(isinstance(a, ArtifactMetadata) for a in response.artifacts)


def test_artifact_list_response_empty():
    """Test ArtifactListResponse with no artifacts."""
    response = ArtifactListResponse(
        artifacts=[],
        total=0,
    )
    
    assert len(response.artifacts) == 0
    assert response.total == 0
