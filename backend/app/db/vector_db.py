"""Vector DB client used by the document service.

The retriever already defines a ``VectorDBClient`` *protocol* in
``app/rag/retriever.py``. This module provides:

* a concrete ``VectorDBClient`` class with ``upsert`` + ``query`` methods
  that the document service calls,
* a ``LocalVectorDBClient`` fallback that persists vectors to disk so the
  system works in local dev without Pinecone/Weaviate,
* a FastAPI dependency provider ``get_vector_db_client``.

In production the same interface can be backed by Pinecone / Weaviate by
swapping the implementation.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class LocalVectorDBClient:
    """File-backed vector store. Suitable for local dev and tests only.

    Stored shape on disk is one JSON file with a list of records:

        [{"id", "vector", "metadata"}, ...]
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage"
        self.storage_path = Path(storage_path) if storage_path else base / "vectors.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load vector store: %s", exc)
            return []

    def _persist(self) -> None:
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self._records, f)

    async def upsert(self, vectors: Iterable[dict[str, Any]]) -> int:
        """Insert/replace vector records.

        Each record must have ``id``, ``vector`` (list[float]), and ``metadata``.
        Returns the number of records written.
        """
        by_id = {r["id"]: r for r in self._records}
        count = 0
        for record in vectors:
            by_id[record["id"]] = {
                "id": record["id"],
                "vector": list(record["vector"]),
                "metadata": dict(record.get("metadata", {})),
            }
            count += 1
        self._records = list(by_id.values())
        self._persist()
        return count

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k cosine-similar records, optionally filtered by metadata.

        Each result is ``{"id", "score", "metadata", "content"}``.
        """
        scored: list[tuple[float, dict[str, Any]]] = []
        for record in self._records:
            if filters and not _matches_filters(record["metadata"], filters):
                continue
            score = _cosine_similarity(vector, record["vector"])
            scored.append((score, record))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "id": rec["id"],
                "score": score,
                "metadata": rec["metadata"],
                "content": rec["metadata"].get("content", ""),
            }
            for score, rec in scored[:top_k]
        ]

    async def delete(self, ids: Iterable[str]) -> int:
        ids_set = set(ids)
        before = len(self._records)
        self._records = [r for r in self._records if r["id"] not in ids_set]
        self._persist()
        return before - len(self._records)


def _matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(metadata.get(key) == value for key, value in filters.items())


VectorDBClient = LocalVectorDBClient


_singleton: LocalVectorDBClient | None = None


def get_vector_db_client() -> VectorDBClient:
    """FastAPI dependency provider — returns a process-wide singleton.

    For Pinecone/Weaviate, this is the seam to swap the backend. The
    function signature stays sync because instantiation does not perform
    I/O until upsert/query is called.
    """
    global _singleton
    if _singleton is None:
        provider = (settings.VECTOR_DB_PROVIDER or "local").lower()
        if provider != "local":
            logger.warning(
                "VECTOR_DB_PROVIDER=%s is not yet implemented; "
                "falling back to local file-backed store.",
                provider,
            )
        path = os.getenv("VECTOR_DB_LOCAL_PATH")
        _singleton = LocalVectorDBClient(storage_path=path)
    return _singleton
