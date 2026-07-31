"""Unauthenticated chat endpoint for local testing only.

Only mounted when DEBUG=true (see src/main.py) — it is never importable
into a production deployment path, since it skips auth and rate limiting
entirely.
"""

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from src.api.models.chat import ChatRequest
from src.core.agent.chat import ChatAgent
from src.services.supabase.database import DatabaseService
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger()

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
TEST_AUTH_USER_ID = "test-auth-id"


async def _ensure_test_user(db: DatabaseService) -> None:
    user_data = await db.get_user_by_id(TEST_USER_ID)
    if user_data:
        return

    def _create():
        db.client.table("users").insert(
            {
                "id": TEST_USER_ID,
                "auth_user_id": TEST_AUTH_USER_ID,
                "free_chat_attempts": 100,
            }
        ).execute()

    await asyncio.to_thread(_create)


@router.post("/chat/stream")
async def test_chat_stream(request: ChatRequest, req: Request):
    """Test endpoint: stream a chat response without authentication."""
    logger.info(f"Test chat request from {TEST_USER_ID}")

    db: DatabaseService = req.app.state.db
    agent: ChatAgent = req.app.state.chat_agent

    await _ensure_test_user(db)

    async def event_generator():
        async for chunk in agent.stream_response(
            user_id=TEST_USER_ID,
            message=request.message,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            location=request.location,
            weather=request.weather,
        ):
            yield {"data": chunk}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())