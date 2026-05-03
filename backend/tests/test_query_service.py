"""Tests for the async QueryService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.services.document_service import DocumentMetadata, DocumentSearchResult
from app.services.query_service import (
    QueryRequest,
    QueryService,
    _INSUFFICIENT_CONTEXT_ANSWER,
)


def _make_search_result(doc_id: str, score: float, idx: int = 0) -> DocumentSearchResult:
    return DocumentSearchResult(
        id=f"chunk-{doc_id}-{idx}",
        content=f"content-{doc_id}-{idx}",
        similarity_score=score,
        metadata=DocumentMetadata(
            document_id=doc_id,
            title=f"Title {doc_id}",
            chunk_index=idx,
            organization_id="org-A",
        ),
    )


@pytest.fixture
def mock_document_service():
    svc = MagicMock()
    svc.search = AsyncMock(return_value=[])
    return svc


@pytest.fixture
def mock_llm_client():
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="A safe answer.")
    return llm


@pytest.fixture
def query_service(mock_document_service, mock_llm_client):
    return QueryService(
        document_service=mock_document_service,
        llm_client=mock_llm_client,
    )


# -------------------------- request validation --------------------------

def test_question_too_long_raises_validation_error():
    with pytest.raises(ValidationError):
        QueryRequest(
            question="x" * 2001,
            user_id="u1",
            session_id="s1",
        )


def test_question_too_short_raises_validation_error():
    with pytest.raises(ValidationError):
        QueryRequest(question="hi", user_id="u1", session_id="s1")


# -------------------------- LLM is called with disclaimer --------------------------

@pytest.mark.asyncio
async def test_ask_question_calls_llm_with_medical_disclaimer(
    query_service, mock_document_service, mock_llm_client
):
    mock_document_service.search = AsyncMock(
        return_value=[_make_search_result("doc-1", 0.9)]
    )
    request = QueryRequest(
        question="What is the treatment for diabetes?",
        user_id="u1",
        session_id="s1",
    )
    await query_service.ask_question(request, organization_id="org-A")

    mock_llm_client.complete.assert_awaited_once()
    system_prompt, _ = mock_llm_client.complete.await_args.args
    assert "educational purposes only" in system_prompt
    assert "consult" in system_prompt.lower()


@pytest.mark.asyncio
async def test_response_carries_query_id(query_service, mock_document_service):
    mock_document_service.search = AsyncMock(
        return_value=[_make_search_result("doc-1", 0.9)]
    )
    response = await query_service.ask_question(
        QueryRequest(
            question="Tell me about hypertension management.",
            user_id="user-42",
            session_id="session-7",
        ),
        organization_id="org-A",
    )
    assert response.query_id
    assert isinstance(response.query_id, str)


# -------------------------- empty context skips LLM --------------------------

@pytest.mark.asyncio
async def test_no_context_chunks_skips_llm_call(
    query_service, mock_document_service, mock_llm_client
):
    mock_document_service.search = AsyncMock(return_value=[])

    response = await query_service.ask_question(
        QueryRequest(
            question="What is a fictional disease?",
            user_id="u1",
            session_id="s1",
        ),
        organization_id="org-A",
    )
    assert response.answer == _INSUFFICIENT_CONTEXT_ANSWER
    assert response.sources == []
    mock_llm_client.complete.assert_not_called()


# -------------------------- source dedup keeps highest score --------------------------

@pytest.mark.asyncio
async def test_source_dedup_keeps_highest_scoring_chunk(
    query_service, mock_document_service, mock_llm_client
):
    mock_document_service.search = AsyncMock(
        return_value=[
            _make_search_result("doc-A", 0.4, idx=0),
            _make_search_result("doc-A", 0.9, idx=1),  # higher score, same doc
            _make_search_result("doc-B", 0.7, idx=0),
        ]
    )
    response = await query_service.ask_question(
        QueryRequest(
            question="What is the treatment plan?",
            user_id="u1",
            session_id="s1",
        ),
        organization_id="org-A",
    )
    by_id = {s.document_id: s.similarity_score for s in response.sources}
    assert by_id["doc-A"] == pytest.approx(0.9)
    assert by_id["doc-B"] == pytest.approx(0.7)
