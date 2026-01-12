
from app.workflow.engine import workflow_engine
from app.graph.state import GraphState
import logging

logger = logging.getLogger(__name__)

class WorkflowNode:
    async def __call__(self, state: GraphState) -> GraphState:
        wf_name = state.get("workflow_name")
        curr_step = state.get("workflow_step")
        msg = state["messages"][-1].content
        
        # Context extraction
        user_id = state.get("user_id")
        company_id = state.get("company_id")
        wf_context = state.get("workflow_context") or {}

        if not wf_name:
            # Start new workflow (default to scheduler for now)
            wf_name = "scheduler"
            curr_step = None 
        
        # Progress
        result = await workflow_engine.get_next_step(
            workflow_name=wf_name, 
            current_step=curr_step, 
            user_input=msg,
            user_id=user_id,
            company_id=company_id,
            context=wf_context
        )
        
        # Extract text for chat history
        view_data = result.get("view", {})
        response_text = "Workflow Updated."
        if view_data and "payload" in view_data:
            response_text = view_data["payload"].get("text", "Workflow Updated.")
        
        return {
            "workflow_name": wf_name, # Persist name if started
            "workflow_step": result.get("workflow_step"),
            "workflow_data": result.get("view"),
            "workflow_context": result.get("context", wf_context), # Update context
            "final_response": response_text # [FIX] Save actual question to history
        }
