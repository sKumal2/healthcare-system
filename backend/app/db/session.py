"""SQLAlchemy session factory and FastAPI dependency.

The healthcare backend uses a synchronous SQLAlchemy engine because the
RAG and admin services are already written against `Session`. The DSN is
assembled from the `POSTGRES_*` env vars (read directly from os.environ to
avoid re-shaping the public Settings object).
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    user = os.getenv("POSTGRES_USER", "healthcare_user")
    password = os.getenv("POSTGRES_PASSWORD", "healthcare_password")
    host = os.getenv("POSTGRES_SERVER", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "healthcare_db")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


_engine = None
_SessionLocal: sessionmaker | None = None


def _ensure_engine() -> sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine, future=True)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session and closes it after."""
    SessionLocal = _ensure_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
