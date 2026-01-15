from datetime import datetime
from typing import Optional, Any, Dict
from sqlalchemy import Column, String, DateTime, BigInteger, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid as uuid_pkg
from ..core.database import Base


class ChatMessage(Base):
    """
    Chat message stored in OpenAI format.

    Attributes:
        message_id: Unique message identifier
        investigation_id: Parent investigation
        user_id: User who sent/received the message
        role: OpenAI role (system, user, assistant, tool)
        content: Message content (text or JSON for tool calls)
        name: Optional name field (for function/tool messages)
        tool_calls: Optional tool calls array (for assistant messages)
        tool_call_id: Optional tool call ID (for tool response messages)
        message_type: Message type (question, assistant_answer, agent_chat, etc.)
        parent_message_id: Parent message for threading
        metadata: Additional metadata (intent type, confidence, etc.)
        include_in_llm_context: Whether to send this message to LLM provider
        visible_in_ui: Whether to display this message in the chat UI
        deleted_at: Soft delete timestamp (tombstone) - null means not deleted
        created_at: Message timestamp

    Note:
        - Messages are stored in chronological order
        - Internal system messages (e.g., job status) have include_in_llm_context=False and visible_in_ui=False
        - User questions and assistant answers have include_in_llm_context=True and visible_in_ui=True
        - Allows selective context building for LLM calls and clean UI display
    """

    __tablename__ = "chat_messages"

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    investigation_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.investigation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )

    # OpenAI message format fields
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="OpenAI role: system, user, assistant, tool"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Message content (null for tool_calls)"
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Optional name for function/tool messages"
    )
    tool_calls: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, comment="Tool calls array (for assistant messages)"
    )
    tool_call_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Tool call ID (for tool response messages)"
    )

    # New refactored fields
    message_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Message type: question, agent_message, tool_execution, summary, error",
    )
    parent_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("chat_messages.message_id", ondelete="CASCADE"),
        nullable=True,
        comment="Parent message for threading",
    )

    # Metadata and control fields
    message_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata",  # Database column name
        JSONB,
        nullable=True,
        comment="Additional metadata (intent, confidence, job_id, etc.)",
    )
    include_in_llm_context: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Whether to include in LLM context window"
    )
    visible_in_ui: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether to display in chat UI (excludes internal system messages)",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Soft delete timestamp (tombstone) - null means not deleted",
    )

    # RAG feature - embedding reference
    embedding_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("embeddings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to embedding vector for RAG",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def to_openai_format(self) -> Dict[str, Any]:
        """
        Converts the stored message instance into the dictionary format expected by OpenAI's chat completion API.

        The returned mapping always includes the `role` key and conditionally adds other fields only when they are set on the instance:

        * **content** - included if the message has textual content.
        * **name** - included for messages that specify a name (e.g., function calls).
        * **tool_calls** - included when the message contains tool call objects.
        * **tool_call_id** - included if an identifier for a tool call is present.

        Returns
        -------
        dict[str, Any]
            A dictionary containing the OpenAI-compatible representation of the message, ready to be passed to the chat completion endpoint.
        """
        msg: Dict[str, Any] = {"role": self.role}

        if self.content is not None:
            msg["content"] = self.content

        if self.name is not None:
            msg["name"] = self.name

        if self.tool_calls is not None:
            msg["tool_calls"] = self.tool_calls

        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id

        return msg

    def __repr__(self):
        """
        Return a string representation of the ChatMessage instance, including its primary identifier and key attributes.

        The format is:

        ```
        <ChatMessage(id=<message_id>, role='<role>', investigation=<investigation_id>,
                     include_in_llm=<include_in_llm_context>, visible_in_ui=<visible_in_ui>)>
        ```

        This aids debugging by concisely summarizing the object's state. Returns
        a `str` containing the formatted representation.
        """
        return (
            f"<ChatMessage(id={self.message_id}, "
            f"role='{self.role}', "
            f"investigation={self.investigation_id}, "
            f"include_in_llm={self.include_in_llm_context}, "
            f"visible_in_ui={self.visible_in_ui})>"
        )


__all__ = ["ChatMessage"]
