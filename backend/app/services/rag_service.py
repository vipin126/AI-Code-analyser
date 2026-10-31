"""RAG service — hybrid retrieval pipeline combining vector + structural search.

Handles:
- Code chunk embedding generation via OpenAI text-embedding-3-small
- Qdrant vector upsert and search
- Structural search against AST node names
- Hybrid merge and re-ranking of results
"""

import logging
import uuid
from typing import Any

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings
from app.schemas.analysis import CodeChunk, RetrievedContext

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────
EMBEDDING_DIMENSION = 1536  # text-embedding-3-small output dimension
MAX_CHUNKS_PER_BATCH = 100
MAX_TOKENS_PER_CHUNK = 1500


class RAGService:
    """Service for embedding code chunks and performing hybrid retrieval.

    Combines vector similarity search (Qdrant) with structural AST search
    to produce ranked context chunks for LLM prompt assembly.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

        # OpenAI client for embeddings
        self._openai = OpenAI(api_key=self.settings.openai_api_key)

        # Qdrant client for vector storage
        if self.settings.qdrant_url:
            self._qdrant = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key,
            )
        else:
            self._qdrant = QdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port,
                api_key=self.settings.qdrant_api_key,
            )

    def ensure_collection(self, collection_name: str | None = None) -> None:
        """Create the Qdrant collection if it doesn't exist.

        Args:
            collection_name: Override collection name. Defaults to settings.
        """
        name = collection_name or self.settings.qdrant_collection_name

        collections = self._qdrant.get_collections().collections
        existing_names = {c.name for c in collections}

        if name not in existing_names:
            self._qdrant.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", name)
        else:
            logger.info("Qdrant collection already exists: %s", name)

    def generate_embeddings(
        self,
        chunks: list[CodeChunk],
        repository_id: str,
    ) -> list[str]:
        """Generate embeddings for code chunks and upsert to Qdrant.

        Processes chunks in batches to respect API rate limits.
        Each chunk is stored with metadata (file_path, language, line range)
        for filtered retrieval.

        Args:
            chunks: Code chunks to embed.
            repository_id: Repository UUID for namespace isolation.

        Returns:
            List of Qdrant point IDs.
        """
        if not chunks:
            return []

        self.ensure_collection()
        all_point_ids: list[str] = []

        # Process in batches
        for i in range(0, len(chunks), MAX_CHUNKS_PER_BATCH):
            batch = chunks[i : i + MAX_CHUNKS_PER_BATCH]
            texts = [self._prepare_chunk_text(chunk) for chunk in batch]

            # Generate embeddings via OpenAI
            try:
                response = self._openai.embeddings.create(
                    input=texts,
                    model=self.settings.openai_embedding_model,
                )
                embeddings = [item.embedding for item in response.data]
            except Exception as e:
                logger.error("OpenAI embedding error (batch %d): %s", i, e)
                raise

            # Build Qdrant points
            points: list[PointStruct] = []
            for chunk, embedding in zip(batch, embeddings, strict=True):
                point_id = str(uuid.uuid4())
                all_point_ids.append(point_id)

                points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "repository_id": repository_id,
                        "file_path": chunk.file_path,
                        "language": chunk.language,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "chunk_type": chunk.chunk_type,
                        "node_name": chunk.node_name,
                        "content": chunk.content,
                        "token_estimate": chunk.token_estimate,
                    },
                ))

            # Upsert to Qdrant
            self._qdrant.upsert(
                collection_name=self.settings.qdrant_collection_name,
                points=points,
            )

            logger.info(
                "Embedded batch %d-%d (%d chunks)",
                i, i + len(batch), len(batch),
            )

        logger.info(
            "Generated %d embeddings for repository %s",
            len(all_point_ids), repository_id,
        )
        return all_point_ids

    async def hybrid_search(
        self,
        query: str,
        repository_id: str,
        dependency_graph: dict | None = None,
        top_k: int = 10,
    ) -> list[RetrievedContext]:
        """Perform hybrid search combining vector similarity and structural matching.

        1. Vector search: Embed the query and find similar chunks in Qdrant.
        2. Structural search: Match query terms against AST node names in the graph.
        3. Merge: Combine and deduplicate results, re-rank by score.

        Args:
            query: User's natural language query.
            repository_id: Repository to search within.
            dependency_graph: Optional dependency graph for structural search.
            top_k: Number of results to return.

        Returns:
            Ranked list of RetrievedContext objects.
        """
        results: list[RetrievedContext] = []

        # ── 1. Vector Search ─────────────────────────────────
        vector_results = self._vector_search(query, repository_id, top_k)
        results.extend(vector_results)

        # ── 2. Structural Search ─────────────────────────────
        if dependency_graph:
            structural_results = self._structural_search(
                query, dependency_graph, top_k
            )
            results.extend(structural_results)

        # ── 3. Merge & Re-rank ───────────────────────────────
        merged = self._merge_and_rerank(results, top_k)

        logger.info(
            "Hybrid search returned %d results for query: '%.50s...'",
            len(merged), query,
        )
        return merged

    def _vector_search(
        self, query: str, repository_id: str, top_k: int
    ) -> list[RetrievedContext]:
        """Search Qdrant for semantically similar code chunks.

        Args:
            query: Natural language query to embed.
            repository_id: Filter results to this repository.
            top_k: Number of results.

        Returns:
            List of RetrievedContext from vector search.
        """
        try:
            # Embed the query
            response = self._openai.embeddings.create(
                input=[query],
                model=self.settings.openai_embedding_model,
            )
            query_vector = response.data[0].embedding

            # Search Qdrant with repository filter
            hits = self._qdrant.search(
                collection_name=self.settings.qdrant_collection_name,
                query_vector=query_vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="repository_id",
                            match=MatchValue(value=repository_id),
                        )
                    ]
                ),
                limit=top_k,
            )

            return [
                RetrievedContext(
                    content=hit.payload.get("content", ""),
                    file_path=hit.payload.get("file_path", ""),
                    start_line=hit.payload.get("start_line", 0),
                    end_line=hit.payload.get("end_line", 0),
                    language=hit.payload.get("language", ""),
                    relevance_score=min(hit.score, 1.0),
                    retrieval_method="vector",
                )
                for hit in hits
            ]

        except Exception as e:
            logger.error("Vector search error: %s", e)
            return []

    def _structural_search(
        self, query: str, dependency_graph: dict, top_k: int
    ) -> list[RetrievedContext]:
        """Search AST nodes by name matching against the query.

        Simple text matching: checks if any query term appears
        in node names (case-insensitive). Useful for queries like
        "find the UserService class" or "how does parse_file work".

        Args:
            query: User query to match against node names.
            dependency_graph: The repository's dependency graph.
            top_k: Maximum results to return.

        Returns:
            List of RetrievedContext from structural matching.
        """
        query_terms = query.lower().split()
        nodes: list[dict[str, Any]] = dependency_graph.get("nodes", [])
        matches: list[RetrievedContext] = []

        for node in nodes:
            node_name = node.get("name", "").lower()
            # Score: fraction of query terms that appear in the node name
            matching_terms = sum(1 for term in query_terms if term in node_name)
            if matching_terms > 0:
                score = matching_terms / len(query_terms)
                matches.append(RetrievedContext(
                    content=f"[{node.get('type', 'unknown')}] {node.get('name', '')} "
                            f"in {node.get('file_path', '')}",
                    file_path=node.get("file_path", ""),
                    start_line=node.get("line_start", 0),
                    end_line=node.get("line_end", 0),
                    language="",
                    relevance_score=min(score * 0.8, 1.0),  # Slightly lower weight than vector
                    retrieval_method="structural",
                ))

        # Sort by relevance and take top_k
        matches.sort(key=lambda x: x.relevance_score, reverse=True)
        return matches[:top_k]

    def _merge_and_rerank(
        self, results: list[RetrievedContext], top_k: int
    ) -> list[RetrievedContext]:
        """Merge vector and structural results, deduplicate, and re-rank.

        Deduplication is by (file_path, start_line). When duplicates exist,
        the higher-scoring entry is kept.

        Args:
            results: Combined results from all search methods.
            top_k: Final number of results to return.

        Returns:
            Deduplicated and re-ranked results.
        """
        # Deduplicate by (file_path, start_line)
        seen: dict[tuple[str, int], RetrievedContext] = {}
        for ctx in results:
            key = (ctx.file_path, ctx.start_line)
            if key not in seen or ctx.relevance_score > seen[key].relevance_score:
                seen[key] = ctx

        # Sort by relevance score descending
        merged = sorted(seen.values(), key=lambda x: x.relevance_score, reverse=True)
        return merged[:top_k]

    def _prepare_chunk_text(self, chunk: CodeChunk) -> str:
        """Prepare a code chunk's text for embedding.

        Prefixes with metadata for better semantic matching.

        Args:
            chunk: The code chunk to prepare.

        Returns:
            Formatted text for the embedding model.
        """
        prefix = f"[{chunk.language}] {chunk.file_path}"
        if chunk.node_name:
            prefix += f" :: {chunk.chunk_type} {chunk.node_name}"
        return f"{prefix}\n\n{chunk.content}"

    def delete_repository_embeddings(self, repository_id: str) -> None:
        """Delete all embeddings for a repository from Qdrant.

        Args:
            repository_id: The repository whose embeddings to delete.
        """
        try:
            self._qdrant.delete(
                collection_name=self.settings.qdrant_collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="repository_id",
                            match=MatchValue(value=repository_id),
                        )
                    ]
                ),
            )
            logger.info("Deleted embeddings for repository %s", repository_id)
        except Exception as e:
            logger.error("Failed to delete embeddings for %s: %s", repository_id, e)
