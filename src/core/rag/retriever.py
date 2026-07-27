from typing import List, Dict, Any
import asyncio
from supabase import create_client
from src.core.rag.embedder import Embedder
from src.config import get_settings

settings = get_settings()

class Retriever:
    def __init__(self):
        self.client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
        self.embedder = Embedder()
        self.top_k = settings.RAG_TOP_K
        self.min_score = settings.RAG_MIN_RELEVANCE_SCORE

    async def retrieve(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        """Async retrieval – offloads embedding and DB call to threads."""
        top_k = top_k or self.top_k

        # 1. Generate query embedding (offloaded)
        query_embedding = await self.embedder.get_embedding_async(query)

        # 2. Vector search (offloaded because Supabase client is sync)
        def _search():
            try:
                response = self.client.rpc(
                    "match_chunks",
                    {
                        "query_embedding": query_embedding,
                        "match_threshold": self.min_score,
                        "match_count": top_k
                    }
                ).execute()
                return response.data
            except Exception as e:
                print(f"Error retrieving: {e}")
                return []

        return await asyncio.to_thread(_search)