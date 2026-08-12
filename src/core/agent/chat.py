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
from src.core.agent.weather_service import WeatherService
from src.services.supabase.database import DatabaseService
from src.utils.logging import get_logger

settings = get_settings()
logger = get_logger()


class ChatAgent:
    def __init__(self, retriever: Retriever, db: DatabaseService):
        self.retriever = retriever
        self.db = db
        self.prompt_builder = PromptBuilder()
        self.weather_service = WeatherService()
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
            logger.error(f"Mistral stream error: {e}")
            yield f"Error: {str(e)}"

    async def _stream_gemini(self, prompt: str, message: str) -> AsyncGenerator[str, None]:
        """Gemini streaming."""
        try:
            response = self.model.generate_content(
                f"{prompt}\n\nUser: {message}\nAssistant:",
                stream=True,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini stream error: {e}")
            yield f"Error: {str(e)}"

    async def generate_suggestions(self, user_message: str, assistant_response: str) -> List[str]:
        """Generates 3 short follow-up questions as a genuinely separate,
        structured call — works for both Mistral and Gemini.
        """
        if len(user_message) <= settings.SHORT_QUERY_THRESHOLD:
            return []

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
        prompt = (
            f"User asked: {user_message}\n"
            f"Assistant answered: {assistant_response[:800]}\n\n"
            f"{instruction}"
        )

        if self.provider == "mistral":
            try:
                response = await self.client.chat.complete_async(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.5,
                    max_tokens=250,
                )
                data = json.loads(response.choices[0].message.content)
                suggestions = data.get("suggestions", [])
                return [s for s in suggestions if isinstance(s, str)][:3]
            except Exception as e:
                logger.error(f"Mistral suggestion generation failed: {e}")
                return []

        elif self.provider == "gemini":
            try:
                response = await self.model.generate_content_async(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.5,
                        max_output_tokens=250,
                        response_mime_type="application/json",
                    )
                )
                data = json.loads(response.text)
                suggestions = data.get("suggestions", [])
                return [s for s in suggestions if isinstance(s, str)][:3]
            except Exception as e:
                logger.error(f"Gemini suggestion generation failed: {e}")
                return []

        return []

    async def stream_response(
        self,
        user_id: str,
        message: str,
        conversation_id: str,
        session_id: str,
        location: Optional[Dict[str, float]] = None,
        weather: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        # 1. Retrieve RAG context
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
            await self.db.create_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                session_id=session_id,
                title=(message[:50] + "...") if message else "New Chat",
            )
            history = []
        else:
            history = await self.db.get_recent_messages(conversation_id, limit=settings.RAG_MAX_HISTORY)

        # 3. ── 🔥 THE AGENT UPGRADE ──
        # Fetch fresh weather from backend if location is provided.
        # This overrides any frontend-supplied weather for freshness & reliability.
        fetched_weather = weather  # fallback
        if location and isinstance(location, dict):
            lat = location.get("latitude")
            lon = location.get("longitude")
            if lat is not None and lon is not None:
                try:
                    raw = await self.weather_service.get_current_weather(lat, lon)
                    # Map Open-Meteo keys to the shape prompt builder expects
                    fetched_weather = {
                        "temperature": raw.get("temperature"),
                        "humidity": raw.get("humidity"),
                        "precipitation": raw.get("precipitation"),
                        "wind_speed": raw.get("wind_speed"),
                        "weather_code": raw.get("weather_code"),
                        "condition": self._map_weather_code(raw.get("weather_code")),
                        "is_day": raw.get("is_day"),
                    }
                    logger.info(f"Weather fetched for ({lat}, {lon})")
                except Exception as e:
                    logger.warning(f"Could not fetch weather, using fallback if any: {e}")
                    # fallback to frontend-provided weather if available

        # 4. Build prompt with weather (fetched or fallback)
        prompt = self.prompt_builder.build(
            query=message,
            context=context_chunks,
            conversation_history=history,
            is_short=is_short,
            weather=fetched_weather,
        )

        # 5. Stream from selected provider
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

            # 6. Persist the turn
            await self.db.add_message(conversation_id, "user", message or "[image]")
            await self.db.add_message(conversation_id, "assistant", full_response)
            await self.db.touch_conversation(conversation_id, user_id, message_count_increment=2)
        except Exception as e:
            logger.error(f"Streaming failed for conversation {conversation_id}: {e}")
            yield f"Error: {str(e)}"

    def _map_weather_code(self, code: Optional[int]) -> str:
        """Convert Open-Meteo weather code to a readable condition string."""
        if code is None:
            return "Unknown"
        if code == 0:
            return "Clear sky"
        if code <= 3:
            return "Partly cloudy"
        if code <= 48:
            return "Foggy"
        if code <= 57:
            return "Drizzle"
        if code <= 67:
            return "Rainy"
        if code <= 77:
            return "Snowy"
        if code <= 82:
            return "Rain showers"
        if code <= 99:
            return "Thunderstorm"
        return "Unknown"