
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from app.llm.router import llm_router
from app.graph.state import GraphState
from app.services.schema import SchemaService
from app.core.prompts import SQL_PLANNING_SYSTEM_PROMPT
import logging

logger = logging.getLogger(__name__)

class SQLQuery(BaseModel):
    query: str = Field(..., description="The SQL SELECT query.")
    explanation: str = Field(..., description="Brief explanation of the query logic.")

class SQLPlanningNode:
    def __init__(self):
        self.parser = JsonOutputParser(pydantic_object=SQLQuery)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SQL_PLANNING_SYSTEM_PROMPT),
            ("user", "Conversation History:\n{history}\n\nCurrent Request: {input}\n\n{format_instructions}")
        ])

    async def __call__(self, state: GraphState) -> GraphState:
        try:
            messages = state["messages"]
            last_message = messages[-1].content
            
            user_id = state.get("user_id", "unknown")
            user_role = state.get("user_role", "user") 
            company_id = state.get("company_id") # extracted from user lookup

            # Format history (last 5 messages excluding current)
            history_msgs = messages[:-1][-5:] 
            history_str = "\n".join([f"{m.type}: {m.content}" for m in history_msgs])

            model, provider = await llm_router.get_chat_model("sql")
            
            # Fetch dynamic schema
            schema_context = await SchemaService.get_schema()
            
            chain = self.prompt | model | self.parser
            
            result = await chain.ainvoke({
                "history": history_str,
                "input": last_message,
                "schema": schema_context,
                "user_id": user_id,
                "user_role": user_role,
                "company_id": company_id or "None",
                "format_instructions": self.parser.get_format_instructions()
            })
            
            # Security Check
            query = result["query"]
            if not query.lower().strip().startswith("select"):
                raise ValueError("Generated SQL is not a SELECT statement.")
            
            return {
                "sql_query": query,
                "provider_used": provider
            }
            
        except Exception as e:
            logger.error(f"SQL Planning failed: {e}")
            return {
                "error": f"Failed to generate SQL: {str(e)}",
                "sql_query": None
            }
