from typing import List
from app.core.rag.ranker import RankedDocument


class PromptEngine:
    """Builds structured prompts for LLM using query and context."""

    def build_prompt(self, query: str, documents: List[RankedDocument]) -> str:
        """
        Build a prompt that includes the query and retrieved context.

        Args:
            query: User's question or query
            documents: Retrieved and ranked documents for context

        Returns:
            Formatted prompt string for the LLM
        """
        # Build context section from ranked documents
        context_parts = []
        for i, doc in enumerate(documents, 1):
            context_parts.append(
                f"Source {i}: {doc.title}\n"
                f"Content: {doc.content}\n"
                f"Document ID: {doc.document_id}"
            )

        context_section = "\n\n".join(context_parts)

        # Construct the full prompt
        prompt = (
            "You are a helpful healthcare assistant. Answer the following question "
            "based on the provided medical context. If the context doesn't contain "
            "relevant information, say so clearly.\n\n"
            f"Question: {query}\n\n"
            f"Context:\n{context_section}\n\n"
            "Answer: "
        )

        return prompt

    def build_system_prompt(self) -> str:
        """
        Build the system prompt for the LLM.

        Returns:
            System prompt string
        """
        return (
            "You are an expert healthcare assistant with knowledge of medical best practices. "
            "Provide evidence-based, accurate, and helpful information. "
            "Always cite your sources when available. "
            "If you're unsure about something, acknowledge the limitation."
        )
