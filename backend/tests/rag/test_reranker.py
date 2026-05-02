"""Tests for app.rag.reranker."""

from __future__ import annotations

import pytest

from app.rag.models import RetrievedChunk
from app.rag.reranker import (
    DEFAULT_AUTHORITY,
    Reranker,
    SOURCE_AUTHORITY,
    authority_weight,
)


def _chunk(cid: str, content: str, url: str, name: str = "") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, content=content, source_url=url,
        source_name=name, score=0.0, metadata={}
    )


class TestAuthorityWeight:
    def test_known_domain(self) -> None:
        assert authority_weight("https://www.cdc.gov/page", "CDC") == SOURCE_AUTHORITY["cdc.gov"]

    def test_subdomain_match(self) -> None:
        assert authority_weight("https://api.cdc.gov/data", "") == SOURCE_AUTHORITY["cdc.gov"]

    def test_unknown_domain_uses_default(self) -> None:
        assert authority_weight("https://random.io/x", "") == DEFAULT_AUTHORITY

    def test_who_authority(self) -> None:
        assert authority_weight("https://www.who.int/topics", "") == 1.0


class TestRerankerScoring:
    @pytest.mark.asyncio
    async def test_orders_by_combined_score(self) -> None:
        chunks = [
            _chunk("a", "diabetes treatment plan", "https://random.io/a"),
            _chunk("b", "diabetes treatment plan", "https://www.cdc.gov/b", "CDC"),
            _chunk("c", "completely unrelated content", "https://www.cdc.gov/c", "CDC"),
        ]
        ranker = Reranker()
        ranked = await ranker.rerank(chunks, "diabetes treatment")
        assert ranked[0].chunk_id == "b"  # high overlap + high authority
        assert ranked[-1].chunk_id == "c"  # low overlap

    @pytest.mark.asyncio
    async def test_empty_input(self) -> None:
        assert await Reranker().rerank([], "anything") == []

    @pytest.mark.asyncio
    async def test_top_k_truncation(self) -> None:
        chunks = [
            _chunk(f"c{i}", f"text {i}", f"https://www.cdc.gov/{i}", "CDC")
            for i in range(5)
        ]
        ranked = await Reranker().rerank(chunks, "text", top_k=2)
        assert len(ranked) == 2

    @pytest.mark.asyncio
    async def test_invalid_weights_raise(self) -> None:
        with pytest.raises(ValueError):
            Reranker(overlap_weight=2.0)

    @pytest.mark.asyncio
    async def test_ranks_assigned_sequentially(self) -> None:
        chunks = [
            _chunk("a", "diabetes", "https://www.cdc.gov/a"),
            _chunk("b", "hypertension", "https://www.who.int/b"),
        ]
        ranked = await Reranker().rerank(chunks, "diabetes")
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2
