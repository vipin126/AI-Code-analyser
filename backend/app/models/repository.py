"""Repository model — tracks ingested GitHub repositories and their processing state."""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class RepositoryStatus(str, enum.Enum):
    """Processing pipeline states for a repository."""

    PENDING = "pending"
    CLONING = "cloning"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"


class Repository(BaseModel):
    """A GitHub repository submitted for analysis."""

    __tablename__ = "repositories"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    github_url: Mapped[str] = mapped_column(
        String(500), nullable=False
    )
    clone_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus),
        default=RepositoryStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    total_files: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    parsed_files: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    default_branch: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    language_stats: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Language breakdown: {language: file_count}",
    )

    # ── Relationships ────────────────────────────────────────
    owner: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="repositories"
    )
    code_files: Mapped[list["CodeFile"]] = relationship(  # noqa: F821
        "CodeFile", back_populates="repository", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(  # noqa: F821
        "ChatSession", back_populates="repository", cascade="all, delete-orphan"
    )
