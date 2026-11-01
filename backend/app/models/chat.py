"""Chat models — sessions and messages for RAG-based code analysis chat."""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class MessageRole(str, enum.Enum):
    """Chat message sender roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatSession(BaseModel):
    """A conversation session scoped to a specific repository."""

    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255), default="New Chat", nullable=False
    )

    # ── Relationships ────────────────────────────────────────
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="chat_sessions"
    )
    repository: Mapped["Repository"] = relationship(  # noqa: F821
        "Repository", back_populates="chat_sessions"
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(BaseModel):
    """A single message in a chat session."""

    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole), nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    context_chunks: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="RAG context chunks used to generate this response",
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Token count for cost tracking",
    )

    # ── Relationships ────────────────────────────────────────
    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="messages"
    )
