from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import hashlib
import uuid


class DocumentMetadata(BaseModel):
    """Metadata for document chunks."""
    document_id: str
    title: str
    chunk_index: int
    source_url: Optional[str] = None
    author: Optional[str] = None
    file_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentChunk(BaseModel):
    """Core document chunk schema."""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: DocumentMetadata


class DocumentSearchResult(BaseModel):
    """Search result returned from document search."""
    id: str
    content: str
    similarity_score: float
    metadata: DocumentMetadata


class DocumentService:
    """Service layer for document processing and retrieval."""
    
    def __init__(self):
        # Mock vector database storage
        self.vector_store: List[DocumentChunk] = []
        self.document_index: dict = {}
        
        # Set up storage directory
        self.storage_dir = Path(__file__).parent.parent / "storage" / "uploads"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_chunk_id(self, document_id: str, chunk_index: int) -> str:
        """Generate unique ID for document chunk."""
        hash_input = f"{document_id}_{chunk_index}_{datetime.utcnow().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def _generate_mock_embedding(self, text: str) -> List[float]:
        """Generate mock embedding vector from text."""
        # Simple hash-based mock embedding (384-dimensional)
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        return [(hash_val >> i) % 100 / 100.0 for i in range(384)]
    
    def _split_into_chunks(self, text: str, chunk_size: int = 500) -> List[str]:
        """Split document text into chunks."""
        chunks = []
        words = text.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            current_chunk.append(word)
            current_length += len(word) + 1
            
            if current_length >= chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _compute_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a ** 2 for a in vec1) ** 0.5
        norm2 = sum(b ** 2 for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _save_file(self, filename: str, file_content: bytes) -> str:
        """
        Save file to storage/uploads directory with collision handling.
        
        Args:
            filename: Original filename
            file_content: Raw file content as bytes
        
        Returns:
            Relative path to saved file
        """
        file_path = self.storage_dir / filename
        
        # Handle filename collisions by appending UUID
        if file_path.exists():
            name_parts = filename.rsplit(".", 1)
            if len(name_parts) == 2:
                base_name, extension = name_parts
                filename = f"{base_name}_{uuid.uuid4().hex[:8]}.{extension}"
            else:
                filename = f"{filename}_{uuid.uuid4().hex[:8]}"
            file_path = self.storage_dir / filename
        
        # Write file to disk
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # Return relative path
        return f"storage/uploads/{filename}"
    
    def process_and_store(
        self,
        document_text: str,
        metadata: dict,
        file_content: Optional[bytes] = None,
        filename: Optional[str] = None
    ) -> dict:
        """
        Process document text into chunks and store with embeddings.
        
        Args:
            document_text: Raw document text to process
            metadata: Dict with keys: title, document_id, source_url, author
            file_content: Optional raw file content as bytes to save locally
            filename: Optional filename for saving the raw file
        
        Returns:
            Dictionary with processing status, chunk IDs, and file path
        """
        document_id = metadata.get("document_id")
        file_path = None
        
        # Save raw file if content and filename provided
        if file_content is not None and filename is not None:
            file_path = self._save_file(filename, file_content)
        
        chunks = self._split_into_chunks(document_text)
        stored_chunks = []
        
        for chunk_index, chunk_text in enumerate(chunks):
            chunk_id = self._generate_chunk_id(document_id, chunk_index)
            embedding = self._generate_mock_embedding(chunk_text)
            
            doc_chunk = DocumentChunk(
                id=chunk_id,
                content=chunk_text,
                embedding=embedding,
                metadata=DocumentMetadata(
                    document_id=document_id,
                    title=metadata.get("title", "Untitled"),
                    chunk_index=chunk_index,
                    source_url=metadata.get("source_url"),
                    author=metadata.get("author"),
                    file_path=file_path
                )
            )
            
            # Store in mock vector database
            self.vector_store.append(doc_chunk)
            stored_chunks.append(chunk_id)
        
        # Index document for quick lookup
        self.document_index[document_id] = {
            "chunk_ids": stored_chunks,
            "total_chunks": len(chunks),
            "file_path": file_path,
            "stored_at": datetime.utcnow().isoformat()
        }
        
        return {
            "document_id": document_id,
            "chunks_stored": len(stored_chunks),
            "chunk_ids": stored_chunks,
            "file_path": file_path
        }
    
    def search(
        self,
        query_text: str,
        top_k: int = 5
    ) -> List[DocumentSearchResult]:
        """
        Search for documents using vector similarity.
        
        Args:
            query_text: Query text to search for
            top_k: Number of top results to return
        
        Returns:
            List of DocumentSearchResult sorted by similarity score
        """
        query_embedding = self._generate_mock_embedding(query_text)
        scored_results = []
        
        for chunk in self.vector_store:
            if chunk.embedding:
                similarity = self._compute_similarity(
                    query_embedding,
                    chunk.embedding
                )
                scored_results.append({
                    "chunk": chunk,
                    "score": similarity
                })
        
        # Sort by similarity score descending
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        
        # Return top_k results
        results = [
            DocumentSearchResult(
                id=item["chunk"].id,
                content=item["chunk"].content,
                similarity_score=item["score"],
                metadata=item["chunk"].metadata
            )
            for item in scored_results[:top_k]
        ]
        
        return results
