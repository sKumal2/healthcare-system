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
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
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

    from app.models.database import Query as QueryModel, User

    result = await db.execute(select(User).where(User.id == _uuid.UUID(current_user.user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    organization_id = str(user.organization_id)
    request.user_id = current_user.user_id
    request.session_id = request.session_id or str(_uuid.uuid4())

    response = await service.ask_question(request, organization_id=organization_id)

    # Persist to DB — never break the response on failure.
    try:
        query_record = QueryModel(
            query_id=response.query_id,
            question=request.question,
            answer=response.answer,
            session_id=request.session_id,
            confidence_score=response.confidence_score if response.confidence_score is not None else 0.0,
            processing_time_ms=response.processing_time_ms if response.processing_time_ms is not None else 0,
            sources_count=len(response.sources),
            input_tokens=response.tokens_used,
            output_tokens=None,
            user_id=_uuid.UUID(current_user.user_id),
            organization_id=user.organization_id,
        )
        db.add(query_record)
        await db.commit()
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).error("Failed to save query to DB: %s", exc)

    return response


@router.get("", response_model=dict, summary="List past queries")
async def list_queries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """List the current user's past queries with pagination."""
    import uuid as _uuid
    from sqlalchemy import desc, func, select

    from app.models.database import Query as QueryModel, User

    user_result = await db.execute(
        select(User).where(User.id == _uuid.UUID(current_user.user_id))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    base_filter = QueryModel.user_id == user.id
    if session_id:
        base_filter = base_filter & (QueryModel.session_id == session_id)

    count_result = await db.execute(
        select(func.count(QueryModel.id)).where(base_filter)
    )
    total = count_result.scalar() or 0

    stmt = (
        select(QueryModel)
        .where(base_filter)
        .order_by(desc(QueryModel.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    queries = result.scalars().all()

    return {
        "items": [
            {
                "query_id": q.query_id,
                "question": q.question,
                "answer": q.answer,
                "confidence_score": q.confidence_score,
                "processing_time_ms": q.processing_time_ms,
                "sources_count": q.sources_count,
                "session_id": q.session_id,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in queries
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
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
