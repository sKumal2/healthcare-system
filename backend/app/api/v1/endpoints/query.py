from fastapi import APIRouter, Depends, HTTPException, status
from app.services.query_service import (
    QueryService,
    QueryRequest,
    QueryResponse
)


router = APIRouter(prefix="/queries", tags=["queries"])


def get_query_service() -> QueryService:
    """Dependency injection for QueryService."""
    return QueryService()


@router.post(
    "/ask",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK
)
async def ask_question(
    request: QueryRequest,
    service: QueryService = Depends(get_query_service)
) -> QueryResponse:
    """
    Ask a question and get an answer with sources using RAG.
    
    - **question**: The question to ask (required)
    - **top_k**: Number of document chunks to retrieve as context (default: 5, max: 20)
    
    Returns a QueryResponse with:
    - **answer**: Generated answer based on retrieved context
    - **sources**: List of source documents cited in the answer
    - **generated_at**: Timestamp when the response was generated
    """
    try:
        result = service.ask_question(request)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process question: {str(e)}"
        )
