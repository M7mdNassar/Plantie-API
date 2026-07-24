# src/services/supabase/database.py
from supabase import create_client
from typing import Optional, Dict, Any, List

from src.api.middleware.logging import logger
from src.config import get_settings

settings = get_settings()


class DatabaseService:
    """Supabase database operations."""

    def __init__(self):
        self.client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )

    async def get_user_by_auth_id(self, auth_user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Supabase auth user ID."""
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

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by device ID."""
        try:
            response = self.client.table("users") \
                .select("*") \
                .eq("id", user_id) \
                .single() \
                .execute()
            return response.data
        except Exception:
            return None

    async def create_conversation(
            self,
            user_id: str,
            session_id: str,
            title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new conversation."""
        data = {
            "user_id": user_id,
            "session_id": session_id,
            "title": title or "New Chat",
            "messages": [],
            "message_count": 0,
            "last_message_at": "now()"
        }
        response = self.client.table("rag_conversations") \
            .insert(data) \
            .execute()
        return response.data[0]

    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.client.table("rag_conversations") \
                .select("*") \
                .eq("id", conversation_id) \
                .eq("user_id", user_id) \
                .single() \
                .execute()
            return response.data if response.data else None
        except Exception:
            # Invalid UUID or other error – treat as not found
            return None

    async def get_conversations(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all conversations for a user."""
        response = self.client.table("rag_conversations") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("last_message_at", desc=True) \
            .limit(limit) \
            .execute()
        return response.data

    async def update_conversation(
            self,
            conversation_id: str,
            user_id: str,
            messages: List[Dict[str, str]],
            message_count: int,
            tokens_used: int
    ) -> None:
        """Update conversation with new messages."""
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

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        """Delete a conversation."""
        self.client.table("rag_conversations") \
            .delete() \
            .eq("id", conversation_id) \
            .eq("user_id", user_id) \
            .execute()
