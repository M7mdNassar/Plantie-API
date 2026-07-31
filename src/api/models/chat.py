from pydantic import BaseModel
from typing import Optional, Dict, Any

class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    session_id: str
    location: Optional[Dict[str, float]] = None
    weather: Optional[Dict[str, Any]] = None  # temperature, humidity, condition, wind_speed, precipitation

class ChatResponse(BaseModel):
    response: str
    conversation_id: str