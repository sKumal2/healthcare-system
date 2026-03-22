from typing import List


class Ranker:
    """Ranks retrieved documents by relevance."""

    def rank(self, documents: List[dict]) -> List[dict]:
        """
        Rank documents by relevance score.

        For Phase 1, this is a simple pass-through.
        Later, this can implement cross-encoders or other ranking strategies.

        Args:
            documents: List of retrieved documents

        Returns:
            List of ranked documents sorted by relevance
        """
        # Sort documents by similarity_score in descending order
        ranked = sorted(
            documents,
            key=lambda x: x.get("similarity_score", 0),
            reverse=True
        )
        return ranked
