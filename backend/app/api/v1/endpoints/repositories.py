"""Repository endpoints — CRUD and processing pipeline trigger.

Endpoints:
    POST   /api/v1/repositories           — Submit a repo URL for analysis
    GET    /api/v1/repositories           — List all repositories
    GET    /api/v1/repositories/{id}      — Get repository detail + status
    DELETE /api/v1/repositories/{id}      — Delete repository and its data
"""

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_repository
from app.models.repository import Repository, RepositoryStatus
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryDetail,
    RepositoryResponse,
)
from app.worker.tasks import process_repository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit repository for analysis",
)
def create_repository(
    payload: RepositoryCreate,
    db: Session = Depends(get_db),
) -> Repository:
    """Submit a public GitHub repository URL for analysis.

    The repository is queued for async processing via Celery.
    Returns immediately with status 'pending'.
    """
    url = str(payload.url).rstrip("/")

    # Extract repo name from URL
    match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub URL. Expected format: https://github.com/owner/repo",
        )
    repo_name = f"{match.group(1)}/{match.group(2)}"

    # Check for duplicate (same URL, not in error state)
    existing = (
        db.query(Repository)
        .filter(
            Repository.github_url == url,
            Repository.status != RepositoryStatus.ERROR,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository '{repo_name}' is already being processed or ready. "
                   f"Current status: {existing.status.value}",
        )

    # Create repository record
    repo = Repository(
        name=repo_name,
        github_url=url,
        status=RepositoryStatus.PENDING,
        # user_id will be added when auth is implemented
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    # Queue the processing task
    process_repository.delay(str(repo.id))

    logger.info("Queued repository %s (%s) for processing", repo.id, repo_name)
    return repo


@router.get(
    "",
    response_model=list[RepositoryResponse],
    summary="List all repositories",
)
def list_repositories(
    skip: int = 0,
    limit: int = 50,
    status_filter: RepositoryStatus | None = None,
    db: Session = Depends(get_db),
) -> list[Repository]:
    """List all submitted repositories with optional status filtering.

    Supports pagination via skip/limit.
    """
    query = db.query(Repository)
    if status_filter:
        query = query.filter(Repository.status == status_filter)
    return query.order_by(Repository.created_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/{repository_id}",
    response_model=RepositoryDetail,
    summary="Get repository detail",
)
def get_repository_detail(
    repo: Repository = Depends(get_repository),
) -> Repository:
    """Get detailed information about a repository including processing status,
    language breakdown, and error messages.
    """
    return repo


@router.delete(
    "/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete repository",
)
def delete_repository(
    repository_id: UUID,
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
) -> None:
    """Delete a repository and all associated data.

    Also removes indexed code chunks from Qdrant.
    """
    from app.services.rag_service import RAGService

    # Clean up indexed Qdrant payloads
    try:
        rag_service = RAGService()
        rag_service.delete_repository_chunks(str(repository_id))
    except Exception as e:
        logger.warning("Failed to delete indexed Qdrant chunks for %s: %s", repository_id, e)

    db.delete(repo)
    db.commit()
    logger.info("Deleted repository %s", repository_id)
