# src/api/routes/test_chat.py
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from src.api.models.chat import ChatRequest
from src.core.agent.chat import ChatAgent
from src.services.supabase.database import DatabaseService
from src.utils.logging import get_logger

router = APIRouter()
logger = get_logger()

# Fixed test user – will be created in DB if not exists
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
TEST_AUTH_USER_ID = "test-auth-id"

def get_or_create_test_user():
    """Ensure test user exists in Supabase."""
    db = DatabaseService()
    # Use sync client because this is called inside async endpoints – we'll use async wrapper below
    # Better: call db.get_user_by_id and if None, create one.
    # We'll do this inside each endpoint for simplicity.
    pass

@router.post("/chat/stream")
async def test_chat_stream(request: ChatRequest, req: Request):
    """Test endpoint: stream chat response without authentication."""
    user_id = TEST_USER_ID
    logger.info(f"Test chat request from {user_id}")

    # Ensure test user exists (create if not)
    db = DatabaseService()
    user_data = await db.get_user_by_id(user_id)
    if not user_data:
        # Create test user
        try:
            # Insert a user with free_chat_attempts = 100 (so we never run out)
            db.client.table("users").insert({
                "id": user_id,
                "auth_user_id": TEST_AUTH_USER_ID,
                "free_chat_attempts": 100
            }).execute()
            logger.info(f"Created test user {user_id}")
        except Exception as e:
            logger.warning(f"Could not create test user: {e}")

    # No free attempts check for test endpoint

    agent = ChatAgent()

    async def event_generator():
        async for chunk in agent.stream_response(
                user_id=user_id,
                message=request.message,
                conversation_id=request.conversation_id,
                session_id=request.session_id or "test-session",
                location=request.location
        ):
            yield {"data": chunk}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())

@router.get("/chat/conversations")
async def test_get_conversations(req: Request, limit: int = 20):
    """Get test user's conversations."""
    db = DatabaseService()
    conversations = await db.get_conversations(TEST_USER_ID, limit)
    return {"conversations": conversations}

@router.get("/chat/conversations/{conversation_id}")
async def test_get_conversation(conversation_id: str, req: Request):
    """Get a specific conversation for test user."""
    db = DatabaseService()
    conversation = await db.get_conversation(conversation_id, TEST_USER_ID)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation

@router.delete("/chat/conversations/{conversation_id}")
async def test_delete_conversation(conversation_id: str, req: Request):
    """Delete a conversation for test user."""
    db = DatabaseService()
    await db.delete_conversation(conversation_id, TEST_USER_ID)
    return {"message": "Conversation deleted"}