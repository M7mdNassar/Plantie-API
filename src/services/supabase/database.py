"""Async wrapper around a single, shared Supabase client.

The client itself (see src/main.py's lifespan) is created once at startup
and passed in here, instead of each caller opening its own — avoids a fresh
connection/auth handshake per request.
"""

import asyncio
from typing import Any, Dict, List, Optional

from supabase import Client

from src.utils.logging import get_logger

logger = get_logger()


class DatabaseService:
    def __init__(self, client: Client):
        self.client = client

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def get_user_by_auth_id(self, auth_user_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            try:
                response = (
                    self.client.table("users")
                    .select("*")
                    .eq("auth_user_id", auth_user_id)
                    .single()
                    .execute()
                )
                return response.data
            except Exception as e:
                logger.error(f"Error fetching user: {e}")
                return None

        return await asyncio.to_thread(_get)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            try:
                response = (
                    self.client.table("users")
                    .select("*")
                    .eq("id", user_id)
                    .single()
                    .execute()
                )
                return response.data
            except Exception:
                return None

        return await asyncio.to_thread(_get)

    # ------------------------------------------------------------------
    # Conversations (metadata only — see rag_messages for message content)
    # ------------------------------------------------------------------
    async def create_conversation(
        self,
        conversation_id: str,
        user_id: str,
        session_id: str,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        # id is set explicitly to the client-generated conversation_id, so
        # the client and server always agree on the conversation's identity
        # from the very first message.
        data = {
            "id": conversation_id,
            "user_id": user_id,
            "session_id": session_id,
            "title": title or "New Chat",
            "message_count": 0,
            "last_message_at": "now()",
        }

        def _create():
            response = self.client.table("rag_conversations").insert(data).execute()
            return response.data[0]

        return await asyncio.to_thread(_create)

    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            try:
                response = (
                    self.client.table("rag_conversations")
                    .select("*")
                    .eq("id", conversation_id)
                    .eq("user_id", user_id)
                    .single()
                    .execute()
                )
                return response.data if response.data else None
            except Exception:
                return None

        return await asyncio.to_thread(_get)

    async def get_conversations(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        def _get():
            response = (
                self.client.table("rag_conversations")
                .select("*")
                .eq("user_id", user_id)
                .order("last_message_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data

        return await asyncio.to_thread(_get)

    async def touch_conversation(
        self,
        conversation_id: str,
        user_id: str,
        message_count_increment: int = 2,
    ) -> None:
        """Lightweight metadata bump after a turn completes — NOT a rewrite
        of message content, which now lives in rag_messages. This is the
        replacement for the old update_conversation(messages=...) call that
        used to serialize and rewrite the entire conversation every turn.
        """
        def _update():
            try:
                current = (
                    self.client.table("rag_conversations")
                    .select("message_count")
                    .eq("id", conversation_id)
                    .single()
                    .execute()
                )
                new_count = (current.data.get("message_count") or 0) + message_count_increment
            except Exception:
                new_count = message_count_increment

            self.client.table("rag_conversations").update(
                {
                    "message_count": new_count,
                    "last_message_at": "now()",
                    "updated_at": "now()",
                }
            ).eq("id", conversation_id).eq("user_id", user_id).execute()

        await asyncio.to_thread(_update)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        # rag_messages rows are removed automatically via ON DELETE CASCADE.
        def _delete():
            self.client.table("rag_conversations").delete().eq(
                "id", conversation_id
            ).eq("user_id", user_id).execute()

        await asyncio.to_thread(_delete)

    # ------------------------------------------------------------------
    # Messages (the actual conversation content — one row per message)
    # ------------------------------------------------------------------
    async def add_message(self, conversation_id: str, role: str, content: str) -> None:
        """A single INSERT — O(1) regardless of how long the conversation
        already is. This replaces rewriting the whole messages array.
        """
        def _insert():
            self.client.table("rag_messages").insert(
                {"conversation_id": conversation_id, "role": role, "content": content}
            ).execute()

        await asyncio.to_thread(_insert)

    async def get_recent_messages(self, conversation_id: str, limit: int = 5) -> List[Dict[str, str]]:
        """Returns the last `limit` (user, assistant) turns, oldest first,
        re-paired into the {"user": ..., "assistant": ...} shape the prompt
        builder already expects — so this is a drop-in replacement for the
        old conversation["messages"][-limit:] slicing.
        """
        def _get():
            response = (
                self.client.table("rag_messages")
                .select("role, content, created_at")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(limit * 2)  # each turn is 2 rows (user + assistant)
                .execute()
            )
            rows = list(reversed(response.data))  # back to chronological order

            turns: List[Dict[str, str]] = []
            pending_user: Optional[str] = None
            for row in rows:
                if row["role"] == "user":
                    pending_user = row["content"]
                elif row["role"] == "assistant" and pending_user is not None:
                    turns.append({"user": pending_user, "assistant": row["content"]})
                    pending_user = None
            return turns

        return await asyncio.to_thread(_get)