"""CodeFile model — individual source files parsed from a repository."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class CodeFile(BaseModel):
    """A single source code file extracted from a repository.

    Stores the file metadata, parsed AST data, extracted dependency
    edges, and a reference to the corresponding Qdrant embedding vector.
    """

    __tablename__ = "code_files"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(
        String(1000), nullable=False
    )
    language: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="SHA-256 hash of file content for change detection",
    )
    line_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    ast_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Tree-sitter AST output: classes, functions, imports",
    )
    dependencies: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Extracted import/call dependency edges",
    )
    embedding_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Qdrant point ID for the file's embedding vector",
    )
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="AI-generated summary of the file's purpose",
    )

    # ── Relationships ────────────────────────────────────────
    repository: Mapped["Repository"] = relationship(  # noqa: F821
        "Repository", back_populates="code_files"
    )
