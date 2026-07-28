from typing import AsyncGenerator, List, Dict, Any
import asyncio
import google.generativeai as genai
from mistralai import Mistral
from src.config import get_settings
from src.core.rag.retriever import Retriever
from src.core.rag.prompts import PromptBuilder
from src.services.supabase.database import DatabaseService

settings = get_settings()

class ChatAgent:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.prompt_builder = PromptBuilder()
        self.retriever = Retriever()
        self.db = DatabaseService()

        if self.provider == "mistral":
            api_key = settings.MISTRAL_API_KEY
            if not api_key:
                raise ValueError("MISTRAL_API_KEY required")
            self.client = Mistral(api_key=api_key)
            self.model = settings.MISTRAL_MODEL
        elif self.provider == "gemini":
            api_key = settings.gemini_api_key
            if not api_key:
                raise ValueError("Gemini API key missing")
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    async def _stream_mistral(self, prompt: str, message: str) -> AsyncGenerator[str, None]:
        """Stream from Mistral (fast, first token < 500ms)."""
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ]

        try:
            # Mistral async streaming
            async with self.client.chat.stream_async(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=800,
            ) as response:
                async for chunk in response:
                    if chunk.data.choices[0].delta.content is not None:
                        yield chunk.data.choices[0].delta.content
        except Exception as e:
            yield f"Error: {str(e)}"

    async def _stream_gemini(self, prompt: str, message: str) -> AsyncGenerator[str, None]:
        """Fallback Gemini streaming."""
        try:
            response = self.model.generate_content(
                f"{prompt}\n\nUser: {message}\nAssistant:",
                stream=True
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"Error: {str(e)}"

    async def stream_response(
        self,
        user_id: str,
        message: str,
        conversation_id: str,
        session_id: str,
        location: Dict[str, float] = None
    ) -> AsyncGenerator[str, None]:
        # 1. Skip retrieval for short queries
        is_short = len(message) <= settings.SHORT_QUERY_THRESHOLD
        should_retrieve = not (settings.SKIP_RETRIEVAL_FOR_SHORT_QUERIES and is_short)

        if should_retrieve:
            context_task = self.retriever.retrieve(message, top_k=settings.RAG_TOP_K)
            conv_task = self.db.get_conversation(conversation_id, user_id)
            context_chunks, conversation = await asyncio.gather(context_task, conv_task)
        else:
            context_chunks = []
            conversation = await self.db.get_conversation(conversation_id, user_id)

        # 2. Conversation handling
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
            history = conversation.get("messages", [])[-settings.RAG_MAX_HISTORY:]

        # 3. Build prompt
        prompt = self.prompt_builder.build(
            query=message,
            context=context_chunks,
            conversation_history=history,
            is_short=is_short
        )

        # 4. Stream from selected provider
        if self.provider == "mistral":
            generator = self._stream_mistral(prompt, message)
        else:
            generator = self._stream_gemini(prompt, message)

        full_response = ""
        try:
            async for chunk in generator:
                full_response += chunk
                yield chunk

            # 5. Save conversation
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