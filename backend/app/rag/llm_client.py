"""Anthropic Claude client with retry, streaming-collection, and token logging."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.rag.exceptions import (
    LLMAPIError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
)

logger = logging.getLogger(__name__)


_DEFAULT_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


class LLMClient:
    """Async wrapper around the Anthropic SDK with retry and token tracking.

    Streaming is used internally to avoid hitting per-request size limits, but
    the public interface returns the assembled string so callers don't need
    to deal with chunk plumbing.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
        client: Any = None,
        backoff_seconds: tuple[float, ...] = _DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("ANTHROPIC_API_KEY is required to call the LLM.")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.backoff_seconds = backoff_seconds
        self._client = client or self._build_client(api_key)

    @staticmethod
    def _build_client(api_key: str) -> Any:
        """Lazy-import the Anthropic SDK so unit tests can run without it."""
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise LLMError(
                "The 'anthropic' package is required to call the LLM. "
                "Install with: pip install anthropic"
            ) from exc
        return anthropic.AsyncAnthropic(api_key=api_key)

    @staticmethod
    def _classify_exception(exc: BaseException) -> LLMError:
        """Map an SDK exception to one of our public exception types.

        Imports ``anthropic`` lazily so this stays usable in environments
        where the SDK isn't installed (e.g. CI without network deps).
        """
        try:
            import anthropic  # type: ignore
        except ImportError:
            return LLMAPIError(str(exc))

        if isinstance(exc, anthropic.RateLimitError):
            return LLMRateLimitError(str(exc))
        if isinstance(exc, anthropic.APIConnectionError):
            return LLMConnectionError(str(exc))
        if isinstance(exc, anthropic.APIError):
            return LLMAPIError(str(exc))
        return LLMAPIError(str(exc))

    async def _stream_once(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[str, dict[str, int]]:
        """Single streamed call. Returns ``(text, usage)``."""
        text_parts: list[str] = []
        usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            async for chunk in stream.text_stream:
                text_parts.append(chunk)
            final = await stream.get_final_message()
            if getattr(final, "usage", None):
                usage["input_tokens"] = getattr(final.usage, "input_tokens", 0)
                usage["output_tokens"] = getattr(final.usage, "output_tokens", 0)

        return "".join(text_parts), usage

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send the prompts to the LLM and return the assembled response text.

        Retries up to ``len(backoff_seconds)`` times on transient errors with
        exponential backoff. Logs token usage on success. Re-raises a
        :class:`LLMError` subclass on terminal failure.
        """
        last_exc: LLMError | None = None
        attempts = len(self.backoff_seconds) + 1

        for attempt in range(1, attempts + 1):
            try:
                text, usage = await self._stream_once(system_prompt, user_prompt)
                logger.info(
                    "llm_call_success",
                    extra={
                        "model": self.model,
                        "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "attempt": attempt,
                    },
                )
                return text
            except Exception as raw_exc:
                mapped = self._classify_exception(raw_exc)
                last_exc = mapped
                if isinstance(mapped, LLMRateLimitError) and attempt < attempts:
                    delay = self.backoff_seconds[attempt - 1]
                    logger.warning(
                        "llm_rate_limited; retrying in %.1fs (attempt %d/%d)",
                        delay, attempt, attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                if isinstance(mapped, LLMConnectionError) and attempt < attempts:
                    delay = self.backoff_seconds[attempt - 1]
                    logger.warning(
                        "llm_connection_error; retrying in %.1fs (attempt %d/%d): %s",
                        delay, attempt, attempts, mapped,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error("llm_call_failed: %s", mapped)
                raise mapped from raw_exc

        assert last_exc is not None
        raise last_exc
