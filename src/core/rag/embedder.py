from typing import List
import time
from src.config import get_settings

settings = get_settings()

class Embedder:
    def __init__(self):
        self.provider = settings.EMBEDDING_PROVIDER
        self.embedding_dim = 384  # BGE-small-en-v1.5 outputs 384

        if self.provider == "fastembed":
            from fastembed import TextEmbedding
            self.model = TextEmbedding(model_name=settings.FASTEMBED_MODEL)
            print(f"✅ Using local embedding model: {settings.FASTEMBED_MODEL} (dim={self.embedding_dim})")
        elif self.provider == "gemini":
            import google.generativeai as genai
            api_key = settings.gemini_api_key
            if not api_key:
                raise ValueError("Gemini API key missing")
            genai.configure(api_key=api_key)
            self.model = genai
            self.embedding_dim = self._get_gemini_dimension()
            print(f"✅ Using Gemini embedding model: {settings.GEMINI_EMBEDDING_MODEL} (dim={self.embedding_dim})")
        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def _get_gemini_dimension(self):
        try:
            res = self.model.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                content="test",
                task_type="retrieval_document"
            )
            return len(res["embedding"])
        except:
            return 3072

    def get_embedding(self, text: str) -> List[float]:
        return self.get_embeddings_batch([text])[0]

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.provider == "fastembed":
            # fastembed returns a generator of numpy arrays
            embeddings = list(self.model.embed(texts))
            return [emb.tolist() for emb in embeddings]
        elif self.provider == "gemini":
            return self._gemini_batch(texts)
        else:
            raise ValueError("Unknown provider")

    def _gemini_batch(self, texts: List[str]) -> List[List[float]]:
        import random, re
        from google.api_core.exceptions import ResourceExhausted
        retries = 10
        for attempt in range(retries):
            try:
                result = self.model.embed_content(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    content=texts,
                    task_type="retrieval_document"
                )
                return result["embedding"]
            except ResourceExhausted as e:
                if attempt == retries - 1:
                    raise
                msg = str(e)
                delay_match = re.search(r"retry in ([\d.]+)s", msg)
                wait = float(delay_match.group(1)) + random.uniform(0, 1) if delay_match else (2 ** attempt) + random.uniform(0, 1)
                print(f"⏳ Rate limited. Retry {attempt+1}/{retries} in {wait:.2f}s...")
                time.sleep(wait)
            except Exception as e:
                if attempt == retries - 1:
                    raise
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"⚠️ Error: {e}. Retry {attempt+1}/{retries} in {wait:.2f}s...")
                time.sleep(wait)
        return []