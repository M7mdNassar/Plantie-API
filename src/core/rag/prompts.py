from typing import Any, Dict, List, Optional
import re

class PromptBuilder:
    SYSTEM_PROMPT_EN = """You are Plantie AI, an expert agricultural assistant.

You have access to a knowledge base about farming, plant diseases, treatments, and best practices.

Your responses should be:
- **Accurate** and based on the provided context
- **Practical** and actionable
- **Conversational** and helpful
- **Safe** - if you're unsure, say so

If the user asks about something not in the context, use your general knowledge.
Always consider the user's location (if provided) for personalized advice.

**Language**: Respond in the same language as the user's question.
"""

    SYSTEM_PROMPT_AR = """أنت Plantie AI، مساعد زراعي خبير.

لديك إمكانية الوصول إلى قاعدة معرفية حول الزراعة وأمراض النباتات والعلاجات وأفضل الممارسات.

يجب أن تكون ردودك:
- **دقيقة** وتعتمد على السياق المقدم
- **عملية** وقابلة للتنفيذ
- **محادثة** ومفيدة
- **آمنة** - إذا كنت غير متأكد، فقل ذلك

إذا سأل المستخدم عن شيء غير موجود في السياق، استخدم معرفتك العامة.
ضع في اعتبارك دائماً موقع المستخدم (إذا تم توفيره) للحصول على نصائح مخصصة.

**اللغة**: أجب بنفس لغة سؤال المستخدم.
"""

    def _detect_language(self, text: str) -> str:
        arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        return 'ar' if arabic_pattern.search(text) else 'en'

    def _format_weather(self, weather: Optional[Dict[str, Any]]) -> str:
        if not weather:
            return ""
        parts = []
        if "temperature" in weather:
            parts.append(f"Temperature: {weather['temperature']}°C")
        if "humidity" in weather:
            parts.append(f"Humidity: {weather['humidity']}%")
        if "condition" in weather:
            parts.append(f"Condition: {weather['condition']}")
        if "wind_speed" in weather:
            parts.append(f"Wind: {weather['wind_speed']} km/h")
        if "precipitation" in weather:
            parts.append(f"Precipitation: {weather['precipitation']} mm")
        return "Current weather at user's location:\n" + "\n".join(parts) if parts else ""

    def build(
        self,
        query: str,
        context: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        is_short: bool = False,
        weather: Optional[Dict[str, Any]] = None,
    ) -> str:
        lang = self._detect_language(query)
        system_prompt = self.SYSTEM_PROMPT_AR if lang == 'ar' else self.SYSTEM_PROMPT_EN

        weather_text = self._format_weather(weather)

        context_text = ""
        if context:
            formatted_chunks = []
            for chunk in context[:2]:
                meta = chunk.get("metadata", {})
                source = meta.get("source", "Unknown")
                page = meta.get("page", "N/A")
                if page == "N/A" and "chunk_index" in meta:
                    page = f"chunk {meta['chunk_index']}"
                formatted_chunks.append(
                    f"[Source: {source}, Page: {page}]\n{chunk.get('content', '')}"
                )
            context_text = "\n\n".join(formatted_chunks)

        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f"User: {msg['user']}\nAssistant: {msg['assistant']}"
                for msg in conversation_history[-1:]
            )

        context_section = context_text if context_text else ("" if is_short else "No relevant context found.")

        sections = []
        if weather_text:
            sections.append(f"## Weather\n{weather_text}")
        if context_section:
            sections.append(f"## Context\n{context_section}")
        if history_text:
            sections.append(f"## Previous Conversation\n{history_text}")
        else:
            sections.append("## Previous Conversation\nNo previous conversation.")
        sections.append(f"## Question\n{query}")
        sections.append("## Response")

        full_prompt = f"{system_prompt}\n\n" + "\n\n".join(sections)
        return full_prompt