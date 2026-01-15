from sqlalchemy import Column, BigInteger, Text, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..core.database import Base


class ToolResult(Base):
    """Persisted tool execution results for RAG."""
    
    __tablename__ = "tool_results"

    result_id = Column(BigInteger, primary_key=True, index=True)
    job_id = Column(BigInteger, ForeignKey("jobs_agents.job_id", ondelete="CASCADE"), nullable=False)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False)
    embedding_id = Column(BigInteger, ForeignKey("embeddings.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


__all__ = ["ToolResult"]
