
import logging
from typing import Dict, Any, Optional
from app.workflow.flows import AVAILABLE_WORKFLOWS

logger = logging.getLogger(__name__)

class WorkflowEngine:
    def __init__(self):
        self.registry = {wf.name: wf for wf in AVAILABLE_WORKFLOWS}
        logger.info(f"Workflow Engine initialized with: {list(self.registry.keys())}")

    async def get_next_step(
        self, 
        workflow_name: str, 
        current_step: Optional[str], 
        user_input: str,
        user_id: str,
        company_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        workflow = self.registry.get(workflow_name)
        if not workflow:
            return {"error": f"Workflow '{workflow_name}' not found."}

        # Delegate execution to the specific workflow
        return await workflow.step(current_step, user_input, user_id, company_id, context)

workflow_engine = WorkflowEngine()
