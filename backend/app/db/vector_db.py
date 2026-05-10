"""Vector DB client used by the document service.

The retriever already defines a ``VectorDBClient`` *protocol* in
``app/rag/retriever.py``. This module provides:

* a concrete ``VectorDBClient`` class with ``upsert`` + ``query`` methods
  that the document service calls,
* a ``LocalVectorDBClient`` fallback that persists vectors to disk so the
  system works in local dev without Pinecone/Weaviate,
* a ``PineconeVectorDBClient`` backed by the Pinecone serverless API,
* a FastAPI dependency provider ``get_vector_db_client``.

Set ``VECTOR_DB_PROVIDER=pinecone`` (the default) to use Pinecone.
Set ``VECTOR_DB_PROVIDER=local`` to use the file-backed store.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from itertools import islice
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


def _batched(iterable: Iterable[Any], n: int) -> Iterable[list[Any]]:
    """Yield successive n-sized chunks from iterable."""
    it = iter(iterable)
    while True:
        batch = list(islice(it, n))
        if not batch:
            break
        yield batch


class PineconeVectorDBClient:
    """Pinecone-backed vector store.

    Reads configuration from environment / settings:
      - PINECONE_API_KEY    — required
      - PINECONE_INDEX_NAME — default "healthcare-rag"
      - PINECONE_CLOUD      — default "aws"
      - PINECONE_REGION     — default "us-east-1"
      - PINECONE_DIMENSION  — inferred from first upsert when not set
    """

    _BATCH_SIZE = 100

    def __init__(self) -> None:
        from pinecone import Pinecone, ServerlessSpec  # noqa: PLC0415

        self._ServerlessSpec = ServerlessSpec
        self._api_key = settings.PINECONE_API_KEY
        self._index_name = settings.PINECONE_INDEX_NAME
        self._cloud = settings.PINECONE_CLOUD
        self._region = settings.PINECONE_REGION
        self._dimension: int | None = (
            settings.PINECONE_DIMENSION if settings.PINECONE_DIMENSION > 0 else None
        )
        self._pc = Pinecone(api_key=self._api_key)
        self._index = None  # lazy — created on first use

    def _ensure_index(self, dimension: int) -> None:
        """Create the Pinecone index if it doesn't already exist."""
        if not self._pc.has_index(self._index_name):
            logger.info(
                "Creating Pinecone index '%s' (dim=%d, cloud=%s, region=%s)",
                self._index_name,
                dimension,
                self._cloud,
                self._region,
            )
            self._pc.create_index(
                name=self._index_name,
                dimension=dimension,
                metric="cosine",
                spec=self._ServerlessSpec(cloud=self._cloud, region=self._region),
            )
        if self._index is None:
            self._index = self._pc.Index(self._index_name)

    def _get_index(self) -> Any:
        if self._index is None:
            if not self._pc.has_index(self._index_name):
                raise RuntimeError(
                    f"Pinecone index '{self._index_name}' does not exist and no vectors "
                    "have been upserted yet. Call upsert() first or set PINECONE_DIMENSION."
                )
            self._index = self._pc.Index(self._index_name)
        return self._index

    async def upsert(self, vectors: Iterable[dict[str, Any]]) -> int:
        """Insert/replace vector records.

        Each record must have ``id``, ``vector`` (list[float]), and ``metadata``.
        Returns the number of records written.
        """
        records = list(vectors)
        if not records:
            return 0

        dimension = self._dimension or len(records[0]["vector"])
        await asyncio.get_running_loop().run_in_executor(
            None, self._ensure_index, dimension
        )
        index = self._get_index()

        # pinecone_vectors = [
        #     {
        #         "id": r["id"],
        #         "values": list(r["vector"]),
        #         "metadata": dict(r.get("metadata", {})),
        #     }
        #     for r in records
        # ]
        #updated the pinecone_vector method to handle null value during uploads
        pinecone_vectors = [
            {
                "id": r["id"],
                "values": list(r["vector"]),
                "metadata": {
                    k: v for k, v in r.get("metadata", {}).items()
                    if v is not None
                },
            }
            for r in records
        ]

        total = 0
        for batch in _batched(pinecone_vectors, self._BATCH_SIZE):
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda b=batch: index.upsert(vectors=b),
            )
            total += response.upserted_count
        return total

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k cosine-similar records, optionally filtered by metadata.

        Each result is ``{"id", "score", "metadata", "content"}``.
        Returns an empty list when the index has not been created yet.
        """
        if self._index is None and not self._pc.has_index(self._index_name):
            logger.debug(
                "Pinecone index '%s' does not exist yet; returning empty results.",
                self._index_name,
            )
            return []

        index = self._get_index()
        pinecone_filter = filters if filters else None

        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: index.query(
                vector=vector,
                top_k=top_k,
                filter=pinecone_filter,
                include_metadata=True,
            ),
        )

        return [
            {
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata or {},
                "content": (match.metadata or {}).get("content", ""),
            }
            for match in response.matches
        ]

    async def delete(self, ids: Iterable[str]) -> int:
        """Delete records by ID. Returns the number of IDs submitted for deletion."""
        ids_list = list(ids)
        if not ids_list:
            return 0
        index = self._get_index()
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: index.delete(ids=ids_list),
        )
        return len(ids_list)


VectorDBClient = LocalVectorDBClient


_singleton: LocalVectorDBClient | PineconeVectorDBClient | None = None


def get_vector_db_client() -> LocalVectorDBClient | PineconeVectorDBClient:
    """FastAPI dependency provider — returns a process-wide singleton.

    Routes to PineconeVectorDBClient when VECTOR_DB_PROVIDER=pinecone (default),
    or LocalVectorDBClient when VECTOR_DB_PROVIDER=local.
    """
    global _singleton
    if _singleton is None:
        provider = (settings.VECTOR_DB_PROVIDER or "local").lower()
        if provider == "pinecone":
            logger.info("Using Pinecone vector DB (index=%s)", settings.PINECONE_INDEX_NAME)
            _singleton = PineconeVectorDBClient()
        else:
            if provider != "local":
                logger.warning(
                    "VECTOR_DB_PROVIDER=%s is not supported; falling back to local store.",
                    provider,
                )
            path = os.getenv("VECTOR_DB_LOCAL_PATH")
            _singleton = LocalVectorDBClient(storage_path=path)
    return _singleton
