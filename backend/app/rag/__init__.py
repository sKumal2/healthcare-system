"""RAG Processing Engine for the Healthcare System.

Implements: Query Parser -> Retrieval -> Ranking -> Prompt Engineering -> LLM Call -> Response.
"""

from app.rag.pipeline import RAGPipeline
from app.rag.models import (
    ParsedQuery,
    RetrievedChunk,
    RankedChunk,
    RAGRequest,
    RAGResponse,
    PipelineState,
)
from app.rag.exceptions import (
    RAGError,
    InsufficientSourcesError,
    RetrievalError,
    LLMError,
    LLMRateLimitError,
    LLMConnectionError,
    LLMAPIError,
)

__all__ = [
    "RAGPipeline",
    "ParsedQuery",
    "RetrievedChunk",
    "RankedChunk",
    "RAGRequest",
    "RAGResponse",
    "PipelineState",
    "RAGError",
    "InsufficientSourcesError",
    "RetrievalError",
    "LLMError",
    "LLMRateLimitError",
    "LLMConnectionError",
    "LLMAPIError",
]
