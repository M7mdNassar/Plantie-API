# src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Settings(BaseSettings):
    APP_NAME: str = "Plantie AI Backend"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    # Gemini
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "models/gemini-flash-latest"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # Embedding
    EMBEDDING_PROVIDER: str = "fastembed"
    FASTEMBED_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-001"  # for fallback

    # RAG
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200
    RAG_TOP_K: int = 5
    RAG_MIN_RELEVANCE_SCORE: float = 0.7

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_PERIOD: int = 60

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    @property
    def gemini_api_key(self) -> str:
        return self.GEMINI_API_KEY or self.OPENAI_API_KEY


@lru_cache()
def get_settings() -> Settings:
    return Settings()