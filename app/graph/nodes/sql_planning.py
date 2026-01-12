
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from app.llm.router import llm_router
from app.graph.state import GraphState
import logging

logger = logging.getLogger(__name__)

class SQLQuery(BaseModel):
    query: str = Field(..., description="The SQL SELECT query.")
    explanation: str = Field(..., description="Brief explanation of the query logic.")

class SQLPlanningNode:
    def __init__(self):
        self.parser = JsonOutputParser(pydantic_object=SQLQuery)
        
        # Schema context derived from the user's provided DDL
        self.schema_context = """
        KEY TABLES AND COLUMNS:
        
        1. company (id, name, type, is_active)
        2. user (id, email_id, first_name, last_name, company_id, mobile_number, is_active)
        3. facility (id, name, code, company_id, facility_types_id, location_levels_id, is_active)
        4. asset (id, name, code, company_id, asset_category_id, is_active)
        5. location_levels (id, location_name, parent_id, company_id) - Hierarchy of locations
        
        6. task_transaction (id, task_id, status, priority, remarks, scheduled_date, 
           assigned_user_id, facility_id, asset_id, location_level_id, company_id, 
           date_created, date_updated)
           - status: 1=Pending, 2=In Progress, 3=Completed (approx mapping)
           
        7. scheduler (id, name, description, company_id, is_active)
        8. scheduler_details (id, name, facility_id, date, day_of_week, scheduled_ref_no)
        
        9. maintenance_transaction (id, facility_id, comments, transaction_type, date_created, company_id)
        
        10. alert_configuration (id, event_code, subject_template, email_to, is_active)
        
        11. check_list_transaction (id, task_transaction_id, check_list_master_id, status, remarks)
        
        12. ai_conversation_session (id, session_id, user_id, summary)
        
        RELATIONSHIPS:
        - All tables have `company_id` for multi-tenancy.
        - `task_transaction` links to `user` (assigned_user_id), `facility` (facility_id), `asset` (asset_id).
        - `facility` links to `location_levels`.
        """
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert SQL data analyst for a facility operations system.
Your goal is to generate a VALID MySQL SELECT query based on the user's request.

Rules:
1. ONLY generate SELECT statements.
2. NEVER generate INSERT, UPDATE, DELETE, DROP, or ALTER statements.
3. LIMIT results to 200 rows max if not specified.
4. **Human-Readable Columns**: 
   - ALWAYS prefer Name/Code/Description columns over IDs.
   - **JOIN** with related tables to get names.
   - Example 1: `SELECT t.status, u.first_name as assignee FROM task_transaction t LEFT JOIN user u ON t.assigned_user_id = u.id`
   - Example 2: `SELECT f.name as facility_name FROM facility f ...`
   - Avoid selecting raw foreign key IDs (like `assigned_user_id`, `facility_id`) if you can select the name instead.
5. `company_id` Handling:
   - Valid IDs: [56942686, 56942699, 56942704, 56942732, 56942783, 56942784]
   - ONLY filter by `company_id` if the user explicitly mentions a company or if the context clearly implies one.
   - If the request is generic (e.g., "how many facilities"), DO NOT filter by company_id. Query the entire table.
6. Use the provided schema.
7. `status` in task_transaction is usually integer (0=Pending, 1=In Progress, 2=Completed, 3=Overdue).
8. **RBAC Rules**:
   - Current User Role: {user_role}
   - Current User ID: {user_id}
   - **Enforced Company ID**: {company_id}
   - **CRITICAL**: If `Enforced Company ID` is present (not None/unknown), you **MUST** add `AND company_id = {company_id}` to your WHERE clause for ALL tables that have a company_id column. This provides multi-tenancy isolation.
   - If role is 'admin': No user-level restrictions, but MUST still respect `Enforced Company ID` if present.
   - If role is 'user': You MUST filter relevant tables by `assigned_user_id = '{user_id}'` (if applicable) AND `company_id = {company_id}`.
9. **DATE HANDLING (CRITICAL)**:
   - **ALWAYS** convert natural language dates (e.g., "1st Dec", "December 1 2025") to strict `YYYY-MM-DD` format in SQL.
   - Example: "1 december 2025" -> `WHERE scheduled_date LIKE '2025-12-01%'` (using LIKE protects against timestamp mismatch).
   - If the user re-asks for a date that previously returned 0 results, **CHECK AGAIN**. Do not be biased by history saying "no tasks". Trust the database, not the chat history.

10. Schema:
{schema}
"""),
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
            
            chain = self.prompt | model | self.parser
            
            result = await chain.ainvoke({
                "history": history_str,
                "input": last_message,
                "schema": self.schema_context,
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
