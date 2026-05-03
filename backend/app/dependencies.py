"""FastAPI dependency providers for service classes.

Routers should depend on these factories rather than instantiating the
services manually so async sessions, the vector DB client, and the LLM
client all flow through one place.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.core.config import settings
from app.db.vector_db import VectorDBClient, get_vector_db_client
from app.rag.llm_client import LLMClient
from app.services.document_service import DocumentService
from app.services.query_service import QueryService


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient(
        api_key=settings.ANTHROPIC_API_KEY,
        model=settings.LLM_MODEL,
    )


def get_document_service(
    vector_db: VectorDBClient = Depends(get_vector_db_client),
) -> DocumentService:
    return DocumentService(vector_db=vector_db)


def get_query_service(
    document_service: DocumentService = Depends(get_document_service),
    llm_client: LLMClient = Depends(get_llm_client),
) -> QueryService:
    return QueryService(
        document_service=document_service,
        llm_client=llm_client,
    )
