"""Built exactly once at startup (see src/main.py's lifespan) and reused for
every request. The Mistral / Gemini SDK clients each wrap their own HTTP
connection pool, so reusing one instance across requests also means
connections get reused instead of a fresh TLS handshake every time.
"""

import asyncio
from typing import AsyncGenerator, Dict, List, Optional

import google.generativeai as genai
from mistralai import Mistral

from src.config import get_settings
from src.core.rag.prompts import PromptBuilder
from src.core.rag.retriever import Retriever
from src.services.supabase.database import DatabaseService

settings = get_settings()


class ChatAgent:
    def __init__(self, retriever: Retriever, db: DatabaseService):
        self.retriever = retriever
        self.db = db
        self.prompt_builder = PromptBuilder()
        self.provider = settings.LLM_PROVIDER

        if self.provider == "mistral":
            if not settings.MISTRAL_API_KEY:
                raise ValueError("MISTRAL_API_KEY required")
            self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
            self.model = settings.MISTRAL_MODEL
        elif self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                raise ValueError("Gemini API key missing")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    async def _stream_mistral(self, prompt: str, message: str) -> AsyncGenerator[str, None]:
        """Stream from Mistral (fast, first token < 500ms)."""
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message},
        ]
        try:
            # ✅ Correct: await the stream_async() call before using `async with`
            async with await self.client.chat.stream_async(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=800,
            ) as response:
                async for chunk in response:
                    if chunk.data.choices and chunk.data.choices[0].delta.content is not None:
                        yield chunk.data.choices[0].delta.content
        except Exception as e:
            yield f"Error: {str(e)}"

    async def _stream_gemini(self, prompt: str, message: str) -> AsyncGenerator[str, None]:
        """Fallback Gemini streaming."""
        try:
            response = self.model.generate_content(
                f"{prompt}\n\nUser: {message}\nAssistant:",
                stream=True,
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
        location: Optional[Dict[str, float]] = None,
    ) -> AsyncGenerator[str, None]:
        # 1. Skip retrieval for short, likely conversational queries.
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
                title=message[:50] + "...",
            )
            conversation_id = new_conv["id"]
            conversation = new_conv
            history = []
        else:
            history = conversation.get("messages", [])[-settings.RAG_MAX_HISTORY :]

        # 3. Build prompt
        prompt = self.prompt_builder.build(
            query=message,
            context=context_chunks,
            conversation_history=history,
            is_short=is_short,
        )

        # 4. Stream from selected provider
        generator = (
            self._stream_mistral(prompt, message)
            if self.provider == "mistral"
            else self._stream_gemini(prompt, message)
        )

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
                tokens_used=0,
            )
        except Exception as e:
            yield f"Error: {str(e)}"