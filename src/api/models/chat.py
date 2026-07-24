from pydantic import BaseModel
from typing import Optional, Dict

class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    session_id: str
    location: Optional[Dict[str, float]] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str