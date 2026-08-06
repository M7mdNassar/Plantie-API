"""Built exactly once at startup (see src/main.py's lifespan) and reused for
every request. The Mistral / Gemini SDK clients each wrap their own HTTP
connection pool, so reusing one instance across requests also means
connections get reused instead of a fresh TLS handshake every time.
"""

import asyncio
import json
from typing import AsyncGenerator, Dict, List, Optional, Any

import google.generativeai as genai
from mistralai import Mistral

from src.config import get_settings
from src.core.rag.prompts import PromptBuilder
from src.core.rag.retriever import Retriever
from src.services.supabase.database import DatabaseService
from src.utils.logging import get_logger

settings = get_settings()
logger = get_logger()


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

    async def generate_suggestions(self, user_message: str, assistant_response: str) -> List[str]:
        """Generates 3 short follow-up questions as a genuinely separate,
        structured call — never scraped out of the streamed answer's free
        text. This is what makes suggestion chips reliable: there is no
        formatting convention for a regex to get wrong, because the model
        is asked for nothing but a JSON object here.
        """
        if self.provider != "mistral":
            return []  # Gemini fallback: no suggestions yet, keep scope tight
        if len(user_message) <= settings.SHORT_QUERY_THRESHOLD:
            return []  # not worth the extra call for "hi" / "thanks"

        lang = self.prompt_builder._detect_language(user_message)
        instruction = (
            'بناءً على هذا التبادل، اقترح 3 أسئلة متابعة قصيرة وطبيعية قد يطرحها '
            'المستخدم بعد ذلك. أجب فقط بصيغة JSON صالحة على هذا الشكل: '
            '{"suggestions": ["...", "...", "..."]} بدون أي نص إضافي.'
            if lang == "ar"
            else
            'Based on this exchange, suggest 3 short, natural follow-up '
            'questions the user might ask next. Respond with ONLY valid '
            'JSON in this exact shape: {"suggestions": ["...", "...", "..."]} '
            '— no extra text, no markdown.'
        )
        try:
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"User asked: {user_message}\n"
                            f"Assistant answered: {assistant_response[:800]}\n\n"
                            f"{instruction}"
                        ),
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=250,
            )
            data = json.loads(response.choices[0].message.content)
            suggestions = data.get("suggestions", [])
            return [s for s in suggestions if isinstance(s, str)][:3]
        except Exception as e:
            logger.error(f"Suggestion generation failed: {e}")
            return []  # never let a suggestions failure break the actual chat turn

    async def stream_response(
        self,
        user_id: str,
        message: str,
        conversation_id: str,
        session_id: str,
        location: Optional[Dict[str, float]] = None,
        weather: Optional[Dict[str, Any]] = None,
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

        # 3. Build prompt with weather
        prompt = self.prompt_builder.build(
            query=message,
            context=context_chunks,
            conversation_history=history,
            is_short=is_short,
            weather=weather,
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