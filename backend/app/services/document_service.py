"""Document processing and retrieval service.

Embeds chunks with sentence-transformers, persists vectors via
``VectorDBClient``, and stores raw bytes either in S3 (when AWS credentials
are configured) or on local disk for dev. All public methods are async.

Note on embeddings: ``sentence-transformers`` runs synchronously on CPU.
In production this should be replaced with an async embedding API call
(e.g. OpenAI ``text-embedding-3-small``) so model encoding does not block
the event loop. For now we offload via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.vector_db import VectorDBClient

UTC = timezone.utc

logger = logging.getLogger(__name__)


_embedding_model = None
EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2 default


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


class DocumentMetadata(BaseModel):
    """Metadata for document chunks."""

    document_id: str
    title: str
    chunk_index: int
    source_url: Optional[str] = None
    author: Optional[str] = None
    file_path: Optional[str] = None
    organization_id: Optional[str] = None
    uploaded_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentChunk(BaseModel):
    """Core document chunk schema."""

    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: DocumentMetadata


class DocumentSearchResult(BaseModel):
    """Search result returned from document search."""

    id: str
    content: str
    similarity_score: float
    metadata: DocumentMetadata


class DocumentService:
    """Service layer for document processing and retrieval."""

    def __init__(self, vector_db: VectorDBClient):
        self.vector_db = vector_db
        self.storage_dir = Path(__file__).parent.parent / "storage" / "uploads"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ---------- internal helpers ----------

    def _generate_chunk_id(self, document_id: str, chunk_index: int) -> str:
        hash_input = f"{document_id}_{chunk_index}_{datetime.now(UTC).isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _generate_embedding(self, text: str) -> List[float]:
        """Encode ``text`` to an embedding vector.

        Encoding is CPU-bound and synchronous, so it runs in a thread to
        avoid blocking the event loop. In production, swap this for an
        async embedding API call.
        """

        def _encode() -> List[float]:
            model = _get_embedding_model()
            return model.encode(text).tolist()

        return await asyncio.to_thread(_encode)

    def _split_into_chunks(self, text: str, chunk_size: int = 500) -> List[str]:
        """Split text into chunks on sentence boundaries first."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_length = 0

        for sentence in sentences:
            if current_length + len(sentence) > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_length = len(sentence)
            else:
                current_chunk.append(sentence)
                current_length += len(sentence) + 1

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks if chunks else [text]

    async def _save_file(self, filename: str, file_content: bytes) -> str:
        """Persist ``file_content``. Uses S3 when AWS credentials are
        configured, otherwise writes to the local upload directory.
        """
        if settings.AWS_ACCESS_KEY_ID and settings.S3_BUCKET_NAME:
            import aioboto3  # type: ignore

            session = aioboto3.Session()
            async with session.client("s3", region_name=settings.AWS_REGION) as s3:
                key = f"uploads/{uuid.uuid4().hex}/{filename}"
                await s3.put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=key,
                    Body=file_content,
                    ContentType="application/octet-stream",
                )
                return f"s3://{settings.S3_BUCKET_NAME}/{key}"

        file_path = self.storage_dir / filename
        if file_path.exists():
            name_parts = filename.rsplit(".", 1)
            if len(name_parts) == 2:
                base, ext = name_parts
                filename = f"{base}_{uuid.uuid4().hex[:8]}.{ext}"
            else:
                filename = f"{filename}_{uuid.uuid4().hex[:8]}"
            file_path = self.storage_dir / filename

        import aiofiles  # type: ignore

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)
        return f"storage/uploads/{filename}"

    # ---------- public API ----------

    async def process_and_store(
        self,
        document_text: str,
        metadata: dict,
        organization_id: str,
        uploaded_by: str,
        file_content: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> dict:
        """Chunk, embed, and persist a document.

        ``organization_id`` and ``uploaded_by`` are stored on every chunk
        so the search path can enforce per-org isolation.
        """
        document_id = metadata.get("document_id") or uuid.uuid4().hex
        file_path = None

        if file_content is not None and filename is not None:
            file_path = await self._save_file(filename, file_content)

        chunks = self._split_into_chunks(document_text)
        stored_chunks: List[str] = []
        records: List[dict[str, Any]] = []

        for chunk_index, chunk_text in enumerate(chunks):
            chunk_id = self._generate_chunk_id(document_id, chunk_index)
            embedding = await self._generate_embedding(chunk_text)

            chunk_metadata = DocumentMetadata(
                document_id=document_id,
                title=metadata.get("title", "Untitled"),
                chunk_index=chunk_index,
                source_url=metadata.get("source_url"),
                author=metadata.get("author"),
                file_path=file_path,
                organization_id=organization_id,
                uploaded_by=uploaded_by,
            )

            records.append(
                {
                    "id": chunk_id,
                    "vector": embedding,
                    "metadata": {
                        **chunk_metadata.model_dump(mode="json"),
                        "content": chunk_text,
                    },
                }
            )
            stored_chunks.append(chunk_id)

        await self.vector_db.upsert(records)

        return {
            "document_id": document_id,
            "chunks_stored": len(stored_chunks),
            "chunk_ids": stored_chunks,
            "file_path": file_path,
        }

    async def search(
        self,
        query_text: str,
        organization_id: str,
        top_k: int = 5,
    ) -> List[DocumentSearchResult]:
        """Search for chunks, optionally restricted to ``organization_id``.

        When ``organization_id`` is empty, no filter is applied so the search
        runs against all vectors. This avoids zero-result responses when
        callers haven't resolved a tenant yet.
        """
        query_embedding = await self._generate_embedding(query_text)
        filters = {"organization_id": organization_id} if organization_id else None
        raw_results = await self.vector_db.query(
            query_embedding,
            top_k=top_k,
            filters=filters,
        )

        results: List[DocumentSearchResult] = []
        for item in raw_results:
            md = item.get("metadata", {})
            results.append(
                DocumentSearchResult(
                    id=item["id"],
                    content=item.get("content") or md.get("content", ""),
                    similarity_score=float(item.get("score", 0.0)),
                    metadata=DocumentMetadata(
                        document_id=md.get("document_id", ""),
                        title=md.get("title", "Untitled"),
                        chunk_index=md.get("chunk_index", 0),
                        source_url=md.get("source_url"),
                        author=md.get("author"),
                        file_path=md.get("file_path"),
                        organization_id=md.get("organization_id"),
                        uploaded_by=md.get("uploaded_by"),
                    ),
                )
            )
        return results
