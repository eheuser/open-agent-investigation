from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Core
    jwt_secret: str = "change-me-in-production-supersecret"
    database_url: str = "postgresql+asyncpg://postgres:example@db:5432/open_agent_inv"
    
    # UI origins (CORS)
    ui_origin: str = "http://localhost:5173"
    
    # Optional observability
    prometheus_enabled: bool = True
    
    # LLM endpoint (for policy routing)
    llm_endpoint: Optional[str] = None
    
    # Worker settings
    worker_poll_interval: int = 1  # seconds
    worker_timeout: int = 30  # seconds
    num_workers: int = 8  # Number of main worker processes (parsing/agent jobs) - default 8
    num_embedding_workers: int = 4  # Number of dedicated embedding worker processes - default 4
    max_concurrent_embedding_batches: int = 16  # Concurrent API calls per embedding job - default 16
    embedding_batch_size: int = 100  # Events per embedding API call - default 100
    
    # File storage
    investigations_base_path: str = "/data/investigations"
    policies_path: str = "/app/data/policies"
    agents_path: str = "/app/data/agents"
    
    # API server (for worker callbacks)
    api_host: str = "api"  # Docker service name
    api_port: int = 8000
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "allow",
    }


settings = Settings()

__all__ = ["settings"]
