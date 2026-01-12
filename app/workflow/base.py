from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseWorkflow(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the workflow (e.g., 'scheduler')."""
        pass

    @abstractmethod
    async def step(
        self, 
        current_step: Optional[str], 
        user_input: str,
        user_id: str,
        company_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes a single step of the workflow.
        Returns a dict containing 'workflow_step', 'view', and 'context'.
        """
        pass
