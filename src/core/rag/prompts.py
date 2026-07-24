from typing import List, Dict, Any

class PromptBuilder:
    SYSTEM_PROMPT = """You are Plantie AI, an expert agricultural assistant.

You have access to a knowledge base about farming, plant diseases, treatments, and best practices.

Your responses should be:
- **Accurate** and based on the provided context
- **Practical** and actionable
- **Conversational** and helpful
- **Safe** - if you're unsure, say so

If the user asks about something not in the context, use your general knowledge.
Always consider the user's location (if provided) for personalized advice."""

    def build(
            self,
            query: str,
            context: List[Dict[str, Any]],
            conversation_history: List[Dict[str, str]] = None
    ) -> str:
        # Format context with safe access
        context_text = ""
        if context:
            formatted_chunks = []
            for chunk in context[:5]:
                meta = chunk.get('metadata', {})
                source = meta.get('source', 'Unknown')
                page = meta.get('page', 'N/A')        # fallback if missing
                # If page is not present, try chunk_index
                if page == 'N/A' and 'chunk_index' in meta:
                    page = f"chunk {meta['chunk_index']}"
                formatted_chunks.append(
                    f"[Source: {source}, Page: {page}]\n{chunk.get('content', '')}"
                )
            context_text = "\n\n".join(formatted_chunks)

        # Format conversation history (unchanged)
        history_text = ""
        if conversation_history:
            history_text = "\n".join([
                f"User: {msg['user']}\nAssistant: {msg['assistant']}"
                for msg in conversation_history[-5:]
            ])

        return f"""{self.SYSTEM_PROMPT}

## Context
{context_text if context_text else "No relevant context found."}

## Previous Conversation
{history_text if history_text else "No previous conversation."}

## Question
{query}

## Response
"""