"""Tests for app.rag.retriever."""

from __future__ import annotations

import json

import pytest

from app.rag.exceptions import RetrievalError
from app.rag.models import ParsedQuery, RetrievedChunk
from app.rag.retriever import Retriever, reciprocal_rank_fusion


def _chunk(cid: str, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid,
        content=f"content for {cid}",
        source_url=f"https://example.com/{cid}",
        source_name="Example",
        score=score,
        metadata={},
    )


class FakeVectorClient:
    def __init__(self, results: list[RetrievedChunk] | None = None,
                 raise_exc: Exception | None = None) -> None:
        self.results = results or []
        self.raise_exc = raise_exc
        self.calls = 0

    async def query(self, query_text: str, top_k: int, filters=None):
        self.calls += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.results[:top_k]


class FakeKeywordClient:
    def __init__(self, results: list[RetrievedChunk] | None = None,
                 raise_exc: Exception | None = None) -> None:
        self.results = results or []
        self.raise_exc = raise_exc
        self.calls = 0

    async def search(self, terms, top_k):
        self.calls += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.results[:top_k]


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.get_calls = 0
        self.set_calls = 0

    async def get(self, key):
        self.get_calls += 1
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.set_calls += 1
        self.store[key] = value


@pytest.fixture
def parsed_query() -> ParsedQuery:
    return ParsedQuery(
        original_query="treatment for diabetes",
        expanded_terms=["t2dm"],
        medical_entities=["diabetes"],
        intent="treatment",
    )


class TestReciprocalRankFusion:
    def test_merges_two_lists(self) -> None:
        a = [_chunk("x"), _chunk("y")]
        b = [_chunk("y"), _chunk("z")]
        merged = reciprocal_rank_fusion([a, b])
        ids = [m.chunk_id for m in merged]
        assert ids[0] == "y"  # appears at top of both lists
        assert set(ids) == {"x", "y", "z"}

    def test_empty_input(self) -> None:
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []


class TestRetrieverHappyPath:
    @pytest.mark.asyncio
    async def test_returns_fused_results(self, parsed_query: ParsedQuery) -> None:
        vec = FakeVectorClient(results=[_chunk("a"), _chunk("b")])
        kw = FakeKeywordClient(results=[_chunk("b"), _chunk("c")])
        retriever = Retriever(vector_client=vec, keyword_client=kw)
        result = await retriever.retrieve(parsed_query, top_k=3)
        ids = [c.chunk_id for c in result]
        assert ids[0] == "b"
        assert len(result) == 3
        assert vec.calls == 1
        assert kw.calls == 1


class TestRetrieverGracefulDegradation:
    @pytest.mark.asyncio
    async def test_vector_failure_falls_back_to_keyword(
        self, parsed_query: ParsedQuery
    ) -> None:
        vec = FakeVectorClient(raise_exc=RuntimeError("pinecone down"))
        kw = FakeKeywordClient(results=[_chunk("k1"), _chunk("k2")])
        retriever = Retriever(vector_client=vec, keyword_client=kw)
        result = await retriever.retrieve(parsed_query, top_k=2)
        assert len(result) == 2
        assert {c.chunk_id for c in result} == {"k1", "k2"}

    @pytest.mark.asyncio
    async def test_both_unavailable_returns_empty(
        self, parsed_query: ParsedQuery
    ) -> None:
        retriever = Retriever()
        result = await retriever.retrieve(parsed_query, top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_invalid_top_k_raises(self, parsed_query: ParsedQuery) -> None:
        retriever = Retriever()
        with pytest.raises(RetrievalError):
            await retriever.retrieve(parsed_query, top_k=0)


class TestRetrieverCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_search(self, parsed_query: ParsedQuery) -> None:
        chunks = [_chunk("a"), _chunk("b")]
        cache = FakeCache()
        cache.store[Retriever._cache_key(parsed_query, 2)] = json.dumps(
            [c.model_dump() for c in chunks]
        )
        vec = FakeVectorClient(results=[_chunk("z")])
        retriever = Retriever(vector_client=vec, cache_client=cache)
        result = await retriever.retrieve(parsed_query, top_k=2)
        assert [c.chunk_id for c in result] == ["a", "b"]
        assert vec.calls == 0  # short-circuited by cache

    @pytest.mark.asyncio
    async def test_cache_miss_then_set(self, parsed_query: ParsedQuery) -> None:
        cache = FakeCache()
        vec = FakeVectorClient(results=[_chunk("a")])
        retriever = Retriever(vector_client=vec, cache_client=cache)
        await retriever.retrieve(parsed_query, top_k=1)
        assert cache.set_calls == 1

    @pytest.mark.asyncio
    async def test_cache_failure_does_not_break_retrieval(
        self, parsed_query: ParsedQuery
    ) -> None:
        class BrokenCache:
            async def get(self, key):
                raise RuntimeError("redis down")

            async def set(self, key, value, ex=None):
                raise RuntimeError("redis down")

        vec = FakeVectorClient(results=[_chunk("a")])
        retriever = Retriever(vector_client=vec, cache_client=BrokenCache())
        result = await retriever.retrieve(parsed_query, top_k=1)
        assert len(result) == 1
