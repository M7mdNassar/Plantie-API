from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
import json

from src.api.dependencies.auth import get_current_user
from src.api.models.chat import ChatRequest
from src.core.agent.chat import ChatAgent
from src.services.supabase.database import DatabaseService
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger()


def get_chat_agent(request: Request) -> ChatAgent:
    return request.app.state.chat_agent


def get_db(request: Request) -> DatabaseService:
    return request.app.state.db


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
    agent: ChatAgent = Depends(get_chat_agent),
):
    """Stream chat response with SSE."""
    user_id = user["user_id"]
    logger.info(f"Chat request from user {user_id}")

    async def event_generator():
        async for chunk in agent.stream_response(
            user_id=user_id,
            message=request.message,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            location=request.location,
            weather=request.weather,
        ):
            # JSON-encode each chunk. Raw text gets split across multiple
            # SSE "data:" lines whenever it contains a newline, and the
            # client's .trim() on each line eats real leading/trailing
            # spaces too — together that's exactly the missing-space,
            # collapsed-markdown bug. A JSON string keeps the payload on
            # one line and protects the spaces inside the quotes.
            yield {"data": json.dumps({"content": chunk})}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())


@router.get("/chat/conversations")
async def get_conversations(
    limit: int = 20,
    user: dict = Depends(get_current_user),
    db: DatabaseService = Depends(get_db),
):
    """Get the authenticated user's conversations."""
    conversations = await db.get_conversations(user["user_id"], limit)
    return {"conversations": conversations}


@router.get("/chat/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    db: DatabaseService = Depends(get_db),
):
    """Get a specific conversation."""
    conversation = await db.get_conversation(conversation_id, user["user_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    db: DatabaseService = Depends(get_db),
):
    """Delete a conversation."""
    await db.delete_conversation(conversation_id, user["user_id"])
    return {"message": "Conversation deleted"}