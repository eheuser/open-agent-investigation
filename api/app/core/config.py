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
