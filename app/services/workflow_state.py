
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import WorkflowState
import logging

logger = logging.getLogger(__name__)

class WorkflowStateService:
    @staticmethod
    async def load_state(session_id: str) -> dict:
        """
        Returns active workflow state or empty dict.
        """
        state = {}
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowState).where(WorkflowState.session_id == session_id)
                result = await session.execute(stmt)
                record = result.scalars().first()
                
                if record and record.active:
                    state = {
                        "workflow_name": record.workflow_name,
                        "workflow_step": record.current_step,
                        "workflow_context": record.state_data or {}
                    }
        except Exception as e:
            logger.warning(f"Workflow state load failed: {e}")
        
        return state

    @staticmethod
    async def save_state(session_id: str, final_state: dict):
        """
        Updates or creates workflow state record.
        """
        # If no workflow name and no current record, nothing to do.
        # But if we HAVE a record, we might need to deactivate it.
        
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowState).where(WorkflowState.session_id == session_id)
                result = await session.execute(stmt)
                record = result.scalars().first()
                
                wf_name = final_state.get("workflow_name")
                wf_step = final_state.get("workflow_step")
                wf_context = final_state.get("workflow_context")
                is_active = wf_step != "end" if wf_name else False
                
                if record:
                    record.workflow_name = wf_name
                    record.current_step = wf_step
                    record.state_data = wf_context
                    record.active = is_active
                elif wf_name:
                    record = WorkflowState(
                        session_id=session_id,
                        workflow_name=wf_name,
                        current_step=wf_step,
                        state_data=wf_context,
                        active=is_active
                    )
                    session.add(record)
                
                if record:
                    await session.commit()
                
        except Exception as e:
            logger.error(f"Workflow state save failed: {e}")
