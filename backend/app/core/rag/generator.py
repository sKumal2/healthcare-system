import os
import logging
from typing import Optional

try:
    import google.generativeai as genai
except ImportError:
    genai = None


logger = logging.getLogger(__name__)


class LLMGenerator:
    """Generates responses using Google Gemini API."""

    def __init__(self):
        """Initialize Gemini client with API key from environment."""
        if genai is None:
            raise ImportError(
                "google-generativeai is not installed. "
                "Install it with: pip install google-generativeai"
            )

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Please add it to your .env file."
            )

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> str:
        """
        Generate a response using Google Gemini API.

        Args:
            prompt: The main prompt with context and query
            system_prompt: System-level instructions for the LLM
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)

        Returns:
            Generated response text from Gemini
        """
        try:
            # Combine system and main prompt
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # Call Gemini API
            response = self.model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )

            # Extract text from response
            if response.text:
                return response.text.strip()
            else:
                return "Unable to generate response. Please try again."

        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            return (
                f"An error occurred while processing your request: {str(e)}. "
                "Please ensure your GEMINI_API_KEY is valid."
            )

    def extract_citations_from_documents(self, documents: list) -> list:
        """
        Extract citations from the ranked documents.

        Args:
            documents: List of ranked documents used as context

        Returns:
            List of citation dictionaries
        """
        citations = [
            {
                "document_id": doc.get("document_id"),
                "title": doc.get("title"),
                "text": doc.get("text", doc.get("content"))
            }
            for doc in documents
        ]
        return citations
