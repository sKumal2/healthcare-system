"""SQLAlchemy session factories and FastAPI dependencies.

Provides both sync (legacy) and async sessions. The async session is the
default for new service code (admin / document / query). The sync session
is preserved for callers that have not been migrated yet.

DSN is assembled from the ``POSTGRES_*`` env vars unless ``DATABASE_URL``
is set explicitly.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker


def _sync_database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    user = os.getenv("POSTGRES_USER", "healthcare_user")
    password = os.getenv("POSTGRES_PASSWORD", "healthcare_password")
    host = os.getenv("POSTGRES_SERVER", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "healthcare_db")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def _async_database_url() -> str:
    explicit = os.getenv("DATABASE_URL_ASYNC")
    if explicit:
        return explicit
    sync_url = _sync_database_url()
    return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


_engine = None
_SessionLocal: sessionmaker | None = None
_async_engine = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def _ensure_sync_engine() -> sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = create_engine(_sync_database_url(), pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_engine, future=True
        )
    return _SessionLocal


def _ensure_async_engine() -> async_sessionmaker[AsyncSession]:
    global _async_engine, _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _async_engine = create_async_engine(_async_database_url(), pool_pre_ping=True)
        _AsyncSessionLocal = async_sessionmaker(
            bind=_async_engine, expire_on_commit=False, autoflush=False
        )
    return _AsyncSessionLocal


def get_sync_db() -> Generator[Session, None, None]:
    """Legacy sync session dependency (use ``get_db`` for new code)."""
    SessionLocal = _ensure_sync_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an :class:`AsyncSession`."""
    SessionLocal = _ensure_async_engine()
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
