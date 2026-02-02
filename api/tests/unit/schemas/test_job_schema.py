import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.job import (
    JobRead,
    ParsingJobRead,
    AgentJobRead,
    JobStatusUpdate,
)


@pytest.mark.unit
class TestJobRead:
    """Test JobRead schema."""

    def test_job_read_minimal(self):
        """
        Test that the :class:`JobRead` model correctly initializes with only the required fields, automatically setting optional timestamp and error attributes to `None`. The test creates a minimal payload containing `job_id`, `investigation_id`, `status` and `created_at`, instantiates a `JobRead` object, and asserts that all provided values are retained while `started_at`, `finished_at` and `error_message` remain unset.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "pending",
            "created_at": created_at,
        }

        job = JobRead(**data)

        assert job.job_id == 1
        assert job.investigation_id == investigation_id
        assert job.status == "pending"
        assert job.created_at == created_at
        assert job.started_at is None
        assert job.finished_at is None
        assert job.error_message is None

    def test_job_read_full(self):
        """
        Test that a JobRead instance correctly populates all fields when provided with complete data, including timestamps and a null error_message. The test creates UUID and timezone-aware datetime objects for investigation_id, created_at, started_at, and finished_at, constructs a JobRead model with these values, and asserts that the started_at and finished_at attributes on the resulting object match the original timestamps.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)
        started_at = datetime.now(timezone.utc)
        finished_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "completed",
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "error_message": None,
        }

        job = JobRead(**data)

        assert job.started_at == started_at
        assert job.finished_at == finished_at

    def test_job_read_with_error(self):
        """
        Test reading a failed job instance and verifying its error message.

        This test creates a `JobRead` object with a status of `"failed"` and an associated
        `error_message`. It asserts that the `status` attribute is set to `"failed"`
        and that the `error_message` attribute matches the provided string, confirming
        that the schema correctly captures error details for failed jobs.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "failed",
            "created_at": created_at,
            "error_message": "Processing failed: Invalid data format",
        }

        job = JobRead(**data)

        assert job.status == "failed"
        assert job.error_message == "Processing failed: Invalid data format"

    def test_job_read_missing_required_fields(self):
        """
        Test that constructing a JobRead instance without any of its required fields raises a pydantic ValidationError, and verify that the error details include each missing field (job_id, investigation_id, status, created_at).
        """
        with pytest.raises(ValidationError) as exc_info:
            JobRead()

        errors = exc_info.value.errors()
        error_fields = {error["loc"][0] for error in errors}
        assert "job_id" in error_fields
        assert "investigation_id" in error_fields
        assert "status" in error_fields
        assert "created_at" in error_fields


@pytest.mark.unit
class TestParsingJobRead:
    """Test ParsingJobRead schema."""

    def test_parsing_job_read(self):
        """
        Test parsing job schema deserialization.

        Creates a sample payload with required fields (job_id, investigation_id, status, created_at, artifact_id), instantiates a `ParsingJobRead` model using that data, and asserts that each attribute on the resulting object matches the input values. This verifies that the Pydantic schema correctly parses and stores all mandatory fields for a parsing job.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "running",
            "created_at": created_at,
            "artifact_id": 123,
        }

        job = ParsingJobRead(**data)

        assert job.job_id == 1
        assert job.investigation_id == investigation_id
        assert job.status == "running"
        assert job.artifact_id == 123

    def test_parsing_job_missing_artifact_id(self):
        """
        Test that constructing a `ParsingJobRead` instance without the required `artifact_id` field raises a `ValidationError`, and verify that the error details include `artifact_id` as a missing field.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        with pytest.raises(ValidationError) as exc_info:
            ParsingJobRead(
                job_id=1, investigation_id=investigation_id, status="pending", created_at=created_at
            )

        errors = exc_info.value.errors()
        error_fields = {error["loc"][0] for error in errors}
        assert "artifact_id" in error_fields

    def test_parsing_job_with_timestamps(self):
        """
        Test that a ParsingJobRead instance correctly stores provided timestamp fields.

        Creates a parsing job payload containing explicit `created_at`, `started_at` and `finished_at` datetime values, constructs the model with `ParsingJobRead(**data)` and asserts that the resulting object's `started_at` and `finished_at` attributes match the input timestamps. This verifies that optional timestamp fields are accepted and retained unchanged by the schema validation.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)
        started_at = datetime.now(timezone.utc)
        finished_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "completed",
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "artifact_id": 123,
        }

        job = ParsingJobRead(**data)

        assert job.started_at == started_at
        assert job.finished_at == finished_at


@pytest.mark.unit
class TestAgentJobRead:
    """Test AgentJobRead schema."""

    def test_agent_job_read(self):
        """
        Test that an AgentJobRead instance can be created from valid input data and that its fields are correctly populated, including job identifier, policy identifier, rule values dictionary, and seed instructions. The test constructs sample UUID and timestamp values, builds a data dictionary with required and optional fields, instantiates the model, and asserts that each attribute matches the expected value.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "pending",
            "created_at": created_at,
            "policy_id": "event_search",
            "rule_values": {"effort": "medium"},
            "seed_instructions": "Investigate suspicious activity",
        }

        job = AgentJobRead(**data)

        assert job.job_id == 1
        assert job.policy_id == "event_search"
        assert job.rule_values == {"effort": "medium"}
        assert job.seed_instructions == "Investigate suspicious activity"

    def test_agent_job_missing_required_fields(self):
        """
        Test that creating an :class:`AgentJobRead` instance without the required agent-specific fields raises a `ValidationError`.

        The test generates a random `investigation_id` and a current UTC timestamp for `created_at`. It then attempts to instantiate `AgentJobRead` with only the common job fields (`job_id`, `investigation_id`, `status`, `created_at`). Because the agent-specific fields `policy_id`, `rule_values` and `seed_instructions` are omitted, Pydantic should raise a `ValidationError`.

        The raised exception is captured with `pytest.raises`; its `errors()` list is inspected to collect the field names that triggered validation failures. The test asserts that each of the missing fields appears in this set, confirming that the schema enforces their presence.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        with pytest.raises(ValidationError) as exc_info:
            AgentJobRead(
                job_id=1, investigation_id=investigation_id, status="pending", created_at=created_at
            )

        errors = exc_info.value.errors()
        error_fields = {error["loc"][0] for error in errors}
        assert "policy_id" in error_fields
        assert "rule_values" in error_fields
        assert "seed_instructions" in error_fields

    def test_agent_job_with_complex_rule_values(self):
        """
        Test that an AgentJobRead instance correctly parses and stores complex nested rule values.\n\nThe test creates sample data containing a variety of nested structures within the `rule_values` field, including strings, integers, lists, and dictionaries. It then instantiates an :class:`AgentJobRead` model with this data and asserts that each nested value is accessible and matches the expected content.\n\nThis ensures that the Pydantic schema for agent jobs can handle deep, heterogeneous rule configurations without loss of fidelity.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "running",
            "created_at": created_at,
            "policy_id": "advanced_search",
            "rule_values": {
                "effort": "high",
                "max_turns": 15,
                "tools": ["search_events", "aggregate"],
                "filters": {
                    "event_type": ["login", "logout"],
                    "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
                },
            },
            "seed_instructions": "Perform advanced analysis",
        }

        job = AgentJobRead(**data)

        assert job.rule_values["effort"] == "high"
        assert job.rule_values["max_turns"] == 15
        assert job.rule_values["tools"] == ["search_events", "aggregate"]
        assert job.rule_values["filters"]["event_type"] == ["login", "logout"]

    def test_agent_job_with_empty_rule_values(self):
        """
        Test that an AgentJobRead instance can be created with an empty dictionary for the `rule_values` field, ensuring the model accepts and stores empty rule values without raising validation errors. The test constructs sample data including required fields such as `job_id`, `investigation_id`, `status`, `created_at`, `policy_id`, and `seed_instructions`, passes it to the `AgentJobRead` constructor, and asserts that the resulting object's `rule_values` attribute equals an empty dict.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "pending",
            "created_at": created_at,
            "policy_id": "simple_policy",
            "rule_values": {},
            "seed_instructions": "Simple task",
        }

        job = AgentJobRead(**data)

        assert job.rule_values == {}


@pytest.mark.unit
class TestJobStatusUpdate:
    """Test JobStatusUpdate schema."""

    def test_status_update_pending(self):
        """
        Test that a JobStatusUpdate instance can be created with the status set to "pending", and verify that the status attribute is correctly assigned while the optional error_message remains unset (None).
        """
        update = JobStatusUpdate(status="pending")

        assert update.status == "pending"
        assert update.error_message is None

    def test_status_update_running(self):
        """
        Test that a JobStatusUpdate instance can be created with the status set to "running" and that the status attribute correctly reflects this value. This verifies that the model accepts valid status strings and stores them as expected.
        """
        update = JobStatusUpdate(status="running")

        assert update.status == "running"

    def test_status_update_completed(self):
        """
        Test that a `JobStatusUpdate` instance can be instantiated with the status set to `\"completed\"` and that the resulting object's `status` attribute correctly returns `\"completed\"`.
        """
        update = JobStatusUpdate(status="completed")

        assert update.status == "completed"

    def test_status_update_failed(self):
        """
        Test that a JobStatusUpdate instance can be created with a status of "failed" and an associated error_message, and verify that both attributes are correctly set on the resulting object.
        """
        update = JobStatusUpdate(status="failed", error_message="Processing error occurred")

        assert update.status == "failed"
        assert update.error_message == "Processing error occurred"

    def test_status_update_invalid_status(self):
        """
        Test that providing an invalid status value to `JobStatusUpdate` triggers a `ValidationError` when instantiated. This ensures the model enforces allowed status enumerations.
        """
        with pytest.raises(ValidationError):
            JobStatusUpdate(status="invalid_status")

    def test_status_update_empty_status(self):
        """
        Test that providing an empty string for the `status` field of :class:`JobStatusUpdate` triggers a Pydantic `ValidationError`. The test ensures that the model enforces non-empty status values as required by its validation rules.
        """
        with pytest.raises(ValidationError):
            JobStatusUpdate(status="")

    def test_status_update_case_sensitive(self):
        """
        Test that providing a status value with incorrect case raises a ValidationError, confirming that the status field is case-sensitive.
        """
        with pytest.raises(ValidationError):
            JobStatusUpdate(status="PENDING")  # Must be lowercase

    def test_status_update_missing_status(self):
        """
        Test that initializing JobStatusUpdate without providing the required 'status' field raises a ValidationError, confirming proper validation of mandatory fields.
        """
        with pytest.raises(ValidationError):
            JobStatusUpdate()


@pytest.mark.unit
class TestJobSchemaEdgeCases:
    """Test edge cases for job schemas."""

    def test_job_with_very_long_error_message(self):
        """
        Test that a JobRead instance can store and retrieve an exceptionally long error_message string without truncation or validation errors, ensuring the length exceeds 10,000 characters.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)
        long_error = "Error: " + ("A" * 10000)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "failed",
            "created_at": created_at,
            "error_message": long_error,
        }

        job = JobRead(**data)

        assert len(job.error_message) > 10000

    def test_job_with_unicode_error_message(self):
        """
        Test that a JobRead instance correctly stores and preserves Unicode characters in the error_message field, ensuring that non-ASCII text such as Japanese characters and emoji are retained without alteration. The test creates a job with a specific investigation_id, timestamp, and an error_message containing Unicode symbols, then verifies that those symbols are present in the resulting object's error_message attribute.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "failed",
            "created_at": created_at,
            "error_message": "エラー: 処理失敗 🚫",
        }

        job = JobRead(**data)

        assert "エラー" in job.error_message
        assert "🚫" in job.error_message

    def test_agent_job_with_unicode_instructions(self):
        """
        Test that an AgentJobRead instance correctly accepts and retains Unicode characters in the `seed_instructions` field.

        This test creates a sample payload containing Japanese text and an emoji, constructs an `AgentJobRead` model from it, and asserts that both the Unicode string and the emoji are present in the resulting object's `seed_instructions` attribute. It verifies proper handling of non-ASCII characters by the Pydantic schema.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "pending",
            "created_at": created_at,
            "policy_id": "test",
            "rule_values": {},
            "seed_instructions": "調査を実行する 🔍",
        }

        job = AgentJobRead(**data)

        assert "調査" in job.seed_instructions
        assert "🔍" in job.seed_instructions

    def test_parsing_job_with_negative_artifact_id(self):
        """
        Test parsing job with negative artifact ID.

        This test verifies that the `ParsingJobRead` schema accepts an `artifact_id` value that is negative, confirming that the schema validates only the type (integer) and does not enforce a non-negative constraint.

        Steps performed:
        - Generate a random `investigation_id` using `uuid4`.
        - Set `created_at` to the current UTC datetime.
        - Build a data dictionary containing required fields for a parsing job, including an `artifact_id` of `-1`.
        - Instantiate `ParsingJobRead` with the provided data.
        - Assert that the resulting object's `artifact_id` attribute equals `-1`.

        The test ensures that no validation error is raised for negative artifact identifiers.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        # Schema doesn't validate artifact_id value, only type
        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "pending",
            "created_at": created_at,
            "artifact_id": -1,
        }

        job = ParsingJobRead(**data)

        assert job.artifact_id == -1

    def test_job_status_all_valid_values(self):
        """
        Test that the JobStatusUpdate model accepts each of the defined valid status strings and correctly stores the provided value.
        """
        valid_statuses = ["pending", "running", "completed", "failed"]

        for status in valid_statuses:
            update = JobStatusUpdate(status=status)
            assert update.status == status

    def test_agent_job_with_special_chars_in_policy_id(self):
        """
        Test that an AgentJobRead instance correctly accepts and preserves a policy_id containing special characters such as hyphens, underscores, and periods. The test constructs a job payload with a policy_id like `policy-with_special.chars` and verifies that the resulting model stores the exact string without alteration. This ensures the schema does not unintentionally sanitize or reject valid Unicode/special-character identifiers.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "pending",
            "created_at": created_at,
            "policy_id": "policy-with_special.chars",
            "rule_values": {},
            "seed_instructions": "Test",
        }

        job = AgentJobRead(**data)

        assert job.policy_id == "policy-with_special.chars"

    def test_job_with_null_timestamps(self):
        """
        Test that a JobRead instance correctly accepts explicit `None` values for optional timestamp fields and the error message.

        Creates a job payload with required fields (`job_id`, `investigation_id`, `status`, `created_at`) and sets `started_at`, `finished_at` and `error_message` to `None`. Instantiates :class:`JobRead` with this data and asserts that the resulting object's optional attributes retain the `None` values, confirming that null timestamps and a missing error message are handled without validation errors.
        """
        investigation_id = uuid4()
        created_at = datetime.now(timezone.utc)

        data = {
            "job_id": 1,
            "investigation_id": investigation_id,
            "status": "pending",
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
            "error_message": None,
        }

        job = JobRead(**data)

        assert job.started_at is None
        assert job.finished_at is None
        assert job.error_message is None
