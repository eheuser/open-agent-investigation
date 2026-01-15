from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, BigInteger, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from ..core.database import Base


class MCPServer(Base):
    """
    MCP Server model - stores external tool server configurations.

    Attributes:
        server_id: Unique identifier (auto-incrementing)
        name: Friendly name shown in UI (unique)
        base_url: HTTP endpoint of the MCP server
        auth_token: Optional bearer token for authentication
        allowed_agents: List of agent IDs that may call this server
        owner_user_id: Owner user (cascade delete on user removal)
        created_at: Creation timestamp
    """

    __tablename__ = "mcp_servers"

    server_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allowed_agents: Mapped[List[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self):
        """
        Return a string representation of the MCPServer instance, showing its primary identifier, name, and base URL in a concise, readable format useful for debugging. The returned value follows the pattern `<MCPServer(id=<server_id>, name='<name>', url='<base_url>')>`, where `server_id` is the unique integer ID, `name` is the human-readable server name, and `base_url` is the configured URL of the MCP server. This method does not modify any attributes and always returns a string.
        """
        return f"<MCPServer(id={self.server_id}, name='{self.name}', url='{self.base_url}')>"


__all__ = ["MCPServer"]
