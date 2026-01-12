
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from typing import Any, List, Optional
from langchain_core.embeddings import Embeddings

class LLMClient(ABC):
    """
    Abstract Base Class for LLM Providers.
    Wraps LangChain's BaseChatModel and provides a unified interface.
    """

    @abstractmethod
    def get_chat_model(self, model_name: Optional[str] = None, temperature: float = 0.7) -> BaseChatModel:
        """Returns a configured LangChain ChatModel instance."""
        pass

    @abstractmethod
    def get_embeddings(self) -> Embeddings:
        """Returns a configured LangChain Embeddings instance."""
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """Checks if the provider is healthy and reachable."""
        pass
