"""Hybrid retrieval: dense vector search + sparse BM25, with Redis caching.

The retriever is engineered to degrade gracefully:
- If the vector DB is unreachable, BM25 results are still returned.
- If Redis is unavailable, we just skip the cache and continue.
- A pluggable ``VectorDBClient`` protocol lets callers (and tests) swap
  Pinecone / Weaviate / a stub implementation without code changes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Protocol, runtime_checkable

from app.rag.exceptions import RetrievalError
from app.rag.models import ParsedQuery, RetrievedChunk

logger = logging.getLogger(__name__)


@runtime_checkable
class VectorDBClient(Protocol):
    """Provider-agnostic vector DB client.

    Implementations may wrap Pinecone, Weaviate, or any compatible store.
    Must be safe to call from an async context.
    """

    async def query(
        self, query_text: str, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[RetrievedChunk]:
        """Return up to ``top_k`` semantically similar chunks."""
        ...


@runtime_checkable
class KeywordSearchClient(Protocol):
    """Sparse / keyword search backend (e.g. BM25 over a chunk corpus)."""

    async def search(
        self, terms: list[str], top_k: int
    ) -> list[RetrievedChunk]:
        """Return up to ``top_k`` keyword-matched chunks."""
        ...


@runtime_checkable
class CacheClient(Protocol):
    """Minimal Redis-style cache interface used by the retriever."""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> None: ...


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]], k: int = 60
) -> list[RetrievedChunk]:
    """Merge multiple ranked lists into a single list using RRF.

    See: Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and
    individual Rank Learning Methods" (2009). ``k`` is the standard
    smoothing constant of 60.
    """
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}

    for ranked_list in rankings:
        for rank, chunk in enumerate(ranked_list):
            chunks.setdefault(chunk.chunk_id, chunk)
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)

    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    merged: list[RetrievedChunk] = []
    for chunk_id, score in fused:
        chunk = chunks[chunk_id].model_copy(update={"score": score})
        merged.append(chunk)
    return merged


class Retriever:
    """Hybrid (dense + sparse) retriever with optional Redis caching."""

    def __init__(
        self,
        vector_client: VectorDBClient | None = None,
        keyword_client: KeywordSearchClient | None = None,
        cache_client: CacheClient | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.vector_client = vector_client
        self.keyword_client = keyword_client
        self.cache_client = cache_client
        self.cache_ttl_seconds = cache_ttl_seconds

    @staticmethod
    def _cache_key(parsed_query: ParsedQuery, top_k: int) -> str:
        """Deterministic cache key derived from parsed query content + top_k."""
        payload = json.dumps(
            {
                "q": parsed_query.original_query,
                "exp": sorted(parsed_query.expanded_terms),
                "ents": sorted(parsed_query.medical_entities),
                "intent": parsed_query.intent,
                "top_k": top_k,
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"rag:retrieval:{digest}"

    async def _get_cached(self, key: str) -> list[RetrievedChunk] | None:
        if self.cache_client is None:
            return None
        try:
            raw = await self.cache_client.get(key)
        except Exception as exc:  # cache must never break retrieval
            logger.warning("Cache get failed: %s", exc)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return [RetrievedChunk.model_validate(item) for item in data]
        except (ValueError, TypeError) as exc:
            logger.warning("Failed to deserialize cached retrieval: %s", exc)
            return None

    async def _set_cached(self, key: str, chunks: list[RetrievedChunk]) -> None:
        if self.cache_client is None:
            return
        try:
            payload = json.dumps([c.model_dump() for c in chunks])
            await self.cache_client.set(key, payload, ex=self.cache_ttl_seconds)
        except Exception as exc:
            logger.warning("Cache set failed: %s", exc)

    async def _vector_search(
        self, parsed_query: ParsedQuery, top_k: int
    ) -> list[RetrievedChunk]:
        """Run dense retrieval, never raising — failures yield ``[]``."""
        if self.vector_client is None:
            return []
        try:
            return await self.vector_client.query(parsed_query.original_query, top_k)
        except Exception as exc:
            logger.error("Vector DB search failed: %s", exc, exc_info=True)
            return []

    async def _keyword_search(
        self, parsed_query: ParsedQuery, top_k: int
    ) -> list[RetrievedChunk]:
        """Run sparse retrieval, never raising — failures yield ``[]``."""
        if self.keyword_client is None:
            return []
        terms = [parsed_query.original_query, *parsed_query.expanded_terms,
                 *parsed_query.medical_entities]
        try:
            return await self.keyword_client.search(terms, top_k)
        except Exception as exc:
            logger.error("Keyword search failed: %s", exc, exc_info=True)
            return []

    async def retrieve(
        self, parsed_query: ParsedQuery, top_k: int
    ) -> list[RetrievedChunk]:
        """Run hybrid retrieval and return up to ``top_k`` fused chunks.

        Order of operations:
        1. Try cache (graceful skip on miss / failure).
        2. Run vector + keyword searches concurrently via ``asyncio.gather``.
        3. Merge with reciprocal rank fusion.
        4. Cache and return the top-k slice.
        """
        if top_k <= 0:
            raise RetrievalError("top_k must be > 0")

        cache_key = self._cache_key(parsed_query, top_k)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Retrieval cache hit: %s", cache_key)
            return cached[:top_k]

        vector_results, keyword_results = await asyncio.gather(
            self._vector_search(parsed_query, top_k),
            self._keyword_search(parsed_query, top_k),
        )

        if not vector_results and not keyword_results:
            logger.warning(
                "Both vector and keyword retrieval returned empty results "
                "for query=%r", parsed_query.original_query
            )
            return []

        fused = reciprocal_rank_fusion([vector_results, keyword_results])
        result = fused[:top_k]
        await self._set_cached(cache_key, result)
        return result
