"""Tests for app.rag.prompt_builder."""

from __future__ import annotations

import pytest

from app.rag.models import ParsedQuery, RankedChunk
from app.rag.prompt_builder import (
    MEDICAL_DISCLAIMER,
    PromptBuilder,
    SYSTEM_PROMPT,
    estimate_tokens,
)


def _chunk(cid: str, content: str, score: float = 0.5) -> RankedChunk:
    return RankedChunk(
        chunk_id=cid, content=content,
        source_url=f"https://cdc.gov/{cid}", source_name="CDC",
        score=score, metadata={}, rank=0, relevance_score=score,
    )


@pytest.fixture
def parsed_query() -> ParsedQuery:
    return ParsedQuery(
        original_query="What is metformin?",
        expanded_terms=["t2dm drug"],
        medical_entities=["metformin"],
        intent="drug_info",
    )


class TestEstimateTokens:
    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_short_string(self) -> None:
        assert estimate_tokens("abcd") >= 1


class TestPromptBuilder:
    def test_system_prompt_includes_disclaimer(
        self, parsed_query: ParsedQuery
    ) -> None:
        chunks = [_chunk("a", "metformin is a first-line drug for type 2 diabetes")]
        builder = PromptBuilder()
        system, _ = builder.build(parsed_query, chunks)
        assert MEDICAL_DISCLAIMER in system
        assert system == SYSTEM_PROMPT

    def test_user_prompt_lists_chunks_and_question(
        self, parsed_query: ParsedQuery
    ) -> None:
        chunks = [_chunk("a", "metformin info"), _chunk("b", "more metformin info")]
        _, user = PromptBuilder().build(parsed_query, chunks)
        assert "Chunk 1" in user
        assert "Chunk 2" in user
        assert "metformin info" in user
        assert "What is metformin?" in user

    def test_truncates_low_ranked_chunks_when_over_budget(
        self, parsed_query: ParsedQuery
    ) -> None:
        # Build chunks far beyond a tiny token budget; lowest-ranked first dropped
        chunks = [
            _chunk("hi", "x" * 1000, score=0.95),
            _chunk("lo", "y" * 1000, score=0.10),
        ]
        builder = PromptBuilder(max_prompt_tokens=600)  # tiny budget
        _, user = builder.build(parsed_query, chunks)
        assert "x" * 100 in user  # high-ranked content kept
        # Lower-ranked (score=0.10) dropped: its 1000 y's must NOT all be present
        assert "y" * 1000 not in user

    def test_handles_no_chunks(self, parsed_query: ParsedQuery) -> None:
        _, user = PromptBuilder().build(parsed_query, [])
        assert "no context available" in user

    def test_invalid_max_tokens_raises(self) -> None:
        with pytest.raises(ValueError):
            PromptBuilder(max_prompt_tokens=0)

    def test_intent_hint_included_for_specific_intent(
        self, parsed_query: ParsedQuery
    ) -> None:
        _, user = PromptBuilder().build(parsed_query, [_chunk("a", "info")])
        assert "drug_info" in user

    def test_no_intent_hint_for_general(self) -> None:
        general = ParsedQuery(
            original_query="hello", expanded_terms=[],
            medical_entities=[], intent="general",
        )
        _, user = PromptBuilder().build(general, [_chunk("a", "info")])
        assert "Detected intent" not in user
