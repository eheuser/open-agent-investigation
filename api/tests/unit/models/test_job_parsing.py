"""
Unit tests for ParsingJob model.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.models.job_parsing import ParsingJob, JobStatus


@pytest.mark.unit
class TestJobStatus:
    """Test JobStatus enum."""

    def test_job_status_values(self):
        """
        Test that each member of the JobStatus enumeration is defined with the correct string value, ensuring the constants PENDING, RUNNING, COMPLETED, and FAILED map to "pending", "running", "completed", and "failed" respectively.
        """
        assert JobStatus.PENDING == "pending"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"

    def test_job_status_from_string(self):
        """
        Test that converting string literals to `JobStatus` enum members works correctly.\n\nThe test verifies that passing the lowercase status names `\"pending\"`, `\"running\"`, `\"completed\"` and `\"failed\"` to the :class:`JobStatus` constructor returns the corresponding enum members `JobStatus.PENDING`, `JobStatus.RUNNING`, `JobStatus.COMPLETED` and `JobStatus.FAILED`. This ensures that the enum’s value-to-member conversion is case-sensitive and matches the defined string values.
        """
        assert JobStatus("pending") == JobStatus.PENDING
        assert JobStatus("running") == JobStatus.RUNNING
        assert JobStatus("completed") == JobStatus.COMPLETED
        assert JobStatus("failed") == JobStatus.FAILED


@pytest.mark.unit
class TestParsingJobModel:
    """Test ParsingJob model structure."""

    def test_parsing_job_creation_minimal(self):
        """
        Test creating a :class:`ParsingJob` instance with only the required fields and verify that all optional attributes are set to `None`.
        """
        investigation_id = uuid4()

        job = ParsingJob(
            job_id=1, investigation_id=investigation_id, artifact_id=123, status=JobStatus.PENDING
        )

        assert job.job_id == 1
        assert job.investigation_id == investigation_id
        assert job.artifact_id == 123
        assert job.status == JobStatus.PENDING
        assert job.worker_id is None
        assert job.started_at is None
        assert job.finished_at is None
        assert job.error_message is None

    def test_parsing_job_creation_full(self):
        """
        Test creating a :class:`ParsingJob` instance with all optional and required fields populated.

        The test constructs unique identifiers for an investigation and a worker using `uuid4` and timestamps for creation, start, and finish moments using the current UTC time. It then instantiates a :class:`ParsingJob` with:

        * `job_id` set to `1`.
        * The generated `investigation_id` and `worker_id`.
        * An example `artifact_id` of `123`.
        * `status` explicitly set to :data:`JobStatus.COMPLETED`.
        * The three timestamp fields `created_at`, `started_at` and `finished_at`.
        * `error_message` left as `None`.

        After creation, the test asserts that the `worker_id` and each of the timestamp attributes on the resulting object match the values supplied during construction. This verifies that the model correctly stores all provided data without alteration.
        """
        investigation_id = uuid4()
        worker_id = uuid4()
        created_at = datetime.now(timezone.utc)
        started_at = datetime.now(timezone.utc)
        finished_at = datetime.now(timezone.utc)

        job = ParsingJob(
            job_id=1,
            investigation_id=investigation_id,
            artifact_id=123,
            status=JobStatus.COMPLETED,
            worker_id=worker_id,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            error_message=None,
        )

        assert job.worker_id == worker_id
        assert job.created_at == created_at
        assert job.started_at == started_at
        assert job.finished_at == finished_at

    def test_parsing_job_with_error(self):
        """
        Test parsing job with error message.

        Creates a `ParsingJob` instance representing a failed job and verifies that the status and error_message attributes are correctly set.

        * **Setup** - Instantiates `ParsingJob` with:
          - `job_id` set to `1`
          - `investigation_id` generated via `uuid4()`
          - `artifact_id` set to `123`
          - `status` set to `JobStatus.FAILED`
          - `error_message` containing a descriptive failure reason

        * **Assertions** - Confirms that:
          - `job.status` equals `JobStatus.FAILED`
          - `job.error_message` matches the provided error string.
        """
        job = ParsingJob(
            job_id=1,
            investigation_id=uuid4(),
            artifact_id=123,
            status=JobStatus.FAILED,
            error_message="Parsing failed: Invalid EVTX format",
        )

        assert job.status == JobStatus.FAILED
        assert job.error_message == "Parsing failed: Invalid EVTX format"

    def test_parsing_job_status_transitions(self):
        """
        Test that a ParsingJob instance correctly updates its status attribute through valid state transitions: from PENDING to RUNNING and then to COMPLETED, asserting the status after each assignment. This verifies that the job's status field accepts enum values and reflects changes as expected.
        """
        job = ParsingJob(
            job_id=1, investigation_id=uuid4(), artifact_id=123, status=JobStatus.PENDING
        )

        # Transition to running
        job.status = JobStatus.RUNNING
        assert job.status == JobStatus.RUNNING

        # Transition to completed
        job.status = JobStatus.COMPLETED
        assert job.status == JobStatus.COMPLETED

    def test_parsing_job_repr(self):
        """
        Test that the string representation of a `ParsingJob` instance includes key identifying information such as the class name, job ID, status (in lowercase), and artifact ID. The test creates a minimal `ParsingJob` with known values, obtains its `repr`, and asserts that each expected component appears in the resulting string.
        """
        job = ParsingJob(
            job_id=1, investigation_id=uuid4(), artifact_id=123, status=JobStatus.PENDING
        )

        repr_str = repr(job)
        assert "ParsingJob" in repr_str
        assert "id=1" in repr_str
        assert "status=pending" in repr_str
        assert "artifact=123" in repr_str

    def test_parsing_job_tablename(self):
        """
        Test that the :class:`ParsingJob` model defines the expected SQLAlchemy table name.\n\nThe test asserts that `ParsingJob.__tablename__` is exactly `\"jobs_parsing\"` to verify the ORM mapping aligns with the database schema.
        """
        assert ParsingJob.__tablename__ == "jobs_parsing"

    def test_parsing_job_has_required_columns(self):
        """
        Test that the :class:`ParsingJob` model defines all mandatory attributes required for database persistence and job tracking, ensuring each expected column (job_id, investigation_id, artifact_id, status, worker_id, created_at, started_at, finished_at, error_message) is present on the class.
        """
        assert hasattr(ParsingJob, "job_id")
        assert hasattr(ParsingJob, "investigation_id")
        assert hasattr(ParsingJob, "artifact_id")
        assert hasattr(ParsingJob, "status")
        assert hasattr(ParsingJob, "worker_id")
        assert hasattr(ParsingJob, "created_at")
        assert hasattr(ParsingJob, "started_at")
        assert hasattr(ParsingJob, "finished_at")
        assert hasattr(ParsingJob, "error_message")


@pytest.mark.unit
class TestParsingJobEdgeCases:
    """Test edge cases for ParsingJob model."""

    def test_parsing_job_with_very_long_error_message(self):
        """
        Test that a ParsingJob can store and retain an exceptionally long error_message string.

        The test constructs a very large error message (over 10 000 characters), creates a `ParsingJob` instance with `status=JobStatus.FAILED` and the generated message, then asserts that the stored `error_message` length exceeds the 10 000-character threshold. This verifies that the model does not truncate or otherwise mishandle unusually long error strings.
        """
        long_error = "Error: " + ("A" * 10000)

        job = ParsingJob(
            job_id=1,
            investigation_id=uuid4(),
            artifact_id=123,
            status=JobStatus.FAILED,
            error_message=long_error,
        )

        assert len(job.error_message) > 10000

    def test_parsing_job_with_unicode_error_message(self):
        """
        Test that a ParsingJob instance correctly stores and retains a Unicode error message.

        This test creates a `ParsingJob` with `status` set to :pyattr:`JobStatus.FAILED` and an `error_message` containing Japanese characters and an emoji. It then asserts that both the Japanese substring and the emoji are present in the `error_message` attribute, verifying proper handling of Unicode text.
        """
        job = ParsingJob(
            job_id=1,
            investigation_id=uuid4(),
            artifact_id=123,
            status=JobStatus.FAILED,
            error_message="エラー: ファイル形式が無効です 🚫",
        )

        assert "エラー" in job.error_message
        assert "🚫" in job.error_message

    def test_parsing_job_with_multiline_error(self):
        """
        Test parsing job with multiline error message.

        This test verifies that a `ParsingJob` instance can store and retain an error
        message containing multiple lines, including line breaks and additional sections
        such as a stack trace. It asserts that the stored `error_message` includes the
        specific substring `"Stack trace:"` and contains newline characters, confirming
        that multiline strings are preserved correctly.
        """
        error_message = """Parsing failed at line 42:
Expected: valid EVTX header
Received: corrupted data

Stack trace:
  File "parser.py", line 123
  File "evtx.py", line 456"""

        job = ParsingJob(
            job_id=1,
            investigation_id=uuid4(),
            artifact_id=123,
            status=JobStatus.FAILED,
            error_message=error_message,
        )

        assert "Stack trace:" in job.error_message
        assert "\n" in job.error_message

    def test_parsing_job_multiple_instances(self):
        """
        Test creating multiple ParsingJob instances and verify their properties.

        Creates ten `ParsingJob` objects with sequential `job_id` values, the same `investigation_id`, distinct `artifact_id` values, and an initial status of :class:`JobStatus.PENDING`.

        The test asserts that:
        - Exactly ten job instances are created.
        - Every element in the resulting list is an instance of `ParsingJob`.
        - Each job’s `status` attribute equals `JobStatus.PENDING`.
        """
        investigation_id = uuid4()

        jobs = [
            ParsingJob(
                job_id=i,
                investigation_id=investigation_id,
                artifact_id=100 + i,
                status=JobStatus.PENDING,
            )
            for i in range(10)
        ]

        assert len(jobs) == 10
        assert all(isinstance(job, ParsingJob) for job in jobs)
        assert all(job.status == JobStatus.PENDING for job in jobs)

    def test_parsing_job_with_same_artifact_different_investigations(self):
        """
        Test that two ParsingJob instances can reference the same artifact identifier while belonging to different investigations.

        The test creates an `artifact_id` shared by two jobs, each with a distinct `investigation_id` generated via `uuid4()`. It verifies that:
        - The `artifact_id` attribute of both jobs is equal.
        - The `investigation_id` attributes are not equal, confirming that the same artifact can be processed in separate investigations without conflict.
        """
        artifact_id = 123

        job1 = ParsingJob(
            job_id=1, investigation_id=uuid4(), artifact_id=artifact_id, status=JobStatus.PENDING
        )

        job2 = ParsingJob(
            job_id=2, investigation_id=uuid4(), artifact_id=artifact_id, status=JobStatus.PENDING
        )

        assert job1.artifact_id == job2.artifact_id
        assert job1.investigation_id != job2.investigation_id
