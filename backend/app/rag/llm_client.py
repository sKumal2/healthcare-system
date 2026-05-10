"""Provider-agnostic LLM client.

Supports Anthropic Claude and Google Gemini. Select the active provider via
the ``LLM_PROVIDER`` setting in ``.env``:

  * ``anthropic`` — Claude (uses ``ANTHROPIC_API_KEY``, paid)
  * ``gemini``    — Google Gemini (uses ``GEMINI_API_KEY``, free tier)

Callers should normally construct ``LLMClient()`` with no arguments and let
settings drive the choice. The legacy keyword-form
``LLMClient(api_key=..., model=..., client=..., backoff_seconds=...)`` is
retained so existing tests and direct-instantiation call sites that target
the Anthropic streaming path continue to work unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.rag.exceptions import (
    LLMAPIError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
)

logger = logging.getLogger(__name__)


_DEFAULT_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


# ─────────────────────────────────────────
# Anthropic provider — streamed + retry
# ─────────────────────────────────────────


class _AnthropicProvider:
    """Async wrapper around the Anthropic SDK with retry and token tracking."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        client: Any | None,
        backoff_seconds: tuple[float, ...],
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
        last_exc: LLMError | None = None
        attempts = len(self.backoff_seconds) + 1

        for attempt in range(1, attempts + 1):
            try:
                text, usage = await self._stream_once(system_prompt, user_prompt)
                logger.info(
                    "llm_call_success",
                    extra={
                        "provider": "anthropic",
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


# ─────────────────────────────────────────
# Gemini provider
# ─────────────────────────────────────────


class _GeminiProvider:
    """Google Gemini provider — uses the synchronous SDK off the event loop."""

    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required to call the LLM.")
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:
            raise LLMError(
                "The 'google-generativeai' package is required to call Gemini. "
                "Install with: pip install google-generativeai"
            ) from exc
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model_name

    @staticmethod
    def _classify(exc: BaseException) -> LLMError:
        msg = str(exc).lower()
        rate_signals = ("quota", "rate limit", "rate_limit", "ratelimit",
                        "429", "resource_exhausted", "too many requests")
        if any(s in msg for s in rate_signals):
            return LLMRateLimitError(str(exc))
        auth_signals = ("api key", "api_key", "authentication", "unauthorized",
                        "permission denied", "permission_denied", "401", "403")
        if any(s in msg for s in auth_signals):
            return LLMAPIError(f"Invalid Gemini API key or permission denied: {exc}")
        conn_signals = ("connection", "timeout", "unavailable", "deadline exceeded")
        if any(s in msg for s in conn_signals):
            return LLMConnectionError(str(exc))
        return LLMAPIError(str(exc))

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            model = self._genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system_prompt,
            )
            response = await asyncio.to_thread(model.generate_content, user_prompt)
            text = response.text or ""
            usage_meta = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0
            output_tokens = getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0
            logger.info(
                "llm_call_success",
                extra={
                    "provider": "gemini",
                    "model": self._model_name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
            return text
        except Exception as raw_exc:
            mapped = self._classify(raw_exc)
            logger.error("llm_call_failed: %s", mapped)
            raise mapped from raw_exc


# ─────────────────────────────────────────
# Unified client
# ─────────────────────────────────────────


class LLMClient:
    """Provider-agnostic LLM client.

    Construction:

    * ``LLMClient()`` — read ``settings.LLM_PROVIDER`` and route to the
      matching backend. This is the production path.
    * ``LLMClient(api_key=..., model=..., client=..., backoff_seconds=...)``
      — legacy direct-Anthropic construction. Preserved for existing tests
      and call sites; ignores ``LLM_PROVIDER``.
    """

    _SENTINEL: Any = object()

    def __init__(
        self,
        api_key: Any = _SENTINEL,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
        client: Any = None,
        backoff_seconds: tuple[float, ...] = _DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        explicit = api_key is not LLMClient._SENTINEL or client is not None

        if explicit:
            # Legacy Anthropic-direct path — preserves existing tests.
            self._provider: _AnthropicProvider | _GeminiProvider = _AnthropicProvider(
                api_key=api_key if api_key is not LLMClient._SENTINEL else "",
                model=model,
                max_tokens=max_tokens,
                client=client,
                backoff_seconds=backoff_seconds,
            )
            # Expose attributes the legacy tests/callers expect.
            self.api_key = self._provider.api_key  # type: ignore[attr-defined]
            self.model = self._provider.model  # type: ignore[attr-defined]
            self.max_tokens = self._provider.max_tokens  # type: ignore[attr-defined]
            self.backoff_seconds = self._provider.backoff_seconds  # type: ignore[attr-defined]
            self._client = self._provider._client  # type: ignore[attr-defined]
            return

        # No-arg path: choose provider from settings.
        provider_name = (settings.LLM_PROVIDER or "anthropic").lower().strip()

        if provider_name == "gemini":
            if not settings.GEMINI_API_KEY:
                raise ValueError(
                    "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set in .env"
                )
            logger.info("LLM provider: Google Gemini (%s)", settings.GEMINI_MODEL)
            self._provider = _GeminiProvider(
                api_key=settings.GEMINI_API_KEY,
                model_name=settings.GEMINI_MODEL,
            )
        elif provider_name == "anthropic":
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError(
                    "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set in .env"
                )
            logger.info("LLM provider: Anthropic Claude (%s)", settings.LLM_MODEL)
            self._provider = _AnthropicProvider(
                api_key=settings.ANTHROPIC_API_KEY,
                model=settings.LLM_MODEL,
                max_tokens=max_tokens,
                client=None,
                backoff_seconds=backoff_seconds,
            )
        else:
            raise ValueError(
                f"Unknown LLM_PROVIDER='{provider_name}'. "
                "Valid options: 'anthropic', 'gemini'"
            )

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send the prompts to the active provider and return assembled text."""
        return await self._provider.complete(system_prompt, user_prompt)

    @property
    def provider_name(self) -> str:
        """Name of the active provider: ``"anthropic"`` or ``"gemini"``."""
        return "gemini" if isinstance(self._provider, _GeminiProvider) else "anthropic"

    # Legacy method preserved for direct Anthropic-streaming callers/tests.
    async def _stream_once(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[str, dict[str, int]]:
        if not isinstance(self._provider, _AnthropicProvider):
            raise LLMAPIError("_stream_once is only available on the Anthropic provider")
        return await self._provider._stream_once(system_prompt, user_prompt)
