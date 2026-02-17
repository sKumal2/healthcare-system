from fastapi import APIRouter, Depends
from app.models.schemas import QueryResponse, QueryRequest
from app.services.query_service import QueryService

router = APIRouter()

def get_current_user():
    return{
        "user_id": 1,
        "organization_id": 1,
    }

@router.post("/conversations/{conversation_id}/messages", 
             response_model=QueryResponse)
def send_message(
    conversation_id: str,
    request: QueryRequest,
    user= Depends(get_current_user),
):
    service = QueryService()

    result = service.processQuery(
        conversation_id=conversation_id,
        user_id=user["user_id"],
        organization_id=user["organization_id"],
        query=request.content,
        #look into .content, seems odd here
    )

    return result
    



