from datetime import datetime
import uuid as uuid_pkg
from sqlalchemy import (
    Column,
    BigInteger,
    Text,
    SmallInteger,
    DateTime,
    LargeBinary,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from enum import IntEnum
from ..core.database import Base


class ArtifactClassification(IntEnum):
    """Artifact classification enum matching database constraints."""

    SYSTEM_HIVE = 0
    LOG_FILE = 1
    BINARY = 2
    ARCHIVE = 3
    UNKNOWN = 4


class Artifact(Base):
    """
    Artifact model - stores uploaded files with metadata.

    Attributes:
        artifact_id: Unique identifier (auto-incrementing)
        investigation_id: Parent investigation UUID
        sha256: SHA-256 hash of file (32 bytes binary)
        filename: Original filename from analyst
        classification: File type classification (0-4)
        blob: Full file payload stored in database
        upload_ts: Upload timestamp
    """

    __tablename__ = "artifacts"

    artifact_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True, autoincrement=True
    )
    investigation_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.investigation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    upload_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 4", name="valid_classification"),
        CheckConstraint("length(sha256) = 32", name="valid_sha256_length"),
    )

    def __repr__(self):
        """
        Return a string representation of the Artifact instance, showing its primary key (artifact_id), filename, and classification enum value, formatted as `<Artifact(id=..., filename='...', classification=...)>`. This aids debugging by providing a concise, readable summary of the object's identity and key attributes.
        """
        return f"<Artifact(id={self.artifact_id}, filename='{self.filename}', classification={self.classification})>"


__all__ = ["Artifact", "ArtifactClassification"]
