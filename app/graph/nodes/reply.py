from langchain_core.prompts import ChatPromptTemplate
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langchain_core.output_parsers import StrOutputParser
from app.llm.router import llm_router
from app.graph.state import GraphState
import logging
import json

logger = logging.getLogger(__name__)

class ReplyNode:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful facility operations assistant.
You have processed a user request and now need to provide the final response.

User Context:
- Name: {user_name}
- Role: {user_role}
- Company: {company_name}

Context:
- Intent: {intent}
- SQL Query: {sql_query}
- SQL Result: {sql_result}
- SQL Error: {sql_error}
- Workflow Step: {workflow_step}
- Error: {error}

Instructions:
1. Address the user by name ({user_name}) if creating a greeting.
2. **Data Summary**:
   - IF valid SQL Results exist: Provide a concise summary (e.g., "Found 15 tasks...", "3 facilities are overdue..."). Mention key trends.
   - IF NO SQL Results: DO NOT mention "I didn't receive any SQL result". Just proceed with the conversation or ask for clarification naturally.
3. **Errors**:
   - IF there is a specific 'Error' or 'SQL Error': Explain it simply and user-friendly (e.g. "I couldn't find that data").
   - IF no error: Do NOT mention technical statuses.
4. Chat: Respond naturally and professionally.
5. Workflow: Guide the user through the process if active.

CRITICAL STYLE GUIDELINES:
- **HIDE INTERNALS**: Never mention "SQL", "Database", "Query", or "JSON" unless the user is technical.
- **NATURAL FLOW**: If a tool returned nothing, don't complain. Just ask the user for what you need to find it (e.g. "Could you specify which project?").
- **IDs**: NEVER user internal IDs. Use names.
- If the user asks about their company, say the Company Name ("{company_name}"), NOT the ID.

Be concise, professional, and helpful.
"""),
            ("user", "{input}")
        ])

    async def __call__(self, state: GraphState, config: RunnableConfig) -> GraphState:
        try:
            message = state["messages"][-1].content
            model, provider = await llm_router.get_chat_model("reply")
            
            chain = self.prompt | model | StrOutputParser()
            
            # Prepare context for the prompt
            context = {
                "user_name": state.get("user_name", "User"),
                "user_role": state.get("user_role"),
                "company_name": state.get("company_name", "Unknown"),
                "intent": state.get("intent"),
                "sql_query": state.get("sql_query"),
                "sql_result": str(state.get("sql_result", "")), # Convert list/dict to string
                "sql_error": state.get("sql_error"),
                "workflow_step": state.get("workflow_step"),
                "error": state.get("error"),
                "input": message
            }
            
            response = await chain.ainvoke(context, config=config)
            
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
