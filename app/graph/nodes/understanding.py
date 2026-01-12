
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from app.llm.router import llm_router
from app.graph.state import GraphState
from app.core.intents import INTENT_DESCRIPTIONS, INTENT_WORKFLOW_MAP
import logging

logger = logging.getLogger(__name__)

class IntentData(BaseModel):
    intent: str = Field(..., description="The classification of the user's intent. Must be one of: 'chat', 'sql', 'workflow'.")
    parameters: dict = Field(default_factory=dict, description="Any extracted parameters relevant to the intent.")
    reasoning: str = Field(..., description="Brief explanation of why this intent was chosen.")

class UnderstandingNode:
    def __init__(self):
        self.parser = JsonOutputParser(pydantic_object=IntentData)
        
        # Dynamic Prompt Construction
        workflow_descriptions = "\n".join([f"- '{k}': {v}" for k, v in INTENT_DESCRIPTIONS.items()])
        
        system_prompt = f"""You are the brain of a facility operations assistant.
Your job is to classify the user's input into one of three intents: 'sql', 'workflow', or 'chat'.

User Context:
- Name: {{user_name}}
- Role: {{user_role}}
- Company: {{company_name}}

INTENTS:
1. 'sql': User asks for data (e.g., "list work orders", "show logs").
2. 'workflow': User wants to perform an action OR is responding to a workflow prompt.
   - REQUIRED: Return 'workflow' parameter with one of:
{workflow_descriptions}
   - CRITICAL: If the user selects an option (e.g. "Pending", "Task #123"), CLASSIFY AS 'workflow'.
3. 'chat': General conversation, greetings.

OUTPUT FORMAT:
You MUST return a single valid JSON object. Do not include markdown formatting or explanations.
Example:
{{{{
  "intent": "workflow",
  "parameters": {{{{ "workflow": "create_schedule" }}}},
  "reasoning": "User asked to schedule."
}}}}
"""
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Conversation History:\n{history}\n\nCurrent Input: {input}\n\n{format_instructions}")
        ])

    async def __call__(self, state: GraphState) -> GraphState:
        try:
            # Get the last message
            messages = state["messages"]
            last_message = messages[-1].content
            
            # Check for active workflow (Bypass LLM)
            if state.get("workflow_name") and state.get("workflow_step"):
                 logger.info(f"Active workflow detected: {state.get('workflow_name')}. Bypassing intent classification.")
                 return {
                    "intent": "workflow",
                    "parameters": {"workflow": state.get("workflow_name")},
                    "workflow_name": state.get("workflow_name"),
                    "provider_used": "system"
                 }
            
            # Format history (last 5 messages excluding current)
            history_msgs = messages[:-1][-5:] 
            history_str = "\n".join([f"{m.type}: {m.content}" for m in history_msgs])
            
            # [SOFT RECOVERY] Heuristic Check
            # If explicit state is missing, check history for workflow prompts
            # This prevents "Confusion" errors if DB state is lost
            if history_msgs:
                last_system_msg = history_msgs[-1].content
                lower_msg = last_system_msg.lower()
                
                detected_wf = None
                if "assign to user" in lower_msg or "select a slot" in lower_msg or "select a facility" in lower_msg:
                    detected_wf = "scheduler"
                elif "select a task to update" in lower_msg:
                    detected_wf = "update_task"
                
                if detected_wf:
                    logger.info(f"Soft Recovery: Detected implicit workflow '{detected_wf}' from history. Bypassing understanding.")
                    return {
                        "intent": "workflow",
                        # We don't have parameters, but workflow_node handles empty params by checking context or restarting safely
                        "parameters": {"workflow": detected_wf}, 
                        "workflow_name": detected_wf,
                        "provider_used": "heuristic"
                    }
            
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
            
            # Map Intent to Internal Workflow Name
            mapped_wf_name = INTENT_WORKFLOW_MAP.get(wb_param)
            
            return {
                "intent": result["intent"],
                "parameters": params,
                "workflow_name": mapped_wf_name, 
                "provider_used": provider
            }
            
        except Exception as e:
            logger.error(f"Error in UnderstandingNode: {e}", exc_info=True)
            # Fallback to chat if understanding fails
            return {
                "intent": "chat", 
                "error": str(e),
                "provider_used": "fallback"
            }
