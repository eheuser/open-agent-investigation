from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class LLMConfigCreate(BaseModel):
    """Schema for creating a new LLM configuration."""
    
    provider_name: str = Field(default="openai", description="Provider name (openai, anthropic, local, etc.)")
    api_endpoint: str = Field(..., description="API endpoint URL")
    api_key: Optional[str] = Field(None, description="API key (will be encrypted)")
    model_name: str = Field(default="gpt-4", description="Model identifier")
    max_context_length: int = Field(default=8192, ge=1, le=1000000, description="Maximum context window in tokens")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Nucleus sampling (0.0-1.0, optional)")
    top_k: Optional[int] = Field(None, gt=0, description="Top-k sampling (optional, provider-specific)")
    min_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Min-p sampling (0.0-1.0, optional, provider-specific)")
    timeout: int = Field(default=300, gt=0, le=3600, description="Request timeout in seconds (max 3600)")
    is_active: bool = Field(default=True, description="Whether this config is active")
    
    # Embedding provider configuration (optional - required for RAG)
    embedding_provider: Optional[str] = Field(None, description="Embedding provider: openai, cohere, ollama")
    embedding_api_url: Optional[str] = Field(None, description="Embedding API URL (required)")
    embedding_api_key: Optional[str] = Field(None, description="Embedding API key (will be encrypted)")
    embedding_model_name: Optional[str] = Field(None, description="Embedding model identifier")


class LLMConfigUpdate(BaseModel):
    """Schema for updating an existing LLM configuration."""
    
    provider_name: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    max_context_length: Optional[int] = Field(None, ge=1, le=1000000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, gt=0)
    min_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    timeout: Optional[int] = Field(None, gt=0, le=3600)
    is_active: Optional[bool] = None
    
    # Embedding provider configuration
    embedding_provider: Optional[str] = None
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_model_name: Optional[str] = None


class LLMConfigRead(BaseModel):
    """Schema for reading LLM configuration (response)."""
    
    config_id: int
    user_id: int
    provider_name: str
    api_endpoint: str
    api_key: Optional[str] = None  # Masked in responses for security
    model_name: str
    max_context_length: int
    temperature: float
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    timeout: int
    is_active: bool
    
    # Embedding provider configuration (optional - required for RAG)
    embedding_provider: Optional[str] = None
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None  # Masked in responses
    embedding_model_name: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LLMConfigReadMasked(BaseModel):
    """Schema for reading LLM configuration with masked API key."""
    
    config_id: int
    user_id: int
    provider_name: str
    api_endpoint: str
    api_key_masked: str = "••••••••"  # Always masked
    model_name: str
    max_context_length: int
    temperature: float
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    timeout: int
    is_active: bool
    
    # Embedding provider configuration (optional - required for RAG)
    embedding_provider: Optional[str] = None
    embedding_api_url: Optional[str] = None
    embedding_api_key_masked: str = "••••••••"  # Always masked
    embedding_model_name: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


__all__ = ["LLMConfigCreate", "LLMConfigUpdate", "LLMConfigRead", "LLMConfigReadMasked"]
