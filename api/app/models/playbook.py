# api/app/models/playbook.py
from sqlalchemy import Column, BigInteger, Text, Boolean, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy import DateTime
from app.core.database import Base


class Playbook(Base):
    """User-created investigation playbooks.
    
    Base playbooks are immutable YAML files loaded from disk.
    User playbooks are stored in the database and can be modified.
    """
    __tablename__ = "playbooks"
    
    playbook_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    playbook = Column(Text, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="playbooks")
    investigation_playbooks = relationship("InvestigationPlaybook", back_populates="playbook", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("length(name) > 0", name="playbook_name_not_empty"),
        CheckConstraint("length(description) > 0", name="playbook_description_not_empty"),
        CheckConstraint("length(playbook) > 0", name="playbook_content_not_empty"),
    )


class InvestigationPlaybook(Base):
    """Many-to-many relationship between investigations and playbooks.
    
    Tracks which playbooks are enabled for each investigation.
    Base playbooks are always enabled.
    User playbooks must be explicitly enabled per investigation.
    """
    __tablename__ = "investigation_playbooks"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False)
    playbook_id = Column(BigInteger, ForeignKey("playbooks.playbook_id", ondelete="CASCADE"), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    enabled_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationships
    investigation = relationship("Investigation", back_populates="investigation_playbooks")
    playbook = relationship("Playbook", back_populates="investigation_playbooks")
    
    __table_args__ = (
        UniqueConstraint("investigation_id", "playbook_id", name="uq_investigation_playbook"),
    )
