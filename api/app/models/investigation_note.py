from sqlalchemy import Column, BigInteger, Text, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class InvestigationNote(Base):
    """Free-form investigation notes."""
    
    __tablename__ = "investigation_notes"

    note_id = Column(BigInteger, primary_key=True, index=True)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(BigInteger, ForeignKey("embeddings.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


__all__ = ["InvestigationNote"]
