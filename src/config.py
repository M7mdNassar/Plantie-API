from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional
import os
from dotenv import load_dotenv

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

    # Gemini (fallback)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "models/gemini-1.5-flash"

    # Mistral
    MISTRAL_API_KEY: Optional[str] = None
    MISTRAL_MODEL: str = "mistral-small-latest"

    # LLM Provider: "mistral" or "gemini"
    LLM_PROVIDER: str = "mistral"

    # Embedding (always local fastembed)
    EMBEDDING_PROVIDER: str = "fastembed"
    FASTEMBED_MODEL: str = "BAAI/bge-small-en-v1.5"

    # RAG
    RAG_TOP_K: int = 2
    RAG_MAX_HISTORY: int = 1
    SKIP_RETRIEVAL_FOR_SHORT_QUERIES: bool = True
    SHORT_QUERY_THRESHOLD: int = 20

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_PERIOD: int = 60

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    @property
    def gemini_api_key(self) -> str:
        return self.GEMINI_API_KEY

@lru_cache()
def get_settings() -> Settings:
    return Settings()