from datetime import datetime
from typing import Optional, Any, Dict
from sqlalchemy import Column, String, DateTime, BigInteger, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..core.database import Base


class ToolExecution(Base):
    """
    Individual tool execution record.

    Attributes:
        execution_id: Unique execution identifier
        chat_message_id: Parent agent message (FK to chat_messages)
        tool_name: Internal tool name (e.g., search_events)
        display_name: User-friendly display name
        arguments: Tool arguments (JSON)
        result: Tool result (JSON)
        result_summary: Human-readable result summary
        status: executing, completed, failed
        execution_number: Sequential number within agent run
        max_tools: Maximum tools allowed in this agent run
        started_at: When tool execution started
        finished_at: When tool execution completed
    """

    __tablename__ = "tool_executions"

    execution_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_messages.message_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Internal tool name"
    )
    display_name: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="User-friendly display name"
    )
    arguments: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict, comment="Tool arguments"
    )
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="Tool result")
    result_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Human-readable result summary"
    )
    status: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="executing",
        comment="Status: executing, completed, failed",
    )
    execution_number: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Sequential number within agent run"
    )
    max_tools: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Maximum tools allowed in this agent run"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the model instance into a plain-dictionary representation suitable for API responses.

        The returned dictionary contains all public fields of the execution record:

        * `execution_id` - unique identifier of the execution.
        * `chat_message_id` - identifier of the associated chat message.
        * `tool_name` - internal name of the tool that was run.
        * `display_name` - human-readable name; falls back to `tool_name` when not set.
        * `arguments` - dictionary of arguments supplied to the tool, or an empty dict if none.
        * `result` - raw result data produced by the tool.
        * `result_summary` - concise summary of the result, if available.
        * `status` - current execution status (e.g., `pending`, `running`, `completed`).
        * `execution_number` - ordinal number of this execution within its chat context.
        * `max_tools` - maximum number of tools allowed for the related request.
        * `started_at` - ISO-8601 timestamp marking when execution began, or `None` if not started.
        * `finished_at` - ISO-8601 timestamp marking when execution finished, or `None` if not finished.

        The method returns a `dict[str, Any]` containing these keys and their corresponding values.
        """
        return {
            "execution_id": self.execution_id,
            "chat_message_id": self.chat_message_id,
            "tool_name": self.tool_name,
            "display_name": self.display_name or self.tool_name,
            "arguments": self.arguments or {},
            "result": self.result,
            "result_summary": self.result_summary,
            "status": self.status,
            "execution_number": self.execution_number,
            "max_tools": self.max_tools,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    def __repr__(self):
        """
        Return a string representation of the ToolExecution instance, including its execution ID, tool name, status, and associated chat message ID. This aids debugging by providing a concise summary of the object's key attributes.
        """
        return (
            f"<ToolExecution(id={self.execution_id}, "
            f"tool='{self.tool_name}', "
            f"status='{self.status}', "
            f"message_id={self.chat_message_id})>"
        )


__all__ = ["ToolExecution"]
