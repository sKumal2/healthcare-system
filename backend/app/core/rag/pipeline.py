from typing import Optional
from app.core.rag.retriever import Retriever
from app.core.rag.ranker import Ranker
from app.core.rag.prompt_engine import PromptEngine
from app.core.rag.generator import Generator
from app.core.rag.retriever import RAGResponse, Citation


class RAGPipeline:
    """
    Main orchestrator for the RAG (Retrieval-Augmented Generation) pipeline.

    Coordinates the entire flow:
    Query → Retrieve → Rank → Build Prompt → Generate → Citations
    """

    def __init__(self):
        """Initialize all RAG components."""
        self.retriever = Retriever()
        self.ranker = Ranker()
        self.prompt_engine = PromptEngine()
        self.generator = Generator()

    def process_query(self, query: str, top_k: int = 5) -> RAGResponse:
        """
        Process a query through the complete RAG pipeline.

        Pipeline steps:
        1. Retrieve: Fetch relevant documents from vector store
        2. Rank: Sort documents by relevance
        3. Prompt Engineering: Build structured prompt with context
        4. Generation: Call LLM to generate response
        5. Citations: Extract source citations

        Args:
            query: User's question or search query
            top_k: Number of documents to retrieve (default: 5)

        Returns:
            RAGResponse containing the answer and citations
        """

        # Step 1: Retrieve documents matching the query
        retrieved_docs = self.retriever.retrieve(query=query, top_k=top_k)

        # Step 2: Rank documents by relevance
        ranked_docs = self.ranker.rank(retrieved_docs)

        # Step 3: Build prompt with query and context
        system_prompt = self.prompt_engine.build_system_prompt()
        main_prompt = self.prompt_engine.build_prompt(query, ranked_docs)

        # Step 4: Generate response from LLM
        response_text = self.generator.generate(
            prompt=main_prompt,
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.7
        )

        # Step 5: Extract and format citations
        raw_citations = self.generator.extract_citations_from_documents(ranked_docs)
        citations = [
            Citation(
                document_id=cit["document_id"],
                title=cit["title"],
                text=cit["text"],
                source_url=ranked_docs[i].source_url if i < len(ranked_docs) else None
            )
            for i, cit in enumerate(raw_citations)
        ]

        # Construct final response
        return RAGResponse(
            response=response_text,
            citations=citations,
            retrieved_count=len(retrieved_docs),
            ranked_count=len(ranked_docs)
        )

    def health_check(self) -> dict:
        """
        Check if all RAG components are initialized properly.

        Returns:
            Dictionary with component status
        """
        return {
            "retriever": "initialized" if self.retriever else "missing",
            "ranker": "initialized" if self.ranker else "missing",
            "prompt_engine": "initialized" if self.prompt_engine else "missing",
            "generator": "initialized" if self.generator else "missing"
        }
