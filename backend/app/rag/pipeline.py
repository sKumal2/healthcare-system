"""Top-level RAG pipeline: glues every stage together."""

from __future__ import annotations

import json
import logging
import time
import uuid
from statistics import mean

from app.rag.exceptions import (
    InsufficientSourcesError,
    LLMError,
    RAGError,
)
from app.rag.llm_client import LLMClient
from app.rag.models import (
    ParsedQuery,
    PipelineState,
    RAGRequest,
    RAGResponse,
    RankedChunk,
)
from app.rag.prompt_builder import MEDICAL_DISCLAIMER, PromptBuilder
from app.rag.query_parser import QueryParser
from app.rag.reranker import Reranker
from app.rag.retriever import Retriever
from app.rag.source_validator import SourceValidator

logger = logging.getLogger(__name__)


_INSUFFICIENT_SOURCES_ANSWER = (
    "I cannot find reliable information on this from verified medical "
    "sources. Please consult a qualified healthcare provider."
)


def _now_ms() -> int:
    return int(time.perf_counter() * 1000)


class RAGPipeline:
    """Orchestrates the full Query -> Retrieve -> Rank -> Validate -> Prompt -> LLM flow.

    All collaborators are injected so the pipeline is fully unit-testable
    without external services. Steps are individually wrapped: a failure
    in one step logs full :class:`PipelineState` and re-raises a
    :class:`RAGError`, except for ``InsufficientSourcesError`` which is
    converted into a "cannot verify" :class:`RAGResponse`.
    """

    def __init__(
        self,
        query_parser: QueryParser,
        retriever: Retriever,
        reranker: Reranker,
        source_validator: SourceValidator,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient,
        min_confidence: float = 0.7,
    ) -> None:
        self.query_parser = query_parser
        self.retriever = retriever
        self.reranker = reranker
        self.source_validator = source_validator
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.min_confidence = min_confidence

    @staticmethod
    def _confidence(chunks: list[RankedChunk]) -> float:
        """Confidence = mean relevance_score of the top-3 chunks (or fewer)."""
        if not chunks:
            return 0.0
        top = chunks[:3]
        return float(mean(c.relevance_score for c in top))

    def _log_state(self, state: PipelineState, level: int = logging.ERROR) -> None:
        """Emit a structured snapshot of pipeline state. NEVER includes raw query text.

        Logging the user's raw query risks leaking PHI; only metadata about the
        run (id, intent, counts, latencies) is emitted.
        """
        snapshot = {
            "query_id": state.query_id,
            "user_id": state.request.user_id,
            "session_id": state.request.session_id,
            "intent": state.parsed_query.intent if state.parsed_query else None,
            "n_retrieved": len(state.retrieved_chunks),
            "n_ranked": len(state.ranked_chunks),
            "n_validated": len(state.validated_chunks),
            "confidence_score": state.confidence_score,
            "latencies_ms": state.latencies.model_dump(),
            "failed_step": state.failed_step,
            "error": state.error,
        }
        logger.log(level, "rag_pipeline_state %s", json.dumps(snapshot))

    def _insufficient_response(
        self, state: PipelineState, total_ms: int
    ) -> RAGResponse:
        return RAGResponse(
            answer=_INSUFFICIENT_SOURCES_ANSWER,
            sources=state.validated_chunks,
            confidence_score=0.0,
            disclaimer=MEDICAL_DISCLAIMER,
            query_id=state.query_id,
            processing_time_ms=total_ms,
        )

    async def _step(self, state: PipelineState, name: str, coro):
        """Run a coroutine, time it, and on failure annotate ``state`` and re-raise."""
        start = _now_ms()
        try:
            result = await coro
        except InsufficientSourcesError:
            elapsed = _now_ms() - start
            setattr(state.latencies, f"{name}_ms", elapsed)
            raise
        except Exception as exc:
            elapsed = _now_ms() - start
            setattr(state.latencies, f"{name}_ms", elapsed)
            state.failed_step = name
            state.error = repr(exc)
            self._log_state(state)
            if isinstance(exc, RAGError):
                raise
            raise RAGError(f"Step '{name}' failed: {exc}") from exc

        elapsed = _now_ms() - start
        setattr(state.latencies, f"{name}_ms", elapsed)
        return result

    async def process(self, request: RAGRequest) -> RAGResponse:
        """Run the full pipeline and return a :class:`RAGResponse`.

        Always returns a response: when there are not enough trusted sources,
        a "cannot verify" answer is returned instead of raising.
        """
        wall_start = _now_ms()
        query_id = uuid.uuid4().hex
        state = PipelineState(query_id=query_id, request=request)

        try:
            parsed: ParsedQuery = await self._step(
                state, "parse", self.query_parser.parse(request.query)
            )
            state.parsed_query = parsed

            retrieved = await self._step(
                state, "retrieve", self.retriever.retrieve(parsed, request.top_k)
            )
            state.retrieved_chunks = retrieved

            ranked = await self._step(
                state, "rerank", self.reranker.rerank(retrieved, parsed.original_query)
            )
            state.ranked_chunks = ranked

            try:
                validated = await self._step(
                    state, "validate", self._validate_async(ranked)
                )
            except InsufficientSourcesError as exc:
                state.failed_step = "validate"
                state.error = repr(exc)
                state.validated_chunks = [
                    c for c in ranked if self.source_validator.is_trusted(c.source_url)
                ]
                self._log_state(state, level=logging.WARNING)
                total_ms = _now_ms() - wall_start
                return self._insufficient_response(state, total_ms)

            state.validated_chunks = validated[: request.top_k]

            system_prompt, user_prompt = await self._step(
                state, "prompt", self._build_prompt_async(parsed, state.validated_chunks)
            )
            state.system_prompt = system_prompt
            state.user_prompt = user_prompt

            answer = await self._step(
                state, "llm", self.llm_client.complete(system_prompt, user_prompt)
            )
            state.llm_response = answer

            confidence = self._confidence(state.validated_chunks)
            state.confidence_score = confidence

            total_ms = _now_ms() - wall_start
            self._log_state(state, level=logging.INFO)

            return RAGResponse(
                answer=answer,
                sources=state.validated_chunks,
                confidence_score=confidence,
                disclaimer=MEDICAL_DISCLAIMER,
                query_id=query_id,
                processing_time_ms=total_ms,
            )

        except LLMError:
            raise
        except RAGError:
            raise
        except Exception as exc:
            state.error = repr(exc)
            self._log_state(state)
            raise RAGError(f"Unexpected pipeline failure: {exc}") from exc

    async def _validate_async(self, chunks: list[RankedChunk]) -> list[RankedChunk]:
        """Wrap the sync validator in a coroutine so :meth:`_step` can time it."""
        return self.source_validator.validate(chunks)

    async def _build_prompt_async(
        self, parsed: ParsedQuery, chunks: list[RankedChunk]
    ) -> tuple[str, str]:
        """Wrap the sync prompt builder in a coroutine."""
        return self.prompt_builder.build(parsed, chunks)
