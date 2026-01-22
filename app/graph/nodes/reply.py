from langchain_core.prompts import ChatPromptTemplate
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langchain_core.output_parsers import StrOutputParser
from app.llm.router import llm_router
from app.graph.state import GraphState
from app.core.prompts import REPLY_SYSTEM_PROMPT
import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ReplyNode:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", REPLY_SYSTEM_PROMPT),
            ("user", "{input}")
        ])

    async def __call__(self, state: GraphState, config: RunnableConfig) -> GraphState:
        try:
            # [SHORT-CIRCUIT] If a heuristic node (Understanding) already set the final response, 
            # we respect it and return immediately. This is critical for Help/Cancel/Greetings.
            if state.get("final_response"):
                logger.info("ReplyNode: final_response already set, bypassing LLM generation.")
                return {
                    "final_response": state["final_response"],
                    "provider_used": state.get("provider_used", "heuristic")
                }

            message = state["messages"][-1].content
            model, provider = await llm_router.get_chat_model("reply")
            
            chain = self.prompt | model | StrOutputParser()
            
            # Extract workflow instruction
            # Only include instruction if a workflow is actually active
            workflow_instruction = ""
            workflow_options = []
            if state.get("workflow_name") and state.get("workflow_data") and "payload" in state["workflow_data"]:
                payload = state["workflow_data"]["payload"]
                workflow_instruction = payload.get("text", "")
                workflow_options = payload.get("options", [])

            # Prepare context for the prompt
            context = {
                "user_name": state.get("user_name", "User"),
                "user_role": state.get("user_role"),
                "company_name": state.get("company_name", "Unknown"),
                "intent": state.get("intent"),
                "sql_query": state.get("sql_query"),
                "sql_result": str(state.get("sql_result", ""))[:2500], # Convert list/dict to string and TRUNCATE to avoid massive context loop
                "sql_error": state.get("sql_error"),
                "workflow_step": state.get("workflow_step"),
                "workflow_instruction": workflow_instruction,
                "workflow_options": ", ".join(workflow_options) if workflow_options else None,
                "error": state.get("error"),
                "input": message,
                "current_time": (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %I:%M %p")
            }
            
            response = await chain.ainvoke(context, config=config)
            
            # Add pagination hint if more results are available
            has_more = state.get("has_more_results", False)
            if has_more:
                response += "\n\n💡 **Reply 'Show more' to see additional results.**"
            
            return {
                "final_response": response,
                "provider_used": provider
            }

        except Exception as e:
            logger.error(f"Reply generation failed: {e}")
            return {
                "final_response": "I encountered an error while generating the response. Please try again.",
                "error": str(e)
            }
