from pydantic import BaseModel
from typing import List, Optional

class QueryRequest(BaseModel):
    query: str
    stream: Optional[bool] = False

class Citation(BaseModel):
    document_id: str
    source: str 
    page_numner: Optional[int]

class QueryResponse(BaseModel):
    message_id: str 
    response: str 
    citations: List[Citation]
    tokens_used: int



