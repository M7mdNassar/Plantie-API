# src/api/routes/chat.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from src.api.models.chat import ChatRequest, ChatResponse
from src.api.dependencies.auth import get_current_user
from src.core.agent.chat import ChatAgent
from src.services.supabase.database import DatabaseService
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger()


@router.post("/chat/stream")
async def chat_stream(
        request: ChatRequest,
        req: Request,
        user: dict = Depends(get_current_user)
):
    """Stream chat response with SSE."""

    user_id = user["user_id"]
    logger.info(f"Chat request from user {user_id}", extra={"user_id": user_id})

    # Check free chat attempts
    db = DatabaseService()
    user_data = await db.get_user_by_id(user_id)
    free_attempts = user_data.get("free_chat_attempts", 0)

    if free_attempts <= 0:
        raise HTTPException(status_code=403, detail="No free chat attempts remaining")

    # Decrement free attempts
    # TODO: Update user's free_chat_attempts in Supabase

    # Create agent and stream
    agent = ChatAgent()

    async def event_generator():
        async for chunk in agent.stream_response(
                user_id=user_id,
                message=request.message,
                conversation_id=request.conversation_id,
                session_id=request.session_id,
                location=request.location
        ):
            yield {"data": chunk}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())


@router.get("/chat/conversations")
async def get_conversations(
        req: Request,
        limit: int = 20,
        user: dict = Depends(get_current_user)
):
    """Get user's conversations."""
    db = DatabaseService()
    conversations = await db.get_conversations(user["user_id"], limit)
    return {"conversations": conversations}


@router.get("/chat/conversations/{conversation_id}")
async def get_conversation(
        conversation_id: str,
        req: Request,
        user: dict = Depends(get_current_user)
):
    """Get a specific conversation."""
    db = DatabaseService()
    conversation = await db.get_conversation(conversation_id, user["user_id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(
        conversation_id: str,
        req: Request,
        user: dict = Depends(get_current_user)
):
    """Delete a conversation."""
    db = DatabaseService()
    await db.delete_conversation(conversation_id, user["user_id"])
    return {"message": "Conversation deleted"}