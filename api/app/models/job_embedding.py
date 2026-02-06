from datetime import datetime
from typing import Optional, List
import uuid as uuid_pkg
from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey, Enum as SQLEnum, Integer, ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from .job_parsing import JobStatus
from ..core.database import Base


class EmbeddingJob(Base):
    """
    Embedding job queue model for background embedding generation.
    
    Attributes:
        job_id: Unique identifier (auto-incrementing)
        investigation_id: Parent investigation UUID
        user_id: User whose embedding configuration should be used
        event_ids: Array of event IDs to generate embeddings for (batch)
        status: Current job status (pending/running/completed/failed)
        worker_id: UUID of worker that claimed this job
        created_at: Job creation timestamp
        started_at: When job execution began
        finished_at: When job completed or failed
        error_message: Error details if status is 'failed'
        events_processed: Number of events successfully embedded
    """
    __tablename__ = "jobs_embedding"

    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True, autoincrement=True)
    investigation_id: Mapped[uuid_pkg.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investigations.investigation_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    event_ids: Mapped[List[int]] = mapped_column(
        ARRAY(BigInteger),
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
    events_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<EmbeddingJob(id={self.job_id}, status={self.status.value}, events={len(self.event_ids) if self.event_ids else 0})>"


__all__ = ["EmbeddingJob"]
