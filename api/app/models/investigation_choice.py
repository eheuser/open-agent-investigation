from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID as PyUUID

from sqlalchemy import Column, BigInteger, Text, TIMESTAMP, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..core.database import Base


class InvestigationChoice(Base):
    """
    Investigation choices suggested by the agent when investigation is incomplete.
    
    These are persisted suggestions for next investigative steps that users can select.
    Once selected, the choice triggers a new agent job with the suggested parameters.
    """
    __tablename__ = "investigation_choices"
    
    choice_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("jobs_agents.job_id", ondelete="CASCADE"), nullable=False, index=True)
    investigation_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey("investigations.investigation_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Choice metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Execution parameters (for creating new job when selected)
    suggested_query: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_effort: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    tool_suggestions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Display ordering
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Selection tracking
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    selected_job_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("jobs_agents.job_id", ondelete="SET NULL"), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    job = relationship("AgentJob", foreign_keys=[job_id], back_populates="choices")
    investigation = relationship("Investigation")
    selected_job = relationship("AgentJob", foreign_keys=[selected_job_id])
    
    def __repr__(self):
        """
        Return a string representation of the InvestigationChoice instance, showing its primary identifier, title, and selection status. This aids debugging by providing a concise, readable summary of the object's key attributes.
        """
        return f"<InvestigationChoice(choice_id={self.choice_id}, title='{self.title}', selected={self.selected})>"
