"""Analysis endpoints — dependency graph and file inspection.

Endpoints:
    GET /api/v1/repositories/{id}/graph       — Full dependency graph
    GET /api/v1/repositories/{id}/files       — List parsed files
    GET /api/v1/repositories/{id}/files/{fid} — Single file AST detail
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_repository
from app.models.code_file import CodeFile
from app.models.repository import Repository, RepositoryStatus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/{repository_id}/graph",
    summary="Get dependency graph",
)
def get_dependency_graph(
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
) -> dict:
    """Return the full dependency graph for a repository.

    The graph is a JSON adjacency list:
    - nodes: [{id, name, type, file_path, line_start, line_end}]
    - edges: [{source, target, relationship}]

    Only available when repository status is 'ready'.
    """
    if repo.status != RepositoryStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready. Current status: {repo.status.value}",
        )

    # Reconstruct graph from stored CodeFile AST data
    code_files = (
        db.query(CodeFile)
        .filter(CodeFile.repository_id == repo.id)
        .all()
    )

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_node_ids: set[str] = set()

    for cf in code_files:
        # Extract nodes from ast_data
        if cf.ast_data and "nodes" in cf.ast_data:
            for node in cf.ast_data["nodes"]:
                node_id = f"{cf.file_path}:{node.get('name', '')}"
                if node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    nodes.append({
                        "id": node_id,
                        "name": node.get("name", ""),
                        "type": node.get("type", ""),
                        "file_path": cf.file_path,
                        "line_start": node.get("line_start", 0),
                        "line_end": node.get("line_end", 0),
                    })

        # Extract edges from dependencies
        if cf.dependencies and "edges" in cf.dependencies:
            for edge in cf.dependencies["edges"]:
                edges.append({
                    "source": edge.get("source", ""),
                    "target": edge.get("target", ""),
                    "relationship": edge.get("relationship", ""),
                })

    return {
        "repository_id": str(repo.id),
        "repository_name": repo.name,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "language_stats": repo.language_stats or {},
    }


@router.get(
    "/{repository_id}/files",
    summary="List parsed files",
)
def list_files(
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
    language: str | None = Query(None, description="Filter by language"),
    skip: int = 0,
    limit: int = 100,
) -> dict:
    """List all parsed source files in a repository.

    Supports filtering by language and pagination.
    """
    query = (
        db.query(CodeFile)
        .filter(CodeFile.repository_id == repo.id)
    )
    if language:
        query = query.filter(CodeFile.language == language)

    total = query.count()
    files = query.order_by(CodeFile.file_path).offset(skip).limit(limit).all()

    return {
        "repository_id": str(repo.id),
        "total": total,
        "files": [
            {
                "id": str(f.id),
                "file_path": f.file_path,
                "language": f.language,
                "line_count": f.line_count,
                "size_bytes": f.size_bytes,
                "node_count": len(f.ast_data.get("nodes", [])) if f.ast_data else 0,
                "dependency_count": len(f.dependencies.get("edges", [])) if f.dependencies else 0,
            }
            for f in files
        ],
    }


@router.get(
    "/{repository_id}/files/{file_id}",
    summary="Get file AST detail",
)
def get_file_detail(
    file_id: UUID,
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
) -> dict:
    """Get detailed AST analysis for a single file.

    Returns parsed nodes (classes, functions, imports) and
    dependency edges extracted from the AST.
    """
    code_file = (
        db.query(CodeFile)
        .filter(
            CodeFile.id == file_id,
            CodeFile.repository_id == repo.id,
        )
        .first()
    )
    if not code_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found in repository",
        )

    return {
        "id": str(code_file.id),
        "file_path": code_file.file_path,
        "language": code_file.language,
        "line_count": code_file.line_count,
        "size_bytes": code_file.size_bytes,
        "content_hash": code_file.content_hash,
        "ast_data": code_file.ast_data,
        "dependencies": code_file.dependencies,
        "embedding_id": code_file.embedding_id,
        "summary": code_file.summary,
    }
