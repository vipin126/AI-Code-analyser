"""Shared FastAPI dependencies for API routes."""

from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.repository import Repository


def get_db() -> Generator[Session, None, None]:
    """Yield a database session per request, closing on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_repository(
    repository_id: UUID,
    db: Session = Depends(get_db),
) -> Repository:
    """Fetch a repository by ID or raise 404.

    Usage as a FastAPI dependency:
        @router.get("/{repository_id}")
        def get_repo(repo: Repository = Depends(get_repository)):
            ...
    """
    repo = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repository_id} not found",
        )
    return repo
