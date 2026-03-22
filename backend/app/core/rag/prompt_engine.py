from typing import List


class PromptEngine:
    """Builds structured prompts for LLM using query and context."""

    def build_prompt(self, query: str, documents: List[dict]) -> str:
        """
        Build a strong clinical prompt with query and retrieved context.

        Args:
            query: User's medical question or query
            documents: Retrieved and ranked documents for context

        Returns:
            Formatted prompt string for the LLM
        """
        # Build context section from ranked documents
        context_parts = []
        for i, doc in enumerate(documents, 1):
            title = doc.get("title", "Untitled")
            content = doc.get("content", doc.get("text", ""))
            doc_id = doc.get("document_id", f"doc_{i}")

            context_parts.append(
                f"[Source {i}]\n"
                f"Title: {title}\n"
                f"Content: {content}\n"
                f"Document ID: {doc_id}"
            )

        context_section = "\n\n".join(context_parts)

        # Construct the full prompt with strong clinical guidelines
        prompt = (
            f"Question: {query}\n\n"
            f"Clinical Context:\n"
            f"{context_section}\n\n"
            f"Instructions:\n"
            f"- Answer ONLY based on the provided clinical context above\n"
            f"- If the context doesn't contain relevant information, clearly state that\n"
            f"- Provide evidence-based, accurate medical information\n"
            f"- Keep your answer concise and focused\n"
            f"- Suggest consulting healthcare professionals when appropriate\n"
            f"- Do not make definitive diagnoses or treatment recommendations\n\n"
            f"Answer:"
        )

        return prompt

    def build_system_prompt(self) -> str:
        """
        Build the system prompt that defines LLM behavior.

        Returns:
            System prompt string for the LLM
        """
        return (
            "You are an expert clinical healthcare assistant designed to provide "
            "evidence-based medical information. Your role is to answer healthcare questions "
            "using only the provided medical context and sources. "
            "\n\nKey guidelines:\n"
            "1. Base all answers solely on the provided documents\n"
            "2. Provide accurate, evidence-based information\n"
            "3. Acknowledge limitations and uncertainties\n"
            "4. Always recommend consulting qualified healthcare professionals\n"
            "5. Never diagnose conditions or prescribe treatments\n"
            "6. Keep responses clear, concise, and medically accurate\n"
            "7. Cite the provided sources when relevant\n"
            "8. If information is not in the context, explicitly state this"
        )
