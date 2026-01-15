from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, BigInteger, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid as uuid_pkg
from ..core.database import Base


class Investigation(Base):
    """
    Investigation metadata model.
    
    Attributes:
        investigation_id: UUID primary key (used in URLs and directory names)
        title: Human-readable investigation name
        owner_user_id: Foreign key to users table (nullable on user deletion)
        parsing_locked: True while artifact parsing is in progress (blocks new questions)
        created_at: Creation timestamp
    """
    __tablename__ = "investigations"

    investigation_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_pkg.uuid4,
        index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True
    )
    parsing_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True while artifact parsing is in progress"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self):
        """
        Return a string representation of the Investigation instance, including its primary key (investigation_id), title, and parsing_locked status, formatted as "<Investigation(id=..., title='...', parsing_locked=...)>". This aids debugging by providing a concise, readable summary of the object's essential attributes.
        """
        return f"<Investigation(id={self.investigation_id}, title='{self.title}', parsing_locked={self.parsing_locked})>"


__all__ = ["Investigation"]
