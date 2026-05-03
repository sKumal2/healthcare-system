"""
Document management endpoints — upload and manage healthcare reference documents.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_document_service
from app.gateway.auth.dependencies import get_current_user, require_role
from app.gateway.auth.models import UserIdentity
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
    import uuid

    content = await file.read()
    result = await service.process_and_store(
        document_text=content.decode("utf-8", errors="ignore"),
        metadata={
            "title": title,
            "document_id": str(uuid.uuid4()),
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
    from sqlalchemy import desc, select

    from app.models.database import Document

    stmt = (
        select(Document)
        .where(Document.is_active == True)  # noqa: E712
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
