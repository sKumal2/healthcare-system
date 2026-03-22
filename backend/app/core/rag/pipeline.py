import logging
from app.core.rag.retriever import Retriever
from app.core.rag.ranker import Ranker
from app.core.rag.prompt_engine import PromptEngine
from app.core.rag.generator import LLMGenerator


logger = logging.getLogger(__name__)


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

        try:
            self.generator = LLMGenerator()
        except (ImportError, ValueError) as e:
            logger.warning(f"LLM initialization failed: {str(e)}")
            self.generator = None

    def process_query(self, query: str, top_k: int = 5) -> dict:
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
            Dictionary containing:
            - "response": Generated answer text
            - "citations": List of source documents used
        """
        try:
            # Step 1: Retrieve documents matching the query
            retrieved_docs = self.retriever.retrieve(query=query, top_k=top_k)
            logger.info(f"Retrieved {len(retrieved_docs)} documents for query: {query}")

            # Step 2: Rank documents by relevance
            ranked_docs = self.ranker.rank(retrieved_docs)
            logger.info(f"Ranked {len(ranked_docs)} documents")

            # Step 3: Build prompt with query and context
            system_prompt = self.prompt_engine.build_system_prompt()
            main_prompt = self.prompt_engine.build_prompt(query, ranked_docs)
            logger.info("Built prompt for LLM")

            # Step 4: Generate response from LLM
            if self.generator is None:
                response_text = (
                    "Error: LLM generator not initialized. "
                    "Please ensure GEMINI_API_KEY is set in environment variables."
                )
            else:
                response_text = self.generator.generate(
                    prompt=main_prompt,
                    system_prompt=system_prompt,
                    max_tokens=1024,
                    temperature=0.7
                )
            logger.info("Generated response from LLM")

            # Step 5: Extract and format citations
            citations = [
                {
                    "document_id": doc.get("document_id"),
                    "title": doc.get("title"),
                    "text": doc.get("content"),
                    "source_url": doc.get("source_url")
                }
                for doc in ranked_docs
            ]

            # Construct final response
            return {
                "response": response_text,
                "citations": citations
            }

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            return {
                "response": f"An error occurred while processing your query: {str(e)}",
                "citations": []
            }

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
            "generator": "initialized" if self.generator else "not_available"
        }
