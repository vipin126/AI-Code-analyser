"""Chat endpoints — RAG-powered code analysis chat with SSE streaming.

Endpoints:
    POST /api/v1/repositories/{id}/chat                          — Create session
    GET  /api/v1/repositories/{id}/chat                          — List sessions
    GET  /api/v1/repositories/{id}/chat/{session_id}             — Get messages
    POST /api/v1/repositories/{id}/chat/{session_id}/messages    — Send message (SSE)
"""

import json
import logging
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_repository
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.code_file import CodeFile
from app.models.repository import Repository, RepositoryStatus
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Schemas ───────────────────────────────

class ChatSessionCreate(BaseModel):
    """Request to create a new chat session."""
    title: str = Field(default="New Chat", max_length=255)


class ChatSessionResponse(BaseModel):
    """Chat session summary."""
    id: str
    title: str
    repository_id: str
    message_count: int
    created_at: str


class MessageCreate(BaseModel):
    """Request to send a message."""
    content: str = Field(..., min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    """Chat message response."""
    id: str
    role: str
    content: str
    context_chunks: dict | None = None
    token_count: int | None = None
    created_at: str


# ── Endpoints ────────────────────────────────────────────────

@router.post(
    "/{repository_id}/chat",
    status_code=status.HTTP_201_CREATED,
    summary="Create chat session",
)
def create_chat_session(
    payload: ChatSessionCreate,
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
) -> dict:
    """Create a new chat session scoped to a repository.

    Repository must be in 'ready' status.
    """
    if repo.status != RepositoryStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready for chat. Status: {repo.status.value}",
        )

    session = ChatSession(
        user_id="00000000-0000-0000-0000-000000000000",  # Placeholder until auth
        repository_id=repo.id,
        title=payload.title,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "id": str(session.id),
        "title": session.title,
        "repository_id": str(session.repository_id),
        "created_at": session.created_at.isoformat(),
    }


@router.get(
    "/{repository_id}/chat",
    summary="List chat sessions",
)
def list_chat_sessions(
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
) -> list[dict]:
    """List all chat sessions for a repository."""
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.repository_id == repo.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )

    return [
        {
            "id": str(s.id),
            "title": s.title,
            "repository_id": str(s.repository_id),
            "message_count": len(s.messages),
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@router.get(
    "/{repository_id}/chat/{session_id}",
    summary="Get chat messages",
)
def get_chat_messages(
    session_id: UUID,
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
) -> dict:
    """Get all messages in a chat session."""
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.repository_id == repo.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    return {
        "session_id": str(session.id),
        "title": session.title,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value,
                "content": m.content,
                "context_chunks": m.context_chunks,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat(),
            }
            for m in session.messages
        ],
    }


@router.post(
    "/{repository_id}/chat/{session_id}/messages",
    summary="Send message with RAG context",
)
async def send_message(
    session_id: UUID,
    payload: MessageCreate,
    repo: Repository = Depends(get_repository),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Send a message and receive an AI response with RAG context.

    Uses Server-Sent Events (SSE) for streaming the response.
    The response includes:
    1. Retrieved context chunks from the codebase
    2. AI-generated analysis streamed token by token

    SSE event format:
        event: context
        data: {"chunks": [...]}

        event: token
        data: {"content": "..."}

        event: done
        data: {"message_id": "..."}
    """
    # Validate session
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.repository_id == repo.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    if repo.status != RepositoryStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository is not ready for chat",
        )

    # Save user message
    user_message = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=payload.content,
    )
    db.add(user_message)
    db.commit()

    # Build the dependency graph from stored data for structural search
    code_files = (
        db.query(CodeFile)
        .filter(CodeFile.repository_id == repo.id)
        .all()
    )
    dep_graph = _build_graph_from_files(code_files)

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE events: context → tokens → done."""
        rag_service = RAGService()

        # Step 1: Retrieve context
        try:
            contexts = await rag_service.hybrid_search(
                query=payload.content,
                repository_id=str(repo.id),
                dependency_graph=dep_graph,
                top_k=8,
            )

            context_data = [
                {
                    "file_path": ctx.file_path,
                    "start_line": ctx.start_line,
                    "end_line": ctx.end_line,
                    "language": ctx.language,
                    "relevance_score": ctx.relevance_score,
                    "content": ctx.content[:500],  # Truncate for SSE
                    "method": ctx.retrieval_method,
                }
                for ctx in contexts
            ]

            yield f"event: context\ndata: {json.dumps({'chunks': context_data})}\n\n"

        except Exception as e:
            logger.error("RAG search failed: %s", e)
            context_data = []
            contexts = []
            yield f"event: error\ndata: {json.dumps({'detail': 'Context retrieval failed'})}\n\n"

        # Step 2: Generate response
        # For MVP, we construct a synthesized response from the retrieved context.
        # In production, this would call an LLM (GPT-4, Claude, etc.) with the
        # context + user query for a streaming completion.
        response_parts = _synthesize_response(payload.content, contexts, repo.name)

        full_response = ""
        for part in response_parts:
            full_response += part
            yield f"event: token\ndata: {json.dumps({'content': part})}\n\n"

        # Step 3: Save assistant message
        assistant_message = ChatMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=full_response,
            context_chunks={"chunks": context_data} if context_data else None,
            token_count=len(full_response) // 4,  # Rough estimate
        )

        # Need a fresh session since we're in an async generator
        from app.core.database import SessionLocal
        save_db = SessionLocal()
        try:
            save_db.add(assistant_message)
            save_db.commit()
            yield f"event: done\ndata: {json.dumps({'message_id': str(assistant_message.id)})}\n\n"
        finally:
            save_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Helper Functions ─────────────────────────────────────────

def _build_graph_from_files(code_files: list[CodeFile]) -> dict:
    """Reconstruct dependency graph from stored CodeFile records."""
    nodes: list[dict] = []
    edges: list[dict] = []

    for cf in code_files:
        if cf.ast_data and "nodes" in cf.ast_data:
            nodes.extend(cf.ast_data["nodes"])
        if cf.dependencies and "edges" in cf.dependencies:
            edges.extend(cf.dependencies["edges"])

    return {"nodes": nodes, "edges": edges}


def _synthesize_response(
    query: str,
    contexts: list,
    repo_name: str,
) -> list[str]:
    """Synthesize a response from retrieved context chunks.

    MVP implementation: constructs a structured analysis from the
    retrieved code context. In production, replace this with an
    LLM streaming call (e.g., OpenAI ChatCompletion with stream=True).

    Args:
        query: User's question.
        contexts: Retrieved context chunks.
        repo_name: Repository name for display.

    Returns:
        List of response text chunks (simulates streaming).
    """
    parts: list[str] = []

    if not contexts:
        parts.append(
            f"I couldn't find specific code context in **{repo_name}** "
            f"related to your query. This might be because:\n\n"
            f"- The query doesn't match any indexed code patterns\n"
            f"- The relevant code uses different naming conventions\n\n"
            f"Try rephrasing your question with specific class or function names."
        )
        return parts

    parts.append(f"## Analysis of `{repo_name}`\n\n")
    parts.append(f"Based on your query: *\"{query}\"*\n\n")
    parts.append(f"I found **{len(contexts)}** relevant code sections:\n\n")

    for i, ctx in enumerate(contexts, 1):
        file_info = f"`{ctx.file_path}`"
        if ctx.start_line and ctx.end_line:
            file_info += f" (lines {ctx.start_line}-{ctx.end_line})"

        parts.append(f"### {i}. {file_info}\n")
        parts.append(f"- **Relevance**: {ctx.relevance_score:.0%}\n")
        parts.append(f"- **Found via**: {ctx.retrieval_method} search\n")

        if ctx.content:
            # Show a preview of the code
            preview = ctx.content[:300]
            if len(ctx.content) > 300:
                preview += "..."
            parts.append(f"```{ctx.language}\n{preview}\n```\n\n")

    parts.append(
        "\n---\n*This is a context-based analysis. "
        "Connect an LLM (GPT-4 / Claude) for deeper conversational analysis.*\n"
    )

    return parts
