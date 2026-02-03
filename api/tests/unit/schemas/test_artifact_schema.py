import pytest
from pydantic import ValidationError
from app.schemas.artifact import ArtifactMetadata, ArtifactUploadResponse, ArtifactListResponse
from uuid import uuid4
from datetime import datetime


@pytest.mark.unit
class TestArtifactMetadata:
    """Test ArtifactMetadata schema."""

    def test_create_valid_metadata(self):
        """
        Test that an `ArtifactMetadata` instance can be created with valid input data and that its fields are correctly populated.

        The test constructs a dictionary containing all required fields for the model:
        - `artifact_id`: integer identifier of the artifact.
        - `investigation_id`: string representation of a UUID identifying the investigation.
        - `sha256`: 64-character hexadecimal SHA-256 hash.
        - `filename`: name of the uploaded file.
        - `classification`: integer classification level.
        - `upload_ts`: ISO-8601 timestamp generated at runtime.

        It then instantiates :class:`ArtifactMetadata` with this data and asserts that:
        * The `artifact_id` attribute matches the supplied value.
        * The `filename` attribute is set to the provided filename.
        * The `sha256` attribute has a length of 64 characters, confirming proper handling of the hash string.
        """
        data = {
            "artifact_id": 1,
            "investigation_id": str(uuid4()),
            "sha256": "a" * 64,
            "filename": "test.evtx",
            "classification": 1,
            "upload_ts": datetime.now().isoformat(),
        }

        metadata = ArtifactMetadata(**data)

        assert metadata.artifact_id == 1
        assert metadata.filename == "test.evtx"
        assert len(metadata.sha256) == 64

    def test_create_metadata_missing_field(self):
        """
        Test that creating an :class:`ArtifactMetadata` instance without the required `investigation_id` field raises a :class:`pydantic.ValidationError`. The test supplies a dictionary missing `investigation_id` and asserts that instantiation fails with the expected validation exception.
        """
        data = {
            "artifact_id": 1,
            "filename": "test.evtx",
            # Missing investigation_id
        }

        with pytest.raises(ValidationError):
            ArtifactMetadata(**data)

    def test_sha256_hex_conversion(self):
        """
        Test that the `sha256` field of :class:`ArtifactMetadata` correctly converts a 32-byte SHA-256 value into its hexadecimal string representation and that the resulting string has the expected length of 64 characters.
        """
        sha256_bytes = b"\xaa" * 32

        data = {
            "artifact_id": 1,
            "investigation_id": str(uuid4()),
            "sha256": sha256_bytes,
            "filename": "test.evtx",
            "classification": 1,
            "upload_ts": datetime.now().isoformat(),
        }

        metadata = ArtifactMetadata(**data)

        assert isinstance(metadata.sha256, str)
        assert len(metadata.sha256) == 64

    def test_metadata_unicode_filename(self):
        """
        Test that the `ArtifactMetadata` model correctly preserves Unicode characters in the filename field.

        The test constructs a payload containing a Japanese filename (`"テスト.evtx"`), creates an `ArtifactMetadata` instance from this data, and asserts that the `filename` attribute of the resulting object matches the original Unicode string. This verifies that the schema does not alter or reject non-ASCII filenames during validation.
        """
        data = {
            "artifact_id": 1,
            "investigation_id": str(uuid4()),
            "sha256": "a" * 64,
            "filename": "テスト.evtx",
            "classification": 1,
            "upload_ts": datetime.now().isoformat(),
        }

        metadata = ArtifactMetadata(**data)
        assert metadata.filename == "テスト.evtx"


@pytest.mark.unit
class TestArtifactUploadResponse:
    """Test ArtifactUploadResponse schema."""

    def test_create_upload_response(self):
        """
        Test the creation of an :class:`ArtifactUploadResponse` instance with valid data.

        The test constructs a dictionary representing artifact metadata, including required fields such as `artifact_id`, `investigation_id`,
        `sha256`, `filename`, `classification` and `upload_ts`. It then builds a payload containing the nested
        `artifact` object together with top-level `artifact_id`, `job_id` and `message` values.

        The function instantiates :class:`ArtifactUploadResponse` using the payload and asserts that the resulting object's
        attributes match the input data:

        - `artifact_id` equals the supplied artifact identifier.
        - `job_id` matches the provided job identifier.
        - `message` reflects the success message passed in the payload.
        """
        artifact_data = {
            "artifact_id": 1,
            "investigation_id": str(uuid4()),
            "sha256": "a" * 64,
            "filename": "test.evtx",
            "classification": 1,
            "upload_ts": datetime.now().isoformat(),
        }

        data = {
            "artifact": artifact_data,
            "artifact_id": 1,
            "job_id": 100,
            "message": "Upload successful",
        }

        response = ArtifactUploadResponse(**data)

        assert response.artifact_id == 1
        assert response.job_id == 100
        assert response.message == "Upload successful"

    def test_upload_response_default_message(self):
        """
        Test that creating an :class:`ArtifactUploadResponse` without explicitly providing a `message` field results in the default success message "Uploaded successfully". The test constructs minimal required artifact data, instantiates the response model, and asserts that the `message` attribute matches the expected default.
        """
        artifact_data = {
            "artifact_id": 1,
            "investigation_id": str(uuid4()),
            "sha256": "a" * 64,
            "filename": "test.evtx",
            "classification": 1,
            "upload_ts": datetime.now().isoformat(),
        }

        data = {
            "artifact": artifact_data,
            "artifact_id": 1,
            "job_id": 100,
        }

        response = ArtifactUploadResponse(**data)

        assert response.message == "Uploaded successfully"


@pytest.mark.unit
class TestArtifactListResponse:
    """Test ArtifactListResponse schema."""

    def test_create_list_response(self):
        """
        Test that an :class:`ArtifactListResponse` correctly constructs a response containing multiple artifact entries and accurately reports the total count.

        The test builds two artifact dictionaries with required fields-including IDs, investigation identifiers, SHA-256 hashes, filenames, classification codes, and upload timestamps-then assembles them into a payload matching the schema's expected structure. By instantiating :class:`ArtifactListResponse` with this data, the test verifies that:

        * The `artifacts` attribute contains exactly two items.
        * The `total` attribute reflects the supplied total count of artifacts.

        This ensures proper parsing and validation of list responses within the API model.
        """
        artifacts = [
            {
                "artifact_id": 1,
                "investigation_id": str(uuid4()),
                "sha256": "a" * 64,
                "filename": "test1.evtx",
                "classification": 1,
                "upload_ts": datetime.now().isoformat(),
            },
            {
                "artifact_id": 2,
                "investigation_id": str(uuid4()),
                "sha256": "b" * 64,
                "filename": "test2.evtx",
                "classification": 1,
                "upload_ts": datetime.now().isoformat(),
            },
        ]

        data = {
            "artifacts": artifacts,
            "total": 2,
        }

        response = ArtifactListResponse(**data)

        assert len(response.artifacts) == 2
        assert response.total == 2

    def test_list_response_empty(self):
        """
        Test that an ArtifactListResponse correctly handles an empty artifacts list and a total count of zero, ensuring the resulting object's attributes reflect the empty state.
        """
        data = {
            "artifacts": [],
            "total": 0,
        }

        response = ArtifactListResponse(**data)

        assert len(response.artifacts) == 0
        assert response.total == 0
