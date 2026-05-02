# app/core/config.py
"""Application settings loaded from environment / .env via Pydantic Settings."""

from __future__ import annotations

from typing import List, Union

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for the Healthcare RAG backend."""

    BACKEND_CORS_ORIGINS: Union[List[AnyHttpUrl], str] = []

    # ----- Vector DB -----
    VECTOR_DB_PROVIDER: str = "pinecone"  # "pinecone" | "weaviate"
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "healthcare-rag"
    WEAVIATE_URL: str = "http://localhost:8080"

    # ----- LLM -----
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    MAX_PROMPT_TOKENS: int = 6000

    # ----- RAG Tuning -----
    TOP_K_RETRIEVAL: int = 10
    TOP_K_FINAL: int = 5
    MIN_VALID_SOURCES: int = 2
    MIN_CONFIDENCE_SCORE: float = 0.7
    CACHE_TTL_SECONDS: int = 300

    # ----- Source Allowlist -----
    TRUSTED_DOMAINS: str = (
        "cdc.gov,who.int,pubmed.ncbi.nlm.nih.gov,fda.gov,nih.gov,"
        "mayoclinic.org,clevelandclinic.org,medlineplus.gov"
    )

    @property
    def trusted_domains_list(self) -> list[str]:
        """Parse the comma-separated allowlist into a clean list of domains."""
        return [d.strip().lower() for d in self.TRUSTED_DOMAINS.split(",") if d.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
