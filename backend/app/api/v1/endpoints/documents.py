from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
from app.services.document_service import (
    DocumentService,
    DocumentSearchResult
)


router = APIRouter(prefix="/documents", tags=["documents"])


class UploadDocumentRequest(BaseModel):
    """Request model for document upload."""
    title: str
    content: str
    document_id: str
    source_url: Optional[str] = None
    author: Optional[str] = None


class UploadDocumentResponse(BaseModel):
    """Response model for document upload."""
    document_id: str
    chunks_stored: int
    chunk_ids: List[str]
    message: str


class SearchDocumentRequest(BaseModel):
    """Request model for document search."""
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class SearchDocumentResponse(BaseModel):
    """Response model for document search."""
    query: str
    results: List[DocumentSearchResult]
    total_results: int


def get_document_service() -> DocumentService:
    """Dependency injection for DocumentService."""
    return DocumentService()


@router.post(
    "/upload",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED
)
async def upload_document(
    request: UploadDocumentRequest,
    service: DocumentService = Depends(get_document_service)
) -> UploadDocumentResponse:
    """
    Upload and process a document.
    
    - **title**: Document title
    - **content**: Document text content
    - **document_id**: Unique identifier for the document
    - **source_url**: Optional URL where document was sourced
    - **author**: Optional document author
    """
    try:
        result = service.process_and_store(
            document_text=request.content,
            metadata={
                "title": request.title,
                "document_id": request.document_id,
                "source_url": request.source_url,
                "author": request.author
            }
        )
        
        return UploadDocumentResponse(
            document_id=result["document_id"],
            chunks_stored=result["chunks_stored"],
            chunk_ids=result["chunk_ids"],
            message=f"Document processed successfully into {result['chunks_stored']} chunks"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process document: {str(e)}"
        )


@router.post(
    "/search",
    response_model=SearchDocumentResponse,
    status_code=status.HTTP_200_OK
)
async def search_documents(
    request: SearchDocumentRequest,
    service: DocumentService = Depends(get_document_service)
) -> SearchDocumentResponse:
    """
    Search for documents using vector similarity.
    
    - **query**: Search query text
    - **top_k**: Number of results to return (default: 5, max: 50)
    """
    try:
        results = service.search(
            query_text=request.query,
            top_k=request.top_k
        )
        
        return SearchDocumentResponse(
            query=request.query,
            results=results,
            total_results=len(results)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )
