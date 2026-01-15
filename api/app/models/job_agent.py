from datetime import datetime
from typing import Optional, Dict, Any
import uuid as uuid_pkg
from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .job_parsing import JobStatus
from ..core.database import Base


class AgentJob(Base):
    """
    Agent job queue model - policy-driven agent execution.

    Attributes:
        job_id: Unique identifier (auto-incrementing)
        investigation_id: Parent investigation UUID
        user_id: User who created the job
        policy_id: Filename of the policy YAML
        rule_values: Resolved rule values as JSON
        seed_instructions: Rendered prompt sent to LLM
        status: Current job status (pending/running/completed/failed)
        worker_id: UUID of worker that claimed this job
        created_at: Job creation timestamp
        started_at: When job execution began
        finished_at: When job completed or failed
        error_message: Error details if status is 'failed'
    """

    __tablename__ = "jobs_agents"

    job_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True, autoincrement=True
    )
    investigation_id: Mapped[uuid_pkg.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investigations.investigation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    rule_values: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    seed_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(
            JobStatus,
            name="job_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )
    worker_id: Mapped[Optional[uuid_pkg.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True, server_default="{}"  # Database column name
    )

    # Relationships
    choices = relationship(
        "InvestigationChoice",
        foreign_keys="InvestigationChoice.job_id",
        back_populates="job",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        """
        Return a string representation of the AgentJob instance, formatted as `<AgentJob(id=<job_id>, status=<status.value>, policy='<policy_id>')>`, where `job_id` is the job's unique identifier, `status.value` is the textual value of the job's current status enum, and `policy_id` references the associated policy. This representation is primarily intended for debugging and logging purposes.
        """
        return (
            f"<AgentJob(id={self.job_id}, status={self.status.value}, policy='{self.policy_id}')>"
        )


__all__ = ["AgentJob"]
