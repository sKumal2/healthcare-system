# Fix API Routers — Claude Code Prompt

## Context

Healthcare RAG System, FastAPI backend. The Swagger UI at `/docs` shows a blank page
because the routers have several critical issues. Fix all of them without changing any
business logic or service layer code.

---

## Problems to Fix

### Problem 1 — Admin router has double prefix

`app/api/v1/endpoints/admin.py` defines:
```python
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
```

But `main.py` already adds `/api/v1` via:
```python
app.include_router(api_router, prefix=settings.API_V1_STR)  # API_V1_STR = "/api/v1"
```

So admin routes become `/api/v1/api/v1/admin/...` — completely broken.

**Fix:** Change the prefix in `admin.py` to just:
```python
router = APIRouter(prefix="/admin", tags=["Admin"])
```

### Problem 2 — Admin router uses wrong DB session and wrong auth

`admin.py` has:
```python
from sqlalchemy.orm import Session  # sync session — wrong
from app.core.security import get_current_user  # wrong import path

def get_db():
    pass  # returns None — will crash on every request
```

**Fix:** Replace the dependency section at the top of `admin.py` with:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.gateway.auth.dependencies import get_current_user, require_role
from app.gateway.auth.models import UserIdentity
```

Replace `get_db`, `require_admin`, and `get_admin_service` with:
```python
def require_admin(current_user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def get_admin_service(
    db: AsyncSession = Depends(get_db),
    admin: UserIdentity = Depends(require_admin),
) -> AdminService:
    return AdminService(session=db, current_admin=admin)
```

Also update all endpoint signatures to use `UserIdentity` instead of `User` where the
admin dependency is used.

### Problem 3 — Admin `get_user` endpoint returns 501

```python
@router.get("/users/{user_id}")
async def get_user(...):
    raise HTTPException(status_code=501, detail="Use /users endpoint with filters")
```

This is a placeholder that will always fail. Replace with a real implementation:
```python
@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    service: AdminService = Depends(get_admin_service),
):
    return await service.get_user_by_id(user_id)
```

Note: Also add `get_user_by_id(user_id: int)` method to `AdminService` that does:
```python
async def get_user_by_id(self, user_id: int):
    result = await self.session.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### Problem 4 — Queries router is completely wrong

`app/api/v1/endpoints/queries.py` currently has:
```python
# Wrong route — healthcare RAG doesn't have "conversations"
@router.post("/conversations/{conversation_id}/messages")

# Fake auth
def get_current_user():
    return {"user_id": 1, "organization_id": 1}

# Wrong method name
service.processQuery(...)
```

**Fix:** Rewrite `queries.py` completely:
```python
"""
Query endpoints — ask healthcare questions via the RAG pipeline.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.gateway.auth.dependencies import get_current_user
from app.gateway.auth.models import UserIdentity
from app.services.query_service import QueryService, QueryRequest, QueryResponse
from app.dependencies import get_query_service

router = APIRouter(prefix="/queries", tags=["Queries"])


@router.post("", response_model=QueryResponse, summary="Ask a healthcare question")
async def ask_question(
    request: QueryRequest,
    service: QueryService = Depends(get_query_service),
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
    request.user_id = current_user.user_id
    return await service.ask_question(request)


@router.get("", response_model=dict, summary="List past queries")
async def list_queries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """
    List the current user's past queries with pagination.
    """
    from sqlalchemy import select, desc
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
    """
    Get a specific past query by its query_id.
    """
    from sqlalchemy import select
    from app.models.database import Query as QueryModel
    from fastapi import HTTPException, status

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
    """
    Submit feedback on a query result (helpful, not_helpful, etc.)
    """
    from sqlalchemy import select
    from app.models.database import Query as QueryModel, QueryFeedback
    from app.models.enums import QueryFeedbackEnum
    from fastapi import HTTPException, status

    # Verify query exists and belongs to user
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
```

### Problem 5 — Documents router not registered at all

`app/api/v1/endpoints/documents.py` exists but is never added to `router.py`.

**Fix:** Update `app/api/v1/router.py`:
```python
from fastapi import APIRouter
from app.api.v1 import auth
from app.api.v1.endpoints import admin, queries, documents

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(queries.router)
api_router.include_router(admin.router)
api_router.include_router(documents.router)
```

Then check `documents.py` — if it has wrong prefix or missing routes, apply the same
fixes as above: correct prefix to `/documents`, use real auth dependency, use async DB.

### Problem 6 — Auth router uses sync DB session for login

`auth.py` login endpoint uses:
```python
db: Session = Depends(get_db)          # sync Session
db.query(User).filter(...).first()     # sync query
```

But `get_db` from `app.db.session` yields an `AsyncSession`.

**Fix:** Update the login endpoint to use async:
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def _lookup_user(db: AsyncSession, username: str):
    result = await db.execute(
        select(User).where(User.email == username)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    return str(user.id), role_value, user.password_hash, bool(user.is_active)

@router.post("/login", response_model=TokenPair)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    record = await _lookup_user(db, form_data.username)
    ...
```

### Problem 7 — Add missing `/health` endpoint with DB check to main router

Add to `app/api/v1/router.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db

@api_router.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ok", "database": db_status}
```

---

## Add Missing Documents Router

If `app/api/v1/endpoints/documents.py` is incomplete, rewrite it with these endpoints:

```python
"""
Document management endpoints — upload and manage healthcare reference documents.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.gateway.auth.dependencies import get_current_user, require_role
from app.gateway.auth.models import UserIdentity
from app.dependencies import get_document_service
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])
require_admin = require_role("admin")


@router.post("", response_model=dict, summary="Upload a healthcare document")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    source_url: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    service: DocumentService = Depends(get_document_service),
    current_user: UserIdentity = Depends(get_current_user),
):
    """Upload a PDF or text document to the RAG knowledge base."""
    content = await file.read()
    result = await service.process_and_store(
        document_text=content.decode("utf-8", errors="ignore"),
        metadata={
            "title": title,
            "document_id": str(__import__("uuid").uuid4()),
            "source_url": source_url,
            "author": author,
        },
        file_content=content,
        filename=file.filename,
        organization_id=current_user.user_id,
        uploaded_by=current_user.user_id,
    )
    return result


@router.get("", response_model=dict, summary="List documents")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """List all documents in the organization's knowledge base."""
    from sqlalchemy import select, desc
    from app.models.database import Document

    stmt = (
        select(Document)
        .where(Document.is_active == True)
        .order_by(desc(Document.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    docs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(d.id),
                "title": d.title,
                "source_url": d.source_url,
                "is_processed": d.is_processed,
                "chunks_count": d.chunks_count,
                "created_at": d.created_at,
            }
            for d in docs
        ],
        "page": page,
        "page_size": page_size,
    }


@router.delete("/{document_id}", response_model=dict, summary="Delete a document")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(require_admin),
):
    """Soft-delete a document from the knowledge base (admin only)."""
    from sqlalchemy import select
    from app.models.database import Document

    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.is_active = False
    await db.commit()
    return {"detail": "Document deleted successfully"}
```

---

## Definition of Done

- [ ] `http://localhost:8000/docs` shows all endpoints — not blank
- [ ] Auth endpoints visible: `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- [ ] Query endpoints visible: `POST /queries`, `GET /queries`, `GET /queries/{query_id}`, `POST /queries/{query_id}/feedback`
- [ ] Document endpoints visible: `POST /documents`, `GET /documents`, `DELETE /documents/{document_id}`
- [ ] Admin endpoints visible with correct paths (`/admin/users` not `/api/v1/admin/users`)
- [ ] Health endpoint visible: `GET /health`
- [ ] No sync DB calls anywhere in routers — all use `AsyncSession`
- [ ] No fake `get_current_user` returning hardcoded dict — all use real gateway auth
- [ ] Running `python -c "from app.api.v1.router import api_router; print(len(api_router.routes))"` prints more than 5