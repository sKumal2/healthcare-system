import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.query_service import (
    QueryService,
    QueryRequest,
    QueryResponse,
    SourceMetadata,
)
from app.services.document_service import (
    DocumentService,
    DocumentChunk,
    DocumentMetadata,
    DocumentSearchResult,
)


@pytest.fixture
def document_service():
    """Fixture to create a DocumentService instance with sample data."""
    service = DocumentService()
    
    # Add some sample documents
    sample_text = (
        "Diabetes is a metabolic disorder that affects how your body processes glucose. "
        "Type 1 diabetes occurs when the pancreas cannot produce enough insulin. "
        "Type 2 diabetes is more common and often develops in adults. "
        "Management includes diet, exercise, and medication."
    )
    
    metadata = {
        "document_id": "diabetes_doc",
        "title": "Understanding Diabetes",
        "source_url": "https://example.com/diabetes",
        "author": "Dr. Johnson"
    }
    
    service.process_and_store(sample_text, metadata)
    return service


@pytest.fixture
def query_service(document_service):
    """Fixture to create a QueryService instance."""
    return QueryService(document_service=document_service)


@pytest.fixture
def query_service_no_docs():
    """Fixture to create a QueryService with no document service."""
    return QueryService(document_service=None)


@pytest.fixture
def sample_query_request():
    """Fixture providing a sample QueryRequest."""
    return QueryRequest(question="What is diabetes?", top_k=5)


class TestQueryServiceInitialization:
    """Tests for QueryService initialization."""

    def test_service_initializes_with_document_service(self, document_service):
        """Test that service initializes with a document service."""
        service = QueryService(document_service=document_service)
        assert service.document_service is document_service

    def test_service_initializes_without_document_service(self):
        """Test that service can initialize without a document service."""
        service = QueryService(document_service=None)
        assert service.document_service is None

    def test_service_initializes_with_default_none(self):
        """Test that document_service defaults to None."""
        service = QueryService()
        assert service.document_service is None


class TestQuestionEmbedding:
    """Tests for question embedding generation."""

    def test_generate_question_embedding_returns_list(self, query_service):
        """Test that embedding generation returns a list."""
        embedding = query_service._generate_question_embedding("What is diabetes?")
        assert isinstance(embedding, list)

    def test_generate_question_embedding_has_correct_dimension(self, query_service):
        """Test that embedding has 384 dimensions."""
        embedding = query_service._generate_question_embedding("What is diabetes?")
        assert len(embedding) == 384

    def test_generate_question_embedding_values_are_floats(self, query_service):
        """Test that embedding values are floats."""
        embedding = query_service._generate_question_embedding("Test question")
        assert all(isinstance(val, float) for val in embedding)

    def test_generate_question_embedding_consistent(self, query_service):
        """Test that same question produces same embedding."""
        question = "What is diabetes?"
        embedding_1 = query_service._generate_question_embedding(question)
        embedding_2 = query_service._generate_question_embedding(question)
        assert embedding_1 == embedding_2

    def test_generate_question_embedding_different_for_different_questions(self, query_service):
        """Test that different questions produce different embeddings."""
        embedding_1 = query_service._generate_question_embedding("Question 1?")
        embedding_2 = query_service._generate_question_embedding("Question 2?")
        assert embedding_1 != embedding_2


class TestContextRetrieval:
    """Tests for context chunk retrieval."""

    def test_retrieve_context_chunks_returns_list(self, query_service, sample_query_request):
        """Test that retrieval returns a list."""
        chunks = query_service._retrieve_context_chunks("What is diabetes?", top_k=5)
        assert isinstance(chunks, list)

    def test_retrieve_context_chunks_returns_dicts(self, query_service):
        """Test that retrieved chunks are dictionaries."""
        chunks = query_service._retrieve_context_chunks("diabetes", top_k=5)
        assert all(isinstance(chunk, dict) for chunk in chunks)

    def test_retrieve_context_chunks_has_required_keys(self, query_service):
        """Test that chunks have all required keys."""
        chunks = query_service._retrieve_context_chunks("diabetes", top_k=5)
        required_keys = {
            "content",
            "document_id",
            "title",
            "source_url",
            "author",
            "similarity_score",
        }
        if chunks:
            assert required_keys.issubset(chunks[0].keys())

    def test_retrieve_context_chunks_respects_top_k(self, query_service):
        """Test that retrieval respects top_k parameter."""
        chunks = query_service._retrieve_context_chunks("diabetes", top_k=2)
        assert len(chunks) <= 2

    def test_retrieve_context_chunks_no_document_service(self, query_service_no_docs):
        """Test that retrieval returns empty list without document service."""
        chunks = query_service_no_docs._retrieve_context_chunks("question", top_k=5)
        assert chunks == []

    def test_retrieve_context_chunks_has_similarities(self, query_service):
        """Test that retrieved chunks include similarity scores."""
        chunks = query_service._retrieve_context_chunks("diabetes", top_k=5)
        if chunks:
            assert all("similarity_score" in chunk for chunk in chunks)
            assert all(isinstance(chunk["similarity_score"], float) for chunk in chunks)


class TestPromptBuilding:
    """Tests for LLM prompt building."""

    def test_build_prompt_returns_string(self, query_service):
        """Test that prompt building returns a string."""
        prompt = query_service._build_prompt("What is diabetes?", [])
        assert isinstance(prompt, str)

    def test_build_prompt_includes_question(self, query_service):
        """Test that prompt includes the question."""
        question = "What is diabetes?"
        prompt = query_service._build_prompt(question, [])
        assert question in prompt

    def test_build_prompt_includes_context(self, query_service, query_request=None):
        """Test that prompt includes context from chunks."""
        chunks = [
            {
                "content": "Diabetes is a metabolic disorder",
                "title": "Diabetes Overview",
                "document_id": "doc1",
                "source_url": None,
                "author": None,
                "similarity_score": 0.9,
            }
        ]
        prompt = query_service._build_prompt("What is diabetes?", chunks)
        assert "Diabetes is a metabolic disorder" in prompt

    def test_build_prompt_with_empty_chunks(self, query_service):
        """Test prompt building with no context chunks."""
        prompt = query_service._build_prompt("Question?", [])
        assert "No relevant documents found" in prompt or "Context" in prompt

    def test_build_prompt_includes_multiple_sources(self, query_service):
        """Test that prompt includes multiple source contents."""
        chunks = [
            {
                "content": "First source content",
                "title": "Source 1",
                "document_id": "doc1",
                "source_url": None,
                "author": None,
                "similarity_score": 0.9,
            },
            {
                "content": "Second source content",
                "title": "Source 2",
                "document_id": "doc2",
                "source_url": None,
                "author": None,
                "similarity_score": 0.8,
            },
        ]
        prompt = query_service._build_prompt("Question?", chunks)
        assert "First source content" in prompt
        assert "Second source content" in prompt

    def test_build_prompt_includes_healthcare_context(self, query_service):
        """Test that prompt mentions healthcare assistant role when chunks are provided."""
        chunks = [
            {
                "content": "Sample medical content",
                "title": "Medical Source",
                "document_id": "doc1",
                "source_url": None,
                "author": None,
                "similarity_score": 0.9,
            }
        ]
        prompt = query_service._build_prompt("Question?", chunks)
        assert "healthcare" in prompt.lower() or "assistant" in prompt.lower()


class TestAnswerGeneration:
    """Tests for answer generation."""

    def test_generate_answer_returns_string(self, query_service):
        """Test that answer generation returns a string."""
        prompt = "Sample prompt"
        answer = query_service._generate_answer(prompt)
        assert isinstance(answer, str)

    def test_generate_answer_is_not_empty(self, query_service):
        """Test that generated answer is not empty."""
        prompt = "Sample prompt about diabetes"
        answer = query_service._generate_answer(prompt)
        assert len(answer) > 0

    def test_generate_answer_consistent_for_same_prompt(self, query_service):
        """Test that same prompt produces same answer (mock implementation)."""
        prompt = "Test prompt"
        answer_1 = query_service._generate_answer(prompt)
        answer_2 = query_service._generate_answer(prompt)
        assert answer_1 == answer_2


class TestQuestionAnswering:
    """Tests for the main question answering workflow."""

    def test_ask_question_returns_query_response(self, query_service, sample_query_request):
        """Test that ask_question returns a QueryResponse."""
        response = query_service.ask_question(sample_query_request)
        assert isinstance(response, QueryResponse)

    def test_ask_question_response_has_question(self, query_service, sample_query_request):
        """Test that response includes the original question."""
        response = query_service.ask_question(sample_query_request)
        assert response.question == sample_query_request.question

    def test_ask_question_response_has_answer(self, query_service, sample_query_request):
        """Test that response includes an answer."""
        response = query_service.ask_question(sample_query_request)
        assert response.answer is not None
        assert isinstance(response.answer, str)
        assert len(response.answer) > 0

    def test_ask_question_response_has_sources(self, query_service, sample_query_request):
        """Test that response includes sources list."""
        response = query_service.ask_question(sample_query_request)
        assert response.sources is not None
        assert isinstance(response.sources, list)

    def test_ask_question_response_sources_are_source_metadata(
        self, query_service, sample_query_request
    ):
        """Test that sources are SourceMetadata objects."""
        response = query_service.ask_question(sample_query_request)
        assert all(isinstance(s, SourceMetadata) for s in response.sources)

    def test_ask_question_response_has_timestamp(self, query_service, sample_query_request):
        """Test that response includes a timestamp."""
        response = query_service.ask_question(sample_query_request)
        assert response.generated_at is not None
        assert isinstance(response.generated_at, datetime)

    def test_ask_question_deduplicates_sources(self, query_service):
        """Test that sources are deduplicated by document_id."""
        # Create a query request
        request = QueryRequest(question="What is diabetes?", top_k=10)
        response = query_service.ask_question(request)
        
        # Extract document IDs from sources
        doc_ids = [source.document_id for source in response.sources]
        # Check that there are no duplicates
        assert len(doc_ids) == len(set(doc_ids))

    def test_ask_question_with_custom_top_k(self, query_service):
        """Test ask_question with custom top_k parameter."""
        request = QueryRequest(question="What is diabetes?", top_k=3)
        response = query_service.ask_question(request)
        assert isinstance(response, QueryResponse)
        # Should have at most 3 unique sources
        assert len(response.sources) <= 3


class TestQueryRequestValidation:
    """Tests for QueryRequest validation."""

    def test_query_request_requires_question(self):
        """Test that QueryRequest requires a question."""
        with pytest.raises(ValueError):
            QueryRequest(question="")

    def test_query_request_with_valid_inputs(self):
        """Test creating QueryRequest with valid inputs."""
        request = QueryRequest(question="Valid question?", top_k=5)
        assert request.question == "Valid question?"
        assert request.top_k == 5

    def test_query_request_defaults_top_k(self):
        """Test that top_k defaults to 5."""
        request = QueryRequest(question="Question?")
        assert request.top_k == 5

    def test_query_request_enforces_top_k_bounds(self):
        """Test that top_k is bounded between 1 and 20."""
        # Valid boundaries should work
        request_min = QueryRequest(question="Q?", top_k=1)
        request_max = QueryRequest(question="Q?", top_k=20)
        assert request_min.top_k == 1
        assert request_max.top_k == 20


class TestSourceMetadata:
    """Tests for SourceMetadata in responses."""

    def test_source_metadata_includes_document_id(self, query_service):
        """Test that sources include document ID."""
        request = QueryRequest(question="diabetes", top_k=5)
        response = query_service.ask_question(request)
        if response.sources:
            assert all(source.document_id for source in response.sources)

    def test_source_metadata_includes_title(self, query_service):
        """Test that sources include title."""
        request = QueryRequest(question="diabetes", top_k=5)
        response = query_service.ask_question(request)
        if response.sources:
            assert all(source.title for source in response.sources)

    def test_source_metadata_includes_similarity_score(self, query_service):
        """Test that sources include similarity score."""
        request = QueryRequest(question="diabetes", top_k=5)
        response = query_service.ask_question(request)
        if response.sources:
            assert all(
                hasattr(source, "similarity_score") and isinstance(source.similarity_score, float)
                for source in response.sources
            )


class TestEndToEndQueryFlow:
    """End-to-end tests for the complete query workflow."""

    def test_complete_query_workflow(self, query_service):
        """Test complete workflow from question to answer."""
        # Create a query
        request = QueryRequest(question="What causes diabetes?", top_k=5)
        
        # Get response
        response = query_service.ask_question(request)
        
        # Verify all components
        assert response.question == "What causes diabetes?"
        assert response.answer is not None
        assert len(response.answer) > 0
        assert isinstance(response.sources, list)
        assert response.generated_at is not None

    def test_query_workflow_with_no_relevant_documents(self, query_service_no_docs):
        """Test workflow when no document service is available."""
        request = QueryRequest(question="What is diabetes?", top_k=5)
        response = query_service_no_docs.ask_question(request)
        
        # Should still return a response with empty sources
        assert isinstance(response, QueryResponse)
        assert response.sources == []

    def test_query_workflow_preserves_question_text(self, query_service):
        """Test that original question is preserved in response."""
        original_question = "How is type 1 diabetes diagnosed?"
        request = QueryRequest(question=original_question, top_k=5)
        response = query_service.ask_question(request)
        assert response.question == original_question

    def test_multiple_queries_independent(self, query_service):
        """Test that multiple queries don't interfere with each other."""
        request1 = QueryRequest(question="What is diabetes?", top_k=3)
        request2 = QueryRequest(question="How to treat diabetes?", top_k=3)
        
        response1 = query_service.ask_question(request1)
        response2 = query_service.ask_question(request2)
        
        assert response1.question == "What is diabetes?"
        assert response2.question == "How to treat diabetes?"
        assert response1.answer != response2.answer or response1.sources != response2.sources
