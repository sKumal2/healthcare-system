"""Prompt construction with token-aware truncation and strict instructions."""

from __future__ import annotations

import logging

from app.rag.models import ParsedQuery, RankedChunk

logger = logging.getLogger(__name__)


MEDICAL_DISCLAIMER = (
    "This information is for educational purposes only and does not "
    "constitute medical advice. Consult a qualified healthcare provider "
    "for diagnosis or treatment."
)


SYSTEM_PROMPT = (
    "You are a clinical information assistant for verified healthcare sources.\n"
    "Hard rules:\n"
    "1. Use ONLY the numbered context chunks below. Do NOT rely on prior knowledge.\n"
    "2. For every factual claim, cite the source URL inline using the format "
    "[Source: <url>].\n"
    "3. If the context does not contain enough information to answer, respond "
    "with exactly: 'I cannot find reliable information on this.'\n"
    "4. If sources contradict each other, explicitly call out the contradiction "
    "and cite each side.\n"
    "5. Never invent statistics, dosages, or guidelines that are not in context.\n"
    "6. End every answer with this disclaimer on its own line:\n"
    f"   {MEDICAL_DISCLAIMER}\n"
)


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars per token).

    Good enough for prompt-budget bookkeeping; the LLM client reports
    exact token usage post-hoc.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


class PromptBuilder:
    """Build (system, user) prompts within a token budget.

    The user prompt format is intentionally rigid so the LLM produces
    consistent citations: numbered chunks, source labels, then the question.
    """

    def __init__(self, max_prompt_tokens: int = 6000) -> None:
        if max_prompt_tokens <= 0:
            raise ValueError("max_prompt_tokens must be > 0")
        self.max_prompt_tokens = max_prompt_tokens

    @staticmethod
    def _format_chunk(idx: int, chunk: RankedChunk) -> str:
        return (
            f"[Chunk {idx}]\n"
            f"Source: {chunk.source_name} ({chunk.source_url})\n"
            f"Content: {chunk.content}\n"
        )

    def _build_user_prompt(
        self, parsed_query: ParsedQuery, chunks: list[RankedChunk]
    ) -> str:
        sections = [self._format_chunk(i, c) for i, c in enumerate(chunks, start=1)]
        context = "\n".join(sections) if sections else "(no context available)"
        intent_hint = (
            f"Detected intent: {parsed_query.intent}. "
            if parsed_query.intent != "general"
            else ""
        )
        return (
            f"{intent_hint}Answer the question using only the chunks above. "
            f"Cite source URLs inline.\n\n"
            f"Context:\n{context}\n"
            f"Question: {parsed_query.original_query}\n"
        )

    def build(
        self,
        parsed_query: ParsedQuery,
        ranked_chunks: list[RankedChunk],
    ) -> tuple[str, str]:
        """Return ``(system_prompt, user_prompt)`` within the configured token budget.

        When the prompt would overshoot ``max_prompt_tokens``, the
        lowest-ranked chunks are dropped first.
        """
        chunks = sorted(
            ranked_chunks, key=lambda c: c.relevance_score, reverse=True
        )

        system_tokens = estimate_tokens(SYSTEM_PROMPT)
        budget = self.max_prompt_tokens - system_tokens
        if budget <= 0:
            logger.warning("System prompt alone exceeds token budget; truncating.")
            return SYSTEM_PROMPT, ""

        kept: list[RankedChunk] = []
        running = estimate_tokens(parsed_query.original_query) + 64  # scaffolding
        for chunk in chunks:
            chunk_tokens = estimate_tokens(self._format_chunk(0, chunk))
            if running + chunk_tokens > budget:
                logger.info(
                    "Truncating prompt: dropping chunk_id=%s rank=%s "
                    "(would exceed token budget)",
                    chunk.chunk_id,
                    chunk.rank,
                )
                continue
            kept.append(chunk)
            running += chunk_tokens

        user_prompt = self._build_user_prompt(parsed_query, kept)
        return SYSTEM_PROMPT, user_prompt
