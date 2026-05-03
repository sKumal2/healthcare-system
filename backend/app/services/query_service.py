"""Question-answering service backed by the RAG pipeline pieces.

Replaces the previous mock LLM with a real :class:`LLMClient` call and
delegates prompt construction to :class:`PromptBuilder` so the medical
disclaimer / citation rules are always present.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.rag.llm_client import LLMClient
from app.rag.models import ParsedQuery, RankedChunk
from app.rag.prompt_builder import PromptBuilder
from app.services.document_service import DocumentService

UTC = timezone.utc
logger = logging.getLogger(__name__)


_INSUFFICIENT_CONTEXT_ANSWER = "I cannot find reliable information on this."


class QueryRequest(BaseModel):
    """Request model for asking a question."""

    question: str = Field(..., min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    user_id: str
    session_id: str


class SourceMetadata(BaseModel):
    """Metadata for a source document cited in the answer."""

    document_id: str
    title: str
    source_url: Optional[str] = None
    author: Optional[str] = None
    similarity_score: float


class QueryResponse(BaseModel):
    """Response model containing the answer and sources."""

    question: str
    answer: str
    sources: List[SourceMetadata]
    tokens_used: Optional[int] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    query_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class QueryService:
    """Service layer for question-answering using RAG."""

    def __init__(self, document_service: DocumentService, llm_client: LLMClient):
        self.document_service = document_service
        self.llm_client = llm_client

    async def _retrieve_context_chunks(
        self, question: str, top_k: int, organization_id: str
    ) -> List[dict]:
        search_results = await self.document_service.search(
            query_text=question,
            organization_id=organization_id,
            top_k=top_k,
        )

        chunks: List[dict] = []
        for result in search_results:
            chunks.append(
                {
                    "content": result.content,
                    "document_id": result.metadata.document_id,
                    "title": result.metadata.title,
                    "source_url": result.metadata.source_url,
                    "author": result.metadata.author,
                    "similarity_score": result.similarity_score,
                }
            )
        return chunks

    def _build_prompt(
        self, question: str, context_chunks: List[dict]
    ) -> tuple[str, str]:
        builder = PromptBuilder()
        parsed_query = ParsedQuery(
            original_query=question,
            expanded_terms=[],
            medical_entities=[],
            intent="general",
            language="en",
        )
        ranked_chunks = [
            RankedChunk(
                chunk_id=c["document_id"],
                content=c["content"],
                source_url=c.get("source_url") or "",
                source_name=c.get("title") or "",
                score=c["similarity_score"],
                metadata={},
                rank=idx + 1,
                relevance_score=c["similarity_score"],
            )
            for idx, c in enumerate(context_chunks)
        ]
        return builder.build(parsed_query, ranked_chunks)

    async def _generate_answer(self, system_prompt: str, user_prompt: str) -> str:
        return await self.llm_client.complete(system_prompt, user_prompt)

    async def ask_question(
        self, query_request: QueryRequest, organization_id: str
    ) -> QueryResponse:
        """Answer a question using RAG (Retrieval-Augmented Generation).

        ``organization_id`` is required so the underlying document search
        only sees the caller's tenant.
        """
        question = query_request.question
        top_k = query_request.top_k
        query_id = uuid.uuid4().hex

        context_chunks = await self._retrieve_context_chunks(
            question, top_k, organization_id
        )

        if not context_chunks:
            logger.info(
                "no_context_chunks query_id=%s user_id=%s",
                query_id,
                query_request.user_id,
            )
            return QueryResponse(
                question=question,
                answer=_INSUFFICIENT_CONTEXT_ANSWER,
                sources=[],
                tokens_used=None,
                query_id=query_id,
            )

        system_prompt, user_prompt = self._build_prompt(question, context_chunks)
        answer = await self._generate_answer(system_prompt, user_prompt)

        # Dedup sources by document_id, keeping the highest-scoring chunk.
        best_chunks: dict[str, dict[str, Any]] = {}
        for chunk in context_chunks:
            doc_id = chunk["document_id"]
            current = best_chunks.get(doc_id)
            if current is None or chunk["similarity_score"] > current["similarity_score"]:
                best_chunks[doc_id] = chunk

        sources = [
            SourceMetadata(
                document_id=doc_id,
                title=c["title"],
                source_url=c.get("source_url"),
                author=c.get("author"),
                similarity_score=c["similarity_score"],
            )
            for doc_id, c in best_chunks.items()
        ]

        logger.info(
            "query_answered query_id=%s user_id=%s session_id=%s sources=%d",
            query_id,
            query_request.user_id,
            query_request.session_id,
            len(sources),
        )

        return QueryResponse(
            question=question,
            answer=answer,
            sources=sources,
            tokens_used=None,
            query_id=query_id,
        )
