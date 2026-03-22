from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

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


# Admin Service Schemas
class UserData(BaseModel):
    """User data model."""
    user_id: int
    name: str
    email: str
    role: str
    created_at: datetime


class AnalyticsData(BaseModel):
    """Analytics data model."""
    total_users: int
    total_documents: int
    total_queries: int


class AuditLog(BaseModel):
    """Audit log entry model."""
    log_id: str
    action: str
    user_id: int
    timestamp: datetime
    details: Optional[str] = None



