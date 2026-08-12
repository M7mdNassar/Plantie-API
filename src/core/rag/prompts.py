from typing import Any, Dict, List, Optional
import re

class PromptBuilder:
    SYSTEM_PROMPT_EN = """You are Plantie AI, an expert agricultural assistant.

You have access to a knowledge base about farming, plant diseases, treatments, and best practices.

**Weather Awareness**: If the user's current weather data is provided below, you MUST refer to it explicitly when the question relates to farming activities (irrigation, spraying, planting, frost risk, harvesting). For example: "Based on your current temperature of 28°C and no rain, it's a good time to irrigate."

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

**الوعي بالطقس**: إذا تم توفير بيانات الطقس الحالية للمستخدم أدناه، يجب عليك الرجوع إليها صراحةً عندما يتعلق السؤال بالأنشطة الزراعية (الري، الرش، الزراعة، خطر الصقيع، الحصاد). مثال: "بناءً على درجة الحرارة الحالية البالغة 28 درجة مئوية وعدم وجود مطر، هذا وقت مناسب للري."

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
        if weather.get("temperature") is not None:
            parts.append(f"Temperature: {weather['temperature']}°C")
        if weather.get("humidity") is not None:
            parts.append(f"Humidity: {weather['humidity']}%")
        if weather.get("condition"):
            parts.append(f"Condition: {weather['condition']}")
        if weather.get("wind_speed") is not None:
            parts.append(f"Wind: {weather['wind_speed']} km/h")
        if weather.get("precipitation") is not None:
            parts.append(f"Precipitation: {weather['precipitation']} mm")
        if weather.get("is_day") is not None:
            parts.append("Daytime" if weather['is_day'] else "Nighttime")
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