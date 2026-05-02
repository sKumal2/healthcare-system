"""Tests for app.rag.source_validator."""

from __future__ import annotations

import pytest

from app.rag.exceptions import InsufficientSourcesError
from app.rag.models import RankedChunk
from app.rag.source_validator import SourceValidator


def _ranked(cid: str, url: str) -> RankedChunk:
    return RankedChunk(
        chunk_id=cid, content="x", source_url=url, source_name="Src",
        score=0.5, metadata={}, rank=1, relevance_score=0.5,
    )


class TestIsTrusted:
    def test_exact_match(self) -> None:
        v = SourceValidator()
        assert v.is_trusted("https://cdc.gov/a")

    def test_subdomain_match(self) -> None:
        v = SourceValidator()
        assert v.is_trusted("https://www.cdc.gov/a")

    def test_unknown_domain(self) -> None:
        v = SourceValidator()
        assert not v.is_trusted("https://example.com/a")

    def test_malformed_url(self) -> None:
        v = SourceValidator()
        assert not v.is_trusted("not-a-url")


class TestValidate:
    def test_filters_untrusted(self) -> None:
        v = SourceValidator(min_valid_sources=2)
        chunks = [
            _ranked("a", "https://cdc.gov/a"),
            _ranked("b", "https://who.int/b"),
            _ranked("c", "https://random.com/c"),
        ]
        kept = v.validate(chunks)
        assert {c.chunk_id for c in kept} == {"a", "b"}

    def test_raises_when_insufficient(self) -> None:
        v = SourceValidator(min_valid_sources=3)
        chunks = [_ranked("a", "https://cdc.gov/a"), _ranked("b", "https://untrusted.com/b")]
        with pytest.raises(InsufficientSourcesError) as exc_info:
            v.validate(chunks)
        assert exc_info.value.valid_count == 1
        assert exc_info.value.required_count == 3

    def test_all_untrusted_raises(self) -> None:
        v = SourceValidator(min_valid_sources=1)
        with pytest.raises(InsufficientSourcesError):
            v.validate([_ranked("a", "https://random.com/a")])

    def test_custom_allowlist(self) -> None:
        v = SourceValidator(trusted_domains=["mysource.gov"], min_valid_sources=1)
        kept = v.validate([_ranked("a", "https://mysource.gov/x")])
        assert len(kept) == 1

    def test_logs_warning_for_filtered(self, caplog) -> None:
        v = SourceValidator(min_valid_sources=1)
        chunks = [
            _ranked("a", "https://cdc.gov/a"),
            _ranked("b", "https://untrusted.com/b"),
        ]
        v.validate(chunks)
        assert any(
            "Filtered untrusted source" in rec.getMessage() for rec in caplog.records
        )

    def test_invalid_min_raises(self) -> None:
        with pytest.raises(ValueError):
            SourceValidator(min_valid_sources=0)
