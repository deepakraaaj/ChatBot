
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from app.core.settings import settings
from app.llm.client import LLMClient

class GeminiClient(LLMClient):
    def get_chat_model(self, model_name: Optional[str] = None, temperature: float = 0.7) -> BaseChatModel:
        # Gemini often uses "gemini-pro" or similar. Default can be overridden.
        model = model_name or "gemini-1.5-flash" 
        return ChatGoogleGenerativeAI(
            google_api_key=settings.gemini.api_key,
            model=model,
            temperature=temperature,
            convert_system_message_to_human=True # Often needed for Gemini
        )

    def get_embeddings(self) -> Embeddings:
        return GoogleGenerativeAIEmbeddings(
            google_api_key=settings.gemini.api_key,
            model="models/embedding-001"
        )

    async def check_health(self) -> bool:
        return bool(settings.gemini.api_key)
