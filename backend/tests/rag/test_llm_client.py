"""Tests for app.rag.llm_client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.rag.exceptions import (
    LLMAPIError,
    LLMConnectionError,
    LLMRateLimitError,
)
from app.rag.llm_client import LLMClient


class _StreamCM:
    """Async-context-manager stub mimicking the Anthropic streaming interface."""

    def __init__(self, text_chunks: list[str], usage_in: int = 10, usage_out: int = 20):
        self.text_chunks = text_chunks
        self.usage_in = usage_in
        self.usage_out = usage_out

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @property
    def text_stream(self):
        async def gen():
            for c in self.text_chunks:
                yield c
        return gen()

    async def get_final_message(self):
        msg = MagicMock()
        msg.usage.input_tokens = self.usage_in
        msg.usage.output_tokens = self.usage_out
        return msg


class _Messages:
    def __init__(self, stream_factory):
        self._factory = stream_factory

    def stream(self, **_kwargs):
        return self._factory()


class _ClientStub:
    def __init__(self, stream_factory):
        self.messages = _Messages(stream_factory)


def _make_client(stream_factory) -> LLMClient:
    """Build an ``LLMClient`` with a fake Anthropic client and tiny backoff."""
    return LLMClient(
        api_key="test",
        client=_ClientStub(stream_factory),
        backoff_seconds=(0.0, 0.0, 0.0),
    )


class TestLLMClientHappyPath:
    @pytest.mark.asyncio
    async def test_complete_assembles_streamed_text(self) -> None:
        client = _make_client(lambda: _StreamCM(["Hello, ", "world"]))
        out = await client.complete("system", "user")
        assert out == "Hello, world"


class TestLLMClientRetries:
    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_then_succeeds(self) -> None:
        anthropic = pytest.importorskip("anthropic")
        attempts = {"n": 0}

        def factory():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise anthropic.RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429),
                    body=None,
                )
            return _StreamCM(["ok"])

        client = _make_client(factory)
        out = await client.complete("s", "u")
        assert out == "ok"
        assert attempts["n"] == 2

    @pytest.mark.asyncio
    async def test_rate_limit_exhausts_retries(self) -> None:
        anthropic = pytest.importorskip("anthropic")

        def factory():
            raise anthropic.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429),
                body=None,
            )

        client = _make_client(factory)
        with pytest.raises(LLMRateLimitError):
            await client.complete("s", "u")

    @pytest.mark.asyncio
    async def test_connection_error_retries(self) -> None:
        anthropic = pytest.importorskip("anthropic")
        attempts = {"n": 0}

        def factory():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise anthropic.APIConnectionError(request=MagicMock())
            return _StreamCM(["recovered"])

        client = _make_client(factory)
        out = await client.complete("s", "u")
        assert out == "recovered"

    @pytest.mark.asyncio
    async def test_generic_api_error_does_not_retry(self) -> None:
        # Use a plain RuntimeError -> mapped to LLMAPIError (no retry path)
        def factory():
            raise RuntimeError("boom")

        client = _make_client(factory)
        with pytest.raises(LLMAPIError):
            await client.complete("s", "u")


class TestLLMClientInit:
    def test_requires_api_key_or_client(self) -> None:
        with pytest.raises(ValueError):
            LLMClient(api_key="", client=None)
