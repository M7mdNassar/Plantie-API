from supabase import create_client
from typing import Optional, Dict, Any, List
import asyncio

from src.api.middleware.logging import logger
from src.config import get_settings

settings = get_settings()

class DatabaseService:
    def __init__(self):
        self.client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )

    async def get_user_by_auth_id(self, auth_user_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            try:
                response = self.client.table("users") \
                    .select("*") \
                    .eq("auth_user_id", auth_user_id) \
                    .single() \
                    .execute()
                return response.data
            except Exception as e:
                logger.error(f"Error fetching user: {e}")
                return None
        return await asyncio.to_thread(_get)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            try:
                response = self.client.table("users") \
                    .select("*") \
                    .eq("id", user_id) \
                    .single() \
                    .execute()
                return response.data
            except Exception:
                return None
        return await asyncio.to_thread(_get)

    async def create_conversation(self, user_id: str, session_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        data = {
            "user_id": user_id,
            "session_id": session_id,
            "title": title or "New Chat",
            "messages": [],
            "message_count": 0,
            "last_message_at": "now()"
        }
        def _create():
            response = self.client.table("rag_conversations") \
                .insert(data) \
                .execute()
            return response.data[0]
        return await asyncio.to_thread(_create)

    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            try:
                response = self.client.table("rag_conversations") \
                    .select("*") \
                    .eq("id", conversation_id) \
                    .eq("user_id", user_id) \
                    .single() \
                    .execute()
                return response.data if response.data else None
            except Exception:
                return None
        return await asyncio.to_thread(_get)

    async def get_conversations(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        def _get():
            response = self.client.table("rag_conversations") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("last_message_at", desc=True) \
                .limit(limit) \
                .execute()
            return response.data
        return await asyncio.to_thread(_get)

    async def update_conversation(self, conversation_id: str, user_id: str, messages: List[Dict[str, str]], message_count: int, tokens_used: int) -> None:
        def _update():
            self.client.table("rag_conversations") \
                .update({
                    "messages": messages,
                    "message_count": message_count,
                    "total_tokens": tokens_used,
                    "last_message_at": "now()",
                    "updated_at": "now()"
                }) \
                .eq("id", conversation_id) \
                .eq("user_id", user_id) \
                .execute()
        await asyncio.to_thread(_update)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        def _delete():
            self.client.table("rag_conversations") \
                .delete() \
                .eq("id", conversation_id) \
                .eq("user_id", user_id) \
                .execute()
        await asyncio.to_thread(_delete)