from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from app.llm.router import llm_router
from app.graph.state import GraphState
from app.core.intents import INTENT_DESCRIPTIONS, INTENT_WORKFLOW_MAP
from app.core.prompts import UNDERSTANDING_SYSTEM_PROMPT
from app.core.observability import TraceManager
import logging

logger = logging.getLogger(__name__)

class IntentData(BaseModel):
    intent: str = Field(..., description="The classification of the user's intent. Must be one of: 'chat', 'sql', 'workflow'.")
    parameters: dict = Field(default_factory=dict, description="Any extracted parameters relevant to the intent.")
    filters: dict = Field(default_factory=dict, description="Extracted metadata constraints (e.g. status, assignee).")
    reasoning: str = Field(..., description="Brief explanation of why this intent was chosen.")

class UnderstandingNode:
    def __init__(self):
        self.parser = JsonOutputParser(pydantic_object=IntentData)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", UNDERSTANDING_SYSTEM_PROMPT),
            ("user", "Conversation History:\n{history}\n\nCurrent Input: {input}\n\n{format_instructions}")
        ])

    async def __call__(self, state: GraphState) -> GraphState:
        try:
            # 0. [STATE ISOLATION] Clear turn-specific state from previous turn
            # This ensures heuristics and LLM logic are based ONLY on new input
            state_updates = {
                "final_response": None,
                "sql_query": None,
                "sql_result": None,
                "sql_error": None,
                "intent": None,
                "parameters": {},
                "search_filters": {} # Clear filters from previous turn
            }
            
            # Get the last message
            messages = state["messages"]
            last_message = messages[-1].content
            
            # Normalize: Lowercase and strip common punctuation for robust matching
            import string
            lower_input = last_message.lower().strip().strip(string.punctuation)
            
            # 1. [HEURISTIC: Priority Commands] - Help, Greetings, Cancellation
            # These ALWAYS take precedence over active workflows.
            
            # Cancel/Reset
            if lower_input in ["cancel", "stop", "reset", "exit", "quit"]:
                logger.info("Heuristic: Cancel/Reset command detected.")
                updates = {
                    "intent": "chat",
                    "parameters": {},
                    "workflow_name": None,
                    "workflow_step": "end",
                    "workflow_data": None,
                    "final_response": "Okay, I've cancelled the current action. How else can I help you?",
                    "provider_used": "heuristic"
                }
                return {**state_updates, **updates}

            # Help & Greetings (triggers Help Menu)
            help_phrases = [
                "what you can do", "what can you do", "capabilities", 
                "how can you help", "show me workflows", "what are your features",
                "hii", "hello", "hi", "good morning", "good afternoon", "good evening",
                "help", "menu", "options", "what you do"
            ]
            
            # If the input is EXACTLY a greeting or a help keyword, 
            # or if it contains a help phrase, trigger the help workflow.
            is_greeting = lower_input in ["hi", "hii", "hello", "good morning", "good afternoon", "good evening"]
            is_help = any(phrase in lower_input for phrase in help_phrases)
            
            if is_greeting or is_help:
                 logger.info("Heuristic: Help/Capabilities/Greeting request detected.")
                 updates = {
                    "intent": "workflow",
                    "parameters": {"workflow": "help"},
                    "workflow_name": "help",
                    "final_response": None, # Ensure we don't skip help workflow
                    "provider_used": "heuristic"
                }
                 return {**state_updates, **updates}

            # 1b. [HEURISTIC: Common Workflows] - Speed Optimization
            # Avoid LLM call for clear, exact commands
            if "create" in lower_input and "schedule" in lower_input:
                 logger.info("Heuristic: 'Create Schedule' detected.")
                 return {
                     **state_updates,
                     "intent": "workflow",
                     "parameters": {"workflow": "scheduler"},
                     "workflow_name": "scheduler",
                     "provider_used": "heuristic"
                 }
            
            if "status" in lower_input and "update" in lower_input:
                 logger.info("Heuristic: 'Update Status' detected.")
                 return {
                     **state_updates,
                     "intent": "workflow",
                     "parameters": {"workflow": "update_task"},
                     "workflow_name": "update_task",
                     "provider_used": "heuristic"
                 }

            # [HEURISTIC: Avoid Confusion] - Explicitly handle "Create Facility" or "Create Location"
            if "create" in lower_input and ("facility" in lower_input or "location" in lower_input):
                 logger.info("Heuristic: 'Create Facility' detected (Not Supported).")
                 updates = {
                     "intent": "chat", 
                     "final_response": "I cannot create new facilities yet. I can only schedule tasks for existing facilities.",
                     "workflow_name": None,
                     "provider_used": "heuristic"
                 }
                 return {**state_updates, **updates}

            # 2. [PAGINATION DETECTION]
            # If user says "show more", "next", etc., and we have pagination state, continue pagination
            pagination_keywords = ["show more", "more", "next", "continue", "more results"]
            has_pagination_state = state.get("last_query") and state.get("has_more_results")
            
            if any(keyword in lower_input for keyword in pagination_keywords) and has_pagination_state:
                logger.info("Heuristic: Pagination request detected. Continuing with last query.")
                return {
                    "intent": "sql",  # Route to vector_search via sql intent
                    "parameters": {},
                    "provider_used": "heuristic"
                    # Keep pagination_offset and last_query from state
                }
            
            # 3. [ACTIVE WORKFLOW BYPASS]
            current_wf = state.get("workflow_name")
            current_step = state.get("workflow_step")
            
            if current_wf and current_step and current_step != "end":
                 logger.info(f"Active workflow detected: {current_wf}. Bypassing intent classification.")
                 return {
                    "intent": "workflow",
                    "parameters": {"workflow": current_wf},
                    "workflow_name": current_wf,
                    "provider_used": "system"
                 }
            
            # 3. [LLM CLASSIFICATION]
            # Format history (last 5 messages excluding current)
            # Optimization: Truncate very long history messages (e.g. menus) to save tokens
            def truncate(text: str, max_len: int = 500) -> str:
                return text[:max_len] + "..." if len(text) > max_len else text

            history_msgs = messages[:-1][-5:] 
            history_str = "\n".join([f"{m.type}: {truncate(m.content)}" for m in history_msgs])

            # Get model
            model, provider = await llm_router.get_chat_model("understanding")
            
            # Chain
            chain = self.prompt | model | self.parser
            
            # Invoke
            result = await chain.ainvoke({
                "history": history_str,
                "input": last_message,
                "user_name": state.get("user_name"),
                "user_role": state.get("user_role"),
                "company_name": state.get("company_name"),
                "format_instructions": self.parser.get_format_instructions()
            })
            
            logger.info(f"Understanding result: {result}")
            
            params = result.get("parameters", {})
            wb_param = params.get("workflow")
            
            # [FIX] Robust Mapping for Workflow Names
            if wb_param and isinstance(wb_param, str):
                wb_param = wb_param.lower().strip()
                # If exact match fails, try replacing spaces with underscores (common LLM behavior)
                if wb_param not in INTENT_WORKFLOW_MAP and wb_param.replace(" ", "_") in INTENT_WORKFLOW_MAP:
                    wb_param = wb_param.replace(" ", "_")
            
            # Map Intent to Internal Workflow Name
            mapped_wf_name = INTENT_WORKFLOW_MAP.get(wb_param)
            
            logger.info(f"Workflow Mapping: Raw='{params.get('workflow')}' -> Normalized='{wb_param}' -> Mapped='{mapped_wf_name}'")
            
            # Create update dict
            updates = {
                "intent": result["intent"],
                "parameters": params,
                "search_filters": result.get("filters", {}), # Capture filters
                "workflow_name": mapped_wf_name, 
                "provider_used": provider
            }

            # [FIX] Fallback for unmapped workflows
            if updates["intent"] == "workflow" and not mapped_wf_name:
                logger.warning(f"Intent is 'workflow' but mapping failed for param '{wb_param}'. Falling back to Help.")
                updates["workflow_name"] = "help"
                # We do NOT change intent to chat; we let it go to WorkflowNode which will run HelpWorkflow

            
            # Merge with our initial state_updates
            final_updates = {**state_updates, **updates}
            
            # [MONITORING] Structured feature logging
            TraceManager.info(
                f"Feature Detected: {updates['intent']}", 
                feature=updates['intent'], 
                workflow=mapped_wf_name,
                user_id=state.get("user_id")
            )
            
            return final_updates
            
        except Exception as e:
            logger.error(f"Error in UnderstandingNode: {e}", exc_info=True)
            # Fallback to chat if understanding fails
            return {
                "intent": "chat", 
                "error": str(e),
                "workflow_name": None, # [FIX] Clear workflow on fallback
                "provider_used": "fallback"
            }
