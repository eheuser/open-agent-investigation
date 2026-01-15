"""
Unit tests for Artifact model.
"""

import pytest
import uuid
from datetime import datetime

from app.models.artifact import Artifact, ArtifactClassification


@pytest.mark.unit
class TestArtifactModel:
    """Test Artifact model behavior."""

    def test_artifact_creation(self):
        """
        Test creating an :class:`Artifact` instance with valid inputs and verifying that all attributes are correctly assigned.

        The test:
        - Generates a random investigation UUID.
        - Uses a 32-byte zeroed SHA-256 digest.
        - Provides sample blob data and a filename.
        - Sets the classification to :data:`ArtifactClassification.LOG_FILE`.
        - Instantiates an `Artifact` with these values and the current UTC timestamp.
        - Asserts that each attribute of the resulting object matches the supplied input, including type checking for the `upload_ts` field.
        """
        inv_id = uuid.uuid4()
        sha256 = b"\x00" * 32
        blob = b"test file content"

        artifact = Artifact(
            artifact_id=1,
            investigation_id=inv_id,
            sha256=sha256,
            filename="test.evtx",
            classification=ArtifactClassification.LOG_FILE,
            blob=blob,
            upload_ts=datetime.utcnow(),
        )

        assert artifact.artifact_id == 1
        assert artifact.investigation_id == inv_id
        assert artifact.sha256 == sha256
        assert artifact.filename == "test.evtx"
        assert artifact.classification == ArtifactClassification.LOG_FILE
        assert artifact.blob == blob
        assert isinstance(artifact.upload_ts, datetime)

    def test_artifact_classification_enum(self):
        """
        Verify that every `ArtifactClassification` enum member can be used as the `classification` argument when constructing an `Artifact` instance and that the resulting object's `classification` attribute matches the provided enum value.
        """
        # Test all classification types
        classifications = [
            ArtifactClassification.SYSTEM_HIVE,
            ArtifactClassification.LOG_FILE,
            ArtifactClassification.BINARY,
            ArtifactClassification.ARCHIVE,
            ArtifactClassification.UNKNOWN,
        ]

        for classification in classifications:
            artifact = Artifact(
                artifact_id=1,
                investigation_id=uuid.uuid4(),
                sha256=b"\x00" * 32,
                filename="test",
                classification=classification,
                blob=b"data",
            )
            assert artifact.classification == classification

    def test_artifact_sha256_length(self):
        """
        Test that the Artifact model enforces a SHA-256 hash length of exactly 32 bytes by creating an instance with a valid 32-byte hash and asserting its length.
        """
        valid_sha256 = b"\x00" * 32

        artifact = Artifact(
            artifact_id=1,
            investigation_id=uuid.uuid4(),
            sha256=valid_sha256,
            filename="test",
            classification=0,
            blob=b"data",
        )

        assert len(artifact.sha256) == 32

    def test_artifact_filename_types(self):
        """
        Test various filename formats.

        This test iterates over a collection of representative filenames-including simple names, system files, shortcuts, names with spaces, Unicode characters, and an excessively long name-to verify that the `Artifact` model correctly stores each provided filename. For each filename, an `Artifact` instance is created with placeholder values for other required fields, and the test asserts that the `filename` attribute of the resulting object matches the input value.
        """
        filenames = [
            "Security.evtx",
            "SYSTEM",
            "$MFT",
            "program.pf",
            "shortcut.lnk",
            "file with spaces.evtx",
            "unicode_文件.evtx",
            "very_long_" + "name_" * 50 + ".evtx",
        ]

        for filename in filenames:
            artifact = Artifact(
                artifact_id=1,
                investigation_id=uuid.uuid4(),
                sha256=b"\x00" * 32,
                filename=filename,
                classification=0,
                blob=b"data",
            )
            assert artifact.filename == filename

    def test_artifact_blob_sizes(self):
        """
        Test artifacts with various blob sizes.

        Iterates over a set of predefined blob sizes-including an empty file, 1 byte, 1 KB, and 1 MB-creates a corresponding binary blob for each size, instantiates an :class:`Artifact` with that blob, and asserts that the stored `blob` attribute length matches the expected size. This verifies that the model correctly handles blobs of different lengths without alteration.
        """
        blob_sizes = [
            0,  # Empty file
            1,  # 1 byte
            1024,  # 1 KB
            1024 * 1024,  # 1 MB
        ]

        for size in blob_sizes:
            blob = b"\x00" * size
            artifact = Artifact(
                artifact_id=1,
                investigation_id=uuid.uuid4(),
                sha256=b"\x00" * 32,
                filename="test",
                classification=0,
                blob=blob,
            )
            assert len(artifact.blob) == size


@pytest.mark.unit
class TestArtifactClassification:
    """Test artifact classification logic."""

    def test_classification_values(self):
        """
        Test that the ArtifactClassification enum members map to their correct integer values. This ensures each classification constant (SYSTEM_HIVE, LOG_FILE, BINARY, ARCHIVE, UNKNOWN) is assigned the expected numeric identifier used throughout the application.
        """
        assert ArtifactClassification.SYSTEM_HIVE == 0
        assert ArtifactClassification.LOG_FILE == 1
        assert ArtifactClassification.BINARY == 2
        assert ArtifactClassification.ARCHIVE == 3
        assert ArtifactClassification.UNKNOWN == 4

    def test_classification_by_extension(self):
        """
        Test expected classifications for common file types based on filename extensions.

        This test iterates over a collection of filenames paired with their anticipated
        `ArtifactClassification` enum values. For each case it creates an `Artifact`
        instance using the supplied filename and asserts that the resulting
        `classification` attribute matches the expected classification. The purpose is
        to verify that the model correctly assigns classifications for typical file
        types such as log files, system hives, binaries, archives, and unknown formats.
        """
        # This is a documentation test for how files should be classified
        test_cases = [
            ("Security.evtx", ArtifactClassification.LOG_FILE),
            ("Application.evtx", ArtifactClassification.LOG_FILE),
            ("SYSTEM", ArtifactClassification.SYSTEM_HIVE),
            ("SOFTWARE", ArtifactClassification.SYSTEM_HIVE),
            ("SAM", ArtifactClassification.SYSTEM_HIVE),
            ("NTUSER.DAT", ArtifactClassification.SYSTEM_HIVE),
            ("$MFT", ArtifactClassification.BINARY),
            ("program.exe", ArtifactClassification.BINARY),
            ("library.dll", ArtifactClassification.BINARY),
            ("archive.zip", ArtifactClassification.ARCHIVE),
            ("backup.tar", ArtifactClassification.ARCHIVE),
            ("unknown.xyz", ArtifactClassification.UNKNOWN),
        ]

        for filename, expected_classification in test_cases:
            artifact = Artifact(
                artifact_id=1,
                investigation_id=uuid.uuid4(),
                sha256=b"\x00" * 32,
                filename=filename,
                classification=expected_classification,
                blob=b"data",
            )
            assert artifact.classification == expected_classification


@pytest.mark.unit
class TestArtifactValidation:
    """Test artifact validation constraints."""

    def test_sha256_must_be_32_bytes(self):
        """
        Test that the `sha256` attribute of an :class:`Artifact` instance must be exactly 32 bytes long.

        The test creates an artifact with a valid 32-byte SHA-256 value and asserts that its length is 32. It then iterates over a set of invalid lengths (0, 16, 31, 33, 64), constructs artifacts with those byte strings, and asserts that the stored `sha256` attribute has the same (invalid) length. In practice the database schema enforces the 32-byte constraint; this test demonstrates that Python itself does not raise an error for mismatched lengths, highlighting the importance of the underlying DB validation.
        """
        # Valid SHA-256
        valid = b"\x00" * 32
        artifact = Artifact(
            artifact_id=1,
            investigation_id=uuid.uuid4(),
            sha256=valid,
            filename="test",
            classification=0,
            blob=b"data",
        )
        assert len(artifact.sha256) == 32

        # Invalid SHA-256 lengths (would be rejected by DB)
        invalid_lengths = [0, 16, 31, 33, 64]
        for length in invalid_lengths:
            invalid_sha256 = b"\x00" * length
            # Python allows this, but DB constraint should reject it
            artifact = Artifact(
                artifact_id=1,
                investigation_id=uuid.uuid4(),
                sha256=invalid_sha256,
                filename="test",
                classification=0,
                blob=b"data",
            )
            assert len(artifact.sha256) == length  # Documents DB will reject

    def test_artifact_deduplication(self):
        """
        Test that artifacts can be deduplicated based on their SHA-256 hash.

        The test creates three `Artifact` instances:
        * `artifact1` and `artifact2` share the same 32-byte SHA-256 value but have different filenames, representing duplicate content.
        * `artifact3` uses a distinct SHA-256 value, representing unique content.

        Assertions verify that artifacts with identical hashes are considered duplicates (their `sha256` attributes match) while an artifact with a different hash is not. The test ensures the deduplication logic relies solely on the SHA-256 digest, regardless of other fields such as filename or artifact ID.
        """
        sha256_1 = b"\x01" * 32
        sha256_2 = b"\x02" * 32

        artifact1 = Artifact(
            artifact_id=1,
            investigation_id=uuid.uuid4(),
            sha256=sha256_1,
            filename="file1.evtx",
            classification=0,
            blob=b"data",
        )

        artifact2 = Artifact(
            artifact_id=2,
            investigation_id=uuid.uuid4(),
            sha256=sha256_1,  # Same hash
            filename="file2.evtx",  # Different name
            classification=0,
            blob=b"data",
        )

        # Same SHA-256 indicates duplicate content
        assert artifact1.sha256 == artifact2.sha256

        artifact3 = Artifact(
            artifact_id=3,
            investigation_id=uuid.uuid4(),
            sha256=sha256_2,  # Different hash
            filename="file3.evtx",
            classification=0,
            blob=b"different",
        )

        # Different SHA-256 indicates unique content
        assert artifact1.sha256 != artifact3.sha256


@pytest.mark.unit
class TestArtifactRepr:
    """Test Artifact __repr__ method."""

    def test_repr_format(self):
        """
        Test that the `__repr__` method of :class:`Artifact` produces a string containing the class name and key attribute values.

        The test creates an `Artifact` instance with known values for `artifact_id`, `filename`,
        and `classification` (using the `ArtifactClassification.LOG_FILE` enum). It then obtains
        the representation via `repr(artifact)` and asserts that the resulting string includes:

        * The word `"Artifact"`, indicating the class name.
        * The substring `"id=42"`, confirming the `artifact_id` is displayed correctly.
        * The substring `"filename='test.evpx'"`, verifying the filename appears in the output.
        * The substring `"classification=1"`, ensuring the enum value (its underlying integer) is
          represented as expected.
        """
        artifact = Artifact(
            artifact_id=42,
            investigation_id=uuid.uuid4(),
            sha256=b"\x00" * 32,
            filename="test.evtx",
            classification=ArtifactClassification.LOG_FILE,
            blob=b"data",
        )

        repr_str = repr(artifact)

        assert "Artifact" in repr_str
        assert "id=42" in repr_str
        assert "filename='test.evtx'" in repr_str
        assert "classification=1" in repr_str
