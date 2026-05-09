"""
Query endpoints — ask healthcare questions via the RAG pipeline.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_query_service
from app.gateway.auth.dependencies import get_current_user
from app.gateway.auth.models import UserIdentity
from app.services.query_service import QueryRequest, QueryResponse, QueryService

router = APIRouter(prefix="/queries", tags=["Queries"])


@router.post("", response_model=QueryResponse, summary="Ask a healthcare question")
async def ask_question(
    request: QueryRequest,
    service: QueryService = Depends(get_query_service),
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a healthcare question and get an answer backed by verified sources.

    The RAG pipeline will:
    1. Parse and expand the query with medical terminology
    2. Retrieve relevant chunks from verified healthcare documents
    3. Re-rank by source authority (CDC, WHO, FDA, etc.)
    4. Generate a cited answer with medical disclaimer
    """
    import uuid as _uuid
    from sqlalchemy import select

    from app.models.database import User

    result = await db.execute(select(User).where(User.id == _uuid.UUID(current_user.user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    request.user_id = current_user.user_id
    return await service.ask_question(request, organization_id=str(user.organization_id))


@router.get("", response_model=dict, summary="List past queries")
async def list_queries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """List the current user's past queries with pagination."""
    from sqlalchemy import desc, select

    from app.models.database import Query as QueryModel

    stmt = (
        select(QueryModel)
        .where(QueryModel.user_id == current_user.user_id)
        .order_by(desc(QueryModel.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if session_id:
        stmt = stmt.where(QueryModel.session_id == session_id)

    result = await db.execute(stmt)
    queries = result.scalars().all()

    return {
        "items": [
            {
                "query_id": q.query_id,
                "question": q.question,
                "answer": q.answer,
                "confidence_score": q.confidence_score,
                "created_at": q.created_at,
            }
            for q in queries
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{query_id}", response_model=dict, summary="Get a specific query result")
async def get_query(
    query_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """Get a specific past query by its query_id."""
    from sqlalchemy import select

    from app.models.database import Query as QueryModel

    result = await db.execute(
        select(QueryModel).where(
            QueryModel.query_id == query_id,
            QueryModel.user_id == current_user.user_id,
        )
    )
    query = result.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")

    return {
        "query_id": query.query_id,
        "question": query.question,
        "answer": query.answer,
        "confidence_score": query.confidence_score,
        "processing_time_ms": query.processing_time_ms,
        "created_at": query.created_at,
    }


@router.post("/{query_id}/feedback", response_model=dict, summary="Submit feedback on a query")
async def submit_feedback(
    query_id: str,
    feedback_type: str,
    comment: Optional[str] = None,
    rating: Optional[int] = Query(None, ge=1, le=5),
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """Submit feedback on a query result (helpful, not_helpful, etc.)"""
    from sqlalchemy import select

    from app.models.database import Query as QueryModel, QueryFeedback
    from app.models.enums import QueryFeedbackEnum

    result = await db.execute(
        select(QueryModel).where(
            QueryModel.query_id == query_id,
            QueryModel.user_id == current_user.user_id,
        )
    )
    query = result.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    feedback = QueryFeedback(
        query_id=query.id,
        user_id=current_user.user_id,
        feedback_type=QueryFeedbackEnum(feedback_type),
        feedback_comment=comment,
        rating=rating,
        was_helpful=feedback_type == "helpful",
    )
    db.add(feedback)
    await db.commit()

    return {"detail": "Feedback submitted successfully"}
