"""Integration tests for app.rag.pipeline.RAGPipeline."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.rag.exceptions import (
    InsufficientSourcesError,
    LLMRateLimitError,
    RAGError,
)
from app.rag.llm_client import LLMClient
from app.rag.models import (
    ParsedQuery,
    RAGRequest,
    RankedChunk,
    RetrievedChunk,
)
from app.rag.pipeline import RAGPipeline
from app.rag.prompt_builder import MEDICAL_DISCLAIMER, PromptBuilder
from app.rag.query_parser import QueryParser
from app.rag.reranker import Reranker
from app.rag.retriever import Retriever
from app.rag.source_validator import SourceValidator


@pytest.fixture
def request_obj() -> RAGRequest:
    return RAGRequest(
        query="What are common treatments for type 2 diabetes?",
        user_id="u-1",
        session_id="s-1",
        top_k=3,
    )


@pytest.fixture
def trusted_retrieved_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="c1",
            content="Type 2 diabetes is treated with metformin and lifestyle changes.",
            source_url="https://www.cdc.gov/diabetes/",
            source_name="CDC", score=0.9, metadata={},
        ),
        RetrievedChunk(
            chunk_id="c2",
            content="Insulin therapy is used in advanced diabetes cases.",
            source_url="https://www.who.int/diabetes",
            source_name="WHO", score=0.85, metadata={},
        ),
        RetrievedChunk(
            chunk_id="c3",
            content="Diabetes treatment guidelines emphasize HbA1c monitoring.",
            source_url="https://www.fda.gov/diabetes-guide",
            source_name="FDA", score=0.80, metadata={},
        ),
    ]


def _build_pipeline(
    retrieved: list[RetrievedChunk],
    llm_response: str = "Metformin is a first-line treatment [Source: cdc.gov].",
    llm_side_effect: Exception | None = None,
) -> RAGPipeline:
    """Construct an ``RAGPipeline`` wired to in-memory fakes."""

    class _VectorClient:
        async def query(self, query_text, top_k, filters=None):
            return retrieved[:top_k]

    class _KeywordClient:
        async def search(self, terms, top_k):
            return []

    retriever = Retriever(vector_client=_VectorClient(), keyword_client=_KeywordClient())

    llm = MagicMock(spec=LLMClient)
    if llm_side_effect:
        llm.complete = AsyncMock(side_effect=llm_side_effect)
    else:
        llm.complete = AsyncMock(return_value=llm_response)

    return RAGPipeline(
        query_parser=QueryParser(),
        retriever=retriever,
        reranker=Reranker(),
        source_validator=SourceValidator(min_valid_sources=2),
        prompt_builder=PromptBuilder(),
        llm_client=llm,
    )


class TestRAGPipelineHappyPath:
    @pytest.mark.asyncio
    async def test_end_to_end(
        self, request_obj: RAGRequest,
        trusted_retrieved_chunks: list[RetrievedChunk],
    ) -> None:
        pipeline = _build_pipeline(trusted_retrieved_chunks)
        response = await pipeline.process(request_obj)

        assert response.answer.startswith("Metformin")
        assert MEDICAL_DISCLAIMER in response.disclaimer
        assert response.query_id
        assert len(response.sources) >= 2
        for src in response.sources:
            assert isinstance(src, RankedChunk)
        assert 0.0 <= response.confidence_score <= 1.0
        assert response.processing_time_ms >= 0

    @pytest.mark.asyncio
    async def test_no_phi_in_logs(
        self, request_obj: RAGRequest,
        trusted_retrieved_chunks: list[RetrievedChunk],
        caplog,
    ) -> None:
        pipeline = _build_pipeline(trusted_retrieved_chunks)
        # Inject a PII-like token to confirm it never lands in logs.
        request_with_phi = request_obj.model_copy(update={
            "query": "Patient SSN 123-45-6789 has type 2 diabetes; what treatment?"
        })
        with caplog.at_level(logging.DEBUG, logger="app.rag.pipeline"):
            await pipeline.process(request_with_phi)
        joined = "\n".join(rec.getMessage() for rec in caplog.records)
        assert "123-45-6789" not in joined


class TestRAGPipelineEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_retrieval_raises_insufficient(
        self, request_obj: RAGRequest,
    ) -> None:
        pipeline = _build_pipeline(retrieved=[])
        response = await pipeline.process(request_obj)
        # No retrieved chunks -> validator hits InsufficientSourcesError ->
        # pipeline returns a "cannot verify" response (it does not raise).
        assert "cannot find reliable" in response.answer.lower()
        assert response.confidence_score == 0.0
        assert response.disclaimer == MEDICAL_DISCLAIMER

    @pytest.mark.asyncio
    async def test_all_untrusted_sources_returns_cannot_verify(
        self, request_obj: RAGRequest,
    ) -> None:
        untrusted = [
            RetrievedChunk(
                chunk_id=f"u{i}",
                content="random untrusted content about diabetes",
                source_url=f"https://random{i}.com/x",
                source_name="Random", score=0.5, metadata={},
            )
            for i in range(3)
        ]
        pipeline = _build_pipeline(retrieved=untrusted)
        response = await pipeline.process(request_obj)
        assert "cannot find reliable" in response.answer.lower()
        assert response.confidence_score == 0.0

    @pytest.mark.asyncio
    async def test_llm_rate_limit_propagates(
        self, request_obj: RAGRequest,
        trusted_retrieved_chunks: list[RetrievedChunk],
    ) -> None:
        pipeline = _build_pipeline(
            trusted_retrieved_chunks,
            llm_side_effect=LLMRateLimitError("rate limited"),
        )
        with pytest.raises(LLMRateLimitError):
            await pipeline.process(request_obj)

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        request = RAGRequest(query="", user_id="u", session_id="s", top_k=3)
        pipeline = _build_pipeline(retrieved=[])
        response = await pipeline.process(request)
        # Empty query -> no retrieval results -> insufficient sources path.
        assert "cannot find reliable" in response.answer.lower()


class TestConfidenceScore:
    @pytest.mark.asyncio
    async def test_confidence_is_mean_of_top_3(
        self, request_obj: RAGRequest,
        trusted_retrieved_chunks: list[RetrievedChunk],
    ) -> None:
        pipeline = _build_pipeline(trusted_retrieved_chunks)
        response = await pipeline.process(request_obj)
        if response.sources:
            top3 = response.sources[:3]
            expected = sum(c.relevance_score for c in top3) / len(top3)
            assert abs(response.confidence_score - expected) < 1e-6
