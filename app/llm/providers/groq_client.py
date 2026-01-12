
from typing import Optional
from langchain_groq import ChatGroq
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.settings import settings
from app.llm.client import LLMClient

class GroqClient(LLMClient):
    def get_chat_model(self, model_name: Optional[str] = None, temperature: float = 0.7) -> BaseChatModel:
        return ChatGroq(
            groq_api_key=settings.groq.api_key,
            model_name=model_name or settings.groq.default_model,
            temperature=temperature
        )

    def get_embeddings(self) -> Embeddings:
        # Groq doesn't have native embeddings, using local HF as per requirements
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    async def check_health(self) -> bool:
        try:
            # Simple check, maybe listing models or basic completion
            # For now, just assuming true if key exists, real check would api call
            return bool(settings.groq.api_key)
        except Exception:
            return False
