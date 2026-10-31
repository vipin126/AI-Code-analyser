"""Repository request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


# ── Requests ─────────────────────────────────────────────────

class RepositoryCreate(BaseModel):
    """Request body for submitting a repository for analysis."""

    url: HttpUrl = Field(
        ...,
        description="Public GitHub repository URL",
        examples=["https://github.com/fastapi/fastapi"],
    )


# ── Responses ────────────────────────────────────────────────

class RepositoryResponse(BaseModel):
    """Standard repository response."""

    id: UUID
    name: str
    github_url: str
    status: str
    total_files: int
    parsed_files: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RepositoryDetail(RepositoryResponse):
    """Extended repository detail with language breakdown."""

    language_stats: dict[str, int] | None = None
    default_branch: str | None = None


class RepositoryProgress(BaseModel):
    """Progress update during repository processing."""

    repository_id: UUID
    status: str
    total_files: int
    parsed_files: int
    progress_percent: float = Field(ge=0.0, le=100.0)
