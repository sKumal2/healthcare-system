"""Re-rank retrieved chunks by combining query-overlap and source authority.

A real deployment should swap the heuristic in :meth:`Reranker._score`
for a cross-encoder such as ``cross-encoder/ms-marco-MiniLM-L-6-v2``
(via ``sentence-transformers``); the heuristic exists so the pipeline is
fully testable without GPU-bound model downloads.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from app.rag.models import RankedChunk, RetrievedChunk

logger = logging.getLogger(__name__)


SOURCE_AUTHORITY: dict[str, float] = {
    "cdc.gov": 1.0,
    "who.int": 1.0,
    "pubmed.ncbi.nlm.nih.gov": 0.95,
    "ncbi.nlm.nih.gov": 0.95,
    "nih.gov": 0.95,
    "fda.gov": 0.95,
    "mayoclinic.org": 0.85,
    "clevelandclinic.org": 0.85,
    "medlineplus.gov": 0.85,
    "webmd.com": 0.6,
    "healthline.com": 0.55,
}
DEFAULT_AUTHORITY = 0.4

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]+")


def _domain_for_url(url: str) -> str:
    """Return the registrable host for ``url`` (lowercased, no port)."""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().lstrip(".")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def authority_weight(source_url: str, source_name: str = "") -> float:
    """Lookup authority weight by domain (with parent-suffix fallback).

    Falls back to ``source_name`` (case-insensitive) when no URL match is found,
    and to :data:`DEFAULT_AUTHORITY` when the source is unknown.
    """
    host = _domain_for_url(source_url)
    if host in SOURCE_AUTHORITY:
        return SOURCE_AUTHORITY[host]
    # Try parent-suffix (e.g. ``foo.cdc.gov`` -> ``cdc.gov``).
    for known, weight in SOURCE_AUTHORITY.items():
        if host.endswith("." + known):
            return weight

    name_key = (source_name or "").lower()
    for known, weight in SOURCE_AUTHORITY.items():
        if known.split(".")[0] in name_key:
            return weight
    return DEFAULT_AUTHORITY


class Reranker:
    """Re-rank chunks using a query-overlap × source-authority heuristic."""

    def __init__(
        self,
        overlap_weight: float = 0.7,
        authority_weight: float = 0.3,
    ) -> None:
        if not 0.0 <= overlap_weight <= 1.0 or not 0.0 <= authority_weight <= 1.0:
            raise ValueError("Component weights must be in [0, 1].")
        self.overlap_weight = overlap_weight
        self.authority_weight = authority_weight

    @staticmethod
    def _overlap(query_tokens: set[str], chunk_tokens: set[str]) -> float:
        """Jaccard-like overlap of query terms present in the chunk."""
        if not query_tokens:
            return 0.0
        return len(query_tokens & chunk_tokens) / len(query_tokens)

    def _score(self, chunk: RetrievedChunk, query_tokens: set[str]) -> float:
        overlap = self._overlap(query_tokens, _tokens(chunk.content))
        authority = authority_weight(chunk.source_url, chunk.source_name)
        return self.overlap_weight * overlap + self.authority_weight * authority

    async def rerank(
        self, chunks: list[RetrievedChunk], query: str, top_k: int | None = None
    ) -> list[RankedChunk]:
        """Score and re-rank ``chunks`` and return them as ``RankedChunk``.

        Always returns the chunks in descending relevance order. Empty input
        returns an empty list.
        """
        if not chunks:
            return []

        query_tokens = _tokens(query)
        scored: list[tuple[float, RetrievedChunk]] = [
            (self._score(c, query_tokens), c) for c in chunks
        ]
        scored.sort(key=lambda kv: kv[0], reverse=True)

        ranked: list[RankedChunk] = []
        for rank, (score, chunk) in enumerate(scored, start=1):
            ranked.append(
                RankedChunk(
                    **chunk.model_dump(),
                    rank=rank,
                    relevance_score=score,
                )
            )
        if top_k is not None:
            return ranked[:top_k]
        return ranked
