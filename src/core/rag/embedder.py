
"""Wraps whichever embedding provider is configured.

Loading the model (fastembed) or configuring the SDK (gemini) is real work —
this class must be constructed exactly ONCE, at app startup, and reused for
every request. See src/main.py's lifespan.
"""

import asyncio
from typing import List

from src.config import get_settings
from src.utils.logging import get_logger

settings = get_settings()
logger = get_logger()


class Embedder:
    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER
        self.embedding_dim = 384

        if self.provider == "fastembed":
            from fastembed import TextEmbedding

            self.model = TextEmbedding(
                model_name=settings.FASTEMBED_MODEL,
                cache_dir=settings.FASTEMBED_CACHE_DIR,
            )
            logger.info(
                f"Loaded local embedding model: {settings.FASTEMBED_MODEL} "
                f"(dim={self.embedding_dim})"
            )
        elif self.provider == "gemini":
            import google.generativeai as genai

            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY is required for EMBEDDING_PROVIDER=gemini")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai
            self.embedding_dim = self._get_gemini_dimension()
            logger.info(
                f"Using Gemini embedding model: {settings.GEMINI_EMBEDDING_MODEL} "
                f"(dim={self.embedding_dim})"
            )
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def _get_gemini_dimension(self) -> int:
        try:
            res = self.model.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                content="test",
                task_type="retrieval_document",
            )
            return len(res["embedding"])
        except Exception as e:
            logger.warning(f"Could not determine Gemini embedding dimension, defaulting to 3072: {e}")
            return 3072

    # ---- Sync methods ----
    def get_embedding(self, text: str) -> List[float]:
        return self.get_embeddings_batch([text])[0]

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.provider == "fastembed":
            embeddings = list(self.model.embed(texts))
            return [emb.tolist() for emb in embeddings]
        elif self.provider == "gemini":
            return self._gemini_batch(texts)
        raise ValueError("Unknown provider")

    # ---- Async wrappers (offload CPU/blocking work to a thread) ----
    async def get_embedding_async(self, text: str) -> List[float]:
        return await asyncio.to_thread(self.get_embedding, text)

    async def get_embeddings_batch_async(self, texts: List[str]) -> List[List[float]]:
        return await asyncio.to_thread(self.get_embeddings_batch, texts)

    def _gemini_batch(self, texts: List[str]) -> List[List[float]]:
        import random
        import re
        import time

        from google.api_core.exceptions import ResourceExhausted

        retries = 5
        for attempt in range(retries):
            try:
                result = self.model.embed_content(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    content=texts,
                    task_type="retrieval_document",
                )
                return result["embedding"]
            except ResourceExhausted as e:
                if attempt == retries - 1:
                    raise
                msg = str(e)
                delay_match = re.search(r"retry in ([\d.]+)s", msg)
                wait = (
                    float(delay_match.group(1)) + random.uniform(0, 1)
                    if delay_match
                    else (2**attempt) + random.uniform(0, 1)
                )
                logger.warning(f"Gemini rate limited, retry {attempt + 1}/{retries} in {wait:.2f}s")
                time.sleep(wait)
            except Exception as e:
                if attempt == retries - 1:
                    raise
                wait = (2**attempt) + random.uniform(0, 1)
                logger.warning(f"Gemini embedding error, retry {attempt + 1}/{retries} in {wait:.2f}s: {e}")
                time.sleep(wait)
        return []