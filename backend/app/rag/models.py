"""Pydantic v2 models that flow through the RAG processing pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


QueryIntent = Literal["diagnosis", "treatment", "drug_info", "general"]


class ParsedQuery(BaseModel):
    """Output of the query parser stage."""

    original_query: str
    expanded_terms: list[str] = Field(default_factory=list)
    medical_entities: list[str] = Field(default_factory=list)
    intent: QueryIntent = "general"
    language: str = "en"

    model_config = ConfigDict(extra="forbid")


class RetrievedChunk(BaseModel):
    """A chunk returned by the retriever (vector + keyword hybrid)."""

    chunk_id: str
    content: str
    source_url: str
    source_name: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RankedChunk(RetrievedChunk):
    """A retrieved chunk after re-ranking."""

    rank: int = 0
    relevance_score: float = 0.0


class RAGRequest(BaseModel):
    """Input contract for the RAG pipeline."""

    query: str
    user_id: str
    session_id: str
    top_k: int = 5
    min_confidence: float = 0.7

    model_config = ConfigDict(extra="forbid")


class RAGResponse(BaseModel):
    """Output contract for the RAG pipeline."""

    answer: str
    sources: list[RankedChunk] = Field(default_factory=list)
    confidence_score: float = 0.0
    disclaimer: str = ""
    query_id: str
    processing_time_ms: int = 0

    model_config = ConfigDict(extra="forbid")


class StepLatency(BaseModel):
    """Per-step wall-clock latency in milliseconds."""

    parse_ms: int = 0
    retrieve_ms: int = 0
    rerank_ms: int = 0
    validate_ms: int = 0
    prompt_ms: int = 0
    llm_ms: int = 0


class PipelineState(BaseModel):
    """Mutable state passed through the pipeline so any step can be replayed/debugged.

    Intentionally permissive about ``None`` values during in-flight execution.
    """

    query_id: str
    request: RAGRequest
    parsed_query: ParsedQuery | None = None
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    ranked_chunks: list[RankedChunk] = Field(default_factory=list)
    validated_chunks: list[RankedChunk] = Field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""
    llm_response: str = ""
    confidence_score: float = 0.0
    latencies: StepLatency = Field(default_factory=StepLatency)
    failed_step: str | None = None
    error: str | None = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
