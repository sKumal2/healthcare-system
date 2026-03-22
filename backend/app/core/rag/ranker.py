from typing import List
from app.core.rag.retriever import RetrievedDocument, RankedDocument


class Ranker:
    """Ranks retrieved documents by relevance."""

    def rank(self, documents: List[RetrievedDocument]) -> List[RankedDocument]:
        """
        Rank documents by relevance score.

        For Phase 1, this is a simple pass-through that converts to RankedDocument.
        Later, this can implement cross-encoders or other ranking strategies.

        Args:
            documents: List of retrieved documents

        Returns:
            List of ranked documents
        """
        # Convert RetrievedDocument to RankedDocument
        # For now, use similarity_score as rank_score
        ranked = [
            RankedDocument(
                document_id=doc.document_id,
                title=doc.title,
                content=doc.content,
                source_url=doc.source_url,
                author=doc.author,
                rank_score=doc.similarity_score
            )
            for doc in documents
        ]

        # Sort by rank_score in descending order
        ranked.sort(key=lambda x: x.rank_score, reverse=True)
        return ranked
