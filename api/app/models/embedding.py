from sqlalchemy import Column, BigInteger, Text, DateTime, func, CheckConstraint
from pgvector.sqlalchemy import Vector
from ..core.database import Base


class Embedding(Base):
    """Polymorphic vector store for RAG."""
    
    __tablename__ = "embeddings"

    id = Column(BigInteger, primary_key=True, index=True)
    owner_type = Column(Text, nullable=False)  # 'chat', 'timeline', 'note', 'tool'
    owner_id = Column(BigInteger, nullable=False)
    model_name = Column(Text, nullable=False)
    vector = Column(Vector(1536), nullable=False)  # Default: OpenAI ada-002 dimension
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        CheckConstraint("owner_type IN ('chat', 'timeline', 'note', 'tool')", name='chk_owner_type'),
    )


__all__ = ["Embedding"]
