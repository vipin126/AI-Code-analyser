"""RAG service — local lexical retrieval combined with AST structural search.

Handles:
- Code chunk storage in Qdrant
- Local BM25 retrieval over stored chunk payloads
- Structural search against AST node names
- Hybrid merge and re-ranking of results
"""

import logging
import math
import re
import uuid
from collections import Counter
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings
from app.schemas.analysis import CodeChunk, RetrievedContext

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────
MAX_CHUNKS_PER_BATCH = 100
QDRANT_SCROLL_PAGE_SIZE = 256
LOCAL_INDEX_DIMENSIONS = 1


class RAGService:
    """Store code chunks and perform local hybrid retrieval.

    Combines BM25 keyword ranking with structural AST search to produce
    ranked context chunks for LLM prompt assembly.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

        # Qdrant stores code-chunk payloads; retrieval ranks them locally with BM25.
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
        name = collection_name or self.settings.openrouter_qdrant_collection_name

        collections = self._qdrant.get_collections().collections
        existing_names = {c.name for c in collections}

        if name not in existing_names:
            self._qdrant.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=LOCAL_INDEX_DIMENSIONS,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", name)
        else:
            logger.info("Qdrant collection already exists: %s", name)

        self._qdrant.create_payload_index(
            collection_name=name,
            field_name="repository_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )

    def store_code_chunks(
        self,
        chunks: list[CodeChunk],
        repository_id: str,
    ) -> list[str]:
        """Store code chunks in Qdrant for local lexical retrieval.

        A fixed placeholder vector is required by the Qdrant collection schema;
        retrieval uses the stored payload and does not compare these vectors.

        Args:
            chunks: Code chunks to store for local retrieval.
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
            # Build Qdrant points
            points: list[PointStruct] = []
            for chunk in batch:
                point_id = str(uuid.uuid4())
                all_point_ids.append(point_id)

                points.append(PointStruct(
                    id=point_id,
                    vector=[1.0],
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
                collection_name=self.settings.openrouter_qdrant_collection_name,
                points=points,
            )

            logger.info(
                "Stored code chunk batch %d-%d (%d chunks)",
                i, i + len(batch), len(batch),
            )

        logger.info(
            "Stored %d code chunks for repository %s",
            len(all_point_ids), repository_id,
        )
        return all_point_ids

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split code and natural-language text into searchable terms."""
        return re.findall(r"[a-z0-9_]+", text.casefold())

    async def hybrid_search(
        self,
        query: str,
        repository_id: str,
        dependency_graph: dict | None = None,
        top_k: int = 10,
    ) -> list[RetrievedContext]:
        """Perform hybrid search combining BM25 and structural matching.

        1. Lexical search: Rank stored code chunks locally with BM25.
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

        # ── 1. Lexical Search ────────────────────────────────
        lexical_results = self._lexical_search(query, repository_id, top_k)
        results.extend(lexical_results)

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

    def _lexical_search(
        self, query: str, repository_id: str, top_k: int
    ) -> list[RetrievedContext]:
        """Search stored code chunk payloads with BM25 lexical ranking.

        Args:
            query: Natural-language or code-oriented query.
            repository_id: Filter results to this repository.
            top_k: Number of results.

        Returns:
            List of RetrievedContext from lexical search.
        """
        query_terms = set(self._tokenize(query))
        if not query_terms:
            return []

        self.ensure_collection()

        documents: list[tuple[str | int, Counter[str], int]] = []
        document_frequency: Counter[str] = Counter()
        document_count = 0
        total_document_length = 0
        offset: int | str | None = None

        while True:
            records, next_offset = self._qdrant.scroll(
                collection_name=self.settings.openrouter_qdrant_collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="repository_id",
                            match=MatchValue(value=repository_id),
                        )
                    ]
                ),
                limit=QDRANT_SCROLL_PAGE_SIZE,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            for record in records:
                payload = record.payload
                if not payload:
                    continue
                text = " ".join(
                    str(payload.get(field) or "")
                    for field in ("content", "file_path", "language", "node_name")
                )
                frequencies = Counter(self._tokenize(text))
                document_count += 1
                total_document_length += sum(frequencies.values())
                matched_terms = query_terms.intersection(frequencies)
                if matched_terms:
                    documents.append((
                        record.id,
                        Counter({term: frequencies[term] for term in matched_terms}),
                        sum(frequencies.values()),
                    ))
                    document_frequency.update(matched_terms)

            if next_offset is None:
                break
            offset = next_offset

        if not documents or document_count == 0:
            return []

        average_length = total_document_length / document_count
        scored_documents: list[tuple[float, int, str | int]] = []
        for index, (point_id, frequencies, document_length) in enumerate(documents):
            score = 0.0
            for term in query_terms.intersection(frequencies):
                frequency = frequencies[term]
                inverse_document_frequency = math.log(
                    1 + (document_count - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                length_normalization = 1.5 * (
                    1 - 0.75 + 0.75 * document_length / max(average_length, 1)
                )
                score += inverse_document_frequency * (
                    frequency * (1.5 + 1)
                ) / (frequency + length_normalization)

            scored_documents.append((score / (score + 1), index, point_id))

        scored_documents.sort(key=lambda result: result[0], reverse=True)
        point_ids = [point_id for _, _, point_id in scored_documents[:top_k]]
        records = self._qdrant.retrieve(
            collection_name=self.settings.openrouter_qdrant_collection_name,
            ids=point_ids,
            with_payload=True,
            with_vectors=False,
        )
        payload_by_id = {
            record.id: record.payload
            for record in records
            if record.payload
        }

        ranked: list[RetrievedContext] = []
        for score, _, point_id in scored_documents[:top_k]:
            payload = payload_by_id.get(point_id)
            if not payload:
                continue
            ranked.append(
                RetrievedContext(
                    content=str(payload.get("content") or ""),
                    file_path=str(payload.get("file_path") or ""),
                    start_line=int(payload.get("start_line") or 0),
                    end_line=int(payload.get("end_line") or 0),
                    language=str(payload.get("language") or ""),
                    relevance_score=score,
                    retrieval_method="lexical",
                )
            )
        return ranked

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
        query_terms = self._tokenize(query)
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
                    relevance_score=min(score * 0.8, 1.0),
                    retrieval_method="structural",
                ))

        # Sort by relevance and take top_k
        matches.sort(key=lambda x: x.relevance_score, reverse=True)
        return matches[:top_k]

    def _merge_and_rerank(
        self, results: list[RetrievedContext], top_k: int
    ) -> list[RetrievedContext]:
        """Merge lexical and structural results, deduplicate, and re-rank.

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
            existing = seen.get(key)
            if (
                existing is None
                or (
                    ctx.retrieval_method == "lexical"
                    and existing.retrieval_method == "structural"
                )
                or ctx.relevance_score > existing.relevance_score
            ):
                seen[key] = ctx

        # Sort by relevance score descending
        merged = sorted(seen.values(), key=lambda x: x.relevance_score, reverse=True)
        return merged[:top_k]

    def delete_repository_chunks(self, repository_id: str) -> None:
        """Delete all indexed code chunks for a repository from Qdrant.

        Args:
            repository_id: The repository whose indexed chunks to delete.
        """
        try:
            self._qdrant.delete(
                collection_name=self.settings.openrouter_qdrant_collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="repository_id",
                            match=MatchValue(value=repository_id),
                        )
                    ]
                ),
            )
            logger.info("Deleted indexed code chunks for repository %s", repository_id)
        except Exception as e:
            logger.error("Failed to delete indexed code chunks for %s: %s", repository_id, e)
