import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.models.job_agent import AgentJob
from app.models.job_parsing import JobStatus


@pytest.mark.unit
class TestAgentJobModel:
    """Test AgentJob model structure."""

    def test_agent_job_creation_minimal(self):
        """
        Test creating an :class:`AgentJob` instance using only the required fields and verifying that all attributes are set correctly, with optional fields remaining `None` or empty as appropriate.
        """
        investigation_id = uuid4()

        job = AgentJob(
            job_id=1,
            investigation_id=investigation_id,
            user_id=1,
            policy_id="event_search",
            rule_values={},
            seed_instructions="Search for events",
            status=JobStatus.PENDING,
        )

        assert job.job_id == 1
        assert job.investigation_id == investigation_id
        assert job.user_id == 1
        assert job.policy_id == "event_search"
        assert job.rule_values == {}
        assert job.seed_instructions == "Search for events"
        assert job.status == JobStatus.PENDING
        assert job.worker_id is None
        assert job.started_at is None
        assert job.finished_at is None
        assert job.error_message is None

    def test_agent_job_creation_full(self):
        """
        Test creating an :class:`AgentJob` instance with all possible fields populated.

        The test constructs a fully-specified `AgentJob` using explicit values for identifiers, timestamps, rule values, seed instructions, status, worker information, and metadata. It then asserts that the `worker_id`, timestamp attributes (`created_at`, `started_at`, `finished_at`), and `job_metadata` are stored correctly on the resulting object. This verifies that the model accepts a complete set of inputs without alteration.
        """
        investigation_id = uuid4()
        worker_id = uuid4()
        created_at = datetime.now(timezone.utc)
        started_at = datetime.now(timezone.utc)
        finished_at = datetime.now(timezone.utc)

        job = AgentJob(
            job_id=1,
            investigation_id=investigation_id,
            user_id=1,
            policy_id="advanced_search",
            rule_values={"effort": "high", "max_turns": 15},
            seed_instructions="Perform advanced investigation",
            status=JobStatus.COMPLETED,
            worker_id=worker_id,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            error_message=None,
            job_metadata={"custom": "data"},
        )

        assert job.worker_id == worker_id
        assert job.created_at == created_at
        assert job.started_at == started_at
        assert job.finished_at == finished_at
        assert job.job_metadata == {"custom": "data"}

    def test_agent_job_with_complex_rule_values(self):
        """
        Test that an AgentJob instance correctly stores and retrieves complex nested rule values.

        The test constructs a dictionary containing various data types:
        - Simple key-value pairs (e.g., `"effort": "high"`).
        - Lists of strings (e.g., `"tools"`).
        - Nested dictionaries with further nesting (e.g., `"filters"`, `"date_range"`).
        - Boolean options.

        An `AgentJob` is instantiated with the complex `rule_values` dictionary and a minimal set of required fields. The assertions verify that:
        1. Top-level entries are preserved unchanged.
        2. List values retain their order and contents.
        3. Deeply nested values (such as the start date inside `date_range`) are accessible via standard dictionary indexing.

        This ensures that the model does not flatten, truncate, or otherwise corrupt complex rule structures during initialization.
        """
        rule_values = {
            "effort": "high",
            "max_turns": 15,
            "tools": ["search_events", "aggregate", "hybrid_search"],
            "filters": {
                "event_type": ["login", "logout"],
                "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            },
            "options": {"verbose": True, "save_intermediate": False},
        }

        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="complex_policy",
            rule_values=rule_values,
            seed_instructions="Complex investigation",
            status=JobStatus.PENDING,
        )

        assert job.rule_values["effort"] == "high"
        assert job.rule_values["tools"] == ["search_events", "aggregate", "hybrid_search"]
        assert job.rule_values["filters"]["date_range"]["start"] == "2024-01-01"

    def test_agent_job_status_transitions(self):
        """
        Test that an AgentJob instance correctly updates its status attribute through valid state transitions: from PENDING to RUNNING and then to COMPLETED, asserting the status after each assignment.
        """
        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="test",
            rule_values={},
            seed_instructions="Test",
            status=JobStatus.PENDING,
        )

        # Transition through states
        job.status = JobStatus.RUNNING
        assert job.status == JobStatus.RUNNING

        job.status = JobStatus.COMPLETED
        assert job.status == JobStatus.COMPLETED

    def test_agent_job_repr(self):
        """
        Test that the string representation of an `AgentJob` instance includes key identifying information such as the class name, job identifier, status (in lowercase), and policy identifier. The test creates a minimal `AgentJob` with known values, obtains its `repr`, and asserts that the expected substrings appear in the result.
        """
        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="event_search",
            rule_values={},
            seed_instructions="Test",
            status=JobStatus.RUNNING,
        )

        repr_str = repr(job)
        assert "AgentJob" in repr_str
        assert "id=1" in repr_str
        assert "status=running" in repr_str
        assert "policy='event_search'" in repr_str

    def test_agent_job_tablename(self):
        """
        Test that the SQLAlchemy model `AgentJob` defines its table name correctly by asserting that `AgentJob.__tablename__` equals the expected string `"jobs_agents"`.
        """
        assert AgentJob.__tablename__ == "jobs_agents"

    def test_agent_job_has_required_columns(self):
        """
        Test that the :class:`AgentJob` model defines all required attributes, ensuring each expected column (e.g., `job_id`, `investigation_id`, `user_id`) is present on the class. This validates the schema completeness before further behavior tests.
        """
        assert hasattr(AgentJob, "job_id")
        assert hasattr(AgentJob, "investigation_id")
        assert hasattr(AgentJob, "user_id")
        assert hasattr(AgentJob, "policy_id")
        assert hasattr(AgentJob, "rule_values")
        assert hasattr(AgentJob, "seed_instructions")
        assert hasattr(AgentJob, "status")
        assert hasattr(AgentJob, "worker_id")
        assert hasattr(AgentJob, "created_at")
        assert hasattr(AgentJob, "started_at")
        assert hasattr(AgentJob, "finished_at")
        assert hasattr(AgentJob, "error_message")
        assert hasattr(AgentJob, "job_metadata")


@pytest.mark.unit
class TestAgentJobEdgeCases:
    """Test edge cases for AgentJob model."""

    def test_agent_job_with_unicode_instructions(self):
        """
        Test that an AgentJob correctly stores and preserves Unicode characters in its seed_instructions field, ensuring both Japanese text and emoji are retained.
        """
        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="test",
            rule_values={},
            seed_instructions="調査を実行: 疑わしいアクティビティを検索 🔍",
            status=JobStatus.PENDING,
        )

        assert "調査" in job.seed_instructions
        assert "🔍" in job.seed_instructions

    def test_agent_job_with_very_long_instructions(self):
        """
        Test that an AgentJob can be created with extremely long seed instructions and that the instruction string is stored without truncation, verifying that its length exceeds 100,000 characters. This ensures the model handles large input sizes correctly.
        """
        long_instructions = "Instruction: " + ("A" * 100000)

        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="test",
            rule_values={},
            seed_instructions=long_instructions,
            status=JobStatus.PENDING,
        )

        assert len(job.seed_instructions) > 100000

    def test_agent_job_with_multiline_instructions(self):
        """
        Test that an `AgentJob` correctly stores and preserves multiline seed instructions.\n\nThe test creates a multi-line string containing a task description, numbered steps, and bullet points, then instantiates an `AgentJob` with this string as the `seed_instructions` argument. It asserts that the stored `seed_instructions` attribute contains a known header line (\"Investigation Task:\") and includes newline characters, confirming that multiline content is retained without alteration. This ensures that the model can handle complex, formatted instruction texts required for detailed investigations.
        """
        instructions = """Investigation Task:

1. Search for failed authentication events
2. Identify patterns and anomalies
3. Build a timeline of suspicious activity
4. Register key findings

Focus Areas:
- Remote login attempts
- Brute force patterns
- Lateral movement indicators"""

        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="investigation",
            rule_values={},
            seed_instructions=instructions,
            status=JobStatus.PENDING,
        )

        assert "Investigation Task:" in job.seed_instructions
        assert "\n" in job.seed_instructions

    def test_agent_job_with_empty_rule_values(self):
        """
        Test that an `AgentJob` can be created with an explicitly empty `rule_values` dictionary.

        The test constructs an `AgentJob` instance using minimal required fields and passes `rule_values={}`. It then asserts that the `rule_values` attribute on the resulting object is an empty dict, confirming that the model correctly handles empty rule collections without raising errors or defaulting to `None`.
        """
        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="simple",
            rule_values={},
            seed_instructions="Simple task",
            status=JobStatus.PENDING,
        )

        assert job.rule_values == {}

    def test_agent_job_with_nested_metadata(self):
        """
        Test that an AgentJob instance correctly stores and provides access to nested metadata structures.

        The test constructs a `metadata` dictionary containing two top-level keys (`execution` and `performance`), each with their own nested fields. An `AgentJob` is then instantiated with this metadata via the `job_metadata` parameter.

        Assertions verify that:
        - The `execution` sub-dictionary retains its `turns` value of `0`.
        - The `performance` sub-dictionary retains its `tokens_used` value of `0`.

        This ensures that nested dictionaries are preserved without alteration during model initialization.
        """
        metadata = {
            "execution": {"turns": 0, "tools_used": [], "timeline_entries": 0},
            "performance": {"start_time": "2024-01-01T10:00:00Z", "tokens_used": 0},
        }

        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="test",
            rule_values={},
            seed_instructions="Test",
            status=JobStatus.RUNNING,
            job_metadata=metadata,
        )

        assert job.job_metadata["execution"]["turns"] == 0
        assert job.job_metadata["performance"]["tokens_used"] == 0

    def test_agent_job_with_special_chars_in_policy_id(self):
        """
        Test that an AgentJob correctly stores a policy identifier containing special characters such as hyphens, periods, and underscores. The job is instantiated with a mixed-character `policy_id` ("policy-v2.0_advanced") and the test asserts that the attribute retains the exact string value.
        """
        job = AgentJob(
            job_id=1,
            investigation_id=uuid4(),
            user_id=1,
            policy_id="policy-v2.0_advanced",
            rule_values={},
            seed_instructions="Test",
            status=JobStatus.PENDING,
        )

        assert job.policy_id == "policy-v2.0_advanced"

    def test_agent_job_different_statuses(self):
        """
        Test creating AgentJob instances with each possible JobStatus value and verify that the status attribute is set correctly for every instance.
        """
        investigation_id = uuid4()
        statuses = [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.FAILED]

        for i, status in enumerate(statuses):
            job = AgentJob(
                job_id=i + 1,
                investigation_id=investigation_id,
                user_id=1,
                policy_id="test",
                rule_values={},
                seed_instructions="Test",
                status=status,
            )
            assert job.status == status
