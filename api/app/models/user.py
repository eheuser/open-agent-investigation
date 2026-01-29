from enum import IntEnum
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, BigInteger, Text, SmallInteger, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..core.database import Base


class UserRole(IntEnum):
    """User role enumeration."""

    REGULAR = 0
    ADMIN = 1


class User(Base):
    """
    User account model.

    Attributes:
        user_id: Unique identifier (auto-incrementing)
        username: Login name / email (unique)
        password_hash: Argon2-hashed password
        role: Permission level (0=regular, 1=admin)
        created_at: Account creation timestamp
    """

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    playbooks = relationship("Playbook", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("role IN (0, 1)", name="valid_role"),)

    def __repr__(self):
        """
        Return a string representation of the User instance, showing its primary key, username, and role in a concise format useful for debugging.
        """
        return f"<User(user_id={self.user_id}, username='{self.username}', role={self.role})>"

    def is_admin(self) -> bool:
        """
        Check whether this user has administrative privileges.

        Returns:
            bool: `True` if the user's role is :class:`UserRole.ADMIN`, otherwise `False`.
        """
        return self.role == UserRole.ADMIN


__all__ = ["User", "UserRole"]
