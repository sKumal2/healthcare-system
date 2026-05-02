"""Source validation: only allow chunks from a configured allowlist."""

from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import urlparse

from app.rag.exceptions import InsufficientSourcesError
from app.rag.models import RankedChunk

logger = logging.getLogger(__name__)


DEFAULT_TRUSTED_DOMAINS: tuple[str, ...] = (
    "cdc.gov",
    "who.int",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "fda.gov",
    "nih.gov",
    "mayoclinic.org",
    "clevelandclinic.org",
    "medlineplus.gov",
)


def _normalize(domain: str) -> str:
    return domain.strip().lower().lstrip(".")


def _host(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().lstrip(".")


class SourceValidator:
    """Filter chunks down to those from authoritative healthcare sources."""

    def __init__(
        self,
        trusted_domains: Iterable[str] = DEFAULT_TRUSTED_DOMAINS,
        min_valid_sources: int = 2,
    ) -> None:
        self.trusted_domains: set[str] = {_normalize(d) for d in trusted_domains if d}
        if min_valid_sources < 1:
            raise ValueError("min_valid_sources must be >= 1")
        self.min_valid_sources = min_valid_sources

    def is_trusted(self, url: str) -> bool:
        """Return True if ``url`` is hosted on an allowlisted domain.

        Subdomains are accepted (e.g. ``foo.cdc.gov`` matches ``cdc.gov``).
        """
        host = _host(url)
        if not host:
            return False
        if host in self.trusted_domains:
            return True
        return any(host.endswith("." + d) for d in self.trusted_domains)

    def validate(self, chunks: list[RankedChunk]) -> list[RankedChunk]:
        """Return only chunks whose ``source_url`` is on the allowlist.

        Raises :class:`InsufficientSourcesError` when fewer than
        :attr:`min_valid_sources` chunks pass — this prevents the LLM from
        being asked to answer with weak grounding.
        """
        kept: list[RankedChunk] = []
        for chunk in chunks:
            if self.is_trusted(chunk.source_url):
                kept.append(chunk)
            else:
                logger.warning(
                    "Filtered untrusted source: chunk_id=%s url=%s",
                    chunk.chunk_id,
                    chunk.source_url,
                )
        if len(kept) < self.min_valid_sources:
            raise InsufficientSourcesError(
                valid_count=len(kept),
                required_count=self.min_valid_sources,
            )
        return kept
