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
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """Upload a PDF or text document to the RAG knowledge base."""
    import uuid

    from sqlalchemy import select

    from app.models.database import Document as DocumentModel, User

    # Step 1: Resolve user's organization_id from DB
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(current_user.user_id))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    organization_id = str(user.organization_id)
    document_id = str(uuid.uuid4())

    # Step 2: Read file content
    content = await file.read()

    if file.content_type == "application/pdf":
        import io

        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content))
        document_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        document_text = content.decode("utf-8", errors="ignore")

    # Step 3: Process and store vectors in Pinecone
    rag_result = await service.process_and_store(
        document_text=document_text,
        metadata={
            "title": title,
            "document_id": document_id,
            "source_url": source_url,
            "author": author,
        },
        file_content=content,
        filename=file.filename,
        organization_id=organization_id,
        uploaded_by=current_user.user_id,
    )

    # Step 4: Save Document record to PostgreSQL
    doc_record = DocumentModel(
        id=uuid.UUID(document_id),
        title=title,
        source_url=source_url or None,
        author=author or None,
        organization_id=user.organization_id,
        is_processed=True,
        chunks_count=rag_result.get("chunks_stored", 0),
        mime_type=file.content_type,
        file_size_bytes=len(content),
        file_path=rag_result.get("file_path"),
        is_active=True,
        is_verified=False,
        authority_score=0.5,
    )
    db.add(doc_record)
    await db.commit()

    return {
        "document_id": document_id,
        "chunks_stored": rag_result.get("chunks_stored", 0),
        "chunk_ids": rag_result.get("chunk_ids", []),
        "file_path": rag_result.get("file_path"),
        "title": title,
        "message": "Document uploaded and processed successfully",
    }


@router.get("", response_model=dict, summary="List documents")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: UserIdentity = Depends(get_current_user),
):
    """List all documents in the organization's knowledge base."""
    import uuid

    from sqlalchemy import desc, func, select

    from app.models.database import Document, User

    user_result = await db.execute(
        select(User).where(User.id == uuid.UUID(current_user.user_id))
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.organization_id == user.organization_id,
            Document.is_active == True,  # noqa: E712
        )
    )
    total = count_result.scalar() or 0

    docs_result = await db.execute(
        select(Document)
        .where(
            Document.organization_id == user.organization_id,
            Document.is_active == True,  # noqa: E712
        )
        .order_by(desc(Document.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    docs = docs_result.scalars().all()

    return {
        "items": [
            {
                "id": str(d.id),
                "title": d.title,
                "source_url": d.source_url,
                "author": d.author,
                "is_processed": d.is_processed,
                "chunks_count": d.chunks_count,
                "mime_type": d.mime_type,
                "file_size_bytes": d.file_size_bytes,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
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
