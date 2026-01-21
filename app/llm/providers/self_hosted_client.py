
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.settings import settings
from app.core.settings import settings
from app.llm.client import LLMClient
import httpx
from functools import lru_cache

class SelfHostedClient(LLMClient):
    def get_chat_model(self, model_name: Optional[str] = None, temperature: float = 0.7) -> BaseChatModel:
        return ChatOpenAI(
            base_url=settings.self_hosted.base_url,
            api_key=settings.self_hosted.api_key,
            model=model_name or settings.self_hosted.default_model,
            temperature=temperature
        )

    @lru_cache(maxsize=1)
    def get_embeddings(self) -> Embeddings:
         # Assuming local execution means local embeddings are preferred
        return HuggingFaceEmbeddings(model_name=settings.llm.embedding_model)

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{settings.self_hosted.base_url}/models", timeout=2.0)
                return resp.status_code == 200
        except Exception:
            return False
