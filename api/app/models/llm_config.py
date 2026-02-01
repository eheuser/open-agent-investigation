from sqlalchemy import Column, BigInteger, Text, Integer, Numeric, Boolean, DateTime, func, ForeignKey
from ..core.database import Base


class LLMProviderConfig(Base):
    """LLM provider configuration for per-user inference settings."""
    
    __tablename__ = "llm_provider_config"
    
    # Suppress Pydantic warning about model_name field conflicting with model_ namespace
    model_config = {"protected_namespaces": ()}

    config_id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    provider_name = Column(Text, nullable=False, default="openai")
    api_endpoint = Column(Text, nullable=False)
    api_key = Column(Text)  # Should be encrypted at application layer
    model_name = Column(Text, default="gpt-4")
    max_context_length = Column(Integer, nullable=False, default=8192)
    temperature = Column(Numeric(3, 2), nullable=False, default=0.70)
    top_p = Column(Numeric(4, 3), nullable=True)  # Optional: nucleus sampling (0.0-1.0)
    top_k = Column(Integer, nullable=True)  # Optional: top-k sampling (provider-specific)
    min_p = Column(Numeric(4, 3), nullable=True)  # Optional: min-p sampling (0.0-1.0, provider-specific)
    timeout = Column(Integer, nullable=False, default=300)  # Request timeout in seconds
    is_active = Column(Boolean, nullable=False, default=True)
    allow_concurrent_llm_calls = Column(Boolean, nullable=False, default=False)  # Enable parallel LLM requests
    
    # Embedding provider configuration (optional - required for RAG)
    embedding_provider = Column(Text, nullable=True)  # 'openai', 'cohere', 'ollama'
    embedding_api_url = Column(Text, nullable=True)
    embedding_api_key = Column(Text, nullable=True)  # Encrypted at application layer
    embedding_model_name = Column(Text, nullable=True)  # Model for initial embedding generation
    embedding_max_context_length = Column(Integer, nullable=True, default=8192)  # Max tokens for embedding model
    reranker_model_name = Column(Text, nullable=True)  # Model for reranking (more expensive/capable)
    reranker_max_context_length = Column(Integer, nullable=True, default=8192)  # Max tokens for reranker model
    allow_concurrent_embedding_calls = Column(Boolean, nullable=False, default=False)  # Enable parallel embedding/reranking requests
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


__all__ = ["LLMProviderConfig"]
