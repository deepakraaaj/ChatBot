
import logging
from typing import Optional, Tuple
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from app.core.settings import settings
from app.llm.client import LLMClient
from app.llm.providers.groq_client import GroqClient
from app.llm.providers.gemini_client import GeminiClient
from app.llm.providers.self_hosted_client import SelfHostedClient

logger = logging.getLogger(__name__)

class LLMRouter:
    def __init__(self):
        self.clients = {
            "groq": GroqClient(),
            "gemini": GeminiClient(),
            "self_hosted": SelfHostedClient()
        }

    def get_client(self, provider: str) -> LLMClient:
        return self.clients.get(provider, self.clients[settings.llm.primary_provider])

    async def get_chat_model(self, use_case: str = "understanding") -> Tuple[BaseChatModel, str]:
        """
        Returns (ChatModel, provider_name) based on use_case and fallback logic.
        Fallback chain: Primary -> Fallback -> Production(SelfHosted)
        """
        
        # Determine strict provider if needed (e.g. SQL might force Groq)
        # For now, we follow the general chain unless explicit logic added.
        
        chain = [
            settings.llm.primary_provider, 
            settings.llm.fallback_provider, 
            settings.llm.production_provider
        ]

        # Determine Model Name based on use_case settings
        model_map = {
            "understanding": settings.llm.understanding_model,
            "reply": settings.llm.reply_model,
            "sql": settings.llm.sql_model
        }
        target_model = model_map.get(use_case)

        for provider in chain:
            client = self.clients.get(provider)
            if not client:
                continue
            
            # Simple health check before usage (optional optimization: cache health)
            # In high perf, we might skip this and just try-catch the actual call, 
            # but for robust fallback design, checking availability is good.
            if await client.check_health():
                logger.info(f"Routing to {provider} for {use_case}")
                return client.get_chat_model(model_name=target_model), provider
            else:
                logger.warning(f"Provider {provider} unhealthy, falling back...")

        # If all fail, return primary and hope for best or raise error
        logger.error("All LLM providers failed health checks. Returning primary.")
        return self.clients[settings.llm.primary_provider].get_chat_model(model_name=target_model), settings.llm.primary_provider

    def get_embeddings(self) -> Embeddings:
        provider = settings.llm.embedding_provider
        
        if provider == "local":
            # Use HuggingFace (same as GroqClient logic for now)
            return self.clients["groq"].get_embeddings()
        elif provider == "gemini":
            return self.clients["gemini"].get_embeddings()
        elif provider == "openai":
            # Assuming SelfHosted could be OpenAI compatible or specific
            return self.clients["self_hosted"].get_embeddings()
            
        # Default to local
        return self.clients["groq"].get_embeddings()

llm_router = LLMRouter()
