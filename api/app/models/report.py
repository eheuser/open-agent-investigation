from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, BigInteger, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid as uuid_pkg
from ..core.database import Base


class Report(Base):
    """
    Investigation report model.

    Stores generated reports with markdown content and metadata.
    Only the most recent report per investigation is kept.

    Attributes:
        report_id: Auto-incrementing primary key
        investigation_id: Foreign key to investigations table
        user_id: User who generated the report
        title: Report title
        markdown_content: Full markdown report content
        user_prompt: Optional custom prompt used for generation
        artifacts_count: Number of artifacts analyzed
        timeline_entries_count: Number of timeline entries
        event_types_count: Number of distinct event types
        generated_at: Timestamp when report was generated
    """

    __tablename__ = "reports"

    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    investigation_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.investigation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifacts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeline_entries_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_types_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self):
        """
        Return a string representation of the Report instance, including its primary key, associated investigation ID, and title, formatted as `<Report(id=<report_id>, investigation=<investigation_id>, title='<title>')>`. This aids debugging by providing a concise, readable summary of the object's identifying attributes.
        """
        return f"<Report(id={self.report_id}, investigation={self.investigation_id}, title='{self.title}')>"


__all__ = ["Report"]
