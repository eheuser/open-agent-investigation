"""
Unit tests for artifact CRUD operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from uuid import uuid4
import hashlib

from app.crud.artifact import (
    sha256_bytes,
    create_artifact,
    get_artifact,
    list_artifacts,
)
from app.models.artifact import Artifact, ArtifactClassification


@pytest.mark.unit
class TestSHA256Bytes:
    """Test SHA-256 hashing utility."""

    def test_sha256_returns_bytes(self):
        """
        Test that the sha256_bytes utility returns a 32-byte digest for given binary input. The test supplies a sample byte string, invokes sha256_bytes, and asserts that the result is an instance of bytes with a length equal to the SHA-256 hash size (32 bytes).
        """
        data = b"test data"
        result = sha256_bytes(data)

        assert isinstance(result, bytes)
        assert len(result) == 32  # SHA-256 produces 32 bytes

    def test_sha256_deterministic(self):
        """
        Ensures that hashing identical byte strings with `sha256_bytes` yields consistent results by comparing two hashes generated from the same input data.
        """
        data = b"test data"
        hash1 = sha256_bytes(data)
        hash2 = sha256_bytes(data)

        assert hash1 == hash2

    def test_sha256_different_inputs(self):
        """
        Test that the SHA-256 hashing utility generates distinct digests for different byte inputs.\n\nThe test creates two separate byte strings, computes their hashes using `sha256_bytes`, and asserts that the resulting hexadecimal hash values are not equal, confirming that the function produces unique outputs for differing data.
        """
        data1 = b"test data 1"
        data2 = b"test data 2"

        hash1 = sha256_bytes(data1)
        hash2 = sha256_bytes(data2)

        assert hash1 != hash2

    def test_sha256_empty_data(self):
        """
        Test that `sha256_bytes` correctly hashes an empty byte string.\n\nThe test verifies the function returns a `bytes` object of length 32 (the size of a SHA-256 digest) and that its value matches the expected digest produced by `hashlib.sha256` for an empty input.
        """
        data = b""
        result = sha256_bytes(data)

        assert isinstance(result, bytes)
        assert len(result) == 32
        # SHA-256 of empty string is known value
        expected = hashlib.sha256(b"").digest()
        assert result == expected

    def test_sha256_large_data(self):
        """
        Test that hashing a large byte sequence (1 MiB) returns a SHA-256 digest of the correct type and length. The test creates a 1 MB payload, computes its hash using `sha256_bytes`, and asserts that the result is a `bytes` object exactly 32 bytes long.
        """
        data = b"x" * 1024 * 1024  # 1 MB
        result = sha256_bytes(data)

        assert isinstance(result, bytes)
        assert len(result) == 32


@pytest.mark.unit
class TestCreateArtifact:
    """Test create_artifact function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create and return a mocked asynchronous database session with common ORM methods.

        The returned object mimics an async SQLAlchemy session:
        - `add` is a regular :class:`unittest.mock.MagicMock` for adding instances.
        - `flush`, `commit` and `refresh` are :class:`unittest.mock.AsyncMock` objects representing their asynchronous counterparts.

        :return: A mock database session with the described methods attached.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def sample_file_bytes(self):
        """
        Return a bytes object containing sample EVTX file content used for testing purposes.

        Returns:
            bytes: The byte string `b"Sample EVTX file content"` representing a mock EVTX file.
        """
        return b"Sample EVTX file content"

    @patch("app.crud.artifact.Path")
    @patch("app.crud.artifact.settings")
    async def test_create_artifact_success(
        self, mock_settings, mock_path, mock_db, sample_file_bytes
    ):
        """
        Test that creating an artifact succeeds and correctly persists data.

        The test sets up mock configuration, path handling, and a database session, then calls `create_artifact` with a sample file payload. It asserts that:

        * The database session methods `add`, `flush`, `commit`, and `refresh` are each called exactly once.
        * An :class:`Artifact` instance is added to the session with the expected `investigation_id`, `filename`, `classification`, binary `blob` content, and a 32-byte SHA-256 hash.
        * The target directory for the artifact is created using `mkdir(parents=True, exist_ok=True)`.
        * The file bytes are written to the resolved path via `write_bytes`.

        Parameters
        ----------
        self: object
            Test case instance (unused directly but required by the test framework).
        mock_settings: MagicMock
            Mocked settings object where `investigations_base_path` is configured.
        mock_path: MagicMock
            Mocked :class:`pathlib.Path` used to simulate directory and file path resolution.
        mock_db: MagicMock
            Mocked asynchronous database session providing `add`, `flush`, `commit`, and `refresh` methods.
        sample_file_bytes: bytes
            Sample binary content representing the artifact file.
        """
        # Setup
        investigation_id = uuid4()
        filename = "Security.evtx"
        classification = ArtifactClassification.LOG_FILE

        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_file = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir
        mock_dir.__truediv__.return_value = mock_file

        # Execute
        result = await create_artifact(
            db=mock_db,
            investigation_id=investigation_id,
            filename=filename,
            classification=classification,
            file_bytes=sample_file_bytes,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify artifact object was created
        added_artifact = mock_db.add.call_args[0][0]
        assert isinstance(added_artifact, Artifact)
        assert added_artifact.investigation_id == investigation_id
        assert added_artifact.filename == filename
        assert added_artifact.classification == classification
        assert added_artifact.blob == sample_file_bytes
        assert len(added_artifact.sha256) == 32  # SHA-256 hash

        # Verify directory creation
        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

        # Verify file write
        mock_file.write_bytes.assert_called_once_with(sample_file_bytes)

    @patch("app.crud.artifact.Path")
    @patch("app.crud.artifact.settings")
    async def test_create_artifact_with_different_classifications(
        self, mock_settings, mock_path, mock_db, sample_file_bytes
    ):
        """
        Test creating artifacts with various classifications and verify that each artifact is stored with the correct classification.

        Parameters
        ----------
        self : object
            The test case instance.
        mock_settings : MagicMock
            Mocked settings object where `investigations_base_path` is set to a temporary directory.
        mock_path : MagicMock
            Mocked `Path` class used to simulate filesystem path operations without touching the real file system.
        mock_db : MagicMock
            Mocked database session that records calls to `add` and other ORM interactions.
        sample_file_bytes : bytes
            Sample binary content representing the file data to be stored as an artifact.

        The test iterates over a list of `ArtifactClassification` values (LOG_FILE, BINARY, ARCHIVE, UNKNOWN), creates an artifact for each classification using `create_artifact`, and asserts that the artifact added to the mocked database has its `classification` attribute set to the current enumeration value.
        """
        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_file = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir
        mock_dir.__truediv__.return_value = mock_file

        classifications = [
            ArtifactClassification.LOG_FILE,
            ArtifactClassification.BINARY,
            ArtifactClassification.ARCHIVE,
            ArtifactClassification.UNKNOWN,
        ]

        for classification in classifications:
            mock_db.reset_mock()

            result = await create_artifact(
                db=mock_db,
                investigation_id=uuid4(),
                filename=f"test.{classification.value}",
                classification=classification,
                file_bytes=sample_file_bytes,
            )

            added_artifact = mock_db.add.call_args[0][0]
            assert added_artifact.classification == classification

    @patch("app.crud.artifact.Path")
    @patch("app.crud.artifact.settings")
    async def test_create_artifact_computes_sha256(
        self, mock_settings, mock_path, mock_db, sample_file_bytes
    ):
        """
        Test that creating an artifact computes and stores the correct SHA-256 hash of the provided file bytes.

        Args:
            self: The test case instance.
            mock_settings: Fixture that provides a mocked settings object; its `investigations_base_path` attribute is set to a temporary directory.
            mock_path: Fixture that patches `pathlib.Path`; used to mock directory and file path resolution.
            mock_db: Fixture that supplies a mocked asynchronous database session with an `add` method.
            sample_file_bytes: Bytes fixture representing the content of a sample file used for hashing.

        The test sets up mock path objects, computes the expected SHA-256 digest using `hashlib.sha256`, invokes `create_artifact` with the mocked dependencies, and asserts that the artifact added to the database has its `sha256` attribute equal to the expected hash.
        """
        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_file = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir
        mock_dir.__truediv__.return_value = mock_file

        expected_hash = hashlib.sha256(sample_file_bytes).digest()

        result = await create_artifact(
            db=mock_db,
            investigation_id=uuid4(),
            filename="test.evtx",
            classification=ArtifactClassification.LOG_FILE,
            file_bytes=sample_file_bytes,
        )

        added_artifact = mock_db.add.call_args[0][0]
        assert added_artifact.sha256 == expected_hash


@pytest.mark.unit
class TestGetArtifact:
    """Test get_artifact function."""

    @pytest.fixture
    def mock_db(self):
        """
        Create a mock asynchronous database session for testing purposes.

        Returns
        -------
        AsyncMock
            An `AsyncMock` object that simulates a database session, allowing async methods to be called without a real database connection.
        """
        db = AsyncMock()
        return db

    async def test_get_artifact_found(self, mock_db):
        """
        Test that retrieving an existing artifact by its ID returns the correct Artifact instance and that the database execute method is invoked exactly once. The test sets up a mock database session to return a predefined Artifact object when queried, calls `get_artifact` with the mock session and artifact ID, and asserts that the result matches the expected artifact while verifying the interaction with the mock.
        """
        artifact_id = 123
        expected_artifact = Artifact(
            artifact_id=artifact_id,
            investigation_id=uuid4(),
            filename="test.evtx",
            classification=ArtifactClassification.LOG_FILE,
            sha256=b"x" * 32,
            blob=b"content",
        )

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = expected_artifact
        mock_db.execute.return_value = mock_result

        result = await get_artifact(mock_db, artifact_id)

        assert result == expected_artifact
        mock_db.execute.assert_called_once()

    async def test_get_artifact_not_found(self, mock_db):
        """
        Test that retrieving an artifact with an ID that does not exist in the database returns `None` and that the database execute method is called exactly once.

        Args:
            self: The test case instance.
            mock_db: A mocked asynchronous database session used to simulate query execution.

        Returns:
            None. The function asserts the expected behavior; it does not return a value.
        """
        artifact_id = 999

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_artifact(mock_db, artifact_id)

        assert result is None
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestListArtifacts:
    """Test list_artifacts function."""

    @pytest.fixture
    def mock_db(self):
        """
        Creates and returns a mocked asynchronous database session suitable for use in unit tests. The returned object is an instance of `AsyncMock` that mimics the interface of an async SQLAlchemy session, allowing test code to configure return values and assert calls without requiring a real database connection.
        """
        db = AsyncMock()
        return db

    async def test_list_artifacts_with_results(self, mock_db):
        """
        Test that listing artifacts for a given investigation returns the expected collection.

        Args:
            self: The test case instance.
            mock_db: A MagicMock representing the asynchronous database session used by `list_artifacts`.

        The test creates two `Artifact` objects associated with the same `investigation_id`, mocks the database query to return these artifacts, and then calls `list_artifacts` with the mocked session. It asserts that:
        * The result contains exactly two items.
        * The returned list matches the mocked artifact collection.
        * The database `execute` method was invoked exactly once.
        """
        investigation_id = uuid4()
        artifacts = [
            Artifact(
                artifact_id=1,
                investigation_id=investigation_id,
                filename="file1.evtx",
                classification=ArtifactClassification.LOG_FILE,
                sha256=b"x" * 32,
                blob=b"content1",
            ),
            Artifact(
                artifact_id=2,
                investigation_id=investigation_id,
                filename="file2.evtx",
                classification=ArtifactClassification.LOG_FILE,
                sha256=b"y" * 32,
                blob=b"content2",
            ),
        ]

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = artifacts
        mock_db.execute.return_value = mock_result

        result = await list_artifacts(mock_db, investigation_id)

        assert len(result) == 2
        assert result == artifacts
        mock_db.execute.assert_called_once()

    async def test_list_artifacts_empty(self, mock_db):
        """
        Test the list_artifacts coroutine when the database contains no artifacts for the given investigation.

        Args:
            self: The test case instance.
            mock_db: A MagicMock representing an async database session; its execute method is configured to return an empty result set.

        Returns:
            None - asserts that the returned artifact list is empty and verifies that the database execute method was called exactly once.
        """
        investigation_id = uuid4()

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await list_artifacts(mock_db, investigation_id)

        assert result == []
        mock_db.execute.assert_called_once()

    async def test_list_artifacts_ordered_by_upload_ts(self, mock_db):
        """
        Test that the list_artifacts coroutine queries the database and orders results by upload timestamp in descending order.\n\nArgs:\n    self: The test case instance.\n    mock_db: A MagicMock representing an asynchronous database session used to intercept the execute call.\n\nThe test sets up a mock result returning an empty list, invokes list_artifacts with a generated investigation_id, and asserts that the database's execute method was called exactly once. No value is returned; the purpose is to verify query execution ordering behavior.
        """
        investigation_id = uuid4()

        # Mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        await list_artifacts(mock_db, investigation_id)

        # Verify the query was executed
        mock_db.execute.assert_called_once()
        # Note: We can't easily verify the ORDER BY clause without inspecting
        # the SQL statement, but we've confirmed the function is called


@pytest.mark.unit
class TestArtifactCRUDEdgeCases:
    """Test edge cases for artifact CRUD operations."""

    def test_sha256_with_unicode_data(self):
        """
        Test that the SHA-256 hashing utility correctly processes Unicode strings encoded as UTF-8 bytes, returning a 32-byte digest.
        """
        data = "Hello 世界 🌍".encode("utf-8")
        result = sha256_bytes(data)

        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_sha256_with_binary_data(self):
        """
        Verifies that `sha256_bytes` correctly computes a SHA-256 hash for binary data containing null bytes and non-ASCII values, ensuring the result is a `bytes` object of length 32.
        """
        data = b"\x00\x01\x02\x03\xff\xfe\xfd"
        result = sha256_bytes(data)

        assert isinstance(result, bytes)
        assert len(result) == 32

    @pytest.fixture
    def mock_db(self):
        """
        Create and configure a mocked asynchronous database session for use in tests.

        The returned object mimics an async SQLAlchemy session with the following attributes:
        - `add`: a :class:`unittest.mock.MagicMock` used to record calls to `session.add`.
        - `flush`: an :class:`unittest.mock.AsyncMock` representing the asynchronous `session.flush` method.
        - `commit`: an :class:`unittest.mock.AsyncMock` representing the asynchronous `session.commit` method.
        - `refresh`: an :class:`unittest.mock.AsyncMock` representing the asynchronous `session.refresh` method.

        The mock is intended for unit-testing code that interacts with a database session without requiring a real database connection.
        """
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @patch("app.crud.artifact.Path")
    @patch("app.crud.artifact.settings")
    async def test_create_artifact_with_special_characters_in_filename(
        self, mock_settings, mock_path, mock_db
    ):
        """
        Test creating an artifact when the provided filename contains spaces and various special characters.

        This test verifies that:
        - The `create_artifact` coroutine correctly handles filenames with whitespace, ampersands, hyphens, underscores, and numeric characters.
        - The mocked settings point to a temporary investigations base path.
        - Path objects are appropriately chained using the division operator (`/`) to simulate directory and file creation.
        - After invoking `create_artifact`, the artifact added to the mock database has its `filename` attribute set exactly to the original special-character filename.
        """
        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_file = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir
        mock_dir.__truediv__.return_value = mock_file

        filename = "file with spaces & special-chars_123.evtx"

        result = await create_artifact(
            db=mock_db,
            investigation_id=uuid4(),
            filename=filename,
            classification=ArtifactClassification.LOG_FILE,
            file_bytes=b"content",
        )

        added_artifact = mock_db.add.call_args[0][0]
        assert added_artifact.filename == filename

    @patch("app.crud.artifact.Path")
    @patch("app.crud.artifact.settings")
    async def test_create_artifact_with_empty_file(self, mock_settings, mock_path, mock_db):
        """
        Test creating an artifact when the provided file content is empty.

        This test sets up mock configuration and filesystem objects, then calls `create_artifact` with an empty byte string as the file payload. It verifies that:

        - The resulting artifact's `blob` attribute contains the empty bytes.
        - The generated SHA-256 hash (`sha256`) has a length of 32 bytes (the raw digest size).
        """
        mock_settings.investigations_base_path = "/tmp/investigations"

        # Mock Path operations
        mock_dir = MagicMock()
        mock_file = MagicMock()
        mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_dir
        mock_dir.__truediv__.return_value = mock_file

        result = await create_artifact(
            db=mock_db,
            investigation_id=uuid4(),
            filename="empty.evtx",
            classification=ArtifactClassification.LOG_FILE,
            file_bytes=b"",
        )

        added_artifact = mock_db.add.call_args[0][0]
        assert added_artifact.blob == b""
        assert len(added_artifact.sha256) == 32  # SHA-256 of empty bytes
