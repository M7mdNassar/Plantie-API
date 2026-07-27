from typing import AsyncGenerator, List, Dict, Any
import asyncio
import google.generativeai as genai
from src.config import get_settings
from src.core.rag.retriever import Retriever
from src.core.rag.prompts import PromptBuilder
from src.services.supabase.database import DatabaseService

settings = get_settings()

class ChatAgent:
    def __init__(self):
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("Gemini API key missing")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        self.retriever = Retriever()
        self.prompt_builder = PromptBuilder()
        self.db = DatabaseService()

    async def stream_response(
        self,
        user_id: str,
        message: str,
        conversation_id: str,
        session_id: str,
        location: Dict[str, float] = None
    ) -> AsyncGenerator[str, None]:
        # 1. Fetch context (only top 3) and conversation in parallel
        context_task = self.retriever.retrieve(message, top_k=3)  # Reduced from 5
        conv_task = self.db.get_conversation(conversation_id, user_id)

        context_chunks, conversation = await asyncio.gather(context_task, conv_task)

        if conversation is None:
            new_conv = await self.db.create_conversation(
                user_id=user_id,
                session_id=session_id,
                title=message[:50] + "..."
            )
            conversation_id = new_conv["id"]
            conversation = new_conv
            history = []
        else:
            # Keep only last 3 messages (reduce history)
            history = conversation.get("messages", [])[-3:]

        # 2. Build prompt (lightweight)
        prompt = self.prompt_builder.build(
            query=message,
            context=context_chunks,
            conversation_history=history
        )

        # 3. Stream from Gemini – yields tokens immediately
        try:
            response = self.model.generate_content(
                f"{prompt}\n\nUser: {message}\nAssistant:",
                stream=True
            )

            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text  # <-- SSE will flush immediately

            # 4. Save conversation (async, non‑blocking)
            updated_messages = history + [{"user": message, "assistant": full_response}]
            await self.db.update_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                messages=updated_messages,
                message_count=len(updated_messages),
                tokens_used=0
            )

        except Exception as e:
            yield f"Error: {str(e)}"