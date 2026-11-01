"""Celery tasks — repository processing orchestrator.

The main task `process_repository` coordinates the full pipeline:
1. Clone repository (git_service)
2. Parse source files (parser_service)
3. Index code chunks for local retrieval (rag_service)
4. Update database status at each step
5. Clean up temporary files on completion or failure
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.code_file import CodeFile
from app.models.repository import Repository, RepositoryStatus
from app.services.git_service import GitService
from app.services.parser_service import ParserService
from app.services.rag_service import RAGService
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db() -> Session:
    """Create a standalone database session for use in Celery tasks."""
    return SessionLocal()


def _update_repo_status(
    db: Session,
    repo_id: str,
    status: RepositoryStatus,
    error_message: str | None = None,
    **kwargs: object,
) -> None:
    """Update repository status and optional fields in the database.

    Args:
        db: Database session.
        repo_id: Repository UUID string.
        status: New processing status.
        error_message: Error message if status is ERROR.
        **kwargs: Additional fields to update (total_files, parsed_files, etc.).
    """
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if repo:
        repo.status = status
        if error_message is not None:
            repo.error_message = error_message
        for key, value in kwargs.items():
            if hasattr(repo, key):
                setattr(repo, key, value)
        db.commit()


@celery_app.task(
    bind=True,
    name="process_repository",
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def process_repository(self, repo_id: str) -> dict:  # type: ignore[type-arg]
    """Orchestrate the full repository analysis pipeline.

    This is the main Celery task that drives the entire ingestion flow:
    clone → parse → embed → done.

    Args:
        self: Celery task instance (bound).
        repo_id: UUID of the Repository record to process.

    Returns:
        Dict with processing summary.

    Raises:
        Exception: Re-raised after updating repo status to ERROR.
    """
    db = _get_db()
    git_service = GitService()
    parser_service = ParserService()
    rag_service = RAGService()
    clone_path: Path | None = None

    try:
        logger.info("Starting pipeline for repository %s", repo_id)

        # ── Step 1: Clone ────────────────────────────────────
        _update_repo_status(db, repo_id, RepositoryStatus.CLONING)

        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise ValueError(f"Repository {repo_id} not found")

        clone_result = git_service.clone_repository(repo.github_url)
        clone_path = Path(clone_result.clone_path)

        _update_repo_status(
            db, repo_id, RepositoryStatus.CLONING,
            total_files=clone_result.total_files,
            clone_path=str(clone_path),
            default_branch=clone_result.default_branch,
            language_stats=clone_result.language_stats,
        )

        logger.info(
            "Cloned %s: %d files, %d languages",
            repo.github_url, clone_result.total_files,
            len(clone_result.language_stats),
        )

        # ── Step 2: Parse ────────────────────────────────────
        _update_repo_status(db, repo_id, RepositoryStatus.PARSING)

        file_manifest = [
            {"path": f.path, "language": f.language}
            for f in clone_result.files
        ]
        parse_results = parser_service.parse_repository(clone_path, file_manifest)

        # Build dependency graph
        dep_graph = parser_service.build_dependency_graph(parse_results)

        # Persist parsed file records to database
        for result in parse_results:
            # Find the matching file info for size/hash
            file_info = next(
                (f for f in clone_result.files if f.path == result.file_path),
                None,
            )
            if file_info and not result.error:
                code_file = CodeFile(
                    repository_id=repo_id,
                    file_path=result.file_path,
                    language=result.language,
                    content_hash=file_info.content_hash,
                    line_count=result.line_count,
                    size_bytes=file_info.size_bytes,
                    ast_data={
                        "nodes": [n.model_dump() for n in result.nodes],
                    },
                    dependencies={
                        "edges": [d.model_dump() for d in result.dependencies],
                    },
                )
                db.add(code_file)

        db.commit()

        _update_repo_status(
            db, repo_id, RepositoryStatus.PARSING,
            parsed_files=len([r for r in parse_results if not r.error]),
        )

        logger.info(
            "Parsed %d files (%d successful)",
            len(parse_results),
            len([r for r in parse_results if not r.error]),
        )

        # ── Step 3: Index ────────────────────────────────────
        _update_repo_status(db, repo_id, RepositoryStatus.EMBEDDING)

        # Generate code chunks from all parsed files
        all_chunks = []
        for result in parse_results:
            if result.error:
                continue
            file_info = next(
                (f for f in clone_result.files if f.path == result.file_path),
                None,
            )
            if file_info:
                source_path = clone_path / result.file_path
                if source_path.exists():
                    source = source_path.read_bytes()
                    chunks = parser_service.extract_code_chunks(
                        result.file_path, result.language, source
                    )
                    all_chunks.extend(chunks)

        # Store searchable code chunks in Qdrant
        if all_chunks:
            point_ids = rag_service.store_code_chunks(all_chunks, repo_id)
            logger.info("Stored %d code chunks for local retrieval", len(point_ids))
        else:
            logger.warning("No code chunks generated for local retrieval")

        # ── Step 4: Done ─────────────────────────────────────
        _update_repo_status(db, repo_id, RepositoryStatus.READY)

        summary = {
            "repository_id": repo_id,
            "status": "ready",
            "total_files": clone_result.total_files,
            "parsed_files": len([r for r in parse_results if not r.error]),
            "total_chunks": len(all_chunks),
            "languages": clone_result.language_stats,
            "dependency_graph": {
                "nodes": len(dep_graph["nodes"]),
                "edges": len(dep_graph["edges"]),
            },
        }

        logger.info("Pipeline complete for %s: %s", repo_id, summary)
        return summary

    except Exception as exc:
        logger.error("Pipeline failed for %s: %s", repo_id, exc, exc_info=True)
        _update_repo_status(
            db, repo_id, RepositoryStatus.ERROR,
            error_message=str(exc),
        )
        raise

    finally:
        # Always clean up the cloned repository
        if clone_path:
            git_service.cleanup(clone_path)
        db.close()
