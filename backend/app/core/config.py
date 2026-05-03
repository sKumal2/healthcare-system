# app/core/config.py
"""Application settings loaded from environment / .env via Pydantic Settings."""

from __future__ import annotations

from typing import List, Union

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for the Healthcare RAG backend."""

    # ----- Application -----
    PROJECT_NAME: str = "Healthcare RAG System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # ----- Auth / JWT -----
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ----- Redis -----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ----- CORS -----
    BACKEND_CORS_ORIGINS: Union[List[AnyHttpUrl], List[str], str] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        """Allow JSON-array or comma-separated origins from env."""
        if isinstance(v, str) and not v.startswith("["):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # ----- Rate Limiting -----
    RATE_LIMIT_USER_REQUESTS: int = 100
    RATE_LIMIT_USER_WINDOW_SECONDS: int = 60
    RATE_LIMIT_IP_REQUESTS: int = 20
    RATE_LIMIT_IP_WINDOW_SECONDS: int = 60
    RATE_LIMIT_ADMIN_REQUESTS: int = 300

    # ----- Request Validation -----
    MAX_REQUEST_SIZE_BYTES: int = 1_048_576  # 1MB

    # ----- Security -----
    ADMIN_IP_ALLOWLIST: str = ""  # comma-separated CIDRs, empty = disabled

    # ----- Vector DB -----
    VECTOR_DB_PROVIDER: str = "pinecone"  # "pinecone" | "weaviate" | "local"
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "healthcare-rag"
    WEAVIATE_URL: str = "http://localhost:8080"

    # ----- Object Storage (AWS S3) -----
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = ""

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

    @property
    def admin_ip_allowlist_cidrs(self) -> list[str]:
        """Parse the comma-separated admin IP allowlist into clean CIDR strings."""
        return [c.strip() for c in self.ADMIN_IP_ALLOWLIST.split(",") if c.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
