from sqlalchemy import Column, BigInteger, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..core.database import Base


class FilterConfig(Base):
    """Ingestion filter configuration."""
    
    __tablename__ = "filter_config"

    config_id = Column(BigInteger, primary_key=True, index=True)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=True)  # NULL = global
    content = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


__all__ = ["FilterConfig"]
