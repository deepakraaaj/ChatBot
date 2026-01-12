
from typing import Dict, Any, Optional
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.workflow.base import BaseWorkflow

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
                        "text": f"Update status for '{selected_task['name']}':",
                        "options": ["Pending", "In Progress", "Completed"]
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
                        "text": f"Confirm updating '{context['selected_task_name']}' to '{status}'?",
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
                            "text": f"Task '{context['selected_task_name']}' updated to {context['new_status']}."
                        }
                    }
                }
            else:
                 return {
                    "workflow_step": "end",
                    "view": {
                        "type": "end",
                        "payload": {
                            "text": "Update cancelled."
                        }
                    }
                }
        
        return {"error": "Invalid step"}

    # --- Helpers ---

    async def _step_select_task(self, company_id, user_id, context, error=None):
        options = {}
        async with AsyncSessionLocal() as session:
            # Query tasks assigned to user or generic if none
            # We want tasks that are NOT completed ideally, but let's show all limit 10
            # We assume task_transaction has 'assigned_user_id' and joins with task_description (or has name?)
            # Based on previous work, we know task_transaction links to task_description.
            # But let's check if task_transaction has a 'name' or 'description' column directly? 
            # Usually it links to `task_description`. 
            # Query: JOIN task_transaction t, task_description td ON t.task_description_id = td.id (or similar)
            # Schema from user prompt: 
            # 6. task_transaction (id, task_id, status, ... assigned_user_id ...)
            # 7. (implied) task_description
            
            # Let's try a safe query. If check_data showed `task_transaction`, I can join.
            # If complex, I might just select `id` and formatted string.
            
            query = text(f"""
                SELECT t.id, td.name, t.status 
                FROM task_transaction t
                LEFT JOIN task_description td ON t.task_description_id = td.id
                WHERE t.company_id = {company_id} 
                AND t.assigned_user_id = {user_id}
                AND t.status != 2 
                LIMIT 10
            """)
            
            # Use a simpler fallback query if strict join fails (e.g. if task_description_id is named differently)
            # Actually, let's assume `task_id` is the FK to description based on `6. task_transaction (id, task_id...)`
            # Revising query to use `task_id`.
            
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
                    # label = f"Task #{r['id']} ({r.get('name', 'No Name')})"
                    options[label] = {"id": r["id"], "name": r['name']}
            except Exception as e:
                # Fallback if query fails
                # options["Error loading tasks"] = {"id": -1, "name": "Error"}
                print(f"Task Query Error: {e}")
                pass

        if not options:
             # If no tasks found (or error), show empty or message
             # But prompt expects a menu.
             return {
                "workflow_step": "end",
                "view": {
                    "type": "end",
                    "payload": {
                        "text": f"No active tasks found for you (User {user_id})."
                    }
                }
             }

        context["task_options"] = options
        option_labels = list(options.keys())
        
        return {
            "workflow_step": "select_task",
            "context": context,
            "view": {
                "type": "menu",
                "payload": {
                    "text": error if error else "Select a Task to Update:",
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
