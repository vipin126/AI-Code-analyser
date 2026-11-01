"""Analysis and parsing schemas — AST nodes, dependency graphs, code chunks."""

from pydantic import BaseModel, Field

# ── AST Parse Results ────────────────────────────────────────

class ASTNode(BaseModel):
    """A single node extracted from the AST (class, function, import, etc.)."""

    name: str
    type: str = Field(
        ...,
        description="Node type: class, function, method, import, variable, interface",
    )
    file_path: str
    line_start: int
    line_end: int
    docstring: str | None = None
    parameters: list[str] | None = None


class DependencyEdge(BaseModel):
    """A directed edge in the dependency graph."""

    source: str = Field(..., description="Source node identifier (file:name)")
    target: str = Field(..., description="Target node identifier (file:name or module)")
    relationship: str = Field(
        ...,
        description="Edge type: imports, calls, extends, implements",
    )


class ParseResult(BaseModel):
    """Parsed output for a single source file."""

    file_path: str
    language: str
    nodes: list[ASTNode] = Field(default_factory=list)
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    line_count: int = 0
    error: str | None = None


class DependencyGraph(BaseModel):
    """Complete dependency graph for a repository."""

    nodes: list[ASTNode] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)
    file_count: int = 0
    language_breakdown: dict[str, int] = Field(default_factory=dict)


# ── RAG / Code Search Schemas ───────────────────────────────

class CodeChunk(BaseModel):
    """A meaningful chunk of source code for retrieval."""

    content: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    chunk_type: str = Field(
        default="function",
        description="What this chunk represents: function, class, module, block",
    )
    node_name: str | None = None
    token_estimate: int = 0


class RetrievedContext(BaseModel):
    """A context chunk retrieved by the RAG pipeline for prompt assembly."""

    content: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    retrieval_method: str = Field(
        default="lexical",
        description="How this chunk was found: lexical, structural, hybrid",
    )
