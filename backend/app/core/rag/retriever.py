from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class RetrievedDocument(BaseModel):
    """A document retrieved from the vector store."""
    document_id: str
    title: str
    content: str
    source_url: Optional[str] = None
    author: Optional[str] = None
    similarity_score: float


class RankedDocument(BaseModel):
    """A document after ranking."""
    document_id: str
    title: str
    content: str
    source_url: Optional[str] = None
    author: Optional[str] = None
    rank_score: float


class Citation(BaseModel):
    """A citation to a source document."""
    document_id: str
    title: str
    text: str
    source_url: Optional[str] = None


class RAGResponse(BaseModel):
    """Response from the RAG pipeline."""
    response: str
    citations: List[Citation]
    retrieved_count: int
    ranked_count: int


class Retriever:
    """Handles document retrieval from vector store."""

    def __init__(self):
        """Initialize retriever with mock documents."""
        self.mock_documents = self._load_mock_documents()

    def _load_mock_documents(self) -> List[RetrievedDocument]:
        """Load mock healthcare documents for demonstration."""
        return [
            RetrievedDocument(
                document_id="doc_001",
                title="Diabetes Management Guidelines",
                content="Type 2 diabetes is best managed through a combination of lifestyle changes and medication. "
                       "Patients should maintain a healthy diet rich in vegetables and lean proteins, "
                       "exercise regularly for at least 150 minutes per week, and monitor blood glucose levels daily. "
                       "Metformin is often the first-line medication prescribed.",
                source_url="https://medical.org/diabetes",
                author="Dr. Smith",
                similarity_score=0.95
            ),
            RetrievedDocument(
                document_id="doc_002",
                title="Hypertension Treatment",
                content="Hypertension affects millions worldwide and increases risk of heart disease and stroke. "
                       "Treatment includes ACE inhibitors, beta-blockers, and diuretics. "
                       "Lifestyle modifications such as reducing sodium intake, maintaining healthy weight, "
                       "and regular exercise are crucial components of management.",
                source_url="https://medical.org/hypertension",
                author="Dr. Johnson",
                similarity_score=0.87
            ),
            RetrievedDocument(
                document_id="doc_003",
                title="COVID-19 Clinical Guidelines",
                content="COVID-19 treatment varies based on disease severity. Mild cases may only require supportive care, "
                       "while moderate to severe cases may require antiviral medications and oxygen therapy. "
                       "Vaccination remains the most effective prevention strategy. Latest variants show varying severity.",
                source_url="https://medical.org/covid",
                author="Dr. Williams",
                similarity_score=0.82
            ),
            RetrievedDocument(
                document_id="doc_004",
                title="Cardiovascular Disease Prevention",
                content="Prevention of cardiovascular disease involves managing risk factors including hypertension, "
                       "high cholesterol, obesity, and smoking. Regular cardiovascular exercise, Mediterranean diet, "
                       "and annual check-ups are recommended. Statins may be prescribed for high-risk patients.",
                source_url="https://medical.org/cardio",
                author="Dr. Brown",
                similarity_score=0.78
            ),
            RetrievedDocument(
                document_id="doc_005",
                title="Mental Health Awareness",
                content="Mental health is integral to overall wellbeing. Depression and anxiety are common conditions "
                       "treatable through therapy, medication, or combination approaches. Early interventions and "
                       "professional support significantly improve outcomes. Mindfulness and regular exercise help.",
                source_url="https://medical.org/mental",
                author="Dr. Davis",
                similarity_score=0.71
            ),
        ]

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievedDocument]:
        """
        Retrieve documents similar to the query.

        Args:
            query: User's search query
            top_k: Number of documents to retrieve

        Returns:
            List of retrieved documents sorted by similarity score
        """
        # Mock similarity calculation - in reality, would use vector search
        # For now, simply return top_k documents sorted by similarity_score
        sorted_docs = sorted(
            self.mock_documents,
            key=lambda x: x.similarity_score,
            reverse=True
        )
        return sorted_docs[:top_k]
