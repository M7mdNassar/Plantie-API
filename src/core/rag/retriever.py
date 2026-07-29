"""Vector similarity search over the `chunks` table via the `match_chunks` RPC.

Takes an already-built Embedder and Supabase client (both constructed once
at startup, see src/main.py) — this class does no expensive setup of its own.
"""

import asyncio
from typing import Any, Dict, List, Optional

from supabase import Client

from src.config import get_settings
from src.core.rag.embedder import Embedder

settings = get_settings()


class Retriever:
    def __init__(self, embedder: Embedder, client: Client):
        self.embedder = embedder
        self.client = client
        self.top_k = settings.RAG_TOP_K
        self.min_score = settings.RAG_MIN_RELEVANCE_SCORE

    async def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Async retrieval — embedding and the DB call both run in a thread."""
        top_k = top_k or self.top_k

        query_embedding = await self.embedder.get_embedding_async(query)

        def _search():
            try:
                response = self.client.rpc(
                    "match_chunks",
                    {
                        "query_embedding": query_embedding,
                        "match_threshold": self.min_score,
                        "match_count": top_k,
                    },
                ).execute()
                return response.data
            except Exception as e:
                print(f"Error retrieving: {e}")
                return []

        return await asyncio.to_thread(_search)