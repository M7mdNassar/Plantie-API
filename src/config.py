# src/config.py
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────
    APP_NAME: str = "Plantie AI Backend"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # ── Supabase ─────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    # ── Gemini (fallback LLM + fallback embeddings) ─────────────────────
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "models/gemini-1.5-flash-8b"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # ── Mistral (primary LLM) ───────────────────────────────────────────
    MISTRAL_API_KEY: Optional[str] = None
    MISTRAL_MODEL: str = "mistral-small-latest"
    LLM_PROVIDER: str = "gemini"  # "mistral" | "gemini"

    # ── Embeddings (local, always fastembed) ────────────────────────────
    EMBEDDING_PROVIDER: str = "fastembed"
    FASTEMBED_MODEL: str = "BAAI/bge-small-en-v1.5"
    FASTEMBED_CACHE_DIR: str = "/app/.fastembed_cache"

    # ── RAG ──────────────────────────────────────────────────────────────
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200
    RAG_TOP_K: int = 5
    RAG_MIN_RELEVANCE_SCORE: float = 0.7
    RAG_MAX_HISTORY: int = 5
    SKIP_RETRIEVAL_FOR_SHORT_QUERIES: bool = True
    SHORT_QUERY_THRESHOLD: int = 20

    # ── Rate limiting ────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_PERIOD: int = 60

    # ── Logging ──────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def gemini_api_key(self) -> Optional[str]:
        return self.GEMINI_API_KEY


@lru_cache()
def get_settings() -> Settings:
    return Settings()