from typing import AsyncGenerator, List, Dict, Any
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
        # 1. Retrieve context
        context_chunks = self.retriever.retrieve(message)

        # 2. Get or create conversation
        conversation = await self.db.get_conversation(conversation_id, user_id)
        if conversation is None:
            # Create new conversation
            new_conv = await self.db.create_conversation(
                user_id=user_id,
                session_id=session_id,
                title=message[:50] + "..."
            )
            conversation_id = new_conv["id"]
            conversation = new_conv
            history = []
        else:
            history = conversation.get("messages", [])[-10:]

        # 3. Build prompt
        prompt = self.prompt_builder.build(
            query=message,
            context=context_chunks,
            conversation_history=history
        )

        # 4. Stream from Gemini
        try:
            response = self.model.generate_content(
                f"{prompt}\n\nUser: {message}\nAssistant:",
                stream=True
            )

            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text

            # 5. Save conversation (always update, even for new)
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