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
        """Simple detection: returns 'ar' if Arabic characters are present, else 'en'."""
        arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        if arabic_pattern.search(text):
            return 'ar'
        return 'en'

    def build(
        self,
        query: str,
        context: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        is_short: bool = False,
    ) -> str:
        # Choose system prompt based on detected language
        lang = self._detect_language(query)
        system_prompt = self.SYSTEM_PROMPT_AR if lang == 'ar' else self.SYSTEM_PROMPT_EN

        # Format retrieved context, if any.
        context_text = ""
        if context:
            formatted_chunks = []
            for chunk in context[:2]:  # only top 2 chunks
                meta = chunk.get("metadata", {})
                source = meta.get("source", "Unknown")
                page = meta.get("page", "N/A")
                if page == "N/A" and "chunk_index" in meta:
                    page = f"chunk {meta['chunk_index']}"
                formatted_chunks.append(
                    f"[Source: {source}, Page: {page}]\n{chunk.get('content', '')}"
                )
            context_text = "\n\n".join(formatted_chunks)

        # Format recent conversation history (only last message)
        history_text = ""
        if conversation_history:
            history_text = "\n".join(
                f"User: {msg['user']}\nAssistant: {msg['assistant']}"
                for msg in conversation_history[-1:]
            )

        # Short, conversational messages skip context entirely
        context_section = (
            context_text
            if context_text
            else ("" if is_short else "No relevant context found.")
        )

        return f"""{system_prompt}

## Context
{context_section}

## Previous Conversation
{history_text if history_text else "No previous conversation."}

## Question
{query}

## Response
"""