# src/core/rag/retriever.py
from typing import List, Dict, Any
from supabase import create_client
from src.core.rag.embedder import Embedder
from src.config import get_settings

settings = get_settings()


class Retriever:
    """Vector search retrieval from indexed documents."""

    def __init__(self):
        self.client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
        self.embedder = Embedder()
        self.top_k = settings.RAG_TOP_K
        self.min_score = settings.RAG_MIN_RELEVANCE_SCORE

    def retrieve(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks based on query."""
        # Generate query embedding
        query_embedding = self.embedder.get_embedding(query)
        top_k = top_k or self.top_k

        # Vector similarity search
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