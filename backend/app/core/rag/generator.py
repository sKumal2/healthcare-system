from typing import List
from app.core.rag.ranker import RankedDocument


class Generator:
    """Generates responses using constructed prompts (LLM interface)."""

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> str:
        """
        Generate a response using the LLM.

        For Phase 1, this returns a mock response.
        Later, replace with actual OpenAI/Anthropic/Local LLM API calls.

        Args:
            prompt: The main prompt with context
            system_prompt: System-level instructions for the LLM
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)

        Returns:
            Generated response text from the LLM
        """
        # Phase 1: Return mock response
        # In production, this would call an LLM API
        response = self._generate_mock_response(prompt)
        return response

    def _generate_mock_response(self, prompt: str) -> str:
        """
        Generate a mock response for demonstration.

        Args:
            prompt: The full prompt

        Returns:
            Mock response text
        """
        # Extract question from prompt for context
        if "Question:" in prompt:
            question_part = prompt.split("Question:")[1].split("\n")[0].strip()
        else:
            question_part = "your question"

        response = (
            f"Based on the provided medical context regarding {question_part}, "
            f"here is a comprehensive answer:\n\n"
            f"The information provided in the documents outlines several key points and recommendations. "
            f"These evidence-based guidelines suggest consulting with qualified healthcare professionals "
            f"for personalized medical advice. The sources cited above contain detailed information on best practices "
            f"and management strategies.\n\n"
            f"Please note that this information is for educational purposes and should not replace "
            f"professional medical consultation."
        )
        return response

    def extract_citations_from_documents(
        self,
        documents: List[RankedDocument]
    ) -> List[dict]:
        """
        Extract citations from the ranked documents.

        Args:
            documents: List of ranked documents used as context

        Returns:
            List of citation dictionaries with document_id and text
        """
        citations = [
            {
                "document_id": doc.document_id,
                "title": doc.title,
                "text": doc.content
            }
            for doc in documents
        ]
        return citations
