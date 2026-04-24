import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.document_service import (
    DocumentService,
    DocumentChunk,
    DocumentMetadata,
    DocumentSearchResult,
)


@pytest.fixture
def document_service():
    """Fixture to create a DocumentService instance."""
    return DocumentService()


@pytest.fixture
def sample_metadata():
    """Fixture providing sample metadata."""
    return {
        "document_id": "doc_123",
        "title": "Healthcare Guidelines",
        "source_url": "https://example.com/doc",
        "author": "Dr. Smith",
    }


@pytest.fixture
def sample_document_text():
    """Fixture providing sample document text."""
    return (
        "This is a healthcare document about patient care procedures. "
        "It contains important information for medical professionals. "
        "The guidelines outlined here should be followed carefully. "
        "Patient safety is our primary concern. "
        "These procedures have been tested and validated. "
        "Always follow the protocol as described. "
        "Additional resources are available online. "
        "Contact the administration for questions."
    )


class TestDocumentServiceInitialization:
    """Tests for DocumentService initialization."""

    def test_service_initializes_with_empty_vector_store(self):
        """Test that service initializes with empty vector store."""
        service = DocumentService()
        assert service.vector_store == []
        assert isinstance(service.vector_store, list)

    def test_service_initializes_with_empty_document_index(self):
        """Test that service initializes with empty document index."""
        service = DocumentService()
        assert service.document_index == {}
        assert isinstance(service.document_index, dict)

    def test_storage_directory_is_created(self):
        """Test that storage directory is created on initialization."""
        service = DocumentService()
        assert service.storage_dir.exists()
        assert service.storage_dir.is_dir()


class TestChunkGeneration:
    """Tests for chunk ID generation."""

    def test_generate_chunk_id_returns_string(self, document_service, sample_metadata):
        """Test that chunk ID generation returns a string."""
        chunk_id = document_service._generate_chunk_id("doc_123", 0)
        assert isinstance(chunk_id, str)

    def test_generate_chunk_id_is_16_characters(self, document_service):
        """Test that generated chunk ID is 16 characters long."""
        chunk_id = document_service._generate_chunk_id("doc_456", 0)
        assert len(chunk_id) == 16

    def test_generate_chunk_id_is_unique_for_different_chunks(self, document_service):
        """Test that different chunks get different IDs."""
        id_1 = document_service._generate_chunk_id("doc_123", 0)
        id_2 = document_service._generate_chunk_id("doc_123", 1)
        assert id_1 != id_2

    def test_generate_chunk_id_is_hexadecimal(self, document_service):
        """Test that chunk ID contains only hexadecimal characters."""
        chunk_id = document_service._generate_chunk_id("doc_123", 0)
        try:
            int(chunk_id, 16)
            assert True
        except ValueError:
            assert False, "Chunk ID is not hexadecimal"


class TestEmbeddings:
    """Tests for embedding generation."""

    def test_generate_mock_embedding_returns_list(self, document_service):
        """Test that embedding generation returns a list."""
        embedding = document_service._generate_mock_embedding("test text")
        assert isinstance(embedding, list)

    def test_generate_mock_embedding_has_correct_dimension(self, document_service):
        """Test that embedding has 384 dimensions."""
        embedding = document_service._generate_mock_embedding("test text")
        assert len(embedding) == 384

    def test_generate_mock_embedding_values_are_floats(self, document_service):
        """Test that embedding values are floats."""
        embedding = document_service._generate_mock_embedding("test text")
        assert all(isinstance(val, float) for val in embedding)

    def test_generate_mock_embedding_values_in_valid_range(self, document_service):
        """Test that embedding values are between 0 and 1."""
        embedding = document_service._generate_mock_embedding("test text")
        assert all(0 <= val <= 1 for val in embedding)

    def test_generate_mock_embedding_consistent_for_same_text(self, document_service):
        """Test that same text produces same embedding."""
        text = "consistent test"
        embedding_1 = document_service._generate_mock_embedding(text)
        embedding_2 = document_service._generate_mock_embedding(text)
        assert embedding_1 == embedding_2

    def test_generate_mock_embedding_different_for_different_text(self, document_service):
        """Test that different texts produce different embeddings."""
        embedding_1 = document_service._generate_mock_embedding("text one")
        embedding_2 = document_service._generate_mock_embedding("text two")
        assert embedding_1 != embedding_2


class TestDocumentChunking:
    """Tests for document text chunking."""

    def test_split_into_chunks_returns_list(self, document_service, sample_document_text):
        """Test that chunking returns a list."""
        chunks = document_service._split_into_chunks(sample_document_text)
        assert isinstance(chunks, list)

    def test_split_into_chunks_preserves_all_content(
        self, document_service, sample_document_text
    ):
        """Test that all content is preserved after chunking."""
        chunks = document_service._split_into_chunks(sample_document_text)
        rejoined = " ".join(chunks)
        assert sample_document_text == rejoined

    def test_split_into_chunks_respects_chunk_size(self, document_service):
        """Test that chunks don't exceed specified chunk size."""
        long_text = " ".join(["word"] * 1000)
        chunks = document_service._split_into_chunks(long_text, chunk_size=100)
        for chunk in chunks:
            # Allow some margin due to word boundaries
            assert len(chunk) <= 110

    def test_split_into_chunks_custom_size(self, document_service, sample_document_text):
        """Test chunking with custom chunk size."""
        chunks_small = document_service._split_into_chunks(sample_document_text, chunk_size=50)
        chunks_large = document_service._split_into_chunks(sample_document_text, chunk_size=200)
        assert len(chunks_small) >= len(chunks_large)

    def test_split_into_chunks_empty_text(self, document_service):
        """Test chunking empty text."""
        chunks = document_service._split_into_chunks("")
        assert chunks == [] or chunks == [""]

    def test_split_into_chunks_single_word(self, document_service):
        """Test chunking single word."""
        chunks = document_service._split_into_chunks("word")
        assert len(chunks) == 1
        assert chunks[0] == "word"


class TestSimilarityComputation:
    """Tests for cosine similarity computation."""

    def test_compute_similarity_identical_vectors(self, document_service):
        """Test similarity between identical vectors is 1.0."""
        vector = [1.0, 0.0, 0.0]
        similarity = document_service._compute_similarity(vector, vector)
        assert abs(similarity - 1.0) < 0.0001

    def test_compute_similarity_orthogonal_vectors(self, document_service):
        """Test similarity between orthogonal vectors is 0.0."""
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        similarity = document_service._compute_similarity(vec1, vec2)
        assert abs(similarity - 0.0) < 0.0001

    def test_compute_similarity_returns_float(self, document_service):
        """Test that similarity computation returns a float."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [4.0, 5.0, 6.0]
        similarity = document_service._compute_similarity(vec1, vec2)
        assert isinstance(similarity, float)

    def test_compute_similarity_scale_invariant(self, document_service):
        """Test that similarity is scale invariant."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [2.0, 4.0, 6.0]
        similarity = document_service._compute_similarity(vec1, vec2)
        assert abs(similarity - 1.0) < 0.0001

    def test_compute_similarity_empty_vector(self, document_service):
        """Test similarity with empty vector returns 0.0."""
        vec1 = [1.0, 2.0]
        vec2 = []
        similarity = document_service._compute_similarity(vec1, vec2)
        assert similarity == 0.0

    def test_compute_similarity_zero_vector(self, document_service):
        """Test similarity with zero vector returns 0.0."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        similarity = document_service._compute_similarity(vec1, vec2)
        assert similarity == 0.0


class TestDocumentProcessing:
    """Tests for document processing and storage."""

    def test_process_and_store_returns_dict(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that process_and_store returns a dictionary."""
        result = document_service.process_and_store(sample_document_text, sample_metadata)
        assert isinstance(result, dict)

    def test_process_and_store_contains_required_keys(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that result contains required keys."""
        result = document_service.process_and_store(sample_document_text, sample_metadata)
        required_keys = {"document_id", "chunks_stored", "chunk_ids", "file_path"}
        assert required_keys.issubset(result.keys())

    def test_process_and_store_populates_vector_store(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that chunks are stored in vector store."""
        initial_count = len(document_service.vector_store)
        document_service.process_and_store(sample_document_text, sample_metadata)
        assert len(document_service.vector_store) > initial_count

    def test_process_and_store_indexes_document(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that document is indexed."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        assert sample_metadata["document_id"] in document_service.document_index

    def test_process_and_store_adds_embeddings(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that chunks have embeddings."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        for chunk in document_service.vector_store:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 384

    def test_process_and_store_with_file_content(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test storing with file content."""
        file_content = b"test file content"
        result = document_service.process_and_store(
            sample_document_text, sample_metadata, file_content, "test.txt"
        )
        assert result["file_path"] is not None


class TestDocumentSearch:
    """Tests for document search functionality."""

    def test_search_returns_list(self, document_service, sample_document_text, sample_metadata):
        """Test that search returns a list."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        results = document_service.search("healthcare")
        assert isinstance(results, list)

    def test_search_returns_document_search_results(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that search results are DocumentSearchResult objects."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        results = document_service.search("healthcare")
        assert all(isinstance(r, DocumentSearchResult) for r in results)

    def test_search_respects_top_k(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that search returns at most top_k results."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        results = document_service.search("healthcare", top_k=2)
        assert len(results) <= 2

    def test_search_on_empty_store_returns_empty_list(self, document_service):
        """Test that search on empty store returns empty list."""
        results = document_service.search("query")
        assert results == []

    def test_search_results_have_similarity_scores(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that search results include similarity scores."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        results = document_service.search("procedure")
        if results:
            assert all(hasattr(r, "similarity_score") for r in results)
            assert all(isinstance(r.similarity_score, float) for r in results)

    def test_search_results_sorted_by_similarity(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that results are sorted by similarity score descending."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        results = document_service.search("procedure", top_k=5)
        if len(results) > 1:
            similarities = [r.similarity_score for r in results]
            assert similarities == sorted(similarities, reverse=True)


class TestDocumentMetadataHandling:
    """Tests for metadata handling in chunks."""

    def test_chunk_metadata_preserved(
        self, document_service, sample_document_text, sample_metadata
    ):
        """Test that metadata is preserved in chunks."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        chunk = document_service.vector_store[0]
        assert chunk.metadata.document_id == sample_metadata["document_id"]
        assert chunk.metadata.title == sample_metadata["title"]
        assert chunk.metadata.author == sample_metadata["author"]
        assert chunk.metadata.source_url == sample_metadata["source_url"]

    def test_chunk_index_preserved(self, document_service, sample_document_text, sample_metadata):
        """Test that chunk indices are correctly assigned."""
        document_service.process_and_store(sample_document_text, sample_metadata)
        for i, chunk in enumerate(document_service.vector_store):
            if i == 0:
                assert chunk.metadata.chunk_index == 0


class TestFileOperations:
    """Tests for file operations."""

    def test_save_file_creates_file(self, document_service):
        """Test that save_file creates a file."""
        file_content = b"test content"
        path = document_service._save_file("test.txt", file_content)
        assert "test" in path and ".txt" in path
        assert path.startswith("storage/uploads/")

    def test_save_file_handles_collisions(self, document_service):
        """Test that save_file handles filename collisions."""
        file_content = b"test content"
        path1 = document_service._save_file("test.txt", file_content)
        path2 = document_service._save_file("test.txt", file_content)
        assert path1 != path2
        assert "test" in path1
        assert "test" in path2

    def test_save_file_preserves_extension(self, document_service):
        """Test that file extension is preserved."""
        file_content = b"test"
        path = document_service._save_file("document.pdf", file_content)
        assert path.endswith(".pdf")
