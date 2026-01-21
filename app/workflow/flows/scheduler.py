
import logging
from typing import Dict, Any, Optional
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.workflow.base import BaseWorkflow

logger = logging.getLogger(__name__)

class SchedulerWorkflow(BaseWorkflow):
    @property
    def name(self) -> str:
        return "scheduler"

    async def step(
        self, 
        current_step: Optional[str], 
        user_input: str,
        user_id: str,
        company_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        # 0. Start -> Extract fields from initial input if provided, then select slot
        if not current_step:
            context["slot_offset"] = 0
            # Try to extract any fields from the initial request
            extracted = await self._extract_fields_from_input(user_input, company_id)
            if extracted:
                context.update(extracted)
            return await self._step_select_slot(company_id, context)

        # 1. Slot Selected -> Select Facility
        if current_step == "select_slot":
            if user_input.lower() == "more":
                context["slot_offset"] = context.get("slot_offset", 0) + 5
                return await self._step_select_slot(company_id, context)

            selected_slot = self._resolve_selection(user_input, context.get("slot_options", {}))
            if not selected_slot:
                # Reset offset if invalid selection to show start again or keep same? 
                # Keeping same view but showing error
                return await self._step_select_slot(company_id, context, error="Invalid slot. Please select again.")
            
            context["selected_slot_id"] = selected_slot["id"]
            context["selected_slot_name"] = selected_slot["name"]
            
            # Clean up temporary state
            if "slot_offset" in context:
                del context["slot_offset"]

            return await self._step_select_facility(company_id, context)

        # 2. Facility Selected -> Select Task
        if current_step == "select_facility":
            selected_facility = self._resolve_selection(user_input, context.get("facility_options", {}))
            if not selected_facility:
                return await self._step_select_facility(company_id, context, error="Invalid facility. Please select again.")
            
            context["selected_facility_id"] = selected_facility["id"]
            context["selected_facility_name"] = selected_facility["name"]
            
            return await self._step_select_task(company_id, context)

        # 3. Task Selected -> Select Assignee
        if current_step == "select_task":
            selected_task = self._resolve_selection(user_input, context.get("task_options", {}))
            if not selected_task:
                 return await self._step_select_task(company_id, context, error="Invalid task. Please select again.")
            
            context["selected_task_id"] = selected_task["id"]
            context["selected_task_name"] = selected_task["name"]
            
            return await self._step_select_assignee(company_id, context)

        # 4. Assignee Selected -> Capture Estimate
        if current_step == "select_assignee":
            # Assignee is optional (e.g. "skip" or selection)
            selected_assignee = self._resolve_selection(user_input, context.get("assignee_options", {}))
            
            if selected_assignee:
                context["selected_assignee_id"] = selected_assignee["id"]
                context["selected_assignee_name"] = selected_assignee["name"]
            else:
                 # Default to requester if not recognized or 'skip'
                 try:
                    uid = int(user_id) if user_id and str(user_id).isdigit() else 0
                 except:
                    uid = 0
                 
                 context["selected_assignee_id"] = uid
                 context["selected_assignee_name"] = "Myself"

            return {
                "workflow_step": "capture_estimate",
                "context": context,
                "view": {
                    "type": "input",
                    "payload": {
                        "text": f"Almost done! How long do you estimate this will take? (in minutes)"
                    }
                }
            }

        # 5. Estimate Captured -> Auto-Confirm & Write to DB
        if current_step == "capture_estimate":
            context["estimate_duration"] = user_input
            
            # [MODIFICATION] Auto-Confirm requested by user
            await self._write_schedule(user_id, company_id, context)
            
            return {
                "workflow_step": "end",
                "context": context,
                "view": {
                    "type": "end",
                    "payload": {
                        "text": (
                            f"Perfect! I've created your schedule:\n\n"
                            f"📅 **Slot:** {context.get('selected_slot_name')}\n"
                            f"🏢 **Facility:** {context.get('selected_facility_name')}\n"
                            f"✅ **Task:** {context.get('selected_task_name')}\n"
                            f"👤 **Assigned to:** {context.get('selected_assignee_name')}\n"
                            f"⏱️ **Duration:** {context.get('estimate_duration')} minutes\n\n"
                            f"The schedule is now active. Is there anything else I can help you with?"
                        )
                    }
                }
            }
        
        return {"error": "Invalid step"}

    # --- Helpers ---

    async def _step_select_slot(self, company_id, context, error=None):
        options = {}
        offset = context.get("slot_offset", 0)
        has_more = False

        async with AsyncSessionLocal() as session:
            try:
                # Query scheduler_details table for slots
                # Selecting name (readable) as display, id
                query = text(f"SELECT id, name FROM scheduler_details WHERE company_id = {company_id} AND is_active = 1 LIMIT 6 OFFSET {offset}")
                res = await session.execute(query)
                rows = res.mappings().all()
                
                # Check if we have more than 5 items
                if len(rows) > 5:
                    has_more = True
                    rows = rows[:5] # Take first 5
                
                for r in rows:
                    # Use 'name' column for display label
                    name = r["name"]
                    options[name] = {"id": r["id"], "name": name}
            except Exception:
                pass
        
        context["slot_options"] = options
        option_labels = list(options.keys())
        
        if has_more:
            option_labels.append("More")
        
        option_labels.append("Cancel")
        
        return {
            "workflow_step": "select_slot",
            "context": context,
            "view": {
                "type": "menu",
                "payload": {
                    "text": error if error else "I can help you create a schedule. Which time slot would you like?",
                    "options": option_labels
                }
            }
        }

    async def _step_select_facility(self, company_id, context, error=None):
        options = {}
        async with AsyncSessionLocal() as session:
            try:
                res = await session.execute(text(f"SELECT id, name FROM facility WHERE company_id = {company_id} LIMIT 10"))
                rows = res.mappings().all()
                for r in rows:
                    options[r["name"]] = {"id": r["id"], "name": r["name"]}
            except Exception:
                pass
        
        context["facility_options"] = options
        option_labels = list(options.keys())
        option_labels.append("Cancel")
        
        return {
            "workflow_step": "select_facility",
            "context": context,
            "view": {
                "type": "menu",
                "payload": {
                    "text": error if error else f"Got it! Which facility is this for?",
                    "options": option_labels
                }
            }
        }

    async def _step_select_task(self, company_id, context, error=None):
        options = {}
        async with AsyncSessionLocal() as session:
            try:
                 res = await session.execute(text(f"SELECT id, name FROM task_description WHERE company_id = {company_id} LIMIT 10"))
                 rows = res.mappings().all()
                 for r in rows:
                    options[r["name"]] = {"id": r["id"], "name": r["name"]}
            except Exception:
                 pass
        
        if not options:
             params = ["General Maintenance", "Inspection", "Cleaning/Janitorial"]
             for p in params:
                 options[p] = {"id": 0, "name": p}

        context["task_options"] = options
        option_labels = list(options.keys())
        option_labels.append("Cancel")

        return {
            "workflow_step": "select_task",
            "context": context,
            "view": {
                "type": "menu",
                "payload": {
                    "text": error if error else f"Perfect! What task needs to be done at {context.get('selected_facility_name', 'this facility')}?",
                    "options": option_labels
                }
            }
        }

    async def _step_select_assignee(self, company_id, context, error=None):
        options = {}
        async with AsyncSessionLocal() as session:
            try:
                 res = await session.execute(text(f"SELECT id, first_name, last_name FROM user WHERE company_id = {company_id} AND is_active = 1 LIMIT 5"))
                 rows = res.mappings().all()
                 for r in rows:
                    full_name = f"{r['first_name']} {r['last_name'] or ''}".strip()
                    options[full_name] = {"id": r["id"], "name": full_name}
            except Exception:
                 pass
        
        # Add special option
        options["Myself"] = {"id": 0, "name": "Myself"}

        context["assignee_options"] = options
        option_labels = list(options.keys())
        option_labels.append("Cancel")

        return {
            "workflow_step": "select_assignee",
            "context": context,
            "view": {
                "type": "menu",
                "payload": {
                    "text": error if error else f"Great! Who should handle '{context.get('selected_task_name', 'this task')}'?",
                    "options": option_labels
                }
            }
        }

    def _resolve_selection(self, user_input, options):
        """
        Intelligently resolve user selection with fuzzy matching.
        Handles typos, variations, and partial matches.
        """
        if not options:
            return None
            
        user_input_lower = user_input.lower().strip()
        
        # 1. Exact match (case-insensitive)
        for k, v in options.items():
            if k.lower() == user_input_lower:
                return v
        
        # 2. Check if user input is a number (task ID or option number)
        if user_input.isdigit():
            # Try to match by ID if the option has an ID
            for k, v in options.items():
                if isinstance(v, dict) and v.get("id") == int(user_input):
                    return v
            # Try to match by position (1-indexed)
            try:
                idx = int(user_input) - 1
                if 0 <= idx < len(options):
                    return list(options.values())[idx]
            except:
                pass
        
        # 3. Fuzzy matching using difflib
        from difflib import get_close_matches
        
        # Get all option keys
        option_keys = list(options.keys())
        
        # Find close matches (threshold 0.6 = 60% similarity)
        close_matches = get_close_matches(user_input, option_keys, n=1, cutoff=0.6)
        
        if close_matches:
            return options[close_matches[0]]
        
        # 4. Partial match - check if user input is contained in any option
        for k, v in options.items():
            if user_input_lower in k.lower():
                return v
        
        # 5. Check if option name is contained in user input
        for k, v in options.items():
            if k.lower() in user_input_lower:
                return v
        
        return None

    async def _extract_fields_from_input(self, user_input: str, company_id: str) -> Dict[str, Any]:
        """
        Intelligently extract fields from natural language input.
        Example: "Create schedule for John to fix AC at Building A"
        Extracts: assignee=John, task=fix AC, facility=Building A
        """
        extracted = {}
        lower_input = user_input.lower()
        
        # Try to extract facility name
        async with AsyncSessionLocal() as session:
            try:
                # Get all facilities for this company
                res = await session.execute(text(f"SELECT id, name FROM facility WHERE company_id = {company_id} LIMIT 20"))
                facilities = res.mappings().all()
                
                for fac in facilities:
                    if fac["name"].lower() in lower_input:
                        extracted["selected_facility_id"] = fac["id"]
                        extracted["selected_facility_name"] = fac["name"]
                        break
                
                # Try to extract assignee
                res = await session.execute(text(f"SELECT id, first_name, last_name FROM user WHERE company_id = {company_id} AND is_active = 1 LIMIT 20"))
                users = res.mappings().all()
                
                for user in users:
                    full_name = f"{user['first_name']} {user['last_name'] or ''}".strip()
                    first_name = user['first_name'].lower()
                    
                    if first_name in lower_input or full_name.lower() in lower_input:
                        extracted["selected_assignee_id"] = user["id"]
                        extracted["selected_assignee_name"] = full_name
                        break
                
                # Try to extract task
                res = await session.execute(text(f"SELECT id, name FROM task_description WHERE company_id = {company_id} LIMIT 20"))
                tasks = res.mappings().all()
                
                for task in tasks:
                    if task["name"].lower() in lower_input:
                        extracted["selected_task_id"] = task["id"]
                        extracted["selected_task_name"] = task["name"]
                        break
                        
            except Exception as e:
                logger.error(f"Error extracting fields: {e}")
        
        return extracted

    async def _write_schedule(self, user_id, company_id, context):
        try:
            fid = context.get("selected_facility_id")
            tid = context.get("selected_task_id") or 0
            aid = context.get("selected_assignee_id")
            if aid == 0 and user_id and str(user_id).isdigit():
                 aid = int(user_id) # Fallback to creator if "Myself"
            
            duration = context.get("estimate_duration", "0")
            remarks = f"Scheduled via AI. Slot: {context.get('selected_slot_name')}, Duration: {duration}"

            logger.info(f"Writing Schedule: User={user_id}, FID={fid}, TID={tid}, AID={aid}, Duration={duration}")

            async with AsyncSessionLocal() as session:
                 async with session.begin():
                     sql_query = text("""
                        INSERT INTO task_transaction 
                        (status, priority, remarks, assigned_user_id, facility_id, company_id, date_created)
                        VALUES 
                        (:status, :priority, :remarks, :aid, :fid, :company_id, NOW())
                     """)
                     params = {
                         "status": 0,
                         "priority": 1,
                         "remarks": remarks,
                         "aid": aid,
                         "fid": fid,
                         "company_id": company_id
                     }
                     logger.info(f"Executing SQL with params: {params}")
                     await session.execute(sql_query, params)
            
            logger.info("Schedule successfully written to DB.")

        except Exception as e:
            logger.error(f"Failed to write schedule: {e}", exc_info=True)
            raise e
