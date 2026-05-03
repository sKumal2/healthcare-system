"""Tests for the async DocumentService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.document_service import DocumentService


@pytest.fixture
def mock_vector_db():
    db = MagicMock()
    db.upsert = AsyncMock(return_value=0)
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def service(mock_vector_db):
    svc = DocumentService(vector_db=mock_vector_db)
    # Avoid loading the real sentence-transformers model during tests.
    svc._generate_embedding = AsyncMock(return_value=[0.1] * 384)
    return svc


# -------------------------- chunk splitter --------------------------

def test_split_into_chunks_respects_sentence_boundaries(service):
    text = (
        "Diabetes is a chronic condition. It affects blood sugar levels. "
        "Treatment includes insulin therapy. Patients need regular monitoring."
    )
    chunks = service._split_into_chunks(text, chunk_size=60)
    for chunk in chunks:
        assert chunk.strip().endswith((".", "!", "?"))


def test_split_into_chunks_handles_text_without_terminator(service):
    text = "no terminator at all"
    chunks = service._split_into_chunks(text)
    assert chunks == [text]


# -------------------------- process_and_store --------------------------

@pytest.mark.asyncio
async def test_process_and_store_calls_vector_db_upsert(service, mock_vector_db):
    result = await service.process_and_store(
        document_text="Patient X has diabetes. Treatment is insulin.",
        metadata={"document_id": "doc-1", "title": "Notes"},
        organization_id="org-A",
        uploaded_by="user-1",
    )
    mock_vector_db.upsert.assert_awaited_once()
    payload = mock_vector_db.upsert.await_args.args[0]
    assert all(set(rec.keys()) >= {"id", "vector", "metadata"} for rec in payload)
    assert all(rec["metadata"]["organization_id"] == "org-A" for rec in payload)
    assert result["document_id"] == "doc-1"
    assert result["chunks_stored"] == len(payload)


# -------------------------- search + org isolation --------------------------

@pytest.mark.asyncio
async def test_search_passes_org_filter_to_vector_db(service, mock_vector_db):
    await service.search(query_text="symptoms?", organization_id="org-A", top_k=3)
    mock_vector_db.query.assert_awaited_once()
    kwargs = mock_vector_db.query.await_args.kwargs
    assert kwargs["filters"] == {"organization_id": "org-A"}
    assert kwargs["top_k"] == 3


@pytest.mark.asyncio
async def test_search_org_isolation_does_not_return_other_orgs(mock_vector_db):
    """If the underlying vector DB respects filters, org-B docs never come back to org-A."""
    mock_vector_db.query = AsyncMock(return_value=[])
    svc = DocumentService(vector_db=mock_vector_db)
    svc._generate_embedding = AsyncMock(return_value=[0.1] * 384)

    results = await svc.search(query_text="x", organization_id="org-A")
    assert results == []
    assert mock_vector_db.query.await_args.kwargs["filters"]["organization_id"] == "org-A"


# -------------------------- _save_file --------------------------

@pytest.mark.asyncio
async def test_save_file_writes_local_when_no_aws(service, tmp_path):
    service.storage_dir = tmp_path
    with patch("app.services.document_service.settings") as mock_settings:
        mock_settings.AWS_ACCESS_KEY_ID = ""
        mock_settings.S3_BUCKET_NAME = ""
        path = await service._save_file("note.txt", b"hello")
    assert path.startswith("storage/uploads/")
    assert (tmp_path / "note.txt").read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_save_file_uses_s3_when_credentials_present(service):
    fake_s3 = AsyncMock()
    fake_s3.put_object = AsyncMock()

    class FakeContextManager:
        async def __aenter__(self_inner):
            return fake_s3

        async def __aexit__(self_inner, *args):
            return False

    fake_session = MagicMock()
    fake_session.client = MagicMock(return_value=FakeContextManager())

    with patch("app.services.document_service.settings") as mock_settings, \
         patch.dict("sys.modules", {"aioboto3": MagicMock(Session=lambda: fake_session)}):
        mock_settings.AWS_ACCESS_KEY_ID = "AKIA..."
        mock_settings.S3_BUCKET_NAME = "test-bucket"
        mock_settings.AWS_REGION = "us-east-1"
        path = await service._save_file("note.txt", b"hello")

    assert path.startswith("s3://test-bucket/uploads/")
    fake_s3.put_object.assert_awaited_once()
