"""Smoke tests for vector DB clients.

LocalVectorDBClient: exercises real in-process logic against a temp file.
PineconeVectorDBClient: exercises all methods against a mock Pinecone SDK.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.vector_db import LocalVectorDBClient, PineconeVectorDBClient, get_vector_db_client


# ─────────────────────────── LocalVectorDBClient ─────────────────────────────


@pytest.fixture
def local_client(tmp_path):
    return LocalVectorDBClient(storage_path=tmp_path / "vectors.json")


@pytest.mark.asyncio
async def test_local_upsert_returns_count(local_client):
    records = [
        {"id": "a", "vector": [1.0, 0.0], "metadata": {"content": "alpha"}},
        {"id": "b", "vector": [0.0, 1.0], "metadata": {"content": "beta"}},
    ]
    count = await local_client.upsert(records)
    assert count == 2


@pytest.mark.asyncio
async def test_local_upsert_is_idempotent(local_client):
    record = {"id": "a", "vector": [1.0, 0.0], "metadata": {"x": 1}}
    await local_client.upsert([record])
    await local_client.upsert([{"id": "a", "vector": [1.0, 0.0], "metadata": {"x": 2}}])
    results = await local_client.query([1.0, 0.0], top_k=1)
    assert results[0]["metadata"]["x"] == 2


@pytest.mark.asyncio
async def test_local_query_top_k(local_client):
    await local_client.upsert([
        {"id": "a", "vector": [1.0, 0.0], "metadata": {"content": "a"}},
        {"id": "b", "vector": [0.9, 0.1], "metadata": {"content": "b"}},
        {"id": "c", "vector": [0.0, 1.0], "metadata": {"content": "c"}},
    ])
    results = await local_client.query([1.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["id"] == "a"


@pytest.mark.asyncio
async def test_local_query_filters(local_client):
    await local_client.upsert([
        {"id": "a", "vector": [1.0, 0.0], "metadata": {"org": "x", "content": "a"}},
        {"id": "b", "vector": [1.0, 0.0], "metadata": {"org": "y", "content": "b"}},
    ])
    results = await local_client.query([1.0, 0.0], top_k=5, filters={"org": "x"})
    assert all(r["metadata"]["org"] == "x" for r in results)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_local_delete_returns_count(local_client):
    await local_client.upsert([
        {"id": "a", "vector": [1.0, 0.0], "metadata": {}},
        {"id": "b", "vector": [0.0, 1.0], "metadata": {}},
    ])
    deleted = await local_client.delete(["a"])
    assert deleted == 1
    results = await local_client.query([1.0, 0.0], top_k=5)
    assert not any(r["id"] == "a" for r in results)


@pytest.mark.asyncio
async def test_local_query_result_shape(local_client):
    await local_client.upsert([
        {"id": "z", "vector": [1.0, 0.0], "metadata": {"content": "hello"}}
    ])
    results = await local_client.query([1.0, 0.0], top_k=1)
    assert len(results) == 1
    r = results[0]
    assert set(r.keys()) >= {"id", "score", "metadata", "content"}
    assert r["content"] == "hello"


# ─────────────────────────── PineconeVectorDBClient ──────────────────────────


def _make_mock_pinecone(has_index: bool = True):
    """Build a minimal mock of the Pinecone SDK used by PineconeVectorDBClient."""
    mock_match = MagicMock()
    mock_match.id = "vec-1"
    mock_match.score = 0.95
    mock_match.metadata = {"content": "hello", "org": "x"}

    mock_query_response = MagicMock()
    mock_query_response.matches = [mock_match]

    mock_upsert_response = MagicMock()
    mock_upsert_response.upserted_count = 1

    mock_index = MagicMock()
    mock_index.upsert = MagicMock(return_value=mock_upsert_response)
    mock_index.query = MagicMock(return_value=mock_query_response)
    mock_index.delete = MagicMock(return_value={})

    mock_pc = MagicMock()
    mock_pc.has_index = MagicMock(return_value=has_index)
    mock_pc.create_index = MagicMock()
    mock_pc.Index = MagicMock(return_value=mock_index)

    mock_serverless_spec = MagicMock()

    return mock_pc, mock_index, mock_serverless_spec


@pytest.fixture
def pinecone_client():
    """PineconeVectorDBClient with the Pinecone SDK fully mocked out."""
    mock_pc, mock_index, mock_spec = _make_mock_pinecone(has_index=True)

    with patch("app.db.vector_db.settings") as mock_settings, \
         patch("pinecone.Pinecone", return_value=mock_pc), \
         patch("pinecone.ServerlessSpec", return_value=mock_spec):
        mock_settings.PINECONE_API_KEY = "test-key"
        mock_settings.PINECONE_INDEX_NAME = "test-index"
        mock_settings.PINECONE_CLOUD = "aws"
        mock_settings.PINECONE_REGION = "us-east-1"
        mock_settings.PINECONE_DIMENSION = 0

        client = PineconeVectorDBClient()
        client._pc = mock_pc
        client._index = mock_index  # pre-wire so _ensure_index is skipped
        yield client, mock_pc, mock_index


@pytest.mark.asyncio
async def test_pinecone_upsert_returns_count(pinecone_client):
    client, _, mock_index = pinecone_client
    records = [{"id": "vec-1", "vector": [0.1] * 384, "metadata": {"content": "hi"}}]
    count = await client.upsert(records)
    assert count == 1
    mock_index.upsert.assert_called_once()
    call_kwargs = mock_index.upsert.call_args
    sent = call_kwargs.kwargs.get("vectors") or call_kwargs.args[0]
    assert sent[0]["id"] == "vec-1"
    assert "values" in sent[0]
    assert "metadata" in sent[0]


@pytest.mark.asyncio
async def test_pinecone_upsert_batches_large_payloads(pinecone_client):
    client, _, mock_index = pinecone_client
    mock_index.upsert.return_value = MagicMock(upserted_count=100)
    records = [
        {"id": f"v{i}", "vector": [float(i)] * 4, "metadata": {}}
        for i in range(250)
    ]
    total = await client.upsert(records)
    assert mock_index.upsert.call_count == 3  # ceil(250/100)
    assert total == 300  # 100+100+100 from mock


@pytest.mark.asyncio
async def test_pinecone_query_returns_correct_shape(pinecone_client):
    client, _, _ = pinecone_client
    results = await client.query([0.1] * 384, top_k=5)
    assert len(results) == 1
    r = results[0]
    assert r["id"] == "vec-1"
    assert r["score"] == 0.95
    assert r["content"] == "hello"
    assert set(r.keys()) >= {"id", "score", "metadata", "content"}


@pytest.mark.asyncio
async def test_pinecone_query_passes_filter(pinecone_client):
    client, _, mock_index = pinecone_client
    await client.query([0.1] * 4, top_k=3, filters={"org": "x"})
    call_kwargs = mock_index.query.call_args.kwargs
    assert call_kwargs.get("filter") == {"org": "x"}
    assert call_kwargs.get("top_k") == 3
    assert call_kwargs.get("include_metadata") is True


@pytest.mark.asyncio
async def test_pinecone_query_no_filter(pinecone_client):
    client, _, mock_index = pinecone_client
    await client.query([0.1] * 4, top_k=5)
    call_kwargs = mock_index.query.call_args.kwargs
    assert call_kwargs.get("filter") is None


@pytest.mark.asyncio
async def test_pinecone_delete_returns_id_count(pinecone_client):
    client, _, mock_index = pinecone_client
    deleted = await client.delete(["vec-1", "vec-2"])
    assert deleted == 2
    call_kwargs = mock_index.delete.call_args.kwargs
    assert set(call_kwargs.get("ids", [])) == {"vec-1", "vec-2"}


@pytest.mark.asyncio
async def test_pinecone_delete_empty_noop(pinecone_client):
    client, _, mock_index = pinecone_client
    deleted = await client.delete([])
    assert deleted == 0
    mock_index.delete.assert_not_called()


@pytest.mark.asyncio
async def test_pinecone_upsert_empty_noop(pinecone_client):
    client, _, mock_index = pinecone_client
    count = await client.upsert([])
    assert count == 0
    mock_index.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_pinecone_creates_index_when_missing():
    """When the index doesn't exist yet, upsert should call create_index."""
    mock_pc, mock_index, mock_spec_inst = _make_mock_pinecone(has_index=False)
    mock_pc.has_index.side_effect = [False, True]  # missing on first check, present after create

    with patch("app.db.vector_db.settings") as mock_settings, \
         patch("pinecone.Pinecone", return_value=mock_pc), \
         patch("pinecone.ServerlessSpec", return_value=mock_spec_inst):
        mock_settings.PINECONE_API_KEY = "test-key"
        mock_settings.PINECONE_INDEX_NAME = "test-index"
        mock_settings.PINECONE_CLOUD = "aws"
        mock_settings.PINECONE_REGION = "us-east-1"
        mock_settings.PINECONE_DIMENSION = 0

        client = PineconeVectorDBClient()
        client._pc = mock_pc
        mock_index.upsert.return_value = MagicMock(upserted_count=1)
        mock_pc.Index.return_value = mock_index

        await client.upsert([{"id": "v1", "vector": [1.0, 0.0], "metadata": {}}])

    mock_pc.create_index.assert_called_once()
    call_kwargs = mock_pc.create_index.call_args.kwargs
    assert call_kwargs["name"] == "test-index"
    assert call_kwargs["dimension"] == 2
    assert call_kwargs["metric"] == "cosine"


# ─────────────────────────── Factory ─────────────────────────────────────────


def test_factory_returns_pinecone_when_provider_is_pinecone():
    import app.db.vector_db as vdb

    original_singleton = vdb._singleton
    vdb._singleton = None
    try:
        with patch("app.db.vector_db.settings") as mock_settings, \
             patch("app.db.vector_db.PineconeVectorDBClient") as MockPinecone:
            mock_settings.VECTOR_DB_PROVIDER = "pinecone"
            mock_settings.PINECONE_INDEX_NAME = "test-index"
            MockPinecone.return_value = MagicMock()
            client = get_vector_db_client()
            assert isinstance(client, MagicMock)
            MockPinecone.assert_called_once()
    finally:
        vdb._singleton = original_singleton


def test_factory_returns_local_when_provider_is_local(tmp_path):
    import app.db.vector_db as vdb

    original_singleton = vdb._singleton
    vdb._singleton = None
    try:
        with patch("app.db.vector_db.settings") as mock_settings, \
             patch.dict("os.environ", {"VECTOR_DB_LOCAL_PATH": str(tmp_path / "v.json")}):
            mock_settings.VECTOR_DB_PROVIDER = "local"
            client = get_vector_db_client()
            assert isinstance(client, LocalVectorDBClient)
    finally:
        vdb._singleton = original_singleton
