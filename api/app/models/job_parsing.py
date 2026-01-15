from datetime import datetime
from typing import Optional
import uuid as uuid_pkg
from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from enum import Enum
from ..core.database import Base


class JobStatus(str, Enum):
    """Job status enumeration matching database type."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ParsingJob(Base):
    """
    Parsing job queue model.
    
    Attributes:
        job_id: Unique identifier (auto-incrementing)
        investigation_id: Parent investigation UUID
        artifact_id: Artifact to parse
        status: Current job status (pending/running/completed/failed)
        worker_id: UUID of worker that claimed this job
        created_at: Job creation timestamp
        started_at: When job execution began
        finished_at: When job completed or failed
        error_message: Error details if status is 'failed'
    """
    __tablename__ = "jobs_parsing"

    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True, autoincrement=True)
    investigation_id: Mapped[uuid_pkg.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investigations.investigation_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    artifact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("artifacts.artifact_id", ondelete="CASCADE"),
        nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, name='job_status', create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=JobStatus.PENDING,
        index=True
    )
    worker_id: Mapped[Optional[uuid_pkg.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self):
        """
        Return a string representation of the ParsingJob instance, showing its primary identifier, current status value, and associated artifact identifier. This method is primarily used for debugging and logging purposes, providing a concise summary of the object's key attributes.
        """
        return f"<ParsingJob(id={self.job_id}, status={self.status.value}, artifact={self.artifact_id})>"


__all__ = ["ParsingJob", "JobStatus"]
