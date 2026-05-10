from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth
from app.api.v1.endpoints import admin, documents, queries
from app.db.session import get_db

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(queries.router)
api_router.include_router(admin.router)
api_router.include_router(documents.router)


@api_router.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ok", "database": db_status}


@api_router.get("/health/llm", tags=["Health"])
async def llm_health():
    """Report which LLM provider is active and which API keys are configured."""
    from app.core.config import settings

    provider = (settings.LLM_PROVIDER or "anthropic").lower().strip()
    model = settings.GEMINI_MODEL if provider == "gemini" else settings.LLM_MODEL
    return {
        "provider": provider,
        "model": model,
        "anthropic_key_set": bool(settings.ANTHROPIC_API_KEY),
        "gemini_key_set": bool(settings.GEMINI_API_KEY),
    }
