
from typing import Dict, Any, Optional
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.workflow.base import BaseWorkflow
import logging

logger = logging.getLogger(__name__)

class UpdateTaskWorkflow(BaseWorkflow):
    @property
    def name(self) -> str:
        return "update_task"

    async def step(
        self, 
        current_step: Optional[str], 
        user_input: str,
        user_id: str,
        company_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        # 1. Start -> Select Task
        if not current_step:
            return await self._step_select_task(company_id, user_id, context)

        # 2. Task Selected -> Select Status
        if current_step == "select_task":
            # context["task_options"] populated in previous step
            selected_task = self._resolve_selection(user_input, context.get("task_options", {}))
            
            if not selected_task:
                 return await self._step_select_task(company_id, user_id, context, error="Invalid task. Please select again.")
            
            context["selected_task_id"] = selected_task["id"]
            context["selected_task_name"] = selected_task["name"]
            
            return {
                "workflow_step": "select_status",
                "context": context,
                "view": {
                    "type": "menu",
                    "payload": {
                        "text": f"Got it! What's the new status for '{selected_task['name']}'?",
                        "options": ["Pending", "In Progress", "Completed", "Cancel"]
                    }
                }
            }

        # 3. Status Selected -> Confirmation
        if current_step == "select_status":
            valid_statuses = ["Pending", "In Progress", "Completed"]
            status = user_input.title()
            if status not in valid_statuses:
                 return {
                    "workflow_step": "select_status",
                    "context": context,
                    "view": {
                        "type": "menu",
                        "payload": {
                            "text": "Invalid status. Please select:",
                            "options": valid_statuses
                        }
                    }
                 }
            
            context["new_status"] = status
            
            return {
                "workflow_step": "confirm",
                "context": context,
                "view": {
                    "type": "menu",
                    "payload": {
                        "text": f"Perfect! Just to confirm - I'll update '{context['selected_task_name']}' to '{status}'. Is that correct?",
                        "options": ["Confirm", "Cancel"]
                    }
                }
            }

        # 4. Confirmed -> Update DB
        if current_step == "confirm":
            if user_input.lower() == "confirm":
                await self._update_task_status(context)
                return {
                    "workflow_step": "end",
                    "context": context,
                    "view": {
                        "type": "end",
                        "payload": {
                            "text": f"✅ Done! I've updated '{context['selected_task_name']}' to {context['new_status']}. Anything else I can help with?"
                        }
                    }
                }
            else:
                 return {
                    "workflow_step": "end",
                    "view": {
                        "type": "end",
                        "payload": {
                            "text": "No problem! Update cancelled. Let me know if you need anything else."
                        }
                    }
                }
        
        return {"error": "Invalid step"}

    # --- Helpers ---

    async def _step_select_task(self, company_id, user_id, context, error=None):
        options = {}
        async with AsyncSessionLocal() as session:
            # Query tasks assigned to user or generic if none
            # Query tasks assigned to user or generic if none
            query = text(f"""
                SELECT t.id, td.name, t.status 
                FROM task_transaction t
                JOIN task_description td ON t.task_description_id = td.id
                WHERE t.company_id = {company_id} 
                AND t.assigned_user_id = {user_id}
                AND t.status != 2 
                ORDER BY t.date_created DESC
                LIMIT 10
            """)
            
            try:
                res = await session.execute(query)
                rows = res.mappings().all()
                for r in rows:
                    # Status mapping for display
                    status_map = {0: "Pending", 1: "In Progress"}
                    status_str = status_map.get(r['status'], "Unknown")
                    
                    # Logic to display: "Pump Maintenance (#123) - Pending"
                    label = f"{r['name']} (#{r['id']}) - {status_str}"
                    options[label] = {"id": r["id"], "name": r['name']}
            except Exception as e:
                # Fallback if query fails
                # options["Error loading tasks"] = {"id": -1, "name": "Error"}
                logger.error(f"Task Query Error: {e}")
                pass

        if not options:
             # If no tasks found (or error), show empty or message
             # But prompt expects a menu.
             return {
                "workflow_step": "end",
                "view": {
                    "type": "end",
                    "payload": {
                        "text": f"I couldn't find any active tasks assigned to you. Would you like me to help you with something else?"
                    }
                }
             }

        context["task_options"] = options
        option_labels = list(options.keys())
        option_labels.append("Cancel")
        
        return {
            "workflow_step": "select_task",
            "context": context,
            "view": {
                "type": "menu",
                "payload": {
                    "text": error if error else "I can help you update a task. Which one would you like to update?",
                    "options": option_labels
                }
            }
        }

    def _resolve_selection(self, user_input, options):
        if user_input in options:
            return options[user_input]
        for k, v in options.items():
            if k.lower() == user_input.lower():
                return v
        return None

    async def _update_task_status(self, context):
        task_id = context.get("selected_task_id")
        new_status_str = context.get("new_status")
        
        # Map string to int
        status_map = {"Pending": 0, "In Progress": 1, "Completed": 2}
        status_int = status_map.get(new_status_str, 1)

        async with AsyncSessionLocal() as session:
             async with session.begin():
                 await session.execute(text(f"""
                    UPDATE task_transaction 
                    SET status = {status_int}, date_updated = NOW()
                    WHERE id = {task_id}
                 """))
